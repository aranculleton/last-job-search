"""The code audit of a draft catches every defect class the auditor agent was there to catch.

The workflow's auditor was an agent that re-read everything and re-ran the drafter's own
checks. `tools/draft_audit.py` runs those checks itself (voice_check, check_numbers,
check_claims, the letter checks, the budgets, rule 9, the outreach note) and reads the
drafter's claim map sentence by sentence against the evidence each sentence cites. Each
test here takes one invented draft that passes, breaks it the way real drafts have been
broken, and shows the audit holds it back; and that whatever the old checks found on the
broken draft, the new audit finds too.
"""
from __future__ import annotations

import copy
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
import voice_check  # noqa: E402

FIXTURE = json.load(open(os.path.join(ROOT, "tests", "fixtures", "drafting_round.json"),
                         encoding="utf-8"))
GOOD = FIXTURE["draft"]
sys.path.insert(0, os.path.join(ROOT, "tests"))
from test_one_drafting_call_per_posting import store_pages  # noqa: E402

store_pages()
PICK = {"company": FIXTURE["company"], "role": FIXTURE["role"], "slug": FIXTURE["slug"],
        "abbr": FIXTURE["abbr"], "ask_first": ["SAP"], "skills_no": ["SAP"], "skills_yes": []}
NONE = {"openings": set(), "closings": set()}


def audit(d, pick=PICK, corpus=NONE, research=None):
    d = dict(d)
    d.setdefault("pack_hash", draft_pack.rules_hash())
    return draft_audit.mechanical(d, pick, FIXTURE["posting"],
                                  FIXTURE["research"] if research is None else research,
                                  corpus=corpus)


def edited(field, old, new, cites=None):
    """GOOD with one sentence rewritten, in the field and in its claim-map entry."""
    d = copy.deepcopy(GOOD)
    if field.startswith("cl_bullets"):
        i = int(field[len("cl_bullets["):-1])
        assert old in d["cl_bullets"][i]["text"]
        d["cl_bullets"][i]["text"] = d["cl_bullets"][i]["text"].replace(old, new)
    else:
        assert old in d[field], (field, old)
        d[field] = d[field].replace(old, new)
    for c in d["claim_map"]:
        if c["field"] == field and old in c["sentence"]:
            c["sentence"] = c["sentence"].replace(old, new)
            if cites is not None:
                c["cites"] = cites
    return d


def rules(m):
    """Each rule broken, by its family ("claims") and by its own name ("declined-skill")."""
    return ({f["rule"].split(":")[0] for f in m["findings"]}
            | {f["rule"].split(":")[-1] for f in m["findings"]})


def flags(m):
    return {f["flag"] for f in m["flags"]}


def test_the_draft_the_tests_start_from_passes_with_nothing_for_the_model():
    m = audit(GOOD)
    assert m["gate"] == "clean", (m["findings"], m["flags"])
    assert draft_audit.parity(GOOD, FIXTURE["posting"], FIXTURE["research"], PICK)["old"] == []


SENTENCE_P2 = "Before that, at Oakmere Foods, I modelled shelf-life and order patterns for chilled lines, and write-offs fell 18% over two quarters."
OAKMERE = "write-offs fell 18% over two quarters"

DEFECTS = {
    # A figure the profile does not hold.
    "a fabricated number": (
        edited("cl_bullets[2]", "more than 30", "more than 45"), {"number"}, {"number-not-in-cited"}),
    # A metric moved to work it does not belong to: the profile's own rule and the claim map.
    "a metric on the wrong work": (
        edited("p2", OAKMERE, "cut forecast error from 22% to 14% over two quarters"),
        {"claims"}, {"number-not-in-cited"}),
    # A skill the profile records as not held, on the resume's skills line.
    "an unheld skill on the skills line": (
        dict(copy.deepcopy(GOOD), tools="SQL, Python, dbt, Power BI, SAP ABAP"),
        {"tools", "claims"}, set()),
    # A held skill attached to work whose text never mentions it.
    "a held skill on the wrong work": (
        edited("cl_bullets[2]", "in Power BI", "in Tableau"), set(), {"skill-not-in-cited"}),
    # An employer fact with no research behind it.
    "an unquoted employer fact": (
        edited("p2", "Kestrel Mutual looks after 1.2 million policyholders across home and motor.",
               "Kestrel Mutual grew its claims team by a third last year.", cites=[]),
        set(), {"possible-employer-fact", "p2-uncited"}),
    # A research fact restated with a different figure.
    "an employer figure the research does not hold": (
        edited("p2", "1.2 million", "1.5 million"), set(), {"number-not-in-cited"}),
    # A gap volunteered, in the contrast construction, naming a skill the person declined.
    "a volunteered gap": (
        edited("p4", "I am based in Manchester with settled status and full right to work in the UK, so no sponsorship is needed.",
               "I have not used SAP, but I have reported from the warehouse system behind it.", cites=[]),
        {"letter", "declined-skill"}, set()),
    # A verb stronger than the source ("as part of a team" became "led").
    "a stronger verb than the source": (
        edited("cl_bullets[1]", "Moved a manual daily reconciliation onto scheduled dbt models with tests, ending two hours of checking a day.",
               "I led the footfall forecasts for three retail clients at Saltmarsh Analytics.",
               cites=["SALT_FORECAST"]), set(), {"stronger-verb"}),
    # An ended role in the present tense.
    "an ended role in the present tense": (
        edited("cl_bullets[1]", "Moved a manual daily reconciliation onto scheduled dbt models with tests, ending two hours of checking a day.",
               "At Oakmere Foods I run the supplier segmentation that procurement reviews each quarter.",
               cites=["OF_SUPPLIER"]), set(), {"tense"}),
    # A qualifier on a figure dropped ("an estimated").
    "a dropped qualifier": (
        edited("cl_bullets[0]", "an estimated £1.1M", "£1.1M"), set(), {"qualifier-dropped"}),
    # The posting's domain claimed for adjacent work.
    "the posting's terms for adjacent work": (
        edited("cl_bullets[1]", "Moved a manual daily reconciliation onto scheduled dbt models with tests, ending two hours of checking a day.",
               "At Brindle & Hart Logistics I forecast claims volumes across six distribution centres.",
               cites=["BH_FORECAST"]), set(), {"posting-term"}),
    # A name nobody gave the drafter: a client, say.
    "a name from nowhere": (
        edited("p1", "across 2,400 SKUs.", "across 2,400 SKUs for Brackmoor Retail."),
        set(), {"unknown-name"}),
    # A candidate claim citing nothing.
    "an uncited claim": (
        edited("p2", SENTENCE_P2, SENTENCE_P2, cites=[]), set(), {"uncited-claim"}),
    # An id that is not in the pack.
    "an id that does not exist": (
        edited("cl_bullets[1]", "Moved", "Moved", cites=["BH_NOPE"]), set(), {"unknown-id"}),
}


