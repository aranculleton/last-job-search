"""The page's half of one listener and the brief on the page (CONTRACT 7).

A "Claude isn't listening" card when nothing answers the page, whose Wake Claude rings the
same doorbell every tap uses and says what happens next; the footer's privacy line from the
model; the republish work in plain words; and Settings > Your brief from `model.schedule`:
days and time, a break until a date, and starting again, each written with the schedule's own
rev. Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import copy
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


@pytest.fixture(params=[PHONE, WIDE], ids=["phone", "wide"])
def vp(request):
    return request.param

T = "2026-10-25T09:00:00Z"


def _waiting():
    """A tap's work that has waited half an hour, and a listener last heard before it was asked."""
    return {"work/search~late": {"kind": "search", "title": "Finding jobs", "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:30:00Z",
                                 "status": "queued", "stages": [], "stage": 0, "stage_at": None, "steps": [], "claimed_by": None,
                                 "claimed_at": None, "stop_asked": False, "attempt": 1},
            "meta/listener": {"chat": "cloud-1", "title": "Job search: Claude's helper (keep this)", "kind": "cloud",
                              "answered_at": "2026-10-25T07:30:00Z",
                              "watching": True}}


def test_nobody_listening_is_one_card_and_wake_claude_rings_the_doorbell(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": '[data-item="listen"]', "eval": "document.querySelector('#main [data-card]').dataset.item"},
        {"click": "Wake Claude", "within": '[data-item="listen"]', "wait": 300, "read": '[data-item="listen"]', "calls": "comments"},
    ], vp, seed=_waiting(), clock=T)
    card = got["after"][0]["text"]
    assert "Claude isn't listening right now" in card and "What you tap is saved and waits." in card
    assert got["after"][0]["eval"] == "listen", "it is the first card"
    rings = [c for c in got["after"][1]["calls"] if c.get("text")]
    assert rings and rings[-1]["text"] == "[app] [work:search~late]", "the same doorbell every tap rings"
    assert "Claude has been told. It picks up what is waiting" in got["after"][1]["text"]


def test_with_nothing_to_hear_it_wake_claude_says_so_and_offers_the_chat(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "todo", "click": "Wake Claude", "within": '[data-item="listen"]', "wait": 300, "read": '[data-item="listen"]',
         "attr": ['[data-k="wake-open"]', "href"]},
    ], vp, seed=_waiting(), clock=T, fake={"canSend": "no_session"})
    assert "Nothing is open to hear it." in got["after"][0]["text"]
    assert got["after"][0]["attr"] == _sample()["listener"]["wake"]["url"]


def test_a_listener_heard_lately_shows_no_card(run, tmp_path, vp):
    seed = _waiting()
    seed["meta/listener"]["answered_at"] = "2026-10-25T08:59:00Z"
    seed["chats/cloud-1"] = {"kind": "cloud", "title": "Job search: Claude's helper (keep this)", "seen_at": "2026-10-25T08:59:00Z", "watching": True}
    got = _go(run, tmp_path, [{"hash": "todo", "count": '[data-item="listen"]'}], vp, seed=seed, clock=T)
    assert got["after"][0]["count"] == 0


def test_the_footer_says_the_models_own_privacy_line(run, tmp_path, vp):
    m = _sample()
    m["app"]["privacy"] = "Only you can open this page unless you share it: a line from the model."
    got = _go(run, tmp_path, [{"hash": "todo", "open": "foot-details", "read": "#foot"}], vp, model=m)
    assert "Only you can open this page unless you share it: a line from the model." in got["after"][0]["text"]


def test_a_republish_is_said_in_plain_words(run, tmp_path, vp):
    seed = {"work/republish~v4": {"kind": "republish", "title": "Updating your page", "to": "either", "args": {"version": 4}, "asked_at": "2026-10-25T08:59:30Z",
                                  "status": "running", "claimed_by": "cloud-1", "claimed_at": "2026-10-25T08:59:40Z", "stages": [], "stage": 0,
                                  "stage_at": "2026-10-25T08:59:40Z", "steps": [], "stop_asked": False, "attempt": 1}}
    got = _go(run, tmp_path, [{"hash": "work", "read": '[data-work="republish~v4"]'}], vp, seed=seed, clock=T)
    text = got["after"][0]["text"]
    assert "Updating your page" in text and "republish" not in text.lower()


def test_your_brief_moves_rests_and_starts_again_from_settings(run, tmp_path, vp):
    m = _sample()
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:brief-when", "read": '[data-k="info-sum:brief-when"]'},
        {"click": "Change it", "within": "#main"},
        {"fill": {"Time, in your own time zone": "08:15"}, "submit": True},
        {"open": "info-sum:brief-pause"},
        {"click": "Take a break until…", "within": "#main"},
        {"fill": {"Until": "2026-11-08"}, "submit": True},
    ], vp, model=m, clock=T)
    assert "Mondays and Thursdays at 7:38" in got["after"][0]["text"]
    move = _one(got, "brief.move")
    assert move["item"] == "schedule" and move["rev_seen"] == "sc1" and move["value"] == {"days": [1, 4], "time": "08:15"}
    pause = _one(got, "brief.pause")
    assert pause["value"] == {"until": "2026-11-08"} and pause["rev_seen"] == "sc1"
    # Resting: the row says until when, and Start again writes brief.resume.
    rest = copy.deepcopy(m)
    rest["schedule"]["paused_until"] = "2026-11-08"
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:brief-pause", "read": '[data-k="info-sum:brief-pause"]'},
        {"click": "Start again", "within": "#main"},
    ], vp, model=rest, clock=T)
    assert "Until" in got["after"][0]["text"] and "8" in got["after"][0]["text"]
    assert _one(got, "brief.resume")["rev_seen"] == "sc1"


def test_without_a_schedule_there_is_no_brief_group(run, tmp_path, vp):
    m = _sample()
    m.pop("schedule")
    got = _go(run, tmp_path, [{"hash": "settings", "count": '[data-k="info-sum:brief-when"]'}], vp, model=m, clock=T)
    assert got["after"][0]["count"] == 0
