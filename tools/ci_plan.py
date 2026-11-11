#!/usr/bin/env python3
"""What a CI run needs to run, decided once, in one place a test can hold.

.github/workflows/ci.yml starts with a quick job that runs this and hands its answer to the
jobs after it:

    python3 tools/ci_plan.py lane [--out FILE]        ci.yml: docs_only, tests
    python3 tools/ci_plan.py part 2/3 [file ...]      the test files the second of three
                                                      runners takes (every tests/test_*.py
                                                      when none are named)
    python3 tools/ci_plan.py verdict                  ci.yml's Fast checks: every job this
                                                      change needed ran and passed

`lane` reads the event from the environment, as the workflow sets it: EVENT
(github.event_name) and BASE (the commit the change is measured from). It prints key=value
lines and, with --out, appends them to that file ($GITHUB_OUTPUT). `verdict` reads NEEDS,
the workflow's toJSON(needs).

Every doubt runs more, never less: no usable base, a git error or a file this does not know
runs the whole suite. A wrong "docs only" is worse than a slow run.
Standard library only, and Python 3.9 (tools/python_floor.py), like every tool here.
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)

# ------------------------------------------------------------------ the docs-only lane

# A change made only of these files skips the suite, the Python 3.9 leg and the page's
# browser tests, and runs the tests that read them instead (`tests_for`). Each is read by
# people or by a builder, never by a person's chat or a tool while it works. An allowlist,
# on purpose: a file nobody has placed here runs everything.
DOCS_ONLY = {
    "CHANGELOG.md": "what changed, for people. tools/release.py publishes it and a person's "
                    "update quotes its first line, so the tests that read it run",
    "docs/NEXT_BUILDER.md": "the notes one builder leaves the next",
    "docs/images/**": "the README's pictures; the tests that check the README names them run",
    "README.md": "the app's front page on GitHub; the tests of what checks it run",
    "MAINTAINING.md": "how the app is built, read by a builder; a person's chat never "
                      "changes the app, so never reads it",
    "CONTRIBUTING.md": "how to send a change, for people",
    "SECURITY.md": "how to report a security problem, for people",
    ".github/PULL_REQUEST_TEMPLATE.md": "what a pull request description starts from",
}
# Never docs only, whatever is added above: what a chat or a tool reads while it works
# (instructions, skills, the page, the tools, the example person) and the checks themselves.
NEVER_DOCS = (".claude/", ".agents/", "templates/", "tools/", "tests/", "profile.example/",
              "automation/", "plugin/", ".github/workflows/", "RUNBOOK.md", "CLAUDE.md",
              "SETUP.md", "COMPUTER.md", "START_HERE.md", "HELP.md", "AGENTS.md")

# A test that lists files (the whole tree, a folder, every Markdown file) may read a changed
# document without naming it, so every such test runs in the docs-only lane.
_LISTS_FILES = re.compile(r"repo_files\.tracked|ls-files|ls-tree|os\.walk\(|\.rglob\(|glob\("
                          r"|iterdir\(|listdir\(")
# The scans that read every file whatever its name: their tests run too.
_SCANS = ("leak_scan", "name_guard", "security_guards", "lint_skills")
# What can read a file by name: code and data, never another document.
_READS = re.compile(r"\.(?:py|sh|js|json|ya?ml|toml|ps1)\Z")


def _glob(pattern: str) -> re.Pattern:
    """A path pattern as GitHub writes one: `*` within a folder, `**` across folders."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def is_docs(path: str) -> bool:
    """True when `path` is a document no chat or tool reads while it works."""
    if path.startswith(NEVER_DOCS) or path in NEVER_DOCS:
        return False
    return any(_glob(p).match(path) for p in DOCS_ONLY)


def docs_only(paths: list[str]) -> bool:
    """True when the change is something, and every file of it a document. Nothing changed
    is not docs only: it runs everything."""
    return bool(paths) and all(is_docs(p) for p in paths)


def _tracked(root: str) -> list[str]:
    """The app's files git tracks under `root`, each name whole, never a person's own
    (tools/personal_paths.py): this reads every file it lists."""
    sys.path.insert(0, TOOLS)
    import personal_paths
    got = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    if got.returncode != 0:
        return []
    return [f for f in got.stdout.split("\0") if f and not personal_paths.is_personal(f)]


