"""A resume and its letter take a colour the person chose for a kind of employer, and are
black whenever nothing chose one (templates/doc_style.py, the person's request of 2026-10-24).

A style changes colour and nothing else: the same words in the same places, the same pages,
the same fonts. A different font or layout broke lines differently, and with them which
bullets fit_to_page kept, so neither is a style. And every check a black document passes, a
coloured one passes too: the claims check once read the letter's font key, "Color", as a
spelling mistake.
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

import check_claims  # noqa: E402
import doc_style  # noqa: E402
import opportunity  # noqa: E402
import sector  # noqa: E402

ACCENTS = [n for n, (h, _w) in doc_style.STYLES.items() if h]


@pytest.fixture
def lists(monkeypatch):
    """Invented employers on the example person's lists, and a mapping for them."""
    monkeypatch.setattr(sector, "TECH_COMPANIES", {"quillfeather", "tidewell"})
    monkeypatch.setattr(sector, "ADJACENT_COMPANIES", {"copperleaf pay"})
    monkeypatch.setattr(sector, "NOT_TECH", {"harbourline bank": "bank",
                                             "brackenridge advisory": "professional services"})
    monkeypatch.setattr(opportunity, "YC_AND_BACKED", {"tidewell"})
    mapping = {"kinds": {"bank": "navy", "professional services": "burgundy",
                         "technology company": "slate", "startup": "teal",
                         "software product": "forest"},
               "employers": {"Larkspur Labs": "plum"}}
    real_get = doc_style.person.get

    def get(dotted, *default):
        if dotted == "documents.styles":
            return mapping
        return real_get(dotted, *default)
    monkeypatch.setattr(doc_style.person, "get", get)
    return mapping


def test_with_no_style_set_every_document_is_black_and_the_template_is_untouched():
    assert doc_style.choose({"company": "Kestrel Mutual"}) == ("black", "no style is set")
    for style in (None, "", "black"):
        assert doc_style.resume_block(style) == "" and doc_style.letter_block(style) == ""
    import resume_gen
    # The style's lines sit on a line of their own, after the template's colour lines, so
    # an empty one leaves the blank line that was always there.
    assert "\\sectionfont\\color{{color1}}#1}}}}\n{style}\n\\usepackage[utf8]" in resume_gen.RESUME_HEAD
    assert "\\usepackage{{fancyhdr}}\n{letter_style}\n\\pagestyle{{fancy}}" in resume_gen.LETTER


def test_a_rendered_draft_with_no_style_carries_no_colour_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import render_application as R
    from tests.test_the_resume_says_what_the_draft_put_on_it import DRAFT
    (tmp_path / "cv").mkdir()
    (tmp_path / "cover_letters").mkdir()
    a = json.loads(json.dumps(DRAFT))
    d = R.build(a)
    assert d["style"] == "black"
    R.resume(d)
    R.letter(d)
    tex = open(docpaths.resume_tex(d["abbr"])).read()
    letter = open(docpaths.letter_tex(d["abbr"])).read()
    assert "Style:" not in tex and "\\definecolor" not in tex and "ljsnamefont" not in tex
    assert "Style:" not in letter and "ljsaccent" not in letter


def test_each_kind_takes_its_style_from_the_lists_the_app_already_reads(lists):
    pick = lambda company: doc_style.choose({"company": company})[0]  # noqa: E731
    assert pick("Harbourline Bank") == "navy"                  # employers.py NOT_TECH: bank
    assert pick("Brackenridge Advisory LLP") == "burgundy"     # NOT_TECH: professional services
    assert pick("Quillfeather") == "slate"                     # TECH_COMPANIES
    assert pick("Copperleaf Pay") == "forest"                  # ADJACENT_COMPANIES
    # On YC_AND_BACKED and TECH_COMPANIES both: the startup is the more specific answer.
    assert doc_style.kinds_of("Tidewell") == ["startup", "technology company"]
    assert pick("Tidewell") == "teal"
    # Named by the person: beats whatever its kind would give.
    assert pick("Larkspur Labs Inc.") == "plum"
    # On no list, or no name at all: black, and the reason says so.
    assert doc_style.choose({"company": "Unlisted Widgets"}) == (
        "black", "the employer is not on a list a style is set for")
    assert pick("") == "black"


def test_a_kind_the_mapping_leaves_out_stays_black(lists):
    del lists["kinds"]["bank"]
    assert doc_style.choose({"company": "Harbourline Bank"})[0] == "black"


def test_a_drafts_own_style_wins_and_a_wrong_name_is_loud(lists):
    assert doc_style.choose({"company": "Harbourline Bank", "style": "teal"}) == (
        "teal", "this application's own choice")
    assert doc_style.choose({"company": "Harbourline Bank", "style": "black"})[0] == "black"
    with pytest.raises(ValueError, match="does not exist; the styles are black, navy"):
        doc_style.choose({"company": "Harbourline Bank", "style": "purple"})
    lists["kinds"]["bank"] = "turquoise"
    with pytest.raises(ValueError, match="documents.styles kinds 'bank'"):
        doc_style.choose({"company": "Quillfeather"})


