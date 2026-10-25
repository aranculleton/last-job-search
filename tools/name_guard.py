#!/usr/bin/env python3
"""No real person's name reaches the app: every new name in it is an invented one.

The leak scan knows the maintainer's own people (their profile, their contacts and
applications, from a denylist built out of their repo). It cannot know the people a
real search turns up. On 2026-10-18 names from a real run's search results went into
a code comment, a test, a commit message and a pull request description, each written
by a session explaining a fix, and the leak scan passed every one.

This guard needs no list of real people. In what a change adds, and in the text that
goes with it (a pull request description, its commit messages), a full name the app
has never carried is reported, unless it is on the list of invented names and other
proper names (tools/name_guard_allow.txt), which a person adds to on purpose. A real
person found by a run is described ("a former chief executive", "a short surname"),
never named.

    python3 tools/name_guard.py diff [<base>]      # what HEAD adds against <base>
                                                   # (default origin/master)
    python3 tools/name_guard.py text <file>...     # a PR description, commit messages

A name is two to four capitalised words in a row, an initial allowed among them, at
least one of them a word the app has never contained. Exit 0 clean, 1 with names to
check, 2 usage. A finding prints the name: it is already in the change or the text
being checked, so the log adds nothing to what is public.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW = "tools/name_guard_allow.txt"
# Vendored or generated: never written by a session, and full of names that are
# not people (font names, package authors).
SKIP = (ALLOW, "tools/openroles/", "texmf/", ".agents/skills/*/cli/bun.lock")

# Capital and small letters beyond ASCII too: written as [A-Z][a-z], a name with one
# accented letter in it ("Zoë", "Núñez", "Łukasz") was never a word, so it passed.
_UP = "A-Z" + "".join(re.escape(chr(c)) for c in range(0xC0, 0x2000) if chr(c).isupper())
_LO = "a-z" + "".join(re.escape(chr(c)) for c in range(0xC0, 0x2000) if chr(c).islower())
_WORD = rf"[{_UP}][{_LO}][{_UP}{_LO}'’-]*"
_INITIAL = rf"[{_UP}]\."
# The shapes a name also comes in (2026-10-25): an O' or D' surname, straight apostrophe
# or curly (O'Fennick, D’Arcwell); a name in capitals, three letters or more with a vowel,
# so an acronym such as CSV or HTTP is no word, and only two words the app never held make
# one, since a line in capitals for emphasis is usually words it has; a particle between
# the words (van, de la); and more than one space, or a no-break space, between them.
_VOWELS = "".join(c for c in map(chr, range(0x41, 0x2000)) if c.isupper()
                  and unicodedata.normalize("NFD", c)[0] in "AEIOUY") + "ØÆŒ"
_NAMEWORD = rf"(?:[{_UP}]['’])?{_WORD}"
_CAPS = rf"(?=[{_UP}]*[{_VOWELS}])[{_UP}]{{3,}}"
_PARTICLES = ("van", "von", "der", "den", "ter", "ten", "de", "del", "della", "di", "da",
              "das", "dos", "du", "la", "le", "bin", "ibn")
_PARTICLE = "(?:" + "|".join(_PARTICLES) + ")"
_GAP = r"[ \u00a0]{1,3}"
# Words on one line: a run of two to four capitalised words, with initials and particles;
# or two to four words in capitals. A word in capitals inside an ordinary run is an
# acronym ("SAP ABAP", "Jobseeker API") and ends it, as before.
_RUN = re.compile(rf"(?<![\w.'’-])(?:(?:{_NAMEWORD}|{_INITIAL}){_GAP}(?:{_PARTICLE}{_GAP})"
                  rf"{{0,2}}){{1,3}}{_NAMEWORD}(?![\w'’-])")
_CAPS_RUN = re.compile(rf"(?<![\w.'’-])(?:{_CAPS}{_GAP}){{1,3}}{_CAPS}(?![\w'’-])")


def _git(*args: str, ok=(0,), env=None) -> str:
    r = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, encoding="utf-8",
                       errors="replace", env=dict(os.environ, **env) if env else None)
    if r.returncode not in ok:
        raise subprocess.CalledProcessError(r.returncode, r.args, r.stdout, r.stderr)
    return r.stdout


def _skipped(path: str) -> bool:
    import fnmatch
    return any(path == s or path.startswith(s) or fnmatch.fnmatch(path, s) for s in SKIP)


def vocabulary(ref: str = "HEAD") -> set[str]:
    """Every capitalised word the app holds at `ref`, plus the allow list's words."""
    out = _git("grep", "-h", "-o", "-I", "-E", "[A-Z][a-z][A-Za-z'-]*|[A-Z]{3,}", ref, "--",
               ".", *(f":!{s}" for s in SKIP))
    words = set(out.split())
    # git grep's pattern is ASCII, so it cuts "Montréal" to "Montr": the lines holding
    # anything else are read again here, with the guard's own word.
    wide = _git("grep", "-h", "-I", "-E", "[^ -~\t]", ref, "--", ".",
                *(f":!{s}" for s in SKIP), ok=(0, 1), env={"LC_ALL": "C"})
    words |= set(re.findall(_WORD, unicodedata.normalize("NFC", wide)))
    return words | allowed_words()


