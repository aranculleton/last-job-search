"""The general resume's plain-text copy and its short copy to paste read "AWS", as the PDF does.

Issue 236: `stage_picks.py general` keeps a .txt beside the PDF and prints a short copy to
paste beside it, and both said "Built pipelines on A WS (Redshift, S3)" and "A WS Certified
Machine Learning Engineer Associate" while the PDF read AWS. Both are built from the draft's
own fields (verify_pdf.roundtrip_fields), where "AWS" is written "A\\kern0pt WS" so pypdf reads
the page whole; TeX takes the space after "0pt" as part of the kern, and the plain text kept
it. A recruiter or a form pasted into got "A WS". The candidate and the profile are the
invented example person, given an AWS bullet and an AWS certificate.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools")]

import verify_pdf as V  # noqa: E402

CERT = "AWS Certified Machine Learning Engineer Associate (2025)"


def test_a_kern_reads_as_the_word_tex_prints():
    assert V.tex_plain(r"pipelines on A\kern0pt WS (Redshift, S3)") == \
        "pipelines on AWS (Redshift, S3)"
    assert V.tex_plain(r"A\kern0pt WS Certified") == "AWS Certified"
    # Only the one space TeX reads goes: a word after the kern's own space stays apart.
    assert V.tex_plain(r"on A\kern0pt WS and SQL") == "on AWS and SQL"
    assert V.tex_plain(r"a -\kern0pt- b") == "a -- b"


def _profile(tmp_path) -> str:
    prof = str(tmp_path / "profile")
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof)
    for name, old, new in (
            ("bullets.py", "in Python and SQL across", "in Python and SQL on AWS across"),
            ("roles.py", "Microsoft Certified: Power BI Data Analyst Associate (2024)",
             r"A\kern0pt WS Certified Machine Learning Engineer Associate (2025)"),
            ("01-candidate-profile.md",
             "- Microsoft Certified: Power BI Data Analyst Associate (2024)", "- " + CERT)):
        path = os.path.join(prof, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert old in text, (name, old)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new))
    return prof


@pytest.mark.skipif(not all(shutil.which(t) for t in ("lualatex", "pdftotext", "pdfinfo")),
                    reason="lualatex and Poppler are not installed here")
def test_the_kept_text_and_the_short_copy_read_aws(tmp_path):
    pytest.importorskip("pypdf")
    env = dict(os.environ, LJS_PROFILE=_profile(tmp_path), LJS_STATE=str(tmp_path / "state"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "stage_picks.py"),
                        "general", str(tmp_path / "general")], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=ROOT, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    short = r.stdout.split("paste this short copy beside it:\n", 1)[1]
    [txt] = [ln.split("text: ", 1)[1].strip() for ln in r.stdout.splitlines()
             if ln.startswith("text: ")]
    with open(os.path.join(str(tmp_path / "state"), txt), encoding="utf-8") as fh:
        kept = fh.read()
    assert "Python and SQL on AWS across" in kept, kept
    assert CERT in kept, kept
    assert "Python and SQL on AWS across" in short, short
    for text in (kept, short):
        assert not re.search(r"\bA WS\b", text), text
