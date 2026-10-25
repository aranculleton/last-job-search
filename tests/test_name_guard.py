"""No real person's name reaches the app, in its files or in the text around them.

On 2026-10-18 names from a real run's search results went into a code comment, a test,
a commit message and a pull request description, and the leak scan passed them all:
it knows the maintainer's own people, never the strangers a search turns up. These pin
the two guards that close that: tools/name_guard.py (a full name the app has never
carried, in what a change adds or in its PR text) and leak_scan --text (the denylist,
on a PR description and commit messages). Every name here is invented.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import leak_scan  # noqa: E402
import name_guard  # noqa: E402

KNOWN = {"Kestrel", "Mutual", "Head", "Data", "Chief", "Officer", "Then", "Morgan", "Ellis"}


def test_a_name_the_app_never_carried_is_found_and_known_words_are_not():
    assert name_guard.names("took a surname off \"P. Quillon Varga\" here", KNOWN) == [
        "P. Quillon Varga"]
    assert name_guard.names("Then Quillon Varga joined", KNOWN) == ["Then Quillon Varga"]
    assert name_guard.names("Chief Data Officer at Kestrel Mutual", KNOWN) == []
    assert name_guard.names("Morgan Ellis, the example person", KNOWN) == []
    assert name_guard.names("one word: Varga, and lower case quillon varga", KNOWN) == []
    assert name_guard.names("CSV TSV HTTP are acronyms", KNOWN) == []


def test_a_name_with_an_accented_letter_is_a_name_too():
    # Written as [A-Z][a-z], a word with one letter outside ASCII was never a word, so a
    # full name with an accent in it passed whatever it was.
    assert name_guard.names("met Zoë Quillfeather and Íñigo Ibarrondo", KNOWN) == [
        "Zoë Quillfeather", "Íñigo Ibarrondo"]
    assert name_guard.names("then Łucja Wróbelska wrote", KNOWN) == ["Łucja Wróbelska"]
    # The same name typed with combining accents is the same name.
    assert name_guard.names("met Zoe\u0308 Quillfeather", KNOWN) == ["Zoë Quillfeather"]
    assert name_guard.names("Morgan Ellis in Montréal", KNOWN | {"Montréal"}) == []
    assert name_guard.names("ASCII only: Then Quillon Varga", KNOWN) == ["Then Quillon Varga"]


def test_an_accented_word_the_app_holds_is_known(tmp_path, monkeypatch):
    git = _repo(tmp_path)
    monkeypatch.setattr(name_guard, "ROOT", str(tmp_path))
    (tmp_path / "places.md").write_text("Nørrebro and Montréal are places.\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "places")
    known = name_guard.vocabulary("HEAD")
    assert {"Nørrebro", "Montréal", "Morgan"} <= known
    (tmp_path / "places.md").write_text("Nørrebro and Montréal are places.\n"
                                        "Montréal Kestrel, and Søren Quillfeather.\n",
                                        encoding="utf-8")
    assert name_guard.check_diff("master") == ["places.md:2: Søren Quillfeather"]


def _repo(tmp_path):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, env=env,
                       capture_output=True)
    git("init", "-q", "-b", "master")
    (tmp_path / "tools").mkdir()
    (tmp_path / "notes.md").write_text("Morgan Ellis works at Kestrel Mutual.\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    return git


def test_a_change_that_adds_a_real_looking_name_fails_until_it_is_described(tmp_path, monkeypatch):
    git = _repo(tmp_path)
    monkeypatch.setattr(name_guard, "ROOT", str(tmp_path))
    (tmp_path / "notes.md").write_text("Morgan Ellis works at Kestrel Mutual.\n"
                                       "# the parser cut Quillon Varga to one word\n")
    git("commit", "-q", "-am", "add a case")
    assert name_guard.check_diff("master~1") == ["notes.md:2: Quillon Varga"]
    # Described instead of named: clean.
    (tmp_path / "notes.md").write_text("Morgan Ellis works at Kestrel Mutual.\n"
                                       "# the parser cut a short surname\n")
    git("commit", "-q", "-am", "describe it")
    assert name_guard.check_diff("master~2") == []
    # An invented name, added to the allow list on purpose: clean.
    (tmp_path / "notes.md").write_text("Morgan Ellis works at Kestrel Mutual.\n"
                                       "# an invented Quillon Varga for the test\n")
    (tmp_path / "tools" / "name_guard_allow.txt").write_text("Quillon Varga  # invented\n")
    git("add", "-A")
    git("commit", "-q", "-m", "invented")
    assert name_guard.check_diff("master~3") == []


def test_a_name_not_yet_committed_is_found_before_the_commit(tmp_path, monkeypatch):
    # Run before the commit, the check compared HEAD only and passed a new test file that
    # CI, after the commit, failed.
    _repo(tmp_path)
    monkeypatch.setattr(name_guard, "ROOT", str(tmp_path))
    (tmp_path / "new_test.py").write_text("# Quillon Varga, real-looking\n")
    (tmp_path / "notes.md").write_text("Morgan Ellis works at Kestrel Mutual.\nAnd Pell Ansgar.\n")
    assert sorted(name_guard.check_diff("master")) == ["new_test.py:1: Quillon Varga",
                                                      "notes.md:2: And Pell Ansgar"]


def test_a_pr_description_and_commit_messages_are_scanned_too(tmp_path, monkeypatch):
    _repo(tmp_path)
    monkeypatch.setattr(name_guard, "ROOT", str(tmp_path))
    body = tmp_path / "body.md"
    body.write_text("Two surnames restored: Quillon Varga and Morgan Ellis.\n")
    assert name_guard.check_text([str(body)]) == ["body.md:1: Quillon Varga"]
    tokens = tmp_path / "tokens"
    tokens.write_text("Quillon Varga\n")
    assert leak_scan.main(["--text", str(body), "--tokens", str(tokens)]) == 1
    body.write_text("Two surnames restored.\n")
    assert leak_scan.main(["--text", str(body), "--tokens", str(tokens)]) == 0


def test_the_apps_ci_and_ci_local_run_both_guards():
    ci = open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8").read()
    assert "tools/name_guard.py diff" in ci and "tools/name_guard.py text" in ci
    assert "tools/leak_scan.py --text" in ci and "--no-merges" in ci
    # The PR description reaches the shell through env, never inline in the script.
    assert "PR_BODY: ${{ github.event.pull_request.body }}" in ci
    assert "${{ github.event.pull_request.body }}\"" not in ci
    local = open(os.path.join(ROOT, "tools", "ci_local.sh"), encoding="utf-8").read()
    assert "tools/name_guard.py diff" in local


@pytest.mark.parametrize("path", ["tools/openroles/x.py", "texmf/tex/latex/a.sty",
                                  "tools/name_guard_allow.txt"])
def test_vendored_files_and_the_allow_list_are_not_read_as_new_names(path):
    assert name_guard._skipped(path)


def test_a_file_whose_path_git_quotes_is_read_too(tmp_path, monkeypatch):
    """git writes a path with a letter outside ASCII as `+++ "b/notes/Zo\\303\\253 run.md"`,
    and the guard took a path only from `+++ b/`, so every line of such a file was dropped
    and a name in it passed, here and in CI's own check (found 2026-10-25)."""
    git = _repo(tmp_path)
    monkeypatch.setattr(name_guard, "ROOT", str(tmp_path))
    (tmp_path / "notes" / "sub dir").mkdir(parents=True)
    for rel in ("notes/Zoë run.md", "notes/sub dir/plain.md"):
        (tmp_path / rel).write_text("Run found Brannoc Wexley at the bank.\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "notes")
    assert sorted(name_guard.check_diff("master~1")) == [
        "notes/Zoë run.md:1: Brannoc Wexley", "notes/sub dir/plain.md:1: Brannoc Wexley"]
    # The other characters git quotes (a quote mark, a tab), which Windows allows in no
    # file name, are read the same way.
    assert name_guard._diff_lines('+++ "b/a\\"q\\tz\\303\\253.md"\n@@ -0,0 +1 @@\n+x\n') == [
        ('a"q\tzë.md', 1, "x")]


@pytest.mark.parametrize("text, found", [
    ("Thanks to Orla O'Fennick for the run.", ["Orla O'Fennick"]),
    ("Thanks to Orla O’Fennick.", ["Orla O’Fennick"]),
    ("per Dara D'Arcwell", ["Dara D'Arcwell"]),
    ("Brannoc van Wexley said", ["Brannoc van Wexley"]),
    ("then Ines de la Quarvo wrote", ["Ines de la Quarvo"]),
    ("BRANNOC WEXLEY replied", ["BRANNOC WEXLEY"]),
    ("Brannoc  Wexley (two spaces)", ["Brannoc  Wexley"]),
    ("Brannoc Wexley (a no-break space)", ["Brannoc Wexley"]),
    ("Brannoc Wexley replied", ["Brannoc Wexley"]),
])
def test_common_name_shapes_are_names(text, found):
    """O' and D' surnames, a curly apostrophe, particles (van, de la), a name in capitals and
    two spaces between the words all passed, although they are common in the UK, Ireland
    and Canada the app serves (found 2026-10-25)."""
    assert name_guard.names(text, KNOWN) == found


@pytest.mark.parametrize("text", [
    "CSV TSV HTTP are acronyms",
    "DO NOT APPLY COLD at Kestrel",
    "Chief Data Officer at Kestrel Mutual",
    "Head of Data, then Morgan Ellis",
    "I'm Head",
    "Kestrel van",
    "Morgan Ellis O'Kestrel",
    "MY OWN UNSAVED WORK, not committed",
    "Configured SAP ABAP for the Jobseeker API",
])
def test_known_words_in_those_shapes_are_not_names(text):
    known = KNOWN | {"Do", "Not", "Apply", "Cold", "Kestrel", "My", "Own", "Work", "Configured", "SAP",
                     "Jobseeker"}
    assert name_guard.names(text, known) == []
