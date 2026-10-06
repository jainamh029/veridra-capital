"""Module 5 — K-1 Routing: service layer.

ingest_document()   -- raw K-1 text -> model extraction -> deterministic match -> record
retry_pending()     -- re-attempt extraction for every AWAITING_EXTRACTION record
get_record()        -- one document's current state (replayed from events)
list_records()      -- all documents
list_for_fund()     -- documents routed to one fund

States: RECEIVED -> (ROUTED | NEEDS_REVIEW | AWAITING_EXTRACTION).
AWAITING_EXTRACTION means the model was unreachable at the time — the document is
NOT downgraded to a lower-quality extraction; it waits for a retry. There is no
approve/reject workflow — identification and routing only.

Concurrency: the check-then-append in `_attempt_extraction` (has this doc already
been resolved?) is guarded per-doc by `_doc_lock`, the same approach payment
approvals uses, so two simultaneous retries / re-ingests of one doc can't both
append an outcome. Single-process only (a JSONL store has no cross-process CAS).
"""

from __future__ import annotations

import hashlib
import threading
import uuid

from . import core, store

_OUTCOME_EVENTS = ("ROUTED", "NEEDS_REVIEW", "AWAITING_EXTRACTION")
_RESOLVED = ("ROUTED", "NEEDS_REVIEW")

# --- per-document lock (same pattern as approvals.service._record_lock) ---------
_DOC_LOCKS: dict[str, threading.Lock] = {}
_DOC_LOCKS_GUARD = threading.Lock()


def _doc_lock(doc_id: str) -> threading.Lock:
    with _DOC_LOCKS_GUARD:
        lk = _DOC_LOCKS.get(doc_id)
        if lk is None:
            lk = _DOC_LOCKS[doc_id] = threading.Lock()
        return lk


# --------------------------------------------------------------- replay
def _record_from_events(events: list) -> dict | None:
    recv = next((e for e in events if e["event"] == "RECEIVED"), None)
    if not recv:
        return None
    outcomes = [e for e in events if e["event"] in _OUTCOME_EVENTS]
    last = outcomes[-1] if outcomes else None
    rec = {
        "doc_id": recv["doc_id"],
        "case": recv.get("case"),
        "received_at": recv["ts"],
        "text_sha256": recv["text_sha256"],
        "status": "RECEIVED",
        "extracted": None,
        "routed_at": None,
        "matched_fund": None,
        "matched_lp": None,
        "routed_to": None,
        "review_reason": None,
        "review_detail": None,
        "extraction_error": None,
        "retry_count": max(0, len(outcomes) - 1),
    }
    if last:
        rec["status"] = last["event"]
        rec["routed_at"] = last["ts"] if last["event"] in _RESOLVED else None
        rec["extracted"] = last.get("extracted")        # None for AWAITING_EXTRACTION
        for k in ("matched_fund", "matched_lp", "routed_to", "review_reason",
                  "review_detail", "extraction_error"):
            if k in last:
                rec[k] = last[k]
    return rec


# --------------------------------------------------------------- extraction attempt
def _attempt_extraction(doc_id: str, text: str, *, extractor, data_dir) -> dict:
    """Try to extract + match one document and append its outcome event. If the
    model is unavailable, append AWAITING_EXTRACTION and store NOTHING regex-based.
    Guarded per-doc so concurrent attempts can't both append an outcome."""
    with _doc_lock(doc_id):
        current = get_record(doc_id, data_dir=data_dir)
        if current and current["status"] in _RESOLVED:
            return current                              # already done — idempotent

        try:
            extracted = core.extract_k1(text, extractor=extractor)
        except core.ExtractionUnavailable as e:
            store.append_event({"event": "AWAITING_EXTRACTION", "doc_id": doc_id,
                                "extraction_error": str(e)[:300]}, data_dir=data_dir)
            return get_record(doc_id, data_dir=data_dir)

        routing = core.route_extracted(extracted)
        outcome = {"event": routing["status"], "doc_id": doc_id, "extracted": extracted}
        for k in ("matched_fund", "matched_lp", "routed_to", "review_reason", "review_detail"):
            if k in routing:
                outcome[k] = routing[k]
        store.append_event(outcome, data_dir=data_dir)
        return get_record(doc_id, data_dir=data_dir)


# --------------------------------------------------------------- public
def ingest_document(text: str, *, doc_id: str | None = None, case: str | None = None,
                    extractor=None, data_dir=None) -> dict:
    """Entry point. Writes RECEIVED (with the raw text, for retry) then attempts
    extraction. On model failure the record lands in AWAITING_EXTRACTION — the
    request still succeeds; nothing is silently downgraded."""
    doc_id = doc_id or "k1_" + uuid.uuid4().hex[:12]
    with _doc_lock(doc_id):
        if not any(e["event"] == "RECEIVED"
                   for e in store.events_for(doc_id, data_dir=data_dir)):
            store.append_event({
                "event": "RECEIVED", "doc_id": doc_id, "case": case,
                "text": text,
                "text_sha256": hashlib.sha256((text or "").encode()).hexdigest(),
            }, data_dir=data_dir)
    return _attempt_extraction(doc_id, text, extractor=extractor, data_dir=data_dir)


def retry_pending(*, extractor=None, data_dir=None) -> dict:
    """Re-attempt extraction for every AWAITING_EXTRACTION record. Manual/periodic
    trigger — not a background job. Returns a small summary."""
    pending = [r for r in list_records(data_dir=data_dir)
               if r["status"] == "AWAITING_EXTRACTION"]
    resolved, still = 0, 0
    records = []
    for r in pending:
        recv = next(e for e in store.events_for(r["doc_id"], data_dir=data_dir)
                    if e["event"] == "RECEIVED")
        rec = _attempt_extraction(r["doc_id"], recv.get("text", ""),
                                  extractor=extractor, data_dir=data_dir)
        records.append(rec)
        if rec["status"] in _RESOLVED:
            resolved += 1
        else:
            still += 1
    return {"attempted": len(pending), "resolved": resolved,
            "still_awaiting": still, "records": records}


def get_record(doc_id: str, *, data_dir=None) -> dict | None:
    return _record_from_events(store.events_for(doc_id, data_dir=data_dir))


def list_records(*, data_dir=None) -> list:
    ids, seen = [], set()
    for e in store.all_events(data_dir=data_dir):
        if e["event"] == "RECEIVED" and e["doc_id"] not in seen:
            seen.add(e["doc_id"])
            ids.append(e["doc_id"])
    out = [get_record(i, data_dir=data_dir) for i in ids]
    return sorted([r for r in out if r], key=lambda r: r["received_at"])


def list_for_fund(fund_id: str, *, data_dir=None) -> list:
    return [r for r in list_records(data_dir=data_dir)
            if (r.get("matched_fund") or {}).get("fund_id") == fund_id]
