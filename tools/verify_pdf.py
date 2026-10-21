#!/usr/bin/env python3
"""Verify that a generated PDF has the expected pages and extractable text.

Text-layer extraction tries pypdf (BSD, optional `pip install pypdf`) first,
then Poppler `pdftotext` if pypdf is missing, raises, or returns zero
extractable characters. Poppler remains the fallback.

`--require pypdf` refuses the fallback. Only pypdf sees a text layer whose words
run together (pdftotext infers the spaces), so a check that fell back passed
exactly the failure it exists for. With pypdf unavailable it exits
EXIT_NO_READER, distinct from a finding, so a caller can say the spacing check
was skipped rather than passed.
"""

import argparse
import re
import subprocess
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import local_path  # noqa: E402  pdftotext where Homebrew keeps it, on a Mac's bare PATH

local_path.extend()
from pathlib import Path


class VerificationError(Exception):
    """Raised when a generated PDF does not satisfy its checks."""


class ReaderUnavailable(VerificationError):
    """The extractor the caller required cannot run here."""


# Exit status when --require names a reader this machine does not have: not a
# finding about the PDF, and not a pass either.
EXIT_NO_READER = 3


def run_tool(command):
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout
    except FileNotFoundError as exc:
        raise VerificationError(
            f"required command '{command[0]}' was not found. "
            "Install pypdf (`pip install pypdf`) or poppler-utils "
            "(macOS: brew install poppler, Debian/Ubuntu: apt install poppler-utils, "
            "Windows: winget install oschwartz10612.Poppler)"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or (exc.stdout or "").strip()
        detail = detail or "command failed"
        raise VerificationError(f"{command[0]} could not read the PDF: {detail}") from exc


def parse_page_count(pdfinfo_output):
    match = re.search(r"^Pages:\s+(\d+)\s*$", pdfinfo_output, re.MULTILINE)
    if not match:
        raise VerificationError("pdfinfo output did not contain a page count")
    return int(match.group(1))


# What LaTeX puts in the text layer, and what a person types when asking for it.
#
# This is a live bug rather than a nicety. `normalize_text` collapsed whitespace
# and nothing else, but LaTeX renders ' as U+2019, -- as an en dash, "..." as
# smart quotes and fi as a ligature. So `--contains "Sam's"` could never match
# a PDF containing "Sam's", and `--contains "2023-2025"` could never match a
# date range, which between them is most of what anyone would check a resume
# for. Every such call silently failed, and a check that cannot pass is worse
# than no check because it gets switched off.
#
# Folding runs on BOTH sides, so it does not matter which form the caller types.
_TYPOGRAPHIC = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u00ab": '"', "\u00bb": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-",
    "\u2026": "...",
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\u00a0": " ", "\u2007": " ", "\u2009": " ", "\u202f": " ", "\u200b": "",
    "\u00ad": "",
}
_FOLD = str.maketrans(_TYPOGRAPHIC)


def fold_typography(text):
    """Smart quotes, dashes, ligatures and exotic spaces down to ASCII."""
    return (text or "").translate(_FOLD)


def normalize_text(text):
    """Whitespace-collapsed and typographically folded, for comparison only.

    Never used for what is shown to a reader or written to --dump-text: those
    keep the real characters, because an ATS reads the real text layer.
    """
    return " ".join(fold_typography(text).split())


# Words an extractor runs together, which no --contains check notices unless the
# string it looks for happens to contain a space.
#
# The live case, 2026-10-05: a one-page resume built with LuaLaTeX and an
# OpenType font (Source Sans Pro) rendered perfectly, and `pdftotext -layout`
# read it perfectly, because Poppler infers spaces from where glyphs sit. pypdf
# does not. It read the header city and province as one word, the phone number
# with its spaces gone, and every line below as one token. LuaTeX and XeTeX emit no space glyphs, so a
# font whose metrics pypdf cannot infer spaces from loses them all. pdfLaTeX
# with `\pdfinterwordspaceon` writes real ones. verify_batch.sh reads with
# pdftotext, so this file is the only place that sees what pypdf sees.
#
# Calibrated on every PDF in cv/ and cover_letters/ that day (140): the worst
# average word length was 6.5 letters, and the worst share of 20+ letter words
# 0.26%. The broken page measured 40.0 and 55%. The thresholds sit far from both.
GLUED_MIN_WORDS = 40
GLUED_MAX_AVG_LEN = 12.0
GLUED_MAX_LONG_SHARE = 0.05
GLUED_LONG_LETTERS = 20
# Long by nature, and never evidence of a missing space.
_URLISH = re.compile(r"(https?://|www\.|@|\.(?:com|ca|org|net|io|uk)\b|linkedin)", re.I)


