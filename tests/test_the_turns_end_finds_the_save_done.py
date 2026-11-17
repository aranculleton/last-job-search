"""A cloud chat's turn ends with nothing left for the cloud to ask about, and a save's pull
request costs the chat no turn.

A cloud chat's turn ends with the cloud's own check of the checkout (a Stop hook the cloud
installs, outside the app): anything uncommitted, any untracked file, or commits its branch's
copy on GitHub lacks (origin/<branch>, else origin/HEAD), and the chat is told to commit and
push. `land.py --detach` did the whole save after the turn had ended, in a process the chat
cannot see, so (a person's copy, 2026-11-16):

- the check found the turn's work uncommitted at the end of nearly every turn while the save
  ran, and the chat landed again or waited minutes on a save that was already under way;
- master taken into the branch (a page update, the day's first check, a landing with nothing
  of its own) moved the branch past its copy on GitHub, and the check counted master's own
  commits as unpushed: 53 where 2 were the chat's, three turns running, in a chat whose only
  job is starting chats on the computer;
- each save's pull request subscribed the chat that answers the page by itself, and both of
  its events (subscribed, merged) reached that chat as a turn, reading its whole history.

Now the part the cloud checks is done before the save goes to the background (the turn's work
committed and on its branch's copy on GitHub), the branch's copy moves with every master
taken in, and the events of a pull request on the person's own copy are stopped before they
reach the chat. Throwaway copies with a bare origin only; the check and GitHub are faked.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import land  # noqa: E402
import test_a_chat_lands_its_work_in_one_command as L  # noqa: E402
from test_a_chat_lands_its_work_in_one_command import GREEN, git, write  # noqa: E402


@pytest.fixture
def copy(tmp_path, monkeypatch):
    """(origin, chat, other), as the landing tests have them: a bare origin, this chat on its
    own branch, and a second chat's clone that moves master underneath it."""
    return L.copy.__wrapped__(tmp_path, monkeypatch)


def turn_end(chat) -> str:
    """What the cloud's own check at the end of a turn finds, or "" when it lets the turn
    end: its conditions in its order (changes not committed, staged or not; untracked files;
    then commits on HEAD that the branch's copy lacks, counted from origin/<branch>, or from
    origin/HEAD where the branch has no copy, and nothing where that cannot be counted)."""
    if git(chat, "diff", "--quiet", check=False).returncode or \
            git(chat, "diff", "--cached", "--quiet", check=False).returncode:
        return "uncommitted changes"
    # Untracked files, as the check counts them (ignored ones left out), read from the status
    # rather than a listing of files (tests/test_repo_files.py: listings go through repo_files).
    if any(line.startswith("??") for line in git(chat, "status", "--porcelain", "--untracked-files=normal").stdout.splitlines()):
        return "untracked files"
    name = git(chat, "branch", "--show-current").stdout.strip()
    if not name:
        return ""
    up = "origin/" + name
    if git(chat, "rev-parse", "-q", "--verify", up, check=False).returncode:
        up = "origin/HEAD"
    r = git(chat, "rev-list", "--count", up + "..HEAD", check=False)
    n = int(r.stdout.strip() or 0) if r.returncode == 0 else 0
    return "%d unpushed commit(s)" % n if n else ""


def _started(*a, **k):
    """The background part, never started here: what the chat's turn sees is what the
    foreground call left."""


def _never(*a, **k):
    raise AssertionError("a second landing was started while one runs")


def _on_github(origin, branch, path):
    return git(origin, "show", "%s:%s" % (branch, path), check=False).stdout


# ------------------------------------------------------------------ the turn's own work

def test_a_save_in_the_background_leaves_the_turns_end_nothing_to_ask(copy, capsys):
    origin, chat, _other = copy
    write(chat, "profile/notes.md", "what this turn wrote\n")
    assert turn_end(chat) == "uncommitted changes"
    assert land.detach(str(chat), "Notes", popen=_started) == 0
    assert capsys.readouterr().out.strip() == \
        "land: saving in the background; nothing to wait for or say."
    assert turn_end(chat) == "", "the cloud would hold the turn for work the save holds"
    assert _on_github(origin, "claude/chat-1", "profile/notes.md") == "what this turn wrote\n"
    # Saved to the chat's own branch only: master is reached through the pull request alone.
    assert _on_github(origin, "master", "profile/notes.md") == "first\n"
    # The save itself goes on in the background, asked for and holding the lock.
    assert land.wanted(str(chat)) and land.landing(str(chat))


