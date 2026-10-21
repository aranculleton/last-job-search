"""A rebuild of the interview pack changes only what the tool wrote.

From a sync audit on 2026-10-21: a living document is finished by hand, and a rebuild kept
only the sections it knew (Your answers, To rework, Notes, what they found out). A question
added under Ask them, a section for the panel round, the close: all gone, with nothing
said. On a copy of a real repo a hand-finished document for a process with rounds still to
come lost 94 lines, five whole sections. Now what the tool wrote last time is kept beside
the document, every other line is the person's and stays where they put it, and a rebuild
that would still lose one writes nothing and says so.

Every person, employer, question and answer here is invented; the candidate is the example
person and the application is test_interview_pack's.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.dirname(os.path.abspath(__file__))]

import interview_pack as P  # noqa: E402
import test_interview_pack as base  # noqa: E402

app = base.app                  # the invented application, its own fixture
LATER = "2026-03-12"
# Beside the living document: what the tool wrote last time (interview.md says so).
RECORD = ".interview_prep.built.json"

ASKED = "- How does the depot team hear about a change to the forecast?"
PANEL = ("## If it goes to a panel\n\n"
         "### What would you change first in the weekly forecast?\n"
         "I'd start with the depots that miss most often, because that's where a better number "
         "pays back first.\n")


def _path(folder):
    return os.path.join(folder, P.LIVING)


def _doc(folder):
    with open(_path(folder), encoding="utf-8") as fh:
        return fh.read()


def _save(folder, text):
    with open(_path(folder), "w", encoding="utf-8") as fh:
        fh.write(text)


def _build(today=base.TODAY, *extra):
    return P.main(["pack", base.COMPANY, "--today", today, "--write", *extra])


def _section(text, title):
    return text.split("## %s\n" % title, 1)[1].split("\n## ", 1)[0]


def _heads(text):
    return [ln[3:] for ln in text.splitlines() if ln.startswith("## ")]


def _person_lines(old, generated):
    """The non-blank lines of `old` that the tool did not write, in order."""
    from collections import Counter
    gen = Counter(generated.splitlines())
    out = []
    for ln in old.splitlines():
        if gen[ln]:
            gen[ln] -= 1
        elif ln.strip():
            out.append(ln)
    return out


def test_a_question_under_ask_them_and_a_section_of_their_own_survive(app, capsys):
    """The audit's case: three lines added, three lines kept, each in its place."""
    assert _build() == 0
    text = _doc(app)
    close = next(ln for ln in _section(text, "Ask them").splitlines() if "(the close:" in ln)
    text = text.replace(close + "\n", close + "\n" + ASKED + "\n", 1)
    text = text.replace("## Warm route\n", PANEL + "\n## Warm route\n", 1)
    _save(app, text)
    capsys.readouterr()
    assert _build(LATER) == 0
    again = _doc(app)
    assert "Last updated %s." % LATER in again              # the tool's own lines refreshed
    assert ASKED in _section(again, "Ask them")
    assert PANEL in again                                    # byte for byte
    heads = _heads(again)
    assert heads.index("If it goes to a panel") == heads.index("Ask them") + 1
    assert heads[heads.index("If it goes to a panel") + 1] == "Warm route"
    # Built again with nothing new, it is the same document: nothing doubled.
    assert _build(LATER) == 0 and _doc(app) == again


# A hand-finished document, the shape the audit found: five sections of the person's own,
# answers under headings of their own, notes, a question added and one reworded.
OWN = {
    "On one screen": "## Before the call\n\n- Charge the headset; join five minutes early.\n"
                     "- Have the depot dashboard open on the second screen.\n",
    "Your answers": "## Only if they ask how you got started\n\n"
                    "### How did you get into planning?\n"
                    "I started on the warehouse floor, counting what we had against what the "
                    "system said, and I've wanted the two to agree ever since.\n",
    "Stories": "## If it goes to a panel\n\n### Who would you bring with you on a change?\n"
               "The planners first, because they live with the number every morning.\n\n"
               "Notes:\n- keep it under a minute\n",
    "Ask them": "## For the hiring manager\n\n- What would a good first quarter look like?\n"
                "- Which depot keeps you up at night?\n",
    "Notes": "## The close\n\nThank you for the time. I'd like the role, and I can start one "
             "month after an offer.\n",
}
NOTE = "- Shirin asked for the slides by Friday."


def _hand_finish(text):
    for after, own in OWN.items():
        nxt = P.SECTIONS[P.SECTIONS.index(after) + 1] if after != "Notes" else None
        if nxt:
            text = text.replace("\n## %s\n" % nxt, "\n%s\n## %s\n" % (own, nxt), 1)
        else:
            text = text.rstrip() + "\n\n" + own
    close = next(ln for ln in _section(text, "Ask them").splitlines() if "(the close:" in ln)
    text = text.replace(close + "\n", close + "\n" + ASKED + "\n", 1)
    text = text.replace("## Notes\n\n" + P.NOTES_EMPTY, "## Notes\n\n" + NOTE, 1)
    return text


