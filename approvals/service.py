"""Module 2 — Payment Approvals: service layer.

ingest_pipeline_output()  -- hub output -> stored report + PENDING_APPROVAL record
list_pending()            -- approver queue, each with the FULL verification report
get_record()              -- one record + full report + full check breakdown
record_decision()         -- append a DECIDED event; refuses if already decided
reverse_decision()        -- new record referencing the old one (no overwrite)

HARD BOUNDARY: nothing in this module executes a payment. APPROVED just records
that a human signed off. There is deliberately no send / wire / execute function.

CONCURRENCY (single-process only): record_decision / reverse_decision do a
check-then-append (read current state, then write an event). Without atomicity
there, two simultaneous decides on the same record both see PENDING and both
append a DECIDED event. A per-record lock (`_record_lock`) makes that section
atomic *within one process*. It does NOT protect against two API processes
sharing one data dir — a JSONL file store has no cross-process compare-and-set.
Different records take different locks, so unrelated decisions still run in
parallel.
"""

import os
import threading
import uuid

from verification.baseline import load_baselines, resolve_by_fund_name

from . import store
from .model import DECIDABLE, ApprovalRecord, ApprovalState
from .notify import LoggedNotificationSender, NotificationSender


class ApprovalError(Exception):
    """Base for approval-flow violations (maps to HTTP 409 in the API)."""


class AlreadyDecidedError(ApprovalError):
    pass


class NotFoundError(ApprovalError):
    pass


_BASELINES = None

# --------------------------------------------------------------- per-record locking
# One lock per approval_id, created on demand. Guards the check-then-append in
# record_decision / reverse_decision. Different records -> different locks -> no
# serialisation between unrelated decisions. Single-process only (see module doc).
_RECORD_LOCKS: dict[str, threading.Lock] = {}
_RECORD_LOCKS_GUARD = threading.Lock()


def _record_lock(approval_id: str) -> threading.Lock:
    with _RECORD_LOCKS_GUARD:
        lk = _RECORD_LOCKS.get(approval_id)
        if lk is None:
            lk = _RECORD_LOCKS[approval_id] = threading.Lock()
        return lk


# --------------------------------------------------------------- unresolved-fund routing
# A capital call can arrive for a fund that was never onboarded (no baseline on
# file). The hub already flags this correctly (status="NEEDS_ONBOARDING"), but the
# fund -> approver mapping only covers registered funds, so such a notice would
# otherwise land with assigned_approver=None — an ownerless record routed to
# nobody, for what is arguably the HIGHER-attention case (an entirely unknown
# payee). Instead it routes here: a standing operator bucket a human monitors for
# exactly this. This is a catch-all for ANY unrecognized fund, not a per-fund entry.
ONBOARDING_REVIEW_APPROVER = {
    "name": "Onboarding Review Queue",
    "email": "onboarding-review@synthetic-ops.example",
    "role": "Payee onboarding / unrecognized-fund review",
}

# --------------------------------------------------------------- notifications
# Pluggable. `set_notifier(real_provider)` swaps in email/Slack later with no
# other change here; None falls back to the default logged (mock) sender.
_notifier: NotificationSender | None = None
_DEFAULT_SENDER: LoggedNotificationSender | None = None


def set_notifier(sender: NotificationSender | None) -> None:
    global _notifier
    _notifier = sender


def get_notifier() -> NotificationSender | None:
    return _notifier


def _notify_new_record(rec: ApprovalRecord, *, data_dir=None) -> None:
    """Called once per new PENDING_APPROVAL record from ingest_pipeline_output."""
    global _DEFAULT_SENDER
    sender = _notifier
    if sender is None:
        if data_dir:  # test / scratch run — keep the log beside its data dir, quiet
            sender = LoggedNotificationSender(
                log_path=os.path.join(data_dir, "notifications.log"), echo=False)
        else:
            if _DEFAULT_SENDER is None:
                _DEFAULT_SENDER = LoggedNotificationSender()
            sender = _DEFAULT_SENDER
    sender.notify(rec)


