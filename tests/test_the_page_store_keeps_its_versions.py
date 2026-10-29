"""What a chat reads back from the page's database carries the version its next write needs.

ArtifactData's `out_dir` saves a record's fields and nothing else, and spells a "~" in an id
as "@" in the file's name (checked against the store itself, 2026-10-29). Before 4.3 the chat
read every record with no version, so each write to one that existed was refused, and every
id with a "~" came back with an "@" (the maintainer's copy, 2026-10-29). Each write now
carries the version the record will have (`_v`), and the busiest records live under 4.3's
own names, so no write needs a version from before.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import page_db  # noqa: E402


def _dump(tmp, coll, name, body):
    d = tmp / coll
    d.mkdir(parents=True, exist_ok=True)
    (d / (name + ".json")).write_text(json.dumps(body), encoding="utf-8")


def test_a_saved_record_reads_back_with_its_version_and_its_own_id(tmp_path):
    # As out_dir saves them: the fields alone, "~" spelled "@".
    _dump(tmp_path, "work", "talk@cloud-1@m1", {"status": "queued", "_v": 3})
    _dump(tmp_path, "work", "plain", {"status": "done"})
    _dump(tmp_path, "meta", "listen", {"chat": "cloud-1", "_v": 7})
    _dump(tmp_path, "screen", "list@people@1", {"rev": "a", "_v": 2})
    db = page_db.load(str(tmp_path))
    assert db["work"]["talk~cloud-1~m1"] == {"data": {"status": "queued"}, "version": 3}
    # A record from before _v that no chat rewrote was made once, by the page.
    assert db["work"]["plain"]["version"] == 1
    assert db["meta"]["listener"]["version"] == 7, "the code names it listener; the store, listen"
    assert db["view"]["list~people~1"]["version"] == 2


def test_every_write_carries_the_version_it_will_have(tmp_path):
    w = page_db.Writes(str(tmp_path))
    w.add("set", "work", "new~1", {"a": 1})
    w.add("update", "work", "old~1", {"a": 2}, if_version=4)
    w.add("set", "view", "jobs", {"rev": "b"}, if_version=2)
    w.add("set", "meta", "listener", {"chat": "x"})
    body = {e["doc_id"]: json.load(open(e["file_path"], encoding="utf-8")) for e in w.entries}
    assert body["new~1"]["_v"] == 1 and body["old~1"]["_v"] == 5 and body["jobs"]["_v"] == 3
    names = {(e["collection"], e["doc_id"]) for e in w.entries}
    assert ("screen", "jobs") in names and ("meta", "listen") in names
    assert not any("@" in page_db.safe_id(x) for x in ("a@b", "me@example.com"))


def test_a_batch_stays_under_the_tools_limit(tmp_path):
    w = page_db.Writes(str(tmp_path))
    big = "x" * 200_000
    for n in range(9):
        w.add("set", "view", f"part~jobs~{n}", {"text": big})
    paths = w.save("view")
    assert len(paths) >= 3
    for p in paths:
        entries = json.load(open(p, encoding="utf-8"))
        size = sum(os.path.getsize(e["file_path"]) for e in entries)
        assert size <= page_db.BATCH_BYTES and len(entries) <= page_db.BATCH_MAX


def test_addresses_go_in_a_few_records_each_contact_always_in_the_same_one():
    reach = {f"c{n}": {"linkedin": f"https://www.linkedin.com/in/example-person-{n}", "email": None}
             for n in range(3000)}
    docs = page_db.addr_docs(reach)
    assert 1 < len(docs) < 12
    where = {cid: k for k, d in docs.items() for cid in d["contacts"]}
    assert len(where) == 3000
    reach = dict(reach, c5=dict(reach["c5"], email="c5@example.com"))
    again = page_db.addr_docs(reach)
    changed = [k for k in docs if docs[k] != again[k]]
    assert changed == [where["c5"]], "one contact's change rewrites one record"
