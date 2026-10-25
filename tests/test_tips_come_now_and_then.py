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


def test_notes_already_sent_mean_it_is_not_the_first_round(profile, tmp_path, monkeypatch):
    """Each chat keeps its own copy of the record until its work lands, so a person on
    their thirteenth round of notes in a day was told it was their first (2026-10-24). The
    message log says otherwise: a first note that went, or a reply, is there for good."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv(person.STATE_ENV, str(state_dir))
    log = state_dir / "network_threads.csv"
    log.write_text("contact_id,date,direction,channel,scenario,summary,full_text,subject\n"
                   "wren_halloway,2026-10-21,out,connection,connection_request,,,\n",
                   encoding="utf-8")
    # A bare request is not a note anyone drafted: still the first round of notes.
    assert tips.line("networking", DAY, {}) == tips.FIRST["networking"]
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("juno_quarrie,2026-10-21,out,connection,connection_note,Note sent,Hi Juno,\n")
    state = {}
    assert tips.line("networking", DAY, state) != tips.FIRST["networking"]
    assert state["first"]["networking"] == DAY.isoformat()     # and it is recorded as had
    assert tips.line("reply", DAY, {}) == tips.FIRST["reply"]     # no reply has gone yet
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("juno_quarrie,2026-10-22,out,message,reply,Reply sent,Thanks Juno,\n")
    assert tips.line("reply", DAY, {}) != tips.FIRST["reply"]


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


# The tour, 2026-10-25. The maintainer: "maybe a prompt in setup like would you like to know
# how to use this app / x feature ... not walls of text and beginner friendly but again only
# if necessary or user asks ... be smart here", and of the tips: "make sure it works makes
# sense doesnt spam the user ... in the setup maybe a few more than otherwise but again dont
# spam".

def _words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def test_the_tour_is_one_short_line_a_thing_and_each_topic_a_few_lines(profile):
    state = {}
    menu = tips.tour("", DAY, state)
    lines = menu.splitlines()
    assert lines[0] == tips.TOUR_OPEN and lines[-1] == tips.TOUR_CLOSE
    assert len(lines) <= 12 and _words(menu) <= 150
    assert all(_words(l) <= 14 for l in lines[1:-1])
    for key, menu_line, detail in tips.TOUR:
        assert _words(detail) <= 60, key
        assert "\n" not in detail


def test_a_topic_is_found_by_its_name_or_its_words_and_an_unknown_one_gets_the_list(profile):
    state = {}
    assert tips.tour("interview", DAY, state) == dict((k, d) for k, _, d in tips.TOUR)["interview"]
    assert tips.tour("build my resume", DAY, {}).startswith("Say \"build my resume\"")
    assert tips.tour("knitting", DAY, {}).startswith(tips.TOUR_OPEN)


def test_what_the_tour_showed_is_not_tipped_again_nor_the_tour_itself(profile):
    state = {}
    tips.line("search", DAY, state)                         # the first time
    tips.tour("", DAY, state)                               # they asked to be shown around
    later = [tips.line(a, DAY + dt.timedelta(days=n), state)
             for n in range(2, 120, 2) for a in ("search", "apply", "interview", "networking")]
    said = [s for s in later if s]
    assert all("show me around" not in s for s in said)
    covered = {tid for tid in tips.COVERED_BY}
    for tip_id, _, text in tips.TIPS:
        if tip_id in covered:
            assert all(text.split(tips.OFF_HINT)[0] != s.split(tips.OFF_HINT)[0] for s in said), tip_id


def test_someone_who_never_took_the_tour_is_offered_it_once_in_a_tip(profile):
    state = {}
    tips.line("search", DAY, state)
    said = [tips.line("search", DAY + dt.timedelta(days=n), state) for n in range(1, 120)]
    offers = [s for s in said if "show me around" in s]
    assert len(offers) == 1


def test_how_to_stop_them_is_said_once_with_the_first_tip_and_never_with_a_first_time_line(profile):
    state = {}
    first = tips.line("search", DAY, state)
    assert tips.OFF_HINT not in first
    said = [s for s in (tips.line("search", DAY + dt.timedelta(days=n), state)
                        for n in range(1, 120)) if s]
    assert said[0].endswith(tips.OFF_HINT)
    assert sum(tips.OFF_HINT in s for s in said) == 1


def test_setup_day_has_a_few_lines_never_a_stream(profile):
    # Setup's own day: the first shortlist and the first application each say their
    # first-time line; a third kind of work that day waits for its next time, and no tip
    # comes on top however many replies follow.
    state = {}
    said = [tips.line(a, DAY, state) for a in ("search", "apply", "networking", "interview",
                                               "search", "apply", "general")]
    assert [s for s in said if s] == [tips.FIRST["search"], tips.FIRST["apply"]]
    assert tips.line("networking", DAY + dt.timedelta(days=1), state) == tips.FIRST["networking"]


def test_a_second_chat_the_same_day_gives_no_second_tip(profile, monkeypatch):
    # The cloud chat gave a tip and landed its record; the computer chat's own copy is
    # older. Read together, the computer chat stays quiet.
    landed = {"first": {"search": "2026-10-01"}, "last": DAY.isoformat(),
              "shown": {"rephrase": DAY.isoformat()}, "areas": {"search": DAY.isoformat()}}
    (profile / tips.FILE).write_text(json.dumps({"first": {"search": "2026-10-01"},
                                                 "last": "2026-10-10"}), encoding="utf-8")
    monkeypatch.setattr(tips, "_on_master", lambda: landed)
    assert tips.line("search", DAY) == ""
    assert tips.line("apply", DAY + dt.timedelta(days=0), tips.load()) in ("", tips.FIRST["apply"])


def test_the_later_on_or_off_wins_across_chats():
    a = {"off": True, "off_set": "2026-10-20T09:00:00"}
    b = {"off": False, "off_set": "2026-10-22T09:00:00"}
    assert tips._merge(a, b)["off"] is False
    assert tips._merge(b, a)["off"] is False
    assert tips._merge({"off": True}, {})["off"] is True


def test_tour_words_are_plain():
    jargon = re.compile(r"`|(?<!\w)--[a-z]|\b(?:git|branch|master|merge|commit|repo|"
                        r"repository|python3?|upgrade)\b|\.py\b|—", re.I)
    texts = [tips.TOUR_OPEN, tips.TOUR_CLOSE, tips.OFF_HINT]
    texts += [m for _, m, _ in tips.TOUR] + [d for _, _, d in tips.TOUR]
    for t in texts:
        assert not jargon.search(t), t


def test_tour_command_prints_and_records(profile, capsys):
    assert tips.main(["tour"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(tips.TOUR_OPEN)
    got = json.loads((profile / tips.FILE).read_text())
    assert got["toured"] and set(got["tour_seen"]) == {k for k, _, _ in tips.TOUR}
