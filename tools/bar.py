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
            the stated hard rules. Its reason says when the employer is on none
            of the profile's lists (`listed()` is False): then the verdict says
            nothing about the employer, only that nobody has judged it yet. A
            global bank and a financial-data firm came back "none" for a person
            whose lists were written for another sector, and read as failing the
            bar in networking. Claude judges such a name once and records it
            (`bar.py judge`, profile/employers_judged.json), and every later
            verdict reads the judgement.

    python3 tools/bar.py judge "<company>" <pay|prestige|signal|none> "<why>"
    python3 tools/bar.py unjudged [documents/rounds/<round>.json]

    python3 tools/bar.py "Quayside Foods" "City of Somewhere" "Acme AI"
"""

from __future__ import annotations

import datetime
import glob
import json
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


UNLISTED = ("not on your employer lists yet, so this says nothing about it: judge its pay, "
            "prestige and signal once (`python3 tools/bar.py judge \"<company>\" <verdict> "
            "\"<why>\"`); never a reason to drop it unjudged")
JUDGED_FILE = "employers_judged.json"
_judged_cache: dict = {}


def _judged_path() -> str:
    return person.path(JUDGED_FILE)


def judged() -> dict:
    """The employers judged by `judge`, by company key: {verdict, why, name, date}. The
    profile's tier lists outrank it; it fills only what they leave unnamed."""
    try:
        p = _judged_path()
        m = os.path.getmtime(p)
    except (OSError, person.NoProfile):
        return {}
    if _judged_cache.get("at") != (p, m):
        try:
            with open(p, encoding="utf-8") as fh:
                got = json.load(fh)
        except (OSError, ValueError):
            got = {}
        _judged_cache.update(at=(p, m), rows=got if isinstance(got, dict) else {})
    return _judged_cache["rows"]


def judge(company: str, what: str, why: str, today: str | None = None) -> str:
    """Record a judgement of an employer no list names. Returns the line to say."""
    if what not in (PAY, PRESTIGE, SIGNAL, NONE):
        raise ValueError(f"a judgement is pay, prestige, signal or none, not {what!r}")
    why = " ".join(str(why or "").split())
    if not why:
        raise ValueError("say why, in a few words: it is printed beside every verdict")
    k = company_key(company)
    if not k:
        raise ValueError("no employer name to judge")
    rows = dict(judged())
    rows[k] = {"name": company, "verdict": what, "why": why,
               "date": today or datetime.date.today().isoformat()}
    p = _judged_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(rows.items())), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, p)
    _judged_cache.clear()
    return f"{company}: {what} ({why}), kept in profile/{JUDGED_FILE}"


def listed(company: str | None) -> bool:
    """Whether any of the profile's bar or tier lists names this employer, or it has been
    judged, so that its verdict says something about it."""
    name = str(company or "")
    k = company_key(name)
    both = f"{name} {k}"
    if excluded_by_name(company) or tier(name)[0] or COLLISIONS.search(both) or k in judged():
        return True
    if any(rx.search(both) for rx in (PUBLIC_PRESTIGE, PENSIONS, NAMED_PUBLIC, PUBLIC)):
        return True
    c = f" {k} "
    return bool(_names_in(c, FRONTIER) or _names_in(c, YC_AND_BACKED)
                or _names_in(c, TECH_COMPANIES))


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
    if score < 0 or collided:
        return NONE, why or "a different company wearing a listed employer's name"
    j = judged().get(k)
    if j and j.get("verdict") in (PAY, PRESTIGE, SIGNAL, NONE):
        return j["verdict"], f"judged {j.get('date', '')}: {j.get('why', '')}".replace(" :", ":")
    if mid is not None:
        return NONE, (f"stated range midpoint {CUR}{mid:,} is under the {CUR}{TARGET_MIDPOINT:,} "
                      f"target band, and {UNLISTED}")
    return NONE, f"no stated range, and {UNLISTED}"


def clears(company: str | None, posting: str = "") -> bool:
    return verdict(company, posting)[0] in (PAY, PRESTIGE, SIGNAL)


def unjudged(path: str | None = None) -> list[str]:
    """The employers in a saved shortlist (the newest in documents/rounds/ by default)
    that no list names and nobody has judged, each once, in shortlist order."""
    if not path:
        found = sorted(glob.glob(person.state("documents", "rounds", "*.json")),
                       key=os.path.getmtime)
        if not found:
            return []
        path = found[-1]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data.get("rows", data.get("shortlist", [])) if isinstance(data, dict) else data
    out, seen = [], set()
    for r in rows if isinstance(rows, list) else []:
        name = (r or {}).get("company") if isinstance(r, dict) else None
        k = company_key(name or "")
        if name and k not in seen and not listed(name):
            seen.add(k)
            out.append(name)
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print('usage: python3 tools/bar.py "<company>" ["<company>" ...]\n'
              '       python3 tools/bar.py judge "<company>" <pay|prestige|signal|none> "<why>"\n'
              '       python3 tools/bar.py unjudged [documents/rounds/<round>.json]\n\n'
              + __doc__.strip().split("\n\n")[0])
        return 0 if argv else 2
    if argv[0] == "judge":
        if len(argv) != 4:
            print('usage: python3 tools/bar.py judge "<company>" <pay|prestige|signal|none> "<why>"')
            return 2
        try:
            print(judge(argv[1], argv[2], argv[3]))
        except ValueError as e:
            print(f"bar: {e}")
            return 2
        return 0
    if argv[0] == "unjudged":
        names = unjudged(argv[1] if len(argv) > 1 else None)
        print("\n".join(names) if names else "every employer in the shortlist is on a list or judged")
        return 0
    for n in argv:
        v, why = verdict(n)
        print(f"{n:<34} {v:<9} {why}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
