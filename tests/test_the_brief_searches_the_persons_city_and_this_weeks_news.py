"""The brief's news searches name the person's own place and ask for this week's news.

Two runs on 10 November found no news: the location "Toronto, ON" gave the searches its last
part, so they read "<employer> ON news November 2026", and the first week of a month carried no
time words at all, so results were job boards and evergreen pages (audit BT-5). The place is
now the city where the last part is a province or state code, and every search the brief makes
for an employer asks for news by its words. Invented employers.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import brief  # noqa: E402
import person  # noqa: E402

TIME_WORDS = ("this week", "November 2026", "news", "announces")


@pytest.mark.parametrize("where, place", [
    ("Toronto, ON", "Toronto"),
    ("Austin, TX", "Austin"),
    ("Toronto, ON, Canada", "Canada"),
    ("Manchester, UK", "UK"),
    ("Lyon, France", "France"),
    ("Toronto", ""),
])
def test_the_place_is_the_city_where_the_last_part_is_a_region_code(monkeypatch, where, place):
    monkeypatch.setattr(person, "get", lambda key, default=None: where
                        if key == "identity.location" else default)
    assert brief.home_place() == place


@pytest.mark.parametrize("day", [dt.date(2026, 11, 2), dt.date(2026, 11, 20)])
def test_every_search_asks_for_news_by_its_words(monkeypatch, day):
    monkeypatch.setattr(brief, "home_place", lambda: "Toronto")
    monkeypatch.setattr(brief, "resting", lambda today, got=None: set())
    watch = [{"what": "Larkspur Retail pay deal", "every": "day"}]
    qs = brief.queries(day, ["Larkspur Retail", "Copperleaf Pay"], watch, searched={})
    wide = brief.wider(day, ["Larkspur Retail", "Copperleaf Pay"], watch, qs)
    assert qs and wide
    for q in qs:
        assert " ON " not in f" {q} "
        assert any(w in q for w in ("this week", day.strftime("%B %Y"))), q
    for q in wide:
        if q.startswith(("Larkspur Retail", "Copperleaf Pay")) and "pay deal" not in q:
            assert "announces" in q or "news" in q, q
    assert "Larkspur Retail Toronto news" in " | ".join(qs + wide)
