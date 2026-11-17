"""Employers nobody has judged against the person's bar are judged inside the round, once, by a
small model, and the judgement is kept for good; the round never waits on it past a set time,
and an employer left unjudged still waits below judged ones.

From the job search audit (issue 313, its redesign; issue 327, part 4): a round listed the
employers nobody had judged and ranked them down (issue 304), and a chat judged them by hand
after the round, if at all, so the list a round reported was not the list that cleared the
person's bar. Now the round writes a brief a small agent judges from (the person's bar and what
each posting says about its employer), and its cut with --judged waits for the answer, keeps
each verdict marked as the round's, and cuts with them. Every employer is invented.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bar  # noqa: E402
import run_round  # noqa: E402

TODAY = "2026-11-16"
LEEDS = "Leeds, England, United Kingdom"
UNKNOWN = ("Quorlan Media", "Tessaly Consulting", "Vintry Labs AI")
KNOWN = ("Ambleside Freight", "Bellingham Foods", "Carrow Retail")
ANSWER = [{"company": "Quorlan Media", "verdict": "pay", "why": "pays at the top of the market"},
          {"company": "Tessaly Consulting", "verdict": "prestige", "why": "a well-known firm"},
          {"company": "Vintry Labs AI", "verdict": "none", "why": "a two-person AI start-up"}]


def _row(n, company, priority):
    return {"title": "Data Analyst", "company": company, "location": LEEDS,
            "url": f"https://www.linkedin.com/jobs/view/{8900000 + n}/", "portal": "linkedin",
            "date": "2026-11-14", "first_seen": "2026-11-14", "fit": 78, "priority": priority,
            "opportunity": 70,
            "desc": f"About us: {company} helps businesses grow with data. "
                    "You will build SQL and Python reporting for the planning team."}


def _main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["run_round.py", *argv])
    return run_round.main()


@pytest.fixture
def a_round(tmp_path, monkeypatch, capsys, judged):
    """A round run on the real path (run_round.main, the throttle as a process), its ranking
    given: three employers nobody has judged above three the person's own records place."""
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    monkeypatch.setattr(bar, "FRONTIER", {"frontier example labs"})
    monkeypatch.setattr(bar, "PUBLIC", re.compile(r"(?!x)x"))
    monkeypatch.setattr(run_round, "declined_now", lambda: {})
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    judged(*KNOWN)
    ranked = ([_row(n, c, 95 - n) for n, c in enumerate(UNKNOWN)]
              + [_row(10 + n, c, 85 - n) for n, c in enumerate(KNOWN)])

    def stage(cmd, log, deadline=None, ok=(0,)):
        tool = os.path.basename(cmd[1])
        if tool == "fit.py":
            with open(cmd[cmd.index("--out") + 1], "w", encoding="utf-8") as fh:
                json.dump(ranked, fh)
        elif tool == "throttle.py":
            got = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            assert got.returncode == 0, got.stderr
        return 0

    monkeypatch.setattr(run_round, "run", stage)
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]", encoding="utf-8")
    rounds = st / "documents" / "rounds"
    folder = st / "rounds" / "r7"
    common = ["--seen", str(st / "job_scraper" / "seen_jobs.json"),
              "--tracker", str(st / "job_search_tracker.csv"), "--summary-dir", str(rounds),
              "--today", TODAY, "--show", "3"]
    _main(monkeypatch, ["--out", str(folder), "--from-scraped", str(scraped), "--pages", "1",
                        *common])
    said = capsys.readouterr().out
    return {"folder": folder, "rounds": rounds, "common": common, "said": said}


def _later(path, answer, after=0.4):
    """The agent, answering in the background a moment after the cut starts waiting."""
    def write():
        time.sleep(after)
        tmp = str(path) + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(answer, fh)
        os.replace(tmp, path)
    t = threading.Thread(target=write)
    t.start()
    return t


