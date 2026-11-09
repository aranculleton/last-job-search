"""A change that changed nothing finishes cleanly: no spinner, never "Reply written" (T10).

A person's copy, 2026-11-09: changes asked with the pencil that Claude held, set aside or could
not make finished with nothing new on the page. The draft's row said "Finished · putting the
new version on your page" with its spinner for good, since it waited for a new version that
would never come; and on a person whose draft the change had set aside, the card said "Reply
written · Finished · Putting it on your page" for two hours. Now the finish says how it ended
(`app.py done --outcome held|set_aside|unchanged`), the card says it at once, and work that
changed nothing never waits for a version. A finished change whose new version has not
reached the page in a few minutes stops spinning and says it finished.

Every person and employer is invented (the page journeys' sample).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_cards_say_claudes_work_once_and_keep_every_answer_in_reach import JUNO, PEN, T, _tweak  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402

HELD = "Held until she answers the earlier message."


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _held(outcome="held", rev="m1", finished="2026-10-25T08:58:00.000Z", answer=None):
    seed = _tweak("done", rev=rev, summary=HELD, finished_at=finished)
    w = seed["work/tweak~msg-juno-1~x"]
    w["result"]["outcome"] = outcome
    if answer:
        w["result"]["answer"] = answer
    return seed


def test_a_held_change_says_held_at_once_with_no_spinner(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE, seed=_held(), clock=T)
    done = got["after"][0]["eval"]["done"]
    assert done.startswith("Held · Held until she answers"), done
    assert "putting" not in done and "New version" not in done, done
    spin = got["after"][0]["eval"]
    assert spin["stop"] == 0, spin


def test_a_change_set_aside_or_not_possible_says_so(run, tmp_path):
    for outcome, words in (("set_aside", "Set aside"), ("unchanged", "Not changed")):
        got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE, seed=_held(outcome), clock=T)
        done = got["after"][0]["eval"]["done"]
        assert done.startswith(words), (outcome, done)
        assert "putting" not in done, done


def test_a_written_answer_to_a_change_shows_on_its_card(run, tmp_path):
    said = "Her last message asked for a call, so a shorter note would drop the one thing she wanted."
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE,
              seed=_held("unchanged", answer=said), clock=T)
    done = got["after"][0]["eval"]["done"]
    assert done.startswith("Not changed") and said in done, done


def test_a_finished_change_stops_spinning_once_a_page_update_is_overdue(run, tmp_path):
    """No outcome said, and the version never came: after a few minutes it says it finished."""
    seed = _tweak("done", rev="m1", summary="Her message now asks straight for the call.",
                  finished_at="2026-10-25T08:30:00.000Z")
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE, seed=seed, clock=T)
    done = got["after"][0]["eval"]["done"]
    assert done.startswith("Finished: her message now asks"), done
    assert "putting" not in done, done


GOING = ("(() => { const c = document.querySelector('[data-item=\"%s\"]'); if (!c) return null;"
         " const g = c.querySelector('.going'); return {going: g ? g.innerText.replace(/\\s+/g, ' ').trim() : '',"
         " spin: !!(g && g.querySelector('.spin')), text: c.innerText}; })()" % JUNO)


def test_a_change_that_left_no_draft_never_says_reply_written(run, tmp_path):
    """The change set her draft aside: her card has no draft, and the finished change is not a
    reply about to arrive."""
    model = copy.deepcopy(journeys._sample())
    model["messages"] = [m for m in model.get("messages") or [] if m.get("contact") != JUNO]
    for outcome in ("set_aside", None):
        seed = _held(outcome) if outcome else _tweak("done", rev="m1", summary=HELD,
                                                     finished_at="2026-10-25T08:58:00.000Z")
        got = _go(run, tmp_path, [{"hash": "contacts", "eval": GOING}], WIDE, model=model,
                  seed=seed, clock=T)
        r = got["after"][0]["eval"]
        assert r is not None, "her card is on Contacts"
        assert "Reply written" not in r["text"] and "Putting it on your page" not in r["text"], r
        assert not r["spin"], r
        if outcome:
            assert r["going"].startswith("Set aside"), r
