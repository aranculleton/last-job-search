"""The command and skill inventory in RUNBOOK.md must match the files on disk.

Skills and commands with similar names, like /network and /networking, are
easy to confuse. They are not alternatives: `networking` is
the skill that holds the rules and `/network` is one of the four actions it
owns. `/prep` and `/interview` are worse, because both mean "prep" in English
and they take different arguments and read different files.

RUNBOOK.md carries the map ("Commands and skills: what routes where"), moved there from
CLAUDE.md in 4.0 so the core every call loads stays short (docs/rule_map.json); CLAUDE.md
points at it. A map that drifts is worse than none, so this
asserts it against the filesystem: every command it names exists, every command
file is named, and the disambiguation notes are still in the files they warn
about.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_MD = os.path.join(ROOT, "RUNBOOK.md")
COMMANDS = os.path.join(ROOT, ".claude", "commands")
SKILLS = os.path.join(ROOT, ".claude", "skills")
AGENT_SKILLS = os.path.join(ROOT, ".agents", "skills")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import personal_paths  # noqa: E402

SECTION = "## Commands and skills: what routes where"


def claude_md():
    """The file the map lives in (RUNBOOK.md since 4.0)."""
    return open(MAP_MD, encoding="utf-8").read()


def mapped_section():
    s = claude_md()
    start = s.index(SECTION)
    return s[start:s.index("\n## ", start + 10)]


def on_disk():
    return {f[:-3] for f in os.listdir(COMMANDS) if f.endswith(".md")}


def skill_names():
    """A skill's declared `name:`, which is typeable with a slash on its own."""
    out = set()
    for d in os.listdir(SKILLS):
        path = os.path.join(SKILLS, d, "SKILL.md")
        if not os.path.exists(path):
            continue
        m = re.search(r"^name:\s*(\S+)", open(path, encoding="utf-8").read(), re.M)
        if m:
            out.add(m.group(1))
    return out


class TheMapMatchesTheFilesystem(unittest.TestCase):

    def test_the_section_exists(self):
        self.assertIn(SECTION, claude_md())

    def test_the_core_points_at_the_map(self):
        core = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
        self.assertIn('RUNBOOK.md, "Commands and skills: what routes where"', core)

    def test_every_command_named_in_the_map_is_reachable(self):
        """Either a file in .claude/commands/, or a skill's declared name."""
        named = set(re.findall(r"`/([a-z-]+)`", mapped_section()))
        reachable = on_disk() | skill_names()
        missing = sorted(n for n in named if n not in reachable)
        self.assertEqual(missing, [],
                         "RUNBOOK.md names slash commands that are neither a command "
                         "file nor a skill's declared name")

    def test_every_command_on_disk_is_named_in_the_map(self):
        named = set(re.findall(r"`/([a-z-]+)`", mapped_section()))
        unlisted = sorted(on_disk() - named)
        self.assertEqual(unlisted, [],
                         "these commands exist but the map does not mention them, "
                         "so nobody reading the map can discover them")

    def test_a_skill_whose_declared_name_differs_from_its_folder_is_flagged(self):
        """job-scraper declares `name: scrape`, so /scrape works with no command
        file and the directory name is not what gets typed. That mismatch is the
        source of the confusion the map exists to settle, so any skill with one
        must be called out by both names."""
        section = mapped_section()
        for d in sorted(os.listdir(SKILLS)):
            path = os.path.join(SKILLS, d, "SKILL.md")
            if not os.path.exists(path):
                continue
            m = re.search(r"^name:\s*(\S+)", open(path, encoding="utf-8").read(), re.M)
            if not m or m.group(1) == d:
                continue
            with self.subTest(skill=d, declared=m.group(1)):
                self.assertIn(d, section)
                self.assertIn(m.group(1), section)

    def test_the_two_skill_names_that_are_typed_as_commands_are_explained(self):
        """/scrape and /upskill have no command file behind them."""
        section = mapped_section()
        self.assertIn("`/scrape` and `/upskill` work with no", section)

    def test_every_skill_directory_is_named(self):
        section = mapped_section()
        for d in sorted(os.listdir(SKILLS)):
            if os.path.isdir(os.path.join(SKILLS, d)):
                with self.subTest(skill=d):
                    self.assertIn(d, section)


class TheAmbiguousPairsAreDisambiguatedWhereTheyLive(unittest.TestCase):
    """A warning in the map is not enough: the command file is what gets read
    when the command runs."""

    def test_prep_says_it_is_not_interview(self):
        self.assertIn("Not `/interview`", open(os.path.join(COMMANDS, "prep.md"), encoding="utf-8").read())

    def test_interview_says_it_is_not_prep(self):
        self.assertIn("Not `/prep`", open(os.path.join(COMMANDS, "interview.md"), encoding="utf-8").read())

    def test_the_skills_interview_step_is_the_interview_command(self):
        """"Help me prepare for an interview at X" routes to the skill's Step 4, which
        was four lines of its own: no archive, no research, no learned rules, no pack
        on disk. It must defer to /interview, the one place the steps live."""
        skill = open(os.path.join(SKILLS, "job-application-assistant", "SKILL.md"), encoding="utf-8").read()
        step = skill.split("### Step 4: Interview Preparation", 1)[1].split("\n## ", 1)[0]
        step = step.split("\n### ", 1)[0]
        self.assertIn("`/interview`", step)
        self.assertIn(".claude/commands/interview.md", step)
        quick = skill.split("## Quick Commands", 1)[1]
        line = next(ln for ln in quick.splitlines() if "prepare for an interview" in ln)
        self.assertIn("/interview", line)


class ThePortalsAreWhatTheMapClaims(unittest.TestCase):

    def _enabled(self, name):
        s = open(os.path.join(AGENT_SKILLS, name, "SKILL.md"), encoding="utf-8").read()
        m = re.search(r"^enabled:\s*(true|false)", s, re.M)
        return m and m.group(1) == "true"

    def test_linkedin_and_freehire_are_the_apps_portals_and_on_by_default(self):
        # A person switches either off in their profile (PORTALS), never here.
        # Any other folder here is a portal the person built, and theirs.
        apps = sorted(d for d in os.listdir(AGENT_SKILLS)
                      if os.path.isdir(os.path.join(AGENT_SKILLS, d))
                      and not personal_paths.is_personal(f".agents/skills/{d}/SKILL.md"))
        self.assertEqual(apps, ["freehire-search", "linkedin-search"])
        self.assertTrue(all(self._enabled(d) for d in apps))


if __name__ == "__main__":
    unittest.main()
