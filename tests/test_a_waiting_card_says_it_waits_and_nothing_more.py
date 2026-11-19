"""A card waiting for Claude says it waits, beside its title, and nothing it is not doing yet.

The screen review, 2026-11-18, on Claude's work with a search running and a draft asked after
it: the draft's dot sat alone on a line over its long title, "Waiting for Claude" dropped to a
third line, an empty 0% bar stood under it, and "Starts in a chat of its own, so it does not
wait for other work" sat under "Waiting, in this order:", which headed that one draft. The
running search's line began in lower case ("under a minute so far · about 7 min left") with
its "left" wrapping beside Stop Claude. Now the title keeps beside its dot, a waiting card has
no bar and no own-chat line until Claude picks it up, the queue says "Waiting:" for one, and
the time line starts with a capital, its time left kept in one piece.

Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_claudes_work_says_stop_claude_and_an_answer_offers_its_next_step import AT, LISTEN, _w  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
DRAFT = "draft~r12-2"
SEED = dict(LISTEN, **{
    "work/search~1": _w(kind="search", title="Finding jobs", status="running", asked_at=AT("59:30"), claimed_by="cloud-1",
                        claimed_at=AT("59:30"), stage_at=AT("59:40"), lease_until="2026-10-25T09:30:00.000Z",
                        stages=[{"name": "Getting started", "est_s": 60}, {"name": "Searching job sites", "est_s": 300}, {"name": "Scoring", "est_s": 120}],
                        stage=1, steps=[{"at": AT("58:00"), "text": "Searching 4 job sites and 12 employers"}]),
    "work/" + DRAFT: _w(kind="draft", title="CV and letter: Larkspur Retail, Senior Supply Chain Analyst for the Northern Distribution team",
                        status="queued", asked_at=AT("59:20"), args={"job": "r12-2"}),
})


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


LOOK = r"""(() => {
  const c = [...document.querySelectorAll('[data-work="%s"]')].find((e) => e.getClientRects().length);
  const s = [...document.querySelectorAll('[data-work="search~1"]')].find((e) => e.getClientRects().length);
  const q = [...document.querySelectorAll('[data-k="work-queue"]')].find((e) => e.getClientRects().length);
  if (!c || !s) return null;
  const dot = c.querySelector('.wc-head > :is(.dot, .spin)').getBoundingClientRect();
  const g = document.createRange(); g.selectNodeContents(c.querySelector('.wc-title'));
  const first = g.getClientRects()[0];
  const time = (s.querySelector('[data-time]') || {}).textContent || '';
  return {beside: dot.top < first.bottom && dot.bottom > first.top, titleLines: new Set([...g.getClientRects()].map((r) => Math.round(r.top))).size,
    bar: !!c.querySelector('[role=progressbar]'), own: !!c.querySelector('[data-where="own-chat"]'), text: c.textContent,
    next: q && q.querySelector('[data-queue=next]') ? q.querySelector('[data-queue=next]').textContent : null, time};
})()""" % DRAFT


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_waiting_card_keeps_its_title_by_its_dot_and_says_nothing_it_is_not_doing(run, tmp_path, vp):
    steps = [{"hash": "jobs", "open": "pill", "wait": 200, "eval": LOOK}] if vp is PHONE else [{"hash": "jobs", "eval": LOOK}]
    seen = _go(run, tmp_path, steps, vp, seed=SEED, clock=T)["after"][0]["eval"]
    assert seen, seen
    assert seen["beside"], seen
    # Not picked up yet: no bar at 0%, and no "in a chat of its own" under "Waiting".
    assert not seen["bar"] and not seen["own"], seen
    assert "chat of its own" not in seen["text"], seen
    assert seen["next"] and seen["next"].startswith("Waiting: ") and "in this order" not in seen["next"], seen
    assert "chat of its own" not in seen["next"], seen


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_a_running_cards_time_line_starts_with_a_capital_and_keeps_its_time_left_whole(run, tmp_path, vp):
    steps = [{"hash": "jobs", "open": "pill", "wait": 200, "eval": LOOK}] if vp is PHONE else [{"hash": "jobs", "eval": LOOK}]
    seen = _go(run, tmp_path, steps, vp, seed=SEED, clock=T)["after"][0]["eval"]
    t = seen["time"].strip()
    # Thirty seconds in: "Under a minute so far", never "under a minute so far".
    assert t.startswith("Under a minute") or t.startswith("About "), seen
    assert "left" in t, seen
    # Its time left is one piece: no line break can fall inside "about 7 min left".
    left = t.split(" · ")[-1]
    assert " " not in left and " left" in left, seen
