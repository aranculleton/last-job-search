"""A stage says what it is, how long it lasts and its time zone when it is booked.

4.6 guessed them from the label's English words (a "test" was something due, a "screen" half
an hour, anything else an hour) and from a short list of zone words with a rule of thumb, so
a stage written in French or German, or a zone like IST, came out wrong or with no time
(docs/NEXT_BUILDER.md, 4.6 items 2 and 4). Invented records only.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import interview_pack  # noqa: E402
import upcoming  # noqa: E402
import what_works  # noqa: E402

HEAD = "# Outcome: Quayside - Analyst\n\n## Interview stages reached\n"


def _read(text):
    return what_works.outcome_stages(text)[0]


def test_a_meeting_keeps_its_length_and_its_zones_own_name():
    text = interview_pack._with_stage(HEAD, "Entretien technique", "2026-11-05", "la responsable",
                                      "14:00", "America/Toronto", minutes=45)
    assert "- [ ] Entretien technique (scheduled 2026-11-05 14:00 America/Toronto, 45 min, " \
           "with la responsable)" in text
    s = _read(text)
    assert (s["kind"], s["minutes"], s["time"], s["zone"], s["with"]) == (
        "meeting", 45, "14:00", "America/Toronto", "la responsable")
    # Moved to another day, what it is and how long it lasts stay.
    again = _read(interview_pack._with_stage(text, "Entretien technique", "2026-11-07"))
    assert (again["date"], again["minutes"]) == ("2026-11-07", 45)


def test_something_due_by_a_day_is_written_as_due_in_any_language():
    text = interview_pack._with_stage(HEAD, "Online-Aufgabe", "2026-11-05", due=True)
    assert "- [ ] Online-Aufgabe (due 2026-11-05)" in text
    s = _read(text)
    assert (s["kind"], s["date"], s["scheduled"], s["time"]) == ("test", "2026-11-05", True, "")


def test_an_older_line_still_reads_as_it_did():
    s = _read(HEAD + "- [ ] Phone screen (scheduled 2026-11-05 10:00 EST, with Head of Data)\n")
    assert (s["kind"], s["minutes"], s["time"], s["zone"]) == ("", 0, "10:00", "EST")


@pytest.mark.parametrize("word, home, want", [
    ("America/Toronto", "Europe/London", "America/Toronto"),
    ("Mars/Base", "Europe/London", None),           # not a zone: no time, never a wrong one
    ("EST", "Europe/London", "America/New_York"),
    ("JST", "Europe/London", "Asia/Tokyo"),         # not in the app's own short list
    ("IST", "Europe/London", None),                 # India, Ireland and Israel all say IST
    ("IST", "Asia/Kolkata", "Asia/Kolkata"),        # the person's own zone says it
    ("BRT", "Europe/London", None),                 # no zone uses it any more
    ("", "Europe/Berlin", "Europe/Berlin"),
])
def test_a_zone_comes_from_the_standard_librarys_own_zones(word, home, want):
    assert upcoming._zone_word(word, home) == want


def test_a_zone_is_kept_by_its_name_or_its_word_never_as_anything_else():
    assert interview_pack.zone_name("America/Sao_Paulo") == "America/Sao_Paulo"
    assert interview_pack.zone_name("Not/AZone") == ""
    assert interview_pack.zone_name("est") == "EST"
    assert interview_pack.zone_name("eastern time") == ""
