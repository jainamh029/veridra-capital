"""ABA routing number checksum (deterministic, no ML).

A US ABA routing number is 9 digits d0..d8. It is well-formed iff
    3*(d0+d3+d6) + 7*(d1+d4+d7) + 1*(d2+d5+d8)  is divisible by 10.
A single altered digit almost always breaks this (the exception is a
compensating multi-digit change), which is why it catches the
`altered_routing_digit` fraud type that the LLM struggles with.
"""

import re


def is_valid_aba(routing) -> bool:
    s = re.sub(r"\D", "", str(routing or ""))
    if len(s) != 9:
        return False
    d = [int(c) for c in s]
    checksum = (
        3 * (d[0] + d[3] + d[6])
        + 7 * (d[1] + d[4] + d[7])
        + 1 * (d[2] + d[5] + d[8])
    )
    return checksum % 10 == 0


def digits_only(routing) -> str:
    return re.sub(r"\D", "", str(routing or ""))
