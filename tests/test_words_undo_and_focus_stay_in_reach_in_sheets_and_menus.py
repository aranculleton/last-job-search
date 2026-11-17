"""Words, Undo and focus stay in reach inside sheets and menus (WCAG 2.2 AA; the accessibility
review of the redesign's second round, 2026-11-17, must-fix 1, 2 and 4).

- A sheet opened with showModal() makes the rest of the page inert, and what the page said (its
  polite and its urgent line) and its toasts sat outside every sheet: inside a person's card
  "No longer waiting for Tamsin" was said to no one and its Undo could not be reached (4.1.3,
  2.1.1).
- Choosing from a menu (a person's Update, a list's ⋯, a Coming up row's More) closed the menu
  round the item chosen, so the browser dropped the focus to nothing, and the sheet the item
  opened handed it back to that hidden item (2.4.3).
- A menu floating over the next row stayed open: Tab from its last item put the focus under it,
  and Escape closed only a card's More (2.4.11).

The rules are DESIGN.md's ("Buttons, links and taps": a menu closes once it is left, and the
focus never falls to nothing; "Moving parts": what the page says aloud and its toasts are in the
top open sheet). Every person and employer is the sample's, invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
TAMSIN = "copperleaf_pay_tamsin"
CARD = "contacts/" + TAMSIN + "/open"
CARD_OPEN = "!!document.querySelector('dialog.detail[open] .d-person')"
EVENT = "up-ev20261020120000"
SCREEN = "up-app-larkspur-supply-phone-screen-2026-10-28"


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def test_design_md_holds_both_rules():
    with open(os.path.join(ROOT, "templates", "app", "DESIGN.md"), encoding="utf-8") as fh:
        doc = " ".join(fh.read().split())
    for phrase in ("A menu closes once it is left, and the focus never falls to nothing.",
                   "closes on Escape with the focus on its own button, when the focus moves on to something outside it, and on a tap beside it",
                   "Choosing an item closes its menu and puts the focus on the menu's button before the item does anything",
                   "the focus goes to the button of the menu, fold or More it is hidden in, else to its card, never to nothing",
                   "What the page says aloud (its polite line and its urgent one) and its toasts are in the top open sheet while a sheet is open, and on the page once none is."):
        assert phrase in doc, phrase


# Where the focus is: its key, whether it is drawn, whether it is in an open sheet, and whether
# the browser dropped it to the page itself.
FOCUS = r"""(() => { const a = document.activeElement;
  if (!a || a === document.body || a === document.documentElement) return {k: null, body: true};
  const shown = a.checkVisibility ? a.checkVisibility() : a.getClientRects().length > 0;
  return {k: a.getAttribute('data-k') || a.id || a.tagName, shown, body: false, inSheet: !!a.closest('dialog[open]'),
    inMain: !!a.closest('#main'), menuOpen: !!a.closest('details[open]')}; })()"""


# What a person in the top sheet can hear and reach: the toast with these words, whether its
# buttons are hit where they are drawn, and the words of the polite and urgent lines inside it.
def _heard(words):
    return r"""(() => {
  const open = [...document.querySelectorAll('dialog[open]')]; const top = open[open.length - 1] || null;
  const toast = [...document.querySelectorAll('.toast')].find((t) => t.textContent.includes(%r)) || null;
  const hit = (b) => { const r = b.getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!e && b.contains(e); };
  const inTop = (sel) => top ? [...top.querySelectorAll(sel)].map((e) => e.textContent.trim()).filter(Boolean) : [];
  return {top: top ? (top.getAttribute('data-detail') || top.className) : null, toastInSheet: !!(top && toast && top.contains(toast)),
    buttons: toast ? [...toast.querySelectorAll('button')].filter((b) => !b.classList.contains('toast-x')).map((b) => [b.textContent.trim(), hit(b)]) : [],
    polite: inTop('[aria-live="polite"]'), urgent: inTop('[role="alert"]')};
})()""" % words


SAID = "[...document.querySelectorAll('[aria-live=\"polite\"], [role=\"alert\"]')].some((e) => e.textContent.includes(%r))"


# ------------------------------------------------------------------ A1: said and reachable in a sheet

@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_toast_and_its_undo_are_said_and_reached_inside_a_persons_card(run, tmp_path, vp):
    words = "No longer waiting for Tamsin"
    got = _go(run, tmp_path, [
        {"hash": CARD, "ready": CARD_OPEN},
        {"open": "menu:dupd:" + TAMSIN},
        {"click": "The referral is over", "within": "dialog.detail[open]", "ready": "!!document.querySelector('dialog.sheet[open]')"},
        {"click": "Not happening: stop waiting", "within": "dialog.sheet[open]",
         "ready": "!document.querySelector('dialog.sheet[open]') && " + (SAID % words), "eval": _heard(words)},
        # Undo with the mouse where it is drawn, inside the card: the tap is taken back.
        {"click": "Undo", "within": "dialog.detail[open]", "ready": SAID % "Undone", "eval": _heard("Undone")},
        # The card closed, the page's own lines and toasts are the page's again.
        {"press": "Escape", "ready": "!document.querySelector('dialog[open]')",
         "eval": "[[...document.querySelectorAll('[aria-live=\"polite\"]')].some((e) => !e.closest('dialog') && e.isConnected),"
                 " [...document.querySelectorAll('[role=\"alert\"][aria-atomic]')].some((e) => !e.closest('dialog')),"
                 " !!document.querySelector('.toasts') && !document.querySelector('.toasts').closest('dialog')]"},
    ], vp, clock=T)
    heard = got["after"][3]["eval"]
    assert heard["top"] == "person:" + TAMSIN, heard
    assert heard["toastInSheet"], heard
    assert ["Undo", True] in heard["buttons"], heard
    assert any(words in p for p in heard["polite"]), heard
    assert not [a for a in got["actions"] if a["action"] == "referral.ended"], got["actions"]
    assert any("Undone" in p for p in got["after"][4]["eval"]["polite"]), got["after"][4]["eval"]
    assert got["after"][5]["eval"] == [True, True, True], got["after"][5]["eval"]


def test_a_failure_inside_a_persons_card_is_said_at_once_with_its_try_again_in_reach(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": CARD, "ready": CARD_OPEN},
        {"open": "menu:dupd:" + TAMSIN},
        {"click": "The referral is over", "within": "dialog.detail[open]", "ready": "!!document.querySelector('dialog.sheet[open]')"},
        {"click": "Not happening: stop waiting", "within": "dialog.sheet[open]",
         "ready": "!document.querySelector('dialog.sheet[open]') && " + (SAID % "Not saved"), "eval": _heard("Not saved")},
    ], PHONE, clock=T, fake={"canSend": "available", "failWrites": True})
    heard = got["after"][3]["eval"]
    assert heard["toastInSheet"] and ["Try again", True] in heard["buttons"], heard
    assert any("Not saved" in u for u in heard["urgent"]), heard


# ------------------------------------------------------------------ A2: focus after a menu's item

@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_coming_up_rows_more_leaves_the_focus_on_its_button_after_each_choice(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "open": "up-more:" + EVENT},
        # Its first item by the keyboard: the calendar's sheet; Escape hands the focus back.
        {"press": ["Tab", "Enter"], "ready": "!!document.querySelector('dialog.cal-sheet[open]')"},
        {"press": "Escape", "ready": "!document.querySelector('dialog[open]')", "eval": FOCUS},
        # "Change the day" opens the row's day box; the focus stays on the row, never on nothing.
        {"open": "up-more:" + SCREEN, "press": ["Tab", "Tab", "Enter"], "eval": FOCUS},
    ], vp, clock=T)
    back, day = got["after"][2]["eval"], got["after"][3]["eval"]
    assert back == {"k": "up-more:" + EVENT, "shown": True, "body": False, "inSheet": False, "inMain": True, "menuOpen": False}, back
    assert not day["body"] and day["shown"] and day["inMain"] and not day["menuOpen"], day


def test_taking_a_row_off_coming_up_leaves_the_focus_on_the_screen(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "interviews", "open": "up-more:" + EVENT},
        {"press": ["Tab", "Tab", "Enter"], "ready": SAID % "Taken off", "eval": FOCUS},
    ], PHONE, clock=T)
    gone = got["after"][1]["eval"]
    assert not gone["body"] and gone["shown"] and gone["inMain"], gone


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_sheet_opened_from_a_persons_update_menu_hands_the_focus_back_to_update(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": CARD, "ready": CARD_OPEN},
        {"open": "menu:dupd:" + TAMSIN},
        {"click": "They sent me a job", "within": "dialog.detail[open]", "ready": "!!document.querySelector('dialog.sheet[open]')"},
        {"press": "Escape", "ready": "!document.querySelector('dialog.sheet[open]')", "eval": FOCUS},
    ], vp, clock=T)
    back = got["after"][3]["eval"]
    assert back == {"k": "menu:dupd:" + TAMSIN, "shown": True, "body": False, "inSheet": True, "inMain": False, "menuOpen": False}, back


def test_the_jobs_lists_menu_hands_the_focus_back_to_its_button_when_its_panel_closes(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "jobs", "open": "menu:jobs"},
        {"click": "Change the search", "ready": "!!document.querySelector('.tweak-panel')"},
        {"press": "Escape", "ready": "!document.querySelector('.tweak-panel')", "eval": FOCUS},
    ], PHONE, clock=T)
    back = got["after"][2]["eval"]
    assert back["k"] == "menu:jobs" and back["shown"] and not back["menuOpen"], back


# A redraw while a sheet is open folding away the More its button sat in: the panel hidden and its
# fold shut, as a live update can leave them.
FOLD_SHUT = r"""(() => { const p = document.querySelector('#main [data-item="%s"] .more-panel');
  const s = p && document.querySelector('[aria-controls="' + p.id + '"]'); if (!s) return null;
  s.parentElement.open = false; p.hidden = true; return s.getAttribute('data-k'); })()"""


def test_a_sheet_whose_button_was_folded_away_hands_the_focus_to_the_folds_button(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "contacts", "more": TAMSIN},
        {"click": "They sent me a job", "within": '#main [data-item="%s"]' % TAMSIN, "ready": "!!document.querySelector('dialog.sheet[open]')",
         "eval": FOLD_SHUT % TAMSIN},
        {"press": "Escape", "ready": "!document.querySelector('dialog[open]')", "eval": FOCUS},
    ], WIDE, clock=T)
    fold = got["after"][1]["eval"]
    assert fold and fold.startswith("more-sum:"), fold
    back = got["after"][2]["eval"]
    assert back["k"] == fold and back["shown"] and back["inMain"], back


# ------------------------------------------------------------------ A4: a menu closes when left

MENU = r"""(() => { const d = document.querySelector('[data-k="det:up-more:%s"]'); return d ? d.open : null; })()"""
# The focus put on a menu's last item, as Tab through it leaves it.
LAST = r"""(() => { const b = [...document.querySelectorAll('[data-k="det:up-more:%s"] .menu-item')].pop(); if (b) b.focus(); return !!b && document.activeElement === b; })()"""
UNDER = r"""(() => { const a = document.activeElement; if (!a || a === document.body) return null;
  const r = a.getBoundingClientRect(); const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return {k: a.getAttribute('data-k'), covered: !(e && (a === e || a.contains(e))), open: [...document.querySelectorAll('details:is(.menu, .more)[open]')].map((d) => d.getAttribute('data-k'))}; })()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_floating_menu_closes_on_escape_on_leaving_it_and_on_a_tap_beside_it(run, tmp_path, vp):
    rows = "[...document.querySelectorAll('#main .up-row .up-menu > summary')].map((s) => s.getAttribute('data-k'))"
    got = _go(run, tmp_path, [
        {"hash": "interviews", "eval": rows},
        # Escape on a Coming up row's More: closed, its button keeps the focus.
        {"open": "up-more:" + SCREEN, "press": ["Tab", "Escape"], "eval": "[" + (MENU % SCREEN) + ", " + FOCUS + "]"},
        # Tab on from its last item: the menu closes, so the next row's controls are never under it.
        {"press": "Enter", "eval": "[" + (MENU % SCREEN) + ", " + LAST % SCREEN + "]"},
        {"press": "Tab", "eval": UNDER},
        # A tap beside an open menu closes it.
        {"open": "up-more:" + SCREEN, "tapOn": "#main h2", "eval": MENU % SCREEN},
    ], vp, clock=T)
    order = got["after"][0]["eval"]
    assert order.index("up-more:" + SCREEN) + 1 < len(order), order
    shut, focus = got["after"][1]["eval"]
    assert shut is False and focus["k"] == "up-more:" + SCREEN and focus["shown"], (shut, focus)
    assert got["after"][2]["eval"] == [True, True], got["after"][2]["eval"]
    under = got["after"][3]["eval"]
    assert under and under["k"] and not under["open"] and not under["covered"], under
    assert got["after"][4]["eval"] is False


