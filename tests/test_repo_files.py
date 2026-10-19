"""A test reads this tree, never a checkout nested inside it."""
import re
import subprocess
from pathlib import Path

from tests import repo_files


def test_a_nested_checkout_is_never_read(tmp_path):
    # A background /upgrade agent's worktree sits at .claude/worktrees/<name>/, a whole
    # copy of the repo with its own .git. A glob over .claude/** read its CHANGELOG and
    # failed a test over a file that is not in this tree.
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "network.md").write_text("ours")
    agent = tmp_path / ".claude" / "worktrees" / "agent-1"
    (agent / ".claude" / "commands").mkdir(parents=True)
    (agent / ".git").write_text("gitdir: /elsewhere/.git/worktrees/agent-1\n")
    (agent / "CHANGELOG.md").write_text("theirs")
    (agent / ".claude" / "commands" / "network.md").write_text("theirs")
    other = tmp_path / "vendor" / "checkout"
    (other / ".git").mkdir(parents=True)
    (other / "README.md").write_text("theirs")
    got = repo_files.files(".claude/**/*.md", "**/*.md", root=tmp_path)
    assert [p.relative_to(tmp_path).as_posix() for p in got] == [".claude/commands/network.md"]


def test_every_recursive_glob_in_the_suite_goes_through_repo_files():
    # One test was fixed for this on 2026-09-24 and the next one written was not.
    recursive = re.compile(r"\.rglob\(|glob\([^)\n]*\*\*")
    here = Path(__file__).resolve().parent
    offenders = [f"{p.name}:{n}" for p in sorted(here.glob("*.py"))
                 if p.name not in ("repo_files.py", Path(__file__).name)
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if recursive.search(line) and "repo_files" not in line]
    assert offenders == [], offenders


def test_tracked_reads_each_name_whole_and_leaves_a_persons_files_out(tmp_path):
    # A person's repo tracks their notes and profile, and a name can hold a space: two
    # tests that listed tracked files themselves failed there on both counts.
    for rel in ("tools/odd name.py", "README.md", "profile/search.py", "handoff/notes.md",
                "documents/README.md", "documents/others/kestrel mutual.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    assert sorted(repo_files.tracked(root=tmp_path)) == [
        "README.md", "documents/README.md", "tools/odd name.py"]
    assert "documents/others/kestrel mutual.md" in repo_files.tracked(root=tmp_path, app_only=False)
    assert repo_files.tracked("tools/", root=tmp_path) == ["tools/odd name.py"]
    assert repo_files.tracked(root=tmp_path / "tools" / "missing") == []


def test_every_listing_of_tracked_files_goes_through_repo_files():
    # repo_files.tracked() is the one that reads names whole and knows whose file is whose.
    here = Path(__file__).resolve().parent
    offenders = [f"{p.name}:{n}" for p in sorted(here.glob("*.py"))
                 if p.name not in ("repo_files.py", Path(__file__).name)
                 for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                 if "ls-files" in line]
    assert offenders == [], offenders
