"""A credential gate is lifted only by a sentence saying the credential is a preference or
not needed, never by an equal opportunity, welcome, accommodation or "priority" line.

A posting whose own title is the profession ("Actuarial Analyst") and that keeps naming it
is a credential gate, unless a sentence says the credential is not needed. Any sentence
naming the profession beside an inclusion word lifted the gate: "We welcome applicants from
all backgrounds to our actuarial team", "Reasonable accommodations are available for
actuarial exams" and "Actuarial exam progress is a priority for us" each let the posting
through to drafting. "Part-qualified actuaries welcome" is ordinary wording in such
postings, and it says the role wants exam passes.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import text_screen as T  # noqa: E402

BODY = ("As an Actuarial Analyst you will price motor policies for a mutual insurer. You will "
        "progress through your actuarial exams with study leave. Our actuarial function "
        "reports to the Chief Actuary. ")


def _cut(title, extra):
    return [c for c in T.screen({"title": title, "desc": BODY + extra})["cuts"]
            if "professional designation" in c]


@pytest.mark.parametrize("extra", [
    "We welcome applicants from all backgrounds to our actuarial team.",
    "Our actuarial team is proud to be an inclusive employer.",
    "Reasonable accommodations are available for actuarial exams.",
    "Actuarial exam progress is a priority for us.",
    "Part-qualified actuaries welcome.",
    "Actuarial students are encouraged to apply.",
    # A preference about something else in the sentence is not about the credential.
    "You will work in our actuarial team, and experience with R is a plus.",
])
def test_inclusion_and_welcome_words_never_lift_the_gate(extra):
    assert _cut("Actuarial Analyst", extra)


@pytest.mark.parametrize("extra", [
    "No actuarial exams are needed.",
    "Actuarial exams are desirable.",
    "Actuarial exams would be an advantage, not a requirement.",
    "Completed actuarial exams would be an advantage.",
    "Actuarial exams are optional.",
])
def test_a_sentence_saying_the_credential_is_a_preference_or_not_needed_lifts_it(extra):
    assert not _cut("Actuarial Analyst", extra)


def test_a_role_beside_the_profession_is_still_not_a_gate():
    for extra in ("We welcome applicants from all backgrounds to our actuarial team.",
                  "Part-qualified actuaries welcome."):
        assert not _cut("Pricing Analyst", extra)
