"""Canadian English keeps colour, favour, labelling and travelled, and is checked for them.

The Canadian entry was checked for the American behavior, modeling and center alone, so
"color", "favor", "labeling" and "traveled" passed in a Canadian document, though the
comment above the rule and the person's own rules say Canadian keeps colour (the drafting
audit, 2026-10-25). An employer's name keeps its own spelling ("Travelers").
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import locale_rules  # noqa: E402

TEXT = "The color scheme, labeling, traveled, favor and behavior modeling."


def _found(spelling, text):
    return [m.group(0) for _v, m in
            locale_rules.for_documents({"spelling": spelling}).wrong_spellings(text)]


def test_canadian_flags_every_american_form_it_does_not_use():
    assert _found("canadian", TEXT) == ["color", "labeling", "traveled", "favor", "behavior",
                                        "modeling"]
    assert _found("canadian", "The colour, labelling, travelled, favour and behaviour "
                              "modelling; we organize and analyze.") == []


def test_each_variety_reads_the_double_l_its_own_way():
    assert _found("british", "labeling and traveled") == ["labeling", "traveled"]
    assert _found("american", "labelling and travelled") == ["labelling", "travelled"]
    assert _found("american", "labeling and traveled") == []


def test_an_employers_name_keeps_its_spelling():
    assert _found("canadian", "I would bring this to Travelers.") == []
