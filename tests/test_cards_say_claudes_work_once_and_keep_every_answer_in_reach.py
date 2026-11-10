"""A card says Claude's work once, keeps every answer within reach, and opens where it lives.

The maintainer's notes of 2026-11-05, each held here (every person and employer is invented,
the sample's own):
- a card's question-and-answer box vanished into the card under the pointer (its fill was the
  hovered card's colour in the dark look): it keeps its own hairline;
- "Also at <employer>" on a person's card listed the message to that same person;
- a change asked with the pencil showed twice, the whole paste as one grey run near the top
  and a second pending line under the draft: one block under the draft, the words clipped to
  two lines with their line breaks and Show all, then one state and Stop Claude;
- "New version: ...." (a full stop doubled) over the old words: "New version" only once the
  new words are on the card;
- a person's finished work offered "Open in Jobs": each opens where its record lives;
- finished work was a whole card each: one compact row, the whole row opening its place;
- a hidden answer had no way back, and a long exchange showed everything: the latest only,
  "Earlier (N)" opening the rest in place, a hidden one a quiet "Claude answered ... · Show";
- the Chat bubble grows and shrinks, remembered on the device, never on a phone;
- an inline work line said only "Saved. Sent to Claude ..." where the work list named the
  task: it names it, without the card's employer and role.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import test_the_page_journeys as journeys  # noqa: E402
from test_claudes_work_says_stop_claude_and_an_answer_offers_its_next_step import LISTEN, TH, _answered, _w  # noqa: E402
from test_the_page_journeys import PHONE, WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
JUNO = "larkspur_retail_castellan"


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _card_talk(n):
    """A question asked n times on the Larkspur Retail job's card, each answered."""
    seed = dict(_answered({"msg-juno-1": "m1", "msg-kit-1": "m4"}))
    for k in list(seed):
        if k.startswith("talk/" + TH + "/messages/"):
            del seed[k]
    for i in range(n):
        seed["talk/%s/messages/q%d" % (TH, i)] = {"from": "you", "text": "Question number %d about the role?" % (i + 1),
                                                   "at": "2026-10-25T08:%02d:00.000Z" % (10 + i * 5), "work": "talk~" + TH + "~mq1", "_v": 1}
        seed["talk/%s/messages/a%d" % (TH, i)] = {"from": "claude", "text": "Answer number %d." % (i + 1),
                                                   "at": "2026-10-25T08:%02d:30.000Z" % (10 + i * 5), "_v": 1}
    return seed


# ------------------------------------------------------------------ the box under a card


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_cards_answer_box_stays_distinct_under_the_pointer(run, tmp_path, scheme):
    look = r"""(() => { const c = document.querySelector('[data-item="r12-2"]'), t = c && c.querySelector('.card-talk');
      if (!t) return null; const s = getComputedStyle(t), cs = getComputedStyle(c);
      return {card: cs.backgroundColor, fill: s.backgroundColor, edge: s.borderTopColor, width: parseFloat(s.borderTopWidth)}; })()"""
    got = run("engine", html=_page(tmp_path), viewport=WIDE, scheme=scheme, seed=_card_talk(1), fake={"canSend": "available"}, clock=T,
              steps=[{"hash": "jobs", "eval": "(document.querySelector('[data-item=\"r12-2\"]').dispatchEvent(new MouseEvent('mouseover', {bubbles: true})), 1)"},
                     {"eval": look}])
    assert not got["errors"], got["errors"]
    r = got["after"][1]["eval"]
    assert r and r["width"] >= 1 and r["edge"] != r["card"], r


def _page(tmp_path):
    import app_page
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(journeys._sample())))
    return path


EARLY = r"""(() => { const c = document.querySelector('[data-item="r12-2"] .card-talk'); if (!c) return null;
  const e = c.querySelector('.ct-early'), l = c.querySelector('.ct-latest');
  return {early: e ? [e.textContent, e.getAttribute('aria-expanded')] : null, pairs: [...c.querySelectorAll('.ct-pair')].map((p) => p.textContent.replace(/\s+/g, ' ').trim()),
    top: l ? Math.round(l.getBoundingClientRect().top) : null}; })()"""


