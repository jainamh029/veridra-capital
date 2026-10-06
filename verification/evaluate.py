"""Phase 4 mandatory eval: run the deterministic rules layer over the FULL
Phase 2 synthetic set (~32k records) and report precision / recall / per-type
recall / false-positive rate on clean.

Rules are fed the record's already-parsed fields (entity, bank, routing, domain)
- i.e. the test assumes correct extraction (separately measured at 99.5-100% in
Phase 3) and isolates the rules layer itself.

  python -m verification.evaluate                 # rules only, all records
  python -m verification.evaluate --sample 400 --with-model   # + reconcile the Ollama model
"""

import argparse
import collections
import json
import os

from .baseline import load_baselines
from .report import build_report
from .rules import run_rules

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALLS = os.path.join(REPO_ROOT, "synthetic_data", "output", "capital_calls.jsonl")
TYPES = [
    "altered_routing_digit", "wrong_bank_valid_checksum", "misspelled_entity_name",
    "spoofed_sender_domain", "last_minute_bank_change",
]


def rules_for_record(r, baselines):
    b = baselines[r["fund_id"]]
    return run_rules(
        entity=r["gp_entity_name"],
        bank_name=r["bank_name"],
        routing_number=str(r["routing_number"]),
        account_number=str(r["account_number"]),
        sender_domain=r["sender_domain"],
        notice_text=r["notice_text"],
        baseline=b,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="0 = all records")
    ap.add_argument("--with-model", action="store_true",
                    help="also query the Ollama fraud model and score the reconciled decision")
    args = ap.parse_args()

    baselines = load_baselines()
    rows = [json.loads(l) for l in open(CALLS)]
    if args.sample:
        # deterministic stratified sample: keep all fraud up to sample/2, fill with clean
        fraud = [r for r in rows if r.get("is_fraud")][: args.sample // 2]
        clean = [r for r in rows if not r.get("is_fraud")][: args.sample - len(fraud)]
        rows = fraud + clean

    n = len(rows)
    tp = fp = tn = fn = 0
    type_total = collections.Counter()
    type_hit = collections.Counter()        # flag caught
    type_exact = collections.Counter()      # flag + type both right
    confusion = collections.Counter()

    m_tp = m_fp = m_tn = m_fn = 0
    model = None
    if args.with_model:
        from . import pipeline
        model = pipeline

    for i, r in enumerate(rows):
        gold = bool(r.get("is_fraud"))
        gtype = r.get("fraud_type")
        rr = rules_for_record(r, baselines)

        if gold:
            type_total[gtype] += 1
        if gold and rr.flag:
            tp += 1
            type_hit[gtype] += 1
            if rr.fraud_type == gtype:
                type_exact[gtype] += 1
            confusion[(gtype, rr.fraud_type or "flagged/no-type")] += 1
        elif gold and not rr.flag:
            fn += 1
            confusion[(gtype, "MISSED")] += 1
        elif not gold and rr.flag:
            fp += 1
        else:
            tn += 1

        if model is not None:
            b = baselines[r["fund_id"]]
            try:
                mf, mt = model.model_fraud_flag(
                    {"entity": r["gp_entity_name"], "fund_name": r["fund_name"],
                     "bank_name": r["bank_name"], "routing_number": str(r["routing_number"]),
                     "account_number": str(r["account_number"])},
                    r["sender_email"], r["sender_domain"], r["notice_text"], b,
                )
            except Exception:
                mf, mt = None, None
            rep = build_report(fund_id=b.fund_id, extracted={}, rules_result=rr,
                               model_flag=mf, model_fraud_type=mt)
            combined = rep.fraud
            if gold and combined:
                m_tp += 1
            elif gold and not combined:
                m_fn += 1
            elif not gold and combined:
                m_fp += 1
            else:
                m_tn += 1
            if (i + 1) % 50 == 0:
                print(f"  ...{i + 1}/{n}")

    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * rc / (p + rc) if p + rc else 0.0
        return p, rc, f

    p, rc, f = prf(tp, fp, fn)
    clean_n = sum(1 for r in rows if not r.get("is_fraud"))
    print("\n" + "=" * 66)
    print(f"RULES LAYER — {n} records ({clean_n} clean, {n - clean_n} fraud)")
    print(f"  TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"  precision={p:.4f}  recall={rc:.4f}  f1={f:.4f}")
    print(f"  false-positive rate on clean: {fp}/{clean_n} ({fp / clean_n:.3%})")
    print("\n  per-type  (flag caught / total | flag+type exact):")
    for t in TYPES:
        tot = type_total[t]
        print(f"    {t:26s} {type_hit[t]:4d}/{tot:<4d} ({(type_hit[t]/tot if tot else 0):.1%})"
              f"   | {type_exact[t]}/{tot}")
    print("\n  fraud_type confusion (gold -> rules), fraud rows:")
    for (g, pt), cnt in sorted(confusion.items(), key=lambda x: -x[1]):
        mark = "" if g == pt else "  <--"
        print(f"    {g:26s} -> {pt:26s} {cnt}{mark}")

    if model is not None:
        mp, mr, mf1 = prf(m_tp, m_fp, m_fn)
        print("\n" + "-" * 66)
        print(f"RECONCILED (rules OR model) — {n} records")
        print(f"  TP={m_tp} FP={m_fp} TN={m_tn} FN={m_fn}")
        print(f"  precision={mp:.4f}  recall={mr:.4f}  f1={mf1:.4f}")
        print(f"  false-positive rate on clean: {m_fp}/{clean_n} ({m_fp / clean_n:.3%})")
    print("=" * 66)


if __name__ == "__main__":
    main()
