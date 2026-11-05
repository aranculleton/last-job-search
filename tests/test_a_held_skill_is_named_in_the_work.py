"""A skill the profile holds goes into the bullets, not only the skills line, without asking.

A skill the person said yes to for one application could be named in up to three of its
resume bullets (bullet_rewordings, tools/bullet_rewording.py). A skill the profile already
holds, declared in skills.py, never could: the guard took only a yes, so a posting naming a
held skill put it on the skills line alone, with no work beside it that used it. The
maintainer, 2026-11-04: "If I say yes to a skill, we aren't just dumping it at the bottom,
we're integrating it into existing bullet points without needing to ask me exact specifics,
and inferring where I would've used it for each role."

So a held skill the posting names is the person's standing yes: the pack lists the bullets
it belongs in and tells the drafter to write them without asking, the guard accepts it
under the same rules (numbers, every tool kept, nothing else added, related work), the
model auditor is told it is permission and not an ungrounded claim, and the code audit
fails a resume that leaves it on the skills line alone while a bullet could take it.

And a held skill can go where the profile itself puts it: the guard refused a tool in a
bullet at the very employer whose section of the candidate profile says the work used it,
because no tool family, theme or bridge tied them (the maintainer's case: two product
analytics tools in a growth bullet, a model-explanation library in a risk-scoring bullet).
What the profile names at an employer is now always related to that employer's bullets.

The candidate is the example person (profile.example), in a copy given BigQuery as held and
a detail line naming a tool at one employer; the employer, the posting and the research
are the invented ones in tests/fixtures/drafting_round.json.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import bridges  # noqa: E402
import bullet_rewording  # noqa: E402
import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
import person  # noqa: E402
import render_application as R  # noqa: E402
import skills_block  # noqa: E402
import stage_picks  # noqa: E402
import untrusted  # noqa: E402

from test_one_drafting_call_per_posting import FIXTURE, SLUG, store_pages  # noqa: E402

BIGQUERY = ("eng", "BigQuery", r"\bbig\s?query\b")
POSTING = FIXTURE["posting"].replace("- Strong SQL and Python",
                                     "- Strong SQL and Python, with BigQuery")
FORECAST = ("Built weekly demand-forecasting models in Python and SQL across 2,400 SKUs and 6 "
            "distribution centres, cutting forecast error from 22% to 14% and freeing an "
            "estimated £1.1M of safety stock")
FORECAST_BQ = FORECAST.replace("in Python and SQL", "in Python, SQL and BigQuery")
PIPE_BQ = ("Rebuilt the warehouse-management data feed as scheduled dbt models on BigQuery "
           "with data-quality tests, ending a daily two-hour manual reconciliation")
REWORDED = [{"id": "BH_FORECAST", "skill": "BigQuery", "text": FORECAST_BQ},
            {"id": "BH_PIPE", "skill": "BigQuery", "text": PIPE_BQ}]
# A detail the example person's profile gains in the copy: the graduate job's footfall work
# was read from a product analytics tool that no bullet of theirs names.
DETAIL = ("\n**Additional detail available for tailoring:**\n"
          "- Read each client's store footfall and web visits in Google Analytics\n")
SALT_GA = ("Delivered footfall forecasts for three retail clients using Google Analytics as "
           "part of a graduate consulting team, presenting results to client operations leads")


def _fresh():
    person._modules.clear()
    person._data.clear()
    bullet_rewording.vocabulary.cache_clear()
    getattr(bullet_rewording, "_WORK", {}).clear()     # the profile_work cache


@pytest.fixture
def held(tmp_path, monkeypatch):
    """The example person in a copy of their own, holding BigQuery (skills.py ITEMS) and
    with a detail line naming Google Analytics at Saltmarsh Analytics. The tools that read
    the inventory once, at import, are pointed at the copy's."""
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d,
                    ignore=shutil.ignore_patterns("state"))
    with open(d / "skills.py", "a", encoding="utf-8") as fh:
        fh.write(f"\nITEMS.append({BIGQUERY!r})\n")
    prof = d / "01-candidate-profile.md"
    text = prof.read_text(encoding="utf-8")
    at = text.index("- Built Tableau dashboards for a regional bus operator")
    end = text.index("\n", at) + 1
    prof.write_text(text[:end] + DETAIL + text[end:], encoding="utf-8")
    monkeypatch.setenv(person.ENV, str(d))
    _fresh()
    items = list(person.module("skills").ITEMS)
    assert BIGQUERY in items
    monkeypatch.setattr(skills_block, "ITEMS", items)
    monkeypatch.setattr(bridges, "_HELD_RX", [(i, re.compile(p, re.I)) for _c, i, p in items])
    yield d
    monkeypatch.undo()
    _fresh()


