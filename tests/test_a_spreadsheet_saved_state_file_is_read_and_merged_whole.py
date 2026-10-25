"""A state file a spreadsheet saved is read whole and merges row by row.

Excel's "CSV UTF-8" starts a file with a byte-order mark; the merge driver read it as part
of the first column's name, so every contact_id in a merged contact book and message log
came back empty, and every tracker row lost its date, with no conflict said. Excel's plain
"CSV" saves in Windows' own encoding, and an accented letter followed by a curly quote or a
dash ("André’s") was read as damaged UTF-8: every accented name in the file turned into a
question mark in a diamond, and the next save wrote that for good. Every name and row here
is invented.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import csv_store  # noqa: E402
import merge_state  # noqa: E402

MARK = "﻿"
BOOK = "contact_id,name,company,status\n"
TWO = ("acme_halloway,Wren Halloway,Acme,awaiting_reply\n"
       "brindle_castellan,Juno Castellan,Brindle,in_conversation\n")
NEW = "corvid_rook,Ana Rook,Corvid,not_contacted\n"
LOG = "contact_id,date,direction,channel,scenario,summary,full_text\n"
MSGS = ("acme_halloway,2026-10-01,out,message,first_note,First note sent,Hi Wren\n"
        "brindle_castellan,2026-10-03,out,message,first_note,First note sent,Hi Juno\n")
TRACKER = "date,company,role,status,notes\n"
APPS = "2026-09-01,Acme,Analyst,applied,\n2026-09-02,Brindle,Planner,applied,\n"


def _rows(text, tmp_path):
    p = tmp_path / "merged.csv"
    p.write_text(text, encoding="utf-8", newline="")
    return csv_store.read_rows(str(p))


@pytest.mark.parametrize("marked", ["ours", "theirs", "both", "base", "all"])
def test_a_marked_contact_book_keeps_every_id(tmp_path, marked):
    sides = {"base": BOOK + TWO, "ours": BOOK + TWO, "theirs": BOOK + TWO + NEW}
    for side in (("ours", "theirs") if marked == "both" else
                 ("base", "ours", "theirs") if marked == "all" else (marked,)):
        sides[side] = MARK + sides[side]
    text, problems = merge_state.merge(sides["base"], sides["ours"], sides["theirs"],
                                       "network_contacts.csv")
    assert problems == []
    assert not text.startswith(MARK) and text.splitlines()[0] == BOOK.strip()
    rows = _rows(text, tmp_path)
    assert [r["contact_id"] for r in rows] == ["acme_halloway", "brindle_castellan",
                                               "corvid_rook"]


def test_a_marked_message_log_keeps_every_message_to_its_person(tmp_path):
    from network import state
    added = "acme_halloway,2026-10-05,in,message,,They replied,Happy to chat\n"
    text, problems = merge_state.merge(LOG + MSGS, MARK + LOG + MSGS, LOG + MSGS + added,
                                       "network_threads.csv")
    assert problems == [] and not text.startswith(MARK)
    rows = _rows(text, tmp_path)
    assert [(r["contact_id"], r["date"]) for r in rows] == [
        ("acme_halloway", "2026-10-01"), ("brindle_castellan", "2026-10-03"),
        ("acme_halloway", "2026-10-05")]
    assert state.derive_status([r for r in rows if r["contact_id"] == "acme_halloway"]) \
        == "replied_needs_response"


def test_a_marked_tracker_keeps_every_date_and_both_changes(tmp_path):
    ours = MARK + TRACKER + APPS.replace("Analyst,applied", "Analyst,interview")
    theirs = TRACKER + APPS + "2026-09-05,Corvid,Analyst,applied,\n"
    text, problems = merge_state.merge(TRACKER + APPS, ours, theirs, "job_search_tracker.csv")
    assert problems == []
    rows = _rows(text, tmp_path)
    assert [(r["date"], r["company"], r["status"]) for r in rows] == [
        ("2026-09-01", "Acme", "interview"), ("2026-09-02", "Brindle", "applied"),
        ("2026-09-05", "Corvid", "applied")]


def test_a_marked_json_state_file_merges():
    base = {"a": {"status": "seen"}}
    ours = dict(base, b={"status": "excluded"})
    theirs = dict(base, c={"status": "seen"})
    text, problems = merge_state.merge(json.dumps(base), MARK + json.dumps(ours),
                                       json.dumps(theirs), "job_scraper/seen_jobs.json")
    assert problems == [] and set(json.loads(text)) == {"a", "b", "c"}


def test_the_driver_writes_the_file_back_unmarked_and_reads_windows_encoding(tmp_path,
                                                                             monkeypatch):
    monkeypatch.setattr(merge_state, "git_later", lambda path: None)
    monkeypatch.setattr(merge_state, "eol", lambda path: None)
    base, ours, theirs = tmp_path / "O", tmp_path / "A", tmp_path / "B"
    base.write_bytes((BOOK + TWO).encode("utf-8"))
    ours.write_bytes(codecs_bom() + (BOOK + TWO).encode("utf-8"))
    theirs.write_bytes((BOOK + TWO + "zoe_halloway,Zoë Halloway,Corvid,not_contacted\n")
                       .encode("cp1252"))
    assert merge_state.main([str(base), str(ours), str(theirs), "network_contacts.csv"]) == 0
    saved = ours.read_bytes()
    assert not saved.startswith(codecs_bom())
    assert saved.decode("utf-8").splitlines()[-1] == "zoe_halloway,Zoë Halloway,Corvid,not_contacted"


def test_the_driver_leaves_a_damaged_side_to_gits_own_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(merge_state, "git_later", lambda path: None)
    base, ours, theirs = tmp_path / "O", tmp_path / "A", tmp_path / "B"
    for p in (base, ours):
        p.write_bytes((BOOK + "lukasz_w,Łukasz Wren,Acme,\n").encode("utf-8"))
    theirs.write_bytes((BOOK + "lukasz_w,Łukasz Wren,Acme,\n").encode("utf-8")
                       + b"bad,\xff,x,\n")
    before = ours.read_bytes()
    got = merge_state.main([str(base), str(ours), str(theirs), "network_contacts.csv"])
    assert got == merge_state.COULD_NOT and ours.read_bytes() == before


def codecs_bom():
    import codecs
    return codecs.BOM_UTF8


HEAD = "contact_id,name,company,notes\r\n"
WINDOWS = ("zoe_d,Zoë Halloway,Acme,André’s old team\r\n"
           "jose_n,Ana Núñez,Brindle,Zoë–Brindle intro\r\n"
           "ines_o,Inès,Corvid,met at the “data” meetup; 30° and sunny\r\n")


@pytest.mark.parametrize("body", [
    WINDOWS,
    "zoe_d,Zoë Halloway,Acme,André’s old team\r\n",
    "jose_n,JOSÉ’S Café,Brindle,Ñ \r\nines_o,Inès,Corvid,é–\r\n",
])
def test_a_file_in_windows_encoding_keeps_every_accented_name(tmp_path, capsys, body):
    p = tmp_path / "network_contacts.csv"
    p.write_bytes((HEAD + body).encode("cp1252"))
    rows = csv_store.read_rows(str(p), ("contact_id", "name"))
    want = [line.split(",") for line in body.strip("\r\n").split("\r\n")]
    assert [[r["contact_id"], r["name"], r["company"], r["notes"]] for r in rows] == want
    assert "�" not in p.read_text(encoding="utf-8")
    assert p.read_bytes() == (HEAD + body).encode("utf-8")
    csv_store.write_rows(str(p), rows, ("contact_id", "name"))
    assert p.read_bytes() == (HEAD + body).encode("utf-8")


def test_a_damaged_utf8_file_is_never_saved_over(tmp_path, capsys):
    p = tmp_path / "network_contacts.csv"
    body = (HEAD + "lukasz_w,Łukasz,Acme,\r\nzoe_d,Zoë,Brindle,\r\n").encode("utf-8") \
        + b"bad,Ren\xe9e,Corvid,\r\n"
    p.write_bytes(body)
    rows = csv_store.read_rows(str(p), ("contact_id", "name"))
    assert rows[0]["name"] == "Łukasz" and "�" in rows[2]["name"]
    assert "line 4" in capsys.readouterr().err
    with pytest.raises(csv_store.Unreadable) as e:
        csv_store.write_rows(str(p), rows, ("contact_id", "name"))
    assert "line 4" in str(e.value) and isinstance(e.value, csv_store.Conflicted)
    assert p.read_bytes() == body


def test_the_other_readers_of_a_state_file_read_the_mark_and_windows_encoding(tmp_path):
    import build_app
    import rehearse_sync
    tracker = tmp_path / "job_search_tracker.csv"
    tracker.write_bytes(b"\xef\xbb\xbf" + "date,company,role,status\r\n2026-10-01,Café Brûlé,"
                        "Analyst,interview\r\n".encode("utf-8"))
    assert build_app._csv(str(tracker))[0]["date"] == "2026-10-01"
    tracker.write_bytes("date,company,role,status\r\n2026-10-01,Café Brûlé,Analyst,"
                        "interview\r\n".encode("cp1252"))
    assert rehearse_sync._live_interviews(str(tmp_path)) == [("Café Brûlé", "Analyst")]
    assert csv_store.decode("Zoë’s".encode("cp1252")) == ("Zoë’s", csv_store.CP1252)
