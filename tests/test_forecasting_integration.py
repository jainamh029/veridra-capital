"""Cross-module: the forecasting projection's historical basis must match what
cash planning / payment approvals independently report for the same fund's
confirmed capital-call history. If these ever diverge, this fails.
"""
import datetime
import sqlite3

import pytest
from fastapi.testclient import TestClient

from cash_planning import core as cash_core
from forecasting import core as fc_core

FUND = "FUND-01"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from approvals import service as A
    from approvals import store
    from approvals.notify import NotificationSender

    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "REPORTS_LOG", str(tmp_path / "verification_reports.jsonl"))
    monkeypatch.setattr(store, "EVENTS_LOG", str(tmp_path / "approval_events.jsonl"))

    class _Silent(NotificationSender):
        def notify(self, rec):
            pass

    monkeypatch.setattr(A, "_notifier", _Silent())

    from agents.app import app
    c = TestClient(app)
    c._svc = A
    return c


def _seed_approved(client, amount, due_date):
    b = _baseline()
    out = {
        "status": "OK", "decision": "PASS", "overall_severity": "none", "fraud": False,
        "fraud_type": None, "fraud_labels": [], "failed_checks": [], "confidence": "high",
        "extracted": {"fund_name": b.fund_name, "entity": b.entity_name, "amount": amount,
                      "bank_name": b.bank_name, "routing_number": b.routing_number,
                      "account_number": "8840-2291-7734", "due_date": due_date},
        "fund_baseline": {"fund_id": b.fund_id, "fund_name": b.fund_name},
        "checks": {"routing_checksum": {"passed": True}}, "alert": None,
    }
    ap = client._svc.ingest_pipeline_output(out).approval_id
    client._svc.record_decision(ap, "APPROVED", "c@synthetic-ops.example", "ok")
    return ap


def _baseline():
    from verification.baseline import load_baselines
    return load_baselines()[FUND]


def test_forecasting_basis_matches_cash_planning_and_ledger(client):
    # seed one APPROVED call in payment approvals and one REJECTED (must NOT show up)
    ap_ok = _seed_approved(client, 4_000_000.00, "2026-05-01")
    b = _baseline()
    rej = client._svc.ingest_pipeline_output({
        "status": "OK", "decision": "PASS", "overall_severity": "none", "fraud": False,
        "fraud_type": None, "fraud_labels": [], "failed_checks": [], "confidence": "high",
        "extracted": {"fund_name": b.fund_name, "entity": b.entity_name, "amount": 9_000_000.0,
                      "bank_name": b.bank_name, "routing_number": b.routing_number,
                      "account_number": "a", "due_date": "2026-05-02"},
        "fund_baseline": {"fund_id": FUND, "fund_name": b.fund_name},
        "checks": {}, "alert": None,
    }).approval_id
    client._svc.record_decision(rej, "REJECTED", "c@synthetic-ops.example", "no")

    resp = client.get(f"/forecasting/{FUND}").json()
    hist = resp["history_used"]

    # -- 1. ledger part: sum + count match an independent query on gl_transactions --
    con = sqlite3.connect(fc_core.DB_PATH)
    ind_sum, ind_events = con.execute(
        "select round(sum(amount),2), count(distinct related_event_id) "
        "from gl_transactions where fund_id=? and account_code='3001'", (FUND,)).fetchone()
    con.close()
    ledger_pts = [h for h in hist if h["source"] == "ledger_contribution"]
    assert len(ledger_pts) == ind_events
    assert round(sum(h["amount"] for h in ledger_pts), 2) == ind_sum

    # -- 2. approvals part: exactly the APPROVED (non-rejected) call, matching cash planning --
    appr_pts = [h for h in hist if h["source"] == "approved_approval"]
    # cash planning reads the same monkeypatched approvals store the endpoint does
    cp_lines = cash_core.approved_call_lines(FUND, data_dir=None)
    assert {(h["ref"], h["amount"]) for h in appr_pts} == {(l.ref, round(l.amount, 2))
                                                           for l in cp_lines}
    assert any(h["ref"] == ap_ok and h["amount"] == 4_000_000.00 for h in appr_pts)
    assert all(h["ref"] != rej for h in appr_pts)          # rejected call never enters the basis

    # -- 3. tier-1 number the UI shows == cash planning's own confirmed balance --
    cp = cash_core.cash_position(FUND)
    assert resp["context"]["confirmed_cash_balance"] == cp["confirmed_cash_balance"]
    assert resp["context"]["near_term_obligations_total"] == \
        cp["near_term_obligations"]["total_not_yet_realized"]

    # -- 4. and the projection is internally consistent with its own basis --
    assert resp["basis"]["last_call_date"] == hist[-1]["date"]
    assert resp["basis"]["first_call_date"] == hist[0]["date"]
    assert resp["history_call_count"] == len(hist)


