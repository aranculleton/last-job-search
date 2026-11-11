"""A finished job chat whose work never reached GitHub is asked to save it, once, then said.

The maintainer's copy, 2026-11-06: the "Finding jobs" chat timed out while saving, its work
on no branch at all. It reported "not landed", the chat that answers the page kept it ("its
work is not on GitHub yet") and said nothing, and the chat sat in the person's list. Now the
chat that answers the page notices "finished, not landed, nothing pushed": it first asks that
chat, once, to save its work to GitHub (land.py --keep, no check); if it still is not there,
the work's own card on the page says plainly that it was lost, with Try again, and the chat is
put away. Said once. Every id, title and page here is invented.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import land  # noqa: E402
import page_db  # noqa: E402
import tidy  # noqa: E402
from test_a_beginner_is_told_in_plain_words import _plain  # noqa: E402
from test_a_finished_chat_closes_at_once_and_one_page_helper_stays import (  # noqa: E402
    LIVE, REPO, _chat, _detail, _json, copy)

JOB = "session_EXAMPLEFINDINGJOBS"
TITLE = "Job search: Finding jobs"
BRANCH = "claude/finding-jobs-x1"
LISTENER = {"chat": LIVE, "kind": "cloud", "helper": True, "since": "2026-11-05T08:00:00Z"}

assert copy  # the fixture, imported


def _dump(tmp_path, status="done"):
    dump = tmp_path / "dump"
    (dump / "work").mkdir(parents=True, exist_ok=True)
    doc = {"data": {"kind": "search", "status": status, "title": "Finding jobs",
                    "claimed_by": JOB, "finished_at": "2026-11-06T08:00:00Z"}, "version": 5}
    (dump / "work" / "search~1.json").write_text(json.dumps(doc), encoding="utf-8")
    return dump


def _tidy(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert tidy.main(argv) == 0
    return buf.getvalue()


def _never_on_github(monkeypatch):
    monkeypatch.setattr(tidy, "_listener", lambda d: LISTENER)
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "unmerged", lambda: set())
    monkeypatch.setattr(tidy, "on_github", lambda: {"master"})


def _close(tmp_path, dump, now):
    return _tidy(["close", JOB, "--work", "search~1", "--dump", str(dump), "--chat", LIVE,
                  "--now", now, "--details",
                  _json(tmp_path, "d.json", _detail(JOB, TITLE, branch=BRANCH))])


def _batch(out):
    # Each batch is printed on a line of its own, and a path may hold a space (a Windows user
    # folder such as "C:\\Users\\Ada Example"): read whole lines, never \\S+ (the Git Bash run,
    # 2026-11-09 and 2026-11-10).
    paths = [ln.strip() for ln in out.splitlines()
             if ln.strip().endswith(".json") and os.path.isfile(ln.strip())]
    assert paths, out
    with open(paths[-1], encoding="utf-8") as fh:
        return json.load(fh)


def test_its_report_asks_it_to_save_once_then_its_card_says_it_was_lost(copy, tmp_path,
                                                                       monkeypatch):
    _never_on_github(monkeypatch)
    dump = _dump(tmp_path)
    out = _close(tmp_path, dump, "2026-11-06T08:05:00Z")
    # First: that chat is asked, once, to save its work; nothing archived, nothing said.
    assert "send_message" in out and JOB in out and "python3 tools/land.py --keep" in out, out
    # Nothing comes back by message: a message between chats asks the person's approval each
    # time, and the reply this asked for made two (the second audit of 2026-11-10, C3). The
    # next tidy-up looks again; a report that does come is judged as below.
    assert "[app] Finished" not in out and "never message another chat" in out, out
    assert "archive_session" not in out
    # Judged again on a later report from that chat (it sends no answer to the ask since C3; a
    # report it makes all the same is still read), the work still not on GitHub: the card says
    # it was lost.
    out = _close(tmp_path, dump, "2026-11-06T08:09:00Z")
    batch = _batch(out)
    assert [(e["collection"], e["doc_id"]) for e in batch] == [("work", "search~1")]
    with open(batch[0]["file_path"], encoding="utf-8") as fh:
        body = json.load(fh)
    assert body["status"] == "failed" and body["error"] == page_db.LOST_SAID
    assert batch[0]["if_version"] == 5
    assert f'archive_session {{"session_id": "{JOB}"}}' in out
    # Said once: a third report changes nothing on the page.
    out = _close(tmp_path, dump, "2026-11-06T08:20:00Z")
    assert "send_message" not in out and page_db.LOST_SAID not in out
    assert not re.findall(r"lost\S*\.json", out)


def test_work_that_reached_github_after_the_ask_is_kept_waiting(copy, tmp_path, monkeypatch):
    _never_on_github(monkeypatch)
    dump = _dump(tmp_path)
    _close(tmp_path, dump, "2026-11-06T08:05:00Z")
    monkeypatch.setattr(tidy, "unmerged", lambda: {BRANCH})
    monkeypatch.setattr(tidy, "on_github", lambda: {"master", BRANCH})
    out = _close(tmp_path, dump, "2026-11-06T08:09:00Z")
    assert out.startswith(f"keep {JOB}: its work is not on master yet"), out
    assert "send_message" not in out and "archive_session" not in out


def test_the_daily_tidy_up_asks_and_then_says_it_for_a_chat_that_never_reported():
    chats = [_chat(LIVE, "Job search page"),
             _chat(JOB, TITLE, updated="2026-11-06T08:00:00Z")]
    det = {JOB: _detail(JOB, TITLE, branch=BRANCH)}
    jobs = {JOB: "2026-11-06T08:00:00Z"}
    items = {JOB: {"all": ["search~1"], "done": ["search~1"]}}
    today = dt.date(2026, 11, 6)

    def plan(now, saves):
        return tidy.plan(chats, [], det, {}, LISTENER, LIVE, REPO, today, set(), set(), set(),
                         jobs, now=now, on_github={"master"}, saves=saves, job_items=items)

    at = dt.datetime(2026, 11, 6, 9, 0, tzinfo=dt.timezone.utc)
    got = plan(at, {})
    assert got["save"] == [{"id": JOB, "title": TITLE, "work": "search~1"}]
    assert not got["archive"] and not got["lost"]
    asked = {JOB: {"work": "search~1", "asked": "2026-11-06T09:00:00Z"}}
    got = plan(at + dt.timedelta(minutes=10), asked)            # not long ago: it waits
    assert not got["save"] and not got["lost"] and not got["archive"]
    got = plan(at + dt.timedelta(minutes=40), asked)
    assert got["lost"] == [{"id": JOB, "title": TITLE, "work": ["search~1"]}]
    assert [c["id"] for c in got["archive"]] == [JOB]
    said = dict(asked, **{JOB: dict(asked[JOB], lost="2026-11-06T09:40:00Z")})
    got = plan(at + dt.timedelta(hours=2), said)                 # once only
    assert not got["lost"] and [c["id"] for c in got["archive"]] == [JOB]
    # Without the page's records the tidy-up judges as before.
    got = tidy.plan(chats, [], det, {}, LISTENER, LIVE, REPO, today, set(), set(), set(), jobs,
                    now=at, on_github={"master"})
    assert not got["save"] and not got["archive"]
    assert any(k["id"] == JOB and "not on GitHub" in k["why"] for k in got["keep"])


def test_the_daily_tidy_up_command_asks_then_sends_the_card_once(copy, tmp_path, monkeypatch):
    import routines
    _never_on_github(monkeypatch)
    monkeypatch.setattr(tidy, "_campaign_chats", lambda: set())
    monkeypatch.setattr(routines, "load", lambda *a, **k: {})
    dump = _dump(tmp_path)
    chats = [_chat(LIVE, "Job search page"), _chat(JOB, TITLE, updated="2026-11-06T08:00:00Z")]

    def plan(now):
        return _tidy(["plan", "--chat", LIVE, "--now", now, "--dump", str(dump),
                      "--sessions", _json(tmp_path, "s.json", {"data": chats}),
                      "--details", _json(tmp_path, "d.json", _detail(JOB, TITLE, branch=BRANCH))])

    out = plan("2026-11-06T09:00:00Z")
    assert f"save {JOB}:" in out and "python3 tools/land.py --keep" in out, out
    assert f"archive {JOB}" not in out
    out = plan("2026-11-06T09:45:00Z")
    assert f"lost {JOB}:" in out and f"archive {JOB}" in out, out
    assert _batch(out)[0]["doc_id"] == "search~1"
    out = plan("2026-11-06T11:00:00Z")
    assert f"lost {JOB}:" not in out and f"save {JOB}:" not in out and f"archive {JOB}" in out


def test_what_the_card_says_is_plain():
    _plain(page_db.LOST_SAID)
    assert "Try again" in page_db.LOST_SAID


def test_keep_saves_the_work_to_its_branch_with_no_check(tmp_path, monkeypatch):
    """land.py --keep, what the job chat is asked to run: its work on GitHub in seconds, with
    no check and no pull request; the next landing brings it in."""
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)

    def git(cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=True)

    origin, chat = tmp_path / "origin.git", tmp_path / "chat"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(tmp_path, "init", "-q", "-b", "master", str(chat))
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        (chat / ".gitignore").write_text(fh.read(), encoding="utf-8")
    (chat / "profile").mkdir()
    (chat / "profile" / "person.json").write_text("{}\n", encoding="utf-8")
    git(chat, "add", "-A")
    git(chat, "commit", "-q", "-m", "start")
    git(chat, "remote", "add", "origin", str(origin))
    git(chat, "push", "-q", "origin", "master")
    git(chat, "fetch", "-q", "origin")
    git(chat, "switch", "-q", "-c", "claude/finding-jobs")
    os.makedirs(chat / "documents" / "rounds")
    (chat / "documents" / "rounds" / "r9.json").write_text("[]\n", encoding="utf-8")
    never = [sys.executable, "-c", "raise SystemExit('the check ran')"]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = land.main(["--keep", "--message", "Search: r9"], root=str(chat), check=never,
                         sleep=lambda s: None)
    out = buf.getvalue()
    assert code == 0, out
    assert "the check ran" not in out and "create_pull_request" not in out
    assert "the work waits on claude/finding-jobs" in out
    assert "documents/rounds/r9.json" in git(origin, "ls-tree", "-r", "--name-only",
                                             "claude/finding-jobs").stdout
