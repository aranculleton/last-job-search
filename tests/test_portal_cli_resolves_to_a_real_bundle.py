"""`portal_cli()` must return a runnable bundle, or raise saying why.

This exists because of a bug I wrote and the suite did not catch.

`hydrate.py` and `scrape_wide.py` each carried a second candidate path, a
hard-coded scratchpad directory left over from an old container. Removing it
left the line as:

    for candidate in (dist):

A one-element tuple needs a trailing comma, so `(dist)` is just the string.
The loop then walked it one character at a time, and the first `os.path.exists`
to return True would have handed back a single character as the path to a
portal CLI. `/` exists on every machine.

Every one of 1,438 tests passed over that, because nothing called the function.
The failure it would have produced is the quiet kind the scrape module's own
docstring says it exists to prevent: a scrape that returns nothing, with no
error explaining why.

Both modules resolve CLIs the same way and were edited identically, so both are
checked here. A test that covered only the one I happened to run by hand would
have left the other in exactly the state that caused this.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import hydrate  # noqa: E402
import scrape_wide  # noqa: E402

MODULES = (hydrate, scrape_wide)

# The portals this repo actually runs. A disabled portal may have no build.
ENABLED = ("linkedin-search", "freehire-search")


class TestTheResolverReturnsSomethingRunnable(unittest.TestCase):
    def setUp(self):
        for mod in MODULES:
            mod.portal_cli.cache_clear()

    def test_every_enabled_portal_resolves_to_its_own_bundle(self):
        for mod in MODULES:
            for portal in ENABLED:
                with self.subTest(module=mod.__name__, portal=portal):
                    path = mod.portal_cli(portal, "PORTAL_CLI_UNSET_IN_TEST")
                    self.assertTrue(path.endswith(".mjs"),
                                    f"{path!r} is not a bundle")
                    self.assertIn(portal, path,
                                  f"{path!r} is not this portal's bundle")
                    self.assertTrue(os.path.isfile(path),
                                    f"{path!r} is not a file")

    def test_the_result_is_never_a_single_character(self):
        """The exact shape of the bug: iterating a string instead of a tuple."""
        for mod in MODULES:
            for portal in ENABLED:
                with self.subTest(module=mod.__name__, portal=portal):
                    path = mod.portal_cli(portal, "PORTAL_CLI_UNSET_IN_TEST")
                    self.assertGreater(len(path), 1, path)
                    self.assertNotEqual(path, os.sep)

    def test_both_modules_agree(self):
        """They resolve the same portal the same way or one of them is wrong."""
        for portal in ENABLED:
            with self.subTest(portal=portal):
                seen = {mod.portal_cli(portal, "PORTAL_CLI_UNSET_IN_TEST")
                        for mod in MODULES}
                self.assertEqual(1, len(seen), f"{portal} resolves two ways: {seen}")


class TestTheOverrideAndTheFailurePath(unittest.TestCase):
    def setUp(self):
        for mod in MODULES:
            mod.portal_cli.cache_clear()
        self.addCleanup(os.environ.pop, "PORTAL_CLI_TEST_OVERRIDE", None)

    def test_an_env_override_pointing_at_a_real_file_wins(self):
        real = str(ROOT / "README.md")
        os.environ["PORTAL_CLI_TEST_OVERRIDE"] = real
        for mod in MODULES:
            with self.subTest(module=mod.__name__):
                mod.portal_cli.cache_clear()
                self.assertEqual(real, mod.portal_cli("linkedin-search",
                                                      "PORTAL_CLI_TEST_OVERRIDE"))

    def test_an_env_override_pointing_at_nothing_raises_rather_than_falling_back(self):
        """Silently ignoring a bad override is how you debug the wrong binary."""
        os.environ["PORTAL_CLI_TEST_OVERRIDE"] = "/nonexistent/portal-cli.mjs"
        for mod in MODULES:
            with self.subTest(module=mod.__name__):
                mod.portal_cli.cache_clear()
                with self.assertRaises(FileNotFoundError):
                    mod.portal_cli("linkedin-search", "PORTAL_CLI_TEST_OVERRIDE")

    def test_an_unknown_portal_raises_instead_of_returning_a_path(self):
        for mod in MODULES:
            with self.subTest(module=mod.__name__):
                mod.portal_cli.cache_clear()
                with self.assertRaises(Exception) as caught:
                    mod.portal_cli("no-such-portal", "PORTAL_CLI_UNSET_IN_TEST")
                self.assertNotIsInstance(caught.exception, AssertionError)


if __name__ == "__main__":
    unittest.main()
