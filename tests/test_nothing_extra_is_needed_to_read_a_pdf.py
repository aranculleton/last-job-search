"""A PDF is read with the app's own Python packages: no Poppler, on any computer.

fit_to_page.py, verify_batch and audit_letters read every PDF with Poppler (pdfinfo,
pdftotext, pdffonts), a system package a Mac has only through Homebrew and Windows only
through winget. Without it fit_to_page stopped on a traceback and the batch check
flagged documents that were fine (2026-10-25). tools/pdftext.py reads the same three
things with pypdf; Poppler is used only where it is there and pypdf cannot run at all.
The documents here are built in the test, and every name in them is invented.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pdftext  # noqa: E402

pypdf = pytest.importorskip("pypdf")


def _pdf(path, words="Morgan Ellis forecasts depot demand", pages=1):
    """A PDF whose pages say `words` in Helvetica, built with pypdf alone."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    w = PdfWriter()
    font = w._add_object(DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                           NameObject("/Subtype"): NameObject("/Type1"),
                                           NameObject("/BaseFont"): NameObject("/Helvetica")}))
    for _ in range(pages):
        page = w.add_blank_page(300, 200)
        body = DecodedStreamObject()
        body.set_data(f"BT /F1 12 Tf 20 100 Td ({words}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = w._add_object(body)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    with open(path, "wb") as fh:
        w.write(fh)
    return str(path)


@pytest.fixture
def no_poppler(monkeypatch):
    """No pdftotext, pdfinfo or pdffonts anywhere this process looks."""
    real = pdftext.shutil.which
    monkeypatch.setattr(pdftext.shutil, "which",
                        lambda name, *a, **k: None if name.startswith("pdf") else real(name))


def test_pages_text_and_fonts_are_read_with_no_poppler(tmp_path, no_poppler):
    pdf = _pdf(tmp_path / "Morgan_Ellis_CV_Acme.pdf", pages=2)
    assert pdftext.pages(pdf) == 2
    assert pdftext.reader() == "pypdf"
    assert "Morgan Ellis forecasts depot demand" in pdftext.text(pdf)
    assert pdftext.fonts(pdf) == [{"name": "Helvetica", "type": "Type1", "embedded": False}]
    # Unreadable is said, never guessed: no count for a file that is not a PDF.
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    assert pdftext.pages(str(bad)) is None
    assert pdftext.pages(str(tmp_path / "none.pdf")) is None
    with pytest.raises(pdftext.Unreadable):
        pdftext.text(str(tmp_path / "none.pdf"))


def test_with_neither_reader_it_says_what_installs_one(tmp_path, monkeypatch, no_poppler):
    pdf = _pdf(tmp_path / "r.pdf")
    monkeypatch.setattr(pdftext, "_pypdf", lambda: None)
    assert pdftext.reader() == ""
    with pytest.raises(pdftext.Unreadable, match=r"env_check\.py --fix"):
        pdftext.text(pdf)


@pytest.mark.skipif(not pdftext.shutil.which("pdftotext"), reason="Poppler is not here")
def test_where_pypdf_cannot_run_poppler_still_reads(tmp_path, monkeypatch):
    pdf = _pdf(tmp_path / "r.pdf")
    monkeypatch.setattr(pdftext, "_pypdf", lambda: None)
    assert pdftext.reader() == "pdftotext"
    assert "Morgan Ellis" in pdftext.text(pdf) and pdftext.pages(pdf) == 1
    # Git for Windows brings pdftotext and no pdfinfo: the pages are still counted.
    which = pdftext.shutil.which
    monkeypatch.setattr(pdftext.shutil, "which", lambda n, *a, **k: None if n == "pdfinfo"
                        else which(n, *a, **k))
    two = _pdf(tmp_path / "two.pdf", pages=2)
    got = pdftext.pages(two)
    if got != 2:
        # What pdftotext itself said of both files, and whether a pdfinfo counted the first,
        # so a failure on a computer this cannot be run on says why (on Windows, in cp1252
        # under a folder named with "ë", it came back None, 2026-10-25).
        exe = which("pdftotext")
        said = []
        for f in (pdf, two):
            ran = subprocess.run([exe, "-layout", "-enc", "UTF-8", f, "-"], capture_output=True)
            feeds = ran.stdout.count(b"\f")         # outside the f-string: 3.9 allows no \ there
            err = ran.stderr.decode("utf-8", "replace")[:300]
            said.append(f"{os.path.basename(f)}: exit {ran.returncode}, {feeds} form feed(s), "
                        f"{len(ran.stdout)} bytes, stderr {err!r}")
        raise AssertionError(f"pages {got!r} from {exe} (pdfinfo: {which('pdfinfo')}); "
                             + "; ".join(said))
    assert pdftext.pages(pdf) == 1


@pytest.mark.skipif(not pdftext.shutil.which("pdftotext"), reason="Poppler is not here")
def test_a_pdfinfo_that_cannot_open_the_file_leaves_the_count_to_pdftotext(tmp_path, monkeypatch):
    """On Windows, under a user folder with an accent, a pdfinfo gave no count for a file
    pdftotext read (2026-10-25): the pages are counted from pdftotext's form feeds."""
    pdf = _pdf(tmp_path / "two.pdf", pages=2)
    monkeypatch.setattr(pdftext, "_pypdf", lambda: None)
    which, run = pdftext.shutil.which, pdftext.subprocess.run
    monkeypatch.setattr(pdftext.shutil, "which",
                        lambda n, *a, **k: "pdfinfo" if n == "pdfinfo" else which(n, *a, **k))

    def ran(cmd, *a, **k):
        if cmd[0] == "pdfinfo":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="Couldn't open file")
        return run(cmd, *a, **k)
    monkeypatch.setattr(pdftext.subprocess, "run", ran)
    assert pdftext.pages(pdf) == 2


