"""Step 5 — run the 33-notice Phase-6 batch through hub -> approvals and check it.

Uses a scratch data dir so it never touches approvals/data/. Re-runs the live hub
for each notice; if Ollama is unreachable for one, falls back to that notice's
saved hub output (demo_batch/results.jsonl) and logs the fallback.
"""
import json
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from verification.baseline import load_baselines
from verification.demo_pipeline import run_pipeline
from approvals import service as A
from approvals import store
from approvals.model import ApprovalState


def _hub_outputs(scratch):
    """yield (batch_id, truth, hub_output) — live hub, saved fallback per-notice."""
    bl = load_baselines()
    batch = [json.loads(l) for l in open(os.path.join(ROOT, "demo_batch/batch.jsonl"))]
    saved = {json.loads(l)["batch_id"]: json.loads(l).get("output")
             for l in open(os.path.join(ROOT, "demo_batch/results.jsonl"))}
    fell_back = []
    t0 = time.time()
    for i, r in enumerate(batch):
        try:
            out = run_pipeline(r["notice_text"], sender_domain=r["sender_domain"],
                               sender_email=r.get("sender_email"), baselines=bl)
        except Exception as e:
            out = saved.get(r["batch_id"])
            fell_back.append((r["batch_id"], str(e)))
        print(f"  hub [{i+1:>2}/{len(batch)}] {r['batch_id']} -> "
              f"{out.get('decision') if out else 'NO OUTPUT'} "
              f"({(time.time()-t0)/(i+1):.1f}s/notice)", flush=True)
        yield r["batch_id"], r["truth"], r["truth_type"], out
    if fell_back:
        print(f"  (used saved hub output for {len(fell_back)}: {fell_back})", flush=True)


