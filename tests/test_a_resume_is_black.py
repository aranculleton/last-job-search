"""Every resume's text is black: the name, the section titles, the rule under the name, the
contact line, the links and the bullet marks (the person's request of 2026-10-24).

The template took moderncv's blue scheme, which coloured the name, the headings and the
bullet marks blue and the contact line grey. Black changes only colour: on six real
resumes the words sat in exactly the same places before and after, with the same pages
and fonts. A colour is a choice per job type, never the default.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools"), os.path.join(ROOT, "templates")]

import resume_gen  # noqa: E402


def test_the_template_takes_the_black_scheme_and_black_links():
    head = resume_gen.RESUME_HEAD
    assert "\\moderncvcolor{{black}}" in head and "\\moderncvcolor{{blue}}" not in head
    assert "linkcolor=black, filecolor=black, urlcolor=black" in head
    assert not re.search(r"(?:link|file|url)color=(?!black)", head)
    # The ATS fixes stay: the zero-width rule under the name, the text bullet, no icons.
    assert "\\rule[-0.42em]{{0pt}}{{0pt}}" in head and "\\textbullet" in head
    assert "\\renewcommand*{{\\emailsymbol}}{{}}" in head


def _colours(pdf):
    """Every colour a page's drawing sets, as (r, g, b), from its content stream."""
    from pypdf import PdfReader
    out = set()
    for page in PdfReader(pdf).pages:
        data = page.get_contents().get_data().decode("latin-1")
        for m in re.finditer(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(?:rg|RG)\b", data):
            out.add(tuple(round(float(x), 2) for x in m.groups()))
        for m in re.finditer(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(?:k|K)\b", data):
            c, mg, y, _k = (float(x) for x in m.groups())
            out.add((round(1 - c, 2), round(1 - mg, 2), round(1 - y, 2)))
    return out


@pytest.mark.skipif(not shutil.which("lualatex"), reason="lualatex is not installed here")
def test_a_real_render_draws_nothing_in_colour(tmp_path, monkeypatch):
    pytest.importorskip("pypdf")
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import fit_to_page as F
    import render_application as R
    from tests.test_the_resume_says_what_the_draft_put_on_it import DRAFT
    (tmp_path / "cv").mkdir()
    a = json.loads(json.dumps(DRAFT))
    R.resume(R.build(a))
    tex, pdf = docpaths.resume_tex(a["abbr"]), docpaths.resume_pdf(a["abbr"])
    F._compile("lualatex", os.path.basename(tex), os.path.dirname(tex), pdf)
    coloured = {c for c in _colours(pdf) if max(c) - min(c) > 0.01}
    assert coloured == set(), coloured