def test_the_page_checks_use_it(tmp_path, no_poppler):
    import fit_to_page as F
    pdf = _pdf(tmp_path / "r.pdf", pages=2)
    assert F._pages(pdf) == 2 and F._lines(pdf) == 2
    assert F._pages(str(tmp_path / "none.pdf")) == 9       # unreadable reads as too long
    assert F.font_problems(pdf) == [
        "the font Helvetica is not embedded in r.pdf, so the reader's machine puts another "
        "in its place"]
    for name in ("fit_to_page.py", "audit_letters.py", "verify_batch.py"):
        with open(os.path.join(ROOT, "tools", name), encoding="utf-8") as fh:
            src = fh.read()
        # No command they run starts with a Poppler tool.
        assert not re.search(r'\[\s*"(pdfinfo|pdftotext|pdffonts)"', src), name


def test_a_compile_that_never_ends_is_stopped_and_said(tmp_path, monkeypatch):
    import fit_to_page as F

    def hangs(cmd, **kw):
        assert kw.get("timeout") == F.COMPILE_TIMEOUT and kw.get("stdin") is subprocess.DEVNULL
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(F.subprocess, "run", hangs)
    with pytest.raises(F.CompileFailed, match=r"still running .* after 5 minutes.*--fix"):
        F._compile("lualatex", "t.tex", str(tmp_path), str(tmp_path / "t.pdf"))

    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])
    monkeypatch.setattr(F.subprocess, "run", missing)
    with pytest.raises(F.CompileFailed, match=r"lualatex is not on this computer.*--fix"):
        F._compile("lualatex", "t.tex", str(tmp_path), str(tmp_path / "t.pdf"))


def test_the_letter_audit_reads_the_letter_with_it(tmp_path, monkeypatch, no_poppler):
    import audit_letters as AU
    pdf = _pdf(tmp_path / "Morgan_Ellis_Cover_Letter_Acme.pdf", "Dear Acme hiring team")
    monkeypatch.setattr(AU.docpaths, "letter_pdf", lambda abbr: pdf)
    assert "Dear Acme hiring team" in AU.pdf_text("Acme")
    monkeypatch.setattr(AU.docpaths, "letter_pdf", lambda abbr: str(tmp_path / "none.pdf"))
    with pytest.raises(FileNotFoundError):
        AU.pdf_text("Acme")
