"""The day's update, its improvements and the turn's save reach a stranger's copy by themselves.

From the stranger audit (2026-11-03): copies made by people with no connection to the
maintainer, on a phone, weeks behind, in any market. Each test reproduces one finding on
throwaway copies with invented data (the example person), never a real one:

- X-15: what the updates did never showed: the app's own commits crashed the reading;
- X-28: on releases, an update "waited" that saying "update" could not take;
- X-32, S4: improvements the check listed were only a printed line, and waited for days;
- X-36: an update that changed the app skill was never named to the chat holding it;
- X-46, X-52: the page's steps came only from a check that finished, last, under the job
  sites' block;
- X-54: a cloud chat's proxy address made start call a person's own copy "not a copy";
- X-62: nothing made a chat save before its turn ended;
- X-71: a check that could not finish was asked for again before every message;
- the chat-only review: one unsaved file of theirs stopped every morning's update for good.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(ROOT, "tools"), HERE]

import app_setup  # noqa: E402
import land  # noqa: E402
import learned  # noqa: E402
import person  # noqa: E402
import profile_upgrades as U  # noqa: E402
import sync_app  # noqa: E402
from test_a_reaction_is_recorded_before_the_turn_ends import _line, _transcript  # noqa: E402
from test_sync_app import (ENV, _with_local_origin, commit, head, read, repos, run,  # noqa: E402,F401
                           sh, write)


def git(cwd, *args, check=True):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check, env=ENV)


# ------------------------------------------------------------------ a person's copy


@pytest.fixture
def copy(tmp_path, monkeypatch):
    """A person's copy at the root of its own repo (the example person, in Toronto), with
    a bare origin it has pushed to and the day's sync on its history."""
    origin, me = tmp_path / "origin.git", tmp_path / "copy"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(tmp_path, "init", "-q", "-b", "master", str(me))
    shutil.copytree(os.path.join(ROOT, "profile.example"), me / "profile",
                    ignore=shutil.ignore_patterns("state"))
    data = json.loads((me / "profile" / "person.json").read_text(encoding="utf-8"))
    data["time_zone"] = "America/Toronto"
    (me / "profile" / "person.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    shutil.copy(os.path.join(ROOT, ".gitignore"), me / ".gitignore")
    (me / "job_search_tracker.csv").write_text("date,company,role,status\n", encoding="utf-8")
    git(me, "add", "-A")
    git(me, "add", "-f", "job_search_tracker.csv")
    git(me, "commit", "-q", "-m", "set me up")
    git(me, "commit", "-q", "--allow-empty", "-m", "Sync from the app: 1 new commit(s)")
    git(me, "remote", "add", "origin", str(origin))
    git(me, "push", "-q", "-u", "origin", "master")
    git(me, "switch", "-q", "-c", "claude/this-chat")
    git(me, "push", "-q", "-u", "origin", "claude/this-chat")
    for k in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(k, ENV[k])
    monkeypatch.setenv(person.ENV, str(me / "profile"))
    monkeypatch.setenv(person.STATE_ENV, str(me))
    monkeypatch.setenv("LJS_CHAT", "session_HERCHAT")
    monkeypatch.setattr(U, "ROOT", str(me))
    person._modules.clear()
    person._data.clear()
    yield me
    person._modules.clear()
    person._data.clear()


def _stop(path, active=False):
    return learned.hook({"hook_event_name": "Stop", "transcript_path": path,
                         "stop_hook_active": active, "session_id": "local-1"})


def _agent(prompt):
    return {"type": "assistant", "message": {"role": "assistant", "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "name": "Agent",
                         "input": {"description": "Improvements", "prompt": prompt,
                                   "run_in_background": True}}]}}


def _listed(ids=("method-drafts",), day=None):
    U.remember_listed([(U.by_id(i), "pending") for i in ids], today=day)


TURN = [_line("user", text="what's on today?"),
        _line("tool", command="python3 tools/app.py view"), _line("result"),
        _line("end", text="Here is today.")]


# ------------------------------------------------------------------ S4 and X-32


