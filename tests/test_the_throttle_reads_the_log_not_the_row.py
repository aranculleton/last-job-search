"""Warm or cold is decided by the messages, in both places that decide it.

The networking layer's documented premise, in CLAUDE.md: "Status is derived
from the messages, never stored independently, so it cannot drift from the
evidence." That was true of `state.py` and false of `throttle.py`, which read
the stored column straight off `network_contacts.csv`. Two implementations of
one rule, which is the failure this repo names more than any other.

The case this was written for was misread, and the correction matters as much
as the rule. A contact stored `connected_no_reply` had one inbound row in the
log: "Accepted the connection request. No message." (scenario
`accepted_no_reply`). The derivation read that row's direction and called it a
reply, so a test pinned that employer as a warm route. It never was: nobody
there had written a word, and the stored row was right.
`test_accepting_a_request_is_not_a_reply` in a person's own suite has the
whole account.

The rule stands. Reading the stored column instead of the log is still two
implementations of one rule, and a reply the row has not caught up with is
still the unused-referral failure described in `_contacts_by_employer`'s own
docstring: a live route invisible to the thing deciding whether the
application is cold.

The throttle now derives, the same way `prefilter.py` imports
`throttle.ruled_out()` rather than reimplementing it. It fails open to the
stored column, because a missing message log is a reason to fall back to the
row, never a reason to stop a scrape.
"""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import throttle  # noqa: E402


def _csv(rows, fields):
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    fh.close()
    return fh.name


class AReplyMakesTheRouteWarmEvenIfNobodyEditedTheRow(unittest.TestCase):
    FIELDS = ["contact_id", "name", "company", "status", "title", "next_action"]
    TFIELDS = ["contact_id", "direction", "date", "channel", "body"]

    def setUp(self):
        self.contacts = _csv([{
            "contact_id": "c1", "name": "Robin Vale", "company": "Acme",
            "status": "connected_no_reply", "title": "Director", "next_action": "",
        }], self.FIELDS)
        self.addCleanup(lambda: Path(self.contacts).unlink(missing_ok=True))

    def _threads(self, rows):
        path = _csv(rows, self.TFIELDS)
        self.addCleanup(lambda: Path(path).unlink(missing_ok=True))
        return path

    def test_the_stored_row_alone_reads_as_not_yet_warm(self):
        """Establishes the starting state the bug depended on."""
        self.assertIn("connected_no_reply", throttle.SENT_NO_REPLY)
        self.assertNotIn("connected_no_reply", throttle.RESPONDED)

    def test_an_inbound_message_moves_it_to_warm(self):
        threads = self._threads([
            {"contact_id": "c1", "direction": "out", "date": "2026-08-01",
             "channel": "linkedin", "body": "hello"},
            {"contact_id": "c1", "direction": "in", "date": "2026-08-05",
             "channel": "linkedin", "body": "happy to chat"},
        ])
        rows = list(csv.DictReader(open(self.contacts, newline="", encoding="utf-8")))
        derived = throttle._derived_statuses(rows, threads)
        self.assertEqual("replied_needs_response", derived.get("c1"))
        self.assertIn(throttle._status_of(rows[0], derived), throttle.RESPONDED)

    def test_with_no_reply_it_stays_where_it_was(self):
        threads = self._threads([
            {"contact_id": "c1", "direction": "out", "date": "2026-08-01",
             "channel": "linkedin", "body": "hello"},
        ])
        rows = list(csv.DictReader(open(self.contacts, newline="", encoding="utf-8")))
        derived = throttle._derived_statuses(rows, threads)
        self.assertNotIn(throttle._status_of(rows[0], derived), throttle.RESPONDED)


class ItFailsOpenToTheStoredColumn(unittest.TestCase):
    """A scrape must never stop because the message log is unreadable."""

    def test_a_missing_log_falls_back(self):
        rows = [{"contact_id": "c1", "status": "awaiting_reply"}]
        self.assertEqual({}, throttle._derived_statuses(rows, "/nonexistent/x.csv"))
        self.assertEqual("awaiting_reply", throttle._status_of(rows[0], {}))

    def test_a_row_with_no_id_falls_back(self):
        self.assertEqual("in_conversation",
                         throttle._status_of({"status": "in_conversation"}, {}))

    def test_a_corrupt_log_falls_back_rather_than_raising(self):
        path = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                           encoding="utf-8")
        path.write("\x00not,a,csv\n\x00")
        path.close()
        self.addCleanup(lambda: Path(path.name).unlink(missing_ok=True))
        try:
            throttle._derived_statuses([{"contact_id": "c1"}], path.name)
        except Exception as e:                     # noqa: BLE001 - the point
            self.fail(f"a corrupt log must not raise: {e!r}")


class TheRuleHasOneImplementation(unittest.TestCase):
    def test_the_throttle_does_not_reimplement_the_derivation(self):
        src = (ROOT / "tools" / "throttle.py").read_text(encoding="utf-8")
        self.assertIn("from state import effective_status", src,
                      "two implementations of one rule is the failure this "
                      "repo names more than any other")


if __name__ == "__main__":
    unittest.main()
