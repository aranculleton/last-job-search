"""A chat put away never shows on the page as busy (issue 318).

A page chat archived after a fresh one took the page over left its busy line on the page's
Claude's work panel ("Job search: reading 40 postings, about half done"), so the page said
work was running that no chat was doing. `tidy.py retire` did not clear it, and the way round
it was `app.py busy --done --chat <the old chat>` by hand. Now retiring a chat takes its line
off the page, and every tidy-up and every page update takes off the line of each chat recorded
as put away, so a line an older version left on someone's page clears by itself. A chat still
at work keeps its line. Every id here is invented.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import page_db  # noqa: E402
import tidy  # noqa: E402

REPO = "example-owner/example-copy"
LIVE = "session_EXAMPLENEWHELPER"
OLD = "session_EXAMPLEOLDHELPER"
LISTENER = {"chat": LIVE, "helper": True, "took_from": OLD, "took_from_helper": True,
            "since": "2026-11-10T11:30:00Z"}
OLD_LINE = "Job search: reading 40 postings, about half done. People search: finding 7 more"
LIVE_LINE = "Answering your question about Acme"


def _beat(line, seen="2026-11-10T11:50:00Z"):
    return {"kind": "cloud", "title": "Last Job Search · Page", "can": [], "seen_at": seen,
            "busy": line}


def _dump(root, beats):
    """A wake's read of the page's heartbeats, as a chat's read saves it."""
    where = os.path.join(root, "beats")
    os.makedirs(where, exist_ok=True)
    for cid, (fields, version) in beats.items():
        with open(os.path.join(where, cid + ".json"), "w", encoding="utf-8") as fh:
            json.dump(dict(fields, _v=version), fh)
    return str(root)


def _writes(paths):
    """{(collection, doc id): (if_version, body)} for every write in the batches printed."""
    out = {}
    for p in paths:
        for e in json.load(open(p, encoding="utf-8")):
            body = json.load(open(e["file_path"], encoding="utf-8")) if e.get("file_path") else None
            out[(e["collection"], e["doc_id"])] = (e.get("if_version"), body)
    return out


def _detail(status="idle", updated="2026-11-10T11:58:00Z"):
    return {"id": OLD, "title": "Last Job Search · Page", "status": status,
            "updated_at": updated, "session_context": {"sources": [{"git_repository": {
                "url": f"https://github.com/{REPO}"}}], "outcomes": []}}


@pytest.fixture
def helper(monkeypatch, tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setattr(tidy, "_record_path", lambda: str(profile / "tidy.json"))
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(tmp_path))
    monkeypatch.setattr(tidy, "_listener", lambda dump: LISTENER)
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda *_: set())
    monkeypatch.setattr(tidy, "on_github", lambda: set())
    return tmp_path


def _retire(monkeypatch, capsys, dump, detail):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"details": detail})))
    a = argparse.Namespace(dump=dump, stdin=True, details=[], now="2026-11-10T12:00:00Z")
    assert tidy.run_retire(a) == 0
    out = capsys.readouterr().out
    return out, [ln.strip() for ln in out.splitlines() if ln.strip().endswith(".json")]


@pytest.mark.parametrize("status", ["archived", "idle"])
def test_retiring_the_helper_taken_over_from_takes_its_busy_line_off_the_page(
        helper, monkeypatch, capsys, status):
    """Archived already (it put itself away), or quiet with its work still saving: either way
    it does nothing for the person any more, so its line comes off. The live chat's stays."""
    d = _dump(helper / "d", {OLD: (_beat(OLD_LINE), 4), LIVE: (_beat(LIVE_LINE), 2)})
    out, paths = _retire(monkeypatch, capsys, d, _detail(status=status))
    writes = _writes(paths)
    assert writes == {(page_db.STORE["chats"], OLD): (4, {"busy": None, "_v": 5})}, out
    assert "ArtifactData batch" in out and "asking nobody" in out, out
    # The folder is as the batch leaves it, so the next command over it pins to version 5.
    assert page_db.load(d)["chats"][OLD]["data"].get("busy") is None


