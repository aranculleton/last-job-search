"""Interview prep drafts what the person asks for, and the call prep and the interview pack
read one set of rules.

From an audit of both documents on 2026-10-20:
- rules in the commands, the guide and the code still refused a draft the person asked
  for (an example, an anecdote, a metric, their reasons), after the maintainer's decision
  that prep must draft it, marked, and never refuse;
- the pack's check failed a requested draft, so it could not be shown, while the call
  prep's check passed one and read its mark as words to say;
- a gap from the fit score was named by its reason ("big-data engineering is not held"),
  and a skill the person said yes to was both claimed and never to be claimed;
- "Why Northwind Co.?" was no question at all, the earliest of four employers fell out of
  "the moves", and "declined: no referral" registered a referral;
- /prep said nothing for a booked recruiter screen with no tracker row, read gaps from the
  tracker's notes, answered from a builder of its own (no "Why are you looking?", the raw
  sponsorship line), read team research one way to the pack's other, and the recruiter was
  asked about the next stage twice;
- docs disagreed with the code and each other, and dead code stayed.

Every person and employer here is invented; the candidate is the example person.
"""
from __future__ import annotations

import argparse
import csv
import inspect
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import bridges  # noqa: E402
import check_numbers  # noqa: E402
import interview_pack as P  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import prep  # noqa: E402
import profile_facts  # noqa: E402
import record_drafts  # noqa: E402
import schema  # noqa: E402
import untrusted  # noqa: E402

TODAY = "2026-03-11"
FIRM, ROLE = "Fernhill Freight", "Demand Planning Analyst"
ROW = {"date": "2026-02-20", "company": FIRM, "role": ROLE, "status": "interview",
       "channel": "company site", "fit_rating": "78",
       "cv_file": "cv/Morgan_Ellis_Resume_Fernhill.tex",
       "cover_letter_file": "cover_letters/Morgan_Ellis_Cover_Letter_Fernhill.tex"}
OUTCOME = ("# Outcome\n\n## Interview stages reached\n- [ ] Phone screen (scheduled 2026-03-14, "
           "with Dana Okafor, Talent Partner)\n")
HEAD = {"contact_id": "fernhill_freight_example", "name": "Shirin Example", "company": FIRM,
        "title": "Head of Planning", "route": "referral", "referred_by": "Hal Okonedo",
        "status": "call_booked", "next_action": "Technical interview",
        "next_action_due": "2026-03-14"}
RECRUITER = {"contact_id": "fernhill_freight_okafor", "name": "Dana Okafor", "company": FIRM,
             "title": "Talent Partner", "route": "referral", "status": "call_booked",
             "next_action": "Recruiter screen", "next_action_due": "2026-03-12"}
PEER = {"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
        "company": "Larkspur Retail", "title": "Data Analyst", "route": "alumni",
        "status": "call_booked"}
SAID = ("I set up a nightly job that reloaded the stock tables, and I added a check that "
        "stopped it when a load came in short.")
NO_NEVER = lambda text: []  # noqa: E731


@pytest.fixture
def st(tmp_path, monkeypatch):
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof,
                    ignore=shutil.ignore_patterns("__pycache__", "state"))
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv(person.ENV, str(prof))
    monkeypatch.setenv(person.STATE_ENV, str(state_dir))
    person.reset()
    yield state_dir
    monkeypatch.undo()
    person.reset()


