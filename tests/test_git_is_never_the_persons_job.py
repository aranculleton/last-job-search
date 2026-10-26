"""Saving, updating and merging are Claude's job: done without asking, never explained.

On 2026-10-22 a person's chats told her about master, merges, branches and command
options, and asked her to merge. The instructions told them to: a `git revert <sha>` line
at the end of every reply that applied an update, "show the person what it listed and
ask" when a sync stopped, the branch named when work was unfinished, a pull request link
in the morning brief, and every CHANGELOG headline passed on, the maintainer's own news
and tool options included. These pin that none of that reaches anyone but the maintainer.
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_no_instruction_gives_the_person_a_git_command_or_a_branch():
    for parts in (("CLAUDE.md",), ("RUNBOOK.md",), ("automation", "prompts", "_common.md"),
                  (".claude", "commands", "upgrade.md")):
        text = _read(*parts)
        assert "`git revert <sha>` to undo it" not in text, parts
        assert "show the person what it listed and ask" not in text, parts
        assert "name the branch, so the next chat" not in text, parts
        assert "with the PR link" not in text, parts


def test_claude_md_says_git_is_never_asked_about_or_explained():
    text = _read("CLAUDE.md")
    rule = text[text.index("**Git and GitHub are yours"):]
    rule = rule[:rule.index("\n\n")]
    for must in ("never ask", "never describe", "Saved.", "maintainer"):
        assert must in rule, must


def test_saving_and_merging_are_pre_approved_and_nothing_wider():
    allow = json.loads(_read(".claude", "settings.json"))["permissions"]["allow"]
    for needed in ("Bash(git commit:*)", "Bash(git push -u origin HEAD)", "Bash(gh pr merge:*)",
                   "Bash(gh pr create:*)", "Bash(python3 tools/sync_app.py:*)"):
        assert needed in allow, needed
    # A push is approved only in its one exact form: never a wildcard that would let a
    # force push, a deleted branch or another remote through.
    assert not [a for a in allow if a.startswith("Bash(git push") and "*" in a]
    assert not [a for a in allow if a in ("Bash(*)", "Bash(git:*)", "Bash(gh:*)")]
