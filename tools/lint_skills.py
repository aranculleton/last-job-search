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
  whose `description` is non-empty, and any `model` is one the Agent tool accepts

Exit code 0 on success, 1 with a failure list otherwise.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import local_path  # the repo's .venv, where env_check --fix installs PyYAML
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
