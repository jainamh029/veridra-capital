"""Concurrency: two simultaneous decisions on one approval record.

Observed BEFORE the fix (40/40 runs, threads + barrier, calling record_decision
directly): BOTH requests returned success, the events log got TWO DECIDED events
for the same record, and the two events collided on the same `seq`. The JSONL
file was not line-corrupted (the write itself is locked) but the audit trail was
logically corrupted — one record "decided" twice, by two people, to two states.

Root cause: check-then-append race in record_decision (read state -> check
PENDING -> append), with nothing atomic between the read and the write; plus a
non-atomic `seq = count + 1` in store.append_event.

Fix: a per-record lock (approvals.service._record_lock) around the check-and-
append, and `seq` computed under store._LOCK. Single-process only — documented in
both modules. These tests hold it to the UI-contract-test standard: a
negative-proof test deliberately removes the lock and confirms the race returns.
"""
import contextlib
import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from approvals import service as A
from approvals import store
from approvals.model import ApprovalState


def _po(decision="BLOCK", fund_id="FUND-01"):
    return {
        "status": "OK", "decision": decision, "overall_severity": "high",
        "fraud": decision != "PASS", "fraud_type": None, "fraud_labels": [],
        "failed_checks": ["sender_domain_match"], "confidence": "high",
        "extracted": {"fund_name": "Fieldstone Equity Partners II", "entity": "x",
                      "amount": 1000, "bank_name": "b", "routing_number": "011401533",
                      "account_number": "a"},
        "fund_baseline": {"fund_id": fund_id, "fund_name": "Fieldstone Equity Partners II"},
        "checks": {"routing_checksum": {"passed": True}},
        "alert": {"subject": "s", "body": "b"},
    }


@pytest.fixture
def scratch():
    d = tempfile.mkdtemp(prefix="conc_test_")
    store.reset(data_dir=d)
    A.set_notifier(None)
    A._RECORD_LOCKS.clear()
    yield d
    A.set_notifier(None)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def _race_same_record(aid, data_dir, states=("APPROVED", "REJECTED")):
    """Fire len(states) decides at one record, released together by a barrier."""
    barrier = threading.Barrier(len(states))
    results = {}

    def worker(i, state):
        barrier.wait()
        try:
            r = A.record_decision(aid, state, f"w{i}@x.example", f"n{i}", data_dir=data_dir)
            results[i] = ("OK", r["state"], r["decision_by"])
        except A.AlreadyDecidedError:
            results[i] = ("409", None, None)
        except Exception as e:  # pragma: no cover - surfaced as a test failure
            results[i] = ("ERR", f"{type(e).__name__}: {e}", None)

    with ThreadPoolExecutor(max_workers=len(states)) as ex:
        for i, s in enumerate(states):
            ex.submit(worker, i, s)
    return results


# --- 1. HTTP level: exactly one 200, one 409 ---------------------------------
def test_simultaneous_http_decides_one_wins(scratch, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(scratch))
    monkeypatch.setattr(store, "REPORTS_LOG", os.path.join(scratch, "verification_reports.jsonl"))
    monkeypatch.setattr(store, "EVENTS_LOG", os.path.join(scratch, "approval_events.jsonl"))
    monkeypatch.setattr(A, "_notifier", type("S", (A.NotificationSender,),
                                             {"notify": lambda s, r: None})())

    rec = A.ingest_pipeline_output(_po())
    from fastapi.testclient import TestClient

    from agents.app import app
    client = TestClient(app)

    barrier = threading.Barrier(2)
    codes = {}

    def hit(i, state):
        barrier.wait()
        r = client.post(f"/approvals/{rec.approval_id}/decide",
                        json={"state": state, "approver": f"w{i}@x.example", "note": "n"})
        codes[i] = r.status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        ex.submit(hit, 0, "APPROVED")
        ex.submit(hit, 1, "REJECTED")

    assert sorted(codes.values()) == [200, 409], codes


# --- 2. audit-log integrity over many simultaneous races --------------------
def test_same_record_race_keeps_one_decision_and_clean_seq(scratch):
    for _ in range(25):
        store.reset(data_dir=scratch)
        A._RECORD_LOCKS.clear()
        aid = A.ingest_pipeline_output(_po(), data_dir=scratch).approval_id

        results = _race_same_record(aid, scratch)
        tags = sorted(v[0] for v in results.values())
        assert tags == ["409", "OK"], f"expected one OK + one 409, got {results}"

        evs = store.events_for(aid, data_dir=scratch)
        decided = [e for e in evs if e["event"] == "DECIDED"]
        assert len(decided) == 1, f"{len(decided)} DECIDED events for one record"

        # the winner reported by the OK call matches the single persisted decision
        winner_state = next(v[1] for v in results.values() if v[0] == "OK")
        final = A.get_record(aid, data_dir=scratch)
        assert final["state"] == winner_state == decided[0]["state"]

        all_seqs = [e["seq"] for e in store.all_events(data_dir=scratch)]
        assert len(all_seqs) == len(set(all_seqs)), f"duplicate seq: {all_seqs}"
        assert sorted(all_seqs) == list(range(1, len(all_seqs) + 1))


