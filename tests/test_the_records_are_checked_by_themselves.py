"""The checks of the person's records run by themselves, as upgrades, never only on request.

The independent review of NW-28, NW-23 and NW-32 (2026-11-11): `reading.py unlinked`,
`record_drafts.py check` and `company_research.py check` were commands nothing ran, and a
contact whose profile had been read before the fix kept its blank employer for good. Now one
instant upgrade fills each blank employer a saved reading names (`reading.py link-all`), and
one upgrade a chat applies lists what the person's own records disagree about that it can put
right: a letter its row does not name, a research file without its employer or named apart
from its key, a reading kept under a name its contact does not have. What nobody can put
right (a document with no row, research with no fetched day) is said by the commands and never
keeps the upgrade waiting. Every person and employer is invented.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import csv_store  # noqa: E402
import docpaths  # noqa: E402
import person  # noqa: E402
import profile_upgrades as U  # noqa: E402
import record_drafts  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    return st


def _up(uid):
    return U.by_id(uid)


def _reading(st, cid, data):
    folder = st / "documents" / "network" / cid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "reading.json").write_text(json.dumps(data), encoding="utf-8")


def test_a_blank_employer_a_saved_reading_names_is_filled_by_an_instant_upgrade(state):
    import state as network_state
    path = str(state / "network_contacts.csv")
    rows = network_state.load_contacts(path)
    rows.append({"contact_id": "halvorsen", "name": "Ines Halvorsen", "company": "",
                 "status": "awaiting_reply"})
    network_state.save_contacts(rows, path)
    _reading(state, "halvorsen", {"name": "Ines Halvorsen", "company": "",
                                  "current": "Ashgrove Ledger", "read_on": "2026-11-01",
                                  "sources": [], "items": []})
    up = _up("readings-linked")
    assert up.cost == "instant" and "1" in up.pending()
    import subprocess
    subprocess.run([sys.executable, os.path.join(ROOT, *up.command[1].split("/")),
                    *up.command[2:]], check=True, cwd=ROOT, capture_output=True)
    row = next(r for r in network_state.load_contacts(path) if r["contact_id"] == "halvorsen")
    assert row["company"] == "Ashgrove Ledger"
    assert up.pending() == ""


def test_what_a_chat_can_put_right_keeps_the_records_upgrade_waiting_and_nothing_else(state):
    up = _up("records-agree")
    assert up.pending() == ""
    # A document no row names, and research with no fetched day: said, never waiting.
    for rel in (docpaths.resume_rel("Ottergate"),):
        p = person.state(*rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write("x")
    folder = state / "company_research"
    folder.mkdir(exist_ok=True)
    (folder / "marlowe-cartage.json").write_text(json.dumps(
        {"company": "Marlowe Cartage", "facts": [{"text": "a"}], "sources": ["x"]}),
        encoding="utf-8")
    assert up.pending() == ""
    # A letter on disk that its row does not name: a chat names it.
    tracker = person.state("job_search_tracker.csv")
    rows = csv_store.read_rows(tracker, record_drafts.HEADER)
    rows.append({"date": "2026-11-04", "company": "Ottergate Foods", "role": "Pricing Analyst",
                 "status": "applied", "cv_file": docpaths.resume_rel("Ottergate"),
                 "cover_letter_file": ""})
    csv_store.write_rows(tracker, rows, record_drafts.HEADER)
    p = person.state(*docpaths.letter_rel("Ottergate").split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write("x")
    assert "1 letter" in up.pending()
    # Research named apart from its key, and a reading kept under a name its contact lacks.
    (folder / "ashgrove-ledger-inc.json").write_text(json.dumps(
        {"company": "Ashgrove Ledger", "fetched_date": "2026-11-01", "sources": ["x"],
         "facts": [{"text": "a"}]}), encoding="utf-8")
    _reading(state, "fernhill_halloway_x", {"name": "Wren Halloway", "company": "",
                                            "read_on": "2026-11-01", "sources": [],
                                            "items": []})
    got = up.pending()
    assert "1 research file" in got and "1 reading" in got
