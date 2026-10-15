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
      Lines starting "#" are comments.

Findings name the file, the line and WHICH denylist entry matched (by number),
never the token itself: CI logs of a public repo are public, and printing the
token would publish exactly what the scan exists to keep out.

Allowances (--allow FILE, or the app's own ALLOW below): "path-glob<TAB>regex".
Text matching the regex on a line of a matching path is blanked before the
token scan. The LICENSE copyright line is the one allowance the maintainer's
name gets.

Usage:
    python3 tools/leak_scan.py <tree> [--tokens FILE] [--allow FILE] [--show]
    --show prints the matched token (local use only, never in CI).
Exit 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

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
PLACEHOLDER_HANDLE = re.compile(r"^(?:example|your|yourname|your-name|your-handle|yourprofile|"
                                r"your-profile|handle|someone|name|person|example-[a-z-]+|"
                                r"[a-z-]+-example)$", re.I)

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
    # The app's own address is not a leak.
    ("**", r"github\.com/aranculleton/last-job-search(?![-\w])"),
    ("**", r"aranculleton/last-job-search(?![-\w])"),
    # Nor is the address of openroles, the app's employer-board reader published as its
    # own library and vendored in tools/openroles/.
    ("**", r"github\.com/aranculleton/openroles(?![-\w])"),
    ("**", r"aranculleton/openroles(?![-\w])"),
    # Unmodified TeX Live packages carry their CTAN authors' public addresses.
    ("texmf/**", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+"),
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
    out = []
    for n, raw in enumerate(lines, 1):
        t = raw.strip()
        if not t or t.startswith("#"):
            continue
        exact = t.startswith("=")
        pat = re.compile(_token_regex(t[1:] if exact else t), 0 if exact else re.I)
        out.append((pat, n))
    return out


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
        text = data.decode("utf-8", errors="replace")
        rules = [rx for g, rx in allow if g.match(rel)]
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
            for pat, n in file_tokens:
                m = pat.search(line)
                if m:
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
    for pat, n in tokens:
        if _GAP not in pat.pattern:
            continue                   # one-word entries cannot straddle a line break
        for m in pat.finditer(text):
            first = max(i for i, st in enumerate(starts) if st <= m.start())
            last = max(i for i, st in enumerate(starts) if st <= m.end() - 1)
            if first != last:
                out.append(f"{rel}:{first + 1}: denylist entry {n} (across a line break)"
                           + (f" ({m.group(0)})" if show else ""))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tree")
    ap.add_argument("--tokens", help="denylist file, one token per line")
    ap.add_argument("--allow", help="extra allowances, path-glob<TAB>regex per line")
    ap.add_argument("--show", action="store_true", help="print matched text (never in CI)")
    ap.add_argument("--git", action="store_true",
                    help="scan only what git would commit (tracked, and new files not ignored)")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.tree):
        print(f"leak_scan: no such directory {a.tree}", file=sys.stderr)
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
