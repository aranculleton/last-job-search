"""The interview pack's smaller refusals are right, and plain.

From the sync audit, 2026-10-21:
- Mock feedback that mentioned a rating model and a count a few words on ("the credit
  rating model you built across 3 teams") was refused as giving a score.
- `interview_pack.py --help`, run where there is no profile (the app itself, or before
  /setup), printed a traceback instead of its usage; so did `prep.py --help`.

Everything here is invented.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import interview_pack as P  # noqa: E402

ANSWER = ("I rebuilt the credit rating model we used across 3 teams, and I checked it against "
          "a year of held-out loans before anyone relied on it.")
QUOTE = "checked it against a year of held-out loans"


@pytest.mark.parametrize("note", [
    "say more about the credit rating model you built across 3 teams",
    "the rating model behind 3 lenders is the strong part: lead with it",
    "lead with the 2 points that landed, then the result",
])
def test_a_note_that_names_a_rating_model_and_a_number_is_not_a_score(note):
    assert P.feedback_problems(ANSWER, "Solid", [(QUOTE, note)]) == []


@pytest.mark.parametrize("note", ["I'd give it a rating of 4", "you scored 8 here",
                                  "score: 6 for structure", "worth 3 points out of 5"])
def test_a_score_is_still_refused(note):
    [why] = P.feedback_problems(ANSWER, "Solid", [(QUOTE, note)])
    assert "never a score" in why


@pytest.mark.parametrize("tool", ["interview_pack.py", os.path.join("network", "prep.py")])
def test_help_with_no_profile_shows_the_usage_and_no_traceback(tmp_path, tool):
    env = dict(os.environ, LJS_PROFILE=str(tmp_path / "no-profile-here"))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", tool), "--help"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    assert r.returncode == 0 and "Traceback" not in r.stderr, r.stderr
    assert r.stdout.strip()
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", tool), "check", "Anyone"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    assert r.returncode == 1 and "Traceback" not in r.stderr
    assert "no profile/ yet: /setup builds one." in r.stdout
