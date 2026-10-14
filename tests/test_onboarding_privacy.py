"""Guards for the privacy posture of a repo that holds real people's names.

Upstream's version of this file (issue #345) pinned a warning next to the
`gh repo fork` command in the README quick start, because forks of a public
repo cannot be private and `/setup` then wrote personal data into tracked
files. A real user hit exactly that.

This fork is the private repo that warning was telling people to create, so
there is no fork step left to warn next to. The risk did not go away, it
inverted: the danger here is no longer walking into a public fork, it is
someone later making *this* repo public, or a session weakening the rules that
keep personal data out of a surface that could be published. A repo in use
carries named contacts, who may have said things about their own employer in
confidence, plus full employment history and salary expectations.

So the guards are:

1. The docs state plainly that this repo is private and say why, so the fact
   survives the session that knew it.
2. `/setup` still checks where the working copy would publish to BEFORE it
   writes any profile file. That test is unchanged from upstream and still
   load-bearing: `/setup` is exactly the command that would repopulate this
   repo's personal data, and its closing notes fire after everything is
   already on disk.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"
SECURITY = REPO / "SECURITY.md"
SETUP_COMMAND = REPO / ".claude" / "commands" / "setup.md"


def section(text: str, heading: str) -> str:
    """Body of a markdown section up to the next heading of the same level."""
    level = heading.split(" ")[0]
    pattern = re.compile(
        rf"^{re.escape(heading)}\n(.*?)(?=^{level} |\Z)", re.MULTILINE | re.DOTALL
    )
    match = pattern.search(text)
    return match.group(1) if match else ""


class TestTheDocsSayThisRepoIsPrivateAndWhy(unittest.TestCase):
    def test_security_policy_names_the_contact_list_as_the_reason(self):
        text = SECURITY.read_text(encoding="utf-8")
        self.assertIn("private", text.lower(),
                      "SECURITY.md must state the repo is private")
        self.assertIn("network_contacts.csv", text,
                      "SECURITY.md must name the file that is the reason it is private; "
                      "an abstract 'personal data' warning is the one people talk "
                      "themselves out of")

    def test_readme_does_not_walk_anyone_into_a_public_fork(self):
        """The upstream quick start's `gh repo fork` is the exact step #345 was about."""
        text = README.read_text(encoding="utf-8")
        self.assertNotIn(
            "gh repo fork", text,
            "the README must not carry a fork-and-clone quick start: this repo is the "
            "private destination, not a template to fork, and a fork of it would be "
            "public with every contact's name in it",
        )

    def test_readme_states_the_security_posture(self):
        """Matched on the section's content, not its exact heading text.

        This pinned the literal string "## Security posture" and broke when the
        heading was shortened to "## Security", which is a rename and not a
        regression. A guard that fails on an edit it should not care about is a
        guard people learn to ignore.
        """
        text = README.read_text(encoding="utf-8")
        heading = next((h for h in re.findall(r"^## .*$", text, re.M)
                        if "security" in h.lower()), None)
        self.assertIsNotNone(heading, "README lost its security section")
        body = section(text, heading)
        self.assertTrue(body, f"{heading} is empty")
        for phrase in ("allowlist", "instructions"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, body.lower(),
                              f"README's security section must mention {phrase}")


class TestSetupChecksOriginBeforeWriting(unittest.TestCase):
    def test_preflight_exists_and_precedes_profile_generation(self):
        text = SETUP_COMMAND.read_text(encoding="utf-8")
        self.assertIn(
            "git remote get-url origin",
            text,
            "/setup must check where the working copy would publish to",
        )
        preflight_at = text.index("git remote get-url origin")
        writes_at = text.index("## Step 3: Generate Profile Files")
        self.assertLess(
            preflight_at,
            writes_at,
            "the origin check must run before any profile file is written - the "
            "existing Step 4 note fires after everything is already on disk",
        )
        self.assertIn(
            "public",
            text[max(0, preflight_at - 2000) : preflight_at + 2000].lower(),
            "the preflight must be about public visibility, not just remote presence",
        )


if __name__ == "__main__":
    unittest.main()
