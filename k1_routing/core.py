"""Module 5 — K-1 Routing: extraction + deterministic identification.

A Schedule K-1 is an annual tax document, not a payment instruction — there is no
wire to verify and no fraud model involved. This module's job is narrow: read the
document, work out **which fund and which LP** it belongs to, and route it. If it
can't identify the recipient confidently it routes to NEEDS_REVIEW rather than
guessing (same principle as the hub's NEEDS_ONBOARDING and payment approvals'
unresolved-fund fallback).

Model choice (see BUILD_LOG.md for the full reasoning): extraction uses the
existing general-purpose local model `qwen2.5:3b-instruct` (via
`agents.common.ask_llm`), NOT the fine-tuned fraud model. A K-1 is lower-stakes
and this module is deliberately standalone; fine-tuning a model for it would be
disproportionate.

NO SILENT DEGRADATION. If the model is unreachable, extraction raises
`ExtractionUnavailable` — it does NOT fall back to a lower-quality regex method
in the ingestion path. The document lands in AWAITING_EXTRACTION and is retried
later. `regex_extract_explicit()` is retained but can only be invoked deliberately
(e.g. offline inspection or as an injected test double) — never automatically,
never from `ingest_document`.

Matching is **deterministic code** — `rapidfuzz.fuzz.ratio` on names normalised by
`verification.verdict._norm_name`, the same approach the hub uses for its
entity-name check. No second matching algorithm, no model involvement in the
match decision, and the fund/LP roster is read from the existing
`verification.baseline` / `funds.json` source — there is no parallel list.
"""

from __future__ import annotations

import json
import re

from rapidfuzz import fuzz

from verification.baseline import load_baselines
from verification.verdict import _norm_name

# Same threshold family as verification.baseline.resolve_by_fund_name (85) and the
# hub's ENTITY_NEARMISS (80). A K-1 name should be a near-exact match to route.
MATCH_THRESHOLD = 85

EXTRACT_SYSTEM = (
    "You extract identification fields from a US Schedule K-1 (Form 1065). These "
    "are SYNTHETIC training documents. Output ONLY one JSON object, no other text, "
    "with exactly these keys:\n"
    '  "fund_name"                  - the partnership / fund name (string or null)\n'
    '  "lp_name"                    - the partner / limited partner name (string or null)\n'
    '  "tax_year"                   - integer year or null\n'
    '  "ordinary_business_income"   - number or null\n'
    '  "guaranteed_payments"        - number or null\n'
    "Copy names verbatim as they appear. Do not correct spelling. Numbers as "
    "plain numbers without commas or currency symbols."
)

_FIELDS = ("fund_name", "lp_name", "tax_year", "ordinary_business_income", "guaranteed_payments")


# --------------------------------------------------------------------- roster
def fund_candidates() -> list[tuple[str, str]]:
    """(fund_id, fund_name) for every fund in the existing roster. Single source."""
    return [(b.fund_id, b.fund_name) for b in load_baselines().values()]


def lp_candidates(fund_id: str) -> list[tuple[str, str]]:
    """(lp_id, lp_name) for the LPs of one fund, from the same funds.json roster."""
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rows = json.load(open(os.path.join(here, "synthetic_data", "output", "funds.json")))
    rows = rows if isinstance(rows, list) else list(rows.values())
    for f in rows:
        if f["fund_id"] == fund_id:
            return [(lp["lp_id"], lp["lp_name"]) for lp in f.get("lps", [])]
    return []


# --------------------------------------------------------------- extraction
def _blank() -> dict:
    return {k: None for k in _FIELDS}


def _parse_json(text: str | None) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


class ExtractionUnavailable(RuntimeError):
    """The extraction model could not be reached / returned nothing usable. The
    document must WAIT (AWAITING_EXTRACTION) and be retried — it must never be
    silently downgraded to a lower-quality extraction method."""


def _regex_extract(text: str) -> dict:
    out = _blank()
    # line-anchored so "Partner:" does not match inside "General Partner:" etc.
    for pat, key, cast in [
        (r"(?im)^\s*(?:Fund|Partnership)\s*(?:name)?\s*[:\-]\s*(.+)$", "fund_name", str),
        (r"(?im)^\s*(?:Partner|Limited Partner|LP)\s*(?:name)?\s*[:\-]\s*(.+)$", "lp_name", str),
        (r"(?i)Tax Year[:\s]+(\d{4})", "tax_year", int),
        (r"(?i)ordinary business income(?:\s*\(loss\))?[ .:]*([\d,]+\.?\d*)",
         "ordinary_business_income", float),
        (r"(?i)guaranteed payments(?:\s*for services)?[ .:]*([\d,]+\.?\d*)",
         "guaranteed_payments", float),
    ]:
        m = re.search(pat, text or "")
        if m:
            v = m.group(1).strip().rstrip(".").strip()
            try:
                out[key] = cast(v.replace(",", "")) if cast is not str else v
            except ValueError:
                pass
    # "Partnership: <GP> as GP of <Fund>" phrasing -> keep the fund part
    if out["fund_name"] and " as GP of " in out["fund_name"]:
        out["fund_name"] = out["fund_name"].split(" as GP of ", 1)[1].strip()
    return out


