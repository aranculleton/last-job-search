#!/usr/bin/env python3
"""Does this employer clear the bar the profile sets?

A candidate's bar is a rule they have stated: the kind of employer worth an
application. Left in prose it is applied by eye, every round, by a model paid to
strike the same employers out again; a rule a person has stated twice belongs
in code. The bar itself, the employers it names and the reasons printed are
the profile's (search.py, BAR_*); this module reads them and applies them in a
fixed order. A verdict of pay, prestige or signal clears the bar; none does not.

Verdicts, first match wins:

  excluded  a hard rule the profile states: a sector (BAR_EXCLUDED), an
            employer declined by name (BAR_DECLINED), a public-sector agency
            named outright (BAR_NAMED_PUBLIC), or any other public body unless
            the posting states a range that reaches the target band
            (BAR_PUBLIC). Public-adjacent employers on the profile's target
            list (BAR_PUBLIC_TARGETS) never land here.
  pay       a stated range whose midpoint reaches the target band, or a tier-1
            employer, whose pay is top of market by definition.
  prestige  a tier-2 employer, a public body the profile names as a prestige
            exception (BAR_PUBLIC_PRESTIGE), or a target-list public-adjacent
            employer.
  signal    frontier AI (BAR_FRONTIER), elite-VC and YC-backed, or an
            established technology company: the name that says where the next
            move is going rather than how big the employer is.
  none      none of the three. FLAGGED, NOT CUT. An unknown name with no stated
            range is exactly the case where the posting knows more than this
            file, and "rank down, do not cut" still holds for everything except
            the stated hard rules.

    python3 tools/bar.py "Quayside Foods" "City of Somewhere" "Acme AI"
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from company_key import key as company_key  # noqa: E402
from opportunity import YC_AND_BACKED, _names_in, tier  # noqa: E402
from sector import TECH_COMPANIES  # noqa: E402
from text_screen import salary_range  # noqa: E402

EXCLUDED, PAY, PRESTIGE, SIGNAL, NONE = "excluded", "pay", "prestige", "signal", "none"

import person  # noqa: E402

_S = person.module("search")
CUR = getattr(_S, "CURRENCY_SYMBOL", "$")
TARGET_MIDPOINT = getattr(_S, "BAR_TARGET_MIDPOINT", _S.SALARY_TARGET)
_NEVER = re.compile(r"(?!x)x")
EXCLUDED_RULES = list(getattr(_S, "BAR_EXCLUDED", []))
DECLINED = dict(getattr(_S, "BAR_DECLINED", {}))
PUBLIC_PRESTIGE, _PRESTIGE_WHY = getattr(_S, "BAR_PUBLIC_PRESTIGE", (_NEVER, ""))
PENSIONS, _TARGETS_WHY = getattr(_S, "BAR_PUBLIC_TARGETS", (_NEVER, ""))
NAMED_PUBLIC, _NAMED_WHY = getattr(_S, "BAR_NAMED_PUBLIC", (_NEVER, ""))
PUBLIC, _PUBLIC_PAID, _PUBLIC_WHY = getattr(_S, "BAR_PUBLIC", (_NEVER, "", ""))
# A different company wearing a tiered company's name: `_names_in` matches a
# short tiered name inside a longer, unrelated one.
COLLISIONS = getattr(_S, "BAR_COLLISIONS", _NEVER)
FRONTIER = set(getattr(_S, "BAR_FRONTIER", ()))


def excluded_by_name(company: str | None) -> str:
    """Why the employer's name alone excludes it, or "".

    The bar's rules that read nothing but the name: an excluded sector, an
    employer declined by name, a public agency named outright. The prefilter
    applies these before hydrate fetches a body nobody will read. A public body
    with a well-paid posting (BAR_PUBLIC) needs the posting, so it is not here.
    """
    name = str(company or "")
    k = company_key(name)
    both = f"{name} {k}"
    for rx, why in EXCLUDED_RULES:
        if rx.search(both):
            return why
    if k in DECLINED:
        return DECLINED[k]
    if PUBLIC_PRESTIGE.search(both) or PENSIONS.search(both):
        return ""
    return _NAMED_WHY if NAMED_PUBLIC.search(both) else ""


def verdict(company: str | None, posting: str = "") -> tuple[str, str]:
    """(verdict, reason). See the module docstring for the order and meaning."""
    name = str(company or "")
    k = company_key(name)
    both = f"{name} {k}"
    lo, hi, _ = salary_range(posting or "")
    mid = (lo + hi) // 2 if lo and hi else None
    paid = mid is not None and mid >= TARGET_MIDPOINT

    why = excluded_by_name(company)
    if why:
        return EXCLUDED, why
    if PUBLIC_PRESTIGE.search(both):
        return PRESTIGE, _PRESTIGE_WHY
    if PENSIONS.search(both):
        pass  # a target-list public-adjacent employer is never public sector
    elif PUBLIC.search(both):
        if paid:
            return PAY, _PUBLIC_PAID.format(cur=CUR, mid=mid, target=TARGET_MIDPOINT)
        return EXCLUDED, _PUBLIC_WHY

    collided = bool(COLLISIONS.search(both))
    score, why = (0, "") if collided else tier(name)
    if score >= 30:
        return PAY, f"{why}; top-of-market pay"
    if paid:
        return PAY, f"stated range midpoint {CUR}{mid:,} reaches the {CUR}{TARGET_MIDPOINT:,} target band"
    if score >= 20:
        return PRESTIGE, why
    if PENSIONS.search(both):
        return PRESTIGE, _TARGETS_WHY
    if not collided:
        c = f" {k} "
        hit = _names_in(c, FRONTIER)
        if hit:
            return SIGNAL, f"frontier AI ({hit})"
        hit = _names_in(c, YC_AND_BACKED)
        if hit:
            return SIGNAL, f"YC or top-tier backed ({hit})"
        hit = _names_in(c, TECH_COMPANIES)
        if hit:
            return SIGNAL, f"established technology company ({hit})"
    if score < 0:
        return NONE, why
    return NONE, "no stated range at the target band, and not a name on the tier, frontier or backed lists"


def clears(company: str | None, posting: str = "") -> bool:
    return verdict(company, posting)[0] in (PAY, PRESTIGE, SIGNAL)


if __name__ == "__main__":  # pragma: no cover
    for n in sys.argv[1:]:
        v, why = verdict(n)
        print(f"{n:<34} {v:<9} {why}")
