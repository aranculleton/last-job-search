#!/usr/bin/env python3
"""Merge the state files two chats changed at once, row by row (a git merge driver).

Several chats run against one repo, each in its own container. Two of them adding a
tracker row, logging a message or ruling out a posting on the same afternoon is
normal, and git's line merge calls that a conflict whenever the two edits sit next to
each other, which at the end of an append-only file they always do. A row is the unit
that matters, so this merges rows:

- a row only one side added, changed or removed takes that side;
- a row both sides changed the same way is taken once;
- a row both sides changed differently is merged field by field, and the notes both
  sides added are both kept;
- a field both sides set to different values, or a row one side removed while the
  other changed it, is a real conflict. The CSV gets git's markers around the two
  versions of that row, the JSON keeps this side's value, the conflicts are listed,
  and the exit is 1, so git leaves the file for a person, as it would have anyway.

`tools/sync_app.py` sets `merge.ljs-state.driver` in the repo's git config on every
run and `.gitattributes` names the files. Where the driver is not set (a fresh clone
before its first sync, GitHub's own merge), git merges lines exactly as before.

    python3 tools/merge_state.py %O %A %B %P
"""
from __future__ import annotations

import csv
import io
import json
import os
import platform
import sys

# The floor in tools/python_floor.py, inline: git runs this file on its own, from a
# checkout where nothing else may be importable yet.
FLOOR = (3, 9)

# The key that says two rows are the same row. A file not named here is merged with
# the whole row as its key, which suits a log: a row is only ever added.
KEYS = {
    "job_search_tracker.csv": ("date", "company", "role"),
    "network_contacts.csv": ("contact_id",),
    "network_threads.csv": None,
    "question_bank.csv": None,          # documents/interview/: a log, rows only added
}
# Free text that both sides may have added to: kept from both, never a conflict.
NOTES = {"notes"}


# ------------------------------------------------------------------ fields


def merge_note(base: str, ours: str, theirs: str) -> str:
    """Both sides' additions to a notes field, ours first."""
    if ours == theirs or theirs == base:
        return ours
    if ours == base:
        return theirs
    if theirs.startswith(base) and ours.startswith(base):
        return ours + theirs[len(base):]
    if theirs in ours:
        return ours
    if ours in theirs:
        return theirs
    return ours + (" | " if ours and theirs else "") + theirs


def merge_fields(base: dict | None, ours: dict, theirs: dict) -> tuple[dict, list[str]]:
    """One row both sides changed: field by field. Returns (row, conflicting fields)."""
    base = base or {}
    out, clash = {}, []
    for k in list(ours) + [k for k in theirs if k not in ours]:
        b, o, t = base.get(k), ours.get(k), theirs.get(k)
        if o == t or t == b:
            out[k] = o if k in ours else t
        elif o == b:
            out[k] = t
        elif k in NOTES and all(isinstance(v, str) or v is None for v in (b, o, t)):
            out[k] = merge_note(b or "", o or "", t or "")
        else:
            out[k], clash = o, clash + [k]
    return out, clash


# ------------------------------------------------------------------ CSV


def _read(text: str) -> tuple[list[str], list[dict]]:
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        return [], []
    head = rows[0]
    return head, [dict(zip(head, (r + [""] * len(head))[:len(head)]))
                  for r in rows[1:] if r]


def _keyed(rows: list[dict], fields) -> dict:
    """{key: row}, with the n-th repeat of a key kept apart as (key, n)."""
    out, n = {}, {}
    for r in rows:
        k = tuple(r.get(f, "") for f in fields) if fields else tuple(r.values())
        n[k] = n.get(k, 0) + 1
        out[(k, n[k])] = r
    return out


def merge_csv(base: str, ours: str, theirs: str, name: str) -> tuple[str, list[str]]:
    fields = KEYS.get(name)
    hb, rb = _read(base)
    ho, ro = _read(ours)
    ht, rt = _read(theirs)
    head = ho + [h for h in ht if h not in ho]
    if fields and not all(f in head for f in fields):
        fields = None
    if fields is None:
        # A log is keyed by its whole row, so read every side under one header.
        rb, ro, rt = ([{h: r.get(h, "") for h in head} for r in rs] for rs in (rb, ro, rt))
    B, O, T = _keyed(rb, fields), _keyed(ro, fields), _keyed(rt, fields)
    out, problems = [], []

    def place(k):
        b, o, t = B.get(k), O.get(k), T.get(k)
        if o is None and t is None:
            return None
        if o is None or t is None:                 # one side removed it, or one side added it
            kept = o if t is None else t
            if b is None:
                return kept
            if kept == b:
                return None                        # removed on one side, untouched on the other
            problems.append(f"{name}: a row one side removed and the other changed: "
                            f"{', '.join(k[0])}")
            return ("conflict", o, t)
        if o == t or t == b:
            return o
        if o == b:
            return t
        row, clash = merge_fields(b, o, t)
        if clash:
            problems.append(f"{name}: {', '.join(k[0])}: both changed {', '.join(clash)}")
            return ("conflict", o, t)
        return row

    for k in O:
        out.append(place(k))
    for k in T:
        if k not in O:
            out.append(place(k))
    ending = "\r\n" if ours.split("\n", 1)[0].endswith("\r") else "\n"
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=head, restval="", extrasaction="ignore",
                       lineterminator=ending)
    w.writeheader()
    for r in out:
        if r is None:
            continue
        if isinstance(r, tuple):
            _, o, t = r
            buf.write("<<<<<<< ours" + ending)
            if o is not None:
                w.writerow(o)
            buf.write("=======" + ending)
            if t is not None:
                w.writerow(t)
            buf.write(">>>>>>> theirs" + ending)
            continue
        w.writerow(r)
    return buf.getvalue(), problems