def test_a_long_exchange_shows_the_latest_and_opens_the_rest_in_place(run, tmp_path):
    into = "(document.querySelector('[data-item=\"r12-2\"] .card-talk').scrollIntoView({block: 'center'}), 1)"
    tap = "(document.querySelector('[data-k=\"ct-early:%s\"]').click(), 1)" % TH
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": into}, {"eval": EARLY}, {"eval": tap}, {"eval": EARLY}],
              WIDE, seed=_card_talk(5), clock=T)
    got["after"] = [got["after"][1], got["after"][3]]
    first, opened = got["after"][0]["eval"], got["after"][1]["eval"]
    assert first["early"] == ["Earlier (4)", "false"] and len(first["pairs"]) == 1 and "Question number 5" in first["pairs"][0], first
    assert opened["early"][1] == "true" and len(opened["pairs"]) == 5, opened
    assert [p.split(" about")[0][-1] for p in opened["pairs"]] == ["1", "2", "3", "4", "5"], opened["pairs"]
    assert abs(opened["top"] - first["top"]) <= 2, ("the page holds still", first["top"], opened["top"])


def test_one_exchange_has_no_earlier_and_a_hidden_one_leaves_a_way_back(run, tmp_path):
    folded = ("(() => { const f = document.querySelector('[data-item=\"r12-2\"] .ct-folded'); return f ? f.textContent : null; })()")
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": EARLY},
                              {"open": "ct-hide:" + TH, "eval": folded},
                              {"open": "ct-show:" + TH, "eval": EARLY}],
              WIDE, seed=_card_talk(1), clock=T)
    one, line, back = (a["eval"] for a in got["after"])
    assert one["early"] is None and len(one["pairs"]) == 1, one
    assert line and line.startswith("Claude answered ") and "Show" in line, line
    assert back and len(back["pairs"]) == 1, back


# ------------------------------------------------------------------ a person's card


def test_also_at_never_names_the_cards_own_person(run, tmp_path):
    rel = "(() => { const r = document.querySelector('[data-item=\"%s\"] .related'); return r ? r.textContent : ''; })()" % JUNO
    got = _go(run, tmp_path, [{"hash": "contacts", "more": JUNO, "eval": rel}], WIDE, clock=T)
    text = got["after"][0]["eval"]
    assert "Juno" not in text, text


ASK = "Make it shorter, and mention Thursday.\n\nHere is what she sent me:\nThanks Morgan, Thursday works.\nSee you then, and bring the planning examples."


def _tweak(status="queued", rev="m1", summary=None, **kw):
    w = _w(kind="tweak", title="Edit message: Juno at Larkspur Retail", status=status,
           args={"v": 1, "text": ASK, "target": {"id": "msg-juno-1", "output": "message", "contact": JUNO, "rev": rev}}, **kw)
    if summary:
        w["result"] = {"summary": summary, "links": []}
    return dict(LISTEN, **{"work/tweak~msg-juno-1~x": w})


PEN = r"""(() => { const c = document.querySelector('[data-item="%s"]'); if (!c) return null;
  const all = c.textContent;
  const block = c.querySelector('.tweak-going');
  const q = block && block.querySelector('.clip-text');
  return {times: all.split('Thanks Morgan, Thursday works').length - 1, going: [...c.querySelectorAll('[data-going]')].map((g) => g.textContent),
    clipped: q ? q.classList.contains('is-clipped') && getComputedStyle(q).whiteSpace === 'pre-wrap' : null,
    show: block ? [...block.querySelectorAll('.clip-toggle')].map((b) => b.textContent) : [], stop: [...c.querySelectorAll('button')].filter((b) => b.textContent === 'Stop Claude').length,
    done: (c.querySelector('.tweak-done') || {}).textContent || ''}; })()""" % JUNO


def test_a_change_asked_with_the_pencil_is_said_once_under_the_draft(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE, seed=_tweak(), clock=T)
    r = got["after"][0]["eval"]
    assert r["times"] == 1 and r["clipped"] is True and r["show"] == ["Show all"] and r["stop"] == 1, r
    assert not any("Thanks Morgan" in g for g in r["going"]), r["going"]


