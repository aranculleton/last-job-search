"""Contacts uses the whole width: on a wide screen the person cards stand side by side.

The maintainer, on a wide screen, 2026-11-18: "is everything meant to be cropped far to the
left of this screen?" Each person's card ran the whole width of a 1970px window, but its draft
keeps a reading measure (640px, the accessibility review's 140-letter lines) and its pills sit
under the draft, so the right half of every card was empty. Every screen is the whole width
(DESIGN.md), so where the list holds two cards of 620px they stand side by side, row by row in
the list's own order, each its own height; a phone and a narrower window keep one column, and
the draft keeps its measure inside its card (DESIGN.md, Contacts).

Every person and employer here is invented (the book of
`test_contacts_show_only_what_the_persons_rules_allow`, with a crowd of invented people, and
the on hold group of `test_the_on_hold_group_is_last_and_folded`).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_contacts_show_only_what_the_persons_rules_allow import APP, Book, NOW, PHONE, WIDE, fixed  # noqa: E402

CLOCK = "2026-10-25T18:30:00Z"
WIDEST = {"width": 1970, "height": 1100}
CARD = 620      # the narrowest a card stands beside another (DESIGN.md, Contacts)
MEASURE = 640   # a draft's reading measure (app.css, li.person .pdraft)
GAP = 8         # between the cards (app.css, ul.people)


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    return Book(str(tmp_path_factory.mktemp("contactswidth")), crowd=12)


@pytest.fixture(scope="module")
def model(book):
    return book.model()


@pytest.fixture(scope="module")
def run():
    from test_the_page_journeys import browser
    yield from browser()


@pytest.fixture(scope="module")
def page(book):
    import app_page
    out = os.path.join(book.root, "page.artifact.html")
    book.run(APP, "page", "--now", NOW, "--out", out)
    path = os.path.join(book.root, "page.html")
    with open(out, encoding="utf-8") as fh, open(path, "w", encoding="utf-8") as w:
        w.write(app_page.standalone(fh.read()))
    return path


# Where each card and its draft are drawn (the harness's __drawnRect: the page is zoomed on a
# phone), in the list's own order.
LOOK = r"""((sel) => {
  const ul = document.querySelector(sel);
  if (!ul) return null;
  const r = (e) => { const b = e.__drawnRect(); return {left: b.left, right: b.right, top: b.top, width: b.width, height: b.height}; };
  return {list: r(ul), inner: window.innerWidth, scroll: document.documentElement.scrollWidth,
    cards: [...ul.querySelectorAll(':scope > li[data-item]')].map((c) => {
      const d = c.querySelector('details.pdraft');
      return Object.assign({id: c.dataset.item, draft: d ? r(d) : null}, r(c)); })};
})(%r)"""
MAIN = "#main ul.people:not([data-held-list])"
HELD = "#main ul[data-held-list]"


def _rows(cards):
    """The cards as they stand, row by row: a row is the cards whose tops meet."""
    rows = []
    for c in cards:
        if rows and abs(rows[-1][0]["top"] - c["top"]) < 1:
            rows[-1].append(c)
        else:
            rows.append([c])
    return rows


def _holds(width):
    """How many cards of 620px the list holds side by side, at least one."""
    return max(1, int((width + GAP) // (CARD + GAP)))


@pytest.mark.parametrize("vp", [PHONE, WIDE, WIDEST], ids=["phone", "1440", "1970"])
def test_the_cards_stand_side_by_side_where_the_list_holds_two(run, page, model, vp):
    got = run("engine", html=page, viewport=vp, clock=CLOCK, seed=fixed(model), steps=[
        {"hash": "contacts", "ready": "!!document.querySelector('%s > li[data-item]')" % MAIN, "eval": LOOK % MAIN}])
    assert not got["errors"], got["errors"]
    look = got["after"][0]["eval"]
    lst, cards = look["list"], look["cards"]
    assert len(cards) >= 6, [c["id"] for c in cards]
    # Nothing scrolls sideways, at any width.
    assert look["scroll"] <= look["inner"] + 1, look
    cols = _holds(lst["width"])
    rows = _rows(cards)
    # As many side by side as the list holds, row by row in the list's own order, so the eye
    # and the keyboard (which follows that order) go first to second along the top.
    assert [len(r) for r in rows[:-1]] == [cols] * (len(rows) - 1), ([len(r) for r in rows], lst)
    assert len(rows[-1]) <= cols, [len(r) for r in rows]
    for row in rows:
        assert all(a["right"] <= b["left"] for a, b in zip(row, row[1:])), row
    assert all(a[0]["top"] < b[0]["top"] for a, b in zip(rows, rows[1:])), rows
    # The row is the list's whole width: its first card at the list's left edge, its last at
    # the right, and none narrower than 620px or wider than its share.
    for row in rows[:-1]:
        assert abs(row[0]["left"] - lst["left"]) <= 1 and abs(row[-1]["right"] - lst["right"]) <= 1, (row, lst)
    for c in cards:
        assert c["width"] >= min(CARD, lst["width"]) - 1, (c, lst)
        assert c["width"] <= (lst["width"] - GAP * (cols - 1)) / cols + 1, (c, lst, cols)
    # The draft keeps its reading measure inside its card.
    drafts = [c for c in cards if c["draft"]]
    assert drafts, "the book has drafts on the list"
    for c in drafts:
        assert c["draft"]["width"] <= MEASURE + 1 and c["draft"]["right"] <= c["right"], c
    if cols >= 2:
        # Never the right half of a card empty: its draft reaches across most of it (on a
        # 1970px window, one card across the list had its draft end 42% of the way across).
        for c in drafts:
            assert (c["draft"]["right"] - c["left"]) / c["width"] >= 0.75, c
        # Each card is its own height: the first, its draft drawn whole, is never stretched
        # onto the one beside it.
        first, beside = rows[0][0], rows[0][1]
        assert first["draft"] and not beside["draft"] and beside["height"] < first["height"] - 20, rows[0]
    if vp is WIDEST:
        assert cols == 2, lst
    if vp is PHONE:
        assert cols == 1, lst


def test_the_on_hold_group_stands_the_same_way(run, tmp_path):
    """The On hold group's cards stand side by side too, in its own order."""
    from test_the_on_hold_group_is_last_and_folded import IVO, LEORIC, _two_waiting_for_a_role
    from test_the_page_journeys import _go
    got = _go(run, tmp_path, [
        {"hash": "contacts", "ready": "!!document.querySelector('#main [data-on-hold]')"},
        {"open": "held:contacts", "ready": "!!document.querySelector('%s')" % HELD, "eval": LOOK % HELD},
    ], WIDEST, model=_two_waiting_for_a_role())
    look = got["after"][1]["eval"]
    lst, cards = look["list"], look["cards"]
    assert [c["id"] for c in cards] == [IVO, LEORIC], cards
    assert _holds(lst["width"]) >= 2, lst
    (row,) = _rows(cards)
    assert row[0]["right"] <= row[1]["left"] and abs(row[0]["left"] - lst["left"]) <= 1, row