def _application(state_dir, posting="Demand Planning Analyst. You will own the weekly forecast.",
                 draft=None, contacts=()):
    with open(state_dir / "job_search_tracker.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=record_drafts.HEADER)
        w.writeheader()
        w.writerow({k: ROW.get(k, "") for k in record_drafts.HEADER})
    with open(state_dir / "network_contacts.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=schema.CONTACT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for c in contacts:
            w.writerow(c)
    folder = outreach.app_folder(FIRM, ROLE)
    os.makedirs(folder, exist_ok=True)
    files = {"job_posting.md": "# %s - %s\n\n%s" % (ROLE, FIRM, untrusted.fence(posting)),
             "outcome.md": OUTCOME}
    if draft is not None:
        files["draft.json"] = json.dumps([dict({"company": FIRM, "role": ROLE}, **draft)])
    for name, body in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write(body)
    return folder


def _gather(stage="Technical interview", with_=""):
    return P.gather(FIRM, today=TODAY, contacts=[], threads=[], stage=stage, with_=with_)


def _section(text, title):
    return text.split("## %s\n" % title, 1)[1].split("\n## ", 1)[0]


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return " ".join(fh.read().split())


INTERVIEW_MD = (".claude", "commands", "interview.md")
PREP_MD = (".claude", "commands", "prep.md")
GUIDE = (".claude", "skills", "job-application-assistant", "07-interview-prep.md")


# ------------------------------------------------------------ 1. a requested draft is allowed

def test_the_commands_and_the_guide_never_forbid_a_draft_they_asked_for():
    cmd, guide = _read(*INTERVIEW_MD), _read(*GUIDE)
    assert ("Grounded strictly in `01-candidate-profile.md` and `profile/07-interview-prep.md`, "
            "unless they ask for a draft (rule 2)") in cmd
    assert "asked, never written for them" not in cmd and "never written for them" not in cmd
    assert "If they ask you to draft their reasons instead, draft them, marked (rule 2)" in cmd
    assert "not embellished - unless they ask for a draft (rule 2)" in cmd
    assert "`check_numbers` skips any answer carrying `DRAFT_MARK`" in cmd
    assert "coaches claims beyond them" not in cmd
    assert "coaches no claim beyond them unless they ask for a draft (rule 2)" in cmd
    assert "Never claim the skill." not in guide
    assert "Unasked, never claim the skill; asked for an example of using it, draft one" in guide
    assert "except a draft the person asked for, which is marked" in guide


def test_the_packs_own_lines_offer_the_draft_and_never_refuse_it(st, monkeypatch):
    _application(st, posting="Demand Planning Analyst. Experience with PySpark is essential.")
    ctx = _gather()
    donts = P.do_not_say(ctx, never_say=[])
    assert "- Never claim PySpark: big-data engineering is not held. Ask for an example and " \
        "Claude drafts one, marked for you to confirm (source: tools/bridges.py)" in donts
    assert donts[-1] == ("- No claim in the room beyond the paper they read, except a draft you "
                         "asked for and have made true.")
    call = P.call_ctx(PEER, "", profile_facts.build())

    def lines(**item):
        return " ".join(P.answer_for(dict({"why": "", "source": "x"}, **item), call)["lines"])

    assert "never claim it" not in lines(question="What is your experience with Kafka?",
                                         gap=True, framing="")
    assert "Asked for an example of using it, Claude drafts one" in lines(
        question="What is your experience with Kafka?", gap=True, framing="")
    assert "never a story you do not have" not in lines(
        question="Tell me about your experience with SAP.", req=True, evidence="")
    assert "Asked for an example, Claude drafts one" in lines(
        question="Tell me about a time you led something.")
    assert "facts only" not in lines(question="How would you survey a zebra crossing?")
    monkeypatch.setattr(P, "hard_answers", lambda path=None: [])
    asked = P.answer_for({"question": "Why are you looking?", "why": "", "source": ""},
                         P.call_ctx(PEER, "", profile_facts.build()))
    assert asked["ask"].startswith(P.ASK_MARK) and "If they ask for a draft instead" in asked["ask"]
    # Small talk: no invented memory unasked, an anecdote drafted when asked.
    who = {"identity.moved": "just arrived", "identity.area": "Ancoats, Manchester"}
    monkeypatch.setattr(P, "_person", lambda dotted: who.get(dotted, ""))
    talk = " ".join(P.small_talk_lines(ctx))
    assert "ask for an anecdote and Claude drafts one" in talk
    assert "Asked for an anecdote, Claude drafts one" in " ".join(P.where_lines.__doc__.split())


def test_the_call_prep_offers_the_draft_too():
    fit = prep.fit_assessment({}, {"gaps": [{"gap": "Kafka", "framing": ""}]})
    assert any("asked, Claude drafts one, marked for you to confirm" in ln for ln in fit)
    doc = prep.prep_markdown(PEER, {}, None, {}, [], TODAY, never_say=NO_NEVER)
    fit_section = _section(doc, "Fit, honestly")
    # The words a person's own test pins stay, with the draft offered beside them.
    assert "Do not improvise a fit story on the call" in fit_section
    assert "Claude drafts one, marked for you to confirm" in fit_section


def test_check_numbers_skips_an_answer_marked_as_a_draft(tmp_path):
    doc = ("## Your answers\n\n### Tell me about a time you saved money.\n%s\n"
           "I cut 23 hours a week from the stock report.\n\n### And another?\n"
           "I cut 37 hours a week from a second report.\n\n- **Q.** One more?\n"
           "  **A.** %s\n    I saved 41 hours.\n- **Q.** Last?\n  **A.** I saved 59 hours.\n"
           % (P.DRAFT_MARK, P.DRAFT_MARK))
    kept = check_numbers.without_drafts(doc)
    assert "23 hours" not in kept and "41 hours" not in kept
    assert "37 hours" in kept and "59 hours" in kept
    path = tmp_path / "interview_prep.md"
    path.write_text(doc, encoding="utf-8")
    run = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_numbers.py"),
                          str(path)], capture_output=True, text=True)
    assert "'37 hours'" in run.stdout and "'59 hours'" in run.stdout
    assert "'23 hours'" not in run.stdout and "'41 hours'" not in run.stdout
    # Never outside markdown: a draft has no business in a resume or a letter.
    tex = tmp_path / "resume.tex"
    tex.write_text(doc, encoding="utf-8")
    run = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_numbers.py"),
                          str(tex)], capture_output=True, text=True)
    assert "'23 hours'" in run.stdout


