"""The tidy-up judges an old chat's branch by what GitHub holds, from a chat's own copy.

A chat's copy is a shallow clone of master alone: `git branch -r` there names no other branch,
so every earlier chat's branch read as "never reached GitHub", and each old page chat and old
brief chat was kept for two more days though its branch was on GitHub and merged (the
maintainer's chat list, 2026-11-16: two "finishing up" chats and an old brief chat beside the
live ones, every day). GitHub is asked itself which branches it holds, and a chat's branch is
fetched to see whether master holds it. Invented names; a throwaway repository.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import person  # noqa: E402
import tidy  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com", GIT_TERMINAL_PROMPT="0")


def _git(where, *args):
    return subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True,
                          text=True, env=ENV).stdout.strip()


def _commit(where, name, text):
    (where / name).write_text(text, encoding="utf-8")
    _git(where, "add", name)
    _git(where, "commit", "-q", "-m", name)


@pytest.fixture
def chat_copy(tmp_path, monkeypatch):
    """GitHub (a bare repository) with master, a chat's branch merged into it, a chat's branch
    still open, and twenty later commits; and a chat's copy cloned from it as a chat's is."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(origin)], check=True,
                   env=ENV)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True, env=ENV,
                   capture_output=True)
    _git(work, "checkout", "-q", "-b", "master")
    _commit(work, "a.txt", "start")
    _git(work, "push", "-q", "origin", "master")
    for branch, merge in (("claude/land-20261114-082234", True), ("claude/open-work", False)):
        _git(work, "checkout", "-q", "-b", branch, "master")
        _commit(work, branch.replace("/", "-") + ".txt", branch)
        _git(work, "push", "-q", "origin", branch)
        _git(work, "checkout", "-q", "master")
        if merge:
            _git(work, "merge", "-q", "--no-ff", "-m", "Merge " + branch, branch)
    for n in range(20):
        _commit(work, "later%d.txt" % n, str(n))
    _git(work, "push", "-q", "origin", "master")
    copy = tmp_path / "copy"
    subprocess.run(["git", "clone", "-q", "--depth", "5", "--single-branch", "--branch",
                    "master", "file://" + str(origin), str(copy)], check=True, env=ENV,
                   capture_output=True)
    monkeypatch.setenv("LJS_STATE", str(copy))
    person.reset()
    yield copy
    person.reset()


def test_a_chats_copy_sees_every_branch_github_holds(chat_copy):
    # The copy itself knows only master.
    seen = set(_git(chat_copy, "branch", "-r", "--format=%(refname:short)").split())
    assert seen <= {"origin", "origin/master"}, seen       # origin/HEAD shows as "origin"
    got = tidy.on_github()
    assert {"master", "claude/land-20261114-082234", "claude/open-work"} <= got, got


def test_a_merged_branch_is_on_master_and_an_open_one_is_not(chat_copy):
    names = {"claude/land-20261114-082234", "claude/open-work", "claude/never-pushed"}
    # Merged twenty commits before the copy's history begins: still seen as merged.
    assert tidy.unmerged(names) == {"claude/open-work"}


def test_an_old_page_chat_whose_branch_is_merged_is_put_away(chat_copy):
    import datetime as dt
    import routines
    repo = "example-owner/my-job-search"
    helper, old = "session_EXAMPLEPAGEHELPER", "session_EXAMPLEOLDHELPER"
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": []}

    def chat(sid, title, at):
        return {"id": sid, "title": title, "updated_at": at, "created_at": at,
                "origin": "claude_code_mcp_seed", "session_status": "SESSION_STATUS_IDLE"}

    chats = [chat(helper, "Job search page", "2026-11-16T08:14:00Z"),
             chat(old, "Job search page (finishing up)", "2026-11-14T17:44:00Z")]
    info = {c["id"]: {"id": c["id"], "session_status": "SESSION_STATUS_IDLE",
                      "session_context": {"sources": [{"git_repository": {
                          "url": "https://github.com/" + repo}}]},
                      "external_metadata": {"current_branches": {
                          "": "claude/land-20261114-082234"}}} for c in chats}
    names = {b for d in info.values() for b in tidy._branches_of(d)}
    got = tidy.plan(chats, [], info, reg, {"chat": helper, "helper": True}, helper, repo,
                    dt.date(2026, 11, 16), set(), tidy.unmerged(names), set(),
                    now=dt.datetime(2026, 11, 16, 10, 0, tzinfo=dt.timezone.utc),
                    on_github=tidy.on_github())
    assert [a["id"] for a in got["archive"]] == [old], got
    assert routines  # the registry module the plan reads is the app's own


