"""Every way a chat takes a LinkedIn read of the page's on the computer, LinkedIn signed out,
a second sign-out and a check all go on the person's page: nothing tells the chat to tell
the person, or to wait for them to say done, in a chat nobody reads (journey J2).

The local review of 2026-11-11 (4): a read was known as the page's only when `next
--computer-only` took it, so one taken by plain `next` (route's `here`) or by a cloud chat lent
the computer's browser was told "tell the person ... then say done"; a second sign-out and a
check said "tell the person" whatever chat it was. Invented people and computers only.
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import page_db  # noqa: E402
import reading  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search, _w  # noqa: E402

WID = "network~read~1"
LOGIN = "Sign in\nEmail or phone\nPassword\nForgot password?\nSign in\nNew to LinkedIn? Join now\n"
NEVER = ("tell the person", "say done", "ask once more")


def _said_to_a_chat_nobody_reads(out: str) -> None:
    low = out.lower()
    for words in NEVER:
        assert words not in low, (words, out)


@pytest.mark.parametrize("flags,kind", [
    (["--computer-only"], "computer"),          # a chat the app started on the computer
    ([], "computer"),                           # route's `here`: plain next on the computer
    (["--computer-only", "--lent"], "cloud"),   # a cloud chat lent the computer's browser
])
def test_every_way_a_read_is_taken_puts_its_sign_in_on_the_page(tmp_path, monkeypatch, capsys,
                                                                flags, kind):
    import app_listen
    import person
    s = Search(str(tmp_path))
    s.put("work", WID, _w("network", "Harbourline Bank", to="computer",
                          title="Reading 3 profiles"), version=4)
    got = json.loads(s.run("next", s.dump, "--chat", "chat-1", "--kind", "computer", *flags,
                           "--claim-out", os.path.join(s.dump, "claim"), "--now", NOW))
    assert got["work"] == WID and got["run"] == "here"
    monkeypatch.setenv(person.STATE_ENV, s.state)
    monkeypatch.setenv(person.ENV, s.profile)
    monkeypatch.setattr(app_listen, "chat_kind", lambda: kind)
    assert reading.app_job_here() == WID
    # LinkedIn's sign-in page instead of a profile.
    monkeypatch.setattr(sys, "stdin", io.StringIO(LOGIN))
    assert reading.main(["signin", "--page", "-"]) == reading.EXIT["signin"]
    out = capsys.readouterr().out
    _said_to_a_chat_nobody_reads(out)
    assert "--signin linkedin" in out and f"--work {WID}" in out
    # What it names, done: the read waits on the page's sign-in card.
    s.run("done", s.dump, "--work", WID, "--chat", "chat-1", "--kind", "computer", "--signin",
          "linkedin", "--question", "LinkedIn is signed out in Claude's browser.", "--now", NOW)
    item = page_db.load(s.dump)["work"][WID]["data"]
    assert item["status"] == "needs_you" and item["needs"]["signin"] == "linkedin"
    # Still the page's while it waits: a sign-in page seen meanwhile goes there too.
    monkeypatch.setattr(sys, "stdin", io.StringIO(LOGIN))
    reading.main(["signin"])
    out = capsys.readouterr().out
    _said_to_a_chat_nobody_reads(out)
    assert "--signin linkedin" in out


def test_a_second_sign_out_and_a_check_in_such_a_chat_go_on_the_page(tmp_path, monkeypatch,
                                                                     capsys):
    import person
    monkeypatch.setenv(person.STATE_ENV, str(tmp_path / "state"))
    monkeypatch.setattr(reading, "app_job_here", lambda: WID)
    for way_back in (reading.RESUME_LINE, ""):
        monkeypatch.setattr(reading, "_way_back", lambda now=None, w=way_back: w)
        reading._said_signout({"kind": "friction", "why": "LinkedIn's sign-in page again"})
        out = capsys.readouterr().out
        _said_to_a_chat_nobody_reads(out)
        assert f"--work {WID}" in out and "app.py done" in out
    said = reading._job_check_said(WID, "Let's do a quick security check")
    _said_to_a_chat_nobody_reads(said)
    assert f"--work {WID}" in said and "--failed" in said and "tomorrow" in said
