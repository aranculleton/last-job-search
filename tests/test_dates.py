"""One reading of a date, and the eight helpers that used to have their own.

`tools/dates.py` is the definition. The helpers that remain (state, discovery,
reading, why, followups, prefilter, throttle, what_works) keep their names and
signatures and each is one of its three readings. Every shape below was run
through the old bodies of all eight on Python 3.10 and 3.13 before they were
replaced; the table holds what they read then, except in the ways CHANGED
lists, one input for each, and each of those was a bug.

The one that started it: `reading._days` read `2026-10-17T10:00:00` as undated
while `why._age` read the same post on the same reading as ten days old, so a
person was "active" to one and had nothing to hook a note on to the other.
"""
from __future__ import annotations

import ast
import datetime as dt
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import dates  # noqa: E402
import discovery  # noqa: E402
import followups  # noqa: E402
import prefilter  # noqa: E402
import reading  # noqa: E402
import state  # noqa: E402
import throttle  # noqa: E402
import what_works  # noqa: E402
import why  # noqa: E402

TODAY = dt.date(2026, 10, 17)
D = dt.date(2026, 10, 1)
FULLWIDTH = "２０２６-１０-０１"

# Every shape one of the eight was given, and what each reading takes from it:
# (value, as_date, iso_only, iso_only and anywhere).
SHAPES = [
    (D, D, D, D),
    (dt.datetime(2026, 10, 1, 9, 30), D, D, D),
    (None, None, None, None),
    ("", None, None, None),
    ("   ", None, None, None),
    (0, None, None, None),
    (2026, None, None, None),
    (1760000000, None, None, None),                 # an epoch
    (b"2026-10-01", None, None, D),
    ("None", None, None, None),
    # ISO, and ISO with a time after it
    ("2026-10-01", D, D, D),
    ("2026-10-01T09:30:00", D, D, D),
    ("2026-10-01T09:30:00Z", D, D, D),
    ("2026-10-01T09:30:00.000Z", D, D, D),
    ("2026-10-01T09:30:00+01:00", D, D, D),
    ("2026-10-01T", D, D, D),
    ("2026-10-01t09:30", D, D, D),
    ("2026-10-01 09:30:00", D, D, D),
    (" 2026-10-01 ", D, D, D),
    ("\t2026-10-01\n", D, D, D),
    ("2026-10-01 (edited)", D, D, D),
    ("2026-10-011", D, D, D),
    # an ISO date inside text: state's rows only
    ("sent 2026-10-01", None, None, D),
    ("between 2026-10-01 and 2026-10-05", None, None, D),
    ("2026-02-30 then 2026-03-01", None, None, None),   # the first date, never the next one
    # impossible dates
    ("2026-02-30", None, None, None),
    ("2026-13-01", None, None, None),
    ("0000-01-01", None, None, None),
    # the formats a search snippet writes: discovery's
    ("2026-10", D, None, None),
    ("2026-1-7", dt.date(2026, 1, 7), None, None),
    ("2026-10-1", D, None, None),
    ("2026-1-7T10:00", dt.date(2026, 1, 7), None, None),
    ("2026/10/01", D, None, None),
    ("2026/10/01T09:30", D, None, None),
    ("1 October 2026", D, None, None),
    ("01 October 2026", D, None, None),
    ("1  October   2026", D, None, None),
    ("October 2026", D, None, None),
    ("Oct 2026", D, None, None),
    ("oct 2026", D, None, None),
    ("OCTOBER 2026", D, None, None),
    ("1 OCTOBER 2026", D, None, None),
    ("OCT 2026", D, None, None),
    # never a date
    ("Sept 2026", None, None, None),
    ("2 weeks ago", None, None, None),
    ("10/01/2026", None, None, None),
    ("01/10/2026", None, None, None),
    ("20261001", None, None, None),
    (20261001, None, None, None),
    ("2026-W40-4", None, None, None),
    ("2026-W40", None, None, None),
    ("2026W404", None, None, None),
    ("2026-274", None, None, None),
    (FULLWIDTH, None, None, None),
]


def _age(d):
    return None if d is None else (TODAY - d).days


CALL = {
    "state.as_date": state.as_date,
    "discovery._as_date": discovery._as_date,
    "followups._iso": followups._iso,
    "what_works._date": what_works._date,
    "reading._days": lambda v: reading._days(v, TODAY),
    "why._age": lambda v: why._age(v, TODAY),
    "prefilter.age_days": lambda v: prefilter.age_days({"date": v}, TODAY),
    "throttle._row_age_days": lambda v: throttle._row_age_days({"date": v}, TODAY),
}

