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
import shutil
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


def test_the_skills_check_reads_the_same_on_every_computer():
    # The check is Python now (tools/verify_batch.py), so no sed of a Mac's or of Linux's
    # decides what it reads; the shell name is a shim that runs it.
    import verify_batch as B
    lines = ["Intro", "Skills", "SQL (advanced)", "Education", "BSc"]
    assert B.sed_range(lines, "Skills", "Education", drop_end=True) == ["Skills",
                                                                        "SQL (advanced)"]
    # A range is closed by the next end line and opens again at the next start, as sed's.
    assert B.sed_range(["Skills", "a", "Education", "b", "Skills", "c"], "Skills",
                       "Education") == ["Skills", "a", "Education", "Skills", "c"]
    with open(os.path.join(ROOT, "tools", "verify_batch.sh"), encoding="utf-8") as fh:
        shim = fh.read()
    code = [ln for ln in shim.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert not [ln for ln in code if re.search(r"\b(sed|awk|pdftotext|pdfinfo)\b", ln)]
    assert "verify_batch.py" in shim
    sed = shutil.which("sed")
    if sed:
        # Bytes in and out: in text mode Python turns each "\n" it writes into os.linesep,
        # "\r\n" on Windows (https://docs.python.org/3/library/subprocess.html, "Frequently
        # Used Arguments"), so sed read other lines from the ones the port reads. The full
        # path, as Windows looks in its own folders first for a bare name.
        out = subprocess.run([sed, "-n", "/^Skills/,/^Education/{/^Education/d;p;}"],
                             input=b"Intro\nSkills\nSQL (advanced)\nEducation\nBSc\n",
                             capture_output=True)
        said = out.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
        assert said.splitlines() == B.sed_range(lines, "Skills", "Education", drop_end=True), (
            sed, out.returncode, out.stderr.decode("utf-8", "replace"))
