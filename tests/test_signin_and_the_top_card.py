"""A browser read from a clean install: signing in, then the profile as LinkedIn shows it.

Found on a person's first local run (2026-10-18). Everyone starts signed out in the
desktop app's browser pane; the first profile showed LinkedIn's sign-in wall, the
session recorded a stop for the day, and the person had to have it cleared by hand.
Then the read saved the line under the headline ("Employer · School") as the
headline, no current employer, and a note grounded on nothing, though the page held
what the person calls their work. Invented people only.
"""
from __future__ import annotations

import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "network"))
import reading  # noqa: E402

TODAY = datetime.date(2026, 10, 18)

AUTHWALL = """LinkedIn
Join LinkedIn
Make the most of your professional life
Email or phone
Password
Agree & Join
Already on LinkedIn? Sign in
"""
LOGIN = """Sign in
Stay updated on your professional world
Email or phone
Password
Show
Forgot password?
Sign in
New to LinkedIn? Join now
"""
GUEST = """Rosalind Achterberg
Head of Pricing Analytics at Kestrel Mutual
Manchester, England, United Kingdom
Sign in to view Rosalind's full profile
Join now
Sign in
"""
CHECK = """Let's do a quick security check
We've noticed some unusual activity from your account.
Press and hold the button
"""
# The signed-in top card: name, pronouns, degree, headline, "Employer · School", city.
CARD = """Rosalind Achterberg
She/Her
· 2nd
Head, Pricing Analytics | Model Governance | Insurance
Kestrel Mutual · University of Leeds
Manchester, England, United Kingdom
· Contact info
500+ connections
Connect
Message
More
Activity
Rosalind Achterberg posted this • 2w
Model governance is mostly writing down what the model is for.
"""


def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")


@pytest.mark.parametrize("text,kind", [(AUTHWALL, "signin"), (LOGIN, "signin"),
                                        (GUEST, "signin"), (CHECK, "check"), (CARD, "profile")])
def test_a_sign_in_page_is_told_apart_from_a_check_and_a_profile(text, kind):
    assert reading.page_kind(text)[0] == kind


def test_the_first_sign_in_page_is_a_wait_and_counts_nothing(tmp_path, monkeypatch, capsys):
    _state(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(AUTHWALL))
    code = reading.main(["read", "kestrel_achterberg", "-", "--source", "browser",
                         "--name", "Rosalind Achterberg", "--company", "Kestrel Mutual"])
    assert code == 4 and "run `reading.py signin`" in capsys.readouterr().out
    assert not os.path.exists(tmp_path.joinpath(*reading.STOP_FILE))      # no stop
    assert reading._browser_reads() == []                                  # not a read
    assert reading.load("kestrel_achterberg") is None


def test_the_sign_in_wait_opens_the_sign_in_page_and_watches_only_the_address():
    steps = " ".join(reading.signin_steps())
    assert reading.SIGNIN_URL in steps and "not a profile" in steps
    assert reading.SIGNIN_SAY in steps and "never type" in steps
    assert "address" in steps and "ask once more" in steps
    assert "—" not in steps and "press" not in steps.lower()
    assert reading.url_kind("https://www.linkedin.com/login") == "waiting"
    assert reading.url_kind("https://www.linkedin.com/checkpoint/challenge/ABC") == "verifying"
    assert reading.url_kind("https://www.linkedin.com/feed/") == "signed-in"


def test_after_sign_in_a_sign_in_page_or_a_check_is_a_stop(tmp_path, monkeypatch, capsys):
    _state(tmp_path, monkeypatch)
    reading.mark_signed_in()
    for text in (LOGIN, CHECK):
        if os.path.exists(tmp_path.joinpath(*reading.STOP_FILE)):
            os.remove(tmp_path.joinpath(*reading.STOP_FILE))
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(text))
        # Its own exit code, so `read; verdict` can tell a stop from a skip or a wait.
        assert reading.main(["read", "kestrel_achterberg", "-", "--source", "browser",
                             "--name", "Rosalind Achterberg", "--company",
                             "Kestrel Mutual"]) == reading.EXIT["check"]
        assert "stopped for today" in capsys.readouterr().out
        assert reading.stopped()


