"""Business days skip the person's public holidays, worked out by rule for any year.

From one person's repo: the 5-to-7-business-day follow-up counted Canada's Thanksgiving
(12 October 2026) as a working day. Holidays come from rules (Easter by the computus,
"the second Monday of October" by the calendar), by country and region, with a
profile list for anywhere the rules do not cover.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import holidays as H  # noqa: E402
import state  # noqa: E402

D = dt.date


def test_easter_and_the_nth_weekday_rules():
    assert [H.easter(y) for y in (2024, 2025, 2026, 2027)] == [
        D(2024, 3, 31), D(2025, 4, 20), D(2026, 4, 5), D(2027, 3, 28)]
    assert H.nth(2026, 10, 0, 2) == D(2026, 10, 12)          # second Monday of October
    assert H.nth(2026, 5, 0, -1) == D(2026, 5, 25)           # last Monday of May
    assert H.monday_before(D(2026, 5, 25)) == D(2026, 5, 18)  # Victoria Day


def test_a_province_a_nation_and_a_state_each_get_their_own_days():
    on = H.for_year(2026, "CA", "ON", ())
    assert {D(2026, 2, 16), D(2026, 5, 18), D(2026, 8, 3), D(2026, 10, 12)} <= set(on)
    assert D(2026, 12, 28) in on                              # Boxing Day, a Saturday, moved
    qc = H.for_year(2026, "CA", "QC", ())
    assert D(2026, 6, 24) in qc and D(2026, 2, 16) not in qc
    eng, sct = H.for_year(2026, "GB", "", ()), H.for_year(2026, "GB", "SCT", ())
    assert D(2026, 4, 6) in eng and D(2026, 4, 6) not in sct   # Easter Monday
    assert D(2026, 8, 31) in eng and D(2026, 8, 3) in sct      # Summer bank holiday
    us, tx, ma = (H.for_year(2026, "US", r, ()) for r in ("", "TX", "MA"))
    assert D(2026, 7, 3) in us                                # 4 July, a Saturday, on the Friday
    assert D(2026, 11, 27) in tx and D(2026, 11, 27) not in us
    assert D(2026, 4, 20) in ma                               # Patriots' Day
    assert H.for_year(2026, "ZZ", "", ()) == {}               # no rules: nothing invented


@pytest.mark.parametrize("country,location,region", [
    ("CA", "Toronto, ON, Canada", "ON"), ("CA", "Montréal, Québec", "QC"),
    ("GB", "Edinburgh, Scotland", "SCT"), ("GB", "Manchester, UK", ""),
    ("US", "Austin, TX", "TX"), ("US", "Seattle, Washington", "WA"),
    ("US", "Washington, D.C.", ""), ("US", "Remote", "")])
def test_the_region_is_read_from_where_they_live(country, location, region):
    assert H.region_from(country, location) == region


@pytest.fixture
def ontario(monkeypatch):
    H.for_year.cache_clear()
    monkeypatch.setattr(H, "_settings", lambda: ("CA", "ON", ("2026-10-13",)))
    yield
    H.for_year.cache_clear()


def test_business_days_skip_them(ontario):
    # Friday 9 October to Friday 16 October 2026: Thanksgiving (Monday) and the person's
    # own day off (Tuesday, PUBLIC_HOLIDAYS) are not working days.
    assert state.business_days_between(D(2026, 10, 9), D(2026, 10, 16)) == 3
    assert state.add_business_days(D(2026, 10, 9), 1) == D(2026, 10, 14)
    assert state.business_days_between(D(2026, 10, 16), D(2026, 10, 9)) == -3


def test_without_a_profile_weekends_alone_count(monkeypatch):
    H.for_year.cache_clear()
    monkeypatch.setattr(H, "_settings", lambda: ("", "", ()))
    assert state.business_days_between(D(2026, 10, 9), D(2026, 10, 16)) == 5
    H.for_year.cache_clear()
