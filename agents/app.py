"""FastAPI surface for the platform. Working logic, not a product UI.

Run:  uvicorn agents.app:app --reload
Needs Ollama up with `capitalcall-extract`, `capitalcall-fraud`, `qwen2.5:3b-instruct`.
"""

import datetime
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .common import AS_OF, list_funds
from .forecasting import forecast
from .k1_routing import route_k1, sample_k1_documents
from .payment_approval import draft_alert
from verification.baseline import load_baselines
from verification.demo_pipeline import run_pipeline
from verification.pipeline import verify
from approvals import service as approvals
from approvals.service import AlreadyDecidedError, ApprovalError, NotFoundError
from cash_planning import core as cash_core
from cash_planning import narrative as cash_narrative
from forecasting import core as fc_core
from forecasting import narrative as fc_narrative
from k1_routing import core as k1_core
from k1_routing import service as k1_service

app = FastAPI(title="Capital Call Verification Platform (synthetic)", version="0.1.0")

# Local dev only: lets the Vite frontend (agents/../frontend, served on its own
# port) call this API from the browser. No auth on this API either way — see
# module docstrings — so this is not widening an otherwise-protected surface.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:5180", "http://127.0.0.1:5180"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_BASELINES = load_baselines()


class NoticeIn(BaseModel):
    notice_text: str
    sender_domain: str | None = None
    sender_email: str | None = None
    use_model: bool = True


class K1In(BaseModel):
    document_text: str
    with_llm: bool = True


@app.get("/health")
def health():
    return {"ok": True, "as_of": AS_OF, "funds": len(_BASELINES)}


@app.get("/funds")
def funds():
    return list_funds()


@app.get("/cash/{fund_id}")
def cash(fund_id: str):
    """DEPRECATED — replaced by /cash-planning/{fund_id}. The old path used a
    separate, non-approval-gated computation (agents/cash_planning.py, now
    removed) that could report a different 'cash position' for the same fund.
    There is one source of truth now: cash_planning/core.py."""
    raise HTTPException(410, detail={
        "error": "endpoint removed",
        "use": f"/cash-planning/{fund_id}",
        "why": "consolidated onto the approval-gated cash_planning.core (single source of truth)",
    })


@app.get("/forecast/{fund_id}")
def forecast_ep(fund_id: str, horizon_quarters: int = 4, narrative: bool = True):
    try:
        return forecast(fund_id, horizon_quarters=horizon_quarters, with_narrative=narrative)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/verify")
def verify_ep(body: NoticeIn):
    try:
        rep = verify(
            notice_text=body.notice_text, sender_domain=body.sender_domain,
            sender_email=body.sender_email, use_model=body.use_model,
            baselines=_BASELINES,
        )
        return rep.as_dict()
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/decision")
def decision_ep(body: NoticeIn):
    """THE demo entry point. Raw notice -> extraction -> rules -> model (Bug-1 derived
    verdict) -> PASS/REVIEW/BLOCK -> approver alert. Every result (PASS/REVIEW/BLOCK)
    also opens a PENDING_APPROVAL record in Module 2 — a human still has to act."""
    out = run_pipeline(
        body.notice_text, sender_domain=body.sender_domain,
        sender_email=body.sender_email, use_model=body.use_model, baselines=_BASELINES,
    )
    rec = approvals.ingest_pipeline_output(out)
    out["approval"] = {"approval_id": rec.approval_id, "state": rec.state,
                       "assigned_approver": rec.assigned_approver}
    return out


# ---------------------------------------------------------------- Module 2: approvals
class DecisionIn(BaseModel):
    state: str                     # APPROVED | REJECTED | NEEDS_MORE_INFO
    approver: str                  # who is acting
    note: str | None = None


class ReversalIn(BaseModel):
    approver: str
    note: str


_UI_FILE = os.path.join(os.path.dirname(__file__), "static", "approvals.html")


@app.get("/ui/approvals")
def ui_approvals():
    """Minimal local demo surface: pending queue + approve/reject/needs-info.
    Same-origin with the API, so no CORS. Not a production UI — no auth, no
    real notification delivery, single approver view."""
    return FileResponse(_UI_FILE, media_type="text/html")


@app.get("/approvals/pending")
def approvals_pending():
    """Every pending record with the FULL verification report + per-check breakdown."""
    return approvals.list_pending()


@app.get("/approvals")
def approvals_all():
    return approvals.list_all()


@app.get("/approvals/{approval_id}")
def approvals_get(approval_id: str):
    try:
        return approvals.get_record(approval_id)
    except NotFoundError:
        raise HTTPException(404, f"no approval record {approval_id}")


