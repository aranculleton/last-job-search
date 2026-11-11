"""Settings, Your rules: one row, "Held back for now", says what the person's rules hold back
today, each a plain line with the day it opens and what lifts it, and folds every rule that
holds anything behind one link (T12 on the page).

An employer was shut for 45 days whenever two people there waited on a reply, and nothing on
the page said so or when it would open (the maintainer, 2026-11-09). The lines are the
engine's (tools/holds.py); the page only draws them.
"""
from __future__ import annotations

import os
import re
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
LINE = "Larchmont Health: 2 people there are waiting on a reply, so it opens again Fri 27 Nov"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _model(held=True):
    m = _sample()
    rules = dict(m.get("rules") or {})
    rules["held"] = ([{"id": "hold~employer_wait~larchmont health", "rule": "employer_wait",
                       "what": "Larchmont Health", "until": "2026-11-27", "line": LINE,
                       "say": "more at Larchmont Health", "lift": "Open it now"},
                      {"id": "hold~person_hold~celia marsh", "rule": "person_hold",
                       "what": "Celia Marsh", "until": None,
                       "line": "Celia Marsh: on hold with no end day",
                       "say": "write to Celia again", "lift": "Write again"}] if held else [])
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
    # Named for what it holds, with no count: "How every rule ends (35)" read as "you have
    # 35 rules" (the screen review, 2026-11-11).
    assert "How long each kind of hold lasts" in opened["text"] and "How every rule ends" not in opened["text"], opened["text"][-300:]
    assert not re.search(r"lasts \(\d+\)", opened["text"]), opened["text"][-300:]
    assert every["count"] == len(holds.RULES)


# Each held line's pill, and every rule grouped under its area's heading.
SHAPE = r"""(() => { const d = document.querySelector('[data-k="det:info:rules-held"]');
  const pills = [...d.querySelectorAll('.held-row button')].map((b) => [b.textContent.trim(), b.getAttribute('data-wakes')]);
  const heads = [...d.querySelectorAll('.held-area-name')].map((e) => e.textContent);
  const rule = d.querySelector('.held-rule');
  const gap = rule && rule.nextElementSibling ? rule.nextElementSibling.getBoundingClientRect().top - rule.getBoundingClientRect().bottom : null;
  return {pills, heads, gap, rowText: [...d.querySelectorAll('.held-row .held-t')].map((e) => e.textContent),
    wide: rule ? rule.closest('.held-rules').getBoundingClientRect().width : 0, fs: rule ? parseFloat(getComputedStyle(rule).fontSize) : 0}; })()"""


def test_a_held_line_ends_at_its_day_with_a_pill_that_lifts_it(run, tmp_path):
    """The screen review (2026-11-09): each line ended "or say 'more at <employer>'", and every
    rule was one wall of 34 lines."""
    got = _go(run, tmp_path, [
        {"hash": "settings"},
        {"open": "info-sum:rules-held"},
        {"open": "few:held-rules", "eval": SHAPE},
    ], WIDE, _model())
    r = got["after"][-1]["eval"]
    assert r["pills"] == [["Open it now", "talk"], ["Write again", "talk"]], r
    assert all("or say" not in t for t in r["rowText"]) and r["rowText"][0] == LINE, r
    assert r["heads"] == ["Jobs", "Applications", "People", "Messages", "Interviews", "This page"], r
    assert r["gap"] is not None and r["gap"] >= 4, r
    assert r["wide"] <= 64 * r["fs"], r


def test_the_pill_asks_claude_under_the_row(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "settings"},
        {"open": "info-sum:rules-held"},
        {"open": "held-lift:hold~employer_wait~larchmont health", "wait": 300,
         "read": '[data-k="det:info:rules-held"]'},
    ], WIDE, _model())
    last = got["after"][-1]
    asked = [w for w in last["work"] if w.get("kind") == "talk"]
    assert asked and asked[0]["args"]["text"] == "more at Larchmont Health", last["work"]
    assert asked[0]["args"]["about"]["id"] == "held", asked[0]
    # The hold's own id goes with its words, which can name two holds (the rules review,
    # 2026-11-11): Claude lifts it by the id (holds.py lift <id> --said <words>).
    assert asked[0]["args"]["about"]["ref"] == "hold~employer_wait~larchmont health", asked[0]
    assert "more at Larchmont Health" in last["text"], last["text"][:600]


def test_with_nothing_held_it_says_so_and_still_opens_every_rule(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "settings", "eval": "document.getElementById('main').textContent"},
        {"open": "info-sum:rules-held", "read": '[data-k="det:info:rules-held"]'},
    ], WIDE, _model(held=False))
    first, opened = got["after"]
    assert "Nothing now" in first["eval"]
    assert "Nothing is held back today." in opened["text"]


def test_a_learned_rule_said_for_now_is_asked_about_in_your_rules(run, tmp_path):
    """Your rules drew no learned rule (they have their own list), so one the person said was
    "for now" was asked about nowhere when its day came. One the engine marks Still right? is
    drawn there, saying it was for now, with Keep it (rules_view.for_now_review)."""
    m = _model(held=False)
    m["rules"]["rows"] = list(m["rules"].get("rows") or []) + [
        {"id": "rule~learned~1", "kind": "learned", "name": "Learned from you",
         "sentence": "Keep first notes to two lines.", "set_on": "2026-09-20",
         "words": "keep notes short for now", "review_on": "2026-10-20", "left_out": None,
         "edit": None, "drop": {"kind": "learned", "n": 1}, "still_right": True, "rev": "r1"}]
    got = _go(run, tmp_path, [
        {"hash": "settings", "eval": "document.getElementById('main').textContent"},
    ], WIDE, m)
    text = got["after"][0]["eval"]
    assert "Learned from you" in text and "Still right?" in text, text[:2000]


def _declined(rev):
    return {"id": "rule~declined~ormsby retail", "kind": "declined",
            "name": "No more from Ormsby Retail", "sentence": "No more roles from Ormsby Retail.",
            "set_on": "2026-11-08", "words": None, "review_on": None, "left_out": 0,
            "edit": None, "drop": {"kind": "declined", "key": "ormsby retail"},
            "still_right": False, "rev": rev}


@pytest.mark.parametrize("seen, shown", [("r-old", True), ("r-new", False)],
                         ids=["set-again-since", "the-one-binned"])
def test_a_rule_set_again_after_its_bin_is_listed(run, tmp_path, seen, shown):
    """The page hid a row of Your rules while an earlier bin on the same rule stood (up to 60
    days): an employer turned down again, or a role set aside again, after its bin was not
    listed. A bin hides only the row it was tapped on (its rev)."""
    m = _model(held=False)
    m["rules"]["rows"] = list(m["rules"].get("rows") or []) + [_declined("r-new")]
    seed = {"actions/act~rule~declined~1": {
        "item": "rule~declined~ormsby retail", "action": "rule.drop", "value": {},
        "at": "2026-11-09T08:00:00Z", "rev_seen": seen, "tab": "t0"}}
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(m)))
    got = run("engine", html=path, viewport=WIDE, seed=seed, fake={"canSend": "available"},
              clock=CLOCK, steps=[{"hash": "settings",
                                   "eval": "document.getElementById('main').textContent"}])
    assert not got["errors"], got["errors"]
    assert ("Employers you've turned down (1)" in got["after"][0]["eval"]) is shown
