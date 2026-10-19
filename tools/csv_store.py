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

import csv
import os
import sys


def header(path: str) -> list[str]:
    """The file's header row, stripped, or [] when there is no file."""
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return [h.strip() for h in next(csv.reader(f), [])]
    except OSError:
        return []


def write_rows(path: str, rows, columns) -> None:
    """Write `rows` under the file's own header, `columns` it lacks added at the end."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    # Only columns already in the file's header count: a key a tool put on a
    # row in memory (a search snippet, a review flag) is not a column.
    try:
        with open(path, newline="", encoding="utf-8") as f:
            first = f.readline()
            f.seek(0)
            head = next(csv.reader(f), [])
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
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
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