def allowed_words() -> set[str]:
    try:
        with open(os.path.join(ROOT, ALLOW), encoding="utf-8") as fh:
            lines = [ln.split("#", 1)[0] for ln in fh]
    except OSError:
        return set()
    return {w for ln in lines for w in ln.split()}


def names(text: str, known: set[str]) -> list[str]:
    """The runs of capitalised words in `text` with a word `known` does not hold."""
    out = []
    for line in unicodedata.normalize("NFC", str(text or "")).splitlines():
        for m in sorted([*_RUN.finditer(line), *_CAPS_RUN.finditer(line)],
                        key=lambda m: m.start()):
            words = [w for w in m.group(0).split() if not re.fullmatch(_INITIAL, w)
                     and w not in _PARTICLES]
            new = [w for w in words if not _known(w, known)]
            if len(words) >= 2 and len(new) >= (2 if m.re is _CAPS_RUN else 1):
                out.append(m.group(0))
    return out


def _known(word: str, known: set[str]) -> bool:
    """A word the app holds: as written, after an O' or D' (O'Kestrel is Kestrel's), or in
    capitals as it is written in ordinary case (DO NOT is Do Not)."""
    if word in known:
        return True
    if len(word) > 2 and word[1] in "'’" and word[2:] in known:
        return True
    return word.isupper() and word.capitalize() in known


def added(base: str) -> list[tuple[str, int, str]]:
    """(path, line, text) for every line this checkout adds against `base`: what is
    committed since the two parted, what is changed but not committed yet, and every line
    of a new file git would commit. Compared with HEAD alone, a check run before the commit
    (ci_local.sh) passed a file that CI, after it, failed."""
    fork = _git("merge-base", base, "HEAD").strip()
    diff = _git("diff", "--unified=0", "--no-color", "--no-ext-diff", fork, "--",
                ".", *(f":!{s}" for s in SKIP))
    out = _diff_lines(diff)
    for rel in _git("ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if not rel or _skipped(rel):
            continue
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                out += [(rel, n, t) for n, t in enumerate(fh.read().splitlines(), 1)]
        except (OSError, UnicodeDecodeError):
            continue
    return out


def _unquote(path: str) -> str:
    """A path as git writes it in a diff: as it is, or, holding a letter outside ASCII, a
    quote mark, a backslash or a control character, in double quotes with C escapes
    (`"b/notes/Zo\\303\\253 run.md"`, https://git-scm.com/docs/git-config#Documentation/
    git-config.txt-corequotePath). Those were read as no path at all, and every line of the
    file was dropped (2026-10-25)."""
    if not (len(path) >= 2 and path[0] == path[-1] == '"'):
        return path
    simple = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}
    raw, body, i = bytearray(), path[1:-1], 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt in "01234567" and re.fullmatch(r"[0-7]{3}", body[i + 1:i + 4]):
                raw.append(int(body[i + 1:i + 4], 8))
                i += 4
                continue
            raw.append(simple.get(nxt, ord(nxt)))
            i += 2
            continue
        raw += c.encode("utf-8")
        i += 1
    return raw.decode("utf-8", errors="replace")


def _diff_lines(diff: str) -> list[tuple[str, int, str]]:
    out, path, line = [], "", 0
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            # A path with a space in it ends with a tab, which git adds to mark its end.
            got = _unquote(ln[4:][:-1] if ln.endswith("\t") else ln[4:])
            path = got[2:] if got.startswith("b/") else ""
        elif ln.startswith("@@"):
            m = re.search(r"\+(\d+)", ln)
            line = int(m.group(1)) if m else 0
        elif ln.startswith("+") and path and not _skipped(path):
            out.append((path, line, ln[1:]))
            line += 1
    return out


def check_diff(base: str) -> list[str]:
    known = vocabulary(base)
    return [f"{p}:{n}: {name}" for p, n, text in added(base) for name in names(text, known)]


def check_text(paths: list[str]) -> list[str]:
    known = vocabulary("HEAD")
    out = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh.read().splitlines(), 1):
                out += [f"{os.path.basename(p)}:{n}: {name}" for name in names(line, known)]
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("diff", "text") or argv[0] == "text" and len(argv) < 2:
        print(__doc__.split("\n\n")[3])
        return 2
    found = check_diff(argv[1] if len(argv) > 1 else "origin/master") if argv[0] == "diff" \
        else check_text(argv[1:])
    for f in found:
        print(f)
    print(f"name_guard: {len(found)} name(s) the app has never carried"
          + (". Each is a real person to describe instead, or an invented name or a "
             f"product to add to {ALLOW}." if found else ""), file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
