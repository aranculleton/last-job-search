"""A LinkedIn export given to a chat is saved, and its history imported, before anything is
written from it.

On 2026-10-21 a chat read messages.csv straight from the person's unzipped download to
write follow-ups, and never saved it or imported it: only Connections.csv was ever kept,
and the message log held just the messages for the people being written to, so no later
chat could see the rest of the conversations. The connections import read Connections.csv
alone from an archive, by design. Every name, address and message here is invented
(tests/fixtures/linkedin_export/README.md).
"""
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import export as E  # noqa: E402
import person  # noqa: E402
import sources  # noqa: E402
import state  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "linkedin_export"
CSVS = ("Connections.csv", "messages.csv", "Invitations.csv", "Profile.csv")


def _state(tmp_path, monkeypatch):
    """This test's own state, with the invented contact book and log in it."""
    st = tmp_path / "state"
    st.mkdir()
    monkeypatch.setenv("LJS_STATE", str(st))
    shutil.copy(FIX / "book_contacts.csv", st / "network_contacts.csv")
    shutil.copy(FIX / "book_threads.csv", st / "network_threads.csv")
    return st, str(st / "network_contacts.csv"), str(st / "network_threads.csv")


def _archive(path, names=CSVS):
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.write(FIX / n, n)
        z.writestr("Ad_Targeting.csv", "Audience\n25-34\n")
    return path


def test_take_saves_the_export_and_imports_its_history_once(tmp_path, monkeypatch):
    st, c, t = _state(tmp_path, monkeypatch)
    before = len(state.load_threads(t))
    lines = E.take([str(_archive(tmp_path / "Basic_LinkedInDataExport.zip"))], c, t)
    kept = st / "documents" / "linkedin"
    assert sorted(p.name for p in kept.iterdir()) == sorted(CSVS)
    assert lines[0].startswith("Saved Connections.csv, messages.csv, Invitations.csv and "
                               "Profile.csv. I read only those from the archive; the other "
                               "file in it was not opened.")
    assert lines[1].startswith("Imported ") and "Nothing was sent." in lines[1]
    after = len(state.load_threads(t))
    assert after > before
    # Taken again, nothing is added twice.
    E.take([str(kept)], c, t)
    assert len(state.load_threads(t)) == after


def test_take_fills_what_the_book_lacks_from_the_connections_and_never_replaces_it(
        tmp_path, monkeypatch):
    """A take imported the messages and invitations only: a contact the book knew by its
    profile address alone kept no name, employer or title, whatever Connections.csv said
    (the maintainer, 2026-11-04). A take fills what is missing, never a value already there
    (the export's employer and title are as of the day they connected), adds nobody, and
    says what it filled; the same file again fills again and doubles nothing."""
    st, c, t = _state(tmp_path, monkeypatch)
    rows = state.load_contacts(c)
    by = {r["contact_id"]: r for r in rows}
    by["larkspur_retail_castellan"].update(name="", title="", company="", company_key="")
    by["fernhill_freight_okonedo"].update(title="Head of Planning", company="", company_key="")
    state.save_contacts(rows, c)
    lines = E.take([str(_archive(tmp_path / "Basic_LinkedInDataExport.zip"))], c, t)
    after = {r["contact_id"]: r for r in state.load_contacts(c)}
    juno, hal = after["larkspur_retail_castellan"], after["fernhill_freight_okonedo"]
    assert (juno["name"], juno["title"], juno["company"], juno["company_key"]) == (
        "Juno Castellan", "Analytics Manager", "Larkspur Retail", "larkspur retail")
    assert (hal["title"], hal["company"]) == ("Head of Planning", "Fernhill Freight")
    assert len(after) == len(rows)                     # a connection not in the book is not added
    said = [ln for ln in lines if ln.startswith("Filled ")]
    assert said and "2 contacts" in said[0] and "as of the day you connected" in said[0], lines
    # The same file again: the history stays once, and what went missing is filled again.
    logged = len(state.load_threads(t))
    rows = state.load_contacts(c)
    next(r for r in rows if r["contact_id"] == "fernhill_freight_okonedo")["company"] = ""
    state.save_contacts(rows, c)
    again = E.take([str(st / "documents" / "linkedin")], c, t)
    assert len(state.load_threads(t)) == logged
    assert {r["contact_id"]: r for r in state.load_contacts(c)}[
        "fernhill_freight_okonedo"]["company"] == "Fernhill Freight"
    assert any(ln.startswith("Filled ") and "1 contact" in ln for ln in again), again


def test_files_says_plainly_when_the_history_was_never_saved(tmp_path, monkeypatch, capsys):
    st, _c, _t = _state(tmp_path, monkeypatch)
    kept = st / "documents" / "linkedin"
    kept.mkdir(parents=True)
    shutil.copy(FIX / "Connections.csv", kept / "Connections.csv")   # what the old import kept
    assert E.main(["files"]) == 0
    out = capsys.readouterr().out
    assert "NOT SAVED: messages.csv and Invitations.csv are not in documents/linkedin/" in out
    assert "export.py take" in out and "Never read the files straight from the download" in out
    for n in ("messages.csv", "Invitations.csv"):
        shutil.copy(FIX / n, kept / n)
    assert E.main(["files"]) == 0
    assert "NOT SAVED" not in capsys.readouterr().out


