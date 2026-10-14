#!/usr/bin/env python3
"""Verify that a generated PDF has the expected pages and extractable text.

Text-layer extraction tries pypdf (BSD, optional `pip install pypdf`) first,
then Poppler `pdftotext` if pypdf is missing, raises, or returns zero
extractable characters. Poppler remains the fallback.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


class VerificationError(Exception):
    """Raised when a generated PDF does not satisfy its checks."""


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
            "Windows: choco install poppler)"
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


def _extract_pdftotext(pdf_path):
    text = run_tool(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf_path), "-"])
    # Always call pdfinfo here so the fallback path returns a page count
    # even when the caller did not request --pages (same Poppler package).
    pages = parse_page_count(run_tool(["pdfinfo", str(pdf_path)]))
    return text, pages


def extract_text_layer(pdf_path):
    """Extract ATS-readable text. Returns (text, pages, extractor_name)."""
    pypdf_result = _extract_pypdf(pdf_path)
    if pypdf_result is not None:
        text, pages = pypdf_result
        return text, pages, "pypdf"
    text, pages = _extract_pdftotext(pdf_path)
    return text, pages, "pdftotext"


def verify_pdf(pdf_path, expected_pages=None, min_chars=1, required_text=(), dump_text=None):
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise VerificationError(f"PDF does not exist: {pdf_path}")

    extracted_text, actual_pages, extractor = extract_text_layer(pdf_path)

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
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        extractor, text, pages = verify_pdf(
            args.pdf,
            args.pages,
            args.min_chars,
            args.contains,
            dump_text=args.dump_text,
        )
    except VerificationError as exc:
        print(f"Error: {args.pdf}: {exc}", file=sys.stderr)
        return 1
    print(f"Verified {args.pdf} (extractor: {extractor}, pages: {pages})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