def _read(root: str, rel: str) -> str:
    try:
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _names(path: str) -> set[str]:
    """How a test may name a file: its path, its file name, its name without the ending
    (NEXT_BUILDER, CHANGELOG) and, deeper than one folder, its folder (docs/images)."""
    base = posixpath.basename(path)
    stem = posixpath.splitext(base)[0]
    out = {path, base}
    if len(stem) >= 6:
        out.add(stem)
    folder = posixpath.dirname(path)
    if "/" in folder:
        out.add(folder)
    return out


def _mentions(text: str, rel: str) -> bool:
    """`text` names the file `rel`, or imports it as a module."""
    base = posixpath.basename(rel)
    stem = posixpath.splitext(base)[0]
    return base in text or re.search(r"\b" + re.escape(stem) + r"\b", text) is not None


def tests_for(paths: list[str], root: str = ROOT,
              tracked: list[str] | None = None) -> list[str]:
    """The test files that read any of `paths`: each that names one (`_names`), each that
    names code or data which names one as a string (one step removed: docs/rule_map.json
    names MAINTAINING.md, so the test of the rule map runs), each that lists files, and the
    tests of the scans that read every file."""
    tracked = _tracked(root) if tracked is None else tracked
    tests = sorted(f for f in tracked if f.startswith("tests/test_") and f.endswith(".py")
                   and "/" not in f[len("tests/"):])
    text = {t: _read(root, t) for t in tests}
    readers = set()
    for rel in tracked:
        if not _READS.search(rel) or rel.startswith(("tests/", "profile.example/")):
            continue
        body = _read(root, rel)
        for p in paths:
            if rel == p:
                continue
            # The file as a string of its own: its path, or its name alone where code
            # joins the folders (os.path.join(ROOT, "docs", "NEXT_BUILDER.md")). Never
            # "documents/README.md" for README.md.
            said = "|".join(re.escape(x) for x in {p, posixpath.basename(p)})
            if re.search(r"[\"'](?:" + said + r")[\"']", body) or (
                    rel.endswith((".yml", ".yaml"))
                    and re.search(r"(?<![\w/.-])" + re.escape(p) + r"(?![\w.-])", body)):
                readers.add(rel)
    picked = []
    for t in tests:
        s = text[t]
        if (any(n in s for p in paths for n in _names(p))
                or any(_mentions(s, r) for r in readers)
                or _LISTS_FILES.search(s)
                or any(re.search(r"\b" + scan + r"\b", s) for scan in _SCANS)):
            picked.append(t)
    return picked


def changed(base: str, root: str = ROOT, merge: bool = False) -> list[str] | None:
    """The files changed since `base`, None when that cannot be known. A rename counts as
    both of its names (a tool moved under docs/ is still a tool changed). With `merge`, a
    pull request's merge commit also counts against its own first parent, the base as it
    is now, in case the base the event names is older."""
    if not base or set(base) == {"0"}:
        return None

    def git(*args):
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")

    if git("cat-file", "-e", base + "^{commit}").returncode != 0:
        return None
    # -z: each name whole, never quoted (git quotes a name with an accent by default).
    got = git("diff", "--name-only", "--no-renames", "-z", base, "HEAD")
    if got.returncode != 0:
        return None
    files = {f for f in got.stdout.split("\0") if f}
    if merge and len(git("rev-list", "--parents", "-n", "1", "HEAD").stdout.split()) == 3:
        mine = git("diff", "--name-only", "--no-renames", "-z", "HEAD^1", "HEAD")
        if mine.returncode != 0:
            return None
        files |= {f for f in mine.stdout.split("\0") if f}
    return sorted(files)


def lane(event: str, base: str, root: str = ROOT) -> dict:
    """ci.yml's plan. The docs-only lane is for pull requests alone: master's own run after
    a merge is always the whole suite, so a test the lane did not pick is still run within
    minutes of the merge, before anything is released."""
    if event == "workflow_dispatch":
        return {"docs_only": "false", "tests": "", "why": "a run by hand runs everything"}
    files = changed(base, root, merge=event == "pull_request")
    if files is None:
        return {"docs_only": "false", "tests": "",
                "why": "no usable base to compare with, so everything runs"}
    if event == "pull_request" and docs_only(files):
        return {"docs_only": "true", "tests": " ".join(tests_for(files, root)),
                "why": f"{len(files)} documents changed and nothing else"}
    return {"docs_only": "false", "tests": "", "why": f"{len(files)} files changed"}