def test_improvements_the_check_listed_hold_the_turn_until_they_are_started(copy, tmp_path):
    """S4 / X-32: the update check listed improvements Claude applies itself, and the chat
    did not start them, for days. The turn's end is held, once a turn, until an agent is
    started on them; then nothing more is owed today, in any chat on this computer."""
    _listed()
    path = _transcript(tmp_path, TURN)
    held = _stop(path)
    assert held["decision"] == "block" and "upgrade.md" in held["reason"]
    assert "--not-now" in held["reason"]
    assert _stop(path, active=True) == {}            # never while already continuing for it
    started = TURN[:-1] + [_agent("Follow .claude/commands/upgrade.md, budget 20"),
                           _line("result"), _line("end")]
    assert _stop(_transcript(tmp_path, started)) == {}
    assert U.unstarted() == [] and _stop(path) == {}


def test_a_turn_a_notification_opened_is_not_taken_as_an_old_start(copy, tmp_path):
    """The chat-only review (safety, round 2): a turn opened by a notification read back to
    the person's last message, days old, and an /upgrade started then counted as today's.
    Only what this turn ran counts."""
    note = {"type": "user", "origin": {"kind": "task-notification"},
            "message": {"role": "user", "content": "<task-notification>done</task-notification>"}}
    old = [_line("user", text="hi"), _agent("Follow .claude/commands/upgrade.md"),
           _line("result"), _line("end")]
    _listed()
    path = _transcript(tmp_path, old + [note, _line("tool", command="ls"), _line("result"),
                                        _line("end", text="Nothing new.")])
    assert "upgrade.md" in _stop(path)["reason"]


def test_a_chat_that_cannot_start_them_says_why_and_is_let_go_for_the_day(copy, tmp_path):
    _listed()
    path = _transcript(tmp_path, TURN)
    assert "upgrade.md" in _stop(path)["reason"]
    assert U.main(["--not-now", "no background agents in this chat"]) == 0
    assert U._listed()["not_now"]["session_HERCHAT"]["why"] == "no background agents in this chat"
    assert _stop(path) == {}
    # Recorded for this chat alone: another chat on the same computer is still held.
    assert U.unstarted(chat="session_OTHERCHAT") != []


def test_holds_are_few_a_day_and_never_in_a_chat_for_one_big_job(copy, tmp_path):
    _listed()
    path = _transcript(tmp_path, TURN)
    for _ in range(U.HOLDS_A_DAY):
        assert _stop(path).get("decision") == "block"
    assert _stop(path) == {}
    job = [_line("user", text="Do one piece of work: python3 tools/app.py start --on m "
                              "--tools none --work draft~r1-3")] + TURN[1:]
    os.remove(U._listed_path())
    _listed()
    assert _stop(_transcript(tmp_path, job)) == {}
    # The same listing, an ordinary chat's turn: held.
    assert _stop(_transcript(tmp_path, TURN)).get("decision") == "block"


def test_a_job_chat_stays_one_once_the_person_types_in_it(copy, tmp_path, monkeypatch):
    """The re-audit of 4 November: a chat started for one big job was known only by the turn
    that ran its start. Once the person typed in it, their message carried the day's update
    check, and its turn's end was held for the improvements and the page like the chat that
    answers the page. `start --work` records the chat in this checkout's own git folder, by
    every name it goes by, and every check reads that record."""
    for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID",
              "CLAUDE_CODE_BRIDGE_SESSION_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LJS_CHAT", "session_JOBCHAT")
    monkeypatch.setattr(sync_app, "stale", lambda: True)
    monkeypatch.setattr(sync_app, "retry_due", lambda: True)
    monkeypatch.setattr(learned, "_page_owed_here", lambda t="": ("session_JOBCHAT", "new"))
    _listed()
    said = "can you make the second paragraph shorter?"
    later = [_line("user", text=said)] + TURN[1:]
    path = _transcript(tmp_path, later)
    ups = {"hook_event_name": "UserPromptSubmit", "prompt": said, "transcript_path": path,
           "session_id": "local-1"}
    stop = {"hook_event_name": "Stop", "transcript_path": path, "session_id": "local-1"}
    items = learned._this_turn(learned._transcript_texts(path))
    # An ordinary chat: told, and held.
    assert learned._update_due(ups) and learned._page_due(ups)
    assert learned._undone(stop, items) and learned._page_hold(stop)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "start",
                        "--on", "m", "--tools", "none", "--work", "draft~r1-3"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=dict(os.environ), cwd=str(copy), timeout=300)
    assert app_setup.job_chat() == "draft~r1-3", r.stdout + r.stderr
    assert learned._update_due(ups) == "" and learned._page_due(ups) == ""
    assert learned._undone(stop, items) == [] and learned._page_hold(stop) == {}
    # Known by Claude Code's own session id too, which is all a hook may be given.
    monkeypatch.delenv("LJS_CHAT")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc")
    assert app_setup.record_job_chat("draft~r1-4")
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    assert learned._update_due(dict(ups, session_id="abc")) == ""
    # Any other chat on this computer is still an ordinary one.
    monkeypatch.setenv("LJS_CHAT", "session_OTHERCHAT")
    assert learned._update_due(ups) and learned._page_due(ups)