def _grey(hexcolour):
    r, g, b = (int(hexcolour[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


@pytest.mark.parametrize("name", ACCENTS)
def test_every_accent_reads_as_text_on_white_and_prints_dark_in_black_and_white(name):
    hexcolour = doc_style.STYLES[name][0]
    # WCAG 2's line for body text, which a heading in the accent has to clear on its own.
    assert doc_style.contrast(hexcolour) >= 4.5, name
    # A black-and-white printer turns the accent into a grey; it has to stay a dark one.
    assert _grey(hexcolour) <= 120, name


@pytest.mark.parametrize("name", ACCENTS)
def test_a_style_reaches_both_generations_of_moderncv(name):
    block = doc_style.resume_block(name, "the kind 'bank' in documents.styles")
    # 2.4 and later copy the scheme's colours into names of their own when the style loads,
    # and print the name in two parts: each is set again, and the name's font takes the colour.
    for colour in ("firstnamecolor", "lastnamecolor", "namecolor", "sectioncolor",
                   "subsectioncolor", "bodyrulecolor"):
        assert "\\colorlet{%s}{color1}" % colour in block, colour
    assert "\\renewcommand*{\\namefont}{\\ljsnamefont\\color{color1}}" in block
    assert block.startswith(f"%% Style: {name}, the kind 'bank' in documents.styles.")
    letter = doc_style.letter_block(name)
    assert "\\addfontfeature{Color=%s}" % doc_style.STYLES[name][0] in letter
    assert ("hypersetup" in block) == (name == "blue")


def test_the_claims_check_reads_no_font_key_as_a_word():
    letter = doc_style.letter_block("navy")
    assert "Color" not in check_claims.strip_latex(letter)
    assert not [f for f in check_claims.check_text(letter, letter=True) if "spelling" in f[1]]


def _words(pdf):
    out = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True).stdout
    return re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">'
                      r"(.*?)</word>", out)


def _fills(pdf):
    from pypdf import PdfReader
    out = set()
    for page in PdfReader(pdf).pages:
        data = page.get_contents().get_data().decode("latin-1")
        for m in re.finditer(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+rg\b", data):
            out.add("%02X%02X%02X" % tuple(round(float(x) * 255) for x in m.groups()))
    return out


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """The test draft in every style, compiled: {style: (resume_pdf, letter_pdf)}."""
    for tool in ("lualatex", "xelatex", "pdftotext", "pdfinfo"):
        if not shutil.which(tool):
            pytest.skip(f"{tool} is not installed here")
    import docpaths
    import fit_to_page as F
    import render_application as R
    from tests.test_the_resume_says_what_the_draft_put_on_it import DRAFT
    out, before = {}, os.environ.get("LJS_STATE")
    for name in doc_style.STYLES:
        state = tmp_path_factory.mktemp(name)
        os.environ["LJS_STATE"] = str(state)
        (state / "cv").mkdir()
        (state / "cover_letters").mkdir()
        for part in ("cover.cls", "OpenFonts"):
            os.symlink(os.path.join(ROOT, "cover_letters", part), state / "cover_letters" / part)
        a = json.loads(json.dumps(DRAFT))
        a["style"], a["letter_date"] = name, "October 24, 2026"
        d = R.build(a)
        R.resume(d)
        R.letter(d)
        pdfs = []
        for engine, tex, pdf in (("lualatex", docpaths.resume_tex(d["abbr"]), docpaths.resume_pdf(d["abbr"])),
                                 ("xelatex", docpaths.letter_tex(d["abbr"]), docpaths.letter_pdf(d["abbr"]))):
            assert F._compile(engine, os.path.basename(tex), os.path.dirname(tex), pdf) == 1, name
            pdfs.append(pdf)
        out[name] = tuple(pdfs)
    if before is None:
        os.environ.pop("LJS_STATE", None)
    else:
        os.environ["LJS_STATE"] = before
    return out


@pytest.mark.parametrize("name", ACCENTS)
def test_a_style_moves_no_word_and_adds_only_its_own_colour(rendered, name):
    black_resume, black_letter = rendered["black"]
    resume, letter = rendered[name]
    assert _words(resume) == _words(black_resume) and _words(resume)
    assert _words(letter) == _words(black_letter) and _words(letter)
    accent = doc_style.STYLES[name][0]
    links = {"0000FF"} if name == "blue" else set()
    assert _fills(resume) == {"000000", accent} | links
    # The letter keeps its grey contact line; its name and bullet marks take the accent.
    assert _fills(black_letter) - {"000000"} == {"2B2B2B", "6A6A6A"}
    assert _fills(letter) - {"000000"} == {accent, "6A6A6A"}
    for pdf, black in ((resume, black_resume), (letter, black_letter)):
        fonts = lambda p: sorted(re.sub(r"^[A-Z]{6}\+", "", ln.split()[0]) for ln in  # noqa: E731
                                 subprocess.run(["pdffonts", p], capture_output=True,
                                                text=True).stdout.splitlines()[2:] if ln.strip())
        assert fonts(pdf) == fonts(black)
