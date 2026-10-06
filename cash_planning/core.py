"""Module 3 — Cash Planning: deterministic layer.

Answers, per fund: what is the real *confirmed* cash position right now, and what
capital calls are *known to be coming due soon*? Those are two different numbers
and this module never merges them.

DOWNSTREAM of payment approvals. The single most important rule:

    only an APPROVED capital call is real cash.

  * APPROVED            -> counted in the confirmed balance
  * PENDING_APPROVAL    -> a known upcoming obligation; reported separately,
                           NEVER added to the balance
  * REJECTED            -> not incoming cash at all; excluded entirely
  * NEEDS_MORE_INFO     -> not incoming cash at all; excluded entirely

Every number here is produced by plain Python / SQL. No model is involved in any
calculation. The optional plain-language summary lives in cash_planning/narrative.py
and is *given* these numbers to describe — it does not compute them, and it can be
turned off or fail without affecting anything here.

Sources (read-only — nothing is re-derived or duplicated):
  synthetic_data/output/accounting.db
    - gl_transactions      : historical ledger, one row per cash movement;
                             `amount` is the signed cash impact (+ in / - out).
    - cash_balances_daily  : the generator's own running balance. It equals the
                             cumulative sum of gl_transactions for every one of
                             the 18,210 fund/date points — that equality is the
                             cross-source reconciliation (see reconcile() and
                             tests/test_cash_planning.py).
  approvals.service        : APPROVED / PENDING_APPROVAL / REJECTED / NEEDS_MORE_INFO
                             records (this module only reads them).
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_REPO_ROOT, "synthetic_data", "output", "accounting.db")

# Near-term obligation window. Configurable per call; this is the default.
NEAR_TERM_HORIZON_DAYS = 30

# Synthetic amounts are 2dp; a sub-cent tolerance absorbs float summation noise.
RECON_TOLERANCE = 0.005

# The one state that is real cash. Everything else is excluded from the balance.
CASH_STATE = "APPROVED"
OBLIGATION_STATE = "PENDING_APPROVAL"
EXCLUDED_STATES = ("REJECTED", "NEEDS_MORE_INFO")


# --------------------------------------------------------------------- types
@dataclass(frozen=True)
class LedgerLine:
    """One individual cash line. The confirmed balance is exactly the sum of these."""
    date: str | None
    source: str          # "historical_gl" | "approved_capital_call"
    category: str
    amount: float        # signed cash impact: + is cash in, - is cash out
    ref: str             # transaction_id or approval_id
    description: str = ""


@dataclass(frozen=True)
class Obligation:
    """A PENDING_APPROVAL capital call — known, not yet realized. Never cash."""
    approval_id: str
    fund_id: str | None
    fund_name: str
    due_date: str | None
    amount: float
    hub_status: str


@dataclass(frozen=True)
class Reconciliation:
    fund_id: str
    reported_balance: float
    itemized_sum: float
    line_count: int
    delta: float
    ok: bool


# ----------------------------------------------------------------- db adapters
def _db(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def list_fund_ids(*, db_path: str | None = None) -> list[str]:
    with _db(db_path) as c:
        return [r["fund_id"] for r in c.execute(
            "select distinct fund_id from gl_transactions order by fund_id")]


def fund_name(fund_id: str, *, db_path: str | None = None) -> str:
    with _db(db_path) as c:
        r = c.execute("select fund_name from capital_calls where fund_id=? limit 1",
                      (fund_id,)).fetchone()
    return r["fund_name"] if r else fund_id


def latest_ledger_date(*, db_path: str | None = None) -> str:
    with _db(db_path) as c:
        return c.execute("select max(date) d from gl_transactions").fetchone()["d"]


def historical_gl_lines(fund_id: str, *, as_of: str | None = None,
                        db_path: str | None = None) -> list[LedgerLine]:
    """Every historical ledger line for the fund, on or before `as_of`
    (default: no cutoff). Row-by-row — the caller sums them."""
    q = "select * from gl_transactions where fund_id=?"
    args: list = [fund_id]
    if as_of:
        q += " and date<=?"
        args.append(as_of)
    q += " order by date, transaction_id"
    with _db(db_path) as c:
        rows = c.execute(q, args).fetchall()
    return [LedgerLine(date=r["date"], source="historical_gl", category=r["account_name"],
                       amount=float(r["amount"]), ref=r["transaction_id"],
                       description=r["description"] or "") for r in rows]


def ledger_running_balance(fund_id: str, *, as_of: str | None = None,
                           db_path: str | None = None) -> float:
    """The generator's OWN running balance from cash_balances_daily as of `as_of`
    — an independent derivation we reconcile the summed GL lines against."""
    q = "select cash_balance from cash_balances_daily where fund_id=?"
    args: list = [fund_id]
    if as_of:
        q += " and date<=?"
        args.append(as_of)
    q += " order by date desc limit 1"
    with _db(db_path) as c:
        r = c.execute(q, args).fetchone()
    return round(float(r["cash_balance"]), 2) if r else 0.0


# ------------------------------------------------------------- approvals adapter
def _approval_records(*, data_dir: str | None = None) -> list[dict]:
    """Full approval records (with verification_report) from the payment-approvals
    module. Read-only."""
    from approvals import service as approvals
    return [approvals.get_record(r["approval_id"], data_dir=data_dir)
            for r in approvals.list_all(data_dir=data_dir)]


def _amount(rec: dict) -> float:
    ext = (rec.get("verification_report") or {}).get("extracted") or {}
    a = ext.get("amount")
    return float(a) if isinstance(a, (int, float)) else 0.0


def _due_date(rec: dict) -> str | None:
    ext = (rec.get("verification_report") or {}).get("extracted") or {}
    d = ext.get("due_date")
    return d if isinstance(d, str) and d else None


def _superseded(rec: dict) -> bool:
    """True if this record has been reversed (a newer PENDING record supersedes it).
    A reversal in payment approvals leaves the old record's `state` as-is (e.g.
    APPROVED) and adds a `superseded_by` back-link — so an APPROVED-but-reversed
    call is no longer confirmed cash; its replacement PENDING record carries the
    obligation forward."""
    return bool(rec.get("superseded_by"))


def approved_call_lines(fund_id: str, *, data_dir: str | None = None,
                        records: list[dict] | None = None) -> list[LedgerLine]:
    """APPROVED capital-call records for this fund, as positive cash lines.
    This is the ONLY approvals-derived money that enters the balance. A reversed
    (superseded) approval does NOT count — it has been pulled back to pending."""
    recs = records if records is not None else _approval_records(data_dir=data_dir)
    return [
        LedgerLine(date=r.get("decision_at") or r.get("created_at"),
                   source="approved_capital_call",
                   category="Capital call (approved)",
                   amount=_amount(r), ref=r["approval_id"],
                   description=f"approved by {r.get('decision_by') or '?'}")
        for r in recs
        if r.get("state") == CASH_STATE and r.get("fund_id") == fund_id
        and not _superseded(r)
    ]


def pending_obligations(fund_id: str, *, data_dir: str | None = None,
                        records: list[dict] | None = None) -> list[Obligation]:
    """PENDING_APPROVAL capital-call records for this fund — known, not realized."""
    recs = records if records is not None else _approval_records(data_dir=data_dir)
    return [
        Obligation(approval_id=r["approval_id"], fund_id=r.get("fund_id"),
                   fund_name=r.get("fund_name") or fund_id, due_date=_due_date(r),
                   amount=_amount(r), hub_status=r.get("hub_status") or "OK")
        for r in recs
        if r.get("state") == OBLIGATION_STATE and r.get("fund_id") == fund_id
    ]


def _excluded_counts(fund_id: str, records: list[dict]) -> dict:
    """REJECTED / NEEDS_MORE_INFO counts for the fund. A superseded (reversed)
    record is excluded here too — it is no longer the live decision."""
    out = {s: 0 for s in EXCLUDED_STATES}
    for r in records:
        if (r.get("fund_id") == fund_id and r.get("state") in out
                and not _superseded(r)):
            out[r["state"]] += 1
    return out


# ---------------------------------------------------------------- pure functions
def sum_lines(lines: Iterable[LedgerLine]) -> float:
    return round(sum(l.amount for l in lines), 2)


def confirmed_balance(historical_balance: float,
                      approved_lines: Iterable[LedgerLine]) -> float:
    """Current real cash = historical ledger position + every APPROVED call.
    Pure: a function of the two inputs handed in, nothing else."""
    return round(historical_balance + sum_lines(approved_lines), 2)


def within_window(obligations: Iterable[Obligation], *, reference_date: date,
                  horizon_days: int) -> list[Obligation]:
    """Obligations whose due_date falls in [reference_date, reference_date + horizon]."""
    lo, hi = reference_date, reference_date + timedelta(days=horizon_days)
    out = []
    for o in obligations:
        if not o.due_date:
            continue
        try:
            d = date.fromisoformat(o.due_date)
        except ValueError:
            continue
        if lo <= d <= hi:
            out.append(o)
    return out


def reconcile(fund_id: str, *, reported_balance: float,
              all_lines: Iterable[LedgerLine],
              tolerance: float = RECON_TOLERANCE) -> Reconciliation:
    """The load-bearing check: the sum of every individual line must equal the
    reported balance. `reported_balance` is derived a DIFFERENT way (historical
    part from cash_balances_daily, not from summing gl rows), so this is a real
    cross-check, not x == x."""
    lines = list(all_lines)
    itemized = round(sum(l.amount for l in lines), 2)
    delta = round(itemized - reported_balance, 2)
    return Reconciliation(fund_id=fund_id, reported_balance=round(reported_balance, 2),
                          itemized_sum=itemized, line_count=len(lines),
                          delta=delta, ok=abs(delta) <= tolerance)


# --------------------------------------------------------------- orchestrator
def cash_position(fund_id: str, *, as_of: str | None = None,
                  reference_date: date | str | None = None,
                  horizon_days: int = NEAR_TERM_HORIZON_DAYS,
                  data_dir: str | None = None, db_path: str | None = None) -> dict:
    """Full deterministic cash picture for one fund. No model involved.

    - confirmed_cash_balance : historical ledger position + APPROVED calls only.
    - near_term_obligations   : PENDING_APPROVAL calls due within `horizon_days`,
                                reported separately and explicitly NOT in the balance.
    - reconciliation          : sum(individual lines) vs the reported balance.
    """
    as_of = as_of or latest_ledger_date(db_path=db_path)
    if reference_date is None:
        reference_date = date.today()
    elif isinstance(reference_date, str):
        reference_date = date.fromisoformat(reference_date)

    records = _approval_records(data_dir=data_dir)
    hist_lines = historical_gl_lines(fund_id, as_of=as_of, db_path=db_path)
    hist_balance = ledger_running_balance(fund_id, as_of=as_of, db_path=db_path)
    approved_lines = approved_call_lines(fund_id, records=records)

    balance = confirmed_balance(hist_balance, approved_lines)

    all_lines = hist_lines + approved_lines
    recon = reconcile(fund_id, reported_balance=balance, all_lines=all_lines)

    obligations = pending_obligations(fund_id, records=records)
    near = within_window(obligations, reference_date=reference_date, horizon_days=horizon_days)
    lo = reference_date
    hi = reference_date + timedelta(days=horizon_days)

    return {
        "fund_id": fund_id,
        "fund_name": fund_name(fund_id, db_path=db_path),
        "as_of_ledger": as_of,
        "reference_date": reference_date.isoformat(),
        "confirmed_cash_balance": balance,
        "confirmed_components": {
            "historical_ledger_balance": hist_balance,
            "approved_capital_calls_total": sum_lines(approved_lines),
            "approved_capital_calls_count": len(approved_lines),
        },
        "near_term_obligations": {
            "note": ("PENDING_APPROVAL capital calls only — known but NOT realized; "
                     "deliberately excluded from confirmed_cash_balance"),
            "horizon_days": horizon_days,
            "window": [lo.isoformat(), hi.isoformat()],
            "count": len(near),
            "total_not_yet_realized": round(sum(o.amount for o in near), 2),
            "items": [
                {"approval_id": o.approval_id, "due_date": o.due_date,
                 "amount": round(o.amount, 2), "fund_name": o.fund_name,
                 "hub_status": o.hub_status}
                for o in sorted(near, key=lambda o: o.due_date or "9999")
            ],
            "pending_outside_window": len(obligations) - len(near),
        },
        "excluded_from_balance": {
            **_excluded_counts(fund_id, records),
            "note": "REJECTED / NEEDS_MORE_INFO have zero effect on confirmed_cash_balance",
        },
        "reconciliation": {
            "ok": recon.ok,
            "reported_balance": recon.reported_balance,
            "itemized_sum": recon.itemized_sum,
            "line_count": recon.line_count,
            "delta": recon.delta,
        },
    }
