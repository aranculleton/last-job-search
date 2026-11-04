"""A search's card says its shortlist is ready only once Jobs can show it, under a round's name.

The helper chat's report of 2 November: a search's work item said "Your shortlist of 60
ranked jobs is ready" while its results were not saved, so Jobs said "Nothing new"; and the
search chat, told to run `run_round.py --show N` with an `--out` it had to make up, saved
the round as "2026-11-04-app", which failed the person's own tests that read rounds as "r"
and a number. Both are now the code's to decide: `app.py done` refuses a search whose
shortlist is not saved where Jobs reads it, and a round names itself. Every person and
employer here is invented (tests/app_state.py).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_state  # noqa: E402
import page_db  # noqa: E402

APP = os.path.join(ROOT, "tools", "app.py")
WID = "search~20261104T0900-ab12"


def _stamp(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _search(tmp_path):
    """The example search, its saved round written long ago, and a dump holding one search
    a chat claimed ten minutes ago."""
    state = app_state.small(str(tmp_path / "state"))
    profile = app_state.profile_copy(str(tmp_path / "profile"))
    rounds = os.path.join(state, "documents", "rounds")
    old = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp()
    for name in os.listdir(rounds):
        if name.endswith(".json"):
            os.utime(os.path.join(rounds, name), (old, old))
    now = dt.datetime.now(dt.timezone.utc)
    item = {"kind": "search", "title": "Find me jobs", "status": "running", "args": {"size": 10},
            "asked_at": _stamp(now - dt.timedelta(minutes=12)), "claimed_by": "session_job",
            "claimed_at": _stamp(now - dt.timedelta(minutes=10)),
            "stages": page_db.progress("search")["stages"], "stage": 1}
    dump = tmp_path / "dump" / "work"
    dump.mkdir(parents=True)
    (dump / (WID.replace("~", "@") + ".json")).write_text(json.dumps(dict(item, _v=3)),
                                                         encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=profile, LJS_STATE=state, LJS_COPY="private")
    env.pop("LJS_TODAY", None)
    return state, str(tmp_path / "dump"), env


def _done(dump, env):
    return subprocess.run([sys.executable, APP, "done", dump, "--work", WID, "--chat",
                           "session_job", "--summary", "Your shortlist of 10 ranked jobs is ready."],
                          env=env, capture_output=True, encoding="utf-8", errors="replace",
                          timeout=120)


def test_a_search_is_not_done_while_its_shortlist_is_unsaved_and_is_done_once_it_is(tmp_path):
    state, dump, env = _search(tmp_path)
    early = _done(dump, env)
    assert early.returncode == 2, early.stdout + early.stderr
    assert "not saved yet" in early.stderr and "Jobs" in early.stderr
    assert not os.path.isdir(os.path.join(dump, "out")) or not os.listdir(
        os.path.join(dump, "out"))                                  # nothing was written
    # The round saves its shortlist where Jobs reads it, as run_round.py does at its end.
    with open(os.path.join(state, "documents", "rounds", "r10.json"), "w",
              encoding="utf-8") as fh:
        json.dump([{"title": "Demand Analyst", "company": "Sedgemoor Freight",
                    "url": "https://jobs.example/sedgemoor/demand", "fit": 80,
                    "priority": 80, "first_seen": dt.date.today().isoformat()}], fh)
    later = _done(dump, env)
    assert later.returncode == 0, later.stdout + later.stderr
    assert json.loads(later.stdout)["status"] == "done"


def test_a_search_that_failed_is_left_failed_with_nothing_saved(tmp_path):
    _state, dump, env = _search(tmp_path)
    got = subprocess.run([sys.executable, APP, "done", dump, "--work", WID, "--chat",
                          "session_job", "--failed", "No job site answered."],
                         env=env, capture_output=True, encoding="utf-8", errors="replace",
                         timeout=120)
    assert got.returncode == 0, got.stdout + got.stderr


def _round(tmp_path, monkeypatch, *argv):
    """tools/run_round.py's main with every stage stood in, on the example search's state,
    its shortlist saved among the person's own rounds (no --summary-dir)."""
    import run_round
    state = app_state.small(str(tmp_path / "state"))
    monkeypatch.setenv("LJS_STATE", state)
    monkeypatch.setenv("LJS_PROFILE", app_state.profile_copy(str(tmp_path / "profile")))

    def fake_run(cmd, log, deadline=None, ok=(0,)):
        for flag in ("--out", "--dropped", "--out-all", "--skipped"):
            if flag in cmd:
                dest = cmd[cmd.index(flag) + 1]
                if cmd[1].endswith("scrape_wide.py"):
                    os.makedirs(dest, exist_ok=True)
                    dest = os.path.join(dest, "kept.json")
                with open(dest, "w", encoding="utf-8") as fh:
                    json.dump([], fh)
        return 0

    monkeypatch.setattr(run_round, "run", fake_run)
    monkeypatch.setattr(run_round.subprocess, "call", lambda cmd, *a, **k: 0)
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--today", "2026-11-04", *argv])
    run_round.main()
    return state


def test_a_round_given_no_folder_names_itself_r_and_the_next_number(tmp_path, monkeypatch,
                                                                    capsys):
    state = _round(tmp_path, monkeypatch, "--show", "10")
    saved = sorted(os.listdir(os.path.join(state, "documents", "rounds")))
    assert "r10.json" in saved, saved                      # r9 was the highest before
    assert os.path.isfile(os.path.join(state, "rounds", "r10", "round.log"))
    assert "round: r10, its files in" in capsys.readouterr().out


def test_a_round_given_a_folder_with_a_made_up_name_still_saves_as_r_and_a_number(
        tmp_path, monkeypatch):
    made_up = str(tmp_path / "scratch" / "2026-11-04-app")
    state = _round(tmp_path, monkeypatch, "--out", made_up, "--show", "10")
    saved = sorted(os.listdir(os.path.join(state, "documents", "rounds")))
    assert "2026-11-04-app.json" not in saved and "r10.json" in saved, saved
    assert os.path.isdir(str(tmp_path / "scratch" / "r10"))
