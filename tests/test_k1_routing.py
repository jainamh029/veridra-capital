"""Module 5 — K-1 Routing: matching accuracy + roster consistency.

Ollama-free by DEPENDENCY INJECTION: tests pass `extractor=regex_extract_explicit`
into ingest_document — an explicit test seam, not a production fallback (the
production path has no fallback; a model failure -> AWAITING_EXTRACTION). This
still fully exercises the deterministic fuzzy matching and the NEEDS_REVIEW path.
The real model path is covered by tests/test_k1_routing_live.py (opt-in).
"""
import tempfile

import pytest

from k1_routing import core as k1_core
from k1_routing import service as k1_service
from k1_routing import store as k1_store
from k1_routing.synthetic import SYNTHETIC_K1_DOCS


@pytest.fixture
def scratch():
    d = tempfile.mkdtemp(prefix="k1_test_")
    k1_store.reset(data_dir=d)
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def _ingest_all(data_dir):
    return {d["doc_id"]: k1_service.ingest_document(
        d["text"], doc_id=d["doc_id"], case=d["case"],
        extractor=k1_core.regex_extract_explicit, data_dir=data_dir)
        for d in SYNTHETIC_K1_DOCS}


# ----------------------------------------------------------- Step 6: accuracy
def test_matching_accuracy_on_the_synthetic_batch(scratch):
    recs = _ingest_all(scratch)
    wrong = []
    for d in SYNTHETIC_K1_DOCS:
        r = recs[d["doc_id"]]
        if r["status"] != d["expect"]:
            wrong.append((d["doc_id"], f"status {r['status']} != {d['expect']}"))
            continue
        if d["expect"] == "ROUTED":
            if (r["matched_fund"] or {}).get("fund_id") != d["fund_id"]:
                wrong.append((d["doc_id"], f"fund {r['matched_fund']} != {d['fund_id']}"))
            if (r["matched_lp"] or {}).get("lp_id") != d["lp_id"]:
                wrong.append((d["doc_id"], f"lp {r['matched_lp']} != {d['lp_id']}"))
        else:  # NEEDS_REVIEW
            if r["review_reason"] != d["expect_reason"]:
                wrong.append((d["doc_id"], f"reason {r['review_reason']} != {d['expect_reason']}"))
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(f"  {x}" for x in wrong)


def test_clean_cases_all_route(scratch):
    recs = _ingest_all(scratch)
    for d in SYNTHETIC_K1_DOCS:
        if d["case"] == "clean":
            assert recs[d["doc_id"]]["status"] == "ROUTED"
            assert recs[d["doc_id"]]["matched_fund"]["exact"] is True
            assert recs[d["doc_id"]]["matched_lp"]["exact"] is True


def test_typo_lp_name_still_fuzzy_matches(scratch):
    r = _ingest_all(scratch)["K1-0007"]        # "Haas Group Retirement Sytem" (missing s)
    assert r["status"] == "ROUTED"
    assert r["matched_lp"]["lp_id"] == "LP-001"
    assert r["matched_lp"]["exact"] is False           # matched via fuzz, not exact
    assert 85 <= r["matched_lp"]["match_score"] < 100


def test_formatting_difference_still_matches(scratch):
    r = _ingest_all(scratch)["K1-0008"]        # "VELEZ-CHARLES   FAMILY   OFFICE"
    assert r["status"] == "ROUTED"
    assert r["matched_lp"]["lp_id"] == "LP-001"


def test_unknown_fund_goes_to_review_not_a_false_match(scratch):
    r = _ingest_all(scratch)["K1-0009"]        # fund "Aetheric Growth Partners IX"
    assert r["status"] == "NEEDS_REVIEW"
    assert r["review_reason"] == "fund_not_matched"
    assert r["matched_fund"] is None and r["matched_lp"] is None


def test_unknown_lp_in_real_fund_goes_to_review(scratch):
    r = _ingest_all(scratch)["K1-0010"]        # real fund, bogus LP
    assert r["status"] == "NEEDS_REVIEW"
    assert r["review_reason"] == "lp_not_matched"
    assert r["matched_fund"]["fund_id"] == "FUND-02"   # fund still identified
    assert r["matched_lp"] is None


# ----------------------------------------------------------- tracking record
def test_tracking_record_is_append_only_received_then_outcome(scratch):
    k1_service.ingest_document(SYNTHETIC_K1_DOCS[0]["text"], doc_id="D1",
                               extractor=k1_core.regex_extract_explicit, data_dir=scratch)
    evs = k1_store.events_for("D1", data_dir=scratch)
    assert [e["event"] for e in evs] == ["RECEIVED", "ROUTED"]
    assert [e["seq"] for e in evs] == [1, 2]
    # no decision/approve/reject event kinds exist in this module
    assert all(e["event"] in ("RECEIVED", "ROUTED", "NEEDS_REVIEW", "AWAITING_EXTRACTION")
               for e in evs)


def test_list_for_fund_only_returns_that_funds_routed_docs(scratch):
    _ingest_all(scratch)
    f1 = k1_service.list_for_fund("FUND-01", data_dir=scratch)
    assert {r["doc_id"] for r in f1} == {"K1-0001", "K1-0002", "K1-0007"}
    assert all(r["matched_fund"]["fund_id"] == "FUND-01" for r in f1)


# ----------------------------------------------------------- Step 6: no drift
def test_fund_roster_is_the_existing_one_no_parallel_list():
    from verification.baseline import load_baselines
    from cash_planning import core as cash_core

    roster = load_baselines()
    k1_funds = dict(k1_core.fund_candidates())
    assert set(k1_funds) == set(roster), "k1_routing fund list differs from the baseline roster"
    for fid, name in k1_funds.items():
        assert name == roster[fid].fund_name
        assert name == cash_core.fund_name(fid)        # same as cash planning / forecasting


def test_every_routed_doc_resolves_to_a_real_roster_fund_and_lp(scratch):
    from verification.baseline import load_baselines
    roster = load_baselines()
    for r in k1_service.list_records(data_dir=scratch) or list(_ingest_all(scratch).values()):
        if r["status"] != "ROUTED":
            continue
        fid = r["matched_fund"]["fund_id"]
        assert fid in roster
        lp_ids = {lp_id for lp_id, _ in k1_core.lp_candidates(fid)}
        assert r["matched_lp"]["lp_id"] in lp_ids
