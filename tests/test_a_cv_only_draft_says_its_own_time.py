"""Drafting the CV alone says its own time, never the CV and letter's.

The screen review of 2026-11-11 (row 31): under a job's More, "Draft the CV only" said "9 min
of Claude", the same as "Draft this" beside it (the CV and the letter), so the cheaper choice
read as no cheaper. Its time is this copy's own, from its finished CV-only drafts, which their
work records tell apart (`args.resume_only`), and counted apart from the full drafts, so
neither's minutes are the other's. With none finished yet, it is the draft's own stages without
the one the drafting workflow never runs for the CV alone: the employer research, which is only
for the letter (.claude/workflows/draft-applications.js, NO_RESEARCH). Every person and
employer is the sample's, invented.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_page  # noqa: E402
import page_db  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go, _sample  # noqa: E402

NOW = dt.datetime(2026, 10, 25, 9, 0, tzinfo=dt.timezone.utc)
T = "2026-10-25T09:00:00Z"


def _done(i, took, alone):
    end = NOW - dt.timedelta(days=1, hours=i)
    return {"data": {"kind": "draft", "status": "done", "args": {"resume_only": True} if alone else {"job": "r%d" % i},
                     "claimed_at": (end - dt.timedelta(seconds=took)).isoformat(), "finished_at": end.isoformat()}}


def test_this_copys_own_cv_only_drafts_are_timed_apart_from_the_full_ones():
    work = {"a%d" % i: _done(i, 300 + i, True) for i in range(3)}
    work.update({"b%d" % i: _done(10 + i, 600 + i, False) for i in range(3)})
    got = page_db.work_times({"work": work}, NOW)
    assert got.get(page_db.RESUME_ONLY_KIND) == 301 and got.get("draft") == 601, got


def test_with_none_finished_it_is_the_drafts_own_stages_without_the_research():
    draft, alone = app_page.tables()["stages"]["draft"], app_page.tables()["estimates"][page_db.RESUME_ONLY_KIND]
    research = [name for key, name, _s in page_db.STAGES["draft"] if key == "research"]
    assert research and research[0] not in [n for n, _s in alone], alone
    assert [x for x in draft if x[0] != research[0]] == alone, (draft, alone)
    assert sum(s for _n, s in alone) < sum(s for _n, s in draft)
    # As much of Claude as a full draft, by the gauge's bars: only the minutes differ.
    assert app_page.tables()["work_cost"][page_db.RESUME_ONLY_KIND] == app_page.tables()["work_cost"]["draft"]


def test_a_cv_only_draft_is_queued_with_its_own_stages_and_pinned_by_their_names():
    alone = page_db.progress(page_db.RESUME_ONLY_KIND)["stages"]
    # A chat pins a draft's stages by the draft's keys; the CV alone has no research stage,
    # so "write" is its second, by its name.
    assert page_db.stage_index("draft", "write", alone) == [s["name"] for s in alone].index("Writing")
    assert page_db.stage_index("draft", "write", page_db.progress("draft")["stages"]) == 2


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


LOOK = ("(() => { const t = (k) => { const b = document.querySelector('[data-k=\"' + k + '\"]'); const c = b && b.nextElementSibling;"
        " return c && c.classList.contains('cost') ? c.textContent : ''; };"
        " return {full: t('draft:r12-1'), alone: t('draftalone:r12-1')}; })()")


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_the_more_panel_says_less_time_for_the_cv_alone(run, tmp_path, vp):
    got = _go(run, tmp_path, [{"hash": "jobs", "moreText": "Pricing Analyst", "eval": LOOK}], vp, clock=T)
    seen = got["after"][0]["eval"]
    full = int(re.search(r"(\d+) min", seen["full"]).group(1))
    alone = int(re.search(r"(\d+) min", seen["alone"]).group(1))
    assert alone < full, seen
    secs = sum(s for _n, s in app_page.tables()["estimates"][page_db.RESUME_ONLY_KIND])
    assert alone == round(secs / 60), seen
    # This copy's own times, once it has them, for each.
    m = _sample()
    m["work_time"] = {"draft": 720, page_db.RESUME_ONLY_KIND: 300}
    got = _go(run, tmp_path, [{"hash": "jobs", "moreText": "Pricing Analyst", "eval": LOOK}], vp, model=m, clock=T)
    seen = got["after"][0]["eval"]
    assert seen["full"].startswith("12 min") and seen["alone"].startswith("5 min"), seen


def test_the_toast_says_the_cv_alones_time(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "jobs", "moreText": "Pricing Analyst", "open": "draftalone:r12-1", "wait": 300,
                               "eval": "[...document.querySelectorAll('.toast')].map((t) => t.textContent).join(' ')"}], WIDE, clock=T)
    said = got["after"][0]["eval"]
    secs = sum(s for _n, s in app_page.tables()["estimates"][page_db.RESUME_ONLY_KIND])
    assert "in about %d minutes" % round(secs / 60) in said, said
