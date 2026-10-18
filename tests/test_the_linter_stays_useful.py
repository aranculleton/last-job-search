"""The linter is scoped to bugs, and the repo stays clean against it.

Ruff's broader default set reports over a thousand findings here, almost all
style preferences: `re.I` rather than `re.IGNORECASE`, quote characters, import
ordering. None of those is wrong in this repo, and a linter that shouts a
thousand times is one somebody switches off, which costs more than it ever
saved.

So the selection is pyflakes (undefined names, unused imports, dead locals),
the syntax errors, and bugbear (late-binding closures, mutable defaults,
unguarded zip). Every one is a real defect class rather than a preference.

Enabling it found, on the first run: six late-binding closures in
`tools/network/state.py`, two dead locals left behind by an earlier dead-code
removal in `hydrate.py` and `scrape_wide.py`, five unused imports, and two
`zip()` calls where the right answer was different in each case (one had to be
strict, because a length mismatch would silently drop a job's bullets; the
other is deliberately offset by one and had to be explicitly non-strict).

This test keeps the scope honest in both directions: it must not quietly widen
into style, and it must not quietly narrow until it catches nothing.
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

from tests import repo_files

ROOT = Path(__file__).resolve().parent.parent
BUG_RULES = {"E9", "F", "B"}

# Read the one line this test cares about rather than importing a TOML parser.
# `tomllib` is stdlib only from 3.11 and CI runs 3.9 through 3.13, so
# importing it failed three tests on the oldest leg while passing locally. A
# four-key config does not need a parser.
_SELECT = re.compile(r"^select\s*=\s*\[(.*?)\]", re.M | re.S)


def selected_rules() -> set[str]:
    m = _SELECT.search((ROOT / ".ruff.toml").read_text(encoding="utf-8"))
    return set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()


def _ruff(*args):
    return subprocess.run([sys.executable, "-m", "ruff", *args],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=180)


def _ruff_missing(result) -> bool:
    """`python -m ruff` exits 1, not 2, when the module is absent.

    The original guard checked for 2, so it never fired and the assertion
    below failed on every CI leg: the workflow installs ruff in the lint job
    and only pytest in the test jobs.
    """
    return "No module named ruff" in ((result.stderr or "") + (result.stdout or ""))


class TheScopeIsBugsNotStyle(unittest.TestCase):
    def test_the_config_exists_and_selects_the_bug_rules(self):
        self.assertEqual(BUG_RULES, selected_rules())

    def test_it_has_not_widened_into_style(self):
        """A style rule here is how a linter becomes noise and gets ignored."""
        for rule in selected_rules():
            with self.subTest(rule=rule):
                self.assertIn(rule[0], "EFB")

    def test_ci_runs_it(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("ruff check", ci)
        self.assertIn("pip install pyyaml ruff", ci)


class TheRepoIsCleanAgainstIt(unittest.TestCase):
    def test_no_findings(self):
        r = _ruff("check", "--no-cache", "--output-format", "concise",
                  "tools/", "templates/", "tests/")
        if _ruff_missing(r):
            self.skipTest("ruff is not installed here; the lint job runs it")
        self.assertEqual(0, r.returncode, r.stdout or r.stderr)


def _stdlib_on_39(mod: str) -> bool:
    """Python 3.9 has no sys.stdlib_module_names: a module the standard library ships."""
    if hasattr(sys, "stdlib_module_names"):
        return False
    import importlib.util
    import sysconfig
    if mod in sys.builtin_module_names:
        return True
    try:
        spec = importlib.util.find_spec(mod)
    except (ImportError, ValueError):
        return False
    origin = (spec.origin or "") if spec else ""
    return origin.startswith(sysconfig.get_paths()["stdlib"]) and "site-packages" not in origin


class TheDependenciesAreWrittenDown(unittest.TestCase):
    def test_the_manifest_covers_every_third_party_import(self):
        import ast
        manifest = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        std = set(getattr(sys, "stdlib_module_names", ()))   # Python 3.10+
        sources = repo_files.files("tools/**/*.py", "templates/**/*.py")
        local = {p.stem for p in sources}
        local |= {"network"}
        # A package folder under tools/ is local too: the vendored openroles is one.
        local |= {p.parent.name for p in (ROOT / "tools").glob("*/__init__.py")}
        third = set()
        for p in sources:
            for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(n, ast.Import):
                    third.update(a.name.split(".")[0] for a in n.names)
                elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                    third.add(n.module.split(".")[0])
        alias = {"yaml": "pyyaml"}
        for mod in sorted(m for m in third - std - local if not _stdlib_on_39(m)):
            with self.subTest(module=mod):
                self.assertIn(alias.get(mod, mod), manifest,
                              f"{mod} is imported but not in requirements.txt")


if __name__ == "__main__":
    unittest.main()
