"""Module 5 — K-1 Routing: synthetic test documents with known ground truth.

10 fictional Schedule K-1 documents. Every one is clearly labelled SYNTHETIC in
its own text. Fund names are taken from the EXISTING roster
(`synthetic_data/output/funds.json`) — these documents look like they came from
funds already in the system. No real taxpayer data, no new fund names invented
(except the one deliberately-unknown fund, for the review-queue path).

Ground truth per doc:
  fund_id / fund_name / lp_id / lp_name : the roster entities it should resolve to
  tax_year, obi, gp_pay                 : the figures embedded in the text
  expect                               : "ROUTED" or "NEEDS_REVIEW"
  expect_reason                        : for NEEDS_REVIEW, which part fails
  case                                 : short label for the test report
"""

from __future__ import annotations

_BANNER = "*** SYNTHETIC TEST DOCUMENT — not a real Schedule K-1, not real taxpayer data ***"


def _doc(fund_name, gp, lp_name, year, obi, gp_pay, cap):
    return (
        "SCHEDULE K-1 (FORM 1065) — Partner's Share of Income, Deductions, Credits, etc.\n"
        f"Tax Year {year}\n"
        f"{_BANNER}\n\n"
        "Part I — Partnership\n"
        f"  Fund: {fund_name}\n"
        f"  General Partner: {gp}\n"
        "  Partnership EIN: 98-1234567 (synthetic)\n\n"
        "Part II — Partner\n"
        f"  Partner: {lp_name}\n"
        "  Partner type: Limited partner\n\n"
        "Part III — Partner's Share of Current Year Items\n"
        f"  1   Ordinary business income (loss) ............ {obi:.2f}\n"
        f"  4a  Guaranteed payments for services .......... {gp_pay:.2f}\n"
        f"  L   Ending capital account ................... {cap:.2f}\n"
    )


# (fund_id, fund_name, gp_entity, [(lp_id, lp_name)]) — copied verbatim from funds.json
_F1 = ("FUND-01", "Fieldstone Equity Partners II", "Fieldstone Equity Management, LLC")
_F2 = ("FUND-02", "Sagebrush Ventures Partners IV", "Sagebrush Ventures Management, LLC")
_F3 = ("FUND-03", "Blackfern Ventures Partners IV", "Blackfern Ventures Management, LLC")

