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
- a field both sides set to different values takes the later change: each side's own
  history says when its value was set (the author date of the commit that set it, which
  a rebase keeps), and the merge says which it kept and what the other side had, so a
  person who wants the other can say so;
- where neither change is later (no history to read, or the same moment), or a row one
  side removed while the other changed it, it is a real conflict. The CSV gets git's
  markers around the two versions of that row, the JSON keeps this side's value, the
  conflicts are listed, and the exit is 1, so git leaves the file for a person, as it
  would have anyway.

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
# A log row both sides changed is still one row: the fields that say which message it is.
# Keyed by its whole row, a message one chat named the file of and another added the words
# of was two new rows and a removed one, and the merge kept both copies, saying nothing;
# the copy read as a second message sent and spent the one nudge (networking audit,
# 2026-10-25). Only a row in the common ancestor that both sides changed is paired this
# way: two messages each side added on one day are two messages, and both are kept.
SAME_MESSAGE = {"network_threads.csv": ("contact_id", "date", "direction", "channel")}
# Free text that both sides may have added to: kept from both, never a conflict.
NOTES = {"notes"}
# Lists of records inside a JSON state file, merged item by item the way rows are: each
# item is known by the fields that never change once it is written, so one side retiring
# a rule and the other adding one keeps both. Without this a list both sides added to was
# one value, and two chats recording a reaction on the same day stopped every merge of the
# person's rules (three times on 2026-10-24, each kept by hand).
LIST_KEYS = {
    "learned.json": {
        "entries": ("date", "area", "said", "rule"),
        "approved": ("date", "said", "text"),
        "skipped": ("date", "said", "why"),
        "offers": ("setting", "version"),
    },
    # The employers where the person wants more people written to (reading.py more-at):
    # a list at the top of the file, one row an employer.
    "more_at.json": {"": ("employer",)},
}


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


def merge_fields(base: dict | None, ours: dict, theirs: dict,
                 decide=None) -> tuple[dict, list[str], list[str]]:
    """One row both sides changed: field by field. `decide(field, ours, theirs)` says which
    side made the later change ("ours", "theirs", or "" when neither is known to be later).
    Returns (row, conflicting fields, what was settled by which change was later)."""
    base = base or {}
    out, clash, settled = {}, [], []
    for k in list(ours) + [k for k in theirs if k not in ours]:
        b, o, t = base.get(k), ours.get(k), theirs.get(k)
        if o == t or t == b:
            out[k] = o if k in ours else t
        elif o == b:
            out[k] = t
        elif k in NOTES and all(isinstance(v, str) or v is None for v in (b, o, t)):
            out[k] = merge_note(b or "", o or "", t or "")
        else:
            side = decide(k, o, t) if decide else ""
            if side:
                kept, other = (o, t) if side == "ours" else (t, o)
                out[k] = kept
                settled.append(f"{k}: kept {kept!r}, the later change; the other side had "
                               f"{other!r}")
            else:
                out[k], clash = o, clash + [k]
    return out, clash, settled


# ------------------------------------------------------------------ CSV


# The byte-order mark a spreadsheet's "CSV UTF-8" starts a file with. Read as part of the
# first column's name ("\ufeffcontact_id"), the marked side's rows had no key, the other
# side's read as removed, and every contact_id in the merged book came back empty with no
# conflict said (networking audit, 2026-10-25). It is dropped from each side on reading,
# so the merge is row by row and the file is written back without it.
_MARK = "\ufeff"


def _unmark(text: str) -> str:
    return text[len(_MARK):] if text.startswith(_MARK) else text


def decode(raw: bytes) -> str:
    """One side of the merge as text, read the way every tool reads a state file
    (csv_store.decode): the mark dropped, a file a spreadsheet saved in Windows' own
    encoding read as that. Raises ValueError for a file that cannot be read for sure (UTF-8
    with a damaged character), and the merge is left to git's line merge, which loses
    nothing."""
    try:
        import csv_store
    except ImportError:  # git runs this alone: without its neighbour, UTF-8 or nothing
        return _unmark(raw.decode("utf-8"))
    text, how = csv_store.decode(raw)
    if how == csv_store.DAMAGED:
        raise ValueError("a character in it is not readable text")
    return text


