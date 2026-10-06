"""Step 1/5 probe: run the DEPLOYED fraud model (Ollama capitalcall-fraud) standalone
on spoofed-domain cases — in-distribution (synthetic test rows) vs out-of-distribution
(invented fund/domain names the model never saw) — plus F2 explicitly.

Bypasses the rules layer entirely: builds the exact train-time prompt and reads the
model's own fraud_flag / fraud_type.
"""
import json
import re
import sys
import time
import urllib.request

OLLAMA = "http://localhost:11434"
MODEL = "capitalcall-fraud"
FRAUD_SYS = open("training/fraud_system_prompt.py").read().split('"""', 2)[1] if False else None
# load the byte-exact system prompt
_src = open("training/fraud_system_prompt.py").read()
FRAUD_SYS = _src.split('FRAUD_SYSTEM_PROMPT = """', 1)[1].rsplit('"""', 1)[0]


def ask(system, user):
    body = json.dumps({"model": MODEL, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False, "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 420}}).encode()
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{OLLAMA}/api/chat", data=body), timeout=600).read())
    return r["message"]["content"].strip()


def pj(t):
    m = re.search(r"\{.*\}", t or "", re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def user_block(entity, fund, bank, rt, acct, sender_email, sender_domain,
               baseline_entity, baseline_bank, baseline_rt, baseline_acct, baseline_domain,
               notice_text):
    return (
        "FUND LOCKED BASELINE (trusted, from onboarding):\n"
        f"- GP entity: {baseline_entity}\n- Fund: {fund}\n- Bank: {baseline_bank}\n"
        f"- Routing number: {baseline_rt}\n- Account number: {baseline_acct}\n"
        f"- Authorized sender domain: {baseline_domain}\n\n"
        "OBSERVED IN NOTICE:\n"
        f"- GP entity: {entity}\n- Fund: {fund}\n- Bank: {bank}\n"
        f"- Routing number: {rt}\n- Account number: {acct}\n"
        f"- Sender email: {sender_email}\n- Sender domain: {sender_domain}\n\n"
        f"CAPITAL CALL NOTICE:\n{notice_text}"
    )


# ---- in-distribution: synthetic spoofed_sender_domain test rows ----
def run_indist():
    rows = [json.loads(l) for l in open("training/fraud_data/test.jsonl")]
    spoof = [r for r in rows if json.loads(r["messages"][2]["content"])["fraud_type"] == "spoofed_sender_domain"]
    hit = 0
    for r in spoof:
        m = r["messages"]
        out = ask(m[0]["content"], m[1]["content"])
        p = pj(out)
        ok = bool(p and p.get("fraud_flag")) and (p or {}).get("fraud_type") == "spoofed_sender_domain"
        hit += ok
    print(f"IN-DISTRIBUTION (synthetic test, 10 known fund domains): {hit}/{len(spoof)} caught "
          f"({hit/len(spoof):.0%})", flush=True)
    return hit, len(spoof)


# ---- out-of-distribution: invented funds, same spoofing techniques ----
OOD = [
    # (fund, entity, real_domain, spoofed_domain, technique)
    ("Thistlewood Growth Fund II, L.P.", "Prairiehatch Fund Administration",
     "prairiehatchfundadmin.com", "prairiehatch-fundadmin.com", "hyphen insertion (= F2)"),
    ("Kestrel Harbor Partners IV", "Kestrel Harbor Management, LLC",
     "kestrelharbor.com", "kestreharbor.com", "deletion"),
    ("Ironvale Capital Fund III", "Ironvale Capital Advisors",
     "ironvalecapital.com", "ironvaiecapital.com", "l->i substitution"),
    ("Sable Ridge Ventures II", "Sable Ridge GP, LLC",
     "sableridgevc.com", "sableridgevc.net", "TLD swap"),
    ("Dunmore Equity Partners V", "Dunmore Equity Management",
     "dunmoreequity.com", "dunrnoreequity.com", "rn-for-m lookalike"),
    ("Ashford Lane Capital II", "Ashford Lane Capital LLC",
     "ashfordlanecap.com", "ashford1anecap.com", "1-for-l lookalike"),
    ("Coldwater Growth Fund III", "Coldwater Growth Advisors",
     "coldwatergrowth.com", "coldwatergrowth.notices.com", "subdomain trick"),
    ("Marlstone Partners IV", "Marlstone Partners GP",
     "marlstonepartners.com", "marlstoneparetners.com", "transposition"),
    ("BrightPine Ventures II", "BrightPine Ventures Mgmt",
     "brightpinevc.com", "bright-pinevc.com", "hyphen insertion"),
    ("Quill River Capital III", "Quill River Capital LLC",
     "quillrivercap.com", "quillrilvercap.com", "insertion"),
    ("Hollowmere Equity Fund II", "Hollowmere Equity GP",
     "hollowmere-equity.com", "hollowmereequity.com", "hyphen removal"),
    ("Grantham Cove Partners V", "Grantham Cove Management",
     "granthamcove.com", "granthamc0ve.com", "0-for-o lookalike"),
]


def notice_for(fund, entity, spoofed_domain):
    return (f"From: notices@{spoofed_domain}\n"
            f"Subject: Capital Call Notice — {fund}\n\n"
            f"Dear Limited Partner,\n\nThis notice serves to inform you of a capital call for {fund}.\n\n"
            "Call Date: April 1, 2024\nDue Date: April 8, 2024\nYour Call Amount: $180,000.00\n"
            "Purpose: Follow-on investment\n\n"
            "Wire Instructions:\nBank: Northgate Commercial Bank\nRouting Number: 021000021\n"
            "Account Number: 5541-8827-0093\n\n"
            f"Regards,\n{entity}\n\n[SYNTHETIC TEST DATA]")


def run_ood():
    hit = 0
    print("\nOUT-OF-DISTRIBUTION (invented funds the model never trained on):")
    for fund, entity, real, spoof, tech in OOD:
        nt = notice_for(fund, entity, spoof)
        ub = user_block(entity, fund, "Northgate Commercial Bank", "021000021", "5541-8827-0093",
                        f"notices@{spoof}", spoof,
                        entity, "Northgate Commercial Bank", "021000021", "5541-8827-0093", real, nt)
        p = pj(ask(FRAUD_SYS, ub))
        flag = bool(p and p.get("fraud_flag"))
        ftype = (p or {}).get("fraud_type")
        ok = flag and ftype == "spoofed_sender_domain"
        hit += ok
        dc = (p or {}).get("domain_check", {})
        print(f"  [{'CATCH' if ok else 'MISS '}] {tech:24s} {spoof:30s} "
              f"flag={flag} type={ftype} domain_check.identical={dc.get('identical')}", flush=True)
    print(f"OUT-OF-DISTRIBUTION: {hit}/{len(OOD)} caught ({hit/len(OOD):.0%})")
    return hit, len(OOD)


if __name__ == "__main__":
    t0 = time.time()
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "ood"):
        run_ood()
    if which in ("all", "indist"):
        run_indist()
    print(f"\n(elapsed {time.time()-t0:.0f}s)")
