"""Step 1 — assemble a leak-free 33-notice demo batch from the Phase-2 synthetic
dataset (synthetic_data/output/capital_calls.jsonl).

Excludes every call_id consumed by:
  - the extraction model  (training/data/split_call_ids.json)
  - the v3.4 wire-fraud model  (replay prepare_fraud_data.py's deterministic sampling)

Batch: 15 clean (4 templates x >=4 funds) + 18 fraud:
  3x altered_routing_digit, 3x wrong_bank_valid_checksum, 3x spoofed_sender_domain,
  3x misspelled_entity_name, 3x last_minute_bank_change,
  3x combined_domain_entity  (synthesised here: a clean unseen notice with BOTH a
     domain typosquat and an entity-name typo injected — Phase 2 has no combined
     attacks; these are clearly flagged synthetic="derived_combined").

Ground truth is written to demo_batch/batch.jsonl and demo_batch/ground_truth.csv.
"""
import csv
import json
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS = os.path.join(ROOT, "synthetic_data", "output", "capital_calls.jsonl")
OUT = os.path.join(ROOT, "demo_batch")
os.makedirs(OUT, exist_ok=True)

FRAUD_TYPES = ["altered_routing_digit", "wrong_bank_valid_checksum",
               "misspelled_entity_name", "spoofed_sender_domain", "last_minute_bank_change"]


def fraud_model_consumed_ids():
    """Replay training/prepare_fraud_data.py sampling (SEED=20260902) exactly."""
    SEED = 20260902
    TRAIN_PER_TYPE = {"spoofed_sender_domain": 230}
    TRAIN_DEFAULT = 340
    SPLIT_COUNTS = {"train": (1700, None), "valid": (250, 45), "test": (200, 40)}
    rng = random.Random(SEED)
    clean, by_type = [], {t: [] for t in FRAUD_TYPES}
    for line in open(CALLS):
        r = json.loads(line)
        (by_type[r["fraud_type"]] if r.get("is_fraud") else clean).append(r)
    rng.shuffle(clean)
    for t in FRAUD_TYPES:
        rng.shuffle(by_type[t])
    consumed = set()
    ci, ti = 0, {t: 0 for t in FRAUD_TYPES}
    for split, (cn, fn) in SPLIT_COUNTS.items():
        for r in clean[ci:ci + cn]:
            consumed.add(r["call_id"])
        ci += cn
        for t in FRAUD_TYPES:
            k = (TRAIN_PER_TYPE.get(t, TRAIN_DEFAULT) if split == "train" else fn)
            for r in by_type[t][ti[t]:ti[t] + k]:
                consumed.add(r["call_id"])
            ti[t] += k
    return consumed


def spoof_domain(dom):
    base, tld = dom.rsplit(".", 1)
    i = max(3, len(base) // 2)
    return base[:i] + "-" + base[i:] + "." + tld          # hyphen insertion


def typo_entity(name):
    w = name.split()
    if len(w[0]) >= 5:
        w[0] = w[0][:2] + w[0][3] + w[0][2] + w[0][4:]     # transpose chars 3-4
    return " ".join(w)


def main():
    excl = fraud_model_consumed_ids()
    excl |= set(sum(json.load(open(os.path.join(ROOT, "training", "data",
                                                "split_call_ids.json"))).values(), []))
    print(f"excluded call_ids: {len(excl)} "
          f"(fraud-model + extraction-model training/eval)")

    rng = random.Random(20260902)
    recs = [json.loads(l) for l in open(CALLS)]
    pool = [r for r in recs if r["call_id"] not in excl]
    rng.shuffle(pool)
    clean_pool = [r for r in pool if not r.get("is_fraud")]
    fraud_pool = {t: [r for r in pool if r.get("fraud_type") == t] for t in FRAUD_TYPES}

    batch = []

    # --- 15 clean: cover all 4 templates and >=4 funds ---
    fmts = ["formal_pdf_style", "casual_bullet_email", "fund_admin_email", "messy_gp_email"]
    picked, used_funds = [], set()
    # first pass: 1 per (template, distinct fund) until >=4 funds and all templates covered
    for fmt in fmts:
        for r in clean_pool:
            if r["notice_format"] == fmt and r["fund_id"] not in used_funds:
                picked.append(r); used_funds.add(r["fund_id"]); break
    # fill to 15, rotating templates
    fi = 0
    for r in clean_pool:
        if len(picked) >= 15:
            break
        if r in picked:
            continue
        if r["notice_format"] == fmts[fi % 4]:
            picked.append(r); fi += 1
    for r in picked[:15]:
        batch.append({"batch_id": f"C{len([b for b in batch if b['truth']=='clean'])+1:02d}",
                      "truth": "clean", "truth_type": "", "call_id": r["call_id"],
                      "fund_id": r["fund_id"], "notice_format": r["notice_format"],
                      "sender_domain": r["sender_domain"], "notice_text": r["notice_text"],
                      "synthetic": "phase2"})

    # --- 15 single-type fraud: 3 each ---
    for t in FRAUD_TYPES:
        for r in fraud_pool[t][:3]:
            batch.append({"batch_id": f"F{len([b for b in batch if b['truth']=='fraud'])+1:02d}",
                          "truth": "fraud", "truth_type": t, "call_id": r["call_id"],
                          "fund_id": r["fund_id"], "notice_format": r["notice_format"],
                          "sender_domain": r["sender_domain"], "notice_text": r["notice_text"],
                          "synthetic": "phase2"})

    # --- 3 combined domain+entity attacks (derived from unseen clean notices) ---
    combos = [r for r in clean_pool if r["call_id"] not in {b["call_id"] for b in batch}][:3]
    for r in combos:
        real_dom = r["sender_domain"]
        bad_dom = spoof_domain(real_dom)
        bad_ent = typo_entity(r["gp_entity_name"])
        nt = r["notice_text"]
        nt = nt.replace(real_dom, bad_dom).replace(r["gp_entity_name"], bad_ent)
        batch.append({"batch_id": f"F{len([b for b in batch if b['truth']=='fraud'])+1:02d}",
                      "truth": "fraud", "truth_type": "combined_domain_entity",
                      "call_id": r["call_id"] + "-COMBO", "fund_id": r["fund_id"],
                      "notice_format": r["notice_format"], "sender_domain": bad_dom,
                      "notice_text": nt, "synthetic": "derived_combined"})

    with open(os.path.join(OUT, "batch.jsonl"), "w") as f:
        for b in batch:
            f.write(json.dumps(b) + "\n")
    with open(os.path.join(OUT, "ground_truth.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["batch_id", "truth", "truth_type", "call_id", "fund_id",
                    "notice_format", "synthetic"])
        for b in batch:
            w.writerow([b["batch_id"], b["truth"], b["truth_type"], b["call_id"],
                        b["fund_id"], b["notice_format"], b["synthetic"]])

    import collections
    print(f"\nbatch: {len(batch)} notices")
    print("  truth:", dict(collections.Counter(b["truth"] for b in batch)))
    print("  fraud types:", dict(collections.Counter(b["truth_type"] for b in batch if b["truth"] == "fraud")))
    print("  clean templates:", dict(collections.Counter(b["notice_format"] for b in batch if b["truth"] == "clean")))
    print("  clean funds:", sorted({b["fund_id"] for b in batch if b["truth"] == "clean"}))
    print("  any excluded id leaked in?:",
          any(b["call_id"].replace("-COMBO", "") in excl for b in batch))


if __name__ == "__main__":
    main()
