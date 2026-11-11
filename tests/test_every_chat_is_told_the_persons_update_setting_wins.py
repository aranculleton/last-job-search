"""Every chat is told the person's own update setting, as the rule that wins over its history.

The maintainer, 2026-11-11: "I keep having to tell all the chats, and for some reason they're
all stuck on something I said in October, like wait for updates when I say". Their profile had
said updates come by themselves since the night before, and the October rule was retired, but
a chat kept open for days, a compacted chat and the chat a scheduled task wakes each morning
still held "If an update is waiting, say so in one plain line and wait." in their own history,
which no file reaches. Now the start, the brief's start and every check a chat runs end with
one line for Claude naming the setting, where the person wrote one, as what wins.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import sync_app  # noqa: E402
from test_sync_app import (_with_local_origin, commit, read, repos, run, write,  # noqa: E402,F401
                           )

AUTO = sync_app.SETTING_LINES["auto"]
WAIT = sync_app.SETTING_LINES["when_asked"]


def _set(me, value):
    write(me, "profile/person.json", json.dumps({"app_updates": value}) + "\n")
    commit(me, f"updates: {value}")


def _last(out):
    return out.rstrip("\n").splitlines()[-1]


def test_every_check_a_chat_runs_ends_with_the_setting(repos, tmp_path):  # noqa: F811
    app, me = repos
    _with_local_origin(me, tmp_path)
    _set(me, "auto")
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    for args in ((), ("--if-stale",), ("--if-stale",), ("--update",), ("--if-moved",)):
        rc, out = run(me, app, *args)
        assert rc == 0, (args, out)
        assert _last(out) == AUTO and out.count(AUTO) == 1, (args, out)
    assert read(me, "README.md") == "v2\n"
    assert "already checked today" in run(me, app, "--if-stale")[1]
    # A look that changes nothing, and the tools' own runs, are not a chat's check.
    for args in (("--check",), ("--pull",)):
        assert AUTO not in run(me, app, *args)[1], args


def test_where_updates_wait_the_line_says_so_and_names_no_command(repos):  # noqa: F811
    app, me = repos
    assert run(me, app)[0] == 0
    _set(me, "when_asked")
    write(app, "README.md", "v2\n")
    commit(app, "app v2")
    rc, out = run(me, app)
    assert rc == 0 and _last(out) == WAIT, out
    assert read(me, "README.md") == "v1\n"
    assert "--update" not in out and "python3" not in out


def test_nothing_is_said_where_the_person_set_nothing(repos):  # noqa: F811
    app, me = repos
    rc, out = run(me, app)
    assert rc == 0 and "Claude: updates" not in out, out


def _start(monkeypatch, capsys, said, work=""):
    import app
    import app_listen
    import app_setup
    monkeypatch.setattr(app, "days_check", lambda on, chat, tools="", new_chat=False: {
        "ran": True, "rc": 0, "said": said, "landed": False, "before": "abc"})
    monkeypatch.delenv(app.START_UPDATED, raising=False)
    monkeypatch.setattr(app_setup, "start", lambda **k: (
        0, ["app start: set up", "Claude, do this:", "1. Carry on with what the person asked."]))
    monkeypatch.setattr(app_listen, "shape", lambda code, lines, **k: lines)
    monkeypatch.setattr(app, "own_tests_first", lambda: "")
    a = types.SimpleNamespace(argv=["start"], paste=False, work=work, on="m", tools="none",
                              page="", chat="", listen=False, helper=False, dump="")
    assert app.cmd_start(a) == 0
    return capsys.readouterr().out


def test_the_start_says_it_once_last_and_a_jobs_chat_never(repos, monkeypatch, capsys):  # noqa: F811
    app, me = repos
    _set(me, "auto")
    rc, said = run(me, app, "--if-stale")
    assert rc == 0 and AUTO in said
    monkeypatch.setattr(sync_app, "ROOT", me)
    out = _start(monkeypatch, capsys, said)
    assert _last(out) == AUTO and out.count(AUTO) == 1, out
    assert "update check ran in this command" in out
    # A chat started for one big job takes no update part way through: nothing about taking them.
    assert AUTO not in _start(monkeypatch, capsys, "", work="w-1")


def test_the_briefs_start_says_it_first(tmp_path, monkeypatch, capsys):
    import brief
    import person
    copy = tmp_path / "copy"
    write(str(copy), "profile/person.json", json.dumps({"app_updates": "auto"}) + "\n")
    monkeypatch.setattr(sync_app, "ROOT", str(copy))
    monkeypatch.setenv("LJS_BRIEF_SYNC", str(tmp_path / "sync.txt"))

    class Done:
        returncode, stdout, stderr = 0, "", ""
    monkeypatch.setattr(brief.subprocess, "run", lambda argv, **kw: Done())
    monkeypatch.setattr(brief, "page_url", lambda: "")
    monkeypatch.setattr(person, "today", lambda now=None: dt.date(2026, 11, 11))
    import land
    monkeypatch.setattr(land, "stranded", lambda root=None, fetch=False: {}, raising=False)
    monkeypatch.setattr(brief, "_prompts_seen", lambda: {})
    assert brief.start(["--on", "a model", "--write"], "a model") == 0
    out = capsys.readouterr().out
    assert out.startswith(AUTO + "\n"), out
