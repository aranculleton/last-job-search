"""LinkedIn signed out in a read on the person's computer goes on their page, one To do card,
and the read waits there for their Done: the chat on the computer never keeps it, or the steps
to sign in, in its own conversation.

The maintainer's Mac, 2026-11-11: the read found LinkedIn signed out, and the chat there wrote
the steps in its own chat and kept the job there, "rather than parking it on your page". Three
things told it to: the steps `next --kind computer --computer-only` prints said only "never
queue a profile for the page"; its prompt said to wait "never parking the job"; and the
sign-in question it put on the page ended its hold on the work here, so every later sign-in
line it was given was the one for a chat the person watches ("tell the person ... then say
done"), a second sign-out the same day included. Invented people and computers only.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import computer  # noqa: E402
import reading  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import T, URL, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search, _db, _w  # noqa: E402

WID = "network~read~1"


def test_the_steps_a_computer_chat_follows_put_a_sign_out_on_the_page(tmp_path, monkeypatch):
    import app
    _as(monkeypatch, "computer", tmp_path)
    db = _db((WID, _w("network", to="computer", title="Reading 3 profiles", args={"count": 3})))
    chosen = app.choose(db, "mac-chat", "computer", T, on="claude-opus-5-5", no_sessions=True,
                        computer_only=True)
    steps = "\n".join(chosen["steps"])
    # The one thing that stops the run on the computer is said, and said to go on the page.
    assert computer.SIGNED_OUT_ON_PAGE in steps
    assert "--signin linkedin" in steps and "Never write the sign-in" in steps
    assert "queued for their Done" in steps
    # The prompt of a chat the app starts there says the same, and never "never parking".
    prompt = computer.session_prompt(WID, "Reading 3 profiles", URL, "their job search")
    assert "parking" not in prompt
    assert "queued for their Done" in prompt and "never kept in this conversation" in prompt
    assert "nothing of the sign-in" in prompt


def test_a_sign_in_question_leaves_the_work_this_chats_so_the_sign_in_stays_on_the_page(
        tmp_path, monkeypatch):
    import app_listen
    import person
    s = Search(str(tmp_path))
    s.put("work", WID, _w("network", "Harbourline Bank", to="computer",
                          title="Reading 3 profiles"), version=4)
    claim = os.path.join(s.dump, "claim")
    got = json.loads(s.run("next", s.dump, "--chat", "mac-1", "--kind", "computer",
                           "--computer-only", "--claim-out", claim, "--now", NOW))
    assert got["work"] == WID
    s.run("done", s.dump, "--work", WID, "--chat", "mac-1", "--kind", "computer", "--signin",
          "linkedin", "--question", "LinkedIn is signed out in Claude's browser.", "--now", NOW)
    # In that chat on the computer, afterwards: the work is still its own, waiting on the page.
    monkeypatch.setenv(person.STATE_ENV, s.state)
    monkeypatch.setenv(person.ENV, s.profile)
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "computer")
    assert reading.app_job_here() == WID
    said = "\n".join(reading.signin_steps())
    assert "on their page, never in this chat" in said and "--work " + WID in said
    assert "tell the person" not in said.lower() and "say done" not in said


def test_a_second_sign_out_in_a_chat_the_app_started_goes_on_the_page(monkeypatch, capsys):
    monkeypatch.setattr(reading, "app_job_here", lambda: WID)
    got = {"kind": "friction", "why": "LinkedIn's sign-in page, the second sign-out today"}
    assert reading._said_signout(got) == reading.EXIT["check"]
    out = capsys.readouterr().out
    assert "--signin linkedin" in out and "--work " + WID in out
    assert "Tell the person" not in out and "never in this chat" in out
    # A chat the person reads is still told, as before.
    monkeypatch.setattr(reading, "app_job_here", lambda: "")
    reading._said_signout(got)
    assert "Tell the person" in capsys.readouterr().out
