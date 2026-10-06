"""Phase 3b wire-fraud training set (v3.1).

Per-field comparison targets, deterministic from Phase-2 ground truth:
  entity/bank : word-split, mismatched_word_index
  routing     : character-spaced digits, first_diff_position
  domain      : plain strings, lengths, first_diff_position
"""

import json
import os
import random

from fraud_system_prompt import FRAUD_SYSTEM_PROMPT

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS = os.path.join(REPO_ROOT, "synthetic_data", "output", "capital_calls.jsonl")
FUNDS = os.path.join(REPO_ROOT, "synthetic_data", "output", "funds.json")
OUT_DIR = os.path.join(REPO_ROOT, "training", "fraud_data")

SEED = 20260902
FRAUD_TYPES = [
    "altered_routing_digit", "wrong_bank_valid_checksum", "misspelled_entity_name",
    "spoofed_sender_domain", "last_minute_bank_change",
]
# All types capped so valid+test keep a full 40-45/type held out (smallest pool ~434).
# v3.3: fewer in-distribution spoofed rows from the 10-fund pool; the augmentation
# supplies the diverse-domain spoofed + hard-clean-negative rows instead.
TRAIN_PER_TYPE = {"spoofed_sender_domain": 230}
TRAIN_DEFAULT = 340
SPLIT_COUNTS = {"train": (1700, None), "valid": (250, 45), "test": (200, 40)}


def load_funds():
    raw = json.load(open(FUNDS))
    funds = raw if isinstance(raw, list) else list(raw.values())
    return {f["fund_id"]: f for f in funds}


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
    obs, base = str(obs), str(base)
    fd = first_diff(obs, base)
    return {"observed_spaced": spaced(obs), "baseline_spaced": spaced(base),
            "first_diff_position": fd, "identical": "YES" if fd is None else "NO"}


def domain_check(obs, base):  # v3.3: no length fields (see fraud_system_prompt.py)
    obs, base = str(obs), str(base)
    fd = first_diff(obs, base)
    return {"observed": obs, "baseline": base, "first_diff_position": fd,
            "identical": "YES" if fd is None else "NO"}


def build_target(rec, fund):
    is_fraud = bool(rec.get("is_fraud"))
    ftype = rec["fraud_type"] if is_fraud else None
    if is_fraud:
        reason = (rec.get("fraud_reasoning") or "").split("\n")[0].strip()
        reason = reason[:237] + "..." if len(reason) > 240 else reason
    else:
        reason = "all four fields match the locked baseline"
    return {
        "entity_check": word_check(rec["gp_entity_name"], fund["gp_entity_name"]),
        "bank_check": word_check(rec["bank_name"], fund["baseline_bank_name"]),
        "routing_check": routing_check(rec["routing_number"], fund["baseline_routing_number"]),
        "domain_check": domain_check(rec["sender_domain"], fund["domain"]),
        "bank_change_announced": ftype == "last_minute_bank_change",
        "fraud_flag": is_fraud,
        "fraud_type": ftype,
        "reason": reason,
    }


def baseline_block(f):
    return (
        "FUND LOCKED BASELINE (trusted, from onboarding):\n"
        f"- GP entity: {f['gp_entity_name']}\n- Fund: {f['fund_name']}\n"
        f"- Bank: {f['baseline_bank_name']}\n- Routing number: {f['baseline_routing_number']}\n"
        f"- Account number: {f['baseline_account_number']}\n"
        f"- Authorized sender domain: {f['domain']}"
    )


def observed_block(r):
    return (
        "OBSERVED IN NOTICE:\n"
        f"- GP entity: {r['gp_entity_name']}\n- Fund: {r['fund_name']}\n- Bank: {r['bank_name']}\n"
        f"- Routing number: {r['routing_number']}\n- Account number: {r['account_number']}\n"
        f"- Sender email: {r['sender_email']}\n- Sender domain: {r['sender_domain']}"
    )


def to_example(rec, fund):
    user = (baseline_block(fund) + "\n\n" + observed_block(rec) + "\n\n"
            "CAPITAL CALL NOTICE:\n" + rec["notice_text"].strip())
    return {"messages": [
        {"role": "system", "content": FRAUD_SYSTEM_PROMPT},
        {"role": "user", "content": user},
        {"role": "assistant", "content": json.dumps(build_target(rec, fund))},
    ]}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = random.Random(SEED)
    funds = load_funds()
    clean, by_type = [], {t: [] for t in FRAUD_TYPES}
    for line in open(CALLS):
        r = json.loads(line)
        (by_type[r["fraud_type"]] if r.get("is_fraud") else clean).append(r)
    rng.shuffle(clean)
    for t in FRAUD_TYPES:
        rng.shuffle(by_type[t])

    ci, ti = 0, {t: 0 for t in FRAUD_TYPES}
    for split, (cn, fn) in SPLIT_COUNTS.items():
        rows = [to_example(r, funds[r["fund_id"]]) for r in clean[ci:ci + cn]]
        ci += cn
        for t in FRAUD_TYPES:
            k = (TRAIN_PER_TYPE.get(t, TRAIN_DEFAULT) if split == "train" else fn)
            for r in by_type[t][ti[t]:ti[t] + k]:
                rows.append(to_example(r, funds[r["fund_id"]]))
            ti[t] += k
        rng.shuffle(rows)
        with open(os.path.join(OUT_DIR, f"{split}.jsonl"), "w") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
        print(f"{split}: {len(rows)} rows")
    print(f"clean used {ci}/{len(clean)}")
    for t in FRAUD_TYPES:
        print(f"  {t}: {ti[t]}/{len(by_type[t])}")


if __name__ == "__main__":
    main()
