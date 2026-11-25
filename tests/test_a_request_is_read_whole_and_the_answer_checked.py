"""Issue 370: a chat read each message literally and narrowly, answered only the newest,
dropped what the earlier ones asked, and met "use an agent" or "use experts" with prose. The
person asked again about fifteen times on one task.

Two shipped agents stop it: `request-interpreter` reads every message of the task before the
chat acts, and `result-checker` fails a reply the person would have to ask about again. Both
are subagents in `.claude/agents/`, written the way Claude Code documents them
(code.claude.com/docs/en/sub-agents, read 2026-11-25): YAML frontmatter with `name` and
`description` required, `tools` as a comma-separated string ("If omitted, the subagent
inherits every tool"), and `model` one of the aliases, `haiku` the smallest. Both stay cheap:
haiku, no project CLAUDE.md, and only the tools reading needs.

These tests pin the frontmatter, the reading rules and the reasons to fail, the core's one
sentence and its fuller home, and that an existing copy gets the files from the sync alone.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS = os.path.join(ROOT, ".claude", "agents")
NAMES = ("request-interpreter", "result-checker")
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
           PYTHONDONTWRITEBYTECODE="1")


def _read(rel: str) -> str:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _norm(text: str) -> str:
    return " ".join(text.split())


def _agent(name: str) -> tuple[dict, str]:
    text = _read(f".claude/agents/{name}.md")
    assert text.startswith("---\n"), name
    head, body = text[4:].split("\n---", 1)
    # Flat "key: value" lines, read without PyYAML (the Python-test job does not install it).
    meta: dict = {}
    for line in head.splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        meta[key.strip()] = {"true": True, "false": False}.get(value, value)
    return meta, _norm(body)


# ------------------------------------------------------------------ the frontmatter

def test_both_agents_are_named_for_their_file_and_run_on_haiku():
    for name in NAMES:
        meta, _ = _agent(name)
        assert meta["name"] == name
        assert meta["model"] == "haiku", name
        assert meta.get("omitClaudeMd") is True, name


def test_each_has_only_the_tools_reading_needs():
    interpreter, _ = _agent("request-interpreter")
    checker, _ = _agent("result-checker")
    assert interpreter["tools"] == "Read"
    assert checker["tools"] == "Read, Grep, Glob"
    for meta in (interpreter, checker):
        tools = {t.strip() for t in meta["tools"].split(",")}
        assert not tools & {"Write", "Edit", "Bash", "Agent", "WebSearch", "WebFetch"}, tools


def test_the_descriptions_say_when_to_use_them():
    interpreter, _ = _agent("request-interpreter")
    checker, _ = _agent("result-checker")
    assert "before acting on any request bigger than a one-line question" in interpreter["description"]
    assert "every message" in interpreter["description"]
    assert "before replying" in checker["description"]
    for meta in (interpreter, checker):
        assert "proactively" in meta["description"]


# ------------------------------------------------------------------ what they do

def test_the_interpreter_holds_the_four_reading_rules():
    _, body = _agent("request-interpreter")
    for phrase in (
        "A new message adds to the earlier ones; it does not replace them.",
        "A complaint means do more and do it better",
        "A quality word applies to the whole process",
        "Asking for an agent or a role means a real run.",
    ):
        assert _norm(phrase) in body, phrase


def test_the_interpreter_returns_requirements_assumptions_done_and_agents():
    _, body = _agent("request-interpreter")
    for heading in ("REQUIREMENTS", "done:", "ASSUMPTIONS", "ask first", "AGENTS (once, in parallel)"):
        assert heading in body, heading
    assert "only if a wrong guess wastes real work" in body
    assert "on the cheapest model that can do it" in body


def test_the_interpreter_knows_every_agent_the_app_ships():
    _, body = _agent("request-interpreter")
    shipped = {f[:-3] for f in os.listdir(AGENTS) if f.endswith(".md")} - set(NAMES)
    assert shipped, "no agents found"
    missing = sorted(a for a in shipped if f"`{a}`" not in body)
    assert missing == [], f"request-interpreter does not offer: {missing}"


def test_the_checker_fails_on_each_of_the_six():
    _, body = _agent("result-checker")
    for phrase in (
        "Any requirement is unmet.",
        "The reply answers only the latest message",
        "Prose stood in for an agent run",
        "The content is generic",
        "It is not on the page",
        "The person would have to ask again",
    ):
        assert _norm(phrase) in body, phrase


def test_the_checker_answers_in_a_fixed_shape_with_evidence():
    _, body = _agent("result-checker")
    for part in ("RESULT: PASS | FAIL", "met | unmet: <evidence", "FAILURES", "FIX"):
        assert part in body, part
    assert "A claim in the reply is not evidence" in body
    assert "On a FAIL the chat fixes every line under FIX before it replies" in body


# ------------------------------------------------------------------ where the rule lives

def test_the_core_tells_every_chat_to_run_them():
    core = _norm(_read("CLAUDE.md"))
    assert _norm(
        "Any request beyond a one-line question: run the `request-interpreter` agent on all its "
        "messages before acting, and `result-checker` before replying, fixing what it fails "
        "(RUNBOOK.md, \"Reading a request\")."
    ) in core


def test_the_fuller_rule_is_in_the_runbook_and_mapped():
    runbook = _read("RUNBOOK.md")
    assert "\n## Reading a request, and checking the answer\n" in runbook
    section = _norm(runbook.split("\n## Reading a request, and checking the answer\n", 1)[1]
                    .split("\n## ", 1)[0])
    for phrase in ("every message the person sent on the task", "once, all at once",
                   "a role asked for is a real run", "On a FAIL, fix every line it gives, then reply",
                   "A one-line question or a plain yes or no skips both"):
        assert phrase in section, phrase
    with open(os.path.join(ROOT, "docs", "rule_map.json"), encoding="utf-8") as fh:
        rules = {r["id"]: r for r in json.load(fh)["rules"]}
    assert rules["interpret-then-check"]["home"] == "RUNBOOK.md"
    assert "page" in rules["interpret-then-check"]["needed_by"]
    assert rules["interpret-then-check-core"]["home"] == "CLAUDE.md"


def test_both_are_placed_in_the_build_and_keep_nothing():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import build_versions
    finally:
        sys.path.pop(0)
    for name in NAMES:
        assert f".claude/agents/{name}.md" in build_versions.KEEPS_NOTHING, name


# ------------------------------------------------------------------ existing copies

def _sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, env=ENV, text=True, encoding="utf-8",
                          errors="replace", capture_output=True, check=True).stdout


def _write(repo, rel, text):
    path = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _commit(repo, msg):
    _sh(repo, "git", "add", "-A")
    _sh(repo, "git", "commit", "-q", "-m", msg)


def test_an_existing_copy_gets_both_agents_from_the_sync_alone(tmp_path):
    # Agents are the app's (tools/personal_paths.py lists nothing under .claude/agents), so
    # the next sync brings new ones with no step for the person, and Claude Code picks up
    # an added file without a restart (code.claude.com/docs/en/sub-agents).
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import personal_paths
    finally:
        sys.path.pop(0)
    for name in NAMES:
        assert not personal_paths.is_personal(f".claude/agents/{name}.md"), name

    app = str(tmp_path / "app")
    os.makedirs(app)
    _sh(app, "git", "init", "-q", "-b", "master")
    for tool in ("sync_app.py", "personal_paths.py"):
        _write(app, f"tools/{tool}", _read(f"tools/{tool}"))
    _write(app, ".gitignore", "__pycache__/\n")
    _write(app, "CHANGELOG.md", "# Changelog\n")
    _write(app, ".claude/agents/news-reader.md", _read(".claude/agents/news-reader.md"))
    _commit(app, "app before the two agents")

    me = str(tmp_path / "me")
    shutil.copytree(app, me, ignore=shutil.ignore_patterns(".git"))
    _sh(me, "git", "init", "-q", "-b", "master")
    _sh(me, "git", "remote", "add", "origin", "https://github.com/someone/my-job-search")
    _commit(me, "Initial commit")
    _write(me, "profile/person.json", "{}\n")
    _commit(me, "set me up")

    for name in NAMES:
        _write(app, f".claude/agents/{name}.md", _read(f".claude/agents/{name}.md"))
    _write(app, "CHANGELOG.md", "# Changelog\n- Two agents read a request whole (issue 370)\n")
    _commit(app, "the two agents")

    r = subprocess.run([sys.executable, os.path.join(me, "tools", "sync_app.py")], cwd=me,
                       env=dict(ENV, LJS_APP_URL=app), text=True, encoding="utf-8",
                       errors="replace", capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    for name in NAMES:
        with open(os.path.join(me, ".claude", "agents", f"{name}.md"), encoding="utf-8") as fh:
            assert fh.read() == _read(f".claude/agents/{name}.md"), name
    with open(os.path.join(me, "profile", "person.json"), encoding="utf-8") as fh:
        assert fh.read() == "{}\n"


def test_the_core_names_no_agent_that_is_not_shipped():
    named = set(re.findall(r"`([a-z]+-[a-z]+)` agent", _read("CLAUDE.md")))
    for name in named:
        assert os.path.isfile(os.path.join(AGENTS, f"{name}.md")), name
