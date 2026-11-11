"""A checklist card in To do offers Plan a time, which puts the work in the person's calendar.

The UX review of 2026-11-10 (U-18): only interviews could be added to a calendar, and To do
never helped to plan when the rest would be done; a plan of when is what turns an intention into
the thing done (Gollwitzer and Sheeran, 2006). Each checklist card now has Plan a time: a day
and a time, then the calendar sheet Coming up uses (Google Calendar, Outlook, a file, or the
details to copy), with nothing sent. Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_a_question_is_answered_on_its_card import _busier  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00Z"
SHEET = ("(() => { const d = document.querySelector('dialog.cal-sheet'); if (!d) return null;"
         " const g = d.querySelector('[data-k=\"cal-google\"]');"
         " return {title: d.querySelector('.sheet-title').textContent, intro: d.querySelector('.sheet-intro').textContent,"
         " google: g ? g.getAttribute('href') : ''}; })()")


def _checklist():
    """Three application follow-ups due today: one checklist card, a row an employer."""
    m = _busier()
    for d in m["due"]:
        if str(d.get("id", "")).startswith("due-more-"):
            d["sub"] = "follow_up"
    return m


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_plan_a_time_puts_the_checklist_in_the_calendar(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "click": "Plan a time"},
        {"fill": {"The day": "2026-10-27", "The time": "09:30"}, "then": "Add it to my calendar", "eval": SHEET},
    ], vp, model=_checklist(), clock=T)
    seen = got["after"][1]["eval"]
    assert seen and seen["title"] == "Add to your calendar", seen
    # Written in UTC from the person's own zone (the review of 2026-11-11), so it is the same
    # moment in every calendar wherever the device is.
    assert "dates=20261027T093000Z/20261027T100000Z" in seen["google"], seen
    assert "text=" in seen["google"] and "action=TEMPLATE" in seen["google"], seen
    # Nothing reaches Claude or the page's records: it is the person's own calendar.
    assert not [a for a in got["actions"] if a["action"].startswith("due.")], got["actions"]


def _plan(run, tmp_path, vp, within=None, zone=None, file=False):
    click = {"hash": "todo", "click": "Plan a time"}
    if within:
        click["within"] = within
    steps = [click, {"fill": {"The day": "2026-10-27", "The time": "09:30"}, "then": "Add it to my calendar", "eval": SHEET}]
    if file:
        steps.append({"click": "Apple Calendar or another app", "wait": 300, "calls": "downloads"})
    return _go(run, tmp_path, steps, vp, model=_checklist(), clock=T, zone=zone)


def test_the_time_is_the_persons_own_whatever_zone_the_device_is_in(run, tmp_path):
    here = _plan(run, tmp_path, WIDE)["after"][1]["eval"]
    tokyo = _plan(run, tmp_path, WIDE, zone="Asia/Tokyo")["after"][1]["eval"]
    assert here["google"] == tokyo["google"], (here, tokyo)
    # Said in the person's own time first, as every time on the page.
    assert "9:30" in tokyo["intro"] and "0:30" not in tokyo["intro"].split("(")[0], tokyo


def test_messages_to_send_can_be_planned_too(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "todo", "click": "Plan a time", "within": '#main [data-item="grp:send"]'},
        {"fill": {"The day": "2026-10-27", "The time": "09:30"}, "then": "Add it to my calendar", "eval": SHEET},
    ], WIDE, clock=T)
    seen = got["after"][1]["eval"]
    assert seen and "Send" in seen["intro"] and "message" in seen["intro"], seen


def test_the_saved_event_reminds_as_the_person_chose_and_folds_its_lines(run, tmp_path):
    import base64
    import io
    import zipfile
    got = _plan(run, tmp_path, WIDE, file=True)
    save = got["after"][2]["calls"][-1]
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(save["bytes"]))) as z:
        ics = z.read(z.namelist()[0]).decode("utf-8")
    assert "BEGIN:VALARM" in ics and "TRIGGER:-PT60M" in ics, ics
    assert all(len(line.encode("utf-8")) <= 75 for line in ics.split("\r\n")), ics
