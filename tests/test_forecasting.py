"""Module 4 — Forecasting: determinism + direction (this module's equivalent of a
reconciliation check) and the "no model in the math / don't oversell" guards.
No Ollama.
"""
import ast
import inspect
import json

import pytest

from forecasting import core as fc
from forecasting import narrative as fc_narrative


def _hist(*pairs):
    return [fc.CallEvent(date=d, amount=float(a), source="ledger_contribution", ref=f"E{i:03d}")
            for i, (d, a) in enumerate(pairs)]


# monthly cadence, gently rising amounts
BASE = _hist(("2025-01-06", 1_000_000), ("2025-02-05", 1_100_000),
             ("2025-03-07", 1_200_000), ("2025-04-06", 1_300_000),
             ("2025-05-06", 1_400_000))
AS_OF = "2025-06-01"


# ---------------------------------------------------------- determinism
def test_projection_is_byte_identical_on_repeat_and_order_independent():
    a = fc.project_next_call(BASE, as_of=AS_OF)
    b = fc.project_next_call(BASE, as_of=AS_OF)
    c = fc.project_next_call(list(reversed(BASE)), as_of=AS_OF)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert json.dumps(a, sort_keys=True) == json.dumps(c, sort_keys=True)


# ---------------------------------------------------------- direction (the "recon")
def test_larger_recent_amount_shifts_the_estimate_up_smaller_shifts_it_down():
    base_est = fc.project_next_call(BASE, as_of=AS_OF)["next_expected_call"]["estimated_amount"]

    bigger = BASE[:-1] + [fc.CallEvent(date="2025-05-06", amount=5_000_000.0,
                                       source="ledger_contribution", ref="E999")]
    up = fc.project_next_call(bigger, as_of=AS_OF)["next_expected_call"]["estimated_amount"]
    assert up > base_est

    smaller = BASE[:-1] + [fc.CallEvent(date="2025-05-06", amount=100_000.0,
                                        source="ledger_contribution", ref="E999")]
    down = fc.project_next_call(smaller, as_of=AS_OF)["next_expected_call"]["estimated_amount"]
    assert down < base_est


def test_wider_intervals_push_the_projected_window_later():
    tight = fc.project_next_call(BASE, as_of=AS_OF)["next_expected_call"]
    wide = fc.project_next_call(
        _hist(("2025-01-06", 1_000_000), ("2025-04-06", 1_100_000),
              ("2025-07-06", 1_200_000), ("2025-10-06", 1_300_000)),
        as_of="2025-11-01")["next_expected_call"]
    assert tight["point_estimate_date"] < wide["point_estimate_date"]
    # ~monthly gap -> a few weeks out; ~quarterly gap -> a few months out
    assert wide["window_end"] > wide["window_start"] > "2025-10-06"


# ---------------------------------------------------------- honest about limits
def test_insufficient_history_returns_no_projection_and_does_not_crash():
    for h in ([], _hist(("2025-01-01", 1_000_000))):
        out = fc.project_next_call(h, as_of=AS_OF)
        assert out["sufficient_history"] is False
        assert out["next_expected_call"] is None and out["basis"] is None
        assert "reason" in out and out["type"] == "projected_estimate"


def test_method_and_notes_never_oversell_the_projection():
    out = fc.project_next_call(BASE, as_of=AS_OF)
    blob = (out["method"] + " " + out["next_expected_call"]["note"]).lower()
    assert "extrapolation" in out["method"].lower()
    assert "not a model" in out["method"].lower() or "not a forecasting model" in blob
    for oversold in ("machine learning", "neural", "deep learning", " ai ", "predictive model",
                     "sophisticated", "accurate forecast"):
        assert oversold not in blob


def test_projection_math_has_no_model_dependency():
    src = inspect.getsource(fc)
    assert "ask_llm" not in src
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("narrative" in m or "ollama" in m.lower() or m == "agents.common"
                   for m in imported), f"forecasting.core imports a model path: {imported}"


