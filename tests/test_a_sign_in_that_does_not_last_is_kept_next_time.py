"""A LinkedIn sign-in on the computer that does not last is seen as one, the person is asked
once, on their page, to have Claude's browser keep the next one, and it never stops the day.

The maintainer's Mac, 2026-11-11: LinkedIn was "signed out again", and the computer's
saved-sign-in setting read "unknown", so keeping the sign-in was never asked for. The
heartbeat judged a lost sign-in only by the heartbeat before it, so one made on the page and
gone by the next look was never one, and nothing ever recorded the setting as on. The local
review the same day (5): a sign-in page minutes after the person signed in, before anything
was read, was friction, which stopped the whole day's reads, the page said LinkedIn asked
Claude to slow down, and signing in on the page lifted nothing. Invented people and computers
only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import claude_surfaces  # noqa: E402
import computer  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import NOW, Search, _w  # noqa: E402
from test_the_computer_side_just_works import BRIDGE  # noqa: E402

T = app_model.parse_time(NOW)
WID = "network~read~1"


def _at(minutes: float) -> str:
    return app_model.stamp(T + dt.timedelta(minutes=minutes))


def _look(minutes: float, linkedin: str) -> dict:
    return computer.beat_fields("Studio Laptop", T + dt.timedelta(minutes=minutes),
                                browser="shown", linkedin=linkedin, version="9.9.9", task=False)


def _asked() -> dict:
    """A read waiting on its own Sign in to LinkedIn card (app.py done --signin linkedin)."""
    return _w("network", "Harbourline Bank", to="computer", title="Reading 3 profiles",
              status="needs_you", note="LinkedIn is signed out in Claude's browser.",
              needs={"question": "LinkedIn is signed out in Claude's browser.",
                     "signin": "linkedin"},
              asked_you_at=_at(-1))


def _lost_beat() -> dict:
    """Signed out at one look, signed in on the page after it, signed out again at the next."""
    first = _look(-120, "out")
    again = _look(0, "out")
    return dict(again, **computer.cookies_seen(first, again, since_in=_at(-60)))


# ------------------------------------------------------------------ the heartbeat (J5)


def test_a_sign_in_made_and_lost_between_two_looks_is_a_lost_sign_in():
    first, again = _look(-120, "out"), _look(0, "out")
    got = computer.cookies_seen(first, again, since_in=_at(-60))
    assert got["keep_cookies"] == "off"
    assert got["signin_lost"] == {"in_at": _at(-60), "out_at": again["seen_at"]}
    # No sign-in between the two looks: one sign-out, never a lost sign-in.
    assert "signin_lost" not in computer.cookies_seen(first, again, since_in=_at(-180))
    # Still signed out at the next look: the loss is kept, so the page keeps saying it.
    beat = dict(again, **got)
    assert computer.cookies_seen(beat, _look(5, "out"))["signin_lost"] == got["signin_lost"]
    # Signed in again: it goes.
    assert "signin_lost" not in computer.cookies_seen(beat, _look(10, "in"))


def test_their_word_on_the_page_records_the_setting_on_until_a_sign_in_is_lost_after_it():
    beat = _lost_beat()
    said = _at(2)
    assert computer.cookies_seen(beat, _look(5, "out"), said_on=said)["keep_cookies"] == "on"
    held = dict(_look(5, "in"), keep_cookies="on", signed_in_at=_at(5))
    assert computer.cookies_seen(held, _look(30, "in"), said_on=said)["keep_cookies"] == "on"
    # Lost again after their word: off, by its effect.
    assert computer.cookies_seen(held, _look(60, "out"), said_on=said)["keep_cookies"] == "off"
    # Never "unknown" for good: with nothing said and nothing lost, it stays as it was.
    assert computer.cookies_seen({}, _look(0, "out")) == {}


def test_the_computer_writes_what_it_knows_into_its_heartbeat(tmp_path, monkeypatch):
    import page_db
    db = {"chats": {computer.beat_id("Studio Laptop"): {"data": _look(-120, "out"),
                                                       "version": 2}}, "work": {}}
    batches = computer.beat(db, "Studio Laptop", T, str(tmp_path / "b"), since_in=_at(-60),
                            browser="shown", linkedin="out", version="9.9.9", task=False)
    with open(batches[0], encoding="utf-8") as fh:
        entry = json.load(fh)[0]
    fields = entry.get("data")
    if fields is None:
        with open(entry["file_path"], encoding="utf-8") as fh:
            fields = json.load(fh)
    assert fields["keep_cookies"] == "off" and fields["signin_lost"]["in_at"] == _at(-60)
    assert page_db  # the batch is the page's own kind


# ------------------------------------------------------------------ the page (bug 4)


def test_the_page_asks_once_to_keep_the_sign_in_before_asking_to_sign_in_again():
    db = {"chats": {computer.beat_id("Studio Laptop"): {"data": _lost_beat(), "version": 3}},
          "work": {WID: {"data": _asked(), "version": 5}}}
    st = computer.state(db, T, envs=BRIDGE)
    assert st["state"] == "signed_out" and st["say"] == "keep_signin"
    # At once, beside a read that waits on its own sign-in card, never ten minutes on.
    assert st["card"]
    card = computer.card(st)
    want = [ln for ln in claude_surfaces.steps("browser-pane-keep-cookies", page=True)
            if ln[:1].isdigit()]
    assert card["steps"] == want and any("Keep cookies" in s for s in card["steps"])
    assert not any("Sign in to LinkedIn" in s for s in card["steps"])     # that comes after
    assert card["about"]["say"] == "keep_signin" and "browser" not in card
    assert [o["label"] for o in card["options"]] == ["Done"]
    assert card["body"].startswith("“Reading 3 profiles” waits because LinkedIn signed out")
    # Said once: from then on, the sign-in alone, as before.
    after = computer.state(db, T, envs=BRIDGE, keep_said=_at(2))
    assert after["say"] == "signed_out_lost" and not after["card"]
    # Known to be kept: never asked.
    on = dict(db, chats={computer.beat_id("Studio Laptop"): {
        "data": dict(_lost_beat(), keep_cookies="on"), "version": 3}})
    assert computer.state(on, T, envs=BRIDGE)["say"] != "keep_signin"


def test_done_on_that_card_keeps_their_word(tmp_path):
    s = Search(str(tmp_path))
    item = _asked()
    beat = _lost_beat()
    db = {"chats": {computer.beat_id("Studio Laptop"): {"data": beat, "version": 3}},
          "work": {WID: {"data": item, "version": 5}}}
    rev = computer.card(computer.state(db, T))["rev"]
    s.put("work", WID, item, version=5)
    s.put("chats", computer.beat_id("Studio Laptop"), beat, version=3)
    aid = s.act("setup.done", "q-setup-computer", rev=rev)
    s.apply()
    got = s.receipt(aid)
    assert got["result"] == "ok", got
    assert "sign in to LinkedIn once more" in got["note"]
    with open(os.path.join(s.profile, "said_once.json"), encoding="utf-8") as fh:
        assert fh.read().count(computer.KEEP_SAID) == 1


# ------------------------------------------------------------------ reading (J3, review 5)


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    import pace
    import reading
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    keep = (dt.date.today() - dt.date(2026, 10, 1)).days + pace.KEEP_DAYS
    monkeypatch.setattr(pace, "KEEP_DAYS", max(pace.KEEP_DAYS, keep))
    return reading


MORNING = dt.datetime(2026, 10, 20, 8, 40)


def test_a_sign_in_page_minutes_after_they_signed_in_is_lost_never_a_stop(ledger):
    reading = ledger
    import pace
    pace.add_load("profile", (MORNING - dt.timedelta(hours=10)).isoformat(timespec="seconds"),
                  90.0, False, "ana_rook")
    # One sign-out (the day's first), the person signs in, and the sign-in page again twenty
    # minutes later, before anything was read.
    assert reading.signout(MORNING)["kind"] == "expired"
    reading.mark_signed_in(MORNING + dt.timedelta(minutes=2), person_=True)
    got = reading.signout(MORNING + dt.timedelta(minutes=22))
    assert got["kind"] == "lost", got
    assert not reading.stopped(MORNING.date())
    assert [x["kind"] for x in pace.friction()] == []
    assert reading.gate_state(MORNING + dt.timedelta(minutes=23))["kind"] != "tomorrow"
    # Read something after signing in, then signed out within the hour: friction, as before.
    reading.mark_signed_in(MORNING + dt.timedelta(minutes=25), person_=True)
    pace.add_load("profile", (MORNING + dt.timedelta(minutes=30)).isoformat(timespec="seconds"),
                  90.0, False, "ben_ash")
    assert reading.signout(MORNING + dt.timedelta(minutes=35))["kind"] == "friction"


def test_the_first_sign_out_on_the_job_path_is_kept(ledger, monkeypatch, capsys):
    reading = ledger
    import io
    monkeypatch.setattr(reading, "app_job_here", lambda: WID)
    page = "Sign in\nEmail or phone\nPassword\nForgot password?\nSign in\nNew to LinkedIn? Join now\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(page))
    assert reading.main(["signin", "--page", "-"]) == reading.EXIT["signin"]
    out = capsys.readouterr().out
    assert "--signin linkedin" in out
    assert len(reading.signouts()) == 1


def test_their_sign_in_on_the_page_lifts_todays_sign_out_stop(ledger):
    reading = ledger
    now = dt.datetime.now()
    reading.stop("LinkedIn signed out: the sign-in page after a page load")
    item = {"args": {"answers": {"answer": "Signed in to LinkedIn"}},
            "answered_at": app_model.stamp((now + dt.timedelta(seconds=5)).astimezone())}
    assert reading.stopped(now.date())
    assert reading.resume_from_page(item, now + dt.timedelta(seconds=10)) == ""
    assert not reading.stopped(now.date())
    # A check is never lifted by it.
    reading.stop("LinkedIn showed a check: Let's do a quick security check")
    assert "check" in reading.resume_from_page(item, now + dt.timedelta(seconds=20))
    assert reading.stopped(now.date())
    # An answer from before the stop is no word on it.
    old = dict(item, answered_at=app_model.stamp((now - dt.timedelta(hours=1)).astimezone()))
    reading.stop("LinkedIn signed out: the sign-in page after a page load")
    assert reading.resume_from_page(old, now + dt.timedelta(seconds=30)) == ""
    assert reading.stopped(now.date())


def test_a_stop_is_said_as_what_linkedin_did_never_a_cause_nobody_measured():
    for said in (computer.SAY["paused"], computer.SAY["forgets"], computer.WAITING_SAY["forgets"]):
        assert "slow down" not in said and "quits" not in said, said


# ------------------------------------------------------------------ the page draws it


TODO = r"""(() => {
  const keep = document.querySelector('[data-item="q-setup-computer"]');
  return {keep: keep ? keep.textContent.replace(/\s+/g, ' ') : null,
          signin: [...document.querySelectorAll('[data-signin="linkedin"]')].filter((e) => e.closest('#main')).length};
})()"""


@pytest.fixture(scope="module")
def run():
    import test_the_page_journeys as journeys
    yield from journeys.browser()


def test_the_sign_in_waits_behind_the_card_that_keeps_it(run, tmp_path, monkeypatch):
    import app_page
    import person
    import test_the_page_journeys as journeys
    s = Search(str(tmp_path / "copy"))
    monkeypatch.setenv(person.ENV, s.profile)
    monkeypatch.setenv(person.STATE_ENV, s.state)
    person._modules.clear()
    person._data.clear()
    db = {"chats": {computer.beat_id("Studio Laptop"): {"data": _lost_beat(), "version": 3}},
          "work": {WID: {"data": _asked(), "version": 5}}}
    st = computer.state(db, T, envs=BRIDGE)
    built, _ = app_model.build(T.date(), T, only=("needs_you", "where"), computer=st)
    person._modules.clear()
    person._data.clear()
    m = journeys._sample()
    m["where"] = dict(m["where"], computer=built["where"]["computer"])
    m["needs_you"] = [c for c in built["needs_you"] if c["id"] == "q-setup-computer"] + \
        list(m.get("needs_you") or [])
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(m)))
    seed = {f"work/{WID}": dict(_asked(), _v=5, needs=dict(_asked()["needs"], work=WID,
                                                             answer={"key": "answer",
                                                                     "kind": "text"}))}
    got = run("engine", html=path, viewport=journeys.WIDE, steps=[{"hash": "todo", "eval": TODO}],
              seed=seed, fake={"canSend": "available"}, clock=NOW)
    assert not got["errors"], got["errors"]
    seen = got["after"][0]["eval"]
    assert seen["keep"] and "Keep cookies" in seen["keep"], seen
    assert seen["signin"] == 0, seen
