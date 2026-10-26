"""Text files keep plain line endings on every computer, Windows included.

Git for Windows checks text files out with CRLF by default (core.autocrlf=true). A CRLF
shell script stops at its first line in bash ("set: pipefail: invalid option", or
"bash\\r: No such file"), and an app file hashed byte for byte no longer matched its
recorded version. `* text=auto eol=lf` keeps every text file LF in the checkout as well
as in the repo; fonts and the documents a person keeps are binary, never touched.
"""
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="needs git")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout


def test_the_first_rule_is_every_text_file_lf():
    rules = [ln.strip() for ln in open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8")
             if ln.strip() and not ln.lstrip().startswith("#")]
    assert rules[0] == "* text=auto eol=lf"


def test_no_app_text_file_holds_crlf():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import repo_files
    bad = []
    for rel in repo_files.tracked():
        try:
            with open(os.path.join(ROOT, rel), "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        if b"\0" not in data and b"\r\n" in data:          # a NUL byte: binary, left alone
            bad.append(rel)
    assert bad == []


@pytest.mark.parametrize("path,binary", [
    ("tools/ci_local.sh", False), ("tools/py.sh", False), ("tools/sync_app.py", False),
    ("network_contacts.csv", False), ("cv/Someone_Resume_ACME.pdf", True),
    ("cover_letters/OpenFonts/fonts/raleway/Raleway-Medium.otf", True),
    ("documents/network/linkedin_export.zip", True), ("texmf/x.tfm", True)])
def test_text_is_lf_and_documents_and_fonts_are_binary(path, binary):
    out = git(ROOT, "check-attr", "text", "eol", "binary", "--", path)
    attrs = {ln.split(": ")[1]: ln.split(": ")[2] for ln in out.splitlines()}
    if binary:
        assert attrs["binary"] == "set" and attrs["text"] == "unset"
    else:
        assert attrs["eol"] == "lf" and attrs["text"] in ("auto", "set")


def test_a_windows_checkout_keeps_scripts_lf_and_binaries_byte_for_byte(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-q", "-b", "master")
    shutil.copy(os.path.join(ROOT, ".gitattributes"), src / ".gitattributes")
    (src / "run.sh").write_bytes(b"#!/usr/bin/env bash\nset -uo pipefail\necho ok\n")
    font = b"OTTO\x00\x0d\x0a\x1a\x0a" + bytes(range(256))
    (src / "Face.otf").write_bytes(font)
    (src / "Resume.pdf").write_bytes(b"%PDF-1.5\r\n" + bytes(range(256)))
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "files")
    win = tmp_path / "win"
    # core.autocrlf=true is what Git for Windows' installer sets by default.
    git(tmp_path, "-c", "core.autocrlf=true", "clone", "-q", str(src), str(win))
    git(win, "config", "core.autocrlf", "true")
    assert b"\r" not in (win / "run.sh").read_bytes()
    assert (win / "Face.otf").read_bytes() == font
    assert (win / "Resume.pdf").read_bytes() == (src / "Resume.pdf").read_bytes()
    # And a file a Windows program saved with CRLF is stored LF, so nothing changed.
    (win / "run.sh").write_bytes(b"#!/usr/bin/env bash\r\nset -uo pipefail\r\necho ok\r\n")
    git(win, "add", "run.sh")
    assert git(win, "diff", "--cached", "--name-only").strip() == ""


def test_a_windows_checkout_made_before_the_rule_is_given_lf_by_the_sync(tmp_path):
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import sync_app
    src = tmp_path / "src"
    src.mkdir()
    git(src, "init", "-q", "-b", "master")
    (src / "run.sh").write_bytes(b"#!/usr/bin/env bash\nset -uo pipefail\necho ok\n")
    (src / "notes.md").write_bytes(b"one\ntwo\n")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "before the rule")
    win = tmp_path / "win"
    git(tmp_path, "-c", "core.autocrlf=true", "clone", "-q", str(src), str(win))
    git(win, "config", "core.autocrlf", "true")
    assert b"\r\n" in (win / "run.sh").read_bytes()          # what Windows checked out
    shutil.copy(os.path.join(ROOT, ".gitattributes"), src / ".gitattributes")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "the rule")
    git(win, "pull", "-q", "--no-rebase")
    (win / "notes.md").write_bytes(b"one\r\ntwo\r\nmine\r\n")    # a change of its own
    assert b"\r" in (win / "run.sh").read_bytes()            # the update left it CRLF
    assert sync_app.lf_checkout(str(win)) == 1
    assert b"\r" not in (win / "run.sh").read_bytes()
    assert (win / "notes.md").read_bytes() == b"one\r\ntwo\r\nmine\r\n"
    assert git(win, "status", "--porcelain").strip() == "M notes.md"
