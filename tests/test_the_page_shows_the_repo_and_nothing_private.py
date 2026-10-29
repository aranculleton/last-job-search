"""The page's view model is the repo, seen the same way every time, with nobody's details in it.

`tools/app.py model` builds one JSON object from the state files (CONTRACT.md section 1).
These tests hold it to that: it keeps the contract, the same state gives the same rev, a
change moves only the revs of what changed, a contact book holding emails and phone numbers
gives the page none of them, a path is written the same way on Windows, and a big search is
still quick. Every person and employer here is invented (tests/app_state.py).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import pytest  # noqa: E402

import app_model  # noqa: E402
import app_state  # noqa: E402
import page_db  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "app_model_example.json")
APP = os.path.join(ROOT, "tools", "app.py")


def _app(state, *args, profile=app_state.EXAMPLE, ok=(0,)):
    env = dict(os.environ, LJS_PROFILE=profile, LJS_STATE=state, LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    r = subprocess.run([sys.executable, APP, *args], env=env, capture_output=True,
                       encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode in ok, r.stdout + r.stderr
    return r


def model(state, now=app_state.NOW, **kw):
    return json.loads(_app(state, "model", "--now", now, **kw).stdout)


@pytest.fixture
def small(tmp_path):
    return app_state.small(str(tmp_path / "state"))


def _comparable(m: dict) -> dict:
    """The model without what depends on the computer rather than the state: the app's own
    version, the repo's address, and (with no PDF reader here) the page counts."""
    m = app_model._without_clock(json.loads(json.dumps(m)))
    for key in ("app", "rev", "updates"):
        m.pop(key, None)
    m["person"].pop("repo", None)
    m.get("listener", {}).get("wake", {}).pop("url", None)    # the repo's address is in it
    try:
        import pypdf  # noqa: F401
    except ImportError:
        for r in m["ready"]:
            r.pop("checks", None)
            r.pop("rev", None)
            for f in r["files"]:
                f.pop("pages", None)
    return m


def test_the_fixture_is_the_model_of_the_example_search(small):
    """tests/fixtures/app_model_example.json is what the page is built and tested against;
    `python3 tests/app_state.py fixture` remakes it after a change to the model."""
    with open(FIXTURE, encoding="utf-8") as fh:
        kept = json.load(fh)
    assert _comparable(model(small)) == _comparable(kept)


def test_the_model_keeps_the_contract(small):
    m = model(small)
    assert app_model.check(m) == []
    assert _app(small, "check", "--model", FIXTURE).stdout.startswith("app: the model keeps")
    # Every section the contract names, and something in each the example search has.
    for key in ("needs_you", "jobs", "ready", "messages", "due", "people", "interviews",
                "done", "settings", "brief"):
        assert m.get(key), key
    assert m["jobs"]["filtered"]["count"] == 3
    kestrel = next(r for r in m["ready"] if r["company"] == "Kestrel Mutual")
    assert kestrel["pay"] == "GBP 42,000 to 48,000"
    assert kestrel["screening"][1] == {"q": "Will you now or in future need sponsorship?",
                                       "a": "No"}
    assert kestrel["outreach"]["text"].startswith("Hi [name], I have applied")
    assert m["interviews"][0]["next_stage"] == "Panel interview"
    assert m["interviews"][0]["when"] == "2026-10-28"
    assert m["needs_you"][0]["title"] == "Did you apply to Dovecote Freight?"
    # 4.0 sends nobody to make a chat on their computer: there is no card for one.
    assert not [q for q in m["needs_you"] if q["kind"] == "setup"]


def test_a_broken_model_is_caught():
    with open(FIXTURE, encoding="utf-8") as fh:
        m = json.load(fh)
    m["ready"][0].pop("status")
    m["due"][0]["due"] = "soon"
    m["people"][0]["next_action"] = "write to her at someone@example.com"
    bad = app_model.check(m)
    assert any("ready" in b and "status" in b for b in bad)
    assert any(b.startswith("due ") for b in bad)
    assert any("an email address" in b for b in bad)
    assert any(b.startswith("rev:") for b in bad), "an edited model no longer matches its rev"


