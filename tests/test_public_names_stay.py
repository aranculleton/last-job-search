"""A name a person's own tests may use is never taken away without saying so.

A person's own tests (profile/tests) may use any of the app's public names. 3.5.0 moved
the board reading into tools/openroles and broke dozens of the maintainer's own tests,
and the work towards the release after 3.13.0 removed holidays.is_holiday and
score_eval.EXPECTATIONS with nothing in their place. tools/public_names.py reads the names
the newest release ships from that release's own tag, and a name may go only when
docs/removed_names.json lists it and the CHANGELOG section it names announces it. Until
4.15.1 the names were a snapshot of 89 KB written at every release, a step of its own.

Every case here runs on a copy of the tree, a throwaway git repo; the real files are only
read.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import public_names as P  # noqa: E402
import release  # noqa: E402
from test_a_beginner_is_told_in_plain_words import _plain  # noqa: E402

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com",
           GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", PYTHONDONTWRITEBYTECODE="1")
LINE = ("**`holidays.is_holiday` is gone**: look the day up in `holidays.for_year` instead, "
        "which every count of business days already does.")
EMPTY_LISTING = {"about": "", "removed": []}


def _git(cwd, *args) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout


def _released(tmp, keep=("tools/holidays.py",), tag="v1.0.0") -> str:
    """A git repo in tmp holding the real files in `keep`, the tool itself, a CHANGELOG and an
    empty docs/removed_names.json, its one commit tagged `tag`: the app as a release left it.
    Only these, so each check reads a few files rather than the whole tree."""
    root = str(tmp / "app")
    for f in (*keep, "tools/public_names.py"):
        os.makedirs(os.path.dirname(os.path.join(root, f)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, f), os.path.join(root, f))
    with open(os.path.join(root, P.CHANGELOG), "w", encoding="utf-8") as fh:
        fh.write("# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-10-01\n\n### Added\n\n"
                 "- **Everything.**\n")
    os.makedirs(os.path.join(root, "docs"))
    P.write_removed(root, EMPTY_LISTING)
    _git(root, "init", "-q", "-b", "master")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the release")
    _git(root, "tag", tag)
    return root


def _edit(root: str, path: str, old: str, new: str) -> None:
    full = os.path.join(root, path)
    with open(full, encoding="utf-8") as fh:
        text = fh.read()
    assert old in text
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new))


def _list(root: str, **entry) -> None:
    P.write_removed(root, {"about": "", "removed": [
        dict({"module": "tools/holidays.py", "name": "is_holiday"}, **entry)]})


def _run(root: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, os.path.join(root, "tools", "public_names.py"),
                           "check"], capture_output=True, text=True, encoding="utf-8",
                          cwd=root, env=ENV)


def test_this_tree_keeps_every_name_the_newest_release_ships():
    # The app's own clone compares with its newest release. A person's copy, whose own
    # remote has no app releases, passes and says why; it is never fetched into.
    tag, commit, why = P.newest_release(ROOT)
    r = subprocess.run([sys.executable, "tools/public_names.py", "check"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    _plain(r.stdout)
    # CI's 3.9 leg is a shallow clone, which may not be able to tell; the 3.13 suite can.
    if (not os.path.isdir(os.path.join(ROOT, "profile")) and "could not be asked" not in why
            and why != P.TOO_SHALLOW):
        assert tag, why
    if tag:
        shipped = P.names_at(ROOT, commit)
        assert "is_holiday" in shipped["tools/holidays.py"]
        assert "EXPECTATIONS" in shipped["tools/score_eval.py"]
        assert not any(p.startswith("tools/openroles/") for p in shipped)
        assert not any(n.startswith("_") for ns in shipped.values() for n in ns)
    # Every record is small and announced, whichever release it went in.
    with open(os.path.join(ROOT, P.REMOVED), encoding="utf-8") as fh:
        records = json.load(fh)["removed"]
    assert len(records) >= 53
    assert all(set(e) == set(P.NEEDS) for e in records), [e for e in records if set(e) != set(P.NEEDS)]
    assert not os.path.exists(os.path.join(ROOT, "tools", "public_names.json"))


def test_a_removed_name_fails_until_it_is_listed_and_announced(tmp_path, monkeypatch):
    root = _released(tmp_path)
    _edit(root, "tools/holidays.py", "def is_holiday(", "def was_holiday(")
    assert P.check(root) == ["tools/holidays.py no longer has is_holiday, which v1.0.0 ships."]
    r = _run(root)
    assert r.returncode == 1
    assert "1 name a person's own tests may use is gone" in r.stdout
    assert "docs/removed_names.json" in r.stdout
    _plain(r.stdout)

    # Listed, but not yet with all it needs, or announced nowhere a person reads.
    _list(root, date="2026-10-25")
    assert P.check(root) == ["tools/holidays.py is_holiday: listed in docs/removed_names.json "
                             "with no announced."]
    _list(root, date="25/10/2026", announced="Unreleased")
    assert "not YYYY-MM-DD" in P.check(root)[0]
    _list(root, date="2026-10-25", announced="1.1.0")
    assert P.check(root) == ["tools/holidays.py is_holiday: listed in docs/removed_names.json "
                             "as announced in 1.1.0, but CHANGELOG.md has no [1.1.0]."]
    _list(root, date="2026-10-25", announced="Unreleased")
    assert P.check(root) == ["tools/holidays.py is_holiday: listed in docs/removed_names.json, "
                             "but no entry in [Unreleased] of CHANGELOG.md names it with its "
                             "file (holidays)."]
    # An entry elsewhere does not announce it: the one in the section the record names does.
    _edit(root, P.CHANGELOG, "- **Everything.**\n", "- **Everything.**\n- " + LINE + "\n")
    assert P.check(root) and "no entry in [Unreleased]" in P.check(root)[0]

    # The line under [Unreleased], wrapped the way an entry is: it passes.
    cut = LINE.rfind(" ", 0, 60)
    _edit(root, P.CHANGELOG, "## [Unreleased]\n", "## [Unreleased]\n\n### Removed\n\n- "
          + LINE[:cut] + "\n  " + LINE[cut + 1:] + "\n")
    assert P.check(root) == []
    assert _run(root).returncode == 0

    # Cutting the version names the section, and the record follows it there.
    with open(os.path.join(root, "docs", "NEXT_BUILDER.md"), "w", encoding="utf-8") as fh:
        fh.write("Written at the release of 1.1.0.\n")
    monkeypatch.setattr(release, "tags", lambda root=None: [])
    assert release.cut("1.1.0", "Days off are looked up one way.", root=root) == 0
    assert P._load(root)["removed"][0]["announced"] == "1.1.0"
    assert P.check(root) == []


def test_a_whole_file_gone_is_named_and_a_name_imported_back_is_kept(tmp_path):
    root = _released(tmp_path)
    os.remove(os.path.join(root, "tools", "holidays.py"))
    gone = P.check(root)
    assert gone and all(g.startswith("tools/holidays.py (the file is gone) no longer has")
                        for g in gone)
    # Moved, and imported under its old module: a test using holidays.is_holiday still works.
    root = _released(tmp_path / "again")
    _edit(root, "tools/holidays.py", "def is_holiday(", "def was_holiday(")
    with open(os.path.join(root, "tools", "holiday_rules.py"), "w", encoding="utf-8") as fh:
        fh.write("def is_holiday(day):\n    return False\n")
    with open(os.path.join(root, "tools", "holidays.py"), "a", encoding="utf-8") as fh:
        fh.write("\nfrom holiday_rules import is_holiday  # noqa: E402,F401\n")
    assert P.check(root) == []


def test_the_names_read_are_the_ones_an_import_gives_and_a_new_one_needs_nothing(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "tools", "openroles"))
    os.makedirs(os.path.join(root, "tools", "tests"))
    with open(os.path.join(root, "tools", "sample.py"), "w", encoding="utf-8") as fh:
        fh.write("import os\n"
                 "A, (B, *C) = 1, (2, 3)\n"
                 "D: int = 4\n"
                 "E: int\n"
                 "_F = 5\n"
                 "def g(): pass\n"
                 "async def h(): pass\n"
                 "class K:\n    inner = 1\n"
                 "try:\n    from json import loads as L\nexcept ImportError:\n    L = None\n"
                 "if os.name:\n    M = 1\n"
                 "if __name__ == '__main__':\n    N = 1\n")
    for skipped in ("openroles", "tests"):
        with open(os.path.join(root, "tools", skipped, "x.py"), "w", encoding="utf-8") as fh:
            fh.write("HIDDEN = 1\n")
    assert P.names(root) == {"tools/sample.py": ["A", "B", "C", "D", "K", "L", "M", "g", "h"]}
    # The release's own files are read the same way, from git, openroles and tests left out.
    os.makedirs(os.path.join(root, "docs"))
    _git(root, "init", "-q", "-b", "master")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "the release")
    _git(root, "tag", "v1.0.0")
    tag, commit, _ = P.newest_release(root)
    assert tag == "v1.0.0" and P.names_at(root, commit) == P.names(root)
    with open(os.path.join(root, "tools", "sample.py"), "a", encoding="utf-8") as fh:
        fh.write("NEW = 1\n")
    assert P.check(root) == []


def test_a_shallow_clone_compares_only_what_it_can_tell_and_a_copy_without_releases_passes(tmp_path):
    """CI's 3.9 leg checks out one commit with no tags; a person's copy has its own remote,
    with no app releases on it. A shallow clone compares with a release it can show it holds
    and otherwise passes, plainly, fetching nothing; the second says there is nothing to
    compare with, plainly, and passes."""
    app = _released(tmp_path, tag="v1.0.0")
    with open(os.path.join(app, "tools", "later.py"), "w", encoding="utf-8") as fh:
        fh.write("LATER = 1\n")
    _git(app, "add", "-A")
    _git(app, "commit", "-qm", "work since")
    _git(app, "tag", "v1.1.0")
    _git(app, "commit", "-q", "--allow-empty", "-m", "more work since")
    clone = str(tmp_path / "ci")
    _git(str(tmp_path), "clone", "-q", "--depth=1", "--no-tags", "file://" + app, clone)
    assert _git(clone, "tag", "-l").strip() == ""
    # One commit: v1.1.0 is its parent, beyond the history it holds, so it cannot tell.
    assert P.newest_release(clone) == ("", "", P.TOO_SHALLOW)
    _edit(clone, "tools/later.py", "LATER = 1", "SOONER = 1")
    assert P.check(clone) == []
    r = _run(clone)
    assert r.returncode == 0 and r.stdout.strip() == ("public_names: nothing to compare with: "
                                                      + P.TOO_SHALLOW + "."), r.stdout
    _plain(r.stdout)
    assert _git(clone, "rev-parse", "--is-shallow-repository").strip() == "true"
    assert _git(clone, "tag", "-l").strip() == ""          # nothing fetched or named
    v110 = _git(app, "rev-parse", "v1.1.0").strip()
    assert subprocess.run(["git", "cat-file", "-e", v110 + "^{commit}"], cwd=clone,
                          env=ENV).returncode != 0
    # Two commits: v1.1.0 is within it, so it is compared with, and the name is missed.
    deeper = str(tmp_path / "ci2")
    _git(str(tmp_path), "clone", "-q", "--depth=2", "--no-tags", "file://" + app, deeper)
    tag, commit, why = P.newest_release(deeper)
    assert (tag, commit, why) == ("v1.1.0", v110, "")
    _edit(deeper, "tools/later.py", "LATER = 1", "SOONER = 1")
    assert P.check(deeper) == ["tools/later.py no longer has LATER, which v1.1.0 ships."]

    # A copy made before the newest release keeps what the newest it holds ships.
    _git(app, "checkout", "-q", "-b", "older", "v1.0.0")
    assert P.newest_release(app)[0] == "v1.0.0" and P.check(app) == []
    _git(app, "checkout", "-q", "master")

    # A person's copy: its own remote has no releases, and one with no remote at all.
    mine = str(tmp_path / "mine")
    shutil.copytree(app, mine, ignore=shutil.ignore_patterns(".git"))
    _git(str(tmp_path), "init", "-q", "--bare", "theirs.git")
    _git(mine, "init", "-q", "-b", "master")
    _git(mine, "add", "-A")
    _git(mine, "commit", "-qm", "Initial commit")
    _git(mine, "remote", "add", "origin", "file://" + str(tmp_path / "theirs.git"))
    os.remove(os.path.join(mine, "tools", "later.py"))
    for remote in (True, False):
        if not remote:
            _git(mine, "remote", "remove", "origin")
        r = _run(mine)
        assert r.returncode == 0, r.stdout
        assert r.stdout.startswith("public_names: nothing to compare with: no release of the "
                                   "app is known here"), r.stdout
        assert r.stdout.rstrip().endswith("so no name can have gone."), r.stdout
        assert ("GitHub could not be asked" in r.stdout) is not remote
        _plain(r.stdout)


def test_a_copy_made_before_a_release_compares_with_the_one_it_holds_on_every_run(tmp_path):
    """The process review of 2026-11-11: a clone made at v1.0.0, then v1.1.0 tagged on the
    app with a name added. A full clone was told on its first check that it no longer had
    the name v1.1.0 ships, and passed on its second, because the first run's fetch left the
    commit behind; a shallow clone was told so on every run. A release HEAD does not hold
    is never compared with, and nothing is fetched."""
    app = _released(tmp_path, keep=())
    with open(os.path.join(app, "tools", "thing.py"), "w", encoding="utf-8") as fh:
        fh.write("def old():\n    pass\n")
    _git(app, "add", "-A")
    _git(app, "commit", "-qm", "a thing")
    _git(app, "tag", "-f", "v1.0.0")
    full, shallow = str(tmp_path / "full"), str(tmp_path / "shallow")
    _git(str(tmp_path), "clone", "-q", "file://" + app, full)
    _git(str(tmp_path), "clone", "-q", "--depth=1", "file://" + app, shallow)
    with open(os.path.join(app, "tools", "thing.py"), "a", encoding="utf-8") as fh:
        fh.write("def newer():\n    pass\n")
    _git(app, "commit", "-qam", "a newer thing")
    _git(app, "tag", "v1.1.0")
    v110 = _git(app, "rev-parse", "v1.1.0").strip()
    for clone in (full, shallow):
        _git(clone, "checkout", "-q", "-b", "old")
        for _ in range(2):
            r = _run(clone)
            assert r.returncode == 0, (clone, r.stdout)
            assert r.stdout.strip() == ("public_names: every name v1.0.0 ships is still here, "
                                        "or listed as gone"), (clone, r.stdout)
        assert subprocess.run(["git", "cat-file", "-e", v110 + "^{commit}"], cwd=clone,
                              env=ENV).returncode != 0, clone       # nothing was fetched
    # A name v1.0.0 ships, gone from the copy, is still found.
    _edit(full, "tools/thing.py", "def old(", "def gone(")
    assert P.check(full) == ["tools/thing.py no longer has old, which v1.0.0 ships."]
    # Once the copy takes the release, it compares with that one.
    _git(full, "checkout", "-q", "--", "tools/thing.py")
    _git(full, "fetch", "-q", "origin")
    _git(full, "merge", "-q", "--ff-only", "origin/master")
    assert P.newest_release(full)[:2] == ("v1.1.0", v110)
    # A copy built on none of the releases (its history began after a fresh start) passes.
    _git(full, "checkout", "-q", "--orphan", "fresh")
    _git(full, "commit", "-qm", "a fresh start")
    assert P.newest_release(full) == ("", "", P.NONE_HELD)
    r = _run(full)
    assert r.returncode == 0 and r.stdout.strip() == ("public_names: nothing to compare with: "
                                                      + P.NONE_HELD + "."), r.stdout
    _plain(r.stdout)


def test_asking_for_help_never_writes_anything(tmp_path, monkeypatch, capsys):
    """The engine review of 2026-11-11: hand-rolled commands took `--help` as the command.
    `public_names.py snapshot --help` rewrote the tracked snapshot, `routines.py reminded --help`
    recorded a reminder made today with no task, and `upkeep-record --help` an upkeep with
    none, in the person's registry."""
    wrote = []
    monkeypatch.setattr(P, "write_removed", lambda *a, **k: wrote.append(a))
    monkeypatch.setattr(P, "newest_release", lambda *a, **k: wrote.append(a) or ("", "", ""))
    for argv in (["check", "--help"], ["check", "-h"], ["--help"]):
        assert P.main(argv) == 0 and not wrote, argv
    assert "public_names.py check" in capsys.readouterr().out
    prof = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), prof,
                    ignore=shutil.ignore_patterns("state"))
    reg = prof / "routines.json"
    before = reg.read_bytes() if reg.exists() else None
    env = dict(os.environ, LJS_PROFILE=str(prof), LJS_STATE=str(tmp_path / "state"))
    for cmd in ("reminded", "upkeep-record", "upkeep-forget", "mended", "record", "adopt"):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "routines.py"), cmd,
                            "--help"], env=env, capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0 and "usage" in r.stdout, (cmd, r.stdout, r.stderr)
        assert (reg.read_bytes() if reg.exists() else None) == before, cmd


def test_a_release_publishes_with_no_step_for_its_names(monkeypatch):
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(release, "_gh", lambda args: calls.append(args) or Done())
    monkeypatch.setattr(release, "tags", lambda: ["v3.2.5"])
    sample = [{"version": "3.3.0", "date": "2026-10-19", "notes": "### Fixed\n\n- **A fix.**"}]
    monkeypatch.setattr(release, "sections", lambda text=None: sample)
    assert release.publish() == 0
    # The tag goes out, then the bugs fixed since the last release are looked up to close.
    assert [c[:2] for c in calls] == [["release", "create"], ["issue", "list"]]
