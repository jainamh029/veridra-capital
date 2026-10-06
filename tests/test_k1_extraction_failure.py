"""Module 5 — K-1 Routing: model-unavailable behaviour + retry + concurrency.

The production ingestion path has NO regex fallback. If the extraction model is
unreachable the document lands in AWAITING_EXTRACTION with nothing regex-derived
stored, and is picked up by retry_pending() when the model is back.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from k1_routing import core as k1_core
from k1_routing import service as k1_service
from k1_routing import store as k1_store
from k1_routing.synthetic import SYNTHETIC_K1_DOCS

CLEAN = SYNTHETIC_K1_DOCS[0]          # K1-0001, expects ROUTED -> FUND-01 / LP-001
CLEAN2 = SYNTHETIC_K1_DOCS[1]         # K1-0002, expects ROUTED -> FUND-01 / LP-002
UNKNOWN = SYNTHETIC_K1_DOCS[8]        # K1-0009, expects NEEDS_REVIEW / fund_not_matched


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(k1_store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(k1_store, "EVENTS_LOG", str(tmp_path / "k1_events.jsonl"))
    k1_service._DOC_LOCKS.clear()
    return str(tmp_path)


def _down(_text):
    raise ConnectionError("Connection refused (simulated Ollama outage)")


# ------------------------------------------------------- Step 1: no silent fallback
def test_extract_k1_raises_and_never_falls_back_on_model_failure():
    with pytest.raises(k1_core.ExtractionUnavailable):
        k1_core.extract_k1(CLEAN["text"], extractor=_down)


def test_ingest_document_never_auto_invokes_regex(monkeypatch):
    """regex_extract_explicit must not run from the ingest path even when the
    model is down."""
    called = []
    real_regex = k1_core.regex_extract_explicit
    monkeypatch.setattr(k1_core, "regex_extract_explicit",
                        lambda t: called.append(t) or real_regex(t))
    monkeypatch.setattr(k1_core, "_model_extractor", _down)      # model is "down"

    import tempfile
    d = tempfile.mkdtemp()
    k1_store.reset(data_dir=d)
    rec = k1_service.ingest_document(CLEAN["text"], doc_id="D", data_dir=d)
    assert rec["status"] == "AWAITING_EXTRACTION"
    assert called == [], "regex extraction was auto-invoked from the ingest path"


# ------------------------------------------------------- Step 2/4: await + recover
def test_model_down_lands_in_awaiting_with_no_regex_data_stored(scratch):
    rec = k1_service.ingest_document(CLEAN["text"], doc_id="D1", case="clean",
                                     extractor=_down, data_dir=scratch)

    assert rec["status"] == "AWAITING_EXTRACTION"
    assert rec["status"] not in ("ROUTED", "NEEDS_REVIEW")
    assert rec["extracted"] is None                       # nothing produced
    assert rec["matched_fund"] is None and rec["matched_lp"] is None
    assert rec["review_reason"] is None
    assert "Connection refused" in rec["extraction_error"]

    # and NOTHING regex-shaped anywhere in the raw event log for this doc
    for e in k1_store.events_for("D1", data_dir=scratch):
        assert e["event"] in ("RECEIVED", "AWAITING_EXTRACTION")
        assert "regex" not in str(e).lower()
        assert e.get("extracted") in (None, {})           # RECEIVED stores no extraction
    assert [e["event"] for e in k1_store.events_for("D1", data_dir=scratch)] == \
        ["RECEIVED", "AWAITING_EXTRACTION"]


def test_retry_pending_resolves_awaiting_records_when_model_returns(scratch):
    # two docs land AWAITING while the model is down
    k1_service.ingest_document(CLEAN["text"], doc_id="D1", case="clean",
                               extractor=_down, data_dir=scratch)
    k1_service.ingest_document(UNKNOWN["text"], doc_id="D2", case="unknown_fund",
                               extractor=_down, data_dir=scratch)
    pend = [r for r in k1_service.list_records(data_dir=scratch)
            if r["status"] == "AWAITING_EXTRACTION"]
    assert {r["doc_id"] for r in pend} == {"D1", "D2"}

    # model is back -> retry with a working (injected) extractor
    out = k1_service.retry_pending(extractor=k1_core.regex_extract_explicit, data_dir=scratch)
    assert out["attempted"] == 2 and out["resolved"] == 2 and out["still_awaiting"] == 0

    d1 = k1_service.get_record("D1", data_dir=scratch)
    d2 = k1_service.get_record("D2", data_dir=scratch)
    # each reached its CORRECT final state, exactly as if the model had been up
    assert d1["status"] == "ROUTED"
    assert d1["matched_fund"]["fund_id"] == "FUND-01" and d1["matched_lp"]["lp_id"] == "LP-001"
    assert d2["status"] == "NEEDS_REVIEW" and d2["review_reason"] == "fund_not_matched"
    # the AWAITING_EXTRACTION event is still in the log (append-only) but superseded
    assert [e["event"] for e in k1_store.events_for("D1", data_dir=scratch)] == \
        ["RECEIVED", "AWAITING_EXTRACTION", "ROUTED"]
    assert d1["retry_count"] == 1


def test_retry_that_still_fails_stays_awaiting(scratch):
    k1_service.ingest_document(CLEAN["text"], doc_id="D1", extractor=_down, data_dir=scratch)
    out = k1_service.retry_pending(extractor=_down, data_dir=scratch)   # still down
    assert out["resolved"] == 0 and out["still_awaiting"] == 1
    assert k1_service.get_record("D1", data_dir=scratch)["status"] == "AWAITING_EXTRACTION"


# ------------------------------------------------------- Item B: concurrency
def test_concurrent_retry_pending_does_not_double_resolve_one_doc(scratch):
    """The realistic race: a periodic retry-pending fires while someone also
    triggers one manually. Both would re-attempt the same AWAITING doc."""
    k1_service.ingest_document(CLEAN["text"], doc_id="D1", extractor=_down, data_dir=scratch)

    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        return k1_service.retry_pending(extractor=k1_core.regex_extract_explicit,
                                        data_dir=scratch)

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(worker) for _ in range(2)]
        outs = [f.result() for f in futs]

    evs = k1_store.events_for("D1", data_dir=scratch)
    outcome_events = [e for e in evs if e["event"] in ("ROUTED", "NEEDS_REVIEW")]
    assert len(outcome_events) == 1, f"doc resolved more than once: {[e['event'] for e in evs]}"
    assert [e["event"] for e in evs] == ["RECEIVED", "AWAITING_EXTRACTION", "ROUTED"]
    # both callers observe it resolved (idempotent); the outcome was appended once
    assert all(o["attempted"] == 1 for o in outs)
    # seq numbers stayed unique + contiguous (locked append)
    seqs = [e["seq"] for e in k1_store.all_events(data_dir=scratch)]
    assert seqs == sorted(seqs) == list(range(1, len(seqs) + 1))
    assert k1_service.get_record("D1", data_dir=scratch)["status"] == "ROUTED"


def test_concurrent_duplicate_ingest_of_same_doc_id_makes_one_record(scratch):
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        return k1_service.ingest_document(CLEAN["text"], doc_id="DUP", case="clean",
                                          extractor=k1_core.regex_extract_explicit,
                                          data_dir=scratch)

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(worker) for _ in range(2)]
        [f.result() for f in futs]

    evs = k1_store.events_for("DUP", data_dir=scratch)
    assert [e["event"] for e in evs].count("RECEIVED") == 1, "duplicate RECEIVED events"
    assert [e["event"] for e in evs].count("ROUTED") == 1, "duplicate outcome events"
    recs = [r for r in k1_service.list_records(data_dir=scratch) if r["doc_id"] == "DUP"]
    assert len(recs) == 1 and recs[0]["status"] == "ROUTED"


def test_negative_proof_removing_the_lock_reintroduces_the_double_resolve(scratch, monkeypatch):
    """Neuter the per-doc lock -> two concurrent retries both append an outcome."""
    import contextlib
    monkeypatch.setattr(k1_service, "_doc_lock", lambda _id: contextlib.nullcontext())

    saw_double = False
    for _ in range(20):
        k1_store.reset(data_dir=scratch)
        k1_service.ingest_document(CLEAN["text"], doc_id="D", extractor=_down, data_dir=scratch)
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            k1_service.retry_pending(extractor=k1_core.regex_extract_explicit, data_dir=scratch)

        with ThreadPoolExecutor(max_workers=2) as ex:
            [ex.submit(worker) for _ in range(2)]
        n_out = sum(1 for e in k1_store.events_for("D", data_dir=scratch)
                    if e["event"] in ("ROUTED", "NEEDS_REVIEW"))
        if n_out > 1:
            saw_double = True
            break
    assert saw_double, "removing _doc_lock did not reproduce the race — lock isn't load-bearing"


def test_doc_lock_is_scoped_per_document_not_a_global_lock(scratch, capsys):
    """Hold _doc_lock for D1 (simulating D1 mid-retry) and, at the same time, run a
    direct retry on a DIFFERENT doc D2. D2 must finish promptly — it must NOT wait
    for D1's lock. (retry_pending() iterates docs sequentially, so a direct
    _attempt_extraction on D2 isolates the lock's scope, which is what's under test.)"""
    k1_service.ingest_document(CLEAN["text"], doc_id="D1", extractor=_down, data_dir=scratch)
    k1_service.ingest_document(CLEAN2["text"], doc_id="D2", extractor=_down, data_dir=scratch)
    assert k1_service.get_record("D1", data_dir=scratch)["status"] == "AWAITING_EXTRACTION"
    assert k1_service.get_record("D2", data_dir=scratch)["status"] == "AWAITING_EXTRACTION"

    HOLD_D1_SECONDS = 0.5                       # D1's lock is deliberately held this long
    holding_d1 = threading.Event()
    t = {}
    t0 = time.perf_counter()

    def hold_d1_lock():
        with k1_service._doc_lock("D1"):
            t["d1_locked_at"] = time.perf_counter() - t0
            holding_d1.set()
            time.sleep(HOLD_D1_SECONDS)         # hold it, unrelated to anything D2 does
        t["d1_lock_released_at"] = time.perf_counter() - t0

    def retry_d2():
        assert holding_d1.wait(timeout=5)       # only start once D1's lock is definitely held
        s = time.perf_counter()
        rec = k1_service._attempt_extraction(
            "D2", CLEAN2["text"], extractor=k1_core.regex_extract_explicit, data_dir=scratch)
        t["d2_done_at"] = time.perf_counter() - t0
        t["d2_elapsed"] = time.perf_counter() - s
        t["d2_status"] = rec["status"]
        t["d2_fund"] = rec["matched_fund"]["fund_id"]
        t["d2_lp"] = rec["matched_lp"]["lp_id"]

    a = threading.Thread(target=hold_d1_lock)
    b = threading.Thread(target=retry_d2)
    a.start()
    b.start()
    b.join(timeout=3)
    b_finished_while_d1_locked = not b.is_alive() and "d1_lock_released_at" not in t
    a.join(timeout=3)

    print(f"\n  D1 lock acquired   @ {t['d1_locked_at']*1000:7.1f} ms   (held for {HOLD_D1_SECONDS*1000:.0f} ms)")
    print(f"  D2 retry finished  @ {t['d2_done_at']*1000:7.1f} ms   (took {t['d2_elapsed']*1000:.2f} ms)"
          f"  -> {t['d2_status']} {t['d2_fund']}/{t['d2_lp']}")
    print(f"  D1 lock released   @ {t['d1_lock_released_at']*1000:7.1f} ms")
    print(f"  => D2 completed {(t['d1_lock_released_at'] - t['d2_done_at'])*1000:.1f} ms BEFORE "
          f"D1's (unrelated) lock was released — not serialised")

    assert b_finished_while_d1_locked, \
        "D2's retry blocked while an UNRELATED doc's lock was held — _doc_lock is global!"
    assert t["d2_status"] == "ROUTED" and t["d2_fund"] == "FUND-01" and t["d2_lp"] == "LP-002"
    assert t["d2_elapsed"] < 0.1, f"D2 retry took {t['d2_elapsed']:.3f}s — suspiciously slow"
    assert t["d2_done_at"] < t["d1_lock_released_at"] - 0.3, \
        "D2 did not clearly finish before D1's lock released — locks may be serialised"
    # D1 is untouched by D2's retry — still awaiting
    assert k1_service.get_record("D1", data_dir=scratch)["status"] == "AWAITING_EXTRACTION"
