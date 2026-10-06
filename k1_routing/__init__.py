"""Module 5 — K-1 Routing.

Reads an annual Schedule K-1 and identifies which fund + which LP it belongs to,
so it can be routed. No fraud detection (a K-1 is not a payment instruction), no
fine-tuned model — extraction uses the general-purpose `qwen2.5:3b-instruct`,
matching is deterministic `rapidfuzz` code reusing the hub's approach, and the
fund/LP roster is the existing one.

If the extraction model is unavailable the document lands in AWAITING_EXTRACTION
and is retried later — it is NEVER silently downgraded to a lower-quality method.
Can't identify confidently -> NEEDS_REVIEW.
"""

from .core import ExtractionUnavailable, extract_k1, regex_extract_explicit, route_extracted
from .service import (get_record, ingest_document, list_for_fund, list_records,
                      retry_pending)

__all__ = [
    "ingest_document", "retry_pending", "get_record", "list_records", "list_for_fund",
    "extract_k1", "route_extracted", "regex_extract_explicit", "ExtractionUnavailable",
]
