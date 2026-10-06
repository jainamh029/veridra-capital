"""Module 3 — Cash Planning: deterministic tests.

The load-bearing one is the reconciliation check (Step 3): sum of every
individual line == reported confirmed balance, for every fund, plus a
negative-proof that it actually fails when a line is dropped. No Ollama.
"""
import inspect
import os
import sqlite3
import tempfile

import pytest

from approvals import service as approvals
from approvals import store
from cash_planning import core

DB = core.DB_PATH


# --------------------------------------------------------------- seeding helpers
def _pipeline_output(fund_id, fund_name, amount, due_date, decision="PASS"):
    return {
        "status": "OK", "decision": decision, "overall_severity": "none",
        "fraud": decision != "PASS", "fraud_type": None, "fraud_labels": [],
        "failed_checks": [], "confidence": "high",
        "extracted": {"fund_name": fund_name, "entity": "GP LLC", "amount": amount,
                      "bank_name": "b", "routing_number": "011401533",
                      "account_number": "a", "due_date": due_date},
        "fund_baseline": {"fund_id": fund_id, "fund_name": fund_name},
        "checks": {"routing_checksum": {"passed": True}},
        "alert": None if decision == "PASS" else {"subject": "x", "body": "y"},
    }


@pytest.fixture
def scratch():
    d = tempfile.mkdtemp(prefix="cashplan_")
    store.reset(data_dir=d)
    approvals.set_notifier(None)
    yield d
    approvals.set_notifier(None)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def _seed(data_dir, fund_id, fund_name, amount, due_date, final_state=None):
    rec = approvals.ingest_pipeline_output(
        _pipeline_output(fund_id, fund_name, amount, due_date,
                         "PASS" if final_state in (None, "APPROVED") else "BLOCK"),
        data_dir=data_dir)
    if final_state and final_state != "PENDING_APPROVAL":
        approvals.record_decision(rec.approval_id, final_state,
                                  "controller@synthetic-ops.example", "test",
                                  data_dir=data_dir)
    return rec


# ------------------------------------------------------------------- Step 3
def test_reconciliation_holds_for_every_fund_empty_approvals(scratch):
    for as_of in (None, "2023-12-31", "2024-06-30"):
        for fid in core.list_fund_ids():
            pos = core.cash_position(fid, as_of=as_of, data_dir=scratch,
                                     reference_date="2026-09-07")
            r = pos["reconciliation"]
            assert r["ok"], f"{fid} @ {as_of}: recon failed delta={r['delta']}"
            assert r["delta"] == 0.0


def test_reconciliation_holds_with_seeded_approved_calls(scratch):
    fid, fname = "FUND-05", core.fund_name("FUND-05")
    _seed(scratch, fid, fname, 1_250_000.00, "2026-09-15", "APPROVED")
    _seed(scratch, fid, fname, 3_400_000.50, "2026-09-20", "APPROVED")
    _seed(scratch, fid, fname, 999_999.99, "2026-09-18", "PENDING_APPROVAL")
    _seed(scratch, fid, fname, 5_000_000.00, "2026-06-01", "REJECTED")

    pos = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07")
    assert pos["reconciliation"]["ok"]
    assert pos["reconciliation"]["delta"] == 0.0
    # balance moved by exactly the two approved amounts, nothing else
    hist = pos["confirmed_components"]["historical_ledger_balance"]
    assert pos["confirmed_cash_balance"] == round(hist + 1_250_000.00 + 3_400_000.50, 2)


def test_gl_lines_sum_equals_generated_running_balance():
    """Cross-source: the cumulative sum of gl_transactions must equal the
    generator's own cash_balances_daily, for every fund at every date it
    recorded (~18k points). This is the ABA-checksum-equivalent for this module."""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    mismatches = 0
    checked = 0
    for fid in core.list_fund_ids():
        gl = c.execute("select date, amount from gl_transactions where fund_id=? "
                       "order by date, transaction_id", (fid,)).fetchall()
        cum, cum_by_date = 0.0, {}
        for r in gl:
            cum += r["amount"]
            cum_by_date[r["date"]] = cum
        sorted_dates = sorted(cum_by_date)
        for row in c.execute("select date, cash_balance from cash_balances_daily "
                             "where fund_id=? order by date", (fid,)):
            prior = [cum_by_date[k] for k in sorted_dates if k <= row["date"]]
            gl_cum = prior[-1] if prior else 0.0
            checked += 1
            if abs(gl_cum - row["cash_balance"]) > core.RECON_TOLERANCE:
                mismatches += 1
    c.close()
    assert checked > 15000, f"expected the full sweep, only checked {checked}"
    assert mismatches == 0, f"{mismatches}/{checked} GL vs running-balance mismatches"


