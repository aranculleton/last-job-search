"""Research about one country's entity is never read for a posting in another.

`company_key` folds "Acme" and "Acme UK" (or "Acme Canada") into one key, which is what
the joins need: a contact, an application and the research at one employer must meet.
The research cache used the same key, so a US role and a home-country role at one
employer would read one entity's facts. The key stays as it is; research for a posting
in another country than the cached entity's goes to `<key>--<cc>.json` beside it, and
the plain file stays the one the joins read. Every employer here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import company_key  # noqa: E402
import company_research as C  # noqa: E402

UK_FACT = {"claim": "Opened a Bolton bakery", "quote": "We opened our Bolton bakery in 2026.",
           "url": "https://www.oakmere.example.co.uk/news"}
US_FACT = {"claim": "Opened a Chicago plant", "quote": "Our Chicago plant opened in 2026.",
           "url": "https://www.oakmere.example.com/us/news"}


def test_the_join_key_is_unchanged():
    assert company_key.key("Oakmere Foods UK") == company_key.key("Oakmere Foods USA") \
        == company_key.key("Oakmere Foods")


def test_a_posting_abroad_reads_and_writes_its_own_file(tmp_path):
    C.save("Oakmere Foods UK", {"company": "Oakmere Foods UK", "facts": [UK_FACT],
                                "fetched_date": "2026-10-20"}, root=str(tmp_path))
    # A US role at the same employer: nothing of the UK entity's is read as its research.
    assert C.load("Oakmere Foods USA", root=str(tmp_path), country="US") == ({}, None, False)
    written = C.save("Oakmere Foods USA", {"facts": [US_FACT]}, root=str(tmp_path), country="US")
    assert Path(written).name == "oakmere-foods--us.json"
    us, _, _ = C.load("Oakmere Foods", root=str(tmp_path), country="US")
    assert [f["claim"] for f in us["facts"]] == ["Opened a Chicago plant"] and us["country"] == "US"
    # The home-country posting and every join read the plain file, which is untouched.
    for country in ("GB", None):
        home, _, _ = C.load("Oakmere Foods", root=str(tmp_path), country=country)
        assert [f["claim"] for f in home["facts"]] == ["Opened a Bolton bakery"]


def test_an_older_file_says_its_country_by_its_name_or_its_sources(tmp_path):
    assert C.entity_country({"company": "Oakmere Foods UK"}) == "GB"
    assert C.entity_country({"company": "Oakmere Foods", "facts": [UK_FACT]}) == "GB"
    assert C.entity_country({"company": "Oakmere Foods", "country": "us"}) == "US"
    assert C.entity_country({"company": "Oakmere Foods"}) == ""
    # A file that says nothing is taken to be about the person's own country.
    (tmp_path / C.DIR).mkdir()
    (tmp_path / C.DIR / "oakmere-foods.json").write_text(
        json.dumps({"company": "Oakmere Foods", "facts": [dict(UK_FACT, url="https://x.example/a")]}),
        encoding="utf-8")
    assert C.path("Oakmere Foods", root=str(tmp_path), country="GB").endswith("oakmere-foods.json")
    assert C.path("Oakmere Foods", root=str(tmp_path), country="US") is None


def test_where_a_posting_is_reads_from_its_location():
    assert C.country_of("Northbrook, IL") == "US"
    assert C.country_of("Remote - US") == "US"
    assert C.country_of("Toronto, ON") == "CA"
    assert C.country_of("Dublin, Ireland") == "IE"
    assert C.country_of("Manchester") == "GB"          # the example person's own metro
    assert C.country_of("Remote") == "" and C.country_of("San Diego, CA") == ""


def test_an_unknown_country_never_splits_the_cache(tmp_path):
    C.save("Oakmere Foods", {"facts": [UK_FACT], "fetched_date": dt.date.today().isoformat()},
           root=str(tmp_path))
    data, _, fresh = C.load("Oakmere Foods", root=str(tmp_path), country="")
    assert data["facts"] and fresh
