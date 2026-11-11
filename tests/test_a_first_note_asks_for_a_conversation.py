"""A first note asks for a conversation, never a job, to a decision-maker as to anyone.

The networking skill says a first note asks for a conversation and never a job, yet the app's
default ask for a decision-maker was "Would love to hear if you have anything coming up", and
the page's sample InMail ended "Is there anything coming up that a planning analyst could help
with? I would be glad to send my CV." (the research review, 2026-11-10, U-17). The default is an
ask for a short conversation or a pointer; a resume is offered once they reply. A person's own
wording in profile/networking.py TEMPLATES still wins. Every person and employer is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import advice  # noqa: E402
import compose  # noqa: E402

SAMPLE = ("Hello Noor, I am an analyst in Manchester with four years in retail supply chains, "
          "and I saw Brackenridge is growing its analytics practice in the north. Is there "
          "anything coming up that a planning analyst could help with? I would be glad to send "
          "my CV.")


def _rules(text, reader):
    return [v.text for v in compose.first_note_findings(text, reader=reader)]


def test_the_default_ask_to_a_decision_maker_is_for_a_conversation():
    for line in compose.BANK["ask"]["decision_maker"] + compose.BANK_PLAIN["ask"]["decision_maker"] \
            + (advice.OPEN_ASK, advice.OPEN_ASK_PLAIN):
        assert "coming up" not in line.lower(), line
        assert _rules("I'm an analyst in Manchester. " + line, "decision_maker") == [], line


def test_a_first_note_that_asks_for_a_job_or_offers_the_resume_is_refused():
    found = _rules(SAMPLE, "decision_maker")
    assert any("\"anything coming up\"" in f for f in found), found
    assert any("glad to send my CV" in f and "once they reply" in f for f in found), found
    assert _rules(SAMPLE, "peer"), "a peer is never asked for a job either"
    # A recruiter's job is roles: asked what is coming up, and offered a resume.
    assert _rules(SAMPLE, "recruiter") == []


def test_the_persons_own_wording_wins(monkeypatch):
    own = "Would love to hear if you have anything coming up."
    monkeypatch.setattr(compose, "TEMPLATES", {"decision_maker": {"ask": [own]}})
    assert compose.phrase("ask", "decision_maker") == own
    assert _rules("I'm an analyst in Manchester. " + own, "decision_maker") == []


def test_the_pages_sample_inmail_offers_no_resume_before_a_reply():
    path = os.path.join(ROOT, "tests", "fixtures", "app_model_sample.json")
    with open(path, encoding="utf-8") as fh:
        model = json.load(fh)
    noor = next(m for m in model["messages"] if m["id"] == "msg-noor-1")
    assert "CV" not in noor["body"] and noor["chars"] == len(noor["text"]), noor
    # Noor is a recruiter: asked openly what fits, the one reader a first note may ask that of.
    assert _rules(noor["body"], "recruiter") == [] and _rules(noor["body"], "decision_maker") == []


def test_the_persons_own_ask_wins_wherever_they_set_it(monkeypatch):
    """The review of 2026-11-11: only TEMPLATES was read, so their own ASK (profile/networking.py
    ASK) was refused as asking for the job. Every line of their own counts (compose._OwnWords)."""
    own = "Would love to hear if you have anything coming up."
    monkeypatch.setattr(compose, "ASK", own)
    assert _rules("I'm an analyst in Manchester. " + own, "decision_maker") == []


def test_a_question_about_their_plans_is_no_job_ask():
    for line in ("Is there anything exciting coming up on the roadmap?",
                 "Anything big coming up for the depot team this winter?"):
        assert _rules("I'm an analyst in Manchester. " + line, "peer") == [], line
    assert _rules("I'm an analyst in Manchester. Is there anything coming up on your team?",
                  "peer")
