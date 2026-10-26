"""The app runs on the Python a Mac already has, and says so plainly when it cannot.

A person's Mac ran the app on its own python3, 3.9.6. Five calls used zip(strict=),
a 3.10 keyword: the merge driver crashed, so every merge touching the contact book or
the message log stopped with one side's copy in the file; the message checks crashed;
and the text screen raised on the postings whose hard cuts it exists to apply. CI's
floor leg now runs the whole suite on 3.9, so this cannot come back unseen; these
tests pin the parts a run of the suite on a newer Python would not notice.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import merge_state  # noqa: E402
import python_floor  # noqa: E402
from tests import repo_files  # noqa: E402


def test_no_tool_uses_a_keyword_newer_than_the_floor():
    # Static, so it fails on 3.13 too, before the floor leg ever runs.
    newer = re.compile(r"\bzip\([^)]*\bstrict\s*=|\bpairwise\(|^\s*match\s+\S.*:\s*$", re.M)
    found = [f"{p.relative_to(ROOT)}" for p in repo_files.files("tools/**/*.py")
             if "openroles" not in p.parts and newer.search(p.read_text(encoding="utf-8"))]
    assert found == [], found


def test_an_older_python_is_told_in_one_sentence_what_to_install():
    msg = python_floor.message("3.8.9", "darwin")
    assert msg.startswith("Python 3.9 or newer is needed; this is 3.8.9.")
    assert "xcode-select --install" in msg and msg.count(".") >= 2
    assert "python.org" in python_floor.message("3.8.0", "win32")
    assert not python_floor.ok((3, 8)) and python_floor.ok((3, 9)) and python_floor.ok((3, 13))
    for system in ("darwin", "win32", "linux"):
        assert "—" not in python_floor.message("3.8.0", system)


def test_the_merge_driver_never_leaves_one_sides_copy(tmp_path):
    # A driver that cannot merge (an old Python, a crash, no python3) exits with
    # something other than 0 or 1, writes nothing, and git's own line merge runs
    # instead, so the conflict is marked in the file rather than the other side's
    # rows silently lost.
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "merge_state.py").write_text("import sys\nsys.exit(3)\n")
    base, ours, theirs = (tmp_path / n for n in ("base", "ours", "theirs"))
    base.write_text("id,status\na,sent\n")
    ours.write_text("id,status\na,replied\n")
    theirs.write_text("id,status\na,closed\n")
    # The files by their names in the folder it runs in, as git hands the driver its own
    # (.merge_file_XXXXXX): a Windows path, its backslashes unquoted, is not one sh reads.
    cmd = (merge_state.DRIVER.replace("%O", base.name).replace("%A", ours.name)
           .replace("%B", theirs.name).replace("%P", "network_contacts.csv"))
    r = subprocess.run(["sh", "-c", cmd], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode != 0
    merged = ours.read_text()
    assert "<<<<<<<" in merged and "replied" in merged and "closed" in merged


def test_a_crash_inside_the_driver_writes_nothing(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("simulated")
    monkeypatch.setattr(merge_state, "merge", boom)
    files = []
    for name, text in (("o", "x\n"), ("a", "ours\n"), ("b", "theirs\n")):
        p = tmp_path / name
        p.write_text(text)
        files.append(str(p))
    assert merge_state.main(files + ["network_threads.csv"]) == merge_state.COULD_NOT
    assert (tmp_path / "a").read_text() == "ours\n"


def test_env_check_names_python_pytest_and_pyyaml(monkeypatch, capsys):
    import env_check
    monkeypatch.setattr(env_check, "hosts", lambda: [])          # no network in a test
    monkeypatch.setattr(env_check, "board_hosts", lambda: [])
    env_check.main()
    out = capsys.readouterr().out
    assert "Python 3.9+" in out and "pytest" in out and "pyyaml" in out


def test_the_driver_floor_is_the_apps_floor():
    assert merge_state.FLOOR == python_floor.FLOOR


def test_a_new_column_goes_on_the_end_and_rows_keep_their_fields(tmp_path, capsys):
    # The contact book's first save after an update put found_via in its schema place,
    # moving every later field of every row: a whole-file rewrite two chats then
    # collided on line by line.
    sys.path.insert(0, str(ROOT / "tools" / "network"))
    import state
    path = tmp_path / "network_contacts.csv"
    path.write_text("contact_id,name,status,my_note\nfen_1,Tamsin Oyelaran,awaiting_reply,hi\n")
    rows = state._read_csv(str(path), ["contact_id", "name", "found_via", "status"])
    # Nothing in the new column yet: the file is left as it was (one save was a 460-line
    # change to a 229-row book when the empty column went on every row).
    state._write_csv(str(path), rows, ["contact_id", "name", "found_via", "status"])
    assert path.read_text().splitlines()[0] == "contact_id,name,status,my_note"
    rows[0]["found_via"] = "export"
    state._write_csv(str(path), rows, ["contact_id", "name", "found_via", "status"])
    lines = path.read_text().splitlines()
    assert lines[0] == "contact_id,name,status,my_note,found_via"
    assert lines[1] == "fen_1,Tamsin Oyelaran,awaiting_reply,hi,export"
    assert "gains column(s) found_via" in capsys.readouterr().err


def test_a_pension_plans_name_and_its_short_name_are_one_employer():
    import company_key
    assert company_key.key("Fenwick Teachers' Pension Plan") == company_key.key("Fenwick Teachers'")
    assert company_key.key("Fenwick Teachers’ Pension Fund") == company_key.key("Fenwick Teachers'")


def test_the_sentence_itself_reads_on_a_python_older_than_the_floor():
    """SETUP.md sends a Linux whose Python is too old to `python3 tools/python_floor.py`
    for the one command it needs. Its first line was `from __future__ import annotations`,
    which Python 3.6 (RHEL 8's, Ubuntu 18.04's) refuses before running anything, so the
    sentence was a SyntaxError (2026-10-25). Parsed here with 3.6's grammar, and no
    annotation in it is evaluated."""
    import ast
    path = ROOT / "tools" / "python_floor.py"
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src, feature_version=(3, 6))
    futures = [a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
               and n.module == "__future__" for a in n.names]
    assert "annotations" not in futures
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            notes = [a.annotation for a in node.args.args + node.args.kwonlyargs] + [node.returns]
            # A plain name (str, bool) reads on any Python; `str | None` or `list[str]`
            # only on newer ones, so those are written as text.
            assert all(n is None or isinstance(n, (ast.Constant, ast.Name)) for n in notes), \
                node.name
