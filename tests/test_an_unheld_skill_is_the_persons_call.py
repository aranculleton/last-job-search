"""A skill a posting names that the profile does not hold is the person's call, every time.

The app decided it alone: a tool the person did not list was left off, and a tool they
had once said they did not hold was never written down. Only they know whether they use
it and never said, learned it since, or judge they can back it up, and the word left off
can be the one an applicant tracking system screens on. So staging asks about each one,
nothing is drafted or assembled until every answer is in, a yes prints on the skills line
as the posting spells it, and both answers travel in the documents' own header, which the
claim check reads.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import bridges  # noqa: E402
import check_claims  # noqa: E402
import interview_pack  # noqa: E402
import skills_block  # noqa: E402
import stage_picks  # noqa: E402
import untrusted  # noqa: E402

POSTING = ("You will build Looker dashboards and demand forecasts in SQL and Python. "
           "Spark experience is a plus, and SAP ABAP is nice to have.")
DRAFT = {"company": "Kestrel Mutual", "role": "Operations Analyst", "summary": "s",
         "p1": "a.", "p2": "b.", "lead": "c", "cl_bullets": [], "p4": "d."}


def test_every_unheld_skill_the_posting_names_is_found_in_its_own_spelling():
    got = {x["skill"]: x for x in bridges.unheld_asked(POSTING)}
    # A tool of a held family, the fit score's own gap, and one the profile says it lacks.
    assert {"Looker", "Spark", "SAP ABAP"} <= set(got)
    assert got["Looker"]["have"][0] == "Power BI"
    # What the person holds is never asked about.
    assert not {"SQL", "Python", "Power BI"} & set(got)
    assert [x["skill"] for x in bridges.unheld_asked("SQL and Python")] == []


def _stage(tmp_path, posting=POSTING):
    row = {"company": "Kestrel Mutual", "title": "Operations Analyst", "url": "u",
           "portal": "pasted", "desc": posting}
    return stage_picks.stage(str(tmp_path), ["1"], rows=[], root=str(tmp_path),
                             shortlist=[row])[0]


def test_staging_asks_one_short_question_and_nothing_is_assembled_until_it_is_answered(
        tmp_path, monkeypatch):
    # Updated 2026-10-25: the record below has neither audit in it, which assemble now
    # refuses (tests/test_every_draft_sent_gets_the_model_audit.py); what this test reads
    # is the person's answers, so the audit gate is set aside here.
    monkeypatch.setattr(stage_picks, "_held_back", lambda *a, **k: "")
    p = _stage(tmp_path)
    assert {"Looker", "Spark", "SAP ABAP"} <= set(p["ask_first"])
    q = stage_picks.question(p)
    assert q.startswith("Kestrel Mutual asks for Looker (you list Power BI)")
    assert len(stage_picks.question(dict(p, ask_first=["Looker"])).split()) <= 40
    (tmp_path / f"audit_{p['slug']}.json").write_text(
        json.dumps({"verdict": "pass", "draft": DRAFT, "changes": [], "residual_risks": []}),
        encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        stage_picks.assemble(str(tmp_path))
    assert "Looker" in str(e.value) and "consent" in str(e.value)
    rest = [n for n in p["ask_first"] if n != "Looker"]
    got = stage_picks.consent(str(tmp_path), p["slug"], yes=["looker"], no=rest)
    assert got["skills_yes"] == ["Looker"] and stage_picks.question(got) == ""
    drafts, missing, rejected = stage_picks.assemble(str(tmp_path))
    assert drafts[0]["consented_skills"] == ["Looker"]
    assert set(drafts[0]["declined_skills"]) == set(rest)


def test_a_changed_answer_moves_the_skill_and_both_at_once_is_refused(tmp_path):
    p = _stage(tmp_path)
    stage_picks.consent(str(tmp_path), p["slug"], no=["Looker"])
    got = stage_picks.consent(str(tmp_path), p["slug"], yes=["Looker"])
    assert got["skills_yes"] == ["Looker"] and "Looker" not in got["skills_no"]
    with pytest.raises(SystemExit):
        stage_picks.consent(str(tmp_path), p["slug"], yes=["Spark"], no=["spark"])


def test_a_pick_staged_before_this_step_is_read_from_its_posting(tmp_path):
    f = tmp_path / "01_kestrel.md"
    f.write_text("# head\n\n" + untrusted.fence(POSTING) + "\n", encoding="utf-8")
    old = {"file": str(f), "company": "Kestrel Mutual", "role": "r", "slug": "kestrel",
           "abbr": "Kestrel"}
    assert "Looker" in stage_picks.unanswered(old)


def test_a_yes_prints_on_the_skills_line_beside_the_held_tool_and_a_no_never_does():
    line = skills_block.render("SQL, Python", posting=POSTING, consented=["Looker"])
    assert "Power BI, Looker" in line
    assert "Spark" not in skills_block.render("SQL, Python", posting=POSTING, consented=["Looker"])
    # Without a yes the held tool stands in alone, as before.
    assert "Looker" not in skills_block.render("SQL, Python", posting=POSTING)
    # Never trimmed, and escaped for LaTeX.
    many = skills_block.render("SQL, Python", posting=POSTING, consented=["R&D tooling", "Spark"])
    assert r"R\&D tooling" in many and "Spark" in many


def _doc(tmp_path, body, yes=(), no=(), folder="cv", name="Morgan_Ellis_CV_Acme.tex"):
    (tmp_path / folder).mkdir(exist_ok=True)
    f = tmp_path / folder / name
    f.write_text("%% Tailored for: Acme - Analyst\n" + check_claims.consent_header(yes, no)
                 + body, encoding="utf-8")
    return str(f)


def test_the_claim_check_reads_the_answers_from_the_document_itself(tmp_path):
    claim = "Configured SAP ABAP reports for the planning team.\n"
    names = lambda path: [(s, n) for s, n, _, _ in check_claims.check(path)  # noqa: E731
                          if n in ("unheld-skill", "declined-skill")]
    assert names(_doc(tmp_path, claim)) == [("ERROR", "unheld-skill")]
    assert names(_doc(tmp_path, claim, yes=["SAP ABAP"])) == []
    assert names(_doc(tmp_path, "Built Spark jobs.\n", no=["Spark"])) == [("WARN", "declined-skill")]
    assert check_claims.read_consent(check_claims.consent_header(["A", "B"], ["C"])) == (["A", "B"], ["C"])
    assert check_claims.consent_header() == ""


def test_the_interview_pack_flags_what_they_said_yes_to():
    ctx = {"draft": {"_path": "draft.json", "consented_skills": ["Looker"]},
           "facts": {"gaps": [], "blockers": []}}
    assert any("yes to claiming Looker" in line for line in interview_pack.gap_lines(ctx))


def test_the_workflow_will_not_draft_a_pick_still_waiting():
    src = open(os.path.join(ROOT, ".claude", "workflows", "draft-applications.js"),
               encoding="utf-8").read()
    node = subprocess.run(["node", "--version"], capture_output=True) if shutil.which("node") \
        else subprocess.CompletedProcess(["node"], 127)
    if node.returncode != 0:
        assert "Ask the person first" in src and "skills_yes" in src
        return
    harness = """
