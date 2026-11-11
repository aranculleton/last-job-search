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


# The three layouts the 2026-11-10 audit (NW-1) still found misread after the fix above: a
# grouped role whose title carries two commas, a group line that is a bare work mode, and a
# place written once for the whole group.
@pytest.mark.parametrize("under, title", [
    (["Full-time · 6 yrs 2 mos"], "Director, Data, AI and Analytics"),
    (["6 yrs 2 mos"], "Director, Data, AI and Analytics"),
    (["Hybrid"], "Senior Data Scientist"),
    (["On-site"], "Senior Data Scientist"),
    (["Full-time · 6 yrs 2 mos", "Hybrid"], "Senior Data Scientist"),
])
def test_a_grouped_title_with_commas_or_a_bare_work_mode_is_read_as_the_title(under, title):
    lines = (["Harbourline Insurance"] + under
             + [title, "Jan 2023 - Present · 1 yr 10 mos",
                "Manager, Analytics", "Sep 2018 - Jan 2023 · 4 yrs 5 mos"])
    assert reading._current(lines) == "Harbourline Insurance"
    got = reading._entries(lines)
    assert [(e["employer"], e["title"]) for e in got] == [
        ("Harbourline Insurance", title), ("Harbourline Insurance", "Manager, Analytics")]


def test_a_place_written_once_for_the_group_is_each_roles_place():
    lines = ["Harbourline Insurance", "Full-time · 6 yrs 2 mos",
             "Toronto, Ontario, Canada · Hybrid", "Senior Data Scientist",
             "Jan 2023 - Present · 1 yr 10 mos", "Data Scientist",
             "Sep 2018 - Jan 2023 · 4 yrs 5 mos", "Oakmere Foods", "Analyst",
             "Oakmere Foods · Full-time", "2016 - 2018"]
    got = reading._entries(lines)
    assert [(e["employer"], e["title"], e["place"], e.get("mode", "")) for e in got[:2]] == [
        ("Harbourline Insurance", "Senior Data Scientist", "Toronto, Ontario, Canada", "hybrid"),
        ("Harbourline Insurance", "Data Scientist", "Toronto, Ontario, Canada", "hybrid")]
    # The group's place is the current role's, so a top card elsewhere is compared with it.
    note = reading.place_note({"location": "Calgary, Alberta, Canada", "experience": got})
    assert "Toronto" in note


def test_an_employer_that_reads_like_a_job_title_is_kept_with_a_caution_never_skipped():
    # A reading saved before the fix: the title was taken for the employer, the place for the
    # title. Read again, it is never a skip for having moved on.
    saved = {"current": "Director, Pricing Science and Strategy", "headline": "Director",
             "experience": [{"employer": "Director, Pricing Science and Strategy",
                             "title": "Toronto, Ontario, Canada",
                             "dates": "Jan 2023 - Present"}]}
    keep, why = reading.verdict(saved, "Harbourline Insurance")
    assert keep, why
    assert "moved on" not in why and "Harbourline Insurance" in why
    # Someone who did move on is still skipped.
    moved = {"current": "Oakmere Foods", "headline": "Analyst",
             "experience": [{"employer": "Oakmere Foods", "title": "Analyst",
                             "dates": "Jan 2023 - Present"}]}
    keep, why = reading.verdict(moved, "Harbourline Insurance")
    assert not keep and "moved on" in why


# The independent review of the NW-1 fix (2026-11-11): a "Remote" line, as LinkedIn writes it
# with its capital, was lost as a place for a group and for a role, and a line describing a
# role with a comma in it, straight under its dates, was read as the role's place over the
# group's own.
def test_a_remote_line_is_a_place_for_a_group_and_for_a_role():
    group = reading._entries(["Harbourline Insurance", "Remote", "Senior Data Scientist",
                              "Jan 2023 - Present · 1 yr 10 mos", "Data Scientist",
                              "Sep 2018 - Jan 2023 · 4 yrs 5 mos"])
    assert [(e["place"], e.get("mode")) for e in group] == [("Remote", "remote")] * 2
    role = reading._entries(["Senior Data Scientist", "Harbourline Insurance · Full-time",
                             "Jan 2023 - Present", "Remote"])
    assert (role[0]["place"], role[0].get("mode")) == ("Remote", "remote")


def test_a_description_with_a_comma_under_a_roles_dates_is_never_its_place():
    lines = ["Harbourline Insurance", "Full-time · 6 yrs 2 mos",
             "Toronto, Ontario, Canada · Hybrid", "Senior Data Scientist",
             "Jan 2023 - Present · 1 yr 10 mos",
             "Led pricing, risk and claims models for the home book", "Data Scientist",
             "Sep 2018 - Jan 2023 · 4 yrs 5 mos"]
    got = reading._entries(lines)
    assert [(e["title"], e["place"]) for e in got] == [
        ("Senior Data Scientist", "Toronto, Ontario, Canada"),
        ("Data Scientist", "Toronto, Ontario, Canada")]
    alone = reading._entries(["Pricing Lead", "Harbourline Insurance · Full-time",
                              "Jan 2023 - Present", "Built pricing, risk and claims models"])
    assert alone[0]["place"] == ""
