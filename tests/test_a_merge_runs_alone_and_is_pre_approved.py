"""A chat on the person's computer lands its work with commands that are each pre-approved,
the merge above all, each run on its own.

On 2026-10-23 a chained command (`git push ...; gh pr edit ...; gh pr merge 164 --merge`)
was refused by the desktop app's auto mode as "Merge Without Review", although
`.claude/settings.json` allows `Bash(gh pr merge:*)`. Claude Code approves a command only
when a rule matches each part of it, split at `&&`, `||`, `;`, `|`, `|&`, `&` and newlines,
and it resolves those rules before auto mode's own check
(https://code.claude.com/docs/en/permissions, "Compound commands";
https://code.claude.com/docs/en/permission-modes, "How the classifier evaluates actions").
One part with no rule sent the whole chain to that check. Not tested in the desktop app
itself: these pin what the documentation says decides it.
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEPARATORS = re.compile(r"\|&|&&|\|\||[;|&\n]")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _rules():
    allow = json.loads(_read(".claude", "settings.json"))["permissions"]["allow"]
    return [a[5:-1] for a in allow if a.startswith("Bash(") and a.endswith(")")]


def _allowed(command: str) -> bool:
    """Whether one subcommand matches a rule: `prefix:*` (the prefix, then a space or the
    end) or the exact command."""
    for rule in _rules():
        if rule.endswith(":*"):
            stem = rule[:-2]
            if command == stem or command.startswith(stem + " "):
                return True
        elif command == rule:
            return True
    return False


def _landing_block() -> list:
    text = _read("RUNBOOK.md")
    start = text.index("```bash", text.index("**On a computer of your own**"))
    block = text[start + len("```bash"):text.index("```", start + 7)]
    lines = [re.sub(r"\s+#.*$", "", ln).strip() for ln in block.strip().splitlines()]
    return [ln.replace("<number>", "164") for ln in lines if ln]


def test_every_landing_command_is_pre_approved_part_by_part_and_none_is_chained():
    lines = _landing_block()
    assert "gh pr merge 164 --merge" in lines
    for line in lines:
        parts = [p.strip() for p in SEPARATORS.split(line) if p.strip()]
        assert parts == [line], f"chained: {line}"
        assert _allowed(line), f"not pre-approved: {line}"


def test_the_chain_that_was_refused_would_not_match_and_the_merge_alone_does():
    refused = "git push origin HEAD:claude/x; gh pr edit 164 --body-file b.md; gh pr merge 164 --merge"
    parts = [p.strip() for p in SEPARATORS.split(refused) if p.strip()]
    assert not all(_allowed(p) for p in parts)
    assert _allowed("gh pr merge 164 --merge")


def test_the_instructions_say_run_it_alone_and_never_reach_for_bypass():
    runbook, claude = _read("RUNBOOK.md"), _read("CLAUDE.md")
    assert "never chained with `;`, `&&`" in runbook
    assert "never chained" in claude
    rule = runbook[runbook.index("**Auto mode refused it**"):]
    rule = rule[:rule.index("\n\n")]
    assert "never switch to bypass permissions" in rule
    # The person approves the one action in their own words, which auto mode accepts.
    assert "Reply: yes, merge pull request <number>." in rule


def test_writing_to_the_persons_own_page_never_stops_at_an_approval_box():
    # The maintainer, 2026-10-29: each page write asked "Allow Claude to edit this artifact's
    # data?" and brought the chat to the front over the page. Its data and comments are
    # pre-approved; publishing or deleting a page still asks. Not tested in a live chat: this
    # pins the rule, not the dialog.
    allow = json.loads(_read(".claude", "settings.json"))["permissions"]["allow"]
    assert "ArtifactData" in allow and "ArtifactComments" in allow
    assert "Artifact" not in allow
