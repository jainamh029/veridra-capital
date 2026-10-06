"""THE demo surface — one callable, raw notice in, full decision object out.

    raw notice text (+ optional email-envelope sender)
      -> extraction            (v3.4 `capitalcall-extract`)
      -> checks                (verdict.evaluate_checks: ABA checksum, baseline routing/bank/
                                name/domain compare, bank-change language — EVERY check runs,
                                nothing short-circuits)
      -> model layer           (v3.4 `capitalcall-fraud`; Bug-1 deterministic derived verdict,
                                the model's self-reported identical/flag fields are IGNORED)
      -> reconciled decision   PASS / REVIEW / BLOCK  (unchanged logic)
      -> approver alert        deterministic; built from the FULL failed-checks list and
                                overall_severity (= MAX across findings, never the first one);
                                names every finding; frames BLOCK as "flagged for the approver,
                                do not pay without human override" — the platform never stops a
                                wire itself

Returns a dict: extracted fields, every check, both layers, decision, alert.
Never raises on a resolvable-baseline miss — that comes back as status="NEEDS_ONBOARDING".
"""

from .baseline import load_baselines, resolve_by_fund_name
from .pipeline import extract_fields, model_layer
from .report import build_report
from .rules import parse_sender_domain, run_rules

_HUMAN_NOTE = ("This is an advisory flag for the approver. The platform does not stop or send "
               "wires on its own — payment proceeds only if an approver reviews this and overrides.")

# one plain-language clause per check (used to build a multi-finding alert)
_CHECK_CLAUSE = {
    "routing_checksum": "the routing number is not a structurally valid ABA number",
    "baseline_routing_match": "the routing number differs from the fund's onboarded instructions",
    "baseline_bank_match": "the receiving bank differs from the fund's onboarded instructions",
    "entity_name_match": "the sender's GP name is a near-miss of the name on file",
    "sender_domain_match": "the sender domain is not one of the fund's authorized domains",
    "bank_change_language": "the notice pushes an unverified last-minute change of bank details",
}
_SEVERITY_LEAD = {
    "high": "Do not release payment.",
    "medium": "Hold for approver review.",
    "medium-low": "Hold for approver review.",
    "low": "Approver review recommended.",
    "none": "Approver review recommended.",
}


def _line_for(check, cv):
    """One '- ...' bullet describing a failed check, using its check-view detail."""
    v = cv.get(check, {})
    if check == "routing_checksum":
        return f"- ABA routing checksum failed for {v.get('observed')}."
    if check == "baseline_routing_match":
        return (f"- Routing number {v.get('observed')} does not match the fund's file "
                f"({v.get('baseline')}).")
    if check == "baseline_bank_match":
        return (f"- Receiving bank '{v.get('observed')}' does not match the fund's file "
                f"('{v.get('baseline')}').")
    if check == "entity_name_match":
        return (f"- Sender GP name '{v.get('observed')}' is a near-miss of the name on file "
                f"('{v.get('baseline')}'){_sim(v)}.")
    if check == "sender_domain_match":
        return (f"- Sender domain '{v.get('observed')}' is not an authorized domain "
                f"({v.get('baseline')}){_sim(v, 'similarity_to_gp')}.")
    if check == "bank_change_language":
        return "- The notice pushes an unverified last-minute change of bank details."
    return f"- {check} failed."


def _sim(v, key="similarity"):
    s = v.get(key)
    return f", similarity {s:.0f}%" if isinstance(s, (int, float)) else ""


def _recommended_action(failed, severity):
    lead = _SEVERITY_LEAD.get(severity, _SEVERITY_LEAD["none"])
    clauses = [_CHECK_CLAUSE[c] for c in failed if c in _CHECK_CLAUSE]
    if len(clauses) > 1:
        joined = "; ".join(clauses[:-1]) + "; and " + clauses[-1]
        why = f"Because {joined}, "
    elif clauses:
        why = f"Because {clauses[0]}, "
    else:
        why = ""
    phishing = " Treat this as phishing." if "sender_domain_match" in failed else ""
    return (f"{lead} {why}an approver must confirm this request with the GP through a known, "
            f"separate channel (e.g. a previously-verified phone number) before any payment.{phishing}")


def _alert(report, cv):
    ext = report["extracted"]
    amount = ext.get("amount")
    amt = f"${amount:,.2f}" if isinstance(amount, (int, float)) else (amount or "unknown amount")
    fund = ext.get("fund_name") or report.get("fund_id")
    failed = list(report.get("failed_checks") or [])
    severity = report.get("overall_severity", "none")
    labels = report.get("fraud_labels") or ([report["fraud_type"]] if report.get("fraud_type") else [])

    if failed:
        lines = [_line_for(c, cv) for c in failed]
    else:  # model-only flag with no concrete failed check
        lines = ["- The wire-fraud model flagged this notice; the deterministic checks found "
                 "no baseline mismatch. Manual review before releasing payment."]
        severity = severity if severity != "none" else "medium"

    subj = (f"{report['decision']} ({severity}): capital call for {fund} ({amt}) — "
            + (", ".join(l.replace('_', ' ') for l in labels) if labels else "anomaly"))
    body = (f"Decision: {report['decision']}  |  severity: {severity}  |  "
            f"confidence: {report['confidence']}.\n\n"
            f"What failed ({len(lines)} finding{'s' if len(lines) != 1 else ''}):\n"
            + "\n".join(lines) + "\n\n"
            f"Recommended action: {_recommended_action(failed, severity)}\n\n{_HUMAN_NOTE}")
    return {"subject": subj, "body": body, "failed_checks": failed,
            "fraud_labels": labels, "overall_severity": severity,
            "recommended_action": _recommended_action(failed, severity)}


