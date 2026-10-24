#!/usr/bin/env python3
"""How a resume and its cover letter look: black, unless the person chose a colour for a kind
of employer.

A style is one accent colour and nothing else. On the resume the name, the section titles,
the rules under them and the bullet marks take it; on the letter the name and the bullet
marks do. Every other word stays black, and every word sits exactly where it sits in black.

Why only colour (measured 2026-10-24 on the example person's resume, same text each time):

  - the letter's own Lato and Raleway as the resume's body font broke 11 and 19 of 43 lines
    differently, and a serif body 15;
  - Lato for the name and the headings alone kept every line, but moved the page's last
    line 3.25pt down, which is the margin a full page has before fit_to_page cuts a bullet;
  - moderncv's own section-rule options did nothing in this template, or moved the page by
    14.8pt, which gives fit_to_page room it fills with another bullet.

A different font or layout is a different document, with different bullets on it. A colour
is the same document. Fonts are where machines differ, too: only the fonts this repo
vendors or every TeX install carries are certain on a Mac and in the cloud alike.

The person's choice is person.json `documents.styles`, and with none every document is
black, as it was before styles existed:

    "styles": {
      "kinds": {"bank": "navy", "insurer": "navy", "professional services": "burgundy",
                "technology company": "slate", "startup": "teal",
                "software product": "forest"},
      "employers": {"Larkspur Labs": "plum"}
    }

The kind is what the app already knows about an employer, never a second guess:

  startup             a name on employers.py YC_AND_BACKED (the venture-backed list the
                      opportunity score reads), checked first, as such a company is usually
                      a technology company too
  technology company  a name on employers.py TECH_COMPANIES (tools/sector.py kind())
  software product    a name on employers.py ADJACENT_COMPANIES
  bank, insurer, ...  the word employers.py NOT_TECH gives the name, in the person's words

A draft's own `style` wins over all of it, for one application; an employer named under
`employers` wins over its kind; anything the rules do not place is black.

    python3 templates/doc_style.py "<employer>" [...]   # the style each would get, and why
    python3 templates/doc_style.py --list               # the styles, with their contrast
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402

DEFAULT = "black"

# name -> (accent, what it is). The accent is a hex colour, or None for black. Each one
# reads as text on white at a contrast of 4.5 or more (WCAG's line for body text), so it
# survives a pale screen and a black-and-white printer alike:
# tests/test_a_style_is_only_colour.py measures it.
STYLES = {
    "black": (None, "every word black, the default"),
    "navy": ("1F3A5F", "a dark navy"),
    "burgundy": ("7A1F3D", "a dark burgundy"),
    "forest": ("22543C", "a dark green"),
    "teal": ("1D5C63", "a dark teal"),
    "plum": ("4B2A6B", "a dark purple"),
    "slate": ("2F4858", "a blue-grey"),
    # Every resume's colour before 2026-10-24: moderncv's blue, with the links in bright blue.
    # Kept so a person who liked it can have it back.
    "blue": ("3873B2", "the blue every resume had before 2026-10-24, links in bright blue"),
}
# moderncv's own value for "blue", written as moderncv writes it, so the resume takes the
# old colour exactly rather than a hex that rounds to it (#3873B2 is that hex, for the
# letter's font and the contrast check).
_BLUE_RGB = "0.22,0.45,0.70"


def setting() -> dict:
    """documents.styles, checked: every style it names is one this file defines."""
    s = person.get("documents.styles", None) or {}
    if not isinstance(s, dict):
        raise ValueError("person.json documents.styles must be an object with \"kinds\" and "
                         "\"employers\", each mapping a name to a style")
    for part in ("kinds", "employers"):
        for k, v in (s.get(part) or {}).items():
            check(v, f"person.json documents.styles {part} {k!r}")
    return s


def check(name, where: str = "the draft's style") -> str:
    if name not in STYLES:
        raise ValueError(f"{where} names the style {name!r}, which does not exist; the styles "
                         f"are {', '.join(STYLES)}")
    return name


def kinds_of(company: str | None) -> list[str]:
    """What the app's own lists say this employer is, most specific first. Nothing is guessed:
    an employer on none of the person's lists has no kind."""
    import opportunity  # noqa: E402  (only when a mapping is set: the default reads nothing)
    import sector  # noqa: E402
    from company_key import key  # noqa: E402
    name = str(company or "").strip()
    if not name:
        return []
    out = []
    if (opportunity._names_in(name.lower(), opportunity.YC_AND_BACKED)
            or opportunity._names_in(key(name), opportunity.YC_AND_BACKED)):
        out.append("startup")
    k = sector.kind(name)
    if k:
        out.append(k)
    return out


