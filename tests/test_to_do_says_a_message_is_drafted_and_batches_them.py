"""To do says a message is drafted, opens it, and puts several drafted ones on one card.

From the maintainer's own page (2026-11-04):
- Follow-ups drafted sat in To do as "Follow up with ..." with nothing saying a draft was
  ready, so the person tapped Follow up again and nineteen were queued a second time. A row
  whose message is drafted says "Draft ready" and its one button opens the draft; a second
  tap never queues drafting again.
- An application's follow-up drafted in Messages was never found from its own To do row: the
  row names the application and the message is its own.
- Six drafted messages were six cards ("same with to do, batch would be easier to read"):
  two or more are one card, "N messages ready to send", a row a person opening their draft,
  and one button that opens Messages. One alone keeps its own card. A row sent leaves at once.

Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import copy
import os
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
# In the sample both Wren's follow-up and Juno's reply are drafted and owed today or earlier.
GROUP = '[data-item="grp:drafted:now"]'
ROWS = ("[...document.querySelectorAll('" + GROUP.replace("'", "\\'") + " .g-row')].map((li) => [li.dataset.item, "
        "li.querySelector('.g-name').textContent, li.querySelector('.muted') ? li.querySelector('.muted').textContent : '', "
        "[...li.querySelectorAll('.g-acts .btn')].map((b) => b.textContent.trim()).filter(Boolean)])")
NO_WORK = ("follow_up", "nudge", "reply")


def _no_drafting(got):
    assert not [w for w in got["work"] if w and w.get("kind") in NO_WORK], got["work"]


def test_two_drafted_messages_are_one_card_whose_rows_open_each_draft(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": GROUP, "eval": ROWS},
        {"eval": "document.querySelectorAll('#main .due-row[data-item=\"due-fernhill-nudge\"], #main .due-row[data-item=\"due-juno-reply\"]').length"},
        {"click": "See the draft", "within": '[data-item="due-juno-reply"]', "until": "location.hash === '#drafts-messages/msg-juno-1'"},
        {"hash": "todo", "click": "Open Messages", "within": GROUP, "until": "location.hash.startsWith('#drafts-messages')"},
    ], vp, clock=T)
    card = got["after"][0]["text"]
    assert "2 messages ready to send" in card, card
    rows = got["after"][0]["eval"]
    assert [r[0] for r in rows] == ["due-fernhill-nudge", "due-juno-reply"], rows
    assert rows[0][1] == "Wren at Fernhill Freight" and rows[1][1] == "Juno at Larkspur Retail", rows
    assert all(r[3] and r[3][0] == "See the draft" for r in rows), rows
    assert "Draft all" not in card and "Draft the follow-up" not in card and "Draft a reply" not in card, card
    assert got["after"][1]["eval"] == 0, "no drafted message is a card of its own while two are drafted"
    assert got["after"][2]["hash"] == "#drafts-messages/msg-juno-1"
    assert got["after"][3]["hash"].startswith("#drafts-messages")
    _no_drafting(got)


def test_one_drafted_message_keeps_its_card_says_draft_ready_and_opens_it(run, tmp_path, vp):
    m = copy.deepcopy(_sample())
    m["messages"] = [x for x in m["messages"] if x["id"] != "msg-juno-1"]
    row = '[data-item="due-fernhill-nudge"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": row, "count": GROUP,
         "eval": "[...document.querySelectorAll('#main .due-row[data-item=\"due-fernhill-nudge\"] .todo-top .chip')].map((c) => c.textContent)"},
        {"click": "See the draft", "within": row, "until": "location.hash === '#drafts-messages/msg-wren-2'"},
        {"hash": "todo", "click": "See the draft", "within": row, "until": "location.hash === '#drafts-messages/msg-wren-2'"},
    ], vp, model=m, clock=T)
    assert got["after"][0]["count"] == 0, "one alone is not a batch"
    assert "Draft ready" in got["after"][0]["eval"], got["after"][0]["eval"]
    assert "See the draft" in got["after"][0]["text"] and "Draft the follow-up" not in got["after"][0]["text"]
    assert got["after"][2]["hash"] == "#drafts-messages/msg-wren-2", "a second tap opens it again"
    _no_drafting(got)


def test_an_applications_follow_up_drafted_opens_from_its_own_row(run, tmp_path, vp):
    m = copy.deepcopy(_sample())
    wren = next(x for x in m["messages"] if x["id"] == "msg-wren-2")
    body = ("Dear Hiring Team, I applied for the Operations Analyst role on 6 October and wanted to "
            "ask whether there is any news. I am still very interested in it.")
    m["messages"].append(dict(copy.deepcopy(wren), id="msg-app-quayside-ops", contact="", first_name="the employer",
                              employer="Quayside Foods", application="app-quayside-ops", kind="follow_up", type="follow_up",
                              text=body, body=body, chars=len(body), due="2026-10-28", rev="m9", related={}))
    due = next(d for d in m["due"] if d["id"] == "due-quayside-ops-follow")
    # The engine's own shape: the row names the application, and its work carries it.
    due.update(item="app-quayside-ops", sub="follow_up", company="Quayside Foods",
               work={"kind": "follow_up", "id": "follow_up~app-quayside-ops",
                     "args": {"application": "app-quayside-ops", "company": "Quayside Foods", "role": "Operations Analyst"}})
    due.pop("application", None)
    row = '[data-item="due-quayside-ops-follow"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": row},
        {"click": "See the draft", "within": row, "until": "location.hash === '#drafts-messages/msg-app-quayside-ops'"},
    ], vp, model=m, clock=T)
    text = got["after"][0]["text"]
    assert "Draft ready" in text and "See the draft" in text and "Draft the follow-up" not in text, text
    assert got["after"][1]["hash"] == "#drafts-messages/msg-app-quayside-ops"
    _no_drafting(got)


def test_a_drafted_message_sent_leaves_the_batch_at_once(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "drafts-messages", "click": "Copy", "within": '[data-item="msg-wren-2"]'},
        {"click": "I sent it", "within": '[data-item="msg-wren-2"]'},
        {"hash": "todo", "count": GROUP, "eval": "document.querySelectorAll('#main [data-item=\"due-fernhill-nudge\"]').length"},
        {"read": '[data-item="due-juno-reply"]'},
    ], vp, clock=T)
    assert got["after"][2]["count"] == 0 and got["after"][2]["eval"] == 0, got["after"][2]
    assert "See the draft" in got["after"][3]["text"], "the one left keeps its own card"