def test_escape_closes_a_menu_inside_a_sheet_and_never_the_sheet(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": CARD, "ready": CARD_OPEN},
        {"open": "menu:dupd:" + TAMSIN, "press": ["Tab", "Escape"],
         "eval": "[document.querySelector('details.upd-menu').open, !!document.querySelector('dialog.detail[open]'), document.activeElement.getAttribute('data-k')]"},
        # Leaving it for the card's other controls closes it too.
        {"open": "menu:dupd:" + TAMSIN, "press": ["Shift+Tab"], "eval": "document.querySelector('details.upd-menu').open"},
    ], PHONE, clock=T)
    assert got["after"][1]["eval"] == [False, True, "menu:dupd:" + TAMSIN], got["after"][1]["eval"]
    assert got["after"][2]["eval"] is False


# Where a tap on each part of each menu's and More's button lands: the button itself, or the
# part, with its button's key.
TAPS_LAND = r"""(() => { const out = [];
  for (const s of document.querySelectorAll('details:is(.menu, .more) > summary')) {
    const parts = [s, ...s.querySelectorAll('*')];
    for (const p of parts) { const r = p.getBoundingClientRect();
      if (!r.width || !r.height || r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) continue;
      const at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      if (at && s.contains(at) && at !== s) out.push([s.getAttribute('data-k'), at.tagName + '.' + (at.className && at.className.baseVal !== undefined ? at.className.baseVal : at.className)]); } }
  return out; })()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_tap_on_a_menus_button_lands_on_the_button_itself(run, tmp_path, vp):
    """Safari starts Tab from the spot a tap lands on: a tap on the ⋯ inside a Coming up row's
    button, then Option-Tab, left the focus where it was and never reached the menu's first item
    (the everywhere check, Safari, 2026-11-17). Every part of a menu's or More's button lets the
    tap through to the button."""
    got = _go(run, tmp_path, [
        {"hash": "interviews", "eval": TAPS_LAND},
        {"hash": "contacts", "eval": TAPS_LAND},
        {"hash": "jobs", "eval": TAPS_LAND},
        {"hash": CARD, "ready": CARD_OPEN, "eval": TAPS_LAND},
    ], vp, clock=T)
    caught = [a["eval"] for a in got["after"]]
    assert caught == [[], [], [], []], caught