# ------------------------------------------------------------ 2. a draft is its own category

DRAFTED = ("- **Q.** Tell me about a time you used Airflow.\n  **A.** %s\n    %s\n"
           % (P.DRAFT_MARK, SAID))


def test_the_call_preps_check_lists_a_draft_and_never_says_its_mark():
    found = prep.check_answers(DRAFTED)
    assert found == [(prep.DRAFT, "Tell me about a time you used Airflow.")]
    assert prep.failures(found) == []
    # The mark is never read as words to say: a draft that is bullets still fails as bullets.
    bullets = DRAFTED.replace("    " + SAID, "    - set up a nightly job\n    - added a check")
    assert prep.answers_in(bullets)[0][1].startswith(P.DRAFT_MARK)
    assert prep.spoken_lines([P.DRAFT_MARK, SAID]) == [SAID]
    assert P.DRAFT_MARK is prep.DRAFT_MARK and P.drafted is prep.drafted


def test_the_call_preps_check_exits_clean_on_a_draft_and_a_rebuild_keeps_it(tmp_path, capsys):
    facts = {"summary": "Operations analyst who builds forecasts.", "narrative": True}
    path = prep.write_prep(PEER, profile_facts=facts, today=TODAY, root=str(tmp_path))
    text = open(path, encoding="utf-8").read()
    raw = "%s %s" % (prep.RAW_MARK, facts["summary"])
    text = text.replace(raw, "%s\n    %s" % (P.DRAFT_MARK, SAID))
    open(path, "w", encoding="utf-8").write(text)
    again = prep.write_prep(PEER, profile_facts=facts, today=TODAY, root=str(tmp_path))
    rebuilt = open(again, encoding="utf-8").read()
    # The mark stays a line of its own: collapsed into the answer, the answer went with it.
    assert "**A.** %s\n    %s" % (P.DRAFT_MARK, SAID) in rebuilt
    assert (prep.DRAFT, "Tell me about yourself.") in prep.check_answers(rebuilt)
    assert not any(q == "Tell me about yourself." for q, _w in prep.check_answers(rebuilt))


