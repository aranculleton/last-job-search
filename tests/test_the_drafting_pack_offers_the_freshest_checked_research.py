"""The drafting pack offers an employer's freshest checked research, never its oldest.

`draft_pack.cached_research()` handed the drafter the first six facts of the employer's
cache file. `company_research.py --save` appends, so those were the oldest six: research
saved today never reached the drafter or the audit once a file held six facts, and an old
fact whose quote no longer matched its page as fetched today (a spacing change on the
employer's site) was offered as F1, cited, and refused by the code audit as
`research:not-on-page`, while the checked copy saved the same day was never offered
(issue 314).

The cache here is built the way a real run leaves it: `company_research.save` with the pages
`fetch` keeps. Every employer, page and figure is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import company_research  # noqa: E402
import draft_audit  # noqa: E402
import draft_pack  # noqa: E402

COMPANY = "Acme Cloud"
LAST_MONTH, TODAY = "2026-10-20", "2026-11-17"
RELEASE = "https://acme.example/news/release"
OLD_RELEASE = ("Acme, the cloud company, opened its Leeds data centre to customers in "
               "the north this autumn.")
NEW_RELEASE = OLD_RELEASE.replace("Acme,", "Acme ,")


def _old_fact(i: int) -> dict:
    url = f"https://acme.example/news/item-{i}"
    quote = f"Acme Cloud announced item number {i} to its customers this year."
    company_research._store_page(url, "News", "News. " + quote + " Read more.", "page")
    return {"claim": f"Acme Cloud announced item {i}", "quote": quote, "url": url,
            "date_seen": LAST_MONTH}


def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("LJS_RESEARCH_PAGES", str(tmp_path / "pages"))
    # Last month: fifteen facts, the first from the press release as it read then.
    company_research._store_page(RELEASE, "Release", "Press. " + OLD_RELEASE, "page")
    old = [{"claim": "Acme Cloud opened a Leeds data centre", "quote": OLD_RELEASE,
            "url": RELEASE, "date_seen": LAST_MONTH}]
    old += [_old_fact(i) for i in range(2, 16)]
    company_research.save(COMPANY, {"fetched_date": LAST_MONTH, "facts": old},
                          today=LAST_MONTH)
    # Today: the release is read again and now has a space before its comma, and three
    # facts are saved with their quotes checked against the pages as they read today.
    company_research._store_page(RELEASE, "Release", "Press. " + NEW_RELEASE, "page")
    hiring = "https://acme.example/careers/toronto"
    hiring_quote = "Acme Cloud is growing its Toronto analytics team through next year."
    company_research._store_page(hiring, "Careers", "Careers. " + hiring_quote, "page")
    results = "https://acme.example/investors/q3"
    results_quote = "Acme Cloud reported its strongest third quarter for new customers."
    company_research._store_page(results, "Results", "Results. " + results_quote, "page")
    new = [{"claim": "Acme Cloud opened a Leeds data centre", "quote": NEW_RELEASE,
            "url": RELEASE, "date_seen": TODAY},
           {"claim": "Acme Cloud is growing its Toronto analytics team", "quote": hiring_quote,
            "url": hiring, "date_seen": TODAY},
           {"claim": "Acme Cloud had a strong third quarter", "quote": results_quote,
            "url": results, "date_seen": TODAY}]
    company_research.save(COMPANY, {"fetched_date": TODAY, "facts": new}, today=TODAY)
    return new


def test_research_saved_today_is_offered_first(tmp_path, monkeypatch):
    new = _cache(tmp_path, monkeypatch)
    rd = tmp_path / "round"
    rd.mkdir()
    got = draft_pack.cached_research({"company": COMPANY, "slug": "acme"}, str(rd), TODAY)
    assert got is not None
    quotes = [f["quote"] for f in got["facts"]]
    assert quotes[:3] == [f["quote"] for f in new], quotes
    assert len(got["facts"]) == 6
    # What the drafter and the audit read is the same list.
    on_disk = json.loads((rd / "research_acme.json").read_text(encoding="utf-8"))
    assert [f["quote"] for f in on_disk["facts"]] == quotes


def test_a_fact_whose_quote_left_its_page_gives_way_to_the_checked_one(tmp_path, monkeypatch):
    _cache(tmp_path, monkeypatch)
    rd = tmp_path / "round"
    rd.mkdir()
    got = draft_pack.cached_research({"company": COMPANY, "slug": "acme"}, str(rd), TODAY)
    quotes = [f["quote"] for f in got["facts"]]
    assert OLD_RELEASE not in quotes
    assert NEW_RELEASE in quotes
    # Every fact offered is one the code audit lets a letter cite.
    status = draft_audit.research_status(got, COMPANY)
    assert {k: v[0] for k, v in status.items()} == {f"F{i}": "checked"
                                                   for i in range(1, len(quotes) + 1)}


def test_a_checked_fact_comes_before_a_newer_unchecked_one(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("LJS_RESEARCH_PAGES", str(tmp_path / "pages"))
    company_research.save(COMPANY, {"fetched_date": LAST_MONTH,
                                     "facts": [_old_fact(2), _old_fact(3)]}, today=LAST_MONTH)
    # Saved today from a page read another way: no kept page, so nothing checked its quote.
    marathon = "Acme Cloud is the headline sponsor of the city marathon."
    company_research.save(COMPANY, {"fetched_date": TODAY, "facts": [
        {"claim": "Acme Cloud sponsors a city marathon", "date_seen": TODAY,
         "quote": marathon, "url": "https://acme.example/never-kept"}]}, today=TODAY)
    rd = tmp_path / "round"
    rd.mkdir()
    got = draft_pack.cached_research({"company": COMPANY, "slug": "acme"}, str(rd), TODAY)
    quotes = [f["quote"] for f in got["facts"]]
    assert len(quotes) == 3 and quotes[-1] == marathon, quotes
    assert all(f.get("quote_checked") for f in got["facts"][:2])
