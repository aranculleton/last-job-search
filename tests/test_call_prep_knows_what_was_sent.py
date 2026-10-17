"""The call prep says what the rest of the search already holds about the employer.

Three things the repo held and the prep document never printed: a role open at the
contact's employer that the search scored well, with nothing applied for there; the
company fact the cover letter used and any gap it conceded, so the call matches what
the employer was already told; and the phrases the person has said never to use,
which the prep's own guidance could still put in their mouth. Each is added, never
in place of a line: a prep document only gains sourced lines.

Every person, employer and role here is invented; the candidate is the example person.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tools" / "network"))

import prep  # noqa: E402

TODAY = "2026-10-15"
CONTACT = {"name": "Juno Castellan", "company": "Oakmere Foods", "title": "Data Analyst"}
APPLICATION = {"company": "Oakmere Foods", "role": "Demand Planning Analyst", "status": "applied",
               "fit_rating": "78", "cv_file": "cv/Morgan_Ellis_CV_Oakmere.tex"}
ROUND = "documents/rounds/r7.json"
ROLES = [{"company": "Oakmere Foods", "title": "Demand Planning Analyst", "fit": 82, "source": ROUND},
         {"company": "Oakmere Foods", "title": "Pricing Analyst", "fit": 70, "source": ROUND},
         {"company": "Oakmere Foods", "title": "Warehouse Supervisor", "fit": 41, "source": ROUND}]
DRAFT_PATH = "documents/applications/oakmere_foods_demand_planning_analyst/draft.json"
DRAFT = {"company": "Oakmere Foods", "role": "Demand Planning Analyst", "abbr": "Oakmere",
         "p2": "Oakmere opened a second bakery site in Bolton this spring, the kind of capacity "
               "change I planned stock around at Brindle & Hart Logistics.",
         "concession": "Named once in p2 that my forecasting was in logistics, not food.",
         "_path": DRAFT_PATH}


def _lines(text, heading):
    body = text.split("## %s\n" % heading, 1)[1]
    return [line for line in body.split("\n## ", 1)[0].splitlines() if line.strip()]


def _is_subsequence(short, long):
    it = iter(long)
    return all(any(line == other for other in it) for line in short)


# ------------------------------------------------------------------ roles open there

def test_with_nothing_applied_for_the_roles_scored_70_or_more_are_named():
    text = prep.prep_markdown(CONTACT, open_roles=ROLES, today=TODAY)
    fit = _lines(text, "Fit, honestly")
    line = next(f for f in fit if f.startswith("- Open there"))
    assert "Demand Planning Analyst (82)" in line and "Pricing Analyst (70)" in line
    assert "Warehouse Supervisor" not in line
    assert line.endswith("(source: %s)" % ROUND)


def test_an_application_there_replaces_the_roles_line():
    text = prep.prep_markdown(CONTACT, application=APPLICATION, open_roles=ROLES, today=TODAY)
    assert "Open there" not in text


def test_no_role_good_enough_adds_nothing():
    text = prep.prep_markdown(CONTACT, open_roles=ROLES[2:], today=TODAY)
    assert text == prep.prep_markdown(CONTACT, today=TODAY)


def test_a_role_with_no_round_file_behind_it_is_refused():
    with pytest.raises(prep.Unsourced):
        prep.prep_markdown(CONTACT, open_roles=[dict(ROLES[0], source="")], today=TODAY)


def test_the_roles_come_from_the_newest_round_with_its_file_named(tmp_path):
    rounds = tmp_path / "documents" / "rounds"
    rounds.mkdir(parents=True)
    old, new = rounds / "r6.json", rounds / "r7.json"
    old.write_text(json.dumps([{"company": "Oakmere Foods", "title": "Old Role", "fit": 90}]))
    new.write_text(json.dumps([{"company": "Oakmere Foods plc", "title": "Pricing Analyst", "fit": 77},
                               {"company": "Saltmarsh Analytics", "title": "Analyst", "fit": 95}]))
    os.utime(old, (1, 1))
    roles, draft = prep.search_context(CONTACT, {}, str(tmp_path))
    assert draft is None
    assert [(r["title"], r["source"]) for r in roles] == [("Pricing Analyst", ROUND)]


# ------------------------------------------------------------------ what the letter said

def test_the_letter_fact_and_its_concession_are_printed_with_the_draft_as_source():
    text = prep.prep_markdown(CONTACT, application=APPLICATION, draft=DRAFT, today=TODAY)
    company = _lines(text, "The company")
    assert company[0].startswith("- not researched")
    assert company[-1] == "- **The letter told them:** %s (source: %s)" % (DRAFT["p2"], DRAFT_PATH)
    fit = _lines(text, "Fit, honestly")
    assert fit[-1] == "- **Conceded in the letter:** %s (source: %s)" % (DRAFT["concession"], DRAFT_PATH)


@pytest.mark.parametrize("none", ["", "None", "none.", "N/A", "No concession needed", "Nothing conceded"])
def test_a_letter_that_conceded_nothing_says_nothing_about_it(none):
    text = prep.prep_markdown(CONTACT, application=APPLICATION,
                              draft=dict(DRAFT, concession=none), today=TODAY)
    assert "Conceded in the letter" not in text


def test_a_draft_for_another_employer_is_refused():
    with pytest.raises(ValueError):
        prep.prep_markdown(CONTACT, application=APPLICATION,
                           draft=dict(DRAFT, company="Saltmarsh Analytics"), today=TODAY)


def test_the_draft_is_the_one_the_application_was_sent_with(tmp_path):
    folder = tmp_path / os.path.dirname(DRAFT_PATH)
    folder.mkdir(parents=True)
    kept = {k: v for k, v in DRAFT.items() if k != "_path"}
    (folder / "draft.json").write_text(json.dumps([kept]), encoding="utf-8")
    other = tmp_path / "documents" / "applications" / "oakmere_foods_pricing_analyst"
    other.mkdir(parents=True)
    (other / "draft.json").write_text(json.dumps([dict(kept, role="Pricing Analyst", abbr="OakmerePricing",
                                                       p2="A different letter.")]), encoding="utf-8")
    roles, draft = prep.search_context(CONTACT, APPLICATION, str(tmp_path))
    assert roles == () and draft["p2"] == DRAFT["p2"]
    assert draft["_path"].replace(os.sep, "/") == DRAFT_PATH


# ------------------------------------------------------------------ words they banned

def _banned(*phrases):
    return lambda line: [p for p in phrases if p.lower() in line.lower()]


def test_guidance_using_a_banned_phrase_is_flagged_and_kept():
    plain = prep.prep_markdown(CONTACT, today=TODAY)
    text = prep.prep_markdown(CONTACT, today=TODAY, never_say=_banned("plain and short"))
    tone = _lines(text, "Tone for this call")
    hit = next(i for i, line in enumerate(tone) if "Plain and short" in line)
    assert tone[hit + 1].startswith('  - careful: "plain and short" is wording you have said never')
    assert prep.LEARNED_SOURCE in tone[hit + 1]
    assert _is_subsequence(plain.splitlines(), text.splitlines())


def test_research_facts_are_not_screened_only_the_wording_is():
    research = {"company": "Oakmere Foods", "fetched_date": "2026-10-10",
                "facts": [{"claim": "Oakmere grew its remit to two sites", "url": "https://oakmere.example/a"}]}
    text = prep.prep_markdown(CONTACT, research, today=TODAY, never_say=_banned("remit"))
    company = _lines(text, "The company")
    assert not any("careful:" in line and "never to use" in line for line in company)
    ask = _lines(text, "Ask them")
    assert any("never to use" in line for line in ask)


def test_with_nothing_banned_the_document_is_unchanged():
    assert prep.prep_markdown(CONTACT, today=TODAY) \
        == prep.prep_markdown(CONTACT, today=TODAY, never_say=lambda line: [])


# ------------------------------------------------------------------ only ever gains lines

def test_every_addition_keeps_every_line_the_document_already_had():
    research = {"company": "Oakmere Foods", "fetched_date": "2026-08-01",
                "facts": [{"claim": "Oakmere runs two bakery sites", "url": "https://oakmere.example/b"}]}
    before = prep.prep_markdown(CONTACT, research, APPLICATION, today=TODAY,
                                never_say=lambda line: [])
    after = prep.prep_markdown(CONTACT, research, APPLICATION, today=TODAY, open_roles=ROLES,
                               draft=DRAFT, never_say=_banned("plain and short"))
    assert _is_subsequence(before.splitlines(), after.splitlines())
    added = [line for line in after.splitlines() if line not in before.splitlines()]
    assert len(added) == 3, added
    assert all("(source: " in line for line in added)


def test_a_top_level_caution_is_printed_with_the_prohibitions():
    import prep
    lines = prep._company_lines({"company": "Oakmere Foods", "fetched_date": "2099-01-01",
                                 "cautions": ["The merger is agreed, not closed: never say merged."]})
    assert any("Careful" in l and "never say merged" in l for l in lines)
