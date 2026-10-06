"""Module 2 — Payment Approvals: notification hook.

When a new PENDING_APPROVAL record is created — either by `ingest_pipeline_output`
(a fresh notice) or by `reverse_decision` (a decided record sent back for another
look) — the fund's assigned approver needs to be told "there's a capital call
waiting for your decision." This module is the seam for that.

DELIBERATELY MOCKED — read this before adding a real provider.

There is no real approver and no real fund on this platform yet: every fund,
approver and wire instruction is synthetic. Wiring a real email / Slack provider
now would be infrastructure with nothing on the other end to receive it. So:

  * `NotificationSender`        — the interface (one method, `notify`).
  * `LoggedNotificationSender`  — the ONLY implementation for now. Writes one
                                  human-readable line per record to a log file
                                  (and optionally echoes to stderr). No network.

A real provider plugs in later as a *second* `NotificationSender` and is handed
to `approvals.service.set_notifier(...)` — nothing else in the module changes.
That step is intentionally deferred until there is a real fund/approver to notify.
"""

from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod

from .model import ApprovalRecord

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG = os.path.join(_HERE, "notifications.log")


def format_notification(rec: ApprovalRecord) -> str:
    """The single line a sender emits for one new pending record.

    Carries an event tag (NEW vs REVERSAL), approver, fund, verdict, severity and
    the created-at timestamp. A reversal record also names the record it
    supersedes, so a reversal notification is never an indistinguishable
    duplicate of the original create-time line."""
    approver = rec.assigned_approver or {}
    who = approver.get("name") or approver.get("email") or "UNASSIGNED APPROVER"
    email = approver.get("email") or "?"
    event = "REVERSAL" if rec.supersedes else "NEW"
    ref = f"approval {rec.approval_id}, report {rec.verification_report_id}"
    if rec.supersedes:
        ref += f", supersedes {rec.supersedes}"
    return (
        f"[{rec.created_at}] NOTIFY[{event}] {who} <{email}> — "
        f"capital call for {rec.fund_name or rec.fund_id or 'unknown fund'} "
        f"needs your decision: verdict={rec.hub_decision or '?'}, "
        f"severity={rec.hub_severity or 'none'} ({ref})"
    )


class NotificationSender(ABC):
    """Hand it a freshly-created ApprovalRecord; it tells the approver.

    Contract: `ingest_pipeline_output` and `reverse_decision` each call `notify`
    exactly once per new PENDING_APPROVAL record they create. Implementations
    must not send more than once for that call and must not raise on a normal
    record (a real provider should swallow/log transport errors rather than
    break ingestion)."""

    @abstractmethod
    def notify(self, approval_record: ApprovalRecord) -> None:  # pragma: no cover
        ...


class LoggedNotificationSender(NotificationSender):
    """The only implementation right now: append one line per record to a log
    file and (by default) echo it to stderr. No network, no real delivery —
    just a provable, testable trigger path."""

    def __init__(self, log_path: str | None = None, echo: bool = True):
        self.log_path = log_path or DEFAULT_LOG
        self.echo = echo
        self.sent: list[str] = []  # in-memory copy of every line, handy for tests

    def notify(self, approval_record: ApprovalRecord) -> None:
        line = format_notification(approval_record)
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "a") as f:
            f.write(line + "\n")
        self.sent.append(line)
        if self.echo:
            print(line, file=sys.stderr, flush=True)
