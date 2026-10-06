"""Payment approval agent: turns a Phase-4 VerificationReport into a short,
plain-language alert for the person who approves the wire.
"""

from .common import ask_llm, usd

SYSTEM = (
    "You are drafting a wire-approval alert for a fund controller. Input is a "
    "verification result. Write a short alert (subject line + 3-5 sentences): "
    "name the fund and amount, state the decision (PASS / REVIEW / BLOCK), and if "
    "flagged, name the SPECIFIC anomaly in plain language and the recommended "
    "action. No jargon, no hedging, no invented details."
)

_ACTION = {
    "altered_routing_digit": "Do not wire. Call the GP on a known-good number to reconfirm the routing number.",
    "wrong_bank_valid_checksum": "Do not wire. The receiving bank differs from the fund's file; reconfirm with the GP directly.",
    "misspelled_entity_name": "Hold. The sender entity name is a near-miss of the GP's real name — verify sender identity.",
    "spoofed_sender_domain": "Do not reply. The sender domain is a look-alike of the GP's domain; treat as phishing and confirm out-of-band.",
    "last_minute_bank_change": "Do not wire. Unverified last-minute bank change — confirm with a known GP contact before any payment.",
    None: "Manual review before releasing payment.",
}


def draft_alert(report: dict, with_narrative: bool = True) -> dict:
    ext = report.get("extracted", {}) or {}
    decision = report.get("decision", "REVIEW")
    fraud_type = report.get("fraud_type")
    # Phase-6c: prefer the full multi-label view when the report carries it.
    labels = report.get("fraud_labels") or ([fraud_type] if fraud_type else [])
    failed = report.get("failed_checks") or []
    severity = report.get("overall_severity", "n/a")
    amount = ext.get("amount")
    fund = ext.get("fund_name") or report.get("fund_id")
    lp = ext.get("lp_name")

    if not report.get("fraud"):
        action = "Cleared for payment."
    elif len(labels) > 1:
        action = ("Do not release payment. Multiple identity/instruction checks failed at once ("
                  + ", ".join(l.replace("_", " ") for l in labels) + "). An approver must confirm "
                  "this request with the GP out-of-band before any payment."
                  + (" Treat as phishing." if "spoofed_sender_domain" in labels else ""))
    else:
        action = _ACTION.get(fraud_type, _ACTION[None])

    alert = {
        "fund": fund,
        "lp": lp,
        "amount": amount,
        "decision": decision,
        "fraud_type": fraud_type,          # primary label (back-compat)
        "fraud_labels": labels,            # every implicated label
        "failed_checks": failed,
        "overall_severity": severity,
        "confidence": report.get("confidence"),
        "recommended_action": action,
        "evidence": report.get("reasons", []),
    }

    if with_narrative:
        facts = (
            f"Fund: {fund}\nLP: {lp}\nAmount: {usd(amount) if isinstance(amount, (int, float)) else amount}\n"
            f"Decision: {decision}  severity: {severity}\nAnomalies: {', '.join(labels) or 'none'}\n"
            f"Confidence: {report.get('confidence')}\n"
            f"Evidence: {'; '.join(report.get('reasons', [])) or 'none'}\n"
            f"Recommended action: {action}"
        )
        alert["alert_text"] = ask_llm(SYSTEM, facts, num_predict=300)

    return alert
