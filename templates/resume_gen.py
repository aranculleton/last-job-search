#!/usr/bin/env python3
"""LaTeX templates for the tailored resume and cover letter.

Boilerplate is shared so it cannot drift between documents; only the selected
content varies per posting. Bullet text is NOT here: tools/bullet_library.py
is the single copy, drawn from 01-candidate-profile.md and never escalated. A
second copy in this file once kept a Claude Code clause that had already been
moved out of the library.
"""
import datetime as _dt
import os
import sys

# Derived from this file's location, like every other tool here. It was the
# literal string "/home/user/ai-job-search", which is the path the cloud
# container happens to clone into, so it worked in the only environment anybody
# had run it in. Anywhere else, and SETUP.md documents macOS, Windows and Linux
# paths, resume_gen would have written a resume to a directory that does
# not exist, or worse, to a stale copy at that path.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import person  # noqa: E402
import docpaths  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doc_style  # noqa: E402

# Everything about the person comes from the profile: the name and contact
# line, the document noun and headings, the paper, education, certifications
# and sign-off. The templates below hold the layout and nothing else.
_ID = person.get("identity")
_DOC = person.get("documents")
_ROLES = person.module("roles")
_H = _DOC["headings"]

RESUME_HEAD = r"""%% {noun_title} - {name}
%% Tailored for: {company} - {role}
{consent}%% Compile with: lualatex {fname}.tex

\documentclass[11pt,{paper},sans]{{moderncv}}
\moderncvstyle{{banking}}
%% Black: the name, the section titles, the rule under the name, the contact line and
%% the bullet marks all take moderncv's black scheme (color1 and color2 both black).
%% The person asked for black text (2026-10-24); colour is a choice per job type, never
%% the default.
\moderncvcolor{{black}}
%% ATS: a name with no descenders sets the city one baselineskip below a 30pt
%% name, and position-sorting extractors then read the name and the city as one
%% word. A zero-width rule with depth forces the gap the extractor expects.
\renewcommand*{{\namestyle}}[1]{{{{\namefont#1\rule[-0.42em]{{0pt}}{{0pt}}}}}}
%% moderncv 2.4 and later (a current TeX install, a Mac's included) print the name through
%% \firstnamestyle and \lastnamestyle and never call \namestyle, so the rule above never
%% runs there: under a name with no descenders the city sat close enough that pdftotext
%% read the two as one word (2026-10-24). There the name is drawn 9.5pt higher instead,
%% its box unchanged, which puts it where the rule puts it on 2.3 relative to the city,
%% and nothing else on the page moves. 2.3 defines neither command and is untouched.
\ifdefined\lastnamestyle
\renewcommand*{{\firstnamestyle}}[1]{{\raisebox{{9.5pt}}[\height][\depth]{{{{\namefont\textcolor{{firstnamecolor}}{{#1}}}}}}}}
\renewcommand*{{\lastnamestyle}}[1]{{\raisebox{{9.5pt}}[\height][\depth]{{{{\namefont\textcolor{{lastnamecolor}}{{#1}}}}}}}}
\fi
%% ATS: the default bullet is a FontAwesome circle whose metrics make layout
%% extractors insert blank lines mid-bullet, splitting one bullet into two
%% paragraphs. A text bullet from the body font does not.
\AtBeginDocument{{\renewcommand*{{\labelitemi}}{{\strut\textcolor{{color1}}{{\large\rmfamily\textbullet}}}}}}

\renewcommand*{{\namefont}}{{\fontsize{{30}}{{32}}\bfseries\upshape}}
\colorlet{{firstnamecolor}}{{color1}}
\colorlet{{lastnamecolor}}{{color1}}
\colorlet{{namecolor}}{{color1}}
\renewcommand*{{\sectionstyle}}[1]{{{{\sectionfont\color{{color1}}#1}}}}
{style}
\usepackage[utf8]{{inputenc}}
\usepackage{{needspace}}

%% ATS: fontawesome glyphs extract as their own names ("MOBILE-ALT", "Envelope")
%% and land in the text layer directly in front of the phone number and email,
%% where a parser reading the contact block sees them as part of the value.
%% The icons are decoration; the contact details are the point. Drop the icons.
\renewcommand*{{\mobilephonesymbol}}{{}}
\renewcommand*{{\fixedphonesymbol}}{{}}
\renewcommand*{{\emailsymbol}}{{}}
\renewcommand*{{\addresssymbol}}{{}}
\renewcommand*{{\homepagesymbol}}{{}}

%% A labelled, left-aligned line with a hanging indent, for the blocks that are
%% lists of things rather than achievements. Bullets are reserved for what the
%% candidate did; a skills inventory rendered as bullets flattens that
%% distinction and reads as a wall.
\newcommand{{\blockline}}[2]{{%
  \par\noindent\hangindent=1.1em\hangafter=1\relax
  \textbf{{#1}}: #2\par\vspace{{1.5pt}}}}
\AtEndPreamble{{\hypersetup{{
    colorlinks=true, linkcolor=black, filecolor=black, urlcolor=black,
    pdftitle={{{name} - {noun_title}}}, pdfsubject={{{noun_title} of {name}}},
    pdfkeywords={{{pdf_keywords}}}, pdfpagemode=UseNone,
}}}}
\usepackage[scale=0.885]{{geometry}}
\usepackage{{import}}

\name{{{first}}}{{{last}}}
\address{{{location}}}{{}}{{}}
{contact_lines}

\begin{{document}}
\makecvtitle
\enlargethispage{{3\baselineskip}}

\vspace{{-22pt}}
"""

