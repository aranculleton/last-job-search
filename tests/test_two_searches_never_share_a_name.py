"""Two searches never share a round's name, and neither is lost when they did.

The maintainer's copy, 2026-11-06: two job chats each named their search r43. Each is a fresh
clone, and tools/run_round.py next_round counted only the rounds in its own folder, so both
took the same number; the second's save would have written over the first's record (the
row-by-row driver merges two lists of the same name into one). Now a round's number also
counts the rounds on GitHub, and a landing that meets two different searches under one name
renames one to the next free name: the one master does not hold yet, or the one being brought
in. Its summary, its left-out list (which names it inside) and, here, its own round folder
and round.log move with it. These run on throwaway copies with a bare origin, the check faked.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import land  # noqa: E402
import run_round  # noqa: E402

GREEN = [sys.executable, "-c", "print('Green.')"]
RED = [sys.executable, "-c", "print('  tests   FAIL'); raise SystemExit(1)"]


def git(cwd, *args, check=True):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=check)


def write(repo, rel, text):
    p = os.path.join(str(repo), rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read(repo, rel):
    with open(os.path.join(str(repo), rel), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def copies(tmp_path, monkeypatch):
    """(origin, a, b): a bare origin whose master holds one earlier search (r42), and two job
    chats' fresh clones, each on a branch of its own."""
    for k, v in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@example.com"),
                 ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@example.com")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("LJS_LAND_CHECK", raising=False)
    origin, seed = tmp_path / "origin.git", tmp_path / "seed"
    git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    git(tmp_path, "init", "-q", "-b", "master", str(seed))
    for name in (".gitignore", ".gitattributes"):
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            write(seed, name, fh.read())
    write(seed, "profile/person.json", "{}\n")
    write(seed, "documents/rounds/r42.json", '[\n {\n  "url": "https://example.com/old"\n }\n]\n')
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "the person's start")
    git(seed, "remote", "add", "origin", str(origin))
    git(seed, "push", "-q", "origin", "master")
    a, b = tmp_path / "a", tmp_path / "b"
    for c, br in ((a, "claude/finding-jobs"), (b, "claude/finding-jobs-2")):
        git(tmp_path, "clone", "-q", str(origin), str(c))
        git(c, "switch", "-q", "-c", br)
    return origin, a, b


def _search(repo, name, urls, work):
    rows = [{"url": u, "title": "Analyst", "company": "Larkspur Ltd"} for u in urls]
    write(repo, f"documents/rounds/{name}.json", json.dumps(rows, indent=1) + "\n")
    write(repo, f"documents/rounds/filtered/{name}.json",
          json.dumps({"round": name, "filtered": [{"url": urls[0] + "/cut"}]}, indent=1) + "\n")
    write(repo, f"rounds/{name}/round.log", run_round.round_stamp(name, work) + "done\n")


def _land(repo, check=GREEN):
    return land.main(["--message", "Search"], root=str(repo), check=check, sleep=lambda s: None)


def _urls(repo, rel):
    return [r["url"] for r in json.loads(read(repo, rel))]


def test_a_search_master_has_keeps_its_name_and_this_chats_takes_the_next(copies, capsys):
    origin, a, b = copies
    _search(a, "r43", ["https://example.com/a1", "https://example.com/a2"], "w-a")
    _search(b, "r43", ["https://example.com/b1"], "w-b")
    assert _land(a) == 0
    git(a, "push", "-q", "origin", "HEAD:refs/heads/master")      # its pull request, merged
    assert _land(b) == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert _urls(b, "documents/rounds/r43.json") == ["https://example.com/a1",
                                                     "https://example.com/a2"], out
    assert _urls(b, "documents/rounds/r44.json") == ["https://example.com/b1"], out
    assert json.loads(read(b, "documents/rounds/filtered/r44.json"))["round"] == "r44"
    assert json.loads(read(b, "documents/rounds/filtered/r43.json"))["filtered"][0]["url"] \
        == "https://example.com/a1/cut"
    # This chat's own round folder moves with its name, so its round.log names it.
    assert not os.path.isdir(os.path.join(str(b), "rounds", "r43"))
    assert "round: r44" in read(b, "rounds/r44/round.log")
    assert "work: w-b" in read(b, "rounds/r44/round.log")
    assert "r43" in out and "r44" in out


def test_a_search_brought_in_from_a_waiting_branch_takes_the_next_name(copies, capsys):
    origin, a, b = copies
    _search(a, "r43", ["https://example.com/a1"], "w-a")
    _search(b, "r43", ["https://example.com/b1", "https://example.com/b2"], "w-b")
    assert _land(a, check=RED) == 1                       # its work waits on its branch
    assert _land(b) == 0, capsys.readouterr().out
    out = capsys.readouterr().out
    assert "brought in work that waited on origin/claude/finding-jobs" in out, out
    assert _urls(b, "documents/rounds/r43.json") == ["https://example.com/b1",
                                                     "https://example.com/b2"], out
    assert _urls(b, "documents/rounds/r44.json") == ["https://example.com/a1"], out
    assert json.loads(read(b, "documents/rounds/filtered/r44.json"))["round"] == "r44"
    assert "round: r43" in read(b, "rounds/r43/round.log")       # this chat's own, kept


def test_one_search_alone_keeps_its_files_exactly(copies, capsys):
    origin, a, b = copies
    _search(a, "r43", ["https://example.com/a1"], "w-a")
    before = read(a, "documents/rounds/r43.json")
    assert _land(a, check=RED) == 1
    assert _land(b) == 0
    capsys.readouterr()
    assert read(b, "documents/rounds/r43.json") == before
    assert not os.path.exists(os.path.join(str(b), "documents", "rounds", "r44.json"))
    # The same search met twice (brought in, then on master) is one search, never renamed.
    git(b, "push", "-q", "origin", "HEAD:refs/heads/master")
    assert _land(a) in (0, 1)
    assert not os.path.exists(os.path.join(str(a), "documents", "rounds", "r44.json"))
    assert read(a, "documents/rounds/r43.json") == before


def test_a_new_round_counts_the_rounds_waiting_on_github(copies):
    origin, a, b = copies
    _search(a, "r43", ["https://example.com/a1"], "w-a")
    assert _land(a, check=RED) == 1                       # r43 waits on GitHub, not on master
    git(b, "fetch", "-q", "origin")
    assert run_round.next_round(os.path.join(str(b), "documents", "rounds")) == "r44"
    # A folder outside any copy counts only itself.
    assert run_round.next_round(os.path.join(str(origin), "nowhere")) == "r1"
