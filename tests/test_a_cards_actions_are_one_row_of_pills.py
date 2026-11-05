"""A card's actions are one row of pills (templates/app/DESIGN.md, "Buttons, links and taps").

The maintainer, 2026-11-05: "can we have all buttons next to each other (see the posting and
more) have the same bubble theme that see the draft/draft this has? ... some things are just
text buttons which makes it look quite cluttered", and "a lot of parts of the app also have
all these buttons clustered together when they are either redundant or could be put under
More". So on every screen: the one next step is the filled pill, every other control beside
it the soft grey pill of the same height and radius, More a soft pill too; no underlined
text control in a row of actions; at most one filled pill a card; at most three before More.
Read on a phone and a wide screen, light and dark. Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"

# Every row of actions on the screen, and what is wrong with each: a control that is not a
# pill (underlined, square, no fill), pills of different heights, more than three before
# More, more than one filled pill on a card.
PROBE = r"""(() => {
  const seen = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length) && !e.closest('details:not([open]) > :not(summary)');
  const rows = [...document.querySelectorAll('.card-actions, .wc-actions, .suggest-acts, .g-acts, .bp-foot')].filter(seen);
  const bad = [];
  const name = (c) => (c.getAttribute('aria-label') || c.textContent || '').trim().slice(0, 40);
  for (const r of rows) {
    // Every control in the row, wrapped or not (a link inside a <p> in the row is still in
    // it), but nothing under its More.
    const ctrls = [...r.querySelectorAll('button, a, details.more')].filter((c) => seen(c) && !c.matches('.icon-only')
      && (c.matches('details.more') || !c.closest('details.more')) && c.closest('.card-actions, .wc-actions, .suggest-acts, .g-acts, .bp-foot') === r);
    const look = ctrls.map((c) => (c.matches('details.more') ? c.querySelector(':scope > summary') : c));
    const where = (r.closest('[data-item],[data-work]') || r).getAttribute('data-item') || (r.closest('[data-work]') || {}).dataset?.work || r.className;
    const hs = [];
    look.forEach((c, i) => {
      const s = getComputedStyle(c);
      const flat = s.backgroundColor === 'rgba(0, 0, 0, 0)' || s.backgroundColor === 'transparent';
      if (s.textDecorationLine !== 'none' || parseFloat(s.borderTopLeftRadius) < 12 || flat) bad.push([where, 'not a pill', name(ctrls[i])]);
      hs.push(Math.round(c.getBoundingClientRect().height));
    });
    if (hs.length > 1 && Math.max(...hs) - Math.min(...hs) > 1) bad.push([where, 'heights ' + hs.join('/'), look.map(name).join(' | ')]);
    const before = ctrls.filter((c) => !c.matches('details.more')).length;
    if (before > 3) bad.push([where, before + ' before More', ctrls.map(name).join(' | ')]);
    // More is for what is rare: five at most (DESIGN.md, "Buttons, links and taps").
    for (const m of [...r.querySelectorAll(':scope > details.more')]) {
      const inside = [...m.querySelectorAll('.more-panel button, .more-panel a')].length;
      if (inside > 5) bad.push([where, inside + ' under More', '']);
    }
  }
  for (const card of [...document.querySelectorAll('[data-card], [data-work]')].filter(seen)) {
    const own = [...card.querySelectorAll('.btn.primary')].filter((b) => seen(b) && b.closest('[data-card], [data-work]') === card && !b.closest('details.more:not([open])'));
    if (own.length > 1) bad.push([card.getAttribute('data-item') || card.getAttribute('data-work'), own.length + ' filled pills', own.map(name).join(' | ')]);
  }
  return {rows: rows.length, controls: rows.reduce((n, r) => n + r.children.length, 0), bad};
})()"""

SCREENS = ["todo", "brief", "interviews", "settings", "chat"]
# Claude's work with something in each state: waiting its turn, asking, done, stopped short.
_W = {"to": "cloud", "args": {}, "asked_at": "2026-10-25T08:40:00.000Z", "_v": 2}
WORK = {"chats/cloud-1": {"kind": "cloud", "seen_at": "2026-10-25T08:58:30.000Z", "watching": True},
        "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": "2026-10-25T08:56:00.000Z", "since": "2026-10-24T08:00:00.000Z"},
        "work/follow_up~wren": dict(_W, kind="follow_up", title="Follow up with Wren", status="queued"),
        "work/reply~juno": dict(_W, kind="reply", title="Reply to Juno", status="needs_you", note="Did the call go ahead?",
                                needs={"question": "Did the call go ahead?", "work": "reply~juno", "answer": {"key": "answer", "kind": "yesno"}}),
        "work/prep~bea": dict(_W, kind="prep", title="Prepare for the call with Bea", status="done", finished_at="2026-10-25T08:55:00.000Z",
                              result={"summary": "Your prep is ready.", "links": []}),
        "work/draft~quayside": dict(_W, kind="draft", title="Draft Quayside", status="failed", finished_at="2026-10-25T08:50:00.000Z",
                                    error="The posting could not be read.")}


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_every_row_of_actions_on_these_screens_is_one_row_of_pills(run, tmp_path, vp, scheme):
    steps = [{"hash": s, "eval": PROBE} for s in SCREENS]
    # Claude's work: open beside To do on a wide screen, opened from its pill on a phone.
    steps.append(dict({"hash": "todo", "eval": PROBE}, **({"open": "pill"} if vp is PHONE else {})))
    got = run("engine", html=_page(tmp_path), viewport=vp, steps=steps, seed=WORK, fake={"canSend": "available"}, clock=T, scheme=scheme)
    assert not got["errors"], got["errors"]
    read = dict(zip(SCREENS + ["Claude's work"], (a["eval"] for a in got["after"])))
    wrong = {screen: r["bad"] for screen, r in read.items() if r["bad"]}
    assert not wrong, wrong
    # The probe read real rows: To do and Claude's work have cards with actions.
    assert read["todo"]["rows"] >= 3 and read["Claude's work"]["rows"] >= 1, {k: (v["rows"], v["controls"]) for k, v in read.items()}


def _page(tmp_path):
    import app_page
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(journeys._sample())))
    return path


def test_a_link_inside_a_sentence_stays_a_link(run, tmp_path):
    """A fold's "Show them" or a name in a line is a link in a sentence, never a pill."""
    look = ("(() => { const f = [...document.querySelectorAll('#main p.fold .btn.link')].filter((b) => b.offsetParent);"
            " return f.map((b) => getComputedStyle(b).textDecorationLine); })()")
    got = _go(run, tmp_path, [{"hash": "todo", "eval": look}], WIDE, clock=T)
    assert all(x == "underline" for x in got["after"][0]["eval"]), got["after"][0]["eval"]