# ------------------------------------------------------------------ JSON


def merge_json(base, ours, theirs, path: str = "") -> tuple[object, list[str]]:
    """Dicts merge key by key, all the way down; anything else three ways."""
    if ours == theirs or theirs == base:
        return ours, []
    if ours == base:
        return theirs, []
    if not (isinstance(ours, dict) and isinstance(theirs, dict)):
        return ours, [path or "(the whole file)"]
    base = base if isinstance(base, dict) else {}
    out, problems = {}, []
    for k in list(ours) + [k for k in theirs if k not in ours]:
        sub = f"{path}/{k}" if path else str(k)
        if k not in theirs:
            if k in base and ours[k] != base[k]:
                problems.append(sub + " (removed on one side, changed on the other)")
            if k not in base or ours[k] != base[k]:
                out[k] = ours[k]
            continue
        if k not in ours:
            if k in base and theirs[k] != base[k]:
                problems.append(sub + " (removed on one side, changed on the other)")
                out[k] = theirs[k]
            elif k not in base:
                out[k] = theirs[k]
            continue
        if k in NOTES and all(isinstance(v, str) for v in (ours[k], theirs[k])):
            out[k] = merge_note(base.get(k) or "", ours[k], theirs[k])
            continue
        out[k], more = merge_json(base.get(k), ours[k], theirs[k], sub)
        problems += more
    return out, problems


# ------------------------------------------------------------------ the driver

# What git runs. Git runs a merge driver from the top of the working tree, so the path
# is relative and each worktree runs its own copy; a checkout too old to have this file
# merges lines the way git always did.
# merge_state exits 0 or 1 when it merged; anything else (an old Python, a crash,
# no python3 at all) and git's own line merge runs instead, which marks every
# conflict in the file. The file is never left holding only this side's rows.
DRIVER = ("if [ -f tools/merge_state.py ]; then python3 tools/merge_state.py %O %A %B %P; "
          "rc=$?; if [ $rc -le 1 ]; then exit $rc; fi; fi; git merge-file %A %O %B")


def install(root: str) -> None:
    """Point this repo's git config at the driver. Config is not committed, so every
    container sets it again: two quick config writes, and never an error."""
    import subprocess
    for k, v in (("name", "state files, row by row"), ("driver", DRIVER)):
        subprocess.run(["git", "-C", root, "config", f"merge.ljs-state.{k}", v],
                       capture_output=True, text=True, check=False)


def merge(base: str, ours: str, theirs: str, path: str) -> tuple[str, list[str]]:
    name = os.path.basename(path)
    if name.endswith(".json"):
        try:
            b = json.loads(base) if base.strip() else {}
            o, t = json.loads(ours), json.loads(theirs)
        except ValueError as e:
            return ours, [f"{path}: not JSON on one side ({e})"]
        merged, problems = merge_json(b, o, t)
        return json.dumps(merged, indent=2, ensure_ascii=False) + "\n", problems
    return merge_csv(base, ours, theirs, name)


# Exit codes. 0 merged; 1 merged with real conflicts marked for a person. Anything
# else means this driver could not merge at all and wrote nothing, and the driver
# command (DRIVER) then runs git's own line merge, which marks every conflict: a
# state file is never left as one side's copy with the other side's rows lost.
COULD_NOT = 3


def main(argv: list[str]) -> int:
    if sys.version_info[:2] < FLOOR:
        print(f"merge_state: Python {FLOOR[0]}.{FLOOR[1]} or newer is needed; this is "
              f"{platform.python_version()} (python3 tools/env_check.py says how to install it)",
              file=sys.stderr)
        return COULD_NOT
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    base_p, ours_p, theirs_p, path = argv

    def read(p):
        with open(p, encoding="utf-8", newline="") as f:
            return f.read()

    try:
        text, problems = merge(read(base_p), read(ours_p), read(theirs_p), path)
    except Exception as e:  # noqa: BLE001  nothing is written; git's line merge takes over
        print(f"merge_state: could not merge {path} ({type(e).__name__}: {e}); "
              "git's line merge marks the conflicts instead", file=sys.stderr)
        return COULD_NOT
    with open(ours_p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    for p in problems:
        print(f"merge_state: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