def glued_text(text):
    """How badly a text layer runs its words together.

    Returns (words, average length, share of 20+ letter words, up to three
    examples). URLs, emails and profile handles are left out, and so is
    anything with no letters in it (dates, phone numbers, bullets).
    """
    words = [w for w in fold_typography(text).split()
             if re.search(r"[A-Za-z]", w) and not _URLISH.search(w)]
    if not words:
        return 0, 0.0, 0.0, []
    avg = sum(len(w) for w in words) / len(words)
    long = [w for w in words if len(re.sub(r"[^A-Za-z]", "", w)) >= GLUED_LONG_LETTERS]
    return len(words), avg, len(long) / len(words), long[:3]


def check_spacing(text, extractor):
    """Raise when the text layer has lost its interword spaces."""
    words, avg, share, examples = glued_text(text)
    if words < GLUED_MIN_WORDS:
        return
    if avg > GLUED_MAX_AVG_LEN or share > GLUED_MAX_LONG_SHARE:
        sample = ", ".join(repr(e[:40]) for e in examples)
        raise VerificationError(
            f"text layer runs words together: {avg:.1f} letters per word on average, "
            f"{share:.0%} of words {GLUED_LONG_LETTERS}+ letters (e.g. {sample}), "
            f"so a parser using this extractor reads lines as single tokens "
            f"(extractor: {extractor}). Usual cause: LuaLaTeX or XeLaTeX with an "
            f"OpenType font that emits no space glyphs; build with pdfLaTeX and "
            f"\\pdfinterwordspaceon, or with a font that extracts cleanly")


def _extract_pypdf(pdf_path):
    """Return (text, pages) or None if pypdf is unavailable, raises, or yields no text.

    The guards catch BaseException rather than Exception, which looks
    indiscriminate and is not. On a container whose system `cryptography`
    package is broken, importing pypdf reaches Rust bindings that abort inside
    pyo3, and pyo3 surfaces that as `pyo3_runtime.PanicException`, a direct
    subclass of BaseException. An `except ImportError` does not see it and
    neither does an `except Exception`, so this function did not return None:
    it took the whole process down, and the Poppler fallback three lines below
    in `extract_text_layer` never ran even with `pdftotext` installed and
    working. The tool whose job is the last check before a document reaches an
    employer refused to check anything, and the traceback pointed at pypdf
    rather than at the broken dependency.

    `pip3 install --upgrade cffi` fixes the underlying container problem, and
    the fallback is what makes that a footnote instead of a blocked session.
    KeyboardInterrupt and SystemExit are re-raised because swallowing those is
    how a script stops being interruptible.
    """
    try:
        from pypdf import PdfReader
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return None
    try:
        reader = PdfReader(str(pdf_path))
        pages = len(reader.pages)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return None
    # Harden: treat empty/degraded extraction as failure so we fall back
    if len(normalize_text(text)) == 0:
        return None
    return text, pages


def pypdf_available():
    """Whether pypdf imports. The same broad guard as `_extract_pypdf`, for the
    same reason: a broken `cryptography` panics inside pyo3 on import."""
    try:
        import pypdf  # noqa: F401
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return False
    return True


