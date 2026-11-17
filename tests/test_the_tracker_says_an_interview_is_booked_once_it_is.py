"""Once an interview's day is booked, the application's tracker notes say so too.

Issue 274: a stage booked with no day was noted on the tracker row as "the day still to
choose". Its day, booked later with `interview_pack.py book`, went on the stage line in
outcome.md alone, so the tracker kept the older line, and a chat that read the tracker first
told the person the interview was not booked when it was.

Here booking the day adds it to the row's notes as a dated note, once however often it is
booked, and a tracker an older version left that way is put right by the update itself (the
instant profile upgrade `interview-days-noted`). Every person and employer is invented: the
search is tests/app_state.py's, with Thornbury Bank at interview.
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

OUTCOME = ("documents", "applications", "thornbury_bank_risk_analyst_thornbury", "outcome.md")
UNCHOSEN = "2026-11-10: interview, Final round booked, the day still to choose (page)"


@pytest.fixture
def search(tmp_path):
    s = Search(str(tmp_path))
    path = os.path.join(s.state, *OUTCOME)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("- [ ] Final round\n")
    _notes(s, "2026-10-20: phone screen went well | " + UNCHOSEN)
    return s


def tool(search, *args, today="2026-11-12"):
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state,
               LJS_COPY="private", LJS_TODAY=today)
    r = subprocess.run([sys.executable, *args], env=env, capture_output=True, encoding="utf-8",
                       errors="replace", timeout=120, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _rows(search):
    with open(os.path.join(search.state, "job_search_tracker.csv"), encoding="utf-8",
              newline="") as fh:
        return list(csv.DictReader(fh))


def _notes(search, notes=None):
    rows = _rows(search)
    row = next(r for r in rows if r["company"] == "Thornbury Bank")
    if notes is None:
        return row["notes"]
    row["notes"] = notes
    with open(os.path.join(search.state, "job_search_tracker.csv"), "w", encoding="utf-8",
              newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return notes


def _outcome(search):
    with open(os.path.join(search.state, *OUTCOME), encoding="utf-8") as fh:
        return fh.read()


BOOKED = "2026-11-12: Final round booked for 2026-11-20 at 14:00 America/Toronto (chat)"


def test_booking_the_day_puts_it_on_the_tracker_after_the_note_that_had_none(search):
    out = tool(search, "tools/interview_pack.py", "book", "Thornbury Bank", "--stage",
               "Final round", "--date", "2026-11-20", "--time", "14:00", "--zone",
               "America/Toronto", "--today", "2026-11-12")
    assert "- [ ] Final round (scheduled 2026-11-20 14:00 America/Toronto)" in _outcome(search)
    notes = _notes(search)
    assert notes.endswith(UNCHOSEN + " | " + BOOKED), notes
    assert "tracker" in out, out
    # Said again (the chat booking the same day twice, or a time added): once on the notes.
    tool(search, "tools/interview_pack.py", "book", "Thornbury Bank", "--stage", "Final round",
         "--date", "2026-11-20", "--time", "14:00", "--zone", "America/Toronto",
         "--today", "2026-11-12")
    assert _notes(search).count("2026-11-20") == 1, _notes(search)


def test_a_new_day_for_the_same_round_is_noted_as_well(search):
    tool(search, "tools/interview_pack.py", "book", "Thornbury Bank", "--stage", "Final round",
         "--date", "2026-11-20", "--today", "2026-11-12")
    tool(search, "tools/interview_pack.py", "book", "Thornbury Bank", "--stage", "Final round",
         "--date", "2026-11-24", "--today", "2026-11-13")
    notes = _notes(search)
    assert notes.endswith("2026-11-12: Final round booked for 2026-11-20 (chat) | "
                          "2026-11-13: Final round booked for 2026-11-24 (chat)"), notes


def test_a_tracker_an_older_version_left_saying_no_day_is_put_right_by_the_update(search):
    # Booked before this version: the day on outcome.md, the tracker still saying none.
    path = os.path.join(search.state, *OUTCOME)
    text = _outcome(search).replace("- [ ] Final round\n",
                                    "- [ ] Final round (scheduled 2026-11-20 14:00 America/Toronto)\n")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    before = [dict(r) for r in _rows(search)]
    out = tool(search, "tools/interview_pack.py", "booked-days")
    notes = _notes(search)
    assert notes.endswith(UNCHOSEN + " | 2026-11-12: Final round booked for 2026-11-20 at 14:00 "
                          "America/Toronto (from its interview record)"), notes
    assert "Thornbury Bank" in out, out
    # Nothing else on the tracker moved, and a second run changes nothing.
    after = _rows(search)
    assert [{k: v for k, v in r.items() if k != "notes"} for r in after] == \
        [{k: v for k, v in r.items() if k != "notes"} for r in before]
    assert [r["notes"] for r in after if r["company"] != "Thornbury Bank"] == \
        [r["notes"] for r in before if r["company"] != "Thornbury Bank"]
    tool(search, "tools/interview_pack.py", "booked-days")
    assert _notes(search) == notes


def test_a_booked_day_the_notes_never_spoke_of_is_left_alone_by_the_update(search):
    # The fixture's panel interview is booked for a day its notes never mention, and nothing
    # on the tracker says otherwise: the update leaves the person's notes as they are.
    _notes(search, "2026-10-20: phone screen went well")
    before = _notes(search)
    tool(search, "tools/interview_pack.py", "booked-days", today="2026-10-25")
    assert _notes(search) == before