@app.post("/approvals/{approval_id}/decide")
def approvals_decide(approval_id: str, body: DecisionIn):
    try:
        return approvals.record_decision(approval_id, body.state, body.approver, body.note)
    except NotFoundError:
        raise HTTPException(404, f"no approval record {approval_id}")
    except AlreadyDecidedError as e:
        raise HTTPException(409, str(e))
    except ApprovalError as e:
        raise HTTPException(422, str(e))


@app.post("/approvals/{approval_id}/reverse")
def approvals_reverse(approval_id: str, body: ReversalIn):
    """A recorded decision is immutable. This opens a NEW pending record that
    references the old one — it does not edit the old decision."""
    try:
        return approvals.reverse_decision(approval_id, body.approver, body.note)
    except NotFoundError:
        raise HTTPException(404, f"no approval record {approval_id}")
    except ApprovalError as e:
        raise HTTPException(422, str(e))


# ---------------------------------------------------------------- Module 3: cash planning
# Thin HTTP wrappers over cash_planning.core.cash_position(). NO math here — every
# number comes straight from core.py (reconciled + tested in tests/test_cash_planning.py).
_CASH_UI_FILE = os.path.join(os.path.dirname(__file__), "static", "cash-planning.html")


@app.get("/ui/cash-planning")
def ui_cash_planning():
    """Local demo surface for Module 3, same style as /ui/approvals. No auth."""
    return FileResponse(_CASH_UI_FILE, media_type="text/html")


def _date_or_422(s: str | None, name: str) -> str | None:
    """Validate a YYYY-MM-DD query param before it reaches core (which passes
    as_of straight into a SQL `date <= ?` and would otherwise treat garbage as
    'after everything')."""
    if s is None:
        return None
    try:
        datetime.date.fromisoformat(s)
    except ValueError:
        raise HTTPException(422, f"{name} must be YYYY-MM-DD, got {s!r}")
    return s


def _cash_for(fund_id: str, *, want_narrative: bool,
              as_of: str | None, reference_date: str | None) -> dict:
    # pure plumbing: as_of / reference_date are passed straight to core, which
    # already filters the ledger by date (WHERE date <= as_of) — see
    # cash_planning.core.historical_gl_lines / ledger_running_balance.
    pos = cash_core.cash_position(fund_id, as_of=as_of, reference_date=reference_date)
    if want_narrative:
        # narrative.describe never raises: Ollama down -> generated=False + reason
        pos["narrative"] = cash_narrative.describe(pos)
    return pos


@app.get("/cash-planning")
def cash_planning_all(narrative: bool = False, as_of: str | None = None,
                      reference_date: str | None = None):
    """Every fund's cash_position(), for the overview list. `as_of` sets the ledger
    cutoff (default: latest ledger date); `reference_date` anchors the near-term
    window (default: today). Both dates as YYYY-MM-DD."""
    as_of = _date_or_422(as_of, "as_of")
    reference_date = _date_or_422(reference_date, "reference_date")
    return [_cash_for(fid, want_narrative=narrative, as_of=as_of,
                      reference_date=reference_date)
            for fid in cash_core.list_fund_ids()]


@app.get("/cash-planning/{fund_id}")
def cash_planning_one(fund_id: str, narrative: bool = False, as_of: str | None = None,
                      reference_date: str | None = None):
    if fund_id not in cash_core.list_fund_ids():
        raise HTTPException(404, f"unknown fund_id {fund_id!r}")
    as_of = _date_or_422(as_of, "as_of")
    reference_date = _date_or_422(reference_date, "reference_date")
    return _cash_for(fund_id, want_narrative=narrative, as_of=as_of,
                     reference_date=reference_date)


# ---------------------------------------------------------------- Module 4: forecasting
# Thin wrappers over forecasting.core.project_next_call() (pure, deterministic,
# NO model). The endpoint also attaches a read-only `context` slice from cash
# planning so the UI can show all three tiers from one fetch — the projection
# itself is computed only in forecasting.core.
_FORECAST_UI_FILE = os.path.join(os.path.dirname(__file__), "static", "forecasting.html")


@app.get("/ui/forecasting")
def ui_forecasting():
    """Local demo surface for Module 4, same style as the other two pages. No auth."""
    return FileResponse(_FORECAST_UI_FILE, media_type="text/html")


