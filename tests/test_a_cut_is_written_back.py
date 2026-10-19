"""Every posting the text screen cuts is written back, so it is not fetched again.

CLAUDE.md: every posting ruled out is written back to seen_jobs.json. The text
screen's hard cuts never were, so each round hydrated, screened and cut the same
postings again: one HTTP call each, every round, for a verdict already reached.
They are recorded through tools/exclude.py, with the quote and what the cut
rests on, and the next round's prefilter drops them before hydrate. A flag is a
scoring input, never a ruling, and is not recorded.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import exclude  # noqa: E402
import prefilter  # noqa: E402

LOC = "Manchester, England, United Kingdom"
FILLER = (" You will own demand forecasting and inventory analytics for the North West "
          "network, working with operations and commercial teams in SQL and Python.") * 4
CUT = {"url": "https://careers.example.com/jobs/101", "title": "Supply Chain Analyst",
       "company": "Brindle Hart Logistics", "location": LOC,
       "desc": "Fluency in Welsh is essential for this role." + FILLER}
FLAGGED = {"url": "https://careers.example.com/jobs/102", "title": "Inventory Analyst",
           "company": "Fernhill Freight", "location": LOC,
           "desc": "A Master's degree in operations research is required." + FILLER}


def test_a_cut_is_recorded_with_its_reason_and_a_flag_is_not(tmp_path):
    src, out, seen = tmp_path / "in.json", tmp_path / "out.json", tmp_path / "seen.json"
    src.write_text(json.dumps([CUT, FLAGGED]))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "text_screen.py"), str(src),
                        "--out", str(out), "--seen", str(seen), "--today", "2026-10-14"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert [j["title"] for j in json.loads(out.read_text())] == ["Inventory Analyst"]
    entries = json.loads(seen.read_text())["seen"]
    assert len(entries) == 1
    (e,) = entries.values()
    assert e["status"] == "excluded" and e["basis"] == "rules"
    assert e["exclusion_reason"].startswith("Welsh stated as a requirement")
    assert e["location"] == LOC and e["excluded_date"] == "2026-10-14"
    assert e["rests_on"] != exclude.ALL            # the screen's own words name its setting
    # The next round drops it before hydrate pays for it again.
    assert prefilter.already_ruled_out(str(seen))(CUT)
    assert not prefilter.already_ruled_out(str(seen))(FLAGGED)


def test_many_rulings_are_one_write_and_the_same_as_one_at_a_time(tmp_path):
    one, many = str(tmp_path / "one.json"), str(tmp_path / "many.json")
    rulings = [{"url": CUT["url"], "reason": "Welsh stated as a requirement: \"essential\"",
                "title": CUT["title"], "company": CUT["company"], "location": LOC}]
    exclude.add(CUT["url"], rulings[0]["reason"], CUT["title"], CUT["company"],
                today="2026-10-14", path=one, location=LOC)
    assert exclude.add_many(rulings, today="2026-10-14", path=many) == 1
    assert json.load(open(one)) == json.load(open(many))


def _screen_command(tmp_path, monkeypatch, *extra):
    import run_round
    stages = []
    monkeypatch.setattr(run_round, "run", lambda cmd, log, deadline=None, ok=(0,): stages.append(cmd))
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]")
    monkeypatch.setattr(sys, "argv", ["run_round.py", "--out", str(tmp_path / "r1"),
                                      "--from-scraped", str(scraped),
                                      "--summary-dir", str(tmp_path / "summ"), *extra])
    run_round.main()
    (cmd,) = [c for c in stages if os.path.basename(c[1]) == "text_screen.py"]
    return cmd


def test_a_round_records_its_cuts_unless_told_not_to_write(tmp_path, monkeypatch):
    seen = str(tmp_path / "seen.json")
    cmd = _screen_command(tmp_path, monkeypatch, "--seen", seen)
    assert cmd[cmd.index("--seen") + 1] == seen
    assert "--seen" not in _screen_command(tmp_path, monkeypatch, "--no-seen-write")
