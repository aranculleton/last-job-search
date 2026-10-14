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


if __name__ == "__main__":
    unittest.main()
