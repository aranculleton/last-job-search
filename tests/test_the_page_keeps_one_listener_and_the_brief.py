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
from test_the_page_works_in_a_browser import EMPTY  # noqa: E402


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
            "meta/listener": {"chat": "cloud-1", "title": "Job search helper", "kind": "cloud",
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
    # It starts what it can as soon as it can: a big job waiting its turn behind the cap does
    # not start "within a minute or two" (the audit, 2026-11-03).
    assert "Claude has been told. It starts on what is waiting as soon as it can" in got["after"][1]["text"]


def test_with_nothing_to_hear_it_the_one_button_is_open_claude(run, tmp_path, vp):
    """Nothing open to hear a ring is known before the tap: the card offers the one button that
    can work, Open Claude, never a Wake Claude that cannot (the 3 November audit, shell 8).
    On a phone, where that link leaves the Claude app for the browser, there is none: the card
    says where it works instead (the maintainer, 2026-11-04)."""
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": '[data-item="listen"]', "attr": ['[data-k="wake-open"]', "href"],
         "eval": "[...document.querySelectorAll('[data-item=\"listen\"] .card-actions .btn')].map((b) => b.textContent.trim() + '|' + b.className)"},
    ], vp, seed=_waiting(), clock=T, fake={"canSend": "no_session"})
    card = got["after"][0]["text"]
    assert "Wake Claude" not in card, card
    buttons = got["after"][0]["eval"]
    if vp == PHONE:
        assert "Open this page on a computer to start it now." in card and buttons == [] and got["after"][0]["attr"] is None, (card, buttons)
        return
    assert "Open Claude to start what is waiting." in card, card
    assert got["after"][0]["attr"] == _sample()["listener"]["wake"]["url"]
    assert len(buttons) == 1 and buttons[0].startswith("Open Claude") and "primary" in buttons[0], buttons


def test_a_listener_heard_lately_shows_no_card(run, tmp_path, vp):
    seed = _waiting()
    seed["meta/listener"]["answered_at"] = "2026-10-25T08:59:00Z"
    seed["chats/cloud-1"] = {"kind": "cloud", "title": "Job search helper", "seen_at": "2026-10-25T08:59:00Z", "watching": True}
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


# The moving line under the header glides: it moves by transform alone, on its own layer, and
# stays inside the header. It was a background-position sweep, repainted every frame, and it
# stuttered on a busy page (the maintainer, 2026-11-02: "this loading animation is quite laggy").
LINE = ("(() => { const p = document.getElementById('pulse'); const a = document.getAnimations().find((x) => x.animationName === 'sweep'); "
        "const keys = a ? [...new Set(a.effect.getKeyframes().flatMap((k) => Object.keys(k)))].filter((k) => !['offset', 'easing', 'composite', 'computedOffset'].includes(k)) : null; "
        "return [p.classList.contains('is-updating'), getComputedStyle(p, '::after').animationName, keys, p.scrollWidth <= p.clientWidth, "
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth]; })()")


def test_the_update_line_glides_by_transform_and_stays_in_the_header(run, tmp_path, vp):
    seed = {"work/republish~v4": {"kind": "republish", "title": "Updating your page", "to": "either", "args": {"version": 4}, "asked_at": "2026-10-25T08:59:30Z",
                                  "status": "running", "claimed_by": "cloud-1", "claimed_at": "2026-10-25T08:59:40Z", "stages": [], "stage": 0,
                                  "stage_at": "2026-10-25T08:59:40Z", "steps": [], "stop_asked": False, "attempt": 1}}
    got = _go(run, tmp_path, [{"hash": "brief", "ready": "document.getElementById('pulse').classList.contains('is-updating')",
                               "eval": LINE}], vp, seed=seed, clock=T)
    updating, name, keys, inside, page_inside = got["after"][0]["eval"]
    assert updating and name == "sweep"
    assert keys == ["transform"], keys
    assert inside and page_inside


def test_your_brief_moves_rests_and_starts_again_from_settings(run, tmp_path, vp):
    m = _sample()
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:brief-when", "read": '[data-k="info-sum:brief-when"]'},
        {"click": "Change it", "within": "#main"},
        {"fill": {"Time": "08:15"}, "submit": True},
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


# ------------------------------------------------------------------ the brief's bell


def test_the_bell_turns_a_brief_off_and_says_so_where_settings_does(run, tmp_path, vp):
    # The bell on the Brief opens the same sheet as Settings > Your brief (the maintainer,
    # 2026-10-29: "the bell is both there and the settings too yes?").
    got = _go(run, tmp_path, [
        {"hash": "brief", "read": '[data-k="brief-bell"]'},
        {"open": "brief-bell"},
        {"click": "Off", "role": "radio", "exact": True},
        {"submit": True, "wait": 300},
        {"hash": "settings", "read": '[data-k="info-sum:brief-when"]'},
    ], vp, clock=T)
    assert "Mondays and Thursdays at 7:38" in got["after"][0]["text"]
    off = _one(got, "brief.off")
    assert off["item"] == "schedule" and off["rev_seen"] == "sc1"
    assert "Off" in got["after"][4]["text"], "Settings shows the bell's change at once"


def test_the_bell_turns_it_back_on_every_day(run, tmp_path, vp):
    m = _sample()
    m["schedule"]["off"] = True
    got = _go(run, tmp_path, [
        {"hash": "brief", "open": "brief-bell"},
        {"click": "Every day", "role": "radio", "exact": True},
        {"submit": True, "wait": 300},
    ], vp, model=m, clock=T)
    assert _one(got, "brief.on")["item"] == "schedule"
    move = _one(got, "brief.move")
    assert sorted(move["value"]["days"]) == [1, 2, 3, 4, 5, 6, 7] and move["value"]["time"] == "07:38"


