"""A job that stopped because LinkedIn is signed out in Claude's browser is signed in inside the
page, and goes back to Claude by itself.

On 2026-11-10 a read of ten profiles on the person's computer stopped signed out, and its card
said "Sign in there once, then tap Done" over an Answer button that opened a text box. To sign
in, the person had to leave the page, find the job's chat on their computer and come back. The
page has its own LinkedIn panel inside the Claude app (openReading): the card uses it. Invented
people only.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_a_cards_actions_are_one_row_of_pills import _page  # noqa: E402
from test_the_page_journeys import PHONE  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
_W = {"args": {}, "asked_at": "2026-10-25T08:40:00.000Z", "_v": 2, "kind": "network",
      "status": "needs_you", "asked_you_at": "2026-10-25T08:50:00.000Z"}
SEED = {"chats/cloud-1": {"kind": "cloud", "seen_at": "2026-10-25T08:58:30.000Z", "watching": True},
        "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": "2026-10-25T08:56:00.000Z",
                          "since": "2026-10-24T08:00:00.000Z"},
        # Asked with the kind the page knows (app.py done --signin linkedin).
        "work/network~read~new": dict(_W, to="computer", title="Reading 3 profiles on your computer",
                                      note="LinkedIn is signed out in Claude's browser.",
                                      needs={"question": "LinkedIn is signed out in Claude's browser.",
                                             "work": "network~read~new", "signin": "linkedin",
                                             "answer": {"key": "answer", "kind": "text"}}),
        # Asked before the page knew it (4.14): the same card all the same.
        "work/network~read~old": dict(_W, to="computer", title="Reading 10 profiles on your computer",
                                      note="LinkedIn is signed out in Claude's browser on your computer. "
                                           "Sign in there once, then tap Done.",
                                      needs={"question": "x", "work": "network~read~old",
                                             "answer": {"key": "answer", "kind": "text"}})}

PROBE = r"""(() => {
  const out = {};
  for (const id of ['network~read~new', 'network~read~old']) {
    const cards = [...document.querySelectorAll('[data-item="work:' + id + '"], [data-work="' + id + '"]')];
    out[id] = cards.map((c) => ({
      signin: !!c.querySelector('[data-signin="linkedin"]'),
      buttons: [...c.querySelectorAll('button')].map((b) => (b.textContent || '').trim()),
    }));
  }
  return out;
})()"""


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def test_a_stopped_sign_in_is_made_on_the_page_never_in_an_answer_box(run, tmp_path):
    got = run("engine", html=_page(tmp_path), viewport=PHONE,
              steps=[{"hash": "todo", "eval": PROBE}], seed=SEED,
              fake={"canSend": "available"}, clock=T)
    assert not got["errors"], got["errors"]
    seen = got["after"][0]["eval"]
    for wid, cards in seen.items():
        assert cards, (wid, seen)
        for c in cards:
            assert c["signin"], (wid, c)
            assert "Sign in to LinkedIn" in c["buttons"], (wid, c)
            assert "Answer" not in c["buttons"], (wid, c)


QUEUED = r"""(() => {
  const c = document.querySelector('[data-work="network~read~wait"]');
  return c ? c.textContent.replace(/\s+/g, ' ') : null;
})()"""


def test_work_waiting_for_the_computer_says_so_with_no_clock(run, tmp_path):
    """"Waking Claude · 23m 41s" over a read waiting for the Mac read as stuck work (the
    maintainer's page, 2026-11-10)."""
    from test_the_page_journeys import WIDE
    seed = dict(SEED)
    seed["work/network~read~wait"] = {"args": {}, "asked_at": "2026-10-25T08:30:00.000Z", "_v": 2,
                                      "kind": "network", "status": "queued", "to": "computer",
                                      "title": "Reading 4 profiles on your computer"}
    # The computer is known and was seen lately, so the card is not "away".
    seed["chats/computer~studio-laptop"] = {"kind": "computer", "computer": "Studio Laptop",
                                            "seen_at": "2026-10-25T08:58:00.000Z", "watching": True}
    seed["meta/doorbell"] = {"ids": ["network~read~wait"], "rung_at": "2026-10-25T08:30:05.000Z",
                             "listener": "cloud-1", "thread": ""}
    got = run("engine", html=_page(tmp_path), viewport=WIDE,
              steps=[{"hash": "todo", "eval": QUEUED}], seed=seed,
              fake={"canSend": "available"}, clock=T)
    assert not got["errors"], got["errors"]
    text = got["after"][0]["eval"]
    assert text, "the waiting read has its card"
    assert "Waking Claude" not in text and "Waiting for your computer" in text, text


def test_a_reply_that_only_says_the_answer_follows_is_refused(tmp_path):
    """"Putting the change on your page first. The answer follows in a moment." finished the
    Chat item, so the page showed nothing running while the work went on (the maintainer,
    2026-11-10)."""
    import page_db
    db = {"work": {"talk~a": {"data": {"kind": "talk", "status": "running", "claimed_by": "cloud-1",
                                       "args": {"thread": "t1", "message": "m1"}}, "version": 3}}}
    import datetime as dt
    now = dt.datetime(2026, 10, 25, 9, tzinfo=dt.timezone.utc)
    with pytest.raises(ValueError, match="keep it running"):
        page_db.finish(db, "talk~a", now, str(tmp_path / "o"), summary="Answered.",
                       reply="Putting the change on your page first. The answer follows in a moment.",
                       thread="t1", chat="cloud-1")
    assert not page_db.reply_defers("Yes: your reply to them is drafted and on Contacts.")


BUSY = r"""(() => {
  const c = document.querySelector('[data-work="talk~next"]');
  return c ? c.textContent.replace(/\s+/g, ' ') : null;
})()"""


def test_a_question_asked_while_claude_is_busy_says_next_after_it(run, tmp_path):
    from test_the_page_journeys import WIDE
    seed = dict(SEED)
    seed["chats/cloud-1"] = dict(SEED["chats/cloud-1"], busy="Answering your message about a reply")
    seed["meta/listener"] = dict(SEED["meta/listener"], answered_at="2026-10-25T08:30:00.000Z")
    seed["work/talk~next"] = {"args": {"thread": "t1", "message": "m2", "text": "is it there?"}, "_v": 2,
                              "kind": "talk", "status": "queued", "to": "cloud", "title": "Answer: “is it there?”",
                              "asked_at": "2026-10-25T08:59:00.000Z"}
    seed["meta/doorbell"] = {"ids": ["talk~next"], "rung_at": "2026-10-25T08:59:01.000Z", "listener": "cloud-1", "thread": ""}
    got = run("engine", html=_page(tmp_path), viewport=WIDE, steps=[{"hash": "todo", "eval": BUSY}],
              seed=seed, fake={"canSend": "available"}, clock=T)
    assert not got["errors"], got["errors"]
    text = got["after"][0]["eval"]
    assert text and "Next, after" in text and "Answering your message about a reply" in text, text
    assert "Starting in a moment" not in text, text


START = r"""(() => {
  const out = {};
  for (const id of ['network~read~late', 'network~read~fresh']) {
    const c = document.querySelector('[data-work="' + id + '"]');
    out[id] = c ? {text: c.textContent.replace(/\s+/g, ' '),
                   buttons: [...c.querySelectorAll('button')].map((b) => b.textContent.trim())} : null;
  }
  return out;
})()"""


def test_computer_work_past_its_window_offers_one_tap_and_promises_nothing(run, tmp_path):
    """Queued work for the computer whose start never came said "Claude starts it there when
    your computer is on", with no button, for hours: nothing re-checks it without a tap (the
    independent review, 2026-11-11, CC-5)."""
    from test_the_page_journeys import WIDE
    seed = dict(SEED)
    for wid, asked in (("network~read~late", "2026-10-25T08:30:00.000Z"),
                       ("network~read~fresh", "2026-10-25T08:58:00.000Z")):
        seed["work/" + wid] = {"args": {}, "asked_at": asked, "_v": 2, "kind": "network",
                               "status": "queued", "to": "computer", "asked_from": "t1",
                               "title": "Reading profiles on your computer"}
    steps = [{"hash": "todo", "eval": START},
             {"click": "Start it now: Reading profiles on your computer", "wait": 300,
              "calls": "comments"}]
    got = run("engine", html=_page(tmp_path), viewport=WIDE, steps=steps, seed=seed,
              fake={"canSend": "available"}, clock=T)
    assert not got["errors"], got["errors"]
    seen = got["after"][0]["eval"]
    late, fresh = seen["network~read~late"], seen["network~read~fresh"]
    assert late and "Start it now" in late["buttons"], late
    assert "has not started on your computer yet" in late["text"], late
    assert "when your computer is on" not in late["text"], late
    assert fresh and "Start it now" not in fresh["buttons"], fresh
    rings = [c for c in got["after"][1]["calls"] if c.get("cap") == "comments"]
    assert rings and any("network~read~late" in str(c) for c in rings), got["after"][1]["calls"]