def test_a_helper_taken_over_from_that_is_still_at_work_keeps_its_line(helper, monkeypatch, capsys):
    d = _dump(helper / "d", {OLD: (_beat(OLD_LINE), 4)})
    out, paths = _retire(monkeypatch, capsys, d, _detail(status="running"))
    assert not paths and "kept for now" in out, out


def test_the_days_tidy_up_takes_off_the_line_of_every_chat_put_away(helper, capsys):
    """An older version left the line of a chat it recorded as put away: the day's tidy-up,
    which reads the heartbeats with the page, takes it off by itself."""
    tidy._record([OLD], {OLD: "Last Job Search · Page"}, "2026-11-09")
    d = _dump(helper / "d", {OLD: (_beat(OLD_LINE), 7), LIVE: (_beat(LIVE_LINE), 2)})
    assert tidy.main(["done", "--today", "2026-11-10", "--dump", d]) == 0
    out = capsys.readouterr().out
    writes = _writes([ln.strip() for ln in out.splitlines() if ln.strip().endswith(".json")])
    assert writes[(page_db.STORE["chats"], OLD)] == (7, {"busy": None, "_v": 8}), out
    assert (page_db.STORE["chats"], LIVE) not in writes, out


def test_only_a_busy_line_of_a_chat_put_away_is_written(tmp_path):
    """No line, a chat brought back, or one never put away: nothing written for it."""
    db = page_db.load(_dump(tmp_path / "d", {OLD: (_beat(OLD_LINE), 3), LIVE: (_beat(LIVE_LINE), 2),
                                             "session_QUIET": (_beat(None), 5)}))
    assert page_db.clear_busy(db, {"session_QUIET", "session_NEVERSEEN"}, str(tmp_path / "o")) == []
    got = _writes(page_db.clear_busy(db, {OLD}, str(tmp_path / "o2")))
    assert list(got) == [(page_db.STORE["chats"], OLD)]


def test_a_page_update_takes_off_the_line_of_a_chat_put_away_before(tmp_path):
    """The real page update (`app.py view`) over a page an older version left a put-away chat's
    line on: once its batches are sent, the line is gone and the live chat's is kept."""
    import test_one_chat_answers_the_page as one
    from test_a_page_from_4_2_moves_to_its_new_names import read
    c = one.Copy(tmp_path)
    try:
        c.page(current=True)
        with open(os.path.join(c.profile, "tidy.json"), "w", encoding="utf-8") as fh:
            json.dump({"archived": [{"id": OLD, "title": "Last Job Search · Page",
                                     "on": "2026-10-24"}]}, fh)
        os.makedirs(os.path.join(c.db, "beats"))
        for cid, line, v in ((OLD, OLD_LINE, 4), (LIVE, LIVE_LINE, 2)):
            with open(os.path.join(c.db, "beats", cid + ".json"), "w", encoding="utf-8") as fh:
                json.dump({"data": dict(_beat(line, "2026-10-25T17:30:00Z"), _v=v), "version": v}, fh)
        d = read(c, os.path.join(c.root, "read"), ("screen", "meta", "addr", "work", "holds", "beats"))
        out = json.loads(c.run("view", os.path.join(c.root, "out"), "--dump", d,
                               "--now", "2026-10-25T18:00:00Z", "--chat", LIVE))
        assert c.send("\n".join(out["batches"])), out
        beats = {cid: json.load(open(os.path.join(c.db, "beats", cid + ".json"), encoding="utf-8"))
                 for cid in (OLD, LIVE)}
        assert beats[OLD]["data"].get("busy") is None, beats[OLD]
        assert beats[LIVE]["data"]["busy"] == LIVE_LINE, beats[LIVE]
    finally:
        sys.path.remove(c.root)