# ------------------------------------------------------------- Step 3 negative proof
def test_negative_proof_reconciliation_fails_when_an_approved_line_is_dropped(scratch):
    fid, fname = "FUND-07", core.fund_name("FUND-07")
    _seed(scratch, fid, fname, 2_000_000.00, "2026-09-15", "APPROVED")
    _seed(scratch, fid, fname, 750_000.00, "2026-09-16", "APPROVED")

    records = core._approval_records(data_dir=scratch)
    hist_lines = core.historical_gl_lines(fid)
    hist_balance = core.ledger_running_balance(fid)
    approved = core.approved_call_lines(fid, records=records)
    assert len(approved) == 2

    # correct: balance counts both approved lines
    good = core.confirmed_balance(hist_balance, approved)
    assert core.reconcile(fid, reported_balance=good,
                          all_lines=hist_lines + approved).ok

    # BUG: the reported balance forgot one approved line, but it's still in the
    # itemized ledger -> reconciliation must catch it, not shrug.
    dropped = approved[-1]
    buggy = core.confirmed_balance(hist_balance, approved[:-1])
    r = core.reconcile(fid, reported_balance=buggy, all_lines=hist_lines + approved)
    assert not r.ok
    assert r.delta == round(dropped.amount, 2)


def test_negative_proof_reconciliation_fails_when_a_gl_line_is_dropped(scratch):
    fid = "FUND-02"
    hist_lines = core.historical_gl_lines(fid)
    hist_balance = core.ledger_running_balance(fid)
    good = core.confirmed_balance(hist_balance, [])
    assert core.reconcile(fid, reported_balance=good, all_lines=hist_lines).ok

    missing = hist_lines[len(hist_lines) // 2]
    r = core.reconcile(fid, reported_balance=good,
                       all_lines=[l for l in hist_lines if l.ref != missing.ref])
    assert not r.ok
    assert r.delta == round(-missing.amount, 2)


# ------------------------------------------------------------------- Step 5
def test_only_approved_calls_enter_the_balance(scratch):
    fid, fname = "FUND-05", core.fund_name("FUND-05")
    _seed(scratch, fid, fname, 1_000_000.00, "2026-09-15", "APPROVED")
    _seed(scratch, fid, fname, 2_000_000.00, "2026-09-16", "APPROVED")
    _seed(scratch, fid, fname, 4_000_000.00, "2026-09-12", "PENDING_APPROVAL")   # near
    _seed(scratch, fid, fname, 9_000_000.00, "2027-03-01", "PENDING_APPROVAL")   # far
    _seed(scratch, fid, fname, 8_000_000.00, "2026-09-10", "REJECTED")
    _seed(scratch, fid, fname, 7_000_000.00, "2026-09-11", "NEEDS_MORE_INFO")

    pos = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07",
                             horizon_days=30)
    hist = pos["confirmed_components"]["historical_ledger_balance"]

    # only the 2 approved calls
    assert pos["confirmed_components"]["approved_capital_calls_count"] == 2
    assert pos["confirmed_cash_balance"] == round(hist + 3_000_000.00, 2)

    # the near pending is listed; the far one is not; neither is in the balance
    nt = pos["near_term_obligations"]
    assert nt["count"] == 1
    assert nt["items"][0]["amount"] == 4_000_000.00
    assert nt["total_not_yet_realized"] == 4_000_000.00
    assert nt["pending_outside_window"] == 1
    assert pos["confirmed_cash_balance"] != round(hist + 3_000_000.00 + 4_000_000.00, 2)

    # rejected / needs-info are counted only as excluded, never as cash
    assert pos["excluded_from_balance"]["REJECTED"] == 1
    assert pos["excluded_from_balance"]["NEEDS_MORE_INFO"] == 1
    assert pos["reconciliation"]["ok"]


