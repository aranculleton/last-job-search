#!/usr/bin/env python3
"""LinkedIn's data export, read: one reader for every file the app uses from it.

A person can download a copy of their own LinkedIn data (`python3
tools/claude_surfaces.py steps linkedin-export-files` says how, checked against LinkedIn's
help page) and give it here, as the ZIP or as the files inside it. Nothing here fetches
linkedin.com, and nothing is ever sent: the export is the one way the app sees what
happened on LinkedIn itself.

**Given an export, `take` it first**: it saves every file the app reads into
documents/linkedin/ and imports the message history into the log, in one step. A chat that
read messages.csv straight from the person's download (2026-10-21) wrote its follow-ups
and left only Connections.csv saved and 86 messages in the log, so no later chat could see
the rest of the conversations. The files are kept in the main folder on a computer, never
in a chat's own folder, which is removed with everything in it when its work lands.

Only the files named in FILES are ever opened; everything else in the archive stays
shut. Their column names come from three independent parsers of the export, not from a
file LinkedIn was seen to write, so every header is matched without regard to case or
spacing, a header found below a few lines of notes (Connections.csv has them) is
found, and a missing file or column is named rather than a crash.

What it gives:

- **the connections** (`state.first_degree()` reads them through `read()`);
- **the history**: messages and invitations into network_threads.csv as message rows,
  joined to the contact book by profile address (`state.profile_handle`, the one
  normaliser, which reads ca., uk. and www. addresses as one), else by a careful name
  match, else listed as not in the contact book. Running it twice adds nothing, and a
  message the app already logged is not added again. Status stays derived from the log,
  so afterwards `state.py` shows who replied and who is owed a reply;
- **the invitations still waiting**: the ones sent and never accepted, older than
  PENDING_DAYS, oldest first, for the person to withdraw on LinkedIn themselves;
- **what changed since the last download**, said first by `take`: new connections,
  requests accepted, replies, and requests still waiting. The day it was taken is kept
  in documents/network/linkedin_export.json, and once it is EXPORT_EVERY_DAYS old
  (fortnightly unless the person set otherwise) the brief asks for a new one (`due`).

    python3 tools/network/export.py take <zip|folder|csv>...        # given an export: this, first
    python3 tools/network/export.py take --find                     # the newest one on this computer
    python3 tools/network/export.py files [<zip|folder>]          # what it holds, what is missing
    python3 tools/network/export.py due                           # the brief's fortnightly ask
    python3 tools/network/export.py status [--tools browser]      # the next step, from what is recorded
    python3 tools/network/export.py requested [--date YYYY-MM-DD] # it was asked for on LinkedIn
    python3 tools/network/export.py save <zip|csv>... [--only connections|history|profile]
    python3 tools/network/export.py history [--from <zip|folder>] [--apply]
    python3 tools/network/export.py pending [--from <zip|folder>] [--days N] [--all]
    python3 tools/network/export.py withdrawn <name|profile address|contact id>... \\
        [--oldest N] [--reason "..."] [--from <zip|folder>]
"""

from __future__ import annotations

