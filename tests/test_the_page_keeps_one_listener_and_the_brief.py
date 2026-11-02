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
        {"eval": count}], vp, model=model, clock="2026-10-25T15:00:00Z")
    assert got["after"][1]["eval"] is bool(asks)          # the gauge only where Claude is asked
    assert got["after"][3]["eval"] == asks


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


# A quiet day leaves no empty space: one booked thing and no likely questions, and Today's
# right half was empty while Coming up was a strip over nothing, its one item being Today's
# (the maintainer's page, 2026-11-02). Today gives the next step beside it, taken from Next
# three; Coming up gives what is due next from To do, each with its day; nothing is shown twice.
QUIET = ("(() => { const t = document.querySelector('#main .bp-today'); const u = document.querySelector('#main .bp-upcoming'); "
         "const side = t.querySelector('.bp-today-side'); const ids = [...document.querySelectorAll('#main .bpanel [data-k^=\"bp-\"]')].map((a) => a.getAttribute('data-k')).filter((k) => /^bp-(due|next|person|job):/.test(k)); "
         "return {side: !!side, then: side ? (side.querySelector('.bp-ready-t') || {}).textContent : null, thenRows: side ? side.querySelectorAll('.bp-steps li').length : 0, "
         "empty: [...t.querySelectorAll('.bp-body > *')].filter((e) => !e.textContent.trim()).length, "
         "upRows: u.querySelectorAll('.bp-up li, .bp-up-due li').length, dup: ids.length - new Set(ids).size, "
         "heroWide: side ? null : t.querySelector('.bp-iv').getBoundingClientRect().width / t.querySelector('.bp-body').getBoundingClientRect().width}; })()")


def test_a_quiet_day_fills_today_and_coming_up_with_something_useful(run, tmp_path, vp):
    model = copy.deepcopy(_sample())
    one = model["upcoming"][0]
    model["upcoming"] = [one]
    iv = next(i for i in model["interviews"] if i["id"] == one["go"]["item"])
    iv["one_screen"] = {"questions": []}
    iv.setdefault("prep", {})["updated"] = "2026-10-24"
    for sec in model["brief"]["sections"]:
        if sec.get("kind") == "lead":
            sec["parts"], sec["text"] = [], ""
    got = _go(run, tmp_path, [{"hash": "brief", "eval": QUIET}], vp, model=model, clock=T)
    r = got["after"][0]["eval"]
    assert r["side"] and r["then"] == "Then" and r["thenRows"] == 1, r
    assert r["empty"] == 0, r
    assert r["upRows"] >= 1, r
    assert r["dup"] == 0, r
    # With nothing to put beside it, the booked thing takes the card's width.
    model["due"], model["brief"]["sections"] = [], [s for s in model["brief"]["sections"] if s.get("kind") not in ("next", "owed")]
    got = _go(run, tmp_path, [{"hash": "brief", "eval": QUIET}], vp, model=model, clock=T)
    r = got["after"][0]["eval"]
    assert not r["side"] and r["empty"] == 0 and r["heroWide"] > 0.9, r


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