def test_narrative_layer_is_optional_and_isolated():
    proj = fc.project_next_call(BASE, as_of=AS_OF)
    off = fc_narrative.describe(proj, enabled=False)
    assert off == {"narrative": None, "generated": False, "reason": "disabled"}


# ---------------------------------------------------------- Gap 3: no fabricated forecast
def test_narrative_does_not_call_the_model_when_there_is_no_projection(monkeypatch):
    """?narrative=true on a fund with < 2 calls must NOT reach the model — it would
    invent a date/amount. describe() short-circuits to a fixed honest message."""
    def _boom(*a, **k):
        raise AssertionError("ask_llm was called for a no-projection fund")

    monkeypatch.setattr(fc_narrative, "ask_llm", _boom)
    insuff = fc.project_next_call(_hist(("2025-01-01", 1_000_000)), as_of=AS_OF)
    assert insuff["sufficient_history"] is False

    out = fc_narrative.describe(insuff, enabled=True)          # would raise if model called
    assert out == {"narrative": fc_narrative.NO_PROJECTION_MESSAGE,
                   "generated": False, "reason": "insufficient_history"}
    # the fixed message carries no fabricated date or dollar figure
    assert not any(ch.isdigit() for ch in out["narrative"])


# ---------------------------------------------------------- Gap 4: thin-data window
def test_exactly_two_calls_window_is_not_zero_width_and_flagged_low_confidence():
    two = _hist(("2025-01-10", 1_000_000), ("2025-02-09", 1_200_000))   # one 30-day gap
    p = fc.project_next_call(two, as_of="2025-03-01")
    nx, b = p["next_expected_call"], p["basis"]
    assert nx["window_start"] != nx["window_end"], "zero-width window on thinnest data"
    assert b["interval_spread_days"] > 0
    assert b["interval_sample_size"] == 1
    assert b["low_confidence"] is True and nx["confidence"] == "low"
    assert "LOW CONFIDENCE" in nx["note"]
    # locked-in geometry: spread = half the single 30-day gap
    assert b["interval_spread_days"] == 15.0
    assert nx["point_estimate_date"] == "2025-03-11"            # 2025-02-09 + 30d
    assert (nx["window_start"], nx["window_end"]) == ("2025-02-24", "2025-03-26")


def test_identical_gaps_never_produce_a_zero_width_window():
    from datetime import date, timedelta
    ev = [fc.CallEvent(date=(date(2025, 1, 1) + timedelta(days=30 * i)).isoformat(),
                       amount=1_000_000.0, source="x", ref=str(i)) for i in range(5)]
    p = fc.project_next_call(ev, as_of="2025-07-01")
    nx, b = p["next_expected_call"], p["basis"]
    assert b["intervals_observed_days"] == [30, 30, 30, 30]     # pstdev of these is 0
    assert b["interval_spread_days"] == 7.5                     # floored at avg_interval * 0.25
    assert nx["window_start"] != nx["window_end"]
    assert b["low_confidence"] is False and nx["confidence"] == "moderate"   # 4 gaps


def test_low_confidence_is_purely_a_function_of_gap_count():
    def gaps(n):
        return _hist(*[(f"2025-{m:02d}-01", 1_000_000) for m in range(1, n + 2)])
    assert fc.project_next_call(gaps(1), as_of="2026-01-01")["basis"]["low_confidence"] is True
    assert fc.project_next_call(gaps(2), as_of="2026-01-01")["basis"]["low_confidence"] is True
    assert fc.project_next_call(gaps(3), as_of="2026-01-01")["basis"]["low_confidence"] is False


# ---------------------------------------------------------- adapter against real data
def test_history_adapter_reads_real_confirmed_calls():
    import tempfile

    from approvals import store
    d = tempfile.mkdtemp()
    store.reset(data_dir=d)
    hist = fc.approved_call_history("FUND-01", data_dir=d)
    assert len(hist) > 50                     # FUND-01 has years of contribution events
    assert all(e.source == "ledger_contribution" for e in hist)  # nothing approved yet in scratch
    assert hist == sorted(hist, key=lambda e: (e.date, e.ref))
    assert all(e.amount > 0 for e in hist)
