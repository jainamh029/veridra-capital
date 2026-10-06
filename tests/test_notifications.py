"""Fast tests for the payment-approvals notification hook (Step 1).
No Ollama. Run by ./predeploy.sh.

Confirms: the hook is pluggable, fires exactly once per new PENDING_APPROVAL
record, carries the right approver + verdict, and that the only shipped
implementation is a logged/mock sender (no real provider).
"""
import os
import tempfile

import pytest

from approvals import service as A
from approvals import store
from approvals.model import ApprovalRecord
from approvals.notify import (LoggedNotificationSender, NotificationSender,
                              format_notification)


def _pipeline_output(decision="PASS", fund_id="FUND-07", severity="none"):
    return {
        "status": "OK", "decision": decision, "overall_severity": severity,
        "fraud": decision != "PASS", "fraud_type": None, "fraud_labels": [],
        "failed_checks": [] if decision == "PASS" else ["sender_domain_match"],
        "extracted": {"fund_name": "Thornbury Ventures Partners III", "entity": "x",
                      "amount": 1000, "bank_name": "b", "routing_number": "011401533",
                      "account_number": "a"},
        "fund_baseline": {"fund_id": fund_id, "fund_name": "Thornbury Ventures Partners III"},
        "checks": {"routing_checksum": {"passed": True}},
        "alert": None if decision == "PASS" else {"subject": "BLOCK", "body": "..."},
    }


@pytest.fixture
def scratch():
    d = tempfile.mkdtemp(prefix="notif_test_")
    store.reset(data_dir=d)
    A.set_notifier(None)          # default (logged) sender for this dir
    yield d
    A.set_notifier(None)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_ingest_writes_exactly_one_notification_line(scratch):
    rec = A.ingest_pipeline_output(_pipeline_output("BLOCK", severity="high"), data_dir=scratch)
    log = os.path.join(scratch, "notifications.log")
    lines = [l for l in open(log).read().splitlines() if l.strip()]
    assert len(lines) == 1
    line = lines[0]
    assert rec.assigned_approver["email"] in line
    assert rec.approval_id in line
    assert "verdict=BLOCK" in line and "severity=high" in line


def test_one_line_per_record_pass_included(scratch):
    for d in ("PASS", "REVIEW", "BLOCK", "PASS"):
        A.ingest_pipeline_output(_pipeline_output(d), data_dir=scratch)
    lines = [l for l in open(os.path.join(scratch, "notifications.log")).read().splitlines()
             if l.strip()]
    assert len(lines) == 4
    assert sum(1 for l in lines if "verdict=PASS" in l) == 2


def test_reversal_emits_one_distinguishable_notification(scratch):
    # a reversed record is a fresh PENDING thing needing a human decision — the
    # exact case notification exists for. It must add exactly one new line, and
    # that line must be distinguishable from the original create-time one.
    rec = A.ingest_pipeline_output(_pipeline_output("BLOCK"), data_dir=scratch)
    A.record_decision(rec.approval_id, "REJECTED", "a@x.example", "no", data_dir=scratch)
    log = os.path.join(scratch, "notifications.log")
    before = [l for l in open(log).read().splitlines() if l.strip()]
    assert len(before) == 1                              # create-time notification

    rev = A.reverse_decision(rec.approval_id, "b@x.example", "gp reconfirmed",
                             data_dir=scratch)
    after = [l for l in open(log).read().splitlines() if l.strip()]
    assert len(after) == 2                               # exactly one new line
    new_line = after[1]
    assert rev["approval_id"] in new_line                # for the NEW pending record
    assert rev["assigned_approver"]["email"] in new_line
    assert rec.approval_id in new_line                   # references what it supersedes
    # distinguishable via an event tag, not an indistinguishable duplicate
    assert "NOTIFY[REVERSAL]" in new_line
    assert "NOTIFY[NEW]" in before[0] and "NOTIFY[REVERSAL]" not in before[0]
    assert new_line != before[0]


def test_notifier_is_pluggable(scratch):
    seen = []

    class Capturing(NotificationSender):
        def notify(self, approval_record):
            seen.append(approval_record)

    A.set_notifier(Capturing())
    try:
        rec = A.ingest_pipeline_output(_pipeline_output("REVIEW"), data_dir=scratch)
        assert len(seen) == 1
        assert isinstance(seen[0], ApprovalRecord)
        assert seen[0].approval_id == rec.approval_id
        # custom sender was used instead of the logged one -> no file written
        assert not os.path.exists(os.path.join(scratch, "notifications.log"))
    finally:
        A.set_notifier(None)


def test_logged_sender_keeps_an_in_memory_copy(tmp_path):
    s = LoggedNotificationSender(log_path=str(tmp_path / "n.log"), echo=False)
    rec = ApprovalRecord(
        approval_id="ap_x", verification_report_id="vr_x", fund_id="F", fund_name="Fund X",
        assigned_approver={"name": "Dana Whitfield", "email": "dana@synthetic-ops.example"},
        created_at="2026-09-03T00:00:00Z", hub_decision="BLOCK", hub_severity="high",
    )
    s.notify(rec)
    assert s.sent == [format_notification(rec)]
    assert "Dana Whitfield" in s.sent[0] and "verdict=BLOCK" in s.sent[0]


def test_only_shipped_implementation_is_the_mock():
    # NotificationSender has exactly one concrete subclass in the module, and it
    # does no network I/O — a real provider is intentionally deferred.
    import inspect

    import approvals.notify as n
    concrete = [obj for _, obj in inspect.getmembers(n, inspect.isclass)
                if issubclass(obj, NotificationSender) and obj is not NotificationSender]
    assert concrete == [LoggedNotificationSender]
    src = inspect.getsource(n)
    for banned in ("smtplib", "requests", "httpx", "urllib.request", "slack_sdk", "socket"):
        assert banned not in src, f"real-provider I/O ({banned}) leaked into notify.py"
