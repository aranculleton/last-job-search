"""The LinkedIn download's reminder on the page: its trash, its row in Settings, and a panel
that says nothing stale (the maintainer, 2026-11-06).

- "its trash offers 'Every 2 weeks', 'Every month' and 'Stop asking', saved and changeable
  in Settings": one tap sets how often and puts the reminder away, with Undo; Settings >
  LinkedIn has the same choice as a row of chips.
- "On that panel, a 'Done.' from an action days ago and 'Only a chat can take this back: say
  so in a chat.' go: a confirmation shows only just after the action."

Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

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


T = "2026-10-25T09:00:00.000Z"
REMINDER = {"id": "setting-export_remind", "key": "export_remind", "label": "Reminder to download it",
            "kind": "choice", "value": "auto", "rev": "rm1",
            "choices": [["auto", "Weekly while messaging"], ["fortnightly", "Every 2 weeks"],
                        ["monthly", "Every month"], ["off", "Off"]],
            "help": "Weekly while you have sent notes or messages in the last two weeks, every two weeks otherwise."}
HEARD = {"chats/cloud-1": {"kind": "cloud", "seen_at": "2026-10-25T08:58:30.000Z", "watching": True},
         "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": "2026-10-25T08:59:00.000Z"}}
CARD = '#main [data-item="linkedin-export"]'
PANEL = "[data-k=\"det:info:linkedin-download\"]"
CHAT_ONLY = "Only a chat can take this back: say so in a chat."


def _model(value="auto"):
    m = _sample()
    m["linkedin"] = dict(m.get("linkedin") or {}, export=dict(m["linkedin_export"], reminder=dict(REMINDER, value=value)))
    return m


def _taken(at, applied_at):
    """A download taken on the page, as the engine left its receipt: nothing to undo, and the
    old note that only a chat could take it back."""
    return dict(HEARD, **{"actions/a-export": {"action": "export.take", "item": "2026-10", "value": {"assets": []}, "at": at, "rev": None},
                          "receipts/a-export": {"applied_at": applied_at, "by": "cloud-1", "result": "ok", "remove_assets": [],
                                                "counts": {"messages": 3}, "note": "Taken: 3 messages.", "undo_note": CHAT_ONLY}})


PANEL_SAYS = "(() => { const d = document.querySelector('" + PANEL.replace("'", "\\'") + "'); return {text: d ? d.textContent : '', lines: d ? d.querySelectorAll('.state').length : -1}; })()"


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_done_from_a_day_ago_and_the_chat_only_line_are_gone_from_the_panel(run, tmp_path, vp):
    seed = _taken("2026-10-24T08:58:00.000Z", "2026-10-24T08:59:00.000Z")
    got = _go(run, tmp_path, [{"hash": "settings", "open": "info-sum:linkedin-download", "eval": PANEL_SAYS}], vp,
              model=_model(), seed=seed, clock=T)
    r = got["after"][0]["eval"]
    assert r["lines"] == 0, r
    assert "Done." not in r["text"] and "take this back" not in r["text"] and "Only a chat" not in r["text"], r
    assert "Only a chat" not in got["after"][0]["text"]


def test_just_after_the_download_is_taken_its_panel_says_done_and_nothing_about_a_chat(run, tmp_path):
    seed = _taken("2026-10-25T08:57:00.000Z", "2026-10-25T08:58:00.000Z")
    got = _go(run, tmp_path, [{"hash": "settings", "open": "info-sum:linkedin-download", "eval": PANEL_SAYS}], WIDE,
              model=_model(), seed=seed, clock=T)
    r = got["after"][0]["eval"]
    assert r["lines"] == 1 and "Done." in r["text"], r
    assert "take this back" not in r["text"] and "Only a chat" not in r["text"], r


ROW = "(() => { const d = document.querySelector('[data-k=\"det:set:export_remind\"]'); return d ? {value: d.querySelector('.set-value').textContent, chips: [...d.querySelectorAll('label')].map((l) => l.textContent), pills: !!d.querySelector('fieldset.pills'), radios: d.querySelectorAll('input[type=radio]').length, checked: (d.querySelector('input:checked') || {}).value || ''} : null; })()"


def test_settings_has_the_reminder_as_chips_under_the_download_and_a_tap_saves_it(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "set-sum:export_remind", "eval": ROW},
        {"open": "set-export_remind-2", "wait": 900, "eval": ROW},
    ], WIDE, model=_model(), seed=HEARD, clock=T)
    r = got["after"][0]["eval"]
    assert r and r["value"] == "Weekly while messaging" and r["pills"] and r["radios"] == 4, r
    assert r["chips"] == ["Weekly while messaging", "Every 2 weeks", "Every month", "Off"], r
    assert "Weekly while you have sent notes or messages" in got["after"][0]["text"]
    sets = [a for a in got["actions"] if a["action"] == "setting.set"]
    assert [(a["item"], a["value"]) for a in sets] == [("setting-export_remind", "monthly")], got["actions"]
    assert got["after"][1]["eval"]["value"] == "Every month", got["after"][1]["eval"]
    # Its place is LinkedIn's, beside the download, not How the app runs.
    where = "(() => { const d = document.querySelector('[data-k=\"det:set:export_remind\"]'); const g = d && d.closest('.set-group'); return g ? (g.querySelector('h3') || {}).textContent : ''; })()"
    got = _go(run, tmp_path, [{"hash": "settings", "eval": where}], WIDE, model=_model(), seed=HEARD, clock=T)
    assert got["after"][0]["eval"] == "LinkedIn"


SHEET = "[...document.querySelectorAll('dialog[open] .sheet-choices button')].map((b) => b.textContent)"
TOAST = "[...document.querySelectorAll('[data-toast]')].map((t) => t.textContent).join(' | ')"


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_its_trash_offers_three_choices_and_one_tap_puts_it_away_with_undo(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "count": CARD},
        {"open": "export-trash", "eval": SHEET},
        {"open": "sheet-choice:remind-monthly", "count": CARD, "eval": TOAST},
    ], vp, model=_model(), seed=HEARD, clock=T)
    assert got["after"][0]["count"] == 1, "the reminder is on To do"
    assert got["after"][1]["eval"] == ["Every 2 weeks", "Every month", "Stop asking"], got["after"][1]["eval"]
    assert got["after"][2]["count"] == 0, "put away: it leaves To do at once"
    toast = got["after"][2]["eval"]
    assert "every month from now on" in toast and "Undo" in toast, toast
    taps = {a["action"]: a for a in got["actions"]}
    assert taps["setting.set"]["item"] == "setting-export_remind" and taps["setting.set"]["value"] == "monthly", got["actions"]
    assert taps["export.later"]["item"] == "2026-10", got["actions"]


def test_undo_in_its_toast_brings_the_reminder_back(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "todo", "open": "export-trash"},
        {"open": "sheet-choice:remind-off", "count": CARD},
        {"click": "Undo", "exact": True, "within": "#toasts", "count": CARD},
    ], WIDE, model=_model(), seed=HEARD, clock=T)
    assert got["after"][1]["count"] == 0 and got["after"][2]["count"] == 1, [a["count"] for a in got["after"]]


def test_stopped_from_settings_it_is_not_asked_for_on_to_do_nor_at_the_foot_of_contacts(run, tmp_path):
    m = _model("off")
    m["linkedin"]["export"] = dict(m["linkedin"]["export"], due=False, state="fresh")
    got = _go(run, tmp_path, [{"hash": "todo", "count": CARD}, {"hash": "contacts", "count": '[data-k="export-foot"]'}],
              WIDE, model=m, seed=HEARD, clock=T)
    assert got["after"][0]["count"] == 0 and got["after"][1]["count"] == 0, [a["count"] for a in got["after"]]