def test_new_version_is_said_only_once_the_new_words_are_on_the_card(run, tmp_path):
    waiting = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE,
                  seed=_tweak("done", rev="m1", summary="Her message now asks straight for the call she offered.", finished_at="2026-10-25T08:58:00.000Z"), clock=T)
    assert "New version" not in waiting["after"][0]["eval"]["done"] and "putting" in waiting["after"][0]["eval"]["done"], waiting["after"][0]["eval"]
    there = _go(run, tmp_path, [{"hash": "contacts", "eval": PEN}], WIDE,
                seed=_tweak("done", rev="m0", summary="Her message now asks straight for the call she offered.", finished_at="2026-10-25T08:58:00.000Z"), clock=T)
    done = there["after"][0]["eval"]["done"]
    assert "New version: Her message now asks straight for the call she offered. The earlier" in done and ".." not in done, done


# ------------------------------------------------------------------ Claude's work


def _done(kind, title, args):
    return _w(kind=kind, title=title, status="done", finished_at="2026-10-25T08:50:00.000Z", args=args, result={"summary": "Ready.", "links": []})


DONE = dict(LISTEN, **{
    "work/follow_up~a": _done("follow_up", "Follow up with Wren", {"contact": "fernhill_freight_halloway"}),
    "work/tweak~b": _done("tweak", "Change the message to Juno", {"target": {"id": "msg-juno-1", "output": "message", "contact": JUNO}}),
    "work/tweak~c": _done("tweak", "Change the resume: Ellerwick Trust", {"target": {"id": "app-ellerwick-insight", "output": "resume"}}),
    "work/talk~d": _done("talk", "About Larkspur Retail", {"about": {"kind": "job", "id": "r12-2", "label": "Larkspur Retail"}}),
    # A resume made for a contact lives on their card: asked in a chat with only their name in
    # its title, and its download fetched by path (the maintainer, 2026-11-10: each opened Jobs
    # searching for the name, "Nothing matches").
    "work/resume_for_contact~e": _done("resume_for_contact", "Resume for Juno (Larkspur Retail)", {"job": None}),
    "work/files~resume-" + JUNO: _done("files", "The resume made for Juno, ready to download",
                                       {"paths": ["documents/network/%s/Resume_For_Juno.pdf" % JUNO], "files": ["Resume_For_Juno.pdf"]}),
})
ROWS = r"""(() => [...document.querySelectorAll('#rail [data-work]')].map((c) => ({id: c.getAttribute('data-work'),
  open: (c.querySelector('a.wc-open') || {getAttribute: () => null}).getAttribute('data-k'), chip: !!c.querySelector('.state-word'),
  pills: [...c.querySelectorAll('.wc-actions .btn, .wc-actions a')].map((b) => b.textContent), bin: !!c.querySelector('[data-k^="wput:"]')})))()"""


def test_finished_work_is_a_compact_row_opening_where_its_record_lives(run, tmp_path):
    m = journeys._sample()
    m["made_at"] = "2026-10-25T08:55:00Z"      # after they finished: their results are on the page
    got = _go(run, tmp_path, [{"hash": "todo", "eval": ROWS}, {"eval": ROWS}], WIDE, model=m, seed=DONE, clock=T)
    rows = {r["id"]: r for r in got["after"][1]["eval"]}
    assert rows["follow_up~a"]["open"].startswith("open:contacts:"), rows
    assert rows["tweak~b"]["open"].startswith("open:contacts:"), rows          # a person's, never Jobs
    assert rows["tweak~c"]["open"].startswith("open:drafts:app-ellerwick-insight"), rows
    assert rows["talk~d"]["open"] == "open:jobs:r12-2", rows
    for wid in ("resume_for_contact~e", "files~resume-" + JUNO):
        assert rows[wid]["open"].startswith("open:contacts:"), rows[wid]
    for r in rows.values():
        assert not r["chip"] and not r["pills"] and r["bin"], r