def _baselines():
    global _BASELINES
    if _BASELINES is None:
        _BASELINES = load_baselines()
    return _BASELINES


def _resolve_approver(pipeline_output: dict):
    """fund -> (approver, fund_id, fund_name), from the same onboarding config the
    hub uses. If the fund is not onboarded (no baseline), route to the standing
    ONBOARDING_REVIEW_APPROVER bucket rather than returning a null approver — the
    record must still have a real, monitored owner."""
    fb = pipeline_output.get("fund_baseline") or {}
    fund_id = fb.get("fund_id")
    baselines = _baselines()
    b = baselines.get(fund_id) if fund_id else None
    if b is None:
        b = resolve_by_fund_name(
            (pipeline_output.get("extracted") or {}).get("fund_name", ""), baselines)
    if b is not None:
        return b.assigned_approver, b.fund_id, b.fund_name
    # unresolved fund — explicit fallback, decided in code (not the model)
    fund_name = fb.get("fund_name") or (pipeline_output.get("extracted") or {}).get("fund_name")
    return ONBOARDING_REVIEW_APPROVER, fund_id, fund_name


# --------------------------------------------------------------- ingest
def ingest_pipeline_output(pipeline_output: dict, *, data_dir=None) -> ApprovalRecord:
    """Called AFTER the hub (run_pipeline / POST /decision). Creates exactly one
    PENDING_APPROVAL record for this notice — PASS, REVIEW and BLOCK alike."""
    report_id = "vr_" + uuid.uuid4().hex[:12]
    store.put_report(report_id, pipeline_output, data_dir=data_dir)

    approver, fund_id, fund_name = _resolve_approver(pipeline_output)
    rec = ApprovalRecord(
        approval_id="ap_" + uuid.uuid4().hex[:12],
        verification_report_id=report_id,
        fund_id=fund_id,
        fund_name=fund_name or (pipeline_output.get("extracted") or {}).get("fund_name"),
        assigned_approver=approver,
        created_at=store._now(),
        hub_status=pipeline_output.get("status", "OK"),
        hub_decision=pipeline_output.get("decision"),
        hub_severity=pipeline_output.get("overall_severity"),
        state=ApprovalState.PENDING_APPROVAL.value,
    )
    store.append_event({"event": "CREATED", "approval_id": rec.approval_id,
                        "record": rec.as_dict()}, data_dir=data_dir)
    _notify_new_record(rec, data_dir=data_dir)  # exactly one notification per new record
    return rec


# --------------------------------------------------------------- read
def _replay(approval_id: str, *, data_dir=None) -> ApprovalRecord | None:
    events = store.events_for(approval_id, data_dir=data_dir)
    if not events:
        return None
    created = next((e for e in events if e["event"] == "CREATED"), None)
    if not created:
        return None
    rec = ApprovalRecord(**created["record"])
    decided = next((e for e in events if e["event"] == "DECIDED"), None)
    if decided:
        rec = ApprovalRecord(**{**rec.as_dict(),
                                "state": decided["state"],
                                "decision_by": decided["decision_by"],
                                "decision_at": decided["decision_at"],
                                "decision_note": decided.get("decision_note")})
    return rec


def _all_ids(*, data_dir=None) -> list:
    return [e["approval_id"] for e in store.all_events(data_dir=data_dir)
            if e["event"] == "CREATED"]


def get_record(approval_id: str, *, include_report=True, data_dir=None) -> dict:
    rec = _replay(approval_id, data_dir=data_dir)
    if rec is None:
        raise NotFoundError(approval_id)
    out = rec.as_dict()
    if include_report:
        out["verification_report"] = store.get_report(rec.verification_report_id,
                                                      data_dir=data_dir)
    # link any reversal chain
    reversed_by = [e["approval_id"] for e in store.all_events(data_dir=data_dir)
                   if e["event"] == "CREATED" and e["record"].get("supersedes") == approval_id]
    out["superseded_by"] = reversed_by or None
    return out