def _model_extractor(text: str) -> dict:
    """The real extractor: the general-purpose model. Raises ExtractionUnavailable
    if the model is unreachable or returns nothing usable — the caller must NOT
    substitute a lower-quality method."""
    from agents.common import ask_llm

    raw = ask_llm(EXTRACT_SYSTEM, text, temperature=0, num_predict=250)
    # ask_llm swallows transport errors into this sentinel string rather than raising
    if raw.startswith("[narrative unavailable"):
        raise ExtractionUnavailable(f"model call failed: {raw}")
    parsed = _parse_json(raw)
    if not parsed or not (parsed.get("fund_name") or parsed.get("lp_name")):
        raise ExtractionUnavailable(
            f"model returned no usable identification fields: {raw[:200]!r}")
    return {**_blank(), **{k: parsed.get(k) for k in _FIELDS}, "extraction_source": "model"}


def extract_k1(text: str, *, extractor=None) -> dict:
    """Run the extractor (real model by default; an injectable callable for tests).

    Raises `ExtractionUnavailable` on any failure — there is deliberately NO
    automatic fallback to a lower-quality method. `extractor` is a clean, explicit
    test seam; it is never set from production code paths.
    """
    fn = extractor or _model_extractor
    try:
        result = fn(text)
    except ExtractionUnavailable:
        raise
    except Exception as e:  # connection error, timeout, malformed response, …
        raise ExtractionUnavailable(f"{type(e).__name__}: {e}") from e
    result.setdefault("extraction_source", "injected")
    return result


def regex_extract_explicit(text: str) -> dict:
    """The old regex extraction. NEVER invoked automatically — not from
    `extract_k1`, not from `ingest_document`. Kept only for deliberate, opt-in use
    (offline inspection, or as an injected test double). Marked as such in the
    `extraction_source` so a regex-derived record is never mistaken for a
    model-quality one."""
    return {**_regex_extract(text), "extraction_source": "regex_explicit"}


# --------------------------------------------------------------- matching
def _best_match(query: str | None, candidates: list[tuple[str, str]]) -> dict | None:
    """Deterministic. Exact on _norm_name, else the single best fuzz.ratio if it
    clears MATCH_THRESHOLD. Same shape the hub's entity-name check uses."""
    if not query:
        return None
    qn = _norm_name(query)
    for key, name in candidates:
        if _norm_name(name) == qn:
            return {"key": key, "name": name, "score": 100.0, "exact": True}
    best = None
    ql = query.lower()
    for key, name in candidates:
        s = fuzz.ratio(ql, name.lower())
        if best is None or s > best["score"]:
            best = {"key": key, "name": name, "score": round(float(s), 1), "exact": False}
    return best if best and best["score"] >= MATCH_THRESHOLD else None


def route_extracted(extracted: dict) -> dict:
    """Deterministic identification. Match fund, then LP within that fund. Route
    only if BOTH match confidently; otherwise NEEDS_REVIEW with the reason."""
    fund = _best_match(extracted.get("fund_name"), fund_candidates())
    if fund is None:
        return {
            "status": "NEEDS_REVIEW",
            "review_reason": "fund_not_matched",
            "review_detail": (f"extracted fund name "
                              f"{extracted.get('fund_name')!r} did not match any fund in the "
                              f"roster at >= {MATCH_THRESHOLD}% similarity"),
            "matched_fund": None, "matched_lp": None,
        }

    lp = _best_match(extracted.get("lp_name"), lp_candidates(fund["key"]))
    if lp is None:
        return {
            "status": "NEEDS_REVIEW",
            "review_reason": "lp_not_matched",
            "review_detail": (f"fund matched ({fund['name']}) but extracted LP name "
                              f"{extracted.get('lp_name')!r} did not match any LP of that fund "
                              f"at >= {MATCH_THRESHOLD}% similarity"),
            "matched_fund": {"fund_id": fund["key"], "fund_name": fund["name"],
                             "match_score": fund["score"], "exact": fund["exact"]},
            "matched_lp": None,
        }

    return {
        "status": "ROUTED",
        "review_reason": None, "review_detail": None,
        "matched_fund": {"fund_id": fund["key"], "fund_name": fund["name"],
                         "match_score": fund["score"], "exact": fund["exact"]},
        "matched_lp": {"lp_id": lp["key"], "lp_name": lp["name"],
                       "match_score": lp["score"], "exact": lp["exact"]},
        "routed_to": {
            "queue": "K-1 distribution",
            "recipient": f"{lp['name']} — via {fund['name']} investor relations",
            "recipient_ref": f"{fund['key']}/{lp['key']}",
        },
    }
