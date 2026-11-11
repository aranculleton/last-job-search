"""An interview is prepared as the round it really is: what the invite or the recruiter said
it is, kept on its record, and the words recruiters and invites use read as the kind they name.

The review of 2026-11-10 booked a second round as "personal experience interview, live Python
coding exercise, 60 minutes" and then built its live prep with no format given: it came out as
a hiring manager interview, and nothing said it was a guess. These pin the round's format on
its record, and every common name for a round read as its kind, or said to be a guess.

Every person, employer and role here is invented; the candidate is the example person.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import interview_pack as P  # noqa: E402
import outreach  # noqa: E402
from test_a_referred_process_gets_one_living_document import FIRM, ROLE, TODAY, state  # noqa: E402,F401

# The invented consulting firm's process, on disk for every test here.
pytestmark = pytest.mark.usefixtures("state")

FORMAT = "personal experience interview, live Python coding exercise, 60 minutes"


def _outcome():
    with open(os.path.join(outreach.app_folder(FIRM, ROLE), "outcome.md"), encoding="utf-8") as fh:
        return fh.read()


def _live(tmp_path, *extra):
    out = tmp_path / "live.json"
    assert P.main(["live", FIRM, "--role", ROLE, "--today", TODAY, "--out", str(out), *extra]) == 0
    return json.loads(out.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the format is kept on the record

def test_the_format_given_when_a_process_is_registered_shapes_its_prep(tmp_path, capsys):
    assert P.main(["process", FIRM, "--contact", "calder_rook_marsh", "--role", ROLE,
                   "--stage", "Second round", "--date", "2026-11-11", "--time", "10:00",
                   "--minutes", "60", "--format", FORMAT, "--today", TODAY]) == 0
    # On the round's own record, under its line, where every later prep reads it.
    assert "- [ ] Second round (scheduled 2026-11-11 10:00, 60 min)\n  - Format: %s\n" % FORMAT \
        in _outcome()
    assert P.stage_format(_outcome(), "Second round") == FORMAT
    capsys.readouterr()
    # The live prep built with no --format is the round that was booked, not a guess.
    doc = _live(tmp_path)
    assert doc["shape"] == "combined:personal+technical", doc["shape_name"]
    assert [p["kind"] for p in doc["parts"]] == ["opening", "personal", "technical", "probes", "close"]
    assert doc["format"] == FORMAT and not doc["assumed"] and doc["minutes"] == 60


def test_a_format_given_when_booking_is_kept_and_a_later_one_replaces_it(tmp_path):
    assert P.main(["process", FIRM, "--contact", "calder_rook_marsh", "--role", ROLE,
                   "--stage", "Second round", "--date", "2026-11-11", "--today", TODAY]) == 0
    assert P.stage_format(_outcome(), "Second round") == ""
    assert P.main(["book", FIRM, "--role", ROLE, "--stage", "Second round", "--date", "2026-11-11",
                   "--time", "10:00", "--format", "case interview and PEI", "--today", TODAY]) == 0
    assert P.stage_format(_outcome(), "Second round") == "case interview and PEI"
    # Rebooked with a new time and no format: the format stays. Given again: the new one.
    assert P.main(["book", FIRM, "--role", ROLE, "--stage", "Second round", "--date", "2026-11-12",
                   "--time", "09:00", "--today", TODAY]) == 0
    assert P.stage_format(_outcome(), "Second round") == "case interview and PEI"
    assert P.main(["book", FIRM, "--role", ROLE, "--stage", "Second round", "--date", "2026-11-12",
                   "--format", FORMAT, "--today", TODAY]) == 0
    text = _outcome()
    assert P.stage_format(text, "Second round") == FORMAT and text.count("Format:") == 1
    # A later round booked before it keeps each format under its own line.
    assert P.main(["book", FIRM, "--role", ROLE, "--stage", "Final round", "--date", "2026-11-20",
                   "--format", "partner interview", "--today", TODAY]) == 0
    text = _outcome()
    assert P.stage_format(text, "Second round") == FORMAT
    assert P.stage_format(text, "Final round") == "partner interview"
    lines = text.splitlines()
    second = next(i for i, ln in enumerate(lines) if ln.startswith("- [ ] Second round"))
    assert lines[second + 1] == "  - Format: " + FORMAT
    # Nothing that reads the stages reads the format as a stage of its own.
    import what_works
    assert [s["label"] for s in what_works.outcome_stages(text) if s["scheduled"]] == ["Second round", "Final round"]


def test_a_format_said_to_the_live_prep_is_kept_on_the_record_once_it_is_written(tmp_path):
    assert P.main(["process", FIRM, "--contact", "calder_rook_marsh", "--role", ROLE,
                   "--stage", "Second round", "--date", "2026-11-11", "--today", TODAY]) == 0
    # Built with a format and not written: nothing is kept.
    _live(tmp_path, "--format", FORMAT)
    assert P.stage_format(_outcome(), "Second round") == ""
    # The format the record holds wins over an older prep's, and --format over both.
    P.keep_format(outreach.app_folder(FIRM, ROLE), "Second round", "case interview and PEI")
    assert _live(tmp_path)["shape"] == "case"
    assert _live(tmp_path, "--format", FORMAT)["shape"] == "combined:personal+technical"


class _Book:
    """What app_model.referrer_of reads of the page's context: the contact book."""
    def __init__(self, contacts):
        self.contacts, self.live, self._memo = contacts, {}, {}

    def _once(self, key, make):
        return self._memo.setdefault(key, make())


