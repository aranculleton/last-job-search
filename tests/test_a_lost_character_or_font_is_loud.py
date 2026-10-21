"""A character the font cannot print, or a font left out of the PDF, stops the render.

`_compile` caught a font file it could not load, but not a character the font lacks: LaTeX
leaves the character out, writes a valid one-page PDF and says so only in its log, so an
accented surname or a symbol in a figure lost a letter and every check passed. Nor did
anything ask whether the fonts were in the file at all. The compile now reads its log for
"Missing character", and the finished resume and letter are read with pdffonts for a font
that is not embedded or is a Type 3 (bitmap) font. Each is said in plain words.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import fit_to_page as F  # noqa: E402

LOG = ("This is LuaHBTeX\n"
       "Missing character: There is no \u65e5 (U+65E5) in font [lmroman10-regular]:+tlig;!\n"
       "Missing character: There is no \u2713 (U+2713) in font [lmroman10-regular]:+tlig;!\n"
       "Missing character: There is no \u65e5 (U+65E5) in font [lmroman10-regular]:+tlig;!\n")


class _Result:
    returncode, stdout, stderr = 0, b"", b""


def test_the_log_names_each_character_once():
    assert F.missing_characters(LOG) == ["\u65e5 (U+65E5) in lmroman10-regular",
                                         "\u2713 (U+2713) in lmroman10-regular"]
    assert F.missing_characters("Output written on x.pdf (1 page).") == []


def test_a_compile_that_lost_characters_fails_and_says_which(tmp_path):
    pdf = tmp_path / "x.pdf"

    def fake(cmd, cwd=None, capture_output=False, **kw):
        pdf.write_bytes(b"%PDF-1.4\n")
        (tmp_path / "x.log").write_text(LOG, encoding="utf-8")
        return _Result()
    with mock.patch.object(F.subprocess, "run", side_effect=fake), \
            mock.patch.object(F, "_pages", return_value=1):
        with pytest.raises(F.CompileFailed) as caught:
            F._compile("lualatex", "x.tex", str(tmp_path), str(pdf))
    said = str(caught.value)
    assert said.startswith("lualatex could not print 2 character(s) in x.pdf, because its font "
                           "does not have them: \u65e5 (U+65E5) in lmroman10-regular")
    assert "The PDF leaves them out" in said


def _fonts(stdout, returncode=0):
    def fake(cmd, **kw):
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")
    return mock.patch.object(F.subprocess, "run", side_effect=fake)


PDFFONTS = """name                                 type              encoding         emb sub uni object ID
------------------------------------ ----------------- ---------------- --- --- --- ---------
MAIKTH+LMSans10-Bold                 CID Type 0C       Identity-H       yes yes yes     36  0
Helvetica                            Type 1            WinAnsi          no  no  no      12  0
T3Font_0                             Type 3            Custom           yes no  no      14  0
"""


def test_a_font_left_out_or_a_bitmap_font_is_named(tmp_path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    with _fonts(PDFFONTS):
        assert F.font_problems(str(pdf)) == [
            "the font Helvetica is not embedded in r.pdf, so the reader's machine puts another "
            "in its place",
            "the font T3Font_0 in r.pdf is a Type 3 (bitmap) font, which prints blurred and many "
            "parsers read as nothing"]
    with _fonts(PDFFONTS.split("Helvetica")[0]):
        assert F.font_problems(str(pdf)) == []
    with _fonts("", returncode=1):               # pdffonts could not read it: no guess
        assert F.font_problems(str(pdf)) == []
    assert F.font_problems(str(tmp_path / "none.pdf")) == []


def test_a_finished_render_with_a_font_left_out_stops(monkeypatch):
    a = {"company": "Wrenfield Freight Ltd", "role": "Analyst", "posting": "",
         "jobs": [{"employer": "Brindle & Hart Logistics", "bullets": ["BH_FORECAST", "BH_PIPE"]}],
         "summary": "Operations analyst.", "tools": "Python", "p1": "a", "p2": "b",
         "lead": "c", "cl_bullets": [], "p4": "d"}
    monkeypatch.setattr(F, "_render_resume", lambda a: 1)
    monkeypatch.setattr(F, "_render_letter", lambda a: 1)
    monkeypatch.setattr(F, "compile_resume", lambda abbr, passes=1: 1)
    monkeypatch.setattr(F, "grow_resume", lambda *a, **k: None)
    monkeypatch.setattr(F, "font_problems", lambda pdf: ["the font Helvetica is not embedded"]
                        if pdf.endswith(".pdf") and "Cover" not in pdf else [])
    with pytest.raises(F.CompileFailed, match="the font Helvetica is not embedded. Use fonts"):
        F.fit(a)


@pytest.mark.skipif(not (shutil.which("lualatex") and shutil.which("pdffonts")),
                    reason="lualatex and Poppler are not installed here")
def test_a_real_compile_of_a_character_the_font_lacks_fails(tmp_path):
    (tmp_path / "t.tex").write_text("\\documentclass{article}\n\\begin{document}\n"
                                    "Ellis \u2713 forecast\n\\end{document}\n", encoding="utf-8")
    with pytest.raises(F.CompileFailed, match=r"\u2713 \(U\+2713\)"):
        F._compile("lualatex", "t.tex", str(tmp_path), str(tmp_path / "t.pdf"))
    (tmp_path / "t.tex").write_text("\\documentclass{article}\n\\begin{document}\n"
                                    "Ellis forecast\n\\end{document}\n", encoding="utf-8")
    assert F._compile("lualatex", "t.tex", str(tmp_path), str(tmp_path / "t.pdf")) == 1
    assert F.font_problems(str(tmp_path / "t.pdf")) == []
    assert os.path.exists(tmp_path / "t.pdf")
