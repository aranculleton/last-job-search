"""What the code audit of a draft let through, each case held back now.

Found by a bug hunt on the drafting path, each on an invented draft for the example
person (profile.example), mutated one sentence at a time:

- The words "the profile uses" included its target sectors and rules, so a claim of work
  in a sector the person only wants ("models for manufacturing clients") passed.
- A `contact_person` nobody named became the letter's salutation. Then the same person
  written without an accent ("Renee" for the research's "Renée") was a different one.
- A gap volunteered in a phrasing outside two patterns ("my exposure ... is limited",
  "would be a new domain for me") went to render with nothing reading it.
- Then the wider shapes refused correct letters that describe other people or results:
  "reporting that let 30 managers get up to speed", "managers with little experience of
  SQL", "teams with limited exposure to the data". A gap is the candidate's own.
- Leadership and scope the source never gives ("I led a team of four analysts", "for the
  whole company") passed unless the source carried a hedge word.
- One draft with letter bullets as pairs crashed the audit of the whole batch.
- An opening one word off another letter's passed rule 9.
- The model auditor's packet left out the person's learned rules, and "profile changed"
  was settled by copying a hash the packet printed for it.
- Any networking reaction or search setting changed `rules_hash`, so every audited draft
  read as "audited against a profile that has changed".

Every employer, person and posting here is invented.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
import render_application as R  # noqa: E402
import stage_picks  # noqa: E402
from test_one_drafting_call_per_posting import FIXTURE, SLUG, make_round, store_pages  # noqa: E402

GOOD = FIXTURE["draft"]
PICK = {"company": FIXTURE["company"], "role": FIXTURE["role"], "slug": FIXTURE["slug"],
        "abbr": FIXTURE["abbr"], "ask_first": ["SAP"], "skills_no": ["SAP"], "skills_yes": []}
NONE = {"openings": set(), "closings": set()}
P1_SECOND = ("At Brindle & Hart Logistics I built the weekly demand-forecasting models in Python "
             "and SQL that cut forecast error from 22% to 14% across 2,400 SKUs.")
PIPE = ("Moved a manual daily reconciliation onto scheduled dbt models with tests, ending two "
        "hours of checking a day.")
P4_LAST = ("Which kinds of claim move most with the weather is the first thing I would want to "
           "look at in your data.")


def _edited(field, old, new, cites=None, d=None):
    d = copy.deepcopy(d or GOOD)
    if field.startswith("cl_bullets"):
        i = int(field[len("cl_bullets["):-1])
        assert old in d["cl_bullets"][i]["text"]
        d["cl_bullets"][i]["text"] = d["cl_bullets"][i]["text"].replace(old, new)
    else:
        assert old in d[field]
        d[field] = d[field].replace(old, new)
    for c in d["claim_map"]:
        if c["field"] == field and old in c["sentence"]:
            c["sentence"] = c["sentence"].replace(old, new)
            if cites is not None:
                c["cites"] = cites
    return d


def _audit(d, posting=None, research=None, corpus=NONE):
    store_pages()
    return draft_audit.mechanical(dict(d, pack_hash=d.get("pack_hash") or draft_pack.rules_hash()),
                                  PICK, FIXTURE["posting"] if posting is None else posting,
                                  FIXTURE["research"] if research is None else research,
                                  corpus=corpus)


def _flags(m):
    return {f["flag"] for f in m["flags"]}


def _rules(m):
    return {f["rule"].split(":")[0] for f in m["findings"]}


def test_a_sector_the_person_only_targets_is_not_their_vocabulary():
    # "manufacturing" is in the example's Target Sectors (profile/CLAUDE.md) and in no work
    # fact: claimed as work, through the posting's word, it is flagged.
    posting = FIXTURE["posting"].replace(
        "claims volumes", "claims volumes for our manufacturing and grocery clients")
    d = _edited("p1", P1_SECOND, P1_SECOND.replace("models in Python",
                                                    "models for manufacturing clients in Python"))
    m = _audit(d, posting=posting)
    assert any(f["flag"] == "posting-term" and "manufacturing" in f["detail"] for f in m["flags"])


@pytest.mark.parametrize("named,written", [
    ("Renée Thistlewood", "Renee Thistlewood"),
    ("Íñigo Ibarrondo", "Inigo Ibarrondo"),
    ("Søren Halvardsen", "Soren Halvardsen"),
    ("Zoë Quillfeather", "ZOE QUILLFEATHER"),
    ("Dr Łucja Wróbelska", "Lucja Wrobelska"),
])
def test_the_named_contact_is_the_same_person_with_or_without_accents(named, written):
    research = dict(copy.deepcopy(FIXTURE["research"]), named_contact=named)
    d = dict(copy.deepcopy(GOOD), contact_person=written)
    assert "contact" not in _rules(_audit(d, research=research)), (named, written)
    # Another person with the same surname is still someone else.
    other = dict(d, contact_person="Quenby " + written.split()[-1])
    assert "contact" in _rules(_audit(other, research=research))


def test_a_name_from_the_target_list_is_an_unknown_name_in_a_candidate_sentence(tmp_path,
                                                                              monkeypatch):
    dst = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), dst)
    with open(dst / "CLAUDE.md", "a", encoding="utf-8") as fh:
        fh.write("\n## Employers they love\n- Wrackenfold Retail\n")
    monkeypatch.setenv("LJS_PROFILE", str(dst))
    d = _edited("p1", "across 2,400 SKUs.", "across 2,400 SKUs for Wrackenfold Retail.")
    assert "unknown-name" in _flags(_audit(d))


def test_an_addressee_nobody_named_is_a_broken_rule():
    d = dict(copy.deepcopy(GOOD), contact_person="Ysolde Brackwater")
    m = _audit(d)
    assert "contact" in _rules(m)
    assert R.build(dict(copy.deepcopy(d), abbr="Kestrel", posting=FIXTURE["posting"]))[
        "salutation"].find("Brackwater") >= 0      # why it matters: it is the salutation
    named = dict(copy.deepcopy(FIXTURE["research"]), named_contact="Ysolde Brackwater")
    assert "contact" not in _rules(_audit(d, research=named))
    assert "contact" not in _rules(_audit(dict(copy.deepcopy(GOOD), contact_person="Dr Ysolde Brackwater"),
                                          research=named))


@pytest.mark.parametrize("gap", [
    "My exposure to insurance data so far is limited, but forecasting transfers well.",
    "Insurance would be a new domain for me, and I would learn it fast.",
    "I am keen to build my experience of claims data in this role.",
    "I haven't worked with claims data, and I would get up to speed quickly.",
])
def test_a_gap_volunteered_in_any_of_the_softer_shapes_is_a_broken_rule(gap):
    d = _edited("p4", P4_LAST, gap, cites=[])
    assert "letter" in _rules(_audit(d)), gap


@pytest.mark.parametrize("gap", [
    "I'm keen to build experience in insurance pricing.",
    "I have limited exposure to insurance data.",
    "I've had little experience with claims systems.",
    "With my limited exposure to insurance, I would lean on your claims team.",
    "Morgan's exposure to claims data is limited so far.",
    "I would quickly get up to speed on your claims data.",
])
def test_the_softer_shapes_said_of_the_candidate_are_still_caught(gap):
    d = _edited("p4", P4_LAST, gap, cites=[])
    assert "letter" in _rules(_audit(d)), gap


def _concessions(m):
    return [f for f in m["findings"] if "concession" in str(f.get("text") or "")]


@pytest.mark.parametrize("about_others", [
    P4_LAST[:-1] + ", so that your handlers get up to speed on a surge in minutes.",
    P4_LAST[:-1] + ", for claims handlers with little experience of SQL.",
    P4_LAST[:-1] + ", for teams with limited exposure to the data.",
    P4_LAST[:-1] + ", and your handlers have been keen to build their reporting skills.",
    P4_LAST[:-1] + ", because their experience of the weather data has been limited.",
])
def test_the_softer_shapes_said_of_other_people_are_not_a_concession(about_others):
    m = _audit(_edited("p4", P4_LAST, about_others))
    assert _concessions(m) == [], about_others


def test_the_close_written_for_the_role_is_still_clean():
    assert _audit(GOOD)["gate"] == "clean"


@pytest.mark.parametrize("claim", [
    "I led a team of four analysts who moved the daily reconciliation onto scheduled dbt models.",
    "I managed the dbt platform for the whole company, ending two hours of checking a day.",
    "I set the forecasting strategy and moved the daily reconciliation onto dbt.",
])
def test_leadership_or_scope_the_source_never_gives_is_flagged(claim):
    m = _audit(_edited("cl_bullets[1]", PIPE, claim, cites=["BH_PIPE"]))
    assert "scope-not-in-cited" in _flags(m), m["flags"]


def test_scope_the_source_does_give_is_not_flagged():
    # BH_REPORT says "used by 30+ operations managers": a manager counted, never managed.
    m = _audit(GOOD)
    assert "scope-not-in-cited" not in _flags(m)


def test_pair_form_letter_bullets_are_a_finding_and_the_rest_of_the_batch_is_audited(tmp_path):
    rd = make_round(tmp_path, slugs=(SLUG, "kestrel_two"))
    bad = json.loads((rd / "draft_kestrel_two.json").read_text(encoding="utf-8"))
    bad["cl_bullets"] = [[b["label"], b["text"]] for b in bad["cl_bullets"]]
    (rd / "draft_kestrel_two.json").write_text(json.dumps(bad), encoding="utf-8")
    first, second = stage_picks.audit(str(rd))
    assert first["mechanical"]["gate"] == "clean"
    assert "malformed" in {f["rule"] for f in second["mechanical"]["findings"]}


def test_an_opening_one_word_off_another_letters_is_held_back():
    opening = draft_audit.ends(GOOD)[0]
    d = _edited("p1", "Your claims handling teams staff ahead", "Your claims handling team staffs ahead")
    assert "rule-9" in _rules(_audit(d, corpus={"openings": {opening}, "closings": set()}))
    d = _edited("p1", "Your claims handling teams staff ahead", "Your claims handling desks staff ahead")
    m = _audit(d, corpus={"openings": {opening}, "closings": set()})
    assert "rule-9-near" in _flags(m)


def _profile_copy(tmp_path, monkeypatch):
    dst = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), dst)
    monkeypatch.setenv("LJS_PROFILE", str(dst))
    return dst


def _learn(dst, area, rule):
    (dst / "learned.json").write_text(json.dumps({"entries": [{
        "date": "2026-10-20", "area": area, "said": "their words", "rule": rule,
        "applied_to": [], "never_say": [], "status": "active"}]}), encoding="utf-8")


def test_a_networking_reaction_does_not_change_what_a_draft_was_written_against(tmp_path,
                                                                               monkeypatch):
    dst = _profile_copy(tmp_path, monkeypatch)
    before = draft_pack.rules_hash()
    _learn(dst, "people", "Stop suggesting recruiters as contacts.")
    assert draft_pack.rules_hash() == before
    (dst / "search.py").write_text((dst / "search.py").read_text(encoding="utf-8")
                                   + "\n# a comment a session added\n", encoding="utf-8")
    assert draft_pack.rules_hash() == before
    _learn(dst, "documents", "Never open a letter on a question.")
    assert draft_pack.rules_hash() != before


def test_the_packet_shows_what_changed_and_a_hash_alone_settles_nothing(tmp_path, monkeypatch):
    dst = _profile_copy(tmp_path, monkeypatch)
    rd = make_round(tmp_path)
    draft_pack.build(str(rd))
    _learn(dst, "documents", "Never open a cover letter by describing the employer's own team.")
    text = draft_audit.packet(str(rd), SLUG)
    assert "Never open a cover letter by describing the employer's own team." in text
    assert "+ rules: Never open a cover letter by describing" in text
    assert "[profile-changed]" in text
    # A model audit that copies the current hash and rules on nothing does not settle it.
    d = json.loads((rd / f"draft_{SLUG}.json").read_text(encoding="utf-8"))
    (rd / f"model_audit_{SLUG}.json").write_text(json.dumps({
        "verdict": "pass", "draft": d, "changes": [], "residual_risks": [], "rulings": [],
        "audited_md5": draft_audit.md5(d), "rules_hash": draft_pack.rules_hash()}),
        encoding="utf-8")
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "needs_model"
    assert [f["flag"] for f in r["mechanical"]["open_after_model"]] == ["profile-changed"]
    # A ruling on it, made against the profile as it stands, does.
    (rd / f"model_audit_{SLUG}.json").write_text(json.dumps({
        "verdict": "pass", "draft": d, "changes": [], "residual_risks": [],
        "rulings": [{"sentence": "", "flag": "profile-changed", "ruling": "supported",
                     "why": "the opening describes the problem, not their team"}],
        "audited_md5": draft_audit.md5(d), "rules_hash": draft_pack.rules_hash()}),
        encoding="utf-8")
    [r] = stage_picks.audit(str(rd))
    assert r["verdict"] == "pass"
