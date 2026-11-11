"""A step the person's own rules say every brief runs is run by the brief, in code.

Their profile said every brief clears the jobs found over a week ago first (their own script,
after "why isnt it automatic"), but nothing ran it: the brief's prompt says never to read or
run anything the brief's command has not, so a run that followed it exactly never did (audit
BT-4, the "rules enforced only by prose" cluster). Now person.json `brief.before` names such
steps, `brief.py --write` runs each once before it gathers, on the brief's own day, and a rule
in profile/CLAUDE.md that names one is adopted into it by an upgrade. Invented person.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

from test_brief import _profile, _run, _state  # noqa: E402

DAY = "2026-11-10"
STEP = """import os, sys
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ran.txt"), "a") as fh:
    fh.write(os.environ.get("LJS_TODAY", "") + "\\n")
"""


def _copy(tmp_path, before=None, script=STEP, rule=""):
    state = _state(tmp_path)
    prof = _profile(state)
    with open(os.path.join(prof, "clear_old_jobs.py"), "w", encoding="utf-8") as fh:
        fh.write(script)
    if before is not None:
        path = os.path.join(prof, "person.json")
        got = json.load(open(path, encoding="utf-8"))
        got.setdefault("brief", {})["before"] = before
        json.dump(got, open(path, "w", encoding="utf-8"), indent=2)
    if rule:
        with open(os.path.join(prof, "CLAUDE.md"), "a", encoding="utf-8") as fh:
            fh.write("\n\n" + rule + "\n")
    return state, prof


def _ran(prof):
    try:
        return open(os.path.join(prof, "ran.txt"), encoding="utf-8").read().split()
    except OSError:
        return []


def test_a_named_step_runs_once_on_the_briefs_own_day(tmp_path):
    state, prof = _copy(tmp_path, before=["profile/clear_old_jobs.py"])
    r = _run(state, "--today", DAY, "--write")
    assert r.returncode == 0, r.stderr
    assert _ran(prof) == [DAY]
    assert "clear_old_jobs" not in r.stdout          # said to nobody when it works
    # Without --write nothing is changed, so nothing of theirs is run either.
    assert _run(state, "--today", DAY).returncode == 0
    assert _ran(prof) == [DAY]


def test_a_step_that_fails_is_said_to_claude_and_the_brief_goes_on(tmp_path):
    state, prof = _copy(tmp_path, before=["clear_old_jobs.py"],
                        script="raise SystemExit('no rounds folder')\n")
    r = _run(state, "--today", DAY, "--write")
    assert r.returncode == 0, r.stderr
    claude = r.stdout.split("FOR CLAUDE", 1)[1]
    assert "your own step profile/clear_old_jobs.py stopped" in claude
    assert "no rounds folder" in claude
    assert os.path.exists(os.path.join(state, "documents", "briefs", DAY + ".md"))


def test_only_the_persons_own_scripts_are_run(tmp_path, monkeypatch):
    state, prof = _copy(tmp_path, before=["../tools/sync_app.py", "profile/missing.py",
                                          "rm -rf /", 7])
    import brief
    import person
    monkeypatch.setenv("LJS_PROFILE", prof)
    person.reset()
    assert brief.own_steps() == []
    assert _run(state, "--today", DAY, "--write").returncode == 0


RULE = ("- **Jobs over a week old leave the list by themselves.** Every brief, and every chat "
        "before it brings the page up to date, runs `python3 profile/clear_old_jobs.py` first.")


def test_a_rule_in_their_profile_is_adopted_and_then_run(tmp_path, monkeypatch):
    state, prof = _copy(tmp_path, rule=RULE)
    monkeypatch.setenv("LJS_PROFILE", prof)
    monkeypatch.setenv("LJS_STATE", state)
    import brief
    import person
    import profile_upgrades
    person.reset()
    u = profile_upgrades.by_id("brief-own-steps")
    assert u.cost == "instant" and u.needs == "nobody"
    assert "profile/clear_old_jobs.py" in u.pending()
    assert brief.unadopted_steps() == ["profile/clear_old_jobs.py"]
    assert brief.main(["before", "--adopt"]) == 0
    person.reset()
    assert brief.own_steps() == ["profile/clear_old_jobs.py"]
    assert u.pending() == ""
    r = _run(state, "--today", DAY, "--write")
    assert r.returncode == 0, r.stderr
    assert _ran(prof) == [DAY]