SYNTHETIC_K1_DOCS: list[dict] = [
    # --- 6 clean cases: exact roster fund + LP names --------------------------
    {"doc_id": "K1-0001", "case": "clean",
     "fund_id": _F1[0], "fund_name": _F1[1], "lp_id": "LP-001",
     "lp_name": "Haas Group Retirement System", "tax_year": 2024,
     "obi": 143077.10, "gp_pay": 18461.56, "expect": "ROUTED", "expect_reason": None,
     "text": _doc(_F1[1], _F1[2], "Haas Group Retirement System", 2024, 143077.10, 18461.56, 4246159.15)},
    {"doc_id": "K1-0002", "case": "clean",
     "fund_id": _F1[0], "fund_name": _F1[1], "lp_id": "LP-002",
     "lp_name": "Barnett Inc University Endowment", "tax_year": 2024,
     "obi": 218286.57, "gp_pay": 28166.01, "expect": "ROUTED", "expect_reason": None,
     "text": _doc(_F1[1], _F1[2], "Barnett Inc University Endowment", 2024, 218286.57, 28166.01, 6478182.11)},
    {"doc_id": "K1-0003", "case": "clean",
     "fund_id": _F2[0], "fund_name": _F2[1], "lp_id": "LP-001",
     "lp_name": "Walton-Holt University Endowment", "tax_year": 2024,
     "obi": 476643.85, "gp_pay": 61502.43, "expect": "ROUTED", "expect_reason": None,
     "text": _doc(_F2[1], _F2[2], "Walton-Holt University Endowment", 2024, 476643.85, 61502.43, 14145559.28)},
    {"doc_id": "K1-0004", "case": "clean",
     "fund_id": _F2[0], "fund_name": _F2[1], "lp_id": "LP-002",
     "lp_name": "Frost Hobbs and Dominguez University Endowment", "tax_year": 2024,
     "obi": 268445.02, "gp_pay": 34638.07, "expect": "ROUTED", "expect_reason": None,
     "text": _doc(_F2[1], _F2[2], "Frost Hobbs and Dominguez University Endowment", 2024,
                  268445.02, 34638.07, 7966755.40)},
    {"doc_id": "K1-0005", "case": "clean",
     "fund_id": _F3[0], "fund_name": _F3[1], "lp_id": "LP-001",
     "lp_name": "Velez-Charles Family Office", "tax_year": 2024,
     "obi": 230682.81, "gp_pay": 29765.52, "expect": "ROUTED", "expect_reason": None,
     "text": _doc(_F3[1], _F3[2], "Velez-Charles Family Office", 2024, 230682.81, 29765.52, 6846070.36)},
    {"doc_id": "K1-0006", "case": "clean",
     "fund_id": _F3[0], "fund_name": _F3[1], "lp_id": "LP-002",
     "lp_name": "Parrish Group Family Office", "tax_year": 2023,
     "obi": 253495.78, "gp_pay": 32709.13, "expect": "ROUTED", "expect_reason": None,
     "text": _doc(_F3[1], _F3[2], "Parrish Group Family Office", 2023, 253495.78, 32709.13, 7523100.59)},

    # --- tricky: LP name with a minor typo (missing an 's' in "System") -------
    {"doc_id": "K1-0007", "case": "lp_typo",
     "fund_id": _F1[0], "fund_name": _F1[1], "lp_id": "LP-001",
     "lp_name": "Haas Group Retirement System", "tax_year": 2024,
     "obi": 143077.10, "gp_pay": 18461.56, "expect": "ROUTED", "expect_reason": None,
     "text": _doc(_F1[1], _F1[2], "Haas Group Retirement Sytem", 2024, 143077.10, 18461.56, 4246159.15)},

    # --- tricky: LP name formatting difference (caps + extra spacing) --------
    {"doc_id": "K1-0008", "case": "lp_formatting",
     "fund_id": _F3[0], "fund_name": _F3[1], "lp_id": "LP-001",
     "lp_name": "Velez-Charles Family Office", "tax_year": 2024,
     "obi": 230682.81, "gp_pay": 29765.52, "expect": "ROUTED", "expect_reason": None,
     "text": _doc(_F3[1], _F3[2], "VELEZ-CHARLES   FAMILY   OFFICE", 2024, 230682.81, 29765.52, 6846070.36)},

    # --- review queue: fund that does not exist in the system at all ---------
    {"doc_id": "K1-0009", "case": "unknown_fund",
     "fund_id": None, "fund_name": None, "lp_id": None,
     "lp_name": "Aldergrove County Pension Fund", "tax_year": 2024,
     "obi": 91000.00, "gp_pay": 12000.00, "expect": "NEEDS_REVIEW", "expect_reason": "fund_not_matched",
     "text": _doc("Aetheric Growth Partners IX", "Aetheric Growth Management, LLC",
                  "Aldergrove County Pension Fund", 2024, 91000.00, 12000.00, 2700000.00)},

    # --- review queue: real fund, LP that is not one of its LPs -------------
    {"doc_id": "K1-0010", "case": "unknown_lp",
     "fund_id": _F2[0], "fund_name": _F2[1], "lp_id": None,
     "lp_name": "Nonexistent Pension Trust of Nowhere", "tax_year": 2024,
     "obi": 120000.00, "gp_pay": 15500.00, "expect": "NEEDS_REVIEW", "expect_reason": "lp_not_matched",
     "text": _doc(_F2[1], _F2[2], "Nonexistent Pension Trust of Nowhere", 2024,
                  120000.00, 15500.00, 3600000.00)},
]


def write_jsonl(path: str) -> int:
    """Dump the docs to a JSONL artifact for inspection. Returns the count."""
    import json
    with open(path, "w") as fh:
        for d in SYNTHETIC_K1_DOCS:
            fh.write(json.dumps(d) + "\n")
    return len(SYNTHETIC_K1_DOCS)
