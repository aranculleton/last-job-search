"""A page a 4.2 chat left behind moves to 4.3's names on the first wake, with nothing done by hand.

4.3 keeps the records only chats write under names of its own (`view` is `screen`, `chats`
is `beats`, `locks` is `holds`, `meta/listener` is `meta/listen`, `meta/current` is
`meta/now`: page_db.STORE). After a person's copy took 4.3, nothing made the new records: the
chat read 4.2's `meta/listener` as if it were `meta/listen`, pinned its first write to a
version that record never had, and the store refused it, as it refused `app.py view`'s first
write to `meta/now`, until the records were made by hand (the maintainer's copy, 2026-10-29).

The store here is a folder that keeps the real one's rules (tests/test_one_chat_answers_the_
page.py): a create is refused when the record exists, a pinned write when the record is
missing or its version moved on, and a batch is all or nothing. A read saves what ArtifactData's
`out_dir` saves: the fields alone, "~" spelled "@", and a 4.2 record carries no `_v`.
Every chat id and employer is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import page_db  # noqa: E402
import test_one_chat_answers_the_page as one  # noqa: E402

NOW = "2026-10-29T09:00:00Z"
CHAT = "cloud-juno"

# What a 4.2 chat left in the store: {collection/doc id: (fields, the store's version)}.
OLD = {
    "meta/listener": ({"chat": CHAT, "title": "Job search", "kind": "cloud",
                       "since": "2026-10-20T08:00:00Z", "answered_at": "2026-10-28T17:00:00Z",
                       "watching": True}, 9),
    "meta/current": ({"rev": "r-42", "made_at": "2026-10-28T17:00:00Z", "model": "m-42",
                      "by": CHAT}, 14),
    "meta/doorbell": ({"at": "2026-10-28T16:59:00Z", "text": "[app]"}, 3),
    "view/jobs": ({"rev": "r-42", "made_at": "2026-10-28T17:00:00Z",
                   "data": {"rows": [{"id": "r1-1", "company": "Harbourline"}]}}, 14),
    "view/todo": ({"rev": "r-42", "made_at": "2026-10-28T17:00:00Z", "data": []}, 14),
    "chats/cloud-juno": ({"kind": "cloud", "title": "Job search (cloud)", "can": ["draft"],
                          "seen_at": "2026-10-28T17:00:00Z", "busy": None}, 22),
    "locks/employer~harbourline": ({"work": "draft~harbourline", "chat": CHAT,
                                    "since": "2026-10-28T16:50:00Z",
                                    "until": "2026-10-28T17:50:00Z"}, 2),
}
NEW_NAME = {"meta/listener": "meta/listen", "meta/current": "meta/now",
            "view/jobs": "screen/jobs", "view/todo": "screen/todo",
            "chats/cloud-juno": "beats/cloud-juno",
            "locks/employer~harbourline": "holds/employer~harbourline"}

# What every wake reads first (the app skill, "1. Read, in one go"), and what an update that
# left the page's code alone reads before `app.py view` (app_listen.after_update).
WAKE = ("actions", "receipts", "work", "beats", "holds", "meta", "talk")
REFRESH = ("screen", "meta", "addr")


@pytest.fixture
def copy(tmp_path):
    c = one.Copy(tmp_path)
    c.page(current=True)
    for path, (fields, version) in OLD.items():
        coll, doc_id = path.split("/")
        os.makedirs(os.path.join(c.db, coll), exist_ok=True)
        with open(os.path.join(c.db, coll, doc_id + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"data": fields, "version": version}, fh)
    yield c
    sys.path.remove(c.root)


def read(copy, out, collections):
    """ArtifactData query with out_dir, once for each collection: the fields alone."""
    for coll in collections:
        src = os.path.join(copy.db, coll)
        if not os.path.isdir(src):
            continue
        for name in os.listdir(src):
            with open(os.path.join(src, name), encoding="utf-8") as fh:
                doc = json.load(fh)
            os.makedirs(os.path.join(out, coll), exist_ok=True)
            with open(os.path.join(out, coll, name.replace("~", "@")), "w", encoding="utf-8") as fh:
                json.dump(doc["data"], fh)
    return out


def stored(copy, path):
    p = os.path.join(copy.db, *path.split("/")) + ".json"
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def batches(said):
    return [ln for ln in said.splitlines() if ln.endswith(".json")]


def test_the_first_wake_on_4_3_moves_every_record_and_its_own_writes_land(copy, tmp_path):
    d = read(copy, str(tmp_path / "wake"), WAKE)
    said = copy.run("listen", d, "--chat", CHAT, "--out", str(tmp_path / "out"), "--now", NOW)
    if batches(said):
        # Before the fix: the check-in pinned meta/listen to a version it never had.
        assert copy.send(said), "the first wake's own write was refused:\n" + said
    # The chat is asked, once, to read what 4.2 left, into the same folder.
    assert "view" in said and "chats" in said and "locks" in said and not batches(said)
    read(copy, d, ("view", "screen", "chats", "beats", "locks", "holds"))
    said = copy.run("listen", d, "--chat", CHAT, "--out", str(tmp_path / "out"), "--now", NOW)
    assert batches(said) and copy.send(said), said
    # Every record has its new one, with the old one's fields and the version it really has.
    for old, new in NEW_NAME.items():
        got = stored(copy, new)
        assert got is not None, f"{new} was not made from {old}"
        fields = {k: v for k, v in got["data"].items() if k != "_v"}
        if new != "meta/listen":
            assert fields == OLD[old][0], new
        assert got["data"]["_v"] == got["version"], f"{new}: _v is what the store holds"
    listen = stored(copy, "meta/listen")
    assert listen["data"]["chat"] == CHAT and listen["data"]["answered_at"] == NOW
    assert listen["version"] == 2, "made from meta/listener, then this wake's check-in"
    assert stored(copy, "meta/moved") is not None
    assert stored(copy, "meta/doorbell")["version"] == 3, "the page's own records are left alone"
    assert stored(copy, "meta/listener")["version"] == 9, "the old record is never overwritten"
    # The rest of the wake reads the same folder: its pinned writes land too.
    out = json.loads(copy.run("view", str(tmp_path / "view"), "--dump", d, "--now", NOW,
                              "--chat", CHAT))
    assert all(one_batch for one_batch in out["batches"])
    assert copy.send("\n".join(out["batches"])), "app.py view after the move was refused"
    assert stored(copy, "meta/now")["version"] == 2
    # The next wake has nothing to move and nothing to ask.
    d2 = read(copy, str(tmp_path / "wake2"), WAKE)
    said = copy.run("listen", d2, "--chat", CHAT, "--out", str(tmp_path / "out2"), "--now", NOW)
    assert "older version" not in said and "move" not in said.lower()
    assert batches(said) and copy.send(said), said
    assert stored(copy, "meta/listen")["version"] == 3


def test_an_update_that_refreshes_the_page_first_lands_where_4_2_left_it(copy, tmp_path):
    """An update that left the page's code alone runs `app.py view` before any wake."""
    d = read(copy, str(tmp_path / "data"), REFRESH)
    out = json.loads(copy.run("view", str(tmp_path / "view"), "--dump", d, "--now", NOW,
                              "--chat", CHAT))
    assert copy.send("\n".join(out["batches"])), "the first write to meta/now was refused"
    assert stored(copy, "meta/now")["data"]["_v"] == stored(copy, "meta/now")["version"] == 1
    # The wake that follows still moves what is left, and lands.
    d = read(copy, str(tmp_path / "wake"), WAKE + ("view", "screen", "chats", "locks"))
    said = copy.run("listen", d, "--chat", CHAT, "--out", str(tmp_path / "out"), "--now", NOW)
    assert batches(said) and copy.send(said), said
    assert stored(copy, "holds/employer~harbourline") and stored(copy, "beats/cloud-juno")
    assert stored(copy, "meta/now")["data"]["rev"] != "r-42", "a newer record is never overwritten"


