"""The page's design language, held on every screen (templates/app/DESIGN.md).

The maintainer, 2026-10-29: "why are some Xs and some bins?", "there's a lot of ? on one of
the draft screenshots", "why do some things show up indents and messy and some things are
bubbles?". Each rule is measured in a browser on every screen, on a phone and wide, light and
dark, over the sample with every kind of item: one "?" a card at most; no x on any card,
since the bin is the one way to put something away; no line drawn down the side of anything;
and every live job, draft, message, person, interview and application carries the bin.
Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_the_page_journeys import _sample, browser  # noqa: E402
from test_the_page_works_in_a_browser import _write  # noqa: E402

SIZES = {"phone": {"width": 375, "height": 812}, "wide": {"width": 1440, "height": 900}}


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    return _write(tmp_path_factory.mktemp("design"), "sample", _sample())


@pytest.mark.parametrize("vp", ["phone", "wide"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_every_screen_keeps_the_design_language(run, page, vp, scheme):
    got = run("design", html=page, viewport=SIZES[vp], scheme=scheme, clock="2026-10-25T09:00:00Z")
    assert not got["errors"], got["errors"]
    assert got["sections"], "nothing was measured"
    bad = {sec: {rule: hits for rule, hits in v.items() if hits} for sec, v in got["sections"].items()}
    bad = {sec: v for sec, v in bad.items() if v}
    assert not bad, bad


# ------------------------------------------------------------------ each bin writes the right record

from test_the_page_journeys import PHONE, _go, _one  # noqa: E402

T = "2026-10-25T09:00:00Z"


def _old_and_closed():
    """The Ellerwick draft's posting closed, and up for four months: the two reasons the bin
    offers only where they are true."""
    m = _sample()
    a = next(x for x in m["ready"] if x["id"] == "app-ellerwick-insight")
    a["apply"] = dict(a["apply"], status="closed")
    next(r for r in m["jobs"]["rows"] if r["id"] == a["job"])["posted_days"] = 120
    return m


# The Jobs bin's reasons, each a button that acts in the tap (2026-11-03: a reason already chosen
# and then "Done" took two taps), each sent as the engine reads it (tests/test_every_bin_choice_changes
# _what_it_says.py applies each one); only the employer choice turns the employer down. "Posted too
# long ago" and "It has closed" are offered only where they are true.
@pytest.mark.parametrize("pick,why,toast,model", [
    ("Not this one", "not this role", "Not applying: Ellerwick Trust", None),
    ("The pay", "pay", "Not applying: Ellerwick Trust", None),
    ("The place", "place", "Not applying: Ellerwick Trust", None),
    ("Not my field", "field", "Not applying: Ellerwick Trust", None),
    ("Posted too long ago", "old", "Not applying: Ellerwick Trust", _old_and_closed),
    ("No more from Ellerwick Trust", "employer", "No more roles from Ellerwick Trust", None),
    ("It has closed", "closed", "Not applying: Ellerwick Trust", _old_and_closed),
])
def test_a_drafts_bin_says_why_it_is_not_going_out(run, tmp_path, pick, why, toast, model):
    got = _go(run, tmp_path, [
        {"hash": "drafts", "open": "dbin:app-ellerwick-insight", "read": "dialog[open]"},
        {"click": pick, "exact": True, "within": "dialog",
         "ready": "[...document.querySelectorAll('[data-toast]')].some((t) => t.textContent.includes(%r))" % toast},
    ], PHONE, clock=T, model=model() if model else None)
    sheet = got["after"][0]["text"]
    assert "Not sending this one?" in sheet
    assert ("It has closed" in sheet and "Posted too long ago" in sheet) == bool(model), "offered only where true"
    assert "Already applied" not in sheet, "I have applied is on the draft's own face, never in the bin too"
    a = _one(got, "ready.not_applying")
    assert a["item"] == "app-ellerwick-insight" and a["value"] == {"why": why}


def test_a_messages_bin_sets_the_note_aside_first(run, tmp_path):
    got = _go(run, tmp_path, [
        # The note is on Ash's card in Contacts (2026-11-04): its one trash, the person's.
        {"hash": "contacts", "open": "pbin:copperleaf_pay_ash", "read": "dialog[open]"},
        {"click": "Not now: set this note aside", "exact": True, "within": "dialog", "wait": 300},
    ], PHONE, clock=T)
    assert "Not now: set this note aside" in got["after"][0]["text"]
    assert _one(got, "msg.skip")["item"] == "msg-ash-1"
    assert not [x for x in got["actions"] if x["action"] == "person.stop"]


def test_an_interviews_bin_records_how_it_ended(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews/int-harbourline-risk", "open": "ivbin:int-harbourline-risk", "read": "dialog[open]"},
        {"click": "I withdrew", "exact": True, "within": "dialog", "wait": 300},
    ], PHONE, clock=T)
    # An interview moved or called off is its own choice, first (the audit, 2026-11-03).
    assert "What happened to the" in got["after"][0]["text"] and "Harbourline" in got["after"][0]["text"]
    assert "It was moved or cancelled" in got["after"][0]["text"]
    a = _one(got, "outcome.withdrawn")
    assert a["item"] == "int-harbourline-risk" and a["value"]["on"]


def test_a_to_do_card_about_one_person_offers_their_choices_and_a_week_off(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "todo", "count": "#main .hide-x svg path[d='M7 7l10 10M17 7L7 17']"},
    ], PHONE, clock=T)
    assert got["after"][0]["count"] == 0, "no x on To do: the bin, as everywhere"


def test_a_reply_never_offers_to_set_it_aside_which_the_engine_would_refuse(run, tmp_path):
    # state.py drop refuses anyone already written to, so "set aside" is for first notes only.
    got = _go(run, tmp_path, [
        {"hash": "contacts", "open": "pbin:larkspur_retail_castellan", "read": "dialog[open]"},
    ], PHONE, clock=T)
    sheet = got["after"][0]["text"]
    assert "Not Juno?" in sheet and "set this note aside" not in sheet


# ------------------------------------------------------------------ a name starts with what it shows

# WCAG 2.5.3, Label in Name: a speech user says the words they see. Every control's accessible
# name starts with its visible words, on every screen and in every card's sheet, with each fold
# and menu open (the accessibility review of the redesign's second round, 2026-11-17: "Take it
# off" was named "Take off: ...", a "More" "Show all of the ...", "They sent me a job" "<name>
# sent me a job", "Latest" "Go to the latest message"). The name is worked out as a screen
# reader does: aria-label, else the words inside, leaving out what is hidden from it, with a
# picture's own name; the visible words leave out what is only for a screen reader.
LABEL_IN_NAME = r"""(() => {
  const root = document.querySelector('dialog[open]') || document.querySelector('#main');
  const vis = (e) => e.getClientRects().length > 0 && e.checkVisibility({visibilityProperty: true});
  const norm = (t) => t.toLowerCase().replace(/’/g, "'").replace(/[^a-z0-9'£%]+/g, '');
  const shown = (el) => { let t = ''; for (const c of el.childNodes) { if (c.nodeType === 3) t += ' ' + c.textContent;
    else if (c.nodeType === 1 && !c.matches('.sr-only, [aria-hidden="true"], svg, [hidden], [role="tooltip"]') && getComputedStyle(c).display !== 'none') t += ' ' + shown(c); } return t; };
  const named = (el) => { let t = ''; for (const c of el.childNodes) { if (c.nodeType === 3) t += ' ' + c.textContent;
    else if (c.nodeType === 1 && c.getAttribute('aria-hidden') !== 'true' && !c.matches('svg, [hidden], [role="tooltip"]')) t += ' ' + (c.getAttribute('role') === 'img' ? c.getAttribute('aria-label') || '' : named(c)); } return t; };
  const bad = [];
  for (const el of root.querySelectorAll('button, a[href], summary, [role="button"], [role="link"], [role="radio"], [role="tab"]')) {
    if (!vis(el) || el.getAttribute('aria-labelledby')) continue;
    const v = norm(shown(el));
    const n = norm(el.getAttribute('aria-label') || named(el));
    if (v && n && !n.startsWith(v)) bad.push(shown(el).replace(/\s+/g, ' ').trim() + ' => ' + (el.getAttribute('aria-label') || named(el).replace(/\s+/g, ' ').trim()));
  }
  return [...new Set(bad)];
})()"""
OPEN_ALL = ("(() => { const ds = [...(document.querySelector('dialog[open]') || document.querySelector('#main')).querySelectorAll('details')];"
            " ds.forEach((d) => { d.open = true; }); return ds.length; })()")
SCREENS = ["brief", "todo", "jobs", "applied", "contacts", "interviews", "progress", "chat", "settings", "profile"]
SHEETS = ["contacts/copperleaf_pay_tamsin/open", "contacts/fernhill_freight_halloway/open", "interviews/int-copperleaf-payments/open",
          "interviews/int-larkspur-supply/open", "jobs/app-fernhill-ops/open", "jobs/emp~larkspur-retail/open", "interviews/emp~copperleaf-pay/open",
          "interviews/prep~int-larkspur-supply/open", "past job"]
PAST_JOB = "you-job:you-job-Brindle---Hart-Logistics-Senior-Operations-Analyst"


@pytest.mark.parametrize("vp", [PHONE, SIZES["wide"]], ids=["phone", "wide"])
def test_every_controls_name_starts_with_the_words_it_shows(run, tmp_path, vp):
    bad, opened = {}, 0
    for where in SCREENS + SHEETS:
        # Every fold and menu open first: a row's More draws its items once it is opened.
        step = {"hash": "jobs", "open": "jobsw:applied", "eval": OPEN_ALL} if where == "applied" else \
            {"hash": "profile", "open": PAST_JOB, "eval": OPEN_ALL} if where == "past job" else {"hash": where, "eval": OPEN_ALL}
        got = _go(run, tmp_path, [step, {"wait": 300, "eval": LABEL_IN_NAME}], vp, clock=T)
        opened += got["after"][0]["eval"] or 0
        if got["after"][1]["eval"]:
            bad[where] = got["after"][1]["eval"]
    assert opened > 10, "the folds and menus were opened"
    assert not bad, bad
