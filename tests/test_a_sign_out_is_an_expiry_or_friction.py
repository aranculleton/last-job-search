"""A sign-in page is an expired session or friction, by when it came, and a stop has a way back.

From a real run (2026-10-20): profiles read late one evening, and about nine hours later the
first page of the morning showed LinkedIn's sign-in page. The app called it "signed out
mid-run", stopped the whole day and logged it as friction. The person signed back in with no
check at all, `signin --url` said signed-in, and the gate still said tomorrow; the only way
on was editing the ledger by hand. Invented people only.
"""
from __future__ import annotations

import datetime
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "network"))
import pace  # noqa: E402
import reading  # noqa: E402

LOGIN = """Sign in
Stay updated on your professional world
Email or phone
Password
Forgot password?
Sign in
New to LinkedIn? Join now
"""
MORNING = datetime.datetime(2026, 10, 20, 8, 40)


@pytest.fixture(autouse=True)
def _ledger_keeps_these_dates(monkeypatch):
    # The pace ledger drops what is older than KEEP_DAYS by the calendar, and the loads here
    # are dated in October 2026: kept from then, so these tests pass whatever today is.
    keep = (datetime.date.today() - datetime.date(2026, 10, 1)).days + pace.KEEP_DAYS
    monkeypatch.setattr(pace, "KEEP_DAYS", max(pace.KEEP_DAYS, keep))


def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")


def _loaded(at: datetime.datetime):
    pace.add_load("profile", at.isoformat(timespec="seconds"), 90.0, False, "ana_rook")


