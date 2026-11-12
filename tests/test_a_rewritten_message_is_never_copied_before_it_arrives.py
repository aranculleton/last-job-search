"""A rewritten message is never copied before it arrives (#230).

From a real page: after a change was asked to a contact's draft, the card showed the draft
with its OLD wording, under it a spinner and "Finished · putting the new version on your
page", with Copy and "I sent it" live; Claude's work said "Putting on page · Finished 2 min
ago". Copy then copied the old message. Now, while the change has finished and its new words
are not on the card, the card and Claude's work both say the new version is on its way, and
the old words are not offered to copy or mark as sent. When the new words land, Copy is back,
on them. (The finish carries no new text, tools/page_db.py finish, so there is none to show
early.)

Every person and employer is invented (the page journeys' sample).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_cards_say_claudes_work_once_and_keep_every_answer_in_reach import JUNO, T, _tweak  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402

WID = "tweak~msg-juno-1~x"
NEW = "Hi Juno, Thursday at 12 is perfect. Looking forward to it."

CARD = ("(() => { const c = document.querySelector('[data-item=\"%s\"]'); if (!c) return null;"
        " const d = c.querySelector('.pdraft[data-msg=\"msg-juno-1\"]');"
        " const vis = (e) => !!e && e.getClientRects().length > 0 && !e.disabled;"
        " const w = document.querySelector('[data-work=\"%s\"]');"
        " return {done: (c.querySelector('.tweak-done') || {}).textContent || '',"
        " body: d ? d.textContent : '',"
        " copy: vis(d && d.querySelector('[data-k^=\"copy:msgt-\"]')),"
        " sent: vis(c.querySelector('[data-k=\"sent:msg-juno-1\"]')),"
        " work: w ? w.textContent.replace(/\\s+/g, ' ').trim() : null}; })()" % (JUNO, WID))
COPY = ("(() => { const c = document.querySelector('[data-item=\"%s\"]');"
        " const b = c && c.querySelector('.pdraft[data-msg=\"msg-juno-1\"] [data-k^=\"copy:msgt-\"]');"
        " if (b) b.click(); return !!b; })()" % JUNO)


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _landed():
    msgs = copy.deepcopy(journeys._sample()["messages"])
    for m in msgs:
        if m["id"] == "msg-juno-1":
            m.update(text=NEW, rev="m2")
    return {"view/messages": {"made_at": "2026-10-25T09:00:30Z", "data": msgs}}


def test_a_finished_change_not_on_the_card_offers_no_copy_of_the_old_words(run, tmp_path):
    seed = _tweak("done", rev="m1", summary="Her message now asks straight for the call.",
                  finished_at="2026-10-25T08:58:00.000Z")
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": CARD},
                              {"write": _landed(), "eval": CARD},
                              {"eval": COPY}, {"wait": 200}], WIDE, seed=seed, clock=T)
    before, after = got["after"][0]["eval"], got["after"][1]["eval"]
    assert before is not None, "her card is on Contacts"
    # On its way, never "Finished" over the old words.
    assert "Rewritten · the new version is on its way" in before["done"], before
    assert "Finished" not in before["done"] and "putting" not in before["done"], before
    # The old words are not offered to copy or mark as sent.
    assert not before["copy"] and not before["sent"], before
    # Claude's work says the same, not "Finished 2 min ago" or "Putting on page".
    if before["work"] is not None:
        assert "Finished" not in before["work"] and "Putting on page" not in before["work"], before
        assert "the new version is on its way" in before["work"], before
    # The new words land: Copy and I sent it are back, on them.
    assert NEW in after["body"], after
    assert after["copy"] and after["sent"], after
    assert "on its way" not in after["done"], after
    copied = [c for c in got.get("clipboard") or [] if c]
    if copied:
        assert copied[-1] == NEW, copied


def test_the_work_card_says_the_new_version_is_on_its_way(run, tmp_path):
    seed = _tweak("done", rev="m1", summary="Her message now asks straight for the call.",
                  finished_at="2026-10-25T08:58:00.000Z")
    label = "(document.querySelector('[data-work=\"%s\"] .state-word') || {}).textContent || ''" % WID
    now1 = "(document.querySelector('[data-work=\"%s\"] .wc-now') || {}).textContent || ''" % WID
    tm = "(document.querySelector('[data-work=\"%s\"] .wc-time') || {}).textContent || ''" % WID
    got = _go(run, tmp_path, [{"hash": "todo", "eval": label}, {"eval": now1}, {"eval": tm}], WIDE,
              seed=seed, clock=T)
    word, line, time = (got["after"][i]["eval"] for i in range(3))
    assert word == "On its way", word
    assert line == "Rewritten · the new version is on its way.", line
    assert "Finished" not in time, time
