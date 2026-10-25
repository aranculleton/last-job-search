"""A LinkedIn download is found, and read, the way a Windows computer or a Mac keeps it.

Three ways it was missed (networking audit, 2026-10-25): an archive made by PowerShell
5.1's Compress-Archive names its entries with backslashes, so off Windows none of the
export's files was found in it; OneDrive moves Desktop and Documents into its own folder,
where nothing looked; and a Mac that has not let the app read Downloads raised a
permission error that was reported as "no LinkedIn download on this computer". Every
name in the fixtures is invented (tests/fixtures/linkedin_export/README.md).
"""
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network")]

import export as E  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "linkedin_export"
CSVS = ("Connections.csv", "messages.csv", "Invitations.csv", "Profile.csv")


def _windows_archive(path):
    """An archive whose entries carry backslashes, as Compress-Archive on PowerShell 5.1
    writes them."""
    with zipfile.ZipFile(path, "w") as z:
        for n in CSVS:
            z.writestr("Basic_LinkedInDataExport\\" + n, (FIX / n).read_bytes())
    return path


def test_an_archive_with_backslashes_is_found_and_read(tmp_path):
    (tmp_path / "Downloads").mkdir()
    zip_path = _windows_archive(tmp_path / "Downloads" / "Basic_LinkedInDataExport.zip")
    assert E.find_exports(str(tmp_path)) == [str(zip_path)]
    text, where = E._raw("connections", str(zip_path))
    assert text and where.endswith("Connections.csv")
    dest = tmp_path / "kept"
    line = E.save([str(zip_path)], "all", dest=str(dest))
    assert line.startswith("Saved Connections.csv, messages.csv")
    assert sorted(p.name for p in dest.iterdir()) == sorted(CSVS)


def test_a_download_on_a_onedrive_desktop_is_found(tmp_path):
    folder = tmp_path / "OneDrive - Kestrel Mutual" / "Desktop" / "Basic_LinkedInDataExport"
    folder.mkdir(parents=True)
    for n in ("Connections.csv", "messages.csv"):
        shutil.copy(FIX / n, folder / n)
    assert E.find_exports(str(tmp_path)) == [str(folder)]
    assert str(tmp_path / "OneDrive - Kestrel Mutual" / "Desktop") in E.search_folders(
        str(tmp_path))


def test_the_onedrive_folder_windows_names_is_searched(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    elsewhere = tmp_path / "D" / "OneDrive"
    (elsewhere / "Documents").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("OneDrive", str(elsewhere))
    assert str(elsewhere / "Documents") in E.search_folders()


def test_a_folder_the_computer_would_not_open_is_said_and_never_called_empty(
        tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    for d in ("Downloads", "Desktop", "Documents"):
        (home / d).mkdir(parents=True)
    real = os.scandir

    def scandir(path="."):
        if os.path.basename(str(path)) == "Downloads":
            raise PermissionError(1, "Operation not permitted", str(path))
        return real(path)

    monkeypatch.setattr(E.os, "scandir", scandir)
    denied = []
    assert E.find_exports(str(home), denied=denied) == []
    assert denied == [str(home / "Downloads")]
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    assert E.main(["take", "--find"]) == 3
    out = capsys.readouterr().out
    assert "did not let me look in Downloads" in out
    assert "no LinkedIn download on this computer" not in out


def test_windows_folders_are_asked_for_only_on_windows():
    if sys.platform != "win32":
        assert E._windows_folders() == []


def test_entry_names_split_on_either_slash():
    assert E._entry_name("Export\\Connections.csv") == "Connections.csv"
    assert E._entry_name("Export/sub/messages.csv") == "messages.csv"
    assert E._entry_name("Connections.csv") == "Connections.csv"