def test_with_no_brief_the_bell_asks_once_and_turning_it_on_is_work_for_claude(run, tmp_path, vp):
    m = _sample()
    m["schedule"] = {"id": "schedule", "set_up": False, "off": False, "when": "", "days": [], "time": "",
                     "zone": "Europe/London", "paused": None, "waiting": 0, "rev": "sc0",
                     "actions": {"move": "brief.move", "pause": "brief.pause", "resume": "brief.resume", "off": "brief.off", "on": "brief.on"}}
    got = _go(run, tmp_path, [
        {"hash": "brief", "open": "brief-bell", "read": "dialog[open]"},
        {"click": "Turn it on", "wait": 500},
        {"hash": "settings", "read": '[data-k="info-sum:brief-when"]'},
    ], vp, model=m, clock=T)
    sheet = got["after"][0]["text"]
    assert "A brief each morning" in sheet and "no new chat is made" in sheet
    w = [x for x in got["work"] if x and x.get("kind") == "brief"]
    assert w and w[-1]["args"] == {"setup": True}, got["work"]
    assert "Being set up" in got["after"][2]["text"]
    assert not got["actions"], "nothing scheduled by a tap that only asks"
    assert w[-1]["to"] == "cloud"


def test_answered_on_the_computer_the_bell_sends_the_brief_to_the_cloud_and_starts_the_helper(run, tmp_path, vp):
    """A brief comes with the computer off, so only a chat in the cloud can run it (tools/page_db.py
    can_take). Where the page is answered on the computer and no helper is set up, the same tap
    asks for the brief and opens the helper's chat: nothing else to choose."""
    m = _sample()
    m["schedule"] = {"id": "schedule", "set_up": False, "off": False, "when": "", "days": [], "time": "",
                     "zone": "Europe/London", "paused": None, "waiting": 0, "rev": "sc0",
                     "actions": {"move": "brief.move", "pause": "brief.pause", "resume": "brief.resume", "off": "brief.off", "on": "brief.on"}}
    m.setdefault("where", {})["helper"] = {"state": "optional", "title": None, "say": "Only for work while your computer is off."}
    seed = {"meta/listener": {"chat": "local-1", "title": "Job search", "kind": "computer",
                              "answered_at": "2026-10-25T08:59:00Z", "watching": True}}
    got = _go(run, tmp_path, [
        {"hash": "brief", "eval": "window.__opened = []; window.open = (u) => { window.__opened.push(String(u)); return null; }; 'ok'"},
        {"open": "brief-bell", "read": "dialog[open]"},
        {"click": "Turn it on", "wait": 500, "eval": "JSON.stringify(window.__opened)"},
    ], vp, model=m, seed=seed, clock=T)
    sheet = got["after"][1]["text"]
    assert "Claude's helper in the cloud" in sheet and "press Send there, once" in sheet
    w = [x for x in got["work"] if x and x.get("kind") == "brief"]
    assert w and w[-1]["to"] == "cloud" and w[-1]["args"] == {"setup": True}
    assert "claude.ai/code" in got["after"][2]["eval"], got["after"][2]


# An open page learns a newer one was published and reloads itself to it, once per version:
# before 4.7 it compared a field nothing wrote, and a pinned page stayed two versions behind
# with a brief four days old (2026-11-02). meta/now `page` is the version last published
# (tools/app.py view); the model's app.page the version built into this page.
def test_an_open_page_reloads_itself_to_a_newer_version_once(run, tmp_path, vp):
    model = copy.deepcopy(_sample())
    model.setdefault("app", {})["page"] = 5
    seed = {"meta/now": {"rev": "newer", "made_at": T, "model": 1, "by": "brief", "page": 6}}
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "sessionStorage.getItem('ljs:reloaded-to')",
                               "until": "sessionStorage.getItem('ljs:reloaded-to') === '6'"}],
              vp, model=model, seed=seed, clock=T, settle=True)
    assert got["after"][0]["eval"] == "6"
    # The same version is never reloaded to twice, and an equal one not at all.
    same = copy.deepcopy(model)
    same["app"]["page"] = 6
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "sessionStorage.getItem('ljs:reloaded-to')"}],
              vp, model=same, seed=seed, clock=T)
    assert got["after"][0]["eval"] is None


# Refresh wakes Claude only for data from before today, and says so with the cost gauge every
# ask carries; data a chat wrote this morning is looked at again for free (2026-11-02: a
# Refresh on the day's own data spent the person's allowance on nothing).
@pytest.mark.parametrize("made, asks", [("2026-10-25T07:00:00Z", 0), ("2026-10-24T07:00:00Z", 1)])
def test_refresh_asks_claude_only_when_the_data_is_older_than_today(run, tmp_path, vp, made, asks):
    model = copy.deepcopy(_sample())
    model["made_at"] = made
    count = ("[...LJS.state().localWork.keys(), ...LJS.state().work.keys()]"
             ".filter((k) => String(k).indexOf('update~refresh') >= 0).length")
    got = _go(run, tmp_path, [
        {"hash": "brief", "eval": "(() => { document.querySelector('[data-k=\"conn\"]').click(); return 1; })()",
         "until": "!!document.querySelector('[data-k=\"refresh\"]')"},
        {"eval": "!!document.getElementById('refresh-cost')"},
        {"eval": "(() => { document.querySelector('[data-k=\"refresh\"]').click(); return 1; })()"},
        {"eval": count}, {"eval": "document.getElementById('toasts').textContent"}], vp, model=model, clock="2026-10-25T15:00:00Z")
    assert got["after"][1]["eval"] is bool(asks)          # the gauge only where Claude is asked
    assert got["after"][3]["eval"] == asks
    # A free re-check says so: a Refresh that changed nothing on screen read as broken (the
    # maintainer, 2026-11-02: "it doesnt seem to do anything").
    assert ("Up to date" in got["after"][4]["eval"]) is (not asks), got["after"][4]["eval"]


