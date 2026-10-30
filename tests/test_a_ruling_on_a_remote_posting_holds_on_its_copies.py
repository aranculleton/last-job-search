"""A ruling on a remote posting holds for the same role on every board, with or without a place.

`throttle.city("Remote (Canada)")` was "": the brackets and the word "remote" were cut and
nothing was left. A ruling on that posting was kept under the empty city, which only a posting
with no location, or a plain "Remote", ever had. So the same role on another board, posted as
"Canada" or "Toronto, ON, Canada", was kept by `ruled_pair` while the prefilter, which asks
without the location, dropped it: the two answered differently for one posting. A remote
posting names no place to be, so its ruling is kept under ANYWHERE and covers the role
wherever it is posted, and a posting read without its place never meets a ruling that a
posting read with it would not.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import exclude  # noqa: E402
import prefilter  # noqa: E402
import throttle  # noqa: E402

WELSH = 'Welsh stated as a requirement: "fluent Welsh is essential"'
TITLE, EMPLOYER = "Senior Data Scientist", "Ellerwick Trust"
LOCATIONS = ["Remote (Canada)", "Remote", "Canada", "Toronto, ON, Canada", "Calgary, AB, Canada",
             "Toronto (Hybrid/Remote)", "Manchester, England, United Kingdom", "Hybrid", "", None]


@pytest.fixture(autouse=True)
def _no_rescreen(monkeypatch):
    monkeypatch.setenv("LJS_RESCREEN", "off")


def _job(location, company=EMPLOYER, n=2):
    job = {"url": f"https://boards.example.com/{company.split()[0].lower()}/{n}",
           "title": TITLE, "company": company}
    if location is not None:
        job["location"] = location
    return job


def _seen(tmp_path, location, company=EMPLOYER):
    path = str(tmp_path / "seen_jobs.json")
    exclude.add_many([{"url": "https://careers.example.com/ellerwick/1", "title": TITLE,
                       "company": company, "location": location, "reason": WELSH}],
                     today="2026-10-22", path=path)
    return path


def _pairs(path):
    return throttle.ruled_out(throttle.load_seen(path)["seen"], "2026-10-25")[1]


@pytest.mark.parametrize("location", ["Remote (Canada)", "Remote", "Remote - Canada",
                                      "Canada (Remote)", "Fully remote (UK)", "Work from home",
                                      "Remote, US"])
def test_a_remote_location_names_no_city(location):
    assert throttle.city(location) == throttle.ANYWHERE


@pytest.mark.parametrize("location,city", [("Toronto, ON, Canada", "toronto"),
                                           ("Toronto (Hybrid/Remote)", "toronto"),
                                           ("Hybrid", ""), ("", ""), (None, "")])
def test_a_place_that_is_named_is_still_the_city(location, city):
    assert throttle.city(location) == city


def test_a_ruling_on_a_remote_posting_is_kept_under_anywhere(tmp_path):
    pairs = _pairs(_seen(tmp_path, "Remote (Canada)"))
    assert list(pairs) == [(throttle.title_key(TITLE), throttle.key(EMPLOYER), throttle.ANYWHERE)]


@pytest.mark.parametrize("location", LOCATIONS)
def test_the_role_on_another_board_is_ruled_out_wherever_it_says_it_is(tmp_path, location):
    pairs = _pairs(_seen(tmp_path, "Remote (Canada)"))
    assert throttle.ruled_pair(pairs, _job(location)).startswith("excluded in seen_jobs.json")


def test_another_employers_role_is_not_covered(tmp_path):
    pairs = _pairs(_seen(tmp_path, "Remote (Canada)"))
    assert throttle.ruled_pair(pairs, _job("Canada", company="Fernhill Freight")) == ""


@pytest.mark.parametrize("ruled_at", ["Remote (Canada)", "Remote", "Toronto, ON, Canada",
                                      "Hybrid", None])
def test_the_prefilter_and_the_throttle_agree_with_the_place_or_without_it(tmp_path, ruled_at):
    path = _seen(tmp_path, ruled_at)
    check = prefilter.already_ruled_out(path, today=dt.date(2026, 10, 25))
    pairs = _pairs(path)
    for location in LOCATIONS:
        job = _job(location)
        without = {k: v for k, v in job.items() if k != "location"}
        # What the prefilter drops, it drops with the place too, as the throttle reads it.
        assert bool(check(job)) == bool(throttle.ruled_pair(pairs, job)), (ruled_at, location)
        if check(without):
            assert throttle.ruled_pair(pairs, job), (ruled_at, location)
            assert check(job), (ruled_at, location)


def test_a_ruling_in_one_city_is_not_read_into_a_posting_with_no_place(tmp_path):
    path = _seen(tmp_path, "Toronto, ON, Canada")
    check = prefilter.already_ruled_out(path, today=dt.date(2026, 10, 25))
    assert check(_job("Toronto, ON, Canada"))
    assert check(_job(None)) == ""
    assert check(_job("Calgary, AB, Canada")) == ""


def test_the_round_drops_the_copy_the_prefilter_drops(tmp_path):
    path = _seen(tmp_path, "Remote (Canada)")
    urls, pairs = throttle.ruled_out(throttle.load_seen(path)["seen"], "2026-10-25")
    copy = {**_job("Canada"), "priority": 70, "fit": 80}
    kept, skipped = throttle.throttle([copy], {}, urls, pairs, "2026-10-25")
    assert skipped and not kept
    assert skipped[0]["skip_reason"].startswith("already ruled out")


def test_a_ruling_on_where_a_remote_posting_is_holds_only_there(tmp_path, monkeypatch):
    # "Remote - US" ruled out for someone in Canada was kept under ANYWHERE, so the same role
    # posted as "Toronto, ON, Canada" or "Remote - Canada" was dropped with the US reason (the
    # release review, 2026-10-30). A ruling on the place stays with the place as written.
    monkeypatch.setattr(throttle, "_place_still_fails", lambda e: "us" in str((e or {}).get("location", "")).lower())
    path = str(tmp_path / "seen_jobs.json")
    exclude.add_many([{"url": "https://careers.example.com/ellerwick/1", "title": TITLE, "company": EMPLOYER,
                       "location": "Remote - US", "reason": "Location: based in the US only"}],
                     today="2026-10-22", path=path)
    pairs = _pairs(path)
    assert throttle.ruled_pair(pairs, _job("Remote - US")), "the same place on another board is still ruled out"
    for location in ["Toronto, ON, Canada", "Remote - Canada", "Remote", "Canada", "", None]:
        assert throttle.ruled_pair(pairs, _job(location)) == "", location
