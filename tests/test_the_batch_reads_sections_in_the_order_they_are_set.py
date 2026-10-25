"""The batch reads each section to the heading after it on the page, and a role's bullets
under the employer whose name its line opens with.

SKILLPARENS read Skills to the Education heading, so a profile that puts Education first
(the order resume_gen documents for a recent graduate) had the Skills range run to the foot
of the page and fail every resume on a certification's "(2024)". And bullets were counted
under the last employer whose name a line starts with, so with "Acme" and "Acme Labs" both
employers, a page holding 2/1 counted 0/3 (the drafting audit, 2026-10-25).

The employers and lines are invented.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import verify_batch as B  # noqa: E402

EDU_FIRST = ["Profile", "Education", "Professional Experience", "Skills", "Certifications"]
PAGE = ["Morgan Ellis", "Profile", "Analyst.", "Education", "BSc Mathematics (2016-2019)",
        "Professional Experience", "Acme Labs, Leeds, UK", "• one", "• two", "Acme, York, UK",
        "• three", "Skills", "Languages: SQL, Python", "Certifications",
        "Microsoft Certified: Power BI Data Analyst Associate (2024)"]


def test_the_next_heading_is_the_pages_own():
    assert B.next_heading(EDU_FIRST, "Skills") == "Certifications"
    assert B.next_heading(EDU_FIRST, "Professional Experience") == "Skills"
    assert B.next_heading(EDU_FIRST, "Certifications") == ""
    assert B.next_heading(EDU_FIRST, "Nowhere") == ""


def test_the_skills_range_stops_at_the_heading_after_it():
    skills = B.sed_range(PAGE, "Skills", B.next_heading(EDU_FIRST, "Skills"), drop_end=True)
    assert skills == ["Skills", "Languages: SQL, Python"]
    # With Education as the end, which sits above Skills here, it ran to the foot.
    old = B.sed_range(PAGE, "Skills", "Education", drop_end=True)
    assert any("(2024)" in line for line in old)
    # A section that is the page's last reads to the end.
    assert B.sed_range(PAGE, "Certifications", "")[-1].endswith("(2024)")


def test_a_line_belongs_to_the_longest_employer_name_it_opens_with():
    page = ["Professional Experience", "Analyst", "Acme Labs, Leeds, UK", "• one", "• two",
            "Analyst", "Acme, York, UK", "• three", "Education"]
    assert B.bullets_per_role(page, ["Acme Labs", "Acme"], "Education") == "2/1"
    assert B.bullets_per_role(page, ["Acme", "Acme Labs"], "Education") == "1/2"
    assert B.bullets_per_role(PAGE, ["Acme Labs", "Acme"],
                              B.next_heading(EDU_FIRST, "Professional Experience")) == "2/1"