# --- 3. no line corruption under a wider concurrent load -------------------
def test_events_log_not_corrupted_under_concurrency(scratch):
    ids = [A.ingest_pipeline_output(_po(fund_id="FUND-01"), data_dir=scratch).approval_id
           for _ in range(6)]

    def decide(aid, state):
        try:
            A.record_decision(aid, state, "x@x.example", "n", data_dir=scratch)
        except A.AlreadyDecidedError:
            pass

    jobs = []
    for aid in ids:                       # 6 unique + 6 more racing the same 6
        jobs.append((aid, "APPROVED"))
        jobs.append((aid, "REJECTED"))
    with ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(lambda j: decide(*j), jobs))

    path = os.path.join(scratch, "approval_events.jsonl")
    lines = open(path).read().splitlines()
    parsed = [json.loads(ln) for ln in lines if ln.strip()]   # every line is valid JSON
    assert len(parsed) == len(lines)
    seqs = [e["seq"] for e in parsed]
    assert sorted(seqs) == list(range(1, len(seqs) + 1)), "seq not unique+contiguous"
    for aid in ids:                       # each raced record decided exactly once
        assert sum(1 for e in parsed if e["event"] == "DECIDED" and e["approval_id"] == aid) == 1


# --- 4. different records are NOT serialised by the fix -------------------
def test_different_records_decided_concurrently(scratch, monkeypatch):
    a1 = A.ingest_pipeline_output(_po(fund_id="FUND-01"), data_dir=scratch).approval_id
    a2 = A.ingest_pipeline_output(_po(fund_id="FUND-02"), data_dir=scratch).approval_id

    a1_in_section = threading.Event()
    let_a1_finish = threading.Event()
    orig_replay = A._replay

    def gated_replay(approval_id, **kw):
        r = orig_replay(approval_id, **kw)
        # hold thread-1 *inside* record_decision's locked section (it holds
        # _record_lock(a1)); a global lock would now block a2 as well.
        if approval_id == a1 and not a1_in_section.is_set():
            a1_in_section.set()
            assert let_a1_finish.wait(timeout=3), "a1 was never released"
        return r

    monkeypatch.setattr(A, "_replay", gated_replay)

    out = {}

    def dec(aid, key, state):
        try:
            out[key] = A.record_decision(aid, state, "x@x.example", "n", data_dir=scratch)["state"]
        except Exception as e:  # pragma: no cover
            out[key] = f"ERR {e}"

    t1 = threading.Thread(target=dec, args=(a1, "a1", "APPROVED"))
    t2 = threading.Thread(target=dec, args=(a2, "a2", "REJECTED"))
    t1.start()
    assert a1_in_section.wait(timeout=3), "thread-1 never entered the locked section"

    # thread-1 is parked holding _record_lock(a1). thread-2 on a DIFFERENT record
    # must be able to run to completion right now.
    t2.start()
    t2.join(timeout=3)
    assert not t2.is_alive(), "decision on an unrelated record was blocked (over-serialised)"
    assert out["a2"] == "REJECTED"

    let_a1_finish.set()
    t1.join(timeout=3)
    assert out["a1"] == "APPROVED"


# --- 5. negative proof: remove the lock, the race comes back -------------
def test_negative_proof_record_lock_is_load_bearing(scratch, monkeypatch):
    # neuter the per-record lock -> back to a bare check-then-append
    monkeypatch.setattr(A, "_record_lock", lambda _aid: contextlib.nullcontext())

    saw_double_success = False
    saw_two_decided_events = False
    for _ in range(30):
        store.reset(data_dir=scratch)
        aid = A.ingest_pipeline_output(_po(), data_dir=scratch).approval_id
        results = _race_same_record(aid, scratch)
        if [v[0] for v in results.values()].count("OK") == 2:
            saw_double_success = True
        decided = [e for e in store.events_for(aid, data_dir=scratch) if e["event"] == "DECIDED"]
        if len(decided) > 1:
            saw_two_decided_events = True
        if saw_double_success and saw_two_decided_events:
            break

    assert saw_double_success or saw_two_decided_events, (
        "removing _record_lock did NOT reproduce the race — the concurrency tests "
        "above would then be passing regardless of whether the fix exists")
