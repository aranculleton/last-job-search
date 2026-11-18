"""An interview that has ended is finished: in Coming up's fold, with nothing left to do on it.

The maintainer, 2026-11-18, on Coming up: "surely me withdrawing should be under me
finishing". An interview the person withdrew from, its card saying "You withdrew", sat among
the live interviews, above "1 earlier, finished: Hide", and its card still offered "I heard
back" and "Read your prep". The engine marks every ended process past (`app_model._interviews`,
`throttle.FINAL`), and the page folded only the rounds had more than two weeks ago. Now every
ended one (they said no, you withdrew, no reply, hired, an offer turned down, an older
tracker's "declined") is in the fold at once, sorted as the rest are, the newest first, never a
row in By day nor a card in To do; its card offers nothing (DESIGN.md, Coming up's Interviews
list). A round had and waiting to hear back stays above with its "I heard back". Every person
and employer here is invented (tests/app_state.py, the sample page model).
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import throttle  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import Search  # noqa: E402

CLOCK = "2026-10-26T09:00:00Z"
# The ended ones copied from the engine's own withdrawn interview: (status, employer, its day,
# what its pill says). Quillfeather's round was later today: withdrawn the morning of it.
ENDED = [("rejected", "Fernhollow Insurance", "2026-10-20", "They said no"),
         ("no_response", "Quillmark Analytics", "2026-10-12", "No reply"),
         ("hired", "Saltmarsh Foods", "2026-10-19", "Hired"),
         ("offer_declined", "Bramblegate Lending", "2026-10-21", "Offer declined"),
         ("declined", "Brindlemoor Freight", "2026-10-18", "Closed"),
         ("withdrawn", "Quillfeather Health", "2026-10-26T15:00:00Z", "You withdrew")]


def _withdrawn(root):
    """The engine's own interview once the person withdrew: past, never had, never counted."""
    search = Search(os.path.join(str(root), "search"))
    iv = next(i for i in search.model()["interviews"] if i["company"] == "Thornbury Bank")
    aid = search.act("outcome.withdrawn", iv["id"], value={"on": "2026-10-25"}, rev=iv["rev"])
    assert search.apply()["ok"] == [aid], search.receipt(aid)
    m = search.model()
    got = next(i for i in m["interviews"] if i["id"] == iv["id"])
    return got, m["coming_up"]


def test_the_engine_marks_every_ended_status_final_and_a_withdrawal_past(tmp_path):
    for st, *_ in ENDED + [("withdrawn", "", "", "")]:
        assert st in throttle.FINAL, st
    got, cu = _withdrawn(tmp_path)
    assert got["status"] == "withdrawn" and got["past"] is True and not got["had"], got
    assert got["id"] not in cu["ahead"] and got["id"] not in cu["waiting"]
    # Its prep is still on the record: the page is what decides not to offer it.
    assert got["prep"] and got["prep"]["updated"]


def _model(root):
    from test_the_page_journeys import _sample
    m = _sample()
    thornbury, _cu = _withdrawn(root)
    ivs = list(m["interviews"])
    for st, company, when, _word in ENDED:
        one = copy.deepcopy(thornbury)
        one.update(id="int-" + company.split()[0].lower(), company=company, status=st, when=when,
                   all_day="T" not in when, time=None, related={}, alerts=[], suggest=None)
        ivs.append(one)
    ivs.append(thornbury)
    # A round had and waiting to hear back: still going, above the fold, with its I heard back.
    waiting = copy.deepcopy(next(i for i in m["interviews"] if i["id"] == "int-harbourline-risk"))
    waiting.update(id="int-larchmere", company="Larchmere Insurance", role="Pricing Analyst", when="2026-10-21",
                   all_day=True, time=None, had=True, past=False, related={}, alerts=[], suggest=None)
    ivs.append(waiting)
    m["interviews"] = ivs
    m["coming_up"] = app_model.coming_up(ivs)
    return m