MENU = r"""(() => {
  const side = document.getElementById('side');
  const lists = [...side.children];
  const main = side.querySelector('.side-main'), foot = side.querySelector('.side-foot'), head = side.querySelector('.side-head');
  const last = [...main.querySelectorAll('li')].pop().getBoundingClientRect();
  const rule = foot.getBoundingClientRect();
  const first = foot.querySelector('li').getBoundingClientRect();
  const s = getComputedStyle(foot), hs = getComputedStyle(head);
  const fold = head.querySelector('li').getBoundingClientRect(), hrule = head.getBoundingClientRect().bottom;
  const next = main.querySelector('li').getBoundingClientRect();
  return {above: Math.round(rule.top - last.bottom), below: Math.round(first.top - rule.top - parseFloat(s.borderTopWidth)),
    after: lists.slice(lists.indexOf(foot) + 1).length, rules: lists.filter((e) => parseFloat(getComputedStyle(e).borderTopWidth) > 0).length,
    first: lists.indexOf(head), headAbove: Math.round(hrule - parseFloat(hs.borderBottomWidth) - fold.bottom),
    headBelow: Math.round(next.top - hrule)};
})()"""


def test_the_menu_foot_is_one_rule_with_equal_space_round_it_and_settings_last(run, tmp_path):
    """The maintainer, 2026-11-05, on the side menu's foot: "why's the spacing here weird" (a
    rule above Settings, an empty block, a second rule, then Icons only)."""
    got = _go(run, tmp_path, [{"hash": "todo", "eval": MENU}, {"eval": "(document.querySelector('[data-k=\"side-toggle\"]').click(), 1)"},
                              {"eval": MENU}], WIDE, clock=T)
    for r in (got["after"][0]["eval"], got["after"][2]["eval"]):
        assert r["after"] == 0 and r["rules"] == 1, ("Settings is last, under the one rule", r)
        # On the 8, 12, 16 scale as the page draws it (its text size can scale it by a pixel).
        assert abs(r["above"] - r["below"]) <= 1 and any(abs(r["above"] - g) <= 1 for g in (8, 12, 16)), ("the same space above and below the rule, on the scale", r)
        # Icons only is the menu's first section, under its own rule with the same space round it.
        assert r["first"] == 0 and abs(r["headAbove"] - r["headBelow"]) <= 1 and abs(r["headAbove"] - r["above"]) <= 1, ("Icons only, its own section", r)