def test_rejected_and_needs_more_info_have_zero_balance_effect(scratch):
    fid, fname = "FUND-09", core.fund_name("FUND-09")
    base = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07")
    base_bal = base["confirmed_cash_balance"]

    for bad_state in ("REJECTED", "NEEDS_MORE_INFO"):
        rec = _seed(scratch, fid, fname, 6_500_000.00, "2026-09-15", "PENDING_APPROVAL")
        approvals.record_decision(rec.approval_id, bad_state,
                                  "c@synthetic-ops.example", "n", data_dir=scratch)
        after = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07")
        assert after["confirmed_cash_balance"] == base_bal, \
            f"{bad_state} changed the balance: {base_bal} -> {after['confirmed_cash_balance']}"
        assert after["reconciliation"]["ok"]


def test_near_term_window_is_configurable_and_never_touches_balance(scratch):
    fid, fname = "FUND-03", core.fund_name("FUND-03")
    _seed(scratch, fid, fname, 1_111_111.00, "2026-09-15", "APPROVED")
    _seed(scratch, fid, fname, 2_222_222.00, "2026-09-20", "PENDING_APPROVAL")   # +13d
    _seed(scratch, fid, fname, 3_333_333.00, "2026-10-25", "PENDING_APPROVAL")   # +48d

    balances, memberships = set(), {}
    for h in (7, 30, 60):
        pos = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07",
                                 horizon_days=h)
        balances.add(pos["confirmed_cash_balance"])
        memberships[h] = pos["near_term_obligations"]["count"]
        assert pos["reconciliation"]["ok"]

    assert len(balances) == 1, f"horizon changed the balance: {balances}"
    assert memberships == {7: 0, 30: 1, 60: 2}


def test_pending_call_due_today_still_not_in_balance(scratch):
    fid, fname = "FUND-06", core.fund_name("FUND-06")
    before = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07"
                                )["confirmed_cash_balance"]
    _seed(scratch, fid, fname, 50_000_000.00, "2026-09-07", "PENDING_APPROVAL")
    pos = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07")
    assert pos["confirmed_cash_balance"] == before
    assert pos["near_term_obligations"]["count"] == 1
    assert pos["near_term_obligations"]["total_not_yet_realized"] == 50_000_000.00


def test_reversed_approval_stops_counting_as_cash(scratch):
    """A payment-approvals reversal leaves the old record APPROVED but adds a
    `superseded_by` link and a new PENDING record. Cash planning must stop
    counting the superseded APPROVED call and pick the pending one back up."""
    fid, fname = "FUND-04", core.fund_name("FUND-04")
    before = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07"
                                )["confirmed_cash_balance"]
    rec = _seed(scratch, fid, fname, 2_500_000.00, "2026-09-15", "APPROVED")

    approved = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07")
    assert approved["confirmed_cash_balance"] == round(before + 2_500_000.00, 2)

    rev = approvals.reverse_decision(rec.approval_id, "c@synthetic-ops.example",
                                     "reconsider", data_dir=scratch)
    after = core.cash_position(fid, data_dir=scratch, reference_date="2026-09-07")
    assert after["confirmed_cash_balance"] == before          # back down
    assert after["confirmed_components"]["approved_capital_calls_count"] == 0
    assert rev["approval_id"] in [o["approval_id"]
                                  for o in after["near_term_obligations"]["items"]]
    assert after["reconciliation"]["ok"] and after["reconciliation"]["delta"] == 0.0


# ------------------------------------------------------------------- Step 4
def test_narrative_layer_is_optional_and_never_computes():
    from cash_planning import narrative

    pos = {
        "fund_id": "FUND-01", "fund_name": "Fieldstone Equity Partners II",
        "as_of_ledger": "2025-12-30", "reference_date": "2026-09-07",
        "confirmed_cash_balance": 1234.56,
        "confirmed_components": {"historical_ledger_balance": 0.0,
                                 "approved_capital_calls_total": 1234.56,
                                 "approved_capital_calls_count": 1},
        "near_term_obligations": {"horizon_days": 30, "count": 0,
                                  "total_not_yet_realized": 0.0, "items": []},
        "excluded_from_balance": {"REJECTED": 0, "NEEDS_MORE_INFO": 0},
        "reconciliation": {"ok": True},
    }
    off = narrative.describe(pos, enabled=False)
    assert off == {"narrative": None, "generated": False, "reason": "disabled"}

    # core must not CALL or IMPORT any model path (docstrings may mention it)
    src = inspect.getsource(core)
    assert "ask_llm(" not in src and "def " in src
    assert not hasattr(core, "ask_llm")
    import ast
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("narrative" in m or "ollama" in m.lower() or m == "agents.common"
                   for m in imported), f"core imports a model path: {imported}"
