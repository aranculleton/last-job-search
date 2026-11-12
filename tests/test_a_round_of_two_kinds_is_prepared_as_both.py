"""A round with two kinds of interview in it is prepared as both, with the minutes it states.

An hour booked as "Practical Skills and Personal Experience interview", whose written prep
said the live coding ran about 30 to 45 minutes and the personal experience interview about
15, came out as one personal experience interview for the whole hour: twenty questions about
the person and nothing for the coding, which is most of the hour, and no terms explained. The
live prep reads the kinds the round's own words name, the stage, the format and the written
prep beside it (`interview_prep.md`), and builds each as its own part in the order stated.

Every person, employer and role here is invented: the candidate is the example person, the
application is the made-up one `tests/test_interview_pack.py` builds, and the interviewer is
made up for this file.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import interview_live as L  # noqa: E402
import interview_pack as P  # noqa: E402
from test_interview_pack import COMPANY, ROLE, _ctx, app  # noqa: E402,F401

pytestmark = pytest.mark.usefixtures("app")

STAGE = "Practical Skills and Personal Experience interview"
# The written prep as a chat writes it beside the pack, in its own words.
WRITTEN = """# Interview prep: {company}

## The round

An hour with Priya Okonkwo-Lund, a principal data scientist.

Practical Skills, about 30 to 45 minutes, live on HackerRank: a live, applied
pair-programming exercise in Python, with starter code and a small data file to read first.
Then Personal Experience: Connection, about 15 minutes, one story told in depth.
"""


def _with_prep(written, stage=STAGE, fmt=""):
    """The context the live prep is built from, read the way the command reads it: the
    written prep saved beside the application, then gathered."""
    folder = _ctx()["folder"]
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, P.LIVING), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(written.format(company=COMPANY))
    ctx = _ctx(stage=stage, format_=fmt)
    ctx["stages"] = [{"label": stage, "minutes": 60}]
    return ctx


def _pieces(doc):
    """[(kind of interview, minutes)] in the order the parts run, the hello and their
    questions left out."""
    out = []
    for p in doc["parts"]:
        n = L._piece_of(p["kind"])
        if not n:
            continue
        if out and out[-1][0] == n:
            out[-1] = (n, out[-1][1] + p["minutes"])
        else:
            out.append((n, p["minutes"]))
    return out


def test_a_mixed_round_gets_both_parts_with_the_minutes_its_prep_states():
    ctx = _with_prep(WRITTEN)
    assert "Practical Skills" in ctx["living"]
    doc = L.build(ctx)
    assert doc["shape"] == "combined:technical+personal" and not doc["assumed"]
    kinds = [p["kind"] for p in doc["parts"]]
    assert kinds == ["opening", "technical", "probes", "personal", "close"]
    got = dict(_pieces(doc))
    # About 40 of the hour for the coding (the middle of 30 to 45), 15 for the story, and the
    # hello and their questions in what is left.
    assert 35 <= got["technical"] <= 42 and got["personal"] == 15, got
    assert doc["minutes"] == 60 == sum(p["minutes"] for p in doc["parts"])
    assert all(p["minutes"] >= 2 for p in doc["parts"])


def test_the_coding_part_is_the_problem_worked_aloud_not_personal_questions():
    doc = L.build(_with_prep(WRITTEN))
    by_id = {p["id"]: p for p in doc["parts"]}
    coding = [p for p in doc["parts"] if p["kind"] in ("technical", "probes")]
    assert [p["title"] for p in coding] == ["A problem, worked aloud",
                                            "The follow-up probes and trade-offs"]
    for q in doc["questions"]:
        kind = by_id[q["part"]]["kind"]
        if kind in ("technical", "probes"):
            assert not q["q"].lower().startswith("tell me about a time"), q["q"]
            assert q["who"] in ("technical", "peer"), q
    assert any("trade-off" in q["q"].lower() for q in doc["questions"]
               if by_id[q["part"]]["kind"] == "probes")
    # Until the problem as they would set it is written, the coding part is not finished.
    found = L.problems(doc)
    assert any("A problem, worked aloud" in w and "Given" in why for w, why in found)
    # The story in depth keeps its own part, after the coding.
    personal = next(p for p in doc["parts"] if p["kind"] == "personal")
    assert personal["questions"] and personal["minutes"] == 15


def test_the_stage_alone_names_both_kinds():
    # With no written prep, the stage's own words still say there are two.
    ctx = _ctx(stage=STAGE)
    ctx["living"] = ""
    shape, assumed = L.shape_of(ctx)
    assert shape == "combined:technical+personal" and not assumed


def test_the_stated_split_beats_the_stage_name():
    ctx = _with_prep(WRITTEN, stage="Personal Experience interview")
    shape, _why = L.shape_of(ctx)
    assert shape == "combined:technical+personal"
    assert dict(_pieces(L.build(ctx)))["personal"] == 15
    # And the order stated wins over the order the stage names them in.
    flipped = WRITTEN.replace(
        "Practical Skills, about 30 to 45 minutes", "Behavioural questions first, about 20 minutes. "
        "Then Practical Skills, about 30 minutes").replace(
        "Then Personal Experience: Connection, about 15 minutes, one story told in depth.", "")
    doc = L.build(_with_prep(flipped, stage="Technical interview"))
    assert doc["shape"] == "combined:behaviour+technical"
    assert _pieces(doc) == [("behaviour", 20), ("technical", 30)]


def test_a_single_kind_round_is_built_as_before():
    # One kind stated with its minutes is no split: the round's own name decides, as before.
    one = "## The round\n\nPersonal Experience, about 30 minutes, one story in depth.\n"
    doc = L.build(_with_prep(one, stage="Personal experience interview"))
    assert doc["shape"] in ("personal", "case") and "technical" not in [p["kind"] for p in doc["parts"]]
    tech = L.build(_with_prep("", stage="Technical interview, 45 minutes", fmt="live SQL and Python"))
    assert tech["shape"] == "technical" and [p["kind"] for p in tech["parts"]] == [
        "opening", "technical", "probes", "close"]


def test_a_problem_solving_test_at_a_consulting_firm_stays_a_test(monkeypatch):
    monkeypatch.setattr(P, "employer_type", lambda ctx: "consulting")
    ctx = _ctx(stage="Problem solving test")
    ctx["living"] = ""
    assert L.shape_of(ctx)[0] == "assessment"
    ctx = _ctx(stage="Problem solving interview")
    ctx["living"] = ""
    assert L.shape_of(ctx)[0] in ("case", "case_only")


def test_an_empty_glossary_with_technical_questions_is_flagged():
    doc = L.build(_with_prep(WRITTEN))
    doc["terms"] = {}
    found = L.problems(doc)
    assert any(w == "the terms" for w, _why in found), found
    why = next(why for w, why in found if w == "the terms")
    assert "worked example" in why and COMPANY in why
    # A prep whose questions carry no word of the work is not asked for terms.
    plain_doc = {"company": COMPANY, "parts": [], "questions": [
        {"id": "q1", "part": "p1", "q": "Why this team?", "simple": "", "detailed": "", "follow": []}],
                 "ask": [], "terms": {}}
    assert not any(w == "the terms" for w, _why in L.problems(plain_doc))


def test_the_command_builds_the_mixed_round_from_the_written_prep(tmp_path):
    _with_prep(WRITTEN)
    out = tmp_path / "live.json"
    got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "interview_pack.py"), "live",
                          COMPANY, "--role", ROLE, "--stage", STAGE, "--out", str(out)],
                         capture_output=True, text=True, encoding="utf-8", env=dict(os.environ))
    assert got.returncode == 0, got.stdout + got.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["shape"] == "combined:technical+personal"
    assert [n for n, _m in _pieces(doc)] == ["technical", "personal"]
    assert "- the terms:" in got.stdout


def test_another_rounds_split_in_the_prep_is_not_this_rounds():
    # The written prep is one for the whole process: a split it states for the coding round
    # never shapes the final, whose name says no kind and which the prep does not name.
    ctx = _with_prep(WRITTEN, stage="Final round with the director")
    assert L.stated_split(ctx) == []
    assert L.build(ctx)["shape"] == "final"


def test_the_coding_part_says_what_its_first_words_are_for():
    doc = L.build(_with_prep(WRITTEN))
    said = [w for k, w in L.problems(doc) if k == '"A problem, worked aloud"']
    opening = [w for w in said if w.startswith("nothing to say first yet")]
    assert opening and "starter code and data" in opening[0] and "think aloud" in opening[0], said
    probes = [w for k, w in L.problems(doc) if k == '"The follow-up probes and trade-offs"']
    assert any("trade-offs you chose" in w for w in probes), probes
