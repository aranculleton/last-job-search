#!/usr/bin/env python3
"""Public holidays, worked out by rule, so "business days" skip the days offices close.

    python3 tools/holidays.py [year]          # this person's holidays, for one year

A follow-up "five to seven business days" later counted Canada's Thanksgiving as a
working day, so a nudge fell due a day early. The rules here cover the countries the
app's people have so far and their usual regions, computed for any year (Easter by the
Gregorian computus, "the second Monday of October" by the calendar), never a list of
dates that runs out. The country is profile/person.json identity.country; the region
is read from identity.location ("Toronto, ON, Canada", "Edinburgh, Scotland") unless
profile/search.py HOLIDAY_REGION names it. A country with no rules here, or a holiday
the rules miss, is covered by profile/search.py PUBLIC_HOLIDAYS: ISO dates, kept
for every year given.

A US state's own days (Patriots' Day, Cesar Chavez Day, the day after Thanksgiving where
the state keeps it) are its government's days off, and a private employer may stay
open on them.

A day that falls on a weekend is moved to the next working day where the country
moves it (the UK's substitute days, Canada's observed days, the US's Friday or
Monday), so the day offices are actually closed is the one skipped.
"""
from __future__ import annotations

import datetime as dt
import functools
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

D = dt.date


def easter(year: int) -> dt.date:
    """Western Easter Sunday (the anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month = (h + m - 7 * n + 114) // 31
    return D(year, month, ((h + m - 7 * n + 114) % 31) + 1)


def nth(year: int, month: int, weekday: int, n: int) -> dt.date:
    """The nth `weekday` (Monday 0) of a month; n = -1 is the last."""
    if n > 0:
        first = D(year, month, 1)
        return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    nxt = D(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def monday_before(day: dt.date) -> dt.date:
    """The Monday strictly before `day` (Canada's Victoria Day: before 25 May)."""
    return day - dt.timedelta(days=(day.weekday() - 0) % 7 or 7)


def _shift(days: dict, rule: str) -> dict:
    """Weekend holidays moved to the day offices close instead.
    'next': to the next free weekday (UK, Canada, Ireland, Australia, New Zealand);
    'nearest': Saturday to Friday, Sunday to Monday (US federal)."""
    out = {}
    for day, name in sorted(days.items()):
        if day.weekday() < 5 or rule == "none":
            out.setdefault(day, name)
            continue
        if rule == "nearest":
            moved = day - dt.timedelta(days=1) if day.weekday() == 5 else day + dt.timedelta(days=1)
        else:
            moved = day + dt.timedelta(days=7 - day.weekday())
            while moved in out or moved in days:
                moved += dt.timedelta(days=1)
        out[day] = name
        out.setdefault(moved, f"{name} (observed)")
    return out


def _gb(y: int, region: str) -> dict:
    e = easter(y)
    days = {D(y, 1, 1): "New Year's Day", e - dt.timedelta(days=2): "Good Friday",
            nth(y, 5, 0, 1): "Early May bank holiday", nth(y, 5, 0, -1): "Spring bank holiday",
            D(y, 12, 25): "Christmas Day", D(y, 12, 26): "Boxing Day"}
    if region == "SCT":
        days.update({D(y, 1, 2): "2 January", nth(y, 8, 0, 1): "Summer bank holiday",
                     D(y, 11, 30): "St Andrew's Day"})
    else:
        days.update({e + dt.timedelta(days=1): "Easter Monday",
                     nth(y, 8, 0, -1): "Summer bank holiday"})
        if region == "NIR":
            days.update({D(y, 3, 17): "St Patrick's Day", D(y, 7, 12): "Battle of the Boyne"})
    return _shift(days, "next")


def _ie(y: int, region: str) -> dict:
    e = easter(y)
    feb = D(y, 2, 1) if D(y, 2, 1).weekday() == 4 else nth(y, 2, 0, 1)
    return _shift({D(y, 1, 1): "New Year's Day", feb: "St Brigid's Day",
                   D(y, 3, 17): "St Patrick's Day", e + dt.timedelta(days=1): "Easter Monday",
                   nth(y, 5, 0, 1): "May bank holiday", nth(y, 6, 0, 1): "June bank holiday",
                   nth(y, 8, 0, 1): "August bank holiday", nth(y, 10, 0, -1): "October bank holiday",
                   D(y, 12, 25): "Christmas Day", D(y, 12, 26): "St Stephen's Day"}, "next")


def _ca(y: int, region: str) -> dict:
    e = easter(y)
    days = {D(y, 1, 1): "New Year's Day", e - dt.timedelta(days=2): "Good Friday",
            D(y, 7, 1): "Canada Day", nth(y, 9, 0, 1): "Labour Day",
            D(y, 12, 25): "Christmas Day"}
    if region != "QC":
        days[monday_before(D(y, 5, 25))] = "Victoria Day"
    if region in ("", "ON", "BC", "AB", "SK", "MB", "NB", "NS", "PE", "NL", "YT", "NT", "NU"):
        days[nth(y, 10, 0, 2)] = "Thanksgiving"
    if region in ("ON", "AB", "SK", "BC", "NB", "PE"):
        days[nth(y, 2, 0, 3)] = "Family Day"
    if region in ("ON", "NB", "NS", "PE", "NL"):
        days[D(y, 12, 26)] = "Boxing Day"
    if region in ("ON", "BC", "AB", "SK", "MB", "NB", "NT", "NU"):
        days[nth(y, 8, 0, 1)] = "Civic Holiday"
    if region == "QC":
        days.update({monday_before(D(y, 5, 25)): "National Patriots' Day",
                     D(y, 6, 24): "Saint-Jean-Baptiste Day", nth(y, 10, 0, 2): "Thanksgiving"})
    if region in ("BC", "MB", "SK", "AB", "NB", "PE", "NL", "NT", "NU", "YT"):
        days[D(y, 11, 11)] = "Remembrance Day"
    if region in ("BC", "MB", "SK", "AB", "NB", "PE", "NT", "NU", "YT") or region == "":
        days[D(y, 9, 30)] = "National Day for Truth and Reconciliation" if region == "" else \
            "Truth and Reconciliation Day"
    return _shift(days, "next")


# A state's own holidays, beside the federal ones: the state government's days off. Many
# private employers stay open on them, so they move a follow-up by a day at most.
_US_STATE = {
    "MA": lambda y: {nth(y, 4, 0, 3): "Patriots' Day"},
    "ME": lambda y: {nth(y, 4, 0, 3): "Patriots' Day"},
    "CA": lambda y: {D(y, 3, 31): "Cesar Chavez Day",
                     nth(y, 11, 3, 4) + dt.timedelta(days=1): "Day after Thanksgiving"},
    "TX": lambda y: {nth(y, 11, 3, 4) + dt.timedelta(days=1): "Day after Thanksgiving",
                     D(y, 12, 24): "Christmas Eve", D(y, 12, 26): "Day after Christmas"},
    "NY": lambda y: {D(y, 2, 12): "Lincoln's Birthday"},
    "IL": lambda y: {D(y, 2, 12): "Lincoln's Birthday",
                     nth(y, 11, 3, 4) + dt.timedelta(days=1): "Day after Thanksgiving"},
    "FL": lambda y: {nth(y, 11, 3, 4) + dt.timedelta(days=1): "Day after Thanksgiving"},
    "GA": lambda y: {nth(y, 11, 3, 4) + dt.timedelta(days=1): "Day after Thanksgiving"},
    "WA": lambda y: {nth(y, 11, 3, 4) + dt.timedelta(days=1): "Native American Heritage Day"},
}


def _us(y: int, region: str) -> dict:
    days = {D(y, 1, 1): "New Year's Day", nth(y, 1, 0, 3): "Martin Luther King Jr. Day",
            nth(y, 2, 0, 3): "Presidents' Day", nth(y, 5, 0, -1): "Memorial Day",
            D(y, 6, 19): "Juneteenth", D(y, 7, 4): "Independence Day",
            nth(y, 9, 0, 1): "Labor Day", nth(y, 10, 0, 2): "Columbus Day",
            D(y, 11, 11): "Veterans Day", nth(y, 11, 3, 4): "Thanksgiving",
            D(y, 12, 25): "Christmas Day"}
    if region in _US_STATE:
        days.update(_US_STATE[region](y))
    return _shift(days, "nearest")


def _au(y: int, region: str) -> dict:
    e = easter(y)
    return _shift({D(y, 1, 1): "New Year's Day", D(y, 1, 26): "Australia Day",
                   e - dt.timedelta(days=2): "Good Friday", e + dt.timedelta(days=1): "Easter Monday",
                   D(y, 4, 25): "Anzac Day", D(y, 12, 25): "Christmas Day",
                   D(y, 12, 26): "Boxing Day"}, "next")


def _nz(y: int, region: str) -> dict:
    e = easter(y)
    return _shift({D(y, 1, 1): "New Year's Day", D(y, 1, 2): "Day after New Year's Day",
                   D(y, 2, 6): "Waitangi Day", e - dt.timedelta(days=2): "Good Friday",
                   e + dt.timedelta(days=1): "Easter Monday", D(y, 4, 25): "Anzac Day",
                   nth(y, 6, 0, 1): "King's Birthday", nth(y, 10, 0, 4): "Labour Day",
                   D(y, 12, 25): "Christmas Day", D(y, 12, 26): "Boxing Day"}, "next")


RULES = {"GB": _gb, "UK": _gb, "IE": _ie, "CA": _ca, "US": _us, "AU": _au, "NZ": _nz}

# A region as a location line writes it, to the code the rules above use.
_REGIONS = {
    "CA": {"ON": "ontario", "QC": "quebec|québec", "BC": "british columbia", "AB": "alberta",
           "MB": "manitoba", "SK": "saskatchewan", "NS": "nova scotia", "NB": "new brunswick",
           "NL": "newfoundland(?: and labrador)?", "PE": "prince edward island|p\\.?e\\.?i\\.?",
           "YT": "yukon", "NT": "northwest territories", "NU": "nunavut"},
    "GB": {"SCT": "scotland", "NIR": "northern ireland", "WLS": "wales", "ENG": "england"},
    "US": {"MA": "massachusetts", "ME": "maine", "CA": "california", "TX": "texas",
           "NY": "new york", "IL": "illinois", "FL": "florida", "GA": "georgia",
           "WA": "washington(?![,\\s]*d\\.?\\s*c\\b)"},
}


def region_from(country: str, location: str) -> str:
    """The region code a location line names, or "" (the country's common days)."""
    table = _REGIONS.get("GB" if country == "UK" else country, {})
    loc = str(location or "")
    for code, names in table.items():
        if re.search(r"(?<![A-Za-z])(?:%s)(?![A-Za-z])" % names, loc, re.I) or (
                len(code) == 2 and re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % code, loc)):
            return code
    return ""


