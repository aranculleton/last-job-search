"""A portal that is off is sent no request: not a search, not a probe, not a detail fetch.

The `enabled:` flag in each portal's SKILL.md was honoured by /scrape's prose
and by nothing that actually ran: scrape_wide.py called LinkedIn and freehire
by name, so `enabled: false` switched off nothing a round did. And the flag
lived in an app-owned file, so a person who changed it lost the change at the
next sync. tools/portals.py is now the one answer, the app's default and then
the person's PORTALS, and every caller asks it.
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hydrate  # noqa: E402
import portals  # noqa: E402
import scrape_wide  # noqa: E402

OFF = {"linkedin-search": False, "freehire-search": True}
ON = {"linkedin-search": True, "freehire-search": True}


class TheDefaults(unittest.TestCase):

    def test_linkedin_and_freehire_ship_on(self):
        d = portals.defaults()
        self.assertIs(d["linkedin-search"], True)
        self.assertIs(d["freehire-search"], True)

    def test_the_danish_portals_ship_off(self):
        d = portals.defaults()
        for name in ("jobbank-search", "jobdanmark-search", "jobindex-search",
                     "jobnet-search"):
            with self.subTest(portal=name):
                self.assertIs(d[name], False)

    def test_the_example_person_takes_the_defaults(self):
        self.assertEqual(portals.overrides(), {})
        self.assertTrue(portals.is_enabled("linkedin-search"))
        self.assertTrue(portals.is_enabled("freehire-search"))


class ThePersonHasTheLastWord(unittest.TestCase):

    def test_portals_overrides_each_portal_it_names(self):
        got = portals.enabled({"linkedin-search": True, "freehire-search": False})
        self.assertIs(got["linkedin-search"], True)
        self.assertIs(got["freehire-search"], False)
        self.assertIs(got["jobindex-search"], False, "a portal not named keeps its default")

    def test_a_misspelt_name_is_reported_not_silently_ignored(self):
        self.assertEqual(portals.unknown({"linkedin": True, "freehire-search": True}),
                         ["linkedin"])


class TheScrapeAsksFirst(unittest.TestCase):

    def test_no_linkedin_request_is_built_when_it_is_off(self):
        kinds = {t[0] for t in scrape_wide.build_tasks(OFF, 2)}
        self.assertEqual(kinds, {"fh"})

    def test_linkedin_requests_are_built_when_the_person_turns_it_on(self):
        kinds = {t[0] for t in scrape_wide.build_tasks(ON, 2)}
        self.assertIn("li", kinds)
        self.assertIn("fh", kinds)

    def test_nothing_is_built_when_every_portal_is_off(self):
        self.assertEqual(scrape_wide.build_tasks({}, 2), [])

    def test_the_canary_probes_only_what_is_on(self):
        def never(*a, **k):
            raise AssertionError("a portal that is off was probed")
        with mock.patch.object(scrape_wide, "linkedin", never), \
             mock.patch.object(scrape_wide, "freehire", return_value=([{"url": "u"}], None)):
            health = scrape_wide.canary(30, OFF)
        self.assertEqual(sorted(health), ["freehire"])


class TheDetailFetchAsksFirst(unittest.TestCase):

    def test_a_posting_from_a_portal_that_is_off_is_not_fetched(self):
        with mock.patch.object(hydrate.subprocess, "run",
                               side_effect=AssertionError("a request was sent")), \
             mock.patch.object(hydrate.portals, "is_enabled", return_value=False):
            got = hydrate.fetch({"portal": "linkedin", "id": "1", "url": "u"})
        self.assertIn("is off", got["hydrate_error"])


if __name__ == "__main__":
    unittest.main()
