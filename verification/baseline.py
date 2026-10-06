"""Locked per-fund baseline (the values agreed at onboarding, treated as trusted).

Loaded from the Phase 2 synthetic output. In the real product this is whatever the
fund confirmed during onboarding; here it is funds.json.
"""

import json
import os
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUNDS_JSON = os.path.join(REPO_ROOT, "synthetic_data", "output", "funds.json")


@dataclass(frozen=True)
class Baseline:
    fund_id: str
    fund_name: str
    entity_name: str          # GP management entity
    bank_name: str
    routing_number: str
    account_number: str
    domain: str               # authorized GP sender domain
    admin_domain: str         # authorized fund-administrator sender domain
    # Module 2 (payment approvals) config — the verification/verdict logic never reads this.
    assigned_approver: dict = None   # {"name","email","role"} from onboarding config

    @property
    def authorized_domains(self) -> set:
        return {d for d in (self.domain.lower(), self.admin_domain.lower()) if d}


def _slug_domain(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower()) + ".com" if name else ""


def _rows():
    raw = json.load(open(FUNDS_JSON))
    return raw if isinstance(raw, list) else list(raw.values())


def load_baselines() -> dict:
    """fund_id -> Baseline"""
    out = {}
    for f in _rows():
        out[f["fund_id"]] = Baseline(
            fund_id=f["fund_id"],
            fund_name=f["fund_name"],
            entity_name=f["gp_entity_name"],
            bank_name=f["baseline_bank_name"],
            routing_number=str(f["baseline_routing_number"]),
            account_number=str(f["baseline_account_number"]),
            domain=f["domain"],
            admin_domain=_slug_domain(f.get("fund_admin_name", "")),
            assigned_approver=f.get("assigned_approver"),
        )
    return out


def resolve_by_fund_name(fund_name: str, baselines: dict) -> Baseline | None:
    """Match an extracted fund name to a baseline. No fraud type in the synthetic
    set alters the fund name, so this is a safe key; fuzzy anyway for robustness."""
    if not fund_name:
        return None
    best, best_score = None, 0.0
    for b in baselines.values():
        score = fuzz.ratio(fund_name.lower(), b.fund_name.lower())
        if score > best_score:
            best, best_score = b, score
    return best if best_score >= 85 else None
