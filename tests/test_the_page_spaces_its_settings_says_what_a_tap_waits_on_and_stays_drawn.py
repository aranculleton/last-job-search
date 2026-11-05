"""Settings laid out across a wide panel, a saved tap that says what it waits on, and a Brief
that stays drawn while a phone scrolls it (the maintainer's own use, 2026-11-04).

- An opened fold stacked its words, its buttons and the line a tap leaves down the left of a
  wide panel ("surely this could be spaced out a bit better instead of bunching them all on
  the left"), and the LinkedIn download had two buttons for one file.
- Calendar reminders stood four radios down the left of the panel with a gap after each
  ("this could be a bit better right").
- "Saved. Claude will pick this up." said neither what nor where ("where? what exactly am I
  waiting for?"), and the download then sat "Waiting to start" behind another item without
  naming it ("took a while, is that intended?").
- An iPhone scrolling the Brief fast showed a blank page, then its foot: every live update
  and the minute's redraw tore the whole Brief down and built it again, because the marks the
  page puts on a screen after drawing it made the fresh copy never match the one on screen.

Every person and employer is invented (tests/fixtures/app_model_sample.json).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import app_page  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


T = "2026-10-25T09:00:00.000Z"

# Every Settings fold opened, and each control it holds measured against the fold's own inner
# edges: its buttons (never a link in a sentence, the steps of "How to get it", nor a row's
# own list of switches), its line after a tap, and the words before them.
FOLDS = r"""(() => {
  for (const d of document.querySelectorAll('#main details')) d.open = true;
  const out = [];
  for (const d of document.querySelectorAll('#main details.setting-row[open]')) {
    const body = d.querySelector(':scope > .set-body');
    if (!body || !body.getClientRects().length) continue;
    const r = body.__drawnRect(), cs = getComputedStyle(body), k = r.width / body.offsetWidth;
    const left = r.left + parseFloat(cs.paddingLeft) * k, right = r.right - parseFloat(cs.paddingRight) * k;
    const btns = [...body.querySelectorAll('.btn:not(.link), button.btn.quiet, a.btn')].filter((b) => b.getClientRects().length &&
      !b.closest('.how, .steps, .checks-list, .where-list, .pill-row, .ctl-row, .controls, .state, .note'));
    const say = [...body.querySelectorAll('p, .chip-list')].filter((p) => p.getClientRects().length && !p.closest('.how, .state, .note') && !p.contains(btns[0] || null));
    out.push({fold: d.getAttribute('data-k'), left, right,
      buttons: btns.map((b) => { const x = b.__drawnRect(); return {name: b.textContent.trim(), l: x.left, r: x.right, t: x.top, b: x.bottom}; }),
      words: say.length ? {t: say[0].__drawnRect().top, b: say[0].__drawnRect().bottom} : null,
      undo: [...body.querySelectorAll('.state .undo')].map((u) => u.__drawnRect().right)});
  }
  return out;
})()"""


def test_an_opened_fold_puts_its_buttons_beside_its_words_on_a_wide_screen_and_after_them_on_a_phone(run, tmp_path):
    m = _sample()
    # A download saved and waiting, so its line (and its Undo) is on the fold too.
    seed = {"actions/a-export": {"action": "export.take", "item": "2026-10", "value": {"assets": []}, "at": "2026-10-25T08:59:00.000Z", "rev": None}}
    wide = _go(run, tmp_path, [{"hash": "settings", "eval": FOLDS}], WIDE, model=m, clock=T)["after"][0]["eval"]
    with_buttons = [f for f in wide if f["buttons"]]
    names = {f["fold"] for f in with_buttons}
    for must in ("det:info:search-roles", "det:info:search-pay", "det:info:brief-pause", "det:info:linkedin-download", "det:info:learned"):
        assert must in names, (must, sorted(names))
    for f in with_buttons:
        last = max(b["r"] for b in f["buttons"])
        assert abs(f["right"] - last) <= 4, ("its buttons stand at the right edge of a wide fold, never bunched on the left", f)
        if f["words"]:
            first = min(f["buttons"], key=lambda b: b["t"])
            assert first["t"] < f["words"]["b"], ("beside the words they belong to, not under them", f)
    # The waiting download's line: its Undo at the right, under where its button stood.
    waited = _go(run, tmp_path, [{"hash": "settings", "eval": FOLDS}], WIDE, model=m, seed=seed, clock=T)["after"][0]["eval"]
    li = next(f for f in waited if f["fold"] == "det:info:linkedin-download")
    assert li["undo"] and abs(li["right"] - li["undo"][0]) <= 4, li
    # On a phone the buttons follow the words, inside the fold.
    phone = _go(run, tmp_path, [{"hash": "settings", "eval": FOLDS}], PHONE, model=m, clock=T)["after"][0]["eval"]
    for f in phone:
        for b in f["buttons"]:
            assert b["l"] >= f["left"] - 1 and b["r"] <= f["right"] + 1, ("nothing runs past a phone's fold", f)
            if f["words"]:
                assert b["t"] >= f["words"]["b"] - 1, ("on a phone the button comes after its words", f)


def test_the_linkedin_download_is_given_one_way_and_not_offered_again_while_it_waits(run, tmp_path):
    """"Add the download" and "Choose its folder" were two ways to give one file (the
    maintainer, 2026-11-04: "any unnecessary or redundant buttons here?"). One button takes
    the zip or the files inside it; while a download waits, its line has the Undo instead."""
    fold = ("(() => { const d = document.querySelector('[data-k=\"det:info:linkedin-download\"]'); d.open = true; "
            "return {buttons: [...d.querySelectorAll('.set-body button')].filter((b) => b.getClientRects().length).map((b) => b.textContent.trim()), "
            "inputs: [...d.querySelectorAll('input[type=file]')].map((i) => [i.multiple, i.hasAttribute('webkitdirectory'), i.accept])}; })()")
    m = _sample()
    for vp in (WIDE, PHONE):
        got = _go(run, tmp_path, [{"hash": "settings", "eval": fold}], vp, model=m, clock=T)["after"][0]["eval"]
        assert got["buttons"] == ["Add the download"], got
        assert got["inputs"] == [[True, False, ".zip,.csv,application/zip,text/csv"]], ("one picker, for the zip or its files", got)
    seed = {"actions/a-export": {"action": "export.take", "item": "2026-10", "value": {"assets": []}, "at": "2026-10-25T08:59:00.000Z", "rev": None}}
    got = _go(run, tmp_path, [{"hash": "settings", "eval": fold}], WIDE, model=m, seed=seed, clock=T)["after"][0]["eval"]
    assert "Add the download" not in got["buttons"] and "Undo" in got["buttons"], got


CHOICES = r"""(() => {
  for (const d of document.querySelectorAll('#main details')) d.open = true;
  const out = {};
  for (const fs of document.querySelectorAll('#main details.setting-row fieldset.setting')) {
    const radios = [...fs.querySelectorAll('input[type=radio]')];
    if (!radios.length) continue;
    const body = fs.closest('.set-body').__drawnRect();
    const boxes = radios.map((i) => i.closest('.choice').__drawnRect());
    out[fs.closest('details').getAttribute('data-k')] = {legend: (fs.querySelector('legend') || {}).textContent || '', names: [...new Set(radios.map((i) => i.name))].length,
      rows: [...new Set(boxes.map((b) => Math.round(b.top / 4)))].length, n: radios.length,
      inside: boxes.every((b) => b.left >= body.left - 1 && b.right <= body.right + 1), height: Math.round(fs.__drawnRect().height)};
  }
  return [out, document.documentElement.scrollWidth <= document.documentElement.clientWidth];
})()"""


def test_a_short_choice_is_a_row_of_chips_on_a_wide_screen_that_wraps_on_a_phone_and_stays_a_radio_group(run, tmp_path):
    m = _sample()
    wide, fits = _go(run, tmp_path, [{"hash": "settings", "eval": CHOICES}], WIDE, model=m, clock=T)["after"][0]["eval"]
    assert fits
    for key in ("det:set:calendar_reminder", "det:set:prep_days", "det:set:linkedin_plan", "det:set:suggestions"):
        c = wide[key]
        assert c["rows"] == 1, ("every choice of a short setting side by side on a wide screen, never a tall list", key, c)
        # Still one radio group, named for a screen reader: arrow keys move through it
        # (test_settings_save_once_the_person_settles_and_show_the_new_value presses them).
        assert c["names"] == 1 and c["legend"], (key, c)
    assert wide["det:set:calendar_reminder"]["n"] == 4 and wide["det:set:calendar_reminder"]["height"] < 110, wide["det:set:calendar_reminder"]
    phone, fits = _go(run, tmp_path, [{"hash": "settings", "eval": CHOICES}], PHONE, model=m, clock=T)["after"][0]["eval"]
    assert fits, "nothing scrolls sideways on a phone"
    cal = phone["det:set:calendar_reminder"]
    assert cal["inside"] and cal["rows"] < cal["n"], ("wrapping, a few to a row, inside the fold", cal)


# A reply running in the chat that answers the page, a follow-up waiting behind it, and the
# LinkedIn download saved after both: the one chat does one thing at a time.
RUNNING = {"kind": "reply", "title": "Reply to Juno", "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:55:00.000Z", "status": "running",
           "claimed_by": "cloud-1", "claimed_at": "2026-10-25T08:56:00.000Z", "lease_until": "2026-10-25T09:20:00.000Z",
           "stages": [{"name": "Writing", "est_s": 300}], "stage": 0, "stage_at": "2026-10-25T08:56:00.000Z", "steps": [], "attempt": 1}
QUEUED = {"kind": "follow_up", "title": "Follow up with Wren", "to": "cloud", "args": {}, "asked_at": "2026-10-25T08:58:00.000Z", "status": "queued",
          "stages": [{"name": "Writing", "est_s": 120}], "stage": 0, "steps": [], "attempt": 1}
TAP = {"action": "export.take", "item": "2026-10", "value": {"assets": []}, "at": "2026-10-25T08:59:00.000Z", "rev": None}
HEARD = {"chats/cloud-1": {"kind": "cloud", "seen_at": "2026-10-25T08:58:30.000Z", "watching": True},
         "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": "2026-10-25T08:56:00.000Z", "since": "2026-10-24T08:00:00.000Z"}}
LINE = "(document.querySelector('[data-k=\"det:info:linkedin-download\"] .state') || {}).textContent || ''"
CARD = "(document.querySelector('[data-tap-work]') || {}).textContent || ''"
WORK = "[...document.querySelectorAll('[data-work]')].map((e) => e.textContent)"


def test_a_saved_tap_says_what_it_waits_behind_and_opens_where_to_watch_it(run, tmp_path):
    seed = dict(HEARD, **{"actions/a-export": TAP, "work/reply~1": RUNNING, "work/follow_up~2": QUEUED})
    got = _go(run, tmp_path, [
        {"hash": "settings", "open": "info-sum:linkedin-download", "eval": "[" + LINE + ", " + CARD + ", " + WORK + "]"},
        {"open": "see-work:export:settings", "eval": "[document.activeElement.getAttribute('data-tap-work'), document.activeElement.textContent]"},
    ], WIDE, seed=seed, clock=T)
    line, card, work = got["after"][0]["eval"]
    assert "Claude will pick this up" not in got["after"][0]["text"]
    assert line.startswith("Saved. Claude reads it after “Reply to Juno”.") and "See it in Claude's work" in line, line
    assert "Next" in card and "Next, after “Reply to Juno”." in card, card
    # Light work waiting behind it says so too.
    wren = next(w for w in work if "Follow up with Wren" in w)
    assert "Next, after “Reply to Juno”." in wren, work
    # Its link opens it in Claude's work, on it.
    focus, text = got["after"][1]["eval"]
    assert focus == "a-export" and "Reading your LinkedIn download" in text, got["after"][1]["eval"]
    # On a phone the same link opens the work sheet, on the same card.
    got = _go(run, tmp_path, [{"hash": "settings", "open": "info-sum:linkedin-download"},
                              {"open": "see-work:export:settings", "eval": "[!!document.querySelector('dialog.work-sheet[open]'), document.activeElement.getAttribute('data-tap-work')]"}],
              PHONE, seed=seed, clock=T)
    assert got["after"][1]["eval"] == [True, "a-export"], got["after"][1]["eval"]


def test_a_tap_whose_helper_is_not_answering_says_so_and_offers_to_start_it(run, tmp_path):
    seed = {"actions/a-export": dict(TAP, at="2026-10-25T08:30:00.000Z"),
            "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": "2026-10-24T08:50:00.000Z", "since": "2026-10-20T08:00:00.000Z"}}
    got = _go(run, tmp_path, [{"hash": "settings", "open": "info-sum:linkedin-download",
                               "eval": "[" + LINE + ", " + CARD + ", !!document.querySelector('[data-tap-work] a[data-k^=\"prefill:\"]')]"}], WIDE, seed=seed, clock=T)
    line, card, start = got["after"][0]["eval"]
    assert line.startswith("Saved. Claude's helper is not answering, so it waits."), line
    assert "No answer yet" in card and "not answering" in card and start, card


def test_every_saved_tap_says_what_happens_and_where_it_shows(run, tmp_path):
    """Not only the download: a setting changed says Claude makes the change next and the line
    says Done when it has, or what it waits behind."""
    act = {"actions/a-cal": {"action": "setting.set", "item": "setting-calendar_reminder", "value": "15", "at": "2026-10-25T08:59:30.000Z", "rev": "s-calendar_reminder"}}
    line = "(document.querySelector('[data-k=\"det:set:calendar_reminder\"] .state') || {}).textContent || ''"
    alone = _go(run, tmp_path, [{"hash": "settings", "open": "set-sum:calendar_reminder", "eval": line}], WIDE, seed=dict(HEARD, **act), clock=T)
    assert alone["after"][0]["eval"].startswith("Saved. Claude makes the change next, and this line says Done when it has."), alone["after"][0]["eval"]
    behind = _go(run, tmp_path, [{"hash": "settings", "open": "set-sum:calendar_reminder", "eval": line}], WIDE,
                 seed=dict(HEARD, **act, **{"work/reply~1": RUNNING}), clock=T)
    assert behind["after"][0]["eval"].startswith("Saved. Claude makes the change after “Reply to Juno”, then this line says Done."), behind["after"][0]["eval"]


def _long_brief(tmp_path):
    m = _sample()
    news = next(s for s in m["brief"]["sections"] if s["kind"] == "news")
    news["items"] = [dict(news["items"][0], text="Item %d: the central bank held its rate this week, and planning teams expect steadier demand." % i)
                     for i in range(14)]
    path = os.path.join(str(tmp_path), "long.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(m)))
    view = copy.deepcopy(m["brief"])
    nxt = next(s for s in view["sections"] if s["kind"] == "next")
    nxt["items"][0] = dict(nxt["items"][0], text="Reply to Juno at Larkspur Retail today.")
    return path, view


def test_a_long_brief_scrolled_fast_on_a_phone_keeps_every_panel_drawn_through_live_updates(run, tmp_path):
    """In Safari's engine (LJS_PW_ENGINE=webkit) this is the iPhone the maintainer used: each
    panel stays the box it was, with its words, while the page scrolls fast and its live
    updates land, and a change to one panel while it rests scrolled redraws that panel alone
    and leaves the page where it was."""
    path, view = _long_brief(tmp_path)
    r = run("fast_scroll", html=path, view=view, clock=T)
    assert not r["errors"], r["errors"]
    steps = r["steps"]
    first = {k: tag for k, tag, _ in steps[0]["panels"]}
    assert len(first) >= 5 and all(first.values()), steps[0]
    upd = next(i for i, s in enumerate(steps) if s["what"] == "updated while scrolled")
    for i, s in enumerate(steps):
        for k, tag, chars in s["panels"]:
            assert chars > 0, ("a panel lost its words", s["what"], k)
            changed = i >= upd and k == "bp:next"
            assert changed or tag == first[k], ("a panel was torn down and built again", s["what"], k)
        if 0 < i <= upd and steps[i - 1]["what"] != "opened":
            assert s["y"] >= steps[i - 1]["y"], ("scrolling down never jumps back up", steps[i - 1], s)
    assert steps[upd]["y"] == steps[upd - 1]["y"] == steps[upd - 1]["max"], ("the page stays where it was", steps[upd - 1], steps[upd])
    assert "Reply to Juno at Larkspur Retail today." in r["text"], "the panel that changed shows the change"


# ------------------------------------------------------------------ Claude's work, 4 November


def test_the_pill_opens_and_closes_claudes_work_on_every_screen(run, tmp_path):
    """On a wide screen Claude's work was a column fixed beside every screen but the Brief, and
    a sheet across the whole page there (the maintainer, 2026-11-04: "just having this
    persistent every page but when u press it, opens or closes the side panel"). The pill opens
    and closes one panel on every screen, Hide closes it, and the choice is remembered."""
    rail = ("(() => { const hd = document.getElementById('h-work-rail'); const pill = document.getElementById('pill');"
            " const r = hd && hd.getClientRects().length ? document.getElementById('rail').getBoundingClientRect() : null;"
            " return [r ? Math.round(r.right) : null, innerWidth, pill ? pill.getAttribute('aria-expanded') : null]; })()")
    seed = dict(HEARD, **{"work/reply~1": RUNNING, "work/follow_up~2": QUEUED})
    d = tmp_path / "wide"
    d.mkdir()
    got = _go(run, d, [{"hash": "brief", "eval": rail}, {"open": "pill", "wait": 300, "eval": rail},
                       {"open": "work-hide", "wait": 300, "eval": rail}, {"hash": "todo", "wait": 300, "eval": rail},
                       {"open": "pill", "wait": 300, "eval": rail}, {"hash": "brief", "wait": 300, "eval": rail}], WIDE, seed=seed, clock=T)
    seen = [x["eval"] for x in got["after"]]
    assert seen[0][0] is None and seen[0][2] == "false", "the Brief keeps its width until the pill is pressed"
    assert seen[1][0] is not None and abs(seen[1][0] - seen[1][1]) <= 40 and seen[1][2] == "true", seen[1]
    assert seen[2][0] is None and seen[2][2] == "false", "Hide closes it"
    assert seen[3][0] is None, "closed stays closed on To do: one choice, remembered"
    assert seen[4][0] is not None and seen[5][0] is not None, "opened stays open, the Brief included"


def test_narrower_claudes_work_opens_on_the_right_and_on_a_phone_from_the_bottom(run, tmp_path):
    box = ("(() => { const d = document.querySelector('dialog.work-sheet[open]'); if (!d) return null;"
           " const r = d.getBoundingClientRect(); return [r.right, r.top, r.width, r.bottom, innerWidth, innerHeight]; })()")
    seed = dict(HEARD, **{"work/reply~1": RUNNING, "work/follow_up~2": QUEUED})
    for vp, side in (({"width": 1024, "height": 768}, True), (PHONE, False)):
        d = tmp_path / ("side" if side else "phone")
        d.mkdir()
        got = _go(run, d, [{"hash": "brief", "open": "pill", "eval": box}], vp, seed=seed, clock=T)
        right, top, width, bottom, vw, vh = got["after"][0]["eval"]
        if side:
            assert abs(right - vw) <= 1 and top <= 1 and width < vw / 2 and bottom >= vh - 2, got["after"][0]["eval"]
        else:
            assert width >= vw - 1 and top > 0, got["after"][0]["eval"]


def test_a_work_card_says_a_day_as_a_person_does_and_its_time_once(run, tmp_path):
    """A card named "<who> at <where>: One follow-up sent 2026-10-21. No more after this", and a
    first step's clock over "2 min so far" counting the same time (the maintainer, 2026-11-04)."""
    noted = dict(QUEUED, title="Wren at Harbourline Bank: One follow-up sent 2026-10-21. No more after this")
    seed = dict(HEARD, **{"work/reply~1": RUNNING, "work/follow_up~2": noted})
    cards = ("Array.from(document.querySelectorAll('#rail [data-work]')).map((c) => [c.getAttribute('data-work'),"
             " c.querySelector('.wc-title').textContent, (c.querySelector('[data-step]') || {}).textContent || '',"
             " (c.querySelector('[data-time]') || {}).textContent || ''])")
    got = _go(run, tmp_path, [{"hash": "todo", "eval": cards}], WIDE, seed=seed, clock=T)
    by = {c[0]: c for c in got["after"][0]["eval"]}
    title = by["follow_up~2"][1]
    assert "2026-10-21" not in title and "21 Oct" in title, title
    _id, _title, step, time = by["reply~1"]
    assert step, "the running step keeps its own clock"
    assert "so far" not in time and "left" in time, time


def test_a_finished_follow_up_opens_the_person_in_contacts(run, tmp_path):
    done = dict(QUEUED, args={"contact": "p-wren"}, status="done", finished_at="2026-10-25T08:59:00.000Z",
                result={"summary": "Closed, as you chose: no more messages to Wren."})
    link = "Array.from(document.querySelectorAll('#rail [data-work=\"follow_up~2\"] a[data-k^=\"open:\"]')).map((a) => [a.getAttribute('data-k'), a.textContent])"
    got = _go(run, tmp_path, [{"hash": "todo", "eval": link}], WIDE, seed=dict(HEARD, **{"work/follow_up~2": done}), clock=T)
    assert got["after"][0]["eval"] == [["open:contacts:p-wren", "Open in Contacts"]], got["after"][0]["eval"]


def test_a_run_of_like_work_is_one_card_with_its_count(run, tmp_path):
    """Fifty follow-ups and replies stood one card each down Claude's work (the maintainer,
    2026-11-04: "an easier way of displaying it in this list rather than scrolling through like
    50 items"). Four or more of one kind waiting, or finished, are one card; Show lists them."""
    names = ["Wren", "Juno", "Tamsin", "Marisol", "Ada"]
    seed = dict(HEARD, **{"work/reply~1": RUNNING})
    for i, n in enumerate(names):
        seed["work/follow_up~r%d" % i] = dict(QUEUED, title="Follow up with " + n, asked_at="2026-10-25T08:58:%02d.000Z" % i)
    look = ("(() => { const r = document.getElementById('rail'); const run = r.querySelector('[data-work-run]');"
            " return [run ? run.querySelector('.wc-title').textContent : null, run ? run.querySelector('.wc-now').textContent : null,"
            " r.querySelectorAll('[data-work^=\"follow_up~r\"]').length]; })()")
    got = _go(run, tmp_path, [{"hash": "todo", "eval": look}, {"open": "run:run~queued:follow_up", "wait": 300, "eval": look}], WIDE, seed=seed, clock=T)
    title, line, cards = got["after"][0]["eval"]
    assert title == "5 follow-ups waiting their turn" and cards == 0, got["after"][0]["eval"]
    assert line.startswith("Wren, Juno, Tamsin and 2 more"), line
    assert got["after"][1]["eval"][2] == 5, "Show lists each of them"


def test_a_card_of_notes_to_check_says_what_it_is(run, tmp_path):
    """Four notes held for an unread profile made a To do card titled with the warning alone,
    over a list of names (the maintainer, 2026-11-04: "idk what the bottom one is"). Its title
    says what it is, the reason sits under it, and its link says where they are."""
    m = copy.deepcopy(_sample())
    held = [x for x in m["messages"] if x.get("kind") == "first_note"][:2]
    assert len(held) == 2
    for x in held:
        x["hold"] = "Written before their profile was read: read it first"
        # The engine's own alert for it (tools/app_alerts.py for_message, "read_first").
        x["alerts"] = [{"id": "read_first:" + x["id"], "kind": "read_first", "level": 1, "item": x["id"],
                        "text": "Written before their profile was read: read it first.",
                        "why": "A note written before their profile was read can get them wrong."}]
    look = ("Array.from(document.querySelectorAll('[data-item^=\"grp:\"]')).map((c) => [(c.querySelector('.card-title') || {}).textContent || '',"
            " c.textContent]).filter((x) => /profile was read/.test(x[1]))")
    got = _go(run, tmp_path, [{"hash": "todo", "eval": look}], WIDE, model=m, clock=T)
    cards = got["after"][0]["eval"]
    assert cards, "the held notes make a card in To do"
    title, text = cards[0]
    assert title.startswith("2 messages to check before you send"), title
    assert "Written before their profile was read: read it first." in text and "Open in Contacts" in text, text


def test_a_card_being_changed_says_so(run, tmp_path):
    """After Apply on an edit, the note showed nothing while the change waited its turn (the
    maintainer, 2026-11-04: "after i send a job is there an indication that that one is being
    worked on in the list")."""
    m = copy.deepcopy(_sample())
    mid = m["messages"][0]["id"]
    work = dict(QUEUED, kind="tweak", title="Edit message", args={"v": 1, "target": {"id": mid, "output": "message"}})
    # The message is on its person's card in Contacts (one page since 2026-11-04).
    look = ("(() => { const c = document.querySelector('[data-msg=\"" + mid + "\"]'); const g = c && c.querySelector('[data-tweak-going]');"
            " return g ? g.textContent : null; })()")
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": look}], WIDE, model=m, seed=dict(HEARD, **{"work/tweak~m1": work}), clock=T)
    line = got["after"][0]["eval"]
    assert line and line.startswith("Claude changes this next") and "See it" in line, line


def test_a_refused_tap_with_nothing_asked_still_has_a_way_out(run, tmp_path):
    """A tap refused before refusals carried their question sat in To do as "Setup ... Not
    done: Which day is it? Give it as 2026-10-28" with no button at all (the maintainer,
    2026-11-04: "doesn't seem to have any options"). It is marked by what it was about, its
    day reads as a day, and its question is answered on the card with a date picker, or it is
    put away with its one bin; never "Say it in Chat" (the maintainer, 2026-11-05)."""
    m = copy.deepcopy(_sample())
    app = m["applications"][0]
    aid = "act~" + app["id"] + "~outcome.interview~old"
    seed = dict(HEARD, **{"actions/" + aid: {"item": app["id"], "action": "outcome.interview", "value": {"stage": "Phone screen"},
                                             "at": "2026-10-25T08:50:00.000Z", "rev_seen": "r", "tab": "t0"},
                          "receipts/" + aid: {"result": "conflict", "note": "Which day is it? Give it as 2026-10-28.",
                                              "applied_at": "2026-10-25T08:51:00Z", "by": "cloud-1"}})
    look = ("(() => { const c = document.querySelector('[data-item=\"refused:" + aid + "\"]'); if (!c) return null;"
            " return [c.querySelector('.kind').textContent, c.textContent, c.querySelectorAll('[data-bin]').length === 1, !!c.querySelector('input[type=date]')]; })()")
    got = _go(run, tmp_path, [{"hash": "todo", "eval": look}], WIDE, model=m, seed=seed, clock=T)
    card = got["after"][0]["eval"]
    assert card, "the refused tap has its card in To do"
    kind, text, one_bin, has_date = card
    assert kind != "Setup" and "2026-10-28" not in text and "28 Oct" in text, card
    assert one_bin and has_date and "in Chat" not in text, card
