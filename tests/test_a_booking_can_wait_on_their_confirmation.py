"""A booked round or call can be asked for and not confirmed yet; a new day keeps the prep.

The maintainer, 2026-11-05: (12) a date asked for and not yet confirmed showed in Coming up as
if it were fixed; now a booking can be "Not confirmed yet", written on its own record, said on
Coming up and the Brief, ticked when the day is given and cleared once it is confirmed.
(13) A new day for the same round said "Prep is for an earlier plan of rounds": a date alone
leaves the plan as it was. (16) When the plan does change, the prep update starts by itself.
Every employer and person here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import docpaths  # noqa: E402
import upcoming  # noqa: E402
import what_works  # noqa: E402
import test_interviews_and_time_hold_from_the_audit as audit  # noqa: E402
from test_interviews_and_time_hold_from_the_audit import (  # noqa: E402
    CO, ROLE, _apply_outcome, _ctx, _outcome, _row)


@pytest.fixture
def where(tmp_path, monkeypatch):
    """A state folder and a profile of one's own (the audit test's own)."""
    yield from audit.where.__wrapped__(tmp_path, monkeypatch)


def _md():
    with open(os.path.join(docpaths.app_folder(CO, ROLE), "outcome.md"), encoding="utf-8") as fh:
        return fh.read()


def _iv():
    ctx = app_model.Ctx(dt.date(2026, 11, 3), app_model.parse_time("2026-11-03T09:00:00Z"))
    ctx._got["tracker"] = [_row()]
    return app_model._interviews(ctx, {})[0]


def test_a_round_asked_for_and_not_confirmed_says_so_until_it_is(where):
    got = _apply_outcome(where, {"stage": "Initial round", "on": "2026-11-12", "time": "10:00",
                                 "zone": "Europe/London", "tentative": True})
    assert "Not confirmed yet." in got["note"], got
    assert "- [ ] Initial round (scheduled 2026-11-12 10:00 Europe/London, not confirmed yet)" in _md()
    assert what_works.outcome_stages(_md())[0]["tentative"] is True
    (up,) = upcoming.build(_ctx("2026-11-03", "2026-11-03T09:00:00Z"))
    assert up["tentative"] is True and up["start"] == "2026-11-12T10:00:00Z"
    assert _iv()["tentative"] is True
    # A time added on its row says nothing about it: what the line said stays.
    _apply_outcome(where, {"stage": "Initial round", "on": "2026-11-12", "time": "11:00",
                           "zone": "Europe/London"})
    assert what_works.outcome_stages(_md())[0]["tentative"] is True
    # Booked again with the box clear: confirmed, said nowhere any more.
    _apply_outcome(where, {"stage": "Initial round", "on": "2026-11-12", "time": "11:00",
                           "zone": "Europe/London", "tentative": False})
    assert "not confirmed" not in _md()
    (up,) = upcoming.build(_ctx("2026-11-03", "2026-11-03T09:00:00Z"))
    assert up["tentative"] is False and "tentative" not in _iv()


def test_a_call_asked_for_and_not_confirmed_says_so(where, monkeypatch):
    import app_actions
    said = {}

    def fake_set(r, status, action, due, note):
        said.update(status=status, action=action, due=due)
        return {}
    monkeypatch.setattr(app_actions, "_set_contact", fake_set)
    run = types.SimpleNamespace(target={"kind": "person", "contact": "lark_ivo"},
                                value={"on": "2026-11-12", "time": "14:00", "zone": "Europe/London",
                                       "tentative": True},
                                day=dt.date(2026, 11, 3), local=dt.datetime(2026, 11, 3, 12, 0))
    run.words = lambda k="why": " ".join(str(run.value.get(k) or "").split())
    got = app_actions._call_booked(run)
    assert said["action"] == "Call on 2026-11-12 at 14:00, not confirmed yet: prepare for it", said
    assert "not confirmed yet" in got["note"]
    contact = {"contact_id": "lark_ivo", "name": "Ivo Lark", "company": "Larkmoor Bank",
               "status": "call_booked", "next_action": said["action"], "next_action_due": "2026-11-12"}
    (up,) = upcoming.build(_ctx("2026-11-03", "2026-11-03T09:00:00Z", tracker=[], contacts=[contact]))
    assert up["kind"] == "call" and up["tentative"] is True
    call = app_model._call_of("lark_ivo", "call_booked", "2026-11-12", said["action"], "Europe/London")
    assert call["tentative"] is True
    contact["next_action"] = "Call on 2026-11-12 at 14:00: prepare for it"
    (up,) = upcoming.build(_ctx("2026-11-03", "2026-11-03T09:00:00Z", tracker=[], contacts=[contact]))
    assert up["tentative"] is False


def _prep(folder, mark):
    path = os.path.join(folder, "interview_prep.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# Prep\n\n<!-- stages: %s -->\n" % mark)
    # The plan as it stood an hour ago, and the prep made after it.
    out = os.path.join(folder, "outcome.md")
    t = os.path.getmtime(out)
    os.utime(out, (t - 3600, t - 3600))
    os.utime(path, (t - 1800, t - 1800))
    return path


def test_a_new_day_alone_never_makes_the_prep_for_an_earlier_plan(where):
    # The prep names the round its own way ("First interview"): current, as the plan stands.
    folder = _outcome(["- [ ] Initial round (scheduled 2026-11-12)"])
    path = _prep(folder, "First interview")
    made = os.path.getmtime(path)
    assert "stale" not in _iv()["prep"]
    _apply_outcome(where, {"stage": "Initial round", "on": "2026-11-14"})
    iv = _iv()
    assert "stale" not in iv["prep"], iv["prep"]
    # The prep reads as made when it was, not now.
    assert os.path.getmtime(path) == made
    # A round that is new to the plan still makes it for an earlier plan.
    _apply_outcome(where, {"stage": "Final round", "on": "2026-11-10"})
    assert _iv()["prep"]["stale"] is True


def test_a_changed_plan_queues_the_prep_update_by_itself_once(where, tmp_path):
    import app
    model = {"interviews": [{"id": "int-quayside", "company": CO, "role": ROLE,
                             "prep": {"updated": "2026-11-01T09:00:00Z", "stale": True,
                                      "stale_since": "2026-11-03T08:00:00Z"}}],
             "ready": []}
    now = dt.datetime(2026, 11, 3, 9, 0, tzinfo=dt.timezone.utc)

    def queued(db):
        out = []
        for path in app.self_fixes(db, model, str(tmp_path / "self"), now):
            with open(path, encoding="utf-8") as fh:
                out += [e for e in json.load(fh) if e["collection"] == "work"]
        return out
    got = queued({"work": {}})
    assert [(e["doc_id"], e["op"]) for e in got] == [("prep~int-quayside", "set")], got
    # The prep made before the change is redone; one made since, or going now, is left alone.
    before = {"version": 3, "data": {"kind": "prep", "status": "done", "finished_at": "2026-11-01T09:00:00Z"}}
    assert [e["doc_id"] for e in queued({"work": {"prep~int-quayside": before}})] == ["prep~int-quayside"]
    since = {"version": 4, "data": {"kind": "prep", "status": "done", "finished_at": "2026-11-03T08:30:00Z"}}
    assert queued({"work": {"prep~int-quayside": since}}) == []
    going = {"version": 5, "data": {"kind": "prep", "status": "running"}}
    assert queued({"work": {"prep~int-quayside": going}}) == []
    # A prep a chat asked for under its own id, for the same interview and still going: never
    # a second one (the maintainer's copy, 2026-11-10: booking a round re-queued the pack
    # while a chat was building it).
    theirs = {"version": 2, "data": {"kind": "prep", "status": "running",
                                     "args": {"interview": "int-quayside"}}}
    assert queued({"work": {"prep~20261103T0850-ab12": theirs}}) == []
    waiting = {"version": 1, "data": {"kind": "prep", "status": "queued",
                                      "args": {"interview": "int-quayside"}}}
    assert queued({"work": {"prep~20261103T0850-ab12": waiting}}) == []
    # Once it has finished, an older pack is redone as before.
    over = dict(theirs, data=dict(theirs["data"], status="done", finished_at="2026-11-01T09:00:00Z"))
    assert [e["doc_id"] for e in queued({"work": {"prep~20261103T0850-ab12": over}})] == ["prep~int-quayside"]
