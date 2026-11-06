"""A search prints the table the person is shown, so the chat does not build it.

The chat read the round's saved shortlist, JSON with every row's reasons, and wrote the
ranked table from it: about 10k tokens a search (the 4.12 cost audit). `run_round.py
--table` prints the counts line and the table the job-scraper skill sets out (Step 5), each
row's warm route in its Check, for the chat to pass on as it is. What the round finds,
scores, orders and writes stays exactly as it was: the golden round (tests/round_fixture.py)
is run with and without it. Every name here is invented.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import round_fixture as F  # noqa: E402

sys.path.insert(0, os.path.join(F.ROOT, "tools"))
import run_round  # noqa: E402

TABLE = os.path.join(F.FIXTURE, "table.md")
HEAD = ("| # | Score | Verdict | Title | Company | Location | Salary | Deadline | Check | Apply |")


def _printed(stdout: str) -> str:
    """The table as the round printed it: after its heading, up to the line after it."""
    start = stdout.index("table for the person")
    body = stdout[start:].split("\n", 1)[1]
    end = body.find("\nnext:")
    return body[:end] if end >= 0 else body.rstrip("\n")


def _write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows), encoding="utf-8")


def _row(n, fit, company, **more):
    return {"priority": 80 - n, "fit": fit, "title": "Data Analyst", "company": company,
            "location": "Manchester, England, United Kingdom",
            "url": f"https://jobs.example/{n}", **more}


# ------------------------------------------------- the table, from a saved shortlist

def test_the_table_has_the_skills_columns_and_the_warm_routes_in_check(tmp_path):
    summary, out = tmp_path / "summary" / "r4.json", tmp_path / "r4"
    _write(summary, [
        _row(1, 78, "Thistlewood Freight", salary="GBP 50,000 to 58,000",
             warm_route_note="DO NOT APPLY COLD. Ottilie Brack (in_conversation): send the CV"),
        _row(2, 88, "Marrow | Pike"),
        _row(3, 64, "Coldharbour Foods",
             outreach_pending_note="Applying is fine, this is not a warm route. A message is "
                                   "already out and unanswered: Pell Varga. Do not send another.",
             near=[{"asked": "Tableau", "have": "Power BI"}]),
        _row(4, 52, "Underhill Mills"),
    ])
    _write(out / "06_shortlist.json", [
        {"url": "https://jobs.example/1", "deadline": "2026-11-20"},
        {"url": "https://jobs.example/2", "location_verdict": "FLAG",
         "location_reason": "a commutable northern city; considered, never auto-dropped",
         "flags": ["posting body too short to screen fully; gates read what there is",
                   'stated range tops out at £40,000, under the £45,000 target; a decision '
                   'input, never a cut: "up to £40,000"']},
    ])
    said = run_round.table(str(summary), str(out), show=None, names=None, rounds=1)
    lines = said.splitlines()
    assert lines[0] == ("**3 of 4 cleared the pass bar (60+), 2 of them strong (75+); "
                        "target 5 and 2: missed after 1 round**")
    assert HEAD in lines
    rows = [ln for ln in lines if ln.startswith("| ") and ln[2].isdigit()]
    # Highest score first, whatever the round's own order; nothing under 60 on it.
    assert [r.split(" | ")[1] for r in rows] == ["88", "78", "64"]
    assert [r.split(" | ")[2] for r in rows] == ["Strong fit", "Strong fit", "Good fit"]
    assert "Marrow \\| Pike" in rows[0]
    assert ("location: a commutable northern city; stated range tops out at £40,000, under "
            "the £45,000 target") in rows[0] and "too short" not in rows[0]
    assert "DO NOT APPLY COLD. Ottilie Brack (in_conversation): send the CV" in rows[1]
    assert "| GBP 50,000 to 58,000 | 2026-11-20 |" in rows[1]
    assert "A message is already out and unanswered: Pell Varga" in rows[2]
    assert "asked for Tableau, you have Power BI" in rows[2]
    assert "| not stated | not stated |" in rows[2]
    assert rows[2].endswith("| [Apply](https://jobs.example/3) |")
    assert lines[-1] == "1 more scored under 60 and are left off this table."


def test_a_widened_round_that_still_missed_says_after_how_many(tmp_path):
    summary = tmp_path / "r5_round3.json"
    _write(summary, [_row(1, 66, "Thistlewood Freight")])
    said = run_round.table(str(summary), None, show=10, names=None, rounds=3)
    assert said.splitlines()[0] == ("**1 of 1 cleared the pass bar (60+), 0 of them strong "
                                    "(75+); target 10 and 2: missed after 3 rounds**")
    assert "| nothing flagged |" in said


# ------------------------------------------------- the golden round, with and without it

def _files(out: str) -> dict:
    got = {}
    for top, _dirs, names in os.walk(out):
        for n in names:
            p = os.path.join(top, n)
            rel = os.path.relpath(p, out)
            if rel != "round.log":  # its times and its own folder's paths
                with open(p, "rb") as fh:
                    got[rel] = fh.read()
    return got


@pytest.mark.skipif(not shutil.which("node"), reason="the stand-in detail CLI needs node")
def test_the_golden_round_prints_its_table_and_writes_the_same_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_RESCREEN", "off")
    plain, tabled = tmp_path / "plain", tmp_path / "tabled"
    r0 = F.free_stages(F.KEPT, str(plain / "r1"), str(plain))
    r1 = F.free_stages(F.KEPT, str(tabled / "r1"), str(tabled), extra=["--table"])
    for r in (r0, r1):
        assert r.returncode in (0, 2), r.stdout[-2000:] + r.stderr[-2000:]
    assert "table for the person" not in r0.stdout
    # The search's files are the same, byte for byte, and still the golden round's.
    assert F.summary(str(tabled / "r1")) == json.loads(open(F.GOLDEN, encoding="utf-8").read())
    assert _files(str(tabled / "r1")) == _files(str(plain / "r1"))
    assert _files(str(tabled / "summary")) == _files(str(plain / "summary"))
    # The table is the one the skill sets out, warm route and all.
    with open(TABLE, encoding="utf-8") as fh:
        want = fh.read().rstrip("\n")
    printed = _printed(r1.stdout)
    assert printed == want
    assert "DO NOT APPLY COLD. Juno Castellan" in printed
    # A cut of the same round again prints the same table.
    again = F.free_stages(F.KEPT, str(tabled / "r1"), str(tabled), extra=["--recut", "--table"])
    assert again.returncode == 0, again.stdout[-2000:] + again.stderr[-2000:]
    assert _printed(again.stdout) == want


# ------------------------------------------------- the skill passes it on

def test_the_skill_runs_the_round_with_table_and_names_its_columns():
    with open(os.path.join(F.ROOT, ".claude", "skills", "job-scraper", "SKILL.md"),
              encoding="utf-8") as fh:
        skill = " ".join(fh.read().split())
    assert "python3 tools/run_round.py --jobage 14 --table" in skill
    assert "never build it from the JSON" in skill
    # The columns it names are the ones the round prints, in the same order.
    cols = [c.strip() for c in run_round.TABLE_HEAD.splitlines()[0].strip("|").split("|")]
    assert "`" + " | ".join(cols) + "`" in skill
    # The template it used to have the chat fill in is gone.
    assert "| 1 | 82 | Strong fit |" not in skill
