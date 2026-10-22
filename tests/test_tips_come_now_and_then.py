"""A short line on how to use the app, the first time and then now and then, never a stream.

The maintainer, 2026-10-22: after a first networking round, or any step, people need to
know the first go may be off and that saying so makes it better, and now and then a tip
on how to use the app, "short, concise, easy to understand, and NOT EVERY TIME".
tools/tips.py decides when, and these pin how often.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import person  # noqa: E402
import tips  # noqa: E402

DAY = dt.date(2026, 10, 22)


@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    d.mkdir()
    (d / "person.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv(person.ENV, str(d))
    return d


def test_the_first_time_says_the_first_go_may_be_off_and_how_to_say_so(profile):
    state = {}
    first = tips.line("networking", DAY, state)
    assert first == tips.FIRST["networking"] and "tell me" in first.lower()
    # Not again that day, in that kind of work or another one already started.
    assert tips.line("networking", DAY, state) == ""


def test_a_first_time_in_a_new_kind_of_work_is_said_even_the_same_day(profile):
    state = {}
    tips.line("search", DAY, state)
    assert tips.line("apply", DAY, state) == tips.FIRST["apply"]


def test_tips_are_now_and_then_never_every_reply(profile):
    state = {}
    tips.line("networking", DAY, state)                       # the first time
    said = [tips.line("networking", DAY + dt.timedelta(days=n), state) for n in range(1, 31)]
    shown = [s for s in said if s]
    # Over a month of daily use: a tip at most every week in one kind of work.
    assert 1 <= len(shown) <= 5
    assert all(s.startswith("Tip: ") for s in shown)
    assert len(set(shown)) == len(shown)                       # each tip once


def test_across_kinds_of_work_at_most_one_line_every_two_days(profile):
    state = {}
    for area in ("search", "apply", "networking", "interview"):
        tips.line(area, DAY, state)                           # every first time, day one
    days = [DAY + dt.timedelta(days=n) for n in range(1, 15)]
    lines = [(d, tips.line(a, d, state)) for d in days for a in ("search", "apply")]
    when = [d for d, s in lines if s]
    assert all((b - a).days >= tips.GAP_DAYS for a, b in zip(when, when[1:]))


def test_no_more_tips_means_none(profile, capsys):
    assert tips.main(["off"]) == 0
    assert tips.main(["search"]) == 0 and "search" not in capsys.readouterr().out.lower().replace(
        "tips: none from now on", "")
    assert json.loads((profile / tips.FILE).read_text())["off"] is True
    tips.main(["on"])
    capsys.readouterr()
    tips.main(["search"])
    assert capsys.readouterr().out.strip() == tips.FIRST["search"]


def test_what_was_said_is_kept_so_a_new_chat_does_not_repeat_it(profile, capsys):
    tips.main(["apply"])
    assert capsys.readouterr().out.strip() == tips.FIRST["apply"]
    tips.main(["apply"])
    assert capsys.readouterr().out == ""


def test_without_a_profile_it_says_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(person.ENV, str(tmp_path / "nowhere"))
    assert tips.main(["search"]) == 0 and capsys.readouterr().out == ""


JARGON = re.compile(r"`|--|\b(?:git|branch|master|merge|commit|repo|repository|CLI|config|"
                    r"gmail|e-?mail|inbox)\b", re.I)


def test_every_line_is_short_and_plain():
    texts = list(tips.FIRST.values()) + [t for _, _, t in tips.TIPS]
    for text in texts:
        assert len(text.split()) <= 32, text
        assert not JARGON.search(text), text
        assert "—" not in text, text
    assert set(tips.FIRST) == set(tips.AREAS)
    assert all(set(suits) <= set(tips.AREAS) for _, suits, _ in tips.TIPS)


def test_the_commands_end_with_the_tip_line_not_a_line_of_their_own():
    for name, area in (("apply", "apply"), ("network", "networking"), ("reply", "reply"),
                       ("interview", "interview"), ("prep", "prep"), ("rank", "search")):
        with open(os.path.join(ROOT, ".claude", "commands", name + ".md"), encoding="utf-8") as fh:
            text = fh.read()
        assert f"tools/tips.py {area}" in text, name
        assert "It sticks from now on.\"" not in text, name
