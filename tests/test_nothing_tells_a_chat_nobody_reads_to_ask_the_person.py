"""What the app tells a chat nobody reads (a chat it starts on the person's computer, the small
chat that starts those, a job's own chat, a helper's background agent, the brief) never has it
ask or tell the person in that chat, or wait for them to say done there: a question goes on
their page, as a card (journeys J8 and J9).

The local review of 2026-11-11 (4, 6): the sign-in steps a chat on the computer was given
said "tell the person ... then say done"; a second sign-out and a check said "tell the
person"; and a refused Auto told the wake's agent, the brief and the starter to "say exactly
this to the person, once, and wait for done". Invented people and computers only.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_listen  # noqa: E402
import computer  # noqa: E402
import reading  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import T, URL, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db, _w  # noqa: E402

# Asking or telling the person in the chat itself, or waiting there for their word. A sentence
# that forbids it ("never ...", "say nothing ...") is not one.
ASKS_IN_THE_CHAT = re.compile(
    r"\bsay (?:\\?\")?done\b|\btell the person\b|\bwait for (?:\\?\")?done\b|"
    r"\bsay exactly this to the person\b|\bopen (?:it|that chat|the chat)\b[^.]{0,40}\bin the "
    r"Claude app\b", re.I)


def _offenders(text: str) -> list[str]:
    out = []
    for sentence in re.split(r"(?<=[.;:])\s+|\n", text):
        m = ASKS_IN_THE_CHAT.search(sentence)
        if m and not re.search(r"\b(?:never|nothing|not)\b", sentence[:m.start()], re.I):
            out.append(sentence.strip())
    return out


def _said_to_chats_nobody_reads(monkeypatch, tmp_path) -> dict:
    import app
    wid = "network~read~1"
    _as(monkeypatch, "computer", tmp_path)
    db = _db((wid, _w("network", to="computer", title="Reading 3 profiles", args={"count": 3})))
    steps = app.choose(db, "mac-chat", "computer", T, on="claude-opus-5-5", no_sessions=True,
                       computer_only=True)["steps"]
    return {
        "the prompt of a chat started on the computer":
            computer.session_prompt(wid, "Reading 3 profiles", URL, "their job search"),
        "the steps next --computer-only prints": "\n".join(steps),
        "the starter's prompt": computer.starter_prompt(URL, "github.com/someone/my-job-search"),
        "the scheduled task's steps": "\n".join(computer.task_steps(URL)),
        "a sign-in in a job's chat": reading._job_signin_said(wid, "the session expired"),
        "a second sign-out in a job's chat": reading._job_friction_said(wid, "the sign-in page"),
        "a check in a job's chat": reading._job_check_said(wid, "Let's do a quick security check"),
        "a refused Auto, wherever it is said": app_listen.MODE_REFUSED,
    }


def test_nothing_said_to_a_chat_nobody_reads_asks_the_person_there(monkeypatch, tmp_path):
    for where, text in _said_to_chats_nobody_reads(monkeypatch, tmp_path).items():
        assert _offenders(text) == [], where


def test_the_lint_sees_what_it_is_for():
    assert _offenders("Tell the person, as it is: sign in, then say done.")
    assert _offenders("say exactly this to the person, once, and wait for \"done\"")
    assert _offenders("Open that chat in the Claude app and approve what it asks.")
    assert not _offenders("Never ask or tell the person anything in this chat.")
    assert not _offenders("Say nothing to the person in this chat.")


def test_a_refused_auto_is_one_card_on_the_page_that_links_the_chat(tmp_path, monkeypatch):
    """J8: create_session refused Auto because the chat starting it was not in Auto. The page
    asks, on one card, with that chat's link and the registry's steps; its Done is their word,
    and nothing waits in a chat."""
    import claude_surfaces
    from test_set_me_up_is_the_only_thing_said_in_a_chat import Copy
    c = Copy(str(tmp_path), profile=True)
    c.run("published", "https://claude.ai/code/artifact/example-page")
    env = dict(c.env(), CLAUDE_CODE_REMOTE="true")
    monkeypatch.setattr(c, "env", lambda: env)
    # Asked once already, and done: a refusal after it brings the card back.
    aid = c.act("setup.done", "q-setup-auto")
    assert c.apply()["ok"] == [aid]
    assert not [q for q in c.model()["needs_you"] if q["id"] == "q-setup-auto"]
    said = c.run("mode-refused", "--chat", "session_EXAMPLEhelper1", "--now", "2026-10-25T17:01:30Z")
    assert not _offenders(said) and "Say nothing" in said
    card = next(q for q in c.model()["needs_you"] if q["id"] == "q-setup-auto")
    assert card["open"] == {"label": "Open that chat",
                            "url": "https://claude.ai/code/session_EXAMPLEhelper1"}
    assert card["steps"] == claude_surfaces.steps("cloud-auto", page=True)[1:]
    assert "not in Auto" in card["body"]
    aid = c.act("setup.done", "q-setup-auto")
    assert c.apply()["ok"] == [aid]
    assert not [q for q in c.model()["needs_you"] if q["id"] == "q-setup-auto"]
