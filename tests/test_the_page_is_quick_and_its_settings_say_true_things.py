"""The page's shell and Settings, as the 3 November audit found them on one person's real search
(shell_settings 1 to 32): each test runs that finding's own steps.

The first ones run at the audit's scale, a search the engine builds from invented word lists
(tests/app_state.py large): 716 people on the page, 66 applications and the due list full. Switching to
Contacts froze a laptop for 1.2 seconds and a phone-speed CPU for 7.8: every person was asked
about every due row inside the sort, and every date made a new date formatter (7,658 a render).
Everything else runs on the invented sample (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import types

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_page  # noqa: E402
import app_state  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _sample  # noqa: E402

NOW = "2026-10-25T08:00:00Z"
CLOCK = "2026-10-25T09:30:00Z"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _go(run, tmp_path, steps, vp, model=None, seed=None, fake=None, clock=CLOCK, touch=False, name="page"):
    path = os.path.join(str(tmp_path), name + ".html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model or _sample())))
    got = run("engine", html=path, viewport=vp, steps=steps, seed=seed or {}, fake=fake or {"canSend": "available"},
              clock=clock, touch=touch)
    assert not got["errors"], got["errors"]
    return got


@pytest.fixture(scope="module")
def big(tmp_path_factory):
    """The audit's scale, from the engine itself: 716 people on the page, 66 applications, 100
    due. The book is bigger: a thread gone quiet is finished history, never on the page (the
    audit, contacts 13), so 716 shown takes a book of 810."""
    tmp = tmp_path_factory.mktemp("big")
    state = app_state.large(str(tmp / "state"), tracker_rows=66, contacts=810, threads=1800)
    out = str(tmp / "model.json")
    env = dict(os.environ, LJS_PROFILE=app_state.EXAMPLE, LJS_STATE=state, LJS_COPY="private")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model", "--now", NOW, "--out", out],
                   env=env, check=True, capture_output=True)
    with open(out, encoding="utf-8") as fh:
        m = json.load(fh)
    assert len(m["people"]) >= 716 and len(m["due"]) >= 90, (len(m["people"]), len(m["due"]))
    return m


# Every date formatter the page makes from here on, counted.
COUNT = ("(() => { window.__dtf = 0; const D = Intl.DateTimeFormat; const W = function (a, b) { window.__dtf++; return new D(a, b); };"
         " W.prototype = D.prototype; W.supportedLocalesOf = D.supportedLocalesOf; Intl.DateTimeFormat = W; return 1; })()")
ZERO = "(() => { window.__dtf = 0; window.__lt = []; return 1; })()"
# Long tasks from here on, and those of the page's own opening.
WATCH = ("(() => { window.__lt = []; new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push(Math.round(e.duration)); })"
         ".observe({type: 'longtask'}); return 1; })()")
OPENING = ("new Promise((r) => { const o = new PerformanceObserver((l) => { r(l.getEntries().map((e) => Math.round(e.duration))); o.disconnect(); });"
           " o.observe({type: 'longtask', buffered: true}); setTimeout(() => r([]), 1000); })")


# ------------------------------------------------------------------ 1 and 2: Contacts and the Brief at scale

def test_contacts_and_the_brief_at_full_scale_make_no_date_formatter_a_row(run, tmp_path, big):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": COUNT}, {"hash": "contacts", "eval": "window.__dtf"},
                              {"eval": ZERO}, {"hash": "brief", "eval": "window.__dtf"},
                              {"eval": ZERO}, {"hash": "contacts", "eval": "window.__dtf"}], WIDE, model=big)
    contacts, brief, again = got["after"][1]["eval"], got["after"][3]["eval"], got["after"][5]["eval"]
    # Before: 7,658 formatters a Contacts render and 1,648 a Brief one (the audit's count).
    assert contacts < 40 and brief < 40 and again < 10, (contacts, brief, again)


@pytest.mark.timing
def test_switching_to_contacts_or_the_brief_at_full_scale_is_quick(run, tmp_path, big):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": OPENING}, {"eval": WATCH},
                              {"hash": "contacts", "wait": 400, "eval": "window.__lt.slice()"}, {"eval": ZERO},
                              {"hash": "brief", "wait": 400, "eval": "window.__lt.slice()"}], WIDE, model=big)
    opening = max(got["after"][0]["eval"] or [0])
    contacts = max(got["after"][2]["eval"] or [0])
    brief = max(got["after"][4]["eval"] or [0])
    # Before, on a laptop: Contacts 1.2 to 1.3 seconds, the Brief 0.7, the opening 1.8 to 2.4.
    assert contacts < 900 and brief < 500 and opening < 1200, (contacts, brief, opening)


# ------------------------------------------------------------------ 3: a burst of writes from a chat

@pytest.mark.timing
def test_ten_documents_a_chat_writes_at_once_draw_the_page_a_few_times_not_ten(run, tmp_path, big):
    burst = {k: big[k] for k in ("learned", "help", "where", "search", "resume", "linkedin", "you", "brief", "settings", "updates")}
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": WATCH}, {"view": burst, "wait": 1500, "eval": "window.__lt.slice()"}], WIDE, model=big)
    tasks = [t for t in got["after"][1]["eval"] if t > 50]
    # Before: one full redraw a document, ten long tasks of a second each.
    assert len(tasks) <= 3, tasks


# ------------------------------------------------------------------ 4: each section reaches the page once

def test_the_store_sends_only_what_changed_since_the_page_was_made_and_the_whole_lists(run, tmp_path):
    m = _sample()
    old = {"made_at": "2026-10-25T07:00:00Z", "data": dict(m["jobs"], summary="An older search.")}
    new = {"made_at": "2026-10-25T09:00:00Z", "data": dict(m["jobs"], summary="A newer search: 2 worth a look.")}
    lists = {"list": "people", "part": 1, "parts": 1, "rev": "x", "made_at": "2026-10-25T07:00:00Z", "items": []}
    read = "[...LJS.state().views.keys()].sort().concat([LJS.state().m.jobs.summary])"
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": read}], WIDE, model=m,
              seed={"view/jobs": old, "view/brief": {"made_at": "2026-10-25T07:30:00Z", "data": m["brief"]}, "view/list~people~1": lists})
    # Older than the page's own copy (made 08:00): never sent again. The whole lists always are.
    assert got["after"][0]["eval"][:-1] == ["list~people~1"], got["after"][0]["eval"]
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": read}], WIDE, model=m, seed={"view/jobs": new, "view/list~people~1": lists})
    assert got["after"][0]["eval"] == ["jobs", "list~people~1", "A newer search: 2 worth a look."], got["after"][0]["eval"]


# ------------------------------------------------------------------ 5: the page's own link

def test_open_on_another_device_gives_the_pages_own_link(run, tmp_path):
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    url = "https://claude.ai/code/artifact/00000000-0000-4000-8000-000000000001"
    with open(os.path.join(prof, "app.json"), "w", encoding="utf-8") as fh:
        json.dump({"url": url, "published_at": "2026-10-20T08:00:00Z"}, fh)
    state = app_state.small(str(tmp_path / "state"))
    out = str(tmp_path / "model.json")
    env = dict(os.environ, LJS_PROFILE=prof, LJS_STATE=state, LJS_COPY="private")
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "app.py"), "model", "--now", NOW, "--out", out],
                   env=env, check=True, capture_output=True)
    with open(out, encoding="utf-8") as fh:
        assert json.load(fh)["app"]["url"] == url
    m = _sample()
    m["app"] = dict(m["app"], url=url)
    got = _go(run, tmp_path, [{"hash": "settings", "open": "info-sum:device-link", "read": '[data-k="det:info:device-link"]'}], PHONE, model=m)
    text = got["after"][0]["text"]
    assert url in text and "Copy link" in text and "arrives with the next update" not in text, text


# ------------------------------------------------------------------ 6 and 22: Where Claude works

ADVANCED = "(() => { document.querySelectorAll('details.set-advanced').forEach((d) => { d.open = true; }); return 1; })()"


def test_where_claude_works_counts_the_rows_it_shows_and_reading_profiles_is_one_row(run, tmp_path):
    m = _sample()
    m["where"] = dict(m["where"], computer={"state": "ready", "say": "Answers only what needs your computer."})
    m["where"]["tidied"] = {"count": 1, "on": "2026-10-20"}
    read = ("(() => ({value: document.querySelector('[data-k=\"info-sum:where\"] .set-value').textContent,"
            " rows: [...document.querySelectorAll('.where-list > li[data-where]')].map((x) => x.dataset.where),"
            " tidied: (document.querySelector('.where-tidied') || {}).textContent || ''}))()")
    got = _go(run, tmp_path, [{"hash": "settings", "eval": ADVANCED}, {"open": "info-sum:where", "eval": read}], WIDE, model=m)
    r = got["after"][1]["eval"]
    assert r["rows"] == ["helper", "computer"], r
    assert r["value"] == "Ready", r
    # 12: one chat is "it".
    assert "1 old chat" in r["tidied"] and "Bring it back" in r["tidied"] and "them" not in r["tidied"], r
    # 22: the one row for reading profiles says whether it works, and Ready is never followed
    # by "open this page in the Claude app to check it".
    m["settings"] = m["settings"] + [{"id": "setting-profile_reads", "key": "profile_reads", "label": "Reading LinkedIn profiles", "kind": "choice",
                                      "value": "browser", "choices": [["browser", "Claude reads them"], ["paste", "I paste them"]], "rev": "pr1"}]
    m["linkedin"] = dict(m.get("linkedin") or {}, reading=dict((m.get("linkedin") or {}).get("reading") or {}, ok=True, page_reads=True))
    got = _go(run, tmp_path, [{"hash": "settings", "open": "set-sum:profile_reads", "read": '[data-k="det:set:profile_reads"]'}], PHONE, model=m)
    row = got["after"][0]["text"]
    assert "Claude reads them · Ready" in row and "to check it" not in row, row


# ------------------------------------------------------------------ 7 and 8: nobody listening

def _waiting():
    return {"work/search~late": {"kind": "search", "title": "Finding jobs", "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:30:00Z",
                                 "status": "queued", "stages": [], "stage": 0, "stage_at": None, "steps": [], "claimed_by": None,
                                 "claimed_at": None, "stop_asked": False, "attempt": 1},
            "meta/listener": {"chat": "cloud-1", "title": "Job search helper", "kind": "cloud", "answered_at": "2026-10-25T07:30:00Z", "watching": True}}


def test_claude_not_listening_is_said_in_the_header_and_its_card_has_no_bin(run, tmp_path):
    read = ("(() => ({bins: document.querySelectorAll('[data-item=\"listen\"] .hide-x').length, conn: document.getElementById('conn').getAttribute('data-state'),"
            " dot: document.getElementById('conn').textContent, pulse: document.getElementById('pulse').hidden ? '' : document.getElementById('pulse').textContent,"
            " kind: document.querySelector('[data-item=\"listen\"] .kind').textContent}))()")
    hide = ("(() => { localStorage.setItem('ljs:hidden', JSON.stringify({listen: Date.now() + 6e8})); LJS.render();"
            " return document.querySelectorAll('#main [data-item=\"listen\"]').length; })()")
    got = _go(run, tmp_path, [{"hash": "todo", "eval": read}, {"eval": hide}], PHONE, seed=_waiting(), clock="2026-10-25T09:00:00Z")
    r = got["after"][0]["eval"]
    assert r["bins"] == 0 and r["kind"] == "Claude", r
    # The header's dot says it; the line under the header no longer says it again beside the
    # card (the maintainer, 2026-11-04: "Why is there a top Open Claude link").
    assert r["conn"] == "unheard" and "Claude isn't listening right now" in r["dot"], r
    assert "listening" not in r["pulse"], r
    assert got["after"][1]["eval"] == 1, "a week's hiding from before cannot hide it either"


# ------------------------------------------------------------------ 9: read only here

def test_a_read_only_view_says_so_once_at_the_tap_and_changes_nothing(run, tmp_path):
    m = _sample()
    m["made_at"] = "2026-10-22T08:00:00Z"     # days old: Refresh would ask Claude, and cost
    tips = "document.getElementById('set-tips').checked"
    got = _go(run, tmp_path, [
        {"hash": "settings", "click": "Tips now and then", "role": "switch", "exact": True, "wait": 900,
         "eval": "[" + tips + ", document.querySelectorAll('#main .state').length, document.getElementById('toasts').textContent]"},
        {"hash": "jobs", "click": "Draft this: Harbourline Bank, Pricing Analyst", "wait": 300, "calls": "comments",
         "eval": "document.getElementById('toasts').textContent"},
        {"eval": "(() => { document.querySelector('[data-k=\"conn\"]').click(); return !!document.getElementById('refresh-cost'); })()"},
    ], PHONE, model=m, fake={"caps": ["user"]})
    on, lines, toast = got["after"][0]["eval"]
    assert on is True, "the switch goes back to what is saved"
    assert lines == 0, "no inline 'Not saved' under the row as well"
    assert "Read only here" in toast, toast
    assert "Read only here" in got["after"][1]["eval"] and not got["after"][1]["calls"], "nothing rung for work that cannot be asked"
    assert got["after"][2]["eval"] is False, "no cost shown for a Refresh that cannot run"


# ------------------------------------------------------------------ 10, 25, 27, 28: Your search in plain words

def test_your_search_is_said_in_plain_words(tmp_path, monkeypatch):
    prof = app_state.profile_copy(str(tmp_path / "profile"))
    state = app_state.small(str(tmp_path / "state"))
    with open(os.path.join(prof, "boards.py"), "w", encoding="utf-8") as fh:
        fh.write('BOARDS = {"Harbourline Bank": "greenhouse", "Kestrel Mutual": "lever", "Ellerwick Trust": "workday"}\n')
    os.makedirs(os.path.join(state, "job_scraper"), exist_ok=True)
    with open(os.path.join(state, "job_scraper", "do_not_target.json"), "w", encoding="utf-8") as fh:
        json.dump([{"company": "Kestrel Mutual", "reason": "turned down"}], fh)
    monkeypatch.setenv("LJS_PROFILE", prof)
    monkeypatch.setenv("LJS_STATE", state)
    import app_model
    import person
    import portals
    for mod in (person,):
        if hasattr(mod, "_cache"):
            mod._cache.clear()
    monkeypatch.setattr(portals, "url", lambda name, root=None: "https://www.builtexample.com/jobs" if name == "builtexample-search" else "")
    assert app_model.portal_label("builtexample-search") == "builtexample.com"
    assert app_model.portal_label("linkedin-search") == "LinkedIn"
    seen = {"https://jobs.example/1": {"status": "excluded", "basis": "person", "exclusion_reason": "Harbourline Bank: not this one",
                                       "title": "Senior Analyst, Credit Risk &amp; Collections", "company": "Harbourline Bank", "date": "2026-10-20"},
            "https://jobs.example/2": {"status": "excluded", "basis": "person", "exclusion_reason": "cleared from the list at the person's request",
                                       "title": "Demand Planner", "company": "Ellerwick Trust", "date": "2026-10-19"}}
    ctx = types.SimpleNamespace(seen=seen, today=dt.date(2026, 10, 25))
    s = app_model._search(ctx, {})
    by = {r["words"]: r for r in s["rules"]}
    assert by["harbourline bank"]["label"] == "Harbourline Bank"
    assert by["harbourline bank"]["examples"] == ["Senior Analyst, Credit Risk & Collections at Harbourline Bank"]
    assert by["cleared from the list at the person's request"]["label"] == "Cleared from the list at the person's request"
    assert [b["employer"] for b in s["boards"]] == ["Ellerwick Trust", "Harbourline Bank"] and s["boards_left_out"] == 1
    assert "robots" not in json.dumps(s["portals"]) and "crawlers" not in json.dumps(s["portals"])


def test_jobs_you_hid_names_them_plainly_and_asks_before_bringing_back_hundreds(run, tmp_path):
    m = _sample()
    m["search"] = dict(m["search"], rules=[
        {"id": "rule-hidden", "words": "cleared from the list at the person's request", "label": "Hidden by you", "count": 233, "basis": "person",
         "examples": ["Demand Planner at Ellerwick Trust"], "rev": "rr1"},
        {"id": "rule-quayside", "words": "quayside foods", "label": "Quayside Foods", "count": 2, "basis": "person", "examples": [], "rev": "rr2"}],
        boards=[{"employer": "Employer %03d" % i, "system": "greenhouse"} for i in range(106)], boards_left_out=6,
        pay={"floor": 105000, "target": 120000, "currency": "CAD"})
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:search-rules", "read": '[data-k="det:info:search-rules"]'},
        {"click": "Bring back: Hidden by you", "read": "dialog[open]"},
        {"click": "Cancel", "within": "dialog[open]"},
        {"open": "info-sum:search-boards", "read": '[data-k="det:info:search-boards"]', "count": '[data-k="det:info:search-boards"] li'},
        {"open": "info-sum:search-pay", "read": '[data-k="det:info:search-pay"]'},
    ], PHONE, model=m)
    rules = got["after"][0]["text"]
    assert rules.startswith("Jobs you hid") and "235 jobs" in rules and "Hidden by you: 233 jobs" in rules and "Quayside Foods: 2 jobs" in rules, rules
    assert "Bring back 233 jobs?" in got["after"][1]["dialog"] and not [a for a in got["actions"] if a["action"] == "rule.lift"], "asked first"
    follow = got["after"][3]
    assert follow["count"] == 12 and "94 more employers" in follow["text"] and "6 employers you ruled out are not followed" in follow["text"], follow
    pay = got["after"][4]["text"]
    assert "At least CAD 105,000, hoping for CAD 120,000" in pay and "flagged as under what you would take" in pay, pay


# ------------------------------------------------------------------ 11: the keyboard list

def test_the_keyboard_list_is_the_places_that_work(run, tmp_path):
    press = ("(() => { document.dispatchEvent(new KeyboardEvent('keydown', {key: '?', bubbles: true}));"
             " return (document.querySelector('dialog[open]') || {}).textContent || ''; })()")
    got = _go(run, tmp_path, [{"hash": "todo", "eval": press}], WIDE)
    keys = got["after"][0]["eval"]
    for words in ("g then b", "Brief", "g then y", "Your profile", "Drafts, in Jobs", "g then i", "Coming up"):
        assert words in keys, (words, keys)


# ------------------------------------------------------------------ 13, 14, 26: you and what you taught it

def test_the_profile_summary_counts_roles_degrees_and_certificates(run, tmp_path):
    m = _sample()
    m["you"] = dict(m["you"], jobs=[dict(m["you"]["jobs"][0], id="you-job-%d" % i) for i in range(4)], skills=["SQL", "Python", "Excel", "R", "dbt"],
                    education=["BSc Mathematics, University of Leeds, UK (2016-2019)"], certificates=["One", "Two", "Three"])
    got = _go(run, tmp_path, [{"hash": "settings", "read": '[data-k="open-profile"]'}], PHONE, model=m)
    assert "4 roles · 5 skills · 1 degree · 3 certificates" in got["after"][0]["text"], got["after"][0]["text"]


def test_what_you_taught_it_opens_on_the_newest_five_with_a_search_and_speaks_to_you(run, tmp_path):
    m = _sample()
    m["learned"] = [{"id": "learned-%d" % i, "area": "messages", "rule": "Rule number %d about notes" % i, "say": "Rule number %d about notes" % i,
                     "said": "", "on": "2026-10-%02d" % (1 + i % 24), "retired": False, "rev": "l%d" % i} for i in range(30)]
    m["learned"][0].update(rule="Answer the question he actually asked", say="Answer the question you actually asked", on="2026-10-24")
    got = _go(run, tmp_path, [{"hash": "settings", "open": "info-sum:learned", "read": '[data-k="det:info:learned"]',
                               "count": '[data-k="det:info:learned"] .learned', "eval": "!!document.getElementById('q-learned')"}], PHONE, model=m)
    r = got["after"][0]
    assert r["count"] == 5 and "25 more rules" in r["text"] and r["eval"], (r["count"], r["text"][:300])
    assert "Answer the question you actually asked" in r["text"] and "he actually asked" not in r["text"]


def test_a_rule_written_about_the_person_is_said_to_them():
    import app_model
    say = app_model.to_person
    assert say("Answer the question he actually asked.") == "Answer the question you actually asked."
    assert say("The candidate wants a yes or no first.") == "You want a yes or no first."
    assert say("He prefers short notes; his voice is plain.") == "You prefer short notes; your voice is plain."
    assert say("Morgan's resume never names clients; he always asks first.", "Morgan") == "Your resume never names clients; you always ask first."
    assert say("Ask Morgan before sending.", "Morgan") == "Ask you before sending."
    # Where someone else could be meant, he and him are left as written.
    assert say("If the contact replies, thank him.") == "If the contact replies, thank him."


def test_the_briefs_usual_is_only_rules_about_the_brief(run, tmp_path):
    m = _sample()
    m["learned"] = [{"id": "learned-1", "area": "other", "rule": "Answer the question he actually asked", "say": "Answer the question you actually asked",
                     "said": "", "on": "2026-10-20", "retired": False, "rev": "l1"},
                    {"id": "learned-2", "area": "other", "rule": "The brief leads with interviews", "say": "The brief leads with interviews",
                     "said": "", "on": "2026-10-21", "retired": False, "rev": "l2"}]
    # The rules kept sit under "Keeping 1 rule of yours", opened as a person opens it: the panel
    # was read whole only while it was hidden in the rail (2026-11-05).
    got = _go(run, tmp_path, [{"hash": "brief", "click": "Edit the brief"}, {"open": "tweak-usual", "read": ".tweak-panel"}], WIDE, model=m)
    panel = got["after"][1]["text"]
    assert "Keeping 1 rule of yours" in panel and "The brief leads with interviews" in panel and "Answer the question" not in panel, panel


def test_a_tweak_panel_opened_on_a_wide_screen_shows_at_once(run, tmp_path):
    # Opened once the page had settled, the panel went into a rail hidden for having nothing to
    # show and stayed hidden until something else drew the page (2026-11-05).
    shown = "(() => { const p = document.querySelector('.tweak-panel'); return !!(p && p.getClientRects().length); })()"
    got = _go(run, tmp_path, [{"hash": "brief", "wait": 2500}, {"click": "Edit the brief", "eval": shown}], WIDE)
    assert got["after"][1]["eval"] is True


# ------------------------------------------------------------------ 15, 16, 17, 21: reach and focus

def test_save_stays_in_reach_on_a_long_list_of_roles(run, tmp_path):
    m = _sample()
    m["search"] = dict(m["search"], roles=["Analyst role %d" % i for i in range(73)])
    where = ("(() => { const d = document.querySelector('dialog[open]'); const s = d.querySelector('[data-k=\"sheet-go\"]');"
             " const a = d.__drawnRect(), b = s.__drawnRect(); return {inside: b.top >= a.top && b.bottom <= a.bottom + 1, scrolls: d.scrollHeight > d.clientHeight}; })()")
    got = _go(run, tmp_path, [{"hash": "settings", "open": "info-sum:search-roles"}, {"click": "Change", "within": '[data-k="det:info:search-roles"]', "eval": where}], PHONE, model=m)
    r = got["after"][1]["eval"]
    assert r["scrolls"] and r["inside"], r


TARGETS = ("(() => { const z = parseFloat(document.body.style.zoom) || 1; const out = [];"
           " for (const el of document.querySelectorAll('#side a, #main .btn:not(.link), .seg-opt, .sum .help-q, .gear')) {"
           " const r = el.__drawnRect(); if (!r.width || !r.height) continue; const a = getComputedStyle(el, '::after');"
           " const extra = a.content !== 'none' && a.position === 'absolute' ? Math.max(0, -parseFloat(a.top) || 0) + Math.max(0, -parseFloat(a.bottom) || 0) : 0;"
           " const h = r.height + extra * z; if (h < 43.5) out.push((el.dataset.k || el.className) + ':' + Math.round(h)); } return out; })()")


@pytest.mark.parametrize("width", [768, 1024])
def test_a_touch_tablet_gets_a_full_finger_target(run, tmp_path, width):
    got = _go(run, tmp_path, [{"hash": "settings", "eval": TARGETS}, {"hash": "todo", "eval": TARGETS}], {"width": width, "height": 1024}, touch=True)
    for step in got["after"]:
        assert step["eval"] == [], step["eval"][:12]


def test_see_every_change_has_a_full_target_on_a_phone(run, tmp_path):
    m = _sample()
    m["updates"] = dict(m.get("updates") or {}, changelog="https://github.com/morgan-example/job-search/blob/master/CHANGELOG.md")
    size = "(() => { const a = document.querySelector('[data-k=\"changelog\"]'); return a ? Math.round(a.__drawnRect().height) : null; })()"
    got = _go(run, tmp_path, [{"hash": "settings", "open": "info-sum:news", "eval": size}], PHONE, model=m)
    assert got["after"][0]["eval"] is not None and got["after"][0]["eval"] >= 43, got["after"][0]["eval"]


def test_the_briefs_greeting_has_no_focus_ring_like_every_screen_title(run, tmp_path):
    ring = "(() => { const t = document.querySelector('#main .brief-hello .screen-title'); t.focus(); return getComputedStyle(t).outlineStyle; })()"
    got = _go(run, tmp_path, [{"hash": "brief", "eval": ring}], WIDE)
    assert got["after"][0]["eval"] == "none"


# ------------------------------------------------------------------ 18, 19, 20: the frame

def test_the_wide_rail_shows_only_while_claude_has_work(run, tmp_path):
    rail = "getComputedStyle(document.getElementById('rail')).display"
    got = _go(run, tmp_path, [{"hash": "todo", "eval": rail}], WIDE)
    assert got["after"][0]["eval"] == "none", "Nothing running: no column saying so"
    busy = {"work/search~1": {"kind": "search", "title": "Finding jobs", "to": "cloud", "args": {}, "asked_at": "2026-10-25T09:20:00Z", "status": "running",
                              "claimed_by": "cloud-1", "claimed_at": "2026-10-25T09:20:00Z", "stages": [{"name": "Searching", "est_s": 300}], "stage": 0,
                              "stage_at": "2026-10-25T09:20:00Z", "steps": [], "stop_asked": False, "attempt": 1}}
    got = _go(run, tmp_path, [{"hash": "todo", "eval": rail, "read": "#rail"}], WIDE, seed=busy)
    assert got["after"][0]["eval"] != "none" and "Finding jobs" in got["after"][0]["text"]


def test_on_a_phone_the_gear_says_you_are_on_settings_and_the_footer_is_the_privacy_line(run, tmp_path):
    cur = "(() => [document.querySelector('[data-k=\"gear\"]').getAttribute('aria-current'), document.querySelectorAll('#foot a').length, document.getElementById('foot').textContent])()"
    got = _go(run, tmp_path, [{"hash": "settings", "eval": cur}, {"hash": "profile", "eval": cur}, {"hash": "todo", "eval": cur}], PHONE)
    assert [s["eval"][0] for s in got["after"]] == ["page", "page", None]
    for s in got["after"]:
        assert s["eval"][1] == 0 and "Private to you." in s["eval"][2], s["eval"]


# ------------------------------------------------------------------ 24, 30, R9, R14: fewer and plainer controls

def test_a_search_months_in_is_not_offered_the_tour_and_settings_say_what_they_hold(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "todo", "count": '#main [data-item="tour"]'},
        {"hash": "settings", "eval": ("(() => [...document.querySelectorAll('#main .set-group > h3.group, #main .set-advanced > summary')].map((x) => x.textContent.trim()))()"),
         "read": "#main .summary"},
        {"eval": "(() => [getComputedStyle(document.querySelector('.set-advanced > summary'), '::after').content, document.getElementById('set-tips').getAttribute('role'), document.getElementById('size-name').textContent])()"},
    ], WIDE)
    assert got["after"][0]["count"] == 0, "a search with applications is not new"
    groups = got["after"][1]["eval"]
    assert "Appearance" in groups and "Look" not in groups, groups
    assert "usual" not in got["after"][1]["text"], got["after"][1]["text"]
    mark, tips, size = got["after"][2]["eval"]
    assert mark in ('""', "none") and tips == "switch" and size == "Text size", (mark, tips, size)


def test_an_update_is_one_moving_line_with_no_stop(run, tmp_path):
    """31: the header said an update twice (a pill and a line) and its work offered Stop."""
    update = {"work/update~1": {"kind": "update", "title": "Updating to the newest version", "to": "cloud", "args": {}, "asked_at": "2026-10-25T09:20:00Z",
                                "status": "running", "claimed_by": "cloud-1", "claimed_at": "2026-10-25T09:20:00Z", "stages": [{"name": "Updating", "est_s": 300}],
                                "stage": 0, "stage_at": "2026-10-25T09:20:00Z", "steps": [], "stop_asked": False, "attempt": 1}}
    read = "(() => [document.querySelectorAll('#pill').length, document.getElementById('pulse').textContent, document.querySelectorAll('[data-k^=\"stop:\"]').length])()"
    got = _go(run, tmp_path, [{"hash": "todo", "eval": read}], PHONE, seed=update)
    pills, pulse, _ = got["after"][0]["eval"]
    assert pills == 0 and "Updating to the newest version" in pulse, (pills, pulse)
    got = _go(run, tmp_path, [{"hash": "todo", "eval": read}], WIDE, seed=update)
    assert got["after"][0]["eval"][2] == 0, "no Stop on an update"


def test_keyboard_shortcuts_are_not_offered_where_there_is_no_keyboard(run, tmp_path):
    keys = ("(() => { document.querySelectorAll('details.set-advanced').forEach((d) => { d.open = true; });"
            " return !!document.getElementById('keys-on'); })()")
    got = _go(run, tmp_path, [{"hash": "settings", "eval": keys}], {"width": 768, "height": 1024}, touch=True)
    assert got["after"][0]["eval"] is False
    got = _go(run, tmp_path, [{"hash": "settings", "eval": keys}], WIDE)
    assert got["after"][0]["eval"] is True


def test_the_menu_fold_is_its_own_section_at_the_top_settings_is_last_and_an_empty_fortnight_is_one_line(run, tmp_path):
    """The fold left the menu's foot (the maintainer, 2026-11-05: a second divider and an empty
    block under Settings), then the page's title ("in its own section (like settings) above
    them saying icons only, not near the name"): it is the menu's first row, a row like the
    others, and Settings is the menu's last."""
    m = _sample()
    m["interviews"] = []
    m["upcoming"] = []
    order = ("(() => { const s = document.getElementById('side'); const c = [...s.querySelectorAll('a, button')];"
             " const t = c[0]; return [c[c.length - 1].dataset.k, t.dataset.k, t.textContent.trim(), t.tagName,"
             " !!document.querySelector('#top [data-k=\"side-toggle\"]'), t.closest('ul').classList.contains('side-head')]; })()")
    got = _go(run, tmp_path, [{"hash": "brief", "eval": order, "count": '[data-k^="week:"]', "read": '#main [data-k="bp-up-add"]'}], WIDE, model=m)
    assert got["after"][0]["eval"] == ["side:settings", "side-toggle", "Icons only", "BUTTON", False, True], \
        got["after"][0]["eval"]
    assert got["after"][0]["count"] == 0 and got["after"][0]["text"] == "Add something"
