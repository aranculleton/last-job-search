#!/usr/bin/env python3
"""How a resume and its cover letter are laid out: the page, the margins, the fonts, the
sizes, the spacing and where things sit. Colour is templates/doc_style.py, beside this.

Every setting starts unset, and unset means the template exactly as it was before designs
existed: a person nobody chose a design for gets the same page, word for word and point for
point (tests/test_a_design_changes_only_what_it_says.py renders the example person both
ways and compares every word's position). A design changes the document, so fit_to_page
fits the bullets to it again; it never changes what the page says.

Most specific wins, one level over the next:

  1. the template                        every setting unset
  2. the market                          the page size their country uses (person.paper)
  3. the kind of employer                person.json documents.designs.kinds, e.g. "bank"
  4. a named employer                    documents.designs.employers
  5. the person's own choice             documents.design: a design's name, or settings
  6. this one application                the draft's "design": a name, or settings

    "designs": {"kinds": {"bank": "classic", "technology company": "modern"},
                "employers": {"Larkspur Labs": "spacious"}},
    "design": {"body_size": 11, "header_align": "left"}

A level that names a design replaces what came before it with that design's values; settings
given beside a name, or on their own, change only themselves. `/setup` writes the kinds from
SUGGESTED_KINDS for a new person; an existing person keeps their page until they choose.

Only fonts that read back cleanly are offered. Each one is checked the way an applicant
tracking system reads a PDF (pypdf, then pdftotext): words keep their spaces, accented
names, the phone and the email come back as typed, and no ligature or replacement character
appears (`tools/design_check.py --fonts`, which CI runs on every computer). Measured
2026-10-25 with pypdf 3.17, 4.0, 5.0, 5.9 and 6.17, the oldest the app allows to today's:
Caladea and Carlito read with no spaces between words in every version; Raleway ran an
accented name together before 6.x; and under LuaLaTeX Lato did too before 5.9, while under
XeLaTeX every font here read cleanly in every version. So a design's resume is set with
XeLaTeX, the engine its letter always used, and the template's own resume keeps LuaLaTeX. Every font is either one every
TeX install carries (Latin Modern) or one this repo vendors with its licence beside it, and
is loaded from its file, so a Mac, a Windows computer and the cloud all set the same glyphs.

    python3 templates/doc_design.py --list              # the designs and the fonts
    python3 templates/doc_design.py "<employer>" [...]  # the design each would get, and why
    python3 templates/doc_design.py use classic [--kind bank | --employer "<name>"]
    python3 templates/doc_design.py set body_size 12 [--kind ... | --employer ...]
    python3 templates/doc_design.py adjust bigger      # a reaction, in their words: ADJUST
    python3 templates/doc_design.py clear [--kind ... | --employer ...]
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402
import local_path  # noqa: E402

DEFAULT = "standard"
# The template's resume has always been set with LuaLaTeX and keeps it; a design is set with
# XeLaTeX, which read back cleanly for every font here in every pypdf version measured.
ENGINE_TEMPLATE, ENGINE = "lualatex", "xelatex"
FONT_DIR = os.path.join("cover_letters", "OpenFonts", "fonts")

# name -> (folder under FONT_DIR, or None for a font every TeX install carries;
#          regular, bold, italic, bold italic; what it is; where it may be used)
FONTS = {
    "latin-modern-sans": (None, ("lmsans10-regular.otf", "lmsans10-bold.otf",
                                 "lmsans10-oblique.otf", "lmsans10-boldoblique.otf"),
                          "Latin Modern Sans, the template's own sans serif", ("body", "heading")),
    "lato": ("lato", ("Lato-Reg.ttf", "Lato-Bol.ttf", "Lato-RegIta.ttf", "Lato-BolIta.ttf"),
             "Lato, a rounded modern sans serif (the letter's own)", ("body", "heading")),
    "liberation-serif": ("liberation-serif",
                         ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf",
                          "LiberationSerif-Italic.ttf", "LiberationSerif-BoldItalic.ttf"),
                         "Liberation Serif, a classic serif with Times New Roman's widths",
                         ("body", "heading")),
}

# setting -> (allowed: a tuple of values, or (low, high) for a number; what it does).
# The bounds are where applicant tracking guidance and print agree: a body under 10pt or
# a margin under half an inch is where readability and some parsers both start to fail
# (references in 05-cv-templates.md, "Designs").
SCHEMA = {
    "page": (("letter", "a4"), "the paper: the market's unless set"),
    "margin_mm": ((12.0, 25.4), "every margin, in millimetres (half an inch to an inch)"),
    "body_font": (tuple(k for k, v in FONTS.items() if "body" in v[3]), "the text's font"),
    "heading_font": (tuple(FONTS), "the name's and the section titles' font"),
    # The document's size: moderncv sets its body one step smaller (\\small), so 11 gives
    # 10pt text and 12 gives 10.95pt. 10 would give 9pt, under every guide's floor, so it is
    # not offered (measured 2026-10-25, tools/design_check.py).
    "body_size": ((11, 12), "the document's size in points (its text is one step smaller)"),
    "name_size": ((20.0, 34.0), "the name's size in points"),
    "section_size": ((11.0, 16.0), "the section titles' size in points"),
    "contact_size": ((9.0, 12.0), "the contact lines' size in points"),
    "line_spread": ((1.0, 1.25), "line spacing, as a multiple of the font's own"),
    "header_align": (("left", "center", "right"), "where the name and contact lines sit"),
    "date_align": (("right", "left"), "dates at the right of the title line, or before the title"),
    "section_rule": ((True, False), "a rule under each section title"),
    "bullet_size": (("large", "normal"), "the bullet marks' size"),
    "ragged_right": ((True, False), "text set flush left with a ragged right edge"),
}
SETTINGS = tuple(SCHEMA)

# A complete set of values each, so a name always means the same page.
DESIGNS = {
    "standard": ({}, "the template as it always was: Latin Modern Sans, 11pt, a centred "
                     "name, rules under the section titles"),
    "classic": ({"body_font": "liberation-serif", "heading_font": "liberation-serif",
                 "body_size": 11, "margin_mm": 19.0, "name_size": 26.0, "section_size": 13.0,
                 "contact_size": 10.0, "line_spread": 1.0, "header_align": "center",
                 "date_align": "right", "section_rule": True, "bullet_size": "normal",
                 "ragged_right": True},
                "a serif page with a centred name: banks, insurers, law, consulting, "
                "the public sector"),
    "modern": ({"body_font": "lato", "heading_font": "lato", "body_size": 11,
                "margin_mm": 16.0, "name_size": 28.0, "section_size": 13.0,
                "contact_size": 10.0, "line_spread": 1.0, "header_align": "left",
                "date_align": "right", "section_rule": False, "bullet_size": "normal",
                "ragged_right": True},
               "a clean sans serif, name on the left, no rules: technology and startups"),
    "compact": ({"body_font": "latin-modern-sans", "heading_font": "latin-modern-sans",
                 "body_size": 11, "margin_mm": 12.0, "name_size": 22.0, "section_size": 11.5,
                 "contact_size": 9.0, "line_spread": 1.0, "header_align": "center",
                 "date_align": "right", "section_rule": True, "bullet_size": "normal",
                 "ragged_right": True},
                "the template's look with narrow margins and a smaller name: a long history on one page"),
    "spacious": ({"body_font": "lato", "heading_font": "lato", "body_size": 11,
                  "margin_mm": 22.0, "name_size": 30.0, "section_size": 14.0,
                  "contact_size": 10.5, "line_spread": 1.12, "header_align": "left",
                  "date_align": "left", "section_rule": True, "bullet_size": "normal",
                  "ragged_right": True},
                 "room to breathe, dates first: an early career with fewer bullets"),
}

# What /setup writes into documents.designs.kinds for a new person: the kinds
# templates/doc_style.py already reads from the employer lists.
SUGGESTED_KINDS = {
    "bank": "classic", "insurer": "classic", "professional services": "classic",
    "law firm": "classic", "public sector": "classic",
    "technology company": "modern", "startup": "modern", "software product": "modern",
}

# The order a page too full for its design is relaxed in, one step at a time, never past
# each setting's bound: closer lines first, then the margins, then the size.
_STEPS = (("line_spread", -0.04), ("margin_mm", -2.0), ("body_size", -1), ("name_size", -2.0),
          ("section_size", -1.0))


def check_value(key, value, where="the design"):
    if key not in SCHEMA:
        raise ValueError(f"{where} names the setting {key!r}, which does not exist; the "
                         f"settings are {', '.join(SETTINGS)}")
    allowed, _what = SCHEMA[key]
    if value is None:
        return None
    numeric = (len(allowed) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                         for x in allowed) and key not in ("body_size",))
    if numeric:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{where}: {key} must be a number from {allowed[0]} to {allowed[1]}")
        if not allowed[0] - 1e-9 <= value <= allowed[1] + 1e-9:
            raise ValueError(f"{where}: {key} {value} is outside {allowed[0]} to {allowed[1]}")
        return float(value)
    if value not in allowed or (isinstance(value, bool) != isinstance(allowed[0], bool)):
        raise ValueError(f"{where}: {key} must be one of {', '.join(map(str, allowed))}; "
                         f"it is {value!r}")
    if key == "heading_font" or key == "body_font":
        return value
    return value


def check_design(name, where="the design"):
    if name not in DESIGNS:
        raise ValueError(f"{where} names the design {name!r}, which does not exist; the "
                         f"designs are {', '.join(DESIGNS)}")
    return name


def values_of(name, where="the design") -> dict:
    """A named design's complete values (unset keys are None)."""
    vals = dict.fromkeys(SETTINGS)
    vals.update(DESIGNS[check_design(name, where)][0])
    return vals


