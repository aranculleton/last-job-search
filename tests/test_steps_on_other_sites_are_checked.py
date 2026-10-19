"""A step on another company's site is dated, sourced and checked, never passed on.

From one person's repo: the steps for LinkedIn's connections export said to choose
"Connections only", which LinkedIn no longer offered, and to expect a file in ten
minutes. They had come from two old third-party guides and were passed on unchecked.
Invented people and employers only.
"""
from __future__ import annotations

import datetime
import os
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import claude_surfaces as C  # noqa: E402
import profile_upgrades as U  # noqa: E402
import sources  # noqa: E402
import state  # noqa: E402

REG = C.load()
CSV = ("Notes:\n\"When exporting your connection data, you may notice that some of the email "
       "addresses are missing.\"\n\nFirst Name,Last Name,URL,Email Address,Company,Position,"
       "Connected On\nShirin,Example,https://www.linkedin.com/in/example-shirin,,Kestrel Mutual,"
       "Head of Demand Planning,03 Mar 2024\nCorwin,Haldane,https://www.linkedin.com/in/"
       "example-corwin,,Fernhill Freight,Data Analyst,12 Jan 2023\n")


# ------------------------------------------------------------ every printed step

def test_every_step_printed_says_when_it_was_checked_and_against_what():
    for e in REG["entries"]:
        if not (e.get("steps") or e.get("how")):
            continue
        assert C.official(e).startswith("https://"), e["id"]
        if e.get("steps"):
            head = C.steps(e["id"], today=datetime.date.fromisoformat(e["verified_on"]))
            assert head[0] == (f"At the time of writing (checked {e['verified_on']}; official "
                               f"page: {C.official(e)}):")
            assert not head[-1].startswith("[claude_surfaces:")


def test_a_step_past_its_date_tells_claude_to_check_it_first():
    e = C.entry("linkedin-connections")
    late = datetime.date.fromisoformat(e["verified_on"]) + datetime.timedelta(
        days=int(REG["stale_after_days"]) + 1)
    out = C.steps("linkedin-connections", today=late)
    assert out[-1].startswith("[claude_surfaces: 'linkedin-connections' was checked")
    assert "re-check https://www.linkedin.com/help/linkedin/answer/50191" in out[-1]


def test_a_page_that_is_never_fetched_is_put_to_the_maintainer_by_hand():
    asked = []

    def fetch(url):
        asked.append(url)
        return ""
    reg = {"stale_after_days": 60, "hand_check_days": 30, "release_notes": "", "entries": [
        {"id": "x", "verified_on": "2026-10-19", "ui_sensitive": True,
         "sources": [{"url": "https://www.linkedin.com/help/x", "quote": "Within 24 hours",
                      "fetch": False, "why_not_fetched": "robots.txt"}]}]}
    assert C.watch(reg, fetch, today=datetime.date(2026, 11, 10)) == []
    found = C.watch(reg, fetch, today=datetime.date(2026, 11, 25))
    assert found and found[0][1].startswith("check by hand: https://www.linkedin.com/help/x "
                                            "is never fetched (robots.txt)")
    assert asked == []                                   # linkedin.com is never fetched
    linkedin = [s for e in REG["entries"] for s in e["sources"] if "linkedin.com" in s["url"]]
    assert linkedin and all(s.get("fetch") is False for s in linkedin)


# ------------------------------------------------------------ the connections export

