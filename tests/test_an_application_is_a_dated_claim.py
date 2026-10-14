"""A sent application stops suppressing its employer once it has gone quiet.

`tools/throttle.py` already knows this shape. `is_stale_exclusion()` exists
because a permanent exclusion is a DATED claim about a scoring rule, and it
releases when the rule that produced it no longer exists. An application is a
dated claim too, and nobody applied that reading to it.

The consequence, on a tracker full of `applied` rows and **none in any terminal
state**: nothing in the repo ever writes `no_response`, because doing so needs a
person to notice silence and run `/outcome`, and silence is the thing nobody
notices. So every employer applied to is suppressed with no exit path, and a
better role at any of them never surfaces again.

The release is deliberately narrow. It does NOT rewrite the tracker: marking a
row `no_response` is a claim about the world and belongs to a person running
`/outcome`. It only stops the row suppressing, which is a claim about this
repo's own behaviour.

Against a committed tracker the release is gradual: nothing is released while
the oldest row is younger than the threshold, and every employer is released
once its row is older than the threshold.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import throttle  # noqa: E402
from company_key import key  # noqa: E402

TODAY = dt.date(2026, 3, 2)


def row(days_ago, status="applied", company="Example Bank"):
    return {"date": (TODAY - dt.timedelta(days=days_ago)).isoformat(),
            "company": company, "status": status, "role": "Data Scientist"}


class SilenceIsDatedNotPermanent(unittest.TestCase):
    def test_a_fresh_application_is_not_silent(self):
        self.assertFalse(throttle.is_silent(row(1), TODAY))
        self.assertFalse(throttle.is_silent(row(throttle.SILENCE_DAYS - 1), TODAY))

    def test_it_becomes_silent_exactly_at_the_threshold(self):
        self.assertTrue(throttle.is_silent(row(throttle.SILENCE_DAYS), TODAY))
        self.assertTrue(throttle.is_silent(row(throttle.SILENCE_DAYS + 200), TODAY))

    def test_an_unreadable_date_is_never_silent(self):
        """Fail closed: an unparseable row keeps suppressing."""
        for bad in ("", "not a date", None, "2026-13-45"):
            with self.subTest(date=bad):
                self.assertFalse(throttle.is_silent(
                    {"date": bad, "company": "X", "status": "applied"}, TODAY))

    def test_the_threshold_is_past_any_live_hiring_process(self):
        self.assertGreaterEqual(throttle.SILENCE_DAYS, 30)
        self.assertLessEqual(throttle.SILENCE_DAYS, 90)


class TheThrottleReleasesWhatItShould(unittest.TestCase):
    def setUp(self):
        import tempfile
        import csv
        self.tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, newline="", encoding="utf-8")
        self.addCleanup(lambda: Path(self.tmp.name).unlink(missing_ok=True))
        w = csv.DictWriter(self.tmp, fieldnames=["date", "company", "status", "role"])
        w.writeheader()
        w.writerow(row(5, company="Fresh Co"))
        w.writerow(row(60, company="Quiet Co"))
        w.writerow(row(90, company="Rejected Co", status="rejected"))
        w.writerow(row(90, company="Draft Co", status="drafted"))
        self.tmp.close()

    def test_a_fresh_application_still_suppresses(self):
        self.assertIn(key("Fresh Co"), throttle.open_applications(self.tmp.name, TODAY))

    def test_a_quiet_application_stops_suppressing(self):
        self.assertNotIn(key("Quiet Co"), throttle.open_applications(self.tmp.name, TODAY))

    def test_and_is_reported_rather_than_silently_forgotten(self):
        """The shortlist row must be able to say why it came back."""
        self.assertIn(key("Quiet Co"), throttle.silent_applications(self.tmp.name, TODAY))

    def test_a_resolved_application_is_not_counted_as_silent(self):
        """It was already out of the suppressing set on its status."""
        silent = throttle.silent_applications(self.tmp.name, TODAY)
        self.assertNotIn(key("Rejected Co"), silent)

    def test_an_unsent_draft_is_neither(self):
        self.assertNotIn(key("Draft Co"), throttle.open_applications(self.tmp.name, TODAY))
        self.assertNotIn(key("Draft Co"), throttle.silent_applications(self.tmp.name, TODAY))

    def test_the_two_sets_never_overlap(self):
        o = set(throttle.open_applications(self.tmp.name, TODAY))
        s = set(throttle.silent_applications(self.tmp.name, TODAY))
        self.assertEqual(set(), o & s)


def tracker_day_before_release(tracker):
    """The last day on which the oldest dated row is still inside the threshold."""
    import csv
    dates = []
    with open(tracker, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                dates.append(dt.date.fromisoformat((r.get("date") or "").strip()))
            except ValueError:
                continue
    if not dates:
        return None
    return min(dates) + dt.timedelta(days=throttle.SILENCE_DAYS - 1)


# The example person's tracker, in the temporary state tests/conftest.py makes:
# the app's suite never reads a real person's tracker, which can hold anything
# (a repo's very first /apply leaves one drafted row and nothing to release).
STATE_TRACKER = Path(os.environ.get("LJS_STATE", ROOT)) / "job_search_tracker.csv"


class TheCommittedTrackerReleasesOverTime(unittest.TestCase):
    """A committed tracker, the example person's, released over time."""

    def test_nothing_is_released_while_the_oldest_row_is_inside_the_threshold(self):
        tracker = STATE_TRACKER
        if not tracker.is_file():
            self.skipTest("no committed tracker")
        day = tracker_day_before_release(str(tracker))
        if day is None:
            self.skipTest("no dated rows in the committed tracker")
        self.assertEqual({}, throttle.silent_applications(str(tracker), day),
                         "the oldest committed row is younger than the threshold")

    def test_the_suppressed_set_drains_as_the_threshold_passes(self):
        tracker = STATE_TRACKER
        if not tracker.is_file():
            self.skipTest("no committed tracker")
        day = tracker_day_before_release(str(tracker))
        if day is None:
            self.skipTest("no dated rows in the committed tracker")
        counts = [len(throttle.open_applications(str(tracker), d))
                  for d in (day,
                            day + dt.timedelta(days=30),
                            day + dt.timedelta(days=60))]
        self.assertEqual(counts, sorted(counts, reverse=True), counts)
        self.assertGreater(counts[0], counts[-1],
                           "every employer stayed suppressed forever, which is "
                           "the bug this file exists for")

    def test_the_release_does_not_rewrite_the_tracker(self):
        """A `no_response` claim belongs to a person running /outcome."""
        tracker = STATE_TRACKER
        if not tracker.is_file():
            self.skipTest("no committed tracker")
        before = tracker.read_bytes()
        throttle.open_applications(str(tracker), TODAY + dt.timedelta(days=400))
        throttle.silent_applications(str(tracker), TODAY + dt.timedelta(days=400))
        self.assertEqual(before, tracker.read_bytes())


