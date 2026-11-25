#!/usr/bin/env python3
"""Lint the repo's skill, command, and settings files.

Run from anywhere: python tools/lint_skills.py

Checks:
- Every SKILL.md (.claude/skills/*, .agents/skills/*) has YAML frontmatter that
  parses, with non-empty `name` and `description` keys
- `allowed-tools` entries of the form `Bash(bun run <path> *)` point at files
  that exist (skill paths resolve relative to the repo root and to .agents/)
- Every .claude/commands/*.md starts with a `# /<name>` title
- .claude/settings.json is valid JSON with a permissions.allow list
- Every .claude/agents/*.md has frontmatter whose `name` matches its filename and
  whose `description` is non-empty, any `model` is one the Agent tool accepts, and any
  `tools` names at least one tool, as a comma-separated string or a list
- No skill, command, RUNBOOK.md or routine prompt gives a search window of its own
  (`--jobage <a number>`): the window is the person's (JOB_AGE_DAYS)

Exit code 0 on success, 1 with a failure list otherwise.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import local_path  # the repo's .venv, where env_check --fix installs PyYAML
    local_path.run_in_venv()
    local_path.use_venv()
except Exception:  # noqa: BLE001  the lint must not need it
    pass
try:
    import yaml
except ImportError:
    sys.exit("lint_skills.py requires PyYAML: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def check_skill(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append(f"{rel(path)}: missing YAML frontmatter (file must start with ---)")
        return
    end = text.find("\n---", 4)
    if end == -1:
        errors.append(f"{rel(path)}: unterminated YAML frontmatter")
        return
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        errors.append(f"{rel(path)}: frontmatter is not valid YAML: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(f"{rel(path)}: frontmatter did not parse to a mapping")
        return
    for key in ("name", "description"):
        if not data.get(key):
            errors.append(f"{rel(path)}: frontmatter missing required key '{key}'")

    allowed = data.get("allowed-tools", "")
    if isinstance(allowed, str):
        for match in re.finditer(r"bun run ([^\s)]+)", allowed):
            target = match.group(1).rstrip("*")
            if not target or target.endswith("/"):
                continue
            # Targets may contain globs (e.g. .agents/skills/*/cli/src/cli.ts);
            # require at least one existing file to match.
            if "*" in target:
                if not list(ROOT.glob(target)) and not list((ROOT / ".agents").glob(target)):
                    errors.append(f"{rel(path)}: allowed-tools glob matches no files: {target}")
            else:
                candidates = [ROOT / target, ROOT / ".agents" / target]
                if not any(c.is_file() for c in candidates):
                    errors.append(f"{rel(path)}: allowed-tools references a missing file: {target}")


def check_command(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").lstrip().splitlines()
    first = lines[0] if lines else ""
    if not first.startswith("# /"):
        errors.append(f"{rel(path)}: command file must start with a '# /<name>' title (found: {first[:50]!r})")


def check_settings() -> None:
    path = ROOT / ".claude" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f".claude/settings.json: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(".claude/settings.json: expected top-level JSON value to be an object")
        return
    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict):
        errors.append(".claude/settings.json: expected permissions to be an object")
        return
    if not isinstance(permissions.get("allow"), list):
        errors.append(".claude/settings.json: expected permissions.allow to be a list")


# The values the Agent tool accepts for a subagent's model. `inherit` and an
# absent key both mean the session's model, which is deliberate for the agents
# that must never be downgraded (11-cost-model.md): a typo here would silently
# drop them to whatever the runtime falls back to.
AGENT_MODELS = {"sonnet", "opus", "haiku", "fable", "inherit"}


def check_agent(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 4)
    if not text.startswith("---\n") or end == -1:
        errors.append(f"{rel(path)}: missing YAML frontmatter")
        return
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        errors.append(f"{rel(path)}: frontmatter does not parse: {exc}")
        return
    if meta.get("name") != path.stem:
        errors.append(f"{rel(path)}: name {meta.get('name')!r} does not match the filename")
    if not str(meta.get("description") or "").strip():
        errors.append(f"{rel(path)}: empty description, so nothing routes to it")
    model = meta.get("model")
    if model is not None and model not in AGENT_MODELS:
        errors.append(f"{rel(path)}: model {model!r} is not one of {sorted(AGENT_MODELS)}")
    # `tools` is a comma-separated string or a YAML list (code.claude.com/docs/en/sub-agents).
    # Left off, the agent inherits every tool; given empty or in another shape, what it gets
    # is not what the file seems to say.
    if "tools" in meta:
        tools = meta["tools"]
        names = ([t.strip() for t in tools.split(",")] if isinstance(tools, str)
                 else tools if isinstance(tools, list) else None)
        if not names or not all(isinstance(t, str) and t.strip() for t in names):
            errors.append(f"{rel(path)}: tools {tools!r} is not a comma-separated list of "
                          "tool names (leave it off to inherit every tool)")


# A documented round or search command that names a window of its own overrides the
# person's (profile/search.py JOB_AGE_DAYS, which run_round.py reads when --jobage is left
# off): their window was 10 days, the skill's one command said 14, RUNBOOK.md and the job
# round's prompt said 7, and a round asked for in a chat ranked postings up to 14 days old
# (2026-11-16). A placeholder ("--jobage <days>") is fine; a number is not.
WINDOW = re.compile(r"--jobage[ =]\d+")
WINDOW_DOCS = (".claude/skills/**/*.md", ".claude/commands/*.md", "RUNBOOK.md",
               "automation/prompts/*.md")


def round_window_problems(text: str) -> list[str]:
    """Each search window a document gives in place of the person's own."""
    return [m.group(0) for m in WINDOW.finditer(text)]


def check_round_windows() -> None:
    for pattern in WINDOW_DOCS:
        for path in sorted(ROOT.glob(pattern)):
            for hit in round_window_problems(path.read_text(encoding="utf-8")):
                errors.append(
                    f"{rel(path)}: `{hit}` gives a search window of its own, which overrides "
                    "the person's (JOB_AGE_DAYS in profile/search.py): leave --jobage off, or "
                    "write `--jobage <days>` for a window the person asked for one search")


def main() -> int:
    skills = sorted(ROOT.glob(".claude/skills/*/SKILL.md")) + sorted(ROOT.glob(".agents/skills/*/SKILL.md"))
    commands = sorted((ROOT / ".claude" / "commands").glob("*.md"))
    if not skills:
        errors.append("no SKILL.md files found - glob roots are wrong or the tree moved")
    if not commands:
        errors.append("no command files found under .claude/commands/")

    agents = sorted((ROOT / ".claude" / "agents").glob("*.md"))
    for agent in agents:
        check_agent(agent)
    for skill in skills:
        check_skill(skill)
    for command in commands:
        check_command(command)
    check_settings()
    check_round_windows()

    if errors:
        print(f"lint_skills: {len(errors)} failure(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(f"lint_skills: OK ({len(skills)} skills, {len(commands)} commands, "
          f"{len(agents)} agents, settings.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
