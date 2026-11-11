"""What the drafting child chat of 3 November found, and a problem reported with no chat.

The child that drafted a batch of four found `app.py pin` writing only the last of the four
items it was given (every other one then read as stopped), a freehire row whose link was the
employer's own Workable posting stopping the drafting with "could not parse a freehire slug",
and the job prompt and `start` disagreeing about whether a job chat brings the page up to date.
And a person's only way to report a problem with the app went through a chat message, which
was lost whenever the message was. Every name here is invented.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import app  # noqa: E402
import page_db  # noqa: E402
from test_the_page_works_in_a_browser import _sample, _write, run  # noqa: E402

_ = run   # the fixture, used by name

APP = os.path.join(ROOT, "tools", "app.py")
NOW = "2026-11-03T18:00:00Z"


def _dump(tmp_path, ids):
    d = tmp_path / "dump" / "work"
    d.mkdir(parents=True)
    for wid in ids:
        with open(d / (wid.replace("~", "@") + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"kind": "draft", "title": "Drafting " + wid, "status": "running", "stage": 0, "stage_at": NOW,
                       "claimed_by": "child-1", "claimed_at": NOW, "steps": [], "stop_asked": False,
                       "stages": page_db.progress("draft")["stages"], "__version__": 4}, fh)
    return str(tmp_path / "dump")


# ------------------------------------------------------------------ 2. a batch is pinned whole


def test_pin_given_every_member_of_a_batch_writes_every_one(tmp_path):
    ids = ["draft~calder-1", "draft~calder-2", "draft~brindle-3", "draft~quayside-4"]
    d = _dump(tmp_path, ids)
    args = [sys.executable, APP, "pin", d, "--chat", "child-1", "--stage", "write", "--line", "Writing the four drafts", "--now", NOW]
    for wid in ids:
        args += ["--work", wid]
    r = subprocess.run(args, capture_output=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads(r.stdout)
    written = set()
    for path in got["batches"]:
        with open(path, encoding="utf-8") as fh:
            written |= {e["doc_id"] for e in json.load(fh) if e["collection"] == "work"}
    assert written == set(ids), written
    assert [w["work"] for w in got["works"]] == ids


def test_pin_given_one_item_prints_as_it_always_did(tmp_path):
    d = _dump(tmp_path, ["draft~calder-1"])
    r = subprocess.run([sys.executable, APP, "pin", d, "--work", "draft~calder-1", "--chat", "child-1", "--stage", "write", "--now", NOW],
                       capture_output=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    got = json.loads(r.stdout)
    assert got["work"] == "draft~calder-1" and got["batches"]


# ------------------------------------------------------------------ 4. a job site's row whose link is the employer's posting


def test_a_freehire_row_with_a_workable_link_is_read_from_the_employers_board(monkeypatch):
    import hydrate
    import openroles
    from openroles.models import Job
    posting = Job(id="wk-AB12CD34", ats="workable", board="calderanalytics", title="Data Analyst",
                  url="https://apply.workable.com/calderanalytics/j/AB12CD34/", description="Build forecasts for the operations team.")
    asked = []

    def fetch(target, **kw):
        asked.append(str(target))
        return [posting]

    def no_cli(*a, **k):
        raise AssertionError("no freehire detail for a Workable link")
    monkeypatch.setattr(openroles, "fetch", fetch)
    monkeypatch.setattr(hydrate.portals, "run_cli", no_cli)
    row = {"portal": "freehire", "id": "None", "title": "Data Analyst", "company": "Calder Analytics",
           "url": "https://apply.workable.com/calderanalytics/j/AB12CD34/", "desc": None}
    got = hydrate.fetch(row)
    assert got.get("desc", "").startswith("Build forecasts"), got
    assert asked and "calderanalytics" in asked[0]


def test_a_workable_short_link_is_found_on_the_employers_board_by_name(monkeypatch):
    import hydrate
    import openroles
    from openroles.models import Board, Job
    posting = Job(id="wk-ZZ99YY88", ats="workable", board="calderanalytics", title="Data Analyst",
                  url="https://apply.workable.com/calderanalytics/j/ZZ99YY88/", description="Own the weekly demand model.")
    monkeypatch.setattr(openroles, "detect", lambda name: [Board("workable", "calderanalytics")] if name == "Calder Analytics" else [])
    monkeypatch.setattr(openroles, "fetch", lambda target, **kw: [posting])
    row = {"portal": "freehire", "id": "", "title": "Data Analyst", "company": "Calder Analytics",
           "url": "https://apply.workable.com/j/ZZ99YY88", "desc": None}
    assert hydrate.fetch(row)["desc"].startswith("Own the weekly")


def test_a_board_that_will_not_answer_is_said_plainly(monkeypatch):
    import hydrate
    import openroles

    def refuse(target, **kw):
        raise openroles.BoardError("rate limited")
    monkeypatch.setattr(openroles, "fetch", refuse)
    row = {"portal": "freehire", "id": None, "title": "Data Analyst", "company": "Calder Analytics",
           "url": "https://apply.workable.com/calderanalytics/j/AB12CD34/", "desc": None}
    got = hydrate.fetch(row)
    assert "apply.workable.com" in got["hydrate_error"] and "slug" not in got["hydrate_error"]


# ------------------------------------------------------------------ 5. one way for a job chat to finish


def test_a_job_chat_is_told_one_way_to_read_and_one_way_to_finish():
    chosen = {"work": "draft~calder-1", "kind": "draft", "title": "Drafting for Calder Analytics",
              "stages": page_db.progress("draft")["stages"]}
    import job_prompt
    prompt = job_prompt.followed(app.child_prompt(chosen, "listener-1",
                                                  "https://claude.ai/code/artifact/x", session=True))
    flat = " ".join(prompt.split())
    assert "No ArtifactData" not in flat and flat.count("Load ArtifactData") == 1
    assert flat.count("app.py view") == 1, "the page is brought up to date once, at the end"
    assert "never writes the page" not in flat.lower()
    import app_setup
    assert "never writes the page's view" not in app_setup.start.__doc__


# ------------------------------------------------------------------ reporting a problem


def test_something_looks_wrong_reaches_the_makers_with_no_chat_and_nothing_of_the_person(run, tmp_path):
    import app_setup
    m = _sample()
    html = _write(tmp_path, "report", m)
    got = run("script", html=html, clock="2026-10-25T09:00:00Z", steps=[
        {"hash": "settings", "click": "Something looks wrong", "exact": False,
         "eval": "(document.querySelector('#main [data-k=\"report-makers\"]') || {}).href || ''"}])
    assert not got["errors"], got["errors"]
    step = got["steps"][-1]
    href = step["eval"]
    assert href.startswith("https://github.com/" + app_setup.APP_REPO + "/issues/new?"), href
    from urllib.parse import parse_qs, urlsplit
    q = parse_qs(urlsplit(href).query)
    body = q["body"][0] + q["title"][0]
    assert m["app"]["version"] in body
    for p in m["people"]:
        assert p["first_name"] not in body and p["employer"] not in body
    assert m["person"]["first_name"] not in body
    # No popup since 4.12: the box opens in place, the makers' link quiet under it.
    assert not step.get("dialog")
