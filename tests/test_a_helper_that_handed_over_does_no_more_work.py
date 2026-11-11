"""A helper that has handed the page on does no more work, and puts itself away once saved.

The maintainer's copy, 2026-11-06: a helper handed over at 762,632 tokens, against a
compaction point of 784,000, and stayed open about half an hour until the tidy-up put it away,
because its save was still running. Any message, notification or ring in that window ran a
whole turn on a nearly full chat, which can compact it. Now, once it knows another chat
answers the page, every turn it gets is one line (the app's hook says so before anything is
read), and once its own save has landed it archives itself at once. Run on an invented copy
with a fake page store, as the chats run the commands. Every id here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

from test_one_chat_answers_the_page import Copy  # noqa: E402

OLD, NEW = "session_EXAMPLEOLDHELPER", "session_EXAMPLENEWHELPER"


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True)


@pytest.fixture
def copy(tmp_path, monkeypatch):
    """A person's copy whose state is a git checkout with an origin, and a fake page store."""
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)
    c = Copy(tmp_path / "copy")
    c.state = c.root
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(c.root, "init", "-q", "-b", "master")
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as fh:
        ignore = fh.read()
    with open(os.path.join(c.root, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write(ignore + "\n/db/\n/d[0-9]*/\n/fake_db.py\n/driver.py\n/state/\n")
    git(c.root, "add", "-A")
    git(c.root, "commit", "-q", "-m", "the person's start")
    git(c.root, "remote", "add", "origin", str(origin))
    git(c.root, "push", "-q", "origin", "master")
    git(c.root, "fetch", "-q", "origin")
    git(c.root, "switch", "-q", "-c", "claude/old-helper")
    c.page()
    git(c.root, "add", "-A")
    git(c.root, "commit", "-q", "-m", "the page's address")
    git(c.root, "push", "-q", "origin", "HEAD:refs/heads/master")
    git(c.root, "fetch", "-q", "origin")
    yield c
    sys.path.remove(c.root)


def _run(copy, *args, chat=OLD):
    return copy.run(*args, LJS_STATE=copy.root, LJS_CHAT=chat, CLAUDE_CODE_REMOTE="true")


def _hook(copy, prompt, chat=OLD):
    env = copy.env(LJS_STATE=copy.root, LJS_CHAT=chat, CLAUDE_CODE_REMOTE="true")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "learned.py"), "hook"],
                       input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt,
                                         "session_id": "x"}),
                       env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else {}


def _context(got):
    return ((got or {}).get("hookSpecificOutput") or {}).get("additionalContext") or ""


def test_after_the_hand_over_every_turn_is_one_line_and_it_goes_once_saved(copy):
    # The old helper answers the page; the fresh one it started takes it.
    assert copy.send(_run(copy, "listen", copy.dump("d1"), "--chat", OLD, "--helper"))
    ring = "[app] [work:reply~1] Artifact comment sent to Claude"
    # While it answers, a ring is answered as ever: nothing from the hook about it.
    assert "app.py retired" not in _context(_hook(copy, ring))
    assert copy.send(_run(copy, "listen", copy.dump("d2"), "--chat", NEW, "--listen",
                          "--helper", chat=NEW))
    # Its next check-in finds the fresh helper: from now on it does no more work.
    said = _run(copy, "listen", copy.dump("d3"), "--chat", OLD)
    assert "another chat answers the page" in said
    assert f"python3 tools/app.py retired --chat {OLD}" in said, said
    # Any turn the app makes now, a ring, a notification or a scheduled run: the hook says one
    # line, read nothing.
    for prompt in (ring, "<task-notification>done</task-notification>",
                   "Scheduled run: a check-in."):
        ctx = _context(_hook(copy, prompt))
        assert f"python3 tools/app.py retired --chat {OLD}" in ctx, ctx
        assert "read nothing" in ctx
    # The person typing here is answered, never told to put the chat away (second audit A8: a
    # person holding a real conversation in an old helper was answered "archive yourself").
    ctx = _context(_hook(copy, "hello? can you look at my notes from the call"))
    assert "app.py retired" not in ctx and "archive" not in ctx.lower()
    assert "answer the person" in ctx
    # Its own work not saved yet: the save is started, with a wait that wakes it once.
    with open(os.path.join(copy.profile, "notes.md"), "w", encoding="utf-8") as fh:
        fh.write("the last thing it wrote\n")
    said = _run(copy, "retired", "--chat", OLD)
    assert "python3 tools/land.py --detach" in said and "retired --chat" in said, said
    assert "archive_session" not in said
    # Saved and on GitHub: it puts itself away at once.
    git(copy.root, "add", "-A")
    git(copy.root, "commit", "-q", "-m", "its last work")
    git(copy.root, "push", "-q", "origin", "HEAD:refs/heads/master")
    git(copy.root, "fetch", "-q", "origin")
    said = _run(copy, "retired", "--chat", OLD)
    assert f'archive_session {{"session_id": "{OLD}"}}' in said, said
    # The chat that answers the page is never told any of this.
    assert "app.py retired" not in _context(_hook(copy, ring, chat=NEW))
    said = _run(copy, "retired", "--chat", NEW, chat=NEW)
    assert "archive_session" not in said and "answers the page" in said
