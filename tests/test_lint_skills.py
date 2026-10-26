import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
LINTER_SCRIPT = REPO_ROOT / "tools" / "lint_skills.py"


def run_linter(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(root / "tools" / "lint_skills.py")],
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )


class LinterRepoFixture(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        tools = self.root / "tools"
        tools.mkdir()
        shutil.copy(LINTER_SCRIPT, tools / "lint_skills.py")
        # The Python-test CI job does not install PyYAML; the separate lint job
        # does. These settings-focused tests only need a valid frontmatter map.
        # The stub parses simple "key: value" lines, enough for the flat
        # frontmatter these fixtures write, so the checks under test see the
        # actual file content instead of a canned mapping.
        (tools / "yaml.py").write_text(
            "class YAMLError(Exception):\n"
            "    pass\n\n"
            "def safe_load(text):\n"
            "    result = {}\n"
            "    for line in (text or '').splitlines():\n"
            "        if ':' in line:\n"
            "            key, _, value = line.partition(':')\n"
            "            result[key.strip()] = value.strip()\n"
            "    return result\n",
            encoding="utf-8",
        )

        command = self.root / ".claude" / "commands" / "setup.md"
        command.parent.mkdir(parents=True)
        command.write_text("# /setup - Test setup command\n", encoding="utf-8")

        skill = self.root / ".claude" / "skills" / "example" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: example\ndescription: Example skill\n---\n",
            encoding="utf-8",
        )

        self.settings = self.root / ".claude" / "settings.json"
        self.write_settings({"permissions": {"allow": []}})

    def write_settings(self, data):
        self.settings.write_text(json.dumps(data), encoding="utf-8")