const src = require('fs').readFileSync(process.argv[1], 'utf8').replace(/^export const meta/m, 'const meta');
const run = async (picks) => {
  const f = new Function('args', 'agent', 'pipeline', 'phase', 'log', 'return (async()=>{' + src + '})()');
  try { await f({today: 'd', round_dir: '/r', picks}, async () => ({}), async () => [], () => {}, () => {}); return 'ran' }
  catch (e) { return 'threw' }
};
(async () => console.log([
  await run([{file: 'f', company: 'A', slug: 'a', ask_first: ['Looker']}]),
  await run([{file: 'f', company: 'A', slug: 'a'}]),
  await run([{file: 'f', company: 'A', slug: 'a', ask_first: ['Looker'], skills_no: ['looker']}]),
].join(' ')))();
"""
    out = subprocess.run(["node", "-e", harness,
                          os.path.join(ROOT, ".claude", "workflows", "draft-applications.js")],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
    assert out == "threw threw ran"


def test_a_rendered_resume_and_letter_carry_the_answers_and_pass_the_check(tmp_path, monkeypatch):
    import render_application as R
    monkeypatch.setattr(R.gen.docpaths, "resume_tex", lambda abbr: str(tmp_path / "cv" / "r.tex"))
    monkeypatch.setattr(R.gen.docpaths, "letter_tex",
                        lambda abbr: str(tmp_path / "cover_letters" / "l.tex"))
    for sub in ("cv", "cover_letters"):
        (tmp_path / sub).mkdir()
    a = {"company": "Kestrel Mutual", "role": "Operations Analyst", "abbr": "KestrelMutual",
         "summary": "Operations analyst who builds weekly demand forecasts that move stock.",
         "tools": "SQL, Python", "posting": POSTING + " Configure SAP ABAP reports.",
         "p1": "Claims come in waves.", "p2": "Kestrel Mutual insures homes.", "lead": "Where:",
         "cl_bullets": [{"label": "Forecasting", "text": "Weekly forecasts across 2,400 SKUs."}],
         "p4": "I am based in Manchester.", "consented_skills": ["Looker", "SAP ABAP"],
         "declined_skills": ["Spark"]}
    d = R.build(a)
    R.resume(d)
    R.letter(d)
    resume = (tmp_path / "cv" / "r.tex").read_text(encoding="utf-8")
    assert "Looker" in d["skills"] and "SAP ABAP" in d["skills"] and "Spark" not in d["skills"]
    assert "% Claimed with the candidate's yes: Looker, SAP ABAP" in resume
    assert "% The candidate said no to: Spark" in resume
    assert "% The candidate said no to: Spark" in (tmp_path / "cover_letters" / "l.tex").read_text()
    assert not [f for f in check_claims.check(str(tmp_path / "cv" / "r.tex"))
                if f[1] in ("unheld-skill", "declined-skill")]
    # With no answers the documents read exactly as before: no header line at all.
    plain = R.build({k: v for k, v in a.items() if k not in ("consented_skills", "declined_skills")})
    assert plain["consent"] == "" and "Looker" not in plain["skills"]
