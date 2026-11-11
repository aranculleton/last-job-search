"""Help Claude do more is found on To do, without crowding today's five or its counts.

The maintainer, 2026-11-07: "i feel like help claude do more is more important but its a bit
too tucked away here": it sat at the foot of To do as a quiet fold after "Not due yet", among
the hidden and done lines. Then it was one faint line right after today's things, and that
was "so hidden" too (2026-11-10). Now it is one soft card there, above Not due yet: its
title, what the first one gives, and its one pill to start it; with nothing due today, its
first card shows under its own heading. It is never counted among today's things (DESIGN.md, Places). The sample (tests/
fixtures/app_model_sample.json) is an invented search.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

T = "2026-10-25T09:00:00Z"
READ = ("(() => { document.querySelectorAll('details.band-more').forEach((d) => { d.open = false; }); const m = document.querySelector('#main');"
        " const folds = [...m.querySelectorAll('details.band-more > summary')].map((s) => s.textContent.trim());"
        " const open = (c) => !c.closest('details:not([open])');"
        " const cards = [...m.querySelectorAll('.band [data-card]')].filter(open).map((c) => ((c.closest('.band').querySelector('h3') || {}).textContent || '') + ': ' + ((c.querySelector('.card-title') || {}).textContent || ''));"
        " const you = m.querySelector('[data-item=\"you\"]');"
        " return {folds, cards, sum: (m.querySelector('.sec-head p, .screen-sum, header p') || {}).textContent || '', youOpen: !!you && open(you)}; })()")


@pytest.fixture(scope="module")
def run():
    from test_the_page_journeys import browser
    yield from browser()


HELP = ("(() => { const m = document.querySelector('#main'); const c = m.querySelector('[data-item=\"help\"]');"
        " const all = [...m.querySelectorAll('.band, details.band-more, [data-item=\"help\"]')];"
        " return c ? {title: (c.querySelector('.card-title') || {}).textContent, text: c.textContent, folded: !!c.closest('details:not([open])'),"
        " pills: [...c.querySelectorAll('.card-actions .btn')].map((b) => b.textContent.trim()), soft: c.classList.contains('card'),"
        " more: [...m.querySelectorAll('.help-band details.band-more > summary')].map((s) => s.textContent.trim()), head: (m.querySelector('.help-band h3') || {}).textContent || null,"
        " before: all.filter((e) => e.matches('details.band-more') && /^Not due yet/.test(e.textContent.trim())).every((e) => c.compareDocumentPosition(e) & 4)} : null; })()")


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_help_is_one_soft_card_after_todays_things_and_above_not_due_yet(run, tmp_path, vp):
    """The maintainer, 2026-11-10: "help claude do more is so hidden". A faint line at the foot
    of To do is now one soft card in To do's own style: its title, the first one's line saying
    what it gives, its one pill to start it; the rest folded under "and N more"."""
    got = _go(run, tmp_path, [{"hash": "todo", "eval": READ}, {"eval": HELP},
                              {"open": "help-start", "eval": READ}], vp, clock=T)
    r, c = got["after"][0]["eval"], got["after"][1]["eval"]
    assert c and c["soft"] and not c["folded"] and c["title"] == "Help Claude do more", c
    assert "built from it" in c["text"] and c["pills"] == ["Finish your profile"], c
    assert all(not f.startswith("Help Claude do more") for f in r["folds"]), r["folds"]
    assert c["before"], c                                     # above Not due yet
    # Under its own small heading, never under "Needs your answer", and its fold says what it
    # holds: "and 1 more" said no noun (the screen review, 2026-11-11).
    assert c["head"] == "When you have a minute", c
    assert c["more"] and all(re.fullmatch(r"\d+ more ways? to help Claude", m) for m in c["more"]), c
    # Today's five are still today's things only, and the help is no card among them.
    today = [x for x in r["cards"] if not x.startswith(": Help Claude do more") and not x.startswith("Help Claude do more")]
    assert len(today) <= 5, r["cards"]
    assert not any("Finish your profile" in x for x in r["cards"]) and not r["youOpen"], r
    # Its pill puts the first one's own card in its place.
    assert got["after"][2]["eval"]["youOpen"], got["after"][2]["eval"]


def test_with_nothing_due_today_its_first_card_shows(run, tmp_path):
    m = _sample()
    for k in ("due", "needs_you", "messages", "interviews", "upcoming", "ready"):
        m[k] = []
    m["to_send"] = {"n": 0, "ids": []}
    for row in m["jobs"]["rows"]:
        row["alerts"] = []
    m["linkedin_export"] = None
    got = _go(run, tmp_path, [{"hash": "todo", "eval": READ, "read": "#main"}], PHONE, model=m, clock=T)
    r = got["after"][0]["eval"]
    text = got["after"][0]["text"]
    assert r["youOpen"], (r, text[:800])
    assert "Help Claude do more" in text
    # Never counted as something to do today.
    assert "1 thing today" not in text and "things today" not in text, text[:400]


def test_hidden_with_its_bin_it_comes_back_from_the_end_of_to_do(run, tmp_path):
    got = _go(run, tmp_path, [
        {"hash": "todo", "open": "hide:help", "count": '[data-item="help"]'},
        {"click": "Show 1 hidden this week", "read": ".todo-hidden-list"},
        {"click": "Bring back: Help Claude do more", "count": '[data-item="help"]'},
    ], PHONE, clock=T)
    first, shown, back = got["after"]
    assert first["count"] == 0 and "Help Claude do more" in shown["text"], (first, shown["text"])
    assert back["count"] == 1