def test_the_round_writes_a_brief_a_small_agent_judges_and_its_cut_keeps_each_verdict(
        a_round, monkeypatch, capsys):
    folder, said = a_round["folder"], a_round["said"]
    assert "nobody has judged yet" in said
    # What the round asks: the agent, on the brief it wrote, then its own cut waiting for it.
    assert f"start the {run_round.JUDGE_AGENT} agent on" in said
    assert f"--recut --out {folder}".replace(str(folder), "") in said and "--judged" in said
    brief = (folder / run_round.JUDGE_BRIEF).read_text(encoding="utf-8")
    assert all(c in brief for c in UNKNOWN)
    assert "pay, prestige, signal or none" in brief and "BEGIN-UNTRUSTED-" in brief
    assert "About us: Quorlan Media helps businesses grow with data." in brief
    assert run_round.JUDGED in brief
    summary = json.loads((a_round["rounds"] / "r7.json").read_text(encoding="utf-8"))
    assert [r["company"] for r in summary] == list(KNOWN)

    # The agent answers while the cut waits; the cut keeps each verdict and cuts with them.
    answer = folder / run_round.JUDGED
    t = _later(answer, ANSWER)
    try:
        assert _main(monkeypatch, ["--out", str(folder), "--recut", "--judged", "30",
                                   *a_round["common"]]) == 0
    finally:
        t.join()
    out = capsys.readouterr().out
    assert "judged in the round: 3 employer(s), kept for good (none 1, pay 1, prestige 1)" in out
    again = json.loads((a_round["rounds"] / "r7.json").read_text(encoding="utf-8"))
    assert [r["company"] for r in again] == ["Quorlan Media", "Tessaly Consulting",
                                             "Ambleside Freight"]
    stored = {r["name"]: r for r in bar.judged().values()}
    assert {stored[c]["by"] for c in UNKNOWN} == {"round"}
    assert stored["Vintry Labs AI"]["verdict"] == "none"
    # Taken once: a judgement overturned afterwards is never written over by a later cut.
    assert not answer.exists()
    bar.judge("Vintry Labs AI", "signal", "a person said it is backed", today=TODAY)
    assert _main(monkeypatch, ["--out", str(folder), "--recut", *a_round["common"]]) == 0
    assert bar.judgement("Vintry Labs AI")["verdict"] == "signal"


def test_an_answer_never_writes_over_a_judgement_made_while_the_round_waited(
        a_round, monkeypatch, capsys):
    folder = a_round["folder"]
    bar.judge("Tessaly Consulting", "none", "a chat looked it up meanwhile", today=TODAY)
    (folder / run_round.JUDGED).write_text(json.dumps(ANSWER), encoding="utf-8")
    assert _main(monkeypatch, ["--out", str(folder), "--recut", "--judged",
                               *a_round["common"]]) == 0
    out = capsys.readouterr().out
    assert "judged in the round: 2 employer(s)" in out
    assert "already judged or on your lists, left as they are: 1" in out
    assert bar.judgement("Tessaly Consulting")["why"] == "a chat looked it up meanwhile"
    assert bar.judgement("Quorlan Media")["by"] == "round"


def test_an_employer_the_answer_leaves_empty_still_waits_below_judged_ones(
        a_round, monkeypatch, capsys):
    folder = a_round["folder"]
    left = [dict(ANSWER[0]), dict(ANSWER[1], verdict="", why=""), dict(ANSWER[2])]
    (folder / run_round.JUDGED).write_text(json.dumps(left), encoding="utf-8")
    assert _main(monkeypatch, ["--out", str(folder), "--recut", *a_round["common"]]) == 0
    out = capsys.readouterr().out
    assert "not judged, so still waiting below judged ones: Tessaly Consulting" in out
    again = json.loads((a_round["rounds"] / "r7.json").read_text(encoding="utf-8"))
    assert [r["company"] for r in again] == ["Quorlan Media", "Ambleside Freight",
                                             "Bellingham Foods"]
    assert bar.judgement("Tessaly Consulting") is None


@pytest.mark.timing
def test_the_round_never_waits_on_the_judge_past_its_time(a_round, monkeypatch, capsys):
    folder = a_round["folder"]
    start = time.monotonic()
    assert _main(monkeypatch, ["--out", str(folder), "--recut", "--judged", "2",
                               *a_round["common"]]) == 0
    took = time.monotonic() - start
    out = capsys.readouterr().out
    assert took < 20, took
    assert "no answer from the employer-judge agent within 2 seconds" in out
    # Unjudged, they wait below judged ones, as before (issue 304).
    again = json.loads((a_round["rounds"] / "r7.json").read_text(encoding="utf-8"))
    assert [r["company"] for r in again] == list(KNOWN)


def test_the_judge_is_a_small_background_agent_the_round_instructions_start():
    head = open(os.path.join(ROOT, ".claude", "agents", "employer-judge.md"),
                encoding="utf-8").read().split("\n---", 1)[0]
    import yaml
    meta = yaml.safe_load(head[4:])
    assert meta["name"] == run_round.JUDGE_AGENT
    assert meta["model"] == "haiku" and meta["background"] is True
    assert {t.strip() for t in meta["tools"].split(",")} == {"Read", "Write"}
    for doc in (".claude/skills/job-scraper/SKILL.md", "RUNBOOK.md",
                "automation/prompts/job_round.md"):
        text = " ".join(open(os.path.join(ROOT, doc), encoding="utf-8").read().split())
        assert "employer-judge" in text and "--judged" in text, doc