# Today's card is what comes next today: a call this afternoon leads, ahead of an interview
# three days out (the maintainer, 2026-11-02: "the most upcoming event"), and the strip
# marks today's things red and tomorrow's amber, nothing else.
def test_today_leads_with_what_is_on_today_and_the_strip_marks_today_and_tomorrow(run, tmp_path, vp):
    model = copy.deepcopy(_sample())
    call = copy.deepcopy(next(u for u in model["upcoming"] if u["kind"] == "call"))
    call.update(id="up-call-today", day="2026-10-25", time="15:00", start="2026-10-25T15:00:00Z",
                end="2026-10-25T15:30:00Z")
    model["upcoming"].insert(0, call)
    got = _go(run, tmp_path, [
        {"hash": "brief", "eval": "document.querySelector('#main .bp-iv .bp-iv-what').textContent"},
        {"eval": "(() => { const d = (n) => document.querySelectorAll('#main .bp-day')[n]; const c = (n) => d(n).querySelector('.bp-day-dots i'); "
                 "return [d(0).classList.contains('is-today'), d(1).classList.contains('is-tomorrow'), "
                 "c(0) ? getComputedStyle(c(0)).backgroundColor : null, d(4).querySelector('.bp-day-dots i') ? getComputedStyle(d(4).querySelector('.bp-day-dots i')).backgroundColor : null]; })()"}],
        vp, model=model, clock=T)
    assert got["after"][0]["eval"] == call["title"], got["after"][0]["eval"]
    today, tomorrow, red, later = got["after"][1]["eval"]
    assert today and tomorrow and red and later and red != later      # today's dot is its own colour


# Today is the one most pressing thing, with what matters about it beside it (the maintainer,
# 2026-11-02): with no booked thing today and an interview whose prep is ready, what has rolled
# over leads, with who it is and how late; Today's right half is never left empty, Coming up is
# never a strip over nothing, and Today's thing is never in Next three as well (2026-11-03).
TODAY = ("(() => { const t = document.querySelector('#main .bp-today'); const u = document.querySelector('#main .bp-upcoming'); "
         "const side = t.querySelector('.bp-today-side'); "
         "return {when: t.querySelector('.bp-iv-when').textContent, what: t.querySelector('.bp-iv-what').textContent, "
         "facts: side ? [...side.querySelectorAll('.bp-facts li')].map((l) => l.textContent) : [], "
         "empty: [...t.querySelectorAll('.bp-body > *')].filter((e) => !e.textContent.trim()).length, "
         "next: [...document.querySelectorAll('#main .bp-next li')].map((l) => l.textContent), "
         "upRows: u.querySelectorAll('.bp-up li, .bp-up-due li').length, "
         "heroWide: side ? null : t.querySelector('.bp-iv').getBoundingClientRect().width / t.querySelector('.bp-body').getBoundingClientRect().width}; })()")


def test_today_is_the_most_pressing_thing_with_what_matters_beside_it(run, tmp_path, vp):
    model = copy.deepcopy(_sample())
    one = model["upcoming"][0]
    model["upcoming"] = [one]
    iv = next(i for i in model["interviews"] if i["id"] == one["go"]["item"])
    iv["one_screen"] = {"questions": []}
    iv.setdefault("prep", {})["updated"] = "2026-10-24"
    late = min((d for d in model["due"] if d.get("due", "9999") < "2026-10-25" and d.get("kind") not in ("request_pending", "withdraw", "hidden")),
               key=lambda d: ((d.get("kind") != "reply"), d["due"]))
    late["context"] = "Operations lead at Fernhill Freight \u00b7 met at a meetup"
    got = _go(run, tmp_path, [{"hash": "brief", "eval": TODAY}], vp, model=model, clock=T)
    r = got["after"][0]["eval"]
    # One date a card, said one way (the walk-through, 2026-11-03): about someone, the corner
    # says Overdue and the facts lead with the day it is about; never "Rolled over · 2 days late".
    assert r["when"] == "Overdue", r
    assert r["facts"][0].startswith("You wrote 21 Sep") and r["facts"][0].endswith("no reply"), r
    assert late["title"] in r["what"], r
    assert "Operations lead at Fernhill Freight" in r["facts"], r
    assert r["empty"] == 0 and r["upRows"] >= 1, r
    assert not any(late["title"] in n for n in r["next"]), ("Today's thing is never said again under it", r["next"])
    # Not about anyone: how late it is, in two words.
    other = copy.deepcopy(model)
    other["due"] = [d for d in other["due"] if d["id"] != late["id"]]
    got = _go(run, tmp_path, [{"hash": "brief", "eval": TODAY}], vp, model=other, clock=T)
    assert got["after"][0]["eval"]["when"] == "2 days late", got["after"][0]["eval"]
    # Prep not written yet: the interview leads instead, inside the prep window.
    iv["prep"] = {}
    got = _go(run, tmp_path, [{"hash": "brief", "eval": TODAY}], vp, model=model, clock=T)
    assert iv["company"] in got["after"][0]["eval"]["what"], got["after"][0]["eval"]
    # With nothing to put beside it, the thing takes the card's width.
    iv["prep"] = {"updated": "2026-10-24"}
    model["due"], model["brief"]["sections"] = [], [s for s in model["brief"]["sections"] if s.get("kind") not in ("next", "owed", "lead")]
    got = _go(run, tmp_path, [{"hash": "brief", "eval": TODAY}], vp, model=model, clock=T)
    r = got["after"][0]["eval"]
    assert r["empty"] == 0 and (r["heroWide"] is None or r["heroWide"] > 0.9), r


