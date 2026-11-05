"""Claude's work is called off one way, a suggestion is dismissed, and a card's answer offers
what it made.

The maintainer, 2026-11-05:
- Claude's work was cluttered: "2 waiting for Claude." under the pill's own "2 waiting", a
  "Waking Claude" chip over the line "Sent to Claude. Its chat is waking up ...", and "Don't do
  it", which read as putting the job away. Now each card says one short state ("Waking Claude
  · 1m 4s"), and every control that calls off Claude's work, in the panel or inline on a card,
  is the one faint red "Stop Claude" ("Stop Claude's work on <what>").
- "No thanks" on a suggestion read as cancelling something: it is "Dismiss".
- A card's answer said a note was ready on someone's card and pasted it: under the answer, the
  draft it wrote or changed is one row with the draft's own Copy and I sent it, which becomes
  "Sent" once sent, and the people the answer names open them. An answer that only explained
  shows no step, and never more than two.
Every person and employer is invented (the sample's own).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
AT = lambda s: "2026-10-25T08:%s.000Z" % s  # noqa: E731


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _w(**kw):
    return dict({"to": "cloud", "args": {}, "asked_at": AT("40:00"), "_v": 2, "stages": [], "stage": 0, "steps": [], "attempt": 1}, **kw)


LISTEN = {"chats/cloud-1": {"kind": "cloud", "seen_at": AT("59:30"), "watching": True},
          "meta/listener": {"chat": "cloud-1", "kind": "cloud", "answered_at": AT("58:00"), "since": "2026-10-24T08:00:00.000Z"}}
WORK = dict(LISTEN, **{
    # Waiting its turn, sent, and running: each with its call-off.
    "work/follow_up~wren": _w(kind="follow_up", title="Follow up with Wren", status="queued", args={"contact": "fernhill_freight_halloway"}),
    "work/prep~bea": _w(kind="prep", title="Prepare for the call with Bea", status="running", claimed_by="cloud-1",
                         claimed_at=AT("50:00"), stage_at=AT("50:00"), lease_until="2026-10-25T09:30:00.000Z"),
    "work/draft~r12-1": _w(kind="draft", title="Draft Harbourline Bank", status="queued", args={"job": "r12-1"}),
    # Inline on a person's card: a reply being written, and a change asked with the pencil.
    "work/reply~quayside_foods_ivo": _w(kind="reply", title="Reply to Ivo", status="queued", args={"contact": "quayside_foods_ivo"}),
    "work/tweak~msg-juno-1~s": _w(kind="tweak", title="Edit message: Juno at Larkspur Retail", status="queued",
                                  args={"v": 1, "text": "Shorter.", "target": {"id": "msg-juno-1", "output": "message", "contact": "larkspur_retail_castellan", "rev": "m1"}}),
})

# Every control on the screen that calls off Claude's work (it carries a work item's stop key)
# and every control whose words are one of the old call-offs.
STOPS = r"""(() => {
  const seen = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const all = [...document.querySelectorAll('button')].filter(seen);
  const stopKey = /^(stop:|run-stop:|fg-stop:|rgo-cancel:)|:cancel$/;
  const stops = all.filter((b) => stopKey.test(b.dataset.k || '')).map((b) => [b.textContent.trim(), b.getAttribute('aria-label') || '', b.className]);
  const old = all.map((b) => b.textContent.trim()).filter((t) => /^(Don.t do it|Don.t do them|Cancel all)$/.test(t));
  const sum = [...document.querySelectorAll('.workp .sum, .workp .sum-small')].map((p) => p.textContent);
  const cards = [...document.querySelectorAll('[data-work]')].filter(seen).map((c) => [c.getAttribute('data-work'),
    (c.querySelector('.state-word') || {}).textContent || '', (c.querySelector('.wc-now') || {}).textContent || '']);
  return {stops, old, sum, cards};
})()"""


@pytest.mark.parametrize("vp", [PHONE, WIDE], ids=["phone", "wide"])
def test_every_call_off_of_claudes_work_reads_stop_claude(run, tmp_path, vp):
    steps = [{"hash": "todo", "eval": STOPS, **({"open": "pill"} if vp is PHONE else {})},
             {"hash": "jobs", "eval": STOPS}, {"hash": "contacts", "eval": STOPS}]
    got = _go(run, tmp_path, steps, vp, seed=WORK, fake={"canSend": "available"}, clock=T)
    for r in (a["eval"] for a in got["after"]):
        assert not r["old"], r["old"]
        assert all(t == "Stop Claude" and aria.startswith("Stop Claude's work on ") and "stop-claude" in cls for t, aria, cls in r["stops"]), r["stops"]
    panel = got["after"][0]["eval"]
    assert len(panel["stops"]) >= 2, panel                      # the queued and the running card
    # The count is the pill's: never "N waiting for Claude." again under it, nor "Nothing is sent."
    assert not any("waiting for Claude" in s or "Nothing is sent" in s for s in panel["sum"]), panel["sum"]
    # Jobs: the draft waiting on its card says so inline, with the same Stop Claude; Contacts:
    # the reply being written and the change asked with the pencil, each with its own.
    assert got["after"][1]["eval"]["stops"], got["after"][1]["eval"]
    assert len(got["after"][2]["eval"]["stops"]) >= 2, got["after"][2]["eval"]


def test_a_card_waking_claude_says_it_once(run, tmp_path):
    seed = dict(LISTEN, **{"work/follow_up~wren": _w(kind="follow_up", title="Follow up with Wren", status="queued",
                                                       args={"contact": "fernhill_freight_halloway"}, rung_at=AT("59:00"), sent_at=AT("59:00"))})
    got = _go(run, tmp_path, [{"hash": "todo", "eval": STOPS}], WIDE, seed=seed, fake={"canSend": "available"}, clock=T)
    cards = {k: (chip, line) for k, chip, line in got["after"][0]["eval"]["cards"]}
    chip, line = cards["follow_up~wren"]
    assert "Sent to Claude" not in line and "waking up, which usually" not in line, line
    # One state, never the chip and the line both saying it.
    assert not (chip and chip in line), (chip, line)


def test_a_suggestion_is_dismissed_not_no_thanksed(run, tmp_path):
    look = ("(() => [...document.querySelectorAll('.suggest button')].filter((b) => b.offsetParent)"
            ".map((b) => [b.textContent.trim(), b.getAttribute('aria-label') || ''])) ()")
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": look}, {"hash": "drafts", "eval": look}], WIDE, clock=T)
    rows = [b for a in got["after"] for b in a["eval"]]
    assert any(t == "Dismiss" and aria == "Dismiss this suggestion" for t, aria in rows), rows
    assert not any(t.startswith("No thanks") or aria.startswith("No thanks") for t, aria in rows), rows


# ------------------------------------------------------------------ a card's answer, actionable

TH = "card-job-r12-2"


def _answered(seen):
    """A question on the Larkspur Retail job's card, answered: `seen` is each message's rev
    when it was asked (what the page writes with the question)."""
    wid = "talk~" + TH + "~mq1"
    return dict(LISTEN, **{
        "talk/" + TH: {"to": "cloud", "card": {"kind": "job", "id": "r12-2", "label": "Larkspur Retail, the planning role"},
                       "title": "About Larkspur Retail", "created_at": AT("30:00"), "last_at": AT("50:00"), "_v": 1},
        "talk/" + TH + "/messages/mq1": {"from": "you", "text": "Should I ask Juno about this role first?", "at": AT("30:00"), "work": wid, "_v": 1},
        "talk/" + TH + "/messages/ma1": {"from": "claude", "text": "Yes: Juno replied last week, so a short note to Juno first is worth it.", "at": AT("50:00"), "_v": 1},
        "work/" + wid: _w(kind="talk", title="About Larkspur Retail", status="done", finished_at=AT("50:00"),
                          args={"thread": TH, "message": "mq1", "about": {"kind": "job", "id": "r12-2", "label": "Larkspur Retail"}, "seen": seen}),
    })


ANSWER = r"""(() => {
  const c = document.querySelector('[data-item="r12-2"]');
  if (!c) return null;
  const rows = [...c.querySelectorAll('.ct-steps .ts-row')];
  return {rows: rows.map((r) => [r.getAttribute('data-ts'), r.textContent.replace(/\s+/g, ' ').trim(), [...r.querySelectorAll('button')].map((b) => b.textContent.trim())]),
    names: [...c.querySelectorAll('.ct-a a.name-link')].map((a) => [a.textContent, a.getAttribute('href')])};
})()"""


def test_an_answer_that_made_a_draft_offers_copy_and_i_sent_it_then_says_sent(run, tmp_path):
    # Juno's reply changed since the question (its rev moved); Kit's did not.
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": ANSWER},
                              {"click": "I sent it: the message to Juno", "within": '[data-item="r12-2"] .ct-steps', "exact": True, "eval": ANSWER}],
              WIDE, seed=_answered({"msg-juno-1": "m0", "msg-kit-1": "m4"}), clock=T)
    first, after = got["after"][0]["eval"], got["after"][1]["eval"]
    assert first and len(first["rows"]) == 1, first
    mid, words, buttons = first["rows"][0]
    assert mid == "msg-juno-1" and "Juno" in words and "Copy" in buttons and "I sent it" in buttons, first["rows"]
    # The name in Claude's answer opens Juno.
    assert ["Juno", "#contacts/larkspur_retail_castellan"] in first["names"], first["names"]
    sent = [a for a in got["actions"] if a["action"] == "msg.sent"]
    assert sent and sent[-1]["item"] == "msg-juno-1", got["actions"]
    assert len(after["rows"]) == 1 and "Sent" in after["rows"][0][1] and not after["rows"][0][2], after


def test_an_answer_that_only_explained_offers_nothing_and_never_more_than_two(run, tmp_path):
    same = _go(run, tmp_path, [{"hash": "jobs", "eval": ANSWER}], WIDE, seed=_answered({"msg-juno-1": "m1", "msg-kit-1": "m4"}), clock=T)
    assert same["after"][0]["eval"]["rows"] == [], same["after"][0]["eval"]
    every = _go(run, tmp_path, [{"hash": "jobs", "eval": ANSWER}], WIDE, seed=_answered({}), clock=T)
    assert 1 <= len(every["after"][0]["eval"]["rows"]) <= 2, every["after"][0]["eval"]
