"""A skill the tailor listed is not trimmed as unasked when the posting names it in a phrase.

A skills line dropped "A/B testing and experiment design" although the tools field named
it, because the posting said "online experimentation" and the person's own pattern for
that skill deliberately skips bare "experimentation" ("a culture of experimentation" is
not the skill). The trim then treated it as never asked for and cut it before a skill the
posting never mentioned. The person's pattern stays theirs; the trim now reads the item's
head noun inside a compound phrase as asked, for items the tailor listed. Every posting
here is invented.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import skills_block as sb  # noqa: E402

ITEM = "A/B testing and experiment design"
# The shape a person's own pattern can take: experiment design and A/B named, the bare
# word left out on purpose.
PATTERN = r"\bA/B\b|\bexperiment(?:al|ation)?[- ]design\b"
TOOLS = ("SQL, Python, pandas, Excel, demand forecasting, inventory optimisation, "
         "route optimisation, statistics, " + ITEM + ", dbt, data quality testing, Power BI, "
         "stakeholder reporting, Jira")
POSTING = ("You will run online experimentation on our checkout, build demand forecasts in "
           "SQL and Python, model inventory optimisation and route optimisation, report in "
           "Power BI and Excel, keep data quality checks in dbt, and work in Jira.")


@pytest.fixture
def own_pattern(monkeypatch):
    monkeypatch.setattr(sb, "ITEMS", [((c, ITEM, PATTERN) if i == "A/B testing" else (c, i, p))
                                      for c, i, p in sb.ITEMS])


def _line(tools, posting):
    return next(line for line in sb.lines(tools, posting=posting)
                if line.startswith("Languages and modelling"))


def test_the_listed_skill_named_in_a_compound_phrase_survives_the_trim(own_pattern):
    line = _line(TOOLS, POSTING)
    assert ITEM in line
    # What goes instead is the one the posting never mentions.
    assert "statistics" not in line


def test_a_bare_word_in_another_sense_is_still_not_an_ask(own_pattern):
    culture = POSTING.replace("run online experimentation on our checkout",
                              "join a culture of experimentation")
    assert ITEM not in _line(TOOLS, culture)


def test_only_what_the_tailor_listed_is_read_this_way(own_pattern):
    unlisted = TOOLS.replace(", " + ITEM, "")
    assert ITEM not in _line(unlisted, POSTING)
    assert sb._compound_named([ITEM], "an experimentation platform for pricing") == {ITEM}
    assert sb._compound_named([ITEM], "Experimentation:\nwe test") == frozenset()
