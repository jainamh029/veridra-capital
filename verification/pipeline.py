"""Verification service: raw notice (+ extracted fields) -> reconciled report.

Deterministic rules always run. The fine-tuned Ollama fraud model is consulted
only if `use_model=True` and Ollama is reachable; the pipeline degrades cleanly
to rules-only otherwise.
"""

import json
import os
import re
import urllib.request

from .baseline import Baseline, load_baselines, resolve_by_fund_name
from .report import build_report
from .rules import parse_sender_domain, run_rules
from .verdict import evaluate_checks

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EXTRACT_MODEL = os.environ.get("CC_EXTRACT_MODEL", "capitalcall-extract")
FRAUD_MODEL = os.environ.get("CC_FRAUD_MODEL", "capitalcall-fraud")

# System prompts must stay byte-identical to training/. Loaded from there.
_TRAIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "training")


def _load_prompt(module_file, var):
    src = open(os.path.join(_TRAIN_DIR, module_file)).read()
    return src.split(f'{var} = """', 1)[1].rsplit('"""', 1)[0]


EXTRACT_SYSTEM = _load_prompt("system_prompt.py", "EXTRACTION_SYSTEM_PROMPT")
FRAUD_SYSTEM = _load_prompt("fraud_system_prompt.py", "FRAUD_SYSTEM_PROMPT")


def _ollama_chat(model, system, user, num_predict=400, timeout=600):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 2048, "num_predict": num_predict},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body)
    resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return resp["message"]["content"].strip()


def _parse_json(text):
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def extract_fields(notice_text: str) -> dict:
    """Run the fine-tuned extraction model over a raw notice."""
    out = _ollama_chat(EXTRACT_MODEL, EXTRACT_SYSTEM, notice_text, num_predict=300)
    return _parse_json(out) or {}


def _fraud_user_block(extracted: dict, sender_email: str, sender_domain: str,
                      notice_text: str, b: Baseline) -> str:
    """Must match training/prepare_fraud_data.py's user message layout."""
    baseline_block = (
        "FUND LOCKED BASELINE (trusted, from onboarding):\n"
        f"- GP entity: {b.entity_name}\n"
        f"- Fund: {b.fund_name}\n"
        f"- Bank: {b.bank_name}\n"
        f"- Routing number: {b.routing_number}\n"
        f"- Account number: {b.account_number}\n"
        f"- Authorized sender domain: {b.domain}"
    )
    observed_block = (
        "OBSERVED IN NOTICE:\n"
        f"- GP entity: {extracted.get('entity', '')}\n"
        f"- Fund: {extracted.get('fund_name', '')}\n"
        f"- Bank: {extracted.get('bank_name', '')}\n"
        f"- Routing number: {extracted.get('routing_number', '')}\n"
        f"- Account number: {extracted.get('account_number', '')}\n"
        f"- Sender email: {sender_email}\n"
        f"- Sender domain: {sender_domain}"
    )
    return baseline_block + "\n\n" + observed_block + "\n\nCAPITAL CALL NOTICE:\n" + notice_text.strip()


def _norm_s(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", str(s or "").lower())).strip()


def _derive_verdict(p, b: Baseline, *, entity, bank_name, routing_number, sender_domain):
    """Bug-1 fix: the model is unreliable at self-reporting `identical` /
    `first_diff_position` (free-form character diffing + an 87%-YES training prior)
    and sometimes 'auto-corrects' a typosquat when echoing it. So the verdict is
    recomputed deterministically from the values we hold (extracted fields + locked
    baseline + parsed envelope domain). The model still contributes the extraction
    and the semantic `bank_change_announced` read.

    Since Phase-6c this delegates to `verdict.evaluate_checks` (multi-label,
    all-checks-reported). Returns (flag, primary_label, verdict) — `verdict` is the
    full structure; callers that want the old dict use `verdict.as_dict()`."""
    v = evaluate_checks(
        entity=entity, bank_name=bank_name, routing_number=routing_number,
        sender_domain=sender_domain, baseline=b,
        bank_change_announced=bool(p.get("bank_change_announced")),
    )
    return v.flag, v.primary_label, v


def model_layer(extracted, sender_email, sender_domain, notice_text, b: Baseline):
    """Full model-layer result: the raw model output, the Bug-1 deterministic
    derived verdict, and the per-check breakdown behind it."""
    user = _fraud_user_block(extracted, sender_email, sender_domain, notice_text, b)
    out = _ollama_chat(FRAUD_MODEL, FRAUD_SYSTEM, user, num_predict=512)
    p = _parse_json(out)
    if not p:
        return {"parsed": False, "raw_flag": None, "raw_type": None,
                "derived_flag": None, "derived_type": None, "verdict": None}
    flag, ftype, v = _derive_verdict(
        p, b,
        entity=extracted.get("entity"), bank_name=extracted.get("bank_name"),
        routing_number=extracted.get("routing_number"), sender_domain=sender_domain,
    )
    return {"parsed": True, "raw_flag": bool(p.get("fraud_flag")),
            "raw_type": p.get("fraud_type"), "derived_flag": flag,
            "derived_type": ftype, "verdict": v}


def model_fraud_flag(extracted, sender_email, sender_domain, notice_text, b: Baseline):
    ml = model_layer(extracted, sender_email, sender_domain, notice_text, b)
    return ml["derived_flag"], ml["derived_type"]


def verify(
    *,
    notice_text: str,
    extracted: dict | None = None,
    baseline: Baseline | None = None,
    sender_domain: str | None = None,
    sender_email: str | None = None,
    use_model: bool = True,
    baselines: dict | None = None,
):
    """Main entry point. `extracted` and `baseline` may be supplied (pipeline
    caller already has them) or resolved here."""
    if extracted is None:
        extracted = extract_fields(notice_text)

    if baselines is None:
        baselines = load_baselines()
    if baseline is None:
        baseline = resolve_by_fund_name(extracted.get("fund_name", ""), baselines)
    if baseline is None:
        raise ValueError("could not resolve a fund baseline for this notice")

    env_domain = sender_domain or parse_sender_domain(notice_text)

    rules_result = run_rules(
        entity=extracted.get("entity", ""),
        bank_name=extracted.get("bank_name", ""),
        routing_number=extracted.get("routing_number", ""),
        account_number=extracted.get("account_number", ""),
        sender_domain=env_domain,
        notice_text=notice_text,
        baseline=baseline,
    )

    m_flag = m_type = m_verdict = None
    if use_model:
        try:
            ml = model_layer(
                extracted, sender_email or f"unknown@{env_domain or 'unknown'}",
                env_domain or "", notice_text, baseline,
            )
            m_flag, m_type, m_verdict = ml["derived_flag"], ml["derived_type"], ml["verdict"]
        except Exception:
            m_flag = m_type = m_verdict = None  # rules-only fallback

    return build_report(
        fund_id=baseline.fund_id, extracted=extracted, rules_result=rules_result,
        model_flag=m_flag, model_fraud_type=m_type, model_verdict=m_verdict,
    )
