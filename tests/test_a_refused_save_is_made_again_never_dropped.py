"""A save the page refused is made again, never dropped in silence.

A person's copy (2026-11-05): the page refused a save because a record had changed since it
was read. The chat did what the refusal says, `app.py version` with the number the store
gave, and ran `app.py view` again over the same folder: it wrote only `meta/now`, and every
screen of the refused batch was dropped without a word. The folder had taken the batch as
landed before it was sent (page_db.keep_landed), so the view run again found its own unsent
screens already there. Now the folder's copy of everything a refused batch (and any sent
after it) moved on is put back as it was, the refused record at the store's number, so the
same command makes the whole save again; refused a second time, it says so plainly and the
save stays waiting. The store is the folder that keeps the real one's rules. Every person,
employer, page and chat id is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import page_db  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_the_page_helper_stays_thin as T  # noqa: E402
from test_the_page_helper_stays_thin import read, wake  # noqa: E402

NEXT_DAY = "2026-10-27T09:00:00Z"


@pytest.fixture
def ring(tmp_path, monkeypatch):
    yield from T.ring.__wrapped__(tmp_path, monkeypatch)


def _view(r, d, now=NEXT_DAY):
    got = json.loads(r.run("view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT, "--now",
                           now, LJS_PAGE_MIRROR=r.mirror, ok=(0, 2)))
    entries = []
    for b in got["batches"]:
        with open(b, encoding="utf-8") as fh:
            entries += json.load(fh)
    return got, {f"{e['collection']}/{e['doc_id']}": e.get("if_version") for e in entries}


def _page_changes(r, coll, doc_id):
    """The page writes the record after the chat read it: the store's number moves on."""
    path = os.path.join(r.db, coll, doc_id + ".json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["version"] += 1
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return doc["version"]


def _send(r, got):
    import fake_db
    return all(fake_db.apply(r.db, b) for b in got["batches"])


def test_a_refused_save_is_made_again_in_the_same_folder_and_lands(ring):
    first, _ = read(ring, "r1")
    wake(ring, first)
    got, _ = _view(ring, first, R.NOW)
    assert _send(ring, got)
    d, _ = read(ring, "r2", now=NEXT_DAY)
    wake(ring, d, now=NEXT_DAY)
    now_at = _page_changes(ring, "screen", "due")
    got, before = _view(ring, d)
    assert "screen/due" in before and len(before) > 2, before
    assert not _send(ring, got)                       # refused: the page changed it
    said = ring.run("version", d, "screen/due", str(now_at), LJS_PAGE_MIRROR=ring.mirror)
    assert "back in it to be saved again" in said, said
    got, again = _view(ring, d)
    # The whole refused save, not only meta/now: every record it held, the refused one pinned
    # to the number the store gave.
    assert set(before) <= set(again), (before, again)
    assert again["screen/due"] == now_at, again
    assert _send(ring, got), again


def test_refused_again_it_says_so_plainly_and_the_save_still_waits(ring):
    first, _ = read(ring, "r1")
    wake(ring, first)
    assert _send(ring, _view(ring, first, R.NOW)[0])
    d, _ = read(ring, "r2", now=NEXT_DAY)
    wake(ring, d, now=NEXT_DAY)
    at = _page_changes(ring, "screen", "due")
    got, _ = _view(ring, d)
    assert not _send(ring, got)
    ring.run("version", d, "screen/due", str(at), LJS_PAGE_MIRROR=ring.mirror)
    at = _page_changes(ring, "screen", "due")       # changed once more while it was saved
    got, _ = _view(ring, d)
    assert not _send(ring, got)
    said = ring.run("version", d, "screen/due", str(at), LJS_PAGE_MIRROR=ring.mirror, ok=(3,))
    assert "refused this save of screen/due again" in said and "Nothing is lost" in said, said
    assert "Read the page again into a new folder" in said, said
    # Still waiting, never dropped: the same folder makes it again, and it lands now.
    got, again = _view(ring, d)
    assert again.get("screen/due") == at, again
    assert _send(ring, got)


def test_only_the_refused_batch_and_those_after_it_are_put_back(tmp_path):
    d = str(tmp_path / "dump")
    os.makedirs(os.path.join(d, "work"))
    with open(os.path.join(d, "work", "draft~one.json".replace("~", "@")), "w", encoding="utf-8") as fh:
        json.dump({"kind": "draft", "status": "queued", "_v": 3}, fh)
    first = page_db.Writes(str(tmp_path / "a"), db=page_db.load(d))
    first.add("set", "work", "draft~one", {"kind": "draft", "status": "running"})
    landed = first.save("claim")
    page_db.keep_landed(d, landed)
    second = page_db.Writes(str(tmp_path / "b"), db=page_db.load(d))
    second.add("set", "view", "due", {"rev": "x", "data": []})
    second.add("set", "work", "draft~one", {"kind": "draft", "status": "done"})
    page_db.keep_landed(d, second.save("view"))
    db = page_db.load(d)
    assert db["work"]["draft~one"]["version"] == 5 and "due" in db["view"]
    # The second batch was refused: its records are as the first left them.
    assert set(page_db.put_back(d, "screen/due")) == {"screen/due", "work/draft~one"}
    db = page_db.load(d)
    assert db["work"]["draft~one"] == {"data": {"kind": "draft", "status": "running"},
                                       "version": 4}
    assert "due" not in db["view"]
    assert page_db.put_back(d, "screen/due") == []         # nothing sent holds it now