def _apply(vals, spec, where):
    """One level: a name replaces the values; settings change only themselves."""
    if spec in (None, "", {}):
        return vals, None
    if isinstance(spec, str):
        return values_of(spec, where), spec
    if not isinstance(spec, dict):
        raise ValueError(f"{where} must be a design's name or an object of settings")
    named = spec.get("name") or spec.get("base")
    out = values_of(named, where) if named else dict(vals)
    for k, v in spec.items():
        if k in ("name", "base"):
            continue
        out[k] = check_value(k, v, where)
    return out, named


def setting() -> tuple[dict, object]:
    """documents.designs and documents.design, as the person's profile gives them."""
    designs = person.get("documents.designs", None) or {}
    if not isinstance(designs, dict):
        raise ValueError("person.json documents.designs must be an object with \"kinds\" "
                         "and \"employers\", each mapping a name to a design")
    for part in ("kinds", "employers"):
        for k, v in (designs.get(part) or {}).items():
            _apply(dict.fromkeys(SETTINGS), v, f"person.json documents.designs {part} {k!r}")
    own = person.get("documents.design", None)
    if own not in (None, "", {}):
        _apply(dict.fromkeys(SETTINGS), own, "person.json documents.design")
    return designs, own


def choose(draft: dict) -> tuple[dict, str, str]:
    """(values, name, why) for one application. `name` is the last design named on the way
    (DEFAULT when none was); `values` holds every setting, None where the template stands."""
    vals, name, why = dict.fromkeys(SETTINGS), DEFAULT, ["no design is set"]
    designs, own = setting()
    company = draft.get("company")
    picked = None
    if designs.get("employers") or designs.get("kinds"):
        from company_key import key  # noqa: E402
        by_name = {key(k): v for k, v in (designs.get("employers") or {}).items()}
        if company and key(company) in by_name:
            picked = (by_name[key(company)], "the employer named in documents.designs")
        else:
            import doc_style  # noqa: E402  (the kinds the colour styles read)
            for kind in doc_style.kinds_of(company):
                if kind in (designs.get("kinds") or {}):
                    picked = (designs["kinds"][kind], f"the kind {kind!r} in documents.designs")
                    break
    if picked:
        vals, named = _apply(vals, picked[0], picked[1])
        name, why = named or DEFAULT, [picked[1]]
    for spec, where in ((own, "person.json documents.design"),
                        (draft.get("design"), "this application's design")):
        if spec in (None, "", {}):
            continue
        vals, named = _apply(vals, spec, where)
        if named:
            name, why = named, [where]
        else:
            why = why + [f"{where} changes {', '.join(k for k in spec if k not in ('name', 'base'))}"]
    for _ in range(int(draft.get("design_step") or 0)):
        smaller = step_down(vals)
        if smaller is None:
            break
        vals = smaller
        why = why + ["made smaller to fit the page"]
    return vals, name, "; ".join(why)


