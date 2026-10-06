"""Phase 3 held-out sanity check.

Runs the fine-tuned model over training/data/test.jsonl (200 held-out examples,
never seen in training) and reports real numbers, not "it ran":
  - JSON validity rate
  - exact-match accuracy per extracted field
  - fraud_flag precision / recall / F1
  - fraud_type accuracy (on the records that are actually fraud)
  - a few printed sample generations (clean + fraud)

Usage:
  # adapter on top of the 4-bit base:
  python training/evaluate.py --model mlx-community/Qwen2.5-1.5B-Instruct-4bit \
      --adapter-path training/adapters
  # or a fused standalone model:
  python training/evaluate.py --model training/fused_model
"""

import argparse
import json
import os
import re

from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler

FIELDS = [
    "entity", "fund_name", "lp_name", "amount", "due_date",
    "bank_name", "routing_number", "account_number", "purpose",
]


def parse_json_block(text):
    """Model is trained to emit a bare JSON object; be lenient anyway."""
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def norm(v):
    if v is None:
        return ""
    return str(v).strip().lower().replace(",", "").replace("$", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter-path", default=None)
    ap.add_argument("--data", default="training/data/test.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--samples", type=int, default=4, help="how many generations to print")
    args = ap.parse_args()

    model, tokenizer = load(args.model, adapter_path=args.adapter_path)
    sampler = make_sampler(temp=0.0)

    rows = []
    with open(args.data) as f:
        for line in f:
            rows.append(json.loads(line))
    if args.limit:
        rows = rows[: args.limit]

    n = len(rows)
    json_ok = 0
    field_ok = {k: 0 for k in FIELDS}
    field_total = {k: 0 for k in FIELDS}
    tp = fp = tn = fn = 0
    ftype_ok = ftype_total = 0
    printed = 0

    for i, row in enumerate(rows):
        msgs = row["messages"]
        system, user = msgs[0]["content"], msgs[1]["content"]
        gold = json.loads(msgs[2]["content"])

        prompt = tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            add_generation_prompt=True,
        )
        out = generate(
            model, tokenizer, prompt=prompt, max_tokens=args.max_tokens,
            sampler=sampler, verbose=False,
        )
        pred = parse_json_block(out)

        if printed < args.samples and (i < args.samples or gold.get("fraud_flag")):
            print(f"\n--- sample {i} (gold fraud_flag={gold.get('fraud_flag')}) ---")
            print("MODEL:", out.strip()[:600])
            print("GOLD :", json.dumps(gold))
            printed += 1

        if pred is None:
            fn += 1 if gold.get("fraud_flag") else 0
            tn += 0
            continue
        json_ok += 1

        for k in FIELDS:
            if k in gold:
                field_total[k] += 1
                if norm(pred.get(k)) == norm(gold.get(k)):
                    field_ok[k] += 1

        g = bool(gold.get("fraud_flag"))
        p = bool(pred.get("fraud_flag"))
        if g and p:
            tp += 1
        elif g and not p:
            fn += 1
        elif not g and p:
            fp += 1
        else:
            tn += 1

        if g:
            ftype_total += 1
            if pred.get("fraud_type") == gold.get("fraud_type"):
                ftype_ok += 1

    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

    print("\n" + "=" * 60)
    print(f"held-out examples          : {n}")
    print(f"valid JSON emitted         : {json_ok}/{n} ({json_ok/n:.1%})")
    print("\nfield exact-match accuracy:")
    for k in FIELDS:
        t = field_total[k]
        print(f"  {k:16s} {field_ok[k]}/{t}" + (f" ({field_ok[k]/t:.1%})" if t else ""))
    print("\nfraud_flag:")
    print(f"  TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print(f"  precision={prec:.3f}  recall={rec:.3f}  f1={f1:.3f}")
    print(f"\nfraud_type accuracy (fraud rows only): {ftype_ok}/{ftype_total}"
          + (f" ({ftype_ok/ftype_total:.1%})" if ftype_total else ""))
    print("=" * 60)


if __name__ == "__main__":
    main()
