"""Endpoint plumbing for cash planning: the deprecated /cash path (Fix 1) and
point-in-time ?as_of (Fix 2). No new computation — every number is asserted
identical to cash_planning.core.cash_position(). Ollama-free.
"""
import pathlib

import pytest
from fastapi.testclient import TestClient

from agents.app import app
from cash_planning import core

client = TestClient(app)
ROOT = pathlib.Path(__file__).resolve().parents[1]


# --------------------------------------------------------------- Fix 1
def test_old_cash_endpoint_is_gone_and_points_to_the_new_one():
    r = client.get("/cash/FUND-01")
    assert r.status_code == 410
    detail = r.json()["detail"]
    assert detail["use"] == "/cash-planning/FUND-01"


def test_old_cash_planning_module_was_removed():
    # the duplicate, non-approval-gated code path must not exist any more
    assert not (ROOT / "agents" / "cash_planning.py").exists()
    import agents.app as a
    src = pathlib.Path(a.__file__).read_text()
    assert "from .cash_planning import" not in src


# --------------------------------------------------------------- Fix 2
def test_as_of_is_a_real_point_in_time_param():
    # FUND-01's generated running balance differs across these two dates
    early = client.get("/cash-planning/FUND-01?as_of=2022-12-31").json()
    late = client.get("/cash-planning/FUND-01?as_of=2023-12-31").json()

    assert early["as_of_ledger"] == "2022-12-31"
    assert late["as_of_ledger"] == "2023-12-31"
    assert early["confirmed_cash_balance"] != late["confirmed_cash_balance"]
    assert late["confirmed_cash_balance"] > early["confirmed_cash_balance"]

    # identical to calling core directly — endpoint adds no math
    assert early == core.cash_position("FUND-01", as_of="2022-12-31")
    assert late == core.cash_position("FUND-01", as_of="2023-12-31")
    assert early["reconciliation"]["ok"] and late["reconciliation"]["ok"]


def test_as_of_default_is_latest_ledger_date():
    default = client.get("/cash-planning/FUND-01").json()
    assert default["as_of_ledger"] == core.latest_ledger_date()


def test_as_of_on_the_overview_endpoint():
    body = client.get("/cash-planning?as_of=2023-12-31").json()
    assert isinstance(body, list) and len(body) == len(core.list_fund_ids())
    assert all(f["as_of_ledger"] == "2023-12-31" for f in body)
    f1 = next(f for f in body if f["fund_id"] == "FUND-01")
    assert f1 == core.cash_position("FUND-01", as_of="2023-12-31")


@pytest.mark.parametrize("bad", ["nonsense", "2023-13-40", "12/31/2023", "2023"])
def test_bad_as_of_is_422_not_silently_latest(bad):
    assert client.get(f"/cash-planning/FUND-01?as_of={bad}").status_code == 422
    assert client.get(f"/cash-planning?as_of={bad}").status_code == 422
