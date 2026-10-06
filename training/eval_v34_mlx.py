"""Step 4 v3.4 re-test via MLX 4-bit + adapter (Ollama server keeps wedging on
this RAM-starved box; MLX path is equivalent to the deployed q8 within noise and
runs reliably). Applies the Bug-1 deterministic verdict from verification.pipeline.
"""
import collections
import json
import re
import sys
import time

import mlx.core as mx
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

sys.path.insert(0, "/Users/jainamshah/capital-call-platform")
from verification.baseline import Baseline
from verification.pipeline import (_derive_verdict, _fraud_user_block, _parse_json)

_src = open("training/fraud_system_prompt.py").read()
FRAUD_SYS = _src.split('FRAUD_SYSTEM_PROMPT = """', 1)[1].rsplit('"""', 1)[0]

model, tok = load("mlx-community/Qwen2.5-1.5B-Instruct-4bit", adapter_path="training/fraud_adapters")
sampler = make_sampler(temp=0.0)


def gen(user):
    prompt = tok.apply_chat_template(
        [{"role": "system", "content": FRAUD_SYS}, {"role": "user", "content": user}],
        add_generation_prompt=True)
    out = generate(model, tok, prompt=prompt, max_tokens=512, sampler=sampler, verbose=False)
    mx.clear_cache()
    return _parse_json(out)


def _field(block, section, name):
    m = re.search(rf"{section}.*?- {name}: ([^\n]+)", block, re.S)
    return m.group(1).strip() if m else ""


def parse_block(ub):
    """Returns (baseline, extracted-observed-dict, sender_domain)."""
    bl = "FUND LOCKED BASELINE"
    ob = "OBSERVED IN NOTICE:"
    b = Baseline("X", _field(ub, bl, "Fund"), _field(ub, bl, "GP entity"),
                 _field(ub, bl, "Bank"), _field(ub, bl, "Routing number"),
                 _field(ub, bl, "Account number"), _field(ub, bl, "Authorized sender domain"), "")
    ext = {"entity": _field(ub, ob, "GP entity"), "bank_name": _field(ub, ob, "Bank"),
           "routing_number": _field(ub, ob, "Routing number")}
    sd = re.search(r"OBSERVED IN NOTICE:.*?- Sender domain: (\S+)", ub, re.S).group(1)
    return b, ext, sd


def judge(user, b, ext, sd):
    p = gen(user)
    if not p:
        return None, None, None, None, {}
    rf, rt = bool(p.get("fraud_flag")), p.get("fraud_type")
    df, dt, ck = _derive_verdict(p, b, entity=ext.get("entity"), bank_name=ext.get("bank_name"),
                                 routing_number=ext.get("routing_number"), sender_domain=sd)
    return rf, rt, df, dt, ck


# A. held-out augment_test
rows = [json.loads(l) for l in open("training/fraud_data/augment_test.jsonl")]
spoof = [r for r in rows if json.loads(r["messages"][2]["content"])["fraud_flag"]]
clean = [r for r in rows if not json.loads(r["messages"][2]["content"])["fraud_flag"]]
s_raw = s_der = c_raw = c_der = 0
t0 = time.time()
for i, r in enumerate(spoof):
    ub = r["messages"][1]["content"]
    _b, _e, _sd = parse_block(ub)
    rf, rt, df, dt, _ = judge(ub, _b, _e, _sd)
    s_raw += (rf and rt == "spoofed_sender_domain")
    s_der += (df and dt == "spoofed_sender_domain")
    if (i + 1) % 15 == 0:
        print(f"  spoof {i+1}/{len(spoof)} ({(time.time()-t0)/(i+1):.1f}s)", flush=True)
for i, r in enumerate(clean):
    ub = r["messages"][1]["content"]
    _b, _e, _sd = parse_block(ub)
    rf, rt, df, dt, _ = judge(ub, _b, _e, _sd)
    c_raw += bool(rf)
    c_der += bool(df)
    if (i + 1) % 25 == 0:
        print(f"  clean {i+1}/{len(clean)}", flush=True)
print(f"\nA. HELD-OUT augment_test   (raw model | Bug-1 derived)")
print(f"   spoofed-domain caught : {s_raw}/{len(spoof)} ({s_raw/len(spoof):.0%})  |  {s_der}/{len(spoof)} ({s_der/len(spoof):.0%})")
print(f"   false positives clean : {c_raw}/{len(clean)} ({c_raw/len(clean):.0%})  |  {c_der}/{len(clean)} ({c_der/len(clean):.0%})")