def test_the_same_state_gives_the_same_rev(small):
    first = model(small)
    later = model(small, now="2026-10-25T21:30:00Z")
    assert first["made_at"] != later["made_at"]
    assert first["rev"] == later["rev"]
    # A file touched but unchanged (a fresh clone) is the same state.
    path = os.path.join(small, "documents", "rounds", "r9.json")
    os.utime(path, (1, 1))
    assert model(small)["rev"] == first["rev"]


def test_a_change_moves_only_the_revs_of_what_changed(small):
    before = model(small)
    seen = os.path.join(small, "job_scraper", "seen_jobs.json")
    with open(seen, encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("seen", {})["jobs.example/brindle/demand"] = {
        "url": "https://jobs.example/brindle/demand", "status": "excluded",
        "exclusion_reason": "not for me", "basis": "person"}
    with open(seen, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    after = model(small)
    assert after["rev"] != before["rev"]
    old = {r["id"]: r for r in before["jobs"]["rows"]}
    new = {r["id"]: r for r in after["jobs"]["rows"]}
    assert new["r9-1"]["status"] == "dismissed"
    assert new["r9-1"]["rev"] != old["r9-1"]["rev"]
    assert all(new[i]["rev"] == old[i]["rev"] for i in new if i != "r9-1")
    assert [r["rev"] for r in after["ready"]] == [r["rev"] for r in before["ready"]]


def test_no_contact_detail_reaches_the_page_even_when_the_book_holds_them(small):
    m = model(small)
    text = json.dumps({k: v for k, v in m.items() if k != "messages"}, ensure_ascii=False)
    for detail in ("pell.ansgar@example.co.uk", "07700 900461", "+44 7700 900461",
                   "linkedin.com/in/", "Ansgar", "Castellan", "Halloway"):
        assert detail not in text, detail
    pell = next(p for p in m["people"] if p["id"] == "kestrel_mutual_ansgar")
    assert pell["first_name"] == "Pell" and "phone" not in pell["next_action"].split()[-1:]
    assert app_model.private_in(pell["next_action"]) == []
    note = m["messages"][0]
    assert note["first_name"] == "Pell" and note["text"].startswith("Hi Pell")
    assert note["why"] == "You studied at the same place"


def test_a_big_contact_book_full_of_details_gives_none_of_them(tmp_path):
    state = app_state.large(str(tmp_path / "big"), tracker_rows=60, contacts=300, threads=700)
    m = model(state)
    assert app_model.check(m) == []
    for section in ("people", "due", "needs_you", "jobs"):
        for _path, text in app_model._strings(m[section]):
            assert app_model.private_in(text) == [], text
    assert "@example.com" not in json.dumps(m["people"]) + json.dumps(m["due"])
    assert m["people_count"]["all"] >= len(m["people"])


def test_a_path_is_written_the_same_way_on_windows(monkeypatch, tmp_path):
    """On Windows a path is joined with backslashes, and two drives (C: and D:) have no
    relative path between them: relpath raises. The model writes every path with forward
    slashes, and a path on another drive is written whole rather than crashing."""
    monkeypatch.setattr(app_model.os, "sep", "\\")
    monkeypatch.setattr(app_model.os.path, "relpath",
                        lambda p, start=None: "documents\\applications\\acme\\interview_prep.md")
    assert app_model.rel("whatever") == "documents/applications/acme/interview_prep.md"

    def other_drive(p, start=None):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")
    monkeypatch.setattr(app_model.os.path, "relpath", other_drive)
    got = app_model.rel(str(tmp_path / "x.md"))
    assert got.endswith("x.md") and "\\" not in got


def test_a_dump_from_windows_reads_the_same(tmp_path):
    """A dump saved on Windows may end its lines with CRLF and keep the version beside the
    fields or in a wrapper; both read the same."""
    d = tmp_path / "dump"
    (d / "work").mkdir(parents=True)
    (d / "work" / "w1.json").write_bytes(
        b'{\r\n "kind": "search",\r\n "status": "queued",\r\n "__version__": 3\r\n}\r\n')
    (d / "work" / "w2.json").write_text(
        json.dumps({"id": "w2", "version": 7, "data": {"kind": "draft", "status": "queued"}}),
        encoding="utf-8")
    db = page_db.load(str(d))
    assert db["work"]["w1"] == {"data": {"kind": "search", "status": "queued"}, "version": 3}
    assert db["work"]["w2"] == {"data": {"kind": "draft", "status": "queued"}, "version": 7}


@pytest.mark.timing
def test_a_big_search_is_modelled_inside_two_seconds(tmp_path, monkeypatch):
    """500 applications, 2,000 contacts and 5,000 messages: what the size of the search costs
    a build, once a first build has loaded the code. Timed against a small search's build,
    which pays the same fixed costs: every build starts git a few times, a few hundredths
    of a second on Linux and about a second on a Windows runner, whatever the search's
    size. This guards how the work grows with the search (2026-10-26). It counts this
    process's own work (process_time), never the wall clock: with the suite in parallel
    workers a busy runner made the same build read 2.67s (2026-10-29)."""
    warm = app_state.large(str(tmp_path / "warm"))
    small_state = app_state.small(str(tmp_path / "small"))
    big = app_state.large(str(tmp_path / "big"))
    monkeypatch.setenv("LJS_COPY", "private")
    today, now = app_model.clock("2026-10-25", app_state.NOW)
    monkeypatch.setenv("LJS_STATE", warm)
    app_model.build(today, now)
    monkeypatch.setenv("LJS_STATE", small_state)
    start = time.process_time()
    app_model.build(today, now)
    fixed = time.process_time() - start
    monkeypatch.setenv("LJS_STATE", big)
    start = time.process_time()
    m, _ = app_model.build(today, now)
    took = time.process_time() - start
    # Every live contact is on the page whatever the book's size (here every one has
    # something due); only finished history and the people beyond the budget fold away.
    assert len(m["people"]) == m["people_count"]["live"] == m["people_count"]["all"]
    assert took - fixed < 2.0, f"{took:.2f}s, of which {fixed:.2f}s any build takes"


def test_every_kind_of_work_has_its_stages():
    kinds = ("search", "draft", "resume_for_contact", "prep", "network", "reply", "follow_up",
             "brief", "research", "update", "talk", "files", "tweak", "evaluate",
             "general_resume", "own_profile", "republish", "profile")
    for kind in kinds:
        got = page_db.progress(kind)
        assert got["stages"] and all(s["est_s"] > 0 and s["name"] for s in got["stages"])
        assert got["total_s"] == sum(s["est_s"] for s in got["stages"])
    assert set(page_db.WORK_KINDS) == set(kinds)
    out = subprocess.run([sys.executable, APP, "progress", "draft"], capture_output=True,
                         encoding="utf-8", timeout=60)
    assert json.loads(out.stdout)["stages"][3]["name"] == "Checking every fact"


def test_the_model_reaches_an_open_page_as_view_documents(small, tmp_path):
    """`app.py view` writes the model a section a document, and meta/current with its rev,
    so a page that is open updates with no republish. A document that exists is pinned to
    the version the dump read."""
    dump = tmp_path / "dump"
    (dump / "view").mkdir(parents=True)
    (dump / "view" / "jobs.json").write_text(json.dumps({"rev": "old", "__version__": 4}),
                                             encoding="utf-8")
    out = json.loads(_app(small, "view", str(tmp_path / "out"), "--dump", str(dump),
                          "--now", app_state.NOW).stdout)
    with open(out["batches"][0], encoding="utf-8") as fh:
        batch = json.load(fh)
    by = {(e["collection"], e["doc_id"]): e for e in batch}
    assert by[("screen", "jobs")]["if_version"] == 4
    assert "if_version" not in by[("screen", "people")]
    with open(by[("meta", "now")]["file_path"], encoding="utf-8") as fh:
        assert json.load(fh)["rev"] == out["rev"] == model(small)["rev"]
    with open(by[("screen", "ready")]["file_path"], encoding="utf-8") as fh:
        assert json.load(fh)["data"][0]["company"] == "Fernhill Freight"


def _written(batches):
    """{(collection, doc id): (op, the document or None)} from `app.py view`'s batch files."""
    got = {}
    for b in batches:
        with open(b, encoding="utf-8") as fh:
            for e in json.load(fh):
                body = None
                if e.get("file_path"):
                    with open(e["file_path"], encoding="utf-8") as fh2:
                        body = json.load(fh2)
                got[(e["collection"], e["doc_id"])] = (e["op"], body)
    return got


def test_a_section_too_big_for_one_document_goes_in_parts_and_comes_back_whole(tmp_path):
    """A long search's jobs section is far over the database's 256 KiB a document. `app.py
    view` used to stop on it ("page_db: view/jobs is over 256 KiB"), so nothing new reached
    the page. It now writes the section as parts, each under the cap, that join back to
    exactly the model's section, and an earlier write's parts the section no longer fills
    are deleted."""
    state = app_state.many_jobs(str(tmp_path / "state"), n=400)
    whole = model(state)["jobs"]
    assert page_db.stored_size({"data": whole}) > page_db.DOC_MAX * 3 // 2
    dump = tmp_path / "dump"
    (dump / "view").mkdir(parents=True)
    for doc_id in ("part~jobs~9", "part~people~1"):    # left by an earlier, bigger write
        (dump / "view" / f"{doc_id}.json").write_text(
            json.dumps({"rev": "old", "text": "[", "__version__": 2}), encoding="utf-8")
    out = json.loads(_app(state, "view", str(tmp_path / "out"), "--dump", str(dump),
                          "--now", app_state.NOW).stdout)
    got = _written(out["batches"])
    for (coll, doc_id), (_op, body) in got.items():
        if body is not None:
            assert page_db.stored_size(body) <= page_db.DOC_MAX, f"{coll}/{doc_id}"
    assert got[("screen", "part~jobs~9")][0] == got[("screen", "part~people~1")][0] == "delete"
    head = got[("screen", "jobs")][1]
    assert "data" not in head and head["in_parts"] >= 2 and head["rev"] == out["rev"]
    view = {d: {"data": b, "version": None} for (c, d), (op, b) in got.items()
            if c == "screen" and op == "set"}
    assert page_db.joined(view, "jobs") == whole
    assert len(page_db.joined(view, "jobs")["rows"]) == 400
    # A part missing, or from another write, is never read as the section.
    view.pop("part~jobs~2")
    assert page_db.joined(view, "jobs") is None


def test_suggestions_on_a_section_in_parts_keep_their_day():
    """The cap of three new suggestions a day reads the suggestions already on the page from
    the view documents, whole or in parts alike."""
    import app_alerts
    rows = [{"id": f"r9-{i}", "suggest": {"id": f"s{i}", "since": "2026-10-20"},
             "pad": "x" * 2000} for i in range(200)]
    doc = {"rev": "abc", "made_at": "2026-10-25T18:00:00Z", "data": {"rows": rows}}
    parts = page_db.split("jobs", doc)
    assert len(parts) > 2
    view = {d: {"data": b, "version": 1} for d, b in parts}
    assert app_alerts.shown_in(view) == {f"s{i}": "2026-10-20" for i in range(200)}
    assert app_alerts.shown_in({"jobs": {"data": doc, "version": 1}}) == app_alerts.shown_in(view)
