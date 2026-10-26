"""A name a person's own tests may use is never taken away without saying so.

A person's own tests (profile/tests) may use any of the app's public names. 3.5.0 moved
the board reading into tools/openroles and broke dozens of the maintainer's own tests,
and the work towards the release after 3.13.0 removed holidays.is_holiday and
score_eval.EXPECTATIONS with nothing in their place. tools/public_names.py holds the
names the last release shipped, and a name may go only when docs/removed_names.json lists
it with the date, the reason and the CHANGELOG line that tells people.

Every case here runs on a copy of the tree; the real files are only read.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import public_names as P  # noqa: E402
import release  # noqa: E402

LINE = ("**`holidays.is_holiday` is gone**: look the day up in `holidays.for_year` instead, "
        "which every count of business days already does.")


def _copy(tmp, keep=("tools/holidays.py",)) -> str:
    """A copy in tmp of the real files in `keep`, the real snapshot's entries for them,
    the tool itself, CHANGELOG.md and docs/removed_names.json. Only these, so each check
    reads a few files rather than the whole tree."""
    root = str(tmp / "app")
    for f in (*keep, "tools/public_names.py", P.CHANGELOG, P.REMOVED):
        os.makedirs(os.path.dirname(os.path.join(root, f)), exist_ok=True)
        shutil.copy(os.path.join(ROOT, f), os.path.join(root, f))
    shot = P._load(ROOT, P.SNAPSHOT, None)
    with open(os.path.join(root, P.SNAPSHOT), "w", encoding="utf-8") as fh:
        json.dump({f: shot[f] for f in (*keep, "tools/public_names.py") if f in shot}, fh)
    return root


def _edit(root: str, path: str, old: str, new: str) -> None:
    full = os.path.join(root, path)
    with open(full, encoding="utf-8") as fh:
        text = fh.read()
    assert old in text
    with open(full, "w", encoding="utf-8") as fh:
        fh.write(text.replace(old, new))


def _list(root: str, **entry) -> None:
    with open(os.path.join(root, P.REMOVED), encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["removed"] = [dict({"module": "tools/holidays.py", "name": "is_holiday"}, **entry)]
    with open(os.path.join(root, P.REMOVED), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


def _run(root: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, os.path.join(root, "tools", "public_names.py"),
                           "check"], capture_output=True, text=True, encoding="utf-8",
                          cwd=root)


def test_this_tree_keeps_every_name_the_last_release_shipped():
    r = subprocess.run([sys.executable, "tools/public_names.py", "check"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    shot = P._load(ROOT, P.SNAPSHOT, None)
    assert "is_holiday" in shot["tools/holidays.py"]
    assert "EXPECTATIONS" in shot["tools/score_eval.py"]
    assert not any(p.startswith("tools/openroles/") for p in shot)
    assert not any(n.startswith("_") for ns in shot.values() for n in ns)
    with open(os.path.join(ROOT, P.REMOVED), encoding="utf-8") as fh:
        assert isinstance(json.load(fh)["removed"], list)


def test_a_removed_name_fails_until_it_is_listed_with_the_line_that_tells_people(tmp_path):
    root = _copy(tmp_path)
    _edit(root, "tools/holidays.py", "def is_holiday(", "def was_holiday(")
    assert P.check(root) == ["tools/holidays.py no longer has is_holiday."]
    r = _run(root)
    assert r.returncode == 1
    assert "1 name a person's own tests may use is gone" in r.stdout
    assert "docs/removed_names.json" in r.stdout

    # Listed, but not yet with all it needs, or with a line nobody can read.
    _list(root, date="2026-10-25", changelog=LINE)
    assert P.check(root) == ["tools/holidays.py no longer has is_holiday: listed in "
                             "docs/removed_names.json with no reason."]
    _list(root, date="25/10/2026", reason="replaced by business_days", changelog=LINE)
    assert "not YYYY-MM-DD" in P.check(root)[0]
    _list(root, date="2026-10-25", reason="replaced by business_days", changelog=LINE)
    assert P.check(root) == ["tools/holidays.py no longer has is_holiday: listed in "
                             "docs/removed_names.json, but its CHANGELOG line is not in "
                             "CHANGELOG.md."]

    # The line in the CHANGELOG, wrapped the way an entry is: it passes.
    with open(os.path.join(root, P.CHANGELOG), "a", encoding="utf-8") as fh:
        cut = LINE.rfind(" ", 0, 60)
        fh.write("\n- " + LINE[:cut] + "\n  " + LINE[cut + 1:] + "\n")
    assert P.check(root) == []
    assert _run(root).returncode == 0


def test_a_whole_file_gone_is_named_and_a_name_imported_back_is_kept(tmp_path):
    root = _copy(tmp_path)
    os.remove(os.path.join(root, "tools", "holidays.py"))
    gone = P.check(root)
    assert gone and all(g.startswith("tools/holidays.py (the file is gone) no longer has")
                        for g in gone)
    # Moved, and imported under its old module: a test using holidays.is_holiday still works.
    root = _copy(tmp_path / "again")
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
    assert P.snapshot(root)["tools/sample.py"][0] == "A"
    assert not P.stale(root)
    with open(os.path.join(root, "tools", "sample.py"), "a", encoding="utf-8") as fh:
        fh.write("NEW = 1\n")
    assert P.check(root) == [] and P.stale(root)


def test_a_release_that_ships_without_its_snapshot_says_so_after_tagging(monkeypatch, capsys):
    calls = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(release, "_gh", lambda args: calls.append(args) or Done())
    monkeypatch.setattr(release, "tags", lambda: ["v3.2.5"])
    sample = [{"version": "3.3.0", "date": "2026-10-19", "notes": "### Fixed\n\n- **A fix.**"}]
    monkeypatch.setattr(release, "sections", lambda text=None: sample)
    monkeypatch.setattr(P, "stale", lambda root=P.ROOT: True)
    assert release.publish() == 1
    assert [c[:2] for c in calls] == [["release", "create"]]       # the tag went out first
    assert "tools/public_names.py snapshot" in capsys.readouterr().out
    monkeypatch.setattr(P, "stale", lambda root=P.ROOT: False)
    assert release.publish() == 0
