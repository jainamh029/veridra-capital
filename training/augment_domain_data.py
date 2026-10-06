"""Step 3 (v3.3) — domain-diversity augmentation, corrected.

v3.2 over-corrected: 2.65x spoofed over-weight + weird TLDs (.io/.fund/.capital)
correlated with fraud + a length instruction the model couldn't run -> 10-40%
false positives on clean.

v3.3 fixes:
  - realistic TLDs only (.com heavy, some .net/.org), SAME distribution for clean
    and spoofed so the TLD carries no fraud signal
  - MODERATE spoofed count (~1.4x, not 2.65x)
  - HARD CLEAN NEGATIVES: legitimate authorized domains that look unusual
    (hyphenated .com, long compound names, .net/.org) where observed == baseline
    exactly -> the model must say identical=YES
  - many distinct domains, split by company (no leakage)
  - domain_check schema: observed/baseline/first_diff_position/identical (no length fields)
"""

import json
import os
import random

from fraud_system_prompt import FRAUD_SYSTEM_PROMPT

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fraud_data")
SEED = 20260904

A = ["Kestrel", "Ironvale", "Sable", "Dunmore", "Ashford", "Coldwater", "Marlstone", "Quill",
     "Hollowmere", "Grantham", "Windrow", "Fenmore", "Aldercrest", "Barrowmere", "Thistlewood",
     "Pinehurst", "Calderwood", "Ravenscar", "Oakmarsh", "Elmsworth", "Harlow", "Cordell",
     "Bexley", "Draymoor", "Foxglove", "Greymont", "Halston", "Larkspur", "Merriman", "Norcliff",
     "Oberon", "Pemberton", "Quimby", "Redhaven", "Stanbridge", "Tolliver", "Underhill", "Vantage",
     "Westmere", "Yarrow", "Ashcombe", "Brightling", "Cranfield", "Denby", "Everly", "Fairholt",
     "Glenmara", "Hартвуд".replace("а", "a").replace("р", "r"), "Inglewood", "Jarrow", "Kingsmere",
     "Lowdham", "Marchmont", "Netherby", "Oxley", "Prescott", "Ravensworth", "Sedgwick", "Tarleton"]
B = ["Harbor", "Capital", "Ridge", "Equity", "Lane", "Growth", "Partners", "Cove", "River",
     "Peak", "Point", "Field", "Gate", "Hill", "Creek", "Bridge", "Rock", "Vale", "Grove", "Bay"]
C = ["Partners", "Fund", "Capital", "Ventures", "Group", "Holdings", "Advisors"]
ENT_SUFFIX = ["Management, LLC", "Capital Advisors", "GP, LLC", "Partners GP", "Fund Administration",
              "Management LP", "Advisors LLC", "Capital Management"]
ROMAN = ["II", "III", "IV", "V"]
# realistic, .com-heavy; SAME list used for clean and spoofed domains
TLDS = ["com"] * 8 + ["net", "org"]

TECHNIQUES = (
    ["hyphen_insert"] * 4 + ["hyphen_remove"] * 3 + ["subtle_sub"] * 4 +
    ["transpose"] * 3 + ["lookalike"] * 3 + ["tld_swap"] * 2 +
    ["deletion"] * 2 + ["insertion"] * 2 + ["subdomain"] * 2 + ["double_letter"] * 1
)
LOOKALIKE = [("m", "rn"), ("rn", "m"), ("o", "0"), ("l", "1"), ("i", "l"), ("l", "i"),
             ("w", "vv"), ("cl", "d"), ("nn", "m")]


def spaced(s):
    return " ".join(list(str(s)))


def first_diff(a, b):
    a, b = str(a), str(b)
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i + 1
    return (min(len(a), len(b)) + 1) if len(a) != len(b) else None


