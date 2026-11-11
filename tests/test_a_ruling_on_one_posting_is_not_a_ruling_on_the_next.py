"""A ruling on one posting does not rule out a new opening months later, and a score never blocks.

`throttle.ruled_out` keeps a ruling by the posting's address and by its title, employer
and city, so a posting relisted under a new address stays out. The second key had no
time limit: a new requisition for the same title, opened many months later under its own
address, was dropped at the prefilter on its predecessor's ruling, before anything read
its own body, while the relist rule beside it (RELIST_WINDOW) said that far out the same
title is more likely a new opening. And a "skipped" entry whose reason was a score
blocked for good, though the same reason as an exclusion is released.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import exclude  # noqa: E402
import prefilter  # noqa: E402
import throttle  # noqa: E402

MCR = "Manchester, England, United Kingdom"


@pytest.fixture(autouse=True)
def _no_rescreen(monkeypatch):
    monkeypatch.setenv("LJS_RESCREEN", "off")


def _job(n, day):
    return {"url": f"https://jobs.example.com/quillfield/{n}", "title": "Data Analyst",
            "company": "Quillfield Foods", "location": MCR, "date": day}


@pytest.fixture
def seen(tmp_path):
    path = str(tmp_path / "seen_jobs.json")
    exclude.add_many([{"url": _job(1, "")["url"], "title": "Data Analyst",
                       "company": "Quillfield Foods", "location": MCR,
                       "reason": 'Welsh stated as a requirement: "Fluency in Welsh is essential."'}],
                     today="2026-10-22", path=path)
    return path


def test_a_new_requisition_months_later_is_judged_on_its_own(seen):
    check = prefilter.already_ruled_out(seen, today=dt.date(2027, 6, 1))
    assert check(_job(977, "2027-05-30")) == ""


def test_a_relist_within_the_window_is_still_that_posting(seen):
    check = prefilter.already_ruled_out(seen, today=dt.date(2026, 11, 10))
    assert check(_job(978, "2026-11-09")).startswith("excluded in seen_jobs.json")


def test_the_ruled_address_itself_stays_out_for_good(seen):
    check = prefilter.already_ruled_out(seen, today=dt.date(2027, 6, 1))
    assert check(_job(1, "2027-05-30")).startswith("excluded in seen_jobs.json")


def test_a_role_the_person_set_aside_holds_for_good_only_where_their_words_say_so(tmp_path):
    """Moved with the rule (the rules review, 2026-11-11). It held a ruling in the person's own
    words for the title at that employer for ever, so one "not for me" left out every later
    opening of it, wherever posted, with nothing saying so. Now a role set aside holds for
    exclude.set_aside_days() (about six months) and then is shown once more; it holds for good
    only where their own words say so ("never", "at all", "no more ... ever")."""
    plain = str(tmp_path / "plain.json")
    exclude.add(_job(1, "")["url"], "not a team I want to join", "Data Analyst",
                "Quillfield Foods", basis="person", today="2026-10-22", path=plain,
                location=MCR)
    # Within its six months it holds every copy, as before.
    check = prefilter.already_ruled_out(plain, today=dt.date(2027, 1, 10))
    assert check(_job(977, "2027-01-08")).startswith("excluded in seen_jobs.json")
    # A year on, a new opening is judged on its own.
    check = prefilter.already_ruled_out(plain, today=dt.date(2027, 6, 1))
    assert check(_job(977, "2027-05-30")) == ""
    assert check(_job(1, "2027-05-30")) == ""
    for words in ("never this team", "not interested at all", "no more of these ever"):
        forever = str(tmp_path / f"{len(words)}.json")
        exclude.add(_job(1, "")["url"], words, "Data Analyst", "Quillfield Foods",
                    basis="person", today="2026-10-22", path=forever, location=MCR)
        check = prefilter.already_ruled_out(forever, today=dt.date(2027, 6, 1))
        assert check(_job(977, "2027-05-30")).startswith("excluded in seen_jobs.json"), words
    # Words that only describe the role or what happened hold for six months, never for good:
    # "never" and "at all" anywhere held these for ever (the rules review, 2026-11-11).
    for words in ("they never replied to my last application", "does not use Python at all",
                  "never heard back from them, not now"):
        described = str(tmp_path / f"d{len(words)}.json")
        exclude.add(_job(1, "")["url"], words, "Data Analyst", "Quillfield Foods",
                    basis="person", today="2026-10-22", path=described, location=MCR)
        check = prefilter.already_ruled_out(described, today=dt.date(2027, 6, 1))
        assert check(_job(977, "2027-05-30")) == "", words
    for words in ("never", "not for me, never", "never show me this again", "for good"):
        assert exclude.for_good(words), words


def test_a_role_set_aside_comes_back_once_marked_with_the_day_and_their_words(tmp_path):
    path = str(tmp_path / "seen_jobs.json")
    exclude.add(_job(1, "")["url"], "the pay (said on the page)", "Data Analyst",
                "Quillfield Foods", basis="person", today="2026-10-22", path=path,
                location=MCR)
    entries = json.load(open(path, encoding="utf-8"))["seen"]
    job = _job(977, "2027-05-30")
    assert throttle.set_aside_returns([job], entries, "2027-01-10") == []    # still held
    assert "set_aside_note" not in job
    lifted = throttle.set_aside_returns([job], entries, "2027-06-01")
    assert job["set_aside_note"] == ("You set a role like this aside on 22 October 2026 (the "
                                     "pay): showing it again in case things changed")
    assert [entries[k]["status"] for k in lifted] == ["lifted"]
    again = _job(978, "2027-06-02")
    assert throttle.set_aside_returns([again], entries, "2027-06-03") == []  # once only
    assert "set_aside_note" not in again


def test_a_skip_whose_reason_is_a_score_does_not_block():
    reason = "scored 58 (moderate fit), below the 60 pass bar"
    for status in ("skipped", "excluded"):
        e = {"url": "https://jobs.example.com/9", "status": status, "skip_reason": reason,
             "exclusion_reason": reason, "title": "Demand Planning Analyst",
             "company": "Quillfield Foods", "location": "Salford, England, United Kingdom",
             "skipped_date": "2026-10-22", "excluded_date": "2026-10-22"}
        urls, pairs = throttle.ruled_out({e["url"]: e}, "2026-10-23")
        assert urls == {} and pairs == {}, status


def test_a_skip_for_a_fact_still_blocks():
    e = {"url": "https://jobs.example.com/10", "status": "skipped",
         "skip_reason": "a duplicate of a posting already on the shortlist",
         "title": "Demand Planning Analyst", "company": "Quillfield Foods",
         "skipped_date": "2026-10-22"}
    urls, _ = throttle.ruled_out({e["url"]: e}, "2026-10-23")
    assert urls


def test_the_throttle_reads_the_window_on_its_own_day(seen, tmp_path):
    with open(seen, encoding="utf-8") as fh:
        entries = json.load(fh)["seen"]
    _, pairs = throttle.ruled_out(entries, "2027-06-01")
    assert throttle.ruled_pair(pairs, _job(977, "2027-05-30")) == ""
    _, pairs = throttle.ruled_out(entries, "2026-11-10")
    assert throttle.ruled_pair(pairs, _job(978, "2026-11-09"))


def test_how_long_a_set_aside_holds_is_read_when_asked_and_needs_no_search_file(tmp_path,
                                                                                 monkeypatch):
    """exclude.py read the person's SET_ASIDE_DAYS when it was imported: with no search.py in
    the profile (only person.json, as a new person starts) it could not be imported at all,
    and a process kept the old end after the person changed their number."""
    import subprocess
    prof = tmp_path / "profile"
    prof.mkdir()
    (prof / "person.json").write_text(json.dumps({"identity": {"name": "Wren Halloway"}}),
                                      encoding="utf-8")
    r = subprocess.run([sys.executable, "-c", "import exclude; print(exclude.set_aside_days())"],
                       cwd=os.path.join(ROOT, "tools"), capture_output=True, text=True,
                       encoding="utf-8", env=dict(os.environ, LJS_PROFILE=str(prof)))
    assert r.returncode == 0 and r.stdout.strip() == "182", r.stderr[-600:]
    import person
    monkeypatch.setenv("LJS_PROFILE", str(prof))
    person.reset()
    try:
        (prof / "search.py").write_text("SET_ASIDE_DAYS = 30\n", encoding="utf-8")
        assert exclude.set_aside_days() == 30
        (prof / "search.py").write_text("SET_ASIDE_DAYS = 60\n", encoding="utf-8")
        person.reset()                          # as profile_set does after it writes
        assert exclude.set_aside_days() == 60
        e = {"url": "https://jobs.example.com/x", "basis": "person", "status": "excluded",
             "exclusion_reason": "not for me", "excluded_date": "2026-01-01"}
        assert exclude.set_aside_until(e) == dt.date(2026, 3, 2)
    finally:
        monkeypatch.undo()
        person.reset()


def test_an_undated_set_aside_counts_from_the_first_day_its_posting_was_seen():
    """A ruling of the person's with no day of its own counted its six months from the latest
    day its posting was seen, and a search that saw it again (--keep-ruled-out) moved that day
    on, so the ruling restarted and never ended. It counts from the earliest day seen."""
    e = {"url": "https://jobs.example.com/quillfield/5", "basis": "person",
         "status": "excluded", "exclusion_reason": "not for me", "first_seen": "2026-01-05",
         "last_seen": "2026-11-01", "rank_date": "2026-01-06"}
    assert exclude.ruled_on(e) == dt.date(2026, 1, 5)
    assert exclude.set_aside_until(e) == dt.date(2026, 1, 5) + dt.timedelta(
        days=exclude.set_aside_days())
    assert not exclude.set_aside_holds(e, dt.date(2026, 11, 10))