def choose(draft: dict) -> tuple[str, str]:
    """(style, why) for one application: the draft's own style, else the employer named in
    documents.styles, else the first of its kinds the setting maps, else black."""
    own = str(draft.get("style") or "").strip()
    if own:
        return check(own), "this application's own choice"
    s = setting()
    company = draft.get("company")
    if not (s.get("kinds") or s.get("employers")):
        return DEFAULT, "no style is set"
    from company_key import key  # noqa: E402
    by_name = {key(k): v for k, v in (s.get("employers") or {}).items()}
    if company and key(company) in by_name:
        return by_name[key(company)], "the employer named in documents.styles"
    for kind in kinds_of(company):
        if kind in (s.get("kinds") or {}):
            return s["kinds"][kind], f"the kind {kind!r} in documents.styles"
    return DEFAULT, "the employer is not on a list a style is set for"


def resume_block(style: str | None, why: str = "") -> str:
    """The lines the resume's preamble takes after the template's own colour lines; "" for
    black, so a black resume is the template exactly.

    Two generations of moderncv read colour differently, and both are in use: the cloud's
    TeX Live 2023 carries 2.3.1, which reads color1 each time it draws, and a current install
    (a Mac's) carries 2.4 or later, which copies the scheme's colours into names of its own
    when the style loads and prints the name in two parts. So every one of those names is set
    again here, and the name's font takes the colour, which reaches it under either."""
    name = check(style or DEFAULT)
    hexcolour, _what = STYLES[name]
    if hexcolour is None:
        return ""
    colour = ("\\definecolor{color1}{rgb}{%s}" % _BLUE_RGB if name == "blue"
              else "\\definecolor{color1}{HTML}{%s}" % hexcolour)
    out = (f"%% Style: {name}, {why or 'chosen for this application'}. Only colour changes: "
           "the name,\n%% the section titles and rules and the bullet marks take it, and every "
           "word sits where\n%% it sits in black. Set for moderncv 2.3 and for 2.4 and later "
           "alike (templates/doc_style.py).\n"
           f"{colour}\n"
           "\\colorlet{firstnamecolor}{color1}\\colorlet{lastnamecolor}{color1}"
           "\\colorlet{namecolor}{color1}\n"
           "\\colorlet{sectioncolor}{color1}\\colorlet{subsectioncolor}{color1}"
           "\\colorlet{bodyrulecolor}{color1}\n"
           "\\let\\ljsnamefont\\namefont\\renewcommand*{\\namefont}{\\ljsnamefont\\color{color1}}\n")
    if name == "blue":
        # The links were bright blue too, the email and the profile link in the contact line.
        out += "\\AtBeginDocument{\\hypersetup{linkcolor=blue, filecolor=magenta, urlcolor=blue}}\n"
    return out


def letter_block(style: str | None, why: str = "") -> str:
    """The lines the letter's preamble takes: the name and the bullet marks in the accent, to
    match the resume; "" for black, so a black letter is the template exactly.

    The bullet marks are set in the letter's main font, which carries its own colour inside
    the font (cover.cls `Color=primary`), so \\color cannot reach them: the same font is asked
    for again with another colour, which keeps the glyph and its width."""
    name = check(style or DEFAULT)
    hexcolour, _what = STYLES[name]
    if hexcolour is None:
        return ""
    return (f"%% Style: {name}, {why or 'chosen for this application'}: the name and the bullet "
            "marks take it,\n%% to match the resume. Nothing moves.\n"
            "\\definecolor{ljsaccent}{HTML}{%s}\n"
            "\\let\\ljsnamesection\\namesection\n"
            "\\renewcommand{\\namesection}[3]{\\ljsnamesection{#1}"
            "{{\\leavevmode\\color{ljsaccent}#2}}{#3}}\n"
            "\\renewcommand{\\labelitemi}{\\labelitemfont\\addfontfeature{Color=%s}\\textbullet}\n"
            % (hexcolour, hexcolour))


def contrast(hexcolour: str) -> float:
    """WCAG 2 contrast ratio of a colour against white."""
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hexcolour[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return 1.05 / (lum + 0.05)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    if argv[0] == "--list":
        for name, (hexcolour, what) in STYLES.items():
            c = f"#{hexcolour}, contrast {contrast(hexcolour):.1f}" if hexcolour else "black"
            print(f"{name:9s} {what} ({c})")
        return 0
    for company in argv:
        style, why = choose({"company": company})
        print(f"{company}: {style} ({why})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