class SettingsShapeTests(LinterRepoFixture):
    def test_valid_settings_pass(self):
        result = run_linter(self.root)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("lint_skills: OK", result.stdout)

    def test_invalid_json_fails_cleanly(self):
        self.settings.write_text("{not json", encoding="utf-8")

        result = run_linter(self.root)

        self.assertEqual(result.returncode, 1)
        self.assertIn(".claude/settings.json", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_non_object_root_fails_cleanly(self):
        for data in ([], "settings", 1, None):
            with self.subTest(data=data):
                self.write_settings(data)

                result = run_linter(self.root)

                self.assertEqual(result.returncode, 1)
                self.assertIn("top-level JSON value to be an object", result.stdout)
                self.assertNotIn("Traceback", result.stderr)

    def test_non_object_permissions_fails_cleanly(self):
        for permissions in ([], "permissions", 1, None):
            with self.subTest(permissions=permissions):
                self.write_settings({"permissions": permissions})

                result = run_linter(self.root)

                self.assertEqual(result.returncode, 1)
                self.assertIn("expected permissions to be an object", result.stdout)
                self.assertNotIn("Traceback", result.stderr)

    def test_non_list_allow_fails_cleanly(self):
        for allow in ({}, "Bash(bun run:*)", 1, None):
            with self.subTest(allow=allow):
                self.write_settings({"permissions": {"allow": allow}})

                result = run_linter(self.root)

                self.assertEqual(result.returncode, 1)
                self.assertIn("expected permissions.allow to be a list", result.stdout)
                self.assertNotIn("Traceback", result.stderr)
class SkillAndCommandCheckTests(LinterRepoFixture):
    """check_skill()/check_command() are the linter's main job and were
    previously untested - only check_settings() had coverage, so deleting
    e.g. the missing-allowed-tools error survived the whole suite (review
    finding F23, 2026-08-19)."""

    def write_skill(self, frontmatter: str):
        skill = self.root / ".claude" / "skills" / "example" / "SKILL.md"
        skill.write_text(frontmatter, encoding="utf-8")

    def test_allowed_tools_referencing_a_missing_file_fails(self):
        self.write_skill(
            "---\n"
            "name: example\n"
            "description: Example skill\n"
            "allowed-tools: Bash(bun run .claude/skills/example/DOES_NOT_EXIST.ts *)\n"
            "---\n"
        )

        result = run_linter(self.root)

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("allowed-tools references a missing file", result.stdout)
        self.assertIn("DOES_NOT_EXIST.ts", result.stdout)

    def test_allowed_tools_referencing_an_existing_file_passes(self):
        target = self.root / ".claude" / "skills" / "example" / "cli.ts"
        target.write_text("// present\n", encoding="utf-8")
        self.write_skill(
            "---\n"
            "name: example\n"
            "description: Example skill\n"
            "allowed-tools: Bash(bun run .claude/skills/example/cli.ts *)\n"
            "---\n"
        )

        result = run_linter(self.root)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_frontmatter_missing_description_fails(self):
        self.write_skill("---\nname: example\ndescription:\n---\n")

        result = run_linter(self.root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing required key 'description'", result.stdout)

    def test_command_without_slash_title_fails(self):
        command = self.root / ".claude" / "commands" / "setup.md"
        command.write_text("# setup - missing the slash\n", encoding="utf-8")

        result = run_linter(self.root)

        self.assertEqual(result.returncode, 1)
        self.assertIn("must start with a '# /<name>' title", result.stdout)



class AgentCheckTests(LinterRepoFixture):
    """Subagents pin the cost model in their frontmatter (11-cost-model.md):
    research on sonnet, the grounding audit on the session's strongest model.
    A mistyped model or a renamed file would silently change which one runs."""

    def write_agent(self, name: str, frontmatter: str):
        agent = self.root / ".claude" / "agents" / f"{name}.md"
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text(frontmatter + "\nBody.\n", encoding="utf-8")

    def test_a_well_formed_agent_passes(self):
        self.write_agent("researcher", "---\nname: researcher\ndescription: Finds things\nmodel: sonnet\n---")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_a_mistyped_model_fails(self):
        self.write_agent("researcher", "---\nname: researcher\ndescription: Finds things\nmodel: sonet\n---")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("model 'sonet'", result.stdout)

    def test_a_name_that_does_not_match_the_file_fails(self):
        self.write_agent("researcher", "---\nname: research\ndescription: Finds things\n---")
        result = run_linter(self.root)
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not match the filename", result.stdout)


class TheRealAgentsKeepTheirModels(unittest.TestCase):
    def model_of(self, name):
        text = (REPO_ROOT / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
        head = text.split("\n---", 1)[0]
        for line in head.splitlines():
            if line.startswith("model:"):
                return line.split(":", 1)[1].strip()
        return None

    def test_research_runs_on_sonnet(self):
        self.assertEqual(self.model_of("employer-researcher"), "sonnet")

    def test_the_grounding_audit_is_never_downgraded(self):
        self.assertIn(self.model_of("grounding-auditor"), (None, "inherit"))

    def test_both_start_without_the_projects_claude_md(self):
        # The app's CLAUDE.md is about 13,000 tokens on every call a helper makes, and
        # neither needs it: each is self-contained, and profile/CLAUDE.md still loads with
        # the first profile file read (code.claude.com/docs/en/sub-agents, 2026-10-25).
        for name in ("employer-researcher", "grounding-auditor", "news-reader"):
            text = (REPO_ROOT / ".claude" / "agents" / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn("\nomitClaudeMd: true\n", text.split("\n---", 1)[0] + "\n", name)

    def test_the_news_reader_runs_on_the_small_model_and_only_searches(self):
        # The brief's news is searching and listing, nothing more, and it ran in the main
        # chat on the strongest model with the publisher pages in its context (the cost
        # audit, 2026-10-25). `haiku` is one of the aliases a subagent's model takes
        # (code.claude.com/docs/en/sub-agents, 2026-10-25); WebSearch is its only tool, so
        # it opens no page and writes nothing.
        self.assertEqual(self.model_of("news-reader"), "haiku")
        head = (REPO_ROOT / ".claude" / "agents" / "news-reader.md").read_text(
            encoding="utf-8").split("\n---", 1)[0] + "\n"
        self.assertIn("\ntools: WebSearch\n", head)

if __name__ == "__main__":
    unittest.main()