def main():
    scratch = tempfile.mkdtemp(prefix="approvals_batch_")
    try:
        store.reset(data_dir=scratch)
        records = []
        for bid, truth, ttype, out in _hub_outputs(scratch):
            assert out is not None, f"{bid}: no hub output at all"
            rec = A.ingest_pipeline_output(out, data_dir=scratch)
            records.append((bid, truth, ttype, out.get("decision"), rec))

        # -- 1. exactly one PENDING per notice, PASS included -----------------
        all_recs = A.list_all(data_dir=scratch)
        pending = A.list_pending(data_dir=scratch)
        n_pass = sum(1 for *_ , d, _ in records if d == "PASS")
        n_review = sum(1 for *_, d, _ in records if d == "REVIEW")
        n_block = sum(1 for *_, d, _ in records if d == "BLOCK")
        print("\n" + "=" * 68)
        print(f"INGEST: {len(records)} notices -> {len(all_recs)} approval records "
              f"({n_pass} from PASS, {n_review} REVIEW, {n_block} BLOCK)")
        assert len(all_recs) == len(records) == 33, "one record per notice"
        assert len(pending) == 33, "every record starts PENDING_APPROVAL (PASS included)"
        assert all(r["state"] == "PENDING_APPROVAL" for r in all_recs)
        assert n_pass >= 1, "batch must include PASS notices and they must still be pending"
        assert all(r["assigned_approver"] and r["assigned_approver"].get("email")
                   for r in all_recs), "every record has a resolved approver"
        assert all(r["verification_report_id"] for r in all_recs), "report is referenced"
        print("  OK: 33/33 PENDING_APPROVAL incl. all PASS; approver + report ref on each")

        # -- 1b. exactly one notification per new record ------------------
        notif_log = os.path.join(scratch, "notifications.log")
        lines = [l for l in open(notif_log).read().splitlines() if l.strip()] \
            if os.path.exists(notif_log) else []
        assert len(lines) == 33, f"expected 33 notification lines, got {len(lines)}"
        # records were ingested in order, so line N corresponds to records[N]
        for (bid, truth, ttype, decision, rec), line in zip(records, lines):
            appr_email = rec.assigned_approver["email"]
            assert appr_email in line, f"{bid}: approver {appr_email} missing from '{line}'"
            assert rec.approval_id in line, f"{bid}: approval id missing from notification"
            assert f"verdict={decision}" in line, \
                f"{bid}: verdict {decision} missing from '{line}'"
        assert sum(1 for l in lines if "verdict=PASS" in l) == n_pass
        assert sum(1 for l in lines if "verdict=BLOCK" in l) == n_block
        print(f"  OK: {len(lines)} notification lines, one per record, "
              f"correct approver + verdict on each ({n_pass} PASS, {n_block} BLOCK)")

        # -- 2. simulate a mix of decisions --------------------------------
        plan = {}   # bid -> (state, approver, note)
        for bid, truth, ttype, decision, rec in records:
            if bid in ("C01", "C02", "C03", "C04"):
                plan[bid] = ("APPROVED", rec.assigned_approver["email"], "matches file, cleared")
            elif bid in ("F01", "F04", "F10", "F16"):
                plan[bid] = ("REJECTED", rec.assigned_approver["email"], "confirmed bad, not paying")
            elif bid == "F13":
                plan[bid] = ("NEEDS_MORE_INFO", rec.assigned_approver["email"],
                             "asked GP to reconfirm by phone")
        decided = {}
        for bid, (state, who, note) in plan.items():
            rec = next(r for b, *_ , r in records if b == bid)
            res = A.record_decision(rec.approval_id, state, who, note, data_dir=scratch)
            decided[bid] = res
            assert res["state"] == state
            assert res["decision_by"] == who and res["decision_at"] and res["decision_note"] == note
        print(f"  OK: recorded {sum(1 for v in plan.values() if v[0]=='APPROVED')} APPROVED, "
              f"{sum(1 for v in plan.values() if v[0]=='REJECTED')} REJECTED, "
              f"{sum(1 for v in plan.values() if v[0]=='NEEDS_MORE_INFO')} NEEDS_MORE_INFO; "
              f"decision_by / decision_at / decision_note all populated")
        pending_after = A.list_pending(data_dir=scratch)
        assert len(pending_after) == 33 - len(plan), "decided records leave the pending queue"

        # -- 3. double-decide is refused, not silently overwritten ---------
        victim = decided["C01"]
        try:
            A.record_decision(victim["approval_id"], "REJECTED",
                              "someone.else@synthetic-ops.example", "trying to flip it",
                              data_dir=scratch)
            raise AssertionError("double-decide was allowed — immutability broken!")
        except A.AlreadyDecidedError as e:
            print(f"  OK: second decide on {victim['approval_id']} refused -> {e}")
        # confirm the original decision is untouched
        still = A.get_record(victim["approval_id"], data_dir=scratch)
        assert still["state"] == "APPROVED" and still["decision_by"] == plan["C01"][1]
        assert still["decision_note"] == "matches file, cleared"
        # the events log still has exactly one DECIDED for it
        evs = store.events_for(victim["approval_id"], data_dir=scratch)
        assert sum(1 for e in evs if e["event"] == "DECIDED") == 1
        print("  OK: original APPROVED decision unchanged; still exactly one DECIDED event")

        # -- 3b. reversal is a NEW record, old one untouched --------------
        rev = A.reverse_decision(decided["F01"]["approval_id"],
                                 "sam.ellery@synthetic-ops.example",
                                 "GP called back, wire instructions actually fine",
                                 data_dir=scratch)
        assert rev["approval_id"] != decided["F01"]["approval_id"]
        assert rev["supersedes"] == decided["F01"]["approval_id"]
        assert rev["state"] == "PENDING_APPROVAL"
        old = A.get_record(decided["F01"]["approval_id"], data_dir=scratch)
        assert old["state"] == "REJECTED", "reversal must NOT edit the old decision"
        assert old["superseded_by"] == [rev["approval_id"]]
        print(f"  OK: reversal opened {rev['approval_id']} (PENDING, supersedes "
              f"{decided['F01']['approval_id']}); old record still REJECTED, links forward")

        # the reversal (a fresh PENDING record) fires exactly one more notification,
        # distinguishable from the create-time line and referencing what it supersedes
        nlines = [l for l in open(notif_log).read().splitlines() if l.strip()]
        assert len(nlines) == 34, \
            f"reversal should add exactly one notification line (33 -> got {len(nlines)})"
        assert rev["approval_id"] in nlines[-1] and "NOTIFY[REVERSAL]" in nlines[-1]
        assert decided["F01"]["approval_id"] in nlines[-1], \
            "reversal notification must reference the record it supersedes"
        assert rev["assigned_approver"]["email"] in nlines[-1]
        print("  OK: reversal fired one more notification line (NOTIFY[REVERSAL], "
              "names superseded record)")

        # -- 4. no payment-execution code path anywhere in the module -----
        # (scan the module's real code; this test file itself holds the pattern
        #  strings, so it is excluded from its own scan)
        import subprocess
        pat = (r"send_payment|execute_wire|send_wire|transfer_funds|"
               r"initiate_(payment|transfer)|(ach|swift|fedwire)_(send|submit)|"
               r"pay_out|disburse|remit_funds|release_funds")
        bad = subprocess.run(
            ["grep", "-rInE", "--include=*.py", "--exclude=test_batch.py", pat,
             os.path.join(ROOT, "approvals")],
            capture_output=True, text=True)
        assert bad.returncode != 0 and not bad.stdout.strip(), \
            f"payment-execution-shaped code found in approvals/:\n{bad.stdout}"
        # also: no REJECTED / NEEDS_MORE_INFO record exposes anything actionable-as-payment
        for bid in ("F04", "F10", "F13"):
            rec = decided.get(bid) or A.get_record(
                next(r for b, *_ , r in records if b == bid).approval_id, data_dir=scratch)
            rd = A.get_record(rec["approval_id"], data_dir=scratch)
            assert set(rd.keys()) <= {
                "approval_id", "verification_report_id", "fund_id", "fund_name",
                "assigned_approver", "created_at", "hub_status", "hub_decision",
                "hub_severity", "state", "decision_by", "decision_at", "decision_note",
                "supersedes", "superseded_by", "verification_report"}, \
                f"{bid}: unexpected field on record (possible payment hook)"
        print("  OK: no send/execute/wire/disburse function anywhere in approvals/;")
        print("      REJECTED / NEEDS_MORE_INFO records carry no actionable payment field")

        # -- 5. the new case: a notice for a fund with NO baseline on file -----
        # (the 33 above are all onboarded funds; this exercises the fallback path)
        n_before = len([l for l in open(notif_log).read().splitlines() if l.strip()])
        unknown = run_pipeline(
            "From: capitalcalls@nybergstonemgmt.com\n"
            "Nybergstone Strategic Partners IV, L.P. — Capital Call Notice #3\n"
            "The General Partner calls capital of $4,250,000.00, due November 14, 2026.\n"
            "Bank: Kesterline National Bank\nABA / Routing Number: 021000089\n"
            "Account Number: 5590-8842-1173\n",
            sender_email="capitalcalls@nybergstonemgmt.com", baselines=load_baselines())
        assert unknown["status"] == "NEEDS_ONBOARDING", unknown.get("status")
        urec = A.ingest_pipeline_output(unknown, data_dir=scratch)
        assert urec.state == "PENDING_APPROVAL" and urec.hub_status == "NEEDS_ONBOARDING"
        assert urec.assigned_approver == A.ONBOARDING_REVIEW_APPROVER, \
            f"unresolved fund not routed to the review bucket: {urec.assigned_approver}"
        assert any(r["approval_id"] == urec.approval_id
                   for r in A.list_pending(data_dir=scratch)), "unknown-fund record not visible"
        nlines = [l for l in open(notif_log).read().splitlines() if l.strip()]
        assert len(nlines) == n_before + 1
        assert "NOTIFY[NEW]" in nlines[-1] and A.ONBOARDING_REVIEW_APPROVER["email"] in nlines[-1]
        # survives a decision like any other record
        d5 = A.record_decision(urec.approval_id, "REJECTED",
                               A.ONBOARDING_REVIEW_APPROVER["email"], "no baseline",
                               data_dir=scratch)
        assert d5["state"] == "REJECTED"
        print(f"  OK: unknown-fund notice -> visible PENDING record {urec.approval_id} "
              f"routed to {A.ONBOARDING_REVIEW_APPROVER['email']}, notified, decidable")

        print("=" * 68)
        print("STEP 5 PASSED")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main()