CARDS = """[...document.querySelectorAll('#main article.card.interview')].map((c) => {
  const fold = [...document.querySelectorAll('#main p.fold')].find((p) => /earlier, finished/.test(p.textContent));
  return {title: c.querySelector('h3').textContent.replace(/\\u00a0/g, ' '),
    above: !fold || !!(c.compareDocumentPosition(fold) & Node.DOCUMENT_POSITION_FOLLOWING),
    buttons: [...c.querySelectorAll('button')].map((b) => (b.getAttribute('aria-label') || b.textContent).trim()),
    bin: !!c.querySelector('[data-bin]'), text: c.textContent};
})"""


def vp_name(vp):
    return "w%d" % vp["width"]


OPEN_FOLD = """(() => { const b = document.querySelector('#main [data-k="fold:interviews"]');
  if (b) b.click(); return b ? (b.getAttribute('aria-label') || b.textContent) : null; })()"""


def test_an_ended_interview_is_in_the_fold_with_nothing_left_to_do(tmp_path):
    from test_the_page_journeys import _go, browser, PHONE, WIDE
    gen = browser()
    run = next(gen)
    ended = [c for _s, c, _w, _p in ENDED] + ["Thornbury Bank"]
    try:
        for vp in (PHONE, WIDE):
            got = _go(run, tmp_path, [
                {"hash": "interviews", "read": "#main"},
                {"hash": "interviews", "click": "Interviews", "exact": True, "eval": CARDS},
                # The fold opened where there is one: before this was fixed there was none.
                {"eval": OPEN_FOLD},
                {"ready": "document.querySelectorAll('#main article.card.interview').length >= 11", "eval": CARDS},
                {"hash": "todo", "read": "#main"},
            ], vp, model=_model(tmp_path / vp_name(vp)), clock=CLOCK)
            by_day = got["after"][0]["text"]
            for company in ended:
                assert company not in by_day, (company, by_day[:600])
            # What is still going is above, by its day, the round had and waiting last; the ended
            # are folded away, said as finished.
            shut = got["after"][1]
            assert "7 earlier, finished: Show" in shut["text"], shut["text"][:800]
            titles = [c["title"] for c in shut["eval"]]
            assert [t.split(" with ")[-1] for t in titles] == ["Larkspur Retail", "Copperleaf Pay", "Harbourline Bank", "Larchmere Insurance"], titles
            larch = shut["eval"][-1]
            assert any(b.startswith("I heard back") for b in larch["buttons"]), larch["buttons"]
            # Opened, the finished are under the fold, the newest first, each saying how it ended
            # and offering nothing: no I heard back, no prep to read, no trash.
            assert got["after"][2]["eval"] == "Show 7 earlier, finished", got["after"][2]["eval"]
            opened = got["after"][3]["eval"]
            below = [c for c in opened if not c["above"]]
            assert [c["title"].split(" with ")[-1] for c in below] == ["Quillfeather Health", "Bramblegate Lending", "Fernhollow Insurance",
                                                                        "Saltmarsh Foods", "Brindlemoor Freight", "Thornbury Bank", "Quillmark Analytics"], below
            words = {c: w for _s, c, _w, w in ENDED}
            words["Thornbury Bank"] = "You withdrew"
            for c in below:
                company = c["title"].split(" with ")[-1]
                assert words[company] in c["text"], (company, c["text"])
                assert not [b for b in c["buttons"] if b.startswith(("I heard back", "Read your prep", "Prepare me", "Not going ahead"))], (company, c["buttons"])
                assert not c["bin"], company
                assert "No prep yet" not in c["text"] and "Prep ready" not in c["text"], (company, c["text"])
            assert [c["title"] for c in opened if c["above"]] == titles
            # To do never offers the interview withdrawn from this morning as one to come.
            todo = got["after"][4]["text"]
            assert "Quillfeather Health" not in todo, todo[:800]
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
