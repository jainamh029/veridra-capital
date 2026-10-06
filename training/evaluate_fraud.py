"""Phase 3b held-out eval for the wire-fraud model.

Reports overall fraud_flag precision/recall/F1, plus a per-fraud-type recall
breakdown and a confusion table over fraud_type (where the misses go).

Usage:
  python training/evaluate_fraud.py --model training/fraud_fused_model
  python training/evaluate_fraud.py --model mlx-community/Qwen2.5-1.5B-Instruct-4bit \
      --adapter-path training/fraud_adapters --limit 120
"""

import argparse
import json
import re
import collections

import mlx.core as mx
from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler

TYPES = [
    "altered_routing_digit", "wrong_bank_valid_checksum", "misspelled_entity_name",
    "spoofed_sender_domain", "last_minute_bank_change",
]


def parse_json_block(text):
    m = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter-path", default=None)
    ap.add_argument("--data", default="training/fraud_data/test.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=340)
    ap.add_argument("--samples", type=int, default=6)
    args = ap.parse_args()

    model, tok = load(args.model, adapter_path=args.adapter_path)
    sampler = make_sampler(temp=0.0)

    rows = [json.loads(l) for l in open(args.data)]
    if args.limit:
        rows = rows[: args.limit]
    n = len(rows)

    json_ok = 0
    tp = fp = tn = fn = 0
    type_total = collections.Counter()
    type_hit = collections.Counter()          # correct flag AND correct type
    type_flag_hit = collections.Counter()     # correct flag (type maybe wrong)
    confusion = collections.Counter()         # (gold_type -> pred_type) on fraud rows
    printed = 0

    for i, row in enumerate(rows):
        m = row["messages"]
        gold = json.loads(m[2]["content"])
        prompt = tok.apply_chat_template(
            [{"role": "system", "content": m[0]["content"]},
             {"role": "user", "content": m[1]["content"]}],
            add_generation_prompt=True,
        )
        out = generate(model, tok, prompt=prompt, max_tokens=args.max_tokens,
                       sampler=sampler, verbose=False)
        mx.clear_cache()  # MLX otherwise grows unified-memory use across many generate() calls
        pred = parse_json_block(out)

        if printed < args.samples:
            print(f"\n--- {i} gold={gold.get('fraud_flag')}/{gold.get('fraud_type')} ---")
            print("MODEL:", out.strip()[:400])
            printed += 1

        g = bool(gold.get("fraud_flag"))
        gt = gold.get("fraud_type")
        if g:
            type_total[gt] += 1

        if pred is None:
            if g:
                fn += 1
                confusion[(gt, "NO_JSON")] += 1
            else:
                fp += 0
                tn += 1
            continue
        json_ok += 1
        p = bool(pred.get("fraud_flag"))
        pt = pred.get("fraud_type")

        if g and p:
            tp += 1
            type_flag_hit[gt] += 1
            if pt == gt:
                type_hit[gt] += 1
            confusion[(gt, pt if pt else "None")] += 1
        elif g and not p:
            fn += 1
            confusion[(gt, "CLEAN")] += 1
        elif not g and p:
            fp += 1
        else:
            tn += 1

    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

    print("\n" + "=" * 64)
    print(f"held-out rows            : {n}")
    print(f"valid JSON               : {json_ok}/{n} ({json_ok/n:.1%})")
    print(f"\nfraud_flag  TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"  precision={prec:.3f}  recall={rec:.3f}  f1={f1:.3f}")
    clean_total = sum(1 for r in rows if not json.loads(r['messages'][2]['content']).get('fraud_flag'))
    print(f"  false-positive rate on clean: {fp}/{clean_total}"
          + (f" ({fp/clean_total:.1%})" if clean_total else ""))
    print("\nper-type detection (flag caught / total  |  flag+type both correct):")
    for t in TYPES:
        tot = type_total[t]
        print(f"  {t:26s} {type_flag_hit[t]}/{tot}"
              + (f" ({type_flag_hit[t]/tot:.0%})" if tot else "")
              + f"   |  {type_hit[t]}/{tot}")
    print("\nfraud_type confusion (gold -> pred), fraud rows only:")
    for (gt, pt), c in sorted(confusion.items(), key=lambda x: -x[1]):
        mark = "" if gt == pt else "  <--"
        print(f"  {gt:26s} -> {pt:26s} {c}{mark}")
    print("=" * 64)


if __name__ == "__main__":
    main()