def word_check(obs, base):
    ow, bw = str(obs).split(), str(base).split()
    idx = None
    for i in range(min(len(ow), len(bw))):
        if ow[i].lower() != bw[i].lower():
            idx = i
            break
    if idx is None and len(ow) != len(bw):
        idx = min(len(ow), len(bw))
    return {"observed_words": ow, "baseline_words": bw,
            "mismatched_word_index": idx, "identical": "YES" if idx is None else "NO"}


def routing_check(obs, base):
    fd = first_diff(str(obs), str(base))
    return {"observed_spaced": spaced(obs), "baseline_spaced": spaced(base),
            "first_diff_position": fd, "identical": "YES" if fd is None else "NO"}


def domain_check(obs, base):
    fd = first_diff(str(obs), str(base))
    return {"observed": obs, "baseline": base, "first_diff_position": fd,
            "identical": "YES" if fd is None else "NO"}


def spoof(domain, rng, tech):
    base, tld = domain.rsplit(".", 1)
    if tech in ("hyphen_insert", "hyphen_remove"):
        if tech == "hyphen_remove" and "-" in base:
            return base.replace("-", "", 1) + "." + tld
        i = rng.randint(3, len(base) - 3)
        return base[:i] + "-" + base[i:] + "." + tld
    if tech == "subtle_sub":
        for s, r in rng.sample([("e", "a"), ("a", "e"), ("i", "e"), ("o", "e"), ("t", "d"), ("s", "z")], 6):
            if s in base:
                i = base.index(s)
                return base[:i] + r + base[i + 1:] + "." + tld
        return base[:-2] + base[-1] + base[-2] + "." + tld
    if tech == "transpose":
        cands = [i for i in range(1, len(base) - 2) if base[i] != base[i + 1]]
        i = rng.choice(cands)
        b = list(base); b[i], b[i + 1] = b[i + 1], b[i]
        return "".join(b) + "." + tld
    if tech == "lookalike":
        for s, r in rng.sample(LOOKALIKE, len(LOOKALIKE)):
            if s in base:
                return base.replace(s, r, 1) + "." + tld
        return base + "0." + tld
    if tech == "tld_swap":
        alt = rng.choice([t for t in ["com", "net", "co", "org"] if t != tld])
        return base + "." + alt
    if tech == "deletion":
        i = rng.randint(2, len(base) - 2)
        return base[:i] + base[i + 1:] + "." + tld
    if tech == "insertion":
        i = rng.randint(2, len(base) - 2)
        return base[:i] + rng.choice("abcdefghijklmnopqrstuvwxyz") + base[i:] + "." + tld
    if tech == "subdomain":
        return base + "." + rng.choice(["notices", "secure", "mail"]) + "." + tld
    if tech == "double_letter":
        i = rng.randint(2, len(base) - 2)
        return base[:i] + base[i] + base[i:] + "." + tld
    return base + "-x." + tld


def transpose_word(w, rng):
    if len(w) < 4:
        return w + w[-1]
    cands = [i for i in range(1, len(w) - 2) if w[i] != w[i + 1]]
    if not cands:
        return w[:-1] + w[-1] * 2
    i = rng.choice(cands)
    c = list(w); c[i], c[i + 1] = c[i + 1], c[i]
    return "".join(c)


def companies(rng, n):
    out, seen = [], set()
    while len(out) < n:
        name = f"{rng.choice(A)} {rng.choice(B)} {rng.choice(C)} {rng.choice(ROMAN)}"
        if name in seen:
            continue
        seen.add(name)
        w = name.replace(",", "").split()
        root = (w[0] + w[1]).lower()
        root = "".join(c for c in root if c.isalnum())
        style = rng.random()
        if style < 0.25:                       # hyphenated but legitimate
            root = w[0].lower() + "-" + w[1].lower()
        elif style < 0.4:                      # longer compound
            root = (w[0] + w[1] + rng.choice(["fund", "admin", "grp", "cap"])).lower()
        dom = f"{root}.{rng.choice(TLDS)}"
        ent = " ".join(w[:2]) + " " + rng.choice(ENT_SUFFIX)
        out.append({"fund": name + ", L.P.", "entity": ent, "domain": dom})
    return out


