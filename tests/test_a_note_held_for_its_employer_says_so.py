"""A first note held back because people at its employer already wait on a reply says so, with a
way to go ahead anyway, and never promises a read that will not happen.

On 2026-11-10 a read of ten profiles on the person's computer skipped one person on purpose:
two people at their employer were already waiting on a reply. Her note still said "Waiting
for their profile: Claude reads it on your computer by itself, then rewrites this note", so
the card promised work nothing would do. Invented people and employers only.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools", "network"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import _go, _sample  # noqa: E402


class _Ctx:
    def __init__(self):
        self._got = {}
        self.contacts, self.threads, self.today = [], [], dt.date(2026, 10, 25)


def test_an_employer_with_people_waiting_holds_the_note_and_says_why(monkeypatch):
    import reading
    monkeypatch.setattr(reading, "employer_limit", lambda company: (2, {}))
    waiting = {"Harbourline Insurance": [{"name": "A"}, {"name": "B"}], "Oakmere Foods": [{"name": "C"}]}
    monkeypatch.setattr(reading, "at_employer", lambda company, contacts, also=(), today=None, threads=None, until=None,
                        owed=None: (waiting.get(company, []), []))
    ctx = _Ctx()
    said = app_model.employer_held(ctx, "Harbourline Insurance", "c1")
    assert said == "On hold: you already have 2 people waiting on a reply at Harbourline Insurance", said
    assert app_model.employer_held(ctx, "Oakmere Foods", "c2") == ""
    assert app_model.employer_held(ctx, "", "c3") == ""


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


LOOK = r"""(() => {
  const l = document.querySelector('[data-k="held:msg-ash-1"]');
  return l ? {text: l.textContent.replace(/\s+/g, ' ').trim(), hold: l.getAttribute('data-hold'),
              anyway: [...l.querySelectorAll('button')].map((b) => b.textContent.trim())} : null;
})()"""


def test_the_card_says_its_own_hold_with_go_ahead_anyway(run, tmp_path):
    m = _sample()
    for msg in m["messages"]:
        if msg["id"] == "msg-ash-1":
            msg["hold"] = "On hold: you already have 2 people waiting on a reply at " + (msg.get("employer") or "their employer")
            msg["hold_why"] = "employer_full"
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": LOOK}], journeys.WIDE, model=m)
    assert not got["errors"], got["errors"]
    r = got["after"][0]["eval"]
    assert r, "the held note has its line"
    assert r["text"].startswith("On hold: you already have 2 people") and "by itself" not in r["text"], r
    assert r["hold"] == "own" and r["anyway"] == ["Go ahead anyway"], r


def test_a_note_held_on_their_record_says_its_hold_never_a_read_by_itself():
    """The audit of 2026-11-10 (DW-2): a note waiting on a read and held on the person's record
    ("Hold until ...") said "Claude reads it on your computer by itself": the read line stood
    over the hold. The hold says itself; only the employer's own hold comes before it."""
    read = app_model.READ_HOLD["computer"]
    mine = {"said": "On hold until 23 Nov: they asked to talk after their busy season", "role": False,
            "until": "2026-11-23"}
    hold, why = app_model.note_hold(read, None, mine)
    assert why == "person_hold" and "by itself" not in hold, hold
    assert app_model.note_hold(read, None, dict(mine, decided=True))[1] == "decided"
    full = "On hold: you already have 2 people waiting on a reply at Harbourline Insurance"
    assert app_model.note_hold(full, "employer_full", mine) == (full, "employer_full")
    assert app_model.note_hold(read, None, None) == (read, None)