# Your progress fits its panel at any width: no strip of numbers with empty space beside it on
# a full row, nothing squeezed on a phone (the maintainer, 2026-11-02: "leaves white space or
# gets weirdly cramped"). With News, it shares a row; without, it has the row to itself.
PROGRESS = ("(() => { const p = document.querySelector('#main .bp-numbers'); const b = p.querySelector('.bp-body').getBoundingClientRect(); "
            "const st = p.querySelector('.bp-stats').getBoundingClientRect(); const sp = p.querySelector('.bp-spark-wrap'); "
            "const tiles = [...p.querySelectorAll('.bp-stat')].map((t) => t.getBoundingClientRect().width); "
            "return {gap: Math.round(b.right - Math.max(st.right, sp ? sp.getBoundingClientRect().right : 0)), narrowest: Math.round(Math.min(...tiles)), "
            "overflow: p.scrollWidth > p.clientWidth}; })()")


@pytest.mark.parametrize("news", [True, False], ids=["with-news", "alone"])
def test_your_progress_fills_its_panel_without_crowding(run, tmp_path, vp, news):
    model = copy.deepcopy(_sample())
    if not news:
        model["brief"]["sections"] = [s for s in model["brief"]["sections"] if s.get("kind") != "news"]
    got = _go(run, tmp_path, [{"hash": "brief", "eval": PROGRESS}], vp, model=model, clock=T)
    r = got["after"][0]["eval"]
    assert r["gap"] <= 2, r            # nothing left empty at its right
    assert r["narrowest"] >= 88, r     # no number squeezed
    assert not r["overflow"], r


# The menu folds to its icons for more room, and back (the maintainer, 2026-11-02: "an option
# to minimise the side panel so it only shows the icons"): each name is still read out and
# shown on hover, To do keeps its badge, the choice is kept on this device, and a phone, which
# has no side menu, has no such button.
SIDE = ("(() => { const s = document.getElementById('side'); const m = document.getElementById('main'); const t = document.querySelector('[data-k=\"side-toggle\"]'); "
        "const a = document.querySelector('[data-k=\"side:jobs\"]'); "
        "return {side: Math.round(s.getBoundingClientRect().width), main: Math.round(m.getBoundingClientRect().width), "
        "shown: !!t && t.getBoundingClientRect().width > 0, pressed: t ? t.getAttribute('aria-pressed') : null, name: a.textContent.trim(), title: a.getAttribute('title'), "
        "badge: !!document.querySelector('#side [data-k=\"side:todo\"] .badge'), kept: localStorage.getItem('ljs:p:nav:mini')}; })()")


def test_the_menu_folds_to_its_icons_and_back(run, tmp_path, vp):
    click = "(() => { document.querySelector('[data-k=\"side-toggle\"]').click(); return 1; })()"
    got = _go(run, tmp_path, [{"hash": "brief", "eval": SIDE}, {"eval": click}, {"eval": SIDE}, {"eval": click}, {"eval": SIDE}], vp, clock=T)
    before, mini, after = got["after"][0]["eval"], got["after"][2]["eval"], got["after"][4]["eval"]
    if vp == PHONE:
        assert not before["shown"], before
        return
    assert before["shown"] and before["pressed"] == "false" and before["side"] >= 180, before
    assert mini["pressed"] == "true" and mini["side"] <= 64 and mini["main"] > before["main"], mini
    assert mini["name"].startswith("Jobs") and mini["title"] == "Jobs" and mini["badge"], mini
    assert mini["kept"] == "true", mini
    assert after["side"] == before["side"] and after["pressed"] == "false" and after["title"] is None, after


# The release review and the walk-through (2026-11-02). A test due today is itself on Today,
# never the interview it belongs to, and that interview stays in Coming up.
def test_a_test_due_today_leads_as_itself_and_its_interview_stays_coming_up(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "[document.querySelector('#main .bp-today .bp-iv-when').textContent, "
                                                       "document.querySelector('#main .bp-today .bp-iv-what').textContent, "
                                                       "document.querySelector('#main .bp-upcoming').textContent]"}],
              vp, clock="2026-11-02T08:30:00Z")
    when, what, coming = got["after"][0]["eval"]
    assert when.startswith("Due today") and "Online test" in what, (when, what)
    assert "Second interview" in coming, coming


# A late reply or follow-up with a draft ready leads to the draft, not to the person's page,
# which has no draft on it.
def test_todays_late_follow_up_opens_its_draft(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "document.querySelector('#main .bp-today .bp-iv .btn').textContent"},
                              {"eval": "(() => { document.querySelector('#main .bp-today .bp-iv .btn').click(); return 1; })()"},
                              {"eval": "location.hash"}], vp, clock=T)
    assert got["after"][0]["eval"] == "See the draft", got["after"][0]["eval"]
    # On the draft itself: Wren's card in Contacts, where it is (one page since 2026-11-04).
    assert got["after"][2]["eval"] == "#contacts/fernhill_freight_halloway", got["after"][2]["eval"]


# Refresh with yesterday's data and the Claude allowance used up says so, never "Up to date".
def test_refresh_says_when_the_allowance_stopped_it(run, tmp_path, vp):
    model = copy.deepcopy(_sample())
    model["made_at"] = "2026-10-24T07:00:00Z"
    got = _go(run, tmp_path, [
        {"hash": "brief", "eval": "(() => { LJS.state().flags.limit = Date.now() + 3600000; document.querySelector('[data-k=\"conn\"]').click(); return 1; })()",
         "until": "!!document.querySelector('[data-k=\"refresh\"]')"},
        {"eval": "(() => { document.querySelector('[data-k=\"refresh\"]').click(); return 1; })()"},
        {"eval": "document.getElementById('toasts').textContent"}], vp, model=model, clock="2026-10-25T15:00:00Z")
    toast = got["after"][2]["eval"]
    assert "allowance" in toast and "Up to date" not in toast, toast


