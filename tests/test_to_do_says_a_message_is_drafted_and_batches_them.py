"""To do puts every message drafted and waiting on one card, and opens each one's draft.

From the maintainer's own page (2026-11-04) and the UX review (2026-11-05):
- Follow-ups drafted sat in To do as "Follow up with ..." with nothing saying a draft was
  ready, so the person tapped Follow up again and nineteen were queued a second time. A row
  whose message is drafted opens the draft; a second tap never queues drafting again.
- An application's follow-up drafted (in Messages, then) was never found from its own To do
  row: the row names the application and the message is its own.
- Drafted messages, the week's first notes and "messages to check before you send" were three
  cards saying one thing, and their counts disagreed with Contacts' "N to send". They are one
  card, "Messages to send (N)": a row a person opening their draft, a flagged one saying
  "Check first", one button opening Contacts, and N the engine's one count (model.to_send),
  the number Contacts says too. A row sent leaves at once, the card's "x of N done" moving.

Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import copy
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param


T = "2026-10-25T09:00:00Z"
CARD = '[data-item="grp:send"]'
ROWS = ("[...document.querySelectorAll('" + CARD.replace("'", "\\'") + " .g-row')].map((li) => [li.dataset.item, "
        "li.querySelector('.g-name').textContent, li.querySelector('.muted') ? li.querySelector('.muted').textContent : '', "
        "[...li.querySelectorAll('.g-acts .btn')].map((b) => b.textContent.trim()).filter(Boolean)])")
TITLE = "(document.querySelector('" + CARD + " .card-title') || {}).textContent || ''"
DONE = "(document.querySelector('" + CARD + " [data-k^=\"grp-done:\"]') || {}).textContent || ''"
CONTACTS_SUM = "(document.querySelector('#main .sec-head .sum') || {}).textContent || ''"
NO_WORK = ("follow_up", "nudge", "reply")


def _no_drafting(got):
    assert not [w for w in got["work"] if w and w.get("kind") in NO_WORK], got["work"]


def _n(title):
    m = re.search(r"Messages to send \((\d+)\)", title)
    return int(m.group(1)) if m else None


def test_every_drafted_message_is_one_card_whose_rows_open_each_draft(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": CARD, "eval": ROWS},
        {"eval": "document.querySelectorAll('#main .due-row[data-item=\"due-fernhill-nudge\"], #main .due-row[data-item=\"due-juno-reply\"]').length"},
        {"click": "See the draft", "within": CARD + ' [data-item="due-juno-reply"]', "until": "location.hash === '#contacts/larkspur_retail_castellan'",
         "eval": "!!document.querySelector('#main [data-item=\"larkspur_retail_castellan\"] details.pdraft[open]')"},
        {"hash": "todo", "click": "Open Contacts", "within": CARD, "until": "location.hash.startsWith('#contacts')",
         "eval": "document.querySelector('#main ul.people > li').dataset.item"},
    ], vp, clock=T)
    card = got["after"][0]["text"]
    assert "Messages to send (7)" in card, card
    rows = got["after"][0]["eval"]
    # A row a person, in the engine's order: the replies and follow-ups owed, then the notes.
    assert [r[0] for r in rows] == ["due-juno-reply", "due-fernhill-nudge", "msg-ash-1", "msg-kit-1", "msg-rafe-1",
                                    "msg-noor-1", "msg-priya-thanks"], rows
    assert rows[0][1].startswith("Juno at Larkspur Retail") and rows[1][1].startswith("Wren at Fernhill Freight"), rows
    assert all(r[3] and r[3][0] in ("See the draft", "See the note") for r in rows), rows
    assert "Draft all" not in card and "Draft the follow-up" not in card and "Draft a reply" not in card, card
    # The drafted rows, the wave of first notes and the ones to check are this one card.
    text = got["after"][1]["text"]
    assert got["after"][1]["eval"] == 0, "no drafted message is a card of its own"
    assert "first notes ready to send" not in text and "to check before you send" not in text, text
    # Her draft opens on her card in Contacts; the card's button opens Contacts on the first.
    assert got["after"][2]["hash"] == "#contacts/larkspur_retail_castellan" and got["after"][2]["eval"] is True, got["after"][2]
    assert got["after"][3]["hash"].startswith("#contacts"), got["after"][3]["hash"]
    _no_drafting(got)


def test_the_card_and_contacts_say_the_engines_one_count_and_a_message_sent_leaves_both(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": TITLE},
        {"hash": "contacts", "eval": CONTACTS_SUM},
        {"click": "Copy", "within": '[data-item="fernhill_freight_halloway"]'},
        {"click": "I sent it", "within": '[data-item="fernhill_freight_halloway"]', "eval": CONTACTS_SUM},
        {"hash": "todo", "count": CARD + ' [data-item="due-fernhill-nudge"]', "eval": "[" + TITLE + ", " + DONE + "]"},
    ], vp, clock=T)
    m = _sample()
    n = m["to_send"]["n"]
    assert _n(got["after"][0]["eval"]) == n, got["after"][0]["eval"]
    assert got["after"][1]["eval"].startswith(f"{n} to send"), got["after"][1]["eval"]
    # Sent: it leaves the card at once, and both screens count one fewer.
    assert got["after"][3]["eval"].startswith(f"{n - 1} to send"), got["after"][3]["eval"]
    title, done = got["after"][4]["eval"]
    assert got["after"][4]["count"] == 0, "the row sent leaves at once"
    assert _n(title) == n - 1 and done == f"1 of {n} done", (title, done)


def test_one_drafted_message_is_the_same_card_with_its_one_row(run, tmp_path, vp):
    m = copy.deepcopy(_sample())
    m["messages"] = [x for x in m["messages"] if x["id"] == "msg-wren-2"]
    m["to_send"] = {"n": 1, "ids": ["msg-wren-2"]}
    row = CARD + ' [data-item="due-fernhill-nudge"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": CARD, "count": '#main .due-row[data-item="due-fernhill-nudge"]'},
        {"click": "See the draft", "within": row, "until": "location.hash === '#contacts/fernhill_freight_halloway'"},
        {"hash": "todo", "click": "See the draft", "within": row, "until": "location.hash === '#contacts/fernhill_freight_halloway'"},
    ], vp, model=m, clock=T)
    assert got["after"][0]["count"] == 0, "one alone is a row of the same card, never a card of its own"
    assert "Messages to send (1)" in got["after"][0]["text"] and "Draft the follow-up" not in got["after"][0]["text"]
    assert got["after"][2]["hash"] == "#contacts/fernhill_freight_halloway", "a second tap opens it again"
    _no_drafting(got)


def test_an_applications_follow_up_drafted_opens_from_its_own_row(run, tmp_path, vp):
    m = copy.deepcopy(_sample())
    wren = next(x for x in m["messages"] if x["id"] == "msg-wren-2")
    body = ("Dear Hiring Team, I applied for the Operations Analyst role on 6 October and wanted to "
            "ask whether there is any news. I am still very interested in it.")
    m["messages"].append(dict(copy.deepcopy(wren), id="msg-app-quayside-ops", contact="", first_name="the employer",
                              employer="Quayside Foods", application="app-quayside-ops", kind="follow_up", type="follow_up",
                              text=body, body=body, chars=len(body), due="2026-10-28", rev="m9", related={}))
    # Two on the card, so its row is among the first shown.
    m["messages"] = [wren, m["messages"][-1]]
    m["to_send"] = {"n": 2, "ids": [x["id"] for x in m["messages"]]}
    due = next(d for d in m["due"] if d["id"] == "due-quayside-ops-follow")
    # The engine's own shape: the row names the application, and its work carries it.
    due.update(item="app-quayside-ops", sub="follow_up", company="Quayside Foods",
               work={"kind": "follow_up", "id": "follow_up~app-quayside-ops",
                     "args": {"application": "app-quayside-ops", "company": "Quayside Foods", "role": "Operations Analyst"}})
    due.pop("application", None)
    row = CARD + ' [data-item="due-quayside-ops-follow"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": row},
        # Nobody on the list carries it: its own card in Contacts.
        {"click": "See the draft", "within": row, "until": "location.hash === '#contacts/msg-app-quayside-ops'",
         "eval": "!!document.querySelector('#main [data-item=\"msg-app-quayside-ops\"] details.pdraft[open]')"},
    ], vp, model=m, clock=T)
    text = got["after"][0]["text"]
    assert "See the draft" in text and "Draft the follow-up" not in text, text
    assert got["after"][1]["hash"] == "#contacts/msg-app-quayside-ops" and got["after"][1]["eval"] is True, got["after"][1]
    _no_drafting(got)


def test_a_row_to_check_says_so_and_one_claude_is_fixing_says_that(run, tmp_path):
    m = copy.deepcopy(_sample())
    ash = next(x for x in m["messages"] if x["id"] == "msg-ash-1")
    ash["alerts"] = [{"level": 1, "id": "al-read_first-msg-ash-1", "kind": "read_first", "text": "Written before their profile was read: read it first.",
                      "why": "A note written before their profile was read can get them wrong.", "action": None, "cost": None}]
    kit = next(x for x in m["messages"] if x["id"] == "msg-kit-1")
    kit["fix"] = {"work": "tweak~msg-kit-1~fix~0a1b2c3d4e", "reasons": ["it is longer than this kind of message may be"], "must": True}
    row = lambda mid: "(document.querySelector('" + CARD + " [data-item=\"" + mid + "\"]') || {}).textContent || ''"  # noqa: E731
    got = _go(run, tmp_path, [{"hash": "todo", "eval": "[" + row("msg-ash-1") + ", " + row("msg-kit-1") + "]"}], WIDE, model=m, clock=T)
    ash_row, kit_row = got["after"][0]["eval"]
    assert "Check first" in ash_row and "Written before their profile was read" in ash_row, ash_row
    assert "Claude is fixing it" in kit_row and "longer than this kind of message" in kit_row, kit_row
    assert "Shorten it" not in got["after"][0]["text"], "no fix button on To do"
