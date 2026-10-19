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