# Where a helper read something else before. (helper, value, before, now)
CHANGED = [
    # A timestamp, a date object, padding or a note after the date: undated to
    # reading, which neither sliced to ten characters nor stripped.
    ("reading._days", "2026-10-01T09:30:00", None, 16),
    ("reading._days", "2026-10-01T09:30:00Z", None, 16),
    ("reading._days", "2026-10-01 09:30:00", None, 16),
    ("reading._days", "2026-10-01 (edited)", None, 16),
    ("reading._days", "2026-10-01 ", None, 16),
    ("reading._days", D, None, 16),
    # Leading whitespace: followups, what_works and throttle stripped it, and
    # why and prefilter did not.
    ("why._age", " 2026-10-01", None, 16),
    ("prefilter.age_days", " 2026-10-01", None, 16),
    # discovery split on every "T" and wanted the rest to be a whole format.
    ("discovery._as_date", "2026-10-01 09:30:00", None, D),
    ("discovery._as_date", "2026-10-01t09:30", None, D),
    ("discovery._as_date", "2026-10-01 (edited)", None, D),
    ("discovery._as_date", "OCT 2026", None, D),
    ("discovery._as_date", "1 OCTOBER 2026", None, D),
    # Anything but text or a date raised.
    ("discovery._as_date", 2026, "AttributeError", None),
    ("discovery._as_date", b"2026-10-01", "TypeError", None),
    ("throttle._row_age_days", D, "AttributeError", 16),
    ("throttle._row_age_days", 2026, "AttributeError", None),
    # date.fromisoformat takes these from Python 3.11 only, so the six helpers
    # built on it read them on 3.13 and not on CI's 3.10.
    ("followups._iso", "20261001", "D on 3.11+", None),
    ("what_works._date", "2026-W40-4", "D on 3.11+", None),
    ("why._age", "2026-W40", "19 on 3.11+", None),
    ("prefilter.age_days", 20261001, "16 on 3.11+", None),
    ("reading._days", "2026W404", "16 on 3.11+", None),
    ("throttle._row_age_days", "20261001", "16 on 3.11+", None),
    # Digits that are not ASCII: state's regex took any Unicode digit.
    ("state.as_date", FULLWIDTH, D, None),
]


@pytest.mark.parametrize("value,default,iso,anywhere", SHAPES)
def test_the_three_readings(value, default, iso, anywhere):
    assert dates.as_date(value) == default
    assert dates.as_date(value, iso_only=True) == iso
    assert dates.as_date(value, iso_only=True, anywhere=True) == anywhere


@pytest.mark.parametrize("value,default,iso,anywhere", SHAPES)
def test_every_helper_is_one_of_the_three(value, default, iso, anywhere):
    assert state.as_date(value) == anywhere
    assert discovery._as_date(value) == default
    for name in ("followups._iso", "what_works._date"):
        assert CALL[name](value) == iso, name
    for name in ("reading._days", "why._age", "prefilter.age_days", "throttle._row_age_days"):
        assert CALL[name](value) == _age(iso), name


@pytest.mark.parametrize("helper,value,before,now", CHANGED)
def test_what_changed_reads_as_it_now_should(helper, value, before, now):
    assert CALL[helper](value) == now


def test_a_timestamped_post_is_a_hook_and_activity_alike():
    """The same reading, through reading and why: the post is ten days old to both."""
    post = {"kind": "post", "date": "2026-10-07T10:00:00", "url": "",
            "text": "Our planning team at Oakmere Foods is growing this winter."}
    got = reading.hooks({"items": [post]}, TODAY)
    assert [h[1] for h in got] == ["post"]
    assert reading._days(post["date"], TODAY) == why._age(post["date"], TODAY) == 10
    them = why.why_them({"title": "Planning Manager", "company": "Oakmere Foods"},
                        {"items": [post]}, today=TODAY)
    assert any("active" in why_ for _, why_ in them["reasons"])


def test_a_reading_stamped_with_a_time_is_still_fresh():
    r = {"read_on": "2026-10-10T08:15:00", "sources": [{"kind": "paste"}]}
    assert reading.fresh(r, TODAY)
    assert not reading.fresh({**r, "read_on": "2026-08-01T08:15:00"}, TODAY)


def test_days_since():
    assert dates.days_since("2026-10-10", TODAY) == 7
    assert dates.days_since("2026-10-20", TODAY) == -3
    assert dates.days_since("2026-10-10", "2026-10-17") == 7
    assert dates.days_since(dt.datetime(2026, 10, 10, 23, 59), TODAY) == 7
    assert dates.days_since(dt.date.today()) == 0
    assert dates.days_since("October 2026", TODAY) == 16
    assert dates.days_since("October 2026", TODAY, iso_only=True) is None
    assert dates.days_since("not a date", TODAY) is None
    with pytest.raises(ValueError):
        dates.days_since("2026-10-10", "not a date")


def test_it_imports_nothing_from_the_app():
    # state imports throttle, so throttle could never import state's reader.
    tree = ast.parse(open(dates.__file__, encoding="utf-8").read())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
             for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree)
              if isinstance(n, ast.ImportFrom) and n.module}
    assert names <= {"__future__", "datetime", "re"}, names
