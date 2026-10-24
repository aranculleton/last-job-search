"""verify_batch.sh on a Mac: BSD sed refused the skills check, and the repeated-bullet
check flagged resumes with no bullet repeated (2026-10-24).

BSD sed needs a ";" before a closing "}" that GNU sed lets go. The repeated-bullet check
read the text layer line by line through sed and cut; a reader that puts each bullet's
mark on a line of its own made every bullet empty, and every empty one a repeat. It now
reads whole bullets in Python (audit_letters.resume_bullets), as the shared-phrase check
does. The resumes are invented.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import audit_letters as A  # noqa: E402

LAYER = """Morgan Ellis
Professional Experience
Quayside Foods                                   Analyst                 2023 - 2025
  • Built a demand model across 40 stores that cut waste by 12% in its first quarter
  • Ran weekly pricing tests on the online shop and wrote up what moved conversion
Larkspur Retail                                  Assistant              2021 - 2023
  • Cleaned the stock ledger and set up the first automated reorder alerts for the team
Education
"""


def test_whole_bullets_are_read_however_the_marks_sit():
    lone = re.sub(r"^( *)• ", r"\1•\n\1  ", LAYER, flags=re.M)   # each mark on its own line
    for text in (LAYER, lone):
        got = A.resume_bullets(text, "Professional Experience", "Education")
        assert len(got) == 3 and got[0].startswith("Built a demand model")
        assert A.duplicate_bullets(got) == []


def test_a_bullet_on_the_page_twice_is_found():
    twice = LAYER.replace("Larkspur Retail", "  • Built a demand model across 40 stores that cut "
                          "waste by 12% in its first quarter\nLarkspur Retail")
    got = A.resume_bullets(twice, "Professional Experience", "Education")
    assert len(A.duplicate_bullets(got)) == 1
    # Two bullets that only start alike are two bullets.
    alike = ["Built a demand model across 40 stores for the buying team",
             "Built a demand dashboard for the store managers in three regions"]
    assert A.duplicate_bullets(alike) == []


def test_the_skills_check_is_written_the_way_both_seds_read_it():
    with open(os.path.join(ROOT, "tools", "verify_batch.sh"), encoding="utf-8") as fh:
        script = fh.read()
    assert "{/^$H_EDUCATION/d;p;}" in script and "{/^$H_EDUCATION/d;p}" not in script
    assert "cut -c1-45" not in script
    out = subprocess.run(["sed", "-n", "/^Skills/,/^Education/{/^Education/d;p;}"],
                         input="Intro\nSkills\nSQL (advanced)\nEducation\nBSc\n",
                         capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout == "Skills\nSQL (advanced)\n"
