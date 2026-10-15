"""Regressions the networking rework shipped, caught by a person's own profile tests.

- "Hi Robin, Saw the post": the first note and the InMail capitalised the clause after
  the greeting comma when the profile has no opener;
- "<City>, <Other City> or remote" read "remote" before the named city and lost tier 1;
- "After 6 years at <Employer>, on to the next thing." stopped reading as a departure;
- "We are not hiring on my team right now." stopped counting as a no, because "my team"
  is a generous cue, so the stop-after-two-nos rule never fired;
- "<City>, ON", the ordinary Canadian form, read as another country, and a postal
  abbreviation in REGION_WORDS matched nearly every post as a word;
- triage's working fields (`undated_signal`, `location_unverified`) could become columns
  in the contact book.
"""
from __future__ import annotations

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import compose  # noqa: E402
import discovery as D  # noqa: E402
import reply  # noqa: E402
import state  # noqa: E402


def test_no_capital_after_the_greeting_comma_without_an_opener():
    note = compose.first_note("Robin Vale", "Saw the post on forecasting at Fernhill",
                              "How is the team set up", opener="")
    assert note.startswith("Hi Robin, saw the post")
    body = compose.inmail("Robin Vale", "Your forecasting post",
                          "Saw the post on forecasting at Fernhill", "How is the team set up",
                          "At Brindle & Hart I cut forecast error from 22% to 14%",
                          opener="").split("\n\n", 1)[1]
    assert body.startswith("Hi Robin, saw the post")


def test_a_named_city_counts_although_the_post_also_says_remote():
    post = "We're hiring data analysts in Leeds, Manchester or remote"
    assert D._signal_reaches_market(post, "Manchester")
    assert D.classify_tier(post, "Head of Data", "Leeds, England, United Kingdom",
                           "Manchester")[0] == 1


def test_on_to_the_next_thing_is_a_departure():
    p = {"name": "Wren Halloway", "title": "Head of Planning",
         "snippet": "After 6 years at Larkspur Retail, on to the next thing."}
    assert D.disqualify(p, "Larkspur Retail")


def test_not_hiring_on_my_team_is_a_no_and_two_of_them_stop_the_thread():
    no = {"contact_id": "x", "direction": "in", "full_text": "We are not hiring on my team right now."}
    one = [dict(no, date="2026-09-01")]
    assert len(reply.declines_in(one)) == 1
    assert reply.should_continue({"contact_id": "x", "status": "in_conversation"}, one)[0]
    two = one + [dict(no, date="2026-09-20")]
    assert not reply.should_continue({"contact_id": "x", "status": "in_conversation"}, two)[0]


def test_a_postal_abbreviation_is_not_another_country_or_a_word(monkeypatch):
    monkeypatch.setattr(D, "_OTHER_COUNTRIES", ("united states", "usa"))
    assert not D._abroad("Calgary, AB")
    assert D._same_market("Calgary, AB", "Calgary")
    assert D._abroad("Calgary, Alberta, United States")
    assert D._free_text(("on", "ab", "alberta", "canada", "uk")) == ("ab", "alberta", "canada", "uk")
    assert "on" not in D._free_text(("on",))


def test_triage_fields_never_become_contact_book_columns(tmp_path):
    path = tmp_path / "network_contacts.csv"
    row = {"contact_id": "acme_reed", "name": "Sasha Reed", "company": "Acme",
           "undated_signal": "We're hiring", "location_unverified": True}
    state.save_contacts([row], str(path))
    header = next(csv.reader(open(path, encoding="utf-8")))
    assert "undated_signal" not in header and "location_unverified" not in header
    # A column somebody added by hand in the spreadsheet is kept.
    text = path.read_text(encoding="utf-8").splitlines()
    path.write_text(text[0] + ",my_column\n" + text[1] + ",kept\n", encoding="utf-8")
    rows = state.load_contacts(str(path))
    state.save_contacts(rows, str(path))
    assert "my_column" in next(csv.reader(open(path, encoding="utf-8")))
    assert state.load_contacts(str(path))[0]["my_column"] == "kept"
