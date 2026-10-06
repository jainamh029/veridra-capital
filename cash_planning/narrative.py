"""Module 3 — Cash Planning: OPTIONAL plain-language layer.

This is the only place a model is used, and it is used strictly to *describe*
numbers that cash_planning.core has already computed. The model is handed the
finished figures as text and asked for prose. It never calculates or "checks" a
number — doing that would be the same class of mistake as asking the fraud model
to diff strings.

This layer is fully optional:
  * `describe(pos, enabled=False)` -> no model call at all.
  * if the model / Ollama is unavailable, `describe` returns `generated=False`
    with the reason and `narrative=None`. The deterministic dict is untouched.

core.py does not import this module.
"""

from __future__ import annotations

from agents.common import ask_llm  # reuse the existing narrative plumbing (qwen2.5:3b-instruct)

SYSTEM = (
    "You are a fund cash-planning assistant for a private-equity CFO. You are "
    "given a set of ALREADY-CALCULATED figures. Write 3-4 plain sentences: the "
    "current confirmed cash position, what capital calls are known to be coming "
    "due soon (these are NOT yet in the balance), and any liquidity note. Do not "
    "invent, recompute, or adjust any number. No preamble, no bullet lists."
)

_UNAVAILABLE_PREFIX = "[narrative unavailable"


def _facts_block(pos: dict) -> str:
    c = pos["confirmed_components"]
    nt = pos["near_term_obligations"]
    lines = [
        f"Fund: {pos['fund_name']} ({pos['fund_id']}).",
        f"Ledger as of {pos['as_of_ledger']}; reference date {pos['reference_date']}.",
        f"Confirmed cash balance: ${pos['confirmed_cash_balance']:,.2f} "
        f"(historical ledger ${c['historical_ledger_balance']:,.2f} "
        f"+ {c['approved_capital_calls_count']} APPROVED capital call(s) "
        f"${c['approved_capital_calls_total']:,.2f}).",
        f"Known upcoming (PENDING_APPROVAL, NOT in the balance) within "
        f"{nt['horizon_days']} days: {nt['count']} call(s) totaling "
        f"${nt['total_not_yet_realized']:,.2f}.",
    ]
    for it in nt["items"]:
        lines.append(f"  - due {it['due_date']}: ${it['amount']:,.2f}")
    ex = pos["excluded_from_balance"]
    lines.append(f"Excluded (no cash effect): {ex.get('REJECTED', 0)} rejected, "
                 f"{ex.get('NEEDS_MORE_INFO', 0)} needs-more-info.")
    lines.append(f"Reconciliation: {'OK' if pos['reconciliation']['ok'] else 'FAILED'}.")
    return "\n".join(lines)


def describe(pos: dict, *, enabled: bool = True, num_predict: int = 260) -> dict:
    """Attach a prose summary to a cash_position() dict. Never mutates `pos`;
    returns a small result dict. Safe to skip or to have fail."""
    if not enabled:
        return {"narrative": None, "generated": False, "reason": "disabled"}
    text = ask_llm(SYSTEM, _facts_block(pos), num_predict=num_predict)
    if text.startswith(_UNAVAILABLE_PREFIX):
        return {"narrative": None, "generated": False, "reason": text}
    return {"narrative": text, "generated": True, "reason": None}
