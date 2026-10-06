"""K-1 / tax-document routing agent — LIGHT STUB.

Reuses the Phase-3 approach (LLM extracts structured fields from a raw document)
on a different document type: a Schedule K-1 (Form 1065). It then routes the K-1
to the responsible tax contact for that LP.

Synthetic K-1 text is generated on the fly from the Phase-2 fund/LP roster so no
new data files are needed. This is intentionally minimal: enough to show the
document-parsing approach generalises, not a finished module.
"""

import json
import re

from .common import REPO_ROOT, ask_llm, db
import os

FUNDS_JSON = os.path.join(REPO_ROOT, "synthetic_data", "output", "funds.json")

EXTRACT_SYSTEM = (
    "You extract fields from a US Schedule K-1 (Form 1065). Output ONLY a JSON "
    "object with keys: partnership_name, partner_name, tax_year, "
    "partner_tin_last4, ordinary_business_income, net_rental_income, "
    "guaranteed_payments, ending_capital_account. Numbers as plain numbers. "
    "Use null if a field is absent. No other text."
)

# tiny synthetic routing table: which team handles which LP type
def _tax_contact(lp_name: str) -> dict:
    n = lp_name.lower()
    if "pension" in n or "retirement" in n:
        return {"team": "Institutional Tax - Retirement", "email": "retire-tax@synthetic-admin.example"}
    if "endowment" in n or "university" in n or "foundation" in n:
        return {"team": "Institutional Tax - Nonprofit", "email": "npo-tax@synthetic-admin.example"}
    if "family office" in n or "trust" in n:
        return {"team": "Private Client Tax", "email": "pc-tax@synthetic-admin.example"}
    return {"team": "General Partnership Tax", "email": "gp-tax@synthetic-admin.example"}


def sample_k1_documents(n_funds: int = 2, lps_per_fund: int = 2, tax_year: int = 2024) -> list:
    funds = json.load(open(FUNDS_JSON))
    funds = funds if isinstance(funds, list) else list(funds.values())
    docs = []
    for f in funds[:n_funds]:
        for lp in f["lps"][:lps_per_fund]:
            commit = lp["commitment_usd"]
            obi = round(commit * 0.031, 2)
            gp_pay = round(commit * 0.004, 2)
            cap = round(commit * 0.92, 2)
            tin = f"{abs(hash(lp['lp_id'])) % 10000:04d}"
            text = f"""SCHEDULE K-1 (FORM 1065)                     Tax Year {tax_year}
Partner's Share of Income, Deductions, Credits, etc.        SYNTHETIC - not a real tax document

Part I  Information About the Partnership
  Partnership: {f['gp_entity_name']} as GP of {f['fund_name']}
  Partnership EIN: 98-{abs(hash(f['fund_id'])) % 10000000:07d}

Part II  Information About the Partner
  Partner: {lp['lp_name']}
  Partner identifying number (last 4): {tin}
  Partner type: Limited partner

Part III  Partner's Share of Current Year Income
  1  Ordinary business income (loss) .......... {obi:,.2f}
  2  Net rental real estate income (loss) ..... 0.00
  4a Guaranteed payments for services ......... {gp_pay:,.2f}
  L  Ending capital account ................... {cap:,.2f}
"""
            docs.append({
                "doc_id": f"K1-{f['fund_id']}-{lp['lp_id']}-{tax_year}",
                "fund_id": f["fund_id"], "lp_id": lp["lp_id"], "text": text, "synthetic": True,
            })
    return docs


def _parse_json(t):
    m = re.search(r"\{.*\}", t or "", re.DOTALL)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


def route_k1(document_text: str, with_llm: bool = True) -> dict:
    """Extract K-1 fields and route to the responsible tax contact."""
    if with_llm:
        extracted = _parse_json(ask_llm(EXTRACT_SYSTEM, document_text, temperature=0, num_predict=250))
    else:
        extracted = None
    if not extracted:  # deterministic fallback so routing still works offline
        pn = re.search(r"Partnership:\s*(.+)", document_text)
        prt = re.search(r"Partner:\s*(.+)", document_text)
        yr = re.search(r"Tax Year (\d{4})", document_text)
        extracted = {
            "partnership_name": pn.group(1).strip() if pn else None,
            "partner_name": prt.group(1).strip() if prt else None,
            "tax_year": int(yr.group(1)) if yr else None,
        }
    partner = extracted.get("partner_name") or ""
    contact = _tax_contact(partner)
    return {
        "status": "STUB — light implementation",
        "extracted": extracted,
        "routed_to": contact,
        "action": f"Deliver K-1 for {partner or 'unknown partner'} "
                  f"({extracted.get('tax_year')}) to {contact['team']} <{contact['email']}>",
    }
