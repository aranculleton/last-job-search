"""C++, C# and C in a job title are three roles, not one.

`throttle.title_key` keeps a title's letters and digits only, so "C++ Developer", "C#
Developer" and "C Developer" were all "c developer". That key is the one the search reads
a title by: a relist of a posting seen before (`first_seen`, the age gate), copies of one
posting in a round (`oldest_copies`), a posting already ruled out (`ruled_pair`) and the
role already applied to (`same_title`). So an application to the C++ role held the C# one
at the same employer back, a ruling on one covered the other, and a new C# posting was aged
as the C++ one seen weeks before. Found and fixed in ai-job-search (#830). Every employer is
invented.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import throttle  # noqa: E402

TODAY = dt.date(2026, 11, 10)
ISO = TODAY.isoformat()
LOC = "Manchester, England, United Kingdom"
SEEN = (TODAY - dt.timedelta(days=20)).isoformat()


def posting(url, title, **kw):
    return {"url": url, "title": title, "company": "Wrenfield Systems", "location": LOC,
            "date": ISO, "portal": "linkedin", **kw}


def test_each_language_keeps_its_own_key():
    keys = {throttle.title_key(t) for t in ("Senior C++ Developer", "Senior C# Developer",
                                            "Senior C Developer", "Senior F# Developer")}
    assert len(keys) == 4, keys
    assert throttle.title_key("Developer (C++)") != throttle.title_key("Developer (C#)")
    assert not throttle.same_title("C++ Engineer", "C# Engineer")
    # The same role written two ways is still one.
    assert throttle.same_title("Sr. C++ Engineer (Hybrid)", "Senior C++ Engineer")
    assert throttle.same_title("C# / .NET Developer", "C#/.NET Developer")
    # A plus or a hash standing alone is still nothing.
    assert throttle.title_key("Data + Analytics Lead") == throttle.title_key("Data Analytics Lead")
    assert throttle.title_key("Analyst #2") == throttle.title_key("Analyst 2")


def test_a_ruling_or_a_sighting_of_one_is_not_the_other(monkeypatch):
    # The person's own call holds for about six months from the day they made it
    # (exclude.set_aside_holds, on the person's day): their day is held at the ruling's,
    # which a clock a year on is past (the everywhere check, "400-days").
    monkeypatch.setenv("LJS_TODAY", ISO)
    seen = {"https://boards.example.com/1": {
        "url": "https://boards.example.com/1", "title": "C++ Developer",
        "company": "Wrenfield Systems", "location": LOC, "status": "excluded",
        "basis": "person", "exclusion_reason": "not the kind of work I want",
        "excluded_date": ISO, "first_seen": SEEN}}
    _urls, pairs = throttle.ruled_out(seen)
    assert throttle.ruled_pair(pairs, posting("https://boards.example.com/2", "C++ Developer"))
    assert not throttle.ruled_pair(pairs, posting("https://boards.example.com/3", "C# Developer"))
    of = throttle.first_seen({"u": {**seen["https://boards.example.com/1"], "status": "surfaced"}},
                             ISO)
    assert of(posting("https://boards.example.com/2", "C++ Developer")) == SEEN
    assert of(posting("https://boards.example.com/3", "C# Developer")) == ""


def test_copies_in_a_round_are_only_the_same_language():
    rows = [posting("https://a.example.com/1", "C++ Developer", date=SEEN),
            posting("https://b.example.com/2", "C# Developer")]
    index = throttle.oldest_copies(rows, ISO)
    assert throttle.copy_date(index, rows[0]) == SEEN
    assert throttle.copy_date(index, rows[1]) == ISO