def test_a_sign_in_page_hours_after_the_last_load_is_an_expiry_not_a_stop(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    reading.mark_signed_in(MORNING - datetime.timedelta(hours=11))
    _loaded(MORNING - datetime.timedelta(hours=9, minutes=10))         # late last night
    got = reading.signout(MORNING)
    assert got["kind"] == "expired" and "first page of the day" in got["why"]
    assert "9.2 hours after the last page load" in got["why"]
    assert not reading.stopped(MORNING.date())
    assert [x["kind"] for x in pace.friction()] == []                  # not a signal
    reading.mark_signed_in(MORNING + datetime.timedelta(minutes=2))    # signin --url
    g = reading.gate_state(MORNING + datetime.timedelta(minutes=3), sends_left=5)
    assert g["kind"] != "tomorrow", g


def test_the_same_day_counts_too_once_enough_hours_have_passed(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    _loaded(MORNING)
    got = reading.signout(MORNING + datetime.timedelta(hours=5))
    assert got["kind"] == "expired" and "5.0 hours after the last page load" in got["why"]


def test_a_sign_in_page_minutes_after_a_load_is_friction_and_says_what_was_seen(tmp_path,
                                                                                 monkeypatch):
    _state(tmp_path, monkeypatch)
    reading.mark_signed_in(MORNING)
    _loaded(MORNING + datetime.timedelta(minutes=20))
    now = MORNING + datetime.timedelta(minutes=27)
    got = reading.signout(now)
    assert got["kind"] == "friction"
    assert "7 min after the last page load (2026-10-20 09:00)" in got["why"]
    assert "mid-run" not in reading.stopped(now.date())
    assert [x["kind"] for x in pace.friction()] == ["signed_out"]
    g = reading.gate_state(now, sends_left=5)
    assert g["kind"] == "tomorrow" and "reading.py resume --reason" in g["why"]


def test_resume_needs_a_clean_sign_in_and_keeps_an_honest_log(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    _loaded(MORNING)
    now = MORNING + datetime.timedelta(minutes=5)
    reading.signout(now)
    try:
        reading.resume("I signed out on my phone", now)
        raise AssertionError("resumed before signing in")
    except SystemExit as e:
        assert "sign in first" in str(e)
    reading.mark_signed_in(now + datetime.timedelta(minutes=1))
    rec = reading.resume("I signed out on my phone", now + datetime.timedelta(minutes=2))
    assert rec["lifted_because"] == "I signed out on my phone"
    assert not reading.stopped(now.date())
    log = pace.friction()
    assert log[-1]["kind"] == "signed_out" and log[-1]["benign"].startswith(
        "person confirmed benign: I signed out on my phone")
    # The page that comes next is read at once: nothing of the app's own holds it back.
    assert reading.browser_gate(now + datetime.timedelta(seconds=1)) == ""


def test_a_second_sign_out_after_a_resume_stops_the_day_with_no_way_back(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    _loaded(MORNING)
    now = MORNING + datetime.timedelta(minutes=5)
    reading.signout(now)
    reading.mark_signed_in(now + datetime.timedelta(minutes=1))
    reading.resume("ordinary sign-out", now + datetime.timedelta(minutes=2))
    _loaded(now + datetime.timedelta(minutes=10))
    later = now + datetime.timedelta(minutes=14)
    got = reading.signout(later)
    assert got["kind"] == "friction" and "the second sign-out today" in got["why"]
    assert reading.stopped(later.date())
    reading.mark_signed_in(later + datetime.timedelta(minutes=1))
    assert "spent" in reading.resumable(later + datetime.timedelta(minutes=2))
    assert "resume" not in reading.gate_state(later, sends_left=5)["why"]


def test_an_expiry_then_another_sign_out_the_same_day_is_friction(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    _loaded(MORNING - datetime.timedelta(hours=10))
    assert reading.signout(MORNING)["kind"] == "expired"
    reading.mark_signed_in(MORNING + datetime.timedelta(minutes=1))
    _loaded(MORNING + datetime.timedelta(minutes=5))
    got = reading.signout(MORNING + datetime.timedelta(minutes=9))
    assert got["kind"] == "friction" and "second sign-out" in got["why"]
    assert "two sign-outs" in reading.resumable(MORNING + datetime.timedelta(minutes=9))


def test_the_same_sign_in_page_seen_again_while_waiting_is_one_sign_out(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    _loaded(MORNING - datetime.timedelta(hours=10))
    reading.signout(MORNING)
    again = reading.signout(MORNING + datetime.timedelta(minutes=1))
    assert again["again"] and again["kind"] == "expired"
    assert len(reading.signouts(MORNING.date())) == 1


def test_a_check_is_never_lifted_by_hand(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    reading.stop("LinkedIn showed a check: Let's do a quick security check")   # today's
    reading.mark_signed_in(datetime.datetime.now() + datetime.timedelta(seconds=2))
    assert "never lifted by hand" in reading.resumable()
    assert "resume" not in reading.gate_state(sends_left=5)["why"]


def test_a_read_and_the_signin_command_classify_it_and_never_suggest_a_stop(tmp_path, monkeypatch,
                                                                         capsys):
    _state(tmp_path, monkeypatch)
    _loaded(datetime.datetime.now() - datetime.timedelta(hours=9))
    monkeypatch.setattr(sys, "stdin", io.StringIO(LOGIN))
    code = reading.main(["read", "ana_rook", "-", "--source", "browser", "--name", "Ana Rook",
                         "--company", "Kestrel Mutual"])
    out = capsys.readouterr().out
    assert code == reading.EXIT["signin"] and "the session expired" in out and "Not a stop" in out
    reading.mark_signed_in()
    assert reading.main(["signin"]) in (reading.EXIT["ok"], reading.EXIT["signin"],
                                        reading.EXIT["check"])
    assert "mid-run" not in capsys.readouterr().out


def test_resume_is_a_command_and_the_stop_says_so(tmp_path, monkeypatch, capsys):
    _state(tmp_path, monkeypatch)
    now = datetime.datetime.now()                       # a load minutes ago, and today's
    _loaded(max(now - datetime.timedelta(minutes=3), datetime.datetime.combine(now.date(),
                                                                                datetime.time())))
    reading.signout()
    assert reading.main(["gate"]) == reading.EXIT["tomorrow"]
    assert "reading.py resume --reason" in capsys.readouterr().out
    reading.mark_signed_in(datetime.datetime.now() + datetime.timedelta(seconds=2))
    assert reading.main(["resume", "--reason", "my own sign-out"]) == reading.EXIT["ok"]
    assert "lifted on the person's word" in capsys.readouterr().out
    assert not reading.stopped()


def test_the_expiry_window_is_four_hours_and_the_persons_to_set():
    assert pace.EXPIRY_HOURS == 4 == reading.EXPIRY_HOURS
    assert pace._setting(6, 4) == 6 and pace._setting("x", 4) == 4 and pace._setting(0, 4) == 4
