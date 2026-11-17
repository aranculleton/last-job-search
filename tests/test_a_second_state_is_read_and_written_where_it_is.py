"""A process that moves to another state reads and writes that state's contact book (issue 340).

tools/network/state.py fixed where the contact book and the message log were when it was first
loaded, and its load and save took those paths as default arguments. A process that set
LJS_STATE afterwards still read, and wrote, the first state's book: a page built for a second
state in the same process showed the first state's holds (app_model._rules, holds.live), and
lifting a hold from it wrote the first state's book.

Built on the real path: two copies of the example's small search, the page model built for
one and then the other in one process, and a hold lifted the way the page's pill lifts it
(holds.lift). Every person and employer here is invented.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"),
           os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_model  # noqa: E402
import app_state  # noqa: E402
import holds  # noqa: E402
from network import state  # noqa: E402

CID = "larchway_lowe"
HOLD = "On hold until 2026-11-20: she is back from leave then"


def _add(path, rows):
    have = app_state._csv_rows(path)
    cols = list(have[0].keys()) if have else []
    for r in rows:
        cols += [k for k in r if k not in cols]
    app_state._save_csv(path, have + rows, cols)


def _book(st):
    return {r["contact_id"]: r for r in app_state._csv_rows(os.path.join(st, "network_contacts.csv"))}


@pytest.fixture
def two(tmp_path, monkeypatch):
    """Two searches: the first the example's own, the second the same with one person on hold."""
    first = app_state.small(str(tmp_path / "first"))
    second = app_state.small(str(tmp_path / "second"))
    _add(os.path.join(second, "network_contacts.csv"), [{
        "contact_id": CID, "name": "Odile Lowe", "title": "Data Lead",
        "company": "Larchway Credit", "company_key": "larchway credit",
        "location": "Manchester, England, United Kingdom",
        "linkedin_url": "https://www.linkedin.com/in/larchway-lowe-example",
        "tier": "2", "route": "cold", "channel": "message", "status": "in_conversation",
        "first_contacted": "2026-10-01", "next_action": HOLD, "next_action_due": ""}])
    monkeypatch.setenv("LJS_COPY", "private")
    monkeypatch.delenv("LJS_TODAY", raising=False)
    return first, second


def _people_held(m):
    return [h["what"] for h in m["rules"]["held"] if h["rule"] == "person_hold"]


def test_a_build_for_a_second_state_shows_that_states_holds(two, monkeypatch):
    first, second = two
    today, now = app_model.clock(app_state.TODAY, app_state.NOW)
    monkeypatch.setenv("LJS_STATE", first)
    m, _ = app_model.build(today, now)
    assert _people_held(m) == []
    monkeypatch.setenv("LJS_STATE", second)
    m, _ = app_model.build(today, now)
    assert _people_held(m) == ["Odile Lowe"]
    # And back: the first state's page holds nobody again.
    monkeypatch.setenv("LJS_STATE", first)
    m, _ = app_model.build(today, now)
    assert _people_held(m) == []


def test_a_hold_lifted_after_the_move_is_written_to_the_second_states_book(two, monkeypatch):
    first, second = two
    today, now = app_model.clock(app_state.TODAY, app_state.NOW)
    monkeypatch.setenv("LJS_STATE", first)
    app_model.build(today, now)
    before = open(os.path.join(first, "network_contacts.csv"), encoding="utf-8").read()
    monkeypatch.setenv("LJS_STATE", second)
    held = [h for h in holds.live(today) if h["rule"] == "person_hold"]
    assert [h["what"] for h in held] == ["Odile Lowe"], held
    said = holds.lift(held[0]["id"], today)
    assert "Odile Lowe" in said and "off hold" in said, said
    assert _book(second)[CID]["next_action"] != HOLD
    # The first state's book is as it was, and nobody was added to it.
    assert open(os.path.join(first, "network_contacts.csv"), encoding="utf-8").read() == before


def test_load_and_save_read_the_state_at_the_moment_of_each_call(two, monkeypatch):
    first, second = two
    monkeypatch.setenv("LJS_STATE", first)
    assert CID not in {r["contact_id"] for r in state.load_contacts()}
    monkeypatch.setenv("LJS_STATE", second)
    rows = state.load_contacts()
    assert CID in {r["contact_id"] for r in rows}
    for r in rows:
        if r["contact_id"] == CID:
            r["notes"] = "met at a meetup"
    state.save_contacts(rows)
    assert _book(second)[CID]["notes"] == "met at a meetup"
    assert CID not in _book(first)
    assert state.contacts_csv() == os.path.join(second, "network_contacts.csv")
    assert state.threads_csv() == os.path.join(second, "network_threads.csv")
    assert state.tracker_csv() == os.path.join(second, "job_search_tracker.csv")
