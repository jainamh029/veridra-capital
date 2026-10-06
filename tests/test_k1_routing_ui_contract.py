"""Contract test — GET /k1-routing must carry every field k1-routing.html reads.

Same pattern as the other three UI contract tests: field names scraped from the
page's JS, asserted against the live endpoint response, negative-proofed by
dropping a field.
"""
import copy
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI_FILE = ROOT / "agents" / "static" / "k1-routing.html"


def _ui_field_refs() -> dict:
    html = UI_FILE.read_text()
    doc = set(re.findall(r"\bdoc\.([A-Za-z_]\w*)", html))
    ext = (set(re.findall(r"\bext\.([A-Za-z_]\w*)", html))
           | set(re.findall(r'\[\s*"([a-z_]+)"\s*,\s*"[^"]*"\s*\]', html)))
    rt = set(re.findall(r"\brt\.([A-Za-z_]\w*)", html))
    sm = set(re.findall(r"\bsm\.([A-Za-z_]\w*)", html))
    # matched_fund / matched_lp are read via a shared matchLine(m, kind) helper:
    m = set(re.findall(r"\bm\.([A-Za-z_]\w*)", html))
    return {
        "document": doc,
        "extracted": ext,
        "routed_to": rt,
        "summary": sm,
        "matched_fund": {k for k in m if not k.startswith("lp_")},   # exact, match_score, fund_*
        "matched_lp": {k for k in m if not k.startswith("fund_")},   # exact, match_score, lp_*
    }


def _assert_shape(body: dict, refs: dict):
    assert not (refs["summary"] - body["summary"].keys()), \
        f"summary missing {sorted(refs['summary'] - body['summary'].keys())}"
    docs = body["documents"]
    assert docs, "expected seeded documents"

    for d in docs:
        assert not (refs["document"] - d.keys()), \
            f"{d.get('doc_id')}: document missing {sorted(refs['document'] - d.keys())}"
        assert not (refs["extracted"] - d["extracted"].keys()), \
            f"{d['doc_id']}: extracted missing {sorted(refs['extracted'] - d['extracted'].keys())}"

    routed = [d for d in docs if d["status"] == "ROUTED"]
    assert routed, "expected at least one ROUTED doc to exercise match/routed_to fields"
    for d in routed:
        assert not (refs["matched_fund"] - d["matched_fund"].keys()), \
            f"{d['doc_id']}: matched_fund missing {sorted(refs['matched_fund'] - d['matched_fund'].keys())}"
        assert not (refs["matched_lp"] - d["matched_lp"].keys()), \
            f"{d['doc_id']}: matched_lp missing {sorted(refs['matched_lp'] - d['matched_lp'].keys())}"
        assert not (refs["routed_to"] - d["routed_to"].keys()), \
            f"{d['doc_id']}: routed_to missing {sorted(refs['routed_to'] - d['routed_to'].keys())}"

    review = [d for d in docs if d["status"] == "NEEDS_REVIEW"]
    assert review, "expected a NEEDS_REVIEW doc"
    for d in review:
        assert d["review_reason"] and d["review_detail"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from k1_routing import core as k1_core
    from k1_routing import service as k1_service
    from k1_routing import store as k1_store
    from k1_routing.synthetic import SYNTHETIC_K1_DOCS

    monkeypatch.setattr(k1_store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(k1_store, "EVENTS_LOG", str(tmp_path / "k1_events.jsonl"))

    for d in SYNTHETIC_K1_DOCS:
        k1_service.ingest_document(d["text"], doc_id=d["doc_id"], case=d["case"],
                                   extractor=k1_core.regex_extract_explicit)

    from fastapi.testclient import TestClient

    from agents.app import app
    return TestClient(app)


def test_k1_routing_response_has_every_field_the_ui_reads(client):
    refs = _ui_field_refs()
    for group, names in refs.items():
        assert names, f"_ui_field_refs() parsed zero names for {group!r} — extractor drifted"
    assert len(refs["document"]) >= 8

    body = client.get("/k1-routing").json()
    _assert_shape(body, refs)

    # per-fund endpoint carries the same document shape
    one = client.get("/k1-routing/FUND-01").json()
    assert one["fund_id"] == "FUND-01" and one["count"] >= 1
    for d in one["documents"]:
        assert not (refs["document"] - d.keys())


def test_negative_proof_contract_fails_when_a_field_is_dropped(client):
    refs = _ui_field_refs()
    good = client.get("/k1-routing").json()
    _assert_shape(good, refs)                      # sanity

    broken = copy.deepcopy(good)
    for d in broken["documents"]:
        d["extracted"].pop("lp_name", None)
    with pytest.raises(AssertionError):
        _assert_shape(broken, refs)

    broken2 = copy.deepcopy(good)
    broken2["summary"].pop("needs_review", None)
    with pytest.raises(AssertionError):
        _assert_shape(broken2, refs)

    # a nested field on the ROUTED branch
    broken3 = copy.deepcopy(good)
    for d in broken3["documents"]:
        if d["status"] == "ROUTED":
            d["matched_fund"].pop("fund_id", None)
    with pytest.raises(AssertionError):
        _assert_shape(broken3, refs)
