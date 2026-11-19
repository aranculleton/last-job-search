"""The day's tidy-up runs on a day the page's chat was renewed, never only the hand-over's step.

The page's chat is renewed at the first wake of every day, and after a hand-over each check-in
printed only `tidy: now` (one get_session of the helper taken over from, `tidy.py retire`) in
place of the day's tidy-up, asked again every half an hour for the rest of the day. So the
day's tidy-up never ran: no old helper of an earlier day, no chat the brief left and no chat
under an old name was put away or renamed, and the maintainer's chat list filled up from
16 November (issue #347). The day's tidy-up comes first, and judges the helper taken over
from as well (tidy.plan, `retiring`); only once it has run that day is the old helper asked
about on its own. Invented chats and page.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app  # noqa: E402
import tidy  # noqa: E402
from test_one_chat_answers_the_page import Copy  # noqa: E402

OLD = "session_EXAMPLEYESTERDAYSPAGE"
NEW = "session_EXAMPLETODAYSPAGE"
# A cloud chat on a machine in London, as the days below are London's: the tidy-up names its
# day by the machine's own clock (`tidy.py done`, the check-in), and on a machine 14 hours
# ahead or 11 behind these times fall on other days (Everywhere's ahead and behind, 4.17.0).
CLOUD = {"CLAUDE_CODE_REMOTE": "true", "TZ": "Europe/London"}


@pytest.fixture
def copy(tmp_path):
    c = Copy(tmp_path)
    # The tidy-up keeps its day in the copy's git folder, as a person's copy has one.
    subprocess.run(["git", "init", "-q", c.state], check=True, timeout=60)
    c.page()
    yield c
    sys.path.remove(c.root)


def _mark(copy, day, at):
    """The day's tidy-up done, as `tidy.py done` writes it onto the page (meta/tidy)."""
    with open(os.path.join(copy.db, "meta", "tidy.json"), "w", encoding="utf-8") as fh:
        json.dump({"data": {"checked": day, "at": at, "sweep": tidy.SWEEP}, "version": 1}, fh)


def _listen(copy, chat, at, *extra):
    said = copy.run("listen", copy.dump(), "--chat", chat, *extra, "--now", at, **CLOUD)
    assert copy.send(said)
    return said


def _tidy_lines(said):
    return [ln for ln in said.splitlines() if ln.startswith("tidy:")]


def test_every_check_in_on_a_renewal_day_runs_the_days_tidy_up_until_it_is_done(copy):
    _listen(copy, OLD, "2026-11-17T12:00:00Z", "--helper")
    _mark(copy, "2026-11-17", "2026-11-17T12:10:00Z")             # yesterday's ran
    # The first wake of a new day: a fresh helper takes the page from yesterday's.
    took = _listen(copy, NEW, "2026-11-18T08:00:00Z", "--listen", "--helper")
    assert "this chat answers the page now" in took
    assert copy.listener()["took_from"] == OLD
    # Its take-over and every check-in after it, half an hour apart or more, until the day's
    # tidy-up is done: the whole of it, never the hand-over's step in its place.
    for said in (took, _listen(copy, NEW, "2026-11-18T10:00:00Z"),
                 _listen(copy, NEW, "2026-11-18T15:30:00Z")):
        lines = _tidy_lines(said)
        assert lines and lines[0].startswith(app.TIDY_SAID), lines
        assert "tidy.py retire" not in said and "list_sessions" in said
    # Done today, with the old helper kept for now: later check-ins ask about it alone.
    _mark(copy, "2026-11-18", "2026-11-18T15:35:00Z")
    said = _listen(copy, NEW, "2026-11-18T16:30:00Z")
    assert _tidy_lines(said) == [app.TIDY_NOW.format(old=OLD)]
    assert "list_sessions" not in said