def make_round(tmp_path, rewordings=None):
    store_pages()
    rd = tmp_path / "r1"
    (rd / "picks").mkdir(parents=True, exist_ok=True)
    f = rd / "picks" / f"01_{SLUG}.md"
    f.write_text(f"# {FIXTURE['company']} | {FIXTURE['role']}\n\n" + untrusted.fence(POSTING)
                 + "\n", encoding="utf-8")
    # Staged as stage does it: what it would ask about is what bridges finds unheld.
    asked = [x["skill"] for x in stage_picks.to_ask(POSTING)]
    pick = {"file": str(f), "company": FIXTURE["company"], "role": FIXTURE["role"],
            "slug": SLUG, "abbr": FIXTURE["abbr"], "ask_first": asked, "skills_no": asked}
    (rd / "picks.json").write_text(json.dumps([pick]), encoding="utf-8")
    (rd / f"research_{SLUG}.json").write_text(json.dumps(FIXTURE["research"]), encoding="utf-8")
    d = dict(copy.deepcopy(FIXTURE["draft"]), pack_hash=draft_pack.rules_hash())
    if rewordings is not None:
        d["bullet_rewordings"] = rewordings
    (rd / f"draft_{SLUG}.json").write_text(json.dumps(d), encoding="utf-8")
    return rd, pick


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


def _bullets(tex: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"\\item\s+(.+)", tex)]


# ------------------------------------------------------------------ note 2: held skills

def test_a_held_skill_the_posting_names_reaches_the_bullets_with_no_question(tmp_path, held):
    rd, pick = make_round(tmp_path)
    # No question: the profile holds it, so staging asks only about what it does not.
    assert "BigQuery" not in pick["ask_first"] and stage_picks.unanswered(pick) == []
    # The pack lists the bullets it belongs in, and says to write them without asking.
    draft_pack.build(str(rd))
    brief = json.loads((rd / "draft_args.json").read_text(encoding="utf-8"))["picks"][0]["brief"]
    assert "Held in the profile and named by the posting, on no chosen bullet yet: BigQuery" in brief
    assert "never ask" in brief
    assert bullet_rewording.held_named(POSTING) == ["SQL", "Python", "dbt", "Power BI",
                                                    "BigQuery"]
    offered = [x for x in brief.splitlines() if re.match(r"- [A-Z]+_[A-Z_]+ \(", x)]
    assert any(x.startswith("- BH_FORECAST ") and "may name BigQuery" in x for x in offered)
    # Only the held skill no chosen bullet names: SQL, Python, dbt and Power BI are in the
    # work already, so none of them is offered.
    assert not any(re.search(r"may name [^)]*\b(?:SQL|Python|dbt|Power BI)\b", x) for x in offered)

    # Left on the skills line alone, the code audit fails it.
    [r] = stage_picks.audit(str(rd))
    [miss] = [f for f in r["mechanical"]["findings"] if f["rule"] == "rewording:skill-not-in-work"]
    assert miss["text"] == "BigQuery" and "without asking" in miss["fix"]

    # Named in two bullets: code passes both, and the model auditor is told it is the
    # person's standing permission, with only the work to rule on.
    rd, pick = make_round(tmp_path / "named", REWORDED)
    [r] = stage_picks.audit(str(rd))
    mech = r["mechanical"]
    assert not [f for f in mech["findings"] if f["rule"].startswith("rewording:")], mech["findings"]
    flags = [f for f in mech["flags"] if f["flag"] == "reworded-bullet"]
    assert {f["field"] for f in flags} == {"bullet_rewordings (BH_FORECAST)",
                                           "bullet_rewordings (BH_PIPE)"}
    assert all("held in the profile, the person's standing yes, not an ungrounded claim"
               in f["detail"] for f in flags)
    packet = draft_audit.packet(str(rd), SLUG)
    assert "Held and named by the posting (the person's standing yes" in packet
    assert "never an ungrounded claim" in packet
    _model(rd, [{"sentence": FORECAST_BQ, "flag": "reworded-bullet", "ruling": "supported"},
                {"sentence": PIPE_BQ, "flag": "reworded-bullet", "ruling": "supported"}])
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "pass", r["mechanical"]
    [d], missing, rejected = stage_picks.assemble(str(rd))
    assert not missing and not rejected and "consented_skills" not in d

    # The resume: one to three of the profile's own bullets name it, and the skills line
    # still lists it.
    tex = _rendered(d)
    named = [b for b in _bullets(tex) if "BigQuery" in b]
    assert 1 <= len(named) <= 3, _bullets(tex)
    assert any("in Python, SQL and BigQuery across 2,400 SKUs" in b for b in named)
    skills = [ln for ln in tex.splitlines() if ln.startswith("\\blockline")]
    assert any("BigQuery" in ln for ln in skills), skills


