"""`verify_pdf.py --dump-text` writes a resume's text only beside it, in cv/ or cover_letters/.

`.claude/settings.json` lets a chat run `python3 tools/verify_pdf.py` with any arguments
without asking, so where `--dump-text` may write is part of that permission. It wrote the
text layer to any path it was given, making the folders on the way and overwriting what was
there: a chat steered by a posting's words could overwrite a shell's start-up file or a
script the allow list runs, and nobody was asked. The same allow list let `pdftotext` run
unasked, which writes to any path too and prints any PDF on the computer. The one place the
app dumps a text layer is beside the document (apply.md, Step 5d: `cv/<Prefix>_<ABBR>_Resume.txt`),
so that is the only place it may now write. Found and fixed in ai-job-search (bc2c583).
"""
from __future__ import annotations

import json
import re
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import person  # noqa: E402
import repo_files  # noqa: E402
import security_guards  # noqa: E402
import verify_pdf as V  # noqa: E402


@pytest.fixture
def pdf(tmp_path):
    p = tmp_path / "Pat_ACME_Resume.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    with patch.object(V, "extract_text_layer", return_value=("Pat Example\nSQL\n", 1, "pypdf")):
        yield p


def _cv(*parts) -> Path:
    d = Path(person.state("cv"))
    d.mkdir(parents=True, exist_ok=True)
    return d.joinpath(*parts)


def test_the_text_is_written_beside_the_resume(pdf):
    out = _cv("Pat_ACME_Resume.txt")
    V.verify_pdf(pdf, dump_text=out)
    assert out.read_text(encoding="utf-8") == "Pat Example\nSQL\n"
    letter = Path(person.state("cover_letters", "Pat_ACME_Cover_Letter.txt"))
    V.verify_pdf(pdf, dump_text=letter)
    assert letter.is_file()


def test_a_path_anywhere_else_is_refused_and_nothing_is_made(pdf, tmp_path):
    target = tmp_path / "home" / ".bashrc.txt"
    with pytest.raises(V.VerificationError, match="cv/ or cover_letters/"):
        V.verify_pdf(pdf, dump_text=target)
    assert not target.exists() and not target.parent.exists()
    # Climbing out of cv/ is the same place as anywhere else.
    with pytest.raises(V.VerificationError, match="cv/ or cover_letters/"):
        V.verify_pdf(pdf, dump_text=_cv("..", "..", "escaped.txt"))


def test_only_a_text_file_and_never_through_a_link(pdf, tmp_path):
    with pytest.raises(V.VerificationError, match=r"\.txt"):
        V.verify_pdf(pdf, dump_text=_cv("make_me.sh"))
    outside = tmp_path / "profile_rc.txt"
    outside.write_text("kept\n", encoding="utf-8")
    link = _cv("Pat_BETA_Resume.txt")
    if link.is_symlink() or link.exists():
        link.unlink()
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("this computer makes no symbolic links")
    with pytest.raises(V.VerificationError, match="link"):
        V.verify_pdf(pdf, dump_text=link)
    assert outside.read_text(encoding="utf-8") == "kept\n"


def test_the_command_says_no_and_exits_1(pdf, tmp_path, capsys):
    target = tmp_path / "elsewhere.txt"
    assert V.main([str(pdf), "--dump-text", str(target)]) == 1
    assert "cv/ or cover_letters/" in capsys.readouterr().err
    assert not target.exists()


def test_pdftotext_is_not_run_unasked():
    allow = json.loads(Path(ROOT, ".claude", "settings.json").read_text(encoding="utf-8"))
    allow = allow["permissions"]["allow"]
    assert "Bash(pdftotext:*)" not in allow
    assert "Bash(pdftotext:*)" not in security_guards.ALLOWED_PERMISSIONS
    # verify_pdf.py, which reads a PDF with pypdf or pdftotext itself, still runs unasked.
    assert "Bash(python3 tools/verify_pdf.py:*)" in allow


def _runs_pdftotext(text: str) -> list:
    """Each place an instruction has the chat run pdftotext itself: a line of a fenced
    command block, or an inline command naming a PDF. A mention of the reader verify_pdf.py
    falls back to ("then Poppler `pdftotext`") is not one."""
    found, fenced = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced and re.search(r"\bpdftotext\b", line):
            found.append(f"{n}: {line.strip()}")
        elif re.search(r"`[^`]*\bpdftotext\s[^`]*\.pdf\b[^`]*`", line):
            found.append(f"{n}: {line.strip()}")
    return found


def test_no_instruction_has_the_chat_run_pdftotext_itself():
    """With the allowance gone, a `pdftotext` the chat runs by hand stops at a permission box
    on a person's computer. apply.md still had two: the page budget's count and a "Poppler
    fallback" that verify_pdf.py already takes itself. verify_pdf.py --dump-text does both."""
    docs = [Path(ROOT, "RUNBOOK.md"), Path(ROOT, "SETUP.md")]
    # Through repo_files: an agent's own checkout under .claude/worktrees is not this one's
    # (tests/test_repo_files.py).
    docs += repo_files.files(".claude/**/*.md", root=ROOT)
    found = {str(p.relative_to(ROOT)): hits for p in docs
             if (hits := _runs_pdftotext(p.read_text(encoding="utf-8")))}
    assert found == {}, found
    apply_md = Path(ROOT, ".claude", "commands", "apply.md").read_text(encoding="utf-8")
    assert "tools/verify_pdf.py cv/<a known one-page resume>.pdf --dump-text" in apply_md
