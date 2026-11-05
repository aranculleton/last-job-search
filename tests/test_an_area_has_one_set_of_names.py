"""`learned.py record` and `learned.py brief` take the same area names.

`record --area networking` was refused while `brief networking` took the word and listed
only the "other" rules, so a rule about messages to people was never kept under the name the
tips and the skills use for them (2026-11-05). The profile is the example person's copy.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import app_state  # noqa: E402


def run(profile, *args):
    env = dict(os.environ, LJS_PROFILE=profile, LJS_STATE=os.path.dirname(profile),
               LJS_COPY="private")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "learned.py"), *args],
                       env=env, capture_output=True, encoding="utf-8", timeout=60, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def test_networking_is_messages_for_record_and_brief_alike(tmp_path):
    profile = app_state.profile_copy(str(tmp_path / "profile"))
    code, out = run(profile, "record", "--area", "networking",
                    "--said", "shorter notes to recruiters please",
                    "--rule", "Notes to recruiters run three lines at most.")
    assert code == 0, out
    for word in ("networking", "messages", "Messages"):
        code, out = run(profile, "brief", word)
        assert code == 0 and "Notes to recruiters run three lines at most." in out, (word, out)
    code, out = run(profile, "list", "networking")
    assert "messages: Notes to recruiters run three lines at most." in out, out


def test_a_word_that_names_no_area_is_refused_by_both_with_the_areas_there_are(tmp_path):
    profile = app_state.profile_copy(str(tmp_path / "profile"))
    for args in (("record", "--area", "astrology", "--said", "x", "--rule", "y"),
                 ("brief", "astrology")):
        code, out = run(profile, *args)
        assert code != 0 and "one of voice, messages" in out, (args, out)
