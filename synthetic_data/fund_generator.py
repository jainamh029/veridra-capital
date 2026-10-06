"""Generates fictional PE funds, their LP rosters, and locked-in baseline
wire instructions (the 'known good' data set against which fraud is detected).
"""

import random
import re
from faker import Faker

from . import config
from .banks import build_bank_directory, random_account_number

_FUND_PREFIXES = [
    "Sagebrush", "Ironwood", "Cobblestone", "Blackfern", "Northwind",
    "Redcliff", "Fieldstone", "Bramblewood", "Copperline", "Stonegate",
    "Ashcroft", "Highmark", "Rivergate", "Brightwater", "Thornbury",
]
_FUND_MIDDLES = ["Capital", "Growth", "Equity", "Ventures"]
_FUND_TYPES = ["Buyout", "Growth Equity"]
# synthetic LP-side finance-team approvers (Module 2). Round-robined across funds.
_APPROVERS = [
    {"name": "Dana Whitfield", "email": "dwhitfield@synthetic-ops.example", "role": "Controller"},
    {"name": "Marcus True", "email": "mtrue@synthetic-ops.example", "role": "Controller"},
    {"name": "Priya Anand", "email": "panand@synthetic-ops.example", "role": "Assistant Controller"},
    {"name": "Sam Ellery", "email": "sellery@synthetic-ops.example", "role": "Head of Finance Ops"},
]
_LP_TYPE_SUFFIXES = [
    "Pension Fund", "Endowment", "Family Office", "Foundation",
    "Retirement System", "Insurance Investment Trust", "University Endowment",
]


def _domain_from_name(fund_short_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "", fund_short_name.lower())
    return f"{slug}.com"


def _make_fund_name(prefix: str, fund_number: int, rng: random.Random) -> tuple[str, str, str]:
    middle = rng.choice(_FUND_MIDDLES)
    roman = {2: "II", 3: "III", 4: "IV"}[fund_number]
    full_name = f"{prefix} {middle} Partners {roman}"
    short_name = f"{prefix}{middle}"
    return full_name, short_name, middle


def generate_lps(rng: random.Random, fake: Faker, count: int, committed_capital: float):
    lps = []
    weights = [rng.uniform(0.3, 1.0) for _ in range(count)]
    total_weight = sum(weights)
    for i, w in enumerate(weights):
        pct = w / total_weight
        lp_type = rng.choice(_LP_TYPE_SUFFIXES)
        base = fake.company().replace(",", "").replace(".", "")
        lp_name = f"{base} {lp_type}"
        lps.append({
            "lp_id": f"LP-{i+1:03d}",
            "lp_name": lp_name,
            "commitment_pct": round(pct, 6),
            "commitment_usd": round(committed_capital * pct, 2),
        })
    return lps


def generate_funds():
    rng = random.Random(config.SEED)
    fake = Faker()
    Faker.seed(config.SEED)

    bank_directory = build_bank_directory(rng)
    bank_names = list(bank_directory.keys())

    funds = []
    used_prefixes = rng.sample(_FUND_PREFIXES, config.NUM_FUNDS)

    for i in range(config.NUM_FUNDS):
        prefix = used_prefixes[i]
        fund_number = rng.choice([2, 3, 4])
        full_name, short_name, middle = _make_fund_name(prefix, fund_number, rng)
        vintage_year = rng.choice([2020, 2021, 2021, 2022, 2022])
        target_size = rng.choice([150_000_000, 200_000_000, 275_000_000, 350_000_000,
                                   450_000_000, 600_000_000])
        committed_capital = round(target_size * rng.uniform(0.92, 1.0), 2)

        bank_name = bank_names[i % len(bank_names)]
        routing_number = bank_directory[bank_name]
        account_number = random_account_number(rng)

        gp_entity_name = f"{prefix} {middle} Management, LLC"
        domain = _domain_from_name(short_name)

        lp_count = rng.randint(config.LP_ROSTER_MIN, config.LP_ROSTER_MAX)
        lps = generate_lps(rng, fake, lp_count, committed_capital)

        fund = {
            "fund_id": f"FUND-{i+1:02d}",
            "fund_name": full_name,
            "fund_type": rng.choice(_FUND_TYPES),
            "vintage_year": vintage_year,
            "target_size_usd": target_size,
            "committed_capital_usd": committed_capital,
            "gp_entity_name": gp_entity_name,
            "domain": domain,
            "contact_email": f"investor.relations@{domain}",
            "baseline_bank_name": bank_name,
            "baseline_routing_number": routing_number,
            "baseline_account_number": account_number,
            "fund_admin_name": rng.choice([
                "Meridian Fund Administration", "Standish Fund Services",
                "Northbridge Fund Admin Partners", "Clearview Fund Services",
            ]),
            # Module 2 (payment approvals): the person on the LP-side finance team who
            # releases wires for this fund. Part of onboarding config, not a separate system.
            "assigned_approver": _APPROVERS[i % len(_APPROVERS)],
            "lps": lps,
            "synthetic": True,
        }
        funds.append(fund)

    return funds, bank_directory
