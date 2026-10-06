"""One reconciled verification report: extracted fields + deterministic rule
flags + (optional) the fine-tuned model's own flag, combined.

Reconciliation policy (UNCHANGED — this module never alters PASS/REVIEW/BLOCK):
  - BLOCKED if either the rules layer or the model flags fraud.
  - REVIEW if only the model flags.
  - Agreement raises confidence.

Since Phase-6c the report also carries the FULL multi-label view: every failed
check from both layers (`failed_checks`), every implicated fraud_type (`fraud_labels`),
and `overall_severity` = MAX across all failed checks. `fraud_type` is retained as a
single "primary" label (highest-severity) for back-compat.
"""

from dataclasses import dataclass, field

from .rules import RulesResult
from .verdict import Verdict, _primary
from .severity import max_severity


@dataclass
class VerificationReport:
    fund_id: str
    extracted: dict
    rules: dict
    model_flag: bool | None = None
    model_fraud_type: str | None = None

    decision: str = "PASS"          # PASS | REVIEW | BLOCK  (unchanged logic)
    fraud: bool = False
    fraud_type: str | None = None   # primary (highest-severity) label — back-compat
    fraud_labels: list = field(default_factory=list)   # every implicated label
    failed_checks: list = field(default_factory=list)  # union across rules + model
    overall_severity: str = "none"  # MAX across all failed checks
    confidence: str = "n/a"         # low | medium | high  (layer agreement, not severity)
    reasons: list = field(default_factory=list)

    def as_dict(self):
        return {
            "fund_id": self.fund_id,
            "decision": self.decision,
            "fraud": self.fraud,
            "fraud_type": self.fraud_type,
            "fraud_labels": self.fraud_labels,
            "failed_checks": self.failed_checks,
            "overall_severity": self.overall_severity,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "extracted": self.extracted,
            "rules": self.rules,
            "model": {"fraud_flag": self.model_flag, "fraud_type": self.model_fraud_type},
        }


def build_report(
    *,
    fund_id: str,
    extracted: dict,
    rules_result: RulesResult,
    model_flag: bool | None = None,
    model_fraud_type: str | None = None,
    model_verdict: Verdict | None = None,
) -> VerificationReport:
    r = VerificationReport(
        fund_id=fund_id, extracted=extracted, rules=rules_result.as_dict(),
        model_flag=model_flag, model_fraud_type=model_fraud_type,
    )
    rules_flag = rules_result.flag
    reasons = list(rules_result.reasons)

    # --- decision / confidence: unchanged ---------------------------------
    if rules_flag and model_flag:
        r.decision, r.fraud, r.confidence = "BLOCK", True, "high"
        reasons.append("model and rules agree")
    elif rules_flag and not model_flag:
        r.decision, r.fraud, r.confidence = "BLOCK", True, "medium"
        reasons.append("flagged by deterministic rules only")
    elif model_flag and not rules_flag:
        r.decision, r.fraud, r.confidence = "REVIEW", True, "medium"
        reasons.append("flagged by model only — rules found no baseline mismatch")
    elif model_flag is None and rules_flag:
        r.decision, r.fraud, r.confidence = "BLOCK", True, "medium"
    else:
        r.decision, r.fraud, r.confidence = "PASS", False, \
            "high" if model_flag is not None else "medium"

    # --- multi-label view: union across whichever layer(s) fired ---------
    rv = rules_result.verdict
    failed, labels, sevs = set(), [], []
    if rules_flag and rv:
        failed |= set(rv.failed_checks); labels += rv.labels; sevs.append(rv.overall_severity)
    if model_flag and model_verdict:
        failed |= set(model_verdict.failed_checks)
        labels += model_verdict.labels; sevs.append(model_verdict.overall_severity)
    # model flagged but rules didn't and we have no model verdict -> fall back to its scalar type
    if model_flag and not model_verdict and model_fraud_type:
        labels.append(model_fraud_type)

    r.failed_checks = sorted(failed)
    r.fraud_labels = list(dict.fromkeys(labels))          # de-dup, keep order
    r.overall_severity = max_severity(failed) if failed else (
        max(sevs, key=lambda s: {"none": 0, "low": 1, "medium-low": 2, "medium": 3, "high": 4}
            .get(s, 0)) if sevs else "none")
    r.fraud_type = _primary(r.fraud_labels) or (
        rules_result.fraud_type or model_fraud_type)
    r.reasons = reasons
    return r
