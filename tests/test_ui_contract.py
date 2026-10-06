"""Contract test — GET /approvals/pending must carry every field the minimal UI reads.

The UI (`agents/static/approvals.html`) is plain HTML/JS with no framework and no
build step, so browser automation would be disproportionate new infrastructure.
Instead this is a backend contract test: it parses the field names straight out of
the HTML/JS and asserts the live `GET /approvals/pending` response contains each
one, in the right place in the object graph.

Because the field list is read from the page (not hand-copied), the test can't
silently drift out of sync. If a future change to the response shape drops or
renames one of these fields, this fails immediately. Runs in ./predeploy.sh.
"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI_FILE = ROOT / "agents" / "static" / "approvals.html"


def _ui_field_refs() -> dict:
    """Field names the page's JS actually dereferences, grouped by the object
    they're read from. Kept as regex over the source so it tracks the real page."""
    html = UI_FILE.read_text()
    return {
        # rec.<x>  — a pending-list item
        "record": set(re.findall(r"\brec\.([A-Za-z_]\w*)", html)),
        # vr.<x>   — item["verification_report"]
        "verification_report": set(re.findall(r"\bvr\.([A-Za-z_]\w*)", html)),
        # appr.<x> — item["assigned_approver"]
        "assigned_approver": set(re.findall(r"\bappr\.([A-Za-z_]\w*)", html)),
        # alert.<x> — item["verification_report"]["alert"] (only when non-null)
        "alert": set(re.findall(r"\balert\.([A-Za-z_]\w*)", html)),
        # extracted keys: fieldRows() `order` table ["snake_key","Label"] + ext.<x>
        "extracted": (set(re.findall(r'\[\s*"([a-z_]+)"\s*,\s*"[^"]*"\s*\]', html))
                      | set(re.findall(r"\bext\.([A-Za-z_]\w*)", html))),
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    from approvals import service as A
    from approvals import store
    from approvals.notify import NotificationSender

    # isolate the append-only store in a temp dir; silence notifications
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "REPORTS_LOG", str(tmp_path / "verification_reports.jsonl"))
    monkeypatch.setattr(store, "EVENTS_LOG", str(tmp_path / "approval_events.jsonl"))

    class _Silent(NotificationSender):
        def notify(self, rec):  # noqa: D401
            pass

    monkeypatch.setattr(A, "_notifier", _Silent())

    from verification.baseline import load_baselines
    b = next(iter(load_baselines().values()))

    def _po(decision, severity, alert):
        return {
            "status": "OK", "decision": decision, "overall_severity": severity,
            "confidence": "high", "fraud": decision != "PASS",
            "fraud_type": None, "fraud_labels": [],
            "failed_checks": [] if decision == "PASS"
            else ["sender_domain_match", "baseline_routing_match"],
            "extracted": {
                "fund_name": b.fund_name, "entity": b.entity_name, "amount": 2_500_000.0,
                "bank_name": b.bank_name, "routing_number": b.routing_number,
                "account_number": "8840-2291-7734", "due_date": "2026-10-15",
            },
            "fund_baseline": {"fund_id": b.fund_id, "fund_name": b.fund_name},
            "checks": {"routing_checksum": {"passed": True}},
            "alert": alert,
        }

    A.ingest_pipeline_output(_po("PASS", "none", None))
    A.ingest_pipeline_output(_po("BLOCK", "high", {
        "subject": "BLOCK (high): spoofed sender domain",
        "body": "Do not release payment. Treat this as phishing.",
        "failed_checks": ["sender_domain_match"],
        "fraud_labels": ["spoofed_sender_domain"],
        "overall_severity": "high",
        "recommended_action": "Confirm with the GP on a known, separate channel.",
    }))

    from fastapi.testclient import TestClient

    from agents.app import app
    return TestClient(app)


def test_pending_response_has_every_field_the_ui_reads(client):
    # The field list is derived entirely from approvals.html — nothing below
    # names a page field by hand. `refs` is whatever _ui_field_refs() scraped.
    refs = _ui_field_refs()

    # Guard: the assertions further down are only meaningful if the regex actually
    # pulled names out of the page. If a future edit to approvals.html breaks the
    # patterns, fail loudly here rather than pass vacuously against empty sets.
    # (No field names here — just "the parse produced something".)
    for group, names in refs.items():
        assert names, (f"_ui_field_refs() parsed zero field names for '{group}' — "
                       f"the extractor has drifted from approvals.html")
    assert len(refs["record"]) >= 4 and len(refs["extracted"]) >= 3

    resp = client.get("/approvals/pending")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list) and len(body) == 2

    for item in body:
        assert not (refs["record"] - item.keys()), \
            f"/approvals/pending item is missing {sorted(refs['record'] - item.keys())}"

        vr = item["verification_report"]
        assert isinstance(vr, dict)
        assert not (refs["verification_report"] - vr.keys()), \
            f"verification_report is missing {sorted(refs['verification_report'] - vr.keys())}"

        appr = item["assigned_approver"]
        assert isinstance(appr, dict)
        assert not (refs["assigned_approver"] - appr.keys()), \
            f"assigned_approver is missing {sorted(refs['assigned_approver'] - appr.keys())}"

        ext = vr["extracted"]
        assert isinstance(ext, dict)
        assert not (refs["extracted"] - ext.keys()), \
            f"extracted is missing {sorted(refs['extracted'] - ext.keys())}"

    # alert sub-fields are only promised when an alert is present (UI guards `alert ?`)
    blocked = [i for i in body if i["verification_report"]["alert"]]
    assert blocked, "seeded a BLOCK record — its verification_report.alert must be non-null"
    for item in blocked:
        al = item["verification_report"]["alert"]
        assert not (refs["alert"] - al.keys()), \
            f"alert is missing {sorted(refs['alert'] - al.keys())}"