# A new person's progress, with no weekly bars yet, still fills its panel.
def test_your_progress_with_no_bars_yet_fills_its_panel(run, tmp_path, vp):
    model = copy.deepcopy(_sample())
    model["done"]["weeks"] = []
    model["brief"]["sections"] = [s for s in model["brief"]["sections"] if s.get("kind") != "news"]
    got = _go(run, tmp_path, [{"hash": "brief", "eval": PROGRESS}], vp, model=model, clock=T)
    assert got["after"][0]["eval"]["gap"] <= 2, got["after"][0]["eval"]


# From the walk-through (2026-11-02). Every count of jobs to look at is the same number, and a
# closed posting is never one of them.
def test_every_count_of_jobs_to_look_at_agrees_and_leaves_out_a_closed_one(run, tmp_path, vp):
    js = ("(() => { const n = (s) => { const m = /(\\d+)/.exec(s || ''); return m ? Number(m[1]) : 0; }; "
          "return {nav: n((document.querySelector('[data-k=\"side:jobs\"] .navcount, [data-k=\"tab:jobs\"] .navcount') || {}).textContent), "
          "brief: document.querySelectorAll('#main .bp-jobs li').length}; })()")
    got = _go(run, tmp_path, [{"hash": "brief", "eval": js},
                              {"hash": "jobs", "eval": "document.querySelector('#main .summary, #main .sum, #main p').textContent"},
                              {"hash": "todo", "eval": "(document.querySelector('[data-k=\"todo-jobs\"]') || {}).textContent || ''"},
                              {"hash": "brief", "eval": "document.querySelector('#main .bp-jobs').textContent"}], vp, clock=T)
    a = got["after"][0]["eval"]
    jobs_line, todo_line, panel = got["after"][1]["eval"], got["after"][2]["eval"], got["after"][3]["eval"]
    assert a["nav"] == a["brief"] and jobs_line.startswith("%d to look at" % a["nav"]), (a, jobs_line)
    assert (not todo_line) or todo_line.startswith("%d new" % a["nav"]), todo_line
    assert "Analytics Consultant" not in panel, panel      # its posting has closed


# Today's thing comes again in Next three only where there is room: the thank-you two days
# late is on the Brief, and Wednesday's phone screen says when it is.
def test_next_three_keeps_room_for_others_and_an_interview_says_when(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "[document.querySelector('#main .bp-today .bp-iv-what').textContent, "
                                                       "[...document.querySelectorAll('#main .bp-next li')].map((l) => l.textContent)]"}], vp, clock=T)
    today, steps = got["after"][0]["eval"]
    assert not any(today.strip() in s for s in steps), (today, steps)
    assert any("Larkspur" in s and "28 Oct" in s and "13:00" in s for s in steps), steps
    # A thank-you owed after a round is not given the next round's day.
    assert not any("Thank-you" in s and "4 Nov" in s for s in steps), steps


# Set up with nothing found yet: Today's one thing is the first search, with a filled button.
def test_a_person_with_nothing_yet_is_shown_the_first_search(run, tmp_path, vp):
    model = copy.deepcopy(_sample())
    for k in ("due", "messages", "ready", "upcoming", "interviews", "people"):
        if isinstance(model.get(k), list):
            model[k] = []
    model["jobs"]["rows"] = []
    model["brief"]["sections"] = [s for s in model["brief"]["sections"] if s.get("kind") not in ("next", "owed", "lead")]
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "[document.querySelector('#main .bp-today .bp-iv-what').textContent, "
                                                       "(document.querySelector('#main .bp-today [data-k=\"bp-first-search\"]') || {}).textContent]"}],
              vp, model=model, clock=T)
    what, button = got["after"][0]["eval"]
    assert what == "Find your first jobs" and button == "Start the search", (what, button)


# A reply owed in To do names its person by `item`, as the model sends it, and the Brief shows
# that person once: the same reply led Today and came third in Next three on the maintainer's
# page (2026-11-02), because only a `contact` field the model never sends was read.
def test_a_reply_owed_is_shown_once_when_a_step_names_the_same_person(run, tmp_path, vp):
    model = copy.deepcopy(_sample())
    d = next(x for x in model["due"] if x["id"] == "due-juno-reply")
    d.pop("contact")
    d["item"] = "larkspur_retail_castellan"
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "[document.querySelectorAll('#main [data-k=\"bp-due:due-juno-reply\"]').length, "
                                                       "[...document.querySelectorAll('#main .bp-today, #main .bp-next, #main .bp-upcoming, #main .bp-people')].filter((p) => p.textContent.includes('Juno')).map((p) => p.getAttribute('data-k'))]"}],
              vp, model=model, clock=T)
    due_rows, junos = got["after"][0]["eval"]
    # The person is in one panel, once: the due row for them is not drawn beside the step.
    assert due_rows == 0 and len(junos) == 1, (due_rows, junos)


# Fitting the Brief to the window is by what each item really saves: nothing is hidden beside
# white space, Today gives a likely question before People or Jobs lose anyone, and Today keeps
# two (the maintainer, 2026-11-02: "dynamic based on screen size ... be smart").
FITS = ("[...document.querySelectorAll('#main [data-fit]')].map((l) => [l.className, l.getAttribute('data-fit'), "
        "[...l.children].filter((li) => li.hidden).length, [...l.children].filter((li) => !li.hidden).length])")


