"""The interview pack keeps what to say apart from notes, and keeps the person's layout.

From a real repo on 2026-10-20, a consulting screen:
- "Likely questions" repeated raw profile wording marked "rewrite before use" beside
  answers already written, printed an older stock answer the person's own file marks
  "Not for: consulting", and printed a "Customize per company" placeholder, all of it easy
  to read as things to say.
- `check` failed sound spoken openers once a note sat above them, and read notes and
  bullet notes after an answer as part of it.
- A rebuild added its "Checking" line again above the person's own italic one.
- The reaction hook fired on another agent's report and on a document heading, and two
  compatible rules were called a contradiction for sharing a file.
- A screen's map questions came before its standard ones, hooks ended mid-sentence, and
  "Ask them" asked how a team is set up after a fact about what it does.

Every person, employer and answer here is invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import learned  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import prep  # noqa: E402
import voice_check  # noqa: E402
import test_a_referral_process_is_prepared_from_what_was_said as referral  # noqa: E402
from test_a_referral_process_is_prepared_from_what_was_said import (  # noqa: E402
    FIRM, ROLE, TODAY, _doc, _process)

case = referral.case            # the same invented process, its own fixture

ABOUT = "Tell me about yourself."


def _section(text, title):
    return text.split("## %s\n" % title, 1)[1].split("\n## ", 1)[0]


def _block(text, question):
    return _section(text, "Your answers").split("### %s\n" % question, 1)[1].split("\n### ")[0]


def _rewrite(old, new):
    path = os.path.join(outreach.app_folder(FIRM, ROLE), P.LIVING)
    text = open(path, encoding="utf-8").read()
    assert old in text, old[:60]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new, 1))
    return path


# ------------------------------------------------------------ 1. notes, never answers

def test_likely_questions_are_notes_and_never_repeat_a_written_answer(case):
    _process()
    likely = _section(_doc(), "Likely questions").lstrip()
    assert likely.startswith("Notes on each question") and "None of it is words to say" in likely
    assert "Notes, not words to say: %s" % prep.RAW_MARK in likely
    # Written in their own words, the raw wording is never shown beside it again.
    block = _block(_doc(), ABOUT)
    _rewrite("### %s\n%s" % (ABOUT, block),
             "### %s\nI'm an operations analyst in Manchester, and I build the forecasts "
             "that decide where stock goes.\n" % ABOUT)
    P.main(["pack", FIRM, "--today", TODAY, "--write"])
    likely = _section(_doc(), "Likely questions")
    about = likely.split("**Q.** %s" % ABOUT, 1)[1].split("- **Q.**", 1)[0]
    assert prep.RAW_MARK not in about and "Your own answer is under Your answers." in about


def test_a_stock_answer_with_a_fill_in_is_never_printed_as_one(case):
    stock = person.path(P.STORIES_FILE)
    with open(stock, "a", encoding="utf-8") as fh:
        fh.write('\n### "What is your notice period, and when could you start?"\n'
                 "> One month, [Customize per company] for the start date.\n")
    _process()
    text = _doc()
    block = _block(text, "What is your notice period, and when could you start?")
    assert "One month," not in block and 'still has a fill-in ("[Customize per company]")' in block
    assert "One month," not in _section(text, "Likely questions")


# ------------------------------------------------------------ 2. the check reads only what is said

def test_a_spoken_opener_passes_and_notes_are_never_checked(case, capsys):
    _process()
    block = _block(_doc(), ABOUT)
    _rewrite("### %s\n%s" % (ABOUT, block),
             "### %s\n*They're checking the thread through my moves.*\n"
             "Two things. First, the scale of the problems. Second, I want to own a forecast "
             "end to end.\n\nNotes:\n- mention the depot work\n- keep it under a minute\n"
             % ABOUT)
    capsys.readouterr()
    P.main(["check", FIRM])
    out = capsys.readouterr().out
    assert "%s: not in the first person" % ABOUT not in out
    assert "%s: written as bullet points" % ABOUT not in out


def test_the_first_person_can_come_in_the_third_sentence():
    assert voice_check.spoken_findings("Two things. First, the scale of the data. Second, I "
                                       "want to own the model end to end.") == []
    assert voice_check.spoken_findings("Senior operations analyst with seven years in "
                                       "logistics and a record of cutting forecast error.")


def test_a_note_that_says_why_is_kept_apart_from_the_answer():
    body = ["*They're checking the moves.*", "I moved for bigger problems each time.", "",
            "Notes:", "- the depot story", "Note: two minutes at most"]
    assert P.spoken(body) == ["I moved for bigger problems each time.", ""]


# ------------------------------------------------------------ 3. a rebuild keeps their layout

def test_a_rebuild_keeps_their_own_checking_line_and_their_paragraphs(case):
    _process()
    q = "Why are you looking?"
    block = _block(_doc(), q)
    checking = [ln for ln in block.splitlines() if ln.startswith(P.INTENT_MARK)]
    assert checking
    _rewrite("### %s\n%s" % (q, block),
             "### %s\n*Checking: whether the reasons hold. They want to hear: what pulls you, "
             "not what pushes you.*\nI want one planning problem I own end to end.\n\n"
             "That is what the next role has to give me.\n" % q)
    P.main(["pack", FIRM, "--today", TODAY, "--write"])
    block = _block(_doc(), q)
    assert P.INTENT_MARK not in block
    assert "own end to end.\n\nThat is what" in block


# ------------------------------------------------------------ 4. the hook and contradictions

def test_the_hook_ignores_an_agents_report_and_a_documents_headings():
    assert learned.reaction("The researcher found the two careers pages are identical.") == ""
    assert learned.reaction("**Do not say**\n- relocating") == ""
    assert learned.reaction("## Do not say\nrelocating") == ""
    assert learned.reaction("[Subagent hand-back] these read like a template") == ""
    assert learned.reaction("these are all identical in structure")
    assert learned.reaction("don't say relocating")


def test_rules_that_share_a_file_are_not_a_contradiction(monkeypatch):
    rows = [{"date": "2026-10-01", "rule": "keep each answer under a minute", "said": "x",
             "applied_to": ["profile/07-interview-prep.md"], "status": "active"}]
    entry = {"rule": "open every answer with the point", "said": "y",
             "applied_to": ["profile/07-interview-prep.md"]}
    monkeypatch.setattr(learned, "profile_never_phrases", lambda text=None: [])
    assert learned.conflicts(entry, rows) == []
    rows[0]["applied_to"] = entry["applied_to"] = ["profile/CLAUDE.md"]
    assert learned.conflicts(entry, rows) == []
    rows[0]["applied_to"] = entry["applied_to"] = ["networking.py OPENER"]
    assert [why for _n, _r, why in learned.conflicts(entry, rows)] == \
        ["both set networking.py OPENER"]


# ------------------------------------------------------------ 5. the generated content

def test_a_screen_asks_its_standard_questions_before_the_map(case):
    _process()
    ctx = P.gather(FIRM, ROLE, stage="Recruiter screen", today=TODAY,
                   story_map={"How would you rebuild our demand forecast?": ""})
    first = [q["question"] for q in P.likely_questions(ctx)[:3]]
    assert first == [q.format(company=FIRM) for q in P.STAGE_QUESTIONS["screen"][:3]]


def test_a_hook_is_a_whole_sentence_never_cut_mid_word():
    long = ("- The firm opened a planning office in Leeds in 2025, which now runs demand "
            "forecasting for grocery and convenience clients across the north of England and "
            "is hiring analysts to build its depot-level models, with a second office planned "
            "for 2027. It also runs a graduate scheme.")
    got = P._hook_text(long)
    assert not got.startswith("-") and "graduate scheme" not in got
    assert got.endswith("...") and got[:-3].rstrip()[-1].isalnum() or got.endswith("England...")
    assert P._hook_text("- The firm opened a planning office in Leeds in 2025.") == \
        "The firm opened a planning office in Leeds in 2025"


def test_ask_them_asks_about_set_up_only_after_a_fact_about_set_up():
    src = {"company": "Calder & Rook Consulting", "fetched_date": "2026-10-20"}
    work = prep.questions_for_them(dict(src, team="The analytics team builds demand forecasts "
                                                  "for retail clients."), "")
    shape = prep.questions_for_them(dict(src, team="The analytics team reports to the COO and "
                                                   "is a team of twelve."), "")
    assert work and work[0]["question"].endswith(prep.TEAM_WORK_TAIL)
    assert shape and shape[0]["question"].endswith("Is that still how the team is set up?")