def _read(text: str) -> tuple[list[str], list[dict]]:
    rows = list(csv.reader(io.StringIO(_unmark(text), newline="")))
    if not rows:
        return [], []
    head = rows[0]
    return head, [dict(zip(head, (r + [""] * len(head))[:len(head)]))
                  for r in rows[1:] if r]


def _pair_edits(B: dict, O: dict, T: dict, ident) -> None:
    """A base row neither side kept as it was, where each side holds exactly one new row
    that is the same message (`ident`): that row changed on both sides. Theirs and the
    base are put under our key, in place, so the row is merged field by field."""
    def same(row):
        return tuple(str(row.get(f) or "").strip() for f in ident)

    new_o = [k for k in O if k not in B]
    new_t = [k for k in T if k not in B]
    for k in [k for k in B if k not in O and k not in T]:
        mine = [x for x in new_o if same(O[x]) == same(B[k])]
        theirs = [x for x in new_t if same(T[x]) == same(B[k])]
        if len(mine) == 1 and len(theirs) == 1 and mine[0] not in T:
            T[mine[0]] = T.pop(theirs[0])
            B[mine[0]] = B.pop(k)
            new_o.remove(mine[0])
            new_t.remove(theirs[0])


def _keyed(rows: list[dict], fields) -> dict:
    """{key: row}, with the n-th repeat of a key kept apart as (key, n)."""
    out, n = {}, {}
    for r in rows:
        k = tuple(r.get(f, "") for f in fields) if fields else tuple(r.values())
        n[k] = n.get(k, 0) + 1
        out[(k, n[k])] = r
    return out


# The fields that say what follows on a contact row. The app writes them from the message
# log (state.write_follow_ups), and a chat or the person writes them from what they know.
FOLLOWS = ("status", "next_action", "next_action_due")


def _app_words():
    """The test for a next action in the app's own words (state._APP_ACTION), or None where
    this checkout cannot read it: the merge then settles the field as before."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        for p in (os.path.join(here, "network"), here):
            if p not in sys.path:
                sys.path.insert(0, p)
        import state  # noqa: E402  the app's own words live there
        return lambda v: bool(state._APP_ACTION.fullmatch(" ".join(str(v or "").split())))
    except Exception:  # noqa: BLE001  an old or half-merged checkout: as before
        return None


def _own_side(b: dict | None, o: dict, t: dict) -> str:
    """On a contact row both sides changed, the side whose next action was written by a chat
    or the person, where the other side's is the app's own words: "ours", "theirs" or "".
    The app's is worked out from the message log as that side saw it, and a background
    upgrade's copy of the log was older than the chat's: its "no more follow-ups" won as the
    later change over a reply the chat had just logged (2026-10-24). Its line can always be
    worked out again; theirs cannot."""
    b = b or {}
    if not ({"next_action"} <= set(o) and o.get("next_action") != t.get("next_action")
            and b.get("next_action") not in (o.get("next_action"), t.get("next_action"))):
        return ""
    app = _app_words()
    if app is None:
        return ""
    mine, other = app(o.get("next_action")), app(t.get("next_action"))
    if mine == other:
        return ""
    own = "theirs" if mine else "ours"
    kept = t if own == "theirs" else o
    return own if str(kept.get("next_action") or "").strip() else ""


def merge_csv(base: str, ours: str, theirs: str, name: str, later=None,
              settled: list | None = None, ending: str | None = None) -> tuple[str, list[str]]:
    """`later(key, field, ours, theirs)` says which side changed a field last (see
    `git_later`); what it settled is appended to `settled`. `ending` is the line ending to
    write: by default a state file's is plain (LF), as .gitattributes asks, and any other
    file keeps ours'."""
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
    if fields is None and all(f in head for f in SAME_MESSAGE.get(name, ("",))):
        _pair_edits(B, O, T, SAME_MESSAGE[name])
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
        decide = (lambda f, ov, tv: later(k, f, ov, tv)) if later and fields else None
        own = _own_side(b, o, t) if name == "network_contacts.csv" else ""
        if own:
            first = decide

            def decide(f, ov, tv, first=first):     # noqa: F811  what follows: their own
                return own if f in FOLLOWS else (first(f, ov, tv) if first else "")
        row, clash, done = merge_fields(b, o, t, decide)
        if own:
            done = [d.replace("the later change", "the next step a chat or the person wrote, "
                              "over one the app worked out from an older copy of the "
                              "messages") if d.split(":", 1)[0] in FOLLOWS else d for d in done]
        if settled is not None:
            settled.extend(f"{name}: {', '.join(k[0])}: both changed {d}" for d in done)
        if clash:
            problems.append(f"{name}: {', '.join(k[0])}: both changed {', '.join(clash)}")
            return ("conflict", o, t)
        return row

    for k in O:
        out.append(place(k))
    for k in T:
        if k not in O:
            out.append(place(k))
    if ending is None:
        # The state files are kept with plain endings (.gitattributes: eol=lf). Ours' ending
        # was kept, so a chat branch from before that rule wrote CRLF back into a merge with
        # master, and the next sync stopped on a file no row of which had changed (2026-10-21).
        ending = "\n" if name in KEYS or not ours.split("\n", 1)[0].endswith("\r") \
            else "\r\n"
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


