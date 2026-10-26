"""A resume and letter compile in the folder the renderer wrote them to.

fit_to_page compiled in the checkout's cv/ and cover_letters/ whatever LJS_STATE said,
while the renderer wrote the .tex under LJS_STATE: so with LJS_STATE set every compile
found no file ("lualatex produced no PDF"), and a check that wanted its documents kept
out of the checkout could not have them (tools/platform_check.py, 2026-10-25).
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def test_both_compiles_run_in_the_folder_the_tex_was_written_to(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_PROFILE", os.path.join(ROOT, "profile.example"))
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import fit_to_page as F
    seen = []
    # Each path as the computer names it: on Windows the stored "cv/..." joins the state
    # folder's "\\" and the folder of it comes back all "\\", one file either way.
    same = os.path.normpath
    monkeypatch.setattr(F, "_compile", lambda engine, tex, cwd, pdf, passes=1:
                        seen.append((engine, same(os.path.join(cwd, tex)), same(pdf))) or 1)
    F.compile_resume("Acme")
    F.compile_letter("Acme")
    assert seen == [("lualatex", same(docpaths.resume_tex("Acme")), same(F.resume_pdf("Acme"))),
                    ("xelatex", same(docpaths.letter_tex("Acme")), same(F.letter_pdf("Acme")))]
    assert all(path.startswith(str(tmp_path)) for _, path, _ in seen)
