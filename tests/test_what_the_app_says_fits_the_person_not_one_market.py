"""What the app tells a person, and writes for them, fits them, not one person's situation.

Small lines shaped by one person's own case, each wrong for most others:
- every long outreach note said to send it "as an InMail", which a free LinkedIn account,
  the default, does not have;
- every interview pack's leadership question said "Claim no people management your
  profile does not hold", which steered a manager away from their strongest answer;
- a first note whose ask was written in German ended on a full stop, because only English
  questions were known;
- every letter's close stated the right to work, and every first note to a recruiter did
  too, which is a visa holder's habit: a citizen applying at home then ends each letter
  "I'm a US citizen and need no sponsorship". It is asked for now only where the person's
  status needs saying (a permit, a visa, a status short of citizenship) or the posting asks.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import compose  # noqa: E402
import draft_pack  # noqa: E402
import interview_pack as P  # noqa: E402
import outreach  # noqa: E402
import profile_facts  # noqa: E402
from test_one_drafting_call_per_posting import FIXTURE  # noqa: E402

PEER = {"contact_id": "larkspur_retail_castellan", "name": "Juno Castellan",
        "company": "Larkspur Retail", "title": "Data Analyst", "route": "alumni",
        "status": "call_booked"}
LED = {"question": "Tell me about a time you led something.", "why": "", "source": "x"}


def _outreach_md(tmp_path, monkeypatch, inmail):
    monkeypatch.setattr(outreach.person, "state", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(outreach._schema, "LIMITS", dict(
        outreach._schema.LIMITS, connection_note_chars=60, inmail_credits_per_month=inmail))
    folder = outreach.write(dict(FIXTURE["draft"]), {}, "2026-11-03")
    with open(os.path.join(folder, "outreach.md"), encoding="utf-8") as fh:
        return fh.read()


def test_inmail_is_suggested_only_on_a_plan_that_has_it(tmp_path, monkeypatch):
    free = _outreach_md(tmp_path / "free", monkeypatch, 0)
    assert "Longer than a connection request" in free and "InMail" not in free
    paid = _outreach_md(tmp_path / "paid", monkeypatch, 5)
    assert "or as an InMail" in paid


def test_a_manager_is_told_to_lead_with_the_team_they_ran(monkeypatch):
    call = P.call_ctx(PEER, "", profile_facts.build())

    class Search:
        MANAGES_PEOPLE = False

    class Bullets:
        LIB = {"Quayside Foods": {"HV_TEAM": (
            {"leadership"}, 8, "Led a team of 3 marketing coordinators across two brands")}}

    real = P.person.module
    monkeypatch.setattr(P.person, "module", lambda name: {"search": Search, "bullets": Bullets}
                        .get(name) or real(name))
    assert P.manages_people()
    said = " ".join(P.answer_for(dict(LED), call)["lines"])
    assert "Claim no people management" not in said and "the team you ran" in said
    Bullets.LIB = {"Quayside Foods": {"HV_CRM": (
        {"crm"}, 8, "Rebuilt the lifecycle email programme, lifting repeat orders by 9%")}}
    assert not P.manages_people()
    assert "Claim no people management" in " ".join(P.answer_for(dict(LED), call)["lines"])


@pytest.mark.parametrize("ask", [
    "Hätten Sie Zeit für ein kurzes Gespräch",
    "Auriez-vous un moment pour en parler",
    "¿Tendría unos minutos esta semana",
    "Você teria alguns minutos para conversar",
    "Zou u tijd hebben voor een kort gesprek",
])
def test_a_question_in_another_language_ends_on_a_question_mark(ask):
    assert compose._sentence(ask).endswith("?")


@pytest.mark.parametrize("status,needs", [
    ("UK settled status. No sponsorship required.", True),
    ("IEC Working Holiday work permit; no sponsorship needed.", True),
    ("Requires visa sponsorship (H-1B transfer).", True),
    ("US citizen. No sponsorship required.", False),
    ("Canadian citizen", False),
    ("Permanent resident of Australia.", False),
    ("", False),
])
def test_a_status_is_stated_unasked_only_where_it_needs_saying(status, needs):
    assert profile_facts.status_needs_saying(status) is needs


def test_a_citizens_letter_states_no_right_to_work_unasked(monkeypatch):
    monkeypatch.setattr(draft_pack, "auth_line", lambda: "US citizen. No sponsorship required.")
    rules = draft_pack.contract()
    assert "only where the posting asks" in rules
    monkeypatch.setattr(draft_pack, "auth_line", lambda: "UK settled status. No sponsorship required.")
    rules = draft_pack.contract()
    assert "where the candidate is and their right to work" in rules


def test_a_recruiter_hears_the_status_by_default_only_where_it_needs_saying(monkeypatch):
    monkeypatch.setattr(profile_facts, "status_needs_saying", lambda text=None: False)
    assert compose.default_eligibility()["recruiter"] is False
    monkeypatch.setattr(profile_facts, "status_needs_saying", lambda text=None: True)
    assert compose.default_eligibility()["recruiter"] is True