def test_the_process_contact_is_its_referrer_only_when_they_referred():
    # The night-before run (2026-11-10): a recruiting coordinator registered as the process's
    # contact showed as "Referred by <name>" on the interview's card and its prep. Only someone
    # who put the person forward is a referrer.
    import app_model
    coord = {"contact_id": "calder_rook_coordinator", "name": "Pip Lander", "company": FIRM,
             "title": "Recruiting Coordinator", "status": "call_booked", "route": "cold"}
    referrer = {"contact_id": "calder_rook_vance", "name": "Ivo Vance", "company": FIRM,
                "title": "Associate Partner", "status": "referral_in_progress", "route": "alumni"}
    row = {"company": FIRM, "role": ROLE, "source": "contact:calder_rook_coordinator", "channel": "recruiter"}
    assert app_model.referrer_of(_Book([coord, referrer]), row) is None
    row = dict(row, source="contact:calder_rook_vance", channel="referral")
    assert app_model.referrer_of(_Book([coord, referrer]), row)["contact"] == "calder_rook_vance"


def test_a_new_format_on_the_record_marks_the_saved_live_prep_out_of_date(tmp_path, capsys):
    # The night-before run (2026-11-10): `book --format` changed what the round is, and the
    # saved live prep, made for the old kind, gave no sign until /interview ran again.
    import app_model
    import interview_live
    assert P.main(["process", FIRM, "--contact", "calder_rook_marsh", "--role", ROLE,
                   "--stage", "Second round", "--date", "2026-11-11", "--format", "case interview and PEI",
                   "--today", TODAY]) == 0
    folder = outreach.app_folder(FIRM, ROLE)
    saved = {"version": interview_live.VERSION, "stage": "Second round", "format": "case interview and PEI",
             "parts": [{"id": "p1", "kind": "opening", "say": []}], "questions": [], "checked": {"problems": 0}}
    with open(interview_live.path_for(folder), "w", encoding="utf-8") as fh:
        json.dump(saved, fh)
    text = open(os.path.join(folder, P.LIVING), encoding="utf-8").read()
    stage = {"label": "Second round"}
    assert not app_model._prep_stale(folder, text, stage)
    assert P.main(["book", FIRM, "--role", ROLE, "--stage", "Second round", "--date", "2026-11-11",
                   "--format", FORMAT, "--today", TODAY]) == 0
    assert app_model._prep_stale(folder, text, stage), "a prep made for another kind of round is out of date"
    capsys.readouterr()
    assert P.main(["live-check", FIRM, "--role", ROLE, "--today", TODAY]) == 1
    assert "another kind of round" in capsys.readouterr().out
