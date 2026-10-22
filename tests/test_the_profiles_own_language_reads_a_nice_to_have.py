"""The profile's own language rows read a nice-to-have the way the second-language gate does.

A language the profile names in search.py LANGUAGE_GATE was cut whenever its row's
requirement pattern matched and its row's own nice-to-have pattern did not: "Fluency in
Welsh is a huge plus", "Bonus: fluent Welsh" and a language listed under "Nice to have:"
were all cut, while the same words passed for any other language. The screen's own
nice-to-have reading, in the clause that holds the language, and a nice-to-have heading
above it, now excuse it too; the row's own pattern still excuses it as well. "Welsh is
required", or a language under "Requirements:", still cuts. A saved ruling today's screen
would not make is released.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import text_screen  # noqa: E402

PAD = "\n\nYou will build demand forecasts in SQL and Python for our planning team." * 3
NICE = (
    "Fluency in {L} is a huge plus.",
    "Fluent {L} would be great.",
    "Bonus: fluent {L}.",
    "Fluency in {L} is preferred but not required.",
    "Fluency in {L} would be an advantage.",
    "Nice to have:\n- Fluency in {L}\n- Tableau",
    "Preferred qualifications:\n* Fluent {L}",
    "**Nice to have**\n- Fluent {L}",
)
REQUIRED = (
    "Fluency in {L} is essential.",
    "{L} is required.",
    "Requirements:\n- Fluency in {L}\nNice to have:\n- Tableau",
    "Must have:\n- Fluent {L}",
    "Fluency in {L} is required, and a degree in statistics is preferred.",
    "Nice to have:\n- Tableau\n\nFluency in {L} is essential for this role.",
)


def _cut(text):
    return [c for c in text_screen.screen({"title": "Planning Analyst", "desc": text + PAD})["cuts"]
            if "stated as a requirement" in c]


@pytest.mark.parametrize("body", NICE)
def test_the_example_profiles_language_asked_as_a_nice_to_have_is_not_cut(body):
    assert _cut(body.format(L="Welsh")) == []


@pytest.mark.parametrize("body", REQUIRED)
def test_the_example_profiles_language_stated_as_a_requirement_is_still_cut(body):
    cuts = _cut(body.format(L="Welsh"))
    assert cuts and cuts[0].startswith("Welsh stated as a requirement")


def test_a_saved_ruling_on_the_profiles_language_is_re_judged():
    assert text_screen.ruling_refused('Welsh stated as a requirement: "Fluency in Welsh is a huge plus."')
    assert not text_screen.ruling_refused('Welsh stated as a requirement: "Fluency in Welsh is essential."')
    # Another language today's screen would cut in the same sentence holds the ruling.
    assert not text_screen.ruling_refused(
        'Welsh stated as a requirement: "Fluency in Welsh is a huge plus, and fluent Spanish '
        'is required."')


# An invented person whose market raises French, hard-failed by their own row.
FRENCH_ROW = '''

FRENCH = re.compile(
    r"\\bfrench\\b[^.\\n]{0,40}\\b(essential|required|mandatory)\\b"
    r"|\\b(fluent|fluency|bilingual)\\s+(in\\s+)?(english\\s+and\\s+)?french\\b", re.I)
FRENCH_SOFT = re.compile(r"\\bfrench\\b[^.\\n]{0,30}\\b(an asset|preferred)\\b", re.I)
LANGUAGE_GATE = [("French", FRENCH, FRENCH_SOFT)]
'''
ASK = """
import json, sys
sys.path.insert(0, %r)
import text_screen
pad = %r
bodies = json.loads(sys.argv[1])
print(json.dumps({b: [c for c in text_screen.screen({"title": "Planning Analyst",
                                                      "desc": b + pad})["cuts"]
                      if "stated as a requirement" in c] for b in bodies}))
""" % (TOOLS, PAD)


@pytest.fixture
def french(tmp_path):
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof)
    with open(prof / "search.py", "a", encoding="utf-8") as fh:
        fh.write(FRENCH_ROW)
    return prof


def test_a_profile_that_hard_fails_french_reads_a_nice_to_have(french):
    nice = [b.format(L="French") for b in NICE] + ["Fluency in French is an asset."]
    required = [b.format(L="French") for b in REQUIRED]
    out = subprocess.run([sys.executable, "-c", ASK, json.dumps(nice + required)],
                         env={**os.environ, "LJS_PROFILE": str(french)},
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    cuts = json.loads(out.stdout)
    for body in nice:
        assert cuts[body] == [], body
    for body in required:
        assert cuts[body] and cuts[body][0].startswith("French stated as a requirement"), body
