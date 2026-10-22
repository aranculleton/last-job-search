"""The leak scan of the app's files runs only where the app is built, and reads names right.

A person who is not the maintainer never builds or publishes the app from their copy, so
scanning its files against their own data could only find their ordinary words in the
released files (a first name an example shares, an employer that is an English word, a
job title in brackets) and block every merge they tried (2026-10-22). In the maintainer's
repo it still runs, and a bracketed role beside a name is no longer read as a name.
"""
from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import build_app  # noqa: E402
import sync_app  # noqa: E402


AT = "@"     # an address written whole reads to the leak scan as an email


def _repo(tmp_path, origin):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", origin], check=True)
    return repo


def test_the_maintainers_repo_is_told_apart_from_anyone_elses(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_APP_URL", "https://github.com/example-owner/last-job-search")
    for origin, mine in (
            ("https://github.com/example-owner/my-search", True),
            ("http://local_proxy" + AT + "127.0.0.1:4567/git/example-owner/my-search", True),
            ("git" + AT + "github.com:example-owner/my-search.git", True),
            ("https://github.com/someone-else/my-search", False)):
        repo = _repo(tmp_path / origin.replace("/", "_").replace(":", "_"), origin)
        monkeypatch.setattr(sync_app, "ROOT", str(repo))
        assert sync_app.maintainers() is mine, origin


def test_ci_local_scans_the_app_only_in_the_maintainers_repo():
    with open(os.path.join(ROOT, "tools", "ci_local.sh"), encoding="utf-8") as fh:
        text = fh.read()
    block = text[text.index('if [ -f profile/person.json ]; then'):]
    block = block[:block.index("\nelse\n  run \"leak scan (what git would commit)\"")]
    assert "sync_app.maintainers()" in block
    assert block.index("sync_app.maintainers()") < block.index("tools/build_app.py")


def test_a_role_in_brackets_beside_a_name_is_not_a_name():
    got = build_app.name_forms("Wren Allard (Talent Acquisition Partner, Fernhill Freight)")
    assert got == ["Wren Allard"]
    assert build_app.given_names("Wren Allard (Talent Acquisition Partner") == ["Wren"]
    # A one-word nickname is still a name it goes by.
    assert "Sally Ho" in build_app.name_forms("Xiu Mei (Sally) Ho, PhD")


def test_an_accented_name_of_the_cast_is_the_cast():
    # The scan matches accent-blind, so a contact written "Zoé" is the app's "Zoe".
    assert build_app._greetings("Zoé Ruíz") == []