def merge_list(base, ours: list, theirs: list, fields, path: str,
               settled: list | None = None) -> tuple[list, list[str]]:
    """A list of records both sides changed, item by item: ours in its order, then what
    only theirs added. An item both kept is merged field by field; one a side removed
    goes, unless the other side changed it, which is a conflict."""
    def key(item):
        if isinstance(item, dict):
            return tuple(json.dumps(item.get(f), sort_keys=True) for f in fields)
        return ("", json.dumps(item, sort_keys=True))

    def index(items):
        out: dict = {}
        for it in items:
            out.setdefault(key(it), it)
        return out

    b = index(base if isinstance(base, list) else [])
    o, t = index(ours), index(theirs)
    out, problems = [], []
    for n, item in enumerate(ours, 1):
        k = key(item)
        label = f"{path} item {n}"
        if k in t:
            merged, more = merge_json(b.get(k), item, t[k], label, None, settled)
            out.append(merged)
            problems += more
        elif k in b:
            if item != b[k]:
                problems.append(label + " (removed on one side, changed on the other)")
                out.append(item)
        else:
            out.append(item)
    for k, item in t.items():
        if k in o:
            continue
        if k in b:
            if item != b[k]:
                problems.append(f"{path} item (removed on one side, changed on the other)")
                out.append(item)
        else:
            out.append(item)
    return out, problems


def merge_json(base, ours, theirs, path: str = "", later=None,
               settled: list | None = None, lists: dict | None = None) -> tuple[object, list[str]]:
    """Dicts merge key by key, all the way down; a list `lists` names, item by item
    (merge_list); anything else three ways, the later change taking a value both sides
    changed where `later(path, ours, theirs)` knows it."""
    if ours == theirs or theirs == base:
        return ours, []
    if ours == base:
        return theirs, []
    if lists and path in lists and isinstance(ours, list) and isinstance(theirs, list):
        return merge_list(base, ours, theirs, lists[path], path, settled)
    if not (isinstance(ours, dict) and isinstance(theirs, dict)):
        # Only a single value is settled by the later change: a list both sides added to
        # would lose the other side's items, so it is left for a person as before.
        scalar = all(v is None or isinstance(v, (str, int, float, bool)) for v in (ours, theirs))
        side = later(path, ours, theirs) if later and path and scalar else ""
        if side:
            kept, other = (ours, theirs) if side == "ours" else (theirs, ours)
            if settled is not None:
                settled.append(f"{path}: both changed it: kept {kept!r}, the later change; "
                               f"the other side had {other!r}")
            return kept, []
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
        out[k], more = merge_json(base.get(k), ours[k], theirs[k], sub, later, settled, lists)
        problems += more
    return out, problems


# ------------------------------------------------------------------ the driver