def is_template(vals) -> bool:
    return not any(v is not None for v in (vals or {}).values())


def step_down(vals):
    """The same design one step smaller, or None when every step is at its bound. A design
    that never set a value has nothing to relax: the template is fitted by its bullets."""
    if is_template(vals):
        return None
    out = dict(vals)
    for key, delta in _STEPS:
        cur = out.get(key)
        if cur is None:
            continue
        allowed = SCHEMA[key][0]
        floor = min(allowed)
        new = cur + delta
        if key == "body_size":
            smaller = [s for s in allowed if s < cur]
            if not smaller:
                continue
            new = max(smaller)
        if new < floor - 1e-9:
            if cur > floor + 1e-9:
                new = floor
            else:
                continue
        out[key] = round(new, 2) if isinstance(new, float) else new
        return out
    return None


def paper(vals, kind="resume") -> str:
    """The LaTeX paper option: the design's page, else the market's (person.paper)."""
    page = (vals or {}).get("page")
    if page:
        return "letterpaper" if page == "letter" else "a4paper"
    return person.paper(kind)


# --- LaTeX --------------------------------------------------------------------------------

def _font_path(folder, tex_dir):
    """Where a vendored font sits, from the folder the document compiles in: relative and with
    forward slashes, which every TeX on every computer reads, and never with a space in it."""
    target = os.path.join(ROOT, FONT_DIR, folder)
    try:
        rel = local_path.rel(target, tex_dir)
    except ValueError:      # another drive on Windows: no relative path exists
        rel = target
    rel = rel.replace("\\", "/").rstrip("/") + "/"
    if " " in rel:
        raise ValueError(f"the font folder {rel!r} has a space in its path from {tex_dir!r}; "
                         "fonts are loaded by a path without spaces")
    return rel


