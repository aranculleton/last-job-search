"""A skill the person says yes to can be named in a resume bullet, for that resume only.

A yes from `stage_picks.py consent` reached the skills line, and the summary or the letter
where the posting asks, while every bullet came unchanged from the profile. So a skill just
claimed sat on the skills line with no work beside it that used it. A draft now carries
`bullet_rewordings`: a few of the allocated bullets, each the same bullet with the yes named
where the work plausibly used it. The renderer prints them on that application's resume and
nowhere else, the kept draft.json carries them so a re-render reproduces them, and the
profile is never written.

The guard (tools/bullet_rewording.py) is code, run by the audit and again by the renderer:
the numbers stay the same, a tool the work used is never replaced, nothing is added but the
yes and a linking word, only this application's yes, and only into work the skill's tool
family, theme or bridge touches.

The candidate is the example person (profile.example); the employer, the posting and the
research are the invented ones in tests/fixtures/drafting_round.json.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import bullet_library  # noqa: E402
import bullet_rewording  # noqa: E402
import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
import person  # noqa: E402
import render_application as R  # noqa: E402
import stage_picks  # noqa: E402
import untrusted  # noqa: E402

from test_one_drafting_call_per_posting import FIXTURE, SLUG, store_pages  # noqa: E402

# The fixture's posting, asking for Looker beside Power BI: Looker is a dashboard tool the
# example person does not list, so staging asks about it, and they said yes.
POSTING = FIXTURE["posting"].replace("- Power BI reporting for operations leaders",
                                     "- Power BI or Looker reporting for operations leaders")
YES, NO = ["Looker"], ["SAP"]
REPORT = ("Owned the Power BI service-level reporting used by 30+ operations managers, "
          "replacing eleven spreadsheets with one governed dataset")
REWORDED = ("Owned the Power BI and Looker service-level reporting used by 30+ operations "
            "managers, replacing eleven spreadsheets with one governed dataset")
GOOD = {"id": "BH_REPORT", "skill": "Looker", "text": REWORDED}


def _profile_digest() -> str:
    h = hashlib.sha256()
    base = os.path.dirname(person.path("bullets.py"))
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name)
        if os.path.isfile(p):
            h.update(name.encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def make_round(tmp_path, rewordings=None, yes=YES, no=NO):
    store_pages()
    rd = tmp_path / "r1"
    (rd / "picks").mkdir(parents=True, exist_ok=True)
    f = rd / "picks" / f"01_{SLUG}.md"
    f.write_text(f"# {FIXTURE['company']} | {FIXTURE['role']}\n\n" + untrusted.fence(POSTING)
                 + "\n", encoding="utf-8")
    pick = {"file": str(f), "company": FIXTURE["company"], "role": FIXTURE["role"],
            "slug": SLUG, "abbr": FIXTURE["abbr"], "ask_first": ["Looker", "SAP"],
            "skills_yes": list(yes), "skills_no": list(no)}
    (rd / "picks.json").write_text(json.dumps([pick]), encoding="utf-8")
    (rd / f"research_{SLUG}.json").write_text(json.dumps(FIXTURE["research"]), encoding="utf-8")
    d = dict(copy.deepcopy(FIXTURE["draft"]), pack_hash=draft_pack.rules_hash())
    if rewordings is not None:
        d["bullet_rewordings"] = rewordings
    (rd / f"draft_{SLUG}.json").write_text(json.dumps(d), encoding="utf-8")
    return rd


def _model(rd, rulings=()):
    base = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    (rd / f"model_audit_{SLUG}.json").write_text(json.dumps({
        "verdict": "pass", "draft": base, "changes": [], "residual_risks": [],
        "rulings": list(rulings), "audited_md5": draft_audit.md5(base),
        "rules_hash": draft_pack.rules_hash()}), encoding="utf-8")


def _rendered(a) -> str:
    os.makedirs(person.state("cv"), exist_ok=True)
    path = R.resume(R.build(copy.deepcopy(a)))
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _draft(rewordings=None, yes=YES, no=NO, **extra) -> dict:
    a = dict(copy.deepcopy(FIXTURE["draft"]), posting=POSTING, abbr=FIXTURE["abbr"],
             letter_date="1 October 2026", consented_skills=list(yes), declined_skills=list(no),
             jobs=[{"employer": "Brindle & Hart Logistics",
                    "bullets": ["BH_FORECAST", "BH_PIPE", "BH_REPORT", "BH_ROUTING"]},
                   {"employer": "Oakmere Foods", "bullets": ["OF_WASTE", "OF_SUPPLIER"]},
                   {"employer": "Saltmarsh Analytics", "bullets": ["SALT_DASH"]}])
    a.update(extra)
    if rewordings is not None:
        a["bullet_rewordings"] = rewordings
    return a


# ------------------------------------------------------------------ the real path

def test_the_pack_offers_the_bullets_a_yes_belongs_in_and_no_others(tmp_path):
    rd = make_round(tmp_path)
    draft_pack.build(str(rd))
    args = json.loads((rd / "draft_args.json").read_text(encoding="utf-8"))
    brief = args["picks"][0]["brief"]
    assert "bullet_rewordings" in args["pack"]
    offered = [x for x in brief.splitlines() if x.startswith("- BH_") or x.startswith("- OF_")
               or x.startswith("- SALT_")]
    assert offered and all("may name Looker" in x for x in offered)
    # Looker is a dashboard tool: offered for the Power BI reporting, never for a model.
    assert any(x.startswith("- BH_REPORT ") for x in offered)
    assert not any(x.startswith("- BH_ROUTING ") or x.startswith("- BH_FORECAST ")
                   for x in offered)
    # With no yes, nothing is offered.
    rd2 = make_round(tmp_path / "none", yes=())
    draft_pack.build(str(rd2))
    brief2 = json.loads((rd2 / "draft_args.json").read_text(encoding="utf-8"))["picks"][0]["brief"]
    assert "Resume bullets you may reword" not in brief2


def test_a_yes_in_related_work_passes_both_audits_and_prints_on_that_resume_only(tmp_path):
    before = _profile_digest()
    library = dict(bullet_library.TEXT)
    rd = make_round(tmp_path, [GOOD])
    [r] = stage_picks.audit(str(rd))
    mech = r["mechanical"]
    assert not [f for f in mech["findings"] if f["rule"].startswith("rewording:")], mech["findings"]
    # Code passes it; whether the work plausibly used Looker is the model auditor's ruling.
    [flag] = [f for f in mech["flags"] if f["flag"] == "reworded-bullet"]
    assert flag["field"] == "bullet_rewordings (BH_REPORT)" and "Power BI" in flag["detail"]
    assert "RESUME BULLETS REWORDED FOR A YES" in draft_audit.packet(str(rd), SLUG)
    _model(rd)
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model"        # the flag is not ruled on yet
    _model(rd, [{"sentence": REWORDED, "flag": "reworded-bullet", "ruling": "supported"}])
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "pass", r["mechanical"]
    [d], missing, rejected = stage_picks.assemble(str(rd))
    assert not missing and not rejected
    assert d["bullet_rewordings"] == [GOOD] and d["consented_skills"] == YES
    # Rendered: the reworded bullet on this resume, the library's own on another's.
    d["jobs"] = _draft()["jobs"]
    tex = _rendered(d)
    assert "Owned the Power BI and Looker service-level reporting used by 30+ operations" in tex
    assert "Owned the Power BI service-level reporting" not in tex
    other = _rendered(_draft(company="Larkspur Casino Group", abbr="Larkspur"))
    assert "Owned the Power BI service-level reporting used by 30+ operations" in other
    assert "Looker service-level" not in other
    # The kept draft.json carries it, and a render from it reproduces it.
    import fit_to_page
    import outreach
    outreach.write(dict(d, posting=POSTING), {}, "2026-10-26")
    kept = os.path.join(outreach.folder(d), "draft.json")
    [again], _read_in = fit_to_page.load(kept)
    assert again["bullet_rewordings"] == [GOOD]
    assert _rendered(again) == tex
    # Nothing reached the profile.
    assert _profile_digest() == before and bullet_library.TEXT == library


# ------------------------------------------------------------------ what the guard refuses

REFUSED = {
    # A number changed: 30+ managers became 40+.
    "numbers": {"id": "BH_REPORT", "skill": "Looker",
                "text": REWORDED.replace("30+", "40+")},
    # The tool the work used at Saltmarsh Analytics replaced by the yes.
    "tool-replaced": {"id": "SALT_DASH", "skill": "Looker",
                      "text": "Built client-facing Looker dashboards for a regional bus "
                              "operator's punctuality data"},
    # A skill nobody said yes to for this application.
    "unconsented-skill": {"id": "BH_REPORT", "skill": "Looker",
                          "text": REWORDED.replace("Power BI and Looker",
                                                   "Power BI, Looker and Qlik")},
    # A yes put into work it clearly had nothing to do with: a route model is no dashboard.
    "unrelated": {"id": "BH_ROUTING", "skill": "Looker",
                  "text": "Designed a route-consolidation model in Looker for regional "
                          "deliveries that removed 9% of weekly van miles, adopted by the "
                          "transport planning team across the North West"},
    # A no, named anyway.
    "declined-skill": {"id": "BH_REPORT", "skill": "Looker",
                       "text": REWORDED.replace("Power BI and Looker", "Power BI, Looker and SAP")},
    # A qualifier taken out escalates the claim.
    "words-dropped": {"id": "BH_REPORT", "skill": "Looker",
                      "text": REWORDED.replace("one governed dataset", "one dataset")},
}


@pytest.mark.parametrize("rule", sorted(REFUSED))
def test_the_guard_refuses_it_in_the_audit_and_the_renderer_never_prints_it(tmp_path, rule):
    bad = REFUSED[rule]
    rd = make_round(tmp_path, [bad])
    [r] = stage_picks.audit(str(rd))
    rules = {f["rule"] for f in r["mechanical"]["findings"]}
    assert f"rewording:{rule}" in rules, r["mechanical"]["findings"]
    # Even a model auditor's pass cannot send it: a rule is still broken.
    _model(rd, [{"sentence": bad["text"], "flag": "reworded-bullet", "ruling": "supported"}])
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model"
    drafts, missing, _ = stage_picks.assemble(str(rd))
    assert drafts == [] and missing
    # A draft.json edited by hand to carry it renders the profile's own bullet instead.
    tex = _rendered(_draft([bad]))
    assert R.clean(bad["text"]) not in tex
    original = bullet_rewording.original(bad["id"])
    assert original in tex


def test_only_a_few_and_only_with_a_yes():
    two = [{"id": b, "skill": "Looker", "text": t} for b, t in (
        ("BH_REPORT", REWORDED),
        ("SALT_DASH", "Built client-facing Tableau and Looker dashboards for a regional bus "
                      "operator's punctuality data"))]
    assert bullet_rewording.problems(two, YES, NO) == []
    over = two + [dict(two[0], id=f"X{i}") for i in range(2)]
    assert "too-many" in {p["rule"] for p in bullet_rewording.problems(over, YES, NO)}
    assert {p["rule"] for p in bullet_rewording.problems([GOOD], [], NO)} == {"no-yes"}
    # Another application's yes is not this one's.
    assert "names-no-yes" in {p["rule"] for p in bullet_rewording.problems([GOOD], ["Snowflake"])}


def test_with_no_rewording_the_documents_are_exactly_what_they_were():
    plain = _rendered(_draft())
    assert _rendered(_draft([])) == plain
    # A rewording that changes nothing prints the profile's own text, byte for byte.
    same = {"id": "BH_REPORT", "skill": "Looker", "text": REPORT}
    assert "names-no-yes" in {p["rule"] for p in bullet_rewording.problems([same], YES)}
    assert _rendered(_draft([same])) == plain
    # The profile's own currency macro is written back where its bullet uses one.
    forecast = {"id": "BH_FORECAST", "skill": "Snowflake",
                "text": "Built weekly demand-forecasting models in Python, SQL and Snowflake "
                        "across 2,400 SKUs and 6 distribution centres, cutting forecast error "
                        "from 22% to 14% and freeing an estimated £1.1M of safety stock"}
    assert bullet_rewording.problems([forecast], ["Snowflake"]) == []
    tex = _rendered(_draft([forecast], yes=["Snowflake"]))
    assert r"in Python, SQL and Snowflake across 2,400 SKUs" in tex
    assert r"freeing an estimated \pounds{}1.1M of safety stock" in tex