BANKS = ["Northgate Commercial Bank", "Silverline Bank & Trust", "Blue Harbor Bank & Trust",
         "Cornerstone National Bank", "Redwood Capital Bank", "Meridian Trust Bank",
         "Highland Ridge Bank", "Summit Peak Bank", "Lakeshore National Bank", "Ironwood Commercial Bank"]
RTS = ["021000021", "011401533", "121000248", "026009593", "071000013", "091000019", "011000015"]


_LPS = ["Kelley Ortega Endowment", "White Young Pension Fund", "Harmon Family Office",
        "Delgado University Endowment", "Rivas Group Retirement System", "Stein Foundation"]
TEMPLATES = ["formal_pdf", "casual_bullet", "fund_admin", "messy_gp"]


def notice(fund, entity, sd, bank, rt, acct, rng, style):
    """Bug-2 fix: rotate all four notice templates so spoofed-domain (and clean)
    augmentation is not concentrated in one style."""
    lp, amt = rng.choice(_LPS), "$184,500.00"
    if style == "formal_pdf":
        return (f"From: notices@{sd}\nSubject: Capital Call Notice — {fund}\n\n"
                f"Dear Limited Partner,\n\nPursuant to Section 4.2 of the Limited Partnership "
                f"Agreement, this notice serves to inform you of a capital call for {fund}.\n\n"
                f"Call Date: April 1, 2024\nDue Date: April 8, 2024\nYour Call Amount: {amt}\n"
                "Purpose: Follow-on investment\n\nWire Instructions:\n"
                f"Bank: {bank}\nRouting Number: {rt}\nAccount Number: {acct}\n\n"
                f"Regards,\n{entity}\n\n[SYNTHETIC TEST DATA]")
    if style == "casual_bullet":
        return (f"From: notices@{sd}\nSubject: {fund} - capital call due 2024-04-08\n\n"
                f"Hi {lp} team,\n\nQuick capital call notice for {fund}:\n\n"
                f"- Amount: {amt}\n- Purpose: Follow-on investment\n- Due: 2024-04-08\n"
                f"- Wire to: {bank}, routing {rt}, account {acct}\n\n"
                f"Thanks,\n{entity}\n\n[SYNTHETIC TEST DATA]")
    if style == "fund_admin":
        return (f"From: capitalcalls@{sd}\nSubject: Capital Call Notice - {fund}\n\n"
                f"This notice is being sent on behalf of {entity}, fund administrator for {fund}.\n\n"
                f"Limited Partner: {lp}\nCall Purpose: Follow-on investment\n"
                f"Call Amount Due: {amt}\nDue Date: 2024-04-08\n\n"
                f"Wire Instructions:\nBank: {bank}\nRouting #: {rt}\nAccount #: {acct}\n"
                f"Beneficiary: {entity}\n\n{entity}\nOn behalf of {fund}\n\n[SYNTHETIC TEST DATA]")
    return (f"From: notices@{sd}\nSubject: {fund} capital call - please wire\n\n"
            f"hi {lp},\n\nneed you to wire {amt} by 2024-04-08 for capital call, follow-on investment\n"
            f"this is for {fund}.\n\nbank is {bank}\nrouting {rt}\nacct {acct}\n\n"
            f"let me know once sent, thx\n{entity}\n\n[SYNTHETIC TEST DATA]")


