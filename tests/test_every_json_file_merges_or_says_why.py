"""Every JSON file the app writes into a person's copy is wired to the merge, or says why not.

Two chats change one person's copy at once, and a state file git merges as lines stops on a
conflict whenever both sides wrote near each other. The app's code is read for every
`.json` name it writes, reads or matches (a string, an f-string, a `%` pattern, a suffix),
and each must end a path `.gitattributes` gives the merge driver, or be listed in
tools/merge_state.py JSON_NAMES with where it lands or why two chats never change one copy
of it differently. A name built in code is listed with the file that builds it, so a new
one anywhere is looked at. An entry no code names any more fails too, so the list stays
the code's.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import merge_state as M  # noqa: E402

SCAN = ("tools", "templates")
SKIP = {"openroles", "__pycache__", "tests"}
# The merge's own tables name every file, so it is read for none.
OWN = "tools/merge_state.py"


def _built(name: str) -> bool:
    return any(c in name for c in "*%{") or name == ".json"


def names_in_code() -> dict:
    """{name, or "<file>: <name>" for one built in code: [where]} for every .json name."""
    out: dict = {}
    for top in SCAN:
        for base, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = sorted(d for d in dirs if d not in SKIP)
            for f in sorted(files):
                if not f.endswith(".py"):
                    continue
                path = os.path.join(base, f)
                rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
                if rel == OWN:
                    continue
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read())
                for node in ast.walk(tree):
                    text = None
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        text = node.value
                    elif isinstance(node, ast.JoinedStr):
                        text = "".join(v.value if isinstance(v, ast.Constant) else "*"
                                       for v in node.values)
                    if not text or not text.endswith(".json") or any(c in text for c in " \n"):
                        continue
                    name = text.replace("\\", "/").rsplit("/", 1)[-1]
                    key = f"{rel}: {name}" if _built(name) else name
                    out.setdefault(key, []).append(f"{rel}:{node.lineno}")
    return out


def wired_patterns() -> list:
    with open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8") as fh:
        return [ln.split()[0] for ln in fh
                if "merge=ljs-state" in ln and not ln.lstrip().startswith("#")]


def _wired(paths) -> list:
    """The merge attribute git gives each path, in this checkout."""
    r = subprocess.run(["git", "-C", ROOT, "check-attr", "merge", "--", *paths],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return [ln.rsplit(": ", 1)[-1] for ln in r.stdout.splitlines()]


def _sample(pattern: str) -> str:
    return pattern.replace("*", "example")


def test_every_json_name_in_the_code_is_wired_or_listed_with_why():
    wired = {p.rsplit("/", 1)[-1] for p in wired_patterns() if "*" not in p.rsplit("/", 1)[-1]}
    found = names_in_code()
    missing = sorted(k for k in found if k not in wired and k not in M.JSON_NAMES)
    assert not missing, "a JSON name neither wired nor listed in merge_state.JSON_NAMES: " + \
        "; ".join(f"{k} ({found[k][0]})" for k in missing)
    stale = sorted(k for k in M.JSON_NAMES if k not in found)
    assert not stale, f"listed in JSON_NAMES but no code names it now: {stale}"


def test_a_name_listed_as_wired_is_wired_and_a_reason_says_something():
    patterns = [v for v in M.JSON_NAMES.values() if " " not in v]
    assert patterns, "JSON_NAMES maps some names to the patterns they land under"
    assert _wired([_sample(p) for p in patterns]) == ["ljs-state"] * len(patterns)
    for k, v in M.JSON_NAMES.items():
        assert " " not in v or len(v.split()) >= 6, f"{k}: say why in a sentence"


def test_every_file_with_rules_of_its_own_is_wired_and_every_wired_json_has_its_format():
    rules = list(M.JSON_FILES)
    assert _wired([_sample(p) for p in rules]) == ["ljs-state"] * len(rules)
    json_wired = [p for p in wired_patterns() if p.endswith(".json")]
    no_rules = [p for p in json_wired if not any(
        M._at(_sample(p), r) for r in rules)]
    # The two that were wired before their writers' formats were written down merge with
    # the default, which is how their writers write them (indent 2, keys in order).
    assert sorted(no_rules) == ["job_scraper/seen_jobs.json", "profile/learned.json"], no_rules