# What git runs. Git runs a merge driver from the top of the working tree, so the path
# is relative and each worktree runs its own copy; a checkout too old to have this file
# merges lines the way git always did.
# merge_state exits 0 or 1 when it merged; anything else (an old Python, a crash,
# no Python at all) and git's own line merge runs instead, which marks every
# conflict in the file. The file is never left holding only this side's rows.
#
# It runs the Python that installed it, by its full path: `python3` is not a command on
# a Windows computer with python.org's Python (docs.python.org/3/using/windows.html), so
# a driver that said python3 fell back to the line merge there on every merge, and two
# chats' appended rows conflicted. Should that Python have gone since (removed, or a
# virtual environment deleted), the shell says 126 or 127 and tools/py.sh finds another.
# Git runs the driver in a shell (on Windows, the one Git Bash brings), so the path is
# written with forward slashes and single-quoted.
def _sh_quote(path: str) -> str:
    return "'" + path.replace("\\", "/").replace("'", "'\\''") + "'"


def driver(python: str = "") -> str:
    exe = _sh_quote(python or sys.executable or "python3")
    return ("if [ -f tools/merge_state.py ]; then "
            f"{exe} tools/merge_state.py %O %A %B %P; rc=$?; "
            "if [ $rc -ge 126 ] && [ -f tools/py.sh ]; then "
            "sh tools/py.sh tools/merge_state.py %O %A %B %P; rc=$?; fi; "
            "if [ $rc -le 1 ]; then exit $rc; fi; fi; "
            "git merge-file -L ours -L base -L theirs %A %O %B")


DRIVER = driver()


