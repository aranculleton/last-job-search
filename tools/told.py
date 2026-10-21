#!/usr/bin/env python3
"""Where the person told each employer they are, when it is not one place for every one.

Someone who tells one employer they are in London and another that they are in Toronto
cannot be served from one location: the interview pack printed the profile's city to an
employer that had heard another, and the small talk asked how they were settling into a
city that employer did not know about. Each employer that heard a place of its own is kept
in person.json `identity.places_told` ({employer: place}), joined by company_key, and read
by the interview pack, the call prep and the message checks before the profile's own place.

    python3 tools/told.py                          # every employer and what it heard
    python3 tools/told.py "<Employer>" "<place>"   # record what one heard
    python3 tools/told.py "<Employer>" --clear     # back to the profile's own place
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402
from company_key import key as company_key  # noqa: E402

KEY = "places_told"
# identity.moved and identity.area when the person gives each employer their own answer:
# nothing single is said for everyone, and the place each heard is kept here instead.
PER_EMPLOYER = "per employer"


def places() -> dict:
    """{employer: place} as recorded, or {} when nothing is."""
    try:
        got = person.get("identity.places_told", {})
    except person.NoProfile:
        return {}
    return {str(k): str(v) for k, v in got.items() if str(v).strip()} \
        if isinstance(got, dict) else {}


def place(company: str) -> str:
    """The place this employer was told, or "" when it heard nothing of its own."""
    k = company_key(company or "")
    return next((v for c, v in places().items() if k and company_key(c) == k), "")


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", str(text or "").lower()) if len(w) > 2}


def home() -> str:
    """The person's own place for everyone else: identity.area, else identity.location,
    never a value still marked to confirm or kept per employer."""
    for k in ("identity.area", "identity.location"):
        try:
            v = str(person.get(k, "") or "").strip()
        except person.NoProfile:
            return ""
        if v and "[CONFIRM" not in v and v.lower() != PER_EMPLOYER:
            return v
    return ""


def differs(company: str) -> bool:
    """Did this employer hear a place other than the person's own? Then nothing written for
    the person's own place (a move, settling in, its neighbourhoods) is for this employer."""
    told = place(company)
    return bool(told) and not (_words(told) & _words(home()))


def record(company: str, where: str = "", clear: bool = False) -> str:
    """Write what `company` heard into person.json; returns the line to say."""
    path = person.path("person.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    ident = data.setdefault("identity", {})
    told = {str(k): str(v) for k, v in (ident.get(KEY) or {}).items()}
    k = company_key(company)
    same = [c for c in told if company_key(c) == k]
    for c in same:
        told.pop(c)
    if not clear:
        if not str(where).strip():
            raise ValueError("say the place they were told, or --clear")
        told[company] = " ".join(str(where).split())
    if told:
        ident[KEY] = told
    else:
        ident.pop(KEY, None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    person.reset()
    if clear:
        return ("%s: back to your own place (%s)." % (company, home() or "none recorded")
                if same else "%s: nothing was recorded for it." % company)
    return "%s heard: %s. Packs and message checks for %s use it." % (company, told[company],
                                                                    company)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("company", nargs="?")
    ap.add_argument("place", nargs="?", default="")
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args(argv)
    try:
        if not a.company:
            got = places()
            print("\n".join("%s: %s" % kv for kv in sorted(got.items())) if got else
                  "Every employer hears your own place: %s." % (home() or "none recorded"))
            return 0
        print(record(a.company, a.place, a.clear))
    except person.NoProfile:
        print("told: no profile/ yet: /setup builds one.")
        return 1
    except ValueError as exc:
        print("told: %s" % exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
