"""A prep is judged out of date by when its files were committed, and a stopped one stays stopped.

The audit of 2026-11-10 (PE-3): whether an interview prep was for an older plan of rounds was
judged by the files' own times, and git writes a checkout's files in name order, so after any
merge `outcome.md` read as a moment newer than `interview_prep.md`. A redraw then queued the
prep again, including one the person had stopped. Every employer here is invented.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app  # noqa: E402
import app_model  # noqa: E402

PREP = "# Prep\n<!-- stages: First round -->\n"


def _git(where, *args, when=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="Example", GIT_AUTHOR_EMAIL="nobody",
               GIT_COMMITTER_NAME="Example", GIT_COMMITTER_EMAIL="nobody")
    if when:
        env.update(GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    subprocess.run(["git", *args], cwd=where, env=env, check=True, capture_output=True)


def test_a_checkout_that_writes_outcome_last_never_makes_the_prep_stale(tmp_path):
    folder = tmp_path / "quayside"
    folder.mkdir()
    _git(folder, "init", "-q")
    (folder / "outcome.md").write_text("Final round booked.\n", encoding="utf-8")
    _git(folder, "add", "outcome.md")
    _git(folder, "commit", "-q", "-m", "outcome", when="2026-11-01T09:00:00+00:00")
    (folder / "interview_prep.md").write_text(PREP, encoding="utf-8")
    _git(folder, "add", "interview_prep.md")
    _git(folder, "commit", "-q", "-m", "prep", when="2026-11-02T09:00:00+00:00")
    # As a checkout leaves them: outcome.md written a moment after the prep.
    t = time.time()
    os.utime(folder / "interview_prep.md", (t, t))
    os.utime(folder / "outcome.md", (t + 0.001, t + 0.001))
    assert not app_model._prep_stale(str(folder), PREP, {"label": "Final round"})
    # Changed since the prep and not committed: newer by its own time, so out of date.
    time.sleep(0.01)
    (folder / "outcome.md").write_text("Final round moved.\n", encoding="utf-8")
    assert app_model._prep_stale(str(folder), PREP, {"label": "Final round"})


def test_a_prep_the_person_stopped_is_never_queued_again_by_a_redraw(tmp_path):
    model = {"interviews": [{"id": "int-quayside", "company": "Quayside Mutual", "role": "Analyst",
                             "prep": {"updated": "2026-11-01T09:00:00Z", "stale": True,
                                      "stale_since": "2026-11-03T08:00:00Z"}}],
             "ready": []}
    now = dt.datetime(2026, 11, 4, 9, 0, tzinfo=dt.timezone.utc)
    stopped = {"kind": "prep", "status": "stopped", "stop_asked": True,
               "finished_at": "2026-11-02T10:00:00Z", "asked_at": "2026-11-02T09:00:00Z",
               "args": {"interview": "int-quayside"}}
    db = {"work": {"prep~int-quayside": {"data": stopped, "version": 4}}}
    out = []
    for path in app.self_fixes(db, model, str(tmp_path / "self"), now):
        with open(path, encoding="utf-8") as fh:
            out += [e for e in json.load(fh) if e["collection"] == "work"]
    assert not [e for e in out if e["doc_id"] == "prep~int-quayside"], out


def test_a_redraw_puts_a_finished_prep_back_by_update_and_a_job_chat_queues_nothing(tmp_path):
    """The review of 2026-11-11 (PE-3's parts left): the prep went again by a `set` over its own
    record, and a job chat's own redraw (`view --work`) queued self-fixes too."""
    model = {"interviews": [{"id": "int-quayside", "company": "Quayside Mutual", "role": "Analyst",
                             "prep": {"updated": "2026-11-01T09:00:00Z", "stale": True,
                                      "stale_since": "2026-11-03T08:00:00Z"}}],
             "ready": []}
    now = dt.datetime(2026, 11, 4, 9, 0, tzinfo=dt.timezone.utc)
    done = {"kind": "prep", "status": "done", "finished_at": "2026-11-02T10:00:00Z", "attempt": 1,
            "asked_at": "2026-11-02T09:00:00Z", "args": {"interview": "int-quayside"}}
    db = {"work": {"prep~int-quayside": {"data": done, "version": 4}}}
    out = []
    for path in app.self_fixes(db, model, str(tmp_path / "self"), now):
        with open(path, encoding="utf-8") as fh:
            out += [e for e in json.load(fh) if e["collection"] == "work"]
    entry = next(e for e in out if e["doc_id"] == "prep~int-quayside")
    assert entry["op"] == "update" and entry["if_version"] == 4, entry
    assert app.self_fixes(db, model, str(tmp_path / "job"), now, work="draft~1") == []


def test_a_prep_queued_again_for_a_new_plan_of_rounds_is_a_new_run_not_a_try_again(tmp_path):
    """The engine review of 2026-11-11: the redraw's re-prep took a Try again each time the plan
    of rounds changed. After one change a chat that stopped once failed it at once as "It
    stopped part way twice", with no second try made; after two, its card said "Tap Try again"
    with no Try again on it (the page offers one while the attempt is below 3)."""
    import re
    import page_db
    model = {"interviews": [{"id": "int-quayside", "company": "Quayside Mutual", "role": "Analyst",
                             "prep": {"updated": "2026-11-01T09:00:00Z", "stale": True,
                                      "stale_since": "2026-11-03T08:00:00Z"}}],
             "ready": []}
    now = dt.datetime(2026, 11, 4, 9, 0, tzinfo=dt.timezone.utc)
    item = {"kind": "prep", "status": "done", "finished_at": "2026-11-02T10:00:00Z",
            "attempt": 2, "asked_at": "2026-11-02T09:00:00Z", "args": {"interview": "int-quayside"}}
    for n in range(2):
        # The plan of rounds changes again after each prep is made.
        model["interviews"][0]["prep"]["stale_since"] = f"2026-11-0{3 + n}T08:00:00Z"
        db = {"work": {"prep~int-quayside": {"data": item, "version": 4 + n}}}
        body = None
        for path in app.self_fixes(db, model, str(tmp_path / f"self{n}"), now):
            with open(path, encoding="utf-8") as fh:
                for e in json.load(fh):
                    if e["doc_id"] == "prep~int-quayside":
                        with open(e["file_path"], encoding="utf-8") as bf:
                            body = json.load(bf)
        assert body is not None and body["attempt"] == 1, body
        item = dict(page_db.applied(item, body), status="done",
                    finished_at=f"2026-11-0{3 + n}T10:00:00Z")
    # Its chat stops once: started again by itself, never failed as stopped twice.
    went = page_db.applied(item, page_db.taken(dict(item, status="queued"), "session_job", "cloud",
                                               "2026-11-04T07:00:00Z", "2026-11-04T07:30:00Z",
                                               running=True))
    assert page_db.stranded({"work": {"prep~int-quayside": {"data": went, "version": 9}}}, now) == []
    # A card says "Tap Try again" only where the page offers it.
    src = open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8").read()
    assert re.search(r"\btries < (\d)\b", src).group(1) == str(page_db.TRY_AGAIN_BELOW)
    late = dict(went, attempt=page_db.TRY_AGAIN_BELOW, lease_until="2026-11-04T07:30:00Z")
    got = page_db.fail_stranded({"work": {"p": {"data": late, "version": 9}}}, now,
                                str(tmp_path / "late"))
    with open(got["batches"][0], encoding="utf-8") as fh:
        entry = json.load(fh)[0]
    with open(entry["file_path"], encoding="utf-8") as fh:
        said = json.load(fh)["error"]
    assert "Try again" not in said and "Ask Claude" in said, said
    assert "Tap Try again" in page_db.try_again_said(page_db.STRANDED_SAID, {"attempt": 2})


def test_what_git_says_of_a_file_is_asked_once(tmp_path, monkeypatch):
    path = tmp_path / "outcome.md"
    path.write_text("x", encoding="utf-8")
    asked = []
    real = app_model._saved_at
    monkeypatch.setattr(app_model, "_saved_at", lambda p: asked.append(p) or real(p))
    app_model._SAVED_AT.clear()
    for _ in range(5):
        app_model.saved_at(str(path))
    assert len(asked) == 1
