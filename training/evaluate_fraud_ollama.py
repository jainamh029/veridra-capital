"""Held-out eval of the DEPLOYED wire-fraud model (Ollama `capitalcall-fraud`, q8_0).

Same scoring as evaluate_fraud.py but hits the real serving path instead of MLX.
    python training/evaluate_fraud_ollama.py           # full 400 test rows
    python training/evaluate_fraud_ollama.py --limit 120
"""

import argparse
import collections
import json
import os
import re
import time
import urllib.request

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("CC_FRAUD_MODEL", "capitalcall-fraud")
DATA = os.path.join(os.path.dirname(__file__), "fraud_data", "test.jsonl")
TYPES = ["altered_routing_digit", "wrong_bank_valid_checksum", "misspelled_entity_name",
         "spoofed_sender_domain", "last_minute_bank_change"]


def parse_json_block(t):
    m = re.search(r"\{.*\}", t or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def ask(system, user, num_predict=400):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 2048, "num_predict": num_predict},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=body)
    return json.loads(urllib.request.urlopen(req, timeout=600).read())["message"]["content"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(DATA)]
    if args.limit:
        rows = rows[: args.limit]
    n = len(rows)

    json_ok = tp = fp = tn = fn = 0
    type_total = collections.Counter()
    type_flag_hit = collections.Counter()
    type_exact = collections.Counter()
    confusion = collections.Counter()
    t0 = time.time()

    for i, row in enumerate(rows):
        m = row["messages"]
        gold = json.loads(m[2]["content"])
        out = ask(m[0]["content"], m[1]["content"])
        pred = parse_json_block(out)

        g = bool(gold.get("fraud_flag"))
        gt = gold.get("fraud_type")
        if g:
            type_total[gt] += 1

        if pred is None:
            if g:
                fn += 1
                confusion[(gt, "NO_JSON")] += 1
            else:
                tn += 1
            continue
        json_ok += 1
        p = bool(pred.get("fraud_flag"))
        pt = pred.get("fraud_type")
        if g and p:
            tp += 1
            type_flag_hit[gt] += 1
            if pt == gt:
                type_exact[gt] += 1
            confusion[(gt, pt or "flag/no-type")] += 1
        elif g and not p:
            fn += 1
            confusion[(gt, "CLEAN")] += 1
        elif not g and p:
            fp += 1
        else:
            tn += 1

        if (i + 1) % 40 == 0:
            print(f"  ...{i+1}/{n}  ({(time.time()-t0)/(i+1):.1f}s/row)", flush=True)

    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    clean_n = sum(1 for r in rows if not json.loads(r["messages"][2]["content"]).get("fraud_flag"))

    print("\n" + "=" * 64)
    print(f"DEPLOYED FRAUD MODEL ({MODEL})  —  {n} held-out rows")
    print(f"  valid JSON            : {json_ok}/{n} ({json_ok/n:.1%})")
    print(f"  fraud_flag  TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"  precision={prec:.3f}  recall={rec:.3f}  f1={f1:.3f}")
    print(f"  false positives on clean: {fp}/{clean_n} ({fp/clean_n:.2%})")
    print("\n  per-type  (flag caught / total | flag+type exact):")
    for t in TYPES:
        tot = type_total[t]
        print(f"    {t:26s} {type_flag_hit[t]:3d}/{tot:<3d} "
              f"({(type_flag_hit[t]/tot if tot else 0):.0%})   | {type_exact[t]}/{tot}")
    print("\n  confusion (gold -> pred), fraud rows:")
    for (a, b), c in sorted(confusion.items(), key=lambda x: -x[1]):
        print(f"    {a:26s} -> {b:26s} {c}{'' if a == b else '  <--'}")
    print("=" * 64)


if __name__ == "__main__":
    main()
