import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "tools" / "upstream_triage.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "upstream-watch.yml"
UPSTREAM_SLUG = "MadsLorentzen/ai-job-search"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace"
    ).stdout


class TriageRepoFixture(unittest.TestCase):
    """Builds a real git history: a shared base, then an `upstream/master`
    ref that runs ahead, so the triage script can be exercised fully offline.
    """

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

        (self.root / "tools").mkdir()
        shutil.copy(SCRIPT, self.root / "tools" / "upstream_triage.py")
        (self.root / ".github").mkdir()

        git(self.root, "init", "-b", "master")
        git(self.root, "config", "user.name", "Test")
        git(self.root, "config", "user.email", "test@example.com")
        git(self.root, "remote", "add", "upstream",
            f"https://github.com/{UPSTREAM_SLUG}.git")

        self.write("shared.txt", "base\n")
        self.write("kept.py", "print('hi')\n")
        self.commit("init")

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, msg: str) -> str:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", msg)
        return git(self.root, "rev-parse", "HEAD").strip()

    def set_upstream_to_head(self) -> None:
        git(self.root, "update-ref", "refs/remotes/upstream/master", "HEAD")

    def run_triage(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(self.root / "tools" / "upstream_triage.py"), *args],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )


class UpToDateTests(TriageRepoFixture):
    def test_reports_up_to_date_when_not_behind(self):
        self.set_upstream_to_head()
        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Up to date", result.stdout)


class RelevanceFilterTests(TriageRepoFixture):
    def test_commit_touching_only_removed_files_is_skipped(self):
        # Upstream edits a file this fork never had -> not relevant.
        self.write("portals/removed_portal.py", "x = 1\n")
        self.commit("upstream: add removed_portal")
        self.set_upstream_to_head()
        # Fork drops back to before that commit and deletes nothing extra;
        # the file simply is not in fork HEAD.
        git(self.root, "reset", "--hard", "HEAD~1")

        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("touches only files not in this fork", result.stdout)
        self.assertIn("Probably skip", result.stdout)

    def test_commit_touching_kept_files_is_worth_reviewing(self):
        self.write("kept.py", "print('changed')\n")
        self.commit("upstream: change kept.py")
        self.set_upstream_to_head()
        git(self.root, "reset", "--hard", "HEAD~1")

        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Worth reviewing", result.stdout)
        self.assertIn("kept.py", result.stdout)
        # Ready-to-run cherry-pick lines are offered, not executed.
        self.assertIn("git cherry-pick", result.stdout)

    def test_changelog_only_footprint_is_skipped(self):
        self.write("portals/gone.py", "y = 2\n")
        self.write("CHANGELOG.md", "- did a thing\n")
        self.commit("upstream: feature living in removed area + changelog")
        self.set_upstream_to_head()
        # Fork ships CHANGELOG.md but not the removed portal file.
        git(self.root, "reset", "--hard", "HEAD~1")
        self.write("CHANGELOG.md", "- fork changelog\n")
        self.commit("fork changelog")

        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("changelog-only footprint in this fork", result.stdout)


class AlreadyAppliedTests(TriageRepoFixture):
    def test_cherry_picked_commit_drops_off_via_patch_id(self):
        # Upstream adds a feature commit, then a second unrelated commit.
        self.write("kept.py", "print('feature')\n")
        upstream_sha = self.commit("upstream: add feature")
        self.write("shared.txt", "upstream edit\n")
        self.commit("upstream: unrelated change")
        self.set_upstream_to_head()

        # Fork diverges (its own commit first), then cherry-picks the feature.
        # The cherry-pick lands with a DIFFERENT sha but the same patch, so
        # only patch-id matching - not raw sha - can tell it is already ported.
        git(self.root, "reset", "--hard", "HEAD~2")
        self.write("fork_only.txt", "mine\n")
        self.commit("fork: divergent commit")
        git(self.root, "cherry-pick", upstream_sha)

        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        # The feature dropped off via patch-id; only the unrelated commit
        # remains worth reviewing.
        self.assertIn("already applied (cherry-picked)", result.stdout)
        self.assertIn("**1** worth reviewing", result.stdout)


class WontPortTests(TriageRepoFixture):
    def test_listed_sha_is_excluded(self):
        self.write("kept.py", "print('rejected feature')\n")
        rejected = self.commit("upstream: feature the fork rejects")
        self.set_upstream_to_head()
        git(self.root, "reset", "--hard", "HEAD~1")
        self.write(".github/upstream-wontport.txt",
                   f"{rejected[:9]}  # rejected on purpose\n")
        self.commit("fork: won't-port list")

        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("on the fork's won't-port list", result.stdout)


class MissingUpstreamRefTests(TriageRepoFixture):
    def test_missing_ref_degrades_gracefully(self):
        # upstream/master ref never materialized.
        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("was not available", result.stdout)


