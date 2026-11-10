"""Someone still at the employer they were found at is never read as having moved on because
LinkedIn grouped their roles under it.

On 2026-11-10 a read of a manager at a large insurer said she had moved on: her Experience
grouped two roles under the insurer's name with a place line (or a bare "Full-time") under it
instead of the time spent there, so the first role's title was read as her employer. The chat
fixed the reading by hand. Invented people and employers only.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import pytest  # noqa: E402

import reading  # noqa: E402

TWO = ["Senior Manager, Data Science", "Jan 2023 - Present · 1 yr 10 mos",
       "Manager, Analytics", "Sep 2018 - Jan 2023 · 4 yrs 5 mos"]


@pytest.mark.parametrize("under", [
    ["Toronto, Ontario, Canada · Hybrid"],
    ["Full-time"],
    ["Permanent Full-time · 6 yrs 2 mos"],
    ["Full-time · 6 yrs 2 mos", "Toronto, Ontario, Canada"],
    ["Remote"],
    ["6 yrs 2 mos"],
])
def test_roles_grouped_under_one_employer_keep_it_as_their_employer(under):
    lines = ["Harbourline Insurance"] + under + TWO
    assert reading._current(lines) == "Harbourline Insurance"
    got = reading._entries(lines)
    assert [(e["employer"], e["title"]) for e in got] == [
        ("Harbourline Insurance", "Senior Manager, Data Science"),
        ("Harbourline Insurance", "Manager, Analytics")]
    keep, why = reading.verdict({"current": reading._current(lines), "headline": "Senior Manager",
                                 "experience": got}, "Harbourline Insurance")
    assert "moved on" not in why, why


def test_a_kind_of_work_between_a_grouped_title_and_its_dates_is_not_its_title():
    lines = ["Harbourline Insurance", "6 yrs 2 mos", "Senior Manager, Data Science", "Full-time",
             "Jan 2023 - Present · 1 yr 10 mos", "Toronto, Ontario, Canada"]
    assert reading._entries(lines)[0]["title"] == "Senior Manager, Data Science"


@pytest.mark.parametrize("lines, employer", [
    (["Senior Manager, Data Science", "Harbourline Insurance · Full-time", "Jan 2023 - Present",
      "Toronto, Ontario, Canada · Hybrid"], "Harbourline Insurance"),
    (["Senior Manager", "Harbourline Insurance", "Jan 2023 - Present", "Toronto, Ontario, Canada"],
     "Harbourline Insurance"),
])
def test_one_role_laid_out_as_before_reads_as_before(lines, employer):
    assert reading._current(lines) == employer
    assert reading._entries(lines)[0]["employer"] == employer
