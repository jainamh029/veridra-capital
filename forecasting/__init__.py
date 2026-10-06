"""Module 4 — Scenario / Forecasting.

Deterministic layer: `forecasting.core` (next-expected-call projection from a
fund's own confirmed capital-call history). Optional prose: `forecasting.narrative`.

This is a SIMPLE HISTORICAL EXTRAPOLATION — average interval between past calls,
mean of recent call amounts. It is not a forecasting model and must never be
described as one.
"""

from .core import CallEvent, approved_call_history, project_next_call

__all__ = ["project_next_call", "approved_call_history", "CallEvent"]