class WorkflowGuardTests(unittest.TestCase):
    """The workflow must no-op on the upstream template, so a template clone
    never opens an issue by surprise. GitHub Actions can't run offline, so we
    pin the guard by asserting the job's `if` condition excludes upstream."""

    def test_workflow_is_guarded_against_upstream(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(f"github.repository != '{UPSTREAM_SLUG}'", text)

    def test_workflow_runs_only_in_the_public_app(self):
        # Every private copy pays per billed minute; the public app does not.
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("github.repository == 'aranculleton/last-job-search'", text)

    def test_workflow_uses_builtin_token_only(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("GH_TOKEN: ${{ github.token }}", text)
        # A cross-repo PAT is what let an early run write outside its own repo;
        # the built-in token can't. Make sure no PAT secret sneaks back in.
        self.assertNotIn("secrets.", text)

    def test_actions_are_sha_pinned(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- uses:") or stripped.startswith("uses:"):
                ref = stripped.split("uses:", 1)[1].strip()
                self.assertIn("@", ref)
                sha = ref.split("@", 1)[1].split()[0]
                self.assertRegex(sha, r"^[0-9a-f]{40}$",
                                 f"action not SHA-pinned: {ref}")


if __name__ == "__main__":
    unittest.main()


class DisabledPortalCommitsAreSkipped(TriageRepoFixture):
    """A portal that is on disk and switched off is not a portal this fork runs.

    `path_exists` answers "does this fork still ship the file", which is right
    for a deleted file and wrong for a disabled one. An upstream fix to a portal
    this fork keeps switched off applies perfectly and means nothing. Every one
    of those was arriving under "worth reviewing", which is how a weekly report
    gets skimmed and then ignored.
    """

    def _portal(self, name, enabled):
        self.write(f".agents/skills/{name}/SKILL.md",
                   f"---\nname: {name}\nenabled: {enabled}\n---\n\n# {name}\n")
        self.write(f".agents/skills/{name}/cli/src/cli.ts", "export const x = 1;\n")

    def test_a_commit_only_touching_a_disabled_portal_is_skipped(self):
        self._portal("oldboard-search", "false")
        self.commit("fork: ship oldboard-search disabled")
        self.write(".agents/skills/oldboard-search/cli/src/cli.ts",
                   "export const x = 2;\n")
        self.commit("upstream: fix oldboard-search parsing")
        self.set_upstream_to_head()
        git(self.root, "reset", "--hard", "HEAD~1")

        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("only touches portals this fork has disabled", result.stdout)

    def test_a_commit_touching_an_enabled_portal_is_still_worth_reviewing(self):
        self._portal("linkedin-search", "true")
        self.commit("fork: ship linkedin-search enabled")
        self.write(".agents/skills/linkedin-search/cli/src/cli.ts",
                   "export const x = 2;\n")
        self.commit("upstream: fix linkedin-search parsing")
        self.set_upstream_to_head()
        git(self.root, "reset", "--hard", "HEAD~1")

        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Worth reviewing", result.stdout)
        self.assertIn("linkedin-search", result.stdout)
        self.assertNotIn("only touches portals this fork has disabled", result.stdout)

    def test_a_commit_touching_both_is_worth_reviewing(self):
        """The enabled half is real work; the disabled half must not hide it."""
        self._portal("oldboard-search", "false")
        self._portal("linkedin-search", "true")
        self.commit("fork: ship both")
        self.write(".agents/skills/oldboard-search/cli/src/cli.ts", "export const x = 3;\n")
        self.write(".agents/skills/linkedin-search/cli/src/cli.ts", "export const x = 3;\n")
        self.commit("upstream: shared fix across two portals")
        self.set_upstream_to_head()
        git(self.root, "reset", "--hard", "HEAD~1")

        result = self.run_triage()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Worth reviewing", result.stdout)
        self.assertIn("linkedin-search", result.stdout)

    def test_the_comment_marker_after_enabled_does_not_confuse_the_reader(self):
        """The shipped SKILL.md files write `enabled: true  # set to false to ...`."""
        import sys as _s
        _s.path.insert(0, str(REPO_ROOT / "tools"))
        import upstream_triage as U
        self.write(".agents/skills/p/SKILL.md",
                   "---\nenabled: false  # set to true to run this one\n---\n")
        # With "/" between folders, as git names the paths it is compared with, on Windows
        # too.
        self.assertEqual(U.disabled_portal_prefixes(str(self.root / ".agents/skills")),
                         [(self.root / ".agents/skills/p").as_posix() + "/"])
        self.write(".agents/skills/p/SKILL.md",
                   "---\nenabled: true  # set to false to keep it installed but skipped\n---\n")
        self.assertEqual(U.disabled_portal_prefixes(str(self.root / ".agents/skills")), [])

    def test_a_missing_skills_directory_is_not_an_error(self):
        import sys as _s
        _s.path.insert(0, str(REPO_ROOT / "tools"))
        import upstream_triage as U
        self.assertEqual(U.disabled_portal_prefixes("/nonexistent/skills"), [])