def fontspec_options(name, tex_dir, extra=""):
    """fontspec's options for one font: its four files, ligatures off so a parser reads
    'fi' and 'fl' as letters, and lining figures where the font has old-style ones."""
    folder, files, _what, _uses = FONTS[name]
    reg, bold, ital, bital = files
    stem, ext = os.path.splitext(reg)
    opts = [f"Extension={ext}", f"UprightFont={stem}", f"BoldFont={os.path.splitext(bold)[0]}",
            f"ItalicFont={os.path.splitext(ital)[0]}",
            f"BoldItalicFont={os.path.splitext(bital)[0]}", "Ligatures={NoCommon}"]
    if folder:
        opts.insert(0, f"Path={_font_path(folder, tex_dir)}")
    if extra:
        opts.append(extra)
    return ",".join(opts), stem


def _font_cmd(cmd, name, tex_dir, extra=""):
    opts, stem = fontspec_options(name, tex_dir, extra)
    return f"\\{cmd}[{opts}]{{{stem}}}"


def _pt(x):
    return ("%g" % round(float(x), 2))


def _lead(size):
    return _pt(round(float(size) * 1.2, 2))


def resume_parts(vals, ident, tex_dir, name=DEFAULT, why=""):
    """The pieces of the resume a design changes, as a dict resume_gen fills its template
    with. Every piece is the template's own text when its setting is unset."""
    v = vals or dict.fromkeys(SETTINGS)
    parts = {
        "body_size": str(v.get("body_size") or 11),
        "geometry": ("margin=%smm" % _pt(v["margin_mm"])) if v.get("margin_mm") else "scale=0.885",
        "name_font": "\\fontsize{%s}{%s}\\bfseries\\upshape" % (
            (_pt(v["name_size"]), _pt(float(v["name_size"]) + 2)) if v.get("name_size")
            else ("30", "32")),
        "design": "",
        "title": "\\makecvtitle",
        "after_title": "\\vspace{-22pt}",
        "item_start": "",
        "para_start": "",
        # The engine fit_to_page compiles with, read back from the .tex's first lines.
        "engine": ENGINE_TEMPLATE,
    }
    if is_template(v):
        return parts
    parts["engine"] = ENGINE
    head = "\\ljsheadfont" if v.get("heading_font") else ""
    if head:
        parts["name_font"] = head + parts["name_font"]
    lines = [f"%% Design: {name}, {why or 'chosen for this application'} "
             "(templates/doc_design.py)."]
    if v.get("body_font"):
        lines.append("\\usepackage{fontspec}")
        lines.append(_font_cmd("setmainfont", v["body_font"], tex_dir))
        lines.append(_font_cmd("setsansfont", v["body_font"], tex_dir))
    if v.get("heading_font"):
        lines.append("\\usepackage{fontspec}")
        lines.append(_font_cmd("newfontfamily\\ljsheadfont", v["heading_font"], tex_dir))
    if v.get("line_spread"):
        lines.append("\\linespread{%s}" % _pt(v["line_spread"]))
    if v.get("section_size") or head:
        size = v.get("section_size") or 14.4
        lines.append("\\renewcommand*{\\sectionfont}{%s\\fontsize{%s}{%s}\\selectfont"
                     "\\bfseries\\upshape}" % (head, _pt(size), _lead(size)))
    if v.get("bullet_size") == "normal":
        lines.append("\\AtBeginDocument{\\renewcommand*{\\labelitemi}{\\strut\\textcolor{color1}"
                     "{\\rmfamily\\textbullet}}}")
    if v.get("ragged_right"):
        parts["item_start"] = "\\raggedright"
        parts["para_start"] = "\\raggedright"
    # The section title, drawn here rather than by moderncv, when its rule goes, so moderncv
    # 2.3 and 2.4+ draw it the same.
    if v.get("section_rule") is False:
        lines.append("\\makeatletter\\renewcommand*{\\section}[1]{\\par\\addvspace{7pt}"
                     "\\noindent\\sectionstyle{#1}\\par\\nobreak\\vspace{3pt}}\\makeatother")
    if v.get("date_align") == "left":
        # Dates before the title, on the title line; the employer's line first, as always, so
        # every check that finds a role by its employer still finds it.
        lines.append("\\renewcommand*{\\cventry}[7][.25em]{\\par\\noindent{\\bfseries #4}"
                     "\\par\\nobreak\\noindent{\\itshape #2}\\quad\\textbar\\quad"
                     "{\\itshape #3}\\par\\nobreak\\vspace{1pt}#7\\par\\addvspace{#1}}")
    if v.get("header_align"):
        # Defined in the preamble and called in the body, so the body carries no contact
        # detail or size the claims and numbers checks would read as a claim.
        lines.append("\\newcommand*{\\ljsheader}{%%\n%s}" % header(v, ident))
        parts["title"] = "\\ljsheader"
        parts["after_title"] = "\\vspace{2pt}"
    if v.get("contact_size") and not v.get("header_align"):
        lines.append("\\renewcommand*{\\addressfont}{\\fontsize{%s}{%s}\\selectfont\\mdseries"
                     "\\upshape}" % (_pt(v["contact_size"]), _lead(v["contact_size"])))
    parts["design"] = "\n".join(lines) + "\n"
    return parts


