"""Multi-label, all-checks-reported, severity-ranked verdict.

Replaces the old first-match-wins classification (return on the first failed
check) that was in rules.py and pipeline.py. EVERY check runs and reports its own
result; nothing short-circuits. `failed_checks` is the full set, `overall_severity`
is the MAX over that set, and `primary_label` (kept for back-compat with single-
`fraud_type` consumers) is a pure function of the failed SET plus a fixed priority
table — never of code ordering.

The PASS/REVIEW/BLOCK decision is unchanged: `flag` here == "any material check
failed", which reproduces the old `run_rules` / `_derive_verdict` flag exactly.
"""

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .aba import digits_only, is_valid_aba
from .baseline import Baseline
from .severity import max_severity, severity_of

ENTITY_NEARMISS = 80
BANK_MATCH = 90
DOMAIN_TYPOSQUAT = 80

_BANK_CHANGE_RE = re.compile(
    r"\b(chang(?:e|ed|ing)\s+(?:the\s+)?bank|bank(?:ing)?\s+(?:details|information|instructions)"
    r"\s+(?:have\s+)?(?:been\s+)?(?:chang|updat|revis)|new\s+(?:bank|wire|banking)\s+"
    r"(?:details|instructions|information)|updated?\s+(?:our\s+)?(?:bank|wire|banking)|"
    r"disregard\s+(?:the\s+)?previous|effective\s+immediately|as\s+of\s+today.*bank)\b",
    re.IGNORECASE,
)

# fraud_type label -> priority for breaking ties between EQUAL-severity findings.
# Fixed table, not code order. "Money is going to the wrong place / this is
# phishing" ranks above "a name is slightly off".
_LABEL_PRIORITY = [
    "last_minute_bank_change",
    "wrong_bank_valid_checksum",
    "spoofed_sender_domain",
    "altered_routing_digit",
    "unrecognized_sender_domain",
    "misspelled_entity_name",
]
# which check drives each label (for ranking a label by its check's severity)
_LABEL_DRIVER = {
    "last_minute_bank_change": "baseline_bank_match",
    "wrong_bank_valid_checksum": "baseline_bank_match",
    "spoofed_sender_domain": "sender_domain_match",
    "altered_routing_digit": "baseline_routing_match",
    "unrecognized_sender_domain": "sender_domain_match",
    "misspelled_entity_name": "entity_name_match",
}


@dataclass
class CheckResult:
    check: str
    passed: bool
    severity: str | None = None          # set only when not passed
    detail: str = ""
    observed: str | None = None
    baseline: str | None = None

    def as_dict(self):
        d = {"check": self.check, "passed": self.passed}
        if not self.passed:
            d["severity"] = self.severity
        if self.detail:
            d["detail"] = self.detail
        if self.observed is not None:
            d["observed"] = self.observed
        if self.baseline is not None:
            d["baseline"] = self.baseline
        return d


@dataclass
class Verdict:
    checks: list = field(default_factory=list)         # list[CheckResult] — ALL of them, always
    failed_checks: list = field(default_factory=list)  # names of the material failures (sorted)
    labels: list = field(default_factory=list)         # every fraud_type implicated (not just one)
    primary_label: str | None = None                   # highest-severity label; back-compat
    overall_severity: str = "none"
    flag: bool = False
    reasons: list = field(default_factory=list)

    def as_dict(self):
        return {
            "checks": [c.as_dict() for c in self.checks],
            "failed_checks": self.failed_checks,
            "labels": self.labels,
            "primary_label": self.primary_label,
            "overall_severity": self.overall_severity,
            "flag": self.flag,
            "reasons": self.reasons,
        }


