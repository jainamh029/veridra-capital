"""Step 5 — prove the spoofed-domain gap is closed in the MODEL itself.

Runs the DEPLOYED Ollama model (capitalcall-fraud) STANDALONE — no rules layer.

  A. held-out augment_test.jsonl: 100 spoofed + 100 clean over 25 companies whose
     domains NEVER appear in training (leak-free). -> spoofed catch rate + clean FP rate.
  B. the 12 hand-built OOD cases from probe_domain_gap.py (incl. F2) + F2 explicitly.
"""
import collections
import json
import re
import time
import urllib.request

OLLAMA, MODEL = "http://localhost:11434", "capitalcall-fraud"
_src = open("training/fraud_system_prompt.py").read()
FRAUD_SYS = _src.split('FRAUD_SYSTEM_PROMPT = """', 1)[1].rsplit('"""', 1)[0]


def ask(system, user):
    body = json.dumps({"model": MODEL, "messages": [
        {"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False, "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 420}}).encode()
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{OLLAMA}/api/chat", data=body), timeout=600).read())["message"]["content"].strip()


def pj(t):
    m = re.search(r"\{.*\}", t or "", re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def part_A():
    rows = [json.loads(l) for l in open("training/fraud_data/augment_test.jsonl")]
    spoof = [r for r in rows if json.loads(r["messages"][2]["content"])["fraud_flag"]]
    clean = [r for r in rows if not json.loads(r["messages"][2]["content"])["fraud_flag"]]
    s_hit = c_fp = 0
    t0 = time.time()
    for i, r in enumerate(spoof):
        p = pj(ask(r["messages"][0]["content"], r["messages"][1]["content"]))
        if p and p.get("fraud_flag") and p.get("fraud_type") == "spoofed_sender_domain":
            s_hit += 1
        if (i + 1) % 25 == 0:
            print(f"  spoof {i+1}/{len(spoof)} ({(time.time()-t0)/(i+1):.1f}s/row)", flush=True)
    for i, r in enumerate(clean):
        p = pj(ask(r["messages"][0]["content"], r["messages"][1]["content"]))
        if p and p.get("fraud_flag"):
            c_fp += 1
        if (i + 1) % 25 == 0:
            print(f"  clean {i+1}/{len(clean)}", flush=True)
    print(f"\nA. HELD-OUT augment_test (fresh domains, leak-free):")
    print(f"   spoofed-domain caught (model flag, standalone): {s_hit}/{len(spoof)} ({s_hit/len(spoof):.0%})")
    print(f"   false positives on clean:                       {c_fp}/{len(clean)} ({c_fp/len(clean):.0%})")
    return s_hit, len(spoof), c_fp, len(clean)


OOD = [
    ("Thistlewood Growth Fund II, L.P.", "Prairiehatch Fund Administration",
     "prairiehatchfundadmin.com", "prairiehatch-fundadmin.com", "hyphen insertion (= F2)"),
    ("Kestrel Harbor Partners IV", "Kestrel Harbor Management, LLC", "kestrelharbor.com", "kestreharbor.com", "deletion"),
    ("Ironvale Capital Fund III", "Ironvale Capital Advisors", "ironvalecapital.com", "ironvaiecapital.com", "l->i sub"),
    ("Sable Ridge Ventures II", "Sable Ridge GP, LLC", "sableridgevc.com", "sableridgevc.net", "TLD swap"),
    ("Dunmore Equity Partners V", "Dunmore Equity Management", "dunmoreequity.com", "dunrnoreequity.com", "rn-for-m"),
    ("Ashford Lane Capital II", "Ashford Lane Capital LLC", "ashfordlanecap.com", "ashford1anecap.com", "1-for-l"),
    ("Coldwater Growth Fund III", "Coldwater Growth Advisors", "coldwatergrowth.com", "coldwatergrowth.notices.com", "subdomain"),
    ("Marlstone Partners IV", "Marlstone Partners GP", "marlstonepartners.com", "marlstoneparetners.com", "transposition"),
    ("BrightPine Ventures II", "BrightPine Ventures Mgmt", "brightpinevc.com", "bright-pinevc.com", "hyphen insertion"),
    ("Quill River Capital III", "Quill River Capital LLC", "quillrivercap.com", "quillrilvercap.com", "insertion"),
    ("Hollowmere Equity Fund II", "Hollowmere Equity GP", "hollowmere-equity.com", "hollowmereequity.com", "hyphen removal"),
    ("Grantham Cove Partners V", "Grantham Cove Management", "granthamcove.com", "granthamc0ve.com", "0-for-o"),
]


def ub(entity, fund, sd, real_domain):
    nt = (f"From: notices@{sd}\nSubject: Capital Call Notice — {fund}\n\n"
          f"Dear Limited Partner,\n\nThis notice serves to inform you of a capital call for {fund}.\n\n"
          "Call Date: April 1, 2024\nDue Date: April 8, 2024\nYour Call Amount: $180,000.00\n"
          "Purpose: Follow-on investment\n\nWire Instructions:\nBank: Northgate Commercial Bank\n"
          f"Routing Number: 021000021\nAccount Number: 5541-8827-0093\n\nRegards,\n{entity}\n\n[SYNTHETIC TEST DATA]")
    return (
        "FUND LOCKED BASELINE (trusted, from onboarding):\n"
        f"- GP entity: {entity}\n- Fund: {fund}\n- Bank: Northgate Commercial Bank\n"
        f"- Routing number: 021000021\n- Account number: 5541-8827-0093\n"
        f"- Authorized sender domain: {real_domain}\n\n"
        "OBSERVED IN NOTICE:\n"
        f"- GP entity: {entity}\n- Fund: {fund}\n- Bank: Northgate Commercial Bank\n"
        f"- Routing number: 021000021\n- Account number: 5541-8827-0093\n"
        f"- Sender email: notices@{sd}\n- Sender domain: {sd}\n\nCAPITAL CALL NOTICE:\n{nt}")


def part_B():
    hit = 0
    print("\nB. hand-built OOD cases (standalone model flag):")
    for fund, entity, real, sd, tech in OOD:
        p = pj(ask(FRAUD_SYS, ub(entity, fund, sd, real)))
        flag = bool(p and p.get("fraud_flag"))
        ft = (p or {}).get("fraud_type")
        ok = flag and ft == "spoofed_sender_domain"
        hit += ok
        dc = (p or {}).get("domain_check", {})
        print(f"   [{'CATCH' if ok else 'MISS '}] {tech:22s} {sd:30s} flag={flag} "
              f"type={ft} dc.identical={dc.get('identical')} len={dc.get('observed_length')}/{dc.get('baseline_length')}",
              flush=True)
    print(f"   OOD: {hit}/{len(OOD)} ({hit/len(OOD):.0%})")
    return hit, len(OOD)


if __name__ == "__main__":
    t0 = time.time()
    a = part_A()
    b = part_B()
    print(f"\n(elapsed {time.time()-t0:.0f}s)")