_ALIGN = {"left": "\\raggedright", "center": "\\centering", "right": "\\raggedleft"}


def header(v, ident):
    """The name and contact lines, drawn here rather than by moderncv, so the alignment is
    exact and the same on every moderncv. Name, place, then the contact lines, each its own
    line in reading order, every detail as literal text."""
    align = _ALIGN[v.get("header_align") or "center"]
    size = _pt(v.get("contact_size") or 10)
    lead = _lead(v.get("contact_size") or 10)
    rows = [r for r in ident["header_rows"] if r]
    body = "\\\\[1pt]\n".join(rows)
    return ("{%s\\namestyle{%s}\\par\\vspace{6pt}\n"
            "{\\fontsize{%s}{%s}\\selectfont\\color{color2}%%\n%s\\par}}\n\\vspace{4pt}"
            % (align, ident["name"], size, lead, body))


def letter_parts(vals, ident, tex_dir, name=DEFAULT, why=""):
    """The pieces of the letter a design changes: the same fonts, size, margins, page and
    alignment as its resume. Every piece is the template's own text when unset."""
    v = vals or dict.fromkeys(SETTINGS)
    default_list = ("\\raggedright\\fontspec[Path = OpenFonts/fonts/raleway/]{Raleway-Medium}"
                    "\\fontsize{11pt}{13pt}\\selectfont")
    parts = {"letter_design": "", "list_font": default_list}
    if is_template(v):
        return parts
    size = float(v.get("body_size") or 11)
    lead = _lead(size)
    body = ("\\ljsletterfont\\fontsize{%s}{%s}\\selectfont" % (_pt(size), lead))
    lines = [f"%% Design: {name}, to match its resume (templates/doc_design.py)."]
    if v.get("body_font"):
        lines.append(_font_cmd("newfontfamily\\ljsletterfont", v["body_font"], tex_dir,
                               "Color=primary"))
    else:
        lines.append("\\newfontfamily\\ljsletterfont[Path = OpenFonts/fonts/raleway/,"
                     "Color=primary]{Raleway-Medium}")
    if v.get("heading_font") or v.get("body_font"):
        lines.append(_font_cmd("newfontfamily\\ljsletterhead",
                               v.get("heading_font") or v["body_font"], tex_dir, "Color=primary"))
        head = "\\ljsletterhead"
    else:
        head = "\\fontspec[Path = OpenFonts/fonts/lato/]{Lato-Lig}"
    if v.get("margin_mm"):
        lines.append("\\geometry{margin=%smm}" % _pt(v["margin_mm"]))
    if v.get("line_spread"):
        lines.append("\\linespread{%s}" % _pt(v["line_spread"]))
    align = _ALIGN[v.get("header_align") or "center"]
    nsize = _pt(min(float(v.get("name_size") or 30), 30.0))
    csize = _pt(v.get("contact_size") or 10)
    lines.append("\\renewcommand{\\namesection}[3]{{%s{%s\\fontsize{%s}{%s}\\selectfont #1 #2}"
                 "\\par\\vspace{4pt}{\\ljsletterfont\\fontsize{%s}{%s}\\selectfont #3}\\par}"
                 "\\vspace{6pt}}" % (align, head, nsize, _pt(float(nsize) + 4), csize, _lead(csize)))
    for cmd, after in (("lettercontent", "\\\\}\\mbox{}\\\\ \\normalfont"),
                       ("closing", "\\\\}\\mbox{}\\\\\\mbox{}\\\\ \\normalfont"),
                       ("signature", "\\\\} \\normalfont")):
        lines.append("\\renewcommand{\\%s}[1]{\\raggedright%s {#1 %s}" % (cmd, body, after))
    lines.append("\\renewcommand{\\currentdate}[1]{\\raggedleft%s {#1 \\\\} \\normalfont}" % body)
    parts["letter_design"] = "\n".join(lines) + "\n"
    parts["list_font"] = "\\raggedright" + body
    return parts


