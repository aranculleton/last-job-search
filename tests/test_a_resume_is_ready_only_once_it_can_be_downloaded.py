"""A resume is one piece of work, and says ready only once it can be downloaded (issue #237).

After a resume was made for a contact, Claude's work showed two items: "Resume for <name>"
finished ("Putting on page · Finished 2 min ago", Open in Contacts) and a second one running,
"Make the files downloadable: the resume for <name> · Finding the files". The resume could not
be had until the second ended, so "Finished" was wrong. The maintainer: "why is make the resume
downloadable a separate step? is it done or not?"

Now the files work names the work it is part of (tools/page_db.py queue_files `part_of`), the
page draws the two as one card, "On its way" with the stage "Making it downloadable", and the
contact's own card says it is on its way rather than offering it. Once the file is on the page
the card is done, and the files work never shows as an item of its own.

The engine half runs on the real path (`app.py done` on a resume made for a contact); the page
half in the page harness. Every person and employer is invented (the page journeys' sample).
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import page_db  # noqa: E402
import test_the_page_journeys as journeys  # noqa: E402
from test_claudes_work_says_stop_claude_and_an_answer_offers_its_next_step import LISTEN, _w  # noqa: E402
from test_the_page_journeys import WIDE, _go  # noqa: E402

T = "2026-10-25T09:00:00.000Z"
JUNO = "larkspur_retail_castellan"
RESUME = "contact_resume~larkspur_retail_castellan~r1"
FILES = "files~resfor-larkspur_retail_castellan"
PATH = "documents/network/larkspur_retail_castellan/Morgan_Ellis_Resume_For_Juno.pdf"


def test_the_engine_names_the_resume_its_files_work_is_part_of(tmp_path):
    now = page_db.dt.datetime(2026, 10, 25, 9, 0, tzinfo=page_db.dt.timezone.utc)
    apps = [{"id": "resfor-" + JUNO, "what": "the resume for Juno", "files": ["r.pdf"],
             "paths": [PATH]}]
    got = page_db.queue_files({"work": {}}, apps, now, str(tmp_path / "out"), part_of=RESUME)
    assert got and got["batches"], got
    with open(got["batches"][0], encoding="utf-8") as fh:
        batch = json.load(fh)
    with open(batch[0]["file_path"], encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["part_of"] == RESUME and doc["kind"] == "files", doc
    # app.py done passes the finishing work's id through.
    with open(os.path.join(ROOT, "tools", "app.py"), encoding="utf-8") as fh:
        src = " ".join(fh.read().split())
    assert "part_of=a.work" in src


@pytest.fixture(scope="module")
def run():
    yield from journeys.browser()


def _model():
    m = journeys._sample()
    juno = next(p for p in m["people"] if p["id"] == JUNO)
    juno["resume_for_them"] = {"name": "Morgan_Ellis_Resume_For_Juno.pdf", "made_on": "2026-10-25",
                               "path": PATH, "asset": None,
                               "get": {"kind": "files", "id": FILES, "args": {"paths": [PATH]}}}
    return m


def _seed(files_status="running"):
    stages = page_db.progress("resume_for_contact")["stages"]
    resume = _w(kind="resume_for_contact", title="Resume for Juno (Larkspur Retail)", status="done",
                claimed_by="session_job1", claimed_at="2026-10-25T08:40:00.000Z",
                stage_at="2026-10-25T08:56:00.000Z", stage=4, stages=stages,
                finished_at="2026-10-25T08:58:00.000Z", done_at="2026-10-25T08:58:00.000Z",
                args={"for_contact": JUNO},
                result={"summary": "Your resume for Juno is ready.", "links": []})
    files = _w(kind="files", title="Make the files downloadable: the resume for Juno",
               status=files_status, to="either", part_of=RESUME, asked_at="2026-10-25T08:58:01.000Z",
               stages=page_db.progress("files")["stages"],
               args={"application": "resfor-" + JUNO, "applications": ["resfor-" + JUNO], "paths": [PATH]},
               **({"claimed_by": "cloud-1", "claimed_at": "2026-10-25T08:59:00.000Z",
                   "stage_at": "2026-10-25T08:59:00.000Z",
                   "lease_until": "2026-10-25T09:30:00.000Z"} if files_status == "running" else {}),
               **({"finished_at": "2026-10-25T08:59:30.000Z", "done_at": "2026-10-25T08:59:30.000Z",
                   "result": {"summary": "Your files are on your page.", "links": []}}
                  if files_status == "done" else {}))
    return dict(LISTEN, **{"work/" + RESUME: resume, "work/" + FILES: files})


LOOK = r"""(() => {
  const cards = [...document.querySelectorAll('.work-card')].map((c) => c.textContent.replace(/\s+/g, ' ').trim());
  const one = document.querySelector('[data-part-of="%s"]');
  const juno = document.querySelector('#main [data-resume-for="%s"]');
  return {cards, one: one ? one.textContent.replace(/\s+/g, ' ').trim() : null,
    juno: juno ? juno.textContent.replace(/\s+/g, ' ').trim() : null,
    getIt: juno ? [...juno.querySelectorAll('button')].map((b) => b.textContent) : []};
})()""" % (RESUME, JUNO)


def test_while_its_file_is_put_on_the_page_the_resume_is_one_card_on_its_way(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": LOOK}], WIDE, model=_model(),
              seed=_seed("running"), clock=T)
    r = got["after"][0]["eval"]
    # One card: the resume, on its way, at its stage "Making it downloadable".
    assert r["one"] is not None, r
    assert "Resume for Juno" in r["one"] and "On its way" in r["one"], r
    assert "Making it downloadable" in r["one"], r
    assert "Finished" not in r["one"] and "ready" not in r["one"].lower(), r
    # Never an item of its own, never "Putting on page" or "Finished" for the resume.
    assert not any("Make the files downloadable" in c for c in r["cards"]), r["cards"]
    assert sum("Resume for Juno" in c for c in r["cards"]) == 1, r["cards"]
    assert not any("Putting on page" in c or "Finished" in c for c in r["cards"] if "Juno" in c), r["cards"]
    # Her own card says it is on its way, with nothing to get yet.
    assert r["juno"] and "on its way" in r["juno"], r
    assert "Get it" not in r["getIt"], r


def test_a_files_part_still_waiting_says_so_on_the_one_card(run, tmp_path):
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": LOOK}], WIDE, model=_model(),
              seed=_seed("queued"), clock=T)
    r = got["after"][0]["eval"]
    assert r["one"] is not None and "Making it downloadable" in r["one"], r
    assert not any("Make the files downloadable" in c for c in r["cards"]), r["cards"]


def test_once_the_file_is_on_the_page_the_resume_is_done_and_can_be_had(run, tmp_path):
    m = _model()
    juno = next(p for p in m["people"] if p["id"] == JUNO)
    juno["resume_for_them"]["asset"] = "asset-juno-1"
    m["made_at"] = "2026-10-25T08:59:45Z"
    got = _go(run, tmp_path, [{"hash": "contacts", "eval": LOOK}], WIDE, model=m,
              seed=_seed("done"), clock=T)
    r = got["after"][0]["eval"]
    assert r["one"] is None, r
    assert not any("Make the files downloadable" in c for c in r["cards"]), r["cards"]
    assert "Get it" in r["getIt"], r
