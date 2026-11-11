"""A tap on the page reads only what changed, and every save after it lands with no version
typed in by hand (issue 217).

A person's copy, on an ordinary tap with no other chat writing: the read that should bring
back only what changed since the last one brought back every work item not finished, a
follow-up untouched since the day before among them, and the writes after it were refused
until each record's version was typed in with `app.py version`. Work had no field every write
moves, so the read asked for every open item each time. Now every write to a work item, by a
chat or by the page, says when it was made (`changed_at`), the read asks only for what changed
since, and what it does not bring back is laid from the copy this checkout keeps, at the
version the page holds.

Also pinned here: work this checkout wrote that never reached the page is read again before
anything is pinned to it, and a page update from a fresh checkout leaves the Interviews screen
as it is (its prep's time was the file's checkout time, so every such update rewrote it).

The store is the folder that keeps the real one's rules; its reads save what the real one
saves: each record's fields as the last writer left them (its own `_v` stamp, right or wrong),
the version only in the lines it prints, which the app's hook keeps. Every person, employer,
page and chat id is invented.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import repo_files  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_the_page_helper_stays_thin as T  # noqa: E402

DAY_BEFORE = "2026-10-24T09:00:00Z"
TAP_AT = "2026-10-25T18:01:00Z"
LATER = "2026-10-25T18:30:00Z"
FOLLOW = "follow~kestrel"


@pytest.fixture
def ring(tmp_path, monkeypatch):
    yield from T.ring.__wrapped__(tmp_path, monkeypatch)


def query(r, out, q):
    """One query as ArtifactData answers it, the hook keeping the versions it lists."""
    import page_db
    src = os.path.join(r.db, q["collection"])
    listed = []
    if not os.path.isdir(src):
        return listed
    for f in sorted(os.listdir(src)):
        with open(os.path.join(src, f), encoding="utf-8") as fh:
            doc = json.load(fh)
        ok = True
        for field, op, val in q["query"].get("where") or []:
            v = doc["data"].get(field)
            ok = ok and v is not None and (str(v) >= str(val) if op == ">=" else v not in val)
        if not ok:
            continue
        os.makedirs(os.path.join(out, q["collection"]), exist_ok=True)
        path = os.path.join(out, q["collection"], f.replace("~", "@"))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc["data"], fh)
        listed.append(f'- "{f[:-5]}"  {os.path.getsize(path)} bytes  version {doc["version"]}  '
                      f'"{path}"')
    page_db.keep_listed_event({"tool_name": "ArtifactData", "tool_response": listed,
                               "tool_input": dict(q, action="query", out_dir=out)})
    return listed


def read(r, name, now):
    """`app.py reads` and its queries: (the folder, the ids each collection brought back)."""
    out = os.path.join(r.root, name)
    said = r.run("reads", out, "--now", now, LJS_PAGE_MIRROR=r.mirror)
    got: dict = {}
    for line in said.splitlines():
        if line.startswith("{"):
            q = json.loads(line)
            got.setdefault(q["collection"], set()).update(
                re.match(r'- "([^"]+)"', ln).group(1) for ln in query(r, out, q))
    return out, said, got


def send(r, paths):
    """Each batch as the store takes it, in order, stopping at the first it refuses."""
    import fake_db
    for p in paths:
        if not fake_db.apply(r.db, p):
            with open(p, encoding="utf-8") as fh:
                pins = [(e["collection"], e["doc_id"], e.get("if_version")) for e in json.load(fh)]
            return f"refused: {pins}"
    return "landed"


def wake(r, d, now):
    """A wake over `d`, run again with the same folder while it says to, every batch sent."""
    said = ""
    for _ in range(4):
        said = r.run("wake", d, "--chat", R.CHAT, "--kind", "cloud", "--on", "Opus 5.5",
                     "--now", now, LJS_PAGE_MIRROR=r.mirror)
        assert "app.py versions" not in said, said
        assert send(r, [p for p, _ in R.sends(said)]) == "landed", said
        if "run this again with the same folder" not in said:
            break
    return said


def view(r, d, now):
    got = json.loads(r.run("view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT, "--now",
                           now, LJS_PAGE_MIRROR=r.mirror, ok=(0, 2)))
    return got, send(r, got["batches"])


def page_writes(r, wid, **fields):
    """The page's own update to a work item (templates/app/app.js writeWork): its `_v` from its
    own copy of the record, and when it was made."""
    p = os.path.join(r.db, "work", wid + ".json")
    with open(p, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["data"].update(fields, _v=int(doc["data"].get("_v") or 1) + 1, changed_at=TAP_AT)
    doc["version"] += 1
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def drawn_once(r):
    """Two months of use, an open follow-up waiting on the person since the day before (its
    stamp behind the store's own number, as a page with an old copy leaves it), and the page
    read whole and drawn."""
    T.used_page(r)
    r.put("work", FOLLOW, {"kind": "talk", "status": "needs_you", "title": "A follow-up",
                           "to": "cloud", "asked_at": DAY_BEFORE, "asked_you_at": DAY_BEFORE,
                           "changed_at": DAY_BEFORE, "note": "Which day suits you?", "_v": 2},
          version=4)
    d, said, _ = read(r, "r1", R.NOW)
    assert "a whole read" in said, said
    wake(r, d, R.NOW)
    assert view(r, d, R.NOW)[1] == "landed"


def test_a_tap_brings_back_only_what_changed_and_every_save_after_it_lands(ring):
    drawn_once(ring)
    aid = ring.act("job.keep", "r9-3")
    d, said, got = read(ring, "r2", TAP_AT)
    assert "what changed since" in said, said
    assert aid in got.get("actions", set()), got
    # The follow-up nobody touched since the day before stays where it was.
    assert FOLLOW not in got.get("work", set()), got
    assert '"not-in"' not in said, said
    # It is still in the folder, laid from the copy this checkout keeps, at the page's number.
    said = wake(ring, d, TAP_AT)
    assert os.path.isfile(os.path.join(d, "work", FOLLOW.replace("~", "@") + ".json"))
    import page_db
    assert page_db.load(d)["work"][FOLLOW]["version"] == 4
    assert ring.stored("receipts", aid)["data"]["result"] == "ok"
    got_view, sent = view(ring, d, TAP_AT)
    assert sent == "landed", got_view
    # The person answers it on the page: the next read brings back that and nothing else of
    # the work, and the chat's claim, pinned to the number the page holds now, lands.
    page_writes(ring, FOLLOW, status="queued", answered_at=TAP_AT, note=None, asked_you_at=None)
    d, said, got = read(ring, "r3", LATER)
    assert FOLLOW in got.get("work", set()), got
    wake(ring, d, LATER)
    held = ring.stored("work", FOLLOW)
    assert held["data"]["claimed_by"] == R.CHAT and held["data"]["changed_at"], held
    assert view(ring, d, LATER)[1] == "landed"


def test_a_page_on_its_old_code_still_has_every_open_item_read(ring):
    """Until the published page says when it changed a work item, its Stop or answer moves no
    time a read could ask by: the read asks for every item not finished, as before."""
    drawn_once(ring)
    ring.page(current=False)
    _, said, got = read(ring, "r2", TAP_AT)
    assert '"not-in"' in said and FOLLOW in got.get("work", set()), said


def test_work_written_here_that_never_reached_the_page_is_read_again_first(ring):
    """A wake's batch that was never sent (the chat stopped part way) left the copy this
    checkout keeps holding the work as that batch would have left it. Laid from it, the next
    write was pinned one past the page's number and refused; now the work not finished is read
    again into the same folder first, and every save after it lands."""
    drawn_once(ring)
    ring.put("actions", "stop01", {"action": "work.stop", "item": FOLLOW, "at": TAP_AT,
                                   "tab": "t1"})
    d, _, got = read(ring, "r2", TAP_AT)
    assert FOLLOW not in got.get("work", set()), got
    said = ring.run("wake", d, "--chat", R.CHAT, "--kind", "cloud", "--on", "Opus 5.5",
                    "--now", TAP_AT, LJS_PAGE_MIRROR=ring.mirror)
    assert R.sends(said), said                      # the Stop, written here: never sent
    assert not ring.stored("work", FOLLOW)["data"].get("stop_asked")
    d, _, got = read(ring, "r3", LATER)
    assert FOLLOW not in got.get("work", set()), got
    said = ring.run("wake", d, "--chat", R.CHAT, "--kind", "cloud", "--on", "Opus 5.5",
                    "--now", LATER, LJS_PAGE_MIRROR=ring.mirror)
    assert "read again" in said and not R.sends(said), said
    for q in re.findall(r"\{\"collection\".*?\]\]\}\}", said):
        query(ring, d, json.loads(q))
    import page_db
    assert page_db.load(d)["work"][FOLLOW]["version"] == 4     # the page's own, never 5
    wake(ring, d, LATER)                            # every save lands, none typed in
    assert ring.stored("receipts", "stop01")["data"]["result"] == "ok"
    assert view(ring, d, LATER)[1] == "landed"


def _commit(folder):
    git = ["git", "-C", folder, "-c", "user.name=Example", "-c", "user.email=example@example.com",
           "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q", folder], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "state"], check=True,
                   env=dict(os.environ, GIT_COMMITTER_DATE="2026-10-20T10:00:00Z",
                            GIT_AUTHOR_DATE="2026-10-20T10:00:00Z"))


def test_a_page_update_from_a_fresh_checkout_leaves_interviews_as_they_are(ring):
    """Interviews carried each prep's file time, which is when this checkout put the file
    down: a fresh copy, or another chat's folder, rewrote the whole screen, preps and all, with
    nothing in it changed. It carries when the prep was written (its commit)."""
    _commit(ring.state)
    d, _, _ = read(ring, "r1", R.NOW)
    wake(ring, d, R.NOW)
    assert view(ring, d, R.NOW)[1] == "landed"
    assert ring.stored("screen", "interviews"), "the example has an interview with a prep"
    before = ring.stored("screen", "interviews")["version"]
    preps = [str(f) for f in repo_files.files("**/interview_prep.md", root=ring.state)]
    assert preps
    for p in preps:
        os.utime(p, (time.time() - 5000, time.time() - 5000))
    d, _, _ = read(ring, "r2", TAP_AT)
    wake(ring, d, TAP_AT)
    got, sent = view(ring, d, TAP_AT)
    assert sent == "landed", got
    written = [e["doc_id"] for b in got["batches"] for e in json.load(open(b, encoding="utf-8"))]
    assert "interviews" not in written, written
    assert ring.stored("screen", "interviews")["version"] == before


def test_the_page_says_when_it_changed_a_work_item():
    """Every write the page makes to a work item carries `changed_at`, as every chat's does."""
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        js = " ".join(fh.read().split())
    assert 'update(Object.assign(patch, {_v: nextV(cur), changed_at: iso()}))' in js
    assert "attempt: 1, _v: nextV(had), changed_at: iso()}" in js
