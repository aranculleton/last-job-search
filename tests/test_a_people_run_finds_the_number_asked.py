"""A people run asked for a number finds and drafts that many, or says plainly why it could not.

The maintainer's page, 2026-11-12: Contacts, Find people, 20. The run (a chat on their
computer, reading LinkedIn in Claude's browser) read 10 profiles, kept 8, wrote 8 notes and
finished the item as done, `count: {done: 8, total: 20}`, its summary "8 recruiter notes
ready" and not a word about the other 12. The number asked is a target, not a cap: a finish
short of it is refused, and only a run that has truly run out of good people within the
person's rules finishes short, saying so ("8 of 20: ..."), kept as part-done
(`result.short`), never plainly done. Invented employers and chats only.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import page_db  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import T  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search, _w  # noqa: E402

WID = "network~targets~20261112T0900"
TITLE = "People at the employers you want"
SHORT_WHY = "no more good people at your employers right now"


def _running(args: dict, count: dict | None = None) -> dict:
    """The item as the run on the computer leaves it before its finish."""
    d = _w("network", to="computer", title=TITLE, status="running", claimed_by="mac-1",
           claimed_as="computer", claimed_at="2026-10-25T17:00:00Z",
           lease_until="2026-10-25T19:00:00Z", args=args,
           stages=page_db.progress("network")["stages"], stage=4)
    if count:
        d["count"] = count
    return d


def _finish(tmp_path, item: dict, **kw):
    db = {"work": {WID: {"data": item, "version": 6}}, "locks": {}, "chats": {}}
    return page_db.finish(db, WID, T, str(tmp_path / "out"), chat="mac-1",
                          chat_kind="computer", **kw)


def _written(got: dict) -> dict:
    for path in got["batches"]:
        with open(path, encoding="utf-8") as fh:
            for e in json.load(fh):
                if e["doc_id"] == WID and e.get("file_path"):
                    with open(e["file_path"], encoding="utf-8") as b:
                        return json.load(b)
    raise AssertionError("the finish wrote nothing to the item")


def test_a_run_asked_for_twenty_is_never_finished_as_done_at_eight(tmp_path):
    item = _running({"count": 20}, {"done": 8, "total": 20})
    # As the run finished it on 2026-11-12: refused, saying how many and what to do next.
    with pytest.raises(ValueError) as e:
        _finish(tmp_path, item, summary="8 recruiter notes ready at six employers.")
    said = str(e.value)
    assert "8 of the 20" in said and "keep finding" in said and "--short" in said
    # Saying the number does not make 8 enough.
    with pytest.raises(ValueError):
        _finish(tmp_path, item, summary="8 recruiter notes ready at six employers.", drafted=8)
    # A run that never said how far it got is asked to say it.
    with pytest.raises(ValueError) as e:
        _finish(tmp_path, _running({"count": 20}), summary="Notes ready at six employers.")
    assert "--drafted" in str(e.value)


def test_a_run_that_truly_ran_out_finishes_part_done_and_says_so(tmp_path):
    item = _running({"count": 20}, {"done": 8, "total": 20})
    # Its summary says how many of how many: "8 notes ready" alone hid the other 12.
    with pytest.raises(ValueError) as e:
        _finish(tmp_path, item, summary="8 recruiter notes ready at six employers.",
                drafted=8, short=SHORT_WHY)
    assert "8 of 20" in str(e.value)
    got = _finish(tmp_path, item, summary=f"8 of 20: {SHORT_WHY}.", drafted=8, short=SHORT_WHY)
    body = _written(got)
    assert body["status"] == "done"
    assert body["result"]["short"] == {"done": 8, "total": 20, "why": SHORT_WHY}
    assert body["count"] == {"done": 8, "total": 20, "word": page_db.DRAFTED}
    assert body["result"]["summary"].startswith("8 of 20")


def test_a_run_that_drafted_the_number_asked_is_done(tmp_path):
    got = _finish(tmp_path, _running({"count": 20}, {"done": 20, "total": 20}),
                  summary="20 notes ready at nine employers.", drafted=20)
    body = _written(got)
    assert body["status"] == "done" and "short" not in body["result"]
    assert body["count"] == {"done": 20, "total": 20, "word": page_db.DRAFTED}


def test_work_that_asks_for_no_number_is_finished_as_before(tmp_path):
    # Notes rewritten from profiles just read, and one employer's own Find people.
    for args in ({"contacts": ["fern_aldous_fernhill"], "rewrite": True, "read_first": True},
                 {"company": "Fernhill Freight"}):
        got = _finish(tmp_path, _running(args), summary="Your notes are ready.")
        assert _written(got)["status"] == "done"
    # A stop, a failure and a question are never held to the number.
    item = _running({"count": 20}, {"done": 8, "total": 20})
    assert _written(_finish(tmp_path, item, status="failed",
                            error="LinkedIn asked for a check."))["status"] == "failed"


def test_the_finish_the_computer_chat_runs_is_refused_short_of_the_number(tmp_path):
    """On the real path: `next` claims it on the computer, the run pins how far it got, and
    `app.py done` as it was run on 2026-11-12."""
    s = Search(str(tmp_path))
    s.put("work", WID, _w("network", to="computer", title=TITLE, args={"count": 20}), version=4)
    got = json.loads(s.run("next", s.dump, "--chat", "mac-1", "--kind", "computer",
                           "--computer-only", "--claim-out", os.path.join(s.dump, "claim"),
                           "--now", NOW))
    assert got["work"] == WID
    s.run("pin", s.dump, "--work", WID, "--chat", "mac-1", "--stage", "check", "--done", "8",
          "--total", "20", "--line", "Checking the notes.", "--now", NOW)
    done = ("done", s.dump, "--work", WID, "--chat", "mac-1", "--kind", "computer", "--now", NOW)
    s.run(*done, "--summary", "8 recruiter notes ready at six employers.", ok=(2,))
    assert page_db.load(s.dump)["work"][WID]["data"]["status"] == "running"
    s.run(*done, "--summary", f"8 of 20: {SHORT_WHY}.", "--drafted", "8", "--short", SHORT_WHY)
    item = page_db.load(s.dump)["work"][WID]["data"]
    assert item["status"] == "done" and item["result"]["short"]["total"] == 20


def test_what_the_run_is_told_says_the_number_is_a_target():
    import app
    row = app.work_row("network")
    assert "at most" not in row
    assert "target" in row and "--drafted" in row and "--short" in row
    with open(os.path.join(ROOT, ".claude", "commands", "network.md"), encoding="utf-8") as fh:
        text = " ".join(fh.read().split())
    assert "--drafted <n>" in text and "--short" in text


def test_a_progress_count_never_says_more_done_than_its_total(tmp_path):
    """Seen live on "12 more people at the employers you want": "14 found, including two
    employers; reading profiles, 14 of 12 done". Found people were counted against the notes
    wanted. Reading is counted against the people being read ("9 of 14 read"), and the number
    asked is a figure of its own: a count past its total is never written."""
    item = _running({"count": 12})
    item.update(stage=2, stage_at="2026-10-25T17:30:00Z")
    db = {"work": {WID: {"data": item, "version": 6}}, "locks": {}, "chats": {}}
    got = page_db.pin(db, WID, T, str(tmp_path / "p1"), stage="read",
                      line="14 found; reading profiles", count={"done": 14, "total": 12},
                      chat="mac-1")
    assert got["count"] is None and "14 of 12" in got["count_refused"]
    assert "people being read" in got["count_refused"]
    written = _written(got)
    assert "count" not in written and written["steps"][-1]["text"] == "14 found; reading profiles"
    got = page_db.pin(db, WID, T, str(tmp_path / "p2"), stage="read", line="Reading profiles",
                      count={"done": 9, "total": 14, "word": "read"}, chat="mac-1")
    assert _written(got)["count"] == {"done": 9, "total": 14, "word": "read"}


def test_the_run_is_told_to_count_reading_against_the_people_being_read():
    with open(os.path.join(ROOT, ".claude", "commands", "network.md"), encoding="utf-8") as fh:
        text = " ".join(fh.read().split())
    assert "--done <found so far> --total <N>" not in text
    assert "--done <read so far> --total <on the list to read> --word read" in text
    import subprocess
    said = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "pin",
                           "--help"], capture_output=True, text=True, encoding="utf-8").stdout
    assert "--word" in said