def test_an_improvement_done_since_it_was_listed_is_never_started_again(copy, tmp_path):
    _listed(("method-drafts", "method-interview"))
    git(copy, "commit", "-q", "--allow-empty", "-m", "Profile upgrade: method-drafts")
    assert [i for i, _d in U.unstarted()] == ["method-interview"]
    # One an earlier day's /upgrade took is not announced or started again the next morning.
    yesterday = person.today() - dt.timedelta(days=1)
    _listed(("method-interview",), day=yesterday)
    U.mark_started(yesterday)
    assert U.unstarted() == []


def test_the_day_is_the_persons_whoever_counts_it(copy, tmp_path, monkeypatch):
    """One clock: an evening in Toronto is past midnight in UTC, and on the computer's clock
    /upgrade's first step marked the improvements started tomorrow, so the next turn was held
    to start them again (the chat-only review, round 3)."""
    toronto_evening = dt.datetime(2026, 11, 4, 1, 40, tzinfo=dt.timezone.utc)
    assert person.today(toronto_evening) == dt.date(2026, 11, 3)
    day = dt.date(2026, 11, 3)
    monkeypatch.setattr(person, "today", lambda now=None: day)
    _listed()
    started = TURN[:-1] + [_line("tool", command="python3 tools/profile_upgrades.py --plan"),
                           _line("result"), _line("end")]
    assert _stop(_transcript(tmp_path, started)) == {}
    assert U._listed()["started"] == {"day": "2026-11-03"}
    assert U.unstarted() == [] and _stop(_transcript(tmp_path, TURN)) == {}


def test_every_start_names_the_improvements_still_waiting(copy, monkeypatch):
    """X-32: start named none of them, and only the day's first check listed them, so a
    second chat that day never heard of them. With no page, the person is told in the chat,
    and the head no longer says "page to publish"."""
    _listed()
    monkeypatch.setattr(app_setup, "ROOT", str(copy))
    monkeypatch.setattr(app_setup, "_stranded", lambda: {})
    st = {"repo": {"kind": "private"}, "setup": {"state": "here", "say": ""},
          "page": {"none": person.today().isoformat()}, "page_current": False,
          "stale": False, "answers": {}, "set_up": True}
    monkeypatch.setattr(app_setup, "state", lambda runner=None: st)
    monkeypatch.setattr(app_setup, "_finished", lambda: True)
    # This chat cannot publish: said for this chat alone (the stranger audit, X-21), since a
    # copy-wide "none" in profile/app.json is another chat's word and is not read as its own.
    app_setup.record_no_page(why="no Artifact tool in this chat")
    _code, lines = app_setup.start(on="test", tools="none")
    said = "\n".join(lines)
    assert lines[0] == "app start: set up"
    assert "1 improvement to their search has waited since" in said
    assert "upgrade.md" in said and "one plain line per change" in said
    _code, lines = app_setup.start(on="test", tools="none", work="draft~a")
    assert "upgrade.md" not in "\n".join(lines)


# ------------------------------------------------------------------ X-62, X-75


