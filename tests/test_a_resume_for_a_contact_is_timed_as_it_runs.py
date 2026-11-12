"""A resume made for a contact is timed as it really runs, and never sits at the end of its bar.

Issue #238: the work that makes a resume for one of the person's contacts was estimated at about
6.5 minutes (60 + 120 + 120 + 45 + 45 seconds); a real run took about 15, so its card sat at the
end of its bar, looking stuck, long before it finished. Its stages now add up to the measured
time, and once any job runs past its estimate its card shows how long it has run, with no bar.

Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_page  # noqa: E402
import page_db  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_claudes_work_says_stop_claude_and_an_answer_offers_its_next_step import LISTEN, _w  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
WID = "contact_resume~sam_example~r1"

CARD = ("(() => { const c = document.querySelector('[data-work=\"%s\"]'); if (!c) return null;"
        " return {bar: !!c.querySelector('[role=progressbar]'),"
        " time: (c.querySelector('[data-time]') || {}).textContent || '',"
        " text: c.textContent.replace(/\\s+/g, ' ').trim()}; })()" % WID)


def test_its_estimate_is_the_measured_fifteen_minutes_on_the_engine_and_the_page():
    total = page_db.progress("resume_for_contact")["total_s"]
    # A real run took about 15 minutes (issue #238); 6.5 was the old estimate.
    assert 13 * 60 <= total <= 17 * 60, total
    page = app_page.tables()["stages"]["resume_for_contact"]
    assert sum(s for _n, s in page) == total, page


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _resume(started: str, stage: int) -> dict:
    stages = page_db.progress("resume_for_contact")["stages"]
    return dict(LISTEN, **{"work/" + WID: _w(
        kind="resume_for_contact", title="Resume for Sam (Example Insurance)", status="running",
        claimed_by="session_job1", claimed_at=started, stage_at=started, stage=stage, stages=stages,
        run_by="session_job1", lease_until="2026-10-25T09:30:00.000Z",
        args={"for_contact": "sam_example"})})


def test_past_its_estimate_the_card_shows_how_long_it_has_run_with_no_bar(run, tmp_path):
    # Started 18 minutes ago, in its last step: past every estimate.
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": CARD}], WIDE,
              seed=_resume("2026-10-25T08:42:00.000Z", 4), clock=T)
    card = got["after"][0]["eval"]
    assert card is not None, "the resume's card is in Claude's work"
    assert not card["bar"], card
    assert "left" not in card["text"], card
    assert "18 min" in card["text"] or "18m" in card["text"], card


def test_inside_its_estimate_the_bar_and_the_time_left_stay(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": CARD}], WIDE,
              seed=_resume("2026-10-25T08:58:00.000Z", 1), clock=T)
    card = got["after"][0]["eval"]
    assert card is not None and card["bar"], card
    assert "left" in card["text"], card
