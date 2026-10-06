"""Fast state-machine + audit-trail tests for Module 2 (payment approvals).
No Ollama. Run by ./predeploy.sh.
"""
import os
import subprocess
import tempfile

import pytest

from approvals import service as A
from approvals import store
from approvals.model import ApprovalState

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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
    d = tempfile.mkdtemp(prefix="approvals_test_")
    store.reset(data_dir=d)
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_ingest_creates_one_pending_with_approver_and_report_ref(scratch):
    rec = A.ingest_pipeline_output(_pipeline_output("PASS"), data_dir=scratch)
    assert rec.state == ApprovalState.PENDING_APPROVAL.value
    assert rec.assigned_approver and rec.assigned_approver["email"].endswith("synthetic-ops.example")
    assert rec.verification_report_id.startswith("vr_")
    assert len(A.list_all(data_dir=scratch)) == 1
    assert len(A.list_pending(data_dir=scratch)) == 1


def test_pass_notices_are_not_skipped(scratch):
    for d in ("PASS", "REVIEW", "BLOCK"):
        A.ingest_pipeline_output(_pipeline_output(d), data_dir=scratch)
    pend = A.list_pending(data_dir=scratch)
    assert len(pend) == 3
    assert {r["hub_decision"] for r in pend} == {"PASS", "REVIEW", "BLOCK"}


def test_report_is_referenced_not_copied(scratch):
    rec = A.ingest_pipeline_output(_pipeline_output("BLOCK"), data_dir=scratch)
    full = A.get_record(rec.approval_id, data_dir=scratch)
    # the record itself does not carry the report body...
    assert "checks" not in full and "extracted" not in full and "alert" not in full
    # ...it is fetched via the reference and includes the full per-check breakdown
    assert full["verification_report"]["checks"]
    assert full["verification_report"]["decision"] == "BLOCK"


def test_decide_records_audit_fields(scratch):
    rec = A.ingest_pipeline_output(_pipeline_output("PASS"), data_dir=scratch)
    out = A.record_decision(rec.approval_id, "APPROVED",
                            "dana@synthetic-ops.example", "cleared", data_dir=scratch)
    assert out["state"] == "APPROVED"
    assert out["decision_by"] == "dana@synthetic-ops.example"
    assert out["decision_at"] and out["decision_note"] == "cleared"
    assert A.list_pending(data_dir=scratch) == []


def test_double_decide_is_refused_and_original_untouched(scratch):
    rec = A.ingest_pipeline_output(_pipeline_output("BLOCK"), data_dir=scratch)
    A.record_decision(rec.approval_id, "REJECTED", "a@x.example", "bad", data_dir=scratch)
    with pytest.raises(A.AlreadyDecidedError):
        A.record_decision(rec.approval_id, "APPROVED", "b@x.example", "flip", data_dir=scratch)
    still = A.get_record(rec.approval_id, data_dir=scratch)
    assert still["state"] == "REJECTED" and still["decision_by"] == "a@x.example"
    assert sum(1 for e in store.events_for(rec.approval_id, data_dir=scratch)
               if e["event"] == "DECIDED") == 1


def test_invalid_decision_state_rejected(scratch):
    rec = A.ingest_pipeline_output(_pipeline_output(), data_dir=scratch)
    for bad in ("PENDING_APPROVAL", "approved", "MAYBE", ""):
        with pytest.raises(A.ApprovalError):
            A.record_decision(rec.approval_id, bad, "a@x.example", data_dir=scratch)


def test_reversal_is_new_record_old_untouched(scratch):
    rec = A.ingest_pipeline_output(_pipeline_output("BLOCK"), data_dir=scratch)
    A.record_decision(rec.approval_id, "REJECTED", "a@x.example", "no", data_dir=scratch)
    rev = A.reverse_decision(rec.approval_id, "b@x.example", "gp reconfirmed", data_dir=scratch)
    assert rev["approval_id"] != rec.approval_id
    assert rev["supersedes"] == rec.approval_id
    assert rev["state"] == "PENDING_APPROVAL"
    old = A.get_record(rec.approval_id, data_dir=scratch)
    assert old["state"] == "REJECTED"            # NOT edited
    assert old["superseded_by"] == [rev["approval_id"]]


def test_cannot_reverse_a_pending_record(scratch):
    rec = A.ingest_pipeline_output(_pipeline_output(), data_dir=scratch)
    with pytest.raises(A.ApprovalError):
        A.reverse_decision(rec.approval_id, "a@x.example", "n", data_dir=scratch)


def test_get_missing_record_raises(scratch):
    with pytest.raises(A.NotFoundError):
        A.get_record("ap_doesnotexist", data_dir=scratch)


def test_no_payment_execution_code_in_module():
    pat = (r"send_payment|execute_wire|send_wire|transfer_funds|initiate_(payment|transfer)|"
           r"(ach|swift|fedwire)_(send|submit)|pay_out|disburse|remit_funds|release_funds")
    r = subprocess.run(["grep", "-rInE", "--include=*.py",
                        "--exclude=test_batch.py", "--exclude=test_approvals.py",
                        pat, os.path.join(ROOT, "approvals"), os.path.join(ROOT, "agents")],
                       capture_output=True, text=True)
    assert r.returncode != 0 and not r.stdout.strip(), \
        f"payment-execution-shaped code found:\n{r.stdout}"