@pytest.mark.parametrize("name", sorted(DEFECTS))
def test_each_defect_holds_the_draft_back(name):
    d, want_rules, want_flags = DEFECTS[name]
    m = audit(d)
    assert m["gate"] == "model", name
    assert want_rules <= rules(m), (name, m["findings"])
    assert want_flags <= flags(m), (name, m["flags"])


@pytest.mark.parametrize("name", sorted(DEFECTS))
def test_whatever_the_old_checks_found_the_new_audit_finds(name):
    d = DEFECTS[name][0]
    got = draft_audit.parity(d, FIXTURE["posting"], FIXTURE["research"], PICK)
    assert got["missed"] == [], got


def test_an_unheld_skill_in_the_letter_is_a_question_for_the_model_auditor():
    # check_claims only warns on a letter, where naming a requirement to bridge it is
    # allowed; whether the sentence claims it is judgment, so it goes to the model.
    pick = dict(PICK, ask_first=[], skills_no=[])
    d = edited("p1", "across 2,400 SKUs.", "across 2,400 SKUs, and configured SAP ABAP reports.")
    m = audit(d, pick=pick)
    assert "unheld-skill" in flags(m) and m["gate"] == "model"
    # The person's yes is their consent, not a defect.
    yes = audit(d, pick=dict(pick, skills_yes=["SAP ABAP"]))
    assert "unheld-skill" not in flags(yes)


def test_an_opening_or_closing_another_letter_has_breaks_rule_9():
    opening, closing = draft_audit.ends(GOOD)
    assert opening and closing
    m = audit(GOOD, corpus={"openings": {opening}, "closings": set()})
    assert [f["field"] for f in m["findings"] if f["rule"] == "rule-9"] == ["p1"]
    m = audit(GOOD, corpus={"openings": set(), "closings": {closing}})
    assert [f["field"] for f in m["findings"] if f["rule"] == "rule-9"] == ["p4"]
    # Compared the way voice_check --corpus compares the letters already sent.
    assert opening == voice_check.end_key(GOOD["p1"].split(". ")[0])


def test_a_sentence_missing_from_the_claim_map_is_unmapped():
    d = copy.deepcopy(GOOD)
    d["lead"] = "This is the work I know best. " + d["lead"]
    m = audit(d)
    assert [f["sentence"] for f in m["flags"] if f["flag"] == "unmapped"] == [
        "This is the work I know best."]


def test_a_reported_stretch_and_a_changed_profile_go_to_the_model():
    s = GOOD["claim_map"][5]["sentence"]
    m = audit(dict(copy.deepcopy(GOOD), stretches=[{"sentence": s, "why": "staffing is not stock"}]))
    assert "stretch" in flags(m) and m["gate"] == "model"
    m = audit(dict(copy.deepcopy(GOOD), pack_hash="0" * 16))
    assert "profile-changed" in flags(m) and m["gate"] == "model"


def test_a_research_caution_on_a_cited_fact_goes_to_the_model():
    research = copy.deepcopy(FIXTURE["research"])
    research["facts"][0]["caution"] = "the figure is from 2024"
    m = audit(GOOD, research=research)
    assert "caution" in flags(m)


def test_a_letter_bullet_that_repeats_the_resume_is_found_before_the_render():
    # verify_batch.sh finds this only after the PDFs exist. The allocator is code, so
    # the bullets the resume will carry are known before anything is rendered.
    d = edited("cl_bullets[2]", "I own the service-level reporting in Power BI that replaced eleven spreadsheets for more than 30 operations managers.",
               "I owned the Power BI service-level reporting used by 30+ operations managers.")
    m = audit(d)
    assert any(f["rule"] == "letter" and "repeats the resume" in f["text"] for f in m["findings"])
