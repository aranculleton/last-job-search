#!/usr/bin/env python3
"""The person this copy of the app works for: one loader, by path.

Every fact about the candidate (name, contact line, work history, bullets,
skills, market, preferences, voice) lives in their profile directory, and no
tool hardcodes one. This module is the only way in.

Where the profile is:
    profile/ at the repo root, or wherever LJS_PROFILE points (a path, absolute
    or relative to the repo root). The app's own tests set LJS_PROFILE to
    profile.example/, a fictional person, so they run with nobody's real data.

What happens with no profile:
    NoProfile, whose message says to run /setup. There is deliberately NO
    fallback to the example person. A stranger who skipped /setup must get a
    loud error, never a resume under a fictional name, and never the example's
    market rules silently applied to their search.

Why by path and not `import profile`:
    `profile` is a standard-library module (the profiler), so a package of that
    name would shadow it or be shadowed by it depending on sys.path order. Each
    profile file is loaded from its path with importlib under a private module
    name instead.

Usage:
    import person
    person.module("bullets").LIB          # profile/bullets.py
    person.data("person")["identity"]     # profile/person.json
    person.get("identity.email")          # one dotted value from person.json
    person.path("01-candidate-profile.md")

    python3 tools/person.py dir           # the profile directory in use
    python3 tools/person.py get identity.email
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import python_floor  # noqa: E402

python_floor.require()

# The tools a person installed where a non-login shell does not look (MacTeX's
# /Library/TeX/texbin, Bun's ~/.bun/bin): on PATH for every tool, tools/local_path.py.
import local_path  # noqa: E402

local_path.extend()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = "LJS_PROFILE"
DEFAULT = "profile"

# Another chat may hold the profile, or be writing it: look before starting again (2026-10-25).
SETUP_HINT = ("no profile here: run `python3 tools/place.py state` first (another chat may hold "
              "it or be writing it), and run /setup only if it finds none")


class NoProfile(RuntimeError):
    """The profile directory, or a file a tool needs from it, does not exist."""


def directory() -> str:
    """The profile directory in use. Raises NoProfile if it does not exist."""
    p = os.environ.get(ENV) or DEFAULT
    if not os.path.isabs(p):
        p = os.path.join(ROOT, p)
    p = os.path.normpath(p)
    if not os.path.isdir(p):
        raise NoProfile(f"{SETUP_HINT} (looked for {p})")
    return p


def exists(*parts: str) -> bool:
    """Whether a profile is in place (and, given parts, whether that file is)."""
    try:
        d = directory()
    except NoProfile:
        return False
    return os.path.exists(os.path.join(d, *parts)) if parts else True


def path(*parts: str) -> str:
    """A path inside the profile directory. The file need not exist."""
    return os.path.join(directory(), *parts)


def file(key: str, default: str) -> str:
    """One of the profile's documents, by its person.json `files` key.

    `files` maps a key (candidate_profile, evaluation, summary) to a path
    relative to the profile directory, so a profile whose documents still live
    elsewhere can point at them; the default is a name inside the profile.
    """
    return os.path.normpath(path(get(f"files.{key}", default)))


def _need(name: str) -> str:
    f = path(name)
    if not os.path.isfile(f):
        raise NoProfile(f"the profile has no {name} ({f}): run /setup for that part, or add it")
    return f


_modules: dict = {}
_data: dict = {}


def module(name: str):
    """Load profile/<name>.py by path and return it. Cached per file."""
    f = _need(name + ".py")
    if f not in _modules:
        spec = importlib.util.spec_from_file_location(f"ljs_profile_{name}", f)
        mod = importlib.util.module_from_spec(spec)
        # No compiled copy beside the profile: profile/__pycache__ is one more thing a forced
        # add commits, and these files are read once a run.
        was, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.dont_write_bytecode = was
        _modules[f] = mod
    return _modules[f]


def data(name: str = "person"):
    """Load profile/<name>.json and return it. Cached per file."""
    f = _need(name + ".json")
    if f not in _data:
        with open(f, encoding="utf-8") as fh:
            _data[f] = json.load(fh)
    return _data[f]


_MISSING = object()


def get(dotted: str, default=_MISSING):
    """One value from person.json by dotted key, e.g. "identity.email"."""
    node = data("person")
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif default is not _MISSING:
            return default
        else:
            raise KeyError(f"person.json has no {dotted!r}")
    return node


STATE_ENV = "LJS_STATE"


def state(*parts: str) -> str:
    """A path to the search's state: the tracker, the network CSVs, documents/.

    State lives at the repo root, beside the profile rather than inside it, so
    a person's tracker and contact book stay where they have always been.
    LJS_STATE moves the root, which is how the app's tests point the state
    tools at the example person's small fake tracker and contact book.
    """
    root = os.environ.get(STATE_ENV) or ROOT
    if not os.path.isabs(root):
        root = os.path.join(ROOT, root)
    return os.path.join(os.path.normpath(root), *parts)


def main_checkout() -> str | None:
    """The repository's main working folder when this one is a linked git worktree, else
    None. A local chat works in a worktree of its own (CLAUDE.md, "On the person's own
    computer"), and a worktree has none of the ignored files the main folder holds."""
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "--git-dir", "--git-common-dir"], cwd=ROOT,
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    got = r.stdout.split() if r.returncode == 0 else []
    if len(got) != 2:
        return None
    here, common = (os.path.realpath(os.path.join(ROOT, g)) for g in got)
    if here == common:
        return None
    main = os.path.dirname(common)
    return main if os.path.isdir(main) and main != os.path.realpath(ROOT) else None


