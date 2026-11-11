"""A live prep says the follow-ups that come after any story once in a part, never under each
question, and says why a part's chip is marked.

The screen review of 2026-11-11 (row 35): "What was your part in it, exactly?", "How did you
know it had worked?" and "What would you do differently now?" stood under every question of a
part told with a story, the same three again and again. They are the part's: said once there,
by who asks, and a question keeps only follow-ups of its own. A prep written before, with them
under each question, keeps the words written for the first and says them once. And the gold
mark on a part's chip had a reason nobody could see: it now says it, in its name and beside
"Known to ask" at a glance. Every person and employer is invented.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import interview_live as L  # noqa: E402
from test_an_interview_has_a_live_prep import _fill  # noqa: E402
from test_interview_pack import _ctx, app  # noqa: E402,F401
from test_the_live_prep_on_the_page import OPEN, REAL, _go, _model, _real_ctx, browser  # noqa: E402
from test_the_page_journeys import PHONE, WIDE  # noqa: E402

pytestmark = pytest.mark.usefixtures("app")
STORY = {L._norm(q) for _w, q in L.STORY_FOLLOW}


def _part_follow(doc):
    return {p["id"]: [L._norm(f["q"]) for f in p.get("follow") or []] for p in doc["parts"]}


def _under_questions(doc):
    out = {}
    for q in doc["questions"]:
        out.setdefault(q["part"], []).extend(L._norm(f["q"]) for f in q.get("follow") or [])
    return out


def test_a_new_prep_puts_the_story_follow_ups_on_the_part_once():
    doc = L.build(_ctx(stage="Second round", format_="PEI and a HackerRank Python exercise, 60 mins"))
    told = {q["part"] for q in doc["questions"] if q["story"]}
    assert told, "the round tells stories"
    for p in doc["parts"]:
        mine = _part_follow(doc)[p["id"]]
        # Once in each part a story is told in, by who asks; none where no story is told.
        assert (sorted(mine) == sorted(STORY)) if p["id"] in told else mine == [], (p["kind"], mine)
        assert all(f["who"] in L.PERSONAS for f in p.get("follow") or [])
    # No question carries them: a question's follow-ups are its own.
    assert not [x for xs in _under_questions(doc).values() for x in xs if x in STORY]


def test_the_words_for_a_parts_follow_ups_are_written_once_and_checked():
    doc = L.build(_ctx(stage="Second round", format_="PEI and a HackerRank Python exercise, 60 mins"))
    part = next(p for p in doc["parts"] if p.get("follow"))
    # Unwritten, the check asks for them, as for any answer.
    assert any(part["title"] in where and "simple answer is not written" in what
               for where, what in L.problems(L.finish(json.loads(json.dumps(doc))), _ctx()))
    words = {"parts": {part["id"]: {"follow": [dict(f, simple="I built the model myself. The planners "
                                                                 "owned what it fed.") for f in part["follow"]]}}}
    got = L.words_into(doc, words)
    said = [t for where, t, _d, _q in L.spoken(got) if part["title"] in where]
    assert said.count("I built the model myself. The planners owned what it fed.") == len(L.STORY_FOLLOW), said


def test_a_prep_written_before_says_them_once_and_keeps_the_words():
    ctx = _real_ctx()
    with open(REAL, encoding="utf-8") as fh:
        old = json.load(fh)
    written = {}
    for q in old["questions"]:
        for f in q.get("follow") or []:
            if L._norm(f["q"]) in STORY:
                written.setdefault((q["part"], L._norm(f["q"])), []).append((f["simple"], q.get("story")))
    doc = L.merge(L.build(ctx), old)
    assert L.problems(doc, ctx) == [], L.problems(doc, ctx)
    kinds = {p["id"]: p["kind"] for p in old["parts"]}
    for p in doc["parts"]:
        mine = _part_follow(doc)[p["id"]]
        under = _under_questions(doc).get(p["id"], [])
        # Said once in the part, and never again under one of its questions.
        assert len(mine) == len(set(mine)) and not set(mine) & set(under), (p["kind"], mine, under)
        assert len(under) == len(set(under)), (p["kind"], under)
        for f in p.get("follow") or []:
            old_part = next(k for k, v in kinds.items() if v == p["kind"])
            # The words written under one of the questions it stood under, with the story they
            # tell, said once.
            assert (f["simple"], f.get("story")) in written[(old_part, L._norm(f["q"]))], f


def test_a_prep_saved_before_is_read_onto_the_page_saying_them_once():
    # The page reads the saved prep as it is: one saved before says them once as it is read,
    # with nothing made again.
    with open(REAL, encoding="utf-8") as fh:
        old = json.load(fh)
    page = L.for_page(old)
    assert page, "the saved prep is fit to show"
    for p in page["parts"]:
        mine, under = _part_follow(page)[p["id"]], _under_questions(page).get(p["id"], [])
        assert not set(mine) & set(under) and len(under) == len(set(under)), (p["kind"], mine, under)
    assert any(set(STORY) <= set(x) for x in _part_follow(page).values()), _part_follow(page)


def test_a_follow_up_written_under_two_questions_of_a_part_is_said_once():
    doc = _fill(L.build(_ctx(stage="Second round", format_="PEI and a HackerRank Python exercise, 60 mins")))
    part = next(p for p in doc["parts"] if len(p["questions"]) >= 2)
    a, b = [q for q in doc["questions"] if q["part"] == part["id"]][:2]
    same = {"who": "manager", "q": "Who else was involved?", "also": [], "simple": "Two planners and a "
            "buyer. I ran the model and they ran the orders.", "detailed": "", "follow": []}
    a["follow"] = a["follow"] + [dict(same)]
    b["follow"] = b["follow"] + [dict(same, simple="Only me at first. Then the planners joined.")]
    done = L.finish(doc)
    assert L._norm("Who else was involved?") in _part_follow(done)[part["id"]]
    assert L._norm("Who else was involved?") not in _under_questions(done)[part["id"]]
    kept = next(f for f in next(p for p in done["parts"] if p["id"] == part["id"])["follow"] if f["q"] == "Who else was involved?")
    assert kept["simple"].startswith("Two planners"), kept


@pytest.fixture(scope="module")
def run():
    yield from browser()


LOOK = ("(() => { const d = document.querySelector('dialog.detail'); return {"
        " parts: [...d.querySelectorAll('.lp-part[data-lpp]')].map((p) => ({id: p.dataset.lpp,"
        "   under: [...p.querySelectorAll('.lp-q[data-lpq] .lp-f-q')].map((x) => x.textContent),"
        "   once: [...p.querySelectorAll(':scope > .lp-group > .lp-part-follow .lp-f-sum .lp-f-q, :scope .lp-part-follow > .lp-kids > .lp-f > .lp-f-sum .lp-f-q')].map((x) => x.textContent),"
        "   head: (p.querySelector('.lp-part-follow .lp-kids-h') || {}).textContent || ''})),"
        " chips: [...d.querySelectorAll('.lp-chips .btn.lp-chip-known')].map((b) => ({name: b.getAttribute('aria-label') || '', title: b.title || '', text: b.textContent})),"
        " key: [...d.querySelectorAll('.lp-glance .lp-glance-part.lp-chip-known')].map((x) => x.textContent)}; })()")


def test_on_the_page_each_part_says_them_once_and_the_marked_chip_says_why(run, tmp_path, vp=None):
    for vp in (PHONE, WIDE):
        got = _go(run, tmp_path, _model(), [dict(OPEN, eval=LOOK)], vp)
        seen = got["after"][0]["eval"]
        for p in seen["parts"]:
            assert not set(p["once"]) & set(p["under"]), p
            assert len(p["under"]) == len(set(p["under"])), p
        told = [p for p in seen["parts"] if p["once"]]
        assert told and all(p["head"] == "After any story here, they may ask" for p in told), seen["parts"]
        # A marked chip says why, to a screen reader and on hover, and the mark is keyed at a
        # glance beside the known question's part.
        assert seen["chips"], seen
        for c in seen["chips"]:
            assert "a question they are known to ask is in this part" in c["name"] and c["text"] in c["name"], c
            assert c["title"] == "A question they are known to ask is in this part", c
        assert seen["key"] and all(k.strip().startswith("Part ") for k in seen["key"]), seen