def test_forecasting_drops_a_reversed_approval_from_its_history(client):
    """Gap 1: forecasting reuses cash_planning.core.approved_call_lines, which was
    fixed to exclude reversed/superseded approvals. Confirm forecasting inherits
    that here specifically — approve a call (it enters history_used), reverse it
    (it must leave), and the projection recalculates without it."""
    ap = _seed_approved(client, 4_000_000.00, "2026-05-01")

    before = client.get(f"/forecasting/{FUND}").json()
    refs_before = [h["ref"] for h in before["history_used"]]
    assert ap in refs_before, "approved call should appear in forecasting history"
    win_before = (before["next_expected_call"]["window_start"],
                  before["next_expected_call"]["window_end"],
                  before["next_expected_call"]["estimated_amount"])

    rev = client.post(f"/approvals/{ap}/reverse",
                      json={"approver": "c@synthetic-ops.example", "note": "reconsider"})
    assert rev.status_code == 200
    new_pending = rev.json()["approval_id"]

    after = client.get(f"/forecasting/{FUND}").json()
    refs_after = [h["ref"] for h in after["history_used"]]
    assert ap not in refs_after, "reversed (superseded) approval STILL in forecasting history — bug"
    assert new_pending not in refs_after, "the new PENDING record must not count as history either"
    assert after["history_call_count"] == before["history_call_count"] - 1

    win_after = (after["next_expected_call"]["window_start"],
                 after["next_expected_call"]["window_end"],
                 after["next_expected_call"]["estimated_amount"])
    assert win_after != win_before, "projection did not recalculate after the reversal"


def test_three_tiers_are_reported_separately_never_merged(client):
    due = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    # a pending obligation for tier 2
    b = _baseline()
    client._svc.ingest_pipeline_output({
        "status": "OK", "decision": "PASS", "overall_severity": "none", "fraud": False,
        "fraud_type": None, "fraud_labels": [], "failed_checks": [], "confidence": "high",
        "extracted": {"fund_name": b.fund_name, "entity": b.entity_name, "amount": 2_500_000.0,
                      "bank_name": b.bank_name, "routing_number": b.routing_number,
                      "account_number": "a", "due_date": due},
        "fund_baseline": {"fund_id": FUND, "fund_name": b.fund_name},
        "checks": {}, "alert": None,
    })
    _seed_approved(client, 1_000_000.00, "2026-04-01")

    r = client.get(f"/forecasting/{FUND}").json()
    tier1 = r["context"]["confirmed_cash_balance"]
    tier2 = r["context"]["near_term_obligations_total"]
    tier3 = r["next_expected_call"]["estimated_amount"]

    # three distinct fields, each its own number; nothing in the payload is their sum
    assert tier2 == 2_500_000.00
    assert tier3 > 0
    flat = [v for v in _flatten(r) if isinstance(v, (int, float))]
    assert round(tier1 + tier2 + tier3, 2) not in {round(x, 2) for x in flat}, \
        "a value equal to tier1+tier2+tier3 appears in the response — tiers must never be summed"


def _flatten(o):
    if isinstance(o, dict):
        for v in o.values():
            yield from _flatten(v)
    elif isinstance(o, list):
        for v in o:
            yield from _flatten(v)
    else:
        yield o