def test_a_turn_that_changed_the_persons_files_is_held_until_a_save_starts(copy, tmp_path):
    """X-62: a quick edit in a phone chat was answered and never committed, and was gone with
    the computer. The end of the turn is held once for it, and let go while the landing runs
    or once it is saved."""
    path = _transcript(tmp_path, TURN)
    assert _stop(path) == {}                           # nothing unsaved: nothing held
    (copy / "job_search_tracker.csv").write_text(
        "date,company,role,status\n2026-11-03,Kestrel Mutual,Analyst,interviewing\n",
        encoding="utf-8")
    held = _stop(path)
    assert held["decision"] == "block" and "python3 tools/land.py" in held["reason"]
    assert "job_search_tracker.csv" in held["reason"]
    assert _stop(path, active=True) == {}
    lock = os.path.join(land.git_dir(str(copy)), land.LOCK_FILE)
    with open(lock, "w", encoding="utf-8") as fh:
        fh.write(land.lock_text())
    assert _stop(path) == {}                           # the landing is running
    os.remove(lock)
    git(copy, "add", "-f", "job_search_tracker.csv")
    git(copy, "commit", "-q", "-m", "the tracker")
    assert "not on GitHub" in _stop(path)["reason"]    # committed, but only here
    git(copy, "push", "-q")
    assert _stop(path) == {}


def test_a_reaction_and_unsaved_work_are_held_together(copy, tmp_path):
    (copy / "profile" / "notes.md").write_text("a note\n", encoding="utf-8")
    path = _transcript(tmp_path, TURN[:-1] + [_line("user", text="too formal, all of them")])
    held = _stop(path)
    assert "learned.py record" in held["reason"] and "tools/land.py" in held["reason"]


# ------------------------------------------------------------------ X-15, X-28


def test_what_the_updates_did_is_read_whatever_the_apps_own_commits_say(copy, monkeypatch):
    """X-15: `git log --grep=^Profile upgrade:` matched the app's own commits, whose bodies
    say it under subjects with no colon; reading their id crashed, and the page never showed
    what was done for the person, on every copy."""
    git(copy, "commit", "-q", "--allow-empty", "-m", "Offer to rewrite a saved intro once",
        "-m", "Profile upgrade: own-profile-review is offered by the sync.")
    git(copy, "commit", "-q", "--allow-empty", "-m", "Profile upgrade: method-drafts",
        "-m", "Your unsent applications were made again with the current build.")
    got = app_setup._upgrade_commits()
    assert [c["id"] for c in got] == ["method-drafts"]
    assert got[0]["said"].startswith("Your unsent applications")


def test_on_releases_no_update_waits_while_only_master_is_ahead(copy, monkeypatch):
    """X-28: between releases the app's master is ahead of the newest one, and a copy on
    releases holding that release was told "An update is waiting" that "update" could not
    take, with queued work held "after the update" for ever."""
    (copy / "CHANGELOG.md").write_text("# Changelog\n\n## [9.9.8] - 2026-10-30\n\n"
                                       "- **The release this copy holds.** Released.\n",
                                       encoding="utf-8")
    git(copy, "add", "CHANGELOG.md")
    git(copy, "commit", "-q", "-m", "the release, as the copy took it")
    base = git(copy, "rev-parse", "HEAD").stdout.strip()
    git(copy, "update-ref", "refs/remotes/app/stable", base)
    git(copy, "switch", "-q", "-c", "ahead")
    (copy / "CHANGELOG.md").write_text("# Changelog\n\n## [9.9.9] - 2026-11-02\n\n"
                                       "- **Something new on master.** Not released.\n\n"
                                       "## [9.9.8] - 2026-10-30\n\n"
                                       "- **The release this copy holds.** Released.\n",
                                       encoding="utf-8")
    git(copy, "add", "CHANGELOG.md")
    git(copy, "commit", "-q", "-m", "the app's master moves on")
    git(copy, "update-ref", "refs/remotes/app/master", "HEAD")
    git(copy, "switch", "-q", "claude/this-chat")
    monkeypatch.setattr(app_setup, "ROOT", str(copy))
    monkeypatch.setattr(sync_app, "ROOT", str(copy))
    git(copy, "remote", "set-url", "origin", "https://github.com/kestrelpine/my-search")
    assert sync_app.channel() == "stable"
    assert sync_app.channel_target() == sync_app.STABLE
    assert app_setup.updates_section(dt.date(2026, 11, 3), {})["waiting"] is None
    # A release past what the copy holds is waiting, and named.
    git(copy, "update-ref", "refs/remotes/app/stable", "refs/remotes/app/master")
    waiting = app_setup.updates_section(dt.date(2026, 11, 3), {})["waiting"]
    assert waiting and "Something new on master" in waiting["line"]


# ------------------------------------------------------------------ X-54


