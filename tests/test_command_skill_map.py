"""The command and skill inventory in CLAUDE.md must match the files on disk.

Skills and commands with similar names, like /network and /networking, are
easy to confuse. They are not alternatives: `networking` is
the skill that holds the rules and `/network` is one of the four actions it
owns. `/prep` and `/interview` are worse, because both mean "prep" in English
and they take different arguments and read different files.

CLAUDE.md now carries the map. A map that drifts is worse than none, so this
asserts it against the filesystem: every command it names exists, every command
file is named, and the disambiguation notes are still in the files they warn
about.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE_MD = os.path.join(ROOT, "CLAUDE.md")
COMMANDS = os.path.join(ROOT, ".claude", "commands")
SKILLS = os.path.join(ROOT, ".claude", "skills")
AGENT_SKILLS = os.path.join(ROOT, ".agents", "skills")

SECTION = "## Commands and skills: what routes where"


def claude_md():
    return open(CLAUDE_MD).read()


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
        m = re.search(r"^name:\s*(\S+)", open(path).read(), re.M)
        if m:
            out.add(m.group(1))
    return out


class TheMapMatchesTheFilesystem(unittest.TestCase):

    def test_the_section_exists(self):
        self.assertIn(SECTION, claude_md())

    def test_every_command_named_in_the_map_is_reachable(self):
        """Either a file in .claude/commands/, or a skill's declared name."""
        named = set(re.findall(r"`/([a-z-]+)`", mapped_section()))
        reachable = on_disk() | skill_names()
        missing = sorted(n for n in named if n not in reachable)
        self.assertEqual(missing, [],
                         "CLAUDE.md names slash commands that are neither a command "
                         "file nor a skill's declared name")

    def test_every_command_on_disk_is_named_in_the_map(self):
        named = set(re.findall(r"`/([a-z-]+)`", mapped_section()))
        unlisted = sorted(on_disk() - named)
        self.assertEqual(unlisted, [],
                         "these commands exist but the map does not mention them, "
                         "so nobody reading CLAUDE.md can discover them")

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
            m = re.search(r"^name:\s*(\S+)", open(path).read(), re.M)
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
    """A warning in CLAUDE.md is not enough: the command file is what gets read
    when the command runs."""

    def test_prep_says_it_is_not_interview(self):
        self.assertIn("Not `/interview`", open(os.path.join(COMMANDS, "prep.md")).read())

    def test_interview_says_it_is_not_prep(self):
        self.assertIn("Not `/prep`", open(os.path.join(COMMANDS, "interview.md")).read())


class ThePortalsAreWhatTheMapClaims(unittest.TestCase):

    def _enabled(self, name):
        s = open(os.path.join(AGENT_SKILLS, name, "SKILL.md")).read()
        m = re.search(r"^enabled:\s*(true|false)", s, re.M)
        return m and m.group(1) == "true"

    def test_only_freehire_is_enabled_by_default(self):
        # linkedin-search ships off: LinkedIn's robots.txt and terms forbid
        # automated access (tools/portals.py). A person turns it on in their
        # profile, never here.
        enabled = sorted(d for d in os.listdir(AGENT_SKILLS)
                         if os.path.isdir(os.path.join(AGENT_SKILLS, d))
                         and self._enabled(d))
        self.assertEqual(enabled, ["freehire-search"])

    def test_the_four_danish_portals_are_all_off(self):
        for name in ("jobbank-search", "jobdanmark-search", "jobindex-search",
                     "jobnet-search"):
            with self.subTest(portal=name):
                self.assertFalse(self._enabled(name),
                                 "%s is a Danish portal and is enabled" % name)


if __name__ == "__main__":
    unittest.main()