def _extract_pdftotext(pdf_path):
    text = run_tool(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"])
    # Always call pdfinfo here so the fallback path returns a page count
    # even when the caller did not request --pages (same Poppler package).
    pages = parse_page_count(run_tool(["pdfinfo", str(pdf_path)]))
    return text, pages


def extract_text_layer(pdf_path, require=None):
    """Extract ATS-readable text. Returns (text, pages, extractor_name).

    With `require="pypdf"` there is no fallback: ReaderUnavailable when pypdf
    cannot be imported, and a VerificationError when it reads no text.
    """
    if require == "pypdf" and not pypdf_available():
        raise ReaderUnavailable(
            "pypdf is not available, so words run together cannot be checked: "
            "pip3 install pypdf, or pip3 install --upgrade cffi if it is installed")
    pypdf_result = _extract_pypdf(pdf_path)
    if pypdf_result is not None:
        text, pages = pypdf_result
        return text, pages, "pypdf"
    if require == "pypdf":
        raise VerificationError("pypdf read no text from this PDF, so an ATS reading the "
                                "way it does sees nothing (extractor: pypdf)")
    text, pages = _extract_pdftotext(pdf_path)
    return text, pages, "pdftotext"


def verify_pdf(pdf_path, expected_pages=None, min_chars=1, required_text=(), dump_text=None,
               require=None):
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise VerificationError(f"PDF does not exist: {pdf_path}")

    extracted_text, actual_pages, extractor = extract_text_layer(pdf_path, require)

    # Write dump *before* the checks so a failed verification still leaves a .txt
    if dump_text is not None:
        dump_path = Path(dump_text)
        try:
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            dump_path.write_text(
                extracted_text if extracted_text.endswith("\n") else extracted_text + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise VerificationError(
                f"could not write --dump-text to {dump_path}: {exc}"
            ) from exc

    if expected_pages is not None and actual_pages != expected_pages:
        raise VerificationError(
            f"expected {expected_pages} page(s), found {actual_pages} (extractor: {extractor})"
        )

    normalized = normalize_text(extracted_text)
    if len(normalized) < min_chars:
        raise VerificationError(
            f"text layer has {len(normalized)} character(s); expected at least {min_chars} "
            f"(extractor: {extractor})"
        )

    check_spacing(extracted_text, extractor)

    for required in required_text:
        if normalize_text(required) not in normalized:
            raise VerificationError(
                f"text layer is missing required text: {required!r} (extractor: {extractor})"
            )
    return extractor, extracted_text, actual_pages


# ------------------------------------------------------------------ the round trip
#
# Every check above asks whether the text layer is readable. None asked whether it says
# what the draft put on the page. An unescaped % ate the rest of a bullet, a glyph the font
# lacks dropped a letter from a name, and a swallowed brace lost a skills line: the PDF was
# one page, its text extracted cleanly, and every check passed a document that said
# something other than the draft. draft.json is the ground truth, so each line it put on
# the page (contact lines, headings, the summary, each role's employer, title and dates,
# each bullet, each skills line, education, certifications) must be in the text layer, in
# page order. Hyphenation, spacing and punctuation are set aside; letters, digits and the
# symbols a figure carries (% and currency signs among them) are not.
#
# The idea, a field-by-field recovery of a known draft from the extracted text with each
# field claimed once, in order, is the one Resume-Matcher's ats_parse/roundtrip.py uses
# (github.com/srbhr/Resume-Matcher, Apache-2.0). No code was taken from it.

# How much a page break may put inside one line (a footer, a page number) and still let the
# two halves count as the line, in kept characters.
ROUNDTRIP_GAP = 200
_KEEP = set("%\u00a3$\u20ac&+@#")


def tex_plain(text):
    """A LaTeX field as the page prints it: escapes undone, commands dropped, their text kept."""
    s = str(text or "")
    s = re.sub(r"\\blockline\{([^{}]*)\}\{", r"\1: {", s)
    s = re.sub(r"\\href\{[^{}]*\}\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\kern\s*-?[\d.]*\s*(?:pt|em|ex|mu)?", "", s)
    for name, char in (("pounds", "\u00a3"), ("texteuro", "\u20ac"), ("euro", "\u20ac"),
                       ("textasciitilde", "~"), ("textasciicircum", "^"),
                       ("textbullet", "\u2022"), ("textendash", "-")):
        s = re.sub(r"\\%s(?![a-zA-Z])(?:\{\})?" % name, char, s)
    s = re.sub(r"\\([&%$#_{}])", r"\1", s)
    s = s.replace("\\\\", " ")
    s = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", s)
    return " ".join(s.replace("{", "").replace("}", "").replace("~", " ").split())


def canon(text):
    """Only what a reader cannot lose without the line saying something else: letters,
    digits and the symbols a figure carries. Spaces, hyphens (a hyphenated line break
    among them) and punctuation go."""
    import unicodedata
    folded = unicodedata.normalize("NFKC", fold_typography(text)).casefold()
    return "".join(ch for ch in folded if ch.isalnum() or ch in _KEEP)


def roundtrip_fields(draft):
    """[(label, [(what, text)])] for one draft, in page order: each group's lines may come
    in any order among themselves (a role's employer, title and dates share a line or two),
    and each group comes after the one before it."""
    import copy
    import person
    import render_application as R
    gen = R.gen
    d = R.build(copy.deepcopy(draft))
    ident = person.get("identity") or {}
    docs = person.get("documents") or {}
    heads = docs.get("headings") or {}
    header = [("your name", ident.get("name", ""))]
    header += [(what, ident.get(key, "")) for what, key in (
        ("your location", "location"), ("your phone", "phone"), ("your email", "email"))]
    if ident.get("linkedin"):
        header.append(("your LinkedIn", ident.get("linkedin_label") or "LinkedIn"))
    header += [("the contact line", x) for x in docs.get("resume_extra") or []]
    groups = [("Contact details", [(w, t) for w, t in header if str(t).strip()])]
    for key in gen.section_order():
        heading = heads.get(key, key.capitalize())
        if key == "certifications" and not getattr(gen._ROLES, "CERTIFICATIONS", ""):
            continue
        groups.append(("the heading %s" % heading, [("heading", heading)]))
        if key == "summary":
            groups.append(("%s (the summary)" % heading, [("summary", tex_plain(d["summary"]))]))
        elif key == "experience":
            for j in d["jobs"]:
                groups.append(("%s, its heading line" % j["employer"], [
                    ("employer", "%s, %s" % (j["employer"], j["loc"])), ("title", j["title"]),
                    ("dates", j["dates"])]))
                groups += [("%s, bullet %d" % (j["employer"], i), [("bullet", tex_plain(b))])
                           for i, b in enumerate(j["bullets"], 1)]
        elif key == "skills":
            groups += [("%s, line %d" % (heading, i), [("skills line", tex_plain(ln))])
                       for i, ln in enumerate(str(d["skills"]).splitlines(), 1) if ln.strip()]
        elif key == "education":
            groups.append((heading, [("education", tex_plain(
                "%s %s" % (gen._ROLES.EDUCATION, d.get("edu", gen.EDU_STD))))]))
        else:
            groups.append((heading, [("certifications", tex_plain(gen._ROLES.CERTIFICATIONS))]))
    return groups


def _find(hay, words, pos):
    """(start, end) of `words` in the kept text at or after `pos`, or None. A page break may
    sit inside one line: two halves within ROUNDTRIP_GAP of each other count."""
    needle = canon(" ".join(words))
    if not needle:
        return pos, pos
    at = hay.find(needle, pos)
    if at >= 0:
        return at, at + len(needle)
    for k in range(1, len(words)):
        first, second = canon(" ".join(words[:k])), canon(" ".join(words[k:]))
        a = hay.find(first, pos) if first and second else -1
        while a >= 0:
            b = hay.find(second, a + len(first), a + len(first) + ROUNDTRIP_GAP + len(second))
            if b >= 0:
                return a, b + len(second)
            a = hay.find(first, a + 1)
    return None


def _symbols(text) -> set:
    """The symbols in a line that `canon` sets aside and a reader still reads: a maths or
    other sign ("≥", "→", "×"), never punctuation or the spacing marks LaTeX
    turns into spaces."""
    import unicodedata
    return {ch for ch in str(text or "") if unicodedata.category(ch).startswith("S")
            and ch not in _KEEP and ch not in "~^`|"}


def roundtrip(groups, text):
    """What the text layer lacks or holds out of order, as plain lines; [] when every line
    the draft put on the page is there, in order.

    A symbol the font has no glyph for is set aside by `canon` on both sides (the page
    shows a replacement character, the draft the sign), so every line read as present.
    Each line's symbols are looked for in the text layer as they are, and a replacement
    character on the page is named."""
    hay = canon(text)
    raw = str(text or "")
    pos, last, out = 0, "", []
    if "\ufffd" in raw:
        out.append("missing: a character the font has no glyph for is on the page, shown as "
                   "\ufffd: write it another way")
    for label, fields in groups:
        for _what, field in fields:
            lost = sorted(_symbols(field) - set(raw))
            if lost:
                out.append("missing: %s: the sign %s is not in the text layer (the font has no "
                           "glyph for it): write it in words" % (label, " ".join(lost)))
    for label, fields in groups:
        ends = []
        for _what, field in fields:
            words = str(field).split()
            hit = _find(hay, words, pos)
            if hit:
                ends.append(hit[1])
                continue
            show = " ".join(words[:10]) + (" ..." if len(words) > 10 else "")
            if _find(hay, words, 0):
                out.append("out of order: %s (\"%s\") comes before %s" % (label, show, last))
                continue
            got = max((k for k in range(1, len(words)) if _find(hay, words[:k], pos)), default=0)
            out.append("missing: %s (\"%s\"): %s" % (
                label, show, "the text layer has it only as far as \"%s\"" % " ".join(
                    words[max(0, got - 6):got]) if got else "it is not in the text layer at all"))
        if ends:
            pos = max(ends)
        last = label
    return out


def roundtrip_pdf(pdf_path, drafts_path, abbr=""):
    """(findings, how many lines were checked, extractor) for the resume `pdf_path`, against
    its draft in `drafts_path` (a drafts.json or a kept draft.json)."""
    import fit_to_page
    import render_application as R
    drafts, _ = fit_to_page.load(drafts_path)
    mine = [d for d in drafts if not abbr or abbr in (d.get("abbr"), R.final_abbr(d))]
    if len(mine) != 1:
        raise VerificationError("%s holds %s draft for %s: name it with --abbr" % (
            drafts_path, "no" if not mine else "more than one", abbr or "this resume"))
    groups = roundtrip_fields(mine[0])
    text, _pages, extractor = extract_text_layer(pdf_path)
    return roundtrip(groups, text), sum(len(f) for _l, f in groups), extractor


def keywords_pdf(pdf_path, drafts_path, abbr=""):
    """The keyword coverage report for one resume, as plain lines: the posting's terms on
    the page, held but not on it, and not held (never to add). A report only."""
    import fit_to_page
    import render_application as R
    import skills_block
    drafts, _ = fit_to_page.load(drafts_path)
    mine = [d for d in drafts if not abbr or abbr in (d.get("abbr"), R.final_abbr(d))]
    if len(mine) != 1:
        raise VerificationError("%s holds %s draft for %s: name it with --abbr" % (
            drafts_path, "no" if not mine else "more than one", abbr or "this resume"))
    if not str(mine[0].get("posting") or "").strip():
        return ["no posting kept with this draft, so nothing to measure against"]
    text, _pages, _extractor = extract_text_layer(pdf_path)
    return skills_block.coverage_lines(skills_block.coverage(
        mine[0]["posting"], text, mine[0].get("consented_skills") or ()))


def build_parser():
    parser = argparse.ArgumentParser(
        description="Verify a PDF's page count and ATS-readable text layer."
    )
    parser.add_argument("pdf", type=Path, help="PDF file to verify")
    parser.add_argument("--pages", type=int, help="required exact page count")
    parser.add_argument(
        "--min-chars",
        type=int,
        default=1,
        help="minimum non-whitespace text-layer characters (default: 1)",
    )
    parser.add_argument(
        "--contains",
        action="append",
        default=[],
        help="text that must appear after whitespace normalization; repeatable",
    )
    parser.add_argument(
        "--dump-text",
        type=Path,
        help="write the extracted text layer to this path (UTF-8)",
    )
    parser.add_argument(
        "--roundtrip",
        metavar="DRAFTS",
        help="check instead that every line the draft in this drafts.json (or draft.json) put "
             "on the page is in the text layer, in order; exit 1 naming what is missing",
    )
    parser.add_argument(
        "--keywords",
        metavar="DRAFTS",
        help="report instead which of the posting's terms the page carries, which are held "
             "but not on it, and which are not held; a report, never an edit",
    )
    parser.add_argument("--abbr", default="", help="which draft, with --roundtrip or --keywords")
    parser.add_argument(
        "--require",
        choices=("pypdf",),
        help="read with this extractor only; exit %d when it is unavailable" % EXIT_NO_READER,
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.keywords:
        try:
            lines = keywords_pdf(args.pdf, args.keywords, args.abbr)
        except (VerificationError, OSError, ValueError, KeyError) as exc:
            print(f"Error: {args.pdf}: {exc}", file=sys.stderr)
            return 1
        for line in lines:
            print(line)
        return 0
    if args.roundtrip:
        try:
            found, checked, extractor = roundtrip_pdf(args.pdf, args.roundtrip, args.abbr)
        except (VerificationError, OSError, ValueError, KeyError) as exc:
            print(f"Error: {args.pdf}: {exc}", file=sys.stderr)
            return 1
        if found:
            print(f"Round trip: {args.pdf}: the text layer does not say what the draft put on "
                  f"the page (extractor: {extractor}):")
            for line in found:
                print(f"  - {line}")
            return 1
        print(f"Round trip: {args.pdf}: all {checked} lines the draft put on the page are in "
              f"the text layer, in order (extractor: {extractor})")
        return 0
    try:
        extractor, text, pages = verify_pdf(
            args.pdf,
            args.pages,
            args.min_chars,
            args.contains,
            dump_text=args.dump_text,
            require=args.require,
        )
    except ReaderUnavailable as exc:
        print(f"Skipped: {args.pdf}: {exc}", file=sys.stderr)
        return EXIT_NO_READER
    except VerificationError as exc:
        print(f"Error: {args.pdf}: {exc}", file=sys.stderr)
        return 1
    print(f"Verified {args.pdf} (extractor: {extractor}, pages: {pages})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
