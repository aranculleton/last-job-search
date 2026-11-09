"""Settings, Your rules: one row, "Held back for now", says what the person's rules hold back
today, each a plain line with the day it opens and what lifts it, and folds every rule that
holds anything behind one link (T12 on the page).

An employer was shut for 45 days whenever two people there waited on a reply, and nothing on
the page said so or when it would open (the maintainer, 2026-11-09). The lines are the
engine's (tools/holds.py); the page only draws them.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_page  # noqa: E402
import holds  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _sample  # noqa: E402

CLOCK = "2026-11-09T09:30:00Z"
LINE = "Larchmont Health: open again Fri 27 Nov, or say 'more at Larchmont Health'"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _model(held=True):
    m = _sample()
    rules = dict(m.get("rules") or {})
    rules["held"] = ([{"id": "hold~employer_wait~larchmont health", "rule": "employer_wait",
                       "what": "Larchmont Health", "until": "2026-11-27", "line": LINE,
                       "say": "more at Larchmont Health"},
                      {"id": "hold~person_hold~celia marsh", "rule": "person_hold",
                       "what": "Celia Marsh", "until": None,
                       "line": "Celia Marsh: on hold with no end day, or say 'write to Celia again'",
                       "say": "write to Celia again"}] if held else [])
    rules["every_hold"] = [{"id": r["id"], "area": r["area"], "line": r["line"]}
                           for r in holds.rules()]
    m["rules"] = rules
    return m


def _go(run, tmp_path, steps, vp, model):
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    got = run("engine", html=path, viewport=vp, steps=steps, seed={},
              fake={"canSend": "available"}, clock=CLOCK)
    assert not got["errors"], got["errors"]
    return got


@pytest.mark.parametrize("vp", [WIDE, PHONE], ids=["wide", "phone"])
def test_held_back_is_one_row_with_a_line_each_and_every_rule_one_tap_below(run, tmp_path, vp):
    got = _go(run, tmp_path, [
        {"hash": "settings", "eval": "document.getElementById('main').textContent"},
        {"open": "info-sum:rules-held", "read": '[data-k="det:info:rules-held"]',
         "count": '[data-k="det:info:rules-held"] .held-row'},
        {"open": "few:held-rules", "count": '[data-k="det:info:rules-held"] .held-rule'},
    ], vp, _model())
    first, opened, every = got["after"]
    assert "Held back for now" in first["eval"] and "2 now" in first["eval"]
    assert opened["count"] == 2 and LINE in opened["text"], opened["text"][:400]
    assert "How every rule ends (%d)" % len(holds.RULES) in opened["text"]
    assert every["count"] == len(holds.RULES)


def test_with_nothing_held_it_says_so_and_still_opens_every_rule(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "settings", "eval": "document.getElementById('main').textContent"},
        {"open": "info-sum:rules-held", "read": '[data-k="det:info:rules-held"]'},
    ], WIDE, _model(held=False))
    first, opened = got["after"]
    assert "Nothing now" in first["eval"]
    assert "Nothing is held back today." in opened["text"]
