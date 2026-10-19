"""A closed posting is claimed only on its own top card, never on a neighbour's."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import still_open as so  # noqa: E402

PAD = "<p>" + "Job description text. " * 200 + "</p>"


class Verdicts(unittest.TestCase):
    def test_the_top_card_saying_closed_is_closed(self):
        html = ('<div class="top-card-layout__entity-info">Data Analyst</div>'
                '<figure>No longer accepting applications</figure>' + PAD)
        self.assertEqual(so.verdict(html), "closed")

    def test_a_similar_job_rail_saying_closed_is_not_this_posting(self):
        html = ('<div class="top-card-layout">Data Analyst</div>' + PAD + PAD + PAD +
                '<section><h2>Similar jobs</h2><li>No longer accepting applications</li></section>')
        self.assertEqual(so.verdict(html), "open")

    def test_nothing_fetched_is_unknown_never_closed(self):
        self.assertEqual(so.verdict(""), "unknown")


class AsksTheWayTheAppAsks(unittest.TestCase):
    """It fetched every page as a browser, to portals the person had switched off,
    and past robots.txt. Each gate now says no as `unknown`, with the reason."""

    URL = "https://www.linkedin.com/jobs/view/4100000123"

    def setUp(self):
        self.calls = []
        self._real = (so.subprocess.run, so.robots_check.gate, so.portals.is_enabled)

        def curl(cmd, **kw):
            self.calls.append(cmd)
            return so.subprocess.CompletedProcess(cmd, 0, "<html>" + PAD + "</html>", "")
        so.subprocess.run = curl
        so.robots_check.gate = lambda url: (0, "ALLOWED")
        so.portals.is_enabled = lambda name: True

    def tearDown(self):
        so.subprocess.run, so.robots_check.gate, so.portals.is_enabled = self._real

    def _check(self, url):
        import csv
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="",
                                         encoding="utf-8") as fh:
            w = csv.DictWriter(fh, ["date", "company", "role", "status", "source"])
            w.writeheader()
            w.writerow({"date": "2026-10-01", "company": "Kestrel Mutual",
                        "role": "Data Analyst", "status": "drafted", "source": url})
        self.addCleanup(Path(fh.name).unlink)
        (row,) = so.check({"drafted"}, fh.name)
        return row

    def test_a_portal_switched_off_is_sent_nothing(self):
        so.portals.is_enabled = lambda name: name != "linkedin-search"
        row = self._check(self.URL)
        self.assertEqual((row["verdict"], self.calls), ("unknown", []))
        self.assertIn("linkedin-search is switched off", row["why"])

    def test_a_page_robots_txt_disallows_is_not_fetched(self):
        so.robots_check.gate = lambda url: (1, "DISALLOWED for * - do not retry")
        row = self._check("https://careers.example.com/jobs/12")
        self.assertEqual((row["verdict"], self.calls), ("unknown", []))
        self.assertIn("robots.txt", row["why"])

    def test_it_asks_as_itself(self):
        row = self._check("https://careers.example.com/jobs/12")
        self.assertEqual(row["verdict"], "open")
        ua = self.calls[0][self.calls[0].index("-A") + 1]
        self.assertNotIn("Mozilla", ua)
        self.assertIn("last-job-search", ua)

    def test_a_portals_crawl_delay_is_kept(self):
        real = so.portals.crawl_delay, so.portal_of
        so.portals.crawl_delay = lambda name: 5.0
        so.portal_of = lambda url: "cityboard-search"
        try:
            waits, now = [], [100.0]
            so._LAST.clear()
            so.pace("https://cityboard.example/jobs/1", sleep=waits.append, clock=lambda: now[0])
            now[0] += 1
            so.pace("https://cityboard.example/jobs/2", sleep=waits.append, clock=lambda: now[0])
            self.assertEqual(waits, [4.0])
        finally:
            so.portals.crawl_delay, so.portal_of = real


if __name__ == "__main__":
    unittest.main()
