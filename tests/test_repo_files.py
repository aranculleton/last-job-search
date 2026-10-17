"""A test reads this tree, never a checkout nested inside it."""
import re
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