def test_a_cloud_chats_proxy_address_is_read_as_the_persons_copy(copy, monkeypatch):
    """X-54: a cloud chat whose checkout reaches GitHub through a proxy address was told its
    own copy was "not a copy", with the make-a-copy steps, before the update check, for
    good. Every reader of the address reads that form now; a form no version can read still
    takes the update check first."""
    proxy = "http://local_proxy" + "@127.0.0.1:4567/git/fernbrightwater/my-job-search"
    assert sync_app.repo_of(proxy) == ("fernbrightwater", "my-job-search")
    assert sync_app.repo_of("git" + "@github.com:fernbrightwater/my-job-search.git") == (
        "fernbrightwater", "my-job-search")
    assert sync_app.repo_of("/tmp/somewhere/origin.git") == ("", "")
    monkeypatch.setattr(app_setup, "ROOT", str(copy))
    git(copy, "remote", "set-url", "origin", proxy)
    assert app_setup.origin() == ("fernbrightwater", "my-job-search")
    monkeypatch.delenv(app_setup.COPY_ENV, raising=False)
    assert app_setup.repo_kind_offline()["kind"] == "copy"
    # An address nothing can read: the update check comes before "not a copy".
    git(copy, "remote", "set-url", "origin", "http://127.0.0.1:4567/elsewhere/odd")
    os.makedirs(copy / "tools", exist_ok=True)
    (copy / "tools" / "sync_app.py").write_text("# the app's\n", encoding="utf-8")
    monkeypatch.setattr(app_setup, "state", lambda runner=None: {
        "repo": {"kind": "none", "owner": "", "name": ""}, "setup": {"state": "", "say": ""},
        "page": {}, "page_current": False, "stale": True, "answers": {}, "set_up": True})
    code, lines = app_setup.start(on="test", tools="none")
    said = "\n".join(lines)
    assert code == 1 and said.index("sync_app.py --pull") < said.index("Then open a chat")


# ------------------------------------------------------------------ the sync


def _stubs(me, page=True, sites=True):
    """Stand-ins for the files the sync reads from the copy: the page's line (app_setup) and
    the job sites' check (env_check), so their order can be seen."""
    if page:
        write(me, "tools/app_setup.py", "def page_line(landed=False):\n"
                                        "    return \"Claude: the person's page is not "
                                        "published yet.\"\n")
        write(me, "tools/profile_upgrades.py", "import sys\nsys.path.insert(0, 'tools')\n"
                                               "import app_setup\nprint(app_setup.page_line())\n")
    if sites:
        write(me, "tools/env_check.py", "print(\"This chat can't reach job sites yet.\")\n")
    commit(me, "stand-ins")


