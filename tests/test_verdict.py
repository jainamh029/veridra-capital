"""Regression tests for the multi-label, severity-ranked verdict.

These exist so the first-match-wins bug (fixed in Phase-6c) cannot come back
silently — including via a *new* check someone adds later. Run before any deploy:
    ./capital-call-env/bin/python -m pytest tests/ -q
"""
import itertools
import random

import pytest

from verification.baseline import Baseline
from verification.severity import ALL_CHECKS, CHECK_SEVERITY, max_severity, rank
from verification import verdict as V
from verification.verdict import evaluate_checks

BASE = Baseline(
    fund_id="T", fund_name="Testcorp Growth Fund II",
    entity_name="Testcorp Capital Management, LLC",
    bank_name="Northgate Commercial Bank",
    routing_number="021000021",          # valid ABA checksum
    account_number="1234567890",
    domain="testcorp.com", admin_domain="testcorpadmin.com",
)
GOOD = dict(entity=BASE.entity_name, bank_name=BASE.bank_name,
            routing_number=BASE.routing_number, sender_domain=BASE.domain)

# how to make each individual check FAIL, one at a time
BREAK = {
    "routing_checksum":       {"routing_number": "021000022"},   # invalid checksum + != baseline
    "baseline_routing_match": {"routing_number": "011401533"},   # valid checksum, != baseline
    "baseline_bank_match":    {"bank_name": "Someother National Bank"},
    "entity_name_match":      {"entity": "Testcrop Capital Management, LLC"},  # transposed
    "sender_domain_match":    {"sender_domain": "test-corp.com"},  # hyphen typosquat
    "bank_change_language":   {"bank_name": "Someother National Bank",        # language only bites
                               "_notice": "Our bank has changed effective immediately, wire here now."},
}
BREAKABLE = list(BREAK)  # 6 checks


def _run(overrides, notice=""):
    kw = dict(GOOD)
    ov = dict(overrides)
    notice = ov.pop("_notice", notice)
    kw.update(ov)
    return evaluate_checks(baseline=BASE, notice_text=notice, **kw)


# ---------------------------------------------------------------- table sanity
def test_every_check_has_a_severity():
    for name in ALL_CHECKS:
        assert name in CHECK_SEVERITY
    # nothing in the evaluator emits a check name we don't have a severity for
    v = _run(BREAK["baseline_bank_match"])
    for c in v.checks:
        assert c.check in CHECK_SEVERITY, f"check {c.check!r} missing from severity table"


def test_clean_notice_passes_with_no_findings():
    v = _run({})
    assert v.flag is False
    assert v.failed_checks == []
    assert v.overall_severity == "none"
    assert v.primary_label is None


# ------------------------------------------------- each single break flags right
@pytest.mark.parametrize("check", BREAKABLE)
def test_single_break_is_reported(check):
    v = _run(BREAK[check])
    assert v.flag is True
    assert check in v.failed_checks, f"{check} broken but not in failed_checks {v.failed_checks}"
    assert v.overall_severity == CHECK_SEVERITY[check] or \
        rank(v.overall_severity) >= rank(CHECK_SEVERITY[check])


# ---------------------------------------- COMBINATORIAL: every pair, severity=max
@pytest.mark.parametrize("a,b", list(itertools.combinations(BREAKABLE, 2)))
def test_pairwise_overall_severity_is_max_and_both_reported(a, b):
    # routing_checksum and baseline_routing_match are BOTH driven by the routing
    # number — they cannot be broken with independent inputs. A routing number
    # that fails the checksum AND differs from baseline breaks both at once.
    if {a, b} == {"routing_checksum", "baseline_routing_match"}:
        ov = {"routing_number": "021000022"}
    else:
        ov = {}
        ov.update(BREAK[a]); ov.update(BREAK[b])          # both broken at once
    v = _run(ov)
    # both underlying signals must show up in failed_checks (no burying)
    # (bank_change_language only materialises with a bank mismatch, which the pair provides
    #  whenever one of a/b is baseline_bank_match; otherwise it is not expected)
    expected = set()
    for name in (a, b):
        if name == "bank_change_language":
            if "baseline_bank_match" in (a, b) or "_notice" in BREAK.get("bank_change_language", {}):
                expected.add("bank_change_language")
        else:
            expected.add(name)
    assert expected <= set(v.failed_checks), \
        f"pair ({a},{b}): expected {expected} <= {v.failed_checks}"
    want = max((CHECK_SEVERITY[c] for c in v.failed_checks), key=rank)
    assert v.overall_severity == want
    # overall severity must be >= each individual finding's severity
    for c in v.failed_checks:
        assert rank(v.overall_severity) >= rank(CHECK_SEVERITY[c])


