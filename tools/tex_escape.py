"""Every value that reaches a .tex file, escaped for the place it lands. One copy.

A draft's words, a posting's title, the research agent's guess at a hiring manager's name
and the profile's own plain-text settings all end up inside the LaTeX the documents are
compiled from. LaTeX is a programming language: a backslash starts a command, braces
group, `%` comments out the rest of a line and a line break ends a comment. Escaping only
`% & $ # _` left `\\input{<any file>}` in a salutation able to print another file's text
into a letter, and a newline in a requisition number, written into a `%` comment line, was
the start of a command of the posting's choosing. The batch reported ALL PASS on both.

So there are four places a value can land, and one function for each:

    text(s)     body text: a paragraph, a heading, a label, a name
    comment(s)  the rest of a `%` comment line
    url(s)      the address in \\href{...}{...}, inside another command's argument
    email(s)    moderncv's \\email{...}, which prints the address and links to it

Each is the only place its rule is written. Nothing here returns LaTeX a value chose:
every backslash, brace and line break a value carries comes out as the character it is.
"""

from __future__ import annotations

import re
import urllib.parse

# What a draft may already carry because the model escaped it itself, or an older drafting
# contract asked it to, and what text() itself writes. Kept as they are, so escaping twice
# is escaping once (the fit loop and the audit both run text() over the same fields).
_KEPT = (r"\\[%&$#_{}]"
         r"|\\text(?:asciitilde|asciicircum|backslash)\{\}"
         r"|(?<=-)\\kern0pt(?=-)")
_TEXT = re.compile(r"(?P<keep>%s)|(?P<dash>-(?=-))|(?P<ch>[\\{}%%&$#_~^])" % _KEPT)
_TEXT_CHARS = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "%": r"\%", "&": r"\&",
               "$": r"\$", "#": r"\#", "_": r"\_", "~": r"\textasciitilde{}",
               "^": r"\textasciicircum{}"}

# Every character Python splits a line on (LF, CR, VT, FF, the file/group/record separators,
# NEL, the Unicode line and paragraph separators), and every other control character. A TeX
# engine ends a line on more than "\n", and a control character is an "invalid character"
# error or a glyph no font has.
_BREAKS = re.compile(r"[\n\r\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")


def one_line(s) -> str:
    """`s` with every line break, and the spaces around it, as one space; a tab or any
    other control character as a space."""
    s = str(s if s is not None else "")
    if _BREAKS.search(s):
        parts = _BREAKS.split(s)
        parts = ([parts[0].rstrip()] + [p.strip() for p in parts[1:-1]]
                 + [parts[-1].lstrip()])
        s = " ".join(p for p in parts if p)
    return _CONTROL.sub(" ", s).replace("\t", " ")


def text(s, dashes=False) -> str:
    """Plain text as LaTeX body text: every special character printed as itself.

    `\\ { } % & $ # _ ~ ^` are escaped, a line break is a space (a blank line inside a
    command's argument is a paragraph LaTeX refuses), and two hyphens stay two hyphens
    (`-\\kern0pt-`, which both engines leave apart where `-{}-` is joined by LuaTeX):
    LaTeX joins "--" into an en dash, and a LinkedIn id that carries one printed
    as a dash the dash checks then failed. `dashes=True` leaves "--" to LaTeX, for prose a
    drafter wrote: there a typed dash is a dash, and the page's dash checks are what catch
    it. Idempotent: an escape it would write, or one a draft already carries (`\\%`, `\\&`,
    `\\textasciitilde{}`), is left as it is."""
    def one(m):
        if m.group("keep"):
            return m.group("keep")
        if m.group("dash"):
            return "-" if dashes else "-\\kern0pt"
        return _TEXT_CHARS[m.group("ch")]
    return _TEXT.sub(one, one_line(s))


def comment(s) -> str:
    """A value written after `%` on one line of a .tex file: on that line, and only on it.
    Inside a comment every character is inert except the end of the line, so the line
    breaks are all that go."""
    return one_line(s).strip()


# What a URL may carry as itself: RFC 3986's unreserved and reserved characters, and "%"
# where it opens an escape that is already there.
_URL_SAFE = "-._~:/?#[]@!$&'()*+,;=%"
# Inside \href's address, itself inside another command's argument (moderncv's \extrainfo,
# cover.cls's \namesection), these are written as the escapes hyperref reads back as the
# character; checked by compiling and reading each link out of the PDF.
_URL_TEX = {"%": r"\%", "#": r"\#", "&": r"\&", "_": r"\_", "~": r"\string~",
            "$": r"\string$"}
_BARE_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")


def url(s) -> str:
    """An address for the first argument of \\href, wherever the \\href sits.

    Anything a URL cannot carry as itself (a space, a brace, a backslash, a letter outside
    ASCII) is percent-encoded, which is the same address; an encoding already there is kept
    ("jos%C3%A9", which LinkedIn writes for every accented name). Then each character LaTeX
    reads as markup is escaped: a bare "%" inside \\extrainfo{} commented out the rest of the
    contact block, and the letter did not compile at all."""
    s = str(s if s is not None else "").strip()
    # An escape somebody wrote by hand to make it compile is the character it stands for.
    s = re.sub(r"\\(?:string)?([%#&_~$])", r"\1", s)
    s = _BARE_PERCENT.sub("%25", s)
    s = urllib.parse.quote(s, safe=_URL_SAFE)
    return "".join(_URL_TEX.get(c, c) for c in s)


# moderncv's \email{} prints its argument and links to "mailto:" plus the same tokens, so
# one form has to read right in both: "\_" prints "_" and links "_" (checked as url() is).
_EMAIL_TEX = {"%": r"\%", "#": r"\#", "&": r"\&", "_": r"\_", "~": r"\string~",
              "$": r"\string$", "^": r"\string^"}


def email(s) -> str:
    """An address for moderncv's \\email{}: printed and linked from one argument."""
    s = str(s if s is not None else "").strip()
    if re.search(r"[\s\\{}]", s):
        raise ValueError(f"the email address {s!r} carries a space, a backslash or a brace, "
                         "which no address a person gives out has: correct identity.email "
                         "in person.json")
    return "".join(_EMAIL_TEX.get(c, c) for c in s)