class TheResurfacedRoleExplainsItself(unittest.TestCase):
    """Silence releasing an employer must not read as the throttle forgetting."""

    APPLIED = (TODAY - dt.timedelta(days=60)).isoformat()

    def _row(self):
        rows = [{"url": "u1", "title": "Senior Data Scientist",
                 "company": "Quiet Co", "location": "Manchester"}]
        silent = {key("Quiet Co"): [{"role": "Data Analyst", "date": self.APPLIED}]}
        kept, _ = throttle.throttle(rows, {}, {}, {}, TODAY.isoformat(), silent=silent)
        return kept[0]

    def test_the_role_surfaces(self):
        self.assertTrue(self._row())

    def test_it_carries_a_note_naming_the_old_application(self):
        note = self._row().get("silent_application_note") or ""
        self.assertIn("APPLIED HERE ALREADY", note)
        self.assertIn("Data Analyst", note)
        self.assertIn(self.APPLIED, note)

    def test_the_note_says_what_to_do_about_the_old_row(self):
        self.assertIn("/outcome", self._row().get("silent_application_note") or "")

    def test_no_note_when_nothing_was_released(self):
        rows = [{"url": "u1", "title": "X", "company": "Fresh Co", "location": "Manchester"}]
        kept, _ = throttle.throttle(rows, {}, {}, {}, TODAY.isoformat(), silent={})
        self.assertIsNone(kept[0].get("silent_application_note"))


if __name__ == "__main__":
    unittest.main()