def test_the_packs_check_shows_a_draft_as_one_to_confirm(st, capsys):
    _application(st)
    ctx = _gather()
    path = P.write_pack(ctx, never_say=[])
    text = open(path, encoding="utf-8").read()
    q = P.likely_questions(ctx)[0]["question"]
    head = "### %s\n" % q
    i = text.index(head) + len(head)
    j = text.index("\n### ", i)
    text = text[:i] + "%s\n%s\n" % (P.DRAFT_MARK, SAID) + text[j:]
    open(path, "w", encoding="utf-8").write(text)
    found = P.check(path)
    assert (P.DRAFT, q) in found and (P.DRAFT, q) not in P.failures(found)
    assert not any(a == q for a, _w in found)
    capsys.readouterr()
    P._keep(dict(ctx, living=text))
    out = capsys.readouterr().out
    assert "drafts they asked for, to show them as drafts: 1" in out and q in out


# ------------------------------------------------------------ 3 and 4. gaps, named and consented

def test_a_gap_from_the_score_is_named_by_what_the_posting_wrote(st):
    assert [(g.asked, g.note) for g in bridges.gaps("Experience with PySpark is essential.")] \
        == [("PySpark", "big-data engineering is not held")]
    _application(st, posting="Demand Planning Analyst. Experience with PySpark is essential.")
    questions = [q["question"] for q in P.likely_questions(_gather())]
    assert "What is your experience with PySpark?" in questions
    assert not any("is not held?" in q for q in questions)


def test_a_skill_they_said_yes_to_is_never_also_a_gap(st):
    _application(st, posting="Demand Planning Analyst. Experience with PySpark is essential.",
                 draft={"consented_skills": ["PySpark"], "requirement_map": []})
    ctx = _gather()
    assert not ctx["gaps_hard"] and not ctx["facts"].get("gaps")
    assert any("You said yes to claiming PySpark" in ln for ln in P.gap_lines(ctx))
    assert not any("PySpark" in ln for ln in P.do_not_say(ctx, never_say=[]))
    assert not any("PySpark" in q["question"] for q in P.likely_questions(ctx))


# ------------------------------------------------------------ 5. "Why <employer>?" by any name

@pytest.mark.parametrize("company", ["Northwind Co.", "Larkspur (UK)", "Fernhill Freight"])
def test_why_the_employer_is_read_whatever_its_name_ends_in(company):
    q = "Why %s?" % company
    assert P.motive(q, company) == "why_us"
    assert P.intent(q, company) == P.intent("Why this company?", company) != ("", "")


# ------------------------------------------------------------ 6. every employer in the moves

def test_the_moves_name_every_employer_including_the_earliest(tmp_path):
    src = open(os.path.join(ROOT, "profile.example", "01-candidate-profile.md"),
               encoding="utf-8").read()
    four = src.replace("## Education", "### Graduate Analyst - Kestrel Mutual (Jul 2018 - "
                       "Aug 2019), Leeds\n- Built the weekly sales report for twelve stores\n\n"
                       "## Education", 1)
    path = tmp_path / "four.md"
    path.write_text(four, encoding="utf-8")
    facts = profile_facts.build(path=str(path))
    assert [e["company"] for e in facts["employers"]][-1] == "Kestrel Mutual"
    assert len(facts["employers"]) == 4
    ask = P.motive_ask("moves", {"facts": facts, "company": FIRM})
    assert ask.startswith("What made you take each move (Kestrel Mutual, then ")


# ------------------------------------------------------------ 7. a declined referral

def test_a_declined_referral_never_registers_a_referral(st):
    _application(st)
    lead = {"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
            "company": "Larkspur Retail", "title": "Data Lead", "route": "alumni_employer",
            "status": "in_conversation", "outcome": "declined: no referral, hiring freeze"}
    row, _folder, _added = P.register_process("Larkspur Retail", lead["contact_id"],
                                              "Data Analyst", contacts=[lead], today=TODAY)
    assert row["channel"] == "contact"
    lead2 = dict(lead, contact_id="kestrel_mutual_castellan", company="Kestrel Mutual",
                 outcome="referral made, passed to the hiring manager")
    row, _folder, _added = P.register_process("Kestrel Mutual", lead2["contact_id"],
                                              "Data Analyst", contacts=[lead2], today=TODAY)
    assert row["channel"] == "referral"