def test_a_check_before_sign_in_is_a_stop_too(tmp_path, monkeypatch, capsys):
    _state(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(CHECK))
    assert reading.main(["read", "kestrel_achterberg", "-", "--source", "browser",
                         "--name", "Rosalind Achterberg", "--company",
                         "Kestrel Mutual"]) == reading.EXIT["check"]
    assert "LinkedIn showed a check" in capsys.readouterr().out


def test_the_headline_is_the_line_under_the_name_not_the_employer_line():
    r = reading.parse(CARD, name="Rosalind Achterberg", company="Kestrel Mutual",
                      source="browser", today=TODAY)
    assert r["headline"] == "Head, Pricing Analytics | Model Governance | Insurance"
    assert r["location"] == "Manchester, England, United Kingdom"
    assert r["current"] == "Kestrel Mutual"            # from the card when Experience is not loaded
    assert (r["degree"], r["reach"]) == ("2nd", "request")
    assert r["items"] and r["items"][0]["date"] == "2026-10-04"


def test_the_card_never_offers_a_school_as_the_current_employer():
    card = CARD.replace("Kestrel Mutual · University of Leeds", "University of Leeds")
    r = reading.parse(card, name="Rosalind Achterberg", source="browser", today=TODAY)
    assert r["current"] == ""


def test_what_they_call_their_work_grounds_a_note_when_it_was_read_on_their_page():
    r = reading.parse(CARD.split("Activity")[0], name="Rosalind Achterberg",
                      company="Kestrel Mutual", source="browser", today=TODAY)
    ok, why = reading.grounded("your work on model governance in insurance pricing", r)
    assert ok and why.startswith("their headline")
    # A snippet's title alone is not a reading: nothing from their page, nothing grounded.
    snippet = {"name": "Rosalind Achterberg", "company": "Kestrel Mutual",
               "headline": r["headline"], "sources": [{"kind": "public"}], "items": []}
    assert not reading.grounded("your work on model governance in insurance pricing", snippet)[0]
    assert any(kind == "headline" for _, kind, _, _ in reading.hooks(r, TODAY))


def test_an_old_press_line_grounds_nothing():
    r = {"name": "Rosalind Achterberg", "company": "Kestrel Mutual", "sources": [],
         "items": [{"kind": "news", "date": "2018-03-01",
                    "text": "Kestrel Mutual appoints a head of pricing governance"}]}
    assert not reading.grounded("your appointment to lead pricing governance", r)[0]


def test_stop_takes_its_reason_as_a_flag_too(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    assert reading.main(["stop", "--reason", "a CAPTCHA"]) == 0
    assert reading.stopped() == "a CAPTCHA"


def test_the_about_excerpt_ends_on_a_word():
    page = CARD.replace("Activity\n", "About\n" + "governance " * 60 + "\nActivity\n")
    r = reading.parse(page, name="Rosalind Achterberg", source="paste", today=TODAY)
    assert r["about"].endswith("…") and r["about"][:-1].endswith("governance")


def test_words_are_compared_whatever_their_case():
    assert reading._words("Model Governance") == reading._words("model governance") == {"model", "governance"}


def test_a_place_the_persons_own_gate_fails_is_elsewhere_and_an_unknown_one_is_checked():
    # The example person works in Greater Manchester and considers Leeds.
    base = {"headline": "Senior Data Scientist", "company": "Kestrel Mutual", "current": ""}
    assert reading.verdict({**base, "location": "Manchester, England, United Kingdom"})[0]
    assert reading.verdict({**base, "location": "Leeds"}) == (True, "")
    assert not reading.verdict({**base, "location": "London, England, United Kingdom"})[0]
    keep, why = reading.verdict({**base, "location": "Amsterdam"})
    assert keep and why.startswith("caution: based in Amsterdam")
