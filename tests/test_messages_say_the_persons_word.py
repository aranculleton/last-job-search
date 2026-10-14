"""Every message says the document the way the person's market does.

The example person's document is a CV (person.json documents.noun "CV",
banned_nouns ["resume"]). The composers wrote "My resume is attached" and
"Happy to send my resume" into their emails and referral asks, the outreach note
offered "the context that does not fit on a resume", and the reply guidance told
them "Do not attach a file named CV; the attachment says resume", the opposite
of their own rule. tone.check banned "CV" for a resume market and nothing for a
CV market, so none of it was caught.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import compose  # noqa: E402
import outreach  # noqa: E402
import reply  # noqa: E402
import tone  # noqa: E402

RESUME = re.compile(r"\br[eé]sum[eé]s?\b", re.I)


def test_the_example_is_a_cv_person():
    assert compose.NOUN == "CV"


def test_an_email_attaches_the_persons_document():
    body = compose.email("Wren Halloway", "Following up", "thanks for the chat on Tuesday",
                         "", "Could we talk next week?")
    assert "My CV is attached." in body and not RESUME.search(body)
    named = compose.email("Wren Halloway", "", "thanks for the chat", "", "",
                          attachment="Morgan_Ellis_CV_Acme.pdf")
    assert "My CV is attached (Morgan_Ellis_CV_Acme.pdf)." in named


def test_a_referral_ask_offers_the_persons_document():
    ask = compose.referral_ask("Wren Halloway", "thanks again for the chat on Tuesday",
                               "Senior Analyst at Acme", "https://example.com/jobs/1")
    assert "send my CV" in ask and not RESUME.search(ask)


def test_the_outreach_note_asks_never_name_the_other_word():
    assert not any(RESUME.search(a) for a in outreach.ASKS)


def test_the_reply_guidance_has_the_rule_the_right_way_round():
    texts = []
    for s in reply.SCENARIOS.values():
        texts += [s.move, s.next_action, *s.do_not]
    texts.append(reply.NO_ADDRESS_ACTION)
    assert "Do not attach a file named resume; the attachment says CV." in texts
    stray = [t for t in texts if RESUME.search(t) and "file named resume" not in t]
    assert stray == []


def test_a_banned_noun_in_a_message_is_a_finding():
    rules = {v.rule for v in tone.check("I have attached my resume for the role.")}
    assert "document_noun" in rules and "document_noun" in tone.RULES
    assert any(v.rule == "document_noun"
               for v in tone.check("File: Morgan_Ellis_Resume_ACME.pdf"))


def test_resume_as_a_verb_is_not_the_document():
    assert not [v for v in tone.check("Happy to resume the conversation next week.")
                if v.rule == "document_noun"]


def test_the_application_folder_labels_the_document_by_its_word(tmp_path, monkeypatch):
    monkeypatch.setattr(outreach.person, "state",
                        lambda *parts: str(tmp_path.joinpath(*parts)))
    a = {"company": "Wrenfield Freight Ltd", "role": "Analyst", "abbr": "Wrenfield",
         "posting": "A posting.", "p1": "x.", "p2": "y.", "lead": "", "cl_bullets": [],
         "p4": "", "summary": "", "tools": ""}
    d = outreach.write(a, {}, "2026-10-14")
    text = open(os.path.join(d, "job_posting.md"), encoding="utf-8").read()
    assert "- **CV:**" in text and "**Resume:**" not in text
