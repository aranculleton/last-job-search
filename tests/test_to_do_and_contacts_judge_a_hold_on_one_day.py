"""To do, Contacts and Messages judge one person's hold on the day the page is built for
(issue 341).

The person's own surface rules (surface.held) are asked three times a build for the same
person: by Contacts (app_model._people), on the build's own day, and by To do, through
open_actions._hold_by_rule, and Messages (app_model._messages), which passed no day and so read
the computer's. On a page built for another day than the computer's (`app.py page --now`, the
time variants of the everywhere check), a rule that turns on a day count held someone on
Contacts and offered them on To do, or the other way round.

Built on the real path: the example person's state with one person added, a page model built
for one day while the computer's clock says another, and the person's own quiet days after a
message (networking.py QUIET_AFTER_SEND_DAYS). Every person and employer here is invented.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import pytest
import time_machine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"),
           os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_model  # noqa: E402
import app_state  # noqa: E402
from network import surface  # noqa: E402

CID = "fennick_ardent"
# Our last message went on 21 October; with ten quiet days nothing more goes before the 31st.
LAST_SENT = "2026-10-21"
HELD = "Written to on 2026-10-21: nothing more until 2026-10-31"
EARLY = dt.datetime(2026, 10, 25, 18, tzinfo=dt.timezone.utc)      # inside the quiet days
LATE = dt.datetime(2026, 11, 5, 18, tzinfo=dt.timezone.utc)        # past them


def _add(path, rows):
    have = app_state._csv_rows(path)
    cols = list(have[0].keys()) if have else []
    for r in rows:
        cols += [k for k in r if k not in cols]
    app_state._save_csv(path, have + rows, cols)


@pytest.fixture
def state(tmp_path, monkeypatch):
    """The example's small search and one person in conversation, with a step of the
    person's own dated before either day, a message to her drafted and waiting, and the
    person's quiet days set to ten."""
    st = app_state.small(str(tmp_path / "state"))
    _add(os.path.join(st, "network_contacts.csv"), [{
        "contact_id": CID, "name": "Ilsa Ardent", "title": "Data Lead",
        "company": "Fennick Lending", "company_key": "fennick lending",
        "location": "Manchester, England, United Kingdom",
        "linkedin_url": "https://www.linkedin.com/in/fennick-ardent-example",
        "tier": "2", "route": "cold", "channel": "message", "status": "in_conversation",
        "first_contacted": "2026-10-01",
        "next_action": "Ask how the credit analytics team is set up",
        "next_action_due": "2026-10-24"}])
    _add(os.path.join(st, "network_threads.csv"), [
        {"contact_id": CID, "date": "2026-10-01", "direction": "out", "channel": "connection",
         "scenario": "connection_note", "summary": "First note sent",
         "full_text": "Hi Ilsa, hope you're well. I build demand forecasts in Manchester."},
        {"contact_id": CID, "date": "2026-10-08", "direction": "in", "channel": "message",
         "scenario": "", "summary": "Happy to talk", "full_text": "Happy to talk, Morgan."},
        {"contact_id": CID, "date": LAST_SENT, "direction": "out", "channel": "message",
         "scenario": "reply", "summary": "Thanked them",
         "full_text": "Thanks Ilsa, I will come back with a question or two."}])
    app_state._write(os.path.join(st, "documents", "network", CID, "draft.md"),
                     "Hi Ilsa, how is the credit analytics team set up at Fennick Lending?\n")
    monkeypatch.setenv("LJS_STATE", st)
    monkeypatch.setenv("LJS_COPY", "private")
    monkeypatch.delenv("LJS_TODAY", raising=False)
    # The person's "nobody written to in the last ten days" (networking.py), on the module
    # every copy of the one check reads it from.
    monkeypatch.setattr(surface.state.schema, "QUIET_AFTER_SEND_DAYS", 10)
    return st


def _build(day: dt.datetime, clock: dt.datetime) -> dict:
    """The page model built for `day` while the computer's clock says `clock`."""
    with time_machine.travel(clock, tick=False):
        today, now = app_model.clock(day.date().isoformat(), day.isoformat())
        m, _ = app_model.build(today, now)
    return m


def _contacts_row(m):
    return next(p for p in m["people"] if p["id"] == CID)


def _to_do(m):
    return [d for d in m["due"] if d.get("item") == CID]


def _messages(m):
    return [d for d in m["messages"] if d.get("contact") == CID or d.get("item") == CID]


@pytest.mark.parametrize("day, clock", [(EARLY, LATE), (LATE, EARLY)],
                         ids=["built inside the quiet days, clock past them",
                              "built past the quiet days, clock inside them"])
def test_to_do_and_contacts_agree_whatever_the_computers_clock_says(state, day, clock):
    m = _build(day, clock)
    row, todo, waiting = _contacts_row(m), _to_do(m), _messages(m)
    if day == EARLY:
        # Held on the build's day: Contacts says why, and neither To do nor Messages offers
        # anything to send her.
        assert row["hold"] == HELD, row
        assert todo == [], todo
        assert waiting == [], waiting
    else:
        # Past the quiet days on the build's day: nothing holds her, her step is on To do and
        # the note drafted to her waits in Messages.
        assert row["hold"] is None, row
        assert len(todo) == 1, todo
        assert len(waiting) == 1, waiting


def test_the_same_day_gives_the_same_page_whatever_the_clock(state):
    """A page built for one day is the same page on any computer clock: what To do and
    Contacts say of her is decided by the build's day alone."""
    a, b = _build(EARLY, EARLY), _build(EARLY, LATE)
    assert _contacts_row(a)["hold"] == _contacts_row(b)["hold"] == HELD
    assert _to_do(a) == _to_do(b) == []
    assert _messages(a) == _messages(b) == []


def test_a_draft_checked_for_a_day_is_held_as_that_days_list_holds_it(state):
    """The gate for drafts written by hand (followup_drafts.check) is given the day of the due
    list it checks against, and holds a draft by the person's rules on that day too."""
    import followup_drafts
    from network import state as book
    contacts = book.load_contacts(os.path.join(state, "network_contacts.csv"))
    threads = book.load_threads(os.path.join(state, "network_threads.csv"))
    draft = [{"id": CID, "kind": "nudge", "owed": "nudge",
              "text": "Hi Ilsa, how is the credit analytics team set up at Fennick Lending?"}]
    with time_machine.travel(LATE, tick=False):
        got = followup_drafts.check(draft, contacts, threads, EARLY.date().isoformat())
    assert got[0]["held"] == HELD, got[0]
    with time_machine.travel(EARLY, tick=False):
        got = followup_drafts.check(draft, contacts, threads, LATE.date().isoformat())
    assert not got[0].get("held"), got[0]