# --- The person's reactions -----------------------------------------------------------------

# What a reaction to a page changes, in the words people use: `adjust` writes it into
# person.json documents.design (or a kind or employer's design) and learned.py records it.
ADJUST = {
    "bigger": ("body_size", +1), "smaller": ("body_size", -1),
    "roomier": ("margin_mm", +3.0), "tighter": ("margin_mm", -3.0),
    "more-spacing": ("line_spread", +0.06), "less-spacing": ("line_spread", -0.06),
    "bigger-name": ("name_size", +2.0), "smaller-name": ("name_size", -2.0),
    "name-left": ("header_align", "left"), "name-centre": ("header_align", "center"),
    "name-center": ("header_align", "center"), "name-right": ("header_align", "right"),
    "dates-left": ("date_align", "left"), "dates-right": ("date_align", "right"),
    "serif": ("body_font", "liberation-serif"), "sans": ("body_font", "lato"),
    "no-rules": ("section_rule", False), "rules": ("section_rule", True),
}


def adjusted(vals, what):
    """vals with one reaction applied, kept inside the setting's bounds."""
    if what not in ADJUST:
        raise ValueError(f"{what!r} is not a change this knows; the changes are "
                         f"{', '.join(ADJUST)}")
    key, change = ADJUST[what]
    out = dict(vals)
    cur = out.get(key)
    if isinstance(change, (int, float)) and not isinstance(change, bool):
        base = {"body_size": 11, "margin_mm": 12.1, "line_spread": 1.0, "name_size": 30.0}[key]
        cur = base if cur is None else cur
        allowed = SCHEMA[key][0]
        if key == "body_size":
            options = sorted(allowed)
            i = options.index(cur) if cur in options else 1
            new = options[max(0, min(len(options) - 1, i + (1 if change > 0 else -1)))]
        else:
            new = round(min(max(cur + change, allowed[0]), allowed[1]), 2)
        out[key] = new
    else:
        out[key] = change
    if key == "body_font":
        out["heading_font"] = change
    return out