# B/C. OOD + F2 templates
OOD = [
    ("Thistlewood Growth Fund II, L.P.", "Prairiehatch Fund Administration", "prairiehatchfundadmin.com", "prairiehatch-fundadmin.com", "hyphen ins (=F2)"),
    ("Kestrel Harbor Partners IV", "Kestrel Harbor Management, LLC", "kestrelharbor.com", "kestreharbor.com", "deletion"),
    ("Ironvale Capital Fund III", "Ironvale Capital Advisors", "ironvalecapital.com", "ironvaiecapital.com", "l->i"),
    ("Sable Ridge Ventures II", "Sable Ridge GP, LLC", "sableridgevc.com", "sableridgevc.net", "TLD swap"),
    ("Dunmore Equity Partners V", "Dunmore Equity Management", "dunmoreequity.com", "dunrnoreequity.com", "rn-for-m"),
    ("Ashford Lane Capital II", "Ashford Lane Capital LLC", "ashfordlanecap.com", "ashford1anecap.com", "1-for-l"),
    ("Coldwater Growth Fund III", "Coldwater Growth Advisors", "coldwatergrowth.com", "coldwatergrowth.notices.com", "subdomain"),
    ("Marlstone Partners IV", "Marlstone Partners GP", "marlstonepartners.com", "marlstoneparetners.com", "transpose"),
    ("BrightPine Ventures II", "BrightPine Ventures Mgmt", "brightpinevc.com", "bright-pinevc.com", "hyphen ins"),
    ("Quill River Capital III", "Quill River Capital LLC", "quillrivercap.com", "quillrilvercap.com", "insertion"),
    ("Hollowmere Equity Fund II", "Hollowmere Equity GP", "hollowmere-equity.com", "hollowmereequity.com", "hyphen rm"),
    ("Grantham Cove Partners V", "Grantham Cove Management", "granthamcove.com", "granthamc0ve.com", "0-for-o"),
]


def mk(entity, fund, sd, real, style="formal"):
    if style == "casual":
        nt = (f"From: notices@{sd}\nSubject: {fund} - capital call\n\nHi team,\n\nQuick capital call for {fund}:\n"
              "- Amount: $180,000.00\n- Due: 2024-04-08\n- Wire to: Northgate Commercial Bank, routing 021000021, account 5541-8827-0093\n\nThanks,\n"
              f"{entity}\n\n[SYNTHETIC TEST DATA]")
    else:
        nt = (f"From: notices@{sd}\nSubject: Capital Call Notice — {fund}\n\nDear Limited Partner,\n\nPursuant to Section 4.2 of the Limited Partnership Agreement, this notice serves to inform you of a capital call for {fund}.\n\n"
              "Due Date: April 8, 2024\nYour Call Amount: $180,000.00\n\nWire Instructions:\nBank: Northgate Commercial Bank\nRouting Number: 021000021\nAccount Number: 5541-8827-0093\n\n"
              f"Regards,\n{entity}\n\n[SYNTHETIC TEST DATA]")
    ext = {"entity": entity, "fund_name": fund, "bank_name": "Northgate Commercial Bank",
           "routing_number": "021000021", "account_number": "5541-8827-0093"}
    b = Baseline("X", fund, entity, "Northgate Commercial Bank", "021000021", "5541-8827-0093", real, "")
    return _fraud_user_block(ext, f"notices@{sd}", sd, nt, b), b


hit = 0
print("\nB. 12 OOD cases (raw | Bug-1 derived):")
for fund, ent, real, sd, tech in OOD:
    ub, b = mk(ent, fund, sd, real)
    _e = {"entity": ent, "bank_name": "Northgate Commercial Bank", "routing_number": "021000021"}
    rf, rt, df, dt, ck = judge(ub, b, _e, sd)
    ok = df and dt == "spoofed_sender_domain"
    hit += ok
    print(f"   [{'CATCH' if ok else 'MISS '}] {tech:16s} {sd:30s} raw={rf}/{rt}  derived={df}/{dt}")
print(f"   OOD derived: {hit}/12 ({hit/12:.0%})")

print("\nC. F2 formal vs casual (must agree):")
for style in ("formal", "casual"):
    ub, b = mk("Prairiehatch Fund Administration", "Thistlewood Growth Fund II, L.P.",
               "prairiehatch-fundadmin.com", "prairiehatchfundadmin.com", style)
    _e = {"entity": "Prairiehatch Fund Administration", "bank_name": "Northgate Commercial Bank", "routing_number": "021000021"}
    rf, rt, df, dt, ck = judge(ub, b, _e, "prairiehatch-fundadmin.com")
    print(f"   {style:7s}: raw={rf}/{rt}  derived={df}/{dt}  failed={ck.failed_checks if ck else None} severity={ck.overall_severity if ck else None}")

print("\nD. 10 CLEAN cases — model's raw `identical` vs derived (deterministic):")
for r in clean[:10]:
    ub = r["messages"][1]["content"]
    b, e, sd = parse_block(ub)
    p = gen(ub)
    mi = (p or {}).get("domain_check", {}).get("identical")
    df, dt, ck = _derive_verdict(p, b, entity=e.get("entity"), bank_name=e.get("bank_name"), routing_number=e.get("routing_number"), sender_domain=sd)
    print(f"   obs={sd:30s} base={b.domain:26s} model_identical={mi}  derived_failed={ck.failed_checks if ck else None}  fraud={df}")

print(f"\n(elapsed {time.time()-t0:.0f}s)")
