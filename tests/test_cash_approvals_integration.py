"""Cross-module integration: a live payment-approvals decision must move cash
planning's numbers a moment later.

Every prior cash-planning test used a static pre-built dataset. This one drives
the real flow end to end through the HTTP layer:

    seed PENDING  ->  GET /cash-planning/{fund}      (in near-term, not in balance)
    POST /approvals/{id}/decide APPROVED             ->  balance += amount, leaves near-term
    POST /approvals/{id}/decide REJECTED (other)     ->  balance unchanged, only excluded++
    POST /approvals/{id}/reverse                     ->  balance -= amount, new pending reappears

It runs in ./predeploy.sh so this wiring can't silently break if either module
changes independently. Ollama-free — records are seeded through
approvals.ingest_pipeline_output (the same entry point the hub's /decision uses).
"""
import datetime

import pytest
from fastapi.testclient import TestClient

FUND_ID = "FUND-01"


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
    c._svc = A            # stash for seeding
    return c


def _seed_pending(client, amount, due_date) -> str:
    from verification.baseline import load_baselines
    b = load_baselines()[FUND_ID]
    out = {
        "status": "OK", "decision": "PASS", "overall_severity": "none",
        "fraud": False, "fraud_type": None, "fraud_labels": [], "failed_checks": [],
        "confidence": "high",
        "extracted": {"fund_name": b.fund_name, "entity": b.entity_name, "amount": amount,
                      "bank_name": b.bank_name, "routing_number": b.routing_number,
                      "account_number": "8840-2291-7734", "due_date": due_date},
        "fund_baseline": {"fund_id": b.fund_id, "fund_name": b.fund_name},
        "checks": {"routing_checksum": {"passed": True}}, "alert": None,
    }
    return client._svc.ingest_pipeline_output(out).approval_id


def _cash(client):
    r = client.get(f"/cash-planning/{FUND_ID}")
    assert r.status_code == 200
    return r.json()


def _near_ids(pos):
    return [o["approval_id"] for o in pos["near_term_obligations"]["items"]]


def _decide(client, approval_id, state):
    return client.post(f"/approvals/{approval_id}/decide",
                       json={"state": state, "approver": "controller@synthetic-ops.example",
                             "note": f"test {state}"})


def test_cash_planning_tracks_live_approval_decisions(client):
    due = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    AMT_A, AMT_R = 2_000_000.00, 1_500_000.00
    ap_approve = _seed_pending(client, AMT_A, due)
    ap_reject = _seed_pending(client, AMT_R, due)

    # ---- Step 1: before any decision -------------------------------------
    p0 = _cash(client)
    b0 = p0["confirmed_cash_balance"]
    assert ap_approve in _near_ids(p0) and ap_reject in _near_ids(p0)
    assert p0["near_term_obligations"]["total_not_yet_realized"] == round(AMT_A + AMT_R, 2)
    assert p0["confirmed_components"]["approved_capital_calls_count"] == 0   # nothing in balance
    assert p0["reconciliation"]["ok"]

    # ---- Step 2: APPROVE one -------------------------------------------
    assert _decide(client, ap_approve, "APPROVED").status_code == 200
    p1 = _cash(client)
    assert p1["confirmed_cash_balance"] == round(b0 + AMT_A, 2)     # up by exactly the amount
    assert ap_approve not in _near_ids(p1)                          # left the near-term list
    assert ap_reject in _near_ids(p1)                               # the other is still pending
    assert p1["confirmed_components"]["approved_capital_calls_count"] == 1
    assert p1["reconciliation"]["ok"]

    # ---- Step 3: REJECT the other ------------------------------------
    assert _decide(client, ap_reject, "REJECTED").status_code == 200
    p2 = _cash(client)
    assert p2["confirmed_cash_balance"] == p1["confirmed_cash_balance"]   # reject moves nothing
    assert ap_reject not in _near_ids(p2)                                 # not in near-term
    assert p2["near_term_obligations"]["total_not_yet_realized"] == 0.0
    assert p2["excluded_from_balance"]["REJECTED"] == 1                   # shows up only here
    assert p2["reconciliation"]["ok"]

    # ---- Step 4: REVERSE the approval --------------------------------
    rev = client.post(f"/approvals/{ap_approve}/reverse",
                      json={"approver": "controller@synthetic-ops.example", "note": "reconsider"})
    assert rev.status_code == 200
    new_ap = rev.json()["approval_id"]
    p3 = _cash(client)
    assert p3["confirmed_cash_balance"] == round(b0, 2)          # back down by the amount
    assert new_ap in _near_ids(p3)                               # replacement pending reappears
    assert ap_approve not in _near_ids(p3)                       # the old (superseded) one is not
    assert p3["confirmed_components"]["approved_capital_calls_count"] == 0
    assert p3["reconciliation"]["ok"]


def test_needs_more_info_decision_also_keeps_money_out(client):
    due = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    ap = _seed_pending(client, 900_000.00, due)
    b0 = _cash(client)["confirmed_cash_balance"]

    assert _decide(client, ap, "NEEDS_MORE_INFO").status_code == 200
    p = _cash(client)
    assert p["confirmed_cash_balance"] == b0
    assert ap not in _near_ids(p)
    assert p["excluded_from_balance"]["NEEDS_MORE_INFO"] == 1
    assert p["reconciliation"]["ok"]
