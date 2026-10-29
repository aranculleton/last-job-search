"""The interview pack asks "Which team is this for?" only when the employer really has another
posting for the role, and lists the other postings, never the one the call is for.

`sibling_postings` listed every posting the search had seen for the role at the employer (or
an arm of it), the call's own included, and asked when there were two:

- the call's own posting counted, so an employer with one posting for the role, seen on two
  boards, was asked about, with its own posting listed as the "other" one;
- the same role listed on two boards counted as two postings;
- a posting /rank had retired for a past deadline counted as one;
- an employer with the call's role and one other posting (a Labs arm) was not asked when the
  call's own posting was not among the postings the search had seen (a referral, a
  process with no application), because two were wanted and only one was found.

Every employer, person and link here is invented.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import interview_pack as P  # noqa: E402
import person  # noqa: E402

TODAY = "2026-10-29"
FIRM, ROLE = "Ellerwick Trust", "Senior Data Scientist"
OWN = "https://boards.example.com/ellerwick/101"
SOURCE = "job_scraper/seen_jobs.json"


def _entry(url=None, company=FIRM, title=ROLE, location="Manchester", status="new", **more):
    return dict({"company": company, "title": title, "location": location, "status": status,
                 "url": url}, **more)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A state folder of the test's own, and `run(seen, source=..., notes=...)` that builds
    the pack's context for a tracker row at FIRM and returns it."""
    state = tmp_path / "state"
    (state / "job_scraper").mkdir(parents=True)
    monkeypatch.setenv(person.STATE_ENV, str(state))
    person.reset()

    def run(seen, source=OWN, notes="", stage="Recruiter screen", company=FIRM, role=ROLE):
        (state / "job_scraper" / "seen_jobs.json").write_text(
            json.dumps({"seen": seen}), encoding="utf-8")
        row = {"date": "2026-10-20", "company": FIRM, "role": ROLE, "status": "interview",
               "source": source, "notes": notes}
        return P.gather(company, role, stage=stage, today=TODAY, tracker=[row], contacts=[],
                        threads=[])

    yield run
    person.reset()


def _others(ctx):
    return [what for what, _ in P.sibling_postings(ctx)]


def _asks_which_team(ctx):
    return [ln for ln in P.ask_lines(ctx) if ln.startswith("- Which team")]


def test_one_posting_for_the_role_is_no_question(world):
    ctx = world({OWN: _entry(OWN)})
    assert P.sibling_postings(ctx) == []
    assert _asks_which_team(ctx) == []


def test_the_same_posting_on_two_boards_is_one_posting(world):
    ctx = world({OWN: _entry(OWN),
                 "https://other.example.org/jobs/88": _entry(),
                 "https://third.example.net/p/5": _entry(location="manchester, England")})
    assert P.sibling_postings(ctx) == []
    assert _asks_which_team(ctx) == []


def test_the_same_posting_on_two_boards_is_one_when_the_row_holds_no_link(world):
    ctx = world({"https://boards.example.com/ellerwick/101": _entry(),
                 "https://other.example.org/jobs/88": _entry()}, source="contact:ellerwick_vale")
    assert P.sibling_postings(ctx) == []


def test_the_other_posting_is_listed_and_the_calls_own_is_not(world):
    labs = "https://boards.example.com/ellerwick-labs/7"
    ctx = world({OWN: _entry(OWN),
                 labs: _entry(labs, company="Ellerwick Trust Labs", status="skipped")})
    assert _others(ctx) == ["Senior Data Scientist, Ellerwick Trust Labs (Manchester)"]
    (line,) = _asks_which_team(ctx)
    assert "Ellerwick Trust Labs (Manchester)" in line
    assert "Ellerwick Trust (Manchester)" not in line
    assert line.startswith("- Which team is this recruiter screen for?")


def test_one_other_posting_is_enough_when_the_calls_own_was_never_seen(world):
    labs = "https://boards.example.com/ellerwick-labs/7"
    ctx = world({labs: _entry(labs, company="Ellerwick Trust Labs")})
    assert _others(ctx) == ["Senior Data Scientist, Ellerwick Trust Labs (Manchester)"]
    assert len(_asks_which_team(ctx)) == 1


def test_a_process_with_no_application_leaves_out_its_own_posting_too(world):
    labs = "https://boards.example.com/ellerwick-labs/7"
    ctx = world({OWN: _entry(OWN), labs: _entry(labs, company="Ellerwick Trust Labs")},
                source="contact:ellerwick_vale")
    assert _others(ctx) == ["Senior Data Scientist, Ellerwick Trust Labs (Manchester)"]


