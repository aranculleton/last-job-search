"""The design check reads each document against what was set for it.

Three things it got wrong (the drafting audit, 2026-10-25):

- A profile with `documents.resume_pages: 2` failed every two-page resume: the check
  demanded one page, and its column check compared page 2's first line with page 1's foot.
- The letter was checked against the resume's paper, so `documents.letter_paper` failed
  every letter.
- With no pypdf it reported a finding (exit 1) where every other check says "not checked"
  (exit 3), and the test of that exit replaced the design check with one that always
  passed.

The documents here are invented.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import design_check  # noqa: E402

needs_tex = pytest.mark.skipif(not shutil.which("lualatex") or not importlib.util.find_spec("pypdf"),
                               reason="lualatex or pypdf is not installed")
TOOL = os.path.join(ROOT, "tools", "design_check.py")


def _pdf(folder, stem, paper="a4paper", pages=1):
    """A plain page or two of 11pt text, well inside the margins."""
    os.makedirs(folder, exist_ok=True)
    body = "\n\\newpage\n".join(
        "\n\n".join(f"Page {n} line {i}: weekly demand forecasts for the depots." for i in range(12))
        for n in range(1, pages + 1))
    with open(os.path.join(folder, stem + ".tex"), "w", encoding="utf-8") as fh:
        fh.write(f"\\documentclass[11pt,{paper}]{{article}}\n\\usepackage[margin=25mm]{{geometry}}\n"
                 f"\\pagestyle{{empty}}\n\\begin{{document}}\n{body}\n\\end{{document}}\n")
    subprocess.run(["lualatex", "-interaction=nonstopmode", stem + ".tex"], cwd=folder,
                   capture_output=True, timeout=300)
    return os.path.join(folder, stem + ".pdf")


def _profile(tmp_path, **documents):
    dst = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), dst)
    p = dst / "person.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["documents"].update(documents)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return str(dst)


def _run(args, profile):
    env = dict(os.environ, LJS_PROFILE=profile)
    return subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True,
                          env=env)


def _drafts(tmp_path):
    path = tmp_path / "drafts.json"
    path.write_text(json.dumps([{"company": "Larkspur Freight", "role": "Analyst",
                                 "abbr": "Larkspur"}]), encoding="utf-8")
    return str(path)


@needs_tex
def test_a_two_page_resume_passes_where_two_pages_are_allowed(tmp_path):
    pdf = _pdf(str(tmp_path / "cv"), "Morgan_Ellis_CV_Larkspur", pages=2)
    assert design_check.check(pdf, "a4", pages=2) == []
    one = design_check.check(pdf, "a4", pages=1)
    assert one == ["PAGES 2: the design must keep one page"]      # and no COLUMNS from page 2
    drafts = _drafts(tmp_path)
    two = _run([pdf, "--for", drafts, "--abbr", "Larkspur"], _profile(tmp_path, resume_pages=2))
    assert two.returncode == 0, two.stdout
    default = _run([pdf, "--for", drafts, "--abbr", "Larkspur"],
                   os.path.join(ROOT, "profile.example"))
    assert default.returncode == 1 and "PAGES 2" in default.stdout


@needs_tex
def test_the_letter_is_read_against_the_letters_paper(tmp_path):
    letter = _pdf(str(tmp_path / "cover_letters"), "Morgan_Ellis_Cover_Letter_Larkspur",
                  paper="letterpaper")
    resume = _pdf(str(tmp_path / "cv"), "Morgan_Ellis_CV_Larkspur")
    drafts = _drafts(tmp_path)
    profile = _profile(tmp_path, letter_paper="letterpaper")
    got = _run([letter, "--for", drafts, "--abbr", "Larkspur"], profile)
    assert got.returncode == 0, got.stdout
    got = _run([resume, "--for", drafts, "--abbr", "Larkspur"], profile)
    assert got.returncode == 0, got.stdout          # the resume keeps the market's A4
    # A two-page letter is still a finding where the resume may take two.
    long = _pdf(str(tmp_path / "cover_letters"), "Morgan_Ellis_Cover_Letter_Long",
                paper="letterpaper", pages=2)
    got = _run([long, "--page", "letter"], _profile(tmp_path / "two", resume_pages=2))
    assert got.returncode == 1 and "PAGES 2" in got.stdout


def test_no_pypdf_is_not_checked_never_a_finding(tmp_path):
    pdf = tmp_path / "Morgan_Ellis_CV_Larkspur.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    blocked = (f"import sys, runpy; sys.modules['pypdf'] = None; sys.argv = {[TOOL, str(pdf), '--page', 'a4']!r}; "
               f"runpy.run_path({TOOL!r}, run_name='__main__')")
    got = subprocess.run([sys.executable, "-c", blocked], capture_output=True, text=True,
                         env=dict(os.environ, LJS_PROFILE=os.path.join(ROOT, "profile.example")))
    assert got.returncode == design_check.EXIT_NO_READER == 3, got.stdout + got.stderr
    assert "NOT CHECKED" in got.stdout and "env_check.py --fix" in got.stdout