@pytest.mark.parametrize("size", [{"width": 1440, "height": 1400}, {"width": 1280, "height": 700},
                                  {"width": 1100, "height": 620}])
def test_fitting_the_brief_takes_what_saves_most_and_keeps_today_useful(run, tmp_path, size):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": FITS}], size, clock=T)
    lists = {c: (f, hidden, shown) for c, f, hidden, shown in got["after"][0]["eval"]}
    q = next((v for c, v in lists.items() if "bp-qs" in c), None)
    people, jobs = lists["plain bp-list bp-people"], lists["plain bp-list"]
    assert people[0] == "2,3,3" and jobs[0] == "2,3,2" and (q is None or q[0] == "2,3,0"), lists
    start = lambda v: min(int(v[0].split(",")[1]), v[1] + v[2])  # noqa: E731
    if size["height"] >= 1400:          # room to spare in every engine's type, Firefox's taller
        # Room to spare: every list shows at least what it starts with, and more where its row
        # has room (extra items beyond the start count stay folded only where they would grow it).
        assert all(v[2] >= start(v) for v in lists.values()), lists
    if q is not None:
        assert q[2] >= 2, lists                                   # Today never below two questions
        if people[2] < start(people) or jobs[2] < start(jobs):
            assert q[2] == 2, lists                               # Today gave first

# Each person's next step sits in one column: every step, and the day under it, starts at the
# same edge, so steps of different lengths never jut out (the maintainer, 2026-11-02).
def test_every_persons_step_and_day_start_at_one_edge(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "brief", "eval": "[...document.querySelectorAll('#main .bp-people .bp-state')].map((s) => { "
                                                       "const w = s.querySelector('.bp-when'); const r = document.createRange(); r.selectNodeContents(s.firstChild); "
                                                       "return [Math.round(r.getBoundingClientRect().left), w ? Math.round(w.getBoundingClientRect().left) : null]; })"}], vp, clock=T)
    rows = got["after"][0]["eval"]
    assert len(rows) >= 2, rows
    lefts = {left for left, _day in rows} | {day for _left, day in rows if day is not None}
    assert max(lefts) - min(lefts) <= 1, rows


# Coming up's own day headings mark today and tomorrow in the strip's calm colours.
def test_coming_up_marks_today_and_tomorrow_calmly(run, tmp_path, vp):
    model = copy.deepcopy(_sample())
    for n, day in enumerate(("2026-10-25", "2026-10-26")):
        call = copy.deepcopy(next(u for u in model["upcoming"] if u["kind"] == "call"))
        call.update(id="up-call-%d" % n, day=day, start=day + "T15:00:00Z", end=day + "T15:30:00Z")
        model["upcoming"].insert(n, call)
    got = _go(run, tmp_path, [{"hash": "interviews", "eval": "[...document.querySelectorAll('#main .up-day')].slice(0, 3).map((d) => [d.className, "
                                                            "getComputedStyle(d.querySelector('.group'), '::before').backgroundColor])"}],
              vp, model=model, clock=T)
    (c0, today), (c1, tomorrow), (c2, later) = got["after"][0]["eval"]
    assert "is-today" in c0 and "is-tomorrow" in c1 and "is-to" not in c2, got["after"][0]["eval"]
    assert today != tomorrow and today not in ("rgba(0, 0, 0, 0)", "") and tomorrow not in ("rgba(0, 0, 0, 0)", "")


# ------------------------------------------------------------------ a draft already made is shown, never made again

# A message already drafted is opened, never drafted a second time (2026-11-02): To do's
# "Follow up with Fernhill Freight" queued new work while the follow-up sat ready in Messages
# (now on Wren's own card in Contacts, 2026-11-04).
def test_a_follow_up_already_drafted_opens_from_to_do_and_is_never_drafted_again(run, tmp_path, vp):
    row = '[data-item="due-fernhill-nudge"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": row},
        {"click": "See the draft", "within": row, "until": "location.hash === '#contacts/fernhill_freight_halloway'"},
    ], vp, clock=T)
    text = got["after"][0]["text"]
    assert "See the draft" in text and "Draft the follow-up" not in text, text
    assert got["after"][1]["hash"] == "#contacts/fernhill_freight_halloway"
    assert not [w for w in got["work"] if w and w.get("kind") in ("follow_up", "nudge")], got["work"]


# A reply drafted for Juno and a thank-you for Marisol: their To do row and their own page open
# the draft, their card in Contacts shows it (one page since 2026-11-04), and nothing offers
# "Draft a reply" over it.
def test_a_reply_already_drafted_opens_from_to_do_contacts_and_their_page(run, tmp_path, vp):
    juno, marisol = '[data-item="larkspur_retail_castellan"]', '[data-item="ellerwick_trust_priya"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "read": '[data-item="due-juno-reply"]'},
        {"hash": "contacts", "read": juno},
        {"read": marisol},
        {"hash": "contacts", "click": "Juno", "role": "link", "within": juno, "read": "dialog.detail"},
        {"click": "See the draft", "within": "dialog.detail", "until": "location.hash === '#contacts/larkspur_retail_castellan'",
         "eval": "document.querySelectorAll('dialog.detail[open]').length"},
    ], vp, clock=T)
    todo = got["after"][0]["text"]
    assert "See the draft" in todo and "Draft a reply" not in todo, todo
    for n in (1, 2):
        text = got["after"][n]["text"]
        assert "I sent it" in text and "Copy" in text and "Draft a reply" not in text, (n, text)
    assert "Thursday at 12 suits me well" in got["after"][1]["text"], "her card shows the draft that is ready"
    assert "Your thank-you" in got["after"][2]["text"], got["after"][2]["text"]
    page = got["after"][3]["text"]
    assert "See the draft" in page and "Draft a reply" not in page, page
    assert "Thursday at 12 suits me well" in page, "their page shows the draft that is ready"
    assert got["after"][4]["eval"] == 0 and got["after"][4]["hash"] == "#contacts/larkspur_retail_castellan"
    assert not [w for w in got["work"] if w and w.get("kind") in ("reply", "follow_up")], got["work"]


