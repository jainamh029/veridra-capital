"""Module 5 — K-1 Routing: LIVE model path. Opt-in, skipped by default.

Run explicitly:  K1_LIVE_OLLAMA=1 ./capital-call-env/bin/python -m pytest tests/test_k1_routing_live.py -q

This is the one test that requires a real Ollama connection (qwen2.5:3b-instruct),
kept so the real extraction path can be re-confirmed periodically. It is skipped
in ./predeploy.sh so the gate stays fast and Ollama-independent.
"""
import os
import tempfile

import pytest

from k1_routing import service as k1_service
from k1_routing import store as k1_store
from k1_routing.synthetic import SYNTHETIC_K1_DOCS

pytestmark = pytest.mark.skipif(
    os.environ.get("K1_LIVE_OLLAMA") != "1",
    reason="live Ollama test; set K1_LIVE_OLLAMA=1 to run",
)


def test_real_model_extraction_and_matching_end_to_end():
    d = tempfile.mkdtemp()
    k1_store.reset(data_dir=d)
    wrong = []
    for doc in SYNTHETIC_K1_DOCS:
        # no `extractor` -> the real _model_extractor / qwen2.5:3b-instruct
        r = k1_service.ingest_document(doc["text"], doc_id=doc["doc_id"],
                                       case=doc["case"], data_dir=d)
        assert r["status"] != "AWAITING_EXTRACTION", f"{doc['doc_id']}: Ollama not reachable"
        assert r["extracted"]["extraction_source"] == "model"
        if r["status"] != doc["expect"]:
            wrong.append((doc["doc_id"], r["status"], doc["expect"]))
        elif doc["expect"] == "ROUTED":
            if (r["matched_fund"] or {}).get("fund_id") != doc["fund_id"] or \
               (r["matched_lp"] or {}).get("lp_id") != doc["lp_id"]:
                wrong.append((doc["doc_id"], "wrong entity", r["matched_fund"], r["matched_lp"]))
        elif r["review_reason"] != doc["expect_reason"]:
            wrong.append((doc["doc_id"], r["review_reason"], doc["expect_reason"]))
    assert not wrong, f"model-path mismatches: {wrong}"
