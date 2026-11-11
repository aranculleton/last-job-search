"""A run told its day (LJS_TODAY, the app's one fixed clock) counts every decision on that day.

GitHub's run of 2026-11-10 crossed midnight UTC: the surfacing check (tools/network/surface.py)
counted on the computer's new day while the reads it checked against counted on the day the run
was told, so a note sent "today" read as six days old and three tests failed. person.today()
now honours LJS_TODAY as app_model.clock already did. Invented people only."""
from __future__ import annotations

import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import person  # noqa: E402


def test_the_persons_day_is_the_day_the_run_was_told(monkeypatch):
    told = dt.date.today() - dt.timedelta(days=1)
    monkeypatch.setenv("LJS_TODAY", told.isoformat())
    assert person.today() == told
    monkeypatch.setenv("LJS_TODAY", told.isoformat() + "T23:30:00Z")
    assert person.today() == told


def test_a_given_moment_still_wins_and_no_fixed_clock_reads_the_real_one(monkeypatch):
    monkeypatch.setenv("LJS_TODAY", "2026-01-02")
    now = dt.datetime(2026, 3, 4, 12, tzinfo=dt.timezone.utc)
    assert person.today(now).isoformat() >= "2026-03-03"          # their zone, from that moment
    monkeypatch.delenv("LJS_TODAY")
    real = person.today()
    assert abs((real - dt.date.today()).days) <= 1
    monkeypatch.setenv("LJS_TODAY", "not a date")
    assert person.today() == real


def test_the_surfacing_check_counts_on_that_day(monkeypatch):
    import surface
    told = dt.date.today() - dt.timedelta(days=1)
    monkeypatch.setenv("LJS_TODAY", told.isoformat())
    got = surface.context(contacts=[], threads=[], connections=[])
    assert got["today"] == told, got.get("today")