def test_without_the_skill_held_the_same_rewording_is_refused(tmp_path):
    # The example person as shipped, who does not hold BigQuery: the same bullets are
    # unconsented, so the standing yes is what lets the audit accept the fix.
    rd, pick = make_round(tmp_path, REWORDED)
    [r] = stage_picks.audit(str(rd))
    rules = {f["rule"] for f in r["mechanical"]["findings"]}
    assert "rewording:unconsented-skill" in rules and "rewording:skill-not-in-work" not in rules
    assert bullet_rewording.held_named(POSTING) == ["SQL", "Python", "dbt", "Power BI"]


def test_a_held_skill_is_guarded_like_a_yes(held):
    hold = bullet_rewording.held_named(POSTING)
    assert bullet_rewording.problems(REWORDED, [], [], hold) == []
    # The same rules as a yes: a number changed, a tool replaced, a word added, unrelated work.
    bad = {
        "numbers": dict(REWORDED[0], text=FORECAST_BQ.replace("2,400", "2,600")),
        "tool-replaced": dict(REWORDED[0], text=FORECAST.replace("in Python and SQL",
                                                                 "in Python and BigQuery")),
        "words-added": dict(REWORDED[0], text=FORECAST_BQ.replace("BigQuery", "BigQuery at scale")),
        "unrelated": {"id": "BH_ROUTING", "skill": "BigQuery",
                      "text": "Designed a route-consolidation model on BigQuery for regional "
                              "deliveries that removed 9% of weekly van miles, adopted by the "
                              "transport planning team across the North West"},
    }
    for rule, rw in bad.items():
        assert rule in {p["rule"] for p in bullet_rewording.problems([rw], [], [], hold)}, rule
    # Another held skill's words come only with its whole name: a posting naming data quality
    # testing lends no "testing" to a bullet that names BigQuery alone.
    more = bullet_rewording.held_named(POSTING + "\nData quality testing is part of the job.")
    assert "data quality testing" in more
    lent = dict(REWORDED[0], text=FORECAST_BQ.replace("forecasting models", "forecasting testing models"))
    assert "words-added" in {p["rule"] for p in bullet_rewording.problems([lent], [], [], more)}
    # Only a held skill this posting names: one it does not name is not a standing yes here.
    elsewhere = FIXTURE["posting"]
    assert "unconsented-skill" in {p["rule"] for p in bullet_rewording.problems(
        REWORDED, [], [], bullet_rewording.held_named(elsewhere))}
    # And the renderer uses it only for a posting that names it.
    a = {"bullet_rewordings": REWORDED, "posting": POSTING, "company": FIXTURE["company"]}
    use, why = bullet_rewording.usable(a)
    assert set(use) == {"BH_FORECAST", "BH_PIPE"} and not why
    use, why = bullet_rewording.usable(dict(a, posting=elsewhere))
    assert use == {} and len(why) == 2


