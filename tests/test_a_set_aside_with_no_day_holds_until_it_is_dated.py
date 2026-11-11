"""A role set aside with no day holds from the day it is read, and is dated at the next save.

4.15.0 gave every set-aside an end (about six months), and one written with no day at all held
nothing until something dated it. A person's own checks, and older tools, write set-asides that
way: on the maintainer's copy, four of his own checks failed on the update, each finding a role
it had just set aside not held (2026-11-11). Now one with no day holds as if set today, and the
next save of the file writes that day on it, so it ends like any other: nothing it set aside
stops holding, and nothing undated holds for ever. Invented employers and links only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import exclude  # noqa: E402
import person  # noqa: E402
import throttle  # noqa: E402

DAY = "2026-11-11"


def _undated(url="https://jobs.example.com/quillfield/7", **more):
    """A role set aside as a person's own check writes one: their reason, no day at all."""
    return dict({"url": url, "title": "Pricing Analyst", "company": "Quillfield Foods",
                 "basis": "person", "status": "excluded",
                 "exclusion_reason": "not the kind of team I want"}, **more)


def test_one_with_no_day_holds_as_if_set_today(monkeypatch):
    monkeypatch.setenv("LJS_TODAY", DAY)
    today = person.today()
    e = _undated()
    assert exclude.set_aside_until(e) == today + dt.timedelta(days=exclude.set_aside_days())
    assert exclude.set_aside_holds(e, today)
    # As a search reads it: the role is held, and so is the same title at the employer.
    urls, pairs = throttle.ruled_out({e["url"]: e}, DAY)
    assert any(e["url"].split("//")[1] in k for k in urls), urls
    assert pairs, "the same role at the same employer is held too"
    # Never said as the day they set it aside: nothing says that day.
    assert exclude.set_aside_on(e) is None
    # A chat's own stop with no day holds the same way, and still never for good.
    stop = _undated(by=exclude.CHAT, exclusion_reason="never one they can take")
    assert exclude.set_aside_until(stop) == exclude.set_aside_until(e)


def test_the_next_save_dates_it_so_it_never_holds_for_ever(tmp_path, monkeypatch):
    seen = str(tmp_path / "seen_jobs.json")
    words = _undated(url="https://jobs.example.com/quillfield/8",
                     exclusion_reason="not this team, never again")
    dated = _undated(url="https://jobs.example.com/quillfield/9", excluded_date="2026-10-01")
    seen_once = _undated(url="https://jobs.example.com/quillfield/10", first_seen="2026-09-01")
    with open(seen, "w", encoding="utf-8") as fh:
        json.dump({"seen": {"a": _undated(), "b": words, "c": dated, "d": seen_once}}, fh)
    monkeypatch.setenv("LJS_TODAY", DAY)
    # A save of anything else in the file (a role set aside on the page) dates it, today.
    exclude.add("https://jobs.example.com/fernway/1", "the pay", basis="person", path=seen)
    got = exclude.load_seen(seen)["seen"]
    assert got["a"]["held_from"] == DAY
    # Their words for good, a day of its own, a day its posting was seen: left as they were.
    for k in ("b", "c", "d"):
        assert "held_from" not in got[k], got[k]
    # Read on any later day it ends six months on from that save, not from that day.
    end = dt.date.fromisoformat(DAY) + dt.timedelta(days=exclude.set_aside_days())
    monkeypatch.setenv("LJS_TODAY", end.isoformat())
    assert exclude.set_aside_until(got["a"]) == end
    assert not exclude.set_aside_holds(got["a"], end)
    assert exclude.set_aside_on(got["a"]) is None       # never said as the day set aside


def test_a_search_round_that_writes_the_file_dates_it_too(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_TODAY", DAY)
    seen = str(tmp_path / "seen_jobs.json")
    data = {"seen": {"a": _undated()}}
    throttle.write_back(seen, data, [], DAY)
    with open(seen, encoding="utf-8") as fh:
        assert json.load(fh)["seen"]["a"]["held_from"] == DAY


def test_the_days_check_still_finds_any_left_with_no_day(tmp_path):
    """Between saves, the day's update check dates every one still undated (the instant
    improvement set-asides-dated, run on every sync): nothing waits for a save that never
    comes."""
    seen = str(tmp_path / "seen_jobs.json")
    with open(seen, "w", encoding="utf-8") as fh:
        json.dump({"seen": {"a": _undated()}}, fh)
    assert exclude.undated_set_asides(seen) == ["a"]
    assert exclude.date_set_asides(DAY, seen) == 1
    assert exclude.undated_set_asides(seen) == []
