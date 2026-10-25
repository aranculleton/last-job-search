"""The name and the city under it are two lines to a text extractor, on every moderncv.

The template's rule under the name only runs through \\namestyle, which moderncv 2.4 and
later no longer call: they print the name through \\firstnamestyle and \\lastnamestyle.
There, under a name with no descenders, `pdftotext -layout` read the name and the city as
one word on every resume made with a current TeX install, a Mac's included (2026-10-24).
pypdf read them apart, so the text-layer check passed it. The name is drawn higher there
instead, its box unchanged, so nothing else on the page moves. Every name here is invented.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools"), os.path.join(ROOT, "templates")]

import resume_gen  # noqa: E402


def test_the_newer_name_commands_draw_the_name_higher_and_keep_its_box():
    head = resume_gen.RESUME_HEAD
    # 2.3 keeps the rule it always had, and its output is untouched: neither command exists
    # there, so the redefinitions sit behind \ifdefined.
    assert "\\rule[-0.42em]{{0pt}}{{0pt}}" in head
    guard = head.index("\\ifdefined\\lastnamestyle")
    block = head[guard:head.index("\\fi\n", guard)]
    for which in ("firstname", "lastname"):
        line = next(ln for ln in block.splitlines() if f"{{\\{which}style}}" in ln)
        # Raised with its own height and depth kept, so the line it sits in is unchanged.
        assert "\\raisebox{{9.5pt}}[\\height][\\depth]" in line, line
        assert f"\\textcolor{{{{{which}color}}}}" in line and "\\namefont" in line, line


def _poppler() -> bool:
    """Poppler's pdftotext, whose -bbox and -layout the case was found with. Another one can
    be first on PATH (Git for Windows carries a pdftotext of its own) and print no boxes."""
    exe = shutil.which("pdftotext")
    if not exe:
        return False
    r = subprocess.run([exe, "-v"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return "poppler" in (r.stdout + r.stderr).lower()


@pytest.mark.skipif(not (shutil.which("lualatex") and _poppler()),
                    reason="lualatex or Poppler's pdftotext is not installed here")
def test_a_name_with_no_descenders_is_its_own_line(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import fit_to_page as F
    import render_application as R
    from tests.test_the_resume_says_what_the_draft_put_on_it import DRAFT
    (tmp_path / "cv").mkdir()
    a = json.loads(json.dumps(DRAFT))
    R.resume(R.build(a))
    tex, pdf = docpaths.resume_tex(a["abbr"]), docpaths.resume_pdf(a["abbr"])
    with open(tex, encoding="utf-8") as fh:
        src = fh.read()
    # A name with no descenders, the case that ran together.
    src, n = re.subn(r"\\name\{[^}]*\}\{[^}]*\}", r"\\name{Idris}{Corrie}", src)
    assert n == 1
    with open(tex, "w", encoding="utf-8") as fh:
        fh.write(src)
    F._compile("lualatex", os.path.basename(tex), os.path.dirname(tex), pdf)
    # What every extractor's line grouping rests on: the name's boxes and the city's must
    # not overlap. Whether pdftotext then runs the two together also depends on the columns
    # of the lines below, so the overlap is the test, not one extractor's verdict.
    box = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True,
                         encoding="utf-8").stdout
    words = re.findall(r'yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)">([^<]*)<', box)
    assert [w[2] for w in words[:2]] == ["Idris", "Corrie"], words[:3]
    name_bottom = max(float(w[1]) for w in words[:2])
    city_top = float(words[2][0])
    assert name_bottom <= city_top, (words[:3], name_bottom, city_top)
    text = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", pdf, "-"],
                          capture_output=True, text=True, encoding="utf-8").stdout
    lines = [" ".join(ln.split()) for ln in text.splitlines() if ln.strip()]
    assert lines[0] == "Idris Corrie", lines[:2]