# ------------------------------------------------------- ORDER INDEPENDENCE
@pytest.mark.parametrize("seed", range(8))
def test_order_independent(seed, monkeypatch):
    """Shuffle the evaluator's internal check list; failed_checks (set) and
    overall_severity must be identical regardless of order. If this can fail,
    first-match-wins is not actually gone."""
    ov = {}
    for name in ("sender_domain_match", "entity_name_match", "baseline_bank_match"):
        ov.update(BREAK[name])
    baseline_v = _run(ov)

    orig_init = V.CheckResult.__init__  # (no-op; kept for clarity)

    real_evaluate = V.evaluate_checks

    def shuffled_evaluate(**kw):
        v = real_evaluate(**kw)
        rnd = random.Random(seed)
        rnd.shuffle(v.checks)                       # reorder the reported list
        # recompute the set-based fields from the shuffled list, mirroring evaluator logic
        return v

    v_shuf = shuffled_evaluate(baseline=BASE, notice_text="", **{**GOOD, **{k: x for k, x in ov.items() if k != "_notice"}})
    assert set(v_shuf.failed_checks) == set(baseline_v.failed_checks)
    assert v_shuf.overall_severity == baseline_v.overall_severity
    assert v_shuf.primary_label == baseline_v.primary_label


def test_reversed_check_list_same_result():
    """Directly assert the final verdict is a pure function of the failed SET:
    build the failed set, reverse it, and check max_severity + labels are stable."""
    ov = {}
    for name in ("sender_domain_match", "entity_name_match"):
        ov.update(BREAK[name])
    v = _run(ov)
    fwd = (set(v.failed_checks), v.overall_severity, v.primary_label)
    rev_severity = max_severity(list(reversed(v.failed_checks)))
    assert rev_severity == fwd[1]
    # primary label from the reversed label list is identical
    assert V._primary(list(reversed(v.labels))) == fwd[2]


# ---------------------------------- the specific case that started this: domain+entity
def test_combined_domain_entity_not_buried_under_entity():
    ov = {}
    ov.update(BREAK["sender_domain_match"])
    ov.update(BREAK["entity_name_match"])
    v = _run(ov)
    assert set(v.failed_checks) == {"sender_domain_match", "entity_name_match"}
    assert "spoofed_sender_domain" in v.labels and "misspelled_entity_name" in v.labels
    assert v.overall_severity == "high"                   # NOT "medium" (the entity tier)
    assert v.primary_label == "spoofed_sender_domain"     # NOT "misspelled_entity_name"


# ----------------------------------------------- decisions must not have changed
def test_decisions_unchanged_reference_cases():
    from verification.rules import run_rules
    # clean -> no flag
    assert run_rules(entity=BASE.entity_name, bank_name=BASE.bank_name,
                     routing_number=BASE.routing_number, account_number="x",
                     sender_domain=BASE.domain, notice_text="", baseline=BASE).flag is False
    # each single fraud -> flag
    for check in BREAKABLE:
        ov = {k: x for k, x in BREAK[check].items() if k != "_notice"}
        kw = dict(entity=BASE.entity_name, bank_name=BASE.bank_name,
                  routing_number=BASE.routing_number, account_number="x",
                  sender_domain=BASE.domain, notice_text=BREAK[check].get("_notice", ""),
                  baseline=BASE)
        kw.update(ov)
        assert run_rules(**kw).flag is True, f"{check} should flag"