def test_the_export_steps_match_linkedins_page_and_never_promise_ten_minutes():
    steps = "\n".join(C.steps("linkedin-connections"))
    assert "larger download" in steps and "Connections only" not in steps
    assert "anything from about ten minutes to a day later" in steps
    assert "attach only Connections.csv" in steps
    u = U.by_id("connections-export")
    assert "ten minutes to a day" in u.ask and "about ten minutes," not in u.ask
    assert u.steps().startswith("At the time of writing (checked ")
    assert "import-connections" in u.run and "while-you-wait" in u.run and "people-paste" in u.run
    # The quicker route is offered once, starting where an interview is running.
    offer = sources.while_you_wait([{"company": "Kestrel Mutual", "status": "interview"},
                                    {"company": "Fernhill Freight", "status": "applied"}])
    assert "starting with Kestrel Mutual, where you are interviewing" in offer
    assert "1st-degree people" in offer and offer.endswith("Want the steps for that?")
    assert "the employer that matters most to you now" in sources.while_you_wait([])


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(sources.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    return tmp_path


def test_from_the_whole_archive_only_connections_is_read(home, monkeypatch):
    archive = home / "Basic_LinkedInDataExport.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("Connections.csv", CSV)
        z.writestr("messages.csv", "FROM,TO,CONTENT\nsomeone,me,a private message\n")
        z.writestr("Profile.csv", "First Name,Last Name\nMorgan,Ellis\n")
    opened = []
    real = zipfile.ZipFile.read
    monkeypatch.setattr(zipfile.ZipFile, "read",
                        lambda self, name, *a: opened.append(name) or real(self, name, *a))
    said = sources.import_connections(str(archive))
    assert opened == ["Connections.csv"]
    assert said == ("Saved your 2 connections. I read only Connections.csv from the archive; "
                    "the other 2 files in it were not opened.")
    saved = home / "documents" / "linkedin" / "Connections.csv"
    assert saved.read_text(encoding="utf-8") == CSV
    assert [c["name"] for c in state.first_degree(str(saved))] == ["Shirin Example", "Corwin Haldane"]


def test_the_shorter_download_or_a_wrong_file_saves_nothing(home):
    short = home / "short.zip"
    with zipfile.ZipFile(short, "w") as z:
        z.writestr("Profile.csv", "First Name,Last Name\nMorgan,Ellis\n")
        z.writestr("Invitations.csv", "From,To\n")
    with pytest.raises(ValueError, match="shorter download"):
        sources.import_connections(str(short))
    wrong = home / "wrong.csv"
    wrong.write_text("Name,Employer\nShirin Example,Kestrel Mutual\n", encoding="utf-8")
    with pytest.raises(ValueError, match="First Name"):
        sources.import_connections(str(wrong))
    assert not (home / "documents" / "linkedin" / "Connections.csv").exists()


def test_the_file_itself_with_its_notes_above_the_header_is_read(home):
    path = home / "Connections.csv"
    path.write_text(CSV, encoding="utf-8")
    assert sources.import_connections(str(path)) == "Saved your 2 connections."


# ------------------------------------------------------------ while the export is on its way

PASTE = """Shirin Example
View profile
 • 1st
1st degree connection
Head of Demand Planning at Kestrel Mutual
Manchester, England, United Kingdom
Message
Corwin Haldane • 2nd
Data Analyst at Kestrel Mutual
Greater Manchester
12 mutual connections
Connect
https://www.linkedin.com/in/example-corwin
Tamsin Oyelaran
View profile
• 1st
Events Coordinator
London
Message
"""


def test_one_employers_people_pasted_are_ranked_with_no_browser():
    people = sources.people_paste(PASTE, "Kestrel Mutual")
    assert [(p["name"], p["degree"], p["title"]) for p in people] == [
        ("Shirin Example", "1st", "Head of Demand Planning at Kestrel Mutual"),
        ("Corwin Haldane", "2nd", "Data Analyst at Kestrel Mutual"),
        ("Tamsin Oyelaran", "1st", "Events Coordinator")]
    assert people[1]["linkedin_url"] == "https://www.linkedin.com/in/example-corwin"
    ranked = sources.from_people_paste(PASTE, "Kestrel Mutual", contacts=[])
    assert [(p["name"], p["route"], p["channel"]) for p in ranked] == [
        ("Shirin Example", "connection", "message"),          # 1st, in their function, first
        ("Tamsin Oyelaran", "connection", "message"),
        ("Corwin Haldane", "", "connection")]                  # 2nd: a connection request
    # Somebody already in the contact book is left out.
    book = [{"contact_id": "kestrel_example", "name": "Shirin Example",
             "company": "Kestrel Mutual", "status": "awaiting_reply"}]
    assert "Shirin Example" not in [p["name"] for p in
                                    sources.from_people_paste(PASTE, "Kestrel Mutual", contacts=book)]
    # A paste already filtered to 1st carries no degree: it is given.
    bare = "Shirin Example\nHead of Demand Planning at Kestrel Mutual\nManchester\n"
    assert sources.people_paste(bare, "Kestrel Mutual", "1st")[0]["degree"] == "1st"
