"""What is personal is a person's own life, never a field of work.

From the sync audit, 2026-10-21: the filter that keeps a reader's private life out of a
pack and a call prep matched words, so it cut every one of a dozen work sentences (a
retirement-plans team, mental health services, a cancer research charity, a diagnostics
company, political science, "our family of brands", a report that "came out") and kept
every one of ten personal posts (IVF, a miscarriage, a heart attack, "voted today", Pride,
"a mum of two", "50 today", sobriety, a brother's death, fasting). It now reads what a
person says about their own life, and a field word in the employer's own team research is
the business, never personal.

Everything here is invented.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import prep  # noqa: E402
import test_interview_pack as base  # noqa: E402
import test_nothing_personal_reaches_the_pack as personal  # noqa: E402

app = base.app


@pytest.mark.parametrize("text", [
    "The retirement plans team models member outcomes for workplace pensions.",
    "Leads analytics for the mental health services line at a health insurer.",
    "Data lead at a cancer research charity, building trial-recruitment dashboards.",
    "Head of data science at a medical diagnostics company.",
    "PhD in political science; now runs survey methodology for a polling firm.",
    "Our annual forecasting report came out this week.",
    "Our new paper on demand forecasting is coming out in March.",
    "Turning 12 spreadsheets into one Power BI report saved the planners a day a week.",
    "Rewrote a 20-year-old codebase in Python.",
    "Built the Christmas trading forecast for our family of brands.",
    "Product analytics for a wedding-planning marketplace.",
    "Models demand for NHS maternity services.",
    "A grocer's demand forecasts for Ramadan and Diwali in the world-food aisles.",
    "We retired the old warehouse system this year.",
])
def test_work_in_a_field_with_a_personal_sounding_word_is_kept(text):
    assert prep.sensitive_topic(text) == ""


@pytest.mark.parametrize("text, topic", [
    ("Sharing our IVF journey after two years of trying.", "family"),
    ("Back at my desk after a miscarriage last month.", "family"),
    ("Recovering well after my heart attack in June.", "health"),
    ("Proud to have voted today. Every vote counts.", "politics"),
    ("Wishing everyone a happy Pride!", "sexuality"),
    ("As a mum of two, flexible hours changed everything.", "family"),
    ("Celebrating 50 today and still writing SQL.", "age"),
    ("Six months sober today.", "health"),
    ("Grieving my brother, who died last week.", "family"),
    ("Fasting this month and taking the evenings slower.", "religion"),
])
def test_a_post_about_their_own_life_is_left_out(text, topic):
    assert prep.sensitive_topic(text) == topic


def test_the_employers_own_team_research_keeps_its_business(app):
    """The team is what the interviewer works on: a field word there is the work."""
    ctx = base._ctx()
    work = ["The team models member outcomes for the retirement plans business.",
            "The team forecasts demand for the mental health services line.",
            "The team builds trial-recruitment dashboards for cancer research partners."]
    ctx["research"] = dict(ctx["research"], teams={"Planning": [
        {"claim": c, "source_url": "https://fernhill.example/team"} for c in work]})
    ctx["with"] = "Shirin Example, Head of Planning"
    personal._read([])
    meeting = "\n".join(base._section(P.pack_markdown(ctx, never_say=[]), "Who you are meeting"))
    shown = [c for c in work if c[:-1] in meeting]
    assert len(shown) == 2                                    # the first two it shows, both kept
    assert "retirement plans" in meeting and "mental health services" in meeting
