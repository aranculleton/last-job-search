"""One contact's status, next action, its date and a note change by command.

From a real repo on 2026-10-21: there was no command for it, so the contact book was edited
by hand, a note with line breaks broke the file, and it had to be restored from master.
The people are invented.
"""
from __future__ import annotations

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import schema  # noqa: E402
import state  # noqa: E402

ROWS = [{"contact_id": "oakmere_castellan", "name": "Juno Castellan", "company": "Oakmere Foods",
         "status": "in_conversation", "notes": "met at the meetup"},
        {"contact_id": "kestrel_haldane", "name": "Corwin Haldane", "company": "Kestrel Mutual",
         "status": "awaiting_reply"}]


def _book(tmp_path):
    path = tmp_path / "network_contacts.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=schema.CONTACT_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in schema.CONTACT_COLUMNS} for r in ROWS)
    return path


def test_set_changes_one_row_and_keeps_the_file_one_line_a_row(tmp_path, capsys):
    path = _book(tmp_path)
    args = ["--contacts", str(path), "--threads", str(tmp_path / "none.csv"),
            "--today", "2026-10-21"]
    assert state.main(["set", "Juno Castellan", "--status", "call_booked", "--next-action",
                       "Call on Thursday\nabout the forecast team", "--due", "2026-10-23",
                       "--note", "She suggested\nthe planning lead", *args]) == 0
    out = capsys.readouterr().out
    assert out.startswith("oakmere_castellan (Juno Castellan, Oakmere Foods): status call_booked")
    rows = state.load_contacts(str(path))
    juno = rows[0]
    assert (juno["status"], juno["next_action"], juno["next_action_due"]) == (
        "call_booked", "Call on Thursday about the forecast team", "2026-10-23")
    assert juno["notes"] == "met at the meetup; 2026-10-21: She suggested the planning lead"
    assert rows[1]["status"] == "awaiting_reply"                     # the rest untouched
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3   # one line a row
    # Cleared, and refused when it would write nonsense.
    assert state.main(["set", "oakmere_castellan", "--due", "", *args]) == 0
    assert state.load_contacts(str(path))[0]["next_action_due"] == ""
    for bad in (["--status", "booked"], ["--due", "next week"], []):
        assert state.main(["set", "oakmere_castellan", *bad, *args]) == 1
    assert state.main(["set", "Nobody Here", "--status", "closed", *args]) == 1
