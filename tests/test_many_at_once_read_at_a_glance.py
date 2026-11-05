# ruff: noqa: F811  (the shared page fixtures are imported and then named as parameters)
"""Many pieces of work at once read at a glance, and a conversation stays with Claude.

The maintainer, 2026-11-05: drafting nine follow-ups put "Saved. Sent to Claude, which is open
now: it starts in a moment." and a Cancel on every row ("a bit cluttered and its not
immediately clear"); five finished answers stood one card each in Claude's work ("we already
bulk some running tasks, why arent these ones grouped too?"); and a second message sent while
Claude was answering the first made no work, so it was seen by chance. Every person and
employer here is invented.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_contacts_is_one_page_with_each_persons_draft import book, model, run, page, CLOCK  # noqa: E402,F401
from test_contacts_show_only_what_the_persons_rules_allow import WIDE  # noqa: E402

_W = {"to": "cloud", "args": {}, "asked_at": "2026-10-25T18:20:00Z", "_v": 2}


def _follow_ups(model):
    return [d for d in model["due"] if str(d.get("action", "")).startswith("work:follow_up") and d.get("kind") in ("follow_up", "nudge")]


def test_drafting_several_follow_ups_is_one_line_and_a_word_a_row(run, page, model):
    rows = [d for d in _follow_ups(model) if d.get("kind") == "nudge"][:4]
    seed = {"work/follow_up~due~" + d["id"]: dict(_W, kind="follow_up", title="Follow up", status="queued", args={"due": d["id"]}) for d in rows}
    first = "work/follow_up~due~" + rows[0]["id"]
    seed[first] = dict(seed[first], status="running", claimed_at="2026-10-25T18:21:00Z")
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, seed=seed, steps=[
        {"hash": "todo", "eval": "(() => { const s = document.querySelector('.group-card .g-summary'); return {summary: s ? s.textContent : '', long: document.querySelectorAll('.group-card .g-row .work-inline').length, words: [...document.querySelectorAll('.group-card .g-state')].map((e) => e.textContent.trim())}; })()"}])
    assert not got["errors"], got["errors"]
    e = got["after"][0]["eval"]
    assert "Drafting 4" in e["summary"] and "1 being written" in e["summary"] and "3 in line" in e["summary"] and "Cancel all" in e["summary"], e
    assert e["long"] == 0 and "Writing" in e["words"] and "In line" in e["words"], e


def test_finished_answers_are_one_card_in_claudes_work(run, page):
    # Five finished minutes ago, and four an hour ago (folded away under "N finished").
    seed = {"work/talk~t%d" % i: dict(_W, kind="talk", title="Answer: “About Juno %d: did we apply?”" % i, status="done",
                                      finished_at="2026-10-25T18:2%d:00Z" % i, result={"summary": "Yes."}) for i in range(5)}
    seed.update({"work/talk~o%d" % i: dict(_W, kind="talk", title="Answer: “About Bea %d”" % i, status="done",
                                           finished_at="2026-10-25T17:2%d:00Z" % i, result={"summary": "Yes."}) for i in range(4)})
    titles = "[...document.querySelectorAll('[data-work-run] .wc-title')].map((e) => e.textContent.trim())"
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, seed=seed, steps=[
        # Claude's work, opened where it is not already beside the screen.
        {"hash": "contacts", "eval": "(() => { const r = document.getElementById('rail'); const w = r && r.querySelector('.workp'); if (!w || !w.getClientRects().length) document.getElementById('pill').click(); return 1; })()"},
        {"eval": titles},
        {"eval": "([...document.querySelectorAll('[data-k=\"fold:work\"]')].find((b) => b.getClientRects().length).click(), 1)"},
        {"eval": titles}])
    assert not got["errors"], got["errors"]
    assert "5 answers done" in got["after"][1]["eval"], got["after"][1]["eval"]
    assert "4 answers done" in got["after"][3]["eval"], got["after"][3]["eval"]


def test_a_message_while_claude_answers_the_last_goes_to_claude(run, page):
    seed = {"talk/cloud-1": {"to": "cloud", "conv": "1", "title": "Rafe's thread", "created_at": "2026-10-25T18:10:00Z", "_v": 1},
            "talk/cloud-1/messages/m1": {"from": "you", "text": "Here is Rafe's thread: ...", "at": "2026-10-25T18:10:00Z", "work": "talk~cloud-1~m1", "_v": 1},
            "work/talk~cloud-1~m1": dict(_W, kind="talk", title="Answer: Rafe's thread", status="running", claimed_at="2026-10-25T18:11:00Z",
                                         args={"thread": "cloud-1", "message": "m1"})}
    got = run("engine", html=page, viewport=WIDE, clock=CLOCK, seed=seed, steps=[
        {"hash": "chat"}, {"type": "lets make it go somewhere"}, {"open": "talk-send"}])
    assert not got["errors"], got["errors"]
    talk = [w for w in got["work"] if w.get("kind") == "talk"]
    assert len(talk) == 2, talk
