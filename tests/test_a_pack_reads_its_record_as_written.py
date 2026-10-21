"""The interview pack matches, labels and names what it reads as it was written.

From a real repo on 2026-10-21, a bank's technical round and a consulting firm's:
- "What would you do differently now?" matched the stock answer for "Why now?" at 0.5, on
  the word "now", and took the answer written for leaving a consultancy, at a bank. The
  question also lost the story the last build had given it: the session's map was kept
  nowhere, so a rebuild without it had none.
- A consulting firm with no sector on its row and no research was no kind of employer, so
  its pack offered the answer the person marked "Not for: consulting", although their own
  catalogue (employers.py) calls it professional services.
- A neighbourhood still marked [CONFIRM: ...] was printed as where they live.
- A rebuilt pack listed outcome.md's own advice ("Recommendation: ...", "Likely shape ...,
  from reported processes") under "What you were told about this round".
- A rebuild with no --stage turned "Round 2 (technical)" into "Round 2", and kept both in
  the stages line.

Every person, employer and answer here is invented; the candidate is the example person.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import outreach  # noqa: E402
import sector  # noqa: E402
import test_a_referral_process_is_prepared_from_what_was_said as referral  # noqa: E402
from test_a_referral_process_is_prepared_from_what_was_said import (  # noqa: E402
    FIRM, ROLE, TODAY, _doc, _process)

case = referral.case            # the same invented process, its own fixture

LEAVING = {"question": "Why are you leaving Brindle & Hart Logistics?", "answer": "Depth over a "
           "rotating client portfolio.", "alternatives": ["Why are you leaving Brindle & Hart "
           "Logistics?", "Why are you looking?"], "use_for": ["why now"], "suits": (),
           "not_for": ("consulting",)}
STORY = "The forecast that freed safety stock"
DIFFERENTLY = "What would you do differently now?"


def _outcome():
    return os.path.join(outreach.app_folder(FIRM, ROLE), "outcome.md")


def _screen_held():
    path = _outcome()
    text = open(path, encoding="utf-8").read()
    assert "- [ ] Recruiter screen" in text, text
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace("- [ ] Recruiter screen", "- [x] Recruiter screen", 1))


def _stages():
    return P._STAGES_MARK.search(_doc()).group(1)


# ------------------------------------------------------------ 1. a word for when is no topic

def test_a_question_about_now_is_not_matched_to_why_now_on_that_word():
    assert P.similar(DIFFERENTLY, "Why now?") == 0.0
    assert P._answer_for(DIFFERENTLY, [LEAVING], ["Brindle & Hart Logistics"], "Oakmere Bank") \
        is None
    # "Why now?" itself is still the leaving question, by what it means.
    assert P._answer_for("Why now?", [LEAVING], ["Brindle & Hart Logistics"], "Oakmere Bank") \
        is LEAVING


def test_a_rebuild_keeps_the_story_the_last_build_gave_a_question(case):
    _process()
    mapped = case / "map.json"
    mapped.write_text(json.dumps({DIFFERENTLY: STORY}), encoding="utf-8")
    assert P.main(["pack", FIRM, "--stage", "Technical interview", "--today", TODAY, "--write",
                   "--map", str(mapped)]) == 0
    assert "%s -> story: %s" % (DIFFERENTLY, STORY) in _doc()
    # Rebuilt with no map, it keeps it.
    assert P.main(["pack", FIRM, "--stage", "Technical interview", "--today", TODAY,
                   "--write"]) == 0
    assert "%s -> story: %s" % (DIFFERENTLY, STORY) in _doc()
    # A story since taken out of the file is passed over quietly, never named as missing.
    ctx = P.gather(FIRM, ROLE, stage="Technical interview", today=TODAY)
    ctx["stories"] = [s for s in ctx["stories"] if s["title"] != STORY]
    plan = P.answer_for({"question": DIFFERENTLY}, ctx)
    assert "story: %s" % STORY not in plan["short"]
    assert not any("not a story" in ln for ln in plan["lines"])


# ------------------------------------------------------------ 2. the person's own catalogue

def test_an_employer_the_catalogue_calls_professional_services_is_a_consulting_one(
        case, monkeypatch):
    monkeypatch.setattr(sector, "NOT_TECH", {"orrin & vale": "professional services"})
    ctx = {"company": "Orrin & Vale Analytics", "row": {"sector": ""}, "research": {}}
    assert sector.kind("Orrin & Vale Analytics") == "professional services"
    assert P.employer_type(ctx) == "consulting"
    assert "Not for: line names consulting" in P.against_employer(LEAVING, ctx)
    # The row's own sector still comes first, and a name nothing holds is no kind at all.
    assert P.employer_type(dict(ctx, row={"sector": "Banking"})) == "bank"
    assert sector.kind("Oakmere Foods") == ""


# ------------------------------------------------------------ 3. an unconfirmed fact is not held

def test_a_neighbourhood_still_to_confirm_is_never_where_they_live(monkeypatch):
    monkeypatch.setitem(P._PERSON, "identity.area",
                        lambda: "[CONFIRM: Which neighbourhood should a pack treat as home?]")
    monkeypatch.setitem(P._PERSON, "identity.location", lambda: "Leeds, UK")
    assert P.home_place() == "Leeds, UK"
    monkeypatch.setitem(P._PERSON, "identity.location", lambda: "[CONFIRM: which city?]")
    assert P.home_place() == ""


# ------------------------------------------------------------ 4. advice is not what was said

@pytest.mark.parametrize("line,told", [
    ("Recommendation: round 2 virtual, round 3 in person.", False),
    ("Likely shape of the two rounds, from reported processes: round 2 a technical interview.",
     False),
    ("The recruiter said round 2 is 45 minutes on Teams, and likely with the team lead.", True),
    ("Format: virtual, 45 minutes.", True),
])
def test_advice_and_guesses_are_not_what_they_were_told(line, told):
    assert P._was_told(line) is told


def test_the_format_section_quotes_only_what_was_said_about_the_round(case):
    _process()
    with open(_outcome(), "a", encoding="utf-8") as fh:
        fh.write("\n## Round 2 (technical)\n\n"
                 "- **Recommendation: take round 2 virtual.** A coding round belongs on your "
                 "own machine.\n"
                 "- Likely shape, from reported processes: a 60 minute technical interview.\n"
                 "- The recruiter said it is 45 minutes on Teams with the team lead.\n")
    told = [ln for ln in P.format_lines(P.gather(FIRM, ROLE, stage="Round 2 (technical)",
                                                 today=TODAY))
            if ln.startswith("- What you were told about this round")]
    assert len(told) == 1 and "45 minutes on Teams" in told[0], told


@pytest.mark.parametrize("line,ours", [
    ("The recruiter said round 2 is 45 minutes on Teams.", True),
    ("Our recruiter, Tamsin, said it is a 45 minute technical round.", True),
    ("The technical interview is a 60 minute case with two partners, Tamsin said.", True),
    ("Recruiter screen booked: virtual, 30 minutes.", False),
])
def test_a_line_is_filed_by_what_was_said_not_by_who_said_it(line, ours):
    ctx = {"stage": "Technical interview", "step": "technical"}
    assert P._for_this_stage(ctx, "Notes", line) is ours


# ------------------------------------------------------------ 5. one round keeps its name

def test_a_rebuild_with_no_stage_keeps_the_rounds_fuller_name(case):
    _process()
    assert P.main(["pack", FIRM, "--stage", "Round 2 (technical)", "--today", TODAY,
                   "--write"]) == 0
    _screen_held()
    assert P.main(["pack", FIRM, "--today", TODAY, "--write"]) == 0
    assert _stages() == "Recruiter screen; Round 2 (technical)"
    assert "Next: Round 2 (technical)." in _doc()


def test_a_stages_line_an_earlier_rebuild_doubled_is_put_right(case):
    _process()
    assert P.main(["pack", FIRM, "--stage", "Round 2 (technical)", "--today", TODAY,
                   "--write"]) == 0
    path = os.path.join(outreach.app_folder(FIRM, ROLE), P.LIVING)
    text = open(path, encoding="utf-8").read()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace("<!-- stages: Recruiter screen; Round 2 (technical) -->",
                              "<!-- stages: Recruiter screen; Round 2 (technical); Round 2 -->"))
    _screen_held()
    assert P.main(["pack", FIRM, "--today", TODAY, "--write"]) == 0
    assert _stages() == "Recruiter screen; Round 2 (technical)"


@pytest.mark.parametrize("a,b,same", [
    ("Round 2 (technical)", "Round 2", True),
    ("Round 2", "round 2", True),
    ("Round 2", "Round 20", False),
    ("Recruiter screen", "Round 2", False),
])
def test_one_round_by_two_names_is_one_round(a, b, same):
    assert P._same_round(a, b) is same
