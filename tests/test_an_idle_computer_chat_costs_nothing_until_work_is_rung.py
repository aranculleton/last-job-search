"""An idle computer's own chat costs no Claude turn: it is woken only when work is rung for it.

Issue #322: the computer's own chat (the listener) kept one background `sleep 6600` going, and
each time it ended the whole chat woke and ran a full turn (the page read three times, its own
wake recorded, its bell republished, a new sleep) with nothing to do: about twelve times a day,
each re-reading a long history. The sleep was there to keep the chat's watch on its bell alive,
since a watch Claude Code starts by itself can end after hours with nothing happening
(claude_surfaces: page-watch), and it was kept under two hours because a background command
was taken to stop there; in the desktop app it does not (background-command-limit).

Now whoever rings it also leaves the ring in the person's copy on GitHub (it lands with that
chat's save), and the listener's wait is code: it looks there once a minute and ends, waking
the chat, only when work is rung for that chat. A watch that lapsed costs a minute or two, never
a turn. Every person, chat and computer here is invented.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from datetime import timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import computer  # noqa: E402
from test_a_computer_chat_is_seen_to_its_end import NOW, T, URL, _apply, _as  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import _db  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402
from test_the_computers_own_chat_takes_work_with_no_tap import (  # noqa: E402
    COPY, EVERY_TOOL, LISTENER, STARTER, WORK, _with)

ME = LISTENER["chat"]


def _git(cwd, *args) -> str:
    r = subprocess.run(["git", "-C", str(cwd), "-c", "user.name=Test Person", "-c",
                        "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


@pytest.fixture
def copy(tmp_path, monkeypatch):
    """A person's copy on GitHub (a bare repo) and the computer's checkout of it, as the state
    root; `ring(chat, at)` lands a ring on its master, as a cloud chat's save does."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    cloud = tmp_path / "cloud"
    _git(tmp_path, "clone", "-q", str(origin), str(cloud))
    _git(cloud, "checkout", "-q", "-B", "master")
    (cloud / "README.md").write_text("A copy.\n", encoding="utf-8")
    # The copy's own code on GitHub, which every chat that rings the listener runs, leaves rings.
    os.makedirs(cloud / "tools")
    (cloud / "tools" / "computer.py").write_text(
        'RING_FILE = ("documents", "computer_ring.json")\n', encoding="utf-8")
    _git(cloud, "add", "-A")
    _git(cloud, "commit", "-q", "-m", "Start")
    _git(cloud, "push", "-q", "origin", "master")
    here = tmp_path / "computer"
    _git(tmp_path, "clone", "-q", str(origin), str(here))
    _as(monkeypatch, "computer", here)

    def ring(chat: str, at, other: str = "", code: str = "") -> None:
        os.makedirs(cloud / "documents", exist_ok=True)
        if code:
            (cloud / "tools" / "computer.py").write_text(code, encoding="utf-8")
        elif other:
            (cloud / "documents" / "other.txt").write_text(other, encoding="utf-8")
        else:
            (cloud / "documents" / "computer_ring.json").write_text(
                json.dumps({"chat": chat, "rung_at": app_model.stamp(at)}), encoding="utf-8")
        _git(cloud, "add", "-A")
        _git(cloud, "commit", "-q", "-m", "Save the search's work")
        _git(cloud, "push", "-q", "origin", "master")
    return {"here": here, "ring": ring}


class Clock:
    """The wait's own clock and sleep, so a test runs its rounds in no time."""

    def __init__(self, at):
        self.t = at.timestamp()
        self.slept = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s) -> None:
        self.slept.append(s)
        self.t += s


def _wait(clock, rounds, again=False) -> str:
    return computer.listener_wait(ME, sleep=clock.sleep, clock=clock, rounds=rounds, again=again)


# ------------------------------------------------------------------ the ring, where code reads it