# The sections, in the order documents.section_order names (default below).
# Experience before education is the convention for somebody whose argument is
# what they did; a recent graduate, whose degree is the strongest thing they
# have, often leads with education instead, and that is the person's call.
SECTION_ORDER = ("summary", "experience", "skills", "education", "certifications")

SUMMARY = r"""\section{{{h_summary}}}
\vspace{{1pt}}
\small{{{summary}}}

"""

EXPERIENCE = r"""\section{{{h_experience}}}
\vspace{{0pt}}
"""

JOB = r"""
\needspace{{{ns}\baselineskip}}
\cventry{{{dates}}}{{{title}}}{{{employer}, {loc}}}{{}}{{}}{{%
\begin{{itemize}}
{bullets}
\end{{itemize}}}}
"""

SKILLS = r"""
\section{{{h_skills}}}
\vspace{{1pt}}
{skills}

"""

EDUCATION = r"""\section{{{h_education}}}
\vspace{{1pt}}
\par\noindent\hangindent=1.1em\hangafter=1\relax {education} {edu}\par
"""

RESUME_END = "\\end{document}\n"

CERTIFICATIONS = r"""
\section{{{h_certifications}}}
\vspace{{1pt}}
\par\noindent\hangindent=1.1em\hangafter=1\relax {certs}\par
"""

LETTER = r"""%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Cover Letter - {company}, {role}{req}
{consent}%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\documentclass[{letter_paper}]{{cover}}
\usepackage{{fancyhdr}}
{letter_style}
\pagestyle{{fancy}}
\fancyhf{{}}

\rfoot{{{page_label} \thepage \hspace{{0pt}}}}
\thispagestyle{{empty}}
\renewcommand{{\headrulewidth}}{{0pt}}
\begin{{document}}

\namesection{{}}{{\Huge{{{name}}}}}{{{letter_contact}
}}

\currentdate{{{letter_date}}}
\lettercontent{{{salutation_prefix} {salutation},}}

\lettercontent{{{p1}}}

\lettercontent{{{p2}}}

\lettercontent{{{lead}}}

{{\raggedright\fontspec[Path = OpenFonts/fonts/raleway/]{{Raleway-Medium}}\fontsize{{11pt}}{{13pt}}\selectfont
\begin{{itemize}}
{bullets}
\end{{itemize}}\par}}
\vspace{{6pt}}

\lettercontent{{{p4}}}

\begin{{flushright}}
\closing{{{closing}}}

\signature{{{name}}}
\end{{flushright}}
\end{{document}}
"""

# Bullet text lives in the profile's bullets.py, the only copy. The education
# detail sentence is chosen per draft from the profile's EDUCATION_DETAILS.
EDU_DETAILS = dict(_ROLES.EDUCATION_DETAILS)
EDU_STD = EDU_DETAILS[_ROLES.EDUCATION_DEFAULT]

