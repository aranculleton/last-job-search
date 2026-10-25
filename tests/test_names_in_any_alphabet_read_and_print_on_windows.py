"""Text in and out of the app's tools, whatever the computer's own encoding.

Python on Windows reads and writes a pipe in the computer's code page (cp1252 in English)
unless UTF-8 mode is on, and a spreadsheet saves CSV with a byte-order mark ("CSV UTF-8")
or in that same code page (plain "CSV"). Found 2026-10-25:
- a contact called Łukasz, or a reply ending in 👍, stopped a tool halfway through;
- a contact book Excel saved lost every contact's id to the byte-order mark;
- one saved as plain CSV stopped every tool with UnicodeDecodeError;
- in the cloud, whose computers run on UTC, a person's Monday brief was worked out as Sunday.
"""
import io
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
import csv_store  # noqa: E402
import person  # noqa: E402
import python_floor  # noqa: E402


def _cp1252_env(**more):
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env.update(PYTHONIOENCODING="cp1252", PYTHONUTF8="0", LJS_PROFILE="profile.example",
               PYTHONDONTWRITEBYTECODE="1", **more)
    return env


def test_a_tool_prints_any_name_where_the_terminal_is_cp1252():
    code = ("import sys; sys.path.insert(0, 'tools'); import person; "
            "print('Łukasz 👍 李雷'); print(sys.stdin.read().strip())")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=_cp1252_env(),
                       input="Zoë, Ødegård".encode("utf-8"), capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert r.stdout.decode("utf-8").split() == ["Łukasz", "👍", "李雷", "Zoë,", "Ødegård"]


def test_without_the_fix_that_same_print_stops_the_tool():
    # The failure the fix is for, shown on this computer: cp1252 has no Ł.
    r = subprocess.run([sys.executable, "-c", "print('Łukasz')"], env=_cp1252_env(),
                       capture_output=True, timeout=60)
    assert r.returncode != 0 and b"UnicodeEncodeError" in r.stderr