def local_state(*parts: str) -> str:
    """A state file git does not carry (a connections export, a sync cursor), from this
    folder, or from the main checkout when this is a worktree that lacks it. In a worktree
    the connections export was simply not there, and a run found nothing, silently."""
    here = state(*parts)
    if os.path.exists(here) or os.environ.get(STATE_ENV):
        return here
    main = main_checkout()
    there = os.path.join(main, *parts) if main else ""
    return there if there and os.path.exists(there) else here


def text(name: str) -> str:
    """The contents of a text file in the profile (markdown, a phrase list)."""
    with open(_need(name), encoding="utf-8") as fh:
        return fh.read()


# Where US Letter is the standard paper. Everywhere else uses A4, which is also
# the default when the country is not known.
LETTER_COUNTRIES = frozenset({
    "US", "CA", "MX", "CL", "CO", "CR", "DO", "GT", "PA", "PH", "PR", "VE", "SV",
    "NI", "BZ",
})


def country() -> str:
    """The person's country as an ISO 3166 alpha-2 code, upper case, or "".

    identity.country in person.json; failing that, search.py PORTAL_COUNTRY,
    which every profile that scrapes already sets.
    """
    c = get("identity.country", "") or ""
    if not c:
        try:
            c = getattr(module("search"), "PORTAL_COUNTRY", "") or ""
        except NoProfile:
            c = ""
    return str(c).strip().upper()


def paper(kind: str = "resume") -> str:
    """The LaTeX paper option for a document: "letterpaper" or "a4paper".

    The country decides (US Letter across most of the Americas, A4 everywhere
    else), so nobody has to know which their market uses. An explicit setting
    wins: documents.letter_paper for the letter, then documents.paper for both.
    """
    if kind == "letter" and get("documents.letter_paper", ""):
        return get("documents.letter_paper")
    if get("documents.paper", ""):
        return get("documents.paper")
    return "letterpaper" if country() in LETTER_COUNTRIES else "a4paper"


def reset() -> None:
    """Forget cached files. Tests that switch LJS_PROFILE call this."""
    _modules.clear()
    _data.clear()


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print("usage: python3 tools/person.py dir | get <dotted.key>")
        return 0
    try:
        if argv[:1] == ["dir"]:
            print(directory())
            return 0
        if len(argv) == 2 and argv[0] == "get":
            v = get(argv[1])
            print(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
            return 0
    except (NoProfile, KeyError) as e:
        print(f"person: {e}", file=sys.stderr)
        return 1
    print(__doc__.split("Usage:")[1], file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
