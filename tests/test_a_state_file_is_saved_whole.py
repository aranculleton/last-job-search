"""A save keeps every column a person typed and never leaves half a file.

Two ways a save lost what was in a state file. A column added by hand with a space after its
name ("Referral notes ", which a spreadsheet keeps) was read under the trimmed name and
written under the typed one, so the first save by any tool emptied it; a schema column typed
that way gained a second copy at the end. And the file was rewritten in place, so a save
stopped half way (a closed laptop, a killed chat) left half the message log. Every name
here is invented.
"""
import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import csv_store  # noqa: E402

COLUMNS = ("contact_id", "name", "status")


def test_a_hand_added_column_with_a_stray_space_keeps_its_values(tmp_path):
    p = tmp_path / "network_contacts.csv"
    p.write_text("contact_id,name,status ,Referral notes \n"
                 "acme_halloway,Wren Halloway,awaiting_reply,met at the Leeds meetup\n",
                 encoding="utf-8")
    rows = csv_store.read_rows(str(p), COLUMNS)
    assert rows[0]["Referral notes"] == "met at the Leeds meetup"
    rows[0]["status"] = "replied_needs_response"
    csv_store.write_rows(str(p), rows, COLUMNS)
    again = csv_store.read_rows(str(p), COLUMNS)
    assert again[0]["Referral notes"] == "met at the Leeds meetup"
    assert again[0]["status"] == "replied_needs_response"
    assert csv_store.header(str(p)) == ["contact_id", "name", "status", "Referral notes"]


def test_a_save_stopped_half_way_leaves_the_file_as_it_was(tmp_path, monkeypatch):
    p = tmp_path / "network_threads.csv"
    rows = [{"contact_id": f"c{i}", "name": "x", "status": ""} for i in range(500)]
    csv_store.write_rows(str(p), rows, COLUMNS)
    before = p.read_bytes()
    written = {"n": 0}
    real = csv.DictWriter.writerow

    def stop(self, row):
        written["n"] += 1
        if written["n"] > 250:
            raise KeyboardInterrupt
        return real(self, row)

    monkeypatch.setattr(csv.DictWriter, "writerow", stop)
    with pytest.raises(KeyboardInterrupt):
        csv_store.write_rows(str(p), rows + [{"contact_id": "new"}], COLUMNS)
    assert p.read_bytes() == before
    assert sorted(f.name for f in tmp_path.iterdir()) == ["network_threads.csv"]