def make_row(rec_entity, fund, bank, rt, acct, sender_domain, b_entity, b_domain,
             is_fraud, ftype, reason, rng, style):
    target = {
        "entity_check": word_check(rec_entity, b_entity),
        "bank_check": word_check(bank, bank),
        "routing_check": routing_check(rt, rt),
        "domain_check": domain_check(sender_domain, b_domain),
        "bank_change_announced": False,
        "fraud_flag": is_fraud,
        "fraud_type": ftype,
        "reason": reason,
    }
    user = (
        "FUND LOCKED BASELINE (trusted, from onboarding):\n"
        f"- GP entity: {b_entity}\n- Fund: {fund}\n- Bank: {bank}\n"
        f"- Routing number: {rt}\n- Account number: {acct}\n"
        f"- Authorized sender domain: {b_domain}\n\n"
        "OBSERVED IN NOTICE:\n"
        f"- GP entity: {rec_entity}\n- Fund: {fund}\n- Bank: {bank}\n"
        f"- Routing number: {rt}\n- Account number: {acct}\n"
        f"- Sender email: notices@{sender_domain}\n- Sender domain: {sender_domain}\n\n"
        f"CAPITAL CALL NOTICE:\n{notice(fund, rec_entity, sender_domain, bank, rt, acct, rng, style)}"
    )
    return {"messages": [
        {"role": "system", "content": FRAUD_SYSTEM_PROMPT},
        {"role": "user", "content": user},
        {"role": "assistant", "content": json.dumps(target)},
    ]}


def build_for_company(co, rng):
    ent, fund, dom = co["entity"], co["fund"], co["domain"]
    bank, rt = rng.choice(BANKS), rng.choice(RTS)
    acct = f"{rng.randint(1000,9999)}-{rng.randint(1000,9999)}-{rng.randint(1000,9999)}"
    clean, spoofed = [], []
    # ~4 clean per company (hard negatives: unusual-but-matching domains), 1 per template
    for style in TEMPLATES:
        clean.append(make_row(ent, fund, bank, rt, acct, dom, ent, dom, False, None,
                              "all four fields match the locked baseline", rng, style))
    # ~1.5 spoofed per company (v3.4: 1.5x ratio, down from v3.3 1.8x), template rotated
    for style in rng.sample(TEMPLATES, 2 if rng.random() < 0.5 else 1):
        tech = rng.choice(TECHNIQUES)
        sd = spoof(dom, rng, tech)
        if sd == dom:
            sd = dom.rsplit(".", 1)[0] + "1." + dom.rsplit(".", 1)[1]
        combined = rng.random() < 0.2
        obs_ent = " ".join(transpose_word(w, rng) if i == 0 else w
                           for i, w in enumerate(ent.split())) if combined else ent
        reason = (f"Sender domain '{sd}' is a look-alike of the fund's authorized domain '{dom}'"
                  + ("; the GP entity name is also misspelled." if combined else "."))
        spoofed.append(make_row(obs_ent, fund, bank, rt, acct, sd, ent, dom, True,
                                "spoofed_sender_domain", reason, rng, style))
    return clean, spoofed


def main():
    rng = random.Random(SEED)
    cos = companies(rng, 230)
    rng.shuffle(cos)
    splits = {"train": cos[:180], "valid": cos[180:205], "test": cos[205:230]}
    for split, colist in splits.items():
        clean_rows, spoof_rows = [], []
        for co in colist:
            c, s = build_for_company(co, rng)
            clean_rows += c
            spoof_rows += s
        rows = clean_rows + spoof_rows
        rng.shuffle(rows)
        with open(os.path.join(OUT_DIR, f"augment_{split}.jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        print(f"{split}: {len(rows)} rows ({len(clean_rows)} clean + {len(spoof_rows)} spoofed) "
              f"over {len(colist)} companies")
    with open(os.path.join(OUT_DIR, "augment_test_domains.json"), "w") as f:
        json.dump([{"fund": c["fund"], "entity": c["entity"], "domain": c["domain"]}
                   for c in splits["test"]], f, indent=2)
    print("distinct train domains:", len({c["domain"] for c in splits["train"]}))
    import collections
    tl = collections.Counter(c["domain"].rsplit(".", 1)[1] for c in splits["train"])
    print("train domain TLDs:", dict(tl))


if __name__ == "__main__":
    main()
