"""A label above the words to say is never shown as words of its own.

From the maintainer, 2026-11-07: an interview prep on their page had a section of its own,
"Only if she asks how you got started", and it showed three bullets: "SAY." on its own, the
story, then "Note to you, not to say: ..." as a bullet beside it. The chat that finished the
document had set the story apart with a cue word on a line of its own, and the page read
every line of a section as an item. Now a bare label ("SAY.", "**Say this:**", "TALKING
POINT") is no item and no word of an answer, the words under it are; a note to the person
rides under the item it is about, apart from the words to say; and the check fails a
document that still carries such a label, so the chat takes it out where it wrote it.

Every person, employer and story here is invented.
"""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import interview_pack as P  # noqa: E402
import prep  # noqa: E402

STORY = ("I started on the warehouse floor at Brackenfield, counting what we had against what "
         "the system said, and I've wanted the two to agree ever since.")
NOTE = "Note to you, not to say: this also answers why Pellow Freight was only six months."


def _doc(section_lines):
    return ("# Interview prep: Fernhill Freight\n\n## On one screen\n\n- They're checking fit.\n\n"
            "## Only if she asks how you got started\n\n" + "\n".join(section_lines) + "\n\n"
            "## Notes\n\n- Nothing yet: anything you want kept, write it here.\n")


def _section(text, title="Only if she asks how you got started"):
    got = P.reading(text)
    return next(s for s in got["sections"] if s["title"] == title)


@pytest.mark.parametrize("label", ["SAY.", "- SAY.", "SAY:", "Say:", "**SAY**", "**SAY:**",
                                   "**Say this:**", "say this", "TALKING POINT", "Talking points:",
                                   "*Say it aloud*", "What to say:", "- **SAY.**"])
def test_the_section_shows_the_words_and_the_note_apart_never_the_label(label):
    for shape in ([label, "", STORY, "", NOTE],
                  ["- " + label.lstrip("- "), "- " + STORY, "- " + NOTE]):
        sec = _section(_doc(shape))
        assert [i["text"] for i in sec["items"]] == [STORY], (label, sec["items"])
        assert sec["items"][0]["note"] == [NOTE]


def test_a_label_at_the_head_of_the_words_is_taken_off_them():
    sec = _section(_doc(["**SAY:** " + STORY, NOTE]))
    assert [i["text"] for i in sec["items"]] == [STORY]
    assert P.plain_line("- Say this: " + STORY)[0] == STORY


def test_a_bare_note_label_makes_what_follows_a_note_and_a_say_label_ends_it():
    sec = _section(_doc(["NOTE", "Keep it under a minute.", "", "SAY.", STORY]))
    assert [i["text"] for i in sec["items"]] == ["", STORY]
    assert sec["items"][0]["note"] == ["Keep it under a minute."]


def test_ordinary_lines_that_start_with_the_same_words_are_kept():
    lines = ["Say what you'd change first, then why.", "Answer the question they asked.",
             "Notes from the call are under Earlier rounds."]
    sec = _section(_doc(lines))
    assert [i["text"] for i in sec["items"]] == lines
    assert not any(i.get("note") for i in sec["items"])
    assert all(prep.cue(ln) == "" for ln in lines)
    # The pack's own heading over its list of things to say is the pack's, never a stray cue.
    assert prep.cue("**Say these**") == ""


def test_an_answer_never_says_the_label_or_the_note():
    said = prep.spoken_lines(["SAY.", STORY, NOTE])
    assert said == [STORY]
    # Said again after a note: "SAY" above words ends the note.
    assert prep.spoken_lines(["Notes:", "- keep it short", "**Say this:**", STORY]) == [STORY]


def test_the_check_fails_a_document_with_a_label_on_a_line_of_its_own():
    found = prep.cue_lines(_doc(["SAY.", STORY, NOTE]))
    assert found and found[0][0] == "the document" and '"SAY."' in found[0][1]
    assert prep.failures(found) == found
    # A label inside code is the code's, and a note label is a note.
    assert prep.cue_lines("```\nSAY:\n```\n\nNotes:\n- keep it short\n") == []


def test_a_call_prep_on_the_page_never_shows_the_label(tmp_path):
    import app_model
    path = tmp_path / "prep.md"
    path.write_text("# Call with Ines\n\n## How you got started\n\n**SAY:**\n\n" + STORY + "\n\n"
                    + NOTE + "\n", encoding="utf-8")
    shown = app_model._prep_text(str(path))
    assert "SAY" not in shown and STORY in shown and NOTE in shown