def test_the_helper_just_taken_over_from_goes_once_its_work_is_proven_saved(chat_copy):
    """The page changes hands at the same time each morning, so yesterday's helper was always a
    few seconds short of the day of quiet it was kept for, and nothing wakes it to put itself
    away: it stayed every day. Its branch on GitHub, held by master and last committed when
    it was last used, it goes after an hour; work after its last save keeps it."""
    import datetime as dt
    merged, open_ = "claude/land-20261114-082234", "claude/open-work"
    branches = tidy.unmerged({merged, open_})
    github = tidy.on_github()
    tip = dt.datetime.fromtimestamp(tidy.TIPS[merged], dt.timezone.utc)
    now = tip + dt.timedelta(hours=23, minutes=59)

    def helper(branch, used):
        return {"id": "session_EXAMPLEOLDHELPER", "title": "Job search page (finishing up)",
                "session_status": "SESSION_STATUS_IDLE",
                "updated_at": used.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "session_context": {"sources": [{"git_repository": {
                    "url": "https://github.com/example-owner/my-job-search"}}]},
                "external_metadata": {"current_branches": {"": branch}}}

    def judged(branch, used):
        return tidy.retire("session_EXAMPLEOLDHELPER", helper(branch, used),
                           "example-owner/my-job-search", branches, now, github)[0]

    assert judged(merged, tip + dt.timedelta(minutes=2)) == "archive"
    # Used for hours after its last save: what it did then may be only in its container.
    assert judged(merged, tip + dt.timedelta(hours=3)) == "keep"
    # Its branch not on master yet, or no proof at all: kept, as before.
    assert judged(open_, tip + dt.timedelta(minutes=2)) == "keep"
    assert tidy.retire("session_EXAMPLEOLDHELPER", helper(merged, tip), "example-owner/my-job-search",
                       branches, now) == ("keep", "it puts itself away once its work is saved")


def test_a_backlog_of_old_chats_goes_in_one_tidy_up_and_none_stays_for_good(chat_copy):
    """An existing install's backlog: weeks of old page and brief chats, every one put away by
    the first tidy-up after the update. One whose branch never reached master is kept a week of
    quiet for the next landing to bring it in, then put away too: its branch stays on GitHub."""
    import datetime as dt
    repo = "example-owner/my-job-search"
    helper = "session_EXAMPLEPAGEHELPER"
    reg = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": []}
    now = dt.datetime(2026, 11, 16, 10, 0, tzinfo=dt.timezone.utc)

    def chat(sid, title, days_ago, branch=""):
        at = (now - dt.timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        s = {"id": sid, "title": title, "updated_at": at, "created_at": at,
             "origin": "claude_code_mcp_seed", "session_status": "SESSION_STATUS_IDLE"}
        d = dict(s, session_context={"sources": [{"git_repository": {
            "url": "https://github.com/" + repo}}]},
            external_metadata={"current_branches": {"": branch}} if branch else {})
        return s, d

    rows = [chat(helper, "Job search page", 0)]
    rows += [chat("session_EXAMPLEOLD%02d" % n, "Job search page (finishing up)", 2 + n,
                  "claude/land-20261114-082234") for n in range(8)]
    rows += [chat("session_EXAMPLEOPENRECENT", "Job search page (finishing up)", 3, "claude/open-work"),
             chat("session_EXAMPLEOPENOLD", "Job search page (finishing up)", 9, "claude/open-work")]
    chats, info = [s for s, _ in rows], {s["id"]: d for s, d in rows}
    names = tidy.own_branches(info)
    got = tidy.plan(chats, [], info, reg, {"chat": helper, "helper": True}, helper, repo,
                    now.date(), set(), tidy.unmerged(names), set(), now=now,
                    on_github=tidy.on_github())
    gone = {a["id"] for a in got["archive"]}
    assert {"session_EXAMPLEOLD%02d" % n for n in range(8)} <= gone, got
    assert "session_EXAMPLEOPENOLD" in gone, got                 # a week of quiet: put away
    assert "session_EXAMPLEOPENRECENT" not in gone               # the next landing may bring it in
    assert helper not in gone and not got["ask"]
