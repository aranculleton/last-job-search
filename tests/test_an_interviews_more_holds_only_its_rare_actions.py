"""An interview's More holds only its rare actions; its facts are on its line and its pencil
is on the card.

The day before an interview with a live prep, its card on Coming up (Interviews) showed
"Practise 3 questions", "Read your prep" and More, and More opened on eleven lines: "Prep updated
29 min ago.", "Also at <employer>: the message to ...", Add to calendar, Practise with Claude,
Update my prep, New day, Something else, a tip about the pencil with its Got it, and "Edit the
prep" with a pencil (the maintainer, 2026-11-11). DESIGN.md, "Buttons, links and taps": More is
for what is rare, never a pencil or a way to edit, never a fact that belongs on the card's line;
and an interview's More holds Practise with Claude, Update my prep and a new day. The actions are
defined once (`ivActs`), so To do's card for the same interview holds the same.

The page is the sample with the engine's own live prep on its first interview, the morning
before it. Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_interview_pack import app  # noqa: E402,F401
import app_page  # noqa: E402
from test_the_live_prep_on_the_page import IV, _model  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, browser  # noqa: E402

# The morning before the interview, 29 minutes after its prep was last made.
CLOCK = "2026-10-27T09:00:00Z"
UPDATED = "2026-10-27T08:31:00Z"

# A card's face, its More and its line of facts, as drawn.
CARD = r"""((sel) => {
  const c = document.querySelector(sel);
  if (!c) return null;
  const vis = (e) => e.checkVisibility() && e.getClientRects().length > 0;
  const panel = c.querySelector('.more-panel');
  const label = (b) => [...b.childNodes].filter((n) => !(n.classList && n.classList.contains('sr-only'))).map((n) => n.textContent).join('').trim();
  const pens = [...c.querySelectorAll('[data-k^="tweak:prep"]')];
  return {
    face: [...c.querySelectorAll('.card-actions > .btn, .card-actions > span > .btn')].filter(vis).map(label),
    more: panel ? [...panel.querySelectorAll('.btn')].filter(vis).map(label) : [],
    moreText: panel ? panel.innerText : '',
    open: !!c.querySelector('details.more[open]'),
    meta: (c.querySelector('.meta') || {}).innerText || '',
    pens: pens.filter(vis).map((p) => ({inMore: !!p.closest('.more-panel'), onFacts: !!p.closest('.meta'), icon: p.classList.contains('icon-only'),
      name: p.getAttribute('aria-label') || p.textContent.trim()})),
  };
})"""


@pytest.fixture(scope="module")
def run():
    yield from browser()


@pytest.fixture
def model(app):  # noqa: F811
    m = _model()
    for iv in m["interviews"]:
        if iv["id"] == IV:
            iv["prep"] = dict(iv["prep"], updated=UPDATED)
    return m


def _cards(run, tmp_path, model, vp):
    soon, card = '[data-item="soon:%s"]' % IV, 'article[data-item="%s"]' % IV
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    got = run("engine", html=path, viewport=vp, clock=CLOCK, fake={"canSend": "available"}, steps=[
        {"hash": "interviews", "click": "Interviews", "exact": True},
        {"more": IV, "eval": CARD + "(%r)" % card},
        {"hash": "todo", "more": "soon:" + IV, "eval": CARD + "(%r)" % soon},
    ])
    assert not got["errors"], got["errors"]
    return got["after"][1]["eval"], got["after"][2]["eval"]


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_an_interviews_more_holds_only_its_rare_actions(run, tmp_path, model, vp):
    coming, todo = _cards(run, tmp_path, model, vp)
    assert coming and coming["open"], coming
    # The day before, practice leads the face (DESIGN.md: "Practise 3 questions" beside Read
    # your prep), as before.
    assert coming["face"] == ["Practise 3 questions", "Read your prep"], coming
    # More: the rare actions in DESIGN.md's order, the calendar the practice took the place of,
    # and Something else last.
    assert coming["more"] == ["Practise with Claude", "Update my prep", "New day", "Add to calendar", "Something else"], coming
    # No fact, no tip and no way to edit inside it.
    for words in ("Prep updated", "Also at", "changes the look", "Got it", "Edit the prep"):
        assert words not in coming["moreText"], (words, coming["moreText"])
    # To do offers the same, from the same definition.
    assert todo and todo["face"] == coming["face"] and todo["more"] == coming["more"], (todo, coming)


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_an_interviews_pencil_is_beside_its_prep_on_the_card(run, tmp_path, model, vp):
    coming, todo = _cards(run, tmp_path, model, vp)
    # When the prep was made is a fact on its line, with the pencil beside it.
    assert "Prep ready, updated 29 min ago" in coming["meta"], coming["meta"]
    for card in (coming, todo):
        assert card["pens"] and all(p["onFacts"] and not p["inMore"] and p["icon"] for p in card["pens"]), card
        assert card["pens"][0]["name"].startswith("Edit the prep"), card["pens"]
