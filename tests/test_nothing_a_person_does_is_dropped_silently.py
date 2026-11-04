"""Nothing a person does on the page is dropped without a word, and every action keeps its contract.

Two classes of failure from the 3 November audit, checked for every case rather than the ones
found:

- A silent drop: a chat message, a paste, a tap or a sheet that tried to save and went nowhere,
  with the page saying "Saved" or nothing at all. Every control on every screen is tapped (its
  sheet filled and sent where it opens one) with a store that refuses every write, and every
  one that tried to write must say so where the person is looking. The chat's own three ways
  in (a message, a long paste, a screenshot) are run both ways: refused, they say so; accepted,
  what was written is in the store.
- The page and the engine disagreeing about an action: for every action the page can send,
  the engine answers a stale or missing item with a receipt in plain words, never nothing and
  never a raw id; and the page reads every receipt state as that state (Saved, taken by a chat,
  Done, Not done, Not saved), whatever the action.

Every person and employer is invented (the page's sample and tests/app_state.py).
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_actions  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402
from test_the_page_works_in_a_browser import PHONE, _sample, _write, pages, run  # noqa: E402

_ = (pages, run)   # the fixtures, used by name

APP_JS = os.path.join(ROOT, "templates", "app", "app.js")
T0 = "2026-10-25T09:00:00Z"


def _sent_by_the_page() -> list:
    with open(APP_JS, encoding="utf-8") as fh:
        js = fh.read()
    sent = set(re.findall(r'action: "([a-z_]+\.[a-z_]+)"', js))
    sent |= {"outcome." + k for k in re.findall(r'heard\("([a-z_]+)"', js)}
    return sorted(sent & set(app_actions.ACTIONS))


# ------------------------------------------------------------------ every control, with the store refusing


@pytest.mark.parametrize("section", ["todo", "jobs", "drafts", "drafts-messages", "contacts", "interviews", "settings", "brief"])
def test_every_control_that_tries_to_save_says_so_when_it_cannot(run, pages, section):
    got = run("silent", html=pages["sample"], viewport=PHONE, clock=T0, sections=[section], _wait=900)
    assert got["tapped"] > 0
    assert got["silent"] == [], "tried to save, failed, and said nothing: %s" % got["silent"]


def test_the_check_reaches_writes_on_the_screens_that_make_them(run, pages):
    # The check above is only worth something if its taps really write: on To do and Jobs
    # they do.
    got = run("silent", html=pages["sample"], viewport=PHONE, clock=T0, sections=["todo", "jobs"], limit=40, _wait=900)
    assert len(got["wrote"]) >= 3, got["wrote"]


# ------------------------------------------------------------------ the chat's own ways in


CHAT = [
    ("a message", [{"type": ["#talk-text", "Please look at the Harbourline Bank role for me."]}]),
    ("a long paste", [{"type": ["#talk-text", "Hi Morgan, thanks for getting in touch. We would like to invite you to a phone screen for the "
                                               "Pricing Analyst role next week. " + ("Some more of their message, pasted whole. " * 120).strip()]}]),
    ("a request for work", [{"type": ["#talk-text", "Please find me ten more roles like the Harbourline Bank one."]}]),
    ("a screenshot", [{"pastePic": True}, {"type": ["#talk-text", "Help me reply to this"]}]),
]


@pytest.mark.parametrize("what,steps", CHAT, ids=[c[0] for c in CHAT])
def test_what_is_sent_in_chat_is_stored_or_said_to_have_failed(run, tmp_path, what, steps):
    html = _write(tmp_path, "chat", _sample())
    send = {"send": "[data-k=talk-send]", "run": 2000}
    ok = run("script", html=html, clock=T0, hash="chat", fake={"canSend": "available"}, steps=steps + [send])
    assert not ok["errors"], ok["errors"]
    last = ok["steps"][-1]
    wrote = [c for c in last["calls"] if c["cap"] == "db" and c["op"] in ("set", "update") and not c["failed"]]
    assert last["talk"] or last["work"] or wrote, "%s: nothing was stored" % what
    refused = run("script", html=html, clock=T0, hash="chat", fake={"canSend": "available", "failWrites": True}, steps=steps + [send])
    assert not refused["errors"], refused["errors"]
    r = refused["steps"][-1]
    tried = [c for c in r["calls"] if c["cap"] == "db" and c["failed"]]
    assert tried, "%s: the page tried to save it" % what
    assert r["visibleError"], "%s: the store refused it and the page said nothing" % what


# ------------------------------------------------------------------ every action: the engine's receipt


def test_every_action_the_page_sends_has_a_plain_receipt_for_an_item_that_is_gone(tmp_path):
    kinds = _sent_by_the_page()
    assert len(kinds) >= 30, kinds
    s = Search(str(tmp_path / "s"))
    ids = {}
    for k in kinds:
        ids[k] = s.act(k, "no-such-item-" + k.replace(".", "-"), value={}, rev="r-old")
    s.apply()
    bad = {}
    for k, aid in ids.items():
        try:
            rec = s.receipt(aid)
        except OSError:
            bad[k] = "no receipt at all"
            continue
        note = str(rec.get("note") or "")
        if rec.get("result") not in ("ok", "stale", "conflict"):
            bad[k] = rec.get("result")
        elif not note.strip():
            bad[k] = "an empty note"
        elif re.search(r"act\d+|no-such-item|Traceback|\bNone\b|\{|\}", note):
            bad[k] = note
    assert bad == {}, bad


# ------------------------------------------------------------------ every action: the page reads every receipt state


STATES = [("no receipt yet", None, None, "saved"),
          ("taken by a chat", None, {"claimed_by": "cloud-1", "claimed_until": "2099-01-01T00:00:00Z"}, "claimed"),
          ("applied", {"result": "ok", "note": "Done."}, None, "applied"),
          ("refused as stale", {"result": "stale", "note": "It changed since you saw it: look again."}, None, "refused"),
          ("refused", {"result": "conflict", "note": "That cannot be done to that."}, None, "refused")]


def test_the_page_reads_every_receipt_state_for_every_action(run, tmp_path):
    html = _write(tmp_path, "states", _sample())
    kinds = _sent_by_the_page()
    seed, want = {}, {}
    for k in kinds:
        for n, (_name, receipt, extra, state) in enumerate(STATES):
            aid = "act~contract-%s~%s~%d" % (k.replace(".", "-"), k, n)
            seed["actions/" + aid] = dict({"item": "contract-" + k, "action": k, "value": {}, "at": "2026-10-25T08:%02d:00Z" % n,
                                           "rev_seen": "r", "tab": "t0"}, **(extra or {}))
            if receipt:
                seed["receipts/" + aid] = dict(receipt, applied_at="2026-10-25T08:%02d:30Z" % n, by="cloud-1")
            want[aid] = state
    got = run("script", html=html, clock=T0, seed=seed, steps=[{"eval": "(%s).map((id) => [id, LJS.receiptState(id)])" % json.dumps(sorted(want))}])
    assert not got["errors"], got["errors"]
    read = dict(got["steps"][-1]["eval"])
    wrong = {aid: (read.get(aid), want[aid]) for aid in want if read.get(aid) != want[aid]}
    assert wrong == {}, wrong
