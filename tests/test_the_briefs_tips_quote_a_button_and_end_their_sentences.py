"""The Brief's tips quote a button by its name, and a help card's line ends with its full stop.

The screen review, 2026-11-18: "Read your prep opens an interview prep full screen." read as a
sentence about reading, the button's name unquoted; and "Your profile: every CV and letter is
built from it" lacked the full stop the lines beside it have.
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "templates", "app", "app.js")


def _src():
    with open(APP, encoding="utf-8") as fh:
        return fh.read()


def test_the_tip_about_reading_a_prep_quotes_its_button():
    tips = re.search(r"const BRIEF_TIPS = \[(.*?)\];", _src(), re.S).group(1)
    assert "Read your prep opens" not in tips, tips
    assert "\\u201cRead your prep\\u201d, on an interview, opens its prep full screen." in tips, tips


def test_each_help_cards_line_ends_with_a_full_stop():
    body = re.search(r"function helpWhy\(i\) \{(.*?)\n  \}", _src(), re.S).group(1)
    lines = re.findall(r'"([^"]+)"\s*(?::|$)', body)
    said = [t for t in re.findall(r'\? (?:"Your profile: every " \+ noun\(\) \+ )?"([^"]+)"', body)]
    assert said and len(said) == 3, (said, lines)
    assert all(t.endswith(".") for t in said), said
