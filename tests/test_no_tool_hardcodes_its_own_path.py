"""No tool may hardcode an absolute path to the checkout.

`templates/resume_gen.py` and `tools/fit_to_page.py` both carried
`ROOT = "/home/user/ai-job-search"`, the path this repo's cloud container
happens to clone into. Every other tool derives it from `__file__`.

It worked, because until now that was the only environment anybody ran it in.
Anywhere else it would have written a resume to a directory that does not exist,
or, worse, to a stale checkout that did: SETUP.md documents a local path on
macOS, Windows and Linux, and a second clone of a private repo is the ordinary
case rather than an exotic one. The failure is also quiet in the direction that
matters, because the generator creates what it needs, so the first sign would
have been an application going out built from a profile several commits old.

A repo whose sessions are ephemeral containers is exactly the repo where this
hides longest, since every container looks identical.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PY_FILES = sorted(
    list(ROOT.glob("tools/*.py"))
    + list(ROOT.glob("tools/network/*.py"))
    + list(ROOT.glob("templates/*.py"))
    + list(ROOT.glob("*.py"))
)

# An absolute POSIX path under a user or home directory, in a string literal.
ABSOLUTE = re.compile(r"""["'](/(?:home|Users|root|mnt|opt)/[^"']*)["']""")

# Paths that are genuinely absolute and genuinely not this repo.
ALLOWED = (
    "/opt/pw-browsers",      # the preinstalled browser, an environment fact
    "/opt/homebrew/",        # where Homebrew installs on an Apple-silicon Mac (local_path.py)
    "/usr/",
    "/etc/",
    "/tmp/",
    "/dev/",
)


class TestRootIsDerived(unittest.TestCase):
    def test_there_are_files_to_check(self):
        self.assertGreater(len(PY_FILES), 25)

    def test_no_module_hardcodes_a_checkout_path(self):
        for path in PY_FILES:
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for m in ABSOLUTE.finditer(line):
                    found = m.group(1)
                    if found.startswith(ALLOWED):
                        continue
                    with self.subTest(file=path.name, line=n):
                        self.fail(
                            f"{path.relative_to(ROOT)}:{n} hardcodes {found!r}. "
                            "Derive it: "
                            "os.path.dirname(os.path.dirname(os.path.abspath(__file__)))"
                        )

    def test_no_module_sets_root_to_a_literal(self):
        """Computed, not written down.

        The check is "not a string constant" rather than "mentions `__file__`",
        because four modules legitimately go through a `_HERE` they derived one
        line earlier and a test demanding the literal token `__file__` on the
        same line fails all four for being tidy. What matters is only that the
        value is computed at import rather than typed by someone who knew where
        their own checkout was.
        """
        assigns = re.compile(r"^ROOT\s*=\s*(.+)$", re.M)
        checked = 0
        for path in PY_FILES:
            for m in assigns.finditer(path.read_text(encoding="utf-8")):
                checked += 1
                rhs = m.group(1).split("#", 1)[0].strip()
                with self.subTest(file=path.name, rhs=rhs):
                    self.assertFalse(
                        rhs.startswith(('"', "'")),
                        f"{path.relative_to(ROOT)} sets ROOT to the literal {rhs}; "
                        "derive it from the module's own location instead")
        self.assertGreater(checked, 5, "no ROOT assignments found; the check is vacuous")

    def test_the_two_generators_agree_with_the_repo_root(self):
        """They write into cv/ and cover_letters/, so a wrong ROOT misplaces output."""
        sys.path.insert(0, str(ROOT / "templates"))
        sys.path.insert(0, str(ROOT / "tools"))
        import resume_gen
        import fit_to_page
        for mod in (resume_gen, fit_to_page):
            with self.subTest(module=mod.__name__):
                self.assertEqual(str(ROOT), str(Path(mod.ROOT).resolve()))


if __name__ == "__main__":
    unittest.main()
