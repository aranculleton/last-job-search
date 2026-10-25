"""A compile that reported an error is never a clean fit, even when LaTeX wrote a PDF.

LaTeX recovers from most errors and writes a page anyway: "! Missing $ inserted" printed an
email address without its underscore, "! Paragraph ended before \\extrainfo was complete"
dropped two contact lines, and tools/fit_to_page.py reported each as one clean page,
because it failed only when no PDF came out, a font was missing or a character was lost.

The documents here are invented.
"""
from __future__ import annotations

import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import fit_to_page as F  # noqa: E402


def test_every_error_line_is_named_once():
    log = ("This is LuaHBTeX\n! Missing $ inserted.\n<inserted text>\n! Missing $ inserted.\n"
           "LaTeX Warning: Reference undefined\n! Paragraph ended before \\extrainfo was "
           "complete.\n")
    assert F.latex_errors(log) == ["! Missing $ inserted.",
                                   "! Paragraph ended before \\extrainfo was complete."]
    assert F.latex_errors("LaTeX Warning: nothing wrong\nOutput written") == []


needs_tex = pytest.mark.skipif(not shutil.which("lualatex"), reason="lualatex is not installed")


@needs_tex
def test_a_recovered_error_stops_the_fit(tmp_path):
    good = tmp_path / "good.tex"
    good.write_text("\\documentclass{article}\\begin{document}Plain words.\\end{document}\n",
                    encoding="utf-8")
    assert F._compile("lualatex", "good.tex", str(tmp_path), str(tmp_path / "good.pdf")) == 1
    bad = tmp_path / "bad.tex"
    bad.write_text("\\documentclass{article}\\begin{document}morgan_ellis@example.com"
                   "\\end{document}\n", encoding="utf-8")
    with pytest.raises(F.CompileFailed) as exc:
        F._compile("lualatex", "bad.tex", str(tmp_path), str(tmp_path / "bad.pdf"))
    assert os.path.exists(tmp_path / "bad.pdf")       # LaTeX wrote one all the same
    assert "! Missing $ inserted" in str(exc.value)
    assert "wrote a PDF anyway" in str(exc.value)
