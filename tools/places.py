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
    places.region_takes_in_home("Remote (US, EMEA)")   # (True, "EMEA") for somebody in the UK
    places.code_is_home("U.K.")   # a code naming the person's own country, however written
    places.known_country_in("remote, japan")      # a country the profile's list leaves out
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


def region_takes_in_home(text: str, keep=None) -> tuple:
    """(True, the region) when a region `text` names takes in home, (False, the first) when
    every one it names leaves home out, (None, "") when that cannot be told or it names none.

    The one reading of a list of regions, for the location gate (tools/prefilter.py) and
    the residence cut (tools/text_screen.py): "Remote - North America or EMEA" is remote
    from the UK, whichever region is written first. `keep(match)` False leaves a match
    out, for a reader that asks only about some of them (a region followed by "time
    zones" asks for hours, not a home)."""
    found = [(m.group(0), region_includes_home(m.group(0)))
             for m in REGION_WORDS.finditer(text or "") if keep is None or keep(m)]
    for region, inside in found:
        if inside is True:
            return True, region
    if found and all(inside is False for _, inside in found):
        return False, found[0][0]
    return None, ""


# A country code as a posting writes it, to the country it names, and the names that
# country goes by. Home was recognised only through the profile's own home_country_rx,
# so a person whose pattern left out the bare code ("united states|usa") read "Remote,
# US" and "US residents only" as somewhere else, and failed or cut them.
CODE_COUNTRY = {"US": "US", "USA": "US", "U.S.": "US", "U.S.A.": "US", "UK": "GB", "U.K.": "GB"}
COUNTRY_NAMES = {"US": ("united states", "united states of america", "usa", "us", "america"),
                 "GB": ("united kingdom", "great britain", "britain", "uk", "gb")}


def _own_code() -> str:
    try:
        c = person.country()
    except Exception:                    # no profile
        return ""
    return CODE_COUNTRY.get(c, c)


def code_is_home(code: str) -> bool:
    """Does a country code as written ("US", "U.K.") name the person's own country?"""
    c = CODE_COUNTRY.get(str(code or "").strip().upper())
    if not c:
        return False
    if c == _own_code():
        return True
    return HOME_COUNTRY_RX is not _NEVER and any(HOME_COUNTRY_RX.search(n)
                                                 for n in COUNTRY_NAMES.get(c, ()))


def code_names(code: str, pattern) -> bool:
    """Does `pattern` (a neighbour's words, say) name the country a code stands for?"""
    c = CODE_COUNTRY.get(str(code or "").strip().upper())
    return bool(c) and any(pattern.search(n) for n in COUNTRY_NAMES.get(c, ()))


def home_code_in(text: str) -> bool:
    """Does `text` name the person's own country by its code, in capitals?"""
    return any(code_is_home(m.group(0)) for m in COUNTRY_CODES.finditer(text or ""))


# Every country the region table names, for a reader that meets one the profile's own
# list (LOCATION other_countries) leaves out: "Remote - Canada" passed clean for somebody
# in Germany, while an on-site place there was flagged as not recognised. The short codes
# are left to COUNTRY_CODES, which reads them in capitals.
KNOWN_COUNTRIES = tuple(sorted({n for ms in REGION_MEMBERS.values() for n in ms if len(n) > 3},
                               key=len, reverse=True))


def known_country_in(text: str):
    """The first country from the region table `text` names that is not home, or None."""
    low = str(text or "").lower()
    for c in KNOWN_COUNTRIES:
        if (c not in REGIONS and not HOME_COUNTRY_RX.search(c)
                and re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", low)):
            return c
    return None


# The states and provinces a remote location is anchored to, and the country each is in.
# "Remote, CA", "Remote - CA" and "Remote, California" passed clean for somebody in the UK,
# Germany or India: the gate knew countries and regions, and a state is neither. A code
# is read as a posting writes it, as a whole part in capitals: "IN" is Indiana, "DE"
# Delaware and "CA" California, and a code that is also the person's own country's
# ("CA" for somebody in Canada, "IN" in India, "DE" in Germany) is left to the reading
# of their own country.
_US_STATES = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas", "CA": "california",
    "CO": "colorado", "CT": "connecticut", "DE": "delaware", "DC": "district of columbia",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho", "IL": "illinois",
    "IN": "indiana", "IA": "iowa", "KS": "kansas", "KY": "kentucky", "LA": "louisiana",
    "ME": "maine", "MD": "maryland", "MA": "massachusetts", "MI": "michigan",
    "MN": "minnesota", "MS": "mississippi", "MO": "missouri", "MT": "montana",
    "NE": "nebraska", "NV": "nevada", "NH": "new hampshire", "NJ": "new jersey",
    "NM": "new mexico", "NY": "new york", "NC": "north carolina", "ND": "north dakota",
    "OH": "ohio", "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island",
    "SC": "south carolina", "SD": "south dakota", "TN": "tennessee", "TX": "texas",
    "UT": "utah", "VT": "vermont", "VA": "virginia", "WA": "washington",
    "WV": "west virginia", "WI": "wisconsin", "WY": "wyoming"}
_CA_PROVINCES = {
    "AB": "alberta", "BC": "british columbia", "MB": "manitoba", "NB": "new brunswick",
    "NL": "newfoundland and labrador", "NS": "nova scotia", "NT": "northwest territories",
    "NU": "nunavut", "ON": "ontario", "PE": "prince edward island", "QC": "quebec",
    "SK": "saskatchewan", "YT": "yukon"}
_AU_STATES = {
    "NSW": "new south wales", "VIC": "victoria", "QLD": "queensland",
    "WA": "western australia", "SA": "south australia", "TAS": "tasmania",
    "ACT": "australian capital territory", "NT": "northern territory"}


def _subdivisions() -> tuple:
    """({code: countries}, {name: countries}) for every state and province above."""
    codes: dict = {}
    names: dict = {}
    for cc, table in (("US", _US_STATES), ("CA", _CA_PROVINCES), ("AU", _AU_STATES)):
        for code, name in table.items():
            codes.setdefault(code, set()).add(cc)
            names.setdefault(name, set()).add(cc)
    return codes, names


SUBDIVISION_CODES, SUBDIVISION_NAMES = _subdivisions()
# A location's parts, split the way the location gate splits them (prefilter._SPLIT).
_PART_SPLIT = re.compile(r"\s*(?:,|\||/|&|\(|\)|\s[-\u2013]\s)\s*")


def subdivision_abroad(location: str, own: str = ""):
    """The state or province a location names, as written, when it is in another country
    and the profile does not place it (LOCATION regions), or None.

    Read part by part, the way the location gate splits a location: "Remote, CA" and
    "Remote - California" name California, which is abroad for somebody in the UK. A
    state of the person's own country is home ("Remote, TX" for somebody in the US), and
    so is one that could be ("WA" is Washington or Western Australia). `own` is the
    person's country code, read from the profile when not given."""
    own = CODE_COUNTRY.get(str(own or "").upper(), str(own or "").upper()) or _own_code()
    for part in _PART_SPLIT.split(str(location or "")):
        p = part.strip()
        if not p or p.lower() in REGIONS:
            continue
        if p in SUBDIVISION_CODES:              # a code, in capitals as written
            if p == own:
                continue
            where = SUBDIVISION_CODES[p]
        else:
            where = SUBDIVISION_NAMES.get(p.lower())
        if where and own not in where:
            return p
    return None


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
