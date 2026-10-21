"""Where a rule is said twice, the copies drifted apart, and where code holds the rule the
docs say what the code does.

A documentation audit found nineteen places where two instruction files said one rule two
ways. These are the ones a check can hold, each against the code or the file it names:

- A pointer to a section ("CLAUDE.md, "Never assume the tracker is complete"") that no
  longer exists sends a session looking for a rule it will not find.
- MAINTAINING.md still started a session with a bare `git merge origin/master`, the merge
  CLAUDE.md replaced with `sync_app.py --pull` because a rewritten master conflicts on
  hundreds of files.
- ARCHITECTURE.md said a missed round keeps three diagnostic files; `run_round.py` keeps
  four.
- The verification checklist banned em dashes only; `locale_rules.py` bans en dashes too,
  so a document that followed the checklist failed `verify_batch.sh`.
- Four files gave four different sets of sources that ground a claim. `check_numbers.py`
  reads the files `person.json` `grounding.sources` names, so a doc that says what grounds
  a claim names that setting.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from tests import repo_files  # noqa: E402

ROOT_DOCS = ("CLAUDE.md", "RUNBOOK.md", "MAINTAINING.md", "SETUP.md", "START_HERE.md")
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def _docs():
    return [p for p in repo_files.files("*.md", ".claude/**/*.md", ".claude/**/*.js",
                                        "automation/**/*.md")
            if not p.name.startswith("CHANGELOG")]


def _headings(doc: str) -> list[str]:
    text = (ROOT / doc).read_text(encoding="utf-8")
    return [re.sub(r"^#+\s*", "", ln).strip().lower()
            for ln in text.splitlines() if ln.startswith("#")]


# `CLAUDE.md, "Memory"`, `RUNBOOK.md, "Tools run directly"`, `CLAUDE.md under "..."`.
# A `profile/CLAUDE.md` citation is the person's file, which the app does not ship.
CITATION = re.compile(r'(?<![/\w])(' + "|".join(re.escape(d) for d in ROOT_DOCS) +
                      r')`?,?\s+(?:under\s+)?"([^"]{3,120})"')


def test_every_section_a_doc_points_at_exists():
    heads = {d: _headings(d) for d in ROOT_DOCS if (ROOT / d).exists()}
    missing = []
    for path in _docs():
        text = path.read_text(encoding="utf-8")
        for m in CITATION.finditer(text):
            doc, title = m.group(1), " ".join(m.group(2).split()).lower().rstrip(".")
            if doc in heads and not any(h.startswith(title) for h in heads[doc]):
                missing.append(f"{path.relative_to(ROOT)}: {doc}, \"{m.group(2)}\"")
    assert missing == []


def test_the_session_start_in_maintaining_is_the_sync_not_a_bare_merge():
    text = (ROOT / "MAINTAINING.md").read_text(encoding="utf-8")
    section = text.split("## Master is the trunk", 1)[1].split("\n## ", 1)[0]
    assert "sync_app.py --pull" in section
    assert "git merge origin/master" not in section


def test_the_docs_count_the_files_a_missed_round_keeps():
    import run_round
    said = {}
    for doc in ("ARCHITECTURE.md", "RUNBOOK.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        for m in re.finditer(r"keeps (\w+) files it otherwise deletes", text):
            said[doc] = NUMBERS.get(m.group(1).lower(), m.group(1))
    assert said, "no doc says how many files a missed round keeps"
    assert set(said.values()) == {len(run_round.DIAGNOSTICS)}, said


def test_the_checklist_bans_every_dash_the_checks_ban():
    import locale_rules
    checklist = (ROOT / ".claude" / "skills" / "job-application-assistant" /
                 "verification-checklist.md").read_text(encoding="utf-8")
    line = next(ln for ln in checklist.splitlines() if "dash" in ln.lower())
    if locale_rules.EN_DASH in locale_rules.DEFAULT_BANNED_CHARACTERS:
        assert "en dash" in line or "em or en" in line, line
    guide = (ROOT / ".claude" / "skills" / "job-application-assistant" /
             "05-cv-templates.md").read_text(encoding="utf-8")
    assert "Keep `--` everywhere" not in guide


def test_a_doc_that_says_what_grounds_a_claim_names_the_setting_the_check_reads():
    # check_numbers.py reads person.json grounding.sources, with its own default.
    import check_numbers
    assert check_numbers.SOURCES
    said = re.compile(r"grounded (?:if|when) (?:EITHER|ANY|any|either)\b")
    loose = []
    for path in _docs():
        for para in path.read_text(encoding="utf-8").split("\n\n"):
            if said.search(para) and "grounding.sources" not in para:
                loose.append(f"{path.relative_to(ROOT)}: {said.search(para).group(0)}")
    assert loose == []
