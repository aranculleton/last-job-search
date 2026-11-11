"""A chat that works round an app command files it then, with one command it is handed.

Issue #240: in the maintainer's own copy, chats filed app bugs only when the person pointed one
out. What a chat met itself (an id refused and retried as a file, a step done by hand) was
worked round and never filed, and the person's complaint that nothing was filed was not filed
either. Now `app_bug.py met` is the one command for that moment, with the same check and the
same look as `check`, and the refusals a chat recovers from (tweak.py, app.py next and done,
network/reply.py) print it ready to run, so filing does not rest on a rule remembered. Only
the maintainer's own copy files; anywhere else nothing is printed and nothing filed. No
network; invented names only.
"""
# ruff: noqa: F811  (the app_bug tests' `copy` and the reply tests' `search`, imported and taken as parameters)
from __future__ import annotations

import json
import os
import shlex
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import app  # noqa: E402
import app_bug  # noqa: E402
import sync_app  # noqa: E402
import tweak  # noqa: E402
from test_a_reply_takes_two_commands import LARKSPUR, run, search, write  # noqa: E402,F401
from test_app_bug import KNOWN, copy  # noqa: E402,F401

TOOL = "tools/tweak.py:apply"
WHAT = "tweak.py apply refused: No work item tweak~a1 found: give the read folder before it"
DID = "ran it again with the item's own file"


def _met(copy, capsys, what=WHAT, did=DID, tool=TOOL, **kw):
    code = app_bug.met(tool, what, did, build=copy["build"], known=KNOWN, **kw)
    return code, capsys.readouterr().out


def _command(line: str) -> list[str]:
    """The met command a refusal printed, as a chat runs it, its workaround filled in."""
    cmd = line.split("said to nobody: ", 1)[1].rsplit(", and do the steps it prints", 1)[0]
    args = shlex.split(cmd)
    assert args[:2] == ["python3", "tools/app_bug.py"] and args[2] == "met", args
    return [DID if a == "<what you did instead>" else a for a in args[2:]]


# ------------------------------------------------------------------ met: the same check, the same look


def test_a_workaround_naming_something_of_the_copys_is_refused_and_never_printed(copy, capsys):
    code, out = _met(copy, capsys, did="edited the draft for Wexmoor Lending by hand")
    assert code == 1 and "nothing filed" in out and "denylist entry 2" in out
    assert "Wexmoor" not in out and "list_issues" not in out
    code, out = _met(copy, capsys, what="tweak.py apply refused after Quillon Varga wrote")
    assert code == 1 and "a full name the app has never carried" in out and "Quillon" not in out


def test_a_workaround_is_looked_for_first_and_the_same_one_gets_a_comment_not_an_issue(
        copy, capsys):
    code, out = _met(copy, capsys)
    assert code == 0 and "say nothing about it" in out
    key = app_bug.met_key(TOOL, app_bug.met_title(WHAT))
    assert f"checked (key {key})" in out and f"<!-- app-bug: {key} -->" in out
    look = out.split("1. Look first", 1)[1].split("2. The same bug found", 1)[0]
    assert "state OPEN" in look and "state CLOSED" in look and "these words find it: tweak apply" in look
    same = out.split("2. The same bug found", 1)[1].split("3. Nothing to wake", 1)[0]
    assert "file nothing new" in same and "add_issue_comment" in same
    assert "comment:\nSeen again (version 4.15.1" in out
    body = out.split("body:\n", 1)[1]
    assert f"What happened: {WHAT}" in body and f"Worked round it: {DID}" in body
    assert f"Where: {TOOL}" in body and "nobody asked for it to be filed" in body
    # Met again, however spaced or capitalised: the same key, so the same issue gets the comment.
    _, again = _met(copy, capsys, what="  " + WHAT.lower().replace(" ", "  ") + " ",
                    tool="python3 tools/tweak.py apply")
    assert f"checked (key {key})" in again
    # Another refusal of the same command is another bug, never folded into the first.
    _, other = _met(copy, capsys, what="tweak.py apply refused: More changed than was asked")
    assert f"checked (key {key})" not in other


def test_a_chat_that_cannot_reach_the_apps_issues_holds_it_with_the_same_command(
        copy, capsys, monkeypatch):
    monkeypatch.setattr(app_bug, "ROOT", str(copy["tmp"]))
    _, out = _met(copy, capsys)
    assert "still refused: python3 tools/app_bug.py met <the same words> --hold" in out
    code, out = _met(copy, capsys, keep=True)
    assert code == 0 and "held for the next cloud chat" in out and "list_issues" not in out
    (held,) = app_bug.held()
    assert held["tool"] == TOOL and "Worked round it" in held["body"]
    assert app_bug.file_held(build=copy["build"], known=KNOWN) == 0
    assert f"filed {held['key']}" in capsys.readouterr().out


def test_the_persons_complaint_that_nothing_was_filed_is_filed_too(copy, capsys):
    code, out = _met(copy, capsys, tool=".claude/skills/app/chat.md",
                     what="Chats only file app bugs when asked; a workaround is never filed",
                     did="filed the missed workaround now", person=True)
    assert code == 0 and "The person said a chat should have filed this by itself" in out