def test_a_save_asked_while_the_last_one_waits_is_on_github_at_once(copy, monkeypatch,
                                                                     capsys):
    """The chat that answers the page lands its saves a few minutes apart (land.SETTLE_S), and
    the save waiting out those minutes holds the lock: every turn's save in them was only
    queued, so every turn ended on work the cloud saw as uncommitted. A save asked for while
    the last one only waits is committed and pushed at once, and the waiting one lands it."""
    origin, chat, _other = copy
    root = str(chat)
    monkeypatch.setattr(land, "_answers_page", lambda r: True)
    land._mark_landed(root)                       # one landed a moment ago: the next waits
    waiting, go = threading.Event(), threading.Event()

    def sleep(s):
        if not go.is_set():
            waiting.set()
            assert go.wait(30), "the test never let the wait end"

    def finish(r, ready):
        git(r, "push", "-q", "origin", "HEAD:refs/heads/master")      # GitHub's merge
        return True, "7"

    write(chat, "profile/notes.md", "the first tap\n")
    got = {}
    t = threading.Thread(target=lambda: got.setdefault("code", land.run_detached(
        root, "First tap", check=GREEN, sleep=sleep, finish=finish)))
    t.start()
    try:
        assert waiting.wait(30), "the save never started its wait"
        assert turn_end(chat) == ""                # the first tap went before the wait
        write(chat, "profile/answers.md", "the second tap\n")
        assert land.detach(root, "Second tap", popen=_never) == 0
        out = capsys.readouterr().out
        assert turn_end(chat) == "", out
        assert _on_github(origin, "claude/chat-1", "profile/answers.md") == "the second tap\n"
        assert "nothing to wait for or say" in out and "run no git command" not in out, out
    finally:
        go.set()
        t.join(60)
    assert got.get("code") == 0
    # One pull request took both, and the chat starts from master.
    assert _on_github(origin, "master", "profile/answers.md") == "the second tap\n"
    assert _on_github(origin, "master", "profile/notes.md") == "the first tap\n"
    assert not land.landing(root) and turn_end(chat) == ""


def test_a_save_asked_while_one_is_busy_says_the_turns_end_needs_nothing(copy, capsys):
    """Busy (merging master, checking): nothing is committed beside it, which could reach
    master unchecked. The chat is told plainly that the cloud's message about it at the end of
    the turn is this save, already under way."""
    _origin, chat, _other = copy
    root = str(chat)
    token = land._take_lock(root)                 # a landing in the middle of its work
    assert token
    try:
        head = git(chat, "rev-parse", "HEAD").stdout
        write(chat, "profile/notes.md", "written while it checks\n")
        assert land.detach(root, "Notes", popen=_never) == 0
        out = " ".join(capsys.readouterr().out.split())
        assert git(chat, "rev-parse", "HEAD").stdout == head, "committed beside a busy landing"
        assert " ".join(land.BUSY_SAY.split()) in out, out
        assert "run no git command" in out and "end the turn" in out, out
        assert land._asked(root), "the running landing takes it when it ends"
    finally:
        land._drop_lock(root, token)


# ------------------------------------------------------------------ master taken in

def _master_moves(other, n=3):
    for i in range(n):
        write(other, "profile/other_%d.md" % i, "another chat's work\n")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "another chat's work %d" % i)
    git(other, "push", "-q", "origin", "HEAD:master")


def _a_copy_on_github(chat):
    """The branch's copy on GitHub, as a landing leaves it (moved up to master after its pull
    request merged: the cloud refuses to delete a branch) or as a cloud chat starts with it."""
    git(chat, "push", "-q", "-u", "origin", "HEAD:refs/heads/claude/chat-1")


def test_a_landing_with_nothing_of_its_own_leaves_the_branch_level_with_github(copy, capsys):
    origin, chat, other = copy
    _a_copy_on_github(chat)
    _master_moves(other)
    code, out = L._run(chat, "--message", "Nothing new", capsys=capsys)
    assert code == 0 and "land: nothing to land" in out, out
    assert git(chat, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "master").stdout
    assert turn_end(chat) == "", "master's own commits counted as this chat's, unpushed"


def test_a_page_update_that_takes_master_leaves_the_branch_level_with_github(copy, monkeypatch):
    import app_setup
    origin, chat, other = copy
    _a_copy_on_github(chat)
    _master_moves(other)
    monkeypatch.setattr(app_setup, "ROOT", str(chat))
    monkeypatch.setattr(app_setup, "origin", lambda: ("someone", "their-search"))
    assert app_setup.take_master() == ""
    assert git(chat, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "master").stdout
    assert turn_end(chat) == ""


def test_the_days_first_check_that_takes_master_leaves_the_branch_level_with_github(
        copy, monkeypatch, capsys):
    import sync_app
    origin, chat, other = copy
    _a_copy_on_github(chat)
    _master_moves(other)
    monkeypatch.setattr(sync_app, "ROOT", str(chat))
    assert sync_app.pull_master() == 0
    assert "brought in master" in capsys.readouterr().out
    assert git(chat, "rev-parse", "HEAD").stdout == git(origin, "rev-parse", "master").stdout
    assert turn_end(chat) == ""


