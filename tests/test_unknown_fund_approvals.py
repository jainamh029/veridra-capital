"""Unknown-fund (NEEDS_ONBOARDING) notices in payment approvals.

Gap found: a capital call for a fund with no baseline on file was ingested into a
PENDING_APPROVAL record with `assigned_approver = None` — an ownerless record
routed to nobody, for what is arguably the higher-attention case (an entirely
unknown payee). Fixed by routing unresolved funds to a standing
`ONBOARDING_REVIEW_APPROVER` bucket, in code.

These tests are Ollama-free: they feed `ingest_pipeline_output` a hub output dict
shaped exactly like the real `status="NEEDS_ONBOARDING"` payload (captured from a
live run). Runs in ./predeploy.sh.
"""
import os
import tempfile

import pytest

from approvals import service as A
from approvals import store
from approvals.model import ApprovalState


# ---- hub output fixtures (shapes copied from real run_pipeline output) --------
def _needs_onboarding_output(fund_name="Nybergstone Strategic Partners IV, L.P."):
    return {
        "status": "NEEDS_ONBOARDING",
        "note": "No locked baseline on file for this fund — cannot verify wire instructions.",
        "extracted": {
            "entity": "Nybergstone Management, LLC", "fund_name": fund_name,
            "amount": 4_250_000, "due_date": "2026-11-14",
            "bank_name": "Kesterline National Bank", "routing_number": "021000089",
            "account_number": "5590-8842-1173",
        },
        "sender_domain": {"value": "nybergstonemgmt.com", "source": "notice_from_header"},
        "decision": "REVIEW", "fraud": True, "fraud_type": None, "fraud_labels": [],
        "failed_checks": ["baseline_resolution"], "overall_severity": "medium",
        "confidence": "n/a",
        "alert": {"subject": f"REVIEW (medium): unknown fund '{fund_name}'",
                  "body": "This capital call is for a fund with no onboarded baseline.",
                  "failed_checks": ["baseline_resolution"], "fraud_labels": [],
                  "overall_severity": "medium",
                  "recommended_action": "Route to approver for payee onboarding."},
    }


def _known_fund_output(fund_id, fund_name, decision="PASS"):
    return {
        "status": "OK", "decision": decision, "overall_severity": "none",
        "fraud": decision != "PASS", "fraud_type": None, "fraud_labels": [],
        "failed_checks": [], "confidence": "high",
        "extracted": {"fund_name": fund_name, "entity": "x", "amount": 1000,
                      "bank_name": "b", "routing_number": "011401533", "account_number": "a"},
        "fund_baseline": {"fund_id": fund_id, "fund_name": fund_name},
        "checks": {"routing_checksum": {"passed": True}},
        "alert": None,
    }


@pytest.fixture
def scratch():
    d = tempfile.mkdtemp(prefix="unknownfund_test_")
    store.reset(data_dir=d)
    A.set_notifier(None)
    yield d
    A.set_notifier(None)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def _notif_lines(scratch):
    p = os.path.join(scratch, "notifications.log")
    return [l for l in open(p).read().splitlines() if l.strip()] if os.path.exists(p) else []


def _assert_routed_to_onboarding_bucket(rec_dict):
    """The positive contract: an unresolved-fund record has the standing review
    bucket as a real, monitored owner. Shared by the positive tests and the
    negative-proof test (which asserts THIS raises when the fallback is removed)."""
    appr = rec_dict["assigned_approver"] if isinstance(rec_dict, dict) else rec_dict.assigned_approver
    assert appr is not None, "unresolved-fund record has no approver (ownerless)"
    assert appr["email"] == A.ONBOARDING_REVIEW_APPROVER["email"]
    assert appr["email"].endswith("synthetic-ops.example")


