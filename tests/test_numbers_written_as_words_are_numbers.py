"""A number written as a word is a number, to the resume check and to the claim map alike.

`tools/check_numbers.py` read digits only, and `tools/draft_audit.py` uses the same reader
for its claim map. So "seven years" changed to "twelve years" in a summary, "eleven
spreadsheets" to "forty spreadsheets" in a letter bullet, "more than 30" to "more than
thirty-five" and "two hours" to "five hours" all passed both checks, and a rendered batch
said BATCH: ALL PASS with "twelve years" on the resume. The fixture itself spells numbers
("eleven"), so drafters do write them. Every employer and figure here is invented.

Then the other way: how long a call would take ("a thirty-minute conversation", "happy to
talk for fifteen minutes"), a stretch of time ("or half the morning") and a date ("on 21
October") were hard findings in correct letters, while "over a decade of experience" for
a seven-year profile and "by a factor of three" were never read.
"""
from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import check_numbers  # noqa: E402
import draft_audit  # noqa: E402
import draft_pack  # noqa: E402
from test_one_drafting_call_per_posting import FIXTURE, store_pages  # noqa: E402

GOOD = FIXTURE["draft"]
PICK = {"company": FIXTURE["company"], "role": FIXTURE["role"], "slug": FIXTURE["slug"],
        "abbr": FIXTURE["abbr"], "ask_first": ["SAP"], "skills_no": ["SAP"], "skills_yes": []}


def _edited(field, old, new):
    d = copy.deepcopy(GOOD)
    if field.startswith("cl_bullets"):
        i = int(field[len("cl_bullets["):-1])
        assert old in d["cl_bullets"][i]["text"]
        d["cl_bullets"][i]["text"] = d["cl_bullets"][i]["text"].replace(old, new)
    else:
        assert old in d[field]
        d[field] = d[field].replace(old, new)
    for c in d["claim_map"]:
        if c["field"] == field and old in c["sentence"]:
            c["sentence"] = c["sentence"].replace(old, new)
    return d


def _audit(d):
    store_pages()
    return draft_audit.mechanical(dict(d, pack_hash=draft_pack.rules_hash()), PICK,
                                  FIXTURE["posting"], FIXTURE["research"],
                                  corpus={"openings": set(), "closings": set()})


@pytest.mark.parametrize("text,want", [
    ("replaced forty spreadsheets", {(40.0, "")}),
    ("in twelve years", {(12.0, "year")}),
    ("saving five hours a day", {(5.0, "hour")}),
    ("more than thirty-five managers", {(35.0, "")}),
    ("two hundred and fifty stores", {(250.0, "")}),
    ("a dozen suppliers", {(12.0, "")}),
    ("half a million customers", {(500000.0, "")}),
    ("two and a half years", {(2.5, "year")}),
    ("twenty-five per cent", {(25.0, "%")}),
    # A share is read as the percentage it is, a multiple as one.
    ("halved forecast error", {(50.0, "%")}),
    ("cut it by a third", {(33.0, "%")}),
    ("two thirds of claims", {(67.0, "%")}),
    ("tripled sign-ups", {(3.0, "x")}),
    # An ordinal that counts.
    ("for the fifth consecutive year", {(5.0, "year")}),
    # A hyphen joins a unit to its number, digits or words.
    ("a 9-hour job", {(9.0, "hour")}),
    ("a daily two-hour reconciliation", {(2.0, "hour")}),
    # Decades are years, a factor is a multiple.
    ("over a decade of experience", {(10.0, "year")}),
    ("two decades in retail", {(20.0, "year")}),
    ("cut errors by a factor of three", {(3.0, "x")}),
    ("a factor of 10 faster", {(10.0, "x")}),
    # Minutes said of the work are still a claim.
    ("cut the nightly run from 45 minutes to 3", {(45.0, "")}),
])
def test_a_spelled_out_figure_is_read_as_the_figure(text, want):
    assert check_numbers.claims(text) == want


@pytest.mark.parametrize("text", [
    "one of the analysts", "a third party", "the first half of 2026", "in a quarter",
    "the third quarter", "five ten-minute calls",
    "I would welcome a thirty-minute conversation", "I would welcome a 30-minute call",
    "Happy to talk for fifteen minutes", "or half the morning", "half of the week",
    "I could talk on 21 October", "free from October 21st"])
def test_words_that_are_not_figures_stay_out(text):
    assert check_numbers.claims(text) == set()


def test_the_figure_reads_the_same_on_the_profile_side():
    # "eleven spreadsheets" and "a daily two-hour reconciliation" are in the example profile:
    # the draft's "eleven" and "two hours" are grounded by them, and the fixture passes.
    got = check_numbers.grounded()
    assert (11.0, "") in got and (2.0, "hour") in got and (7.0, "year") in got
    assert check_numbers.check_draft(dict(GOOD, posting=FIXTURE["posting"])) == []


@pytest.mark.parametrize("field,old,new", [
    ("summary", "seven years", "twelve years"),
    ("cl_bullets[2]", "eleven spreadsheets", "forty spreadsheets"),
    ("cl_bullets[2]", "more than 30", "more than thirty-five"),
    ("cl_bullets[1]", "two hours", "five hours"),
])
def test_the_audits_own_examples_are_held_back(field, old, new):
    d = _edited(field, old, new)
    m = _audit(d)
    assert "number" in {f["rule"] for f in m["findings"]}, m["findings"]
    assert "number-not-in-cited" in {f["flag"] for f in m["flags"]}
    # And the render-time check that verify_batch.sh runs says so too.
    assert check_numbers.check_draft(dict(d, posting=FIXTURE["posting"]))


def test_a_posting_figure_never_grounds_the_summary_or_a_letter_bullet():
    posting = FIXTURE["posting"] + "\nThe reporting covers 12 regional operations managers."
    d = _edited("cl_bullets[2]", "more than 30 operations managers", "12 operations managers")
    found = check_numbers.check_draft(dict(d, posting=posting))
    assert [f["source"].rsplit(".", 1)[-1] for f in found] == ["cl_bullets[2]"]
    # The close may still say the posting's figure back to it.
    d = _edited("p4", "in your data.", "in your data across those 12 managers.")
    assert check_numbers.check_draft(dict(d, posting=posting)) == []


P4_LAST = ("Which kinds of claim move most with the weather is the first thing I would want to "
           "look at in your data.")


@pytest.mark.parametrize("field,old,new", [
    ("p4", P4_LAST, "I would welcome a thirty-minute conversation about which kinds of claim "
                    "move most with the weather."),
    ("p4", P4_LAST, "I could talk on 21 October, and the first thing I would look at is which "
                    "claims move with the weather."),
    ("cl_bullets[1]", "ending two hours of checking a day",
     "ending two hours of checking a day, or half the morning"),
])
def test_a_call_a_stretch_of_time_and_a_date_are_not_findings(field, old, new):
    m = _audit(_edited(field, old, new))
    assert "number" not in {f["rule"] for f in m["findings"]}, m["findings"]


@pytest.mark.parametrize("field,old,new", [
    ("summary", "seven years", "over a decade"),
    ("cl_bullets[2]", "that replaced eleven spreadsheets",
     "that cut errors by a factor of three"),
])
def test_a_decade_and_a_factor_are_checked_like_years_and_multiples(field, old, new):
    d = _edited(field, old, new)
    assert check_numbers.check_draft(dict(d, posting=FIXTURE["posting"])), (field, new)
    assert "number" in {f["rule"] for f in _audit(d)["findings"]}
