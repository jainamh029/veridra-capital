"""Append-only stores for the payment-approvals audit trail.

Two JSONL logs, both write-only-by-append. Nothing in this module ever rewrites
or deletes a line:

  data/verification_reports.jsonl : one line per hub output, keyed by report_id.
                                    ApprovalRecords REFERENCE this, they don't copy it.
  data/approval_events.jsonl      : one line per event (CREATED / DECIDED / REVERSAL).
                                    Current state is derived by replaying events.

A decision is recorded by APPENDING a DECIDED event — the CREATED line is never
touched. A reversal is a NEW record (new approval_id) with `supersedes` pointing
at the old one; the old record's events are left exactly as written.

Concurrency: `_LOCK` serialises appends *within one process* so the monotonic
`seq` is computed and the line written atomically (no two events colliding on the
same seq). This is a SINGLE-PROCESS guarantee only — a JSONL file store has no
cross-process check-then-act protection, so running two API processes against the
same data dir can still race. `approvals.service` adds a per-record lock on top
for the decide/reverse critical section, with the same single-process caveat.
"""

import json
import os
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "data")
REPORTS_LOG = os.path.join(DATA_DIR, "verification_reports.jsonl")
EVENTS_LOG = os.path.join(DATA_DIR, "approval_events.jsonl")

_LOCK = threading.Lock()


def _paths(data_dir=None):
    if data_dir is None:
        return REPORTS_LOG, EVENTS_LOG
    return (os.path.join(data_dir, "verification_reports.jsonl"),
            os.path.join(data_dir, "approval_events.jsonl"))


def _write_line(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


def _append(path, obj):
    with _LOCK:
        _write_line(path, obj)


def _read(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


# ------------------------------------------------------------------ reports
def put_report(report_id: str, report: dict, *, data_dir=None) -> None:
    reports_log, _ = _paths(data_dir)
    _append(reports_log, {"report_id": report_id, "stored_at": _now(), "report": report})


def get_report(report_id: str, *, data_dir=None) -> dict | None:
    reports_log, _ = _paths(data_dir)
    for row in _read(reports_log):
        if row["report_id"] == report_id:
            return row["report"]
    return None


# ------------------------------------------------------------------ events
def append_event(event: dict, *, data_dir=None) -> None:
    _, events_log = _paths(data_dir)
    # seq (= count + 1) must be read and the line written under one lock hold, or
    # two concurrent appenders both compute the same seq. Single-process only.
    with _LOCK:
        existing = _read(events_log)
        event = {"seq": len(existing) + 1, "ts": _now(), **event}
        _write_line(events_log, event)


def all_events(*, data_dir=None) -> list:
    _, events_log = _paths(data_dir)
    return _read(events_log)


def events_for(approval_id: str, *, data_dir=None) -> list:
    return [e for e in all_events(data_dir=data_dir) if e.get("approval_id") == approval_id]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def reset(*, data_dir=None) -> None:
    """Test-only: clear both logs for a given data dir."""
    reports_log, events_log = _paths(data_dir)
    for p in (reports_log, events_log):
        if os.path.exists(p):
            os.remove(p)
