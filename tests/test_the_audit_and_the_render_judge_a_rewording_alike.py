"""The code audit and the render judge a reworded bullet the same way.

The maintainer, 2026-11-05: the code audit's rewording guard passed a spreadsheet tool in a
bullet, and fit_to_page then refused the same bullet as unrelated, so the resume printed the
profile's own bullet after both audits had passed the reworded one. fit_to_page has no judge
of its own: it renders through render_application, which asks bullet_rewording.usable. What
differed was what each side handed the guard: the audit read the person's answers from the
pick and the posting from the pick's file, the renderer read the draft's own fields, and a
kept draft.json re-rendered without its posting had no held skill at all. Now both read one
function (bullet_rewording.answers), and a held skill is the person's own whether or not the
posting text is to hand.

The candidate is the example person (profile.example), in the copy the held-skill test uses
(BigQuery held, a detail naming Google Analytics), with one more detail line naming Excel at
Oakmere Foods; the employer and the posting are the invented ones in
tests/fixtures/drafting_round.json.
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import bullet_rewording  # noqa: E402
import fit_to_page  # noqa: E402
import render_application as R  # noqa: E402
import stage_picks  # noqa: E402

from test_a_held_skill_is_named_in_the_work import (  # noqa: E402,F401
    FORECAST_BQ, POSTING, _model, _rendered, held, make_round)

EXCEL_DETAIL = "- Kept the planners' stock-cover workbook in Excel\n"
AUTOMATE_XL = ("Automated the weekly stock-cover report in Python and Excel, saving the "
               "planning team about four hours a week")
ROUTING_XL = ("Designed a route-consolidation model in Excel for regional deliveries that "
              "removed 9% of weekly van miles, adopted by the transport planning team across "
              "the North West")
JOBS = [{"employer": "Brindle & Hart Logistics", "bullets": ["BH_FORECAST", "BH_PIPE", "BH_ROUTING"]},
        {"employer": "Oakmere Foods", "bullets": ["OF_WASTE", "OF_AUTOMATE"]},
        {"employer": "Saltmarsh Analytics", "bullets": ["SALT_FORECAST"]}]
CASES = {
    # Excel is held, the posting names it, and the profile names it at Oakmere Foods.
    "profile": {"id": "OF_AUTOMATE", "skill": "Excel", "text": AUTOMATE_XL},
    # BigQuery is held and a cloud data warehouse: sql work.
    "theme": {"id": "BH_FORECAST", "skill": "BigQuery", "text": FORECAST_BQ},
    # A route model is no spreadsheet, and the profile never puts Excel there.
    "unrelated": {"id": "BH_ROUTING", "skill": "Excel", "text": ROUTING_XL},
}


@pytest.fixture
def excel_at_oakmere(held):  # noqa: F811  the fixture, imported above
    prof = held / "01-candidate-profile.md"
    text = prof.read_text(encoding="utf-8")
    at = text.index("- Automated the weekly stock-cover report")
    end = text.index("\n", at) + 1
    prof.write_text(text[:end] + "\n**Additional detail available for tailoring:**\n"
                    + EXCEL_DETAIL + text[end:], encoding="utf-8")
    return held


def _posting():
    return POSTING + "\n- Excel for the planners' workbooks\n"


@pytest.mark.parametrize("case", sorted(CASES))
def test_what_the_audit_passes_the_render_prints_and_nothing_else(tmp_path, excel_at_oakmere,
                                                                  monkeypatch, case):
    import test_a_held_skill_is_named_in_the_work as H
    monkeypatch.setattr(H, "POSTING", _posting())
    rw = CASES[case]
    rd, _pick = make_round(tmp_path, [rw])
    [r] = stage_picks.audit(str(rd))
    refused = [f for f in r["mechanical"]["findings"]
               if f["field"] == f"bullet_rewordings ({rw['id']})"]
    assert bool(refused) == (case == "unrelated"), r["mechanical"]["findings"]
    # Where the skill is named, up to the figures (a currency prints as the profile's macro).
    printed = R.clean(rw["text"])[:70]

    # The draft as assembled, with its posting.
    d = dict(json.loads((rd / "draft_kestrel_mutual.json").read_text(encoding="utf-8")),
             posting=_posting(), abbr="Kestrel", jobs=copy.deepcopy(JOBS))
    assert (printed in _rendered(d)) == (not refused), case

    # The same draft kept and rendered again by fit_to_page with no posting text beside it.
    kept = tmp_path / "kept" / "draft.json"
    kept.parent.mkdir()
    kept.write_text(json.dumps([{k: v for k, v in d.items() if k != "posting"}]),
                    encoding="utf-8")
    [again], _read_in = fit_to_page.load(str(kept))
    assert "posting" not in again
    use, why = bullet_rewording.usable(again)
    assert (rw["id"] in use) == (not refused), why
    assert (printed in _rendered(again)) == (not refused), case


def test_both_sides_read_the_answers_from_one_place():
    a = {"consented_skills": ["Looker"], "declined_skills": ["SAP"], "posting": POSTING,
         "company": "Kestrel Mutual"}
    pick = {"skills_yes": ["Looker"], "skills_no": ["SAP"], "company": "Kestrel Mutual"}
    assert bullet_rewording.answers(a) == bullet_rewording.answers(a, pick, POSTING)
