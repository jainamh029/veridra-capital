"""Builds a chart of accounts, a GL transaction log, and a daily cash balance
series per fund, all derived from the same call-event schedule used to
generate notices — so capital calls tie directly to cash movements instead of
being generated independently.
"""

import random
from datetime import timedelta

from . import config

CHART_OF_ACCOUNTS = [
    {"account_code": "1001", "account_name": "Cash - Operating Account", "account_type": "Asset"},
    {"account_code": "3001", "account_name": "LP Capital Contributions Received", "account_type": "Equity/Source"},
    {"account_code": "3002", "account_name": "Distributions Paid to LPs", "account_type": "Equity/Use"},
    {"account_code": "3003", "account_name": "Investment Proceeds Received", "account_type": "Income/Source"},
    {"account_code": "4001", "account_name": "Investment Deployments", "account_type": "Use of Cash"},
    {"account_code": "4002", "account_name": "Management Fee Expense", "account_type": "Expense"},
    {"account_code": "4003", "account_name": "Fund Operating Expenses", "account_type": "Expense"},
]


def _biz_day_offset(d, days):
    result = d
    added = 0
    while added < days:
        result += timedelta(days=1)
        if result.weekday() < 5:
            added += 1
    return result


def generate_ledger_for_fund(fund: dict, events: list, rng: random.Random):
    """Returns (gl_transactions, fee_schedule_row) for one fund."""
    txns = []
    txn_seq = 0

    def new_txn(date_, account_code, account_name, amount, description, event_id):
        nonlocal txn_seq
        txn_seq += 1
        txns.append({
            "transaction_id": f"{fund['fund_id']}-GL{txn_seq:06d}",
            "fund_id": fund["fund_id"],
            "date": date_.isoformat(),
            "account_code": account_code,
            "account_name": account_name,
            "amount": amount,
            "description": description,
            "related_event_id": event_id,
            "synthetic": True,
        })

    for event in events:
        on_time = rng.random() < 0.85
        payment_date = event["due_date"] if on_time else _biz_day_offset(event["due_date"], rng.randint(1, 5))
        if payment_date > config.SIM_END:
            payment_date = config.SIM_END

        new_txn(payment_date, "3001", "LP Capital Contributions Received",
                round(event["amount"], 2),
                f"Capital call #{event['event_num']} received ({event['purpose']})",
                f"{fund['fund_id']}-EVT{event['event_num']:05d}")

        outflow_date = _biz_day_offset(payment_date, rng.randint(1, 3))
        if outflow_date > config.SIM_END:
            outflow_date = config.SIM_END

        if event["purpose"] == "investment":
            new_txn(outflow_date, "4001", "Investment Deployments",
                    -round(event["amount"], 2),
                    f"Deployment into {event['portfolio_company']}",
                    f"{fund['fund_id']}-EVT{event['event_num']:05d}")
        elif event["purpose"] == "management_fee":
            new_txn(outflow_date, "4002", "Management Fee Expense",
                    -round(event["amount"], 2),
                    "Quarterly management fee paid to GP",
                    f"{fund['fund_id']}-EVT{event['event_num']:05d}")
        else:
            new_txn(outflow_date, "4003", "Fund Operating Expenses",
                    -round(event["amount"], 2),
                    "Fund operating expenses paid",
                    f"{fund['fund_id']}-EVT{event['event_num']:05d}")

    # Independent exit/distribution cycle: proceeds in, distribution out a few days later.
    start = min((e["call_date"] for e in events), default=config.SIM_START)
    exit_start = start + timedelta(weeks=104)
    w = 0
    exit_num = 0
    while True:
        exit_date = exit_start + timedelta(weeks=w)
        if exit_date > config.SIM_END:
            break
        exit_num += 1
        proceeds = round(fund["committed_capital_usd"] * rng.uniform(0.03, 0.10), 2)
        new_txn(exit_date, "3003", "Investment Proceeds Received", proceeds,
                f"Exit proceeds #{exit_num}", f"{fund['fund_id']}-EXIT{exit_num:03d}")
        dist_date = _biz_day_offset(exit_date, rng.randint(3, 8))
        if dist_date > config.SIM_END:
            dist_date = config.SIM_END
        new_txn(dist_date, "3002", "Distributions Paid to LPs", -proceeds,
                f"Distribution #{exit_num} to LPs", f"{fund['fund_id']}-EXIT{exit_num:03d}")
        w += 20

    txns.sort(key=lambda t: t["date"])

    quarterly_fee = round(fund["committed_capital_usd"] * config.ANNUAL_MGMT_FEE_RATE / 4, 2)
    fee_schedule_row = {
        "fund_id": fund["fund_id"],
        "annual_fee_rate": config.ANNUAL_MGMT_FEE_RATE,
        "committed_capital_usd": fund["committed_capital_usd"],
        "quarterly_fee_amount": quarterly_fee,
        "fee_basis": "committed_capital",
    }
    return txns, fee_schedule_row


def build_daily_balances(fund_id: str, txns: list):
    from collections import defaultdict
    daily_delta = defaultdict(float)
    for t in txns:
        daily_delta[t["date"]] += t["amount"]

    rows = []
    balance = 0.0
    d = config.SIM_START
    while d <= config.SIM_END:
        key = d.isoformat()
        if key in daily_delta:
            balance += daily_delta[key]
            balance = round(balance, 2)
        rows.append({"fund_id": fund_id, "date": key, "cash_balance": balance})
        d += timedelta(days=1)
    return rows
