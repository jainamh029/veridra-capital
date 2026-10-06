"""Corrupts a subset of capital call records into fraud-injected variants.
Only payment-instruction / identity fields are altered (routing, bank name,
entity spelling, sender domain) — dollar amounts and dates are left intact,
since that mirrors how business-email-compromise wire fraud actually works:
the attacker redirects the payment, they don't change the invoice.
"""

import random

from . import config
from .banks import is_valid_aba, random_account_number

_LOOKALIKE_SUBS = [("o", "0"), ("i", "l"), ("l", "i"), ("m", "rn"), ("a", "a")]


def _transpose_typo(word: str, rng: random.Random) -> str:
    if len(word) < 4:
        return word + word[-1]
    candidates = [i for i in range(1, len(word) - 2) if word[i] != word[i + 1]]
    if not candidates:
        return word[:-1] + word[-1] * 2  # double the last letter as a fallback typo
    i = rng.choice(candidates)
    chars = list(word)
    chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


def _misspell(name: str, rng: random.Random) -> str:
    words = name.split(" ")
    idx_candidates = [i for i, w in enumerate(words) if len(w) >= 4]
    if not idx_candidates:
        idx_candidates = list(range(len(words)))
    idx = rng.choice(idx_candidates)
    words[idx] = _transpose_typo(words[idx], rng)
    return " ".join(words)


def _spoof_domain(domain: str, rng: random.Random) -> str:
    base, tld = domain.rsplit(".", 1)
    method = rng.choice(["hyphen", "transpose", "lookalike", "tld"])
    if method == "hyphen" and len(base) > 5:
        i = rng.randint(2, len(base) - 3)
        spoofed = f"{base[:i]}-{base[i:]}.{tld}"
    elif method == "transpose":
        spoofed = f"{_transpose_typo(base, rng)}.{tld}"
    elif method == "lookalike":
        applied = False
        chars = base
        for orig, repl in rng.sample(_LOOKALIKE_SUBS, len(_LOOKALIKE_SUBS)):
            if orig in chars:
                chars = chars.replace(orig, repl, 1)
                applied = True
                break
        spoofed = f"{chars}.{tld}" if applied else f"{base}s.{tld}"
    else:
        spoofed = f"{base}.co"
    if spoofed == domain:
        spoofed = f"{base}-corp.{tld}"
    return spoofed


def _alter_routing_digit(routing: str, rng: random.Random) -> str:
    i = rng.randint(0, 8)
    old_digit = routing[i]
    new_digit = str(rng.choice([d for d in range(10) if str(d) != old_digit]))
    return routing[:i] + new_digit + routing[i + 1:]


def _pick_other_bank(bank_directory: dict, current_bank: str, rng: random.Random):
    others = [b for b in bank_directory if b != current_bank]
    chosen = rng.choice(others)
    return chosen, bank_directory[chosen]


def inject_fraud(records: list, bank_directory: dict, rng: random.Random):
    fraud_count = int(len(records) * config.FRAUD_RATE)
    fraud_indices = set(rng.sample(range(len(records)), fraud_count))

    for idx in fraud_indices:
        rec = records[idx]
        fraud_type = rng.choice(config.FRAUD_TYPES)
        rec["is_fraud"] = True
        rec["fraud_type"] = fraud_type

        if fraud_type == "altered_routing_digit":
            old_routing = rec["routing_number"]
            new_routing = _alter_routing_digit(old_routing, rng)
            rec["routing_number"] = new_routing
            rec["notice_text"] = rec["notice_text"].replace(old_routing, new_routing)
            rec["fraud_reasoning"] = (
                f"Routing number {new_routing} does not match fund baseline "
                f"{old_routing} (single digit altered, checksum "
                f"{'still valid' if is_valid_aba(new_routing) else 'invalid'})."
            )

        elif fraud_type == "wrong_bank_valid_checksum":
            old_bank, old_routing = rec["bank_name"], rec["routing_number"]
            new_bank, new_routing = _pick_other_bank(bank_directory, old_bank, rng)
            rec["bank_name"] = new_bank
            rec["routing_number"] = new_routing
            rec["notice_text"] = (
                rec["notice_text"].replace(old_bank, new_bank).replace(old_routing, new_routing)
            )
            rec["fraud_reasoning"] = (
                f"Bank '{new_bank}' with valid routing {new_routing} does not match "
                f"fund's locked baseline bank '{old_bank}' ({old_routing}); checksum "
                f"alone would not catch this."
            )

        elif fraud_type == "misspelled_entity_name":
            old_name = rec["gp_entity_name"]
            new_name = _misspell(old_name, rng)
            rec["gp_entity_name"] = new_name
            rec["notice_text"] = rec["notice_text"].replace(old_name, new_name)
            rec["fraud_reasoning"] = (
                f"Sender entity '{new_name}' is a near-miss misspelling of the fund's "
                f"known-good entity name '{old_name}'."
            )

        elif fraud_type == "spoofed_sender_domain":
            old_domain = rec["sender_domain"]
            new_domain = _spoof_domain(old_domain, rng)
            old_email = rec["sender_email"]
            new_email = old_email.replace(old_domain, new_domain)
            rec["sender_domain"] = new_domain
            rec["sender_email"] = new_email
            rec["notice_text"] = rec["notice_text"].replace(old_email, new_email)
            rec["fraud_reasoning"] = (
                f"Sender domain '{new_domain}' is a typosquat of the fund's known-good "
                f"domain '{old_domain}'."
            )

        elif fraud_type == "last_minute_bank_change":
            old_bank, old_routing, old_account = (
                rec["bank_name"], rec["routing_number"], rec["account_number"]
            )
            new_bank, new_routing = _pick_other_bank(bank_directory, old_bank, rng)
            new_account = random_account_number(rng)
            rec["bank_name"] = new_bank
            rec["routing_number"] = new_routing
            rec["account_number"] = new_account
            notice = rec["notice_text"]
            notice = notice.replace(old_bank, new_bank)
            notice = notice.replace(old_routing, new_routing)
            notice = notice.replace(old_account, new_account)
            notice += (
                "\n\nPLEASE NOTE: Our banking details have changed effective immediately. "
                "Kindly disregard any previously provided wire instructions.\n"
            )
            rec["notice_text"] = notice
            rec["fraud_reasoning"] = (
                "Notice claims a last-minute, unverified change of bank details with no "
                f"prior notice, redirecting from baseline bank '{old_bank}' to '{new_bank}'."
            )

    return records
