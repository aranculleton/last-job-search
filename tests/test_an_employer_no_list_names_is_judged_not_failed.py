"""An employer on none of the profile's lists is unjudged, not failing the bar.

From a person's repo on 2026-10-21: the bar scored a global bank, two other banks, a
financial-data firm and a fintech "none", because the person's tier lists were written for
another sector. "none" read as failing the bar, and the session would have left them out of
networking. The verdict now says when nobody has judged the employer, `judge` records a
judgement once, and every later verdict reads it.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import bar  # noqa: E402
import opportunity  # noqa: E402


@pytest.fixture
def judged_file(tmp_path, monkeypatch):
    f = tmp_path / "employers_judged.json"
    monkeypatch.setattr(bar, "_judged_path", lambda: str(f))
    bar._judged_cache.clear()
    yield f
    bar._judged_cache.clear()


def test_an_unlisted_employer_is_flagged_as_unjudged_never_as_failing(judged_file):
    v, why = bar.verdict("Oakmere Bank")
    assert v == bar.NONE                       # the verdict a person's own tests pin
    assert "not on your employer lists yet" in why and "never a reason to drop it" in why
    assert not bar.listed("Oakmere Bank")
    low = f"Salary: {bar.CUR}30,000 - {bar.CUR}36,000 a year"      # under the target band
    v, why = bar.verdict("Oakmere Bank", low)
    assert v == bar.NONE and "under the" in why and "not on your employer lists yet" in why


def test_a_judgement_is_kept_and_read_by_every_later_verdict(judged_file):
    said = bar.judge("Oakmere Bank", bar.PRESTIGE, "a global bank",
                     today="2026-10-21")
    assert "Oakmere Bank: prestige" in said
    assert bar.verdict("Oakmere Bank") == (
        bar.PRESTIGE, "judged 2026-10-21: a global bank")
    assert bar.clears("Oakmere Bank Ltd")        # the same employer, keyed
    assert bar.listed("Oakmere Bank")
    kept = json.loads(judged_file.read_text(encoding="utf-8"))
    assert list(kept.values())[0]["verdict"] == "prestige"
    bar.judge("Saltmarsh Analytics", bar.NONE, "a two-person design studio", today="2026-10-21")
    assert bar.verdict("Saltmarsh Analytics")[0] == bar.NONE
    assert bar.listed("Saltmarsh Analytics")                     # judged, so it says something


def test_the_profiles_own_lists_and_hard_rules_outrank_a_judgement(judged_file, monkeypatch):
    monkeypatch.setattr(opportunity, "TIER_1", {"oakmere bank"})
    bar.judge("Oakmere Bank", bar.NONE, "mistaken", today="2026-10-21")
    assert bar.verdict("Oakmere Bank")[0] == bar.PAY               # the tier list wins
    bar.judge("Oakmere Casino", bar.PAY, "pays well", today="2026-10-21")
    assert bar.verdict("Oakmere Casino")[0] == bar.EXCLUDED   # an excluded sector stays out


def test_a_judgement_needs_a_verdict_and_a_reason(judged_file, capsys):
    with pytest.raises(ValueError):
        bar.judge("Oakmere Bank", "great", "why")
    with pytest.raises(ValueError):
        bar.judge("Oakmere Bank", bar.PAY, "  ")
    assert bar.main(["judge", "Oakmere Bank", "great", "why"]) == 2
    assert "pay, prestige, signal or none" in capsys.readouterr().out
    assert not judged_file.exists()


def test_unjudged_lists_each_unknown_employer_in_a_shortlist_once(judged_file, tmp_path,
                                                                   capsys):
    rounds = tmp_path / "r7.json"
    rounds.write_text(json.dumps([
        {"company": "Oakmere Bank", "title": "Analyst"},
        {"company": "Oakmere Bank Ltd", "title": "Data Scientist"},
        {"company": "Saltmarsh Analytics", "title": "Analyst"},
        {"company": "Oakmere Casino", "title": "Analyst"},              # a hard rule names it
        {"title": "no employer"},
    ]), encoding="utf-8")
    assert bar.unjudged(str(rounds)) == ["Oakmere Bank", "Saltmarsh Analytics"]
    bar.judge("Saltmarsh Analytics", bar.SIGNAL, "design-led AI tools", today="2026-10-21")
    assert bar.main(["unjudged", str(rounds)]) == 0
    assert capsys.readouterr().out.split("\n")[0] == "Oakmere Bank"


def test_the_throttle_carries_the_judged_verdict_into_the_shortlist(judged_file):
    import throttle
    bar.judge("Oakmere Bank", bar.PRESTIGE, "a global bank", today="2026-10-21")
    row = {"id": "1", "title": "Data Scientist", "url": "https://jobs.example.com/1",
           "company": "Oakmere Bank", "priority": 80, "fit": 80, "desc": ""}
    kept, skipped = throttle.throttle([row], {}, {}, {}, "2026-10-21")
    assert skipped == [] and kept[0]["bar"] == "prestige"
    assert kept[0]["bar_reason"] == "judged 2026-10-21: a global bank"