# ------------------------------------------------------------ 8. a booked screen with no row

def test_a_booked_recruiter_screen_with_no_row_is_sent_to_interview():
    doc = prep.prep_markdown(RECRUITER, {}, None, {"summary": "x y z."}, [], TODAY,
                             never_say=NO_NEVER)
    assert "prepare it with /interview %s" % FIRM in doc
    assert ('python3 tools/interview_pack.py process "%s" --contact fernhill_freight_okafor '
            '--role "<the role, as they named it>" --stage "Recruiter screen" --date 2026-03-12'
            % FIRM) in doc
    for who in (PEER, dict(RECRUITER, status="awaiting_reply")):
        assert "/interview" not in prep.prep_markdown(who, {}, None, {}, [], TODAY,
                                                      never_say=NO_NEVER)


# ------------------------------------------------------------ 9. one posting reader

def test_the_call_prep_names_the_gaps_the_pack_names(st):
    _application(st, posting="Demand Planning Analyst. SAP experience is essential.")
    assert [g["gap"] for g in _gather()["facts"].get("gaps", [])] == ["SAP"]
    threads = st / "threads.csv"
    threads.write_text("", encoding="utf-8")
    a = argparse.Namespace(profile_facts="", root=str(st), threads=str(threads), today=TODAY)
    peer = dict(HEAD, route="cold", referred_by="", next_action="")
    path = prep._write_one(peer, [dict(ROW, notes="Spoke to the team about the role.")], a)
    fit = _section(open(path, encoding="utf-8").read(), "Fit, honestly")
    assert "- Gap: SAP. Say:" in fit
    assert profile_facts.posting_in(outreach.app_folder(FIRM, ROLE)).endswith(
        "SAP experience is essential.")


# ------------------------------------------------------------ 10. one set of answers

def test_the_call_prep_answers_from_the_packs_functions(monkeypatch):
    facts = profile_facts.build()
    qs = {q["question"]: q for q in prep.likely_questions(PEER, "", facts)}
    stock = {a["question"]: a for a in P.hard_answers()}
    # The person's own stock answers, never the profile's raw line.
    assert qs["Why are you looking?"]["answer"] == stock["Why are you looking?"]["answer"]
    assert qs["Do you need sponsorship?"]["answer"] == stock["Do you need sponsorship?"]["answer"]
    assert qs["Do you need sponsorship?"]["answer"] != facts["work_authorization"]
    # With no stock answer: their reason is asked first, and work authorization is this
    # reader's own register.
    monkeypatch.setattr(P, "hard_answers", lambda path=None: [])
    qs = {q["question"]: q for q in prep.likely_questions(RECRUITER, "", facts)}
    assert qs["Why are you looking?"]["answer"].startswith(prep.ASK_MARK)
    assert qs["Do you need sponsorship?"]["answer"] == prep.work_auth_for(RECRUITER)
    assert list(qs)[:2] == ["Do you need sponsorship?", "Why are you looking?"]
    doc = "- **Q.** Why are you looking?\n  **A.** %s (source: x)\n" % qs[
        "Why are you looking?"]["answer"]
    assert prep.check_answers(doc) == [(prep.ASK, "Why are you looking?")]
    assert prep.likely_questions(PEER, "", {}) == []


# ------------------------------------------------------------ 11. one reader of team research