# ------------------------------------------------------------------ a split suite

def every_test(root: str = ROOT) -> list[str]:
    """Every test file pytest collects from tests/, as os.path.join("tests", name)."""
    tests = os.path.join(root, "tests")
    return sorted(os.path.join("tests", f) for f in os.listdir(tests)
                  if f.startswith("test_") and f.endswith(".py"))


def part(shard: str, files: list[str] | None = None, root: str = ROOT) -> list[str] | None:
    """The files one runner takes when `files` (every test file when None) are split
    ("2/3": the second of three). Each file goes, largest first, to the part with the least
    so far, so every runner splits them the same way and each file is in exactly one part.
    None for an empty or malformed shard."""
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", shard or "")
    if not m or not 1 <= int(m.group(1)) <= int(m.group(2)):
        return None
    k, n = int(m.group(1)), int(m.group(2))
    files = sorted(set(files)) if files else every_test(root)
    size = {f: os.path.getsize(os.path.join(root, f)) for f in files}
    loads, mine = [0] * n, []
    for f in sorted(files, key=lambda f: (-size[f], f)):
        i = loads.index(min(loads))
        loads[i] += size[f]
        if i == k - 1:
            mine.append(f)
    return sorted(mine)


# ------------------------------------------------------------------ Fast checks

# ci.yml's jobs that Fast checks waits for, each by its id.
FAST_NEEDS = ("plan", "checks", "suite", "python-floor", "page", "docs", "latex-smoke")


def verdict(needs: dict) -> tuple[bool, list[str]]:
    """Whether every job this change needed ran and passed. A job may be skipped only when
    the plan says it was not needed: a skipped suite on a change that was not docs only is a
    failure, as is a plan with no answer."""
    said, ok = [], True
    result = {j: (needs.get(j) or {}).get("result", "missing") for j in FAST_NEEDS}
    plan = (needs.get("plan") or {}).get("outputs") or {}
    docs = plan.get("docs_only")
    tex = ((needs.get("checks") or {}).get("outputs") or {}).get("latex")
    if result["plan"] != "success" or docs not in ("true", "false"):
        return False, [f"plan: {result['plan']}, docs_only={docs!r}: "
                       "no answer on what this change needs"]
    if result["checks"] == "success" and tex not in ("true", "false"):
        return False, [f"checks: latex={tex!r}: no answer on whether LaTeX compiles"]
    wanted = {"plan", "checks"} | ({"docs"} if docs == "true" else {"suite", "python-floor", "page"})
    if tex == "true":
        wanted.add("latex-smoke")
    for job in FAST_NEEDS:
        r = result[job]
        if job in wanted:
            good = r == "success"
        else:
            good = r in ("success", "skipped")
        ok = ok and good
        said.append(f"{job}: {r}" + ("" if job in wanted else " (not needed)")
                    + ("" if good else "  <- FAILED"))
    return ok, said


# ------------------------------------------------------------------ the command

def _emit(answer: dict, out: str) -> None:
    lines = [f"{k}={v}" for k, v in answer.items() if k != "why"]
    print(f"ci_plan: {answer.get('why', '')}", file=sys.stderr)
    print("\n".join(lines))
    if out:
        with open(out, "a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = ""
    if "--out" in argv:
        i = argv.index("--out")
        out, argv = argv[i + 1], argv[:i] + argv[i + 2:]
    cmd = argv[0] if argv else ""
    env = os.environ
    if cmd == "lane":
        _emit(lane(env.get("EVENT", ""), env.get("BASE", "")), out)
        return 0
    if cmd == "part" and len(argv) >= 2:
        mine = part(argv[1], argv[2:] or None)
        if not mine:
            print(f"ci_plan: no part {argv[1]!r} of these files", file=sys.stderr)
            return 2
        print(" ".join(f.replace(os.sep, "/") for f in mine))
        return 0
    if cmd == "verdict":
        ok, said = verdict(json.loads(env.get("NEEDS") or "{}"))
        print("\n".join(said))
        print("Fast checks green" if ok else "Fast checks red: a job this change needed did "
              "not pass")
        return 0 if ok else 1
    print("usage: python3 tools/ci_plan.py lane [--out FILE] | part K/N [file ...] | verdict",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
