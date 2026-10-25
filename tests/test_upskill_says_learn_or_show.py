"""/upskill says which gaps to learn and which to show, and reads the postings skipped.

It weighted gaps by (100 - fit) over tracked and ranked postings only, never read why the
person skipped a posting, and sent every gap to a course, including ones the profile's
own honest-framing table says the person already does the same job with. `bridges.nudge`
is that table's answer for one gap; /upskill runs it, and counts skip blockers as a third
source.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bridges  # noqa: E402

SKILL = (Path(ROOT) / ".claude" / "skills" / "upskill" / "SKILL.md").read_text(encoding="utf-8")


def test_a_gap_the_person_bridges_is_evidence_with_the_sentence_to_say():
    got = bridges.nudge("Tableau")          # the example person bridges it from Power BI
    assert got["nudge"] == bridges.EVIDENCE and "Power BI" in got["have"] and got["say"]
    assert bridges.nudge("Power BI")["nudge"] == bridges.EVIDENCE   # held outright


def test_a_gap_nothing_covers_is_one_to_learn():
    got = bridges.nudge("Kubernetes")
    assert got["nudge"] == bridges.LEARN and got["say"] == ""
    cred = bridges.nudge("CIPS")             # a credential: the map's GAP, with its reason
    assert cred["nudge"] == bridges.LEARN and "credential" in cred["why"].lower()


def test_the_command_line_says_it_one_gap_a_line():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "bridges.py"), "--nudge",
                          "Tableau", "Kubernetes"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                         env=dict(os.environ), check=True).stdout
    lines = [ln for ln in out.splitlines() if not ln.startswith(" ")]
    assert lines[0].split()[:2] == ["Tableau", "evidence"]
    assert lines[1].split()[:2] == ["Kubernetes", "learn"]


def test_upskill_runs_it_and_reads_the_skipped_postings():
    assert "Bash(python3 tools/bridges.py *)" in SKILL.split("---", 2)[1]
    assert 'python3 tools/bridges.py --nudge "<gap>"' in SKILL
    assert '"status": "excluded"' in SKILL and "N skips" in SKILL
    assert "## Show What You Have" in SKILL
    assert "An `evidence` gap gets no course" in SKILL
