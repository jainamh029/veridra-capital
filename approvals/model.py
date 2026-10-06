"""Module 2 — Payment Approvals: data model.

Turns a verification verdict into a TRACKED HUMAN DECISION. This module never
executes a payment — there is no code path here that sends money, and there must
never be one. "APPROVED" here means a human approver signed off; the actual wire
is out of scope for this project entirely.

Every notice that clears the hub (PASS, REVIEW, or BLOCK alike) gets exactly one
PENDING_APPROVAL record and must be explicitly acted on by its approver.
"""

from dataclasses import dataclass, field
from enum import Enum


class ApprovalState(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"   # initial — awaiting the approver
    APPROVED = "APPROVED"                   # human signed off (does NOT trigger a payment)
    REJECTED = "REJECTED"                   # human refused — terminal, no payment possible
    NEEDS_MORE_INFO = "NEEDS_MORE_INFO"     # human wants clarification — terminal for this record


DECIDABLE = {ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.NEEDS_MORE_INFO}


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    verification_report_id: str            # REFERENCE to the stored hub output (not a copy)
    fund_id: str | None
    fund_name: str | None
    assigned_approver: dict | None         # {"name","email","role"} from onboarding config
    created_at: str

    # denormalised-for-display scalars only (like fund_id) — the full report lives
    # behind verification_report_id
    hub_status: str = "OK"                 # OK | NEEDS_ONBOARDING
    hub_decision: str | None = None        # PASS | REVIEW | BLOCK
    hub_severity: str | None = None        # none | medium-low | medium | high

    state: str = ApprovalState.PENDING_APPROVAL.value
    decision_by: str | None = None
    decision_at: str | None = None
    decision_note: str | None = None

    supersedes: str | None = None          # set only when this record reverses an earlier one

    def as_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "verification_report_id": self.verification_report_id,
            "fund_id": self.fund_id,
            "fund_name": self.fund_name,
            "assigned_approver": self.assigned_approver,
            "created_at": self.created_at,
            "hub_status": self.hub_status,
            "hub_decision": self.hub_decision,
            "hub_severity": self.hub_severity,
            "state": self.state,
            "decision_by": self.decision_by,
            "decision_at": self.decision_at,
            "decision_note": self.decision_note,
            "supersedes": self.supersedes,
        }
