"""Severity of each individual verification check — an explicit, reviewable table.

Kept in its own module (not inline in the verdict or alert code) so it is a pure,
unit-tested function and cannot be silently changed by an edit to logic elsewhere.

`overall_severity` for a notice is the MAX severity across all failed checks — never
the first-detected one. A notice that fails two checks can never be reported at a
lower tier than its most serious individual finding.
"""

_RANK = {"none": 0, "low": 1, "medium-low": 2, "medium": 3, "high": 4}

# What each check indicates if it FAILS, on its own terms:
#   routing_checksum      - routing number is structurally invalid                -> high
#   baseline_routing_match- payment routing redirected away from the fund's file  -> high
#   baseline_bank_match   - payment redirected to a different receiving bank      -> high
#   sender_domain_match   - sender is a look-alike / unauthorised domain (phish)  -> high
#   entity_name_match     - GP name is a near-miss of the name on file; typos do
#                           happen innocently, so lower confidence on its own     -> medium
#   bank_change_language  - "we changed banks / wire here now" wording; a soft
#                           signal that only matters alongside a bank mismatch    -> medium-low
CHECK_SEVERITY = {
    "routing_checksum": "high",
    "baseline_routing_match": "high",
    "baseline_bank_match": "high",
    "sender_domain_match": "high",
    "entity_name_match": "medium",
    "bank_change_language": "medium-low",
}

ALL_CHECKS = tuple(CHECK_SEVERITY)


def severity_of(check_name: str) -> str:
    return CHECK_SEVERITY.get(check_name, "medium")


def rank(sev: str) -> int:
    return _RANK.get(sev, 0)


def max_severity(check_names) -> str:
    """MAX severity across the given failed-check names. Order-independent:
    a pure function of the SET of names, not their sequence."""
    sevs = [severity_of(c) for c in check_names]
    if not sevs:
        return "none"
    return max(sevs, key=rank)
