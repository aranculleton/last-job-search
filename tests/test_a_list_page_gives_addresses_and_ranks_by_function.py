"""A page of many people gives each one's address, and is ranked by their function.

From a real run (2026-10-20): `reading.py people` read a people search from its text,
which has no profile links, so the candidates came out "[not in the book]" with no address
and the chat wrote a script of its own to read the links, which the desktop app's safety
check refused. A keyword search narrowed to one employer still returned IT support and
general operations. The fixture is what the list extractor returned when run in headless
Chromium on an invented page; every name in it is invented.
"""
from __future__ import annotations

import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import discovery  # noqa: E402
import reading  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "list_extract_people_search.json")


def _raw():
    with open(FIXTURE, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    import state
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [])
    return tmp_path


def test_the_list_extractor_only_reads():
    js = reading.LIST_EXTRACTOR
    for verb in ("click(", "scroll", ".value =", "dispatchEvent", "submit(", "focus("):
        assert verb not in js
    assert "JSON.stringify" in js and "/in/" in js


def test_every_card_keeps_the_persons_own_address_and_never_a_mutuals():
    people = reading.people_page(reading.from_list_extract(_raw()), "Larkspur")
    by = {p["name"]: p for p in people}
    assert by["Juno Castellan"]["linkedin_url"] == "https://www.linkedin.com/in/example-juno"
    assert by["Bo Venn"]["linkedin_url"] == "https://www.linkedin.com/in/example-bo"
    assert "Wren Allard" not in by                     # a mutual connection on Juno's card
    assert by["Juno Castellan"]["degree"] == "2nd"
    assert by["Ana Rook"]["reach"] == "pending"


def test_people_takes_the_extractors_output_and_prints_each_address(here, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(_raw()))
    assert reading.main(["people", "-", "--company", "Larkspur"]) == reading.EXIT["ok"]
    out = capsys.readouterr().out
    assert "[not in the book] https://www.linkedin.com/in/example-juno" in out
    lines = [ln for ln in out.splitlines() if ln.startswith("  ")]
    # Best first: their own title, then a role in their function, then the rest, out last.
    assert lines[0].startswith("  deep read: Juno Castellan") and "one of your titles" in lines[0]
    assert lines[1].startswith("  deep read: Dee Hollis") and "a role in your function" in lines[1]
    assert any("Bo Venn" in ln and "an IT Support role, not one in your function" in ln
               for ln in lines)
    assert any("Cy Marlow" in ln and "an Operations role" in ln for ln in lines)


@pytest.mark.parametrize("title,rank", [
    ("Senior Data Scientist at Larkspur", 3),
    ("Demand Planning Analyst", 2),
    ("Software Engineer", 1),
    ("IT Support Specialist", 0),
    ("Help Desk Technician", 0),
    ("Business Operations Manager", 0),
    ("Operations Research Scientist", 2),
    ("", 1),
])
def test_a_title_is_ranked_by_how_close_it_is_to_their_function(title, rank):
    assert reading.title_fit(title)[0] == rank


def test_a_function_of_the_persons_own_is_never_cut(monkeypatch):
    monkeypatch.setitem(discovery.TITLE_SETS, "function", ["Operations Analyst"])
    assert reading.title_fit("Operations Manager")[0] != 0
    assert reading.title_fit("IT Support Specialist")[0] == 0


def test_a_pending_request_is_never_cut_for_its_title():
    keep, why = reading.screen({"name": "Bo Venn", "title": "IT Support Specialist",
                                "location": "", "reach": "pending", "where": "at",
                                "employer": "Larkspur"}, "Larkspur")
    assert "pending" in why and "IT Support" not in why


def test_a_company_number_is_used_then_confirmed_by_the_first_page(here):
    reading.learn_company_id("Larkspur", "424242")
    url = reading.search_url("Larkspur", keywords=reading.function_keywords())
    assert "currentCompany=%5B%22424242%22%5D" in url and "+OR+" in url
    assert reading._employer_filter("Larkspur")["unconfirmed"]
    said = reading.confirm_company("Larkspur", {"at": 7, "elsewhere": 3, "unknown": 0})
    assert "confirmed: 7 of 10 at Larkspur" in said
    assert "unconfirmed" not in reading._employer_filter("Larkspur")


def test_a_company_number_that_is_someone_elses_is_said_and_refused(here):
    reading.learn_company_id("Larkspur", "13")
    said = reading.confirm_company("Larkspur", {"at": 2, "elsewhere": 8, "unknown": 0})
    assert "NOT Larkspur: only 2 of 10 at Larkspur" in said
    with pytest.raises(LookupError, match="is not Larkspur"):
        reading.search_url("Larkspur")
    reading.learn_company_id("Larkspur", "424242")                  # the right one
    assert "424242" in reading.search_url("Larkspur")


def test_too_few_cards_confirm_nothing_yet(here):
    reading.learn_company_id("Larkspur", "424242")
    assert "not confirmed yet" in reading.confirm_company("Larkspur", {"at": 1, "elsewhere": 1})
    assert reading._employer_filter("Larkspur")["unconfirmed"]


def test_a_hand_filtered_search_is_confirmed_by_the_person(here):
    reading.learn_company_id("Larkspur", "13")
    reading.confirm_company("Larkspur", {"at": 0, "elsewhere": 9})
    reading.learn_search("https://www.linkedin.com/search/results/people/?currentCompany="
                         "%5B%22424242%22%5D&origin=FACETED_SEARCH", "Larkspur")
    f = reading._employer_filter("Larkspur")
    assert "unconfirmed" not in f and "wrong" not in f


def test_the_cli_builds_the_search_from_a_number_and_says_it_is_unconfirmed(here, capsys):
    assert reading.main(["search-url", "--company", "Larkspur", "--company-id", "424242",
                         "--function"]) == reading.EXIT["ok"]
    out = capsys.readouterr().out
    assert "424242" in out and "unconfirmed" in out and "reading.py people" in out


def test_the_function_keywords_are_the_persons_titles_quoted_and_joined_with_or():
    got = reading.function_keywords()
    titles = discovery.TITLE_SETS["function"][:reading.FUNCTION_KEYWORDS]
    assert got == " OR ".join('"%s"' % t for t in titles)


def test_the_people_command_refuses_json_that_is_not_the_extractors(here, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"cards": "nope"})))
    with pytest.raises(SystemExit, match="list extractor"):
        reading.main(["people", "-", "--company", "Larkspur", "--json"])
