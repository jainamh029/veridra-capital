"""Shared constants for the synthetic data pipeline. All data produced from this
pipeline is synthetic and must carry synthetic: true wherever it appears."""

import os
from datetime import date

SEED = 20260830

NUM_FUNDS = 10
LP_ROSTER_MIN = 15
LP_ROSTER_MAX = 25

SIM_START = date(2021, 1, 5)   # first Tuesday of Jan 2021
SIM_WEEKS = 260                # ~5 years
SIM_END = date(2025, 12, 30)

INVESTMENT_PERIOD_WEEKS = 156  # 3 years of active deployment from each fund's vintage
INVESTMENT_CALL_INTERVAL_WEEKS = 2
FEE_CALL_INTERVAL_WEEKS = 13   # quarterly
EXPENSE_CALL_INTERVAL_WEEKS = 4

ANNUAL_MGMT_FEE_RATE = 0.02    # 2% of committed capital per year, standard PE structure

FRAUD_RATE = 0.07              # 5-10% of records corrupted, per spec

NOTICE_FORMATS = ["formal_pdf_style", "casual_bullet_email", "fund_admin_email", "messy_gp_email"]

FRAUD_TYPES = [
    "altered_routing_digit",
    "wrong_bank_valid_checksum",
    "misspelled_entity_name",
    "spoofed_sender_domain",
    "last_minute_bank_change",
]

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_ROOT, "synthetic_data", "output")

PAYMENT_PURPOSES = ["investment", "management_fee", "fund_expense"]
