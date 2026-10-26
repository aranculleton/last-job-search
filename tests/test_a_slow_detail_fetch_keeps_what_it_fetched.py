"""A slow detail fetch stops in its own time and keeps every body it fetched.

Only a paced board's fetches had a budget; LinkedIn's and freehire's had none, and hydrate
wrote its output only when every fetch was done. Under a storm of 429s the stage ran into
its limit in run_round.py, was killed, and every body it had fetched was lost, so the next
round fetched them all again. Now the whole stage has a budget, inside the limit the round
gives it: past it a posting is not fetched and says why, and what was fetched is written.
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hydrate  # noqa: E402


def _slow_linkedin(monkeypatch, secs):
    monkeypatch.setitem(hydrate.CLI, "linkedin", lambda: "cli.mjs")
    monkeypatch.setattr(hydrate.portals, "is_enabled", lambda skill: True)
    monkeypatch.setattr(hydrate.portals, "runtime", lambda: ("node",))
    monkeypatch.setattr(hydrate, "pace", lambda skill: True)

    def run_cli(cmd, timeout=60, empty=None):
        time.sleep(secs)
        return {"description": f"The posting for {cmd[-3]}."}, None
    monkeypatch.setattr(hydrate.portals, "run_cli", run_cli)


def _run(tmp_path, monkeypatch, *extra):
    rows = [{"portal": "linkedin", "id": str(4012345600 + i), "title": "Data Analyst",
             "url": f"https://www.linkedin.com/jobs/view/{4012345600 + i}"} for i in range(8)]
    src, out = tmp_path / "in.json", tmp_path / "out.json"
    src.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["hydrate.py", str(src), "--out", str(out), "--workers", "1",
                                      *extra])
    return hydrate.main(), out


def test_past_its_budget_a_posting_is_not_fetched_and_the_rest_are_kept(tmp_path, monkeypatch,
                                                                        capsys):
    _slow_linkedin(monkeypatch, 0.2)
    code, out = _run(tmp_path, monkeypatch, "--budget", "0.5", "--require", "0.9")
    got = json.loads(out.read_text(encoding="utf-8"))
    fetched = [r for r in got if r.get("desc")]
    left = [r for r in got if r.get("hydrate_error") == "not fetched: the stage's time ran out"]
    assert len(got) == 8 and 1 <= len(fetched) <= 4 and len(fetched) + len(left) == 8
    assert code == 1
    assert f"The bodies it did fetch are kept in {out}" in capsys.readouterr().err
    # Given as the cache, the next run fetches only the rest.
    _slow_linkedin(monkeypatch, 0.0)
    code, out2 = _run(tmp_path, monkeypatch, "--cache", str(out))
    assert code == 0 and all(r.get("desc") for r in json.loads(out2.read_text(encoding="utf-8")))


def test_the_round_gives_hydrate_the_time_its_limit_leaves(drive_round):
    import run_round
    calls, _ = drive_round()
    (cmd,) = [c for c, _ in calls if c[1].endswith("hydrate.py")]
    budget = float(cmd[cmd.index("--budget") + 1])
    limit = run_round.STAGE_BUDGET_SEC["hydrate.py"]
    assert limit - 3 * 60 <= budget <= limit - 60