def _norm_name(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", (s or "").lower())).strip()


def _labels_for(failed: set, bank_change_lang: bool, domain_is_typosquat: bool) -> list:
    """All fraud_type labels implicated by the failed-check SET (order-independent)."""
    out = []
    if "baseline_bank_match" in failed:
        out.append("last_minute_bank_change" if bank_change_lang else "wrong_bank_valid_checksum")
    elif "baseline_routing_match" in failed or "routing_checksum" in failed:
        out.append("altered_routing_digit")
    if "sender_domain_match" in failed:
        out.append("spoofed_sender_domain" if domain_is_typosquat else "unrecognized_sender_domain")
    if "entity_name_match" in failed:
        out.append("misspelled_entity_name")
    return out


def _primary(labels: list) -> str | None:
    if not labels:
        return None
    # rank by driving-check severity, then by the fixed priority table
    return sorted(
        labels,
        key=lambda lab: (-{"high": 4, "medium": 3, "medium-low": 2, "low": 1}.get(
            severity_of(_LABEL_DRIVER.get(lab, "")), 0),
            _LABEL_PRIORITY.index(lab) if lab in _LABEL_PRIORITY else 99),
    )[0]


def evaluate_checks(
    *,
    entity: str,
    bank_name: str,
    routing_number: str,
    sender_domain: str | None,
    baseline: Baseline,
    notice_text: str | None = None,
    bank_change_announced: bool | None = None,
) -> Verdict:
    """Run every check, always. `bank_change_announced` (from the fraud model's
    semantic read) overrides the regex when provided; otherwise the regex on
    `notice_text` is used."""
    rt = digits_only(routing_number)
    base_rt = digits_only(baseline.routing_number)
    checksum_ok = is_valid_aba(rt) if rt else True
    routing_matches = (rt == base_rt) if rt else True

    bank_sim = fuzz.token_sort_ratio((bank_name or "").lower(), baseline.bank_name.lower())
    bank_matches = bank_sim >= BANK_MATCH if bank_name else True

    ent_sim = fuzz.ratio((entity or "").lower(), baseline.entity_name.lower())
    entity_exact = _norm_name(entity) == _norm_name(baseline.entity_name) if entity else True
    entity_nearmiss = (not entity_exact) and ent_sim >= ENTITY_NEARMISS

    dom = (sender_domain or "").lower().strip().rstrip(".") or None
    authorized = baseline.authorized_domains
    domain_authorized = (dom in authorized) if dom else True
    dom_sim = fuzz.ratio(dom, baseline.domain.lower()) if dom else 0.0
    domain_is_typosquat = bool(dom) and not domain_authorized and dom_sim >= DOMAIN_TYPOSQUAT

    if bank_change_announced is None:
        change_lang = bool(_BANK_CHANGE_RE.search(notice_text or ""))
    else:
        change_lang = bool(bank_change_announced)

    # --- every check, independently, no short-circuit ---------------------
    checks = [
        CheckResult("routing_checksum", checksum_ok,
                    None if checksum_ok else "high",
                    "valid ABA check digit" if checksum_ok
                    else "routing number fails the ABA check-digit algorithm",
                    observed=rt),
        CheckResult("baseline_routing_match", routing_matches,
                    None if routing_matches else "high",
                    "" if routing_matches else "routing number differs from the fund's file",
                    observed=rt, baseline=base_rt),
        CheckResult("baseline_bank_match", bank_matches,
                    None if bank_matches else "high",
                    "" if bank_matches else "receiving bank differs from the fund's file",
                    observed=bank_name, baseline=baseline.bank_name),
        CheckResult("entity_name_match", not entity_nearmiss,
                    None if not entity_nearmiss else "medium",
                    "" if not entity_nearmiss
                    else f"GP name is a near-miss of the name on file (similarity {ent_sim:.0f}%)",
                    observed=entity, baseline=baseline.entity_name),
        CheckResult("sender_domain_match", domain_authorized,
                    None if domain_authorized else "high",
                    "" if domain_authorized
                    else (f"sender domain is a {dom_sim:.0f}%-similar look-alike of the GP domain"
                          if domain_is_typosquat else "sender domain is not an authorized domain"),
                    observed=dom, baseline=", ".join(sorted(authorized))),
        CheckResult("bank_change_language",
                    not (change_lang and not bank_matches),
                    None if not (change_lang and not bank_matches) else "medium-low",
                    "" if not (change_lang and not bank_matches)
                    else "notice pushes an unverified last-minute bank change"),
    ]

    material = {"routing_checksum", "baseline_routing_match", "baseline_bank_match",
                "entity_name_match", "sender_domain_match", "bank_change_language"}
    # routing_checksum only counts as a failure when the routing ALSO differs from
    # baseline (a valid baseline can't fail its own checksum; guards a degenerate case)
    failed = set()
    for c in checks:
        if c.passed or c.check not in material:
            continue
        if c.check == "routing_checksum" and routing_matches:
            continue
        failed.add(c.check)

    labels = _labels_for(failed, change_lang, domain_is_typosquat)
    primary = _primary(labels)
    overall = max_severity(failed)
    flag = bool(failed)

    reasons = []
    for c in checks:
        if c.check in failed and c.detail:
            reasons.append(c.detail)

    return Verdict(checks=checks, failed_checks=sorted(failed), labels=labels,
                   primary_label=primary, overall_severity=overall, flag=flag,
                   reasons=reasons)