def test_the_same_role_in_another_place_is_another_posting(world):
    leeds = "https://boards.example.com/ellerwick/102"
    ctx = world({OWN: _entry(OWN), leeds: _entry(leeds, location="Leeds"),
                 "https://other.example.org/jobs/88": _entry(location="Leeds, UK")})
    assert _others(ctx) == ["Senior Data Scientist, Ellerwick Trust (Leeds)"]
    assert len(_asks_which_team(ctx)) == 1


def test_the_calls_own_posting_is_found_by_its_link_where_there_are_several(world):
    leeds = "https://boards.example.com/ellerwick/102"
    ctx = world({OWN: _entry(OWN), leeds: _entry(leeds, location="Leeds")}, source=leeds)
    assert _others(ctx) == ["Senior Data Scientist, Ellerwick Trust (Manchester)"]


def test_a_link_is_matched_however_it_is_written(world):
    leeds = "https://boards.example.com/ellerwick/102"
    ctx = world({OWN: _entry(OWN), leeds: _entry(leeds, location="Leeds")},
                source="http://Boards.Example.com/ellerwick/102/?utm_source=mail")
    assert _others(ctx) == ["Senior Data Scientist, Ellerwick Trust (Manchester)"]


def test_with_several_postings_and_nothing_to_say_which_is_the_calls_all_are_listed(world):
    leeds = "https://boards.example.com/ellerwick/102"
    ctx = world({OWN: _entry(OWN), leeds: _entry(leeds, location="Leeds")},
                source="contact:ellerwick_vale")
    assert sorted(_others(ctx)) == ["Senior Data Scientist, Ellerwick Trust (Leeds)",
                                    "Senior Data Scientist, Ellerwick Trust (Manchester)"]


def test_a_posting_past_its_deadline_is_no_longer_a_posting(world):
    labs = "https://boards.example.com/ellerwick-labs/7"
    ctx = world({OWN: _entry(OWN),
                 labs: _entry(labs, company="Ellerwick Trust Labs", status="expired",
                              deadline="2026-10-01")})
    assert P.sibling_postings(ctx) == []
    assert _asks_which_team(ctx) == []


def test_another_role_and_another_employer_are_not_postings_for_this_one(world):
    ctx = world({OWN: _entry(OWN),
                 "https://boards.example.com/ellerwick/300": _entry(title="Data Engineer"),
                 "https://boards.example.com/fernhill/9": _entry(company="Fernhill Freight")})
    assert P.sibling_postings(ctx) == []


def test_a_note_that_says_there_are_two_postings_is_still_a_reason_to_ask(world):
    ctx = world({OWN: _entry(OWN)}, notes="Vale says there are two postings for this, main and Labs.")
    (what, source), = P.sibling_postings(ctx)
    assert "two postings" in what and source == P.prep.TRACKER_SOURCE
    assert len(_asks_which_team(ctx)) == 1


def test_a_note_comes_after_the_postings_and_is_not_a_second_copy_of_one(world):
    labs = "https://boards.example.com/ellerwick-labs/7"
    ctx = world({OWN: _entry(OWN), labs: _entry(labs, company="Ellerwick Trust Labs")},
                notes="Two postings, main and Labs.")
    found = P.sibling_postings(ctx)
    assert [src for _, src in found] == [SOURCE, P.prep.TRACKER_SOURCE]


def test_past_the_third_posting_the_line_says_how_many_more(world):
    seen = {OWN: _entry(OWN)}
    for n, place in enumerate(["Leeds", "York", "Bath", "Derby", "Hull"]):
        url = "https://boards.example.com/ellerwick/2%d" % n
        seen[url] = _entry(url, location=place)
    (line,) = _asks_which_team(world(seen))
    assert line.count("(source: %s)" % SOURCE) == 3
    assert "(and 2 more)" in line


def test_the_line_says_the_postings_are_besides_the_one_the_call_is_for(world):
    labs = "https://boards.example.com/ellerwick-labs/7"
    ctx = world({OWN: _entry(OWN), labs: _entry(labs, company="Ellerwick Trust Labs")})
    (line,) = _asks_which_team(ctx)
    assert "more than one posting for it; besides this one: " in line
    assert line.count("Senior Data Scientist") == 1
