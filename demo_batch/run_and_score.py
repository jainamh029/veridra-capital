"""Step 3 — run the leak-free batch through the single entry point and score it.

Writes demo_batch/results.jsonl (full decision object per notice) and prints
precision / recall / F1 for fraud detection, a per-fraud-type breakdown, the
clean-subset false-positive rate, and an alert-text spot-check.
"""
import collections
import json
import os
import time
import traceback

from verification.baseline import load_baselines
from verification.demo_pipeline import run_pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
BATCH = os.path.join(HERE, "batch.jsonl")
RESULTS = os.path.join(HERE, "results.jsonl")

# which failed-check names (canonical, post Phase-6c) legitimately explain each type
EXPECTED_CHECKS = {
    "altered_routing_digit": {"routing_checksum", "baseline_routing_match"},
    "wrong_bank_valid_checksum": {"baseline_bank_match", "baseline_routing_match"},
    "misspelled_entity_name": {"entity_name_match"},
    "spoofed_sender_domain": {"sender_domain_match"},
    "last_minute_bank_change": {"baseline_bank_match", "bank_change_language", "baseline_routing_match"},
    "combined_domain_entity": {"sender_domain_match", "entity_name_match"},
}


def main():
    bl = load_baselines()
    rows = [json.loads(l) for l in open(BATCH)]
    results, errors = [], []
    t0 = time.time()
    with open(RESULTS, "w") as fh:
        for i, r in enumerate(rows):
            rec = {"batch_id": r["batch_id"], "truth": r["truth"],
                   "truth_type": r["truth_type"], "call_id": r["call_id"]}
            try:
                out = run_pipeline(r["notice_text"], sender_domain=r["sender_domain"],
                                   sender_email=r.get("sender_email"), baselines=bl)
                rec["output"] = out
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"
                rec["traceback"] = traceback.format_exc()
                errors.append((r["batch_id"], rec["error"]))
            fh.write(json.dumps(rec) + "\n")
            results.append(rec)
            print(f"  [{i+1:>2}/{len(rows)}] {r['batch_id']} truth={r['truth']}/{r['truth_type'] or '-'} "
                  f"-> {rec.get('output', {}).get('decision', rec.get('error', '?'))} "
                  f"({(time.time()-t0)/(i+1):.1f}s/notice)", flush=True)

    # ---- scoring ----
    def flagged(rec):
        d = rec.get("output", {}).get("decision")
        return d in ("BLOCK", "REVIEW")

    scored = [r for r in results if "output" in r]
    tp = sum(1 for r in scored if r["truth"] == "fraud" and flagged(r))
    fn = sum(1 for r in scored if r["truth"] == "fraud" and not flagged(r))
    fp = sum(1 for r in scored if r["truth"] == "clean" and flagged(r))
    tn = sum(1 for r in scored if r["truth"] == "clean" and not flagged(r))
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec_ = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec_ / (prec + rec_) if (prec + rec_) else 0.0
    clean_n = sum(1 for r in scored if r["truth"] == "clean")

    print("\n" + "=" * 70)
    print(f"BATCH: {len(rows)} notices ({sum(1 for r in rows if r['truth']=='clean')} clean, "
          f"{sum(1 for r in rows if r['truth']=='fraud')} fraud), {len(errors)} pipeline errors")
    print(f"\nFRAUD DETECTION (flag = BLOCK or REVIEW):")
    print(f"  TP={tp} FP={fp} TN={tn} FN={fn}")
    print(f"  precision = {prec:.3f}")
    print(f"  recall    = {rec_:.3f}")
    print(f"  F1        = {f1:.3f}")
    print(f"  FALSE-POSITIVE RATE ON CLEAN = {fp}/{clean_n} ({fp/clean_n:.1%})")

    print(f"\nPER FRAUD TYPE (flagged / total | primary-label match | severity):")
    by = collections.defaultdict(list)
    for r in scored:
        if r["truth"] == "fraud":
            by[r["truth_type"]].append(r)
    # for the combined type, "correct" = BOTH sub-labels appear in fraud_labels
    SUBLABELS = {"combined_domain_entity": {"spoofed_sender_domain", "misspelled_entity_name"}}
    for t, rs in by.items():
        fl = sum(1 for r in rs if flagged(r))
        if t in SUBLABELS:
            ok = sum(1 for r in rs
                     if SUBLABELS[t] <= set(r["output"].get("fraud_labels", [])))
            note = f"{ok}/{len(rs)} name BOTH sub-labels"
        else:
            ok = sum(1 for r in rs if r["output"].get("fraud_type") == t)
            note = f"{ok}/{len(rs)} primary-label = {t}"
        sev = collections.Counter(r["output"].get("overall_severity") for r in rs if flagged(r))
        print(f"  {t:26s} {fl}/{len(rs)} flagged | {note} | severity: {dict(sev)}")

    print(f"\nALERT SPOT-CHECK (alert names ALL checks that explain the fraud, at correct severity):")
    for r in scored:
        if r["truth"] != "fraud" or not flagged(r):
            continue
        al = r["output"].get("alert") or {}
        failed = set(al.get("failed_checks", []))
        exp = EXPECTED_CHECKS.get(r["truth_type"], set())
        names_all = exp <= failed
        sev = r["output"].get("overall_severity")
        sev_ok = (r["truth_type"] != "combined_domain_entity") or sev == "high"
        ok = names_all and sev_ok
        print(f"  {r['batch_id']} {r['truth_type']:24s} sev={sev:6s} failed={sorted(failed)}  -> "
              f"{'OK' if ok else 'PROBLEM'}")

    print(f"\nCLEAN CASES flagged as fraud (false positives):")
    fpcs = [r for r in scored if r["truth"] == "clean" and flagged(r)]
    if not fpcs:
        print("  none")
    for r in fpcs:
        al = r["output"].get("alert") or {}
        print(f"  {r['batch_id']} decision={r['output']['decision']} "
              f"type={r['output'].get('fraud_type')} failed={al.get('failed_checks')}")

    if errors:
        print(f"\nPIPELINE ERRORS ({len(errors)}):")
        for bid, e in errors:
            print(f"  {bid}: {e}")
    print("=" * 70)


if __name__ == "__main__":
    main()