def test_a_ring_is_left_in_the_copy_where_the_computers_chat_looks_for_it(tmp_path, monkeypatch):
    """Rung, the computer's own chat also finds the ring in the person's copy, so a watch that
    lapsed after quiet hours still reaches it: the ring is written beside the page's record and
    saved at once, by every chat that rings it."""
    import app_setup
    _as(monkeypatch, "cloud", tmp_path)
    monkeypatch.setattr(app_setup, "origin", lambda: ("someone", "my-job-search"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": URL})
    db = _with(_db(WORK), LISTENER)
    _apply(db, computer.listener_rung(db, T, str(tmp_path / "r")))
    with open(computer.ring_path(), encoding="utf-8") as fh:
        assert json.load(fh) == {"chat": ME, "rung_at": NOW}
    assert computer.ring_path().endswith(os.path.join("documents", "computer_ring.json"))
    got = computer.route(db, T, chat=STARTER["chat"], envs=BRIDGE, tools=EVERY_TOOL, url=URL,
                         copy=COPY)
    assert got["route"] == "ring computer chat"
    assert got["then"].index("listener-rung") < got["then"].index("land.py --detach")
    helper = computer.route(db, T, chat="session_helperEXAMPLE", tools=["ArtifactData"], url=URL,
                            copy=COPY)
    assert "land.py --detach" in helper["handback"][-1]
    # The starter's own bell is rung as before: nothing is left in the copy for it.
    assert "land.py --detach" not in computer.ring_steps(STARTER["bell"], "b.html")


# ------------------------------------------------------------------ the wait is code


def test_the_wait_wakes_the_chat_only_when_work_is_rung_for_it(copy):
    clock = Clock(T)
    # Nothing rung: it looks once a minute and never ends, so the chat is never woken.
    assert _wait(clock, 5) == ""
    assert clock.slept == [computer.LISTENER_POLL_S] * 5 and computer.LISTENER_POLL_S <= 60
    assert computer.wait_running(T + timedelta(seconds=clock.t - T.timestamp()))
    # Other saves, and a ring for another chat, wake nobody.
    copy["ring"]("", T, other="a note\n")
    assert _wait(clock, 2) == ""
    copy["ring"]("session_otherEXAMPLE", T + timedelta(minutes=8))
    assert _wait(clock, 2) == ""
    # Work rung for this chat: the wait ends with one line, and is no longer running.
    copy["ring"](ME, T + timedelta(minutes=9))
    said = _wait(clock, 3)
    assert said.startswith("rung: ") and f"listener-steps --chat {ME}" in said, said
    after = T + timedelta(seconds=clock.t - T.timestamp())
    assert not computer.wait_running(after)
    # Started again, the same ring never wakes it twice.
    assert _wait(clock, 3) == ""


def test_a_ring_the_bell_already_answered_wakes_nothing_more(copy, tmp_path):
    """Its watch alive, the bell woke the chat at once and it took the work: the same ring,
    landing on GitHub a minute later, is answered already."""
    rung = T - timedelta(minutes=1)
    db = _with(_db(WORK), LISTENER, rung_at=app_model.stamp(rung), rings=1)
    assert computer.listener_woke(db, ME, T, str(tmp_path / "w"))["next"].startswith("take:")
    copy["ring"](ME, rung)
    assert _wait(Clock(T), 3) == ""
    copy["ring"](ME, T + timedelta(minutes=5))
    assert _wait(Clock(T + timedelta(minutes=6)), 2).startswith("rung: ")


def test_a_wait_that_cannot_read_github_wakes_the_chat_only_as_often_as_before(copy):
    """GitHub out of reach (or refusing): the ring can only come through the bell, so after the
    old interval the chat is woken to keep its bell's watch, and never sooner."""
    _git(copy["here"], "remote", "set-url", "origin", str(copy["here"] / "nowhere.git"))
    clock = Clock(T)
    rounds = computer.LISTENER_WAIT_S // computer.LISTENER_POLL_S
    said = _wait(clock, rounds + 3)
    assert said.startswith("blind: ") and f"listener-steps --chat {ME}" in said, said
    waited = clock.t - T.timestamp()
    assert computer.LISTENER_WAIT_S <= waited <= computer.LISTENER_WAIT_S + \
        computer.LISTENER_POLL_S, waited
    assert computer.LISTENER_WAIT_S < 2 * 3600 and not computer.wait_running(
        T + timedelta(seconds=waited))


def test_until_the_copys_code_leaves_rings_the_wait_keeps_the_bell_as_often_as_before(copy):
    """The computer took this update before the chats in the cloud that ring it: none of them
    leaves a ring on GitHub yet, so its bell is the only way in, and the wait wakes it to keep
    the bell's watch at the old interval, never sooner; once the copy's code leaves rings, it
    never wakes it for that again."""
    copy["ring"]("", T, code="def route():\n    pass\n")
    clock = Clock(T)
    rounds = computer.LISTENER_WAIT_S // computer.LISTENER_POLL_S
    said = _wait(clock, rounds + 3)
    assert said.startswith("keep: ") and f"listener-steps --chat {ME}" in said, said
    waited = clock.t - T.timestamp()
    assert computer.LISTENER_WAIT_S <= waited <= computer.LISTENER_WAIT_S + \
        computer.LISTENER_POLL_S, waited
    copy["ring"]("", T, code='RING_FILE = ("documents", "computer_ring.json")\n')
    assert _wait(clock, rounds + 3) == ""


def test_a_second_wait_takes_over_and_the_first_goes_quiet_without_waking_the_chat(copy):
    """A chat that lost track of its wait (a compaction) may start another: the newer one takes
    over, and the first stops looking and never ends, since its end would wake the chat."""
    first, second = Clock(T), Clock(T)
    took = []

    def sleep(s):
        first.sleep(s)
        if not took:
            took.append(_wait(second, 1))
    assert computer.listener_wait(ME, sleep=sleep, clock=first, rounds=4) == ""
    assert took == [""] and first.slept[0] == computer.LISTENER_POLL_S
    assert all(s >= 3600 for s in first.slept[1:]), first.slept
    # A wait is running while it is heard from, and not once it has gone quiet that long.
    assert computer.wait_running(T + timedelta(minutes=2))
    assert not computer.wait_running(T + timedelta(seconds=computer.LISTENER_BEAT_S + 120))


# ------------------------------------------------------------------ a wake costs one step at most


def test_an_idle_wake_ends_in_one_step_and_starts_no_second_wait(copy, tmp_path):
    rest_db = _with(_db(), LISTENER)
    # No wait running (the chat has just become it, or its wait ended): the wake's steps read
    # the page; a wait stopped at a time limit is started again in one call, nothing more.
    steps = "\n".join(computer.listener_steps(URL, ME))
    assert f"listener-woke \"$D\" --chat {ME}" in steps
    assert f"listener-wait --chat {ME} --again" in steps and "run_in_background true" in steps
    rest = computer.listener_woke(rest_db, ME, T, str(tmp_path / "a"))["next"]
    stay = computer.listener_become(rest_db, ME, str(tmp_path / "s.html"), T)
    for said in (rest, stay):
        assert f"listener-wait --chat {ME}" in said and "run_in_background true" in said, said
    # Its wait running: anything but its bell ends the turn at once, and nothing starts a second.
    assert _wait(Clock(T), 1) == ""
    steps = computer.listener_steps(URL, ME, now=T)
    assert "- Your bell page republished: do steps 1 and 2 below." in steps, steps
    assert any("end the turn now" in ln and "older plain sleep" in ln for ln in steps), steps
    assert "--again" not in "\n".join(steps)
    # A message the person typed is answered, never taken for a wake.
    assert any("person typed" in ln and "answer it" in ln for ln in steps)
    rest = computer.listener_woke(rest_db, ME, T, str(tmp_path / "b"))["next"]
    stay = computer.listener_become(rest_db, ME, str(tmp_path / "s.html"), T)
    for said in (rest, stay):
        assert "start no other" in said and "listener-wait --chat" not in said, said
    # Chats on the computer can share a folder: the wait of a listener since replaced is never
    # taken for the new one's, which starts its own.
    assert not computer.wait_running(T, "session_macA")
    become = computer.listener_become(_with(_db()), "session_macA", str(tmp_path / "n.html"), T)
    assert "listener-wait --chat session_macA" in become and "start no other" not in become
    # Nothing anywhere sleeps any more.
    for said in (rest, stay, "\n".join(steps), computer.LISTENER_WAIT):
        assert "command sleep" not in said and "sleep 6600" not in said, said
    assert "never a foreground sleep" in computer.LISTENER_WAIT


def test_a_listener_on_the_old_sleep_moves_to_the_new_wait_at_its_next_wake(tmp_path, monkeypatch):
    """Its old `sleep 6600` ends and it runs listener-steps, as it was told: with no wait of the
    new kind running, that is the page read and listener-woke, whose last step starts the new
    wait. Nothing is left for the person to do, and it never sleeps again."""
    _as(monkeypatch, "computer", tmp_path)
    old = _with(_db(), LISTENER, kept_at=app_model.stamp(T - timedelta(hours=2)))
    steps = "\n".join(computer.listener_steps(URL, ME, now=T))
    assert "an older plain sleep of yours ending" in steps and "listener-woke" in steps
    got = computer.listener_woke(old, ME, T, str(tmp_path / "w"), path=str(tmp_path / "l.html"))
    assert got["next"].startswith("keep:") and f"listener-wait --chat {ME}" in got["next"]
    assert "sleep 6600" not in got["next"]


# ------------------------------------------------------------------ a ring that comes the slow way


def test_a_quiet_listener_is_given_longer_to_answer_since_its_ring_may_come_through_github(
        tmp_path, monkeypatch):
    _as(monkeypatch, "cloud", tmp_path)
    quiet = dict(LISTENER, answered_at=app_model.stamp(T - timedelta(hours=3)),
                 kept_at=app_model.stamp(T - timedelta(hours=3)))
    six = _with(_db(WORK), quiet, rung_at=app_model.stamp(T - timedelta(minutes=6)), rings=1)
    assert computer.listener_live(six, T) and computer.listener_rung_lately(six, T)
    late = _with(_db(WORK), quiet, rung_at=app_model.stamp(
        T - timedelta(seconds=computer.LISTENER_LATE_ANSWER_S + 60)), rings=1)
    assert computer.listener_stale(late, T)
    assert computer.LISTENER_LATE_ANSWER_S <= 15 * 60
    # One that answered lately still has five minutes, as before.
    fresh = _with(_db(WORK), LISTENER, rung_at=app_model.stamp(T - timedelta(minutes=6)), rings=1)
    assert computer.listener_stale(fresh, T)


# ------------------------------------------------------------------ idle wakes are filed


def test_idle_wakes_that_pile_up_are_filed_once_in_the_maintainers_copy(tmp_path, monkeypatch):
    """A chat ran the full wake about twelve times a day with nothing to do and filed nothing,
    because nothing it ran was refused (issue #322). Now each wake with nothing waiting counts
    itself, and in the maintainer's own copy the one that makes it too many in a day prints the
    filing line, once a week at most."""
    import sync_app
    _as(monkeypatch, "computer", tmp_path)
    monkeypatch.setattr(sync_app, "maintainers", lambda *a, **k: True)
    idle = _with(_db(), LISTENER)
    said = [computer.listener_woke(idle, ME, T + timedelta(hours=h), str(tmp_path / f"w{h}"))
            ["next"] for h in range(computer.LISTENER_IDLE_FILE_AT + 1)]
    filed = [s for s in said if "tools/app_bug.py met" in s]
    assert filed == [said[computer.LISTENER_IDLE_FILE_AT - 1]], said
    assert "tools/computer.py:listener_woke" in filed[0]
    # A wake its wait asked for only to keep the bell, while the chats that ring it leave no
    # ring on GitHub yet (the update reached this computer first), is expected, and not counted.
    before = len(computer._checkout_json(computer.IDLE_FILE)["wakes"])
    computer._save_checkout_json(computer.WAIT_FILE, {"ended": "keep"})
    computer.listener_woke(idle, ME, T + timedelta(hours=6), str(tmp_path / "k"))
    assert len(computer._checkout_json(computer.IDLE_FILE)["wakes"]) == before
    # A wait started again after a time limit counts.
    clock = Clock(T + timedelta(days=9))
    for _ in range(computer.LISTENER_IDLE_FILE_AT):
        assert _wait(clock, 1, again=True) == ""
    later = computer.listener_woke(_with(_db(WORK), LISTENER), ME, T + timedelta(days=9),
                                   str(tmp_path / "x"))["next"]
    assert later.startswith("take:") and "tools/app_bug.py met" in later
    # Outside the maintainer's copy nothing is filed, and the person hears nothing.
    monkeypatch.setattr(sync_app, "maintainers", lambda *a, **k: False)
    for h in range(computer.LISTENER_IDLE_FILE_AT + 2):
        got = computer.listener_woke(idle, ME, T + timedelta(days=20, hours=h),
                                     str(tmp_path / f"y{h}"))["next"]
        assert "app_bug" not in got


def test_the_wait_command_prints_its_line_and_the_page_needs_no_read(copy, monkeypatch):
    copy["ring"](ME, T + timedelta(minutes=1))
    monkeypatch.setattr(computer, "LISTENER_POLL_S", 0)
    out = io.StringIO()
    with redirect_stdout(out):
        assert computer.main(["listener-wait", "--chat", ME]) == 0
    assert out.getvalue().startswith("rung: ")