_LATEX_SPECIAL = {"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "$": r"\$"}


def _tex(s):
    """Escape a plain-text profile value for LaTeX. URLs are not passed here."""
    return "".join(_LATEX_SPECIAL.get(c, c) for c in str(s))


def _href(url, label):
    return "\\href{%s}{%s}" % (url, _tex(label))


def _identity():
    """The fields both templates fill from the profile."""
    noun = _DOC.get("noun", "resume")
    extra = [_tex(x) for x in _DOC.get("resume_extra", [])]
    links = []
    if _ID.get("linkedin"):
        links.append(_href(_ID["linkedin"], _ID.get("linkedin_label") or "LinkedIn"))
    contact = []
    if _ID.get("phone"):
        contact.append("\\phone[mobile]{%s}" % _tex(_ID["phone"]))
    if _ID.get("email"):
        contact.append("\\email{%s}" % _ID["email"])
    if links or extra:
        contact.append("\\extrainfo{%s}" % " \\textbullet{} ".join(links + extra))
    head = []
    if _ID.get("email"):
        head.append("  " + _href("mailto:" + _ID["email"], _ID["email"]))
    if _ID.get("phone"):
        head.append(_tex(_ID["phone"]))
    if _ID.get("linkedin"):
        head.append(" \\urlstyle{same}" + _href(_ID["linkedin"], "LinkedIn"))
    certs = getattr(_ROLES, "CERTIFICATIONS", "")
    return dict(
        name=_tex(_ID["name"]), first=_tex(_ID["first"]), last=_tex(_ID["last"]),
        location=_tex(_ID.get("location", "")),
        noun_title=noun[:1].upper() + noun[1:],
        paper=person.paper("resume"),
        pdf_keywords=_tex(_DOC.get("pdf_keywords", noun)),
        contact_lines="\n".join(contact),
        letter_contact=" | ".join(head),
        closing=_tex(_DOC.get("closing", "Kind regards,")),
        education=_ROLES.EDUCATION,
        certifications=CERTIFICATIONS.format(h_certifications=_H["certifications"], certs=certs)
        if certs else "",
        **{f"h_{k}": v for k, v in _H.items()},
    )


def section_order():
    """documents.section_order, checked: every section once, nothing unknown."""
    order = tuple(_DOC.get("section_order") or SECTION_ORDER)
    if sorted(order) != sorted(SECTION_ORDER):
        raise ValueError(f"documents.section_order must name each of {SECTION_ORDER} "
                         f"exactly once; it is {order}")
    return order


def resume(a):
    jobs = ""
    for j in a["jobs"]:
        bl = "\n".join(f"    \\item {b}" for b in j["bullets"])
        # Escaped: an employer called "Brindle & Hart" is an alignment tab to
        # LaTeX, and the compile fails on the first one.
        jobs += JOB.format(ns=j.get("ns", 5), dates=_tex(j["dates"]), title=_tex(j["title"]),
                           employer=_tex(j["employer"]), loc=_tex(j["loc"]), bullets=bl)
    me = _identity()
    sections = {
        "summary": SUMMARY.format(summary=a["summary"], **me),
        "experience": EXPERIENCE.format(**me) + jobs,
        "skills": SKILLS.format(skills=a["skills"], **me),
        "education": EDUCATION.format(edu=a.get("edu", EDU_STD), **me),
        "certifications": me["certifications"],
    }
    # The style's colour lines, or nothing: a black resume is the template exactly.
    style = doc_style.resume_block(a.get("style"), a.get("style_why", ""))
    body = (RESUME_HEAD.format(company=a["company"], role=a["role"],
                               consent=a.get("consent", ""), style=style,
                               fname=docpaths.resume_stem(a["abbr"]), **me)
            + "".join(sections[k] for k in section_order())
            + RESUME_END)
    p = docpaths.resume_tex(a["abbr"])
    open(p, "w", encoding="utf-8").write(body)
    return p


def _long_date(d=None):
    """The letter date in the profile's convention: `March 4, 2026`
    (month_day_year, North American) or `4 March 2026` (day_month_year).

    The day is formatted by hand rather than with `%-d`, which is a glibc
    extension: it raises on Windows, and SETUP.md documents a Windows path.
    """
    d = d or _dt.date.today()
    if _DOC.get("date_format") == "day_month_year":
        return "%d %s %d" % (d.day, d.strftime("%B"), d.year)
    return "%s %d, %d" % (d.strftime("%B"), d.day, d.year)


def letter(a):
    # The label and the sentence need a separator: without one the page read
    # "Demand forecasting Gradient-boosted model estimating weekly SKU demand
    # across regional depots", which is a run-on in print and in every text
    # extraction.
    # No emphasis. Bold and italics in a letter's bullets read as shouting, and
    # a template that adds them puts them on every letter at once. The colon
    # carries the separation on its own.
    bl = "\n".join(f"    \\item {t}: {x}" for t, x in a["cl_bullets"])
    # The date is written into the .tex, not left as \today.
    #
    # \today is evaluated at COMPILE time, so every recompile silently re-dated
    # the letter. The committed PDF is the record of what an employer
    # received; re-running verify_batch.sh over an old batch, or recompiling
    # one letter to check a claim, moved the date on the archive while leaving
    # the content identical. It happened: letters drafted on one day came back
    # dated days later, from a compile whose only purpose was to read them.
    #
    # `letter_date` lets a caller pin it; the default is the day it is written,
    # which is what \today meant to say. Either way the .tex reproduces its own
    # PDF afterwards, which is the property that was missing.
    suffix = _DOC.get("salutation_suffix", " hiring team")
    # The country's paper unless the profile says otherwise (person.paper()).
    # US Letter is the class's default, so it is written as no option at all.
    paper = person.paper("letter")
    req = str(a.get("req_id") or "").strip()
    body = LETTER.format(company=a["company"], role=a["role"],
                         req=f" (requisition {req})" if req else "",
                         consent=a.get("consent", ""),
                         letter_style=doc_style.letter_block(a.get("style"),
                                                             a.get("style_why", "")),
                         letter_paper="" if paper == "letterpaper" else paper,
                         salutation=a.get("salutation", f"{a['company']}{suffix}"),
                         letter_date=a.get("letter_date") or _long_date(),
                         # The two words the letter prints that are not the
                         # person's content: in their document language.
                         page_label=_tex(_DOC.get("page_label", "Page")),
                         salutation_prefix=_tex(_DOC.get("salutation_prefix", "Dear")),
                         p1=a["p1"], p2=a["p2"], lead=a["lead"], bullets=bl, p4=a["p4"],
                         **_identity())
    p = docpaths.letter_tex(a["abbr"])
    open(p, "w", encoding="utf-8").write(body)
    return p