def test_one_unsaved_file_of_theirs_no_longer_stops_the_days_update(repos, tmp_path):  # noqa: F811
    """The chat-only review: a chat that skipped landing left profile/person.json changed,
    and every morning's update stopped on it ("Commit or stash these first"), every retry
    too. In a cloud chat their own files are saved first, alone, and the update is taken."""
    app, me = repos
    _with_local_origin(me, tmp_path)
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    write(me, "profile/person.json", '{"changed": "by a chat that never saved"}\n')
    env = dict(ENV, LJS_APP_URL=app, CLAUDE_CODE_REMOTE="true")
    r = subprocess.run([sys.executable, os.path.join(me, "tools", "sync_app.py"), "--if-stale"],
                       cwd=me, env=env, text=True, encoding="utf-8", capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert read(me, "README.md") == "v2\n"
    log = sh(me, "git", "log", "--format=%s", "-3")
    assert sync_app.SAVED_FIRST in log
    assert sh(me, "git", "status", "--porcelain", "--untracked-files=no") == ""
    # On a computer, where another chat may be writing them, and for a file of the app's,
    # it still stops and changes nothing.
    write(me, "profile/person.json", '{"changed": "again"}\n')
    write(me, ".git/ljs-last-sync", "2000-01-01\n")
    computer = {k: v for k, v in ENV.items() if k != "CLAUDE_CODE_REMOTE"}
    r = subprocess.run([sys.executable, os.path.join(me, "tools", "sync_app.py"), "--if-stale"],
                       cwd=me, env=dict(computer, LJS_APP_URL=app), text=True,
                       encoding="utf-8", capture_output=True)
    assert r.returncode == 1 and "Commit or stash" in r.stdout
    write(me, "README.md", "edited here\n")
    r = subprocess.run([sys.executable, os.path.join(me, "tools", "sync_app.py"), "--if-stale"],
                       cwd=me, env=env, text=True, encoding="utf-8", capture_output=True)
    assert r.returncode == 1 and "Commit or stash" in r.stdout
    assert "again" in read(me, "profile/person.json")


def test_a_check_already_run_today_still_says_the_page_and_says_it_first(repos, tmp_path):  # noqa: F811
    """X-52: the page's line came only from the day's first check, last, under the job sites'
    "before anything else": a chat that stopped there to wait for the person never reached
    it, and every later check that day said nothing about the page."""
    app, me = repos
    _with_local_origin(me, tmp_path)
    _stubs(me)
    env = dict(ENV, LJS_APP_URL=app, CLAUDE_CODE_REMOTE="true")
    sync = [sys.executable, os.path.join(me, "tools", "sync_app.py"), "--if-stale"]
    first = subprocess.run(sync, cwd=me, env=env, text=True, encoding="utf-8",
                           capture_output=True).stdout
    later = subprocess.run(sync, cwd=me, env=env, text=True, encoding="utf-8",
                           capture_output=True).stdout
    assert "already checked today" in later
    for out in (first, later):
        assert "page is not published yet" in out, out
        assert out.index("page is not published yet") < out.index("Job sites blocked"), out
        assert "before anything else" not in out


def test_a_check_that_cannot_finish_still_says_the_page_and_waits_before_asking_again(
        repos, tmp_path, monkeypatch):  # noqa: F811
    """X-46: while the day's check kept failing, start said "page to publish" and no step
    published it. X-71: and the hook asked for the failing check before every message."""
    app, me = repos
    _with_local_origin(me, tmp_path)
    _stubs(me, sites=False)
    rc, out = run(me, str(tmp_path / "no-such-app"), "--if-stale")
    assert rc == 2 and "page is not published yet" in out
    probe = [sys.executable, "-c", "import sys; sys.path.insert(0, 'tools'); import sync_app; "
             "print(sync_app.stale(), sync_app.retry_due())"]
    said = subprocess.run(probe, cwd=me, env=ENV, text=True, encoding="utf-8",
                          capture_output=True).stdout.split()
    assert said == ["True", "False"]
    # The hook says nothing while the check waits, and asks again once RETRY_HOURS pass.
    monkeypatch.setattr(sync_app, "stale", lambda: True)
    monkeypatch.setattr(sync_app, "retry_due", lambda: False)
    monkeypatch.setenv(person.ENV, os.path.join(ROOT, "profile.example"))
    monkeypatch.setattr(learned, "_path", lambda: "/a/copy/profile/learned.json")
    monkeypatch.setattr(person, "in_example", lambda p: False)
    ask = {"hook_event_name": "UserPromptSubmit", "prompt": "find me some jobs"}
    assert learned._update_due(ask) == ""
    monkeypatch.setattr(sync_app, "retry_due", lambda: True)
    assert learned._update_due(ask) == sync_app.HOOK_LINE


def test_an_update_that_changed_the_app_skill_says_so(copy, monkeypatch, capsys):
    """X-36: the chat that answers the page runs the brief, whose check took an update that
    rewrote the app skill, and went on all day with the old one in mind, told only that
    CLAUDE.md changed."""
    git(copy, "switch", "-q", "--orphan", "app")
    write(copy, ".claude/skills/app/SKILL.md", "the new skill\n")
    write(copy, "tools/x.py", "x = 1\n")
    git(copy, "add", ".claude/skills/app/SKILL.md", "tools/x.py")
    git(copy, "commit", "-q", "-m", "the app's release")
    git(copy, "switch", "-q", "-f", "claude/this-chat")
    git(copy, "merge", "-q", "--allow-unrelated-histories", "-m",
        "Sync from the app: 1 new commit(s)", "app")
    monkeypatch.setenv(U.LANDED, "1")
    said = U.say_changed()
    assert said == ["Claude: .claude/skills/app/SKILL.md changed. A chat that was already open "
                    "is still following the copy it read when it started: read "
                    ".claude/skills/app/SKILL.md again now, before going on."]
    monkeypatch.setenv(U.LANDED, "0")
    assert U.say_changed() == []
