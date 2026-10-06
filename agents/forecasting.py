"""Scenario / forecasting agent: naive forward projection of a fund's capital
call volume from its own history (simple statistics), plus an LLM narrative.
Deliberately not sold as sophisticated ML.
"""

from collections import defaultdict
from datetime import date

from .common import AS_OF, ask_llm, db, fund_row, usd

SYSTEM = (
    "You are a fund forecasting assistant. Given a fund's historical quarterly "
    "capital-call totals and a naive projection, explain in 3-4 plain sentences "
    "what the history shows and how much confidence the projection deserves. "
    "State clearly that this is a simple trend extrapolation, not a model. Do not "
    "invent numbers."
)


def _quarter(d: str) -> str:
    y, m = int(d[:4]), int(d[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"


def forecast(fund_id: str, as_of: str = AS_OF, horizon_quarters: int = 4,
             with_narrative: bool = True) -> dict:
    f = fund_row(fund_id)
    with db() as c:
        rows = c.execute(
            "select call_date, amount from capital_calls where fund_id=? and call_date<=?",
            (fund_id, as_of)).fetchall()

    by_q = defaultdict(float)
    for r in rows:
        by_q[_quarter(r["call_date"])] += r["amount"]
    quarters = sorted(by_q)
    series = [round(by_q[q], 2) for q in quarters]

    # naive projection: mean of last 4 quarters + linear drift of last 4
    recent = series[-4:] if len(series) >= 4 else series
    base = sum(recent) / len(recent) if recent else 0.0
    drift = ((recent[-1] - recent[0]) / (len(recent) - 1)) if len(recent) > 1 else 0.0

    proj_quarters, proj_vals = [], []
    ly, lq = (int(quarters[-1][:4]), int(quarters[-1][-1])) if quarters else (int(as_of[:4]), 1)
    for i in range(1, horizon_quarters + 1):
        lq += 1
        if lq > 4:
            lq, ly = 1, ly + 1
        proj_quarters.append(f"{ly}Q{lq}")
        proj_vals.append(round(max(0.0, base + drift * i), 2))

    hist_mean = round(sum(series) / len(series), 2) if series else 0.0
    result = {
        "fund_id": fund_id,
        "fund_name": f["fund_name"],
        "as_of": as_of,
        "method": "mean of last 4 quarters + linear drift; naive extrapolation, not a model",
        "history_quarterly": dict(zip(quarters, series)),
        "history_mean_quarterly": hist_mean,
        "history_last_quarter": series[-1] if series else 0.0,
        "projection_quarterly": dict(zip(proj_quarters, proj_vals)),
        "projection_total_next_%dq" % horizon_quarters: round(sum(proj_vals), 2),
    }

    if with_narrative:
        tail = list(zip(quarters, series))[-6:]
        facts = (
            f"Fund {result['fund_name']} ({fund_id}), as of {as_of}.\n"
            f"Recent quarterly capital-call totals:\n"
            + "".join(f"  {q}: {usd(v)}\n" for q, v in tail)
            + f"Historical quarterly mean: {usd(hist_mean)}.\n"
            f"Naive projection next {horizon_quarters} quarters:\n"
            + "".join(f"  {q}: {usd(v)}\n" for q, v in zip(proj_quarters, proj_vals))
        )
        result["narrative"] = ask_llm(SYSTEM, facts, num_predict=350)

    return result
