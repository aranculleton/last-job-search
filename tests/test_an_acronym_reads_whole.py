"""A word on the resume reads back as one word, however its letters are kerned.

pypdf reads any gap inside a run of glyphs of nearly a space's width as a space, and a kern
pair is such a gap: the summary of a resume said "production pipelines on Azure and A WS",
while the bullets, which patched "AWS" word by word, read it whole (2026-11-10). Under
Liberation Serif "WAV", "VAT" and "Vancouver" split too. An applicant tracking system
searching for the word does not find it, and the round trip, which drops every space before
it compares, passed it. Every font is now set with no kerning, and the round trip names a
word the text layer holds with a space inside it. The application is invented; the
candidate is the example person.
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

import verify_pdf as V  # noqa: E402
from tests.test_the_resume_says_what_the_draft_put_on_it import DRAFT, _page  # noqa: E402

KERNED = ("AWS", "AVL", "WAV", "VAT", "LTV", "YAML", "Vancouver", "Tyneside")
SUMMARY = ("Operations analyst with seven years turning warehouse and supplier data into "
           "forecasts and shipping them as production pipelines on Azure and AWS, with AVL, "
           "WAV, VAT, LTV and YAML work for clients from Vancouver to Tyneside. Most recently "
           "cut forecast error from 22% to 14% across 2,400 SKUs at Brindle & Hart Logistics.")


def _draft():
    a = json.loads(json.dumps(DRAFT))
    a["summary"] = SUMMARY
    return a


def test_a_word_read_with_a_space_inside_it_is_named():
    groups = V.roundtrip_fields(_draft())
    page = _page(groups)
    assert V.roundtrip(groups, page) == []
    [why] = V.roundtrip(groups, page.replace("Azure and AWS", "Azure and A WS"))
    assert why.startswith('split: Profile (the summary): "AWS" reads as "A WS"'), why


def test_a_space_the_draft_itself_has_is_not_a_split():
    # "in to" is two words in the draft as well as on the page; "into" elsewhere in the same
    # draft is not split by it. A hyphen at a line break is not a space either.
    a = _draft()
    a["summary"] = SUMMARY.replace("turning", "logging in to systems and turning") + \
        " Turned data into forecasts."
    groups = V.roundtrip_fields(a)
    page = _page(groups).replace("warehouse", "ware-\nhouse")
    assert V.roundtrip(groups, page) == []


@pytest.mark.skipif(not (shutil.which("lualatex") and shutil.which("xelatex")),
                    reason="LuaLaTeX and XeLaTeX are not installed here")
@pytest.mark.parametrize("design", [None, "classic", "modern", "compact", "spacious"])
def test_every_design_reads_kerned_words_whole(tmp_path, monkeypatch, design):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import fit_to_page as F
    import render_application as R
    import doc_design
    PdfReader = pytest.importorskip("pypdf").PdfReader
    assert design is None or design in doc_design.DESIGNS
    (tmp_path / "cv").mkdir()
    a = _draft()
    if design:
        a["design"] = design
    b = R.build(a)
    R.resume(b)
    F.compile_resume(b["abbr"])
    pdf = docpaths.resume_pdf(b["abbr"])
    text = " ".join("".join(p.extract_text() for p in PdfReader(pdf).pages).split())
    for word in KERNED:
        assert re.search(r"\b%s\b" % word, text), (design, word)
    assert "Azure and AWS" in text, text[:400]
    found = V.roundtrip(V.roundtrip_fields(a), text)
    assert not [f for f in found if f.startswith("split:")], found


# --- the cover letter ---------------------------------------------------------------------

LETTER_WORDS = ("AWS", "AVL", "WAV", "VAT", "YAML", "LTV", "Vancouver", "Tyneside")


def _letter_draft():
    a = _draft()
    a["p1"] = "At Brindle & Hart I forecast by depot on Azure and AWS with AVL and WAV data."
    a["p2"] = "Wrenfield moves goods; VAT, YAML and LTV work from Vancouver to Tyneside."
    a["cl_bullets"] = [{"label": "Forecasting", "text": "Weekly models on AWS by depot."}]
    return a


def test_a_letter_word_read_with_a_space_inside_it_is_named():
    a = _letter_draft()
    page = "\n".join(f for _l, fs in V.letter_fields(a) for _w, f in fs)
    assert V.letter_splits(a, page) == []
    [why] = V.letter_splits(a, page.replace("and LTV", "and L TV"))
    assert why == 'split: the letter\'s second paragraph: "LTV" reads as "L TV" in the text layer'


@pytest.mark.skipif(not shutil.which("xelatex"), reason="XeLaTeX is not installed here")
@pytest.mark.parametrize("design", [None, "classic", "modern"])
def test_the_letter_reads_kerned_words_whole(tmp_path, monkeypatch, design):
    # The template's letter read "L TV" in Raleway (2026-11-10): cover.cls sets every font it
    # loads with no kerning, as the resume's are.
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import fit_to_page as F
    import render_application as R
    PdfReader = pytest.importorskip("pypdf").PdfReader
    for d in ("cv", "cover_letters"):
        (tmp_path / d).mkdir()
    for f in ("OpenFonts", "cover.cls"):
        os.symlink(os.path.join(ROOT, "cover_letters", f), tmp_path / "cover_letters" / f)
    a = _letter_draft()
    if design:
        a["design"] = design
    b = R.build(a)
    R.gen.letter(b)
    F.compile_letter(b["abbr"])
    text = " ".join("".join(p.extract_text() for p in
                            PdfReader(docpaths.letter_pdf(b["abbr"])).pages).split())
    for word in LETTER_WORDS:
        assert re.search(r"\b%s\b" % word, text), (design, word, text)
    assert V.letter_splits(a, text) == []
