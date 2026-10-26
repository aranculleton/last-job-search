"""Nothing in the app reads or sends mail, or asks the person to connect an account.

The maintainer's ruling of 2026-10-25: no Gmail, no email, no connectors. /gmail-sync
read the person's mailbox through a claude.ai connector and was the last part of the app
that did; it is gone, and so is the research agent that signed in to a Google account
through the Gemini command line. This keeps them gone: a tool name for a mail, calendar
or workspace connector, the page where connectors are switched on, or an instruction to
connect one fails here, wherever it is written.

What stays, because it is not the app using an account: the email address on the
person's own resume, a networking email they send from their own mail, their GitHub copy,
Claude itself, and a LinkedIn download they give the chat as a file. The changelogs keep
their history.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests import repo_files

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().relative_to(ROOT).as_posix()

# The history of what was removed is history, not a use of it.
HISTORY = {"CHANGELOG.md", "CHANGELOG-upstream.md"}

CONNECTOR_TOOL = re.compile(r"mcp__[\w-]*?(?:gmail|google|outlook|notion|slack)", re.I)
CONNECTOR_PAGE = re.compile(r"claude\.ai/(?:customize|settings)/connectors", re.I)
CONNECTOR_TOOLS = re.compile(r"\b(?:ListConnectors|SuggestConnectors)\b")

# An instruction to Claude or to the person, in the files that carry instructions.
INSTRUCTIONS = (".claude/commands/", ".claude/skills/", ".claude/agents/",
                ".claude/workflows/", "automation/")
ASKS_TO_CONNECT = re.compile(
    r"\b(?:connect|sign in to|log in to|authori[sz]e)\b[^.\n]{0,40}"
    r"\b(?:gmail|e-?mail|inbox|outlook|mailbox|calendar|connector|notion|slack)\b"
    r"|\b(?:gmail|outlook|mailbox|connector|notion|slack)\b[^.\n]{0,30}\bconnect", re.I)
NEGATED = re.compile(r"\b(?:never|not|no|don't|do not|nor|without)\b", re.I)


def _app_files() -> list[str]:
    return [p for p in repo_files.tracked(root=ROOT) if p not in HISTORY and p != HERE]


def _text(rel: str) -> str | None:
    try:
        raw = (ROOT / rel).read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:4096]:
        return None
    return raw.decode("utf-8", "replace")


def test_no_file_names_a_mail_or_workspace_connector():
    found = []
    for rel in _app_files():
        text = _text(rel)
        if text is None:
            continue
        for pat in (CONNECTOR_TOOL, CONNECTOR_PAGE, CONNECTOR_TOOLS):
            for m in pat.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                found.append(f"{rel}:{line}: {m.group(0)}")
    assert not found, "the app names a connector:\n" + "\n".join(found)


def test_no_command_or_skill_asks_to_connect_mail_or_an_account():
    found = []
    for rel in _app_files():
        if not rel.startswith(INSTRUCTIONS):
            continue
        text = _text(rel)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in ASKS_TO_CONNECT.finditer(line):
                before = line[max(0, m.start() - 60):m.start()]
                if NEGATED.search(before) or NEGATED.search(m.group(0)):
                    continue
                found.append(f"{rel}:{n}: {line.strip()[:160]}")
    assert not found, "an instruction asks to connect mail or an account:\n" + "\n".join(found)


def test_the_mail_sync_and_the_google_research_agent_are_gone():
    for gone in (".claude/commands/gmail-sync.md", ".claude/agents/gemini-research-expert.md"):
        assert not (ROOT / gone).exists(), gone


def test_the_guard_catches_what_it_is_for():
    assert CONNECTOR_TOOL.search("call mcp__claude_ai_Gmail__search_threads")
    assert CONNECTOR_TOOL.search("mcp__google_calendar__list")
    assert CONNECTOR_PAGE.search("at claude.ai/customize/connectors once")
    line = "Ask them to connect Gmail so the sync can read replies."
    m = ASKS_TO_CONNECT.search(line)
    assert m and not NEGATED.search(line[:m.start()])
    line = "Never ask for their email or to connect Gmail."
    m = ASKS_TO_CONNECT.search(line)
    assert m and NEGATED.search(line[max(0, m.start() - 60):m.start()])
    # The built-in browser's tools are Claude's own, not a connector.
    assert not CONNECTOR_TOOL.search("enable__mcp__remote-devices__Claude_Browser")
