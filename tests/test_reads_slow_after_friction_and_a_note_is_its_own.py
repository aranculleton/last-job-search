"""Reads stop on what LinkedIn shows, and every note rests on its own reader, from the
networking audit of 2026-10-21.

The slow start after friction (the ramp) and the paused pages are gone since 2026-10-22, on
the maintainer's word: the app sets no reading limit of its own. What stays from the audit: a
security check on the first page of a day stops that day; a page that came back nearly empty
is counted; a stop in words nothing knew was said as a security check; a
national recruiter was cautioned for two cities; a queued draft was read with the notes
below its line of dashes; a promotion on LinkedIn was read as a contradiction; an approved
note's employer and hook reached a note to somebody else; short forms of a name were refused
as greeting the wrong person; and `sources.py harvest --help` crashed. Invented people and
employers only.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import compose  # noqa: E402
import own_profile  # noqa: E402
import pace  # noqa: E402
import reading  # noqa: E402
import sources  # noqa: E402
import state  # noqa: E402
import tone  # noqa: E402

D = datetime.datetime


@pytest.fixture
def here(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath("s", *p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [])
    return tmp_path


# ------------------------------------------------------------ a check, and the day after

def test_a_check_on_a_day_with_no_page_recorded_stops_that_day_and_holds_back_no_other(here):
    # A check on the first page of a day records no load; it stops that day all the same,
    # and the next day reads go at once, with no slow start (the ramp was removed).
    day = D(2026, 10, 16, 9)
    reading.stop("LinkedIn showed a check: a security check on the first page", day.date())
    assert not reading._loads()
    assert reading.gate_state(day + datetime.timedelta(hours=3))["kind"] == "tomorrow"
    next_day = day + datetime.timedelta(days=1)
    assert reading.gate_state(next_day)["kind"] == "go"
    assert [x["kind"] for x in pace.friction()] == ["check"]


# ------------------------------------------------------------ a page that came back empty

def test_a_page_that_came_back_nearly_empty_is_counted_and_holds_nothing_back(here, monkeypatch):
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    reading.shortlist(["c9"], datetime.date.today(),
                      contacts=[{"contact_id": "c9", "location": "Leeds"}], sends_left=10)
    page = here / "blank.txt"
    page.write_text("LinkedIn\n", encoding="utf-8")
    assert not reading._loads()
    code = reading.main(["read", "c9", str(page), "--source", "browser", "--name",
                         "Ana Rook", "--company", "Fernhill Freight"])
    assert code == reading.EXIT["unknown"]
    loads = reading._loads()
    assert len(loads) == 1
    # No pause after it: one alone is said, and only a second within the hour stops the day.
    g = reading.gate_state(loads[0]["when"] + datetime.timedelta(seconds=1), sends_left=None)
    assert g["kind"] == "go"
    assert [x["kind"] for x in pace.friction()] == ["not_rendering"]


# ------------------------------------------------------------ said as what happened

def test_a_stop_in_words_nothing_knows_is_said_in_those_words(here):
    reading.stop("a notice that my account is temporarily restricted")
    rec = pace.friction()[-1]
    assert rec["kind"] == "other"
    said = pace.said(rec)
    assert "temporarily restricted" in said and "security check" not in said
    reading.stop("LinkedIn showed a check: verify it's you")
    assert pace.friction()[-1]["kind"] == "check"


def test_a_recruiter_hiring_nationally_is_not_cautioned_for_two_cities():
    r = {"name": "Bo Venn", "company": "Kestrel Mutual",
         "headline": "Technical Recruiter at Kestrel Mutual, hiring nationally",
         "location": "Leeds, England, United Kingdom", "about": "", "items": [],
         "experience": [{"title": "Technical Recruiter", "employer": "Kestrel Mutual",
                         "dates": "Jan 2024 - Present",
                         "place": "Manchester, England, United Kingdom"}]}
    assert reading.verdict(r, "Kestrel Mutual") == (True, "")
    peer = dict(r, headline="Data Scientist at Kestrel Mutual")
    assert "check where they work" in reading.verdict(peer, "Kestrel Mutual")[1]


# ------------------------------------------------------------ a draft is the note alone

def test_a_draft_is_read_without_the_notes_below_its_line_of_dashes(here):
    note = "Hi Wren, we were both at Oakmere Foods. How did you find the move to Fernhill?"
    reading.save("fern_allard", {"name": "Wren Allard", "company": "Fernhill Freight",
                                 "headline": "Planner at Fernhill Freight", "items": [],
                                 "sources": [{"kind": "paste", "date": "2026-10-20"}],
                                 "experience": [{"title": "Planner",
                                                 "employer": "Fernhill Freight"}]})
    path = reading.draft_path("fern_allard")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(note + "\n\n---\nRests on the reading of 20 Oct (their own page).\n"
                 "Hook: shared employer. Kept under 300 characters.\n" + "A long aside. " * 40)
    assert state._draft_of("fern_allard") == note
    assert reading.queued_notes([{"contact_id": "fern_allard"}]) == {"fern_allard": note}
    assert "too_long" not in {v.rule for v in compose.validate(note, "connection",
                                                               name="Wren Allard")}


# ------------------------------------------------------------ their own profile

PROMOTED = [
    dict(employer="Brindle & Hart Logistics", title="Senior Operations Analyst",
         dates="Mar 2023 - Present"),
    dict(employer="Brindle & Hart Logistics", title="Operations Analyst",
         dates="Sep 2021 - Feb 2023"),
    dict(employer="Oakmere Foods", title="Supply Chain Data Analyst", dates="Sep 2020 - Aug 2021",
         known_as="Oakmere"),
]


def _linkedin(tmp_path, positions):
    p = tmp_path / "paste.json"
    p.write_text(json.dumps({
        "headline": "Senior Operations Analyst at Brindle & Hart Logistics",
        "location": "Manchester, England, United Kingdom", "summary": "x" * 600,
        "positions": positions, "skills": ["SQL"]}), encoding="utf-8")
    return own_profile.from_paste(str(p))


def test_a_promotion_and_a_shortened_employer_raise_nothing_on_a_matching_profile(
        tmp_path, monkeypatch):
    monkeypatch.setattr(own_profile, "roles", lambda: PROMOTED)
    same = [{"company": "Brindle & Hart", "title": "Senior Operations Analyst",
             "started": "Mar 2023", "finished": "", "description": "Leads forecasting."},
            {"company": "Brindle & Hart Logistics", "title": "Operations Analyst",
             "started": "Sep 2021", "finished": "Feb 2023", "description": "Built reports."},
            {"company": "Oakmere Foods", "title": "Supply Chain Data Analyst",
             "started": "Sep 2020", "finished": "Aug 2021", "description": ""}]
    got = own_profile.check(_linkedin(tmp_path, same), today="2026-10-21",
                            answers={"photo": {"answer": "yes"}})
    assert got["findings"] == []
    # A real difference is still found, on that role alone.
    wrong = [dict(same[0], started="Mar 2022")] + same[1:]
    got = own_profile.check(_linkedin(tmp_path, wrong), today="2026-10-21",
                            answers={"photo": {"answer": "yes"}})
    assert [(f["id"], "starts Mar 2022 there and Mar 2023" in f["what"])
            for f in got["findings"]] == [("role:brindle-hart-logistics", True)]


# ------------------------------------------------------------ an approved example

@pytest.fixture
def approved(tmp_path, monkeypatch):
    import csv_store
    import learned
    import person
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "state"))
    (tmp_path / "state").mkdir()
    person._modules.clear()
    person._data.clear()
    csv_store.write_rows(person.state("network_contacts.csv"), [
        {"contact_id": "kes_rook", "name": "Ana Rook", "company": "Kestrel Mutual"},
        {"contact_id": "fern_allard", "name": "Wren Allard", "company": "Fernhill Freight"}],
        ("contact_id", "name", "company"))
    reading.save("fern_allard", {"name": "Wren Allard", "company": "Fernhill Freight",
                                 "headline": "Planner at Fernhill Freight", "items": [],
                                 "sources": [{"kind": "paste", "date": "2026-10-21"}],
                                 "experience": [{"title": "Planner",
                                                 "employer": "Fernhill Freight"}]})
    first = ("Hi Ana, hope you're well. Your talk on promotion lift at the Kestrel Mutual "
             "analytics day stuck with me. I work in supply-chain analytics in Manchester. "
             "Would you have 15 minutes for a few questions sometime?")
    learned.approve("great, sent", first, channel="connection", reader="peer",
                    contact_id="kes_rook")
    yield first
    person._modules.clear()
    person._data.clear()


def test_an_approved_note_gives_its_shape_and_none_of_its_facts(approved, judged):
    judged("Fernhill Freight")   # nobody is shown at an employer nobody has judged
    import learned
    brief = learned.brief("messages", channel="connection", reader="peer")
    assert "never reuse a name, an employer or any fact" in brief
    assert "Kestrel Mutual" not in brief and "Ana" not in brief
    assert "<their employer>" in brief and "Hi <their name>," in brief
    copied = approved.replace("Hi Ana", "Hi Wren")
    found = compose.validate(copied, "connection", name="Wren Allard", contact="fern_allard")
    assert [v.rule for v in found if v.rule == "example_facts"] == ["example_facts"]
    assert "Kestrel Mutual" in next(v.text for v in found if v.rule == "example_facts")
    # Saved as a draft, it is refused the same way.
    assert reading.save_drafts({"fern_allard": (copied, False)}) == reading.EXIT["error"]
    assert not os.path.exists(reading.draft_path("fern_allard"))
    # The same note to the person it was written for, or one in its shape about the new
    # reader, passes.
    assert not [v for v in compose.validate(approved, "connection", name="Ana Rook",
                                            contact="kes_rook") if v.rule == "example_facts"]
    own = ("Hi Wren, hope you're well. Your post on depot routing at Fernhill Freight stuck "
           "with me. I work in supply-chain analytics in Manchester. Would you have 15 minutes "
           "for a few questions sometime?")
    assert not [v for v in compose.validate(own, "connection", name="Wren Allard",
                                            contact="fern_allard") if v.rule == "example_facts"]
    # A note queued before the check, written straight to the draft file, is listed for a
    # rewrite: saving would refuse it now, but it sat there looking ready to send.
    import datetime
    book = [{"contact_id": "fern_allard", "name": "Wren Allard", "company": "Fernhill Freight",
             "status": "not_contacted"}]
    today = datetime.date(2026, 10, 21)
    os.makedirs(os.path.dirname(reading.draft_path("fern_allard")), exist_ok=True)
    with open(reading.draft_path("fern_allard"), "w", encoding="utf-8") as fh:
        fh.write(own)
    assert reading.queue(book, today) == []
    with open(reading.draft_path("fern_allard"), "w", encoding="utf-8") as fh:
        fh.write(copied)
    assert [c["contact_id"] for c in reading.queue(book, today)] == ["fern_allard"]


# ------------------------------------------------------------ the greeting

def test_a_greeting_that_starts_their_given_name_is_theirs():
    # Given names alone: the short form is the start of the name they go by.
    for greeting, name in (("Thad", "Thaddeus"), ("Ignat", "Ignatius"), ("Wil", "Wilhelmina"),
                           ("Gabe", "Gabriel"), ("Tams", "Tamsin Oyelaran")):
        assert tone.wrong_greeting(f"Hi {greeting}, hope you're well.", name) == [], greeting
    # Somebody else is still somebody else, and two letters are not a name.
    for greeting, name in (("Wren", "Ana Rook"), ("Thaddea", "Thaddeus"), ("An", "Ana Rook")):
        assert tone.wrong_greeting(f"Hi {greeting}, hope you're well.", name), greeting


# ------------------------------------------------------------ the sources command

def test_the_sources_command_answers_help_and_mistakes_with_its_usage(capsys):
    assert sources.main(["--help"]) == 0
    assert "Usage:" in capsys.readouterr().out
    assert sources.main(["harvest", "--help"]) == 0
    assert sources.main(["harvest"]) == 2
    assert sources.main(["harvst", "results.json"]) == 2
    out = capsys.readouterr().out
    assert "for harvst" not in out and "Usage:" in out
    assert sources.main(["harvest", "no-such-results.json", "--company", "Kestrel Mutual"]) == 1
