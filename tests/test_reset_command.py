"""Guards for /reset's two scopes: documents and profile.

Both scopes have the same failure mode - /reset promises a clean slate it
does not deliver, because something that writes personal data is missing
from the Step 1 preview the user confirms and from the Step 3 execution.

Documents scope: /reset ends its documents pass by telling the user "The
`documents/` folder is now empty." That statement is only true if every
personal-data drop folder is actually covered by both the Step 1 preview
and the Step 3 delete block. `documents/postings/` was missing from both
while being documented in documents/README.md and protected as personal
data by tools/security_guards.py (review finding F26, 2026-08-19), so a
reset silently kept the user's hand-pasted job postings.

Profile and state scopes: the same class of gap. /setup writes a person's
profile/ and their state files; a /reset that missed one would leave /rank
scoring against an old profile or /scrape skipping postings as already seen,
while saying the slate is clean. And /setup must write nothing else: in a
person's repo an app-owned file is the app's, and the next sync puts it back.

Both lists are derived - the documents folders from the repository tree, the
files /setup writes from its own Step 3 - so a new drop folder or a new /setup
target fails this test until /reset covers it.
"""
import re
import unittest
from pathlib import Path

from tests import repo_files

REPO = Path(__file__).resolve().parent.parent
RESET = REPO / ".claude" / "commands" / "reset.md"
SETUP = REPO / ".claude" / "commands" / "setup.md"


def tracked_document_subfolders():
    """Names of documents/ subfolders tracked in git (ignores local noise)."""
    # The app's own documents/ folders. A person's repo tracks folders of their own there
    # too (a document for someone else, say), which are theirs, not /reset's list.
    folders = set()
    for line in repo_files.tracked("documents/", root=REPO):
        parts = line.split("/")
        if len(parts) >= 3:  # documents/<subfolder>/<file...>
            folders.add(parts[1])
    return folders


class TestResetCoversEveryDocumentsSubfolder(unittest.TestCase):
    def setUp(self):
        self.text = RESET.read_text(encoding="utf-8")
        self.folders = tracked_document_subfolders()
        # The tree must actually contain the folders this test is about,
        # or the assertions below would pass vacuously.
        self.assertGreaterEqual(len(self.folders), 5, self.folders)

    def test_preview_lists_every_subfolder(self):
        missing = [
            f for f in sorted(self.folders) if f"documents/{f}/" not in self.text
        ]
        self.assertEqual(
            missing,
            [],
            "reset.md's preview never mentions these documents/ subfolders, "
            f"so the user confirms a deletion list that omits them: {missing}",
        )

    def test_delete_block_removes_every_subfolder(self):
        deleted = set(re.findall(r"rm -r?f documents/(\w+)/", self.text))
        missing = sorted(self.folders - deleted)
        self.assertEqual(
            missing,
            [],
            "reset.md's delete block has no rm line for these documents/ "
            'subfolders, yet the command then claims "The `documents/` '
            f'folder is now empty.": {missing}',
        )


def section(text: str, start: str, end: str) -> str:
    """The slice of text from the start marker up to the end marker."""
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def setup_step3_targets():
    """Every path /setup Step 3 writes: its `profile/...` targets and state files."""
    step3 = section(SETUP.read_text(encoding="utf-8"), "## Step 3:", "## Step 4:")
    targets = set(re.findall(r"`(profile/[^`]+)`", step3))
    state = section(step3, "Write the state files", "---")
    targets |= set(re.findall(r"`([\w/]+\.(?:csv|json))`", state))
    return targets


class TestSetupWritesOnlyWhatIsThePersons(unittest.TestCase):
    def test_every_step3_target_is_a_personal_path(self):
        import sys
        sys.path.insert(0, str(REPO / "tools"))
        from personal_paths import is_personal
        targets = setup_step3_targets()
        self.assertGreaterEqual(len(targets), 10, targets)
        app_owned = sorted(t for t in targets if not is_personal(t))
        self.assertEqual(app_owned, [],
                         "/setup Step 3 writes these app-owned paths, which the next "
                         f"sync would put back: {app_owned}")


class TestResetCoversWhatSetupWrites(unittest.TestCase):
    def setUp(self):
        self.text = RESET.read_text(encoding="utf-8")
        self.targets = setup_step3_targets()
        self.state = sorted(t for t in self.targets if not t.startswith("profile/"))
        # /setup must still name its state files, or the checks below are vacuous.
        self.assertIn("job_search_tracker.csv", self.state)
        self.assertIn("network_threads.csv", self.state)

    def test_profile_scope_previews_and_removes_the_whole_profile(self):
        preview = section(self.text, "### If scope includes `profile`:", "### If scope includes `state`:")
        execution = section(self.text, "### Profile reset", "### State reset")
        self.assertIn("profile/", preview)
        self.assertIn("rm -rf profile/", execution)

    def test_state_scope_previews_and_removes_every_state_file(self):
        preview = section(self.text, "### If scope includes `state`:", "### If scope includes `documents`:")
        execution = section(self.text, "### State reset", "### Documents reset")
        missing_preview = [f for f in self.state if f not in preview]
        missing_exec = [f for f in self.state if f not in execution]
        self.assertEqual(missing_preview, [],
                         f"/reset's state preview never mentions: {missing_preview}")
        self.assertEqual(missing_exec, [],
                         f"/reset's state pass never removes: {missing_exec}")

    def test_documents_scope_never_deletes_the_apps_templates(self):
        execution = section(self.text, "### Documents reset", "## Step 4:")
        self.assertIn("is_personal", execution,
                      "the cv/ and cover_letters/ pass must ask personal_paths, or it "
                      "deletes the app's templates and fonts with the person's files")


if __name__ == "__main__":
    unittest.main()
