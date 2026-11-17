"""A profile read already done and saved is never queued again, and its repeat can be closed.

Issue 318: a read for the person's computer (`network~read~...`, `to: computer`, `auto: true`)
was queued by a page update for the same people the chat on the computer had read and saved
minutes earlier. That read had finished just before midnight, so the guard that keeps a day's
read from being queued twice (its id carries the day) let the next day's page update through,
and the profiles had not reached this copy yet, so nothing else knew they were read. The repeat
showed as "Waiting for your computer", and a cloud chat could not close it (`app.py done`
refuses work for the computer). Now a read that finished in the last day keeps its people off
the next one, whatever its id, and a cloud chat may close a read for the computer as done once
every profile in it is proven read: saved in this copy, or read by another read the page shows
done. Otherwise it is told why, in plain words. Every id and name here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import pytest  # noqa: E402

import app  # noqa: E402
import page_db  # noqa: E402
import reading  # noqa: E402

UTC = dt.timezone.utc
# Twenty-two minutes past midnight, as the maintainer's own copy met it (London is on UTC then).
NOW = dt.datetime(2026, 11, 17, 0, 22, tzinfo=UTC)
CLOUD = "session_EXAMPLECLOUDCHAT"
MAC = "session_EXAMPLEMACCHAT"


def _model():
    return {"person": {"computer": True},
            "linkedin": {"reading": {"setting": "browser", "paused": False, "queue": [
                {"id": "read-kit_a", "contact": "kit_a", "first_name": "Kit"}]}},
            "to_read": {"n": 2, "ids": ["msg-kit_a", "msg-ash_b"], "contacts": ["kit_a", "ash_b"]}}


def _read(contacts, status="done", finished="2026-11-16T23:52:00Z", asked="2026-11-16T23:20:00Z"):
    fields = page_db.queued("network", "Reading 2 profiles on your computer",
                            {"contacts": list(contacts), "read_first": True, "rewrite": True,
                             "auto": True}, dt.datetime(2026, 11, 16, 23, 20, tzinfo=UTC))
    fields.update(to="computer", status=status, asked_at=asked)
    if status != "queued":
        fields.update(finished_at=finished, claimed_by=MAC, claimed_as="computer",
                      result={"summary": "Read 2 profiles and rewrote their notes.", "links": []})
    return fields


@pytest.fixture
def unsaved_here(monkeypatch):
    """Nobody's profile has reached this copy yet: the save from the computer is on its way."""
    monkeypatch.setattr(reading, "load", lambda cid: None)


def test_a_read_finished_just_before_midnight_keeps_its_people_off_the_next_days_read(unsaved_here):
    wid = page_db.safe_id(app.COMPUTER_READS + "20261116~abc123")
    work = {wid: {"data": _read(["kit_a", "ash_b"]), "version": 6}}
    assert app.computer_reads(_model(), work, NOW) is None
    # A day on, the profiles still not in this copy (that save never came): read again, once.
    again = app.computer_reads(_model(), work, NOW + dt.timedelta(days=1))
    assert again and again[1]["args"]["contacts"] == ["kit_a", "ash_b"], again


def test_a_read_of_one_person_asked_on_the_page_keeps_them_off_the_automatic_read(unsaved_here):
    """"Go ahead anyway" read one person under an id of its own, finished minutes ago: only
    the other is still owed a read."""
    work = {"network~anyway~kit_a": {"data": _read(["kit_a"], finished="2026-11-17T00:15:00Z",
                                                   asked="2026-11-17T00:05:00Z"), "version": 4}}
    got = app.computer_reads(_model(), work, NOW)
    assert got and got[1]["args"]["contacts"] == ["ash_b"], got


# ------------------------------------------------------------------ a cloud chat closes the repeat


def _dump(tmp_path, work):
    where = tmp_path / "d" / "work"
    where.mkdir(parents=True)
    for wid, (fields, version) in work.items():
        (where / (wid.replace("~", "@") + ".json")).write_text(
            json.dumps(dict(fields, _v=version)), encoding="utf-8")
    return str(tmp_path / "d")


REPEAT = page_db.safe_id(app.COMPUTER_READS + "20261117~def456")


def _done(capsys, d, *more):
    code = app.main(["done", d, "--work", REPEAT, "--chat", CLOUD, "--kind", "cloud",
                     "--now", "2026-11-17T00:40:00Z", *more])
    out = capsys.readouterr()
    return code, out.out, out.err


def _finished(out):
    got = json.loads(out)
    for p in got["batches"]:
        for e in json.load(open(p, encoding="utf-8")):
            if e["collection"] == "work" and e["doc_id"] == REPEAT:
                return json.load(open(e["file_path"], encoding="utf-8"))
    raise AssertionError(out)


def test_a_cloud_chat_closes_a_repeat_whose_profiles_are_saved_here(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(reading, "load", lambda cid: {"read_on": "2026-11-16", "sources": [
        {"kind": "browser"}]})
    monkeypatch.setattr(reading, "fresh", lambda got, today=None, signed_in_now=None: bool(got))
    d = _dump(tmp_path, {REPEAT: (_read(["kit_a", "ash_b"], status="queued"), 1)})
    code, out, err = _done(capsys, d)
    assert code == 0, err
    fields = _finished(out)
    assert fields["status"] == "done" and fields["result"]["summary"].startswith("Already read"), fields


def test_a_cloud_chat_closes_a_repeat_another_finished_read_already_did(tmp_path, capsys, unsaved_here):
    first = page_db.safe_id(app.COMPUTER_READS + "20261116~abc123")
    d = _dump(tmp_path, {REPEAT: (_read(["kit_a", "ash_b"], status="queued"), 1),
                         first: (_read(["kit_a", "ash_b"]), 6)})
    code, out, err = _done(capsys, d, "--summary", "Already read on your computer last night.")
    assert code == 0, err
    assert _finished(out)["status"] == "done"


def test_a_repeat_not_yet_read_is_left_for_the_computer_with_a_plain_reason(tmp_path, capsys,
                                                                             unsaved_here):
    first = page_db.safe_id(app.COMPUTER_READS + "20261116~abc123")
    d = _dump(tmp_path, {REPEAT: (_read(["kit_a", "ash_b"], status="queued"), 1),
                         first: (_read(["kit_a"]), 6)})
    code, out, err = _done(capsys, d)
    assert code == 2 and not out, out
    assert "not finished" in err and "1 of its 2 profiles" in err and "ash_b" in err, err
    assert "leave it" in err.lower(), err
    # Failing it is still never a cloud chat's.
    code, out, err = _done(capsys, d, "--failed", "Could not read them here.")
    assert code == 2 and page_db.COMPUTER_ONLY_REFUSAL in err, err
