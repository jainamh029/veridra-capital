"""Contract test — GET /forecasting must carry every field forecasting.html reads.

Same pattern as tests/test_cash_planning_ui_contract.py: field names scraped from
the page's JS (not hand-typed), asserted against the live endpoint's real
response, negative-proofed by dropping a field. No browser automation.
"""
import copy
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI_FILE = ROOT / "agents" / "static" / "forecasting.html"


def _ui_field_refs() -> dict:
    html = UI_FILE.read_text()
    return {
        "fund": set(re.findall(r"\bfund\.([A-Za-z_]\w*)", html)),
        "context": set(re.findall(r"\bctx\.([A-Za-z_]\w*)", html)),
        "next_expected_call": set(re.findall(r"\bnx\.([A-Za-z_]\w*)", html)),
        "basis": set(re.findall(r"\bbasis\.([A-Za-z_]\w*)", html)),
        "history_item": set(re.findall(r"\bhp\.([A-Za-z_]\w*)", html)),
        "narrative": set(re.findall(r"\bnar\.([A-Za-z_]\w*)", html)),
    }


# `reason` (only when history is insufficient) and `narrative` (only ?narrative=true)
# are conditionals the JS guards — like `alert` on the approvals page.
_OPTIONAL_FUND = {"reason", "narrative"}


def _assert_item_matches(item: dict, refs: dict, *, require_narrative: bool):
    assert not ((refs["fund"] - _OPTIONAL_FUND) - item.keys()), \
        f"forecasting item missing {sorted((refs['fund'] - _OPTIONAL_FUND) - item.keys())}"

    ctx = item["context"]
    assert isinstance(ctx, dict) and not (refs["context"] - ctx.keys()), \
        f"context missing {sorted(refs['context'] - set(ctx))}"

    assert item["sufficient_history"] is True, "real funds should have projectable history"
    nx = item["next_expected_call"]
    assert isinstance(nx, dict) and not (refs["next_expected_call"] - nx.keys()), \
        f"next_expected_call missing {sorted(refs['next_expected_call'] - set(nx))}"

    basis = item["basis"]
    assert isinstance(basis, dict) and not (refs["basis"] - basis.keys()), \
        f"basis missing {sorted(refs['basis'] - set(basis))}"

    assert item["history_used"], "a projection must ship the history it is based on"
    for hp in item["history_used"]:
        assert not (refs["history_item"] - hp.keys()), \
            f"history_used item missing {sorted(refs['history_item'] - set(hp))}"

    if require_narrative:
        assert "narrative" in item
        assert not (refs["narrative"] - item["narrative"].keys()), \
            f"narrative missing {sorted(refs['narrative'] - set(item['narrative']))}"


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

    from agents import app as agents_app
    monkeypatch.setattr(agents_app.fc_narrative, "describe",
                        lambda proj, **kw: {"narrative": "stub.", "generated": True, "reason": None})

    from fastapi.testclient import TestClient
    return TestClient(agents_app.app)


def test_forecasting_response_has_every_field_the_ui_reads(client):
    refs = _ui_field_refs()
    for group, names in refs.items():
        assert names, f"_ui_field_refs() parsed zero names for {group!r} — extractor drifted"
    assert len(refs["fund"]) >= 8

    body = client.get("/forecasting").json()
    assert isinstance(body, list) and len(body) >= 2
    f1 = next(f for f in body if f["fund_id"] == "FUND-01")
    _assert_item_matches(f1, refs, require_narrative=False)
    assert f1["type"] == "projected_estimate"     # labelled in the payload itself

    one = client.get("/forecasting/FUND-01").json()
    _assert_item_matches(one, refs, require_narrative=False)

    narr = client.get("/forecasting/FUND-01?narrative=true").json()
    _assert_item_matches(narr, refs, require_narrative=True)


def test_negative_proof_contract_fails_when_a_field_is_dropped(client):
    refs = _ui_field_refs()
    good = client.get("/forecasting/FUND-01").json()
    _assert_item_matches(good, refs, require_narrative=False)     # sanity

    broken = copy.deepcopy(good)
    del broken["next_expected_call"]["window_start"]
    with pytest.raises(AssertionError):
        _assert_item_matches(broken, refs, require_narrative=False)

    broken2 = copy.deepcopy(good)
    del broken2["context"]        # `context` is scraped from fund.context -> caught by the first assert
    with pytest.raises(AssertionError):
        _assert_item_matches(broken2, refs, require_narrative=False)


# ---------------------------------------------------------- Gap 2: insufficient-history UI
def test_api_returns_no_projection_before_a_fund_has_history(client):
    # FUND-01's first call is 2022-01-14; as_of before that -> zero history
    r = client.get("/forecasting/FUND-01?as_of=2021-06-01").json()
    assert r["sufficient_history"] is False
    assert r["next_expected_call"] is None and r["basis"] is None
    assert "reason" in r
    # tiers 1 & 2 still render from cash planning
    assert "confirmed_cash_balance" in r["context"]


def test_forecasting_html_shows_an_unambiguous_message_for_no_projection():
    """The !sufficient_history branch must render an explicit statement and must
    NOT render a number that could be misread as a $0 projection."""
    html = UI_FILE.read_text()
    m = re.search(r"if \(!fund\.sufficient_history\)\s*\{(.+?)\n  \}", html, re.S)
    assert m, "could not find the !sufficient_history branch in forecasting.html"
    branch = m.group(1)

    assert "No projection" in branch
    assert "not a $0 projection" in branch or "absence of one" in branch
    # the branch must not pull any projected number/window into view
    for forbidden in ("money(nx.", "nx.estimated_amount", "nx.window_start", "basis.avg_interval_days"):
        assert forbidden not in branch, f"no-projection branch references {forbidden!r}"
