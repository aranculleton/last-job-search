"""A page update built again before the first was sent keeps every change (issue 358).

A person's copy: `app.py view` built a batch of sixteen writes over a folder read from the
page. Before it was sent, something it covered changed, and the chat ran `view` again into a
fresh out folder over the same read. The second run made two writes, the person's learned
rules and `meta/now`: the other fourteen were taken as already on the page, because the
folder had taken the first batch as landed when it was built (page_db.keep_landed). And
`meta/now` was pinned one version higher on every rebuild while the page still held the
number read, so even those two would have been refused.

What the folder takes as the page's state moves only once a batch is known to be on the page:
the app's hook saw it sent (PostToolUse on ArtifactData), or a later batch was, since batches
go in order and a refused one stops the rest. A new update built over a batch never seen sent
replaces it whole, pinned to the versions last read. The store is the folder that keeps the
real one's rules. Every person, page and chat id is invented.
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


@pytest.fixture(autouse=True)
def versions(tmp_path, monkeypatch):
    """The copy's own record of what its hook has seen, kept in a folder of the test's."""
    monkeypatch.setenv("LJS_VERSIONS", str(tmp_path / "git" / page_db.KNOWN_VERSIONS))
    os.makedirs(tmp_path / "git", exist_ok=True)
    page_db._KNOWN_PATH.clear()
    yield
    page_db._KNOWN_PATH.clear()


@pytest.fixture
def ring(tmp_path, monkeypatch):
    yield from T.ring.__wrapped__(tmp_path, monkeypatch)


def _view(r, d, out):
    got = json.loads(r.run("view", os.path.join(d, out), "--dump", d, "--chat", R.CHAT,
                           "--now", R.NOW, LJS_PAGE_MIRROR=r.mirror, ok=(0, 2)))
    entries = []
    for b in got["batches"]:
        with open(b, encoding="utf-8") as fh:
            entries += json.load(fh)
    return got, {f"{e['collection']}/{e['doc_id']}": e.get("if_version") for e in entries}


def _send(r, got):
    """The store takes each batch, and the app's hook sees each one that landed, as Claude
    Code hands it over after the call (fake_db.apply: `learned.py hook`, PostToolUse on
    ArtifactData)."""
    import fake_db
    return all(fake_db.apply(r.db, b) for b in got["batches"])


def test_an_update_built_again_unsent_keeps_every_change_pinned_to_the_read(ring):
    page_db._mark_sends_seen()          # this copy's hook has recognised a send before
    d, _ = read(ring, "r1")
    wake(ring, d)
    _, first = _view(ring, d, "v1")
    assert "meta/now" in first and len(first) > 2, first
    # Never sent: built again into a fresh out folder over the same read.
    got, again = _view(ring, d, "v2")
    assert set(first) <= set(again), (sorted(first), sorted(again))
    assert again == first, (first, again)
    # And a third time: nothing climbs.
    _, third = _view(ring, d, "v3")
    assert third == first, (first, third)
    # The last one built lands whole.
    assert _send(ring, got)


def test_an_update_seen_sent_is_kept_so_the_next_pins_past_it(ring):
    d, _ = read(ring, "r1")
    wake(ring, d)
    got, first = _view(ring, d, "v1")
    assert _send(ring, got)
    _, again = _view(ring, d, "v2")
    # What the first wrote is on the page: the next is pinned past it, and lands.
    assert again.get("meta/now") == (first["meta/now"] or 0) + 1, (first, again)
    assert all(again[k] != first[k] for k in again if k in first and first[k] is not None)


def test_a_batch_seen_sent_after_another_says_the_one_before_landed_too(tmp_path):
    d = str(tmp_path / "dump")
    os.makedirs(os.path.join(d, "work"))
    with open(os.path.join(d, "work", "one.json"), "w", encoding="utf-8") as fh:
        json.dump({"kind": "draft", "status": "queued", "_v": 3}, fh)
    page_db.mark_listed(d, 1, hook=True, versions={"work/one": 3})
    first = page_db.Writes(str(tmp_path / "a"), db=page_db.load(d))
    first.add("set", "work", "one", {"kind": "draft", "status": "running"})
    a = first.save("claim")
    page_db.keep_landed(d, a)
    second = page_db.Writes(str(tmp_path / "b"), db=page_db.load(d))
    second.add("set", "work", "one", {"kind": "draft", "status": "done"})
    b = second.save("view")
    page_db.keep_landed(d, b, by="view")
    with open(b[0], encoding="utf-8") as fh:
        page_db.keep_sent_event({"tool_name": "ArtifactData", "tool_response": "ok",
                                 "tool_input": {"action": "batch", "writes": json.load(fh)}})
    assert page_db.unconfirmed(d) == []
    # Nothing to put back before the next update: both are on the page.
    assert page_db.replace_unsent(d, "view") == []
    assert page_db.load(d)["work"]["one"]["version"] == 5


def test_a_refused_send_is_never_taken_as_sent(tmp_path):
    d = str(tmp_path / "dump")
    os.makedirs(d)
    page_db.mark_listed(d, 0, hook=True)
    page_db._mark_sends_seen()
    w = page_db.Writes(str(tmp_path / "a"), db=page_db.load(d))
    w.add("set", "work", "one", {"kind": "draft", "status": "running"})
    b = w.save("view")
    page_db.keep_landed(d, b, by="view")
    with open(b[0], encoding="utf-8") as fh:
        writes = json.load(fh)
    page_db.keep_sent_event({"tool_name": "ArtifactData", "tool_input": {"action": "batch",
                             "writes": writes}, "tool_response": {"is_error": True,
                             "error": "version conflict on work/one"}})
    assert len(page_db.unconfirmed(d)) == 1
    assert page_db.replace_unsent(d, "view") == ["work/one"]
    assert "one" not in page_db.load(d)["work"]


def _one_kept(tmp_path, body):
    d = str(tmp_path / "dump")
    os.makedirs(d)
    page_db.mark_listed(d, 0, hook=True)
    w = page_db.Writes(str(tmp_path / "a"), db=page_db.load(d))
    w.add("set", "work", "one", body)
    b = w.save("view")
    page_db.keep_landed(d, b, by="view")
    with open(b[0], encoding="utf-8") as fh:
        return d, json.load(fh)


def test_until_the_hook_has_recognised_a_send_nothing_is_put_back(tmp_path):
    # A send event in a shape the hook cannot read would otherwise make every update sent be
    # put back and made again: until one is recognised, a rebuild works as before the fix.
    d, _ = _one_kept(tmp_path, {"kind": "draft", "status": "running"})
    assert not page_db.sends_seen()
    assert page_db.replace_unsent(d, "view") == []
    assert "one" in page_db.load(d)["work"]


def test_a_landed_batch_whose_words_say_failed_is_still_taken_as_sent(tmp_path):
    # Only the response's own error flag is a refusal: a record holding "failed" or "refused"
    # in its words, echoed back, never makes a batch that landed look unsent.
    d, writes = _one_kept(tmp_path, {"kind": "draft", "status": "failed",
                                     "said": "the first try was refused"})
    page_db.keep_sent_event({"tool_name": "ArtifactData",
                             "tool_input": {"action": "batch", "writes": writes},
                             "tool_response": {"results": [{"doc_id": "one",
                                                             "status": "failed, refused"}]}})
    assert page_db.sends_seen() and page_db.unconfirmed(d) == []
