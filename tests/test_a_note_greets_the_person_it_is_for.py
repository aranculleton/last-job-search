"""A note greets the person it is for.

`tone.check("Hi Tamsin, ...", name="Riley Reed")` and `compose.validate(...)` both
returned nothing: an unfilled "{first_name}" was caught, a wrong real name was not. A
batch of notes staged together and shuffled by one produces exactly that, and each is
pasted by hand into LinkedIn. It is refused wherever the recipient's name is known, and
no recorded rule lifts it, because it is a mistake rather than a matter of taste.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import compose  # noqa: E402
import outreach  # noqa: E402
import reading  # noqa: E402
import tone  # noqa: E402

WRONG = "Hi Tamsin, I saw we both worked in revenue management. Would you be open to a short chat?"


def _rules(found):
    return [v.rule for v in found]


def test_a_greeting_to_somebody_else_is_refused():
    assert "greeting_wrong_name" in _rules(tone.check(WRONG, name="Riley Reed"))
    found = [v for v in compose.validate(WRONG, "connection", name="Riley Reed")
             if v.rule == "greeting_wrong_name"]
    assert found and "Tamsin" in found[0].text and "Riley Reed" in found[0].text
    # After a subject line, in an InMail, the same.
    inmail = "Subject: Forecasting\n\nHi Tamsin,\n\nA question about peak?"
    assert "greeting_wrong_name" in _rules(tone.check(inmail, name="Riley Reed"))


def test_no_recorded_rule_lifts_it(monkeypatch):
    monkeypatch.setattr(compose, "_overrides", lambda: {"greeting_wrong_name", "check_in"})
    assert "greeting_wrong_name" in _rules(compose.validate(WRONG, "connection",
                                                            name="Riley Reed"))


def test_every_way_of_greeting_the_right_person_passes():
    for text, name in (("Hi Riley, a question?", "Riley Reed"),
                       ("Dear Ms Reed, a question?", "Riley Reed"),
                       ("Good morning Riley! A question?", "Riley Reed"),
                       ("Hi Bob, a question?", "Robert Smith"),
                       ("Hi Sally, a question?", "Xiu Mei (Sally) Ho, PhD"),
                       ("Hi Zoe, a question?", "Zoé Ruíz"),
                       ("Hi Jean-Luc, a question?", "Jean-Luc Castellan"),
                       ("Hi Wren, a question?", "Halloway, Wren"),
                       ("Hi Riley and Sam, a question?", "Sam Okafor"),
                       ("Hi JANE, a question?", "Jane Doe"),
                       ("Hi Jane, a question?", "J. Halloway")):
        assert "greeting_wrong_name" not in _rules(tone.check(text, name=name)), (text, name)


def test_a_greeting_to_nobody_by_name_is_not_judged():
    for text in ("Hi there, a question?", "Dear Hiring Manager, a question?",
                 "Hi Acme team, a question?", "Hello, a question?"):
        assert tone.wrong_greeting(text, "Riley Reed") == [], text
    assert tone.wrong_greeting(WRONG, None) == []


def test_a_composed_note_greets_its_reader():
    note = compose.nudge("Riley Reed", "the peak-season forecast you posted about")
    assert note.startswith("Hi Riley") and tone.wrong_greeting(note, "Riley Reed") == []


def test_a_draft_saved_for_a_contact_that_greets_someone_else_is_not_saved(tmp_path, capsys):
    note = tmp_path / "note.txt"
    note.write_text("Hi Juno, your forecasting post on depot demand caught my eye. How is the "
                    "team set up?", encoding="utf-8")
    path = reading.draft_path("fernhill_freight_halloway")
    before = os.path.exists(path)
    assert reading.main(["draft", "fernhill_freight_halloway", str(note)]) == reading.EXIT["error"]
    out = capsys.readouterr().out
    assert "not saved" in out and "Juno" in out and "Wren Halloway" in out
    assert os.path.exists(path) == before


def test_the_outreach_note_stand_in_name_never_trips_it():
    note = ("Hi Tamsin, I've just applied for the Planning Analyst role at Acme. At Brindle & "
            "Hart I cut forecast error from 22% to 14%. Would a short call this week suit?")
    assert not [p for p in outreach.check_note(note) if p.startswith("greeting_wrong_name")]
