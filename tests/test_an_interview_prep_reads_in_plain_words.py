"""An interview's prep reads, in the document and on the page, in plain words for a tired person
on a phone in the minutes before a call.

The person said the interview screen "hits you with walls of text, links to random json files
and destinations the user shouldn't know about, is weirdly formatted and sometimes randomly
says draft", with "so many random don't says" (2026-11-03). The document named every source as
a file ("(source: ../../profile/07-interview-prep.md)"), carried commands for Claude
("python3 tools/interview_pack.py motive ...", "rebuild with --with"), contacts' states as codes
("[replied_needs_response]"), four "do not say" lines (one the same rule on every pack), the
same notes twice, and an introduction saying "Draft" on every pack; and the page showed all of
it, whole, after a box of its own. The page also read the engine's one screen and practice in
shapes only its sample had, so the Brief showed no questions for an interview that day and the
practice asked "[object Object]"; an offer showed as "Round 4", a round with nothing booked
after it as "Round 3, time not set", and an interview the person was turned down for as
"Passed".

These build the example person's own packs with the tools, read them as the page does, and
open the page the engine makes from them in a browser. Every employer and person here is
invented; the candidate is the example person.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools", "network"), os.path.join(ROOT, "tools"),
           os.path.join(ROOT, "tests"), os.path.join(ROOT, "templates", "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app_page  # noqa: E402
import app_state  # noqa: E402
import interview_pack as P  # noqa: E402
from test_interview_pack import COMPANY, _ctx  # noqa: E402
from test_interview_pack import app as app  # noqa: E402,F401  the fixture, by name
from test_the_page_works_in_a_browser import run as run  # noqa: E402,F401  the runner, by name

PACK = os.path.join(ROOT, "tools", "interview_pack.py")
APP = os.path.join(ROOT, "tools", "app.py")
PHONE = {"width": 390, "height": 844}
WIDE = {"width": 1440, "height": 900}
DAY, NOW = "2026-11-03", "2026-11-03T09:00:00Z"

# What a person would have to look up, or should never see: a command, a file or a folder, a
# flag, a rule of Claude's own instructions, a state's code, a plural in brackets, a shouted mark.
INTERNAL = re.compile(r"python3|tools/|\.py\b|\.json\b|\.csv\b|\b[\w-]+\.md\b|(?<![\w-])--[a-z]|"
                      r"interview\.md|\brule 2\b|\[[a-z]+_[a-z_]+\]|\w\((?:e?s)\)|RESEARCH FIRST|"
                      r"ASK YOU FIRST|\.\./|documents/|company_research|draft\.json")


def _person_lines(text):
    """The lines of a document a person reads: its tool comments are never shown."""
    return [ln for ln in text.splitlines() if not ln.strip().startswith("<!--")]


def _internal(text):
    return [(ln, m.group(0)) for ln in _person_lines(text) for m in [INTERNAL.search(ln)] if m]


def _section(text, title):
    return text.split("## %s\n" % title, 1)[1].split("\n## ", 1)[0]


# ------------------------------------------------------------------ the document, at its source

@pytest.mark.parametrize("stage", ["Technical interview", "Phone screen", "Case interview",
                                   "Panel interview", "Final round", "Offer received"])
def test_a_pack_names_no_file_command_or_code(app, stage):
    text = P.pack_markdown(_ctx(stage=stage), never_say=[])
    assert _internal(text) == [], _internal(text)[:3]
    # Every source is still given, as what it is to the person.
    assert "(source: your profile)" in text or "(source: your stories and answers)" in text
    assert "Every fact carries its source" not in text and "One document for this" not in text


def test_a_rebuilt_pack_stays_plain_and_keeps_what_was_written(app):
    path = P.write_pack(_ctx(), never_say=[])
    text = open(path, encoding="utf-8").read()
    mine = "I'd start from the depots' own numbers, because that's where the forecast gets used."
    text = text.replace(P.TO_WRITE, mine, 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    P.write_pack(_ctx(), never_say=[])
    again = open(path, encoding="utf-8").read()
    assert mine in again and _internal(again) == []


def test_the_one_screen_is_what_to_say_what_to_ask_and_two_cautions(app):
    text = P.pack_markdown(_ctx(stage="Phone screen"), never_say=[])
    got = P.one_screen(text)
    assert 2 <= len(got["say"]) <= P.MAX_SAY
    assert got["say"][0]["text"].startswith("Lead with your strongest result: ")
    assert any(s["text"].startswith("The basics: ") and "no sponsorship needed" in s["text"]
               for s in got["say"])
    assert 2 <= len(got["ask"]) <= P.MAX_ASK_FIRST and got["ask"][-1]["text"] == P.CLOSE_QUESTION
    assert 1 <= len(got["do_not_say"]) <= P.MAX_DO_NOT
    # The rule every interview keeps is said once, where it belongs, not as one more "don't".
    assert P.PAPER_RULE.lstrip("- ") not in _section(text, "On one screen")
    assert P.PAPER_RULE in _section(text, "What the paper says")
    # What to say about pay comes first.
    assert got["money"].startswith("say what the form said, GBP 48,000 to 58,000")
    # An offer asks what an offer needs, never the close of an interview.
    offer = P.one_screen(P.pack_markdown(_ctx(stage="Offer received"), never_say=[]))
    assert [a["text"] for a in offer["ask"]] == list(P.OFFER_QUESTIONS)
    assert offer["say"][0]["text"].startswith("Counter inside your target")


def test_draft_is_said_once_and_only_above_an_answer_that_is_one(app):
    path = P.write_pack(_ctx(stage="Phone screen"), never_say=[])
    text = open(path, encoding="utf-8").read()
    # Nothing is a draft yet: the word is nowhere in what the person reads.
    assert "Draft" not in "\n".join(_person_lines(text))
    blocks = text.split("\n### ")
    for i, b in enumerate(blocks):
        if b.startswith("Why Fernhill Freight?") or b.startswith("Tell me about yourself."):
            mark = (P.DRAFT_MARK + "\n") if b.startswith("Why") else ""
            said = ("I want to plan for a network that is still growing." if mark else
                    "I'm a demand planner in Manchester, and I build the forecasts the depots use.")
            blocks[i] = b.replace(P.TO_WRITE, mark + said, 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n### ".join(blocks))
    read = P.reading(open(path, encoding="utf-8").read(), COMPANY)
    drafts = [q["question"] for q in read["questions"] if q["draft"]]
    assert drafts == ["Why Fernhill Freight?"]
    about = next(q for q in read["questions"] if q["question"] == "Tell me about yourself.")
    assert about["answer"].startswith("I'm a demand planner") and not about["draft"]


# An interview prep as an older version wrote it: every source a file, commands for Claude,
# states as codes, research still to do, a draft mark, plurals in brackets. Invented.
OLDER = """# Interview prep: Demand Planning Analyst at Fernhill Freight