def _forecast_for(fund_id: str, *, want_narrative: bool, as_of: str | None) -> dict:
    vantage = as_of or cash_core.latest_ledger_date()
    hist = fc_core.approved_call_history(fund_id, as_of=as_of)
    proj = fc_core.project_next_call(hist, as_of=vantage)     # pure, deterministic
    proj["fund_id"] = fund_id
    proj["fund_name"] = cash_core.fund_name(fund_id)

    cp = cash_core.cash_position(fund_id, as_of=as_of)        # read-only
    proj["context"] = {
        "confirmed_cash_balance": cp["confirmed_cash_balance"],
        "near_term_obligations_total": cp["near_term_obligations"]["total_not_yet_realized"],
        "near_term_obligations_count": cp["near_term_obligations"]["count"],
        "as_of_ledger": cp["as_of_ledger"],
        "note": "tier 1 & 2 from cash planning; shown here only so the UI reads as one product",
    }
    if want_narrative:
        proj["narrative"] = fc_narrative.describe(proj)
    return proj


@app.get("/forecasting")
def forecasting_all(narrative: bool = False, as_of: str | None = None):
    """Every fund's next-expected-call projection, for the overview list.
    `as_of` (YYYY-MM-DD) sets the vantage date; default = latest ledger date."""
    as_of = _date_or_422(as_of, "as_of")
    return [_forecast_for(fid, want_narrative=narrative, as_of=as_of)
            for fid in cash_core.list_fund_ids()]


@app.get("/forecasting/{fund_id}")
def forecasting_one(fund_id: str, narrative: bool = False, as_of: str | None = None):
    if fund_id not in cash_core.list_fund_ids():
        raise HTTPException(404, f"unknown fund_id {fund_id!r}")
    as_of = _date_or_422(as_of, "as_of")
    return _forecast_for(fund_id, want_narrative=narrative, as_of=as_of)


# ---------------------------------------------------------------- Module 5: K-1 routing
# Identify which fund + LP a Schedule K-1 belongs to and route it. Extraction uses
# the general-purpose model (NOT the fraud model). If the model is unreachable the
# document lands in AWAITING_EXTRACTION and is retried via /k1-routing/retry-pending
# — it is never silently downgraded to a lower-quality method. Matching is
# deterministic code reusing the hub's fuzzy approach; can't identify -> NEEDS_REVIEW.
_K1_UI_FILE = os.path.join(os.path.dirname(__file__), "static", "k1-routing.html")


class K1DocIn(BaseModel):
    document_text: str


@app.get("/ui/k1-routing")
def ui_k1_routing():
    return FileResponse(_K1_UI_FILE, media_type="text/html")


@app.post("/k1-routing/ingest")
def k1_ingest(body: K1DocIn):
    """Ingest one K-1: model extraction -> deterministic match -> tracking record.
    If the model is down the record lands in AWAITING_EXTRACTION (request still 200)."""
    return k1_service.ingest_document(body.document_text)


@app.post("/k1-routing/retry-pending")
def k1_retry_pending():
    """Re-attempt extraction for every AWAITING_EXTRACTION record. Trigger this
    manually or on a simple periodic check once the model is back."""
    return k1_service.retry_pending()


@app.get("/k1-routing")
def k1_routing_all():
    """Every tracked K-1 document (overview)."""
    recs = k1_service.list_records()
    return {
        "documents": recs,
        "summary": {
            "total": len(recs),
            "routed": sum(1 for r in recs if r["status"] == "ROUTED"),
            "needs_review": sum(1 for r in recs if r["status"] == "NEEDS_REVIEW"),
            "awaiting_extraction": sum(1 for r in recs if r["status"] == "AWAITING_EXTRACTION"),
        },
    }


@app.get("/k1-routing/{fund_id}")
def k1_routing_one(fund_id: str):
    if fund_id not in cash_core.list_fund_ids():
        raise HTTPException(404, f"unknown fund_id {fund_id!r}")
    recs = k1_service.list_for_fund(fund_id)
    return {"fund_id": fund_id, "fund_name": cash_core.fund_name(fund_id),
            "documents": recs, "count": len(recs)}


@app.post("/pipeline")
def pipeline_ep(body: NoticeIn):
    """Legacy Phase-6 shape (verification report + LLM-narrative alert). Prefer /decision."""
    try:
        rep = verify(
            notice_text=body.notice_text, sender_domain=body.sender_domain,
            sender_email=body.sender_email, use_model=body.use_model,
            baselines=_BASELINES,
        ).as_dict()
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"verification": rep, "approver_alert": draft_alert(rep)}


@app.post("/k1/route")
def k1_ep(body: K1In):
    return route_k1(body.document_text, with_llm=body.with_llm)


@app.get("/k1/samples")
def k1_samples():
    return sample_k1_documents()
