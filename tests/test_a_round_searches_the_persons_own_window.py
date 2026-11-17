"""A round asked for in a chat searches the person's own window, and says which window it used.

From one person's evening (2026-11-16, issue #308): their window was 10 days, and a round
asked for in a chat ran `--jobage 14` because the job-scraper skill's one command said so;
RUNBOOK.md said 7 and the job round's prompt said 7. Postings up to 14 days old took places
on the list, and it cost a re-run. The documented commands now pass no window, the round
says the window at its start (and whether it is the person's), and the skills lint fails on
a literal window in a documented round command.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import run_round  # noqa: E402

TODAY = "2026-11-16"
# The documents a chat or a routine runs a round from.
DOCS = (".claude/skills/job-scraper/SKILL.md", ".claude/skills/job-scraper/manual-round.md",
        "RUNBOOK.md", "automation/prompts/job_round.md")


def _round(tmp_path, monkeypatch, capsys, *extra):
    monkeypatch.setattr(run_round, "run", lambda cmd, log, deadline=None, ok=(0,): 0)
    monkeypatch.setattr(run_round, "_upgrades_line", lambda: "")
    monkeypatch.setattr(run_round, "_job_age_days", lambda: 10)
    scraped = tmp_path / "scraped.json"
    scraped.write_text("[]", encoding="utf-8")
    seen = tmp_path / "seen_jobs.json"
    seen.write_text('{"seen": {}}', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "run_round.py", "--out", str(tmp_path / "r1"), "--from-scraped", str(scraped),
        "--seen", str(seen), "--summary-dir", str(tmp_path / "summ"), "--today", TODAY,
        "--pages", "1", *extra])
    run_round.main()
    said = capsys.readouterr().out
    log = (tmp_path / "r1" / "round.log").read_text(encoding="utf-8")
    return said, log


def test_a_round_with_no_window_given_searches_the_persons_and_says_so(tmp_path, monkeypatch,
                                                                         capsys):
    said, log = _round(tmp_path, monkeypatch, capsys)
    assert "window: 10 days (your setting)" in said
    assert "window: 10 days (your setting)" in log


def test_a_window_given_for_one_search_says_it_is_not_the_persons(tmp_path, monkeypatch,
                                                                  capsys):
    said, _ = _round(tmp_path, monkeypatch, capsys, "--jobage", "14")
    assert "window: 14 days (given for this search; your setting is 10)" in said


def _lint(root: Path) -> subprocess.CompletedProcess:
    """The skills lint run over a small tree of its own, its YAML reader stood in."""
    tools = root / "tools"
    tools.mkdir(parents=True)
    shutil.copy(ROOT / "tools" / "lint_skills.py", tools / "lint_skills.py")
    (tools / "yaml.py").write_text(
        "class YAMLError(Exception):\n    pass\n\n"
        "def safe_load(text):\n"
        "    return dict(l.split(':', 1) for l in (text or '').splitlines() if ':' in l)\n",
        encoding="utf-8")
    skill = root / ".claude" / "skills" / "job-scraper" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: job-scraper\ndescription: finds jobs\n---\n\n"
                     "Run `python3 tools/run_round.py --table`.\n", encoding="utf-8")
    command = root / ".claude" / "commands" / "scrape.md"
    command.parent.mkdir(parents=True)
    command.write_text("# /scrape - find jobs\n", encoding="utf-8")
    (root / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"allow": []}}),
                                                    encoding="utf-8")
    return subprocess.run([sys.executable, str(tools / "lint_skills.py")], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def test_no_documented_round_command_sets_a_window_of_its_own(tmp_path):
    """The app's own documents, copied into a tree of the lint's own, pass it. The skill goes
    in beside its folder's SKILL.md, whose tools this small tree does not hold."""
    _lint(tmp_path)
    for doc in DOCS:
        to = tmp_path / doc.replace("SKILL.md", "skill-text.md")
        to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / doc, to)
    got = subprocess.run([sys.executable, str(tmp_path / "tools" / "lint_skills.py")],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert got.returncode == 0, got.stdout


def test_the_skills_lint_fails_on_a_literal_window_in_a_round_command(tmp_path):
    ok = _lint(tmp_path / "ok")
    assert ok.returncode == 0, ok.stdout
    bad = tmp_path / "bad"
    _lint(bad)
    (bad / "RUNBOOK.md").write_text("```bash\npython3 tools/run_round.py --jobage 7\n```\n",
                                    encoding="utf-8")
    got = subprocess.run([sys.executable, str(bad / "tools" / "lint_skills.py")],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert got.returncode == 1
    assert "RUNBOOK.md" in got.stdout and "--jobage 7" in got.stdout