def test_a_held_skill_no_bullet_can_take_stays_on_the_skills_line_with_a_note(held):
    # Nothing on this page is work a held skill belongs to: it is said, never forced in.
    posting = "Our analysts work in BigQuery every day."
    problems, notes = bullet_rewording.unplaced(posting, ["BH_ROUTING"], [])
    assert problems == [] and notes == [
        "BigQuery stays on the skills line alone: no bullet on this resume is work the profile "
        "ties it to (its tool family, its themes, its bridges, or the profile naming it at "
        "that employer)"]
    # With every rewording spent on other bullets, it is a note too.
    spent = [dict(REWORDED[0], id=b) for b in ("X1", "X2", "X3")]
    problems, notes = bullet_rewording.unplaced(posting, ["BH_FORECAST"], spent)
    assert problems == [] and "3 bullets are reworded already" in notes[0]
    # A bullet that can take it, and room: a failure.
    problems, _ = bullet_rewording.unplaced(posting, ["BH_ROUTING", "BH_FORECAST"], [])
    assert [p["text"] for p in problems] == ["BigQuery"] and "BH_FORECAST" in problems[0]["fix"]
    # Named in a bullet already: nothing to say.
    assert bullet_rewording.unplaced(posting, ["BH_FORECAST"], REWORDED[:1]) == ([], [])


# ------------------------------------------------------------------ note 5: the profile's own word

def test_a_skill_goes_where_the_profile_itself_puts_it(held):
    # No family member, theme or bridge ties Google Analytics to the footfall forecasts;
    # the profile's own section for Saltmarsh Analytics does.
    why = bullet_rewording.related("Google Analytics", "SALT_FORECAST")
    assert why == "the candidate profile names Google Analytics in the work at Saltmarsh Analytics"
    rw = [{"id": "SALT_FORECAST", "skill": "Google Analytics", "text": SALT_GA}]
    assert bullet_rewording.problems(rw, ["Google Analytics"]) == []
    assert bullet_rewording.problems(rw, [], [], ["Google Analytics"]) == []
    # Only there: another employer's bullets are not tied by it.
    assert bullet_rewording.related("Google Analytics", "OF_AUTOMATE") == ""
    # The profile is read again when it changes.
    prof = held / "01-candidate-profile.md"
    prof.write_text(prof.read_text(encoding="utf-8").replace(DETAIL, "\n"), encoding="utf-8")
    assert bullet_rewording.related("Google Analytics", "SALT_FORECAST") == ""


def test_a_rewording_the_model_audit_removed_is_never_demanded_again(tmp_path, held):
    """The model auditor rules on whether the work plausibly used the skill, and removes a
    rewording where it did not. The code audit then failed the corrected draft for leaving
    the held skill on the skills line alone, so the drafter put it back, the auditor took it
    out, and the draft never passed. A skill whose rewording the model audit removed (or
    refused, by name) for this draft is a note on the skills line, never a finding."""
    rd, pick = make_round(tmp_path, REWORDED)
    base = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    draft_audit.write_verdict(str(rd), SLUG, {
        "verdict": "fixed", "draft": {"bullet_rewordings": []},
        "changes": [{"field": "bullet_rewordings", "before": FORECAST_BQ, "after": FORECAST,
                     "reason": "this forecasting work did not plausibly run on BigQuery"}],
        "residual_risks": [],
        "rulings": [{"sentence": FORECAST_BQ, "flag": "reworded-bullet", "ruling": "removed",
                     "why": "not plausible"},
                    {"sentence": PIPE_BQ, "flag": "reworded-bullet", "ruling": "removed",
                     "why": "not plausible"}],
        "audited_md5": draft_audit.md5(base), "rules_hash": draft_pack.rules_hash()})
    [r] = stage_picks.audit(str(rd))
    mech = r["mechanical"]
    assert not [f for f in mech["findings"] if f["rule"] == "rewording:skill-not-in-work"], \
        mech["findings"]
    assert any(n["text"] == "BigQuery" and "model audit" in n["fix"] for n in mech["notes"]), \
        mech["notes"]
    assert r["verdict"] == "fixed", mech
    # The record travels with the draft, so a later check of the kept draft agrees.
    final, _d, _m = draft_audit.final_draft(str(rd), SLUG)
    assert final.get("rewordings_refused") == ["BigQuery"]
    # A skill refused by name, with no rewording ever written, is a note the same way.
    probs, notes = bullet_rewording.unplaced(POSTING, ["BH_FORECAST", "BH_PIPE"], [],
                                             refused=["BigQuery"])
    assert not [p for p in probs if p["text"] == "BigQuery"]
    assert any(n.startswith("BigQuery stays on the skills line: the model audit") for n in notes)
