"""Module 4 — Scenario / Forecasting: deterministic layer.

What this does, plainly: it takes a fund's own history of **confirmed** capital
calls and extrapolates the next one — a date window and an estimated amount —
from (a) the average gap between past calls and (b) the mean of the most recent
call amounts.

That is the whole method. It is a **simple historical pattern extrapolation**,
not a forecasting model, not ML, not a black box. `project_next_call` is a pure
function: the same history in always gives the same projection out. No model is
involved in any number here (the optional prose lives in `forecasting/narrative.py`
and only describes numbers it is handed).

History source (read-only, not re-derived): the fund's **confirmed** capital-call
events —
  * ledger capital-contribution events: `gl_transactions` rows with
    `account_code = '3001'` ("LP Capital Contributions Received"), one event per
    `related_event_id`; and
  * `APPROVED` records from payment approvals, via
    `cash_planning.core.approved_call_lines` (superseded ones already excluded).
Both are "capital calls that actually came in" — the same confirmed-inflow set
cash planning builds its balance from. Raw unverified notices are never used.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Iterable

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_REPO_ROOT, "synthetic_data", "output", "accounting.db")

# how many of the most recent call amounts the estimate averages
RECENT_AMOUNT_WINDOW = 4
# need at least this many past calls to measure an interval at all
MIN_HISTORY = 2

_METHOD = ("average interval between past confirmed calls + mean of the last N "
           "call amounts; simple historical extrapolation, not a model")


@dataclass(frozen=True)
class CallEvent:
    date: str                 # ISO date the call came in / was approved
    amount: float             # positive cash amount of the call
    source: str               # "ledger_contribution" | "approved_approval"
    ref: str                  # related_event_id or approval_id


def _db(db_path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------- history adapter
def approved_call_history(fund_id: str, *, as_of: str | None = None,
                          data_dir: str | None = None,
                          db_path: str | None = None) -> list[CallEvent]:
    """The fund's confirmed capital-call events, oldest first, on/before `as_of`."""
    events: list[CallEvent] = []

    q = ("select related_event_id as ref, min(date) as d, round(sum(amount), 2) as amt "
         "from gl_transactions where fund_id=? and account_code='3001' ")
    args: list = [fund_id]
    if as_of:
        q += "and date<=? "
        args.append(as_of)
    q += "group by related_event_id"
    with _db(db_path) as c:
        for r in c.execute(q, args):
            events.append(CallEvent(date=r["d"], amount=float(r["amt"]),
                                    source="ledger_contribution", ref=r["ref"] or "?"))

    # APPROVED calls recorded in payment approvals (non-superseded), via cash planning
    from cash_planning import core as cash_core
    for ln in cash_core.approved_call_lines(fund_id, data_dir=data_dir):
        d = (ln.date or "")[:10]
        if as_of and d and d > as_of:
            continue
        events.append(CallEvent(date=d or (as_of or ""), amount=float(ln.amount),
                                source="approved_approval", ref=ln.ref))

    events.sort(key=lambda e: (e.date, e.ref))
    return events


# ---------------------------------------------------------------- pure projection
def _history_block(hist: list[CallEvent]) -> list[dict]:
    return [{"date": e.date, "amount": round(e.amount, 2), "source": e.source, "ref": e.ref}
            for e in hist]


def project_next_call(history: Iterable[CallEvent], *, as_of: str | date,
                      recent_window: int = RECENT_AMOUNT_WINDOW) -> dict:
    """Pure. history (any order) + a vantage date -> next-expected-call estimate.

    Deterministic: identical `history` and `as_of` always produce an identical
    dict. Simple historical extrapolation — NOT a forecasting model.
    """
    as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    hist = sorted(history, key=lambda e: (e.date, e.ref))

    out = {
        "type": "projected_estimate",
        "method": _METHOD,
        "as_of": as_of.isoformat(),
        "history_call_count": len(hist),
        "history_used": _history_block(hist),
    }

    if len(hist) < MIN_HISTORY:
        out.update(sufficient_history=False, basis=None, next_expected_call=None,
                   reason=f"need >= {MIN_HISTORY} past confirmed calls, have {len(hist)}")
        return out

    dates = [date.fromisoformat(e.date) for e in hist]
    intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    avg_interval = mean(intervals)

    # Spread = the ± band on the window. Two thin-data traps to avoid, both of
    # which make the window look MORE confident than the data warrants:
    #   - one gap only (exactly 2 calls): pstdev of a single value is 0
    #   - several *identical* gaps (e.g. exact monthly): pstdev is also 0
    # So: use pstdev when there are >= 2 gaps, else half the average gap; then
    # floor the result at a quarter of the average gap so the window is never
    # near-zero-width. Also flag low sample size explicitly.
    raw_spread = pstdev(intervals) if len(intervals) >= 2 else avg_interval * 0.5
    spread = max(raw_spread, avg_interval * 0.25)
    interval_sample_size = len(intervals)
    low_confidence = interval_sample_size < 3

    amounts = [e.amount for e in hist]
    recent = amounts[-min(len(amounts), max(1, recent_window)):]
    est_amount = round(mean(recent), 2)
    if len(recent) >= 2:
        delta = recent[-1] - recent[0]
        trend = "rising" if delta > 0 else "falling" if delta < 0 else "flat"
    else:
        trend = "flat"

    last = dates[-1]
    point = last + timedelta(days=round(avg_interval))
    win_start = last + timedelta(days=round(max(0.0, avg_interval - spread)))
    win_end = last + timedelta(days=round(avg_interval + spread))

    out.update(
        sufficient_history=True,
        basis={
            "first_call_date": hist[0].date,
            "last_call_date": hist[-1].date,
            "avg_interval_days": round(avg_interval, 1),
            "interval_spread_days": round(spread, 1),
            "intervals_observed_days": intervals,
            "interval_sample_size": interval_sample_size,
            "low_confidence": low_confidence,
            "recent_amounts_used": [round(a, 2) for a in recent],
            "estimated_amount_basis": f"mean of last {len(recent)} confirmed call amounts",
            "amount_trend": trend,
        },
        next_expected_call={
            "window_start": win_start.isoformat(),
            "window_end": win_end.isoformat(),
            "point_estimate_date": point.isoformat(),
            "estimated_amount": est_amount,
            "confidence": "low" if low_confidence else "moderate",
            "overdue_relative_to_as_of": point < as_of,
            "note": ("estimate from this fund's own past cadence — a simple historical "
                     "extrapolation, not a forecasting model and not a real obligation"
                     + ("; LOW CONFIDENCE — very few historical gaps to average over"
                        if low_confidence else "")),
        },
    )
    return out


# --------------------------------------------------------------- convenience
def fund_ids(*, db_path: str | None = None) -> list[str]:
    with _db(db_path) as c:
        return [r["fund_id"] for r in c.execute(
            "select distinct fund_id from gl_transactions order by fund_id")]
