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

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import run_round as R  # noqa: E402


def test_no_stage_runs_without_the_deadline(drive_round):
    # Was a search of run_round.py's source for a call spelled without one; this runs
    # the round and reads what every stage was actually handed.
    calls, _ = drive_round()
    stages = [Path(cmd[1]).name for cmd, _ in calls]
    assert "scrape_wide.py" in stages and "throttle.py" in stages, stages
    for cmd, deadline in calls:
        assert deadline is not None, f"{Path(cmd[1]).name} ran without the deadline"


class EveryStageHasACeiling(unittest.TestCase):
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
    """A real stage that hangs, under a one-second budget: no mock of subprocess."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        script = Path(self.dir.name) / "slow_stage.py"
        script.write_text("import sys, time\n"
                          "print('progress: fake 1/9 sent', file=sys.stderr, flush=True)\n"
                          "time.sleep(30)\n", encoding="utf-8")
        self.HANG = [sys.executable, str(script)]

    def tearDown(self):
        self.dir.cleanup()

    def _run(self, keep=None):
        log = mock.MagicMock()
        if keep:
            R.ON_TIMEOUT["slow_stage.py"] = keep
        with mock.patch.object(R, "_stage_budget", return_value=1):
            started = time.monotonic()
            try:
                return log, R.run(self.HANG, log), time.monotonic() - started
            except SystemExit as e:
                return log, e, time.monotonic() - started

    def test_it_exits_with_an_explanation(self):
        log, caught, took = self._run()
        self.assertIsInstance(caught, SystemExit)
        self.assertIn("timed out", str(caught))
        self.assertLess(took, 15, "the hung stage was not stopped")

    def test_the_timeout_and_what_it_said_are_in_the_round_log(self):
        log, _, _ = self._run()
        written = " ".join(str(c) for c in log.write.call_args_list)
        self.assertIn("timed out", written)
        # What the stage said before it hung reached the log as it was written.
        self.assertIn("progress: fake 1/9 sent", written)

    def test_a_stage_that_can_keep_its_results_goes_on(self):
        log, code, _ = self._run(keep=lambda: 2)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
