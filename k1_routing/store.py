"""Module 5 — K-1 Routing: append-only tracking log.

One JSONL log, write-only-by-append. Event kinds per document:

  RECEIVED            — the document arrived (doc_id, raw text, text hash)
  ROUTED              — matched a fund + LP; carries the match result + extracted fields
  NEEDS_REVIEW        — could not confidently identify; carries the reason
  AWAITING_EXTRACTION — the extraction model was unreachable; carries the error.
                        The document is NOT downgraded to a lower-quality method —
                        it waits for `service.retry_pending()`.

Current state is a replay of the events (last outcome wins, so a successful retry
supersedes an earlier AWAITING_EXTRACTION). Nothing rewrites or deletes a line.
There is deliberately NO approve/reject workflow — a K-1 has no payment decision
to make, only correct identification and a record of it.

`append_event` computes `seq` and writes the line under one lock hold — the same
atomic-append the payment-approvals store uses.
"""

import json
import os
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "data")
EVENTS_LOG = os.path.join(DATA_DIR, "k1_events.jsonl")

_LOCK = threading.Lock()


def _path(data_dir=None) -> str:
    return EVENTS_LOG if data_dir is None else os.path.join(data_dir, "k1_events.jsonl")


def _read(path) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append_event(event: dict, *, data_dir=None) -> None:
    path = _path(data_dir)
    with _LOCK:
        existing = _read(path)
        event = {"seq": len(existing) + 1, "ts": _now(), **event}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(event) + "\n")


def all_events(*, data_dir=None) -> list:
    return _read(_path(data_dir))


def events_for(doc_id: str, *, data_dir=None) -> list:
    return [e for e in all_events(data_dir=data_dir) if e.get("doc_id") == doc_id]


def reset(*, data_dir=None) -> None:
    """Test-only: clear the log for a given data dir."""
    p = _path(data_dir)
    if os.path.exists(p):
        os.remove(p)
