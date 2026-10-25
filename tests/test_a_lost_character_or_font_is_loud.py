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


def _pdf_with_fonts(path, fonts):
    """A one-page PDF whose page uses `fonts`: (name, kind) with kind "embedded-cid",
    "type1-not-embedded" or "type3". The facts pdffonts printed, built with pypdf."""
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                               NameObject, NumberObject)
    w = PdfWriter()
    page = w.add_blank_page(200, 200)
    table = DictionaryObject()
    for i, (name, kind) in enumerate(fonts):
        f = DictionaryObject({NameObject("/Type"): NameObject("/Font")})
        if kind == "embedded-cid":
            prog = DecodedStreamObject()
            prog.set_data(b"font program")
            desc = DictionaryObject({NameObject("/Type"): NameObject("/FontDescriptor"),
                                     NameObject("/FontName"): NameObject("/" + name),
                                     NameObject("/FontFile3"): w._add_object(prog)})
            kid = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                    NameObject("/Subtype"): NameObject("/CIDFontType0"),
                                    NameObject("/BaseFont"): NameObject("/" + name),
                                    NameObject("/FontDescriptor"): w._add_object(desc)})
            f.update({NameObject("/Subtype"): NameObject("/Type0"),
                      NameObject("/BaseFont"): NameObject("/" + name),
                      NameObject("/DescendantFonts"): ArrayObject([w._add_object(kid)])})
        elif kind == "type1-not-embedded":
            f.update({NameObject("/Subtype"): NameObject("/Type1"),
                      NameObject("/BaseFont"): NameObject("/" + name)})
        else:
            f.update({NameObject("/Subtype"): NameObject("/Type3"),
                      NameObject("/Name"): NameObject("/" + name),
                      NameObject("/FontMatrix"): ArrayObject([NumberObject(1)] * 6)})
        table[NameObject(f"/F{i}")] = w._add_object(f)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): table})
    with open(path, "wb") as fh:
        w.write(fh)
    return str(path)


def test_a_font_left_out_or_a_bitmap_font_is_named(tmp_path):
    # Read with pypdf (tools/pdftext.py), so the check needs nothing Poppler gave.
    pdf = _pdf_with_fonts(tmp_path / "r.pdf", [("MAIKTH+LMSans10-Bold", "embedded-cid"),
                                               ("Helvetica", "type1-not-embedded"),
                                               ("T3Font_0", "type3")])
    assert F.font_problems(pdf) == [
        "the font Helvetica is not embedded in r.pdf, so the reader's machine puts another "
        "in its place",
        "the font T3Font_0 in r.pdf is a Type 3 (bitmap) font, which prints blurred and many "
        "parsers read as nothing"]
    clean = _pdf_with_fonts(tmp_path / "c.pdf", [("MAIKTH+LMSans10-Bold", "embedded-cid")])
    assert F.font_problems(clean) == []
    broken = tmp_path / "b.pdf"
    broken.write_bytes(b"%PDF-1.4\n")              # nothing can read it: no guess
    assert F.font_problems(str(broken)) == []
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


@pytest.mark.skipif(not shutil.which("lualatex"), reason="lualatex is not installed here")
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