Last updated 2026-10-20. Next: Phone screen, 2026-10-22, with the recruiter. One document for this whole process: change an answer here, and it is sent to you again.
Every fact carries its source, and anything unsourced was left out.
This is for before and after the interview. Claude never helps during a live interview, and never records or transcribes one.
<!-- stages: Phone screen -->

## On one screen

**What they are assessing:** whether the basics hold.
**What they want to hear:** a clear story.

**Likely questions, and what to answer with**
1. Tell me about yourself. -> your summary, said your way (Your answers)
2. Why Fernhill Freight? -> your answer, below
3. Walk me through a project. -> story: The forecast that freed safety stock

**Hooks**
- Opened a cross-dock in Warrington in January 2026. (source: https://fernhill.example/news)

**Money:** nothing on the form; your target is GBP 48,000 to 58,000, and the floor stays unsaid.

<!-- quoted: words to avoid, not to say -->
**Do not say**
- Do not say: Do not call it a parcel carrier: it moves pallets. (source: https://fernhill.example/about)
- Not as it stands: your answer to "Why now?": it argues against them. Rewrite it (source: ../../profile/07-interview-prep.md)
- Words you have said never to use: "synergy" (source: profile/learned.json)
- No claim in the room beyond the paper they read, except a draft you asked for and have made true.
<!-- /quoted -->

## Your answers

What you will say goes under each question, as sentences. Anything else (a reminder, a list) goes under a line "Notes:", after "Note:", or in italics: it is kept on every rebuild and never checked as something to say. An answer drafted for you to confirm starts "Draft:"; delete that line once it is true.

### Tell me about yourself.
> Checking: whether your story is clear. They want to hear: about ninety seconds.
I'm a demand planner in Manchester, and I build the forecasts the depots use.

### Why Fernhill Freight?
> Checking: whether you chose them. They want to hear: something true about them.
Draft: yours to confirm or change. Delete this line once it is true.
You're growing the cross-dock network, and that's the planning problem I want.

### Walk me through a project.
> Checking: whether you did the work. They want to hear: the result in numbers.
[to write: said aloud, first person, whole sentences, contractions welcome]
- From: Story: The forecast that freed safety stock (matched by its Use for tags; source: ../../profile/07-interview-prep.md)
- From: ASK YOU FIRST (Claude asks, once): "Which project are you proudest of?" Nothing on file can supply the reasons. Their answer is kept for every later employer: python3 tools/interview_pack.py motive "Walk me through a project." --answer "<their words>" [--suits <kinds> --not-for <kinds>]. If they ask for a draft instead, write it under the question, marked as one (interview.md rule 2).

## What they have been told

- Read: Hal Okonedo, Transport Analyst [replied_needs_response]: 1 message(s) from you, 2026-09-10 (source: network_threads.csv)
- 2026-09-12, to Hal Okonedo: text not logged: check what this said. Add it: python3 tools/network/state.py text fernhill_freight_okonedo --date 2026-09-12 --text-file <the message as sent> (source: network_threads.csv)

## Who you are meeting

- Assumed: Shirin leads this process. If the invite names someone else, rebuild with --with "<name, title>". (source: network_contacts.csv)
  - RESEARCH FIRST (Claude, not you): Shirin's public work, kept with `python3 tools/network/reading.py add <id> --name "Shirin" --company "Fernhill Freight" ...`, then this is rebuilt.

## Likely questions

Notes on each question: what an answer can come from, and where. None of it is words to say: what you say is under Your answers.

- **Q.** Tell me about yourself. (what a screen usually asks; source: the stage)
  - Notes, not words to say: [raw profile wording: rewrite to spoken first person before use] Demand planner with seven years. (source: ../../profile/01-candidate-profile.md)
- **Q.** Why Fernhill Freight? (what a screen usually asks; source: the stage)
- **Q.** Walk me through a project. (what a screen usually asks; source: the stage)

## Stories

- **The forecast that freed safety stock** (source: ../../profile/07-interview-prep.md)
  - S: error at 22%.
  - R: error down to 14%, about £1.1M of safety stock released.
  - Use for: Walk me through a project end to end

## What the paper says

- Sent: cv/Morgan_Ellis_CV_Fernhill.tex, cover_letters/Morgan_Ellis_Cover_Letter_Fernhill.tex (source: job_search_tracker.csv)
- No draft.json kept for this application, so what the letter argued is not on file: read the letter itself before the interview.

## The company

- RESEARCH FIRST (Claude, not you): Fernhill Freight itself, from its own pages (interview.md Step 2), then this is rebuilt.

## Small talk

- Keep it to a minute or two.

### What you found out

- Chorlton has a market on Saturdays. (source: https://chorlton.example/market)

## Earlier stages

- Booked: Phone screen 2026-10-22 (source: documents/applications/fernhill_freight_demand_planning_analyst/outcome.md)

## To rework

- 2026-10-21, mock: "Tell me about yourself.": lead with the forecast result.

## Notes

- Nothing yet: anything you want kept, write it here.
"""


def test_an_older_prep_reads_cleanly_on_the_page():
    read = P.reading(OLDER, COMPANY)
    blob = json.dumps(read, ensure_ascii=False)
    assert not INTERNAL.search(blob), INTERNAL.search(blob).group(0)
    assert "(source:" not in blob and "Notes, not words to say" not in blob
    g = read["glance"]
    # What to say, from what it holds, when it was built before the one screen said it.
    assert g["say"][0] == "Lead with your strongest result: error down to 14%, about £1.1M of " \
                          "safety stock released."
    assert g["careful"][0] == "Do not call it a parcel carrier: it moves pallets."
    assert len(g["careful"]) <= P.MAX_DO_NOT
    qs = {q["question"]: q for q in read["questions"]}
    assert [q for q in qs if qs[q]["draft"]] == ["Why Fernhill Freight?"]
    assert qs["Tell me about yourself."]["answer"].startswith("I'm a demand planner")
    project = qs["Walk me through a project."]
    assert project["answer"] is None and project["cue"] == "your story: The forecast that freed " \
                                                           "safety stock"
    assert project["notes"][0] == "Your story: The forecast that freed safety stock"
    assert project["notes"][1] == 'Claude asks you first: "Which project are you proudest of?"'
    secs = {s["title"]: s for s in read["sections"]}
    told = [i["text"] for i in secs["What they have been told"]["items"]]
    assert told[0] == "Hal Okonedo, Transport Analyst (replied, your turn): one message from " \
                      "you, 2026-09-10"
    assert told[1].startswith("2026-09-12, to Hal Okonedo: text not logged: check what this said.")
    paper = [i["text"] for i in secs["What the paper says"]["items"]]
    assert paper == ["Sent: your CV, your cover letter",
                     "What the letter argued is not on file: read the letter itself before the "
                     "interview."]
    # Research still to do is Claude's: the person never reads the request.
    assert "About Fernhill Freight" not in secs
    meeting = secs["Who you are meeting"]["items"]
    assert meeting[0]["sub"] == [] and "rebuild" not in meeting[0]["text"]
    story = secs["Stories"]["items"][0]
    assert story["text"] == "The forecast that freed safety stock"
    assert story["sub"] == ["The situation: error at 22%.",
                            "The result: error down to 14%, about £1.1M of safety stock released."]
    assert secs["To work on"]["items"][0]["text"] == \
        "Tell me about yourself. lead with the forecast result. (from your practice, 2026-10-21)"
    assert "Your notes" not in secs                   # its placeholder alone is nothing to read
    # What they found out stays under its own heading.
    talk = secs["Small talk"]["items"]
    assert talk[0]["text"] == "Keep it to a minute or two."
    assert talk[1] == {"text": "What you found out", "link": "", "head": True,
                       "sub": ["Chorlton has a market on Saturdays."]}


def test_sources_are_said_in_words():
    assert P.source_words("../../../profile/07-interview-prep.md") == "your stories and answers"
    assert P.source_words("profile/person.json identity.places_told") == "your profile"
    assert P.source_words("documents/applications/x_y/screening_answers.md") == \
        "the application form"
    assert P.source_words("the recruiter's email, recorded in documents/interview/"
                          "question_bank.csv") == "the recruiter's email, recorded in your past " \
                                                  "interviews"
    assert P.source_words(".claude/skills/job-application-assistant/04-job-evaluation.md") == \
        "the app's guide"
    assert P.source_words("https://fernhill.example/about") == "https://fernhill.example/about"
    assert P.source_words("the stage") == "the stage"


# ------------------------------------------------------------------ the page, from the engine

def _cli(env, *args):
    r = subprocess.run([sys.executable, *args], env=env, capture_output=True, encoding="utf-8",
                       errors="replace", timeout=180, cwd=ROOT)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    return r.stdout


def _outcome(state, company, role, body, status="in_progress"):
    import docpaths
    old = os.environ.get("LJS_STATE")
    os.environ["LJS_STATE"] = state
    try:
        folder = docpaths.app_folder(company, role)
    finally:
        if old is None:
            os.environ.pop("LJS_STATE", None)
        else:
            os.environ["LJS_STATE"] = old
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "outcome.md"), "w", encoding="utf-8") as fh:
        fh.write("# Outcome: %s - %s\n\n**Status:** %s\n\n## Interview stages reached\n%s\n"
                 "## Notes\n- 2026-10-20: booked.\n" % (company, role, status, body))
    return folder


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The example person with an interview in every state, preps made with the tools, a
    real-length one with research and answers (one a draft), and the page the engine makes."""
    tmp = tmp_path_factory.mktemp("ivpage")
    profile = app_state.profile_copy(str(tmp / "profile"))
    state = app_state.small(str(tmp / "state"))
    env = dict(os.environ, LJS_PROFILE=profile, LJS_STATE=state, LJS_TODAY=DAY)
    tracker = os.path.join(state, "job_search_tracker.csv")
    rows = app_state._csv_rows(tracker)
    for r in rows:
        if r["company"] == "Larkspur Retail":
            r["status"] = "interview"
    for company, role, status in (("Brackenridge Advisory", "Analytics Consultant", "interview"),
                                  ("Copperleaf Pay", "Data Analyst, Payments", "offer"),
                                  ("Ellerwick Trust", "Data Analyst", "rejected"),
                                  ("Fernhill Mills", "Planning Analyst", "withdrawn"),
                                  ("Quayside Logistics", "Reporting Analyst", "no_response")):
        rows.append({"date": "2026-10-05", "company": company, "role": role, "status": status,
                     "channel": "company site", "applied_on": "2026-10-05",
                     "confirmed_by": "chat", "confirmed_at": "2026-10-05 09:00"})
    app_state._save_csv(tracker, rows, app_state.TRACKER_COLUMNS)
    _outcome(state, "Copperleaf Pay", "Data Analyst, Payments",
             "- [x] Final round (2026-10-28 15:00, with the hiring manager)\n"
             "- [x] Offer received (2026-10-31)\n", status="offer")
    _outcome(state, "Ellerwick Trust", "Data Analyst",
             "- [x] Phone screen (2026-10-27 09:30, with the recruiter)\n", status="rejected")
    _outcome(state, "Fernhill Mills", "Planning Analyst",
             "- [x] Phone screen (2026-10-29 11:00, with the recruiter)\n", status="withdrawn")
    _outcome(state, "Quayside Logistics", "Reporting Analyst",
             "- [x] First interview (2026-10-22 14:00, with the hiring manager)\n",
             status="no_response")
    research = {"company": "Larkspur Retail", "fetched_date": "2026-11-02",
                "recent_news": [{"claim": "Moved its forecasting to store level for chilled and "
                                          "fresh lines in September 2026.",
                                 "source_url": "https://larkspur.example/news/store-forecasting"}],
                "do_not_claim": [{"claim": "Do not call it a discounter: it prices as a "
                                           "mid-market grocer.",
                                  "source_url": "https://larkspur.example/about"}]}
    os.makedirs(os.path.join(state, "company_research"), exist_ok=True)
    with open(os.path.join(state, "company_research", "larkspur-retail.json"), "w",
              encoding="utf-8") as fh:
        json.dump(research, fh)
    _cli(env, PACK, "book", "Larkspur Retail", "--stage", "Phone screen", "--date", "2026-11-04",
         "--time", "14:00", "--with", "the recruiter", "--today", DAY)
    _cli(env, PACK, "book", "Brackenridge Advisory", "--stage", "Case interview", "--date", DAY,
         "--time", "16:30", "--with", "the engagement manager", "--today", DAY)
    for company, stage in (("Larkspur Retail", "Phone screen"),
                           ("Brackenridge Advisory", "Case interview"),
                           ("Copperleaf Pay", "Offer received")):
        _cli(env, PACK, "pack", company, "--stage", stage, "--write", "--today", DAY)
    folder = os.path.join(state, "documents", "applications",
                          "larkspur_retail_senior_supply_chain_analyst")
    path = os.path.join(folder, P.LIVING)
    text = open(path, encoding="utf-8").read()
    answers = {"Tell me about yourself.": "I'm an operations analyst in Manchester, and I turn "
                                          "warehouse and supplier data into forecasts people "
                                          "plan with.",
               "Why Larkspur Retail?": P.DRAFT_MARK + "\nYou've just moved chilled forecasting "
                                                      "to store level, and that's the problem "
                                                      "I've worked on."}
    for q, a in answers.items():
        i = text.index("### %s\n" % q)
        j = text.index(P.TO_WRITE, i)
        text = text[:j] + a + text[j + len(P.TO_WRITE):]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    _cli(env, PACK, "pack", "Larkspur Retail", "--stage", "Phone screen", "--write", "--today",
         DAY)
    # One process keeps a prep an older version wrote, as a repo that has not remade it does.
    with open(os.path.join(state, "documents", "applications",
                           "thornbury_bank_risk_analyst_thornbury", P.LIVING), "w",
              encoding="utf-8") as fh:
        fh.write(OLDER)
    out = str(tmp / "page.artifact.html")
    _cli(env, APP, "page", "--now", NOW, "--today", DAY, "--out", out)
    page = str(tmp / "page.html")
    with open(page, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(open(out, encoding="utf-8").read()))
    model = json.loads(_cli(env, APP, "model", "--now", NOW, "--today", DAY))
    return {"page": page, "model": model, "env": env, "state": state}


LARKSPUR = "int-larkspur_retail_senior_supply_chain_analyst"


def test_the_model_carries_the_prep_as_parts_and_the_rounds_as_they_stand(built):
    ivs = {i["id"]: i for i in built["model"]["interviews"]}
    lark = ivs[LARKSPUR]
    assert "prep_text" not in lark and lark["prep_read"]["glance"]["say"]
    assert not INTERNAL.search(json.dumps(lark["prep_read"]))
    # An offer is the offer, and a round with nothing booked after it is the round last held.
    offer = ivs["int-copperleaf_pay_data_analyst_payments"]
    assert (offer["next_stage"], offer["when"]) == ("Offer", None)
    thornbury = ivs["int-thornbury_bank_risk_analyst"]
    assert thornbury["next_stage"] == "Panel interview" and thornbury["when"] == "2026-10-28"
    # A prep an older version wrote reads as cleanly once the page's model carries it: read
    # first, then scrubbed of contact details, never the other way round, which left
    # "(source:../../profile/...)" for the reader to miss.
    older = json.dumps(thornbury["prep_read"], ensure_ascii=False)
    assert "source:" not in older and not INTERNAL.search(older), older[:300]
    assert thornbury["prep_read"]["glance"]["careful"][0] == \
        "Do not call it a parcel carrier: it moves pallets."
    assert not any(re.match(r"Round \d", i["next_stage"] or "") for i in ivs.values())
    # A thank-you after the final round, and none after the offer: it asked for both.
    thanks = [d["title"] for d in built["model"]["due"] if d.get("sub") == "thank_you"
              and "Copperleaf" in d["title"]]
    assert thanks == ["Thank-you note after your Copperleaf Pay interview"]


def test_the_prep_on_a_phone_is_the_minutes_before_then_folded(run, built):
    r = run("prep_reader", html=built["page"], id=LARKSPUR, viewport=PHONE, clock=NOW)
    assert not r["errors"], r["errors"]
    assert r["title"] == "Phone screen with Larkspur Retail"
    assert r["when"].startswith("Tomorrow · Wed 4 Nov, 14:00") and "with the recruiter" in r["when"]
    assert r["glanceH"] == "Before you go in"
    labels = [p["label"] for p in r["parts"]]
    assert labels[:2] == ["Say these", "Ask them"] and labels[-1] == "Careful"
    assert 2 <= r["parts"][0]["n"] <= 5 and 2 <= r["parts"][1]["n"] <= 3
    assert r["parts"][-1]["n"] <= 2
    # Big type for the minutes before; the rest folded, one tap each.
    assert r["glanceFont"] > r["bodyFont"]
    assert r["folds"][0] == "Likely questions" and "Stories" in r["folds"]
    assert r["openAtFirst"] == 0 and r["openAfterTap"] == 1
    # Everything once every fold is open: plain words, "Draft" above the one answer that is
    # one, and no link but an employer's own page.
    assert not INTERNAL.search(r["text"]), INTERNAL.search(r["text"]).group(0)
    assert "(source:" not in r["text"] and "**" not in r["text"] and "->" not in r["text"]
    assert [d.split(". ", 1)[1] for d in r["drafts"]] == ["Why Larkspur Retail?"]
    assert r["text"].count("Draft") == 1
    outside = [h for h in r["links"] if not h.startswith("#")]
    assert outside and all(h.startswith("https://larkspur.example/") for h in outside), r["links"]
    assert "Your CV, " in r["text"] and "Morgan_Ellis" not in r["text"]
    assert r["overflow"]["sw"] <= r["overflow"]["cw"]


def test_the_prep_on_a_laptop_in_the_dark_reads_the_same(run, built):
    r = run("prep_reader", html=built["page"], id=LARKSPUR, viewport=WIDE, scheme="dark",
            clock=NOW)
    assert not r["errors"], r["errors"]
    assert r["glanceH"] == "Before you go in" and r["folds"][0] == "Likely questions"
    assert not INTERNAL.search(r["text"]) and r["overflow"]["sw"] <= r["overflow"]["cw"]


def test_an_offer_reads_as_the_offer(run, built):
    r = run("prep_reader", html=built["page"], id="int-copperleaf_pay_data_analyst_payments",
            viewport=PHONE, clock=NOW)
    assert r["title"] == "Your offer from Copperleaf Pay"
    assert "Round" not in r["text"] and "Practise with Claude" not in r["text"]
    assert "Is there anything about my background" not in r["glance"]


def test_each_interview_card_says_how_it_stands(run, built):
    r = run("iv_cards", html=built["page"], viewport=PHONE, clock=NOW)
    assert not r["errors"], r["errors"]
    cards = {c["title"]: c for c in r["cards"]}
    assert "Passed" not in [c["pill"] for c in r["cards"]]
    ended = {"Phone screen with Ellerwick Trust": "They said no",
             "Phone screen with Fernhill Mills": "You withdrew",
             "First interview with Quayside Logistics": "No reply"}
    for title, pill in ended.items():
        assert cards[title]["pill"] == pill, (title, cards[title])
        # Nothing left to end, and no prep to ask for.
        assert not cards[title]["bin"] and "prep" not in cards[title]["meta"].lower()
    waiting = cards["Panel interview with Thornbury Bank"]
    assert waiting["pill"] == "Waiting to hear" and waiting["when"] == "Wed 28 Oct"
    assert "I heard back" in waiting["buttons"]
    offer = cards["Your offer from Copperleaf Pay"]
    assert offer["pill"] == "Offer" and offer["when"] == "" and offer["bin"]
    assert "Practise with Claude" not in offer["buttons"]
    # The Brief's Today reads the prep's own questions for the interview today.
    assert r["likely"] and not any("[object Object]" in x for x in r["likely"])
    assert "Likely to come up" in r["today"]


def test_practice_asks_the_packs_own_questions(run, built):
    r = run("mock", html=built["page"])
    assert not r["errors"], r["errors"]
    prompt = r["prompt"]
    assert "[object Object]" not in prompt
    assert "Ask exactly these questions, one at a time, in this order: 1. Tell me about yourself." \
        in prompt
