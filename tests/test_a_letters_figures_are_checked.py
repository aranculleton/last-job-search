"""Every figure in a cover letter traces to the profile, the employer fact or the posting.

`check_numbers.py` ran over the resumes only, so the letter's opening, its three
bullets and its close were free model text that nothing checked: a drafting
pass could turn "22% to 14%" into "22% to 10%" in a letter and every check
passed. The drafts mode reads the letter where it knows which paragraph is the
verified company fact (p2) and allows that, and the posting's own figures.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_numbers as CN  # noqa: E402


def _draft(**kw):
    return dict({
        "company": "Kestrel Mutual", "role": "Operations Analyst", "abbr": "KestrelMutual",
        "summary": "Operations analyst who cut forecast error from 22% to 14% across 2,400 SKUs.",
        "p1": "Claims come in waves. At Brindle & Hart I built forecasts for 2,400 SKUs.",
        "p2": "Kestrel Mutual handled 410,000 claims last year.",
        "lead": "Where I would start:",
        "cl_bullets": [{"label": "Forecasting", "text": "Cut forecast error from 22% to 14%."}],
        "p4": "I am based in Manchester and need no sponsorship.",
        "posting": "Join a team of 45 analysts handling claims.",
    }, **kw)


def test_a_grounded_letter_is_clean():
    assert CN.check_draft(_draft()) == []


def test_an_invented_figure_in_a_letter_bullet_is_found():
    found = CN.check_draft(_draft(cl_bullets=[{"label": "Forecasting",
                                               "text": "Cut forecast error from 22% to 10%."}]))
    assert [f["value"] for f in found] == ["10%"]
    assert found[0]["source"] == "KestrelMutual.cl_bullets[0]"


def test_the_company_fact_and_the_posting_may_be_repeated_but_nothing_else():
    ok = _draft(p1="Your 410,000 claims a year and a team of 45 analysts: I forecast at that scale.")
    assert CN.check_draft(ok) == []
    bad = _draft(p4="I would bring the 35% saving I delivered at Oakmere.")
    assert [f["source"] for f in CN.check_draft(bad)] == ["KestrelMutual.p4"]


def test_the_command_reads_a_drafts_file(tmp_path):
    path = tmp_path / "drafts.json"
    path.write_text(json.dumps([_draft(summary="Analyst who saved 35% of van miles.")]),
                    encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_numbers.py"),
                        "--drafts", str(path)], capture_output=True, text=True, cwd=ROOT,
                       env=dict(os.environ, LJS_PROFILE=os.path.join(ROOT, "profile.example")))
    assert r.returncode == 1, r.stdout + r.stderr
    assert "KestrelMutual.summary" in r.stdout and "35%" in r.stdout


def test_the_batch_checks_the_letters():
    with open(os.path.join(ROOT, "tools", "verify_batch.sh"), encoding="utf-8") as fh:
        script = fh.read()
    assert 'check_numbers.py" --drafts "$DRAFTS"' in script
