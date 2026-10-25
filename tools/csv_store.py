"""Read and write a state CSV the way every tool that keeps one must: in place.

The tracker, the contact book and the message log are hand-edited in a
spreadsheet as often as they are written by a tool, and several chats save them
on the same day. A save that rewrites what it did not change is how two chats'
work collides on every line when it meets on master. So a save keeps:

  - the file's own column order, with a column it lacks added at the END
    (inserting one in its schema place moved every later field of every row);
  - columns somebody added by hand, where they put them;
  - the file's own line ending ("\\r\\n" from a spreadsheet, "\\n" from git).

This is the behaviour tools/network/state.py had for the contact book and the
log alone. The tracker was written with a plain DictWriter, which turned every
"\\n" into "\\r\\n" and, after a hand-added column, appended a second `deadline`.
"""

from __future__ import annotations

import codecs
import csv
import io
import os
import re
import sys


class Conflicted(RuntimeError):
    """A state file git left with unresolved merge-conflict markers in it."""


# Git's own marker lines: "<<<<<<< ours", a line of exactly "=======", ">>>>>>> theirs".
_OPEN = re.compile(r"<{7}(?:[ \t].*)?\r?$")
_SEPARATOR = re.compile(r"={7}\r?$")
_CLOSE = re.compile(r">{7}(?:[ \t].*)?\r?$")


def conflict_marker(text: str):
    """(the opening marker's line number, its text) when `text` holds a git conflict, else
    None. A conflict is git's three lines in order, an opening "<<<<<<< ", a "=======" and a
    closing ">>>>>>> ", and never three lines inside one quoted field: a message whose words
    hold a line of seven "=" (an email's signature rule) made the whole log unreadable,
    and the advice to delete the marker line would have cut a cell (2026-10-21)."""
    marks, inside, field = [], False, 0
    for n, line in enumerate(str(text or "").split("\n"), 1):
        for kind, rx in (("open", _OPEN), ("sep", _SEPARATOR), ("close", _CLOSE)):
            if rx.match(line):
                marks.append((kind, n, line.strip(), inside, field))
                break
        for ch in line:                  # "" inside a field toggles twice: parity holds
            if ch == '"':
                inside = not inside
                if not inside:
                    field += 1
    for i, (kind, n, said, _in_q, _f) in enumerate(marks):
        if kind != "open":
            continue
        sep = next((j for j in range(i + 1, len(marks)) if marks[j][0] == "sep"), None)
        close = next((j for j in range(sep + 1, len(marks)) if marks[j][0] == "close"),
                     None) if sep is not None else None
        if close is None:
            continue
        trio = (marks[i], marks[sep], marks[close])
        if all(m[3] for m in trio) and len({m[4] for m in trio}) == 1:
            continue                     # all three inside one quoted cell: words, not git's
        return n, said
    return None