# "I sent it" counts everywhere at once, before Claude catches up (2026-11-02): Contacts said
# "Replied: your turn" with "Draft a reply", To do still asked to reply, and the badge stayed.
BADGE = "(() => { const b = document.querySelector('#tabs .badge, #side .badge'); return b ? Number(b.firstChild.textContent) : 0; })()"


def test_i_sent_it_is_done_in_contacts_to_do_and_the_brief_at_once(run, tmp_path, vp):
    juno = '[data-item="larkspur_retail_castellan"]'
    got = _go(run, tmp_path, [
        {"hash": "todo", "eval": BADGE},
        {"hash": "brief", "read": "#main .bp-next"},
        {"hash": "contacts", "click": "Copy", "within": juno},
        {"click": "I sent it", "within": juno},
        {"hash": "contacts", "read": "#main .sec-head"},
        {"open": "fold:contacts", "read": juno},
        {"hash": "todo", "count": '[data-item="due-juno-reply"]',
         "eval": "[" + BADGE + ", (document.querySelector('[data-item=\"grp:send\"] [data-k^=\"grp-done:\"]') || {}).textContent || '']"},
        {"hash": "brief", "read": "#main .bp-next", "eval": "(document.querySelector('#main .bp-people') || {}).textContent || ''"},
    ], vp, clock=T)
    assert _one(got, "msg.sent")["item"] == "msg-juno-1"
    assert "Reply to Juno" in got["after"][1]["text"], "the Brief asked for the reply before it went"
    assert "one of them a reply" not in got["after"][4]["text"], got["after"][4]["text"]
    row = got["after"][5]["text"]
    assert "Message sent" in row and "Replied: your turn" not in row and "Draft a reply" not in row, row
    assert got["after"][6]["count"] == 0, "To do no longer asks for the reply: its row goes at once"
    # The badge counts cards (DESIGN.md, counts): the reply was a row of "Messages to send",
    # which still holds the others, so the badge stays and the card's own count moves.
    badge, done = got["after"][6]["eval"]
    assert badge == got["after"][0]["eval"] and done == "1 of 7 done", (got["after"][0]["eval"], badge, done)
    assert "Juno" not in got["after"][7]["text"] and "Juno" not in got["after"][7]["eval"], got["after"][7]


# A person's page: where it stands is a line of words with ticks, never outlined pills that
# look like the buttons under them; its blocks stand apart; and Back names where the person came
# from (Contacts, where each message is on its person's card since 2026-11-04).
STEPS = ("(() => { const p = document.querySelector('dialog.detail .d-steps'); if (!p) return null; const c = p.cloneNode(true); "
         "c.querySelectorAll('.sr-only').forEach((s) => s.remove()); "
         "return [c.textContent, [...p.querySelectorAll('*')].some((e) => parseFloat(getComputedStyle(e).borderTopWidth) > 0)]; })()")
GAPS = ("(() => { const kids = [...document.querySelector('dialog.detail .detail-body > div').children].filter((e) => e.getBoundingClientRect().height > 0); "
        "return Math.min(...kids.slice(1).map((e, i) => Math.round(e.getBoundingClientRect().top - kids[i].getBoundingClientRect().bottom))); })()")


def test_a_persons_page_says_where_it_stands_in_words_and_back_names_where_it_came_from(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "click": "Juno", "role": "link", "within": '[data-item="larkspur_retail_castellan"]', "read": '[data-k="detail-back"]', "eval": STEPS},
        {"eval": GAPS},
        {"eval": "document.querySelectorAll('dialog.detail .stepper').length"},
    ], vp, clock=T)
    assert got["after"][0]["text"].replace("‹", "").strip() == "Contacts", got["after"][0]["text"]
    assert got["after"][0]["eval"], "the stages are a line of words"
    words, bordered = got["after"][0]["eval"]
    assert " ".join(words.split()) == "Written to ✓ · Replied ✓ · Talked · Referral", words
    assert not bordered, "no stage is drawn as a pill"
    assert got["after"][1]["eval"] >= 12, "the page's blocks stand apart: %r" % got["after"][1]["eval"]
    assert got["after"][2]["eval"] == 0


# ------------------------------------------------------------------ words a person reads and hears


def test_the_brief_time_is_said_as_the_sheet_says_it(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "settings", "open": "info-sum:brief-when", "read": "#main"}], vp, clock=T)
    text = got["after"][0]["text"]
    assert "UK time" in text and "Europe/London" not in text, text


def test_the_bin_says_posted_too_long_ago_not_too_old(run, tmp_path):
    # Offered only for a posting up for months (2026-11-03): the sample's is five days old, so
    # it is put up for four months here, and a fresh one is asked about too.
    m = _sample()
    next(r for r in m["jobs"]["rows"] if r["id"] == "r12-1")["posted_days"] = 120
    got = _go(run, tmp_path, [{"hash": "jobs", "click": "Not for me: Harbourline Bank, Pricing Analyst", "read": "dialog[open]"}], PHONE, clock=T, model=m)
    sheet = got["after"][0]["text"]
    assert "Posted too long ago" in sheet and "Too old" not in sheet, sheet
    fresh = _go(run, tmp_path, [{"hash": "jobs", "click": "Not for me: Copperleaf Pay, Data Analyst, Payments", "read": "dialog[open]"}], PHONE, clock=T)
    assert "Posted too long ago" not in fresh["after"][0]["text"] and "It has closed" not in fresh["after"][0]["text"]


