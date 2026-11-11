"""A person's card follows what was done to the message to them, even where their record lags.

The maintainer, 2026-11-11, two cards on his own page. One: "I sent it" pressed on a follow-up,
and the card still said "Follow-up ready", "Next: Your follow-up is written: send it · You
wrote" the day of the message before, with no draft on it. The tap had reached the page's store
and a chat had applied it, so the message had left the engine's list, but the person's own
record was still the one drawn before (`app.py view` keeps a section another chat drew from a
copy with work not landed yet), and the page read the message's absence as nothing sent.
Two: a follow-up a chat put on hold (the conversation had moved to a colleague there) sat in
the main list with its draft open and "Waiting for a reply", the hold's line under it, though
held people are a folded group at the foot of Contacts: the list's messages were drawn after
the hold, the person's record before it.

On the page itself, with the store as a reload finds it (the tap and its receipt kept, the
message gone or held): the card says what was done, and an old tap never overrides a record
that has caught up. Every person and employer is invented (the sample search).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

WREN = "fernhill_freight_halloway"
MSG = "msg-wren-2"
CLOCK = "2026-10-26T09:00:00Z"
HOLD = "On hold: Wren's follow-up is off the list. Claude checks again on Fri 11 Dec."


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


def _record_from_before(m):
    """Wren as the record drawn before the follow-up went: a follow-up owed and late."""
    wren = next(p for p in m["people"] if p["id"] == WREN)
    wren.update(group="follow", late=2, owed={"kind": "draft", "label": "See the draft", "message": MSG, "reply": False},
                next="Your follow-up is written: send it", last="2026-09-21",
                exchange={"first": "you", "first_on": "2026-09-21", "last": "you", "last_on": "2026-09-21",
                          "in": 0, "out": 1, "replied": False})
    return wren


def _sent_and_applied(day="2026-10-26"):
    """The store as a reload finds it: "I sent it" on the follow-up, and a chat's receipt."""
    tap = "act~" + MSG + "~msg.sent~t1"
    return {"actions/" + tap: {"action": "msg.sent", "item": MSG, "at": day + "T08:40:00.000Z", "rev_seen": "m2",
                               "tab": "t-old", "value": {"on": day, "kind": "follow_up", "channel": "linkedin_message",
                                                         "text": "Hi Wren, a quick follow-up on my note last month."}},
            "receipts/" + tap: {"action": "msg.sent", "item": MSG, "applied_at": day + "T08:45:00Z", "result": "ok",
                                "note": "Logged as sent to Wren."}}


CARD = r"""(() => {
  const e = document.querySelector('#main [data-item="fernhill_freight_halloway"]');
  if (!e) return null;
  return {state: (e.querySelector('.state-word') || {textContent: ''}).textContent.trim(),
    line: (e.querySelector('p.meta') || {textContent: ''}).textContent.replace(/\s+/g, ' ').trim(),
    held: !!e.closest('ul[data-held-list]'),
    main: !!e.closest('ul.people:not([data-held-list])'),
    draftOpen: e.querySelector('details.pdraft') ? e.querySelector('details.pdraft').open : null,
    fold: (document.querySelector('#main [data-on-hold]') || {textContent: ''}).textContent.replace(/\s+/g, ' ').trim()};
})()"""
READY = "!!document.querySelector('#main [data-item=\"fernhill_freight_halloway\"]')"
# Looked up by name, as the person would: someone waiting on a reply is below the fold.
FIND = r"""(() => { const i = document.querySelector('#main input[data-k="q:contacts"]');
  if (i) { i.value = 'wren'; i.dispatchEvent(new Event('input', {bubbles: true})); } return !!i; })()"""


def test_a_follow_up_marked_sent_stays_sent_after_its_message_has_left_the_list(run, tmp_path, vp):
    m = journeys._sample()
    _record_from_before(m)
    m["messages"] = [x for x in m["messages"] if x["id"] != MSG]
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": FIND}, {"ready": READY, "eval": CARD}], vp, model=m,
              seed=_sent_and_applied(), clock=CLOCK)
    card = got["after"][1]["eval"]
    assert card["state"] == "Message sent", card
    assert card["line"] == "Sent. Nothing to do until they write back.", card
    assert "Follow-up ready" not in card["state"] and "send it" not in card["line"], card
    # Their own page says the same: sent, and no "Next: ... send it" from the record before.
    got = _go(run, tmp_path, [{"hash": "contacts/fernhill_freight_halloway/open",
                               "ready": "!!document.querySelector('.d-person')",
                               "eval": "document.querySelector('.d-person').innerText"}], vp, model=m,
              seed=_sent_and_applied(), clock=CLOCK)
    detail = got["after"][0]["eval"]
    assert "Message sent" in detail and "send it" not in detail, detail[:600]
    # Its To do row has gone with it: the follow-up is not asked for again.
    got = _go(run, tmp_path, [{"hash": "todo", "eval": "document.querySelector('#main').innerText"}], vp,
              model=m, seed=_sent_and_applied(), clock=CLOCK)
    assert "Follow up with Wren" not in got["after"][0]["eval"], got["after"][0]["eval"][:600]


def test_an_old_tap_never_overrides_a_record_that_has_caught_up(run, tmp_path):
    m = journeys._sample()
    wren = _record_from_before(m)
    m["messages"] = [x for x in m["messages"] if x["id"] != MSG]
    # The record now knows the follow-up and their answer to it, written after it.
    wren.update(group="now", late=0, owed={"kind": "reply", "label": "Draft a reply"}, next="Reply to Wren",
                last="2026-10-25", status="replied_needs_response",
                exchange={"first": "you", "first_on": "2026-09-21", "last": "them", "last_on": "2026-10-25",
                          "in": 1, "out": 2, "replied": True})
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": FIND}, {"ready": READY, "eval": CARD}], WIDE, model=m,
              seed=_sent_and_applied("2026-10-24"), clock=CLOCK)
    card = got["after"][1]["eval"]
    assert card["state"] != "Message sent" and "They replied 25 Oct" in card["line"], card


def test_a_follow_up_held_before_its_record_knows_is_with_the_held(run, tmp_path, vp):
    m = journeys._sample()
    _record_from_before(m)
    msg = next(x for x in m["messages"] if x["id"] == MSG)
    msg.update(hold=HOLD, hold_why="person_hold", due="2026-12-11")
    m["people_count"] = dict(m.get("people_count") or {}, on_hold={"n": 1, "why": None})
    got = _go(run, tmp_path, [
        {"hash": "contacts", "ready": "!!document.querySelector('#main [data-on-hold]')", "eval": CARD},
        {"open": "held:contacts", "ready": "!!document.querySelector('#main ul[data-held-list]')", "eval": CARD},
    ], vp, model=m, clock=CLOCK)
    folded, shown = got["after"][0]["eval"], got["after"][1]["eval"]
    # Not in the main list with its draft open: in the folded group at the foot.
    assert folded is None or not folded["main"], folded
    shown_fold = copy.deepcopy(shown)
    assert shown_fold["held"] and not shown_fold["main"], shown
    assert shown["state"] == "On hold" and shown["line"] == HOLD, shown
    assert shown["draftOpen"] is False, shown