import argparse
import csv
import datetime
import html
import io
import os
import re
import sys
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.dirname(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dates  # noqa: E402
import person  # noqa: E402
import state as _st  # noqa: E402

# The files the app reads, by what they hold. Nothing else in an archive is opened.
FILES = {
    "connections": "Connections.csv",
    "messages": "messages.csv",
    "invitations": "Invitations.csv",
    "profile": "Profile.csv",
    "positions": "Positions.csv",
    "education": "Education.csv",
    "skills": "Skills.csv",
    "certifications": "Certifications.csv",
}
# What each use needs. "history" takes the connections too: an invitation whose person
# is now a connection was accepted, and that is the only place it says so.
GROUPS = {
    "connections": ("connections",),
    "history": ("messages", "invitations", "connections"),
    "profile": ("profile", "positions", "education", "skills", "certifications"),
}
GROUPS["all"] = tuple(FILES)
# The columns each file is expected to hold, as three independent parsers of the export
# name them (research, 2026-10-21; not checked against a file LinkedIn wrote). Matched
# without regard to case or spacing.
COLUMNS = {
    "connections": ("First Name", "Last Name", "URL", "Email Address", "Company", "Position",
                    "Connected On"),
    "messages": ("CONVERSATION ID", "CONVERSATION TITLE", "FROM", "SENDER PROFILE URL", "TO",
                 "RECIPIENT PROFILE URLS", "DATE", "SUBJECT", "CONTENT", "FOLDER",
                 "ATTACHMENTS"),
    "invitations": ("From", "To", "Sent At", "Message", "Direction", "inviterProfileUrl",
                    "inviteeProfileUrl"),
    "profile": ("First Name", "Last Name", "Maiden Name", "Address", "Birth Date", "Headline",
                "Summary", "Industry", "Geo Location", "Twitter Handles", "Websites",
                "Instant Messengers"),
    "positions": ("Company Name", "Title", "Description", "Location", "Started On",
                  "Finished On"),
    "education": ("School Name", "Start Date", "End Date", "Notes", "Degree Name", "Activities"),
    "skills": ("Name",),
    "certifications": ("Name", "Url", "Authority", "Started On", "Finished On",
                       "License Number"),
}
# Without these a file cannot be used at all; any other missing column is named and the
# rest of the file is still read.
NEEDED = {
    "connections": ("First Name", "Last Name"),
    "messages": ("FROM", "DATE", "CONTENT"),
    "invitations": ("To", "Sent At", "Direction"),
    "profile": ("Headline",),
    "positions": ("Company Name", "Title"),
    "education": ("School Name",),
    "skills": ("Name",),
    "certifications": ("Name",),
}
# A file far past this is not one of LinkedIn's, and is not read into memory to find out.
# A busy inbox's messages.csv runs to tens of megabytes.
MAX_BYTES = 200 * 1024 * 1024
# How far down a file its header may sit (Connections.csv has notes above it).
HEADER_SEARCH_LINES = 40


def _fold_header(name: str) -> str:
    return " ".join(str(name or "").replace("﻿", "").split()).casefold()


def home() -> str:
    """Where the export is kept: documents/linkedin/ in the main checkout when this is a
    worktree, else in this one. Git does not carry these files, and a chat's own folder is
    removed when its work lands, taking anything saved in it."""
    here = person.state("documents", "linkedin")
    # State moved elsewhere (LJS_STATE, or a test's own folder) is where it is kept.
    if os.environ.get(person.STATE_ENV) or not os.path.realpath(here).startswith(
            os.path.realpath(person.ROOT) + os.sep):
        return here
    main = person.main_checkout()
    return os.path.join(main, "documents", "linkedin") if main else here


def default_folder() -> str:
    """Where the export is read from: home(), or this checkout's documents/linkedin/ where
    an older copy saved it there instead."""
    here = person.state("documents", "linkedin")
    keep = home()
    if keep == here or _holds_any(keep):
        return keep
    return here if _holds_any(here) else keep


def _holds_any(folder: str) -> bool:
    try:
        names = {n.lower() for n in os.listdir(folder)}
    except OSError:
        return False
    return any(f.lower() in names for f in FILES.values())


def _source(src) -> tuple[str, str]:
    """("zip" | "folder" | "file", path) for what the person gave, default the folder."""
    src = str(src or "") or default_folder()
    if os.path.isdir(src):
        return "folder", src
    if os.path.isfile(src) and zipfile.is_zipfile(src):
        return "zip", src
    return "file", src


def _entry_name(name: str) -> str:
    """A ZIP entry's own file name. An archive made on Windows by PowerShell 5.1's
    Compress-Archive writes its folders with backslashes ("Export\\Connections.csv"), which
    no reader off Windows splits on: the export's files were never found in it."""
    return str(name or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def _kind_of_file(path: str) -> str:
    base = os.path.basename(path).lower()
    return next((k for k, f in FILES.items() if f.lower() == base), "")


# Where a file was read as Windows text (cp1252) rather than UTF-8: a CSV saved again from
# Excel on Windows is cp1252, and read as UTF-8 every accented name in it came out as "?".
DECODED: dict[str, str] = {}


def _decode(data: bytes, where: str) -> str:
    """UTF-8 (a byte-order mark dropped, as LinkedIn writes one), else Windows text."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        DECODED[where] = "cp1252"
        return data.decode("cp1252", errors="replace")
    DECODED.pop(where, None)
    return text


def encoding_line(tables) -> str:
    """One plain line when any file read was Windows text, else ""."""
    odd = [t["file"] for t in tables if DECODED.get(t.get("where", ""))]
    if not odd:
        return ""
    return (f"{', '.join(odd)} {'was' if len(odd) == 1 else 'were'} saved the Windows way, not "
            "as UTF-8, so I read it that way: check any name with an accent.")


def _raw(kind: str, src=None) -> tuple[str, str]:
    """(text, where it was read) for one file, or ("", "") when it is not there."""
    how, path = _source(src)
    want = FILES[kind].lower()
    if how == "zip":
        with zipfile.ZipFile(path) as z:
            found = [n for n in z.namelist() if _entry_name(n).lower() == want]
            if not found:
                return "", ""
            # The shortest path: the export's own file, not one nested in a folder of extras.
            name = min(found, key=len)
            if z.getinfo(name).file_size > MAX_BYTES:
                raise ValueError(f"the {FILES[kind]} in that archive is too large to be LinkedIn's")
            data = z.read(name)
        where = f"{os.path.basename(path)}:{name}"
        return _decode(data, where), where
    if how == "folder":
        try:
            names = os.listdir(path)
        except OSError:
            return "", ""
        hit = next((n for n in names if n.lower() == want), None)
        if not hit:
            return "", ""
        path = os.path.join(path, hit)
    elif not os.path.isfile(path) or (_kind_of_file(path) not in ("", kind)):
        return "", ""
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError(f"{path} is too large to be LinkedIn's {FILES[kind]}")
    with open(path, "rb") as fh:
        return _decode(fh.read(), path), path


def _header_at(text: str, kind: str) -> tuple[int, list]:
    """(character offset of the header line, its cells), or (-1, []) when none is found."""
    want = {_fold_header(c) for c in COLUMNS[kind]}
    need = min(2, len(want))
    offset = 0
    for i, line in enumerate(text.splitlines(keepends=True)):
        if i >= HEADER_SEARCH_LINES:
            break
        try:
            cells = next(csv.reader([line.rstrip("\r\n")]))
        except (csv.Error, StopIteration):
            cells = []
        if len({_fold_header(c) for c in cells} & want) >= need:
            return offset, cells
        offset += len(line)
    return -1, []


def parse(text: str, kind: str) -> dict:
    """{"rows": [...], "missing": [columns], "found": bool} from one file's text.

    Each row's keys are COLUMNS' names where the header matched one (any case, any
    spacing); a column nobody expected is kept under its own name."""
    at, cells = _header_at(text, kind)
    if at < 0:
        return {"rows": [], "missing": list(COLUMNS[kind]), "found": False}
    canon = {_fold_header(c): c for c in COLUMNS[kind]}
    names = [canon.get(_fold_header(c), str(c).strip()) for c in cells]
    rows = []
    reader = csv.reader(io.StringIO(text[at:]))
    next(reader, None)
    for cells_ in reader:
        if not any(str(c).strip() for c in cells_):
            continue
        rows.append({n: (cells_[i] if i < len(cells_) else "") for i, n in enumerate(names)})
    got = set(names)
    return {"rows": rows, "missing": [c for c in COLUMNS[kind] if c not in got], "found": True}


def read(kind: str, src=None) -> dict:
    """One export file: {"kind", "file", "where", "rows", "missing", "found", "usable"}.

    `src` is the ZIP, a folder holding the files, or the one file itself; by default
    documents/linkedin/. A file that is not there comes back with found False and no
    rows, never an error: the caller names what is missing."""
    if kind not in FILES:
        raise KeyError(f"export: no file kind {kind!r}; one of {', '.join(FILES)}")
    text, where = _raw(kind, src)
    got = parse(text, kind) if text else {"rows": [], "missing": list(COLUMNS[kind]),
                                          "found": False}
    usable = got["found"] and not [c for c in NEEDED[kind] if c in got["missing"]]
    return {"kind": kind, "file": FILES[kind], "where": where, **got, "usable": usable,
            "encoding": DECODED.get(where, "utf-8") if where else ""}


def describe(tables) -> list:
    """Plain lines: each file read, each one missing, each expected column not found."""
    out = []
    for t in tables:
        if not t["where"]:
            out.append(f"{t['file']} is not in it")
        elif not t["found"]:
            out.append(f"{t['file']} has no header this app recognises "
                       f"(it looked for {', '.join(COLUMNS[t['kind']][:3])})")
        else:
            gap = (f"; no {', '.join(t['missing'])} column" if t["missing"] else "")
            out.append(f"{t['file']}: {len(t['rows'])} row{'s' if len(t['rows']) != 1 else ''}"
                       + gap + ("" if t["usable"] else ", so it cannot be used"))
    return out


def save(srcs, only: str = "all", dest: str | None = None, name_absent=None) -> str:
    """Copy the files `only` names from what the person gave into documents/linkedin/,
    opening nothing else, and return what to tell them. Each is checked for its header
    first; one without it is not saved. `name_absent` (kinds) limits which files that were
    not there are named: all of them by default."""
    dest = dest or home()
    kinds = GROUPS[only]
    saved, missing, other, newer = [], [], 0, []
    for src in srcs:
        how, path = _source(src)
        if how == "zip":
            with zipfile.ZipFile(path) as z:
                want = {FILES[k].lower() for k in kinds}
                other += sum(1 for n in z.namelist() if not n.endswith(("/", "\\"))
                             and _entry_name(n).lower() not in want)
        elif how == "file" and _kind_of_file(path) not in kinds:
            missing.append(os.path.basename(path) + " (not a file this reads)")
            continue
        for kind in kinds:
            if how == "file" and _kind_of_file(path) != kind:
                continue
            text, _where = _raw(kind, path)
            if not text:
                continue
            got = parse(text, kind)
            if not got["found"]:
                missing.append(f"{FILES[kind]} (no header this app recognises)")
                continue
            kept = os.path.join(dest, FILES[kind])
            if kind in _DATED and os.path.isfile(kept):
                # An older download given again never replaces a newer one kept: its people
                # would look unconnected and its requests unanswered.
                have = newest([dict(parse(_raw(kind, kept)[0], kind), kind=kind)]).get(kind, "")
                given = newest([dict(got, kind=kind)]).get(kind, "")
                if have and given and have > given:
                    newer.append(f"{FILES[kind]} (the one kept here runs to {have}, this one "
                                 f"to {given})")
                    continue
            os.makedirs(dest, exist_ok=True)
            with open(os.path.join(dest, FILES[kind]), "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            saved.append(FILES[kind])
    absent = [FILES[k] for k in kinds if FILES[k] not in saved
              and not any(m.startswith(FILES[k]) for m in missing)
              and (name_absent is None or k in name_absent)]
    if not saved and newer:
        return "Nothing saved: the files kept here are newer: " + _and(newer) + "."
    if not saved:
        raise ValueError("nothing saved: none of " + ", ".join(FILES[k] for k in kinds)
                         + " was in what you gave")
    line = f"Saved {_and(saved)}."
    if other:
        line += (f" I read only {'that' if len(saved) == 1 else 'those'} from the archive; "
                 + (f"the other {other} files in it were not opened." if other != 1
                    else "the other file in it was not opened."))
    if missing or absent:
        line += " Not saved: " + _and(missing + [f"{a} (not in it)" for a in absent]) + "."
    if newer:
        line += " Kept the newer copy of " + _and(newer) + "."
    return line


# Where a person's download lands on their own computer. Only the top of each is looked
# at, and only an archive or a folder that is LinkedIn's: one named for it, or one holding
# its files.
SEARCH_DIRS = ("Downloads", "Desktop", "Documents")
# Windows keeps where each of those really is in the registry, and OneDrive moves Desktop
# and Documents into its own folder (OneDrive/Desktop, "OneDrive - <Organisation>"/
# Documents): a download saved to the Desktop on such a computer was never looked for.
_SHELL_FOLDERS = {"Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
                  "Desktop": "Desktop", "Documents": "Personal"}


def _windows_folders() -> list:
    """Where Windows says Downloads, Desktop and Documents are; [] anywhere else."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows"
                             r"\CurrentVersion\Explorer\User Shell Folders")
    except (ImportError, OSError):
        return []
    out = []
    with key:
        for value in _SHELL_FOLDERS.values():
            try:
                raw, _kind = winreg.QueryValueEx(key, value)
            except OSError:
                continue
            out.append(os.path.expandvars(str(raw)))
    return out


def search_folders(base: str | None = None) -> list:
    """Every folder a download may have landed in, each once: Downloads, Desktop and
    Documents in the home folder, the same in each OneDrive folder there, and on Windows
    where the registry says they are."""
    home_dir = base or os.path.expanduser("~")
    found = [os.path.join(home_dir, d) for d in SEARCH_DIRS]
    roots = []
    if base is None:
        roots += [os.environ.get(v, "") for v in ("OneDrive", "OneDriveConsumer",
                                                  "OneDriveCommercial")]
    try:
        roots += [e.path for e in os.scandir(home_dir)
                  if e.is_dir() and e.name.lower().startswith("onedrive")]
    except OSError:
        pass
    for r in roots:
        if r:
            found += [os.path.join(r, d) for d in SEARCH_DIRS]
    if base is None:
        found += _windows_folders()
    out, seen = [], set()
    for f in found:
        k = os.path.normcase(os.path.realpath(f))
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


def find_exports(base: str | None = None, denied: list | None = None) -> list:
    """LinkedIn downloads on this computer, newest first: a ZIP with "linkedin" in its name
    that holds Connections.csv or messages.csv, or a folder holding either (with "linkedin"
    in its name, or both files). Nothing in them is read; a cloud computer has none.

    A folder the computer would not let this look in (a Mac asks before an app reads
    Downloads, Desktop or Documents) is added to `denied` when given, so "none found" is
    never said of a folder nobody could look in."""
    out = []
    for folder in search_folders(base):
        try:
            entries = list(os.scandir(folder))
        except PermissionError:
            if denied is not None:
                denied.append(folder)
            continue
        except OSError:
            continue
        # A ZIP opened by the computer can land one folder deeper ("<name>/<name>/"): the
        # folders just inside a LinkedIn-named folder are looked at too, nothing further.
        for e in list(entries):
            if e.is_dir() and "linkedin" in e.name.lower():
                try:
                    entries += [x for x in os.scandir(e.path) if x.is_dir()]
                except OSError:
                    pass
        for e in entries:
            name = e.name.lower()
            try:
                if e.is_file() and name.endswith(".zip") and "linkedin" in name:
                    with zipfile.ZipFile(e.path) as z:
                        held = {_entry_name(n).lower() for n in z.namelist()}
                    if held & {"connections.csv", "messages.csv"}:
                        out.append(e.path)
                elif e.is_dir():
                    held = {n.lower() for n in os.listdir(e.path)}
                    has = held & {"connections.csv", "messages.csv"}
                    if has and ("linkedin" in name or len(has) == 2):
                        out.append(e.path)
            except (OSError, zipfile.BadZipFile):
                continue
    return sorted(out, key=os.path.getmtime, reverse=True)


def not_saved() -> list:
    """The history files missing from where the export is kept, as plain lines; [] when both
    are there. Connections.csv alone is what the connections import used to keep."""
    folder = default_folder()
    gone = [FILES[k] for k in ("messages", "invitations") if not read(k, folder)["where"]]
    if not gone:
        return []
    what = _and(gone)
    return [f"NOT SAVED: {what} {'is' if len(gone) == 1 else 'are'} not in documents/linkedin/, "
            "so the history LinkedIn holds was never imported: chats see only the messages "
            "logged here, and may write twice to someone already in a conversation.",
            "  Given the person's LinkedIn download (the ZIP or its folder): python3 "
            "tools/network/export.py take <it>; on their computer, take --find looks for it "
            "first. Never read the files straight from the download."]


# ---------------------------------------------------------------- a new download, fortnightly

# The download goes stale: who accepted, who replied and which requests still wait are
# known only from a newer one. The brief asks for a new one once the last is this many
# days old (the person's EXPORT_EVERY_DAYS in profile/networking.py, else 14; 0 never
# asks). A record of when it was taken is kept beside the message log, which is
# committed, because the download itself stays on the person's computer.
_NET = person.module("networking") if person.exists("networking.py") else None
try:
    EXPORT_EVERY_DAYS = max(int(getattr(_NET, "EXPORT_EVERY_DAYS", 14) or 0), 0)
except (TypeError, ValueError):                  # a typo there: the app's fortnight
    EXPORT_EVERY_DAYS = 14
STEPS = "python3 tools/claude_surfaces.py steps linkedin-export-files"
# The column each file dates its rows by.
_DATED = {"connections": "Connected On", "messages": "DATE", "invitations": "Sent At"}


def record_path() -> str:
    return person.state("documents", "network", "linkedin_export.json")


def load_record() -> dict:
    """What is recorded about the download: `taken_on` (with what it held), `requested_on`.
    {} when nothing is. The file sits beside the message log, so it is committed, and it
    merges key by key when two chats changed it (tools/merge_state.py, .gitattributes)."""
    import json
    try:
        with open(record_path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def save_record(updates: dict) -> dict:
    """The record with `updates` written over it, every other key kept: a download taken
    keeps the day it was asked for, and a request keeps the last download's day."""
    import json
    got = dict(load_record(), **updates)
    path = record_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(got, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return got


def newest(tables) -> dict:
    """{kind: the newest day a row of that file carries, ISO} for the tables given."""
    out = {}
    for t in tables:
        col = _DATED.get(t.get("kind"))
        days = [d for d in (day(r.get(col)) for r in t.get("rows") or ()) if d] if col else []
        if days:
            out[t["kind"]] = max(days).isoformat()
    return out


def last_taken(threads=None) -> tuple:
    """(the day the last download was taken, how that is known), or (None, ""): the record
    `take` writes; else the newest day in the files kept; else the newest message the log
    has from a download."""
    import json
    try:
        with open(record_path(), encoding="utf-8") as fh:
            got = _state().as_date(json.load(fh).get("taken_on"))
        if got:
            return got, "recorded when it was taken"
    except (OSError, ValueError, AttributeError):
        pass
    kept = newest(read(k, default_folder()) for k in _DATED)
    if kept:
        return datetime.date.fromisoformat(max(kept.values())), "the newest day in it"
    st = _state()
    if threads is None:
        threads = st.load_threads() if os.path.exists(st.THREADS_CSV) else []
    days = [st.as_date(r.get("date")) for r in threads
            if EXPORT_NOTE.lower() in str(r.get("summary") or "").lower()]
    days = [d for d in days if d]
    return (max(days), "the newest message the log has from it") if days else (None, "")


def due(today, threads=None) -> str:
    """The brief's line once the last download is EXPORT_EVERY_DAYS old, else "". Nothing
    when there has never been one: the connections-export upgrade asks for the first."""
    st = _state()
    today = st._need_date(today, "today")
    taken, _how = last_taken(threads)
    if not EXPORT_EVERY_DAYS or taken is None or (today - taken).days < EXPORT_EVERY_DAYS:
        return ""
    asked = st.as_date(load_record().get("requested_on"))
    if asked and asked > taken and (today - asked).days <= REQUEST_WAIT_DAYS:
        # Asked for already, by the chat on their computer: it picks the download up there.
        return (f"Your new LinkedIn download was asked for on {asked.isoformat()}; the chat "
                "on your computer picks it up once it is ready.")
    return (f"Your LinkedIn download is {(today - taken).days} days old (taken "
            f"{taken.isoformat()}). A new one shows who accepted your requests, who replied "
            "and which requests still wait: ask for it with the steps "
            f"({STEPS}, checked that day), then python3 tools/network/export.py take <it>.")


def _record(tables, today) -> None:
    save_record({"taken_on": today.isoformat(), "newest": newest(tables),
                 "rows": {t["kind"]: len(t["rows"]) for t in tables if t.get("found")}})


# ------------------------------------------------------------- the next step, from the record

# LinkedIn's link to the download arrives anything from minutes to a day after it is asked
# for, and works for 72 hours (claude_surfaces: linkedin-export-files). Asked for longer ago
# than this with nothing taken since, it is asked for again.
REQUEST_WAIT_DAYS = 3
BROWSERS = ("browser", "chrome", "enable")
# What the person is told when it has been asked for: one line, nothing to do.
REQUESTED_SAY = ("I've asked LinkedIn for a copy of your data. It takes a while to prepare, "
                 "and I'll pick it up when it's ready.")


def _found_since(taken, found=None) -> str:
    """The newest download on this computer made after the last one was taken, or ""."""
    paths = find_exports() if found is None else list(found)
    for p in paths:
        try:
            made = datetime.datetime.fromtimestamp(os.path.getmtime(p)).date()
        except OSError:
            continue
        if taken is None or made > taken:
            return p
    return ""


def status(today=None, tools=(), found=None, threads=None) -> dict:
    """The next step for the LinkedIn download, from what is recorded, so no chat has to
    remember it: {"state", "line", "do", "path", "taken_on", "requested_on", "due_on"}.

    `take`: a download on this computer is newer than the last one taken (one the browser
    fetched, or one the person saved themselves). `fresh`: the last one is younger than
    EXPORT_EVERY_DAYS (or the person's 0, never asked again). `waiting`: asked for within
    REQUEST_WAIT_DAYS and not here yet. `request`: none taken, or the last is due, and none
    asked for. `tools` is the chat's browser tools (browser, chrome, enable): with one,
    Claude does the step in that browser; without, the person is given the steps once.
    `found` stands for the downloads find_exports() would see."""
    st = _state()
    today = st._need_date(today or datetime.date.today().isoformat(), "today")
    have = {str(t).strip().lower() for t in tools or ()} & set(BROWSERS)
    taken, _how = last_taken(threads)
    rec = load_record()
    asked = st.as_date(rec.get("requested_on"))
    if asked and taken and asked <= taken:
        asked = None                               # that request was the one taken since
    due_on = (taken + datetime.timedelta(days=EXPORT_EVERY_DAYS)) if taken and \
        EXPORT_EVERY_DAYS else None
    out = {"taken_on": taken.isoformat() if taken else "", "path": "",
           "requested_on": asked.isoformat() if asked else "",
           "due_on": due_on.isoformat() if due_on else ""}
    path = _found_since(taken, found)
    if path:
        return dict(out, state="take", path=path,
                    line=f"take: {path}",
                    do=f"python3 tools/network/export.py take \"{path}\": it saves the download "
                       "and imports its history, and says what changed")
    if taken and (not EXPORT_EVERY_DAYS or today < due_on):
        return dict(out, state="fresh",
                    line=f"fresh: taken {taken.isoformat()}"
                         + (f"; the next is due {due_on.isoformat()}" if due_on else ""),
                    do="nothing")
    if asked and (today - asked).days <= REQUEST_WAIT_DAYS:
        if have:
            do = ("in the browser, open LinkedIn's page for a copy of your data (the place "
                  f"`{STEPS}` names) and look for the archive: once it is ready, download it "
                  "there, then run `export.py status` again, which finds it in Downloads. "
                  "Not ready yet: nothing to say, and look again on the next run")
        else:
            do = ("nothing until the person has the ZIP (LinkedIn emails them a link): "
                  "`export.py take <it>` when they attach it")
        return dict(out, state="waiting", line=f"waiting: asked for on {asked.isoformat()}",
                    do=do)
    if have:
        do = (f"in the browser, ask LinkedIn for its whole archive, as `{STEPS}` says, "
              "clicking only what those steps name. If LinkedIn asks for the password, the "
              "person types it there; never type it. Then `export.py requested`, and tell "
              f"the person, once: {REQUESTED_SAY}")
    else:
        do = (f"ask the person once, with the steps `{STEPS}` prints (checked that day by a "
              "web search of LinkedIn's help page, never a fetch of linkedin.com), then "
              "`export.py requested` once they say it is asked for")
    return dict(out, state="request",
                line="request: " + (f"the last one is {(today - taken).days} days old"
                                    if taken else "none taken yet"),
                do=do)


def requested(today=None) -> dict:
    """Record that the download was asked for on LinkedIn, and when."""
    st = _state()
    day = st._need_date(today or datetime.date.today().isoformat(), "date")
    return save_record({"requested_on": day.isoformat()})


def since_last(before, after, plan, contacts, threads, today) -> list:
    """What changed since the last download, in a line or two: new connections, requests
    accepted, replies, and requests still waiting past PENDING_DAYS. `before` is the
    connections the app held before this one was saved (the rows, or None) with the
    record's date; `after` this download's connections."""
    st = _state()
    old_rows, since = before

    def ident(r):
        return st.profile_handle(r.get("URL")) or name_key(
            " ".join(x for x in (r.get("First Name"), r.get("Last Name")) if x))
    if old_rows:
        known = {ident(r) for r in old_rows} - {""}
        new = list({ident(r): r for r in after if ident(r) and ident(r) not in known}.values())
    elif since:
        new = [r for r in after if (day(r.get("Connected On")) or datetime.date.min) > since]
    else:
        return []
    # Only what happened since: a download also holds old conversations with people added
    # to the book since the last one, and those are history, not news.
    added = [r for r in (plan.get("add") or [] if plan else [])
             if not since or (st.as_date(r.get("date")) or datetime.date.min) > since]
    accepted = [r for r in added if st.is_acceptance(r)]
    replies = [r for r in added if st._direction(r) == "in" and not st.is_acceptance(r)
               and st._scenario(r) != "invitation_received"
               and st.said_something(r) and not st.is_auto_reply(r)]
    names = {str(c.get("contact_id") or ""): c.get("name") or c.get("contact_id")
             for c in contacts}

    def who(rows):
        ids = list(dict.fromkeys(str(r.get("contact_id") or "") for r in rows))
        shown = ", ".join(str(names.get(i) or i) for i in ids[:5])
        return f" ({shown}{', ...' if len(ids) > 5 else ''})" if ids else ""
    waiting = pending(contacts, threads, today)["items"]
    when = (since.isoformat() if since else "the last one")
    return [f"Since your last download ({when}): {len(new)} new connection"
            f"{'s' if len(new) != 1 else ''}, {len({r.get('contact_id') for r in accepted})} "
            f"accepted your request{who(accepted)}, {len({r.get('contact_id') for r in replies})} "
            f"replied{who(replies)}, and {len(waiting)} request{'s' if len(waiting) != 1 else ''} "
            f"sent over {PENDING_DAYS} days ago still wait"
            + (" (export.py pending lists them)." if waiting else ".")]


def take(srcs, contacts_path: str | None = None, threads_path: str | None = None) -> list:
    """Save the export and import its history, in one step: what a chat given an export
    does before anything is written from it. Returns the lines to show: what changed since
    the last download first, then what was saved and imported. Each contact waiting on a
    reply gets its follow-up date (state.write_follow_ups), and the day it was taken is
    recorded for the brief's fortnightly ask (`due`)."""
    st = _state()
    today = datetime.date.today()
    cp, tp = contacts_path or st.CONTACTS_CSV, threads_path or st.THREADS_CSV
    held = read("connections", default_folder())
    taken, _how = last_taken(st.load_threads(tp) if os.path.exists(tp) else [])
    before = (held["rows"] if held["usable"] else None, taken)
    lines = [save(srcs, "all", name_absent=("connections", "messages", "invitations"))]
    tables = [read(k, home()) for k in _DATED]
    _record(tables, today)
    contacts, threads = st.load_contacts(cp), st.load_threads(tp)
    plan = plan_history(contacts, threads, home())
    if plan["problem"]:
        lines.append(f"No history imported: {plan['problem']}.")
        return lines
    n = apply_history(threads, plan, contacts)
    dated = st.write_follow_ups(contacts, threads, today)
    if n or dated:
        st.save_threads(threads, tp)
        st.save_contacts(contacts, cp)
    lines[:0] = since_last(before, tables[0]["rows"], plan, contacts, threads, today)
    j = plan["joined"]
    people = j["profile address"] + j["name"]
    wrote = [u for u in plan["unmatched"] if u["sent"]]
    lines.append(f"Imported {n} message row{'s' if n != 1 else ''} into the message log, for "
                 f"{people} {'person' if people == 1 else 'people'} in the contact book. "
                 "Nothing was sent.")
    if plan["unmatched"]:
        lines.append(f"{len(plan['unmatched'])} people in the history are not in the contact "
                     f"book ({len(wrote)} of them written to): `export.py history` lists them.")
    if dated:
        lines.append(f"Follow-up dates written on {len(dated)} contact"
                     f"{'s' if len(dated) != 1 else ''} ({st.schema.follow_up_rule()}).")
    return lines


def _and(items) -> str:
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# ---------------------------------------------------------------- dates

_MDY = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\b")
_DAY_MONTH_YEAR = re.compile(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b")
_MONTH_DAY_YEAR = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})\b")
_MONTH_YEAR = re.compile(r"^\s*([A-Za-z]{3,9})\.?\s+(\d{4})\s*$")
_NUM_MONTH_YEAR = re.compile(r"^\s*(\d{1,2})/(\d{4})\s*$")
_YEAR = re.compile(r"^\s*(\d{4})\s*$")


def _month_number(word: str) -> int | None:
    for fmt in ("%b", "%B"):
        try:
            return datetime.datetime.strptime(word[:3] if fmt == "%b" else word, fmt).month
        except ValueError:
            continue
    return None


# The zone the person's day is read in. None is this computer's own, which is the person's
# (person.cloud_day sets it in a cloud chat); a test names one, so it reads the same anywhere.
HERE = None
# A moment the export states the zone of: messages.csv writes "2024-03-15 14:22:01 UTC".
_STAMP = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[ T]([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?"
                    r"(?:\.\d+)?\s*(UTC|GMT|Z|[+-]\d{2}:?\d{2})\b", re.I)


def _local(value) -> datetime.datetime | None:
    """A timestamp that states its zone, as the person's own clock reads it, or None.

    The export dates messages in UTC; the app dates every message it logs in the person's
    own day (person.cloud_day sets the zone in a cloud chat for exactly this). East of UTC
    the two disagree for part of every day, and a reply sent at 10:10 in Sydney on the 15th
    was logged on the 14th, before the message it answered on the 15th: the thread read as
    waiting on them, the reply owed vanished and a nudge was offered (networking audit,
    2026-10-25). Both are read in one zone: this computer's, which is the person's."""
    m = _STAMP.match(" ".join(str(value or "").split()))
    if not m:
        return None
    zone = m.group(7).upper()
    if zone in ("UTC", "GMT", "Z"):
        tz = datetime.timezone.utc
    else:
        digits = zone[1:].replace(":", "")
        tz = datetime.timezone((-1 if zone[0] == "-" else 1) * datetime.timedelta(
            hours=int(digits[:2]), minutes=int(digits[2:])))
    try:
        at = datetime.datetime(*(int(g) for g in m.groups()[:5]), int(m.group(6) or 0),
                               tzinfo=tz)
        return at.astimezone(HERE).replace(tzinfo=None)
    except (ValueError, OverflowError, OSError):
        return None


def day(value) -> datetime.date | None:
    """A day from any date the export writes: "2024-03-15 14:22:01 UTC" (messages, read on
    the person's own clock: `_local`), "3/15/24, 2:22 PM" (invitations, month first as
    LinkedIn writes it, day first only where the first number cannot be a month), "15 Mar
    2024" (connections)."""
    at = _local(value)
    if at is not None:
        return at.date()
    text = " ".join(str(value or "").split())
    got = dates.as_date(text, iso_only=True)
    if got:
        return got
    m = _MDY.match(text)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y += 2000 if y < 100 else 0
        month, d = (b, a) if a > 12 >= b else (a, b)
        try:
            return datetime.date(y, month, d)
        except ValueError:
            return None
    for rx, order in ((_DAY_MONTH_YEAR, "dmy"), (_MONTH_DAY_YEAR, "mdy")):
        m = rx.search(text)
        if m:
            d, mon, y = ((m.group(1), m.group(2), m.group(3)) if order == "dmy"
                         else (m.group(2), m.group(1), m.group(3)))
            month = _month_number(mon)
            if month:
                try:
                    return datetime.date(int(y), month, int(d))
                except ValueError:
                    return None
    return None


def clock(value) -> str:
    """The time of day a dated export cell carries, "08:40", or "" when it has none: on the
    person's own clock where the cell states its zone (`_local`)."""
    at = _local(value)
    if at is not None:
        return at.strftime("%H:%M")
    m = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?\b", str(value or ""))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


# The mark a repeat carries: the same words to or from one person on one day, sent at
# another time. Without it two genuine messages were two identical rows, which RECONCILE
# reads as one message logged twice (2026-10-23). Never in brackets: a summary ending "an
# attachment attached" read the bracket as the attachment's file name.
_AT = "; sent at {}"
_AT_SEEN = re.compile(r"[;(] ?sent at \d{1,2}:\d{2}\)?$")


def _sig(row) -> tuple:
    return tuple(str(row.get(k) or "").strip()
                 for k in ("date", "direction", "channel", "scenario", "summary", "full_text"))


def month(value) -> tuple | None:
    """(year, month or None) from a position's or a certificate's date: "Mar 2023",
    "03/2023", "2023", or an ISO date. None when there is nothing usable."""
    text = " ".join(str(value or "").split())
    if not text:
        return None
    got = dates.as_date(text, iso_only=True)
    if got:
        return (got.year, got.month)
    m = _MONTH_YEAR.match(text)
    if m and _month_number(m.group(1)):
        return (int(m.group(2)), _month_number(m.group(1)))
    m = _NUM_MONTH_YEAR.match(text)
    if m and 1 <= int(m.group(1)) <= 12:
        return (int(m.group(2)), int(m.group(1)))
    m = _YEAR.match(text)
    if m:
        return (int(m.group(1)), None)
    got = day(text)
    return (got.year, got.month) if got else None


# ---------------------------------------------------------------- who is who

def _state():
    return _st


def me() -> tuple[str, str]:
    """(the person's own profile handle, their name as the name match reads it)."""
    st = _state()
    return (st.profile_handle(person.get("identity.linkedin", "") or ""),
            st._match_name(person.get("identity.name", "") or ""))


def name_key(name) -> str:
    """A name as the contact book is matched on it: credentials, letters after the name,
    pronouns and honorifics gone (state.person_name). "" for a single name, which is too
    little to call anybody by."""
    st = _state()
    bare = st.person_name(name)
    return st._match_name(bare) if len(bare.split()) >= 2 else ""


def contact_index(contacts) -> dict:
    """The book by profile address and by name, built once for a whole import: matching
    each of 2,600 messages against 1,300 rows one by one took most of a 17-second import
    (2026-10-23). The rows themselves, in the book's order."""
    st = _state()
    by_handle: dict = {}
    by_name: dict = {}
    for c in contacts:
        h = st.profile_handle(c.get("linkedin_url"))
        if h:
            by_handle.setdefault(h, c)
        k = name_key(c.get("name"))
        if k:
            by_name.setdefault(k, []).append((c, bool(h)))
    return {"by_handle": by_handle, "by_name": by_name}


def match_contact(contacts, name, url, index=None) -> tuple:
    """(contact row or None, how): "profile address", "name", "ambiguous" or "".

    The profile address first, through the one normaliser (`state.profile_handle`). Then
    the name, only when exactly one row carries it and that row's own address, if it
    has one, is this person's: two rows with the name are two people as far as this can
    tell, and a different address is a different person. A nickname or a near spelling
    never joins. `index` (contact_index) answers the same for a whole import at once."""
    st = _state()
    index = index or contact_index(contacts)
    h = st.profile_handle(url)
    if h and h in index["by_handle"]:
        return index["by_handle"][h], "profile address"
    key = name_key(name)
    if not key:
        return None, ""
    same = [c for c, has in index["by_name"].get(key, ()) if not (h and has)]
    if len(same) == 1:
        return same[0], "name"
    return None, ("ambiguous" if same else "")


# ---------------------------------------------------------------- the history

_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"<br\s*/?>|</p>\s*<p[^>]*>|</div>\s*<div[^>]*>", re.I)
_RESUME = re.compile(r"\b(?:r[eé]sum[eé]|cv|curriculum vitae)\b", re.I)
_URLS = re.compile(r"https?://\S+?(?=[,;\s]|$)")
# A request is a request whichever day the log and the export put it on: a request seen
# on the invitations page is logged as "pending since about" a day.
REQUEST_SLACK_DAYS = 7
# A message the app logged on the day the person said it went and the export's day,
# which is in UTC, can be a day apart.
MESSAGE_SLACK_DAYS = 1
EXPORT_NOTE = "from LinkedIn's export"


def _clean(text) -> str:
    t = str(text or "")
    if "<" in t and _TAG.search(t):
        t = _TAG.sub("", _BREAK.sub("\n", t))
    return html.unescape(t).strip()


def _preview(text, most: int = 60) -> str:
    one = " ".join(str(text or "").split())
    return one if len(one) <= most else one[:most - 3].rstrip() + "..."


def _norm(text) -> str:
    return " ".join(str(text or "").split()).lower()


def same_text(a, b) -> bool:
    """One message, whether the app logged it whole and the export cut it, or the
    other way round (an invitation's preview ends early)."""
    a, b = _norm(a).rstrip(".… "), _norm(b).rstrip(".… ")
    if not a or not b:
        return False
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= 40 and long_.startswith(short)


def _yes(value) -> bool:
    return str(value or "").strip().lower() in ("yes", "true", "1", "y")


def _attachment(row) -> str:
    """What was attached, said plainly: "a resume" when its name or the message says so.

    The same marker `state.attachment_note` writes for a file logged with `--attached`, and
    `state.attached` reads back, so a resume LinkedIn's export saw and one the app logged
    are found by one reader."""
    raw = str(row.get("ATTACHMENTS") or "").strip()
    if not raw:
        return ""
    urls = _URLS.findall(raw)
    names = [os.path.basename(u.split("?")[0]) for u in urls] if urls else [raw]
    # A file is a resume by `state.is_resume_file`, the reader the app's own log uses:
    # "_" is a word character, so "Morgan_Ellis_CV_KestrelMutual.pdf", the app's own
    # <Prefix>_CV_<ABBR> name, was "an attachment" here and the resume stayed owed.
    what = ("a resume" if any(_state().is_resume_file(n) for n in names)
            or _RESUME.search(str(row.get("CONTENT") or "")) else "an attachment")
    shown = ", ".join(n for n in names if n and "." in n and len(n) <= 80)
    return f"{what} attached" + (f" ({shown})" if shown else "")


# What the import writes about an attachment, in a row's summary: "; a resume attached
# (Resume.pdf)". Read back, it is the attachment a message with no words is known by.
_ATTACHED = re.compile(r"\b(?:a resume|an attachment) attached(?: \([^)]*\))?")


def _file_names(summary) -> set:
    """The file names (no folder, lower case) an attachment marker names, in a row's
    summary or in `_attachment`'s words: "documents/cv/Morgan_Ellis_CV.pdf" logged by the
    app and "Morgan_Ellis_CV.pdf" in the export are one file."""
    return {os.path.basename(f.replace("\\", "/")).lower()
            for f in _state().attached({"summary": str(summary or "")})
            if f and f != _state().NOT_KEPT}


def _same_attachment(row, attached: str) -> bool:
    """Does a logged message carry this attachment (`_attachment`'s words), or, for none,
    name no attachment at all?"""
    summary = str(row.get("summary") or "")
    return attached in summary if attached else not _ATTACHED.search(summary)


def _participants(row, mine) -> tuple:
    """(direction, [(name, url)] of the others) for one message row."""
    st = _state()
    my_h, my_n = mine
    sender_url = str(row.get("SENDER PROFILE URL") or "")
    sh = st.profile_handle(sender_url)
    from_me = (sh == my_h) if (sh and my_h) else (name_key(row.get("FROM")) == my_n and bool(my_n))
    urls = [u for u in _URLS.findall(str(row.get("RECIPIENT PROFILE URLS") or ""))]
    others_urls = [u for u in urls if not (my_h and st.profile_handle(u) == my_h)]
    if from_me:
        if len(others_urls) == 1:
            return "out", [(str(row.get("TO") or ""), others_urls[0])]
        if others_urls:
            return "out", [("", u) for u in others_urls]
        return "out", [(str(row.get("TO") or ""), "")]
    people = [(str(row.get("FROM") or ""), sender_url)]
    people += [("", u) for u in others_urls]
    return "in", people


def _from_pending(row) -> bool:
    """A request recorded from LinkedIn's own pages (state.sent outside): seen Pending, its
    day the day it was seen or the latest a "Sent 3 weeks ago" can mean, never earlier."""
    st = _state()
    said = str(row.get("summary") or "").lower()
    return st.is_request(row) and (st._scenario(row) == st.OUTSIDE_SCENARIO
                                   or "from linkedin itself" in said)


def _who(name, url) -> str:
    st = _state()
    h = st.profile_handle(url)
    return ("in:" + h) if h else ("name:" + name_key(name)) if name_key(name) else ""


def _near(a, b, days) -> bool:
    return a is not None and b is not None and abs((a - b).days) <= days


def plan_history(contacts, threads, src=None, mine=None) -> dict:
    """What the export's history adds to the message log, decided and not yet written.

    {"add": [thread rows], "fill": [(an existing row, its words)],
     "redate": [(a request recorded from a Pending page, the day the export says it went)],
     "joined": {how: n},
     "unmatched": [{name, url, last, last_from, sent, received}], "ambiguous": [{name, url}],
     "groups": n, "drafts": n, "tables": [...], "problem": ""}

    A message to or from one person in the contact book becomes one row, `channel`
    message, with its words, subject and any attachment noted. One the app logged already
    (the same person, a day either side, the same words) is not added again; one it logged
    with no words is given them. A request the person sent is a `connection_request` row
    with its note; an invitation they received from someone in the book is an inbound
    row. A request accepted since, which only Connections.csv says, gets its acceptance.
    A conversation with more than one other person is no one thread and is left out."""
    st = _state()
    tables = [read(k, src) for k in GROUPS["history"]]
    msgs, invs, conns = tables
    mine = mine or me()
    if not mine[0] and mine[1]:
        # Their own address, from a message they sent: without it their address among a
        # message's recipients read as a second person and every thread as a group.
        mine = (next((st.profile_handle(r.get("SENDER PROFILE URL")) for r in msgs["rows"]
                      if name_key(r.get("FROM")) == mine[1]
                      and st.profile_handle(r.get("SENDER PROFILE URL"))), ""), mine[1])
    out = {"add": [], "fill": [], "redate": [], "mark": [],
           "joined": {"profile address": 0, "name": 0},
           "unmatched": [], "ambiguous": [], "groups": 0, "drafts": 0, "tables": tables,
           "problem": ""}
    if not (mine[0] or mine[1]):
        out["problem"] = ("person.json has no LinkedIn address and no name, so which messages "
                          "are yours cannot be told")
        return out
    if not (msgs["usable"] or invs["usable"]):
        out["problem"] = ("neither messages.csv nor Invitations.csv could be read (not there, "
                          "or without the columns it needs)")
        return out
    log = list(threads)
    by_cid: dict = {}
    for r in log:
        by_cid.setdefault(str(r.get("contact_id") or "").strip(), []).append(r)
    index = contact_index(contacts)
    joined_ids: dict = {}

    def logged(row):
        log.append(row)
        by_cid.setdefault(str(row.get("contact_id") or "").strip(), []).append(row)

    def join(name, url):
        c, how = match_contact(contacts, name, url, index)
        if c is not None:
            cid = str(c.get("contact_id") or "").strip()
            if cid not in joined_ids:
                joined_ids[cid] = how
            return c
        if how == "ambiguous":
            key = (name_key(name), st.profile_handle(url))
            if key not in {(name_key(a["name"]), st.profile_handle(a["url"]))
                           for a in out["ambiguous"]}:
                out["ambiguous"].append({"name": name, "url": url})
        return None

    def mine_for(cid):
        return list(by_cid.get(str(cid or "").strip(), ()))

    claimed: set = set()

    marked: dict = {}                    # id(an existing row) -> the summary it will carry

    def planned(r) -> tuple:
        sig = _sig(r)
        return sig[:4] + (marked.get(id(r), sig[4]),) + sig[5:]

    def mark_repeat(row, rows, at):
        """A row identical to another of this person's is marked with the time it was sent,
        once. An existing row is marked when the plan is applied, never while it is made."""
        summary = marked.get(id(row), str(row.get("summary") or ""))
        if not at or _AT_SEEN.search(summary):
            return
        if any(r is not row and planned(r) == planned(row) for r in rows):
            new = summary + _AT.format(at)
            if any(a is row for a in out["add"]):
                row["summary"] = new
            else:
                marked[id(row)] = new
                out["mark"].append((row, new))

    def add_message(cid, when, direction, text, subject, summary, attached="", at=""):
        rows = mine_for(cid)
        for r in rows:
            if st._direction(r) == direction and _near(st.as_date(r.get("date")), when,
                                                        MESSAGE_SLACK_DAYS) \
                    and same_text(r.get("full_text"), text):
                return
        files = _file_names(attached)
        if not text and files:
            # A resume sent alone on LinkedIn, which the app logged with words: it needs
            # words to log a message, and the person wrote what they did ("Sent my CV as an
            # attachment."). The same day, way and file is that message, words or not; a
            # second, wordless row beside it was the same resume twice (2026-10-21).
            for r in rows:
                if (id(r) not in claimed and st._direction(r) == direction
                        and _near(st.as_date(r.get("date")), when, MESSAGE_SLACK_DAYS)
                        and files & _file_names(r.get("summary")) and not st.is_request(r)
                        and not st.is_acceptance(r) and not st.is_withdrawal(r)
                        and not st.is_call(r)):
                    claimed.add(id(r))
                    mark_repeat(r, rows, at)
                    return
        if not text:
            # A message with no words (a resume sent alone) has no text to match on, and was
            # added again on every run: the same day, way and attachment is the same message.
            # Each row stands for one export message, so two sent on one day stay two.
            for r in rows:
                if (id(r) not in claimed and st._direction(r) == direction
                        and _near(st.as_date(r.get("date")), when, MESSAGE_SLACK_DAYS)
                        and not str(r.get("full_text") or "").strip()
                        and _same_attachment(r, attached) and not st.is_request(r)
                        and not st.is_acceptance(r) and not st.is_withdrawal(r)
                        and not st.is_call(r)):
                    claimed.add(id(r))
                    mark_repeat(r, rows, at)
                    return
        empty = [r for r in rows if st._direction(r) == direction
                 and _near(st.as_date(r.get("date")), when, MESSAGE_SLACK_DAYS)
                 and not str(r.get("full_text") or "").strip() and not st.is_request(r)
                 and not st.is_acceptance(r) and not st.is_withdrawal(r) and not st.is_call(r)]
        if len(empty) == 1 and text:
            if not any(e is empty[0] for e, _ in out["fill"]):
                out["fill"].append((empty[0], text))
            return
        row = {"contact_id": cid, "date": when.isoformat(), "direction": direction,
               "channel": "message", "scenario": "", "summary": summary,
               "full_text": text, "subject": subject}
        out["add"].append(row)
        logged(row)
        mark_repeat(row, rows + [row], at)
        if not text:
            claimed.add(id(row))

    # Messages, one conversation at a time.
    if msgs["usable"]:
        convs: dict = {}
        for i, r in enumerate(msgs["rows"]):
            if _yes(r.get("IS MESSAGE DRAFT")) or str(r.get("FOLDER") or "").strip().lower() \
                    in ("draft", "drafts", "spam"):
                out["drafts"] += 1
                continue
            cid_ = str(r.get("CONVERSATION ID") or "").strip() or f"row{i}"
            convs.setdefault(cid_, []).append(r)
        for rows in convs.values():
            people, parsed = {}, []
            for r in rows:
                direction, others = _participants(r, mine)
                parsed.append((r, direction))
                for name, url in others:
                    k = _who(name, url)
                    if k:
                        got = people.setdefault(k, ["", ""])
                        got[0] = got[0] or name
                        got[1] = got[1] or url
            if len(people) != 1:
                out["groups"] += 1 if len(people) > 1 else 0
                continue
            name, url = next(iter(people.values()))
            contact = join(name, url)
            dated = sorted(((day(r.get("DATE")), r, d) for r, d in parsed),
                           key=lambda x: (x[0] or datetime.date.min, clock(x[1].get("DATE"))))
            if contact is None:
                sent = sum(1 for _, _, d in dated if d == "out")
                last = dated[-1] if dated else (None, {}, "")
                out["unmatched"].append({
                    "name": name, "url": url,
                    "last": last[0].isoformat() if last[0] else "",
                    "last_from": "you" if last[2] == "out" else "them",
                    "sent": sent, "received": len(dated) - sent, "kind": "messages"})
                continue
            cid = str(contact.get("contact_id") or "").strip()
            for when, r, direction in dated:
                if when is None:
                    continue
                note = _attachment(r)
                text = _clean(r.get("CONTENT"))
                # The words' start is in the summary: two messages to one person on one day
                # are two rows, and reconcile reads identical summaries as one logged twice.
                summary = ("Message " + ("sent" if direction == "out" else "received") + ", "
                           + EXPORT_NOTE + (f"; {note}" if note else "")
                           + (f": {_preview(text)}" if text else ""))
                add_message(cid, when, direction, text, str(r.get("SUBJECT") or "").strip(),
                            summary, attached=note, at=clock(r.get("DATE")))

    # Invitations: the person's requests, and requests to them from people in the book.
    if invs["usable"]:
        for r in invs["rows"]:
            way = str(r.get("Direction") or "").strip().lower()
            when = day(r.get("Sent At"))
            if when is None:
                continue
            note = _clean(r.get("Message"))
            if way.startswith("out"):
                contact = join(r.get("To"), r.get("inviteeProfileUrl"))
                if contact is None:
                    continue           # the pending list names these; see pending()
                cid = str(contact.get("contact_id") or "").strip()
                rows = mine_for(cid)
                same = [x for x in rows if st.is_request(x)
                        and _near(st.as_date(x.get("date")), when, REQUEST_SLACK_DAYS)]
                # A request recorded from a Pending page is logged the day it was seen, or the
                # latest day "Sent 1 month ago" can mean: the export's request on or before
                # that day is the same one, and its day is the true one. Seven days apart, it
                # was added again and counted twice, and its withdraw clock ran from the
                # later day (2026-10-21).
                seen = [x for x in rows if _from_pending(x)
                        and (st.as_date(x.get("date")) or datetime.date.min) >= when]
                same = same or seen[:1]
                if same and _from_pending(same[0]) \
                        and (st.as_date(same[0].get("date")) or when) > when \
                        and not any(x is same[0] for x, _d in out["redate"]):
                    out["redate"].append((same[0], when.isoformat()))
                if same:
                    if note and not str(same[0].get("full_text") or "").strip() \
                            and not any(e is same[0] for e, _ in out["fill"]):
                        out["fill"].append((same[0], note))
                    continue
                row = {"contact_id": cid, "date": when.isoformat(), "direction": "out",
                       "channel": "connection", "scenario": "connection_request",
                       "summary": ("Connection request with a note, " if note
                                   else "Connection request, no note, ") + EXPORT_NOTE,
                       "full_text": note, "subject": ""}
                out["add"].append(row)
                logged(row)
            elif way.startswith("in"):
                contact = join(r.get("From"), r.get("inviterProfileUrl"))
                if contact is None:
                    continue           # an invitation from a stranger is not outreach
                cid = str(contact.get("contact_id") or "").strip()
                if any(st._direction(x) == "in" and st._scenario(x) == "invitation_received"
                       and _near(st.as_date(x.get("date")), when, MESSAGE_SLACK_DAYS)
                       for x in mine_for(cid)):
                    continue
                row = {"contact_id": cid, "date": when.isoformat(), "direction": "in",
                       "channel": "connection", "scenario": "invitation_received",
                       "summary": ("They asked to connect" + (", with a note" if note else "")
                                   + ", " + EXPORT_NOTE),
                       "full_text": note, "subject": ""}
                out["add"].append(row)
                logged(row)

    # Acceptances: a request in the log, and the person now a connection.
    if conns["usable"]:
        for r in conns["rows"]:
            name = " ".join(x for x in (r.get("First Name"), r.get("Last Name")) if x).strip()
            when = day(r.get("Connected On"))
            if when is None:
                continue
            c, _how = match_contact(contacts, name, r.get("URL"), index)
            if c is None:
                continue
            cid = str(c.get("contact_id") or "").strip()
            rows = st._ordered(mine_for(cid))
            asked = [x for x in rows if st.is_request(x)
                     and (st.as_date(x.get("date")) or datetime.date.max)
                     <= when + datetime.timedelta(days=MESSAGE_SLACK_DAYS)]
            if not asked:
                continue           # connected before any request: nothing to accept
            since = st.as_date(asked[-1].get("date"))
            later = [x for x in rows if (st.as_date(x.get("date")) or datetime.date.min) >= since
                     and x is not asked[-1]]
            if any(st.is_acceptance(x) or st.said_something(x) or st.is_withdrawal(x)
                   for x in later):
                continue
            joined_ids.setdefault(cid, _how)
            row = {"contact_id": cid, "date": when.isoformat(), "direction": "in",
                   "channel": "connection", "scenario": "connection_accepted",
                   "summary": "Accepted the connection request, " + EXPORT_NOTE,
                   "full_text": "", "subject": ""}
            out["add"].append(row)
            logged(row)

    touched = ({r["contact_id"] for r in out["add"]}
               | {r.get("contact_id") for r, _ in out["fill"] + out["redate"]})
    for cid in touched:
        how = joined_ids.get(cid)
        if how in out["joined"]:
            out["joined"][how] += 1
    out["unmatched"].sort(key=lambda u: u["last"], reverse=True)
    return out


def apply_history(threads, plan, contacts=None) -> int:
    """Write a plan into the message log in place; the caller saves. Rows changed.

    With `contacts`, each person the import touched has the statuses the log decides
    (state.DERIVABLE) brought in line with it, and an empty first_contacted filled from
    their first message out: the log is the authority for those, and leaving the rows
    behind put every imported thread in front of the person as a contradiction."""
    for row, text in plan["fill"]:
        row["full_text"] = text
    for row, summary in plan.get("mark") or ():
        row["summary"] = summary
    redate = plan.get("redate") or []
    for row, day_ in redate:
        old = row.get("date")
        row["date"] = day_
        cid = str(row.get("contact_id") or "").strip()
        for c in contacts or ():
            if str(c.get("contact_id") or "").strip() == cid \
                    and str(c.get("first_contacted") or "") in ("", old):
                c["first_contacted"] = day_      # contact began when the request went
    threads.extend(plan["add"])
    if contacts is not None:
        settle(contacts, threads, {r["contact_id"] for r in plan["add"]}
               | {str(r.get("contact_id") or "") for r, _ in plan["fill"]}
               | {str(r.get("contact_id") or "") for r, _ in redate})
    return len(plan["add"]) + len(plan["fill"]) + len(redate) + len(plan.get("mark") or ())


def settle(contacts, threads, ids) -> list:
    """For each contact in `ids`, a stored status the log decides set to what it says.
    Returns [(contact_id, old, new)] for the ones changed."""
    st = _state()
    changed = []
    for c in contacts:
        cid = str(c.get("contact_id") or "").strip()
        if cid not in ids:
            continue
        rows = st.threads_for(threads, cid)
        stored = str(c.get("status") or "").strip()
        derived = st.derive_status(rows)
        # A thread gone cold that they have now answered is open again, as state.received
        # makes it for a reply logged by command.
        if ((not stored or stored in st.DERIVABLE) and derived != stored
                and derived != "not_contacted") or (
                stored in st.REOPENED_BY_A_REPLY and st.reopened(c, rows, derived)):
            c["status"] = derived
            changed.append((cid, stored, derived))
        if not str(c.get("first_contacted") or "").strip():
            first = next((r for r in rows if st._direction(r) == "out"), None)
            if first and st.as_date(first.get("date")):
                c["first_contacted"] = st.as_date(first.get("date")).isoformat()
    return changed


# ---------------------------------------------------------------- invitations still waiting

# The same three weeks `state.owed()` lists a request to withdraw after: one rule, one
# number. LinkedIn's help says invitations left pending can lead to a restriction on
# sending more, and that a withdrawn one cannot be sent again for up to three weeks (help
# pages a551012 and a568295, read through a web search on 2026-10-21, never fetched):
# withdrawing at three weeks leaves a second try possible six weeks after the first.
PENDING_DAYS = int(_st.REQUEST_WITHDRAW_DAYS)


def _pending_days() -> int:
    return PENDING_DAYS


# Shown in the state view and /threads; the rest are counted. There is no way to withdraw
# many at once (LinkedIn's help, a568295), so a list of hundreds is not read whole:
# the oldest come first.
PENDING_SHOWN = 10


def pending(contacts, threads, today, src=None, days: int | None = None) -> dict:
    """Invitations the person sent that nobody has accepted, older than `days`, oldest first.

    {"items": [{name, url, sent, days, note, contact_id}], "total_sent": n, "younger": n,
     "file": bool, "connections": bool, "tables": [...]}

    Read from Invitations.csv; an invitation whose person is in Connections.csv was
    accepted, and one the log shows withdrawn, accepted or answered is not waiting.
    Someone in the contact book whose request `state.owed()` already lists to withdraw
    carries `listed`, so the two lists never show one person twice."""
    st = _state()
    today = st._need_date(today, "today")
    days = _pending_days() if days is None else int(days)
    inv, conns = read("invitations", src), read("connections", src)
    out = {"items": [], "total_sent": 0, "younger": 0, "file": inv["usable"],
           "connections": conns["usable"], "tables": [inv, conns]}
    if not inv["usable"]:
        return out
    # Joined the way the import joins (match_contact): by address, and by name wherever one
    # side has no address. Each fallback looked only at its own side, so an invitation with
    # no address against a connection that had one, or the other way round, was listed as
    # never accepted, and `withdrawn --oldest` would have closed someone already connected.
    linked_h, linked_n, linked_bare = set(), set(), set()
    for r in conns["rows"]:
        h = st.profile_handle(r.get("URL"))
        k = name_key(" ".join(x for x in (r.get("First Name"), r.get("Last Name")) if x))
        if h:
            linked_h.add(h)
        if k:
            linked_n.add(k)
            if not h:
                linked_bare.add(k)
    owed_ids = {i["contact_id"] for i in st.owed(contacts, threads, today)
                if i["kind"] == "request_pending"}
    index, by_cid = contact_index(contacts), st.by_contact(threads)
    seen = set()
    for r in inv["rows"]:
        if not str(r.get("Direction") or "").strip().lower().startswith("out"):
            continue
        name, url = str(r.get("To") or "").strip(), str(r.get("inviteeProfileUrl") or "")
        when = day(r.get("Sent At"))
        if when is None:
            continue
        out["total_sent"] += 1
        h, k = st.profile_handle(url), name_key(name)
        if (h and h in linked_h) or (k and k in (linked_bare if h else linked_n)):
            continue
        key = h or name_key(name) or name
        if key in seen:
            continue
        seen.add(key)
        contact, _how = match_contact(contacts, name, url, index)
        cid = str(contact.get("contact_id") or "").strip() if contact else ""
        if contact is not None:
            rows = [x for x in by_cid.get(cid, ()) if st._direction(x)]
            after = [x for x in rows if (st.as_date(x.get("date")) or datetime.date.min) >= when]
            if any(st.is_withdrawal(x) or st.is_acceptance(x) or st.said_something(x)
                   for x in after):
                continue
            if str(contact.get("status") or "").strip() in ("closed", "gone_cold",
                                                            "converted_to_application"):
                continue
        waited = (today - when).days
        if waited < days:
            out["younger"] += 1
            continue
        out["items"].append({"name": name, "url": url, "sent": when.isoformat(),
                             "days": waited, "note": bool(str(r.get("Message") or "").strip()),
                             "contact_id": cid, "listed": cid in owed_ids})
    out["items"].sort(key=lambda i: (i["sent"], i["name"]))
    return out


WITHDRAW_STEPS = "python3 tools/claude_surfaces.py steps linkedin-withdraw-invitation"


def pending_lines(found: dict, shown: int = PENDING_SHOWN) -> list:
    """The section the state view and /threads print: [] when nothing is waiting."""
    items = [i for i in found["items"] if not i["listed"]]
    if not items:
        return []
    weeks = _pending_days() // 7
    head = (f"PENDING INVITATIONS  {len(items)} sent from LinkedIn more than {weeks} weeks ago "
            "and never accepted, oldest first (from your export)")
    lines = [head]
    for i in items[:shown]:
        who = i["name"] or i["url"] or "someone"
        lines.append(f"  {who}: sent {i['sent']}, {i['days']} days ago"
                     + (" (in your contact book)" if i["contact_id"] else ""))
    if len(items) > shown:
        lines.append(f"  and {len(items) - shown} more")
    lines.append("  Worth withdrawing, oldest first: waiting invitations count against how many "
                 "LinkedIn lets you send. You do it on LinkedIn, one at a time; the steps: "
                 + WITHDRAW_STEPS + ". Then tell me who, and I record it: python3 "
                 "tools/network/export.py withdrawn <name>... (or --oldest <n>)")
    return lines


def withdrawn(contacts, threads, who, today, src=None, oldest: int = 0, reason: str = "",
              days: int | None = None) -> dict:
    """Record invitations the person says they withdrew on LinkedIn: each one closed,
    with the reason, so it is never suggested again. Lists changed in place.

    {"done": [(name, contact_id)], "unknown": [what was not found], "ambiguous": [...]}.
    Someone in the contact book is closed through `state.withdraw()`, with the request
    logged first when only the export had it. Someone who is not becomes a closed row
    beside the request and its withdrawal, so the person is never surfaced again."""
    st = _state()
    today = st._need_date(today, "today")
    found = pending(contacts, threads, today, src, days=0 if days is None else days)
    items = found["items"]
    picked, unknown, ambiguous = [], [], []
    for w in who or ():
        w = str(w or "").strip()
        h = st.profile_handle(w)
        hits = ([i for i in items if st.profile_handle(i["url"]) == h] if h
                else [i for i in items if i["contact_id"] == w]
                or [i for i in items if name_key(i["name"]) and name_key(i["name"]) == name_key(w)])
        if len(hits) == 1:
            picked.append(hits[0])
        elif hits:
            ambiguous.append(w)
        else:
            unknown.append(w)
    if oldest:
        old = [i for i in items if (today - datetime.date.fromisoformat(i["sent"])).days
               >= _pending_days()]
        picked += [i for i in old[:int(oldest)] if i not in picked]
    why = " ".join(str(reason or "").split()) or "withdrawn on LinkedIn by the person"
    done = []
    for i in picked:
        sent = datetime.date.fromisoformat(i["sent"])
        cid = i["contact_id"]
        if not cid:
            # A name the export gives with no surname in it is no id: the profile address is.
            named = i["name"] if st.surname(i["name"]) else st.profile_handle(i["url"])
            cid = st.unique_contact_id(named or i["name"], "", contacts, linkedin_url=i["url"])
            st.add_row(contacts, cid, {
                "name": i["name"], "linkedin_url": i["url"], "channel": "connection",
                "status": "awaiting_reply", "first_contacted": i["sent"], "route": "cold",
                "found_via": "export",
                "notes": "an invitation sent from LinkedIn itself, seen in its export"})
        rows = [x for x in st.threads_for(threads, cid) if st._direction(x)]
        if st.request_pending(rows) is None:
            threads.append({"contact_id": cid, "date": sent.isoformat(), "direction": "out",
                            "channel": "connection", "scenario": "connection_request",
                            "summary": "Connection request, " + EXPORT_NOTE,
                            "full_text": "", "subject": ""})
        try:
            st.withdraw(contacts, threads, cid, today, why)
        except ValueError as e:
            unknown.append(f"{i['name'] or i['url']} ({e})")
            continue
        done.append((i["name"] or i["url"], cid))
    return {"done": done, "unknown": unknown, "ambiguous": ambiguous}


# ---------------------------------------------------------------- the command line

def _cli_files(a) -> int:
    for line in describe([read(k, a.src) for k in FILES]):
        print("  " + line)
    if not a.src:
        for line in not_saved():
            print(line)
    return 0


def _keep(src) -> None:
    """An export read from anywhere but where it is kept is saved there first, so the next
    chat has it too."""
    if not src or os.path.realpath(str(src)) == os.path.realpath(home()):
        return
    try:
        print(save([src], "all"))
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        print(f"export: not saved: {e}")


def _cli_take(a) -> int:
    srcs = list(a.srcs)
    if a.find and not srcs:
        denied: list = []
        srcs = find_exports(denied=denied)[:1]
        if not srcs and denied:
            names = _and([os.path.basename(d.rstrip("\\/")) or d for d in denied])
            print(f"export: this computer did not let me look in {names}, so I cannot say "
                  "whether the LinkedIn download is there. Drag the ZIP into this chat, or "
                  "tell me where it is.")
            return 3
        if not srcs:
            print("export: no LinkedIn download on this computer (in Downloads, Desktop or "
                  "Documents). The steps for one: python3 tools/claude_surfaces.py steps "
                  "linkedin-export-files")
            return 3
        print(f"Found {srcs[0]}")
    if not srcs:
        print("export: take needs the ZIP or its folder, or --find")
        return 2
    try:
        lines = take(srcs, a.contacts, a.threads)
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        print(f"export: {e}")
        return 1
    for line in lines:
        print(line)
    return 0


def _cli_save(a) -> int:
    try:
        print(save(a.srcs, a.only))
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        print(f"export: {e}")
        return 1
    return 0


def _cli_history(a) -> int:
    _keep(a.src)
    st = _state()
    contacts, threads = st.load_contacts(a.contacts), st.load_threads(a.threads)
    plan = plan_history(contacts, threads, a.src)
    read_ = [t["file"] for t in plan["tables"] if t["usable"]]
    if plan["problem"]:
        print(f"export: nothing imported: {plan['problem']}.")
        for line in describe(plan["tables"]):
            print("  " + line)
        return 1
    print(f"From your LinkedIn export ({', '.join(read_)}):")
    for line in describe(plan["tables"]):
        if "is not in it" in line or "column" in line or "header" in line:
            print("  " + line)
    j = plan["joined"]
    people = j["profile address"] + j["name"]
    print(f"  {len(plan['add'])} message row{'s' if len(plan['add']) != 1 else ''} to add and "
          f"{len(plan['fill'])} already logged given their words, for {people} "
          f"{'person' if people == 1 else 'people'} in your contact book "
          f"({j['profile address']} by profile address, {j['name']} by name)")
    if plan.get("redate"):
        n_ = len(plan["redate"])
        print(f"  {n_} request{'s' if n_ != 1 else ''} recorded from a Pending page, given the "
              "earlier day the export says it went")
    if plan.get("mark"):
        n_ = len(plan["mark"])
        print(f"  {n_} repeat{'s' if n_ != 1 else ''} already logged (the same words to one "
              "person twice in a day) given the time each was sent, so they are not read as "
              "one message logged twice")
    if plan["groups"]:
        print(f"  {plan['groups']} group conversation{'s' if plan['groups'] != 1 else ''} left "
              "out: a message to several people is not one thread")
    if plan["ambiguous"]:
        print(f"TWO PEOPLE, ONE NAME ({len(plan['ambiguous'])}): more than one row in your contact "
              "book has this name and no LinkedIn address says which. Put the address on the "
              "right row, then run this again:")
        for x in plan["ambiguous"][:10]:
            print(f"  {x['name']} {x['url']}".rstrip())
    if plan["unmatched"]:
        wrote = [u for u in plan["unmatched"] if u["sent"]]
        print(f"NOT IN YOUR CONTACT BOOK ({len(plan['unmatched'])}, {len(wrote)} of them you "
              "wrote to), newest first. Add any worth keeping to network_contacts.csv with "
              "their LinkedIn address, then run this again and their messages join them:")
        for u in plan["unmatched"][:25]:
            print(f"  {u['name'] or u['url']}: last message {u['last'] or 'undated'}, from "
                  f"{u['last_from']}; {u['sent']} sent, {u['received']} received"
                  + (f" ({u['url']})" if u["url"] else ""))
        if len(plan["unmatched"]) > 25:
            print(f"  and {len(plan['unmatched']) - 25} more")
    if not a.apply:
        print("Nothing written yet. To add them: python3 tools/network/export.py history --apply"
              + (f" --from {a.src}" if a.src else ""))
        return 0
    n = apply_history(threads, plan, contacts)
    if n:
        st.save_threads(threads, a.threads)
        st.save_contacts(contacts, a.contacts)
    print(f"Written: {n} row{'s' if n != 1 else ''} in network_threads.csv. Nothing was sent. "
          "python3 tools/network/state.py now shows who replied and who is owed a reply.")
    return 0


def _cli_pending(a) -> int:
    _keep(a.src)
    st = _state()
    contacts, threads = st.load_contacts(a.contacts), st.load_threads(a.threads)
    found = pending(contacts, threads, a.today, a.src, days=a.days)
    if not found["file"]:
        print("export: no Invitations.csv to read; the steps for the export: python3 "
              "tools/claude_surfaces.py steps linkedin-export-files")
        return 1
    lines = pending_lines(found, shown=10 ** 6 if a.all else PENDING_SHOWN)
    for line in lines or ["PENDING INVITATIONS  none older than "
                          f"{(a.days if a.days is not None else _pending_days())} days"]:
        print(line)
    if not found["connections"]:
        print("  Connections.csv was not given, so an invitation accepted since may be listed.")
    return 0


def _cli_withdrawn(a) -> int:
    _keep(a.src)
    st = _state()
    contacts, threads = st.load_contacts(a.contacts), st.load_threads(a.threads)
    if not a.who and not a.oldest:
        print("withdrawn: name who you withdrew (a name, a LinkedIn address or a contact id), "
              "or --oldest <n> for the oldest n listed")
        return 2
    got = withdrawn(contacts, threads, a.who, a.today, a.src, oldest=a.oldest, reason=a.reason)
    for name, cid in got["done"]:
        print(f"  {name}: withdrawal recorded, closed, never suggested again [{cid}]")
    for w in got["ambiguous"]:
        print(f"  {w}: more than one waiting invitation has that name; give their LinkedIn address")
    for w in got["unknown"]:
        print(f"  {w}: not found among the waiting invitations, nothing recorded")
    if got["done"]:
        st.save_threads(threads, a.threads)
        st.save_contacts(contacts, a.contacts)
    print(f"withdrawn: {len(got['done'])} recorded")
    return 0 if got["done"] or not (got["unknown"] or got["ambiguous"]) else 1


def main(argv=None) -> int:
    st = _state()
    ap = argparse.ArgumentParser(prog="export.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("take", help="save the export and import its history, in one step")
    t.add_argument("srcs", nargs="*")
    t.add_argument("--find", action="store_true")
    t.add_argument("--contacts", default=st.CONTACTS_CSV)
    t.add_argument("--threads", default=st.THREADS_CSV)
    d = sub.add_parser("due", help="one line once the last download is EXPORT_EVERY_DAYS old")
    d.add_argument("--today", default=datetime.date.today().isoformat())
    stt = sub.add_parser("status", help="the next step for the download: request, waiting, "
                                        "take or fresh")
    stt.add_argument("--tools", default="", help="this chat's browser tools: browser, chrome, "
                                                 "enable, or none")
    stt.add_argument("--today", default=datetime.date.today().isoformat())
    rq = sub.add_parser("requested", help="record that it was asked for on LinkedIn")
    rq.add_argument("--date", default=datetime.date.today().isoformat())
    f = sub.add_parser("files", help="what the export holds, and what is missing")
    f.add_argument("src", nargs="?", default=None)
    s = sub.add_parser("save", help="copy the named files into documents/linkedin/")
    s.add_argument("srcs", nargs="+")
    s.add_argument("--only", choices=sorted(GROUPS), default="all")
    for name, helptext in (("history", "messages and invitations into network_threads.csv"),
                           ("pending", "invitations sent and never accepted, oldest first"),
                           ("withdrawn", "record invitations withdrawn on LinkedIn")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--from", dest="src", default=None)
        p.add_argument("--contacts", default=st.CONTACTS_CSV)
        p.add_argument("--threads", default=st.THREADS_CSV)
        p.add_argument("--today", default=datetime.date.today().isoformat())
        if name == "history":
            p.add_argument("--apply", action="store_true")
        if name == "pending":
            p.add_argument("--days", type=int, default=None)
            p.add_argument("--all", action="store_true")
        if name == "withdrawn":
            p.add_argument("who", nargs="*")
            p.add_argument("--oldest", type=int, default=0)
            p.add_argument("--reason", default="")
    a = ap.parse_args(argv)
    return {"take": _cli_take, "files": _cli_files, "save": _cli_save, "history": _cli_history,
            "pending": _cli_pending, "withdrawn": _cli_withdrawn, "due": _cli_due,
            "status": _cli_status, "requested": _cli_requested}[a.cmd](a)


def _cli_status(a) -> int:
    got = status(a.today, [t for t in a.tools.split(",") if t.strip()])
    print(got["line"])
    if got["do"] != "nothing":
        print(f"do: {got['do']}")
    return 0


def _cli_requested(a) -> int:
    got = requested(a.date)
    print(f"requested: asked for on {got['requested_on']}; `export.py status` says when to "
          "look for it")
    return 0


def _cli_due(a) -> int:
    line = due(a.today)
    if line:
        print(line)
    return 0


if __name__ == "__main__":
    import csv_store
    try:
        raise SystemExit(main())
    except csv_store.Conflicted as e:
        print(f"export: {e}", file=sys.stderr)
        raise SystemExit(1) from None
