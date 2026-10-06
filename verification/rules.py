"""Deterministic wire-fraud checks. No LLM. Everything here is a checksum, an
exact comparison, or an edit-distance ratio against the fund's locked baseline.

Since v3.4 Phase-6c this is a thin wrapper over `verdict.evaluate_checks()` — the
multi-label, all-checks-reported, severity-ranked verdict. `RulesResult` keeps its
old single-`fraud_type` / `checks`-dict shape for existing callers; `.verdict`
exposes the full structure.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .aba import digits_only, is_valid_aba
from .baseline import Baseline
from .verdict import (BANK_MATCH, DOMAIN_TYPOSQUAT, ENTITY_NEARMISS, Verdict,
                      _norm_name, evaluate_checks)

# parse_sender_domain kept here for backward-compatible imports.
def parse_sender_domain(notice_text: str) -> str | None:
    m = re.search(r"[Ff]rom:[^\n<]*?([A-Za-z0-9._%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", notice_text or "")
    if not m:
        return None
    return m.group(1).split("@")[1].lower().rstrip(".")


@dataclass
class RulesResult:
    fund_id: str
    checks: dict = field(default_factory=dict)   # legacy flat dict of evidence
    flag: bool = False
    fraud_type: str | None = None                # == verdict.primary_label
    reasons: list = field(default_factory=list)
    verdict: Verdict | None = None               # full multi-label structure

    def as_dict(self):
        return {
            "fund_id": self.fund_id,
            "rules_flag": self.flag,
            "rules_fraud_type": self.fraud_type,
            "rules_fraud_labels": self.verdict.labels if self.verdict else [],
            "rules_failed_checks": self.verdict.failed_checks if self.verdict else [],
            "rules_overall_severity": self.verdict.overall_severity if self.verdict else "none",
            "rules_reasons": self.reasons,
            "checks": self.checks,
        }


def _legacy_checks_dict(v: Verdict, baseline: Baseline, entity, bank_name,
                        routing_number, sender_domain) -> dict:
    """Reconstruct the old flat `checks` dict some callers still read."""
    rt = digits_only(routing_number)
    dom = (sender_domain or "").lower().rstrip(".") or None
    bank_sim = fuzz.token_sort_ratio((bank_name or "").lower(), baseline.bank_name.lower())
    ent_sim = fuzz.ratio((entity or "").lower(), baseline.entity_name.lower())
    dom_sim = fuzz.ratio(dom, baseline.domain.lower()) if dom else 0.0
    by = {c.check: c for c in v.checks}
    return {
        "routing_observed": rt,
        "routing_baseline": digits_only(baseline.routing_number),
        "routing_checksum_valid": by["routing_checksum"].passed,
        "routing_matches_baseline": by["baseline_routing_match"].passed,
        "bank_similarity": round(bank_sim, 1),
        "bank_matches_baseline": by["baseline_bank_match"].passed,
        "entity_similarity": round(ent_sim, 1),
        "entity_matches_baseline": _norm_name(entity) == _norm_name(baseline.entity_name),
        "sender_domain": dom,
        "authorized_domains": sorted(baseline.authorized_domains),
        "domain_similarity_to_gp": round(dom_sim, 1),
        "bank_change_language": not by["bank_change_language"].passed,
    }


def run_rules(
    *,
    entity: str,
    bank_name: str,
    routing_number: str,
    account_number: str | None,
    sender_domain: str | None,
    notice_text: str,
    baseline: Baseline,
) -> RulesResult:
    v = evaluate_checks(
        entity=entity, bank_name=bank_name, routing_number=routing_number,
        sender_domain=sender_domain, baseline=baseline, notice_text=notice_text,
    )
    return RulesResult(
        fund_id=baseline.fund_id,
        checks=_legacy_checks_dict(v, baseline, entity, bank_name, routing_number, sender_domain),
        flag=v.flag, fraud_type=v.primary_label, reasons=v.reasons, verdict=v,
    )
