"""A state file a merge left conflict markers in is refused, never read as rows.

From one person's repo: after a real merge conflict the contact book held
"<<<<<<< ours", "=======" and ">>>>>>> theirs". The loaders read the three marker lines
as three contacts and both sides of the conflicted row as two, network/state.py said
nothing needed a person, and the next save wrote the markers back. Invented people only.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import csv_store  # noqa: E402
import state  # noqa: E402
import throttle  # noqa: E402
import what_works  # noqa: E402

BOOK = ("contact_id,name,company,status\n"
        "kestrel_example,Shirin Example,Kestrel Mutual,replied\n"
        "<<<<<<< ours\n"
        "fernhill_haldane,Corwin Haldane,Fernhill Freight,awaiting_reply\n"
        "=======\n"
        "fernhill_haldane,Corwin Haldane,Fernhill Freight,replied\n"
        ">>>>>>> theirs\n")


@pytest.fixture
def conflicted(tmp_path):
    path = tmp_path / "network_contacts.csv"
    path.write_text(BOOK, encoding="utf-8")
    return path


def test_every_reader_refuses_it_and_names_the_file(conflicted):
    for read in (state.load_contacts, what_works._csv, throttle._tracker_rows,
                 lambda p: csv_store.read_rows(p, ("contact_id", "name"))):
        with pytest.raises(csv_store.Conflicted, match="network_contacts.csv has unresolved "
                                                       "merge-conflict markers .* at line 3"):
            read(str(conflicted))


def test_nothing_is_saved_over_it(conflicted):
    with pytest.raises(csv_store.Conflicted):
        csv_store.write_rows(str(conflicted), [{"contact_id": "x", "name": "y"}],
                             ("contact_id", "name"))
    assert conflicted.read_text(encoding="utf-8") == BOOK


def test_a_resolved_file_reads_as_before(tmp_path):
    path = tmp_path / "network_contacts.csv"
    path.write_text(BOOK.replace("<<<<<<< ours\n", "").split("=======\n")[0], encoding="utf-8")
    assert [r["contact_id"] for r in state.load_contacts(str(path))] == \
        ["kestrel_example", "fernhill_haldane"]
    # A line that only starts with the characters, inside a field, is not a marker.
    path.write_text("contact_id,notes\nx,\"======= underlined heading\"\n", encoding="utf-8")
    csv_store.refuse_conflicts(str(path))


def test_the_command_says_so_instead_of_a_traceback(conflicted, tmp_path):
    env = dict(os.environ, LJS_STATE=str(tmp_path), LJS_PROFILE=os.path.join(ROOT, "profile.example"))
    (tmp_path / "network_threads.csv").write_text("contact_id,date,direction\n", encoding="utf-8")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "state.py")],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 1 and "Traceback" not in r.stderr
    assert "network_contacts.csv has unresolved merge-conflict markers" in r.stderr