def test_an_inline_work_line_names_its_task_without_the_cards_employer(run, tmp_path):
    seed = dict(LISTEN, **{"work/draft~r12-1": _w(kind="draft", title="Draft: Harbourline Bank, Pricing Analyst", status="queued", args={"job": "r12-1"})})
    line = "(() => { const l = document.querySelector('[data-item=\"r12-1\"] [data-work-inline]'); return l ? l.textContent.replace(/\\s+/g, ' ').trim() : null; })()"
    got = _go(run, tmp_path, [{"hash": "jobs", "eval": line}], WIDE, seed=seed, clock=T)
    text = got["after"][0]["eval"]
    assert text and text.startswith("Draft ·") and "Harbourline" not in text and "Saved. Sent to Claude" not in text and "Stop Claude" in text, text


# ------------------------------------------------------------------ the Chat bubble


DOCK = r"""(() => { const d = document.getElementById('chat-dock'), b = document.querySelector('[data-k="dock-size"]');
  if (!d || d.hidden) return null; const body = d.querySelector('.dock-body');
  return {w: Math.round(d.getBoundingClientRect().width), h: Math.round(d.getBoundingClientRect().height),
    btn: b && b.getClientRects().length ? [b.getAttribute('aria-label'), b.getAttribute('aria-pressed')] : null,
    end: body ? body.scrollHeight - body.scrollTop - body.clientHeight < 80 : null,
    kept: (() => { try { return localStorage.getItem('ljs:dock-big'); } catch (e) { return 'x'; } })()}; })()"""


def test_the_chat_bubble_grows_and_shrinks_and_keeps_the_choice(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "todo", "open": "chat-fab", "eval": DOCK},
                              {"open": "dock-size", "eval": DOCK},
                              {"hash": "jobs", "eval": DOCK},
                              {"open": "dock-size", "eval": DOCK}], WIDE, clock=T)
    small, big, again, back = (a["eval"] for a in got["after"])
    assert small["btn"] == ["Make the chat bigger", "false"], small
    assert big["w"] >= small["w"] * 1.6 and big["h"] > small["h"] and big["btn"] == ["Make the chat smaller", "true"] and big["kept"] == "1", (small, big)
    assert big["end"] is True, "the latest message is still in view"
    assert again["w"] == big["w"], ("the choice survives a redraw", again)
    assert back["w"] == small["w"] and back["kept"] is None, back


def test_a_phone_has_no_bubble_size_toggle(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "todo", "eval": "(() => { const b = document.querySelector('[data-k=\"dock-size\"]'); return !!(b && b.getClientRects().length); })()"}],
              PHONE, clock=T)
    assert got["after"][0]["eval"] is False


# A person's copy (2026-11-05): a change to the message to someone, finished, said so in a toast
# whose "See it" opened Jobs. The toast now opens where its record lives (workPlace), as the
# work list does: a person's work in Contacts, on them.
TOASTED = r"""(() => ({hash: location.hash, toasts: [...document.querySelectorAll('[data-toast]')].map((t) => t.textContent).join(' | ')}))()"""


def test_a_finished_change_to_a_persons_message_opens_contacts_from_its_toast(run, tmp_path):
    running = dict(DONE["work/tweak~b"], status="running", finished_at=None, result=None,
                   claimed_by="cloud-1", claimed_at="2026-10-25T08:50:00.000Z", stage_at="2026-10-25T08:50:00.000Z",
                   lease_until="2026-10-25T09:30:00.000Z")
    seed = dict(LISTEN, **{"work/tweak~b": running})
    got = _go(run, tmp_path, [
        {"hash": "jobs", "eval": TOASTED},
        {"write": {"work/tweak~b": DONE["work/tweak~b"]}, "eval": TOASTED},
        {"click": "See it", "within": "#toasts", "eval": TOASTED},
    ], WIDE, seed=seed, clock=T)
    before, toasted, opened = (x["eval"] for x in got["after"])
    assert "Change the message to Juno: ready." in toasted["toasts"], toasted
    assert opened["hash"].startswith("#contacts"), opened
