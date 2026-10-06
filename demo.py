"""Phase 6 — minimal end-to-end demo.

Raw synthetic notice -> extraction (fine-tuned model, Ollama)
                     -> fund baseline resolve
                     -> deterministic rules verification
                     -> fine-tuned fraud model
                     -> reconciled verification report
                     -> approver alert (narrative agent)

Runs 5 clean + 5 fraud notices from the Phase-2 synthetic set and prints each
pipeline output plus a summary.  Everything here is synthetic.

    python demo.py                 # 5 clean + 5 fraud
    python demo.py --n 3           # 3 + 3
    python demo.py --no-model      # rules-only (skip the fraud model call)
"""

import argparse
import json
import os
import textwrap

from agents.payment_approval import draft_alert
from verification.baseline import load_baselines
from verification.pipeline import verify

CALLS = os.path.join(os.path.dirname(__file__), "synthetic_data", "output", "capital_calls.jsonl")
FRAUD_TYPES = ["altered_routing_digit", "wrong_bank_valid_checksum", "misspelled_entity_name",
               "spoofed_sender_domain", "last_minute_bank_change"]


def pick_notices(n_each):
    clean, by_type = [], {t: [] for t in FRAUD_TYPES}
    for line in open(CALLS):
        r = json.loads(line)
        if r.get("is_fraud"):
            by_type[r["fraud_type"]].append(r)
        else:
            clean.append(r)
    # clean: spread across the 4 notice formats
    seen_fmt, chosen_clean = set(), []
    for r in clean:
        if r["notice_format"] not in seen_fmt:
            chosen_clean.append(r)
            seen_fmt.add(r["notice_format"])
        if len(chosen_clean) >= n_each:
            break
    chosen_clean += clean[:max(0, n_each - len(chosen_clean))]
    # fraud: one per type, then fill
    chosen_fraud = [by_type[t][0] for t in FRAUD_TYPES][:n_each]
    i = 1
    while len(chosen_fraud) < n_each:
        chosen_fraud.append(by_type[FRAUD_TYPES[len(chosen_fraud) % 5]][i])
        i += 1
    return chosen_clean[:n_each], chosen_fraud[:n_each]


def show(rec, report, alert):
    ext = report["extracted"]
    rules = report["rules"]
    gold = rec.get("fraud_type") or "clean"
    print("=" * 78)
    print(f"NOTICE  {rec['call_id']}   format={rec['notice_format']}   GOLD={gold}")
    print("-" * 78)
    print(textwrap.indent(rec["notice_text"].strip()[:600], "  "))
    print("-" * 78)
    print(f"  extracted : {ext.get('entity')} | {ext.get('fund_name')} | "
          f"{ext.get('amount')} due {ext.get('due_date')} | bank {ext.get('bank_name')} "
          f"rt {ext.get('routing_number')}")
    print(f"  rules     : flag={rules['rules_flag']} type={rules['rules_fraud_type']} "
          f":: {'; '.join(rules['rules_reasons']) or 'no baseline mismatch'}")
    print(f"  model     : flag={report['model']['fraud_flag']} type={report['model']['fraud_type']}")
    print(f"  DECISION  : {report['decision']}  fraud={report['fraud']} "
          f"type={report['fraud_type']} confidence={report['confidence']}")
    print(f"  alert     : {alert.get('alert_text', '').splitlines()[0] if alert.get('alert_text') else alert['recommended_action']}")
    correct = (report["fraud"] == bool(rec.get("is_fraud"))) and \
              (not rec.get("is_fraud") or report["fraud_type"] == rec.get("fraud_type"))
    print(f"  >>> {'OK' if correct else 'MISMATCH'} (gold {gold})")
    return correct


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--no-model", action="store_true")
    args = ap.parse_args()

    baselines = load_baselines()
    clean, fraud = pick_notices(args.n)
    results = []
    for rec in clean + fraud:
        rep = verify(
            notice_text=rec["notice_text"],
            sender_domain=rec["sender_domain"], sender_email=rec["sender_email"],
            use_model=not args.no_model, baselines=baselines,
        ).as_dict()
        alert = draft_alert(rep)
        results.append(show(rec, rep, alert))

    print("=" * 78)
    print(f"SUMMARY: {sum(results)}/{len(results)} pipeline outputs correct "
          f"(decision + fraud_type vs gold)")


if __name__ == "__main__":
    main()
