"""What reaches a person is plain words, and nothing tells them how saving works.

On 2026-10-22 a person's chats told her about master, merges, branches and command
options, and asked her to merge. Some of it came from instructions, some from lines the
tools print that read as if written to her ("Your own tests: 2 now fail", "Improvements
waiting for this repo ... (python3 tools/profile_upgrades.py)", a pull request link at the
foot of every brief). These pin both halves: every line written for the person is free of
git words, commands and ids, and every line a tool prints for Claude says so.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import interview_pack  # noqa: E402
import profile_upgrades as U  # noqa: E402
import sync_app  # noqa: E402
import tips  # noqa: E402

# Words and shapes a person never needs. "GitHub" is not here: the person made their copy
# there, and "your copy on GitHub" is how START_HERE names it.
JARGON = re.compile(r"`|(?<!\w)--[a-z]|\b(?:git|branch(?:es)?|master|merges?|merged|"
                    r"pull requests?|PRs?|commits?|pushed|CI|ci_local|worktrees?|repo|"
                    r"repository|CLI|config\w*|python3?|sha|upgrades?)\b|\.py\b", re.I)


def _plain(text: str, where: str) -> None:
    m = JARGON.search(text or "")
    assert not m, f"{where}: {m.group(0)!r} in {text!r}"
    assert "—" not in (text or ""), where


def test_every_question_and_promise_an_update_shows_is_plain():
    for u in U.REGISTRY:
        for label in ("gives", "ask", "why_ask"):
            _plain(getattr(u, label), f"{u.id}.{label}")
    _plain(U.NO_REPLY, "NO_REPLY")


def test_what_the_person_is_asked_about_their_own_checks_is_plain():
    for name in ("ASK_TIDY", "TIDY_MEANS", "TIDY_YES", "TIDY_NO"):
        _plain(getattr(sync_app, name), name)
    for answer in sync_app.ASK_ANSWERS:
        _plain(answer, "ASK_ANSWERS")


def test_tips_and_the_campaign_offer_are_plain():
    for text in list(tips.FIRST.values()) + [t for _, _, t in tips.TIPS]:
        _plain(text, "tips")
    ctx = {"company": "Kestrel Mutual", "folder": "/nowhere",
           "stages": [{"scheduled": "2026-11-02", "done": False}]}
    _plain(interview_pack.campaign_offer(ctx), "campaign_offer")


def test_lines_a_tool_prints_for_claude_say_so():
    report = sync_app.own_tests_report([("mine::test_x", "AssertionError: 1 != 2")], ROOT)
    assert report.startswith("Claude, not for the person:")
    assert U.line([(U.REGISTRY[0], "missing")]).startswith("Claude:")
    with open(os.path.join(ROOT, "tools", "merge_state.py"), encoding="utf-8") as fh:
        merge = fh.read()
    assert "Tell the person; their word outranks this." not in merge
    assert "Claude: tell the person in plain words" in merge


def test_the_update_lines_a_person_hears_name_no_tool_and_no_maintainer_news():
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("## [Unreleased]")
    end = text.index("\n## [", text.index("\n## [", start + 1) + 1)  # Unreleased and the release before
    for head in sync_app.headlines(text[start:end].splitlines(), maintainer=False):
        assert not head.startswith("`"), head
        assert "maintainer" not in head.lower(), head


# An instruction that has a chat put git in front of the person: each of these is how it
# was worded before 2026-10-22.
TOLD = re.compile(
    r"<PR link>|`git revert <sha>`,?\s+to undo|show the person what it listed and ask"
    r"|name the branch, so the next chat|with the PR link|the person merges it"
    r"|(?:tell|show|give|say to) (?:the person|them)[^.\n]{0,60}\b(?:branch name|pull request"
    r" link|git command|the commit)\b", re.I)


def test_no_instruction_has_a_chat_show_the_person_git():
    files = [os.path.join(ROOT, "CLAUDE.md"), os.path.join(ROOT, "RUNBOOK.md")]
    for folder in (("automation",), ("automation", "prompts"), (".claude", "commands")):
        d = os.path.join(ROOT, *folder)
        files += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".md")]
    for path in files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        m = TOLD.search(text)
        assert not m, f"{os.path.relpath(path, ROOT)}: {m.group(0)!r}"
