"""Orchestrates the full synthetic data build: funds -> LPs -> capital call
events -> per-LP notices -> fraud injection -> GL ledger -> daily cash
balances -> writes everything under synthetic_data/output/.

Run with: python -m synthetic_data.run_pipeline
"""

import json
import os
import random
import sqlite3

import pandas as pd
from faker import Faker

from . import config
from .fund_generator import generate_funds
from .capital_call_generator import generate_call_events, explode_to_lp_records
from .fraud_injector import inject_fraud
from .ledger_generator import CHART_OF_ACCOUNTS, generate_ledger_for_fund, build_daily_balances


def main():
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    rng = random.Random(config.SEED)
    fake = Faker()
    Faker.seed(config.SEED)

    print("Generating funds and LP rosters...")
    funds, bank_directory = generate_funds()
    print(f"  {len(funds)} funds generated")

    all_records = []
    all_txns = []
    all_daily_balances = []
    fee_schedule_rows = []

    for fund in funds:
        events = generate_call_events(fund, rng, fake)
        records = explode_to_lp_records(fund, events, rng)
        all_records.extend(records)

        txns, fee_row = generate_ledger_for_fund(fund, events, rng)
        all_txns.extend(txns)
        fee_schedule_rows.append(fee_row)

        daily_balances = build_daily_balances(fund["fund_id"], txns)
        all_daily_balances.extend(daily_balances)

        print(f"  {fund['fund_id']} ({fund['fund_name']}): {len(events)} events, "
              f"{len(records)} LP-level records, {len(fund['lps'])} LPs")

    print(f"\nTotal capital call records before fraud injection: {len(all_records)}")

    print("Injecting fraud subset...")
    all_records = inject_fraud(all_records, bank_directory, rng)
    fraud_count = sum(1 for r in all_records if r["is_fraud"])
    print(f"  {fraud_count} fraud records injected "
          f"({fraud_count / len(all_records):.1%} of {len(all_records)})")

    # --- funds.json (baseline / ground truth, used by the rules verification layer) ---
    funds_out = [{k: v for k, v in f.items() if k != "lps"} | {"lp_count": len(f["lps"]), "lps": f["lps"]}
                 for f in funds]
    with open(os.path.join(config.OUTPUT_DIR, "funds.json"), "w") as f:
        json.dump(funds_out, f, indent=2, default=str)

    # --- capital_calls.jsonl (full record, incl. notice_text) ---
    calls_path = os.path.join(config.OUTPUT_DIR, "capital_calls.jsonl")
    with open(calls_path, "w") as f:
        for r in all_records:
            f.write(json.dumps(r) + "\n")

    # --- extraction_dataset.jsonl (input/output pairs for Phase 3 fine-tuning) ---
    extraction_path = os.path.join(config.OUTPUT_DIR, "extraction_dataset.jsonl")
    with open(extraction_path, "w") as f:
        for r in all_records:
            example = {
                "call_id": r["call_id"],
                "notice_text": r["notice_text"],
                "extraction": {
                    "entity": r["gp_entity_name"],
                    "fund_name": r["fund_name"],
                    "lp_name": r["lp_name"],
                    "amount": r["amount"],
                    "due_date": r["due_date"],
                    "bank_name": r["bank_name"],
                    "routing_number": r["routing_number"],
                    "account_number": r["account_number"],
                    "purpose": r["purpose"],
                    "fraud_flag": r["is_fraud"],
                    "fraud_type": r["fraud_type"],
                },
                "synthetic": True,
            }
            f.write(json.dumps(example) + "\n")

    # --- accounting data: CSVs ---
    coa_df = pd.DataFrame(CHART_OF_ACCOUNTS)
    coa_df.to_csv(os.path.join(config.OUTPUT_DIR, "chart_of_accounts.csv"), index=False)

    gl_df = pd.DataFrame(all_txns)
    gl_df.to_csv(os.path.join(config.OUTPUT_DIR, "gl_transactions.csv"), index=False)

    balances_df = pd.DataFrame(all_daily_balances)
    balances_df.to_csv(os.path.join(config.OUTPUT_DIR, "cash_balances_daily.csv"), index=False)

    fee_df = pd.DataFrame(fee_schedule_rows)
    fee_df.to_csv(os.path.join(config.OUTPUT_DIR, "fee_schedule.csv"), index=False)

    calls_df = pd.DataFrame(all_records).drop(columns=["notice_text"])
    calls_df.to_csv(os.path.join(config.OUTPUT_DIR, "capital_calls.csv"), index=False)

    fraud_summary = calls_df[calls_df["is_fraud"]]["fraud_type"].value_counts().reset_index()
    fraud_summary.columns = ["fraud_type", "count"]
    fraud_summary.to_csv(os.path.join(config.OUTPUT_DIR, "fraud_summary.csv"), index=False)

    # --- SQLite db for the cash planning / forecasting agents to query ---
    db_path = os.path.join(config.OUTPUT_DIR, "accounting.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    coa_df.to_sql("chart_of_accounts", conn, index=False)
    gl_df.to_sql("gl_transactions", conn, index=False)
    balances_df.to_sql("cash_balances_daily", conn, index=False)
    fee_df.to_sql("fee_schedule", conn, index=False)
    calls_df.to_sql("capital_calls", conn, index=False)
    conn.close()

    print(f"\nWrote outputs to {config.OUTPUT_DIR}/")
    print(f"  funds.json, capital_calls.jsonl ({len(all_records)} records), "
          f"extraction_dataset.jsonl, capital_calls.csv, chart_of_accounts.csv, "
          f"gl_transactions.csv ({len(all_txns)} txns), cash_balances_daily.csv, "
          f"fee_schedule.csv, fraud_summary.csv, accounting.db")


if __name__ == "__main__":
    main()