def _level(argv):
    """("design", None) for the person, or ("kinds"|"employers", name) from --kind/--employer."""
    for flag, part in (("--kind", "kinds"), ("--employer", "employers")):
        if flag in argv:
            i = argv.index(flag)
            name = argv[i + 1]
            del argv[i:i + 2]
            return part, name
    return "design", None


def record(spec_change, part="design", name=None) -> str:
    """Write one change into person.json documents: the person's own design, or the design a
    kind or an employer takes. `spec_change(old_spec) -> new_spec`. Returns the line to say."""
    path = person.path("person.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    docs = data.setdefault("documents", {})
    if part == "design":
        old = docs.get("design")
        new = spec_change(old)
        _apply(dict.fromkeys(SETTINGS), new, "the new design")
        docs["design"] = new
        where = "every resume and letter"
    else:
        designs = docs.setdefault("designs", {})
        table = designs.setdefault(part, {})
        old = table.get(name)
        new = spec_change(old)
        _apply(dict.fromkeys(SETTINGS), new, "the new design")
        table[name] = new
        where = f"the {name} {'kind' if part == 'kinds' else 'application'}s"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    person.reset()
    return f"From the next one, {where} use: {json.dumps(new, ensure_ascii=False)}"


def _as_dict(spec):
    if spec in (None, "", {}):
        return {}
    if isinstance(spec, str):
        return {"name": spec}
    return dict(spec)


def _value(key, text):
    allowed = SCHEMA[key][0]
    if isinstance(allowed[0], bool):
        return text.lower() in ("true", "yes", "on", "1")
    if key == "body_size":
        return int(text)
    if all(isinstance(x, (int, float)) for x in allowed):
        return float(text)
    return text


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    if argv[0] == "--list":
        for name, (vals, what) in DESIGNS.items():
            print(f"{name:9s} {what}")
            if vals:
                print("          " + json.dumps(vals))
        print()
        for name, (folder, _files, what, uses) in FONTS.items():
            print(f"{name:17s} {what} ({'vendored in ' + FONT_DIR + '/' + folder if folder else 'from TeX'};"
                  f" {', '.join(uses)})")
        return 0
    argv = list(argv)
    if argv[0] in ("use", "set", "adjust", "clear"):
        part, name = _level(argv)
        cmd = argv[0]
        try:
            if cmd == "use":
                check_design(argv[1])
                line = record(lambda old: argv[1], part, name)
            elif cmd == "set":
                key = argv[1]
                val = check_value(key, _value(key, argv[2]))
                line = record(lambda old: {**_as_dict(old), key: val}, part, name)
            elif cmd == "adjust":
                def change(old):
                    spec = _as_dict(old)
                    base = values_of(spec.get("name") or DEFAULT)
                    base.update({k: v for k, v in spec.items() if k != "name"})
                    after = adjusted(base, argv[1])
                    spec.update({k: v for k, v in after.items() if v != base.get(k)})
                    return spec
                line = record(change, part, name)
            else:
                line = record(lambda old: {}, part, name)
        except (IndexError, ValueError) as exc:
            print(f"doc_design: {exc}", file=sys.stderr)
            return 2
        print(line)
        print("Record it too: python3 tools/learned.py record --area documents --said "
              "\"<their words>\" --rule \"<what changed>\" --applied-to \"person.json "
              + ("documents.design" if part == "design" else f"documents.designs.{part}") + "\"")
        return 0
    for company in argv:
        vals, name, why = choose({"company": company})
        print(f"{company}: {name} ({why})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
