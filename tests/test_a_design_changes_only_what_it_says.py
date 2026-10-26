"""A resume and its letter take the layout the person, their market or the kind of employer
chose: the fonts, sizes, margins, spacing and where the name and dates sit
(templates/doc_design.py, the maintainer's request of 2026-10-25). And a person nobody chose
a design for gets exactly the page they always had: every setting starts unset, and unset is
the template's own text.

A design is only offered if it survives what an applicant tracking system does to a PDF:
one page, no text under the size guides ask for, nothing in the margins where parsers drop
headers and footers, one column, and every word read back with its spaces in every pypdf
the app allows (tools/design_check.py). Those renders run where TeX is installed; the rules
and the resolution run everywhere.

The application is invented (tests/fixtures/design_draft.json); the candidate is the example
person.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools"), os.path.join(ROOT, "templates")]

import doc_design  # noqa: E402
import doc_style  # noqa: E402
import opportunity  # noqa: E402
import sector  # noqa: E402

with open(os.path.join(ROOT, "tests", "fixtures", "design_draft.json"), encoding="utf-8") as _fh:
    DRAFT = json.load(_fh)
NAMED = [n for n in doc_design.DESIGNS if n != doc_design.DEFAULT]


@pytest.fixture
def setting(monkeypatch):
    """person.json documents.design and documents.designs, set per test."""
    monkeypatch.setattr(sector, "TECH_COMPANIES", {"quillfeather"})
    monkeypatch.setattr(sector, "ADJACENT_COMPANIES", set())
    monkeypatch.setattr(sector, "NOT_TECH", {"harbourline bank": "bank"})
    monkeypatch.setattr(opportunity, "YC_AND_BACKED", set())
    values = {"documents.designs": None, "documents.design": None}
    real_get = doc_design.person.get

    def get(dotted, *default):
        if dotted in values:
            return values[dotted]
        return real_get(dotted, *default)
    monkeypatch.setattr(doc_design.person, "get", get)
    return values


# --- nothing chosen: the template, exactly -------------------------------------------------

def test_with_nothing_chosen_every_piece_is_the_templates_own_text(setting):
    vals, name, why = doc_design.choose({"company": "Harbourline Bank"})
    assert name == "standard" and doc_design.is_template(vals) and why == "no design is set"
    parts = doc_design.resume_parts(vals, {"header_rows": [], "name": "x"}, ROOT)
    # The strings the template carried before designs existed.
    assert parts["body_size"] == "11" and parts["geometry"] == "scale=0.885"
    assert parts["name_font"] == "\\fontsize{30}{32}\\bfseries\\upshape"
    assert parts["title"] == "\\makecvtitle" and parts["after_title"] == "\\vspace{-22pt}"
    assert parts["design"] == parts["item_start"] == parts["para_start"] == ""
    assert parts["engine"] == "lualatex"
    letter = doc_design.letter_parts(vals, {}, ROOT)
    assert letter["letter_design"] == ""
    assert letter["list_font"] == ("\\raggedright\\fontspec[Path = OpenFonts/fonts/raleway/]"
                                   "{Raleway-Medium}\\fontsize{11pt}{13pt}\\selectfont")


def test_a_rendered_draft_with_no_design_is_the_template(tmp_path, monkeypatch, setting):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import render_application as R
    (tmp_path / "cv").mkdir()
    (tmp_path / "cover_letters").mkdir()
    d = R.build(copy.deepcopy(DRAFT))
    R.resume(d)
    R.letter(d)
    tex = open(docpaths.resume_tex(d["abbr"]), encoding="utf-8").read()
    letter = open(docpaths.letter_tex(d["abbr"]), encoding="utf-8").read()
    for line in ("%% Compile with: lualatex ", "\\documentclass[11pt,", "\\makecvtitle\n",
                 "\\vspace{-22pt}\n", "\\usepackage[scale=0.885]{geometry}",
                 "\\renewcommand*{\\namefont}{\\fontsize{30}{32}\\bfseries\\upshape}",
                 "\\begin{itemize}\n", "\\vspace{1pt}\n\\small{"):
        assert line in tex, line
    assert "Design:" not in tex and "ljsheader" not in tex and "%ITEMSTART%" not in tex
    assert "Design:" not in letter and "ljsletterfont" not in letter
    assert ("{\\raggedright\\fontspec[Path = OpenFonts/fonts/raleway/]{Raleway-Medium}"
            "\\fontsize{11pt}{13pt}\\selectfont\n\\begin{itemize}") in letter


# --- who decides, most specific first --------------------------------------------------------

def test_each_level_overrides_the_one_before(setting):
    setting["documents.designs"] = {"kinds": {"bank": "classic", "technology company": "modern"},
                                    "employers": {"Larkspur Labs": "spacious"}}
    pick = lambda company, **d: doc_design.choose(dict(company=company, **d))  # noqa: E731
    assert pick("Harbourline Bank")[1] == "classic"
    assert pick("Quillfeather")[1] == "modern"
    assert pick("Larkspur Labs Ltd")[1] == "spacious"            # the employer beats its kind
    assert pick("Unlisted Widgets")[1] == "standard"
    # The person's own settings change only themselves, over what the kind gave.
    setting["documents.design"] = {"body_size": 12}
    vals, name, why = pick("Harbourline Bank")
    assert name == "classic" and vals["body_size"] == 12 and vals["body_font"] == "liberation-serif"
    assert "documents.design changes body_size" in why
    # The person naming a design replaces the kind's.
    setting["documents.design"] = "compact"
    assert pick("Harbourline Bank")[1] == "compact"
    # One application's own design wins over everything.
    vals, name, _why = pick("Harbourline Bank", design={"name": "modern", "header_align": "right"})
    assert name == "modern" and vals["header_align"] == "right" and vals["body_font"] == "lato"


def test_a_wrong_name_or_value_is_loud(setting):
    with pytest.raises(ValueError, match="names the design 'fancy'"):
        doc_design.choose({"company": "x", "design": "fancy"})
    with pytest.raises(ValueError, match="body_size must be one of 11, 12"):
        doc_design.choose({"company": "x", "design": {"body_size": 10}})
    with pytest.raises(ValueError, match="margin_mm 5 is outside"):
        doc_design.choose({"company": "x", "design": {"margin_mm": 5}})
    with pytest.raises(ValueError, match="setting 'colour'"):
        doc_design.choose({"company": "x", "design": {"colour": "navy"}})
    setting["documents.designs"] = {"kinds": {"bank": "glossy"}}
    with pytest.raises(ValueError, match="documents.designs kinds 'bank'"):
        doc_design.choose({"company": "Harbourline Bank"})


def test_every_named_design_is_complete_and_inside_its_bounds():
    for name in NAMED:
        vals = doc_design.values_of(name)
        assert all(vals[k] is not None for k in doc_design.SETTINGS if k != "page"), name
        for k, v in vals.items():
            assert doc_design.check_value(k, v) == v or v is None, (name, k)
    assert set(doc_design.SUGGESTED_KINDS.values()) <= set(doc_design.DESIGNS)


def test_a_design_is_made_smaller_one_bounded_step_at_a_time():
    assert doc_design.step_down(dict.fromkeys(doc_design.SETTINGS)) is None
    v = doc_design.values_of("spacious")
    seen = [v]
    while True:
        nxt = doc_design.step_down(seen[-1])
        if nxt is None:
            break
        seen.append(nxt)
    last = seen[-1]
    assert last["line_spread"] == 1.0 and last["margin_mm"] == 12.0 and last["body_size"] == 11
    assert last["name_size"] == 20.0 and last["section_size"] == 11.0
    # Spacing goes first, then the margins, then the sizes.
    assert seen[1]["line_spread"] < v["line_spread"] and seen[1]["margin_mm"] == v["margin_mm"]
    # fit_to_page asks for steps through the draft, and each is applied in turn.
    vals, _n, why = doc_design.choose({"company": "x", "design": "spacious", "design_step": 2})
    assert vals == seen[2] and why.endswith("made smaller to fit the page")


def test_a_reaction_changes_its_setting_and_never_passes_a_bound():
    base = doc_design.values_of("classic")
    assert doc_design.adjusted(base, "bigger")["body_size"] == 12
    assert doc_design.adjusted(doc_design.adjusted(base, "bigger"), "bigger")["body_size"] == 12
    assert doc_design.adjusted(base, "smaller")["body_size"] == 11
    tight = base
    for _ in range(9):
        tight = doc_design.adjusted(tight, "tighter")
    assert tight["margin_mm"] == 12.0
    assert doc_design.adjusted(base, "name-left")["header_align"] == "left"
    sans = doc_design.adjusted(base, "sans")
    assert sans["body_font"] == sans["heading_font"] == "lato"
    with pytest.raises(ValueError, match="not a change this knows"):
        doc_design.adjusted(base, "sparkly")


def test_the_command_writes_the_choice_where_the_tools_read_it(tmp_path, monkeypatch):
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof)
    monkeypatch.setenv("LJS_PROFILE", str(prof))
    doc_design.person.reset()
    try:
        assert doc_design.main(["adjust", "bigger"]) == 0
        assert doc_design.main(["use", "classic", "--kind", "bank"]) == 0
        assert doc_design.main(["set", "margin_mm", "20", "--employer", "Larkspur Labs"]) == 0
        docs = json.load(open(prof / "person.json", encoding="utf-8"))["documents"]
        assert docs["design"] == {"body_size": 12}
        assert docs["designs"]["kinds"]["bank"] == "classic"
        assert docs["designs"]["employers"]["Larkspur Labs"] == {"margin_mm": 20.0}
        assert doc_design.main(["set", "body_size", "9"]) == 2      # refused, nothing written
        assert json.load(open(prof / "person.json", encoding="utf-8"))["documents"]["design"] == {
            "body_size": 12}
    finally:
        doc_design.person.reset()


# --- the fonts -----------------------------------------------------------------------------

def test_every_vendored_font_is_present_with_its_licence_beside_it():
    for name, (folder, files, _what, _uses) in doc_design.FONTS.items():
        if folder is None:
            continue
        where = os.path.join(ROOT, doc_design.FONT_DIR, folder)
        for f in files:
            assert os.path.isfile(os.path.join(where, f)), (name, f)
        licence = open(os.path.join(where, "OFL.txt"), encoding="utf-8").read()
        assert "SIL OPEN FONT LICENSE Version 1.1" in licence, name


def test_a_vendored_font_is_loaded_by_a_relative_path_without_spaces(tmp_path, monkeypatch):
    opts, stem = doc_design.fontspec_options("liberation-serif", os.path.join(ROOT, "cv"))
    assert "Path=../cover_letters/OpenFonts/fonts/liberation-serif/" in opts
    assert "Ligatures={NoCommon}" in opts and stem == "LiberationSerif-Regular"
    opts, _stem = doc_design.fontspec_options("latin-modern-sans", os.path.join(ROOT, "cv"))
    assert "Path=" not in opts     # TeX's own font, found by TeX
    # The real case: the app inside a folder named with a space ("Jane Doe"), and a document
    # compiled outside it, where no relative path avoids the space. It was refused, and every
    # design failed from a copy under such a folder (2026-10-25); the font now goes beside
    # the document, by a path with no space.
    root = tmp_path / "Jane Doe" / "job search"
    shutil.copytree(os.path.join(ROOT, doc_design.FONT_DIR, "lato"),
                    root / doc_design.FONT_DIR / "lato")
    monkeypatch.setattr(doc_design, "ROOT", str(root))
    opts, _stem = doc_design.fontspec_options("lato", str(tmp_path / "elsewhere" / "cv"))
    assert "Path=.fonts/lato/" in opts
    assert sorted(os.listdir(tmp_path / "elsewhere" / "cv" / ".fonts" / "lato")) == sorted(
        os.listdir(root / doc_design.FONT_DIR / "lato"))
    # Inside the app, the path from cv/ never leaves it, so a space above it does not matter.
    opts, _stem = doc_design.fontspec_options(
        "lato", str(tmp_path / "Jane Doe" / "job search" / "cv"))
    assert "Path=../cover_letters/OpenFonts/fonts/lato/" in opts


# --- the page each design gives -------------------------------------------------------------

def _render(tmp_path, monkeypatch, design, style=None):
    """Render the fixture in one design, where the compile happens in a scratch folder."""
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import fit_to_page as F
    import render_application as R
    for d in ("cv", "cover_letters"):
        (tmp_path / d).mkdir(exist_ok=True)
    for f in ("OpenFonts", "cover.cls"):
        os.symlink(os.path.join(ROOT, "cover_letters", f), tmp_path / "cover_letters" / f)
    a = copy.deepcopy(DRAFT)
    a["design"] = design
    if style:
        a["style"] = style
    a["jobs"] = [{"employer": "Brindle & Hart Logistics",
                  "bullets": ["BH_FORECAST", "BH_ROUTING", "BH_PIPE"]},
                 {"employer": "Oakmere Foods", "bullets": ["OF_WASTE", "OF_SUPPLIER"]},
                 {"employer": "Saltmarsh Analytics", "bullets": ["SALT_FORECAST"]}]
    d = R.build(a)
    R.resume(d)
    R.letter(d)
    tex = docpaths.resume_tex(d["abbr"])
    engine = F.resume_engine(d["abbr"])
    F._compile(engine, os.path.basename(tex), os.path.dirname(tex), docpaths.resume_pdf(d["abbr"]))
    ltex = docpaths.letter_tex(d["abbr"])
    F._compile("xelatex", os.path.basename(ltex), os.path.dirname(ltex),
               docpaths.letter_pdf(d["abbr"]))
    return d, docpaths.resume_pdf(d["abbr"]), docpaths.letter_pdf(d["abbr"]), engine


needs_tex = pytest.mark.skipif(not (shutil.which("xelatex") and shutil.which("lualatex")),
                               reason="xelatex and lualatex are not installed here")


@needs_tex
@pytest.mark.parametrize("design", NAMED)
def test_every_design_passes_every_rule_an_ats_needs(tmp_path, monkeypatch, design):
    pytest.importorskip("pypdf")
    import design_check
    d, resume, letter, engine = _render(tmp_path, monkeypatch, design)
    assert engine == "xelatex"
    page = "letter" if doc_design.paper(d["design"]) == "letterpaper" else "a4"
    assert design_check.check(resume, page) == []
    assert design_check.check(letter, page) == []
    # The words read back with their spaces, the way verify_batch reads them.
    import subprocess
    for pdf in (resume, letter):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "verify_pdf.py"),
                              "--require", "pypdf", pdf], capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert out.returncode == 0, out.stdout + out.stderr


@needs_tex
def test_a_design_keeps_the_colour_it_is_given(tmp_path, monkeypatch):
    pytest.importorskip("pypdf")
    from tests.test_a_resume_is_black import _colours
    _d, resume, letter, _e = _render(tmp_path, monkeypatch, "classic", style="navy")
    navy = tuple(round(int(doc_style.STYLES["navy"][0][i:i + 2], 16) / 255, 2) for i in (0, 2, 4))
    assert any(max(abs(a - b) for a, b in zip(c, navy)) < 0.02 for c in _colours(resume))
    assert any(max(abs(a - b) for a, b in zip(c, navy)) < 0.02 for c in _colours(letter))


@needs_tex
def test_the_letter_follows_its_resumes_page(tmp_path, monkeypatch):
    pytest.importorskip("pypdf")
    from pypdf import PdfReader
    d, resume, letter, _e = _render(tmp_path, monkeypatch,
                                    {"name": "classic", "page": "letter"})
    for pdf in (resume, letter):
        w, h = (float(x) for x in PdfReader(pdf).pages[0].mediabox[2:])
        assert (round(w), round(h)) == (612, 792), pdf
    fonts = {str(f) for pdf in (resume, letter) for p in PdfReader(pdf).pages
             for f in (p["/Resources"]["/Font"].values())}
    names = " ".join(str(PdfReader(letter).pages[0]["/Resources"]["/Font"][k].get_object()
                         ["/BaseFont"]) for k in PdfReader(letter).pages[0]["/Resources"]["/Font"])
    assert "LiberationSerif" in names, names
    assert fonts


def test_the_rules_catch_a_page_that_breaks_them(tmp_path):
    """The checks themselves: a wrong page size, words at the edge, two columns."""
    pytest.importorskip("pypdf")
    if not shutil.which("xelatex"):
        pytest.skip("xelatex is not installed here")
    import subprocess
    import design_check
    tex = tmp_path / "bad.tex"
    tex.write_text(
        "\\documentclass[11pt]{article}\n\\usepackage[paperwidth=595.28pt,paperheight=841.89pt,"
        "margin=4mm]{geometry}\n\\begin{document}\n\\noindent\\begin{minipage}[t]{0.45\\linewidth}"
        + " ".join(["First column words."] * 40)
        + "\\end{minipage}\\hfill\\begin{minipage}[t]{0.45\\linewidth}"
        + " ".join(["Second column words."] * 40)
        + "\\end{minipage}\n\\end{document}\n", encoding="utf-8")
    subprocess.run(["xelatex", "-interaction=nonstopmode", "bad.tex"], cwd=tmp_path,
                   capture_output=True, timeout=300)
    found = " ".join(design_check.check(str(tmp_path / "bad.pdf"), "letter"))
    assert "PAGE_SIZE" in found and "EDGE" in found and "COLUMNS" in found, found


def test_fit_makes_a_design_smaller_rather_than_leave_two_pages(monkeypatch):
    import fit_to_page as F
    a = copy.deepcopy(DRAFT)
    a["design"] = "spacious"
    a["jobs"] = [{"employer": "Brindle & Hart Logistics", "bullets": ["BH_FORECAST"]}]
    renders = []

    def render(draft):
        renders.append(int(draft.get("design_step") or 0))
        return 2 if renders[-1] < 3 else 1                       # fits at the third step
    monkeypatch.setattr(F, "_render_resume", render)
    monkeypatch.setattr(F, "trim_resume", lambda a: False)      # nothing left to cut
    monkeypatch.setattr(F, "grow_resume", lambda *a, **k: False)
    monkeypatch.setattr(F, "_render_letter", lambda a: 1)
    monkeypatch.setattr(F, "compile_resume", lambda abbr, passes=1: 1)
    monkeypatch.setattr(F, "font_problems", lambda pdf: [])
    monkeypatch.setattr(F, "_lines", lambda pdf: 40)
    monkeypatch.setattr(F, "body_words", lambda a: 100)
    (pages, _lines), lpages = F.fit(a)
    assert a["design_step"] == 3 and pages == 1 and renders == [0, 1, 2, 3]


def test_the_template_is_never_stepped_down(monkeypatch):
    import fit_to_page as F
    a = copy.deepcopy(DRAFT)
    a["jobs"] = [{"employer": "Brindle & Hart Logistics", "bullets": ["BH_FORECAST"]}]
    monkeypatch.setattr(F, "_render_resume", lambda a: 2)
    monkeypatch.setattr(F, "trim_resume", lambda a: False)
    monkeypatch.setattr(F, "grow_resume", lambda *a, **k: False)
    monkeypatch.setattr(F, "_render_letter", lambda a: 1)
    monkeypatch.setattr(F, "compile_resume", lambda abbr, passes=1: 2)
    monkeypatch.setattr(F, "font_problems", lambda pdf: [])
    monkeypatch.setattr(F, "_lines", lambda pdf: 40)
    monkeypatch.setattr(F, "body_words", lambda a: 100)
    F.fit(a)
    assert "design_step" not in a


def test_a_font_reached_through_a_folder_with_a_space_is_put_beside_the_document(
        tmp_path, monkeypatch):
    """fontspec reads no font path with a space in it, and the way from a document in one
    folder to the app's fonts in another can cross one (a user folder whose name has a
    space, as the suite found running from a copy under one, 2026-10-25): it stopped every
    design with a ValueError. The font's files are put beside the document then."""
    app = tmp_path / "Zoë Quillfeather" / "my copy"
    fonts = app / doc_design.FONT_DIR / "lato"
    fonts.mkdir(parents=True)
    (fonts / "Lato-Regular.ttf").write_bytes(b"\0font")
    monkeypatch.setattr(doc_design, "ROOT", str(app))
    beside = tmp_path / "Zoë Quillfeather" / "elsewhere" / "cv"
    beside.mkdir(parents=True)
    assert doc_design._font_path("lato", str(beside)) == ".fonts/lato/"
    assert (beside / ".fonts" / "lato" / "Lato-Regular.ttf").read_bytes() == b"\0font"
    # From inside the copy, the way there has no space: the app's own folder, as before.
    inside = app / "cv"
    inside.mkdir()
    assert doc_design._font_path("lato", str(inside)) == "../cover_letters/OpenFonts/fonts/lato/"