def test_a_hand_finished_pack_keeps_five_sections_of_its_own_through_a_rebuild(app, capsys):
    assert _build() == 0
    generated = _doc(app)                       # built just now: every line is the tool's
    _save(app, _hand_finish(_doc(app)))
    mine = _person_lines(_doc(app), generated)
    assert len(mine) >= 15
    # What the tool reads changes: new research, so its own sections are rebuilt.
    research = os.path.join(os.environ["LJS_STATE"], "company_research", "fernhill-freight.json")
    with open(research, encoding="utf-8") as fh:
        data = __import__("json").load(fh)
    data["recent_news"].append({"claim": "Opened a second cross-dock, in Doncaster, in "
                                         "February 2026.",
                                "source_url": "https://fernhill.example/news/doncaster"})
    with open(research, "w", encoding="utf-8") as fh:
        __import__("json").dump(data, fh)
    capsys.readouterr()
    assert _build(LATER) == 0
    again = _doc(app)
    assert "Doncaster" in again and "Last updated %s." % LATER in again
    for after, own in OWN.items():
        assert own.rstrip() in again, own[:40]               # every section, byte for byte
        heads = _heads(again)
        title = own.splitlines()[0][3:]
        assert heads.index(title) == heads.index(after) + 1, title   # where it was
    assert P._missing(mine, again) == []                     # every line of theirs
    rest = iter(again.splitlines())
    assert all(any(ln == x for x in rest) for ln in mine)   # and in the order they wrote them
    assert ASKED in _section(again, "Ask them") and NOTE in _section(again, "Notes")
    # What the tool wrote is kept beside the document, and none of theirs is in it.
    with open(os.path.join(app, RECORD), encoding="utf-8") as fh:
        assert "For the hiring manager" not in fh.read()


def test_a_line_of_theirs_the_tool_does_not_change_stays_as_they_wrote_it(app):
    assert _build() == 0
    text = _doc(app)
    first = _section(text, "Ask them").strip().splitlines()[0]
    mine = first.rstrip(")") + ", in their own words)" if first.endswith(")") else first + " Mine."
    _save(app, text.replace(first, mine, 1))
    assert _build(LATER) == 0
    ask = _section(_doc(app), "Ask them")
    assert mine in ask and first not in ask.splitlines()


def test_a_rebuild_that_would_lose_a_line_writes_nothing_and_says_so(app, capsys, monkeypatch):
    assert _build() == 0
    text = _doc(app)
    close = next(ln for ln in _section(text, "Ask them").splitlines() if "(the close:" in ln)
    text = text.replace(close + "\n", close + "\n" + ASKED + "\n", 1)
    _save(app, text)
    # Whatever goes wrong in the merge, the check before writing catches it: here a merge
    # that drops the person's lines from the section it rebuilt.
    real = P._merge3

    def broken(base_, ours, new):
        out, mine = real(base_, ours, new)
        return [ln for ln in out if ln not in mine], mine
    monkeypatch.setattr(P, "_merge3", broken)
    capsys.readouterr()
    assert _build(LATER) == 1
    assert _doc(app) == text                                 # untouched
    err = capsys.readouterr().err
    assert "1 line(s) you wrote would have been lost" in err and "nothing was written" in err
    assert ASKED[2:30] in err


def test_a_document_written_by_hand_is_never_replaced(app, capsys):
    hand = ("# Fernhill Freight: the technical round\n\n## Say first\n\nI'm the planner who "
            "cut forecast error at a multi-site network.\n")
    _save(app, hand)
    capsys.readouterr()
    assert _build() == 1
    assert _doc(app) == hand
    err = capsys.readouterr().err
    assert "written by hand" in err and "nothing was written" in err
    # Renaming it is the person's call, never a background upgrade's.
    assert "Only if the person wants the tool's document as well: rename that file" in err
    # Shown without --write, the pack is a preview: it says what a write would do, and runs.
    assert P.main(["pack", base.COMPANY, "--today", base.TODAY]) == 0
    assert "if written: " in capsys.readouterr().err and _doc(app) == hand


def test_an_older_document_with_no_record_loses_nothing(app, capsys):
    """Built before the record existed, a document cannot say which lines are the tool's.
    A section of their own stays where it was; a line in one of the tool's sections that the
    new build does not write is kept at the end of Notes, and the rebuild says so."""
    assert _build() == 0
    if os.path.exists(os.path.join(app, RECORD)):
        os.remove(os.path.join(app, RECORD))
    text = _doc(app)
    close = next(ln for ln in _section(text, "Ask them").splitlines() if "(the close:" in ln)
    text = text.replace(close + "\n", close + "\n" + ASKED + "\n", 1)
    text = text.replace("## Warm route\n", PANEL + "\n## Warm route\n", 1)
    _save(app, text)
    capsys.readouterr()
    assert _build(LATER) == 0
    out = capsys.readouterr().out
    again = _doc(app)
    assert PANEL in again
    heads = _heads(again)
    assert heads.index("If it goes to a panel") == heads.index("Ask them") + 1
    notes = _section(again, "Notes")
    assert P.LEFTOVER_HEAD in notes and ASKED in notes
    # The tool's own lines from the older build are never kept as if they were theirs.
    assert "Last updated %s" % base.TODAY not in again
    assert "kept from the version before this one: 1 line(s)" in out
    # From here on there is a record: built again, nothing moves and nothing doubles.
    assert _build(LATER) == 0 and _doc(app) == again
