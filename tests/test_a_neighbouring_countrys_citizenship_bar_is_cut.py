"""A citizenship, residence or clearance bar is cut in the wording of the country that sets it,
the neighbouring country's as well as home's.

From one person's round (2026-11-16, issue #311): a federal agency's remote posting in the
neighbouring country said "You must be a U.S. Citizen to apply for this position". It passed
the screen and ranked at fit 72: the person's pattern, written by setup for home, held
"us citizen" without the dots. The wording now ships with the app, per country
(tools/markets/<cc>.json "status_words"), and the person's own pattern is added to. A
person who is a citizen of their own country is never cut for its citizenship. Every
posting here is invented.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The example person's market (home: the United Kingdom), with a neighbour added.
NEIGHBOUR = '''
LOCATION["neighbour"] = dict(
    states=set(), words=re.compile(r"\\b(united states|usa|us)\\b"), metros=re.compile(r"(?!x)x"),
    remote_reason="remote but anchored in the US; passes only if the employer hires from home",
    onsite_reason="on-site in the US")
'''
# A person who is a citizen of home: their pattern names only a clearance.
CITIZEN = '''
ELIGIBILITY = re.compile(r"\\b(sc|dv|security)[- ]?(cleared|clearance)\\b", re.I)
ELIGIBILITY_STATUS_TERMS = re.compile(r"(?!x)x")
'''
BODY = ("Kestrel Analytics is hiring a Data Analyst to join our remote team. You will build "
        "SQL and Python reporting for the planning team. ")
POSTINGS = {
    "dotted": BODY + "You must be a U.S. Citizen to apply for this position.",
    "citizens_of": BODY + "Candidates must be citizens of the United States.",
    "green_card": BODY + "Applicants must be a U.S. citizen or green card holder.",
    "clearance": BODY + "Must be eligible for a security clearance.",
    "home_national": BODY + "Applicants must be UK nationals.",
    "welcome": BODY + "We welcome applicants regardless of citizenship.",
}


def _cuts(tmp_path, extra: str) -> dict:
    """Each posting's eligibility cut, from text_screen in a process of its own reading the
    example profile with `extra` added to its search settings."""
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof)
    with open(prof / "search.py", "a", encoding="utf-8") as fh:
        fh.write(extra)
    script = (
        "import json, sys\n"
        f"sys.path.insert(0, {os.path.join(ROOT, 'tools')!r})\n"
        "import text_screen\n"
        "posts = json.loads(sys.argv[1])\n"
        "print(json.dumps({k: [c for c in text_screen.screen({'title': 'Data Analyst', "
        "'company': 'Kestrel Analytics', 'desc': v})['cuts'] if 'eligibility' in c] "
        "for k, v in posts.items()}))\n")
    got = subprocess.run([sys.executable, "-c", script, json.dumps(POSTINGS)],
                         capture_output=True, text=True, encoding="utf-8",
                         env=dict(os.environ, LJS_PROFILE=str(prof)))
    assert got.returncode == 0, got.stderr
    return json.loads(got.stdout.strip().splitlines()[-1])


def test_the_neighbours_citizenship_and_clearance_bars_are_cut_with_the_quote(tmp_path):
    cuts = _cuts(tmp_path, NEIGHBOUR)
    assert cuts["dotted"] and "You must be a U.S. Citizen to apply" in cuts["dotted"][0]
    assert cuts["citizens_of"] and "citizens of the United States" in cuts["citizens_of"][0]
    assert cuts["green_card"]
    assert cuts["clearance"] and "security clearance" in cuts["clearance"][0]
    # Home's own wording, a variant the person's pattern missed, for a status they lack.
    assert cuts["home_national"] and "UK nationals" in cuts["home_national"][0]
    assert cuts["welcome"] == []


def test_without_a_neighbour_its_citizenship_is_not_read(tmp_path):
    assert _cuts(tmp_path, "")["dotted"] == []


def test_a_citizen_of_home_is_never_cut_for_homes_citizenship(tmp_path):
    cuts = _cuts(tmp_path, NEIGHBOUR + CITIZEN)
    assert cuts["home_national"] == []
    assert cuts["dotted"] and cuts["clearance"]
