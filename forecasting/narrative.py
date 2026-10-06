"""Module 4 — Forecasting: OPTIONAL plain-language layer.

Same contract as `cash_planning/narrative.py`: the model is handed a projection
that `forecasting.core` has ALREADY computed and asked to describe it in prose.
It never computes, adjusts, or "checks" a number.

Optional and fail-safe: `describe(proj, enabled=False)` makes no model call;
Ollama down -> `{"generated": False, "reason": …}`, the projection dict is
untouched. `core.py` does not import this module.

When there is NO projection (`sufficient_history` is false) the model is not
called at all — `describe` short-circuits to a fixed, honest sentence. This is
structural, not a prompt instruction: with no facts to describe the model tends
to guess a date/amount anyway (observed), so it never gets the chance.
"""

from __future__ import annotations

from agents.common import ask_llm

SYSTEM = (
    "You are a fund scenario assistant. You are given an ALREADY-COMPUTED "
    "projection of a fund's next capital call, produced by a simple historical "
    "extrapolation (average gap between past calls, mean of recent amounts). In "
    "3-4 plain sentences, say what the past pattern looks like and how much weight "
    "the estimate deserves. State plainly that this is a simple extrapolation from "
    "history, not a forecasting model. Use ONLY the exact figures given below — "
    "quote the estimated amount and the window dates verbatim; do not compute, "
    "round, average, or invent any number."
)

_UNAVAILABLE_PREFIX = "[narrative unavailable"

# fixed wording used when there is no projection to describe — never model-generated
NO_PROJECTION_MESSAGE = ("Not enough historical data for this fund to generate a projection. "
                         "No estimate is produced.")


def _facts_block(proj: dict) -> str:
    lines = [f"Fund: {proj.get('fund_name', proj.get('fund_id', '?'))}. Vantage date {proj['as_of']}.",
             f"Confirmed capital calls in history: {proj['history_call_count']}."]
    if not proj.get("sufficient_history"):
        lines.append(f"Not enough history to project ({proj.get('reason', '')}).")
        return "\n".join(lines)
    b, nx = proj["basis"], proj["next_expected_call"]
    lines += [
        f"Average gap between past calls: {b['avg_interval_days']} days "
        f"(spread {b['interval_spread_days']} days, from {b['interval_sample_size']} gaps).",
        f"Recent call amounts: {b['recent_amounts_used']} (trend: {b['amount_trend']}).",
        f"Projected next call window: {nx['window_start']} to {nx['window_end']} "
        f"(point estimate {nx['point_estimate_date']}).",
        f"Estimated amount: ${nx['estimated_amount']:,.2f}.",
        f"Confidence in this estimate: {nx['confidence']}"
        + (" — very few historical gaps." if b["low_confidence"] else "."),
    ]
    if nx["overdue_relative_to_as_of"]:
        lines.append("The point estimate is already before the vantage date (a call may be due).")
    return "\n".join(lines)


def describe(proj: dict, *, enabled: bool = True, num_predict: int = 220) -> dict:
    if not enabled:
        return {"narrative": None, "generated": False, "reason": "disabled"}
    # No projection -> do NOT call the model. It has nothing real to describe and
    # will invent a date/amount if asked. Return the fixed honest message.
    if not proj.get("sufficient_history"):
        return {"narrative": NO_PROJECTION_MESSAGE, "generated": False,
                "reason": "insufficient_history"}
    text = ask_llm(SYSTEM, _facts_block(proj), num_predict=num_predict)
    if text.startswith(_UNAVAILABLE_PREFIX):
        return {"narrative": None, "generated": False, "reason": text}
    return {"narrative": text, "generated": True, "reason": None}