def refuse_conflicts(path: str) -> None:
    """Raise Conflicted when `path` holds git's merge-conflict markers (conflict_marker).
    Read as rows, the three marker lines became three contacts and both sides of the
    conflicted row two more, and the next save wrote the markers back."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return
    found = conflict_marker(text)
    if found:
        line, said = found
        raise Conflicted(
            f"{os.path.basename(path)} has unresolved merge-conflict markers (the first, "
            f"{said!r}, at line {line}), so nothing was read from it or saved "
            "to it. Keep the right version of each conflicted row, delete the marker lines, "
            "then run this again.")


# A run of bytes only UTF-8 writes: a lead byte and its continuation bytes. A file holding
# one is UTF-8 with a damaged byte somewhere, never Windows' own encoding, which writes
# none of these pairs for ordinary text.
_UTF8_RUN = re.compile(rb"[\xc2-\xf4][\x80-\xbf]+")


def read_text(path: str) -> str:
    """A state file's text, read the way it was saved.

    The app saves UTF-8, and so does git. A spreadsheet often does not: Excel's "CSV UTF-8"
    starts the file with a byte-order mark, which read as part of the first column's name
    ("\\ufeffcontact_id"), so every row lost its id, every contact became an orphan and
    the same people could be messaged twice; its plain "CSV" saves in Windows' own encoding
    (cp1252), which stopped every tool with UnicodeDecodeError. The mark is dropped, and a
    file in Windows' encoding is read that way and saved back as UTF-8 at once, keeping
    every byte of its line endings, with one plain line to say so. Raises OSError when the
    file cannot be read."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(codecs.BOM_UTF8):
        raw = raw[len(codecs.BOM_UTF8):]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    if _UTF8_RUN.search(raw):
        # UTF-8 with a damaged byte: read as UTF-8, the one character shown as "?" in a
        # diamond, and the file left as it is for a person to look at.
        print(f"state: {os.path.basename(path)} has a damaged character in it; read around "
              "it, and the file left as it was", file=sys.stderr)
        return raw.decode("utf-8", errors="replace")
    text = raw.decode("cp1252", errors="replace")
    try:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        print(f"state: {os.path.basename(path)} was saved by another program in Windows' "
              "older text format; it is read that way and saved back in the app's own "
              "(UTF-8), with nothing in it changed", file=sys.stderr)
    except OSError:
        pass
    return text


def dict_rows(path: str, refuse: bool = True) -> list[dict]:
    """csv.DictReader over a state file read the way it was saved (read_text), refusing a
    file git left with conflict markers unless `refuse` is False. Raises OSError when there
    is no file."""
    if refuse:
        refuse_conflicts(path)
    return [dict(r) for r in csv.DictReader(io.StringIO(read_text(path), newline=""))]


def header(path: str) -> list[str]:
    """The file's header row, stripped, or [] when there is no file."""
    try:
        return [h.strip() for h in next(csv.reader(io.StringIO(read_text(path), newline="")), [])]
    except OSError:
        return []


def write_rows(path: str, rows, columns) -> None:
    """Write `rows` under the file's own header, `columns` it lacks added at the end."""
    refuse_conflicts(path)
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    # Only columns already in the file's header count: a key a tool put on a
    # row in memory (a search snippet, a review flag) is not a column.
    try:
        text = read_text(path)
        first = io.StringIO(text, newline="").readline()
        head = next(csv.reader(io.StringIO(text, newline="")), [])
    except OSError:
        first, head = "", []
    fields = [k for k in dict.fromkeys(head) if k] or list(columns)
    # A column the file lacks joins it only once a row has something to put in it. Added
    # empty, it rewrote every row: saving one new contact was a 460-line change to a
    # 229-row contact book. A reader fills a missing column with blanks either way.
    added = [c for c in columns if c not in fields
             and (not head or any(str(r.get(c) or "").strip() for r in rows))]
    if head and added:
        # Once per file: after this save the header has them.
        print(f"state: {os.path.basename(path)} gains column(s) {', '.join(added)}, added "
              "at the end; every row keeps its other fields where they were", file=sys.stderr)
    fields += added
    ending = "\r\n" if first.endswith("\r\n") else "\n"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, restval="", extrasaction="ignore",
                           lineterminator=ending)
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})


def read_rows(path: str, columns=(), create: bool = False) -> list[dict]:
    """Rows as dicts, with every one of `columns` present and every extra column kept.

    Built on `csv.reader` rather than `DictReader` so a short row fills with
    blanks and an over-long one cannot land under a `None` key that then breaks
    the writer. A missing file is [] (and, with `create`, a file holding the
    header alone).
    """
    if not os.path.exists(path):
        if create:
            write_rows(path, [], columns)
        return []
    refuse_conflicts(path)
    reader = csv.reader(io.StringIO(read_text(path), newline=""))
    head = [h.strip() for h in next(reader, [])]
    rows = []
    for raw in reader:
        if not any(cell.strip() for cell in raw):
            continue
        row = {c: "" for c in columns}
        for i, name in enumerate(head):
            if name:
                row[name] = raw[i] if i < len(raw) else ""
        rows.append(row)
    return rows