def test_a_record_under_both_names_reads_as_the_new_one_and_nothing_moves_twice(tmp_path):
    d = tmp_path / "d"
    (d / "meta").mkdir(parents=True)
    (d / "meta" / "listen.json").write_text(json.dumps({"chat": "new", "_v": 4}), encoding="utf-8")
    (d / "meta" / "listener.json").write_text(json.dumps({"chat": "old"}), encoding="utf-8")
    (d / "view").mkdir()
    (d / "view" / "jobs.json").write_text(json.dumps({"rev": "old"}), encoding="utf-8")
    (d / "screen").mkdir()
    (d / "screen" / "jobs.json").write_text(json.dumps({"rev": "new", "_v": 6}), encoding="utf-8")
    db = page_db.load(str(d))
    assert db["meta"]["listener"] == {"data": {"chat": "new"}, "version": 4}
    assert db["view"]["jobs"] == {"data": {"rev": "new"}, "version": 6}
    got = page_db.move(db, str(d), str(tmp_path / "out"), "2026-10-29T09:00:00Z", "c")
    names = {(e["collection"], e["doc_id"]) for e in got["entries"]}
    assert names == {("meta", "moved")}, "only the mark: both records have their new one"
    page_db.moved_into(str(d), got)
    again = page_db.move(page_db.load(str(d)), str(d), str(tmp_path / "out2"),
                         "2026-10-29T09:00:00Z", "c")
    assert again["entries"] == [] and page_db.to_read(str(d), page_db.load(str(d))) == []
