"""A tired person reads each thing once, and finishing one takes one tap (2026-11-03).

A walk through the page found the same thing said several ways and the same thing done two
ways: a sent message left standing with "Saved. Undo" under a toast with its own Undo, a row
of a checklist with Draft, Not now and a bin, a LinkedIn card with three equal buttons for
three steps done in order, two rows in Settings for one choice, and Coming up beside
Settings in the side menu while Chat sat with the main places. Each test taps the page as a
person would. Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _one, _sample  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


T = "2026-10-25T09:00:00Z"
TOASTS = "[...document.querySelectorAll('[data-toast]')].map((t) => t.textContent).join(' | ')"


def test_the_side_menu_has_coming_up_with_the_places_and_settings_alone_at_its_foot(run, tmp_path):
    side = ("(() => ({main: [...document.querySelectorAll('#side .side-list:not(.side-foot) .side-label')].map((e) => e.textContent), "
            "foot: [...document.querySelectorAll('#side .side-foot .side-label')].map((e) => e.textContent)}))()")
    tabs = "[...document.querySelectorAll('#tabs .tab-label')].map((e) => e.textContent)"
    wide = _go(run, tmp_path, [{"hash": "todo", "eval": side}], WIDE, clock=T)["after"][0]["eval"]
    assert wide == {"main": ["Brief", "To do", "Jobs", "Contacts", "Coming up", "Chat"], "foot": ["Settings"]}, wide
    phone = _go(run, tmp_path, [{"hash": "todo", "eval": tabs}], PHONE, clock=T)["after"][0]["eval"]
    assert phone == ["Brief", "To do", "Jobs", "Contacts", "Chat"], ("five places at most on a phone", phone)


def test_a_message_marked_sent_leaves_its_card_with_its_one_undo_in_the_toast(run, tmp_path):
    # Juno's reply is on her card in Contacts (one page since 2026-11-04): sent, the draft and
    # her card leave the list's top at once.
    card = "!!document.querySelector('#main [data-item=\"larkspur_retail_castellan\"] details.pdraft')"
    got = _go(run, tmp_path, [
        {"hash": "contacts", "eval": card},
        {"click": "I sent it: the message to Juno", "eval": "[" + card + ", " + TOASTS + ", document.querySelectorAll('#main button.undo').length]"},
    ], PHONE, clock=T)
    assert got["after"][0]["eval"] is True
    gone, toast, undos = got["after"][1]["eval"]
    assert not gone, "the card leaves the list at once"
    assert "Undo" in toast and undos == 0, ("one Undo, in the toast", toast, undos)
    assert "Saved. Claude will pick this up." not in got["after"][1]["text"]
    assert _one(got, "msg.sent")["item"] == "msg-juno-1"


def test_a_question_answered_in_to_do_leaves_it_with_its_undo_in_the_toast(run, tmp_path):
    q = "!!document.querySelector('#main [data-item=\"q-larkspur-data-looker\"]')"
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": q},
        {"click": "Yes, I have", "eval": "[" + q + ", " + TOASTS + "]"},
        {"click": "Undo", "exact": True, "within": "#toasts", "ready": q, "eval": q},
    ], PHONE, clock=T)
    assert got["after"][0]["eval"] is True
    there, toast = got["after"][1]["eval"]
    assert not there and "Undo" in toast, (there, toast)
    assert got["after"][2]["eval"] is True, "Undo brings the question back"
    assert not got["actions"], "and nothing is left for Claude to do"


def _two_follow_ups():
    m = _sample()
    nudge = next(d for d in m["due"] if d["kind"] == "nudge")
    ppl = [p for p in m["people"] if p["status"] != "closed" and not any(x.get("contact") == p["id"] for x in m["messages"])][:2]
    m["due"] = [d for d in m["due"] if d["kind"] != "nudge"] + [
        dict(nudge, id="due-nudge-%s" % p["id"], contact=p["id"], item=None, title="Follow up with %s at %s" % (p["first_name"], p["employer"]),
             context="Analyst at %s" % p["employer"], work={"kind": "follow_up", "id": "follow_up~%s" % p["id"], "args": {"contact": p["id"]}},
             rev="tn%d" % i) for i, p in enumerate(ppl)]
    return m, ppl


def test_a_checklist_row_is_put_off_from_its_bin_and_has_no_not_now(run, tmp_path):
    """Its bin puts it off to a day in the engine, Tomorrow and Next week first, on every
    device: hiding it on this device alone left it due everywhere else (the UX review,
    2026-11-05, A7)."""
    m, ppl = _two_follow_ups()
    row = "!!document.querySelector('#main .group-card [data-item=\"due-nudge-%s\"]')" % ppl[0]["id"]
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": "[" + row + ", [...document.querySelectorAll('#main .group-card .g-row button')].map((b) => b.textContent)]"},
        {"open": "fgbin:todo:due-nudge-%s" % ppl[0]["id"], "read": "dialog[open]"},
        {"click": "Tomorrow", "exact": True, "within": "dialog", "eval": row},
    ], PHONE, model=m, clock=T)
    there, buttons = got["after"][0]["eval"]
    assert there and "Not now" not in buttons, buttons
    assert "Tomorrow" in got["after"][1]["text"] and "Hide this for a week" not in got["after"][1]["text"], got["after"][1]["text"]
    assert not got["after"][2]["eval"], "it leaves the card at once"
    a = [x for x in got["actions"] if x["action"] == "due.snooze"]
    assert a and a[-1]["item"] == "due-nudge-%s" % ppl[0]["id"] and a[-1]["value"] == {"until": "2026-10-26"}, got["actions"]


def test_the_linkedin_card_offers_one_button_at_a_time_in_the_order_they_are_done(run, tmp_path):
    btns = "[...document.querySelectorAll('#main [data-item=\"linkedin-export\"] .card-actions .btn')].map((b) => b.textContent.replace(' (opens in a new tab)', '').trim())"
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": btns},
        {"open": "export-open", "wait": 400, "eval": btns},
        {"click": "I've asked for it", "eval": btns},
    ], PHONE, clock=T)
    assert [x["eval"] for x in got["after"]] == [["Open LinkedIn's download page"], ["I've asked for it"], ["Add the download"]], [x["eval"] for x in got["after"]]
    assert _one(got, "export.requested")


def test_reading_linkedin_profiles_is_one_row_in_settings(run, tmp_path):
    m = _sample()
    m["settings"] = m["settings"] + [{"id": "setting-profile_reads", "key": "profile_reads", "label": "Reading LinkedIn profiles", "kind": "choice",
                                      "value": "browser", "choices": [["browser", "Claude reads them"], ["paste", "I paste them"]], "rev": "pr1"}]
    names = "[...document.querySelectorAll('#main .set-name')].map((e) => e.textContent)"
    got = _go(run, tmp_path, [{"hash": "settings", "eval": names}], PHONE, model=m, clock=T)
    rows = got["after"][0]["eval"]
    assert "Let Claude read LinkedIn profiles" not in rows and sum(1 for r in rows if r.startswith("Reading")) == 1, rows