def list_pending(*, data_dir=None) -> list:
    """Approver queue. Each item carries the FULL verification report so the
    approver sees the whole picture, not a one-line status."""
    out = []
    for aid in _all_ids(data_dir=data_dir):
        rec = _replay(aid, data_dir=data_dir)
        if rec and rec.state == ApprovalState.PENDING_APPROVAL.value:
            out.append(get_record(aid, data_dir=data_dir))
    out.sort(key=lambda r: r["created_at"])
    return out


def list_all(*, data_dir=None) -> list:
    return [get_record(aid, include_report=False, data_dir=data_dir)
            for aid in _all_ids(data_dir=data_dir)]


# --------------------------------------------------------------- decide
def record_decision(approval_id: str, new_state: str, approver: str,
                    note: str | None = None, *, data_dir=None) -> dict:
    try:
        st = ApprovalState(new_state)
    except ValueError:
        raise ApprovalError(f"invalid decision state {new_state!r}; "
                            f"must be one of {[s.value for s in DECIDABLE]}")
    if st not in DECIDABLE:
        raise ApprovalError(f"{new_state!r} is not a decision state")

    # check-then-append must be atomic per record: without this, two simultaneous
    # decides both see PENDING and both append a DECIDED event (observed: 40/40).
    with _record_lock(approval_id):
        rec = _replay(approval_id, data_dir=data_dir)
        if rec is None:
            raise NotFoundError(approval_id)
        if rec.state != ApprovalState.PENDING_APPROVAL.value:
            # immutability: a decision, once recorded, is never edited or overwritten
            raise AlreadyDecidedError(
                f"{approval_id} is already {rec.state} (decided by {rec.decision_by} "
                f"at {rec.decision_at}). To change it, create a reversal record.")

        store.append_event({
            "event": "DECIDED", "approval_id": approval_id, "state": st.value,
            "decision_by": approver, "decision_at": store._now(),
            "decision_note": note,
        }, data_dir=data_dir)
        return get_record(approval_id, data_dir=data_dir)


def reverse_decision(old_approval_id: str, approver: str, note: str,
                     *, data_dir=None) -> dict:
    """A decision cannot be edited. Reversing = a NEW PENDING record that
    references the old one; the old record's audit trail is untouched."""
    # same check-then-append shape as record_decision: lock on the OLD id so two
    # concurrent reversals of one decided record can't both spawn a supersede.
    with _record_lock(old_approval_id):
        old = _replay(old_approval_id, data_dir=data_dir)
        if old is None:
            raise NotFoundError(old_approval_id)
        if old.state == ApprovalState.PENDING_APPROVAL.value:
            raise ApprovalError(f"{old_approval_id} has no decision to reverse")

        new = ApprovalRecord(**{**old.as_dict(),
                                "approval_id": "ap_" + uuid.uuid4().hex[:12],
                                "created_at": store._now(),
                                "state": ApprovalState.PENDING_APPROVAL.value,
                                "decision_by": None, "decision_at": None,
                                "decision_note": None,
                                "supersedes": old_approval_id})
        store.append_event({"event": "REVERSAL", "approval_id": new.approval_id,
                            "supersedes": old_approval_id, "reversal_note": note,
                            "requested_by": approver, "record": new.as_dict()},
                           data_dir=data_dir)
        # a REVERSAL event doubles as this record's CREATED, so replay handles it:
        store.append_event({"event": "CREATED", "approval_id": new.approval_id,
                            "record": new.as_dict()}, data_dir=data_dir)
        # a reversed record is a fresh thing needing a human decision — notify the
        # approver, same path as a brand-new notice (format tags it REVERSAL and
        # names the record it supersedes).
        _notify_new_record(new, data_dir=data_dir)
        return get_record(new.approval_id, data_dir=data_dir)
