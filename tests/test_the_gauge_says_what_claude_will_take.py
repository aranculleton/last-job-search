"""The gauge says what waking Claude will take, from this copy's own work (2026-11-05).

The maintainer: the gauge beside a control "is meant to deter someone from spending tokens
unnecessarily", but it was on one card in To do and said the app's default minutes. Now a
control that wakes Claude carries it (the page draws it for any button made with `wakes`),
a control that only runs code carries none, and its minutes are this copy's own: the median
of its finished work of that kind (tools/page_db.py work_times), the default only with no
history. Every person and employer is invented.
"""
from __future__ import annotations

import copy
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import page_db  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import WIDE, _go, _sample  # noqa: E402

NOW = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.timezone.utc)
T = "2026-10-25T09:00:00.000Z"


def _done(kind, claimed, took_s):
    start = dt.datetime.fromisoformat(claimed.replace("Z", "+00:00"))
    return {"data": {"kind": kind, "status": "done", "claimed_at": claimed,
                     "finished_at": (start + dt.timedelta(seconds=took_s)).strftime("%Y-%m-%dT%H:%M:%SZ")}, "version": 3}


def test_the_time_is_the_median_of_this_copys_own_finished_work_of_that_kind():
    db = {"work": {"a": _done("draft", "2026-11-04T10:00:00Z", 600), "b": _done("draft", "2026-11-03T10:00:00Z", 1200),
                   "c": _done("draft", "2026-11-02T10:00:00Z", 900),
                   # Too old to say how long it takes now, and a kind with too little history.
                   "d": _done("draft", "2026-09-01T10:00:00Z", 9000),
                   "e": _done("follow_up", "2026-11-04T10:00:00Z", 300), "f": _done("follow_up", "2026-11-04T11:00:00Z", 300),
                   "g": {"data": {"kind": "draft", "status": "failed", "claimed_at": "2026-11-04T10:00:00Z",
                                  "finished_at": "2026-11-04T12:00:00Z"}}}}
    assert page_db.work_times(db, NOW) == {"draft": 900}


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


GAUGES = r"""(() => {
  const seen = (b) => !!(b.offsetWidth || b.offsetHeight);
  const wakers = [...document.querySelectorAll('#main [data-wakes], #rail [data-wakes]')].filter(seen);
  const free = [...document.querySelectorAll('#main button, #rail button')].filter((b) => seen(b) && !b.hasAttribute('data-wakes')
    && (/^(Done|I sent it|Choose the day)$/.test(b.textContent.trim()) || b.hasAttribute('data-bin')));
  const after = (b) => (b.nextElementSibling && b.nextElementSibling.classList.contains('cost') ? b.nextElementSibling.textContent : null);
  return {wakers: wakers.map((b) => [b.dataset.wakes, b.textContent.trim(), after(b)]), freeWithGauge: free.filter(after).map((b) => b.textContent.trim())};
})()"""


def test_every_control_that_wakes_claude_has_the_gauge_and_its_minutes_follow_history(run, tmp_path):
    m = _sample()
    got = _go(run, tmp_path, [{"hash": "todo", "eval": GAUGES}], WIDE, model=m, clock=T)
    r = got["after"][0]["eval"]
    assert r["wakers"], "To do has controls that wake Claude"
    assert all(g for _, _, g in r["wakers"]), ("each carries the gauge", r)
    assert not r["freeWithGauge"], ("a control that only runs code carries none", r)
    kind = r["wakers"][0][0]
    m2 = copy.deepcopy(m)
    m2["work_time"] = {kind: 25 * 60}
    got2 = _go(run, tmp_path, [{"hash": "todo", "eval": GAUGES}], WIDE, model=m2, clock=T)
    g2 = [g for k, _, g in got2["after"][0]["eval"]["wakers"] if k == kind][0]
    assert g2.startswith("25 min") and "About 25 minutes of Claude's time, from your Claude allowance" in g2, g2
    assert g2 != r["wakers"][0][2], "the minutes are this copy's own once it has a history"
