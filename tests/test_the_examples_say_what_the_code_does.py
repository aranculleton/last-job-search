"""The example documents and the guides say what the code does.

Four places contradicted it (the drafting audit, 2026-10-25): templates/README.md stored
a person's templates in the app's own folder, which the next sync puts back; the example
letter asked for an opening that names the role and "three to five" bullets in six blocks;
the example resume had Core Competencies and no Summary or Skills; and
08-application-forms.md said every screening answer is read from the profile.
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, ".claude", "skills", "job-application-assistant")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_a_persons_templates_live_in_their_profile():
    readme = _read("templates", "README.md")
    custom = readme[readme.index("# Custom Templates"):]
    assert "profile/templates/" in custom
    assert "templates/\n├── cv/" not in custom
    assert "adds a managed block to `05-cv-templates.md`" not in custom


def test_the_example_letter_has_the_guides_four_blocks():
    tex = _read("cover_letters", "cover_example.tex")
    body = tex[tex.index("Dear [Hiring Manager / Team]"):tex.index("\\begin{flushright}")]
    assert len(re.findall(r"^\\lettercontent\{", body, re.M)) == 4
    assert len(re.findall(r"^\s*\\item ", body, re.M)) == 3
    assert "three to five" not in tex and "name the role" not in tex.lower().replace(
        "never open on the role", "")


def test_the_example_resume_has_the_generators_sections():
    tex = _read("cv", "main_example.tex")
    sections = re.findall(r"^\\section\{([^}]*)\}", tex, re.M)
    assert "Core Competencies" not in sections
    assert sections[:5] == ["Summary", "Professional Experience", "Skills", "Education",
                            "Certifications"]


def test_the_forms_guide_says_which_answers_are_read_each_time():
    guide = _read(".claude", "skills", "job-application-assistant", "08-application-forms.md")
    assert "Every one is parsed from" not in guide
    assert "profile/screening.py" in guide and "Three are read from the profile" in guide