def _settings() -> tuple[str, str, tuple]:
    try:
        country = str(person.get("identity.country", "") or "").upper()
        location = str(person.get("identity.location", "") or "")
        search = person.module("search")
    except person.NoProfile:
        return "", "", ()
    region = str(getattr(search, "HOLIDAY_REGION", "") or "").upper() or region_from(country, location)
    extra = tuple(getattr(search, "PUBLIC_HOLIDAYS", ()) or ())
    return country, region, extra


@functools.lru_cache(maxsize=64)
def for_year(year: int, country: str | None = None, region: str | None = None,
             extra: tuple | None = None) -> dict:
    """{date: name} for one year: the rules for the country and region, plus the
    profile's own dates that fall in it."""
    c, r, e = _settings()
    country = (c if country is None else country).upper()
    region = (r if region is None else region).upper()
    extra = e if extra is None else extra
    days = dict(RULES[country](year, region)) if country in RULES else {}
    for iso in extra:
        try:
            day = D.fromisoformat(str(iso)[:10])
        except ValueError:
            continue
        if day.year == year:
            days.setdefault(day, "your own (profile/search.py PUBLIC_HOLIDAYS)")
    return days


# Kept for the people whose own tests call it (profile/tests): nothing in the app reads it,
# and state.business_days_between is the count to use. A public name stays while a test may.
def is_holiday(day: dt.date) -> bool:
    """Is `day` one of this person's public holidays? The next year's table is read too, as
    the business-day count reads it: the US keeps a Saturday New Year's Day on Friday 31
    December, and that day sits in the next year's table."""
    return day in for_year(day.year) or day in for_year(day.year + 1)


def covered() -> bool:
    """Do this person's holidays come from somewhere: the rules or their own list?"""
    country, _region, extra = _settings()
    return country in RULES or bool(extra)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (["-h"], ["--help"]):
        print("usage: python3 tools/holidays.py [year]\n\n" + __doc__.strip().split("\n\n")[0])
        return 0
    year = int(argv[0]) if argv else dt.date.today().year
    country, region, _ = _settings()
    days = for_year(year)
    print(f"public holidays {year}: {country or 'no country on file'}"
          + (f", {region}" if region else "") + ("" if days else ": none known"))
    for day, name in sorted(days.items()):
        print(f"  {day.isoformat()} {day.strftime('%a')}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
