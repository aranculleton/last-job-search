"""Every local path the README points at must exist.

The original guard here asserted the README carried at least one local image,
because upstream's landing page led with a mascot GIF and a broken header image
is a silent, high-visibility failure. This fork's README leads with prose and
carries no images, so that assertion was pinning a fact that had stopped being
true and would have failed forever.

What is worth guarding is the general case the image check was a special case
of: the README is the one file read by someone who knows nothing about the
repo, and it links to CLAUDE.md, RUNBOOK.md, the skill methodology files and
several tools by path. Those paths rot exactly when something is renamed, which
is the moment nobody re-reads the README. So the guard is now over every local
reference, image or link, and it fails on the first one that does not resolve.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
README = REPO / "README.md"

IMG_SRC = re.compile(r'<img[^>]+src="([^"]+)"')
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)")

# Paths that are illustrative rather than real: the layout diagram's tree, and
# the round/scratch directories that only exist mid-run.
GLOBBY = ("*", "<", "$")


class ReadmeLocalReferences(unittest.TestCase):
    def _local_refs(self):
        text = README.read_text(encoding="utf-8")
        refs = IMG_SRC.findall(text) + MD_LINK.findall(text)
        out = []
        for r in refs:
            if r.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if any(c in r for c in GLOBBY):
                continue
            out.append(r.split("#", 1)[0])
        return out

    def test_readme_exists(self):
        self.assertTrue(README.is_file(), "README.md is missing")
        self.assertGreater(len(README.read_text(encoding="utf-8")), 2000,
                           "README.md is suspiciously short")

    def test_readme_links_to_the_files_a_newcomer_needs(self):
        """CLAUDE.md is the real entry point; a README that forgets it is a dead end."""
        text = README.read_text(encoding="utf-8")
        for needed in ("RUNBOOK.md", "SECURITY.md", "CLAUDE.md"):
            with self.subTest(needed=needed):
                self.assertIn(needed, text, f"README no longer mentions {needed}")

    def test_all_local_references_resolve(self):
        refs = self._local_refs()
        self.assertGreater(len(refs), 0, "README has no local references at all")
        for ref in refs:
            with self.subTest(ref=ref):
                self.assertTrue((REPO / ref).exists(),
                                f"README references a path that does not exist: {ref}")


if __name__ == "__main__":
    unittest.main()
