"""The pack names where the resume they hold invites a push, and the follow-up behind it.

The interviewer reads the resume before the call. A stay of a few months, a gap between
jobs and a title the role may doubt each draw a question, then a second one behind it,
and the pack said only that every claim on the paper must be defensible in depth. Now
What the paper says lists each one, the likely question, the follow-up, and the honest
framing: the person's own stock answer, what the profile holds, or a line saying their
reasons are asked once and never drafted.

Every employer, title and answer here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import test_interview_pack as base  # noqa: E402

app = base.app

JOBS = [
    {"company": "Kestrel Mutual", "title": "Data Analyst", "dates": "Dec 2025 - Present",
     "evidence": []},
    {"company": "Larkspur Retail", "title": "Graduate Analyst", "dates": "Jan 2024 - Jul 2024",
     "evidence": []},
    {"company": "Oakmere Foods", "title": "Supply Chain Data Analyst",
     "dates": "Sep 2020 - Feb 2023", "evidence": []},
]


def _ctx(role="Senior Data Scientist", jobs=JOBS, answers=()):
    ctx = base._ctx()
    ctx["role"] = role
    ctx["facts"] = dict(ctx["facts"], employers=list(jobs),
                        strengths=["Led the first model-validation standard the team adopted"])
    ctx["answers"] = list(answers)
    return ctx


def _found(ctx):
    return {m["what"]: m for m in P.landmines(ctx)}


def test_a_short_stay_is_named_with_the_question_and_the_one_behind_it(app):
    found = _found(_ctx())
    now = found["A short stay: Data Analyst, Kestrel Mutual (Dec 2025 - Present)"]
    assert now["ask"] == "Why are you looking to leave Kestrel Mutual after 3 months?"
    assert now["then"] == "How do we know you would stay longer with us?"
    past = found["A short stay: Graduate Analyst, Larkspur Retail (Jan 2024 - Jul 2024)"]
    assert past["ask"] == "Why did you leave Larkspur Retail after 7 months?"
    assert past["then"] == "Would you leave us as quickly?"
    # A title that says the post had a set length is said first; the reasons are theirs.
    assert past["framing"][0].startswith("Your title there was Graduate Analyst: if the post had a "
                                         "set length")
    assert "Claude asks you once, in your words" in past["framing"][1]
    assert "Never drafted from the dates." in past["framing"][1]


def test_their_own_stock_answer_is_the_framing_when_they_have_one(app):
    kept = {"question": "Why did you leave Larkspur Retail?", "alternatives": [],
            "use_for": [], "answer": "It was a six-month placement, and I said so when I took it.",
            "confirm": False, "source": "profile/07-interview-prep.md", "fill_in": "",
            "suits": (), "not_for": ()}
    m = _found(_ctx(answers=[kept]))[
        "A short stay: Graduate Analyst, Larkspur Retail (Jan 2024 - Jul 2024)"]
    assert ("Prepared: It was a six-month placement, and I said so when I took it. "
            "(source: profile/07-interview-prep.md)") in m["framing"]


def test_a_gap_between_jobs_is_named_with_its_length(app):
    found = _found(_ctx())
    gap = found["16 months between jobs: Larkspur Retail ended Jul 2024, Kestrel Mutual started "
                "Dec 2025"]
    assert gap["ask"] == "What were you doing between Larkspur Retail and Kestrel Mutual?"
    assert gap["then"] == "What did you keep up or learn in that time?"
    assert "never drafted" in gap["framing"][0]
    assert "10 months between jobs: Oakmere Foods ended Feb 2023, Larkspur Retail started Jan 2024" \
        in found
    # A month or two between jobs is a move, not a gap.
    near = [dict(JOBS[0], dates="Mar 2023 - Present"), dict(JOBS[2])]
    assert not any("between jobs" in w for w in _found(_ctx(jobs=near)))


def test_a_title_the_role_may_doubt_is_named(app):
    found = _found(_ctx())
    up = found["The role is Senior Data Scientist; your latest title is Data Analyst"]
    assert up["ask"] == ("This is a more senior role than your current one. What have you done at "
                         "that level?")
    assert up["framing"][0].startswith("From your profile: Led the first model-validation standard")
    assert up["framing"][-1].endswith("never a title you did not hold.")
    other = found["Your title says analyst; this role is scientist"]
    assert other["ask"] == "Your title is Data Analyst. What in your work is what a scientist here does?"
    assert other["then"] == "What would you need to learn first?"
    down = _found(_ctx(role="Graduate Analyst",
                       jobs=[dict(JOBS[0], title="Senior Data Analyst", dates="Mar 2023 - Present")]))
    assert down["The role is Graduate Analyst; your latest title is Senior Data Analyst"]["ask"] == (
        "Your title is Senior Data Analyst and this role is Graduate Analyst. Why step back?")


def test_the_pack_prints_them_under_what_the_paper_says(app):
    paper = base._section(P.pack_markdown(_ctx(), never_say=[]), "What the paper says")
    start = paper.index("- Where they will push, from the CV they hold (each with the follow-up "
                        "behind it):")
    assert paper[start + 1] == ("  - A short stay: Data Analyst, Kestrel Mutual (Dec 2025 - "
                                "Present). They ask: \"Why are you looking to leave Kestrel Mutual "
                                "after 3 months?\" Then: \"How do we know you would stay longer "
                                "with us?\"")
    assert paper[start + 2].startswith("    - ")


def test_a_steady_record_has_nothing_to_push_on(app):
    # The example person: years at each employer, no gap, an analyst applying as an analyst.
    assert P.landmines(base._ctx()) == []
    assert not any("Where they will push" in ln for ln in base._section(base._pack(),
                                                                        "What the paper says"))
