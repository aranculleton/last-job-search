"""One application, one folder under documents/applications.

`outreach.slug()` did not always take an abbreviation. It was added so that
two roles at one employer with the same title could not overwrite each other:
an employer can post "Senior Business Analyst" twice, and another can post a
title so long that two cities agree for the first eighty characters.

A change like that is not applied to what is already on disk, so every
application written before it keeps its abbreviation-less folder and every
rewrite after it creates a second one beside it. The result is pairs of
folders holding the same posting under two names, and the older half holds the
older outreach note, which may break a rule the newer one keeps (a note over
the word cap, or the wrong tense). Nothing says which half is live, so a
session reading one of them is reading the wrong one half the time.

The test is a prefix check rather than an equality check because that is the
shape the duplication takes: the stale name is the live name with the
abbreviation cut off the end.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPLICATIONS = REPO / "documents" / "applications"


def folders():
    if not APPLICATIONS.is_dir():
        return []
    return sorted(p.name for p in APPLICATIONS.iterdir() if p.is_dir())


class NoApplicationIsFiledTwice(unittest.TestCase):
    def test_no_folder_is_another_folder_without_its_abbreviation(self):
        names = folders()
        if not names:
            self.skipTest("no applications on disk")
        pairs = [(a, b) for a in names for b in names
                 if b.startswith(a + "_") and "_" not in b[len(a) + 1:]]
        self.assertEqual(pairs, [], "\n".join(
            "%s is %s with the abbreviation removed. Keep the one carrying the "
            "abbreviation, which is what outreach.slug() writes, and delete the "
            "other after checking it holds nothing the survivor lacks." % (a, b)
            for a, b in pairs))

    def test_every_folder_holds_the_posting_it_is_named_for(self):
        """An empty folder is the residue of a half-finished consolidation."""
        for name in folders():
            with self.subTest(folder=name):
                self.assertTrue((APPLICATIONS / name / "job_posting.md").is_file(),
                                "%s has no job_posting.md" % name)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