def install(root: str) -> None:
    """Point this repo's git config at the driver. Config is not committed, so every
    container sets it again: two quick config writes, and never an error."""
    import subprocess
    for k, v in (("name", "state files, row by row"), ("driver", driver())):
        subprocess.run(["git", "-C", root, "config", f"merge.ljs-state.{k}", v],
                       capture_output=True, text=True, check=False,
                       encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ which change was later

# The other side of whatever git is doing. A merge names it in the driver's environment
# (GITHEAD_<sha>, which git sets for its conflict labels: MERGE_HEAD is written only after
# the driver has run); a rebase names the commit it is picking in its own todo list.
_THEIRS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD")


def _git(*args) -> str:
    import subprocess
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _theirs() -> str:
    import re
    # Any case: on Windows Python gives every name in os.environ in capitals
    # (https://docs.python.org/3/library/os.html#os.environ), so GITHEAD_<sha> came back
    # with its sha in capitals, matched nothing, and every change both chats made to one
    # row was left for a person there (2026-10-25).
    named = [k[len("GITHEAD_"):].lower() for k in os.environ
             if re.fullmatch(r"GITHEAD_[0-9a-fA-F]{40}([0-9a-fA-F]{24})?", k)]
    if len(named) == 1:
        return named[0]
    if named:
        return ""                                   # an octopus merge: no one other side
    for ref in _THEIRS:
        got = _git("rev-parse", "-q", "--verify", ref).strip()
        if got:
            return got
    gd = _git("rev-parse", "--git-dir").strip()
    try:
        with open(os.path.join(gd, "rebase-merge", "done"), encoding="utf-8") as fh:
            last = [ln.split() for ln in fh if ln.strip() and not ln.startswith("#")]
    except OSError:
        return ""
    return last[-1][1] if last and len(last[-1]) > 1 else ""


def git_later(path: str):
    """`later(key, field, ours, theirs)` for the file git is merging, read from each side's
    own history: when did each side's value appear, by the author date of the commit that
    set it (a rebase keeps it)? None where git has no other side to read, and the merge
    then leaves a field both sides changed for a person, as before."""
    theirs_ref = _theirs()
    if not theirs_ref:
        return None
    base_ref = _git("merge-base", "HEAD", theirs_ref).strip()
    if not base_ref:
        return None
    name = os.path.basename(path)
    fields = KEYS.get(name)
    cache: dict = {}

    def value(commit, key, field):
        if commit not in cache:
            text = _git("show", f"{commit}:{path}")
            if name.endswith(".json"):
                try:
                    cache[commit] = json.loads(text) if text.strip() else {}
                except ValueError:
                    cache[commit] = {}
            else:
                _head, rows = _read(text)
                cache[commit] = _keyed(rows, fields) if fields else {}
        got = cache[commit]
        if name.endswith(".json"):
            # A key can hold a slash itself (seen_jobs.json is keyed by URL), so the
            # path is walked by the longest key at each level that starts what is left.
            rest = key
            while rest:
                if not isinstance(got, dict):
                    return None
                part = max((k for k in got if rest == k or rest.startswith(k + "/")),
                           key=len, default=None)
                if part is None:
                    return None
                got, rest = got[part], rest[len(part) + 1:]
            return got
        row = got.get(key)
        return None if row is None else row.get(field)

    def introduced(ref, key, field, final) -> int:
        """When `final` became this side's value: the oldest of the newest run of commits
        that carry it. 0 where the side never set it since the two parted."""
        when = 0
        for ln in _git("log", "--format=%H %at", f"{base_ref}..{ref}", "--", path).splitlines():
            commit, _, at = ln.partition(" ")
            if value(commit, key, field) != final:
                break
            when = int(at) if at.isdigit() else 0
        return when

    def later(key, field, ours, theirs):
        a = introduced("HEAD", key, field, ours)
        b = introduced(theirs_ref, key, field, theirs)
        if a and b and a != b:
            return "ours" if a > b else "theirs"
        return ""

    if name.endswith(".json"):                     # a JSON value is found by its path alone
        return lambda where, ours, theirs: later(where, None, ours, theirs)
    return later


def eol(path: str) -> str | None:
    """The line ending .gitattributes asks for `path` ("\n" for eol=lf, "\r\n" for
    eol=crlf), or None when it names none or git cannot say."""
    got = _git("check-attr", "eol", "--", path).strip()
    value = got.rsplit(": ", 1)[-1] if got else ""
    return {"lf": "\n", "crlf": "\r\n"}.get(value)


def merge(base: str, ours: str, theirs: str, path: str, later=None,
          settled: list | None = None, ending: str | None = None) -> tuple[str, list[str]]:
    name = os.path.basename(path)
    base, ours, theirs = _unmark(base), _unmark(ours), _unmark(theirs)
    if name.endswith(".json"):
        try:
            b = json.loads(base) if base.strip() else {}
            o, t = json.loads(ours), json.loads(theirs)
        except ValueError as e:
            return ours, [f"{path}: not JSON on one side ({e})"]
        merged, problems = merge_json(b, o, t, later=later, settled=settled,
                                      lists=LIST_KEYS.get(name))
        return json.dumps(merged, indent=2, ensure_ascii=False) + "\n", problems
    return merge_csv(base, ours, theirs, name, later=later, settled=settled, ending=ending)


# Exit codes. 0 merged; 1 merged with real conflicts marked for a person. Anything
# else means this driver could not merge at all and wrote nothing, and the driver
# command (DRIVER) then runs git's own line merge, which marks every conflict: a
# state file is never left as one side's copy with the other side's rows lost.
COULD_NOT = 3


def main(argv: list[str]) -> int:
    if argv[:1] in (["-h"], ["--help"]):
        print("usage: python3 tools/merge_state.py %O %A %B %P  (git runs it as the merge "
              "driver for the state files; tools/sync_app.py sets that up)")
        return 0
    if sys.version_info[:2] < FLOOR:
        print(f"merge_state: Python {FLOOR[0]}.{FLOOR[1]} or newer is needed; this is "
              f"{platform.python_version()} (python3 tools/env_check.py says how to install it)",
              file=sys.stderr)
        return COULD_NOT
    # What it prints names people ("Łukasz"), and a cp1252 Windows terminal could not show
    # them: the driver stopped mid-merge and git fell back to its line merge.
    try:
        import python_floor
        python_floor.utf8_stdio()
    except Exception:  # noqa: BLE001  git runs this alone; nothing else need be importable
        pass
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    base_p, ours_p, theirs_p, path = argv

    def read(p):
        with open(p, "rb") as f:
            return decode(f.read())

    settled: list[str] = []
    try:
        text, problems = merge(read(base_p), read(ours_p), read(theirs_p), path,
                               later=git_later(path), settled=settled, ending=eol(path))
    except Exception as e:  # noqa: BLE001  nothing is written; git's line merge takes over
        print(f"merge_state: could not merge {path} ({type(e).__name__}: {e}); "
              "git's line merge marks the conflicts instead", file=sys.stderr)
        return COULD_NOT
    with open(ours_p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    for p in settled:
        print(f"merge_state: {p}. Claude: tell the person in plain words which of their two "
              "answers was kept and what the other said, never a file or field name; their "
              "word outranks this.", file=sys.stderr)
    for p in problems:
        print(f"merge_state: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