def _checks_view(verdict, baseline, sender_domain):
    """Human-readable per-check view from a Verdict (every check, always)."""
    out = {}
    for c in verdict.checks:
        out[c.check] = {
            "passed": c.passed,
            "severity": c.severity,
            "observed": c.observed,
            "baseline": c.baseline,
            "detail": c.detail,
            "similarity_to_gp": None,
        }
    # enrich domain check with similarity number from the legacy dict if present
    return out


def run_pipeline(notice_text: str, *, sender_domain: str | None = None,
                 sender_email: str | None = None, use_model: bool = True,
                 baselines: dict | None = None) -> dict:
    extracted = extract_fields(notice_text)
    baselines = baselines if baselines is not None else load_baselines()
    baseline = resolve_by_fund_name(extracted.get("fund_name", ""), baselines)

    env_domain = sender_domain or parse_sender_domain(notice_text)
    domain_source = ("email_envelope" if sender_domain
                     else "notice_from_header" if env_domain else "unavailable")

    if baseline is None:
        return {
            "status": "NEEDS_ONBOARDING",
            "note": "No locked baseline on file for this fund — cannot verify wire instructions. "
                    "In production this itself routes to an approver for payee onboarding.",
            "extracted": extracted,
            "sender_domain": {"value": env_domain, "source": domain_source},
            "decision": "REVIEW", "fraud": True, "fraud_type": None, "fraud_labels": [],
            "failed_checks": ["baseline_resolution"], "overall_severity": "medium",
            "confidence": "n/a",
            "alert": {"subject": f"REVIEW (medium): unknown fund '{extracted.get('fund_name')}'",
                      "body": "This capital call is for a fund with no onboarded baseline. An "
                              "approver must complete payee onboarding and verify wire "
                              "instructions before any payment.\n\n" + _HUMAN_NOTE,
                      "failed_checks": ["baseline_resolution"], "fraud_labels": [],
                      "overall_severity": "medium",
                      "recommended_action": "Route to approver for payee onboarding."},
        }

    rules_result = run_rules(
        entity=extracted.get("entity", ""), bank_name=extracted.get("bank_name", ""),
        routing_number=extracted.get("routing_number", ""),
        account_number=extracted.get("account_number", ""),
        sender_domain=env_domain, notice_text=notice_text, baseline=baseline,
    )

    ml = {"parsed": None, "raw_flag": None, "raw_type": None, "derived_flag": None,
          "derived_type": None, "verdict": None}
    if use_model:
        try:
            ml = model_layer(extracted, sender_email or f"unknown@{env_domain or 'unknown'}",
                             env_domain or "", notice_text, baseline)
        except Exception as e:  # pipeline degrades to rules-only
            ml["error"] = f"{type(e).__name__}: {e}"

    report = build_report(
        fund_id=baseline.fund_id, extracted=extracted, rules_result=rules_result,
        model_flag=ml["derived_flag"], model_fraud_type=ml["derived_type"],
        model_verdict=ml["verdict"],
    ).as_dict()

    # per-check view (rules verdict is authoritative for the deterministic checks;
    # domain similarity number comes from the legacy checks dict)
    cv = _checks_view(rules_result.verdict, baseline, env_domain)
    lc = rules_result.checks
    if "sender_domain_match" in cv:
        cv["sender_domain_match"]["similarity_to_gp"] = lc.get("domain_similarity_to_gp")
        cv["sender_domain_match"]["baseline"] = ", ".join(lc.get("authorized_domains", []))
    if "entity_name_match" in cv:
        cv["entity_name_match"]["similarity"] = lc.get("entity_similarity")
    if "baseline_bank_match" in cv:
        cv["baseline_bank_match"]["similarity"] = lc.get("bank_similarity")

    alert = _alert(report, cv) if report["decision"] != "PASS" else None

    return {
        "status": "OK",
        "extracted": extracted,
        "sender_domain": {"value": env_domain, "source": domain_source},
        "fund_baseline": {
            "fund_id": baseline.fund_id, "fund_name": baseline.fund_name,
            "gp_entity": baseline.entity_name, "bank": baseline.bank_name,
            "routing": baseline.routing_number,
            "authorized_domains": lc.get("authorized_domains", []),
        },
        "checks": cv,
        "rules_layer": rules_result.as_dict(),
        "model_layer": {
            "raw_flag": ml["raw_flag"], "raw_type": ml["raw_type"],
            "derived_flag": ml["derived_flag"], "derived_type": ml["derived_type"],
            "failed_checks": ml["verdict"].failed_checks if ml.get("verdict") else [],
            "parsed": ml["parsed"], "error": ml.get("error"),
        },
        "decision": report["decision"],
        "fraud": report["fraud"],
        "fraud_type": report["fraud_type"],          # primary (highest-severity) — back-compat
        "fraud_labels": report["fraud_labels"],       # every implicated label
        "failed_checks": report["failed_checks"],     # union across both layers
        "overall_severity": report["overall_severity"],
        "confidence": report["confidence"],
        "alert": alert,
    }