def test_history_read_from_a_download_saves_it_first(tmp_path, monkeypatch, capsys):
    st, c, t = _state(tmp_path, monkeypatch)
    download = tmp_path / "Downloads" / "Complete_LinkedInDataExport"
    shutil.copytree(FIX, download)
    assert E.main(["history", "--from", str(download), "--contacts", c, "--threads", t]) == 0
    assert "Saved Connections.csv, messages.csv, Invitations.csv" in capsys.readouterr().out
    assert (st / "documents" / "linkedin" / "messages.csv").exists()


def test_the_connections_import_takes_the_whole_download(tmp_path, monkeypatch):
    st, _c, t = _state(tmp_path, monkeypatch)
    folder = tmp_path / "Basic_LinkedInDataExport"
    folder.mkdir()
    for n in CSVS:
        shutil.copy(FIX / n, folder / n)
    monkeypatch.setattr(state, "THREADS_CSV", t)
    monkeypatch.setattr(state, "CONTACTS_CSV", str(st / "network_contacts.csv"))
    said = sources.import_connections(str(folder))
    assert said.startswith("Saved your ") and "Imported " in said
    assert (st / "documents" / "linkedin" / "Invitations.csv").exists()


def test_on_a_computer_it_is_kept_in_the_main_folder_not_a_chats_own(tmp_path, monkeypatch):
    # A chat's own folder is removed when its work lands, and everything saved in it goes too.
    monkeypatch.delenv("LJS_STATE", raising=False)
    monkeypatch.setattr(person, "main_checkout", lambda: str(tmp_path / "main"))
    assert E.home() == str(tmp_path / "main" / "documents" / "linkedin")
    monkeypatch.setattr(person, "main_checkout", lambda: None)
    assert E.home() == person.state("documents", "linkedin")
    monkeypatch.setenv("LJS_STATE", str(tmp_path / "elsewhere"))
    assert E.home() == str(tmp_path / "elsewhere" / "documents" / "linkedin")


def test_the_download_is_found_on_the_computer_and_nothing_else_is(tmp_path, monkeypatch,
                                                                    capsys):
    st, c, t = _state(tmp_path, monkeypatch)
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    (home / "Desktop").mkdir()
    older = _archive(home / "Downloads" / "Basic_LinkedInDataExport_09-01-2026.zip")
    with zipfile.ZipFile(home / "Downloads" / "photos.zip", "w") as z:
        z.writestr("Connections.csv", "not LinkedIn's")                  # not named for it
    newer = home / "Desktop" / "Complete_LinkedInDataExport_10-20-2026"
    newer.mkdir()
    for n in CSVS:
        shutil.copy(FIX / n, newer / n)
    # Both dated from the file system's own clock, a day apart: dated from Python's, the two
    # were on different clocks once the release check moved Python's date on (2026-10-29).
    newest = os.path.getmtime(newer)
    os.utime(older, (newest - 86400, newest - 86400))
    assert E.find_exports(str(home)) == [str(newer), str(older)]
    # The person's own folder: HOME, and on Windows USERPROFILE, which is where Python
    # looks there (https://docs.python.org/3/library/os.path.html#os.path.expanduser).
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    assert E.main(["take", "--find", "--contacts", c, "--threads", t]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"Found {newer}") and "Imported " in out
    # A computer with none says so, and the steps to get one.
    monkeypatch.setenv("HOME", str(tmp_path / "nobody"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "nobody"))
    assert E.main(["take", "--find"]) == 3
    assert "linkedin-export-files" in capsys.readouterr().out


def test_a_repo_that_kept_only_the_connections_is_brought_its_history(tmp_path, monkeypatch):
    import profile_upgrades as U
    st, _c, _t = _state(tmp_path, monkeypatch)
    u = U.by_id("linkedin-history")
    assert u.pending() == ""                                   # nothing given: nothing to ask
    kept = st / "documents" / "linkedin"
    kept.mkdir(parents=True)
    shutil.copy(FIX / "Connections.csv", kept / "Connections.csv")
    assert "messages.csv" in u.pending()
    assert "take --find" in u.run and u.needs == "you"
    shutil.copy(FIX / "messages.csv", kept / "messages.csv")
    assert u.pending() == ""


def test_a_download_opened_one_folder_deeper_is_found(tmp_path):
    inner = tmp_path / "Downloads" / "Basic_LinkedInDataExport" / "Basic_LinkedInDataExport"
    inner.mkdir(parents=True)
    for n in ("Connections.csv", "messages.csv"):
        shutil.copy(FIX / n, inner / n)
    assert E.find_exports(str(tmp_path)) == [str(inner)]
