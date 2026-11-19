"""The tour names only what the page has, in the words the page uses.

Since the redesign (4.17.0) Contacts is one page with each person's note on their card: the
engine's tour still sent the person to "Messages", a view that is gone. And a To do card is
put off with Later in its corner, the trash only where something goes (DESIGN.md, "Putting off
is not putting away"): both tours still said the trash puts a card away. The engine's tour
(tools/tips.py, PAGE_TOUR) is the one the page shows when the engine sends it; the page's own
(app.js, TOUR) where it does not.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import tips  # noqa: E402


def _page_tour() -> dict:
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        src = fh.read()
    body = src[src.index("const TOUR = () => ["):]
    body = body[:body.index("];")]
    return {k: t for k, _title, t in re.findall(r'\["(\w+)", "([^"]*)", "((?:[^"\\]|\\.)*)"', body)}


def test_contacts_never_sends_the_person_to_a_view_that_is_gone():
    engine = {s["key"]: s["text"] for s in tips.PAGE_TOUR}
    for said in (engine["contacts"], _page_tour()["contacts"]):
        assert "Messages" not in said, said


def test_to_do_says_later_puts_a_card_off():
    engine = {s["key"]: s["text"] for s in tips.PAGE_TOUR}
    for said in (engine["todo"], _page_tour()["todo"]):
        assert "Later" in said and "the trash puts it away" not in said, said
