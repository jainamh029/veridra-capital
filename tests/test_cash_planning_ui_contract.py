"""Contract test — GET /cash-planning must carry every field cash-planning.html reads.

Same pattern as tests/test_ui_contract.py: the field list is scraped from the
page's JS (not hand-typed), asserted against the live endpoint's real response,
and negative-proofed by dropping a field and confirming the check fails. No
browser automation. Runs in ./predeploy.sh.
"""
import copy
import datetime
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI_FILE = ROOT / "agents" / "static" / "cash-planning.html"


def _ui_field_refs() -> dict:
    """Field names the page's JS dereferences, grouped by the object they come from.
    Regex over the source so it tracks the real page."""
    html = UI_FILE.read_text()
    return {
        "fund": set(re.findall(r"\bfund\.([A-Za-z_]\w*)", html)),
        "confirmed_components": (set(re.findall(r"\bcomp\.([A-Za-z_]\w*)", html))
                                 | set(re.findall(r'\[\s*"([a-z_]+)"\s*,\s*"[^"]*"\s*\]', html))),
        "near_term_obligations": set(re.findall(r"\bnear\.([A-Za-z_]\w*)", html)),
        "near_term_item": set(re.findall(r"\bobl\.([A-Za-z_]\w*)", html)),
        "excluded_from_balance": set(re.findall(r"\bexcl\.([A-Za-z_]\w*)", html)),
        "reconciliation": set(re.findall(r"\brecon\.([A-Za-z_]\w*)", html)),
        "narrative": set(re.findall(r"\bnar\.([A-Za-z_]\w*)", html)),
    }


def _assert_item_matches(item: dict, refs: dict, *, require_items: bool, require_narrative: bool):
    # `narrative` is only present with ?narrative=true (JS guards it) — like `alert`
    # on the approvals page.
    fund_required = refs["fund"] - {"narrative"}
    assert not (fund_required - item.keys()), \
        f"cash-planning item missing {sorted(fund_required - item.keys())}"

    # every nested container the JS reads must be present and carry its fields
    for container, group in (("confirmed_components", "confirmed_components"),
                             ("near_term_obligations", "near_term_obligations"),
                             ("excluded_from_balance", "excluded_from_balance"),
                             ("reconciliation", "reconciliation")):
        assert container in item, f"response missing {container!r}"
        sub = item[container]
        assert isinstance(sub, dict) and not (refs[group] - sub.keys()), \
            f"{container} missing {sorted(refs[group] - set(sub if isinstance(sub, dict) else []))}"

    near = item["near_term_obligations"]
    if require_items:
        assert near["items"], "expected a seeded near-term obligation to exercise item fields"
    for obl in near["items"]:
        assert not (refs["near_term_item"] - obl.keys()), \
            f"near_term item missing {sorted(refs['near_term_item'] - obl.keys())}"

    if require_narrative:
        assert "narrative" in item, "?narrative=true response must carry `narrative`"
        assert not (refs["narrative"] - item["narrative"].keys()), \
            f"narrative missing {sorted(refs['narrative'] - item['narrative'].keys())}"


SEEDED_FUND = "FUND-01"


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

    # the contract test checks the SHAPE of the narrative block, not that a real
    # model ran — stub describe() so predeploy stays fast and Ollama-independent.
    # (narrative.describe's real behaviour is covered by tests/test_cash_planning.py)
    from agents import app as agents_app
    monkeypatch.setattr(agents_app.cash_narrative, "describe",
                        lambda pos, **kw: {"narrative": "stub summary.",
                                           "generated": True, "reason": None})

    from verification.baseline import load_baselines
    b = load_baselines()[SEEDED_FUND]
    near_due = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()

    def _po(amount, due, decision="PASS"):
        return {
            "status": "OK", "decision": decision, "overall_severity": "none",
            "fraud": decision != "PASS", "fraud_type": None, "fraud_labels": [],
            "failed_checks": [], "confidence": "high",
            "extracted": {"fund_name": b.fund_name, "entity": b.entity_name, "amount": amount,
                          "bank_name": b.bank_name, "routing_number": b.routing_number,
                          "account_number": "8840-2291-7734", "due_date": due},
            "fund_baseline": {"fund_id": b.fund_id, "fund_name": b.fund_name},
            "checks": {"routing_checksum": {"passed": True}},
            "alert": None,
        }

    # one APPROVED (enters balance) + one near-term PENDING (listed, not in balance)
    approved = A.ingest_pipeline_output(_po(1_500_000.00, "2026-06-01"))
    A.record_decision(approved.approval_id, "APPROVED", "c@synthetic-ops.example", "ok")
    A.ingest_pipeline_output(_po(3_200_000.00, near_due))

    from fastapi.testclient import TestClient

    from agents.app import app
    return TestClient(app)


def test_cash_planning_response_has_every_field_the_ui_reads(client):
    refs = _ui_field_refs()

    # guard: the scrape actually produced field names (non-vacuous)
    for group, names in refs.items():
        assert names, f"_ui_field_refs() parsed zero names for {group!r} — extractor drifted"
    assert len(refs["fund"]) >= 6

    # overview list
    resp = client.get("/cash-planning")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list) and len(body) >= 2
    seeded = next(f for f in body if f["fund_id"] == SEEDED_FUND)
    _assert_item_matches(seeded, refs, require_items=True, require_narrative=False)
    # the approved call is in the balance; the pending one is NOT
    assert seeded["confirmed_components"]["approved_capital_calls_count"] == 1
    assert seeded["near_term_obligations"]["count"] == 1

    # single-fund endpoint, same shape
    one = client.get(f"/cash-planning/{SEEDED_FUND}")
    assert one.status_code == 200
    _assert_item_matches(one.json(), refs, require_items=True, require_narrative=False)

    # ?narrative=true adds the narrative block (keys present even if Ollama is down)
    narr = client.get(f"/cash-planning/{SEEDED_FUND}?narrative=true")
    assert narr.status_code == 200
    _assert_item_matches(narr.json(), refs, require_items=True, require_narrative=True)


def test_negative_proof_contract_fails_when_a_field_is_dropped(client):
    refs = _ui_field_refs()
    good = client.get(f"/cash-planning/{SEEDED_FUND}").json()
    _assert_item_matches(good, refs, require_items=True, require_narrative=False)  # sanity

    # drop one nested field the page reads -> the contract check must fail
    broken = copy.deepcopy(good)
    del broken["confirmed_components"]["historical_ledger_balance"]
    with pytest.raises(AssertionError):
        _assert_item_matches(broken, refs, require_items=True, require_narrative=False)

    # and one top-level container
    broken2 = copy.deepcopy(good)
    del broken2["reconciliation"]
    with pytest.raises(AssertionError):
        _assert_item_matches(broken2, refs, require_items=True, require_narrative=False)
