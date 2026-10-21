"""A round streams on in any encoding, and ends with the answer its exit code promises.

- On Windows round.log was opened in cp1252, and a stage's stderr line with an accented
  letter killed the thread draining the pipe: the stage hung until its budget ran out.
  Simulated here with an ASCII default, which fails the same way.
- A round in which nothing survived the free gates died at hydrate ("0% have a
  description") as a broken stage, exit 1, before it said which portals were down.
- A missing --from-scraped file was a traceback; a stage timeout did not say the round
  could go on from the finished scrape; a scrape that timed out was timed twice.
- --from-scraped --expand scraped live from round 2, and each widening multiplied the
  round before's pages, so round 3 searched 6x the first.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import contextlib

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)

import run_round  # noqa: E402

ASCII = {"LC_ALL": "C", "LANG": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}


def test_a_line_the_log_cannot_hold_never_stops_the_pipe_being_read(tmp_path):
    child = ("import sys; sys.stderr.buffer.write('progress: Montr\\u00e9al page 1\\n'"
             ".encode()); sys.stderr.flush()\n"
             "for i in range(3000): sys.stderr.write('progress line %d ' % i + 'x' * 200 + '\\n')\n"
             "print('[]')")
    with open(tmp_path / "round.log", "a", encoding="ascii") as log:
        code, out, err = run_round._stream([sys.executable, "-c", child], log, 8)
    assert code == 0 and out.strip() == "[]"
    assert err.count("progress line") == 3000


def _posting(n, company, desc):
    return {"url": f"https://careers.example.com/jobs/{n}", "title": "Data Analyst",
            "company": company, "location": "Manchester, England, United Kingdom",
            "date": "2026-10-20", "portal": "freehire", "desc": desc}


BODY = ("You will own demand forecasting and inventory analytics for the network, working "
        "with operations and commercial teams on stock levels and replenishment. ") * 6


def _round(tmp_path, scraped, *extra, env=None):
    kept = tmp_path / "kept.json"
    kept.write_text(json.dumps(scraped), encoding="utf-8")
    cmd = [sys.executable, os.path.join(TOOLS, "run_round.py"), "--from-scraped", str(kept),
           "--out", str(tmp_path / "r1"), "--summary-dir", str(tmp_path / "summary"),
           "--seen", str(tmp_path / "seen_jobs.json"), "--tracker", str(tmp_path / "t.csv"),
           "--today", "2026-10-21", *extra]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=ROOT, env={**os.environ, **(env or {})},
                          timeout=300)


def test_a_round_in_a_non_utf8_default_encoding_runs_to_its_end(tmp_path):
    scraped = [_posting(1, "Brûlerie Analytique", "Fluency in Welsh is essential. " + BODY),
               _posting(2, "Café Logistique", BODY)]
    r = _round(tmp_path, scraped, env=ASCII)
    assert r.returncode == run_round.EXIT_YIELD_MISSED, r.stdout[-1500:] + r.stderr[-1500:]
    assert "YIELD TARGET MISSED" in r.stdout
    with open(tmp_path / "r1" / "round.log", encoding="utf-8") as fh:
        assert "Brûlerie Analytique" in fh.read()


def test_a_round_with_nothing_to_fetch_misses_rather_than_breaks(tmp_path):
    r = _round(tmp_path, [])
    assert r.returncode == run_round.EXIT_YIELD_MISSED, r.stdout[-1500:] + r.stderr[-1500:]
    assert "stage failed" not in r.stdout + r.stderr


def test_a_missing_saved_scrape_is_said_plainly(tmp_path):
    cmd = [sys.executable, os.path.join(TOOLS, "run_round.py"), "--from-scraped",
           str(tmp_path / "nowhere.json"), "--out", str(tmp_path / "r1"),
           "--summary-dir", str(tmp_path / "summary")]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "there is no file at" in r.stderr


# ------------------------------------------------------------- stages stood in

@pytest.fixture
def stages(tmp_path, monkeypatch):
    """main() with `_stream` stood in: `timeout` names the stages that run out of time."""
    import sync_app
    plan = {"timeout": set()}

    def stream(cmd, log, budget):
        name = os.path.basename(cmd[1])
        if name in plan["timeout"] and "--finish" not in cmd:
            raise run_round.StageTimeout("")
        return 0, "", ""

    monkeypatch.setattr(run_round, "_stream", stream)
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    monkeypatch.setattr(sync_app, "nudge", lambda *a, **k: None)
    spawned = []
    monkeypatch.setattr(run_round.subprocess, "call",
                        lambda cmd, *a, **k: spawned.append(list(cmd)) or 0)

    def go(*argv, timeout=()):
        plan["timeout"] = set(timeout)
        spawned.clear()
        monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(tmp_path / "r1"),
                                          "--summary-dir", str(tmp_path / "summary"),
                                          "--today", "2026-10-21", *argv])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = run_round.main()
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), list(spawned)
    return go


def test_a_stage_that_runs_out_of_time_says_how_to_go_on(stages, tmp_path):
    saved = tmp_path / "saved.json"
    saved.write_text("[]")
    code, _, _ = stages("--from-scraped", str(saved), timeout=["hydrate.py"])
    assert "--from-scraped" in str(code) and "kept.json" in str(code)


def test_a_scrape_that_ran_out_of_time_is_timed_once(stages):
    _, out, _ = stages(timeout=["scrape_wide.py"])
    (line,) = [ln for ln in out.splitlines() if ln.startswith("time: ")]
    assert line.count("scrape_wide") == 1, line


def test_a_round_from_a_saved_scrape_widens_live_and_says_so(stages, tmp_path):
    # --expand is the asking: a round resumed from a timeout's kept scrape still owes its
    # widening, and a wider round's extra pages exist only on the live portals. It says so
    # before it runs, and the next round is never handed the saved scrape again.
    saved = tmp_path / "saved.json"
    saved.write_text("[]")
    code, out, spawned = stages("--from-scraped", str(saved), "--expand")
    (nxt,) = spawned
    assert "--from-scraped" not in nxt and "--expand" in nxt
    assert "the wider round scrapes the portals live" in out


def test_each_widening_is_a_multiple_of_the_first_rounds_pages(stages, tmp_path):
    _, _, (second,) = stages("--expand", "--pages", "5")
    assert second[second.index("--pages") + 1] == "10"
    # The second round, run with what the first handed it, widens to 3x the first.
    _, _, (third,) = stages(*second[2:])
    assert third[third.index("--pages") + 1] == "15"
