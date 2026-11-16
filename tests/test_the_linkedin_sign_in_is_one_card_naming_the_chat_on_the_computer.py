"""A LinkedIn sign-in a chat on the person's computer waits on is one card on their page, which
names that chat and gives the steps to sign in there, and never a link to it.

Issues 285 and 286 (2026-11-16): the card said "tap Open the chat, then sign in on the page
already open there". Its button opened the chat's claude.ai link, which is a Remote Control view
of it, and there the browser says "Browser isn't available in remote control sessions": the
sign-in could not happen, and the read waited for good. The same chat opened from the list of
chats in the Claude app on the computer had its browser, and the sign-in worked. No link opens a
chat in the desktop app (claude_surfaces `deep-links`), so the card names the chat and gives the
registry's steps (`computer-chat-signin`), Keep cookies among them. A second card for the read
queued behind it asked for the same sign-in again, in other words ("signed out again ... keep
the sign-in there once"). Invented people and computers only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import claude_surfaces  # noqa: E402
import computer  # noqa: E402
import page_db  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, _db, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

T = app_model.parse_time(NOW)
READ_A, READ_B = "network~read~1", "network~read~2"
CHAT = "session_macEXAMPLE"
# The title the chat was started with (computer.session_title), as the person's list shows it.
CHAT_TITLE = "Job search · Reading 3 profiles · Studio Laptop"


def _beat(**facts) -> dict:
    f = dict(browser="shown", linkedin="out", cookies="unknown", read="ok", version="9.9.9",
             task=False, system="darwin")
    f.update(facts)
    data = computer.beat_fields("Studio Laptop", T - dt.timedelta(minutes=1), **f)
    return {computer.beat_id("Studio Laptop"): {"data": data, "version": 3}}


def _mac_steps() -> list:
    return [ln for ln in claude_surfaces.steps("computer-chat-signin-mac", page=True)
            if ln[:1].isdigit()]


def _running(title="Reading 3 profiles", minutes=15) -> dict:
    at = app_model.stamp(T - dt.timedelta(minutes=minutes))
    return _w("network", "Harbourline Bank", to="computer", title=title, status="running",
              claimed_by=CHAT, claimed_as="computer", claimed_at=at,
              lease_until=app_model.stamp(T + dt.timedelta(minutes=20)),
              computer_session={"id": CHAT, "env": "env_bridge1", "computer": "Studio Laptop",
                                "at": at})


def _needs(db: dict, wid: str, tmp_path) -> dict:
    """What `app.py done --signin linkedin` writes for the chat on the computer, as the page
    reads it."""
    made = page_db.finish(db, wid, T, str(tmp_path / ("f-" + wid.replace("~", "-"))),
                          status="needs_you",
                          question="LinkedIn is signed out in Claude's browser.",
                          signin="linkedin", chat_kind="computer", chat=CHAT)
    batches = made["batches"] if isinstance(made, dict) else made
    entry = json.load(open(batches[0], encoding="utf-8"))[0]
    fields = entry.get("data")
    if fields is None:
        fields = json.load(open(entry["file_path"], encoding="utf-8"))
    return fields


def test_the_reads_own_card_names_the_chat_and_gives_the_steps_never_its_link(tmp_path):
    db = _db((READ_A, _running()), chats=_beat())
    needs = _needs(db, READ_A, tmp_path)["needs"]
    assert needs["signin"] == "linkedin" and needs["chat"] == CHAT
    # The chat by the name it has in the person's list, and the computer by its own name.
    assert "“" + CHAT_TITLE + "”" in needs["say"], needs["say"]
    assert "Studio Laptop" in needs["say"]
    # Never "tap Open the chat": that link opens the chat without its browser.
    assert "Open the chat" not in needs["say"]
    assert "claude.ai/code" not in json.dumps(needs) and "linkedin.com" not in json.dumps(needs)
    # The registry's steps for the computer's own system: open it from the app's list, show
    # its browser, sign in, keep the sign-in, then the card's own button.
    assert needs["steps"] == _mac_steps()
    joined = " ".join(needs["steps"])
    assert "Cmd+Shift+B" in joined and "Keep cookies" in joined and "I've signed in" in joined
    assert "Ctrl+Shift+B" not in joined


def test_the_computers_card_for_a_held_read_names_the_chat_and_has_no_link():
    db = _db((READ_A, _running()), chats=_beat())
    st = computer.state(db, T, envs=BRIDGE)
    assert st["state"] == "signed_out" and st["card"] and st["signin_chat"] == CHAT, st
    card = computer.card(st)
    assert "open" not in card, card
    assert "“" + CHAT_TITLE + "”" in card["body"] and "Open the chat" not in card["body"]
    assert card["steps"] == _mac_steps()
    assert [o["label"] for o in card["options"]] == ["I've signed in"]
    assert "claude.ai/code" not in json.dumps(card)
    assert card["link"] == claude_surfaces.official(
        claude_surfaces.entry("computer-chat-signin-mac"))


def test_one_card_covers_every_read_waiting_on_the_same_sign_in(tmp_path):
    # Read A met the sign-out and waits on its own card; read B is queued behind it.
    db = _db((READ_A, _running()), chats=_beat())
    asked = dict(db["work"][READ_A]["data"], **_needs(db, READ_A, tmp_path))
    queued = _w("network", "Northgate Insurance", to="computer", title="Reading 2 profiles",
                asked=app_model.stamp(T - dt.timedelta(minutes=40)))
    db = _db((READ_A, asked), (READ_B, queued), chats=_beat())
    st = computer.state(db, T, envs=BRIDGE)
    assert st["state"] == "signed_out"
    # Before: the computer's own card asked for the same sign-in beside the read's own.
    assert not st["card"], st
    assert computer.card(st) is None


def test_a_sign_in_that_did_not_last_is_kept_on_that_same_card(tmp_path):
    db = _db((READ_A, _running()), chats=_beat())
    asked = dict(db["work"][READ_A]["data"], **_needs(db, READ_A, tmp_path))
    first = computer.beat_fields("Studio Laptop", T - dt.timedelta(minutes=120), browser="shown",
                                 linkedin="out", version="9.9.9", task=False, system="darwin")
    again = computer.beat_fields("Studio Laptop", T - dt.timedelta(minutes=1), browser="shown",
                                 linkedin="out", version="9.9.9", task=False, system="darwin")
    lost = dict(again, **computer.cookies_seen(
        first, again, since_in=app_model.stamp(T - dt.timedelta(minutes=60))))
    queued = _w("network", "Northgate Insurance", to="computer", title="Reading 2 profiles",
                asked=app_model.stamp(T - dt.timedelta(minutes=40)))
    db = _db((READ_A, asked), (READ_B, queued),
             chats={computer.beat_id("Studio Laptop"): {"data": lost, "version": 3}})
    st = computer.state(db, T, envs=BRIDGE)
    # The read's own card already asks to keep the sign-in (its steps hold Keep cookies): no
    # second card asking "keep the sign-in there once, then sign in again".
    assert st["say"] != "keep_signin" and not st["card"], st
    assert any("Keep cookies" in s for s in asked["needs"]["steps"])


def test_the_chat_on_the_computer_is_told_the_card_names_it():
    # Its own prompt and the steps it prints say what the card does, so it never tells the
    # person to tap a button that opens it.
    prompt = computer.session_prompt(READ_A, "Reading 3 profiles", "https://claude.ai/x", "x")
    for text in (prompt, computer.SIGNED_OUT_ON_PAGE):
        assert "one button opens this chat" not in text
        assert "names this chat" in text


# ------------------------------------------------------------------ the page draws it


TODO = r"""(() => {
  const boxes = [...document.querySelectorAll('#main [data-signin="linkedin-chat"]')];
  return {boxes: boxes.length,
          links: boxes.reduce((n, b) => n + b.querySelectorAll('a[href*="claude.ai/code"]').length, 0),
          steps: boxes.length ? [...boxes[0].querySelectorAll('li')].map((li) => li.textContent) : [],
          text: boxes.length ? boxes[0].textContent.replace(/\s+/g, ' ') : ''};
})()"""


@pytest.fixture(scope="module")
def run():
    import test_the_page_journeys as journeys
    yield from journeys.browser()


def test_the_page_shows_one_sign_in_card_and_its_tap_sends_every_read_back(run, tmp_path):
    import app_page
    import test_the_page_journeys as journeys
    steps = _mac_steps()
    say = computer.signin_in_chat("Studio Laptop", CHAT_TITLE)

    def waiting(title, minutes):
        return dict(_w("network", "Harbourline Bank", to="computer", title=title,
                       status="needs_you", note="LinkedIn is signed out.",
                       asked_you_at=app_model.stamp(T - dt.timedelta(minutes=minutes)),
                       computer_session={"id": CHAT, "computer": "Studio Laptop"}),
                    needs={"question": "LinkedIn is signed out in Claude's browser.",
                           "signin": "linkedin", "chat": CHAT, "say": say, "steps": steps,
                           "answer": {"key": "answer", "kind": "text"}}, _v=3)

    m = journeys._sample()
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(m)))
    seed = {f"work/{READ_A}": waiting("Reading 3 profiles", 20),
            f"work/{READ_B}": waiting("Reading 2 profiles", 5)}
    got = run("engine", html=path, viewport=journeys.WIDE,
              steps=[{"hash": "todo", "eval": TODO},
                     {"click": "I've signed in", "within": "#main", "exact": True}],
              seed=seed, fake={"canSend": "available"}, clock=NOW)
    assert not got["errors"], got["errors"]
    seen = got["after"][0]["eval"]
    assert seen["boxes"] == 1, seen                      # one card for the one sign-in
    assert seen["links"] == 0, seen                      # nothing opens the chat's link
    assert CHAT_TITLE in seen["text"] and "Open the chat" not in seen["text"], seen
    assert any("Keep cookies" in s for s in seen["steps"]), seen
    # Its one tap sends both reads back to Claude, not only the one the card was drawn for.
    after = {w["id"]: w for w in got["after"][1]["work"]}
    assert after[READ_A]["status"] == "queued" and after[READ_B]["status"] == "queued", after