ALERT_WORDS = "[...document.querySelectorAll('#main [data-alert]')].map((a) => [a.getAttribute('data-alert'), a.querySelector('.sr-only').textContent.trim()])"


def test_a_screen_reader_hears_note_before_what_is_not_a_fix(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": ALERT_WORDS}, {"hash": "todo", "eval": ALERT_WORDS}], PHONE, clock=T)
    said = dict(got["after"][0]["eval"] + got["after"][1]["eval"])
    # A closed posting is a note where it is shown; it is no To do card (the UX review,
    # 2026-11-05), so To do may not show it at all.
    assert said.get("al-closed-r12-5", "Note:") == "Note:" and said["al-referral_hold-r12-3"] == "Note:", said
    assert all(v == "Needs fixing:" for k, v in said.items() if k.startswith("al-checks-")), said


def test_i_sent_it_is_named_by_its_visible_words_first(run, tmp_path, vp):
    names = "['msg-juno-1', 'msg-ash-1'].map((id) => document.querySelector('[data-k=\"sent:' + id + '\"]').getAttribute('aria-label'))"
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": names}], vp, clock=T)
    assert got["after"][0]["eval"] == ["I sent it: the message to Juno", "I sent it: the note to Ash"]


# ------------------------------------------------------------------ a brand-new person

BUTTONS = "[...document.querySelectorAll('#main .card-actions button')].map((b) => b.textContent)"


@pytest.mark.parametrize("section", ["brief", "jobs", "contacts", "interviews"])
def test_a_new_person_is_asked_to_start_everywhere_until_a_step_is_done(run, tmp_path, section):
    got = _go(run, tmp_path, [{"hash": section, "eval": BUTTONS}, {"hash": "todo", "eval": BUTTONS}], PHONE, model=copy.deepcopy(EMPTY), clock=T)
    assert got["after"][0]["eval"] == ["Start"] and got["after"][1]["eval"] == ["Start"], got["after"]
    # One step done: Continue, as To do says it.
    part = copy.deepcopy(EMPTY)
    part["setup"] = {"state": "running", "next": "work", "progress": {"done": 1, "total": 2},
                     "steps": [{"id": "setup-resume", "step": "resume", "question": "Your CV", "status": "done", "rev": "s1"},
                               {"id": "setup-work", "step": "work", "question": "What work do you want next?", "status": "next", "rev": "s2"}]}
    got = _go(run, tmp_path, [{"hash": section, "eval": BUTTONS}], PHONE, model=part, clock=T)
    assert got["after"][0]["eval"] == ["Continue setting up"], got["after"]


def test_messages_old_link_opens_contacts(run, tmp_path):
    # Messages was a view of its own until Contacts became one page (2026-11-04).
    got = _go(run, tmp_path, [{"hash": "messages", "eval": "document.querySelector('#main h2').textContent"}], PHONE, model=copy.deepcopy(EMPTY), clock=T)
    assert got["after"][0]["eval"] == "Contacts"


# ------------------------------------------------------------------ the brief's phone notification


def _no_brief_yet(m):
    m["schedule"] = {"id": "schedule", "set_up": False, "off": False, "when": "", "days": [], "time": "",
                     "zone": "Europe/London", "paused": None, "waiting": 0, "rev": "sc0", "push_here": False,
                     "actions": {"move": "brief.move", "pause": "brief.pause", "resume": "brief.resume", "off": "brief.off", "on": "brief.on"}}
    return m


def _phone_setting(m, value="off"):
    m["settings"] = [s for s in m.get("settings") or [] if s.get("key") != "brief_push"] + [
        {"id": "setting-brief_push", "key": "brief_push", "label": "Phone notification", "kind": "choice",
         "value": value, "choices": [["off", "Off"], ["on", "On"]], "rev": "s-brief_push"}]
    return m


def test_turning_the_brief_on_asks_about_the_phone_and_keeps_the_answer(run, tmp_path, vp):
    """Off unless chosen, and asked where the brief is set up (the maintainer, 2026-11-04: "make
    it off by default but maybe part of the setup"). The answer is kept either way, so the
    update never asks again what was answered here."""
    for choose, want in ((None, "off"), ("On", "on")):
        here = tmp_path / want
        here.mkdir()
        steps = [{"hash": "brief", "open": "brief-bell", "read": "dialog[open]"}]
        if choose:
            steps.append({"click": choose, "role": "radio", "exact": True})
        steps.append({"click": "Turn it on", "wait": 500})
        got = _go(run, here, steps, vp, model=_phone_setting(_no_brief_yet(_sample())), clock=T)
        assert "Phone notification" in got["after"][0]["text"]
        tap = _one(got, "setting.set")
        assert tap["item"] == "setting-brief_push" and tap["value"] == want, tap
        w = [x for x in got["work"] if x and x.get("kind") == "brief"]
        assert w and w[-1]["args"] == {"setup": True}, got["work"]


def test_settings_offers_the_phone_notification_only_where_the_brief_sends_it(run, tmp_path, vp):
    groups = ("Array.from(document.querySelectorAll('.set-group'))"
              ".map((g) => (g.getAttribute('aria-label') || '') + ':' + g.textContent).join('|')")
    for here in (True, False):
        m = _phone_setting(_sample())
        m["schedule"]["push_here"] = here
        d = tmp_path / str(here)
        d.mkdir()
        got = _go(run, d, [{"hash": "settings", "eval": groups}], vp, model=m, clock=T)
        text = got["after"][0]["eval"]
        brief = next(g for g in text.split("|") if g.startswith("Your brief:"))
        assert ("Phone notification" in brief) is here, brief
        assert ("Phone notification" in text) is here
