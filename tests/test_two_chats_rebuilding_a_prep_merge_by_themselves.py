"""Two chats that took the same update a day apart each rebuilt the same call preps, and the
second one's update stopped on every one of them ("master does not merge cleanly"): the 4.9.0
rehearsal on a real copy. A document the app writes and dates is settled by keeping the later
one, with no side copy, and taking an update settles the person's files as a landing does."""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import land  # noqa: E402

PREP = "documents/network/example_pell/prep.md"


def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t" + "@example.com",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True,
                          encoding="utf-8")


def _write(root, day, owed):
    path = os.path.join(root, PREP)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# Prep - Ada Pell\n\nWritten {day}. Next: Await reply.\n\n"
                 f"- You owe a reply: {owed} business days since 2026-10-26.\n")


def test_two_rebuilds_of_one_prep_keep_the_later_and_leave_no_side_copy(tmp_path):
    root = tmp_path / "copy"
    _git(tmp_path, "init", "-q", "-b", "master", str(root))
    _git(root, "config", "user.name", "t")              # a merge commits: a name of its own
    _git(root, "config", "user.email", "t" + "@example.com")
    _write(root, "2026-11-02", 5)
    # A person's copy never saves the spare folder (.gitignore), where the earlier rebuild is
    # kept, out of their folders, as the other side is on every path a merge settles.
    with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write(".other-chat-copies/\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "a prep")
    _git(root, "checkout", "-q", "-b", "other")
    _write(root, "2026-11-04", 7)                        # the chat that rebuilt it a day later
    _git(root, "commit", "-qam", "rebuilt")
    _git(root, "checkout", "-q", "master")
    _write(root, "2026-11-03", 6)
    _git(root, "commit", "-qam", "rebuilt")
    merged, lines = land.merge_in(str(root), "other")
    assert merged, lines
    with open(os.path.join(root, PREP), encoding="utf-8") as fh:
        text = fh.read()
    assert "Written 2026-11-04" in text and "<<<<<<<" not in text
    assert not os.path.exists(os.path.join(root, PREP + ".from-another-chat"))
    assert _git(root, "status", "--porcelain").stdout.strip() == ""
    import merge_state
    spare = os.listdir(os.path.join(root, merge_state.SPARE_DIR))
    assert len(spare) == 1 and spare[0].startswith(PREP.replace("/", "__")), spare
