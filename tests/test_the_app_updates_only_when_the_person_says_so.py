"""The app updates only when the person says so (the maintainer, 2026-10-25).

Nothing may make an update run on its own, and no feature may need one mid-task. A session
looks at the app and says once that a version is waiting; `sync_app.py --update` takes it,
and only the person's word runs that. These read every place that instructs Claude (the
rules, the commands, the skills, the scheduled tasks' prompts and the tools' own printed
lines) for an instruction to take the update unasked. What a look and an update actually do
is tested in tests/test_sync_app.py.
"""

import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_files  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _docs():
    pats = ("CLAUDE.md", "AGENTS.md", "README.md", "RUNBOOK.md", "SETUP.md", "MAINTAINING.md",
            ".claude/commands/*.md", ".claude/agents/*.md", ".claude/skills/**/*.md",
            "automation/**/*.md")
    return sorted({str(p) for p in repo_files.files(*pats, root=ROOT) if p.is_file()})


def _prompts():
    return sorted(str(p) for p in repo_files.files("automation/**/*.md", root=ROOT))


# The wording an older copy used, every one of which told Claude to take the update at the
# start of a session, in every scheduled run, or as "always yes".
RETIRED = ("take the app's updates", "taking the app's updates", "takes the app's updates",
           "saving and updating are always yes", "brought in the app's updates",
           "merges what is new", "keeps their copy current")

# The person's word, said near the instruction: "when they say", "only when the person says
# so", "asks for it".
THEIR_WORD = re.compile(r"\b(?:they|the person|its person|their person)\s+"
                        r"(?:say|says|said|ask|asks|asked|has said)\b", re.I)
UPDATE_FLAG = re.compile(r"sync_app\.py[^\n`]*--update|`--update`")


def _paragraphs(text):
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def test_no_doc_uses_the_wording_that_took_the_update_unasked():
    found = []
    for path in _docs():
        low = _read(path).lower()
        for phrase in RETIRED:
            if phrase in low:
                found.append(f"{os.path.relpath(path, ROOT)}: {phrase!r}")
    assert not found, "\n".join(found)


def test_every_instruction_to_update_waits_for_the_persons_word():
    found = []
    for path in _docs():
        for para in _paragraphs(_read(path)):
            if UPDATE_FLAG.search(para) and not THEIR_WORD.search(para):
                found.append(f"{os.path.relpath(path, ROOT)}: {para.strip()[:160]!r}")
    assert not found, "\n".join(found)


def test_a_scheduled_run_never_takes_an_update():
    for path in _prompts():
        assert "--update" not in _read(path), os.path.relpath(path, ROOT)
    common = _read(os.path.join(ROOT, "automation", "prompts", "_common.md"))
    assert "never takes an update" in common


def _printed_strings(path):
    """Every string a tool can print: its constants and f-string parts, docstrings left out."""
    tree = ast.parse(_read(path))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    getattr(body[0], "value", None), ast.Constant):
                docs.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            yield node.value


# The ways to run the sync that never take an update and are fine to print.
HARMLESS = ("--pull", "--worktree", "--own-tests", "--own-test-risks", "--check")
RUN = re.compile(r"sync_app\.py(?P<rest>[^`\"'\n)]*)")


def test_no_tool_prints_an_instruction_to_take_or_check_for_an_update():
    found = []
    for path in sorted(str(p) for p in repo_files.files("tools/**/*.py", root=ROOT)):
        rel = os.path.relpath(path, ROOT)
        if rel.startswith(os.path.join("tools", "openroles")):
            continue
        for text in _printed_strings(path):
            if " " not in text:
                continue                     # an argument list's element, not a printed line
            for m in RUN.finditer(text):
                rest = m.group("rest").strip()
                if rest.startswith(HARMLESS):
                    continue
                if "--update" in rest or "--if-stale" in rest or not rest or rest.startswith(
                        ("--on", "--tools")):
                    found.append(f"{rel}: {text.strip()[:160]!r}")
    assert not found, "\n".join(found)


def test_the_rule_is_in_claude_md_where_every_session_reads_it():
    text = _read(os.path.join(ROOT, "CLAUDE.md"))
    assert "The\n   app updates only when the person says so." in text or \
        "app updates only when the person says so" in " ".join(text.split())
    assert "Saving is always yes" in text


def test_a_security_fix_is_offered_never_forced():
    text = " ".join(_read(os.path.join(ROOT, "MAINTAINING.md")).split())
    assert "A security fix is no exception" in text and "never forced" in text
    assert "A release reaches a person when they ask for it" in text
