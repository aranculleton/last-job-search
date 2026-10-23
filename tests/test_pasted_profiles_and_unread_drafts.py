"""Profiles pasted several at once, and a note nobody read anything for.

A chat with no browser reads people from what the person pastes, and one at a time
was the only way: several profiles in one message had nowhere to go. And a first
note written from a search result alone, by the networking upgrade or a run with no
browser, sat in the queue looking ready to send. Now one paste holds several
profiles, each matched to a waiting note by name and employer and read on its own,
and an unread note says at its top that it waits on a read.

The people are invented, against the example profile.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import reading  # noqa: E402
import state  # noqa: E402

TODAY = datetime.date(2026, 10, 17)

TAMSIN = """Skip to main content
Home
Tamsin Oyelaran
She/Her
· 2nd
Head of Demand Forecasting at Fernhill Freight
Manchester, England, United Kingdom
Contact info
Connect
About
I build forecasts that warehouse teams actually use.
Experience
Head of Demand Forecasting
Fernhill Freight · Full-time
Jan 2024 - Present · 1 yr 10 mos
Forecasting Lead
Oakmere Foods · Full-time
Mar 2019 - Dec 2023 · 4 yrs 10 mos
People also viewed
Corwin Haldane
Head of Data at Kestrel Mutual
"""

# The wrong tab: somebody else with a waiting contact's surname, at another employer.
RHIAN = """Rhian Haldane
Data Analyst at Fenwick Lane Insurance
Leeds, England, United Kingdom
Contact info
Connect
About
Claims analytics.
Experience
Data Analyst
Fenwick Lane Insurance · Full-time
Feb 2022 - Present · 2 yrs 9 mos
"""

SHIRIN = """Shirin Example
Lead Data Scientist | pricing and forecasting
Salford, England, United Kingdom
Contact info
· 2nd
Connect
About
Pricing models for a mutual insurer.
Experience
Lead Data Scientist
Kestrel Mutual · Full-time
Apr 2021 - Present · 3 yrs 7 mos
"""

CONTACTS = [
    {"contact_id": "fernhill_oyelaran", "name": "Tamsin Oyelaran", "company": "Fernhill Freight",
     "status": "not_contacted", "linkedin_url": "https://www.linkedin.com/in/example-tamsin"},
    {"contact_id": "kestrel_haldane", "name": "Corwin Haldane", "company": "Kestrel Mutual",
     "status": "not_contacted"},
    {"contact_id": "kestrel_example", "name": "Shirin Example", "company": "Kestrel Mutual Ltd",
     "status": "not_contacted"},
]


@pytest.fixture(autouse=True)
def _employers_judged(judged):
    """Nobody is shown at an employer nobody has judged (tools/network/surface.py): the
    queue these tests read holds people at these two invented employers."""
    judged("Kestrel Mutual", "Fernhill Freight")


@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setattr(state, "load_contacts", lambda *a, **k: [dict(c) for c in CONTACTS])
    for c in CONTACTS:
        reading.write_draft(c["contact_id"], f"Hi {c['name'].split()[0]}, a note.", c["name"])
    return tmp_path


def test_one_paste_reads_several_profiles_each_against_its_own_note(book, capsys):
    assert [c["contact_id"] for c in reading.queue(CONTACTS)] == \
        ["fernhill_oyelaran", "kestrel_haldane", "kestrel_example"]
    paste = book / "paste.txt"
    paste.write_text(TAMSIN + "\n---\n" + RHIAN + "\n-----\n" + SHIRIN, encoding="utf-8")
    assert reading.main(["paste", str(paste)]) == 0
    out = capsys.readouterr().out
    assert "3 profile(s) in the paste, 3 note(s) waiting on a read" in out
    assert "1. Tamsin Oyelaran (fernhill_oyelaran): read; KEEP" in out
    assert '2. not matched ("Rhian Haldane"): names nobody whose note waits on a read' in out
    assert "3. Shirin Example (kestrel_example): read; KEEP" in out
    assert "still waiting on a read: Corwin Haldane (kestrel_haldane)" in out
    assert "compose.first_note(..., reading=reading.load(<id>))" in out
    # Each profile is read on its own: nothing of one reaches another's reading.
    tamsin, shirin = reading.load("fernhill_oyelaran"), reading.load("kestrel_example")
    assert tamsin["current"] == "Fernhill Freight" and shirin["current"] == "Kestrel Mutual"
    assert "Kestrel" not in str(tamsin) and "Fernhill" not in str(shirin)
    assert tamsin["sources"][0]["url"] == CONTACTS[0]["linkedin_url"]
    # A name in LinkedIn's column of other people is never a match: Corwin was not pasted.
    assert reading.load("kestrel_haldane") is None


def test_a_profile_it_could_equally_be_two_people_for_is_left_for_the_person():
    twins = [dict(CONTACTS[1]), dict(CONTACTS[1], contact_id="kestrel_haldane_c")]
    page = "Corwin Haldane\nHead of Data at Kestrel Mutual\nContact info\nAbout\nData.\n"
    (piece, contact, why), = reading.match_paste([page], twins)
    assert contact is None and why.startswith("could be Corwin Haldane (kestrel_haldane) or")
    # The surname and the employer on the page are enough when the first name differs.
    page = "Robin Haldane\nHead of Data at Kestrel Mutual\nContact info\nAbout\nData.\n"
    assert reading.match_paste([page], CONTACTS)[0][1]["contact_id"] == "kestrel_haldane"
    # One paste with no line between profiles is one profile.
    assert reading.split_paste(TAMSIN) == [TAMSIN.strip()]


def test_a_note_for_someone_nobody_read_says_it_waits_on_a_read(book, capsys):
    draft = book / "documents" / "network" / "kestrel_example" / "draft.md"
    first = draft.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("WAITS ON A READ: nothing was read about Shirin Example")
    assert "not sent as it stands" in first
    assert draft.read_text(encoding="utf-8").rstrip().endswith("Hi Shirin, a note.")
    assert reading.waits_on_read("kestrel_example")
    # Read since, and not rewritten yet: the queue still lists it.
    reading.save("kestrel_example", reading.parse(SHIRIN, name="Shirin Example",
                                                  company="Kestrel Mutual Ltd"))
    assert "kestrel_example" in [c["contact_id"] for c in reading.queue(CONTACTS)]
    # Rewritten from the reading, it is a note like any other and leaves the queue.
    note = book / "note.txt"
    note.write_text("Hi Shirin, your pricing models for a mutual insurer caught my eye.",
                    encoding="utf-8")
    assert reading.main(["draft", "kestrel_example", str(note)]) == 0
    assert "WAITS ON A READ" not in capsys.readouterr().out
    assert draft.read_text(encoding="utf-8").startswith("Hi Shirin, your pricing models")
    assert "kestrel_example" not in [c["contact_id"] for c in reading.queue(CONTACTS)]
    # A public finding is something read too.
    reading.save("kestrel_haldane", {"name": "Corwin Haldane", "sources": [{"kind": "public"}],
                                     "items": [reading.item("talk", "https://example.org/t",
                                                            "Pricing a mutual")]})
    assert not reading.draft_text("kestrel_haldane", "Hi Corwin").startswith("WAITS ON A READ")


def test_notes_the_networking_upgrade_writes_are_not_redone_as_older_ones(book):
    """The networking upgrade writes each new contact's note opening on WAITS ON A READ;
    the network-notes method counted any draft as made the older way, so every /network
    run began by rewriting the notes just written, which needs the reads they wait on."""
    import build_versions
    assert not any(reading.written_the_older_way(c["contact_id"]) for c in CONTACTS)
    assert not build_versions.APPLIES["queued_notes"]()
    # A note from before notes rested on a reading: no line, nothing read. That one is redone.
    older = book / "documents" / "network" / "kestrel_older" / "draft.md"
    older.parent.mkdir(parents=True)
    older.write_text("Hi Rhian, a note from a search result.\n", encoding="utf-8")
    assert reading.written_the_older_way("kestrel_older")
    assert build_versions.APPLIES["queued_notes"]()


def test_a_note_written_from_their_public_work_leaves_the_queue(book, capsys):
    reading.save("kestrel_haldane", {"name": "Corwin Haldane", "read_on": TODAY.isoformat(),
                                     "sources": [{"kind": "public"}],
                                     "items": [reading.item("talk", "https://example.org/t",
                                                            "Pricing a mutual")]})
    note = book / "note.txt"
    note.write_text("Hi Corwin, your talk on pricing a mutual stayed with me.", encoding="utf-8")
    assert reading.main(["draft", "kestrel_haldane", str(note)]) == 0
    capsys.readouterr()
    queued = [c["contact_id"] for c in reading.queue(CONTACTS, TODAY)]
    assert "kestrel_haldane" not in queued
    # Read long enough ago, it is read again before it goes.
    later = TODAY + datetime.timedelta(days=reading.FRESH_DAYS + 1)
    assert "kestrel_haldane" in [c["contact_id"] for c in reading.queue(CONTACTS, later)]
