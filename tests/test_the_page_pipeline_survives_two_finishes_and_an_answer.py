"""The page's work survives two finishes in a row and the person answering mid-way (T9).

A person's copy and computer, 2026-11-09:
- the page refused every write of a page update ("carried no if_version", then "pinned to
  version 1 and that document is now at version 82"): the files a read saves hold a record's
  fields and nothing else, and its version is only in the lines the read prints, so every pin
  was the record's own stamp, which can be wrong; a chat typed fifty versions by hand;
- two finishes in a row wrote one batch file, and the first was lost, and a second `done`
  refused it as already finished;
- after a claim, the folder still held the item as read: the first pin was refused and the
  finish left a hold behind;
- a written answer to a change asked with the pencil was refused ("Name its thread");
- a page chat message's words were not with its work item.

The store here is the folder that keeps the real one's rules, and its reads save what the real
one saves: the fields alone, the version only in the listing (as ArtifactData does, checked
2026-11-09). Every person, employer, page and chat id is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import page_db  # noqa: E402
import repo_files  # noqa: E402
import test_a_ring_is_answered_in_one_command as R  # noqa: E402
import test_the_page_helper_stays_thin as T  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
NOW = R.NOW
LATER = "2026-10-25T18:20:00Z"


@pytest.fixture
def ring(tmp_path, monkeypatch):
    yield from T.ring.__wrapped__(tmp_path, monkeypatch)


def query(r, out, q):
    """One query as ArtifactData answers it: each record's fields saved as they are (its own
    `_v` stamp, right or wrong, among them), and a line each naming its version."""
    src = os.path.join(r.db, q["collection"])
    lines = []
    if not os.path.isdir(src):
        return lines
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
            json.dump(doc["data"], fh, indent=2)
        lines.append(f'- "{f[:-5]}"  {os.path.getsize(path)} bytes  version {doc["version"]}  "{path}"')
    return lines


def app_in(r, *args, text=""):
    got = subprocess.run([*repo_files.python_on_github(APP), *args], input=text,
                         env=r.env(LJS_PAGE_MIRROR=r.mirror), capture_output=True,
                         encoding="utf-8", errors="replace", timeout=120)
    return got.returncode, got.stdout + got.stderr


def read(r, name, *args, now=NOW):
    """`reads`, its queries, and the step it names after them: the listing kept."""
    out = os.path.join(r.root, name)
    said = r.run("reads", out, "--now", now, *args, LJS_PAGE_MIRROR=r.mirror)
    listing = []
    for line in said.splitlines()[1:]:
        if line.startswith("{"):
            listing += query(r, out, json.loads(line))
    # Where the app's hook is registered it keeps the versions after the read by itself and
    # `reads` asks for no step; here, with no Claude to run it, the test does what it does.
    import page_db
    assert page_db.hook_keeps_versions() or "app.py versions" in said, said
    code, out_said = app_in(r, "versions", out, text="\n".join(listing))
    assert code == 0, out_said
    return out


def land(r, paths):
    import fake_db
    return [fake_db.apply(r.db, p) for p in paths]


def stored(r, coll, doc_id):
    with open(os.path.join(r.db, coll, doc_id + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def page_writes(r, coll, doc_id, **fields):
    """The page's own write: unpinned, its `_v` stamped from its own copy, which never saw the
    chat's last write, so the stamp is one behind the store."""
    doc = stored(r, coll, doc_id)
    doc["data"].update(fields)
    doc["data"]["_v"] = doc["version"]            # one behind what it will be
    doc["version"] += 1
    with open(os.path.join(r.db, coll, doc_id + ".json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def tweak(contact, company):
    return {"kind": "tweak", "title": f"Change the note to {contact}", "to": "either",
            "status": "queued", "asked_at": "2026-10-25T17:30:00Z", "priority": 0, "stage": 0,
            "stages": [], "steps": [], "attempt": 1, "_v": 1,
            "args": {"v": 1, "text": "Make it shorter", "changes": [],
                     "target": {"id": f"msg-{contact}", "output": "message",
                                "contact": contact, "company": company, "rev": "r1"}}}


def test_two_finishes_in_a_row_and_an_answer_mid_way_with_no_version_typed(ring):
    # The page as a person's has it: drawn once, then its screens moved on far past the stamps
    # they carry (a chat that wrote no stamp, an older copy): the store says 80-odd, the files 1.
    d0 = read(ring, "r0")
    T.wake(ring, d0)
    got, ok = T.view(ring, d0)
    assert ok, got
    screens = [f[:-5] for f in os.listdir(os.path.join(ring.db, "screen"))]
    assert screens
    for doc_id in screens:
        doc = stored(ring, "screen", doc_id)
        doc["data"]["_v"] = 1
        doc["version"] += 80
        with open(os.path.join(ring.db, "screen", doc_id + ".json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    # Two changes asked with the pencil, taken in one pass.
    ring.put("work", "tweak~msg-a~1", tweak("contact_alder", "Alder Freight"))
    ring.put("work", "tweak~msg-b~1", tweak("contact_birch", "Birch Labs"))
    d = read(ring, "r1", "--full", now=LATER)
    said = T.wake(ring, d, now=LATER)
    assert all(land(ring, [p for p, _ in R.sends(said)])), said
    for wid in ("tweak~msg-a~1", "tweak~msg-b~1"):
        assert stored(ring, "work", wid)["data"]["status"] == "running", wid
    held = sorted(os.listdir(os.path.join(ring.db, "holds")))
    assert "contact~contact_alder.json" in held and "contact~contact_birch.json" in held, held
    # The person answers on the second one's card while the first is finished.
    page_writes(ring, "work", "tweak~msg-b~1", note_from_person="Keep the thanks")
    code, out = app_in(ring, "done", d, "--work", "tweak~msg-a~1", "--chat", R.CHAT,
                       "--summary", "Her note is shorter now.", "--now", LATER)
    assert code == 0, out
    assert json.loads(out)["locks"], out          # the holds its claim made, freed
    first = json.loads(out)["batches"]
    answer = "Her note is already as short as it can be while it keeps the thanks."
    code, out = app_in(ring, "done", d, "--work", "tweak~msg-b~1", "--chat", R.CHAT,
                       "--summary", "Left as it was.", "--outcome", "unchanged",
                       "--reply-file", "-", "--now", LATER, text=answer)
    assert code == 0, out                         # never "Name its thread"
    second = json.loads(out)["batches"]
    # Two finishes, two batches: the first is never written over by the second.
    assert set(first).isdisjoint(second), (first, second)
    assert land(ring, first) == [True]
    # The second was read before the person's answer: refused, made again with the number the
    # refusal names, and the same `done` makes it again (never "already finished").
    assert land(ring, second) == [False]
    v = stored(ring, "work", "tweak~msg-b~1")["version"]
    code, out = app_in(ring, "version", d, "work/tweak~msg-b~1", str(v))
    assert code == 0, out
    code, out = app_in(ring, "done", d, "--work", "tweak~msg-b~1", "--chat", R.CHAT,
                       "--summary", "Left as it was.", "--outcome", "unchanged",
                       "--reply-file", "-", "--now", LATER, text=answer)
    assert code == 0 and not json.loads(out).get("again"), out
    assert land(ring, json.loads(out)["batches"]) == [True]
    a = stored(ring, "work", "tweak~msg-a~1")["data"]
    b = stored(ring, "work", "tweak~msg-b~1")["data"]
    assert a["status"] == "done" and b["status"] == "done", (a, b)
    assert b["result"]["outcome"] == "unchanged" and b["result"]["answer"] == answer, b
    assert b["note_from_person"] == "Keep the thanks"     # the person's answer kept
    # Both holds deleted (this store keeps a deleted record as an empty one).
    for h in ("contact~contact_alder", "contact~contact_birch"):
        assert not stored(ring, "holds", h)["data"].get("work"), h
    # The page brought up to date from a whole read (a new computer's first): every screen
    # pinned to the store's own number, none to the stamp it carries, and the batch lands.
    d2 = read(ring, "r2", "--full", now=LATER)
    got, ok = T.view(ring, d2, LATER)
    assert ok, got
    # The next ring plans nothing again: both changes are finished.
    d3 = read(ring, "r3", now=LATER)
    said = T.wake(ring, d3, now=LATER)
    assert "tweak~msg-a~1" not in said and "tweak~msg-b~1" not in said, said


def test_a_refusal_naming_no_version_reads_the_record_again_and_saves_once_more(ring):
    """A write that carried no version to a record the folder never held: the record is read
    again, with the rest of what the refused save pinned by its stamp alone, and the save made
    again lands."""
    d0 = read(ring, "r0")
    T.wake(ring, d0)
    got, ok = T.view(ring, d0)
    assert ok, got
    d = read(ring, "r1", "--full", now=LATER)
    # The folder lost one screen (as one never read), and every stamp is wrong.
    victim = sorted(os.listdir(os.path.join(d, "screen")))[0]
    os.remove(os.path.join(d, "screen", victim))
    for name in os.listdir(os.path.join(d, "screen")):
        p = os.path.join(d, "screen", name)
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc.pop(page_db.STORE_VERSION, None)
        doc["_v"] = 1
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    for name in os.listdir(os.path.join(ring.db, "screen")):
        doc = stored(ring, "screen", name[:-5])
        doc["version"] += 5
        doc["data"]["model_note"] = "moved"       # so the view rewrites it
        with open(os.path.join(ring.db, "screen", name), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    T.wake(ring, d, now=LATER)
    got = json.loads(ring.run("view", os.path.join(d, "v"), "--dump", d, "--chat", R.CHAT,
                              "--now", LATER, LJS_PAGE_MIRROR=ring.mirror, ok=(0, 2)))
    assert not all(land(ring, got["batches"]))
    code, said = app_in(ring, "version", d, "screen/" + victim[:-5].replace("@", "~"))
    assert code == 0 and "First read" in said and "screen again into this folder" in said, said
    listing = query(ring, d, {"collection": "screen", "query": {"limit": 1000}})
    code, _ = app_in(ring, "versions", d, text="\n".join(listing))
    assert code == 0
    got = json.loads(ring.run("view", os.path.join(d, "v2"), "--dump", d, "--chat", R.CHAT,
                              "--now", LATER, LJS_PAGE_MIRROR=ring.mirror, ok=(0, 2)))
    assert all(land(ring, got["batches"])), got


def test_a_read_keeps_each_records_version_from_the_lines_it_printed(tmp_path):
    d = str(tmp_path / "d")
    os.makedirs(os.path.join(d, "screen"))
    os.makedirs(os.path.join(d, "work"))
    with open(os.path.join(d, "screen", "due.json"), "w", encoding="utf-8") as fh:
        json.dump({"rev": 3, "_v": 1}, fh)
    with open(os.path.join(d, "work", "tweak-x-1.json"), "w", encoding="utf-8") as fh:
        json.dump({"status": "queued", "_v": 1}, fh)
    outside = str(tmp_path / "elsewhere.json")
    with open(outside, "w", encoding="utf-8") as fh:
        json.dump({"x": 1}, fh)
    listing = "\n".join([
        f'1 document from collection "screen" saved as JSON files under "{d}/screen":',
        f'- "due"  13 bytes  version 82  "{d}/screen/due.json"',
        f'- "elsewhere"  7 bytes  version 9  "{outside}"',
        "work/tweak-x-1 4"])
    assert page_db.keep_listed(listing, d) == 2
    db = page_db.load(d)
    assert db["view"]["due"]["version"] == 82 and db["work"]["tweak-x-1"]["version"] == 4
    assert "__version__" not in db["view"]["due"]["data"]
    with open(outside, encoding="utf-8") as fh:
        assert json.load(fh) == {"x": 1}              # never a file outside the read's folder
    # The hook's half: the same from the tool call itself, whatever shape its result has.
    event = {"hook_event_name": "PostToolUse", "tool_name": "ArtifactData",
             "tool_input": {"action": "query", "collection": "screen", "out_dir": d},
             "tool_response": [{"type": "text", "text": f'- "due"  13 bytes  version 83  "{d}/screen/due.json"'}]}
    assert page_db.keep_listed_event(event) == 1
    assert page_db.load(d)["view"]["due"]["version"] == 83


def test_a_batch_is_sized_as_it_is_sent_never_over_the_limit(tmp_path):
    """Sized by the files on disk, a page update went as a 2.86 MB request against 1 MiB: the
    screens' JSON text and their curly quotes grow as they are sent."""
    w = page_db.Writes(str(tmp_path))
    text = json.dumps([{"line": "“A quote” · said ’twice’"} for _ in range(3000)])
    for n in range(8):
        w.add("set", "screen", f"part~jobs~{n}", {"text": text[:200_000]})
    for path in w.save("view"):
        with open(path, encoding="utf-8") as fh:
            entries = json.load(fh)
        sent = json.dumps([dict({k: v for k, v in e.items() if k != "file_path"},
                                data=json.dumps(json.load(open(e["file_path"], encoding="utf-8"))))
                           for e in entries])
        assert len(sent.encode("utf-8")) < 1024 * 1024, (path, len(sent))


def test_a_claim_is_kept_in_the_folder_so_the_finish_frees_its_holds(ring):
    ring.put("work", "tweak~msg-a~1", tweak("contact_alder", "Alder Freight"))
    d = read(ring, "r1")
    got = json.loads(ring.run("next", d, "--chat", R.CHAT, "--kind", "computer", "--claim-out",
                              os.path.join(d, "claim"), "--now", NOW))
    assert all(land(ring, got["batches"]))
    code, out = app_in(ring, "pin", d, "--work", "tweak~msg-a~1", "--chat", R.CHAT, "--stage",
                       "write", "--line", "Changing it", "--now", NOW)
    assert code == 0, out
    assert all(land(ring, json.loads(out)["batches"])), out
    code, out = app_in(ring, "done", d, "--work", "tweak~msg-a~1", "--chat", R.CHAT,
                       "--summary", "Her note is shorter now.", "--now", NOW)
    assert code == 0, out
    assert json.loads(out)["locks"] == ["contact~contact_alder", "emp~alder_freight"], out
    assert all(land(ring, json.loads(out)["batches"])), out


def test_a_page_chat_message_comes_with_its_words(ring):
    ring.put("talk", "cloud-t1", {"to": "cloud", "title": "A question", "_v": 1})
    ring.put("talk/cloud-t1/messages", "m1", {"from": "you", "text": "Which of my drafts is oldest?",
                                              "at": "2026-10-25T17:59:00Z", "_v": 1})
    ring.put("work", "talk~cloud-t1~m1", {"kind": "talk", "title": "Answer", "to": "either",
                                          "status": "queued", "asked_at": "2026-10-25T17:59:00Z",
                                          "args": {"thread": "cloud-t1", "message": "m1"}, "_v": 1})
    d = read(ring, "r1")
    # Answered here, where no chat of its own can be started for it (--no-sessions; one that
    # is reads the thread itself, tests/test_the_chat_has_a_chat_of_its_own.py).
    said = ring.run("wake", d, "--chat", R.CHAT, "--kind", "cloud", "--on", "Opus 5.5", "--now",
                    R.NOW, "--no-sessions", LJS_PAGE_MIRROR=ring.mirror)
    item = R.next_item(said)
    # An item made before the page put the words on it: the one read that fetches them.
    assert "talk/cloud-t1/messages" in item.get("read_words", ""), item
    ring.put("work", "talk~cloud-t2~m2", {"kind": "talk", "title": "Answer", "to": "either",
                                          "status": "queued", "asked_at": "2026-10-25T18:00:00Z",
                                          "args": {"thread": "cloud-t2", "message": "m2",
                                                   "text": "Is the panel on Thursday?"}, "_v": 1})
    d = read(ring, "r2", now=LATER)
    said = ring.run("wake", d, "--chat", R.CHAT, "--kind", "cloud", "--on", "Opus 5.5", "--now",
                    LATER, "--no-sessions", LJS_PAGE_MIRROR=ring.mirror)
    assert "Is the panel on Thursday?" in said, said
