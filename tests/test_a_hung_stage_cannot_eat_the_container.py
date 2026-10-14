"""No stage may run without a ceiling, because the container has one.

Not one of the seven stages was given a `timeout`. A portal CLI that hangs on
a socket, or a fetch that never returns, holds the round for as long as the
container lives. These run in ephemeral cloud containers: the session is
reclaimed, the round's ~55MB of stage files are deleted by design, and the
entire search is lost with nothing written down and nothing saying why.

The scrape gets the largest budget because it is thousands of requests. The
stages after it are reading files that already exist, so they get far less.
Every stage is additionally capped by what remains of the round budget, so a
pipeline that is slow rather than hung cannot spend the ceiling one stage at
a time and still overrun.
"""
from __future__ import annotations

import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import run_round as R  # noqa: E402


class EveryStageHasACeiling(unittest.TestCase):
    def test_no_run_call_omits_the_deadline(self):
        src = (ROOT / "tools" / "run_round.py").read_text(encoding="utf-8")
        body = src[src.index("def main():"):]
        self.assertNotIn("], log)", body, "a stage call without the deadline")
        self.assertNotIn(", log)\n", body, "a stage call without the deadline")

    def test_the_scrape_gets_the_most(self):
        scrape = R._stage_budget(["py", "tools/scrape_wide.py"], None)
        other = R._stage_budget(["py", "tools/fit.py"], None)
        self.assertGreater(scrape, other)

    def test_an_unknown_stage_still_gets_one(self):
        self.assertEqual(R.DEFAULT_STAGE_SEC,
                         R._stage_budget(["py", "tools/brand_new.py"], None))

    def test_the_round_budget_caps_a_stage(self):
        deadline = time.monotonic() + 5
        self.assertLessEqual(R._stage_budget(["py", "tools/scrape_wide.py"], deadline), 5)

    def test_a_spent_budget_still_leaves_a_positive_timeout(self):
        """subprocess.run rejects a timeout of zero or less."""
        self.assertGreaterEqual(
            R._stage_budget(["py", "tools/fit.py"], time.monotonic() - 9999), 1)

    def test_the_whole_round_budget_is_under_a_typical_container_life(self):
        self.assertLessEqual(R.ROUND_BUDGET_SEC, 2 * 60 * 60)


class ATimeoutSaysSoRatherThanHanging(unittest.TestCase):
    def test_it_exits_with_an_explanation(self):
        log = mock.MagicMock()
        with mock.patch.object(R.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("cmd", 1)):
            with self.assertRaises(SystemExit) as caught:
                R.run([sys.executable, "tools/fit.py"], log)
        self.assertIn("timed out", str(caught.exception))
        self.assertIn("fit.py", str(caught.exception))

    def test_the_timeout_is_written_to_the_round_log(self):
        log = mock.MagicMock()
        with mock.patch.object(R.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("cmd", 1)):
            with self.assertRaises(SystemExit):
                R.run([sys.executable, "tools/fit.py"], log)
        self.assertTrue(log.write.called)
        self.assertIn("timed out", " ".join(str(c) for c in log.write.call_args_list))

    def test_a_timeout_with_bytes_output_does_not_crash_the_handler(self):
        """TimeoutExpired carries bytes or str depending on how it was raised."""
        log = mock.MagicMock()
        exc = subprocess.TimeoutExpired("cmd", 1, output=b"partial", stderr=b"err")
        with mock.patch.object(R.subprocess, "run", side_effect=exc):
            with self.assertRaises(SystemExit):
                R.run([sys.executable, "tools/fit.py"], log)


if __name__ == "__main__":
    unittest.main()
