"""A LinkedIn limit the app ignores is said, and taken out of the profile by itself.

The app sets no cap on connection requests of its own since 2026-10-22, and `schema` drops
`connections_per_week` and `connections_per_day` from a person's LINKEDIN_LIMITS. One profile
still carried both, with a comment and a test of the person's own saying the key "is 20", and
nothing told them it did nothing (the audit of 2026-11-10, PD-10). The ignored keys are now a
profile upgrade's to take out, the rest of the setting kept. Every value here is invented.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import schema  # noqa: E402


def test_the_keys_the_app_drops_are_named():
    assert schema.ignored_limits({"connections_per_week": 20, "inmail_credits_per_month": 15,
                                  "connections_per_day": 5}) == ["connections_per_day",
                                                                 "connections_per_week"]
    assert schema.ignored_limits({"inmail_credits_per_month": 15}) == []


def test_the_command_says_them_and_changes_nothing(tmp_path):
    # Moved with the review of 2026-11-11: it took them out by itself; now it says them only.
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof)
    with open(prof / "networking.py", "a", encoding="utf-8") as fh:
        fh.write('\nLINKEDIN_LIMITS = {"connections_per_week": 20, '
                 '"inmail_credits_per_month": 15}\n')
    env = dict(os.environ, LJS_PROFILE=str(prof), LJS_STATE=str(prof / "state"))
    tool = os.path.join(ROOT, "tools", "network", "state.py")

    def run(*args):
        return subprocess.run([sys.executable, tool, "linkedin-limits", *args], env=env,
                              capture_output=True, encoding="utf-8", timeout=120)
    got = run("--dry")
    assert got.returncode == 0 and got.stdout.strip() == "1", got.stdout + got.stderr
    before = (prof / "networking.py").read_text(encoding="utf-8")
    got = run()
    assert got.returncode == 0 and "connections_per_week" in got.stdout, got.stdout + got.stderr
    assert (prof / "networking.py").read_text(encoding="utf-8") == before


def test_nothing_is_taken_out_of_the_persons_settings_without_asking(tmp_path):
    """The review of 2026-11-11: an upgrade deleted the keys from the person's own settings,
    which a test of theirs may read. It is said, and asked, never done by itself."""
    import profile_upgrades as U
    u = U.by_id("linkedin-limits-ignored")
    assert u.needs == "you" and u.cost == "question" and not u.command, u
    assert u.ask.endswith("?") and len(u.ask.split()) <= 40
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof)
    with open(prof / "networking.py", "a", encoding="utf-8") as fh:
        fh.write('\nLINKEDIN_LIMITS = {"connections_per_week": 20}\n')
    env = dict(os.environ, LJS_PROFILE=str(prof), LJS_STATE=str(prof / "state"))
    got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "network", "state.py"),
                          "linkedin-limits", "--apply"], env=env, capture_output=True,
                         encoding="utf-8", timeout=120)
    assert "connections_per_week" in (prof / "networking.py").read_text(encoding="utf-8")
    assert "does nothing" in got.stdout or "do nothing" in got.stdout, got.stdout + got.stderr
