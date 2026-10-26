"""A number with no unit is grounded only by the same number counting the same thing.

`check_numbers` keyed a claim by its size and unit, so a count with no unit word was
matched by size alone: "12 stores" in the profile grounded "12 clients" in an interview
answer, and "30+ operations managers" grounded "30 people" managed. Now, where both the
document and the profile name what the number counts, they must share a word or a known
synonym. Everything the example person's documents already say still passes.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bullet_library as LIB  # noqa: E402
import check_numbers as CN  # noqa: E402

GROUNDED = CN.grounded()


def _flagged(text):
    return [f["value"] for f in CN.check(text, allowed=GROUNDED)]


@pytest.mark.parametrize("text", [
    "I ran a pilot across 12 clients.",          # the profile's 12 counts stores
    "I managed 30 people.",                      # its 30+ counts operations managers
    "I segmented 140 customers.",                # its 140 counts suppliers
])
def test_the_same_number_counting_something_else_is_not_grounded(text):
    assert _flagged(text) == [text.split()[-2]]


@pytest.mark.parametrize("text", [
    "I ran a 12-store pilot against matched controls.",
    "Forecasts across 2,400 products, by depot.",       # SKUs and products are one thing
    "Reporting for 30+ managers.",
    "I segmented 140 vendors by cost to serve.",
    "A team of 12, and 140 of them on the list.",       # nothing named: matched by size
    "It freed £1.1M in stock.",                          # money is not a count
])
def test_a_rewording_of_what_the_profile_counts_still_passes(text):
    assert _flagged(text) == []


def test_a_figure_the_profile_never_states_is_still_found():
    assert _flagged("I cut error across 2,500 SKUs.") == ["2,500"]


def test_every_bullet_and_the_example_documents_still_pass():
    for key, text in LIB.TEXT.items():
        assert CN.check(text, key, GROUNDED) == [], key
    for path in ("cv/main_example.tex", "cover_letters/cover_example.tex"):
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            assert CN.check(fh.read(), path, GROUNDED) == [], path


def test_a_plain_set_is_matched_by_size_as_it_always_was():
    assert CN.check("I ran a pilot across 12 clients.", allowed={(12.0, "")}) == []


def test_the_letter_may_repeat_the_employers_figures_whatever_it_says_they_count():
    draft = {"company": "Kestrel Mutual", "abbr": "KestrelMutual",
             "summary": "Operations analyst who forecast 2,400 SKUs.",
             "p1": "Your 410,000 claims a year: I forecast at that scale for 2,400 products.",
             "p2": "Kestrel Mutual handled 410,000 policies last year.", "lead": "",
             "cl_bullets": [], "p4": "I would start with the 12 clients you named.",
             "posting": "You will support 12 regional teams."}
    assert [f["source"] for f in CN.check_draft(draft)] == []


def test_the_command_says_what_each_side_counts(tmp_path):
    doc = tmp_path / "answers.md"
    doc.write_text("### Q\nI led 12 clients through it.\n", encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_numbers.py"), str(doc)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
                       env=dict(os.environ, LJS_PROFILE=os.path.join(ROOT, "profile.example")))
    assert r.returncode == 1
    assert 'the profile counts 12 "stores against' in r.stdout
    assert 'and this counts "clients"' in r.stdout
