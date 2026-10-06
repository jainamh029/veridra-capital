"""Step 4 — v3.4 full re-test.

'standalone model' now = model extraction + Bug-1 deterministic verdict (code
recomputes identical/first_diff from the model's echoed strings). Rules layer
bypassed. Reports RAW model flag AND derived verdict side by side.

  A. held-out augment_test (fresh domains): spoofed catch + clean FP
  B. 12 hand-built OOD cases
  C. F2 domain pair x {formal, casual} template  -> must agree
  D. 10 random clean: show derived `identical` is deterministic (not model-YES-default)
"""
import collections
import json
import re
import time
import urllib.request

from verification.baseline import Baseline
from verification.pipeline import (FRAUD_SYSTEM, _derive_verdict_from_model_strings,
                                   _fraud_user_block, _parse_json)

OLLAMA, MODEL = "http://localhost:11434", "capitalcall-fraud"


def ask_raw(user):
    body = json.dumps({"model": MODEL, "messages": [
        {"role": "system", "content": FRAUD_SYSTEM}, {"role": "user", "content": user}],
        "stream": False, "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 512}}).encode()
    return json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{OLLAMA}/api/chat", data=body), timeout=600).read())["message"]["content"].strip()


def judge(user_block, b, sender_domain):
    """Returns (raw_flag, raw_type, derived_flag, derived_type, checks)."""
    p = _parse_json(ask_raw(user_block))
    if not p:
        return None, None, None, None, {}
    raw_f, raw_t = bool(p.get("fraud_flag")), p.get("fraud_type")
    df, dt, ck = _derive_verdict_from_model_strings(p, b, sender_domain)
    return raw_f, raw_t, df, dt, ck


def block_from_row(row):
    return row["messages"][1]["content"]


# ---------------- A. held-out augment_test ----------------
def part_A():
    rows = [json.loads(l) for l in open("training/fraud_data/augment_test.jsonl")]
    spoof = [r for r in rows if json.loads(r["messages"][2]["content"])["fraud_flag"]]
    clean = [r for r in rows if not json.loads(r["messages"][2]["content"])["fraud_flag"]]
    doms = json.load(open("training/fraud_data/augment_test_domains.json"))
    dmap = {d["fund"]: d for d in doms}

    def b_for(row):
        ub = row["messages"][1]["content"]
        fund = re.search(r"- Fund: (.+)", ub).group(1)
        base_dom = re.search(r"- Authorized sender domain: (.+)", ub).group(1)
        ent = re.search(r"FUND LOCKED BASELINE.*?- GP entity: (.+)", ub, re.S).group(1)
        return Baseline("X", fund, ent, "?", "?", "?", base_dom, "")

    def obs_dom(row):
        return re.search(r"OBSERVED IN NOTICE:.*?- Sender domain: (\S+)", row["messages"][1]["content"], re.S).group(1)

    s_raw = s_der = c_raw_fp = c_der_fp = 0
    t0 = time.time()
    for i, r in enumerate(spoof):
        rf, rt, df, dt, _ = judge(block_from_row(r), b_for(r), obs_dom(r))
        s_raw += (rf and rt == "spoofed_sender_domain")
        s_der += (df and dt == "spoofed_sender_domain")
        if (i + 1) % 20 == 0:
            print(f"  spoof {i+1}/{len(spoof)} ({(time.time()-t0)/(i+1):.1f}s)", flush=True)
    for i, r in enumerate(clean):
        rf, rt, df, dt, _ = judge(block_from_row(r), b_for(r), obs_dom(r))
        c_raw_fp += bool(rf)
        c_der_fp += bool(df)
        if (i + 1) % 25 == 0:
            print(f"  clean {i+1}/{len(clean)}", flush=True)
    print(f"\nA. HELD-OUT augment_test  (raw model | Bug-1 derived)")
    print(f"   spoofed-domain caught : {s_raw}/{len(spoof)} ({s_raw/len(spoof):.0%})  |  "
          f"{s_der}/{len(spoof)} ({s_der/len(spoof):.0%})")
    print(f"   false positives clean : {c_raw_fp}/{len(clean)} ({c_raw_fp/len(clean):.0%})  |  "
          f"{c_der_fp}/{len(clean)} ({c_der_fp/len(clean):.0%})")
    return s_der, len(spoof), c_der_fp, len(clean)


# ---------------- B. 12 OOD cases ----------------
OOD = [
    ("Thistlewood Growth Fund II, L.P.", "Prairiehatch Fund Administration", "prairiehatchfundadmin.com", "prairiehatch-fundadmin.com", "hyphen ins (=F2)"),
    ("Kestrel Harbor Partners IV", "Kestrel Harbor Management, LLC", "kestrelharbor.com", "kestreharbor.com", "deletion"),
    ("Ironvale Capital Fund III", "Ironvale Capital Advisors", "ironvalecapital.com", "ironvaiecapital.com", "l->i"),
    ("Sable Ridge Ventures II", "Sable Ridge GP, LLC", "sableridgevc.com", "sableridgevc.net", "TLD swap"),
    ("Dunmore Equity Partners V", "Dunmore Equity Management", "dunmoreequity.com", "dunrnoreequity.com", "rn-for-m"),
    ("Ashford Lane Capital II", "Ashford Lane Capital LLC", "ashfordlanecap.com", "ashford1anecap.com", "1-for-l"),
    ("Coldwater Growth Fund III", "Coldwater Growth Advisors", "coldwatergrowth.com", "coldwatergrowth.notices.com", "subdomain"),
    ("Marlstone Partners IV", "Marlstone Partners GP", "marlstonepartners.com", "marlstoneparetners.com", "transposition"),
    ("BrightPine Ventures II", "BrightPine Ventures Mgmt", "brightpinevc.com", "bright-pinevc.com", "hyphen ins"),
    ("Quill River Capital III", "Quill River Capital LLC", "quillrivercap.com", "quillrilvercap.com", "insertion"),
    ("Hollowmere Equity Fund II", "Hollowmere Equity GP", "hollowmere-equity.com", "hollowmereequity.com", "hyphen rm"),
    ("Grantham Cove Partners V", "Grantham Cove Management", "granthamcove.com", "granthamc0ve.com", "0-for-o"),
]


def mk_block(entity, fund, sd, real, style="formal"):
    if style == "casual":
        nt = (f"From: notices@{sd}\nSubject: {fund} - capital call due 2024-04-08\n\nHi team,\n\n"
              f"Quick capital call notice for {fund}:\n- Amount: $180,000.00\n- Due: 2024-04-08\n"
              f"- Wire to: Northgate Commercial Bank, routing 021000021, account 5541-8827-0093\n\nThanks,\n{entity}\n\n[SYNTHETIC TEST DATA]")
    else:
        nt = (f"From: notices@{sd}\nSubject: Capital Call Notice — {fund}\n\nDear Limited Partner,\n\n"
              f"Pursuant to Section 4.2 of the Limited Partnership Agreement, this notice serves to inform you of a capital call for {fund}.\n\n"
              "Due Date: April 8, 2024\nYour Call Amount: $180,000.00\n\nWire Instructions:\n"
              "Bank: Northgate Commercial Bank\nRouting Number: 021000021\nAccount Number: 5541-8827-0093\n\n"
              f"Regards,\n{entity}\n\n[SYNTHETIC TEST DATA]")
    ext = {"entity": entity, "fund_name": fund, "bank_name": "Northgate Commercial Bank",
           "routing_number": "021000021", "account_number": "5541-8827-0093"}
    b = Baseline("X", fund, entity, "Northgate Commercial Bank", "021000021", "5541-8827-0093", real, "")
    return _fraud_user_block(ext, f"notices@{sd}", sd, nt, b), b


def part_B():
    hit = 0
    print("\nB. 12 OOD cases (Bug-1 derived verdict):")
    for fund, ent, real, sd, tech in OOD:
        ub, b = mk_block(ent, fund, sd, real)
        rf, rt, df, dt, ck = judge(ub, b, sd)
        ok = df and dt == "spoofed_sender_domain"
        hit += ok
        print(f"   [{'CATCH' if ok else 'MISS '}] {tech:16s} {sd:30s} raw={rf}/{rt}  derived={df}/{dt}")
    print(f"   OOD derived: {hit}/12 ({hit/12:.0%})")
    return hit


# ---------------- C. F2 formal vs casual ----------------
def part_C():
    print("\nC. F2 domain pair — formal vs casual template (must agree):")
    for style in ("formal", "casual"):
        ub, b = mk_block("Prairiehatch Fund Administration", "Thistlewood Growth Fund II, L.P.",
                         "prairiehatch-fundadmin.com", "prairiehatchfundadmin.com", style)
        rf, rt, df, dt, ck = judge(ub, b, "prairiehatch-fundadmin.com")
        print(f"   {style:7s}: raw={rf}/{rt}  derived={df}/{dt}  "
              f"(model domain_check echoed obs={ck.get('domain_observed')} base={ck.get('domain_baseline')})")


# ---------------- D. identical field determinism ----------------
def part_D():
    print("\nD. 10 random CLEAN cases — derived `domain_identical` (deterministic, not model-YES-default):")
    rows = [json.loads(l) for l in open("training/fraud_data/augment_test.jsonl")
            if not json.loads(json.loads(l)["messages"][2]["content"])["fraud_flag"]][:10]
    for r in rows:
        ub = r["messages"][1]["content"]
        fund = re.search(r"- Fund: (.+)", ub).group(1)
        base_dom = re.search(r"- Authorized sender domain: (.+)", ub).group(1)
        ent = re.search(r"- GP entity: (.+)", ub).group(1)
        sd = re.search(r"OBSERVED.*?- Sender domain: (\S+)", ub, re.S).group(1)
        b = Baseline("X", fund, ent, "?", "?", "?", base_dom, "")
        p = _parse_json(ask_raw(ub))
        model_ident = (p or {}).get("domain_check", {}).get("identical")
        df, dt, ck = _derive_verdict_from_model_strings(p, b, sd)
        print(f"   obs={sd:32s} base={base_dom:28s} model_says={model_ident}  derived_identical={ck.get('domain_identical')}  fraud={df}")


if __name__ == "__main__":
    t0 = time.time()
    a = part_A()
    part_C()
    part_D()
    b = part_B()
    print(f"\n(elapsed {time.time()-t0:.0f}s)")
