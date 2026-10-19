#!/usr/bin/env python3
"""The person's places, read once from the job search's location spec.

Where the person will work is written down once, in profile/search.py
LOCATION: the home metro, the regions, the home country and the countries
that are not home. Three tools matched places, and each kept a list of its
own: the prefilter's location gate read LOCATION, the text screen read part of
it and added a hard-coded list of shorthand, and the person-finder kept a
second metro in networking.py that drifted from the first (the example's
search metro named towns its networking metro did not, so a contact in one of
them read as out of market).

This module is the lists; each tool keeps its own matching, because each asks
a different question. The prefilter's location gate (`prefilter.location_verdict`)
reads the whole spec itself, and these lists are the same values it reads.

Usage:
    import places
    places.METRO                  # the home metro, as the gate matches it
    places.OTHER_COUNTRIES        # countries that are not home, lower case
    places.HOME_COUNTRY_RX.search("based in the uk")
    places.abroad_short("remote within the US")   # codes in capitals: "us" is a pronoun
    places.metro_with(own)        # a tool's own metro list joined to the search's
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

_NEVER = re.compile(r"(?!x)x")

try:
    _S = person.module("search")
except Exception:                       # no profile, or no search.py
    _S = None

# The spec itself, empty when the profile has none.
LOCATION = dict(getattr(_S, "LOCATION", None) or {})
# The home metro's places, as the location gate matches them.
METRO = tuple(LOCATION.get("metro") or ())
# A region as a location writes it, to its code ("england": "England").
REGIONS = dict(LOCATION.get("regions") or {})
# The countries a location or a sentence may name that are not home.
OTHER_COUNTRIES = tuple(str(c).lower() for c in LOCATION.get("other_countries") or ())
# The home country as a location or a sentence names it; unset, nothing is home.
HOME_COUNTRY_RX = LOCATION.get("home_country_rx") or _NEVER
# The shorthand a sentence or a location uses for somewhere other than one
# country ("the US", "the EU", "EMEA"). Read only after HOME_COUNTRY_RX, so
# "based in the UK" is home for somebody whose home country pattern names the UK.
#
# The codes are read as written, in capitals. Lower-cased, "us" is the pronoun:
# "You must be based in Manchester and able to join us in the office" was cut
# as a requirement to live abroad. A country code names one country; a region
# code may take in the home country, so a reader treats the two differently.
COUNTRY_CODES = re.compile(r"(?<![A-Za-z.])(?:U\.S\.(?:A\.)?|USA|US|U\.K\.|UK)(?![A-Za-z])")
REGION_CODES = re.compile(r"(?<![A-Za-z])(?:EU|EMEA|APAC|LATAM)(?![A-Za-z])")
# The same places written out, in any case.
ABROAD_WORDS = re.compile(r"\b(?:united states|united kingdom|europe)\b", re.I)


# Which countries each region a posting names takes in, so a requirement to live in a
# region cuts only somebody whose country is outside it. "Must be based in EMEA" cut a
# candidate in the UK, which is in EMEA, and "based in North America" reads the same for
# one in Canada. A country in none of these lists is unknown: such a region never cuts.
_EU = ("austria belgium bulgaria croatia cyprus czechia czech republic denmark estonia "
       "finland france germany greece hungary ireland italy latvia lithuania luxembourg "
       "malta netherlands poland portugal romania slovakia slovenia spain sweden")
_EUROPE_MORE = ("united kingdom uk great britain britain england scotland wales northern "
                "ireland norway switzerland iceland liechtenstein serbia ukraine albania bosnia "
                "montenegro north macedonia moldova andorra monaco san marino kosovo")
_MIDDLE_EAST_AFRICA = ("turkey israel united arab emirates uae saudi arabia qatar kuwait bahrain "
                       "oman jordan lebanon egypt south africa nigeria kenya ghana morocco "
                       "tunisia ethiopia rwanda uganda tanzania senegal")
_NORTH_AMERICA = "united states usa us canada mexico"
_LATAM = ("mexico brazil argentina chile colombia peru uruguay paraguay bolivia ecuador "
          "venezuela costa rica panama guatemala dominican republic")
_APAC = ("australia new zealand india china japan singapore south korea korea hong kong "
         "taiwan philippines indonesia malaysia thailand vietnam pakistan bangladesh sri lanka")


def _members(*groups: str) -> tuple:
    """Country names in a group, longest first so "northern ireland" reads before "ireland"."""
    names = set()
    for g in groups:
        words = g.split()
        i = 0
        while i < len(words):
            # Multi-word names are written joined in the lists above only where they are
            # one country; read greedily against a known set of two- and three-word names.
            for n in (3, 2, 1):
                cand = " ".join(words[i:i + n])
                if n == 1 or cand in _MULTI:
                    names.add(cand)
                    i += n
                    break
    return tuple(sorted(names, key=len, reverse=True))


_MULTI = {"czech republic", "united kingdom", "great britain", "northern ireland",
          "north macedonia", "san marino", "united arab emirates", "saudi arabia",
          "south africa", "united states", "costa rica", "dominican republic",
          "new zealand", "south korea", "hong kong", "sri lanka"}
REGION_MEMBERS = {
    "eu": _members(_EU), "european union": _members(_EU),
    "europe": _members(_EU, _EUROPE_MORE),
    "emea": _members(_EU, _EUROPE_MORE, _MIDDLE_EAST_AFRICA),
    "north america": _members(_NORTH_AMERICA),
    "americas": _members(_NORTH_AMERICA, _LATAM), "the americas": _members(_NORTH_AMERICA, _LATAM),
    "latam": _members(_LATAM), "latin america": _members(_LATAM),
    "apac": _members(_APAC), "asia pacific": _members(_APAC), "asia-pacific": _members(_APAC),
}
REGION_WORDS = re.compile(r"(?<![A-Za-z])(?:EU|EMEA|APAC|LATAM)(?![A-Za-z])|\b(?:european union|"
                          r"europe|north america|(?:the )?americas|latin america|"
                          r"asia[ -]pacific)\b", re.I)


def region_includes_home(region: str):
    """True when the region takes in the person's home country, False when it does not,
    None when that cannot be told (no home country, or one this table does not place)."""
    members = REGION_MEMBERS.get(str(region or "").strip().lower())
    if members is None or HOME_COUNTRY_RX is _NEVER:
        return None
    if any(HOME_COUNTRY_RX.search(m) for m in members):
        return True
    placed = any(HOME_COUNTRY_RX.search(m) for ms in REGION_MEMBERS.values() for m in ms)
    return False if placed else None


def abroad_short(sentence: str):
    """The first shorthand for somewhere abroad in `sentence`, as a match, or None."""
    s = sentence or ""
    return COUNTRY_CODES.search(s) or REGION_CODES.search(s) or ABROAD_WORDS.search(s)


def metro_with(own=()) -> tuple:
    """`own` and the search's metro together, each place once, `own` first.

    A tool's own list stays the person's choice and is only ever added to;
    with none, the search's metro is the whole list.
    """
    return tuple(dict.fromkeys((*own, *METRO)))
