"""Claude's work shows its queue: what runs now, what waits next and in what order (issue #238).

The person asked for several things on the page in a row (a few message changes, then a
resume made for a contact) and could not tell what was queued and in what order, which ran at
the same time, or why the resume seemed to sit behind the small changes. Now one small strip
over the cards says what runs now and what waits, in the order Claude takes it (the engine's,
tools/page_db.py next_item: a question first, then a big job, which starts in a chat of its
own, then the rest as asked), each big job said as running in a chat of its own; a big job's
card says it does not wait for other work, and waiting light work says what it waits behind.

Every person and employer is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_claudes_work_says_stop_claude_and_an_answer_offers_its_next_step import AT, LISTEN, _w  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
RESUME = "contact_resume~sam_example~r1"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _tweak(n, status="queued", **kw):
    return _w(kind="tweak", title=f"Edit message {n}", status=status, to="either", asked_at=AT(f"5{n}:00"),
              args={"v": 1, "text": "Shorter.", "target": {"id": f"msg-x-{n}", "output": "message", "rev": "m1"}}, **kw)


def _seed():
    running = dict(claimed_by="cloud-1", claimed_at=AT("57:00"), stage_at=AT("57:00"),
                   lease_until="2026-10-25T09:30:00.000Z")
    return dict(LISTEN, **{
        "work/tweak~1": _tweak(1, "running", **running),
        "work/tweak~2": _tweak(2),
        "work/tweak~3": _tweak(3),
        # Asked after the changes, started at once in a chat of its own.
        "work/" + RESUME: _w(kind="resume_for_contact", title="Resume for Sam (Example Insurance)", status="running",
                             asked_at=AT("55:30"), claimed_by="cloud-1", claimed_at=AT("56:00"), stage_at=AT("56:00"),
                             run_by="session_job1", chat_title="Resume for Sam", lease_until="2026-10-25T09:30:00.000Z",
                             args={"for_contact": "sam_example"}),
        # A question asked last goes first among what waits.
        "work/talk~q": _w(kind="talk", title="Answer: when is my next interview?", status="queued", to="cloud",
                          asked_at=AT("58:30"), args={"thread": "card-job-1", "message": "m-1",
                                                      "about": {"kind": "job", "id": "r12-1", "label": "A job"}}),
    })


LOOK = r"""(() => {
  const q = document.querySelector('[data-k="work-queue"]');
  const card = (id) => { const c = document.querySelector('[data-work="' + id + '"]'); return c ? c.textContent.replace(/\s+/g, ' ').trim() : null; };
  return {now: q && q.querySelector('[data-queue=now]') ? q.querySelector('[data-queue=now]').textContent : null,
    next: q && q.querySelector('[data-queue=next]') ? q.querySelector('[data-queue=next]').textContent : null,
    resume: card('%s'), waiting: card('tweak~3')};
})()""" % RESUME


def test_the_queue_says_what_runs_now_and_what_waits_in_order(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": LOOK}], WIDE, seed=_seed(), clock=T)
    r = got["after"][0]["eval"]
    assert r["now"] is not None and r["next"] is not None, r
    # Running now: the change here, and the resume in a chat of its own.
    assert r["now"].startswith("Running now:"), r
    assert "Edit message 1" in r["now"] and "Resume for Sam (Example Insurance), in a chat of its own" in r["now"], r
    # Waiting, in the order Claude takes it: the question first, then the changes as asked.
    nxt = r["next"]
    assert nxt.startswith("Waiting, in this order:"), r
    order = [nxt.index(s) for s in ("1. Answer", "2. Edit message 2", "3. Edit message 3")]
    assert order == sorted(order), nxt
    # The big job's card says it does not wait for other work.
    assert r["resume"] and "In a chat of its own, so it does not wait for other work." in r["resume"], r
    # A change waiting here says what it waits behind.
    assert r["waiting"] and "after" in r["waiting"], r


def test_one_piece_of_work_needs_no_queue(run, tmp_path):
    seed = dict(LISTEN, **{"work/tweak~2": _tweak(2)})
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": LOOK}], WIDE, seed=seed, clock=T)
    r = got["after"][0]["eval"]
    assert r["now"] is None and r["next"] is None, r


def test_a_resumes_files_part_is_said_as_the_resume_in_the_queue_and_the_pill(run, tmp_path):
    """Making a resume downloadable is a stage of the resume (#237): the queue and the header's
    pill name the resume, never "Make the files downloadable"."""
    import test_a_resume_is_ready_only_once_it_can_be_downloaded as made
    seed = made._seed("running")
    pill = r"""(() => { const p = document.querySelector('[data-k="pill"]'); return p ? p.textContent : ''; })()"""
    alone = _go(run, tmp_path, [{"hash": "contacts", "eval": pill}], WIDE, model=made._model(), seed=seed, clock=T)
    assert "Make the files" not in alone["after"][0]["eval"], alone["after"][0]["eval"]
    seed["work/tweak~2"] = _tweak(2)
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": LOOK}], WIDE, model=made._model(), seed=seed, clock=T)
    r = got["after"][0]["eval"]
    assert r["now"] and "Resume for Juno (Larkspur Retail), making it downloadable" in r["now"], r
    assert "Make the files" not in (r["now"] or "") + (r["next"] or ""), r
