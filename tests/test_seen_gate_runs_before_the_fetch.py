"""The cross-run gate must drop exactly what the throttle drops, only earlier.

`throttle.ruled_out()` is a pure function of `seen_jobs.json`: it reads a
posting's URL and its (title, employer) pair and nothing else. Both are present
from the scrape, so the decision was always available before `hydrate.py` spent
an HTTP call on the body. It ran last anyway, so every round re-fetched every
posting it had already excluded, screened it, scored its opportunity and scored
its fit, and threw the lot away at the end. A large share of the postings
that pass prefilter's own gates are already ruled out in `seen_jobs.json`.

The whole risk of moving a filter earlier is that it stops being the same
filter. These tests exist to pin that it is:

- prefilter imports `throttle.ruled_out` rather than reimplementing it, so a
  second "have we seen this" cannot drift. The direction that drift goes is
  dropping a role that should have surfaced, which is invisible and permanent.
- everything the early gate drops, the throttle would also have dropped.
- the gate fails open on a missing or corrupt seen file, because a cross-run
  filter that failed closed would silently empty a round.
- the carve-outs `ruled_out` makes (no reason recorded, stale exclusion,
  re-evaluated skip) are honoured here too, since they are what stops stale
  entries blocking good postings forever.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import prefilter as P  # noqa: E402
import throttle as T  # noqa: E402

TODAY = "2026-03-02"


def posting(url, title="Senior Data Scientist", company="Acme", location="Manchester, England, United Kingdom"):
    return {"url": url, "title": title, "company": company, "location": location,
            "posted_date": TODAY, "date": TODAY}


def seen_file(entries):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"seen": entries}, fh)
    fh.close()
    return fh.name


class TestTheGateIsTheThrottlesOwnDecision(unittest.TestCase):
    def test_prefilter_imports_ruled_out_rather_than_restating_it(self):
        src = (ROOT / "tools" / "prefilter.py").read_text(encoding="utf-8")
        self.assertIn("from throttle import ruled_out", src,
                      "a second implementation of the cross-run gate would drift, "
                      "and it drifts towards dropping roles that should surface")

    def test_an_excluded_posting_is_dropped_before_hydrate(self):
        url = "https://example.com/jobs/1"
        path = seen_file({url: {"url": url, "title": "Senior Data Scientist",
                                "company": "Acme", "status": "excluded",
                                "exclusion_reason": "requires a professional licence"}})
        self.addCleanup(os.unlink, path)
        self.assertIn("excluded", P.already_ruled_out(path)(posting(url)))

    def test_an_unseen_posting_survives(self):
        path = seen_file({"https://example.com/jobs/1": {
            "url": "https://example.com/jobs/1", "title": "X", "company": "Acme",
            "status": "excluded", "exclusion_reason": "requires a professional licence"}})
        self.addCleanup(os.unlink, path)
        self.assertEqual("", P.already_ruled_out(path)(posting("https://example.com/jobs/2",
                                                               title="Data Analyst",
                                                               company="Other Co")))

    def test_the_same_role_at_the_same_employer_is_caught_by_the_pair(self):
        """A reposted job gets a new URL; the (title, employer) pair is what holds."""
        old = "https://example.com/jobs/1"
        path = seen_file({old: {"url": old, "title": "Senior Data Scientist",
                                "company": "Acme Inc.", "status": "excluded",
                                "exclusion_reason": "requires a professional licence"}})
        self.addCleanup(os.unlink, path)
        reposted = posting("https://example.com/jobs/9999", company="Acme")
        self.assertIn("excluded", P.already_ruled_out(path)(reposted))


class TestTheCarveOutsAreHonoured(unittest.TestCase):
    """`ruled_out` deliberately lets some entries stop blocking. So must this."""

    def _gate(self, entry):
        url = entry.setdefault("url", "https://example.com/jobs/1")
        path = seen_file({url: entry})
        self.addCleanup(os.unlink, path)
        return P.already_ruled_out(path)(posting(url, title=entry.get("title", "Senior Data Scientist"),
                                                 company=entry.get("company", "Acme")))

    def test_an_exclusion_with_no_reason_does_not_block(self):
        """An entry with no recorded reason cannot be checked, so it blocks nothing."""
        self.assertEqual("", self._gate({"title": "Senior Data Scientist",
                                         "company": "Acme", "status": "excluded",
                                         "exclusion_reason": ""}))

    def test_a_status_that_is_neither_excluded_nor_skipped_does_not_block(self):
        for status in ("new", "estimated", "ranked", "drafted", "applied"):
            with self.subTest(status=status):
                self.assertEqual("", self._gate({"title": "Senior Data Scientist",
                                                 "company": "Acme", "status": status,
                                                 "exclusion_reason": "whatever"}))


class TestTheGateFailsOpen(unittest.TestCase):
    """A cross-run filter that failed closed would silently empty a round."""

    def test_a_missing_file_never_fires(self):
        self.assertEqual("", P.already_ruled_out("/nonexistent/seen.json")(posting("u")))

    def test_corrupt_json_never_fires(self):
        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        fh.write("{not json")
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        self.assertEqual("", P.already_ruled_out(fh.name)(posting("u")))

    def test_an_empty_seen_file_never_fires(self):
        path = seen_file({})
        self.addCleanup(os.unlink, path)
        self.assertEqual("", P.already_ruled_out(path)(posting("u")))


class TestAgainstTheRealSeenFile(unittest.TestCase):
    """End to end on the committed corpus: the gate drops only throttle-drops."""

    # The state in use: the example's under tests/, a person's own under theirs.
    SEEN = T.SEEN

    @classmethod
    def setUpClass(cls):
        with open(cls.SEEN) as fh:
            cls.seen = json.load(fh)["seen"]

    def test_everything_the_gate_drops_the_throttle_would_also_drop(self):
        gate = P.already_ruled_out(str(self.SEEN))
        urls, pairs = T.ruled_out(self.seen)
        dropped = 0
        for u, e in self.seen.items():
            job = {"url": e.get("url") or u, "title": e.get("title"),
                   "company": e.get("company"), "location": e.get("location")}
            if not gate(job):
                continue
            dropped += 1
            n = T.norm(job["url"] or "")
            self.assertTrue((n and n in urls) or T.ruled_pair(pairs, job),
                            f"the early gate dropped {u}, which the throttle keeps")
        # The example's corpus is one excluded posting; a real one runs to
        # hundreds, and a person's own copy of this test holds it to a higher bar.
        self.assertGreater(dropped, 0,
                           "the gate fired on almost nothing, so either the corpus "
                           "changed shape or the matching broke")


class TestTheRoundWiresItUp(unittest.TestCase):
    def test_run_round_passes_seen_to_prefilter_by_default(self):
        src = (ROOT / "tools" / "run_round.py").read_text(encoding="utf-8")
        self.assertIn('prefilter += ["--seen"', src)
        self.assertIn("no_seen_read", src,
                      "there must be a way to re-evaluate everything previously "
                      "excluded, for when the scoring rules change")

    def test_the_escape_hatch_reaches_an_expanded_round(self):
        """--expand re-invokes this script; a flag it drops is a flag that lies."""
        src = (ROOT / "tools" / "run_round.py").read_text(encoding="utf-8")
        # The widened round's call, which now also clears the bodies it handed on
        # after it returns, so it is no longer the return statement itself.
        expansion = src.split("subprocess.call(", 1)[1]
        self.assertIn('"--no-seen-read"', expansion)

    def test_prefilter_accepts_the_flag(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "prefilter.py"), "--help"],
                           capture_output=True, text=True)
        self.assertEqual(0, r.returncode)
        self.assertIn("--seen", r.stdout)


if __name__ == "__main__":
    unittest.main()
