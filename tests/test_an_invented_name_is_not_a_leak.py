"""A greeting with one of the app's invented first names is not a leak.

The maintainer's denylist holds every contact's first name as a greeting ("Hi <name>"),
to catch a real message copied into an example. The app's own examples greet invented
people by first name, and some of those names are common: on 2026-10-22 one contact in
the maintainer's repo shared a first name with the app's invented Ana Rook, and every
greeting to her in the app's tests (64 of them) failed the leak scan, so no chat on that
repo could get green or merge. The greeting is left out for the app's declared cast
(build_app.INVENTED_FIRST_NAMES); the contact is still caught by full name, profile
address, email and contact id. Every greeting in the app names someone declared, so a
new first name in an example is added to the list on purpose.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_app  # noqa: E402
from tests import repo_files  # noqa: E402

# Words a greeting opens on that are not anyone's first name: a company, a title, the
# start of "Ph.D.", "Hiring Manager".
NOT_NAMES = {"Acme", "Dr", "Hiring", "Ms", "Ph"}
GREETING = re.compile(r"\b(?:Hi|Dear) ([A-Z][a-z]+)\b")


def test_every_greeting_in_the_app_names_someone_it_invented():
    undeclared = {}
    for rel in repo_files.tracked():
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        for name in GREETING.findall(text):
            if name not in build_app.INVENTED_FIRST_NAMES and name not in NOT_NAMES:
                undeclared.setdefault(name, rel)
    assert not undeclared, (
        "greetings to first names the app has not declared as invented "
        "(build_app.INVENTED_FIRST_NAMES): %s" % undeclared)


def test_a_contact_named_like_the_cast_is_caught_by_full_name_not_greeting():
    cast = "Ana Rook"
    assert build_app._greetings(cast) == []
    assert cast in build_app.name_forms(cast)


def test_any_other_contact_keeps_the_greeting():
    first = "Hal"
    assert first not in build_app.INVENTED_FIRST_NAMES
    assert build_app._greetings(first + " Okonedo") == ["=Hi " + first, "=Dear " + first]