def test_a_branch_with_work_of_its_own_and_no_copy_is_left_to_its_landing(copy, monkeypatch):
    """Only a copy already on GitHub is moved when master is taken in: a chat's own work is
    pushed by its save, never by a page update, so nothing half done reaches another chat's
    landing that way."""
    import app_setup
    origin, chat, other = copy
    write(chat, "profile/notes.md", "committed, not saved\n")
    git(chat, "commit", "-q", "-am", "work of its own")
    _master_moves(other, 1)
    monkeypatch.setattr(app_setup, "ROOT", str(chat))
    monkeypatch.setattr(app_setup, "origin", lambda: ("someone", "their-search"))
    assert app_setup.take_master() == ""
    assert "claude/chat-1" not in L._branches(origin)


# ------------------------------------------------------------------ the pull request's events

def _event(kind: str, data: str) -> str:
    """A GitHub event as the cloud delivers one to a chat (its envelope, as seen 2026-11-12)."""
    return ('<wake reason="external-event" current-time="2026-11-16T21:40:00Z">\n'
            '  <event source="github" kind="%s" from="system" trust="principal">\n'
            '    <!-- You are now subscribed to the PR shown in this event\'s data. -->\n'
            '    %s\n  </event>\n</wake>' % (kind, data))


@pytest.fixture
def person_copy(tmp_path, monkeypatch):
    """A person's copy whose origin is their own repo on GitHub, the hook's state pointed at
    it (never a real one)."""
    import learned
    repo = tmp_path / "their-search"
    git(tmp_path, "init", "-q", "-b", "master", str(repo))
    git(repo, "remote", "add", "origin", "https://github.com/someone/their-search.git")
    monkeypatch.setenv("LJS_STATE", str(repo))
    monkeypatch.setattr(learned, "_path", lambda: str(tmp_path / "pending.json"))
    monkeypatch.setattr(learned.person, "in_example", lambda p: False)
    monkeypatch.setattr(learned, "_retired", lambda: "")
    return learned


@pytest.mark.parametrize("kind,data", [
    ("subscription.created", '{"pr":"someone/their-search#12"}'),
    ("pull_request.closed", '{"pr":"someone/their-search#12","merged":true}'),
    ("check_run.completed", '{"check":"Fast checks","conclusion":"failure",'
                            '"pr":"Someone/Their-Search#12"}'),
])
def test_a_save_pull_requests_events_never_reach_the_chat(person_copy, kind, data):
    got = person_copy.hook({"hook_event_name": "UserPromptSubmit",
                            "prompt": _event(kind, data)})
    assert got.get("decision") == "block", got
    assert got["hookSpecificOutput"]["suppressOriginalPrompt"] is True
    assert got.get("reason") == "Saved."             # all the person could ever see of it
    assert "pull request" not in json.dumps(got).lower()


def test_the_hook_claude_code_runs_stops_the_event_with_nothing_added(tmp_path):
    """Run as Claude Code runs it (`learned.py hook`, the event on its input): the block is all
    it prints, with nothing the day's checks would add beside a prompt that never arrives."""
    repo, prof = tmp_path / "their-search", tmp_path / "profile"
    git(tmp_path, "init", "-q", "-b", "master", str(repo))
    git(repo, "remote", "add", "origin", "https://github.com/someone/their-search.git")
    prof.mkdir()
    (prof / "person.json").write_text("{}\n", encoding="utf-8")
    env = dict(os.environ, LJS_STATE=str(repo), LJS_PROFILE=str(prof))
    for k in ("LJS_CHAT", "CLAUDE_CODE_REMOTE"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "learned.py"), "hook"],
                       input=json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "x",
                                         "prompt": _event("pull_request.closed",
                                                          '{"pr":"someone/their-search#3"}')}),
                       env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"decision": "block", "reason": "Saved.", "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "suppressOriginalPrompt": True}}, r.stdout


def test_another_repos_pull_request_is_never_taken_for_a_save(person_copy):
    """A chat watching a pull request somewhere else (the app's own, say) is woken by it as
    ever, and never told it is a save's."""
    for data in ('{"pr":"someone/their-search-app#12"}', '{"pr":"elsewhere/their-search#12"}'):
        got = person_copy.hook({"hook_event_name": "UserPromptSubmit",
                                "prompt": _event("check_run.completed", data)})
        assert "decision" not in got and "save" not in json.dumps(got).lower(), got


def test_an_event_that_names_no_pull_request_is_answered_as_before(person_copy):
    got = person_copy.hook({"hook_event_name": "UserPromptSubmit",
                            "prompt": _event("pull_request.closed", "merged")})
    assert "decision" not in got
    assert "Read nothing" in got["hookSpecificOutput"]["additionalContext"]
