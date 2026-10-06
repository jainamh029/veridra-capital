"""Internal-consistency checks on the generated synthetic dataset. Run after
run_pipeline.py and before moving on to Phase 3. Exits non-zero if any check
fails so it can be used as a gate.
"""

import json
import os
import sys

import pandas as pd

from . import config


def load_outputs():
    out = config.OUTPUT_DIR
    with open(os.path.join(out, "funds.json")) as f:
        funds = json.load(f)
    calls_df = pd.read_csv(os.path.join(out, "capital_calls.csv"))
    gl_df = pd.read_csv(os.path.join(out, "gl_transactions.csv"))
    balances_df = pd.read_csv(os.path.join(out, "cash_balances_daily.csv"))
    return funds, calls_df, gl_df, balances_df


def check_no_duplicate_call_ids(calls_df, failures):
    dupes = calls_df["call_id"].duplicated().sum()
    if dupes:
        failures.append(f"{dupes} duplicate call_id values in capital_calls.csv")


def check_due_date_after_call_date(calls_df, failures):
    bad = (pd.to_datetime(calls_df["due_date"]) < pd.to_datetime(calls_df["call_date"])).sum()
    if bad:
        failures.append(f"{bad} records with due_date before call_date")


def check_dates_within_window(calls_df, failures):
    lo, hi = pd.Timestamp(config.SIM_START), pd.Timestamp(config.SIM_END)
    bad = (
        (pd.to_datetime(calls_df["call_date"]) < lo)
        | (pd.to_datetime(calls_df["call_date"]) > hi)
    ).sum()
    if bad:
        failures.append(f"{bad} records with call_date outside the simulation window")


def check_capital_calls_reconcile_to_ledger(funds, calls_df, gl_df, failures):
    contributions = gl_df[gl_df["account_code"] == 3001].groupby("fund_id")["amount"].sum()
    called = calls_df.groupby("fund_id")["amount"].sum()
    for fund in funds:
        fid = fund["fund_id"]
        called_total = called.get(fid, 0.0)
        received_total = contributions.get(fid, 0.0)
        diff = abs(called_total - received_total)
        if diff > 1.0:  # allow a few cents of rounding drift across thousands of records
            failures.append(
                f"{fid}: capital calls summed ({called_total:,.2f}) do not reconcile "
                f"with GL capital-contribution postings ({received_total:,.2f}), diff {diff:,.2f}"
            )


def check_balances_never_negative(balances_df, failures):
    neg = balances_df[balances_df["cash_balance"] < -0.01]
    if len(neg):
        failures.append(f"{len(neg)} daily balance rows go negative "
                         f"(min={balances_df['cash_balance'].min():,.2f}) — not modeled as intentional")


def check_fraud_records_differ_from_baseline(funds, calls_df, failures):
    fund_baseline = {f["fund_id"]: f for f in funds}
    fraud_rows = calls_df[calls_df["is_fraud"]]
    mismatches = 0
    for _, row in fraud_rows.iterrows():
        base = fund_baseline[row["fund_id"]]
        fraud_type = row["fraud_type"]
        if fraud_type in ("altered_routing_digit", "wrong_bank_valid_checksum", "last_minute_bank_change"):
            differs = (
                row["bank_name"] != base["baseline_bank_name"]
                or row["routing_number"] != int(base["baseline_routing_number"])
                or row["account_number"] != int(base["baseline_account_number"])
            )
        elif fraud_type == "misspelled_entity_name":
            differs = row["gp_entity_name"] != base["gp_entity_name"]
        elif fraud_type == "spoofed_sender_domain":
            differs = row["sender_domain"] != base["domain"]
        else:
            differs = False
        if not differs:
            mismatches += 1
    if mismatches:
        failures.append(f"{mismatches} fraud-flagged records do not actually differ "
                         f"from their fund's known-good baseline in the field(s) their "
                         f"fraud_type claims to have altered")


def check_clean_records_match_baseline(funds, calls_df, failures):
    fund_baseline = {f["fund_id"]: f for f in funds}
    clean_rows = calls_df[~calls_df["is_fraud"]]
    mismatches = 0
    for _, row in clean_rows.iterrows():
        base = fund_baseline[row["fund_id"]]
        if (row["bank_name"] != base["baseline_bank_name"]
                or row["routing_number"] != int(base["baseline_routing_number"])):
            mismatches += 1
    if mismatches:
        failures.append(f"{mismatches} clean (non-fraud) records don't match their "
                         f"fund's baseline bank details")


def check_fraud_rate_in_range(calls_df, failures):
    rate = calls_df["is_fraud"].mean()
    if not (0.04 <= rate <= 0.11):
        failures.append(f"fraud rate {rate:.2%} outside expected 5-10% band (with tolerance)")


def check_lp_amounts_sum_to_event_total(calls_df, failures):
    grouped = calls_df.groupby("event_id").agg(
        amount_sum=("amount", "sum"),
        event_total=("event_total_amount", "first"),
    )
    diff = (grouped["amount_sum"] - grouped["event_total"]).abs()
    bad = (diff > 0.05).sum()
    if bad:
        failures.append(f"{bad} events where per-LP amounts don't sum to the event total")


def main():
    print("Loading generated outputs...")
    funds, calls_df, gl_df, balances_df = load_outputs()
    print(f"  {len(funds)} funds, {len(calls_df)} capital call records, "
          f"{len(gl_df)} GL transactions, {len(balances_df)} daily balance rows")

    failures = []
    checks = [
        ("no duplicate call_ids", check_no_duplicate_call_ids, (calls_df,)),
        ("due_date >= call_date", check_due_date_after_call_date, (calls_df,)),
        ("dates within simulation window", check_dates_within_window, (calls_df,)),
        ("capital calls reconcile to GL", check_capital_calls_reconcile_to_ledger, (funds, calls_df, gl_df)),
        ("daily balances never negative", check_balances_never_negative, (balances_df,)),
        ("fraud records differ from baseline", check_fraud_records_differ_from_baseline, (funds, calls_df)),
        ("clean records match baseline", check_clean_records_match_baseline, (funds, calls_df)),
        ("fraud rate in 5-10% band", check_fraud_rate_in_range, (calls_df,)),
        ("per-LP amounts sum to event total", check_lp_amounts_sum_to_event_total, (calls_df,)),
    ]

    for name, fn, args in checks:
        before = len(failures)
        fn(*args, failures)
        status = "PASS" if len(failures) == before else "FAIL"
        print(f"  [{status}] {name}")

    print()
    if failures:
        print(f"VALIDATION FAILED ({len(failures)} issue(s)):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("VALIDATION PASSED: dataset is internally consistent.")


if __name__ == "__main__":
    main()
