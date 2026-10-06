"""Synthetic bank directory with valid-checksum ABA routing numbers.

None of these are real financial institutions. Names were chosen to sound
plausible but avoid any resemblance to real banks.
"""

import random

_BANK_NAMES = [
    "Meridian Trust Bank",
    "Cornerstone National Bank",
    "Blue Harbor Bank & Trust",
    "Highland Ridge Bank",
    "Pacific Crest Bank",
    "Ironwood Commercial Bank",
    "Summit Peak Bank",
    "Lakeshore National Bank",
    "Silverline Bank & Trust",
    "Northgate Commercial Bank",
    "Fieldstone Bank",
    "Amber Valley Trust",
    "Redwood Capital Bank",
    "Bluepoint National Bank",
    "Cedarbrook Bank & Trust",
]


def aba_checksum_digit(first_eight):
    """Given 8 digits, compute the 9th check digit per the ABA routing algorithm."""
    d = [int(c) for c in first_eight]
    total = (
        3 * (d[0] + d[3] + d[6])
        + 7 * (d[1] + d[4] + d[7])
        + 1 * (d[2] + d[5])
    )
    check = (10 - (total % 10)) % 10
    return check


def is_valid_aba(routing_number):
    if not routing_number.isdigit() or len(routing_number) != 9:
        return False
    d = [int(c) for c in routing_number]
    total = 3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + 1 * (d[2] + d[5] + d[8])
    return total % 10 == 0


def generate_valid_routing(rng: random.Random):
    prefix = rng.choice(["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"])
    middle = "".join(str(rng.randint(0, 9)) for _ in range(6))
    first_eight = prefix + middle
    check = aba_checksum_digit(first_eight)
    return first_eight + str(check)


def build_bank_directory(rng: random.Random):
    """One valid routing number per bank name, fixed for the life of this dataset."""
    directory = {}
    for name in _BANK_NAMES:
        routing = generate_valid_routing(rng)
        assert is_valid_aba(routing)
        directory[name] = routing
    return directory


def random_account_number(rng: random.Random):
    length = rng.randint(9, 12)
    return "".join(str(rng.randint(0, 9)) for _ in range(length))
