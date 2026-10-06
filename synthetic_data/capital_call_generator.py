"""Builds capital call events per fund (tied to an investment/fee/expense
schedule, not random noise) and explodes each event into one record per LP,
rendered through one of the four notice styles.
"""

import random
from datetime import date, timedelta

from faker import Faker

from . import config
from .notice_templates import render_notice

_PORTFOLIO_SUFFIXES = ["Holdings", "Technologies", "Group", "Industries", "Solutions", "Partners"]


def _fund_start(fund):
    vintage_start = date(fund["vintage_year"], 1, 1)
    return max(config.SIM_START, vintage_start)


def _add_weeks(d: date, weeks: int) -> date:
    return d + timedelta(weeks=weeks)


def _next_business_day_offset(d: date, days: int) -> date:
    result = d
    added = 0
    step = 1 if days >= 0 else -1
    while added < abs(days):
        result += timedelta(days=step)
        if result.weekday() < 5:
            added += 1
    return result


def generate_call_events(fund: dict, rng: random.Random, fake: Faker):
    """Returns a list of event dicts (one per call, aggregated across the fund's
    whole LP roster) — investment deployments, quarterly management fees, and
    periodic fund expenses."""
    events = []
    start = _fund_start(fund)
    committed = fund["committed_capital_usd"]
    event_num = 0

    investment_end = min(_add_weeks(start, config.INVESTMENT_PERIOD_WEEKS), config.SIM_END)
    w = 0
    while True:
        call_date = _add_weeks(start, w)
        if call_date > investment_end or call_date > config.SIM_END:
            break
        event_num += 1
        amount = round(committed * rng.uniform(0.015, 0.05), 2)
        company = f"{fake.last_name()} {rng.choice(_PORTFOLIO_SUFFIXES)}"
        events.append({
            "event_num": event_num,
            "call_date": call_date,
            "due_date": _next_business_day_offset(call_date, 10),
            "purpose": "investment",
            "purpose_description": f"Capital call for follow-on investment in {company}",
            "portfolio_company": company,
            "amount": amount,
        })
        w += config.INVESTMENT_CALL_INTERVAL_WEEKS

    quarterly_fee = round(committed * config.ANNUAL_MGMT_FEE_RATE / 4, 2)
    w = config.FEE_CALL_INTERVAL_WEEKS
    while True:
        call_date = _add_weeks(start, w)
        if call_date > config.SIM_END:
            break
        event_num += 1
        events.append({
            "event_num": event_num,
            "call_date": call_date,
            "due_date": _next_business_day_offset(call_date, 10),
            "purpose": "management_fee",
            "purpose_description": "Quarterly management fee call (2% annual rate on committed capital)",
            "portfolio_company": None,
            "amount": quarterly_fee,
        })
        w += config.FEE_CALL_INTERVAL_WEEKS

    w = config.EXPENSE_CALL_INTERVAL_WEEKS
    while True:
        call_date = _add_weeks(start, w)
        if call_date > config.SIM_END:
            break
        event_num += 1
        amount = round(committed * rng.uniform(0.0004, 0.0015), 2)
        events.append({
            "event_num": event_num,
            "call_date": call_date,
            "due_date": _next_business_day_offset(call_date, 10),
            "purpose": "fund_expense",
            "purpose_description": "Fund operating expense call (legal, audit, administration)",
            "portfolio_company": None,
            "amount": amount,
        })
        w += config.EXPENSE_CALL_INTERVAL_WEEKS

    events.sort(key=lambda e: e["call_date"])
    for i, e in enumerate(events, start=1):
        e["event_num"] = i
    return events


def explode_to_lp_records(fund: dict, events: list, rng: random.Random):
    """One record per LP per call event, with rendered notice text. Bank/entity
    fields here are the TRUE baseline values — the fraud injector corrupts a
    copy of a subset of these afterward; it never touches the dollar amounts,
    since real wire fraud targets payment instructions, not invoice totals."""
    records = []
    domain = fund["domain"]
    admin_domain = fund["fund_admin_name"].lower().replace(" ", "").replace(",", "").replace("&", "and") + ".com"

    for event in events:
        lp_amounts = []
        running = 0.0
        for lp in fund["lps"][:-1]:
            amt = round(event["amount"] * lp["commitment_pct"], 2)
            lp_amounts.append(amt)
            running += amt
        lp_amounts.append(round(event["amount"] - running, 2))

        for lp, lp_amount in zip(fund["lps"], lp_amounts):
            notice_format = rng.choice(config.NOTICE_FORMATS)
            sender_email = f"investor.relations@{domain}"
            ctx = {
                "gp_entity_name": fund["gp_entity_name"],
                "fund_name": fund["fund_name"],
                "call_number": event["event_num"],
                "call_date": event["call_date"].isoformat(),
                "due_date": event["due_date"].isoformat(),
                "lp_name": lp["lp_name"],
                "purpose_description": event["purpose_description"],
                "amount": lp_amount,
                "bank_name": fund["baseline_bank_name"],
                "routing_number": fund["baseline_routing_number"],
                "account_number": fund["baseline_account_number"],
                "contact_email": fund["contact_email"],
                "sender_email": sender_email,
                "admin_domain": admin_domain,
                "fund_admin_name": fund["fund_admin_name"],
            }
            notice_text = render_notice(notice_format, ctx)

            records.append({
                "call_id": f"{fund['fund_id']}-EVT{event['event_num']:05d}-{lp['lp_id']}",
                "event_id": f"{fund['fund_id']}-EVT{event['event_num']:05d}",
                "fund_id": fund["fund_id"],
                "fund_name": fund["fund_name"],
                "gp_entity_name": fund["gp_entity_name"],
                "lp_id": lp["lp_id"],
                "lp_name": lp["lp_name"],
                "call_date": event["call_date"].isoformat(),
                "due_date": event["due_date"].isoformat(),
                "purpose": event["purpose"],
                "purpose_description": event["purpose_description"],
                "portfolio_company": event["portfolio_company"],
                "amount": lp_amount,
                "event_total_amount": event["amount"],
                "bank_name": fund["baseline_bank_name"],
                "routing_number": fund["baseline_routing_number"],
                "account_number": fund["baseline_account_number"],
                "sender_email": sender_email,
                "sender_domain": domain,
                "notice_format": notice_format,
                "notice_text": notice_text,
                "is_fraud": False,
                "fraud_type": None,
                "synthetic": True,
            })
    return records