def test_the_placeholder_as_printed_is_not_a_workaround(copy, capsys):
    code, out = _met(copy, capsys, did="<what you did instead>")
    assert code == 3 and "nothing filed" in out and copy["builds"] == []


def test_any_other_copy_files_nothing_and_the_person_hears_nothing(copy, capsys, monkeypatch):
    monkeypatch.setattr(sync_app, "maintainers", lambda: False)

    def never(out, tokens):
        raise AssertionError("nothing is built in anyone else's copy")
    assert app_bug.main(["met", "--tool", TOOL, "--what", WHAT, "--did", DID], build=never) == 2
    out = capsys.readouterr().out
    assert "nothing is filed" in out and "person hears nothing" in out and "link" not in out
    assert app_bug.met_line(TOOL, WHAT) == ""


# ------------------------------------------------------------------ the refusals print it


def test_a_tweak_refused_carries_the_met_command_ready_to_run(copy, capsys, monkeypatch, tmp_path):
    # The real refusal of issue #224: the item's id with no read folder before it.
    assert tweak.main(["apply", "--work", "tweak~nosuch-item"]) == 1
    got = json.loads(capsys.readouterr().out)
    assert got["status"] == "refused" and "if_you_work_round_this" in got
    args = _command(got["if_you_work_round_this"])
    assert args[args.index("--tool") + 1] == "tools/tweak.py:apply"
    assert args[args.index("--what") + 1].startswith("tweak.py apply refused: No work item")
    # Run as printed, it is checked and its steps come back.
    assert app_bug.main(args, build=copy["build"]) == 0
    assert "1. Look first" in capsys.readouterr().out
    # Anywhere else the refusal is as it was.
    monkeypatch.setattr(sync_app, "maintainers", lambda: False)
    assert tweak.main(["apply", str(tmp_path), "--work", "tweak~nosuch-item"]) == 1
    assert "if_you_work_round_this" not in json.loads(capsys.readouterr().out)


def test_app_done_and_next_refused_print_the_met_line_beneath(copy, capsys, monkeypatch, tmp_path):
    assert app.main(["done", str(tmp_path), "--work", "nosuch", "--summary", "Done."]) == 2
    err = capsys.readouterr().err
    first, line = err.strip().splitlines()[:2]
    assert first.startswith("app: not finished: no work")
    assert line.startswith("if you work round this") and "tools/app.py:done" in line
    assert _command(line)[_command(line).index("--what") + 1].startswith("app.py done refused:")
    monkeypatch.setattr(app, "choose", lambda *a, **k: (_ for _ in ()).throw(
        ValueError("--kind must be cloud or computer")))
    assert app.main(["next", str(tmp_path), "--chat", "c1", "--kind", "cloud"]) == 2
    assert "tools/app.py:next" in capsys.readouterr().err
    monkeypatch.setattr(sync_app, "maintainers", lambda: False)
    assert app.main(["done", str(tmp_path), "--work", "nosuch", "--summary", "Done."]) == 2
    assert "app_bug" not in capsys.readouterr().err


# Runs reply.py itself, the maintainer's copy alone faked: its check is git's, not the test's.
AS_THE_MAINTAINER = ("import runpy, sys; sys.path.insert(0, 'tools'); import sync_app; "
                     "sync_app.maintainers = lambda: True; sys.argv = sys.argv[1:]; "
                     "runpy.run_path(sys.argv[0], run_name='__main__')")


def test_a_reply_refused_by_its_check_prints_the_met_line(search):
    bad = write(search, "bad.txt", "Thanks Juno — I can leverage my synergies.")
    code, out = run(search, "-c", AS_THE_MAINTAINER, "tools/network/reply.py", "finish",
                    LARKSPUR, "--draft-file", bad)
    assert code == 1 and "REFUSED, nothing saved" in out and "Rewrite it and run finish again." in out
    line = next(ln for ln in out.splitlines() if ln.startswith("if you work round this"))
    args = _command(line)
    assert args[args.index("--tool") + 1] == "tools/network/reply.py:finish"
    assert "draft check refused the draft: em_dash" in args[args.index("--what") + 1]
    code, out = run(search, "tools/network/reply.py", "finish", LARKSPUR, "--draft-file", bad)
    assert code == 1 and "app_bug" not in out                  # the app itself: as it was


# ------------------------------------------------------------------ the skill says so


def test_the_app_skill_files_a_workaround_and_a_complaint_in_the_same_turn():
    with open(os.path.join(ROOT, ".claude", "skills", "app", "chat.md"), encoding="utf-8") as fh:
        chat = " ".join(fh.read().split())
    wrong = chat.split('**"Something looks wrong"**', 1)[1].split("**\"Pin my job", 1)[0]
    mine = wrong.split("**In the app maintainer's own copy**", 1)[1]
    for must in ("**A workaround is filed in the same turn, without asking**",
                 "python3 tools/app_bug.py met --tool <file>:<function>",
                 "said to nobody", "if you work round this", "if_you_work_round_this",
                 "**The person's complaint that something should have been filed is filed too**",
                 "never only promised", "met --person",
                 "Any other copy prints no such line, and `met` files nothing there."):
        assert must in mine, must