# ---- 1. visible + notified ---------------------------------------------------
def test_unknown_fund_creates_visible_notified_record(scratch):
    rec = A.ingest_pipeline_output(_needs_onboarding_output(), data_dir=scratch)

    assert rec.state == ApprovalState.PENDING_APPROVAL.value
    assert rec.hub_status == "NEEDS_ONBOARDING"          # marker distinguishing this case
    assert rec.fund_id is None                            # genuinely no fund id
    assert rec.fund_name == "Nybergstone Strategic Partners IV, L.P."
    _assert_routed_to_onboarding_bucket(rec)

    # visible in the approver queue
    pend = A.list_pending(data_dir=scratch)
    assert len(pend) == 1 and pend[0]["approval_id"] == rec.approval_id
    _assert_routed_to_onboarding_bucket(pend[0])
    assert pend[0]["verification_report"]["status"] == "NEEDS_ONBOARDING"

    # notified — did not bypass NOTIFY[NEW], and to a real address
    lines = _notif_lines(scratch)
    assert len(lines) == 1
    assert "NOTIFY[NEW]" in lines[0]
    assert A.ONBOARDING_REVIEW_APPROVER["email"] in lines[0]
    assert "UNASSIGNED APPROVER" not in lines[0] and "<?>" not in lines[0]
    assert rec.approval_id in lines[0]


# ---- 2. survives the full decide / reject / reversal cycle ------------------
def test_unknown_fund_record_survives_decide_and_reversal(scratch):
    rec = A.ingest_pipeline_output(_needs_onboarding_output(), data_dir=scratch)
    who = A.ONBOARDING_REVIEW_APPROVER["email"]

    dec = A.record_decision(rec.approval_id, "REJECTED", who,
                            "unknown payee — not onboarding on this notice", data_dir=scratch)
    assert dec["state"] == "REJECTED" and dec["decision_by"] == who
    assert A.list_pending(data_dir=scratch) == []

    # cannot double-decide, same as any record
    with pytest.raises(A.AlreadyDecidedError):
        A.record_decision(rec.approval_id, "APPROVED", who, "flip", data_dir=scratch)

    # reversal -> a NEW pending record, still routed to the bucket, still notified
    rev = A.reverse_decision(rec.approval_id, who, "GP verified out of band", data_dir=scratch)
    assert rev["approval_id"] != rec.approval_id
    assert rev["supersedes"] == rec.approval_id
    assert rev["state"] == ApprovalState.PENDING_APPROVAL.value
    _assert_routed_to_onboarding_bucket(rev)

    old = A.get_record(rec.approval_id, data_dir=scratch)
    assert old["state"] == "REJECTED" and old["superseded_by"] == [rev["approval_id"]]

    lines = _notif_lines(scratch)
    assert len(lines) == 2
    assert "NOTIFY[NEW]" in lines[0] and "NOTIFY[REVERSAL]" in lines[1]
    assert rec.approval_id in lines[1]           # reversal names what it supersedes
    assert A.ONBOARDING_REVIEW_APPROVER["email"] in lines[1]


# ---- 3. negative proof: the fallback is load-bearing -----------------------
def test_negative_proof_fallback_is_load_bearing(scratch, monkeypatch):
    """Deliberately remove the fallback and confirm the positive contract FAILS —
    proves the tests above aren't passing regardless of whether the fix exists
    (same discipline as the UI contract test's negative-proof check)."""
    monkeypatch.setattr(A, "ONBOARDING_REVIEW_APPROVER", None)

    rec = A.ingest_pipeline_output(_needs_onboarding_output(), data_dir=scratch)

    # with the fallback gone, the pre-fix bug is back: an ownerless record
    assert rec.assigned_approver is None

    # and the positive-path assertion the other tests rely on now fails
    with pytest.raises(AssertionError):
        _assert_routed_to_onboarding_bucket(rec)

    # the notification also degrades to a non-routable recipient
    lines = _notif_lines(scratch)
    assert len(lines) == 1 and ("UNASSIGNED APPROVER" in lines[0] or "<?>" in lines[0])


# ---- 4. regression: onboarded funds still resolve to their real approver ---
def test_known_funds_still_resolve_to_real_approver(scratch):
    from verification.baseline import load_baselines
    baselines = list(load_baselines().values())
    assert len(baselines) >= 2

    for b in baselines[:3]:
        rec = A.ingest_pipeline_output(
            _known_fund_output(b.fund_id, b.fund_name), data_dir=scratch)
        assert rec.assigned_approver == b.assigned_approver
        assert rec.assigned_approver["email"] != A.ONBOARDING_REVIEW_APPROVER["email"]
        assert rec.fund_id == b.fund_id
        assert rec.hub_status == "OK"
