"""Updates arrive by themselves, unless a person asks to choose when (2026-10-25).

Everyone's repo takes the app's updates on the day's sync. A person who would rather say
when sets `"app_updates": "when_asked"` in their own profile: then a session looks at the
app, says once that a version is waiting, and `sync_app.py --update` takes it only on their
word. These read every place that instructs Claude (the rules, the commands, the skills,
the scheduled tasks' prompts and the tools' own printed lines) for an instruction to run
`--update` that does not wait for that word. What each mode does is tested in
tests/test_sync_app.py.
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


# The person's word, said near the instruction: "when they say", "the person asks".
THEIR_WORD = re.compile(r"\b(?:they|the person|its person|their person)\s+"
                        r"(?:say|says|said|ask|asks|asked|has said)\b", re.I)
UPDATE_FLAG = re.compile(r"sync_app\.py[^\n`]*--update|`--update`")


def _paragraphs(text):
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def test_every_instruction_to_run_update_waits_for_the_persons_word():
    found = []
    for path in _docs():
        for para in _paragraphs(_read(path)):
            if UPDATE_FLAG.search(para) and not THEIR_WORD.search(para):
                found.append(f"{os.path.relpath(path, ROOT)}: {para.strip()[:160]!r}")
    assert not found, "\n".join(found)


def test_a_scheduled_run_never_forces_an_update():
    # The brief's own check takes updates where they arrive by themselves and only looks
    # where the person asked to choose; it never overrides that with --update.
    for path in sorted(str(p) for p in repo_files.files("automation/**/*.md", root=ROOT)):
        assert "--update" not in _read(path), os.path.relpath(path, ROOT)


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


def test_no_tool_prints_an_instruction_to_force_an_update():
    found = []
    for path in sorted(str(p) for p in repo_files.files("tools/**/*.py", root=ROOT)):
        rel = os.path.relpath(path, ROOT)
        if rel.startswith(os.path.join("tools", "openroles")):
            continue
        for text in _printed_strings(path):
            if " " in text and re.search(r"sync_app\.py[^`\"'\n)]*--update", text):
                found.append(f"{rel}: {text.strip()[:160]!r}")
    assert not found, "\n".join(found)


def test_the_option_is_described_where_every_session_reads_it():
    text = " ".join(_read(os.path.join(ROOT, "CLAUDE.md")).split())
    assert '"app_updates": "when_asked"' in text
    assert "--update" in text


def test_the_setting_is_the_persons_own_never_the_apps():
    # Nothing a profile is made from sets it. The page's own code (templates/app/) names it
    # only to offer the choice in Settings, written on the person's tap, and its usual value
    # there is "by themselves".
    page = os.path.join("templates", "app") + os.sep
    for rel in repo_files.tracked(root=ROOT):
        if os.path.normpath(rel).startswith(page):
            continue
        if rel.startswith("profile.example/") or rel.startswith("templates/"):
            assert '"app_updates"' not in _read(os.path.join(ROOT, rel)), rel
    app_js = _read(os.path.join(ROOT, "templates", "app", "app.js"))
    assert re.search(r'USUAL = \{[^}]*app_updates: "auto"', app_js), "the page's usual is not by themselves"


def test_a_security_fix_is_offered_never_forced_where_they_choose():
    text = " ".join(_read(os.path.join(ROOT, "MAINTAINING.md")).split())
    assert "never forced" in text and "when_asked" in text
