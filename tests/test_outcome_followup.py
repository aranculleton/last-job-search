"""Guards for /outcome's follow-up branch (Step 2b).

The branch is part of the /outcome markdown spec (the spec IS the
implementation), so these tests pin the invariants that would break
silently: the draft-only rule (the branch must never send anything on the
user's behalf), the no-new-claims rule that keeps follow-ups inside the
framework's never-fabricate boundary, the two-follow-up cap that terminates
into /outcome's own no_response flow, and the one clock (tools/followups.py,
which the daily brief reads too).
"""
import subprocess
import sys
import unittest
from pathlib import Path

try:
    import yaml  # noqa: F401 - only probing availability for the lint integration test
    _HAVE_YAML = True
except ImportError:
    _HAVE_YAML = False

REPO = Path(__file__).resolve().parent.parent
COMMAND = REPO / ".claude" / "commands" / "outcome.md"


class OutcomeFollowupBranchSpec(unittest.TestCase):
    def test_followup_branch_exists(self):
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn(
            "## Step 2b: Follow-Up Branch",
            text,
            "outcome.md lost its follow-up branch section",
        )

    def test_followup_argument_documented(self):
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn(
            "`followup <company>`",
            text,
            "spec lost the /outcome followup argument forms",
        )

    def test_followup_candidates_come_from_followups_py(self):
        """One clock: the brief, open_actions --due and /outcome read tools/followups.py.

        /outcome once ran its own 10-day threshold, with none of the holds
        (an interview, an offer, a referral, DO NOT CHASE), so it chased an
        application the daily brief was deliberately holding.
        """
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn("python3 tools/followups.py", text,
                      "the follow-up branch must take its candidates from tools/followups.py")
        self.assertNotIn("`followup <N>`", text,
                         "an N-day threshold is a second clock beside followups.py's")
        self.assertNotRegex(text, r"\b10[- ]days?\b|10\+ days",
                            "a 10-day clock is back beside followups.py's 7 days")

    def test_draft_only_rule_present(self):
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn(
            "draft only, never send",
            text,
            "spec lost the rule that the follow-up branch never sends anything on the user's behalf",
        )

    def test_no_new_claims_rule_present(self):
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn(
            "no new claims",
            text,
            "spec lost the rule that follow-ups only reuse claims from the archived submitted materials",
        )

    def test_two_followup_cap_present(self):
        text = COMMAND.read_text(encoding="utf-8")
        self.assertIn(
            "Maximum two follow-ups per application",
            text,
            "spec lost the cap that stops the follow-up branch from nagging indefinitely",
        )

    @unittest.skipUnless(
        _HAVE_YAML,
        "PyYAML not installed (the CI Python-test job omits it; the lint job runs lint_skills.py directly)",
    )
    def test_lint_skills_passes(self):
        result = subprocess.run(
            [sys.executable, str(REPO / "tools" / "lint_skills.py")],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"lint_skills.py failed:\n{result.stdout}{result.stderr}")


if __name__ == "__main__":
    unittest.main()
