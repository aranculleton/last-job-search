"""The field tables say whose titles and tools they hold, and setup researches the local ones.

Every field table's titles and tools are one list from a US source (O*NET), printed for every
country with no source and no language. A graduate nurse in Recife was handed "Staff Nurse"
and "Staff RN" and the systems US hospitals use, told the titles were "a start", and nothing
sent the research agent for "Enfermeiro(a)" or the local systems. The brief now labels them
and names the country's languages, and the research list asks for the local titles and
tools. A copy whose searches were seeded with those English titles in a market that posts in
another language is told so by the market-language upgrade.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import markets  # noqa: E402
import person  # noqa: E402
import profile_upgrades as U  # noqa: E402


def test_a_non_english_market_is_told_the_titles_are_us_english():
    text = markets.brief("br", field="healthcare-nursing", level="graduate", city="Recife")
    assert "Languages: pt" in text
    titles = next(ln for ln in text.splitlines() if ln.startswith("Titles"))
    assert "US English" in titles and "O*NET" in titles
    tools = next(ln for ln in text.splitlines() if ln.startswith("Interchangeable tools"))
    assert "US English" in tools
    gaps = text.split("Still to research:")[1]
    assert "the titles this work is posted under in Portuguese" in gaps
    assert "the tools employers in Brazil use" in gaps


def test_an_english_market_reads_them_as_they_are():
    text = markets.brief("us", field="healthcare-nursing", level="graduate")
    assert "US English" not in text
    assert "posted under in" not in text.split("Still to research:")[1]


def test_a_search_seeded_with_the_english_titles_is_an_upgrade(monkeypatch):
    class Search:
        SCRAPE_QUERIES = ["staff nurse", "charge nurse"]
        INTERNAL_ONLY = INTERNAL_ONLY_TITLE = CANARY_QUERY = object()

    monkeypatch.setattr(person, "country", lambda: "BR")
    monkeypatch.setattr(U, "_missing", lambda *a, **k: [])
    real = person.module
    monkeypatch.setattr(person, "module", lambda n: Search if n == "search" else real(n))
    assert "staff nurse" in U._market_language()
    Search.SCRAPE_QUERIES = ["enfermeiro", "técnico de enfermagem", "staff nurse"]
    assert U._market_language() == ""
    monkeypatch.setattr(person, "country", lambda: "US")
    Search.SCRAPE_QUERIES = ["staff nurse"]
    assert U._market_language() == ""