def test_utf8_stdio_changes_only_a_stream_that_is_not_already_utf8(monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    assert python_floor.utf8_stdio(("stdout",)) == ["stdout"]
    sys.stdout.write("Łukasz 👍")
    sys.stdout.flush()
    assert raw.getvalue().decode("utf-8") == "Łukasz 👍"
    assert python_floor.utf8_stdio(("stdout",)) == []


def _profile(tmp_path, timezone):
    d = tmp_path / "profile"
    d.mkdir(parents=True)
    (d / "networking.py").write_text(f'HOME_CITY = "Sydney"\nTIMEZONE = "{timezone}"\n',
                                     encoding="utf-8")
    return str(d)


# A cloud chat runs on a Linux computer. Windows has no time.tzset
# (https://docs.python.org/3/library/time.html#time.tzset, "Availability: Unix"), so no
# chat on it ever sets its zone this way.
NO_TZSET = "a cloud chat runs on Linux; Windows has no time.tzset to change a process's zone"


def test_a_cloud_chat_works_in_the_persons_own_day(tmp_path, monkeypatch):
    # The choice of zone is read on every computer: with an environment of its own, the
    # function sets it there and never needs the process's tzset, so it stands in for one.
    import time
    monkeypatch.setattr(time, "tzset", getattr(time, "tzset", lambda: None), raising=False)
    prof = _profile(tmp_path, "Sydney time (Australia/Sydney)")
    env = {"CLAUDE_CODE_REMOTE": "true"}
    assert person.cloud_day(env, prof) == "Australia/Sydney" and env["TZ"] == "Australia/Sydney"
    # Not in a chat on their own computer, never over a TZ already set, never for the
    # app's own tests (LJS_PROFILE), never a zone this computer has no data for.
    assert person.cloud_day({}, prof) == ""
    assert person.cloud_day({"CLAUDE_CODE_REMOTE": "true", "TZ": "UTC"}, prof) == ""
    assert person.cloud_day({"CLAUDE_CODE_REMOTE": "true", "LJS_PROFILE": "x"}, prof) == ""
    assert person.cloud_day({"CLAUDE_CODE_REMOTE": "true"},
                            _profile(tmp_path / "b", "Mars/Olympus_Mons")) == ""


def test_the_zone_also_comes_from_the_brief_registry(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    (d / "routines.json").write_text('{"timezone": "America/Toronto"}', encoding="utf-8")
    assert person.home_zone_named(str(d)) == "America/Toronto"


@pytest.mark.skipif(sys.platform == "win32", reason=NO_TZSET)
def test_the_date_a_tool_sees_is_the_persons_after_cloud_day(tmp_path):
    prof = _profile(tmp_path, "Australia/Sydney")
    code = ("import sys, os, time; sys.path.insert(0, 'tools'); import person; "
            f"person.cloud_day(profile_dir={prof!r}); print(os.environ.get('TZ'), "
            "time.strftime('%z'))")
    env = {k: v for k, v in os.environ.items() if k not in ("TZ", "LJS_PROFILE")}
    env.update(CLAUDE_CODE_REMOTE="true", PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True,
                       text=True, timeout=60)
    zone, offset = r.stdout.split()
    assert zone == "Australia/Sydney" and offset in ("+1000", "+1100"), r.stderr


HEAD = "contact_id,name,company\r\n"


def test_a_contact_book_excel_saved_as_csv_utf8_keeps_every_id(tmp_path, capsys):
    p = tmp_path / "network_contacts.csv"
    p.write_bytes(b"\xef\xbb\xbf" + (HEAD + "lukasz_w,Łukasz,Acme\r\n")
                  .encode("utf-8"))
    rows = csv_store.read_rows(str(p), ("contact_id", "name", "company"))
    assert rows == [{"contact_id": "lukasz_w", "name": "Łukasz", "company": "Acme"}]
    assert csv_store.header(str(p)) == ["contact_id", "name", "company"]
    csv_store.write_rows(str(p), rows, ("contact_id", "name", "company"))
    saved = p.read_bytes()
    assert not saved.startswith(b"\xef\xbb\xbf") and saved.count(b"\r\n") == 2
    assert b"\xef\xbb\xbfcontact_id" not in saved and saved.count(b"contact_id") == 1
    assert csv_store.dict_rows(str(p))[0]["contact_id"] == "lukasz_w"


def test_one_saved_as_plain_csv_is_read_and_saved_back_in_utf8(tmp_path, capsys):
    p = tmp_path / "network_contacts.csv"
    p.write_bytes((HEAD + "zoe_d,Zoë,Café Ltd\r\n").encode("cp1252"))
    rows = csv_store.read_rows(str(p), ("contact_id", "name", "company"))
    assert rows[0]["name"] == "Zoë" and rows[0]["company"] == "Café Ltd"
    assert p.read_bytes() == (HEAD + "zoe_d,Zoë,Café Ltd\r\n").encode("utf-8")
    assert "Windows' older text format" in capsys.readouterr().err
    # Read again: plain UTF-8 now, nothing more said.
    csv_store.read_rows(str(p), ("contact_id",))
    assert capsys.readouterr().err == ""


def test_a_utf8_file_with_one_damaged_byte_is_read_and_left_alone(tmp_path, capsys):
    p = tmp_path / "network_threads.csv"
    body = (HEAD + "lukasz_w,Łukasz,Acme\r\n").encode("utf-8") + b"bad,\xff,x\r\n"
    p.write_bytes(body)
    rows = csv_store.read_rows(str(p), ("contact_id", "name"))
    assert rows[0]["name"] == "Łukasz" and rows[1]["name"] == "\ufffd"
    assert p.read_bytes() == body and "damaged character" in capsys.readouterr().err


def test_the_tracker_readers_read_a_bom_tracker(tmp_path, monkeypatch):
    import open_actions
    from network import state
    p = tmp_path / "job_search_tracker.csv"
    p.write_bytes(b"\xef\xbb\xbfcompany,role,status\r\nAcme,Analyst,applied\r\n")
    assert state.load_tracker(str(p))[0]["company"] == "Acme"
    assert open_actions._tracker(str(p))[0]["company"] == "Acme"


def test_a_name_read_in_an_undecodable_locale_prints_as_its_own_bytes():
    # os.listdir in a C locale gives "Łukasz" as two escaped bytes; a lone surrogate from
    # anywhere else, which no encoding can write, is "?" rather than a crash.
    text = "\udcc5\udc81ukasz \ud800 Ł"
    assert text.encode("utf-8", errors=python_floor._SAFE) == b"\xc5\x81ukasz ? \xc5\x81"
    assert b"a\xffb".decode("utf-8", errors=python_floor._SAFE) == "a�b"


def test_windows_is_given_time_zone_data_and_a_copy_without_it_is_fixed():
    """Windows has no IANA zones of its own; Python reads them from the tzdata package there
    (https://docs.python.org/3/library/zoneinfo.html#data-sources). It was in
    requirements.txt but not among the packages checked, so a copy whose packages went in
    before it was "already here" for ever, and their own time could not be read."""
    import env_check
    with_it = env_check.local_fixes("win32", have=lambda t: "C:/x/" + t, py_ok=True,
                                    pypdf="ok", module=lambda m: True, gh_signed_in=True,
                                    newer=False)
    without = env_check.local_fixes("win32", have=lambda t: "C:/x/" + t, py_ok=True,
                                    pypdf="ok", module=lambda m: m != "tzdata",
                                    gh_signed_in=True, newer=False)
    assert [w for w, *_ in without if w not in [x for x, *_ in with_it]] == [
        "the Python packages"]
    elsewhere = env_check.local_fixes("linux", have=lambda t: "/usr/bin/" + t, py_ok=True,
                                      pypdf="ok", module=lambda m: m != "tzdata",
                                      gh_signed_in=True, newer=False)
    assert "the Python packages" not in [w for w, *_ in elsewhere]
    with open(os.path.join(ROOT, "tools", "installs.py"), encoding="utf-8") as fh:
        assert 'MODULES += (("tzdata", "tzdata"),)' in fh.read()