def test_the_call_prep_reads_the_team_the_way_the_pack_does():
    research = {"company": FIRM, "fetched_date": "2026-03-10",
                "teams": {"Planning": [{"claim": "The planning team owns the weekly network "
                                                 "forecast.", "url": "https://fernhill.example/p"}]},
                "not_found": ["team:Pricing"]}
    peer = dict(HEAD, route="cold", referred_by="")
    doc = prep.prep_markdown(peer, research, None, {}, [], TODAY, never_say=NO_NEVER)
    team = _section(doc, "Their team")
    assert "Planning: The planning team owns the weekly network forecast. (source: " \
        "https://fernhill.example/p)" in team
    doc = prep.prep_markdown(dict(peer, title="Head of Pricing"), research, None, {}, [], TODAY,
                             never_say=NO_NEVER)
    assert "Pricing: nothing public found about it" in _section(doc, "Their team")


# ------------------------------------------------------------ 12. the next stage, asked once

def test_a_recruiter_is_asked_about_the_next_stage_once(st):
    _application(st)
    text = P.pack_markdown(_gather(stage="Phone screen", with_="Dana Okafor, Talent Partner"),
                           never_say=[])
    assert "screener" not in P.ASK_KIND
    whole = text.lower()
    assert "next stage look like" not in whole
    assert whole.count("what does the next round involve") == 1
    assert "Ask them about the process" in _section(text, "Who you are meeting")


# ------------------------------------------------------------ 13. docs and code agree

def test_the_close_and_the_stock_answer_rule_read_the_same_everywhere(st):
    cmd, guide = _read(*INTERVIEW_MD), _read(*GUIDE)
    assert P.CLOSE_QUESTION in cmd and P.CLOSE_QUESTION in guide
    _application(st)
    ask = _section(P.pack_markdown(_gather(stage="Phone screen"), never_say=[]), "Ask them")
    assert ask.strip().splitlines()[-1].startswith("- %s" % P.CLOSE_QUESTION)
    assert "CAREFUL" not in cmd and "CAREFUL" not in guide
    assert "use this file" not in guide
    assert "the ones in this file are the example person's" in guide
    assert "a process with no row in the tracker yet" in " ".join(_read(*PREP_MD).split())


def test_a_hiring_manager_on_a_live_process_hears_the_referrer_when_asked():
    app = dict(ROW, status="interview")
    assert prep.on_hiring_side(HEAD, app) and not prep.on_hiring_side(HEAD, None)
    assert "when asked" in prep._referrer_advice(HEAD, app)
    doc = prep.prep_markdown(HEAD, {"company": FIRM, "fetched_date": "2026-03-10", "facts": []},
                             app, {}, [], TODAY, never_say=NO_NEVER)
    assert "Name them in the first minute" not in doc
    assert "Name them early, not as a footnote" not in doc
    assert "never the opener" in _section(doc, "Tone for this call")
    # The referrer, or a peer's coffee chat at the same employer, is not the hiring side.
    assert not prep.on_hiring_side(dict(HEAD, status="referral_in_progress"), app)
    assert not prep.on_hiring_side(dict(HEAD, title="Data Engineer", next_action="coffee"), app)


def test_the_call_prep_supplies_no_generic_question_when_nothing_is_researched():
    doc = prep.prep_markdown(PEER, {}, None, {}, [], TODAY, never_say=NO_NEVER)
    assert "six months" not in _section(doc, "Ask them")
    assert "Generic questions are deliberately absent" in inspect.getsource(prep)


# ------------------------------------------------------------ 14. nothing dead, nothing personal

def test_dead_code_is_gone_and_the_narrative_check_is_nobodys_in_particular():
    assert not hasattr(P, "campaign_chat") and not hasattr(P, "LAST_UPDATED")
    assert not hasattr(bridges, "bridge_for")
    assert not hasattr(profile_facts, "MAX_EMPLOYERS")
    assert not hasattr(prep, "LIVING")
    # The prep asks only whether there is a narrative, by a check that names no one's words;
    # narrative() itself stays because a person's own tests call it.
    assert "learning quickly" not in inspect.getsource(profile_facts.has_narrative)
    assert profile_facts.build().get("narrative") is True
    assert callable(profile_facts.narrative)
    text = inspect.getsource(prep)
    assert not re.search(r"which is the title that actually appears on these rows\.\n# The marks",
                         text)
