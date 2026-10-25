#!/usr/bin/env python3
"""Fail if a tree holds anything that identifies a person: the app's last gate.

The app is public and its history is permanent, so nothing may reach it that
names its maintainer, his contacts, his employers or his applications. This
scan runs on the exact tree about to be pushed, before every push (branches
too, because a public repo's branches are public), and again in the app's CI.

It checks two kinds of thing.

  Structure (needs no list, catches anyone's data):
    - a personal path (tools/personal_paths.py) present in the tree
    - an email address outside the reserved example domains
    - a phone number outside the ranges reserved for fiction
    - a LinkedIn profile URL with a real-looking handle
    - a binary file that is not a vendored font or an allowlisted example

  Denylist (the specific people and organizations):
    - one token per line, from --tokens FILE and/or the LJS_LEAK_TOKENS
      environment variable (how CI receives it, as an encrypted Actions
      secret). The list itself is personal data: it never lives in the app.
      A plain line matches case-insensitively on word boundaries; a line
      starting "=" matches case-sensitively ("=AB" must not hit "ab").
      Lines starting "#" are comments. An entry with accents matches without
      them too: "Zoë" in the list finds "zoe-quillfeather" in a filename.

Findings name the file, the line and WHICH denylist entry matched (by number),
never the token itself: CI logs of a public repo are public, and printing the
token would publish exactly what the scan exists to keep out.

Allowances (--allow FILE, or the app's own ALLOW below): "path-glob<TAB>regex".
Text matching the regex on a line of a matching path is blanked before the
token scan. The LICENSE copyright line is the one allowance the maintainer's
name gets.

Usage:
    python3 tools/leak_scan.py <tree> [--tokens FILE] [--allow FILE] [--show]
    python3 tools/leak_scan.py --text <file>... [--tokens FILE]   # a PR description,
                                                                  # commit messages
    --show prints the matched token (local use only, never in CI).
Exit 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from personal_paths import _regex, is_personal  # noqa: E402

# Reserved for documentation by RFC 2606 / 6761, plus the noreply addresses
# that appear in commit trailers and bot configuration.
SAFE_EMAIL_DOMAINS = (
    "example.com", "example.org", "example.net", "example.co.uk", "example.ca",
    "users.noreply.github.com", "noreply.github.com", "anthropic.com",
)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b")

# An international number: "+" then 10 to 15 digits, spaces, dots or hyphens.
# Fiction ranges are allowed: Ofcom's 07700 900000-900999 drama range and the
# NANP 555-0100 to 555-0199 block.
PHONE = re.compile(r"\+\d[\d .()-]{8,20}\d")
FICTION_PHONE = re.compile(r"^\+?44\s*\(?0?\)?\s*7700\s*900\s*\d{3}$|555[ .-]?01\d\d$|"
                           r"12345678")

LINKEDIN = re.compile(r"linkedin\.com/in/([A-Za-z0-9_%-]+)", re.I)
# An example handle may carry an accented letter percent-encoded ("example-ren%C3%A9e"):
# its two hex digits are the letter, not a real profile's number.
PLACEHOLDER_HANDLE = re.compile(r"^(?:example|your|yourname|your-name|your-handle|yourprofile|"
                                r"your-profile|handle|someone|name|person|"
                                r"example-(?:[a-z-]|%[0-9a-f]{2})+|"
                                r"(?:[a-z-]|%[0-9a-f]{2})+-example)$", re.I)

# Binary files the app may carry: vendored fonts and TeX packages, and the two
# compiled example documents, which hold only placeholders.
BINARY_OK = tuple(_regex(g) for g in (
    "cover_letters/OpenFonts/**", "texmf/**", "**/*.ttf", "**/*.otf", "**/*.pfb",
    "**/*.tfm", "**/*.enc", "**/*.vf",
))

# The app's own allowances. Kept tiny on purpose: every line is a decision.
ALLOW = (
    # The one permitted mention of the maintainer: the copyright credit.
    ("LICENSE", r"^Copyright \(c\) \d{4}(?:-\d{4})? .*$"),
    # The app's own address is not a leak, in any letter case: GitHub reads owner and
    # repository names without regard to case, so a test that the app is still the app in
    # capitals names nobody new (2026-10-25). Only the whole address is set aside.
    ("**", r"(?i)github\.com/aranculleton/last-job-search(?![-\w])"),
    ("**", r"(?i)aranculleton/last-job-search(?![-\w])"),
    # Nor is the address of openroles, the app's employer-board reader published as its
    # own library and vendored in tools/openroles/.
    ("**", r"(?i)github\.com/aranculleton/openroles(?![-\w])"),
    ("**", r"(?i)aranculleton/openroles(?![-\w])"),
    # Unmodified TeX Live packages carry their CTAN authors' public addresses.
    ("texmf/**", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+"),
    # The families of interchangeable tools name software, not employers: only each
    # ("Product", r"pattern") entry is set aside, and every comment and other line in
    # the file is still read.
    ("tools/bridges.py", r'\("[^"\n]{1,40}", r"[^"\n]*"\)'),
)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "venv"}


def _is_binary(data: bytes) -> bool:
    return b"\0" in data[:8192]


def load_tokens(path: str | None) -> list[tuple[re.Pattern, int]]:
    lines: list[str] = []
    if path:
        with open(path, encoding="utf-8") as fh:
            lines += fh.read().splitlines()
    lines += os.environ.get("LJS_LEAK_TOKENS", "").splitlines()
    return tokens_from(lines)


def tokens_from(lines: list[str]) -> list[tuple[re.Pattern, int]]:
    """The denylist's patterns from its lines, each numbered by its line: what a finding's
    "denylist entry N" names."""
    out = []
    for n, raw in enumerate(lines, 1):
        t = raw.strip()
        if not t or t.startswith("#"):
            continue
        exact = t.startswith("=")
        body = unicodedata.normalize("NFC", t[1:] if exact else t)
        for form in dict.fromkeys((body, plain(body))):
            out.append((re.compile(_token_regex(form), 0 if exact else re.I), n))
    return out


# A name loses its accents on the way into a filename, a slug or a contact id ("Zoë
# Quillfeather" becomes zoe_quillfeather, "Søren" soren), and an entry matched only as
# the list held it. Letters with no accent to strip are spelled out. One way only: a
# plain entry does not find an accented word, since the app's invented "Renée" would
# then fail the scan of everybody called Renee.
_SPELLED = str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "æ": "ae", "Æ": "AE",
                          "œ": "oe", "Œ": "OE", "ß": "ss", "đ": "d", "Đ": "D", "ð": "d",
                          "Ð": "D", "þ": "th", "Þ": "Th", "ı": "i"})


def plain(text: str) -> str:
    """`text` with its accents taken off, the way a slug or a filename writes it."""
    if text.isascii():
        return text
    decomposed = unicodedata.normalize("NFKD", text.translate(_SPELLED))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# A name reaches a file in more shapes than the way it is written: in a filename
# (First_Last_CV.pdf), a slug (first-last), a handle (firstlast) or an email's
# local part (first.last). So an entry's edges are any non-alphanumeric, not \w,
# which counts "_" as part of a word and let "First_Last_CV" through; and the
# gaps between its words match a space, "_", "-", "." or nothing at all.
_GAP = r"[\s_.\-]*"


def _token_regex(t: str) -> str:
    words = [re.escape(w) for w in t.split()]
    return r"(?<![A-Za-z0-9])" + _GAP.join(words) + r"(?![A-Za-z0-9])"


def load_allow(path: str | None) -> list[tuple[re.Pattern, re.Pattern]]:
    rules = list(ALLOW)
    if path:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line and not line.startswith("#") and "\t" in line:
                    g, rx = line.split("\t", 1)
                    rules.append((g, rx))
    return [(_regex(g), re.compile(rx)) for g, rx in rules]


def _key(pat: re.Pattern) -> str:
    """An entry's longest word, lowercased. Every word of an entry is in any
    text it matches, so a file whose lowercased text lacks this word cannot
    match the entry, and a substring test costs almost nothing."""
    body = pat.pattern[len(r"(?<![A-Za-z0-9])"):-len(r"(?![A-Za-z0-9])")]
    words = [re.sub(r"\\(.)", r"\1", w) for w in body.split(_GAP)]
    return max(words, key=len).lower()


def _walk(tree: str):
    for dp, dns, fns in os.walk(tree):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
        for fn in sorted(fns):
            yield os.path.join(dp, fn)


def _committable(tree: str):
    """What git would commit: tracked files and new ones it does not ignore.

    A working tree holds build output (compiled PDFs, lock files) that is
    ignored and can never be pushed; scanning it reports leaks that are not.
    """
    out = subprocess.run(["git", "-C", tree, "ls-files", "-z", "--cached", "--others",
                          "--exclude-standard"], capture_output=True, check=True).stdout
    for rel in sorted(set(out.decode("utf-8").split("\0")) - {""}):
        full = os.path.join(tree, rel)
        if os.path.isfile(full):
            yield full


def scan(tree: str, tokens, allow, show: bool = False, git: bool = False) -> list[str]:
    findings: list[str] = []
    keyed = [(_key(pat), (pat, n)) for pat, n in tokens]
    for full in (_committable(tree) if git else _walk(tree)):
        rel = os.path.relpath(full, tree).replace(os.sep, "/")
        if is_personal(rel):
            findings.append(f"{rel}: personal path (tools/personal_paths.py)")
            continue
        with open(full, "rb") as fh:
            data = fh.read()
        if _is_binary(data):
            if not any(r.match(rel) for r in BINARY_OK):
                findings.append(f"{rel}: binary file that cannot be scanned and is not allowlisted")
            continue
        findings += _scan_text(rel, data.decode("utf-8", errors="replace"),
                               [rx for g, rx in allow if g.match(rel)], keyed, show)
    return findings


def scan_text(paths: list[str], tokens, show: bool = False) -> list[str]:
    """The same checks on text that never sits in the tree: a pull request description,
    commit messages. A public repo's PR descriptions and history are as public as its
    files, and a name written there once (2026-10-18) was never scanned."""
    keyed = [(_key(pat), (pat, n)) for pat, n in tokens]
    # The allowances that hold anywhere (the app's own address and openroles'), so a PR
    # or a commit that links the app is not a leak; nothing tied to one file applies.
    anywhere = [re.compile(rx) for g, rx in ALLOW if g == "**"]
    out: list[str] = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as fh:
            out += _scan_text(os.path.basename(p), fh.read(), anywhere, keyed, show)
    return out


def _scan_text(rel: str, text: str, rules, keyed, show: bool) -> list[str]:
    findings: list[str] = []
    # One way of writing each accented letter, the list's: "e" and a combining accent is "é".
    text = unicodedata.normalize("NFC", text)
    # Only the entries whose longest word is somewhere in the file run
    # at all: a handful, against 1,200 on every line.
    low = text.lower()
    file_tokens = [t for k, t in keyed if k in low]
    kept = []                      # each line after the allowances, for the joined pass
    for ln, line in enumerate(text.splitlines(), 1):
        for rx in rules:
            line = rx.sub(" ", line)
        kept.append(line)
        for m in EMAIL.finditer(line):
            dom = m.group(1).lower()
            if not any(dom == d or dom.endswith("." + d) for d in SAFE_EMAIL_DOMAINS):
                findings.append(f"{rel}:{ln}: email address" + (f" {m.group(0)}" if show else ""))
        for m in PHONE.finditer(line):
            digits = re.sub(r"\D", "", m.group(0))
            if 10 <= len(digits) <= 15 and not FICTION_PHONE.search(m.group(0).strip()):
                findings.append(f"{rel}:{ln}: phone number" + (f" {m.group(0)}" if show else ""))
        for m in LINKEDIN.finditer(line):
            h = m.group(1)
            if not PLACEHOLDER_HANDLE.match(h) and not h.startswith(("<", "%", "[")):
                findings.append(f"{rel}:{ln}: LinkedIn profile" + (f" {h}" if show else ""))
        hit = set()                # an entry's forms report its line once
        for pat, n in file_tokens:
            m = None if n in hit else pat.search(line)
            if m:
                hit.add(n)
                findings.append(f"{rel}:{ln}: denylist entry {n}" + (f" ({m.group(0)})" if show else ""))
    findings += _across_lines(rel, kept, file_tokens, show)
    return findings


# A comment wraps where the editor wraps it, so "a Harbour\n# Freight one"
# carries a two-word name no single line holds. The joined pass reads the file as
# one line, each line's indentation and comment marker taken off, and reports a
# multi-word entry only where its match spans a line break (the line pass already
# reported the rest).
_LEAD = re.compile(r"^\s*(?:#+|//+|/?\*+|>+|--+|;+)?\s*")


def _across_lines(rel: str, lines: list[str], tokens, show: bool) -> list[str]:
    out, joined, starts = [], [], []
    pos = 0
    for line in lines:
        piece = _LEAD.sub("", line).rstrip()
        starts.append(pos)
        joined.append(piece)
        pos += len(piece) + 1
    text = " ".join(joined)
    done = set()                   # two forms of an entry, one match: reported once
    for pat, n in tokens:
        if _GAP not in pat.pattern:
            continue                   # one-word entries cannot straddle a line break
        for m in pat.finditer(text):
            first = max(i for i, st in enumerate(starts) if st <= m.start())
            last = max(i for i, st in enumerate(starts) if st <= m.end() - 1)
            if first != last and (n, m.start()) not in done:
                done.add((n, m.start()))
                out.append(f"{rel}:{first + 1}: denylist entry {n} (across a line break)"
                           + (f" ({m.group(0)})" if show else ""))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tree", nargs="?")
    ap.add_argument("--text", nargs="+", metavar="FILE",
                    help="scan these files as text instead of a tree: a PR description, "
                         "commit messages")
    ap.add_argument("--tokens", help="denylist file, one token per line")
    ap.add_argument("--allow", help="extra allowances, path-glob<TAB>regex per line")
    ap.add_argument("--show", action="store_true", help="print matched text (never in CI)")
    ap.add_argument("--git", action="store_true",
                    help="scan only what git would commit (tracked, and new files not ignored)")
    a = ap.parse_args(argv)
    if a.text:
        tokens = load_tokens(a.tokens)
        findings = scan_text(a.text, tokens, show=a.show)
        for f in findings:
            print(f)
        print(f"leak_scan: {len(findings)} finding(s) in {len(a.text)} text file(s); "
              f"{len(tokens)} denylist entries checked", file=sys.stderr)
        return 1 if findings else 0
    if not a.tree or not os.path.isdir(a.tree):
        print(f"leak_scan: no such directory {a.tree or '(none given)'}", file=sys.stderr)
        return 2
    tokens = load_tokens(a.tokens)
    findings = scan(a.tree, tokens, load_allow(a.allow), show=a.show, git=a.git)
    for f in findings:
        print(f)
    print(f"leak_scan: {len(findings)} finding(s); {len(tokens)} denylist entries checked",
          file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
