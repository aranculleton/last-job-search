"""Nothing personal read about an interviewer reaches the pack or the call prep.

A reading keeps a person's public posts, and a post about a new baby, an illness, their
faith or an election reached "Who you are meeting" as something to lead with, and the
question to ask them. None of it is professional, all of it is what an interviewer may
not ask a candidate, and it is not the candidate's to raise. Readings are now shown
without anything touching age, family, health, religion, politics or sexuality.

The interviewer and everything read about them are invented.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import prep  # noqa: E402
import reading  # noqa: E402
import test_interview_pack as base  # noqa: E402

app = base.app
CID = "fernhill_freight_example"          # Shirin Example, the fixture's interviewer


def _recent(days=10):
    return (datetime.date.today() - datetime.timedelta(days=days)).isoformat()


def _read(items, about=""):
    reading.save(CID, {"name": "Shirin Example", "company": base.COMPANY,
                       "headline": "Head of Planning at Fernhill Freight", "about": about,
                       "read_on": _recent(1), "sources": [{"kind": "paste"}], "items": items,
                       "shared": {"employers": [], "schools": [], "places": []}})


@pytest.mark.parametrize("text, topic", [
    ("Back at my desk after maternity leave, and so glad to be.", "family"),
    ("Proud of my daughter running her first 10k.", "family"),
    ("Six months on from my cancer diagnosis, a note of thanks.", "health"),
    ("Speaking openly about burnout and mental health at work.", "health"),
    ("Eid mubarak to everyone celebrating.", "religion"),
    ("Why I voted for the green party this time.", "politics"),
    ("Marching at the pride march with our network.", "sexuality"),
    ("Turned 50 this week, and still forecasting.", "age"),
])
def test_a_personal_subject_is_named_for_what_it_is(text, topic):
    assert prep.sensitive_topic(text) == topic


@pytest.mark.parametrize("text", [
    "Our talk on demand forecasting for a health insurer's claims team.",
    "How we built an election-results model for a broadcaster.",
    "Lessons from rebuilding a chilled-goods network in a year.",
    "A new cross-dock in Warrington, and what it did to our van miles.",
    "The family of forecasting models we retired this year.",
])
def test_work_about_a_field_is_not_personal(text):
    assert prep.sensitive_topic(text) == ""


def test_the_pack_shows_their_work_and_never_their_life(app):
    _read([{"kind": "talk", "text": "Forecasting chilled demand by depot, at a logistics meetup",
            "date": ""},
           {"kind": "post", "text": "Back at my desk after maternity leave, and so glad to be.",
            "date": _recent(5)},
           {"kind": "article", "text": "Six months on from my cancer diagnosis, a note of thanks",
            "date": ""}])
    text = base._pack()
    meeting = "\n".join(base._section(text, "Who you are meeting"))
    talk = "\n".join(base._section(text, "Small talk"))
    assert "Forecasting chilled demand by depot" in meeting
    for personal in ("maternity", "cancer", "diagnosis"):
        assert personal not in meeting and personal not in talk, personal


def test_the_question_to_ask_them_is_never_about_their_life(app):
    # Their only public piece is personal: the question falls back to the one their kind
    # of interviewer owns, never "how it has gone since".
    _read([{"kind": "article", "text": "What my son's diagnosis taught me about patience",
            "date": ""}])
    meeting = "\n".join(base._section(base._pack(), "Who you are meeting"))
    assert "diagnosis" not in meeting and "on their own work" not in meeting
    assert "  - Ask them: \"" in meeting


def test_the_call_prep_reads_them_the_same_way(app):
    _read([{"kind": "post", "text": "Eid mubarak to everyone celebrating this week.",
            "date": _recent(3)},
           {"kind": "talk", "text": "Route planning with fewer vans", "date": ""}])
    lines = prep._reading_lines({"contact_id": CID})
    assert any("Route planning with fewer vans" in ln for ln in lines)
    assert not any("Eid" in ln for ln in lines)


def test_a_team_fact_that_is_personal_is_not_shown(app):
    ctx = base._ctx()
    ctx["research"] = dict(ctx["research"], teams={"Planning": [
        {"claim": "The planning team is led by a manager on parental leave until June.",
         "source_url": "https://fernhill.example/team"},
        {"claim": "The planning team owns the weekly forecast for all fourteen sites.",
         "source_url": "https://fernhill.example/team"}]})
    ctx["with"] = "Shirin Example, Head of Planning"
    _read([])
    meeting = "\n".join(base._section(P.pack_markdown(ctx, never_say=[]), "Who you are meeting"))
    assert "owns the weekly forecast" in meeting
    assert "parental leave" not in meeting
