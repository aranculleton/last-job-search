#!/usr/bin/env python3
"""The page's database, as files: what a chat reads back from it and what it writes to it.

A chat never types a document into a tool call. It saves what it reads with ArtifactData's
`out_dir` (`<dir>/<collection>/<doc_id>.json`), runs code over those files, and sends what
the code wrote back in one ArtifactData `batch`, each entry naming a `file_path`. This module
is both halves: `load()` reads a dump in either shape a document can come back in, and
`Writes` builds the batch files (at most 50 entries each, the tool's limit).

It also holds the shared rules every chat follows for the work list (CONTRACT.md section 2,
WORKFLOWS.md section 2):

  WORK_KINDS   each kind of work: where it runs by default, where it can run, how heavy it
               is, and the stages a chat reports at, with their usual seconds
  next_item()  which queued item a chat should claim: its own kind of chat, the oldest of
               the most urgent, never one whose employer, contact or search another job holds
  claim()      the claim as one batch: the item pinned to the version read (`if_version`),
               each lock created (refused if it exists), and the chat's own heartbeat
  pin()        one stage's progress on a running item, and how long is left when it is known
               (a search's job sites say it themselves: round_progress())
  busy_beat()  the line the page shows while the chat does something asked in the chat

Pure code, standard library only, no network.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

COLLECTIONS = ("actions", "receipts", "work", "chats", "locks", "talk", "meta", "view",
               "reach", "addr")

# Where each record lives in the store. The code names a record by what it is (`view`,
# `meta/listener`); the store keeps the ones only chats write under names of 4.3's own, so
# no write ever needs the version of a record made before every write carried it (`_v`,
# below). Before 4.3 those records came back with no version, and every write to them was
# refused (the maintainer's copy, 2026-10-29).
STORE = {"view": "screen", "chats": "beats", "locks": "holds"}
STORE_DOC = {("meta", "listener"): "listen", ("meta", "current"): "now"}
_LOGICAL = {v: k for k, v in STORE.items()}
_LOGICAL_DOC = {("meta", v): k for (c, k), v in STORE_DOC.items()}


def stored(collection: str, doc_id: str = "") -> tuple[str, str]:
    """(collection, doc id) as the store holds them."""
    return STORE.get(collection, collection), STORE_DOC.get((collection, doc_id), doc_id)


# The access levels a database rule names, lowest first, and the levels a document has with
# no rule at all (artifact-capabilities, db: "view < interact < admin < owner").
LEVELS = ("view", "interact", "admin", "owner")
DEFAULT_LEVEL = {"read": "view", "write": "interact"}


def can(rules, path: str, op: str, level: str) -> bool:
    """Whether a viewer at `level` may `op` ("read" or "write") the document at `path`,
    under `rules` as the page declares them: the most specific rule naming the op wins (a
    rule's path is a prefix of whole segments), else the platform's default."""
    segs = [x for x in str(path or "").split("/") if x]
    need, best = DEFAULT_LEVEL[op], -1
    for rule in rules or ():
        rsegs = [x for x in str(rule.get("path") or "").split("/") if x]
        if op not in rule or len(rsegs) > len(segs) or len(rsegs) <= best:
            continue
        if all(a == b or (a.startswith("{") and a.endswith("}")) for a, b in zip(rsegs, segs)):
            need, best = rule[op], len(rsegs)
    return LEVELS.index(level) >= LEVELS.index(need)
BATCH_MAX = 50
DOC_MAX = 256 * 1024
# No "@": ArtifactData writes a "~" as "@" in a saved file's name, so an "@" of an id's own
# could not be told from it.
_SAFE_ID = re.compile(r"[^A-Za-z0-9_\-.~:+]+")
# One batch's body stays under the tool's 1 MiB, with room for the entries around the files.
BATCH_BYTES = 900_000

# ------------------------------------------------------------------ reading a dump

# Fields a document's wrapper may carry beside its data, as a tool or a page writes it.
_WRAPPER = {"id", "doc_id", "version", "data", "path", "collection", "created_at",
            "updated_at", "create_time", "update_time", "__version__", "_version"}


# Every write, by a chat or by the page, carries the version the record will have once it
# lands (`_v`): the store counts up by one a write, starting at 1 (checked against the store
# itself, 2026-10-29). ArtifactData's `out_dir` saves a record's fields and nothing else, so
# `_v` is how a chat reading a dump knows what to pin its next write to.
VERSION_FIELD = "_v"


def _version_of(obj) -> tuple[dict, int | None, bool]:
    """(fields, version, whether the store itself gave the version): the wrapper's or
    `__version__` beside the fields is the store's own; `_v` is only what the last writer
    said it would be."""
    if not isinstance(obj, dict):
        return {}, None, False
    if isinstance(obj.get("data"), dict) and set(obj) <= _WRAPPER:
        version = obj.get("version", obj.get("__version__", obj.get("_version")))
        fields = dict(obj["data"])
    else:
        fields = {k: v for k, v in obj.items() if k not in ("__version__", "_version")}
        version = obj.get("__version__", obj.get("_version"))
    own = fields.pop(VERSION_FIELD, None)
    real = isinstance(version, int) and not isinstance(version, bool)
    if not real:
        version = own if isinstance(own, int) and not isinstance(own, bool) and own > 0 else 1
    return fields, version, real


def unwrap(obj) -> tuple[dict, int | None]:
    """(the document's fields, its version) from one dumped file. A dump holds either the
    fields themselves, or a wrapper {id, version, data}. The version is the wrapper's, else
    `__version__` or `_version` beside the fields, else the record's own `_v`, else 1: a
    record from before `_v` that a chat never rewrote was made once, by the page."""
    fields, version, _real = _version_of(obj)
    return fields, version


# ------------------------------------------------------------------ the store's own number
#
# `_v` is a stamp the last writer put in the record, not the store's count. One write that
# stamped it wrong (a write by hand, a page with an old copy of the record) and every chat
# read the wrong number back, every write pinned to it was refused, and a new read gave the
# same number again: the listener's check-in bounced on every wake (the maintainer, 4
# November). The store names its real version when it refuses; `app.py version` keeps that
# here, in the copy's git folder, beside the stamp it corrects, and every later read whose
# record still carries that stamp is pinned to the store's number, so the next write lands
# and stamps the record right again. A record the store gave its own version for is never
# corrected: the store's number always wins.
KNOWN_VERSIONS = "ljs-versions.json"
KNOWN_DAYS = 7
_KNOWN_PATH: list = []


def _known_path() -> str:
    """Where the versions the store named are kept: LJS_VERSIONS (tests), else the copy's git
    folder (never committed), else "" (nothing kept)."""
    given = os.environ.get("LJS_VERSIONS")
    if given:
        return given
    if _KNOWN_PATH:
        return _KNOWN_PATH[0]
    path = ""
    try:
        import subprocess
        import person
        r = subprocess.run(["git", "-C", person.state(), "rev-parse", "--absolute-git-dir"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=10, stdin=subprocess.DEVNULL)
        if r.returncode == 0 and r.stdout.strip():
            path = os.path.join(r.stdout.strip(), KNOWN_VERSIONS)
    except Exception:  # noqa: BLE001  no copy, no git: nothing is kept
        path = ""
    _KNOWN_PATH.append(path)
    return path


def known_versions() -> dict:
    """{"<stored collection>/<stored doc id>": {"stamp": n, "real": m, "at": iso}}."""
    path = _known_path()
    got = _read_json(path) if path else None
    return got if isinstance(got, dict) else {}


def remember_version(ref: str, stamp: int | None, real: int, now: dt.datetime | None = None) -> None:
    """Keep the store's version for a record whose stamp read `stamp`."""
    path = _known_path()
    if not path or not isinstance(stamp, int):
        return
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = (now - dt.timedelta(days=KNOWN_DAYS)).strftime("%Y-%m-%dT%H:%M:%S")
    got = {k: v for k, v in known_versions().items()
           if isinstance(v, dict) and str(v.get("at") or "") >= cutoff}
    got[ref] = {"stamp": int(stamp), "real": int(real), "at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(got, fh, indent=1, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
    except OSError:
        pass


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ the store's version, as read
#
# ArtifactData's `out_dir` saves a record's fields and nothing else: the version is only in the
# lines the read prints, one a record (checked against the store itself, 2026-11-09):
#     - "due"  13 bytes  version 2  "<out_dir>/screen/due.json"
# Read from the files alone, every record came back at its `_v` stamp, which the page writes from
# its own copy and so can be behind or ahead, or at 1 for a record no stamp was kept for: every
# screen of a page update was pinned to 1 while the page held them at 82, and refused, and a
# chat put the right numbers in by hand, fifty at a time (a person's computer, 2026-11-09).
# `keep_listed` writes each listed version into its file, beside the fields (`__version__`,
# which `load()` takes as the store's own number), so every command over the folder pins to the
# page's own number. The app's hook keeps them after every read of the page's database
# (`learned.py hook` on PostToolUse for ArtifactData, keep_listed_event; registered on
# 2026-11-09 by the maintainer, since Claude may not add a hook itself). `app.py versions`
# does it from the lines given to it, for a copy whose settings do not register the hook
# yet (`hook_keeps_versions`), so the step is asked for only there.
LISTED = re.compile(r'\bversion\s+(\d+)\s+"([^"\r\n]+?\.json)"')
SHORT = re.compile(r"^\s*([A-Za-z0-9_\-.~:@+]+(?:/[A-Za-z0-9_\-.~:@+]+)*)/([A-Za-z0-9_\-.~:@+]+)"
                   r"\s*[\s=]\s*(\d+)\s*$")
STORE_VERSION = "__version__"
LISTED_MARK = ".versions.json"      # in a dump folder: the read's versions were kept here
# What a chat is told to do after its reads where the app's hook does not keep the versions.
VERSIONS_STEP = ("then keep the page's own version of each record: python3 tools/app.py versions "
                 "\"{dump}\" with the lines those reads printed on its input (a heredoc), each "
                 "`- \"<id>\"  N bytes  version V  \"<file>\"` as printed, or typed short, "
                 "`<collection>/<doc id> V` a line")


def hook_keeps_versions() -> bool:
    """Does this copy's Claude Code settings run the app's hook after a read of the page
    (PostToolUse on ArtifactData), so each read keeps its versions by itself?"""
    path = os.path.join(os.path.dirname(_HERE), ".claude", "settings.json")
    got = _read_json(path)
    entries = ((got or {}).get("hooks") or {}).get("PostToolUse") if isinstance(got, dict) else None
    for e in entries if isinstance(entries, list) else ():
        matcher = str(e.get("matcher") or "*") if isinstance(e, dict) else ""
        if not matcher or (matcher != "*" and "ArtifactData" not in matcher):
            continue
        if any("learned.py hook" in str((h or {}).get("command") or "")
               for h in e.get("hooks") or [] if isinstance(h, dict)):
            return True
    return False


def versions_step(dump: str) -> str:
    """The step that keeps the read's versions, or "" where the hook keeps them."""
    return "" if hook_keeps_versions() else VERSIONS_STEP.format(dump=dump)


def keep_listed(text: str, out_dir: str) -> int:
    """Each record the read's lines name under `out_dir`, given the version the store listed
    it at. Returns how many files took one. A file outside `out_dir`, or not a record the read
    saved, is left alone."""
    if not text or not out_dir:
        return 0
    root = os.path.realpath(out_dir)
    n = 0
    found = list(LISTED.findall(str(text)))
    for line in str(text).splitlines():
        # The short form a chat may type instead: "<collection>/<doc id> <version>".
        got = SHORT.match(line)
        if got and not LISTED.search(line):
            coll, doc_id, version = got.group(1), got.group(2), got.group(3)
            found.append((version, os.path.join(root, *coll.split("/"),
                                                doc_id.replace("~", "@") + ".json")))
    for version, path in found:
        real = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
        if not real.startswith(root + os.sep) or not os.path.isfile(real):
            continue
        got = _read_json(real)
        if not isinstance(got, dict):
            continue
        got[STORE_VERSION] = int(version)
        try:
            tmp = f"{real}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(got, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            os.replace(tmp, real)
            n += 1
        except OSError:
            continue
    if n:
        mark = os.path.join(root, LISTED_MARK)
        had = _read_json(mark)
        had = had if isinstance(had, dict) else {}
        try:
            with open(mark, "w", encoding="utf-8", newline="\n") as fh:
                json.dump({"records": int(had.get("records") or 0) + n}, fh)
        except OSError:
            pass
    return n


def _strings(obj, out: list) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _strings(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _strings(v, out)


def keep_listed_event(event: dict) -> int:
    """The hook's half, for a copy whose settings run `learned.py hook` on PostToolUse after an
    ArtifactData read with `out_dir` (hook_keeps_versions): the versions its
    result lists, kept in the files it saved. Any other call: nothing."""
    if not isinstance(event, dict) or str(event.get("tool_name") or "") != "ArtifactData":
        return 0
    given = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    out = str(given.get("out_dir") or "")
    if not out or str(given.get("action") or "") not in ("get", "list", "query"):
        return 0
    if not os.path.isabs(out):
        out = os.path.join(str(event.get("cwd") or os.getcwd()), out)
    said: list = []
    _strings(event.get("tool_response"), said)
    return keep_listed("\n".join(said), out)


def listed_here(dump_dir: str) -> bool:
    """Were the store's own versions kept in this folder by a read (`keep_listed`)?"""
    return os.path.isfile(os.path.join(dump_dir, LISTED_MARK))


def load(dump_dir: str) -> dict:
    """{collection: {doc_id: {"data": fields, "version": n or None}}} for every collection
    the chat dumped into `dump_dir`. A collection not dumped is empty.

    A record read under its 4.2 name (`view/jobs`, `meta/listener`) stands for its new one
    only while the new one does not exist, and then with no version and `"old": True`: its
    version is the old record's, which the new name never had, so a write pinned to it was
    refused (2026-10-29). The first write makes the new record, and `move()` makes them all."""
    out: dict = {c: {} for c in COLLECTIONS}
    known = None
    for coll in COLLECTIONS:
        new = STORE.get(coll, coll)
        # The old name first, so a record under its new name always wins.
        for where in dict.fromkeys((coll, new)):
            for path in sorted(glob.glob(os.path.join(dump_dir, where, "*.json"))):
                got = _read_json(path)
                if got is None:
                    continue
                fields, version, real = _version_of(got)
                if not real:
                    # Its own stamp only: a wrong one the store has corrected is read as the
                    # store's number (KNOWN_VERSIONS).
                    if known is None:
                        known = known_versions()
                    stem = os.path.splitext(os.path.basename(path))[0].replace("@", "~")
                    fix = known.get(f"{where}/{stem}") if known else None
                    if isinstance(fix, dict) and fix.get("stamp") == version \
                            and isinstance(fix.get("real"), int) and fix["real"] > 0:
                        version = fix["real"]
                # ArtifactData spells a "~" in an id as "@" in the file's name; ids never
                # hold an "@" of their own (safe_id), so every "@" is a "~".
                doc_id = os.path.splitext(os.path.basename(path))[0].replace("@", "~")
                old = where != new
                if coll == "meta":
                    old = ("meta", doc_id) in STORE_DOC
                    doc_id = _LOGICAL_DOC.get(("meta", doc_id), doc_id)
                if not old:
                    out[coll][doc_id] = {"data": fields, "version": version}
                elif doc_id not in out[coll] or out[coll][doc_id].get("old"):
                    out[coll][doc_id] = {"data": fields, "version": None, "old": True}
    return out


# ------------------------------------------------------------------ moving a 4.2 page

# A page a 4.2 chat left holds its records under the old names. The first chat on 4.3 that
# answers the page makes every new record from its old one, in code: the old one's fields
# with the version a new record has (1, as `_v`), and last `meta/moved`, so no chat moves
# them twice. The old records are left as they are: a write to one needs its version, which
# a 4.2 read never kept.
MOVED = "moved"
# What a move reads, besides what every wake reads: both names of each renamed collection,
# so a create never meets a record it did not know was there (a batch is all or nothing).
MOVE_READS = ("view", "screen", "chats", "beats", "locks", "holds")
_ASKED = ".move-asked"      # in a dump folder: the chat was asked to read MOVE_READS into it


def unmoved(dump_dir: str, db: dict) -> bool:
    """Does the store still hold a 4.2 page's records that were never moved? Told by meta,
    which every check-in reads: 4.2's `meta/listener` or `meta/current`, and no mark."""
    if MOVED in (db.get("meta") or {}):
        return False
    return any(os.path.isfile(os.path.join(dump_dir, "meta", doc_id + ".json"))
               for (_c, doc_id) in STORE_DOC)


def to_read(dump_dir: str, db: dict) -> list[str]:
    """The collections a chat reads into `dump_dir` before a move, once: [] when nothing
    needs moving, the old ones are there, or the chat was asked already. An empty collection
    leaves no folder, so a new one missing is no reason to ask: a create that meets a record
    the chat did not read is refused, and the chat reads again. Asking is noted in the
    folder."""
    if not unmoved(dump_dir, db) or os.path.exists(os.path.join(dump_dir, _ASKED)):
        return []
    if all(os.path.isdir(os.path.join(dump_dir, c)) for c in STORE):
        return []
    missing = [c for c in MOVE_READS if not os.path.isdir(os.path.join(dump_dir, c))]
    with open(os.path.join(dump_dir, _ASKED), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(missing) + "\n")
    return missing


def move(db: dict, dump_dir: str, out_dir: str, at: str, chat: str = "") -> dict:
    """The move as batch files: every record read only under its old name created under its
    new one, then the mark, in the last batch. {"batches", "entries", "db"}: `db` is the dump
    as it will be once they land, each moved record at version 1, for the writes this chat
    builds next. Nothing to move, no batches (and `db` as it was)."""
    if not unmoved(dump_dir, db):
        return {"batches": [], "entries": [], "db": db}
    w = Writes(out_dir)
    after = {c: dict(docs) for c, docs in db.items()}
    for coll in COLLECTIONS:
        for doc_id, doc in sorted((db.get(coll) or {}).items()):
            if not doc.get("old"):
                continue
            try:
                w.add("set", coll, doc_id, doc["data"])
            except ValueError:      # over the cap as it stands: its next write makes it
                continue
            after[coll][doc_id] = {"data": doc["data"], "version": 1}
    w.add("set", "meta", MOVED, {"at": at, "by": chat or None,
                                 "records": len(w.entries)})
    after.setdefault("meta", {})[MOVED] = {"data": {"at": at}, "version": 1}
    return {"batches": w.save("move"), "entries": w.entries, "db": after}


def moved_into(dump_dir: str, got: dict) -> None:
    """Write the moved records into the dump, as a read would save them once the move has
    landed, so every later step that reads the same folder pins to the versions they have."""
    for e in got.get("entries") or []:
        where = os.path.join(dump_dir, e["collection"])
        os.makedirs(where, exist_ok=True)
        with open(e["file_path"], encoding="utf-8") as fh:
            body = fh.read()
        name = e["doc_id"].replace("~", "@") + ".json"
        with open(os.path.join(where, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)


def safe_id(text: str) -> str:
    """A document id the database takes: letters, digits and _ - . ~ : + only."""
    return _SAFE_ID.sub("_", str(text or "")).strip("_")[:200] or "x"


# ------------------------------------------------------------------ a document too big for one

# A document the database would refuse (over DOC_MAX as `Writes` stores it) goes as parts: a
# head without the big field, naming how many parts (`in_parts`), then `part~<doc id>~<n>`,
# each holding a piece of that field's JSON text under `text` and the head's `rev`. The page
# joins them only when every part is there at the head's rev (templates/app/app.js joined()),
# and `joined()` below reads them back the same way. Each part stays well under the cap.
PART_BYTES = 200_000
PART_PREFIX = "part~"


ADDR_BYTES = 120_000


def addr_docs(reach: dict) -> dict:
    """Each contact's address (`app_model.reach_docs`) in `addr/part~<n>`, a contact always
    in the same one while the count of documents holds, so a change rewrites one document."""
    import zlib
    if not reach:
        return {}
    size = len(json.dumps(reach, ensure_ascii=False).encode("utf-8"))
    n = max(1, -(-size // ADDR_BYTES))
    out: dict = {}
    for cid in sorted(reach):
        k = f"part~{zlib.crc32(str(cid).encode('utf-8')) % n + 1}"
        out.setdefault(k, {"contacts": {}})["contacts"][str(cid)] = reach[cid]
    return out


def stored_size(doc) -> int:
    """Its bytes as `Writes.add` stores it."""
    return len(json.dumps(doc or {}, ensure_ascii=False, indent=1, sort_keys=True)
               .encode("utf-8"))


def part_id(doc_id: str, n: int) -> str:
    return f"{PART_PREFIX}{doc_id}~{n}"


def _pieces(text: str, limit: int) -> list[str]:
    """`text` cut into pieces, in order, each under `limit` bytes as a stored JSON string.
    Python cuts between code points, so a character is never split."""
    out, start = [], 0
    while start < len(text):
        piece = text[start:start + limit]
        while len(piece) > 1:
            n = stored_size({"text": piece}) + 200
            if n <= limit:
                break
            piece = piece[:max(1, int(len(piece) * limit / n) - 16)]
        out.append(piece)
        start += len(piece)
    return out or [""]


def split(doc_id: str, doc: dict, field: str = "data",
          limit: int = PART_BYTES) -> list[tuple[str, dict]]:
    """[(doc id, document)] to write for `doc`: itself when it fits in one document, else its
    parts first and the head last, so a reader that sees the head finds its parts there."""
    if stored_size(doc) <= DOC_MAX or field not in doc:
        return [(doc_id, doc)]
    text = json.dumps(doc[field], ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    pieces = _pieces(text, limit)
    head = {k: v for k, v in doc.items() if k != field}
    head["in_parts"] = len(pieces)
    rev = doc.get("rev")
    parts = [(part_id(doc_id, n), {"of": doc_id, "part": n, "rev": rev,
                                   "made_at": doc.get("made_at"), "text": piece})
             for n, piece in enumerate(pieces, 1)]
    return parts + [(doc_id, head)]


def joined(docs: dict, doc_id: str, field: str = "data"):
    """The value of `field` in `docs[doc_id]`, whole or joined from its parts; None when it
    is missing or a part is (or holds another rev). `docs` is one collection as `load()`
    returns it: {doc id: {"data": the document, "version": n}}."""
    def fields(i):
        got = (docs or {}).get(i)
        return got.get("data") if isinstance(got, dict) and isinstance(got.get("data"), dict) \
            else {}
    head = fields(doc_id)
    if field in head:
        return head[field]
    n = head.get("in_parts")
    if not isinstance(n, int) or n < 1:
        return None
    text = ""
    for i in range(1, n + 1):
        part = fields(part_id(doc_id, i))
        if part.get("rev") != head.get("rev") or not isinstance(part.get("text"), str):
            return None
        text += part["text"]
    try:
        return json.loads(text)
    except ValueError:
        return None


def stale_parts(docs: dict, written) -> list[str]:
    """The part documents `docs` holds that this write does not fill again: a section that
    shrank by a part, or one that fits in one document again."""
    keep = set(written)
    return sorted(d for d in (docs or {}) if d.startswith(PART_PREFIX) and d not in keep)


# ------------------------------------------------------------------ writing a batch


# A body file is named after its record, never spelled as the id is. Claude Code reads a
# name with "~" and a digit ("part~jobs~1.json") as a short Windows name that can stand for
# another file, so a write from it was a safety check a person had to allow every time, and
# no setting or earlier yes covered it: a new chat asked about 50 times (2026-10-30, its
# prompts read back from the chat). ArtifactData spells "~" as "@" in the files it saves for
# the same reason; ids never hold "@" or "=" (_SAFE_ID), and ":" is no name on Windows.
def body_name(part: str) -> str:
    return str(part).replace("~", "@").replace(":", "=")


def body_path(out_dir: str, collection: str, doc_id: str) -> str:
    """Where `Writes.add` keeps one record's body under `out_dir`."""
    return os.path.join(out_dir, "files", *[body_name(p) for p in collection.split("/") if p],
                        body_name(doc_id) + ".json")


def sent_size(entry: dict) -> int:
    """One batch entry's bytes as the request carries it, at the most: its body as JSON text
    inside JSON (every quote and backslash escaped again) with every character past ASCII
    written as an escape, plus the entry around it. Sized by the file on disk, one page update
    went as a 2.86 MB request against the 1 MiB limit: the screens' own JSON text, and their
    curly quotes and dots, grow by up to three times as they are sent (a person's copy,
    2026-11-09)."""
    head = len(json.dumps({k: v for k, v in entry.items() if k != "file_path"})) + 64
    path = entry.get("file_path")
    if not path:
        return head
    body = _read_json(path)
    if body is None:
        return head + 3 * os.path.getsize(path) if os.path.isfile(path) else head
    return head + max(os.path.getsize(path),
                      len(json.dumps(json.dumps(body, separators=(",", ":")))))


class Writes:
    """The writes one chat turn sends back, each body in a file of its own.

    `add()` keeps the body under `<out>/files/<collection>/<doc_id>.json` (its name spelled by
    `body_name`) and the entry ({op, collection, doc_id, file_path, if_version}); `save()`
    writes the entries as batch files of at most 50, and returns their paths."""

    def __init__(self, out_dir: str, db: dict | None = None):
        self.out_dir = out_dir
        self.entries: list[dict] = []
        # The dump the writes are made from: a write that names no version, to a record the
        # dump holds, is pinned to the version read. An unpinned write to a record that
        # exists is refused by the store, and the whole batch with it: answering the same
        # profile question or changing the same search setting twice stranded every tap in
        # that wake (engine audit, 2026-11-03).
        self.db = db

    def _read_version(self, collection: str, doc_id: str) -> int | None:
        if not self.db:
            return None
        logical = _LOGICAL.get(collection, collection)
        if collection == "meta":
            doc_id = _LOGICAL_DOC.get(("meta", doc_id), doc_id)
        doc = (self.db.get(logical) or {}).get(doc_id)
        v = (doc or {}).get("version")
        return v if isinstance(v, int) and not isinstance(v, bool) and not doc.get("old") else None

    def add(self, op: str, collection: str, doc_id: str, data: dict | None = None,
            if_version: int | None = None) -> dict:
        if op not in ("set", "update", "delete"):
            raise ValueError(f"page_db: no write {op!r}")
        collection, doc_id = stored(collection, safe_id(doc_id))
        if if_version is None:
            if_version = self._read_version(collection, doc_id)
        self.entries = [e for e in self.entries
                        if not (e["collection"] == collection and e["doc_id"] == doc_id)]
        entry = {"op": op, "collection": collection, "doc_id": doc_id}
        if op != "delete":
            data = dict(data or {})
            data[VERSION_FIELD] = int(if_version) + 1 if if_version is not None else 1
            body = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True)
            if len(body.encode("utf-8")) > DOC_MAX:
                raise ValueError(f"page_db: {collection}/{doc_id} is over 256 KiB"
                                 " (page_db.split() writes it as parts)")
            path = body_path(self.out_dir, collection, doc_id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body + "\n")
            entry["file_path"] = os.path.abspath(path)
        if if_version is not None:
            entry["if_version"] = int(if_version)
        self.entries.append(entry)
        return entry

    def drop(self, collection: str, doc_id: str) -> bool:
        collection, doc_id = stored(collection, doc_id)
        before = len(self.entries)
        self.entries = [e for e in self.entries
                        if not (e["collection"] == collection and e["doc_id"] == doc_id)]
        return len(self.entries) != before

    def save(self, name: str = "batch") -> list[str]:
        os.makedirs(self.out_dir, exist_ok=True)
        # At most 50 entries a batch, and at most BATCH_BYTES of bodies: one view went as a
        # 1.5 MB batch the tool refused (2026-10-26 and again 2026-10-29).
        parts: list[list[dict]] = [[]]
        size = 0
        for e in self.entries:
            n = sent_size(e)
            if parts[-1] and (len(parts[-1]) >= BATCH_MAX or size + n > BATCH_BYTES):
                parts.append([])
                size = 0
            parts[-1].append(e)
            size += n
        parts = [p for p in parts if p]
        paths = []
        for i, part in enumerate(parts):
            suffix = "" if len(parts) == 1 else f"_{i + 1}"
            path = os.path.join(self.out_dir, f"{name}{suffix}.json")
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(part, fh, ensure_ascii=False, indent=1)
                fh.write("\n")
            paths.append(os.path.abspath(path))
        return paths


# ------------------------------------------------------------------ the kinds of work

# Default stages, in plain words, from the app's own steps; the page replaces the seconds
# with the medians of the last ten finished items of the kind once there are ten.
#   search   run_round.py: scrape_wide, prefilter, hydrate, text_screen + opportunity + fit,
#            throttle and the round's summary
#   draft    the drafting path (RUNBOOK.md, "2. Draft"): stage_picks stage and consent,
#            employer research, draft_pack + the one drafting call, both audits,
#            fit_to_page, verify_batch
#   network  /network: sources and discovery, reading.py, compose, surface.check and advise
#   files    an application's resume and letter put in the page's own file store
#   tweak    one part of one output changed (TWEAKS.md): the part rewritten or a setting
#            changed, the app's checks and the session's own check, the PDF redrawn
#   prep     an interview pack (args.interview: interview_pack.py pack --write), or, with
#            args.contact, a networking call's prep (tools/network/prep.py "<contact>")
#   republish  the page's own code, published again by the listener only (app_listen.py)
# The page has a table of its own for the moment before a chat writes the stages
# (templates/app/app.js STAGES); a test keeps the two naming the same kinds.
STAGES = {
    # A search's job sites and a networking run's finding took 15 and 23 minutes in a real
    # copy (2026-10-29), against 5 and 4 here, so the page said "Stalled" on work that was
    # fine. A search says how long is left as it goes (`app.py pin --log`); these are only
    # the estimates before it does.
    # The job sites took 31 minutes in a real copy on 2026-10-30 against the 15 above, and the
    # person asked whether it had stuck: the estimate is the slower one, and the step says it is
    # the long part. Ten finished searches replace it with their own median.
    "search": [("start", "Getting started", 60), ("scrape", "Searching job sites, the long part", 1800),
               ("seen", "Setting aside ones already seen", 60),
               ("read", "Reading postings", 180), ("score", "Scoring", 120),
               ("shortlist", "Shortlist ready", 30)],
    "draft": [("start", "Getting started", 60), ("research", "Employer research", 120),
              ("write", "Writing", 120), ("audit", "Checking every fact", 120),
              ("render", "Making the PDFs", 60), ("verify", "Final checks", 60)],
    "resume_for_contact": [("start", "Getting started", 60), ("write", "Writing", 120),
                           ("audit", "Checking every fact", 120),
                           ("render", "Making the PDF", 45), ("verify", "Final checks", 45)],
    "prep": [("start", "Getting started", 60), ("research", "Research", 120),
             ("build", "Building the pack", 120), ("questions", "Likely questions", 60)],
    "network": [("start", "Getting started", 60), ("find", "Finding people", 900),
                ("read", "Reading profiles", 150), ("write", "Writing notes", 180),
                ("check", "Checking", 120)],
    "reply": [("start", "Getting started", 30), ("read", "Reading the thread", 30),
              ("write", "Writing the reply", 60), ("check", "Checking", 60)],
    "follow_up": [("start", "Getting started", 30), ("write", "Writing the follow-up", 45),
                  ("check", "Checking", 45)],
    "brief": [("start", "Getting started", 60), ("owed", "What is owed", 60),
              ("news", "News that matters", 180), ("write", "Writing the brief", 60)],
    "research": [("start", "Getting started", 30), ("find", "Reading their own pages", 120),
                 ("quote", "Quoting what was found", 60), ("save", "Saving it", 30)],
    "update": [("start", "Getting started", 30), ("take", "Taking the update", 60),
               ("apply", "Setting up what is new", 120), ("check", "Checking", 120)],
    "talk": [("read", "Reading", 30), ("answer", "Answering", 60)],
    "files": [("find", "Finding the files", 30), ("upload", "Putting them on your page", 60)],
    "tweak": [("start", "Getting started", 15), ("write", "Changing it", 45),
              ("check", "Checking every fact", 30), ("render", "Making the PDF", 30)],
    # One posting the person pasted or linked: scored first, as /apply Step 1 does
    # (stage_picks.py single, then the gates and fit), and put at the top of their jobs.
    "evaluate": [("read", "Reading the posting", 45), ("score", "Scoring it", 60),
                 ("save", "Adding it to your jobs", 15)],
    # The resume for when nobody named a role (stage_picks.py general): no drafting call.
    "general_resume": [("start", "Getting started", 15), ("render", "Making the PDF", 60),
                       ("verify", "Final checks", 45)],
    # A look over their own LinkedIn profile (tools/network/own_profile.py check).
    "own_profile": [("read", "Reading your profile", 60), ("check", "Checking it", 60),
                    ("write", "Writing what to fix", 45)],
    # A change to what their profile holds, asked on the page (Settings, Your profile): made
    # in 01-candidate-profile.md first, then the files the resume is built from.
    "profile": [("read", "Reading your profile", 20), ("change", "Making the change", 60),
                ("check", "Checking your resume still fits", 45)],
    # The page's own code changed: the listener alone builds it and publishes it
    # (tools/app_listen.py; `already` closes it with nothing published).
    "republish": [("build", "Building the new page", 20), ("publish", "Putting it up", 20)],
    # An application form's own questions, pasted on its card ("Why us?", "An example of
    # when you used X"): answered from the profile and the posting and kept with the
    # application (tools/form_answers.py); never the resume or the letter.
    "form_answers": [("read", "Reading the questions", 20), ("write", "Writing your answers", 60),
                     ("check", "Checking every fact", 30), ("save", "Saving them with the application", 15)],
}
# Where each kind runs by default, where it can run, and whether it is a heavy job (a whole
# session of its own) that counts against the cap.
WORK_KINDS = {
    "search": {"to": "cloud", "can": ("cloud", "computer"), "heavy": True},
    "draft": {"to": "cloud", "can": ("cloud", "computer"), "heavy": True},
    "resume_for_contact": {"to": "cloud", "can": ("cloud", "computer"), "heavy": True},
    "prep": {"to": "cloud", "can": ("cloud", "computer"), "heavy": True},
    "network": {"to": "cloud", "can": ("cloud", "computer"), "heavy": True},
    "reply": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "follow_up": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "brief": {"to": "cloud", "can": ("cloud",), "heavy": False},
    "research": {"to": "cloud", "can": ("cloud", "computer"), "heavy": False},
    "update": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "talk": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "files": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "tweak": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "evaluate": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "general_resume": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "own_profile": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "republish": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "profile": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
    "form_answers": {"to": "either", "can": ("cloud", "computer"), "heavy": False},
}
assert set(STAGES) == set(WORK_KINDS)
# Three big jobs at once on one computer (a search, a networking run and an interview prep, the
# maintainer's own example, 2026-10-29), and an urgent one more. The work and its cost are the
# same run side by side or one after another; the cap only keeps one computer's disk and memory
# clear (a search round's stage files, a batch's LaTeX compiles). In the cloud each big job runs
# in a chat of its own, on a computer of its own, so ten run at once: three at a time held a
# fourth and fifth application back while the first three were still starting (the maintainer,
# 2026-11-03: "i could generate 5, 10, 20 cvs and cover letters in one go").
HEAVY_CAP = 3
HEAVY_CAP_CHATS = 10
ACTIVE = ("claimed", "running")
# A job whose chat stopped is started again by itself this many times in all (the first try
# included); after that it waits for the person's "Ask Claude again".
AUTO_TRIES = 2
FINISHED = ("done", "failed", "stopped")
# A claim not moved on in this long is not believed: a lock it holds is free again.
LEASE_S = 30 * 60


def work_times(db: dict, now: dt.datetime, days: int = 30, least: int = 3) -> dict:
    """{kind: seconds} for each kind of work this copy has finished at least `least` times in
    the last `days`: the median of finished_at minus claimed_at, one item at a time (a batch
    of drafts is that many items). The page's gauge says it, falling back to the kind's
    default stages where there is no history (templates/app/DESIGN.md, the gauge): "about 3
    minutes" for work that takes this person's Claude twelve said nothing true (the
    maintainer, 2026-11-05)."""
    import app_model
    now = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    by: dict = {}
    for doc in (db.get("work") or {}).values():
        w = doc.get("data") if isinstance(doc, dict) and "data" in doc else doc
        if not isinstance(w, dict) or str(w.get("status") or "") != "done":
            continue
        start = app_model.parse_time(w.get("claimed_at"))
        end = app_model.parse_time(w.get("finished_at"))
        if not start or not end or (now - end).days > days:
            continue
        took = (end - start).total_seconds()
        if 5 <= took <= 4 * 3600 and str(w.get("kind") or "") in STAGES:
            # A note rewritten on a profile read is `network` work, but one note, not a run:
            # counted apart, so neither's minutes are the other's (REWRITE_STAGES).
            rewrite = w["kind"] == "network" and isinstance(w.get("args"), dict) \
                and w["args"].get("rewrite")
            by.setdefault(REWRITE_KIND if rewrite else str(w["kind"]), []).append(took)
    out = {}
    for kind, xs in sorted(by.items()):
        if len(xs) >= least:
            xs.sort()
            mid = len(xs) // 2
            out[kind] = int(round(xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2))
    return out


# A note rewritten on a profile just read or pasted (app_actions._queue_rewrite: `network` work
# with args.rewrite): one note written and checked, never a run's finding and reading. The
# "Paste their profile" gauge says this, or this copy's own rewrites' time once it has three
# (work_times, under REWRITE_KIND), never a whole networking run's: it said "a lot of your
# allowance" (the maintainer, 2026-11-07).
REWRITE_KIND = "rewrite"
REWRITE_STAGES = [("start", "Getting started", 30), ("write", "Rewriting the note", 60),
                  ("check", "Checking", 45)]


def rewrite_seconds(work_time: dict | None = None) -> int:
    """How long one note's rewrite takes this copy's Claude: its own median, else the default."""
    got = (work_time or {}).get(REWRITE_KIND)
    if isinstance(got, (int, float)) and not isinstance(got, bool) and got > 0:
        return int(got)
    return sum(s for _, _, s in REWRITE_STAGES)


def progress(kind: str) -> dict:
    """The default stages of a kind of work, with their usual seconds."""
    if kind not in STAGES:
        raise KeyError(f"no kind of work {kind!r}; one of {', '.join(sorted(STAGES))}")
    stages = [{"key": k, "name": n, "est_s": s} for k, n, s in STAGES[kind]]
    return {"kind": kind, "stages": stages, "total_s": sum(s["est_s"] for s in stages)}


# A search asked to draft what it finds (args.draft: the page's Find jobs, "Draft every one as
# it is found") is one job: the search, then a draft of each job that passes every rule, each
# claimed with it as it is found (search_drafts), so the drafting workflow writes them together
# in the search's own chat while it goes on, and its card counts them, "2 of 5 drafted". "Find
# N jobs and draft them all" took two searches and 13 chats run by hand (the maintainer,
# 2026-11-05). Its stages end with this one; DRAFT_ALL_MAX is the most it drafts in one go.
SEARCH_DRAFT_STAGE = ("draft", "Drafting each one", 900)
DRAFT_ALL_MAX = 25
DRAFTED = "drafted"


def drafts_all(item: dict) -> bool:
    """Whether this work is a search that drafts every job it finds."""
    args = item.get("args") if isinstance(item.get("args"), dict) else {}
    return str(item.get("kind") or "") == "search" and args.get("draft") is True


def draft_total(item: dict) -> int:
    """How many a search that drafts what it finds drafts: the number asked for (every one
    that fits, 0, is DRAFT_ALL_MAX), never more than DRAFT_ALL_MAX."""
    args = item.get("args") if isinstance(item.get("args"), dict) else {}
    try:
        n = int(args.get("size") or 10)
    except (TypeError, ValueError):
        n = 10
    return DRAFT_ALL_MAX if n <= 0 else min(n, DRAFT_ALL_MAX)


def item_stages(item: dict) -> list[dict]:
    """A work item's stages, its kind's own, and a search's that drafts what it finds ending
    with drafting each one."""
    stages = progress(str(item.get("kind") or ""))["stages"]
    if drafts_all(item):
        k, n, s = SEARCH_DRAFT_STAGE
        stages = stages + [{"key": k, "name": n, "est_s": s}]
    return stages


def can_take(item: dict, chat_kind: str) -> bool:
    """Whether a chat of this kind can do a work item. One chat answers the page
    (tools/app_listen.py), so work never waits for a chat of the other kind: the item's `to`
    is only where the page expected it to run. A brief alone needs the cloud, since it comes
    with the computer off; work sent to the computer (`to: computer`, a LinkedIn read) needs a
    chat with the computer's browser (computer_only)."""
    kind = WORK_KINDS.get(str(item.get("kind") or ""))
    return kind is not None and chat_kind in kind["can"] and not computer_only(item, chat_kind)


# Work that needs the person's own computer: a LinkedIn read, in the Browser pane of the
# Claude desktop app there. A cloud chat claimed such a run and closed it with "Can't read
# LinkedIn from here" (2026-11-09), so the engine refuses it to any chat but a computer one:
# a chat on the computer, or a cloud chat lent the computer's browser, which says so with
# `--kind computer` (tools/computer.py route). What such a chat is told instead is here.
COMPUTER_ONLY_REFUSAL = ("this needs the person's computer (a LinkedIn read): a cloud chat never "
                      "claims, finishes or fails it. Start it there instead: python3 "
                      "tools/computer.py route")
# The kinds whose `to: computer` means a LinkedIn read (a networking run, its reads and
# rewrites), and the flag any other item sets when it needs one (`args.read_on_computer`).
# Elsewhere `to: computer` is only where the page expected it to run (its listener was on
# the computer), and any chat may still take it: 4.3 stranded work that way.
READS_ON_COMPUTER = ("network",)


def claimed_kind(item: dict, chat_kind: str, chat: str = "") -> str:
    """The kind of chat writing to `item`: the kind its claim was made as (`claimed_as`) when
    `chat` is the one that claimed it, else `chat_kind`. A cloud chat lent the computer's
    browser claims as a computer chat, and the finish it runs is its claim's."""
    if chat and str(item.get("claimed_by") or "") == str(chat) \
            and str(item.get("claimed_as") or "") == "computer":
        return "computer"
    return chat_kind


def computer_only(item: dict, chat_kind: str) -> str:
    """Why a chat of `chat_kind` may not claim, finish or fail `item`, or "": it is sent to the
    computer for a LinkedIn read and this chat is not one. Their own Stop is the one way a
    cloud chat ends it."""
    if str(item.get("to") or "") != "computer" or chat_kind == "computer":
        return ""
    args = item.get("args") if isinstance(item.get("args"), dict) else {}
    if str(item.get("kind") or "") in READS_ON_COMPUTER or args.get("read_on_computer"):
        return COMPUTER_ONLY_REFUSAL
    return ""


def _key(text) -> str:
    try:
        from company_key import key
        k = key(text)
    except Exception:  # noqa: BLE001
        k = str(text or "").lower()
    return safe_id(k.replace(" ", "_"))


def locks_for(item: dict) -> list[str]:
    """The locks a work item holds while it runs (WORKFLOWS.md section 2): one job that
    writes resumes or letters per employer, one search, one networking run per employer,
    one job per contact, one update. A tweak takes its employer's lock (or its contact's,
    for a message), so it and a draft there never run at once."""
    kind = str(item.get("kind") or "")
    args = item.get("args") or {}
    target = args.get("target") if isinstance(args.get("target"), dict) else {}
    company = args.get("company") or args.get("employer") or target.get("company") or ""
    contact = args.get("contact_id") or args.get("contact") or target.get("contact") or ""
    out = []
    if kind in ("draft", "resume_for_contact", "tweak") and company:
        out.append(f"emp~{_key(company)}")
    if kind == "search":
        out.append("search")
    if kind == "network":
        out.append(f"net~{_key(company)}" if company else "network")
    if kind in ("reply", "follow_up", "resume_for_contact", "tweak", "prep") and contact:
        out.append(f"contact~{safe_id(contact)}")
    if kind == "update":
        out.append("update")
    return out


def _time(value) -> dt.datetime | None:
    import app_model
    return app_model.parse_time(value)


def _live_claim(item: dict, now: dt.datetime, work: dict | None = None) -> bool:
    """Is this item held by a chat right now: claimed or running, and moved on lately? An
    item claimed `with` another (a draft batch is one job) is held while its leader is: the
    job pins the leader, and the other postings of the batch were taken again by a second
    job half an hour in, while the first still wrote them (engine audit, 2026-11-03)."""
    if str(item.get("status") or "") not in ACTIVE:
        return False
    lead = str(item.get("with") or "") if work is not None else ""
    if lead and lead in work:
        led = work[lead]["data"]
        if str(led.get("claimed_by") or "") == str(item.get("claimed_by") or "") and \
                _live_claim(led, now):
            return True
    until = _time(item.get("lease_until"))
    if until is not None:
        return until > now
    last = max([t for t in (_time(item.get("stage_at")), _time(item.get("claimed_at"))) if t],
               default=None)
    return last is None or (now - last).total_seconds() < LEASE_S


def held_locks(db: dict, now: dt.datetime) -> dict:
    """{lock id: work id} for every lock some live job holds, from the locks collection and
    from the running items themselves (a lock document may not have been written yet)."""
    held = {}
    work = db.get("work") or {}
    for wid, doc in work.items():
        if _live_claim(doc["data"], now, work):
            for lock in locks_for(doc["data"]):
                held[lock] = wid
    for lid, doc in (db.get("locks") or {}).items():
        d = doc["data"]
        owner = str(d.get("work") or "")
        until = _time(d.get("until"))
        item = (work.get(owner) or {}).get("data")
        if item is None or not _live_claim(item, now, work):
            # Its job finished, stalled or is gone: the lock is free. A finished job is not
            # in a read of the queue, so its lock held the next draft for that employer for
            # half an hour, with nothing to wake the queue after (engine audit, 2026-11-03).
            continue
        if until is not None and until <= now:
            continue
        held.setdefault(lid, owner)
    return held


def next_item(db: dict, chat_kind: str, now: dt.datetime,
              cap: int = HEAVY_CAP, heavy_only: bool = False,
              to_only: str = "") -> dict | None:
    """The queued work item this chat should claim, or None.

    A kind of work it can do (can_take), the most urgent first and then the oldest asked, never past the heavy-job cap (urgent
    may take one more), and never one whose locks another live job holds. `to_only`
    ("computer"): only work sent there, for the chat the app started on the computer for it."""
    work = db.get("work") or {}
    held = held_locks(db, now)
    # A batch is one job: its other postings (`with` its leader) take no place of their own,
    # or one batch of three filled the cap (engine audit, 2026-11-03).
    heavy = sum(1 for d in work.values() if _live_claim(d["data"], now, work)
                and not d["data"].get("with")
                and WORK_KINDS.get(str(d["data"].get("kind") or ""), {}).get("heavy"))
    queued = []
    for wid, doc in work.items():
        item = doc["data"]
        kind = WORK_KINDS.get(str(item.get("kind") or ""))
        if kind is None or item.get("stop_asked") or (heavy_only and not kind.get("heavy")):
            continue
        # A job whose chat stopped (its claim not moved on for LEASE_S) is started again,
        # once, by the next chat to look: it sat "running" for good, and work for the same
        # employer could only wait (2026-11-01). A second stop is left for the person's
        # "Ask Claude again".
        # Never one a chat began for the person in that chat (`in_chat`): they are there, and
        # a second run elsewhere would do it twice; it is ended instead (stranded).
        again = (str(item.get("status") or "") in ACTIVE and not _live_claim(item, now, work)
                 and int(item.get("attempt") or 1) < AUTO_TRIES and not item.get("in_chat"))
        if str(item.get("status") or "") != "queued" and not again:
            continue
        if not can_take(item, chat_kind) or (to_only == "computer" and not computer_only(item, "cloud")):
            continue
        queued.append((-int(item.get("priority") or 0), str(item.get("asked_at") or ""), wid))
    # An update that changes how a record file is stored (args.migration) never interrupts
    # running work: it starts once nothing else is running, and work asked for meanwhile
    # waits until it has landed ("Starts after the update"). A code-only update holds
    # nothing but its own lock.
    migrating = after_update(db)
    others_live = any(_live_claim(d["data"], now, work) for d in work.values()
                      if not _is_migration(d["data"]))
    for _, _, wid in sorted(queued):
        item = work[wid]["data"]
        kind = WORK_KINDS[item["kind"]]
        if migrating and (not _is_migration(item) or others_live):
            continue
        urgent = int(item.get("priority") or 0) >= 2
        if kind["heavy"] and heavy >= cap + (1 if urgent else 0):
            continue
        busy = [lk for lk in locks_for(item) if lk in held and held[lk] != wid]
        if busy:
            continue
        got = {"work": wid, "version": work[wid]["version"], "kind": item["kind"],
               "title": item.get("title") or "", "locks": locks_for(item),
               "stages": item_stages(item)}
        if drafts_all(item):
            got["draft_all"] = draft_total(item)
        if str(item.get("status") or "") in ACTIVE:
            got["again"] = int(item.get("attempt") or 1) + 1
        if item["kind"] == "tweak":
            # Several tweaks queued on one output run as one job: one wake, one render, one
            # audit (TWEAKS.md 5.1). The others are claimed with it and applied together.
            target = str(((item.get("args") or {}).get("target") or {}).get("id") or "")
            same = sorted((str(d["data"].get("asked_at") or ""), w) for w, d in work.items()
                          if w != wid and d["data"].get("kind") == "tweak"
                          and str(d["data"].get("status") or "") == "queued"
                          and not d["data"].get("stop_asked")
                          and str(((d["data"].get("args") or {}).get("target") or {}).get("id")
                                  or "") == target and target)
            got["with"] = [{"work": w, "version": work[w]["version"]} for _, w in same]
        elif item["kind"] == "follow_up":
            # Follow-ups queued together are one job, as drafts are: "Draft all" for nine
            # queued nine items, each claimed in its own batch (every claim writes the chat's
            # heartbeat) and drafted one at a time by hand, and the maintainer saw it "burning
            # tokens" (2026-11-05). Claimed `with` this one, `app.py follow-ups` drafts them all
            # in one run, in code, and finishes them in one batch.
            mine = set(got["locks"])
            same = []
            for _at, w in sorted((str(d["data"].get("asked_at") or ""), w) for w, d in work.items()
                                 if w != wid and d["data"].get("kind") == "follow_up"
                                 and str(d["data"].get("status") or "") == "queued"
                                 and not d["data"].get("stop_asked")
                                 and can_take(d["data"], chat_kind)):
                theirs = locks_for(work[w]["data"])
                if any(lk in held and held[lk] != w for lk in theirs) or mine & set(theirs):
                    continue
                same.append(w)
                mine |= set(theirs)
                if len(same) >= FOLLOW_UP_BATCH - 1:
                    break
            got["with"] = [{"work": w, "version": work[w]["version"]} for w in same]
            got["locks"] = sorted(mine)
        elif item["kind"] == "draft":
            # Drafts queued together are one job: the drafting workflow takes a batch in one
            # run, so ten resumes asked for at once take one chat, never ten, and never wait
            # behind the cap one by one (the maintainer, 2026-10-30). Each still has its card.
            mine = set(got["locks"])
            same = []
            for _at, w in sorted((str(d["data"].get("asked_at") or ""), w) for w, d in work.items()
                                if w != wid and d["data"].get("kind") == "draft"
                                and str(d["data"].get("status") or "") == "queued"
                                and not d["data"].get("stop_asked")):
                theirs = locks_for(work[w]["data"])
                if any(lk in held and held[lk] != w for lk in theirs) or mine & set(theirs):
                    continue
                same.append(w)
                mine |= set(theirs)
                if len(same) >= DRAFT_BATCH - 1:
                    break
            got["with"] = [{"work": w, "version": work[w]["version"]} for w in same]
            got["locks"] = sorted(mine)
        return got
    return None


# A job whose chat stopped twice is never started a third time by itself: it is failed, in
# code, at the check-in, so its card offers Try again and the queue and the page's one-at-a-time
# kinds move on. It sat "running" for good before, refusing every new search and holding the
# helper's renewal (engine audit, 2026-11-03). One they asked to stop is stopped.
STRANDED_SAID = "It stopped part way twice. Tap Try again to start it once more."
# Work a chat began for the person in that chat, gone quiet: never started again elsewhere,
# ended after a lease and as long again with no word, so a long step it forgot to pin keeps it.
CHAT_STRANDED_SAID = "It stopped before it finished. Tap Try again to start it once more."


def _chat_quiet(item: dict, now: dt.datetime) -> bool:
    """Has work a chat runs itself had no word for a lease past its lease?"""
    until = _time(item.get("lease_until")) or _time(item.get("stage_at")) or \
        _time(item.get("claimed_at"))
    return until is not None and (now - until).total_seconds() >= LEASE_S


def stranded(db: dict, now: dt.datetime) -> list[str]:
    """Ids of claimed or running items no chat holds any more, that `next_item` will not start
    again: tried AUTO_TRIES times, asked to stop, or begun in a chat that has gone quiet."""
    work = db.get("work") or {}
    out = []
    for wid, d in work.items():
        item = d["data"]
        if str(item.get("status") or "") not in ACTIVE or d.get("version") is None \
                or _live_claim(item, now, work):
            continue
        if item.get("in_chat") and not item.get("stop_asked"):
            if _chat_quiet(item, now):
                out.append(wid)
            continue
        if item.get("stop_asked") or int(item.get("attempt") or 1) >= AUTO_TRIES:
            out.append(wid)
    return sorted(out)


def fail_stranded(db: dict, now: dt.datetime, out_dir: str) -> dict:
    """The batch that ends every stranded item (failed with a plain reason, or stopped), its
    locks deleted. {"ended": [ids], "batches": [...]}."""
    import app_model
    ids = stranded(db, now)
    if not ids:
        return {"ended": [], "batches": []}
    w = Writes(out_dir)
    at = app_model.stamp(now)
    work = db.get("work") or {}
    for wid in ids:
        stop = bool(work[wid]["data"].get("stop_asked"))
        said = STOPPED_SAID if stop else CHAT_STRANDED_SAID if work[wid]["data"].get("in_chat") \
            else STRANDED_SAID
        w.add("update", "work", wid, {
            "status": "stopped" if stop else "failed", "finished_at": at, "lease_until": None,
            "error": None if stop else said, "result": {"summary": said, "links": []}},
            if_version=work[wid]["version"])
    for lid, lock in sorted((db.get("locks") or {}).items()):
        if str((lock.get("data") or {}).get("work") or "") in ids and not lock.get("old"):
            w.add("delete", "locks", lid, if_version=lock["version"])
    return {"ended": ids, "batches": w.save("stranded")}


# Work whose chat finished it but could not save it before it closed (its save timed out, and
# asked once more it had nothing to save: tidy.py close and plan). Its card said done over a
# result nobody could see (the "Finding jobs" chat, 2026-11-06).
LOST_SAID = ("It finished, but its results could not be saved, so they are lost. Tap Try "
             "again to do it once more.")


def lose(db: dict, ids, now: dt.datetime, out_dir: str) -> list[str]:
    """The batch that says, on each finished item's own card, that its results were lost:
    failed with LOST_SAID, so the card offers Try again. Only items still done, each pinned
    to the version read; [] where there is none."""
    import app_model
    w = Writes(out_dir)
    work = db.get("work") or {}
    for wid in dict.fromkeys(ids):
        doc = work.get(wid) or {}
        if str((doc.get("data") or {}).get("status") or "") != "done" \
                or doc.get("version") is None:
            continue
        w.add("update", "work", wid, {
            "status": "failed", "error": LOST_SAID, "lost_at": app_model.stamp(now),
            "result": {"summary": LOST_SAID, "links": []}}, if_version=doc["version"])
    return w.save("lost") if w.entries else []


def _is_migration(item: dict) -> bool:
    return item.get("kind") == "update" and bool((item.get("args") or {}).get("migration"))


def after_update(db: dict) -> bool:
    """Is a state migration queued or running, so new work starts after it?"""
    return any(_is_migration(d["data"]) and str(d["data"].get("status") or "")
               in ("queued",) + ACTIVE for d in (db.get("work") or {}).values())


def heartbeat(chat_id: str, chat_kind: str, now: dt.datetime, busy: str | None = None,
              title: str = "", watching: bool = True) -> dict:
    """A chat's heartbeat. `watching` False: a chat that is at work but neither answers the
    page nor sits on the computer (a job's own chat, or a cloud chat lent the computer's
    browser or folder), which the page and `computer.route` never count as a chat listening."""
    import app_model
    can = sorted(k for k, v in WORK_KINDS.items() if chat_kind in v["can"])
    return {"kind": chat_kind, "title": title or f"Job search ({chat_kind})", "can": can,
            "seen_at": app_model.stamp(now), "busy": busy,
            **({} if watching else {"watching": False})}


def claim(db: dict, chosen: dict, chat_id: str, chat_kind: str, now: dt.datetime,
          out_dir: str, running: bool = False, watching: bool = True) -> list[str]:
    """The claim for `chosen` (next_item's answer) as batch files: the item pinned to the
    version read, each lock created (a lock left by a finished job is replaced, pinned to
    its version), and the chat's heartbeat. A refused batch means another chat has it.
    `running`: small work this chat does at once (`run: here`), so the claim itself marks it
    running at its first stage, and no progress pin follows: each pin was a step of a chat
    that re-reads its whole history, for work done in a minute (2026-11-03)."""
    import app_model
    work = db.get("work") or {}
    for wid in [chosen["work"]] + [o["work"] for o in chosen.get("with") or []]:
        refused = computer_only((work.get(safe_id(wid)) or {}).get("data") or {}, chat_kind)
        if refused:
            raise ValueError(f"not claimed: {refused}")
    w = Writes(out_dir)
    at = app_model.stamp(now)
    until = app_model.stamp(now + dt.timedelta(seconds=LEASE_S))
    status = "running" if running else "claimed"

    def fresh(wid: str) -> dict:
        """What a claim clears on an item taken from the queue. A question answered on the
        page put the item back with the last try's batch (`with` a finished job), stage,
        steps and a waiting line, and it was then counted as part of a job that had ended
        (engine audit, 2026-11-03)."""
        item = (work.get(wid) or {}).get("data") or {}
        out: dict = {"stage": 0, "stage_at": at if running else None}
        for k in ("with", "stage_line", "note", "error", "in_chat"):
            if item.get(k) not in (None, "", [], {}):
                out[k] = {"__delete__": True}
        if item.get("answered_at"):
            out["steps"] = [{"at": at, "text": "Carrying on with your answer."}]
        return out

    # The kind it was claimed as, kept on the item: a cloud chat lent the computer's browser
    # claims as a computer chat, and its finish, run without `--kind computer`, was refused as
    # a cloud chat's (the release review, 2026-11-09). `finish` believes it for the claimer.
    fields = {"status": status, "claimed_by": chat_id, "claimed_at": at, "lease_until": until,
              "claimed_as": chat_kind, **fresh(chosen["work"])}
    named = str((chosen.get("create_session") or {}).get("title") or "")
    if named:
        # The name of the chat started for it, so the next one started beside it is never
        # given the same name (app.where_it_runs).
        fields["chat_title"] = named
    if chosen.get("again"):
        # Started again after its chat stopped: from the top, with the stop said on its card.
        fields.update(attempt=chosen["again"], stage=0, stage_at=at if running else None,
                      steps=[{"at": at, "text": "Started again: the last try stopped part way. "
                                                "Anything it saved is kept."}])
    w.add("update", "work", chosen["work"], fields, if_version=chosen.get("version"))
    for other in chosen.get("with") or []:
        w.add("update", "work", other["work"],
              dict(fresh(other["work"]), status=status, claimed_by=chat_id, claimed_at=at,
                   lease_until=until, claimed_as=chat_kind, **{"with": chosen["work"]}),
              if_version=other.get("version"))
    # Each lock names the item that needs it, so finishing one posting of a batch (or
    # stopping it for a question) frees its own employer and nothing else.
    owner = {}
    for wid in [o["work"] for o in chosen.get("with") or []] + [chosen["work"]]:
        for lock in locks_for((work.get(wid) or {}).get("data") or {}):
            owner[lock] = wid
    for lock in chosen.get("locks") or []:
        old = (db.get("locks") or {}).get(safe_id(lock))
        w.add("set", "locks", lock, {"work": owner.get(lock, chosen["work"]), "chat": chat_id,
                                     "since": at, "until": until},
              if_version=old["version"] if old else None)
    chats = db.get("chats") or {}
    mine = chats.get(safe_id(chat_id))
    # `busy` is the line the page shows for work asked in the chat (busy_beat), never a work
    # id: the page shows the work itself. A line already there is kept.
    line = plain_busy(((mine or {}).get("data") or {}).get("busy"), db)
    # A chat that only does this work (`watching` False) says so on its heartbeat: written as
    # a computer chat's, a cloud chat lent the computer's browser made the page and
    # computer.route believe a chat on the computer listened for twenty minutes (the release
    # review, 2026-11-09).
    w.add("set", "chats", chat_id, heartbeat(chat_id, chat_kind, now, busy=line,
                                             watching=watching),
          if_version=mine["version"] if mine else None)
    return w.save("claim")


# ------------------------------------------------------------------ progress as it goes

# scrape_wide.Tally.line(), as run_round.py copies it into round.log: "progress: <job site>
# <sent>/<total> sent, <failures>[, ...][, stopped: <why> | , done | , <k> min left]".
_PROGRESS = re.compile(r"progress: (?P<name>.+?) (?P<sent>\d+)/(?P<total>\d+) sent(?P<rest>.*)$")
_FINISHED = re.compile(r", (?:done|stopped: .*)$")
_LEFT = re.compile(r", (\d+) min left$")
# The step run_round.py is on, from the "+ <python> tools/<name>.py ..." line it prints before
# each, as the search stage that step is part of: once the job sites are done, a round goes on
# setting aside, reading and scoring under the stage the chat last pinned, which is not them.
_STEP = re.compile(r"^\+ .*?tools[\\/](?P<tool>\w+)\.py\b")
_STEP_STAGE = {"scrape_wide": "scrape", "prefilter": "seen", "hydrate": "read", "text_screen": "read",
               "opportunity": "score", "fit": "score", "throttle": "score"}


def round_progress(text: str) -> dict | None:
    """How far a search's job sites have got, from run_round.py's round.log: {done, total,
    left_s, sending, stage}. Each job site's last line counts; one that is done or stopped
    counts as complete, and the time left is the longest that any site still sending says (a
    minute at least while one is), or None once none is: "0 left" read as the stage's own
    estimate called every normal round "taking longer than usual" while it read and scored
    (the release review, 2026-10-30). `stage` is the step the round is on (`_STEP_STAGE`), or
    None before the first. None before a job site's first line, unless the round is past them."""
    last: dict = {}
    stage = None
    for raw in str(text or "").splitlines():
        m = _PROGRESS.search(raw.strip())
        if m:
            last[m.group("name")] = m
        step = _STEP.search(raw.strip())
        if step and step.group("tool") in _STEP_STAGE:
            stage = _STEP_STAGE[step.group("tool")]
    if not last and stage in (None, "scrape"):
        return None
    done = total = sending = 0
    left = None
    for m in last.values():
        sent, of, rest = int(m.group("sent")), int(m.group("total")), m.group("rest")
        total += of
        if _FINISHED.search(rest):
            done += of
            continue
        done += min(sent, of)
        sending += 1
        k = _LEFT.search(rest)
        if k:
            left = max(left or 0, int(k.group(1)) * 60, 60)
    return {"done": done, "total": total, "left_s": left if sending and stage in (None, "scrape") else None,
            "sending": sending, "stage": stage}


def stage_index(kind: str, stage, given: list | None = None) -> int:
    """A stage named by its key (`app.py progress <kind>`) or its number, as a number."""
    keys = [k for k, _, _ in STAGES.get(kind, [])] + (
        [SEARCH_DRAFT_STAGE[0]] if kind == "search" else [])
    n = len(given) if given else len(keys) - (1 if kind == "search" else 0)
    text = str(stage).strip()
    if text.isdigit():
        at = int(text)
    elif text in keys:
        at = keys.index(text)
    else:
        raise KeyError(f"no stage {text!r} in {kind or 'this work'}; one of {', '.join(keys)}")
    return max(0, min(at, max(n, 1) - 1))


def _keep_dump(dump_dir: str, collection: str, doc_id: str, fields: dict, version: int) -> None:
    """The dump as it will be once this write lands, so the next pin from it is pinned to
    the right version without reading the page again. A refused write means read again."""
    where = os.path.join(dump_dir, STORE.get(collection, collection))
    if not os.path.isdir(where) and os.path.isdir(os.path.join(dump_dir, collection)):
        where = os.path.join(dump_dir, collection)
    os.makedirs(where, exist_ok=True)
    plain = os.path.join(where, safe_id(doc_id) + ".json")
    path = os.path.join(where, safe_id(doc_id).replace("~", "@") + ".json")
    _keep_read_stamp(dump_dir, os.path.basename(where), safe_id(doc_id), (path, plain))
    if plain != path and os.path.exists(plain):
        os.remove(plain)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dict(fields, **{VERSION_FIELD: version}), fh, ensure_ascii=False, indent=1)
        fh.write("\n")


READ_STAMPS = ".read-stamps.json"     # in a dump folder: each record's own stamp as read


def _keep_read_stamp(dump_dir: str, coll: str, doc_id: str, paths) -> None:
    """Before the folder's copy of a record is moved on (as it will be once a write lands),
    keep the stamp it carried as read, once: a refusal's version is kept beside that stamp
    (note_version), the one every new read of the record still shows."""
    key = f"{coll}/{doc_id}"
    side = os.path.join(dump_dir, READ_STAMPS)
    got = _read_json(side)
    got = got if isinstance(got, dict) else {}
    if key in got:
        return
    for p in paths:
        raw = _read_json(p) if os.path.isfile(p) else None
        if isinstance(raw, dict):
            _f, v, real = _version_of(raw)
            got[key] = None if real else v
            break
    else:
        got[key] = None                     # made by this folder's own writes: no stamp read
    try:
        with open(side, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(got, fh, indent=1, sort_keys=True)
    except OSError:
        pass


def _merged(old: dict, new: dict) -> dict:
    """An update's fields over the record's: a `{"__delete__": true}` takes a field away, at
    the top or inside a field that is itself a record."""
    out = dict(old)
    for k, v in new.items():
        if v == {"__delete__": True}:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict) and \
                "__delete__" in json.dumps(v):
            out[k] = _merged(out[k], v)
        else:
            out[k] = v
    return out


# In a dump folder: the batches keep_landed took as landed before they were sent, in order,
# each with the folder's copy of every record it moved on as it stood before (SENT_DIR). A
# refused batch never landed, nor did any sent after it: `note_version` puts those records
# back as they were, so the same command run again makes the save again. Taken as landed and
# never put back, a refused save was dropped in silence: the view run again found its own
# unsent screens already in the folder and wrote nothing (a person's copy, 2026-11-05).
SENT = ".sent.json"
SENT_DIR = ".sent"


def _sent(dump_dir: str) -> list:
    got = _read_json(os.path.join(dump_dir, SENT))
    return got if isinstance(got, list) else []


def _keep_sent(dump_dir: str, sent: list) -> None:
    try:
        with open(os.path.join(dump_dir, SENT), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(sent, fh, indent=1)
    except OSError:
        pass


def _before(dump_dir: str, n: int, coll: str, doc_id: str, names) -> None:
    """The folder's copy of one record as it stands before batch `n` moves it on, kept once
    for that batch: its file as it is, or a mark that there was none."""
    keep = os.path.join(dump_dir, SENT_DIR, str(n), coll, doc_id.replace("~", "@") + ".json")
    if os.path.exists(keep):
        return
    os.makedirs(os.path.dirname(keep), exist_ok=True)
    raw = next((_read_json(p) for p in names if os.path.isfile(p)), None)
    with open(keep, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"file": raw} if raw is not None else {"none": True}, fh, ensure_ascii=False)


def put_back(dump_dir: str, ref: str) -> list[str]:
    """A batch holding `ref` (`<stored collection>/<stored doc id>`) was refused: the folder's
    copy of every record that batch, and every batch sent after it, moved on is put back as it
    was, newest first, and those batches are no longer taken as landed. Returns the records
    put back; [] when no batch in this folder held `ref`."""
    sent = _sent(dump_dir)
    at = next((i for i in range(len(sent) - 1, -1, -1)
               if ref in (sent[i].get("records") or [])), None)
    if at is None:
        return []
    back: list[str] = []
    for got in reversed(sent[at:]):
        n = str(got.get("n"))
        for key in reversed(got.get("records") or []):
            coll, _, doc_id = key.partition("/")
            kept = _read_json(os.path.join(dump_dir, SENT_DIR, n, coll,
                                           doc_id.replace("~", "@") + ".json"))
            if not isinstance(kept, dict):
                continue
            where = os.path.join(dump_dir, coll)
            names = [os.path.join(where, doc_id.replace("~", "@") + ".json"),
                     os.path.join(where, doc_id + ".json")]
            for p in dict.fromkeys(names):
                if os.path.isfile(p):
                    os.remove(p)
            if not kept.get("none"):
                os.makedirs(where, exist_ok=True)
                with open(names[0], "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(kept.get("file"), fh, ensure_ascii=False, indent=1)
                    fh.write("\n")
            back.append(key)
        shutil.rmtree(os.path.join(dump_dir, SENT_DIR, n), ignore_errors=True)
    _keep_sent(dump_dir, sent[:at])
    return list(dict.fromkeys(back))


def keep_landed(dump_dir: str, batches, skip=()) -> None:
    """The dump as it will be once `batches` land, so the next command over the same folder
    pins to the versions they leave and sees what they made (a work item a tap queued, a
    claim already taken), with no second read. Collections in `skip` are left as read: a
    tap's claim takes the person's words off the page, and the dump keeps them for `apply`.
    A refused batch is put back by `note_version` (`put_back`), never left as landed."""
    sent = _sent(dump_dir)
    for path in batches or ():
        n = max([int(s.get("n") or 0) for s in sent] + [0]) + 1
        records: list[str] = []
        for e in _read_json(path) or []:
            coll, doc_id = str(e.get("collection") or ""), str(e.get("doc_id") or "")
            if not coll or not doc_id or coll in skip or _LOGICAL.get(coll, coll) in skip:
                continue
            where = os.path.join(dump_dir, coll)
            names = [os.path.join(where, doc_id.replace("~", "@") + ".json"),
                     os.path.join(where, doc_id + ".json")]
            try:
                _before(dump_dir, n, coll, doc_id, names)
                records.append(f"{coll}/{doc_id}")
            except OSError:
                pass
            if e.get("op") == "delete":
                for p in dict.fromkeys(names):
                    if os.path.isfile(p):
                        os.remove(p)
                continue
            body = _read_json(e.get("file_path") or "")
            if not isinstance(body, dict):
                continue
            version = body.pop(VERSION_FIELD, None)
            if not isinstance(version, int):
                version = int(e.get("if_version") or 0) + 1
            if e.get("op") == "update":
                old = next((unwrap(_read_json(p))[0] for p in names if os.path.isfile(p)), {})
                body = _merged(old, body)
            _keep_dump(dump_dir, coll, doc_id, body, version)
        if records:
            sent.append({"n": n, "batch": os.path.abspath(path), "records": records})
    if batches:
        _keep_sent(dump_dir, sent)


def note_version(dump_dir: str, ref: str, version: int) -> str:
    """The version a refused write named for one record (`<collection>/<doc id>`), kept in the
    dump, so the command run again pins to it. A record a writer left with a wrong `_v` was
    read back at that wrong version, every write to it refused, and the item stranded however
    often it was read again (engine audit, 2026-11-03): the store's refusal names the version
    it holds. Returns the record's id; KeyError when the dump does not hold it."""
    coll, _, doc_id = str(ref or "").strip().strip("/").rpartition("/")
    if not coll or not doc_id or int(version) < 1:
        raise KeyError("name it as <collection>/<doc id>, with the version the refusal gave")
    logical = _LOGICAL.get(coll, coll)
    if logical == "meta":
        doc_id = _LOGICAL_DOC.get(("meta", doc_id), doc_id)
    # The refused batch never landed, nor any sent after it: the folder's copy of what they
    # moved on is put back first, so the command run again makes the whole save again,
    # pinned to the store's number, rather than finding it already made and writing nothing.
    put_back(dump_dir, "/".join(stored(logical, safe_id(doc_id).replace("@", "~"))))
    db = load(dump_dir)
    doc = (db.get(logical) or {}).get(safe_id(doc_id).replace("@", "~"))
    if doc is None:
        raise KeyError(f"no {coll}/{doc_id} in {dump_dir}: read it again into this folder")
    store_coll, store_id = stored(logical, doc_id)
    # The stamp the record itself carries, as read: kept beside the store's number, so a new
    # read of the same record, still stamped wrong, is pinned right (KNOWN_VERSIONS).
    stamp = None
    side = _read_json(os.path.join(dump_dir, READ_STAMPS))
    if isinstance(side, dict) and f"{store_coll}/{store_id}" in side:
        # Moved on in this folder by a write not yet landed: the stamp as read.
        stamp = side[f"{store_coll}/{store_id}"]
    else:
        for name in (store_id.replace("~", "@"), store_id):
            raw = _read_json(os.path.join(dump_dir, store_coll, name + ".json"))
            if isinstance(raw, dict):
                _f, v, real = _version_of(raw)
                stamp = None if real else v
                break
    if stamp is not None and stamp != int(version):
        remember_version(f"{store_coll}/{store_id}", stamp, int(version))
    _keep_dump(dump_dir, store_coll, store_id, dict(doc["data"]), int(version))
    key = f"{store_coll}/{store_id}"
    _count_refusal(dump_dir, key)
    return key


def _count_refusal(dump_dir: str, key: str) -> None:
    tries = _read_json(os.path.join(dump_dir, REFUSED))
    tries = tries if isinstance(tries, dict) else {}
    tries[key] = int(tries.get(key) or 0) + 1
    try:
        with open(os.path.join(dump_dir, REFUSED), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(tries, fh, indent=1, sort_keys=True)
    except OSError:
        pass


def take_back(dump_dir: str, ref: str) -> str:
    """A refusal that named no version (the record exists, and the write carried none, as one
    the folder never read): the refused batch, and any sent after it, taken back as
    `note_version` takes it, so the same command makes the save again once the record is read
    into the folder. Returns the record's stored name."""
    key = stored_ref(ref)
    if "/" not in key or not key.rpartition("/")[0]:
        raise KeyError("name it as <collection>/<doc id>, as the refusal named it")
    put_back(dump_dir, key)
    _count_refusal(dump_dir, key)
    return key


def stored_ref(ref: str) -> str:
    """`<collection>/<doc id>` as the store names it, from either name of the record."""
    coll, _, doc_id = str(ref or "").strip().strip("/").rpartition("/")
    logical = _LOGICAL.get(coll, coll)
    if logical == "meta":
        doc_id = _LOGICAL_DOC.get(("meta", doc_id), doc_id)
    sc, sid = stored(logical, safe_id(doc_id).replace("@", "~"))
    return f"{sc}/{sid}"


def version_known(dump_dir: str, key: str) -> bool:
    """Is the folder's version of `key` (`<stored collection>/<doc id>`) the store's own: kept
    from the read's listing, or moved on from one by this folder's own writes (or made by
    them)? A record known only by its stamp may be wrong."""
    coll, _, doc_id = key.rpartition("/")
    side = _read_json(os.path.join(dump_dir, READ_STAMPS))
    if isinstance(side, dict) and key in side:
        return side[key] is None
    for name in (doc_id.replace("~", "@"), doc_id):
        raw = _read_json(os.path.join(dump_dir, coll, name + ".json"))
        if isinstance(raw, dict):
            return _version_of(raw)[2]
    return False


def read_again(dump_dir: str, ref: str, missing: bool = False) -> list[str]:
    """The collections to read again into the folder before a refused save is made again:
    those of every record the refused batch (and any sent after it) pins only by its stamp,
    so the save run again is pinned to the page's own numbers, never refused once for each
    (fifty refusals for one page update, a person's computer, 2026-11-09). `missing`: the
    refusal named no version (the record exists and the write carried none), so its own
    collection too. Call before `note_version`, which takes the batch back."""
    key = stored_ref(ref)
    sent = _sent(dump_dir)
    at = next((i for i in range(len(sent) - 1, -1, -1)
               if key in (sent[i].get("records") or [])), None)
    recs = [r for s in sent[at:] for r in s.get("records") or []] if at is not None else []
    colls = {r.rpartition("/")[0] for r in recs if r != key and not version_known(dump_dir, r)}
    if missing:
        colls.add(key.rpartition("/")[0])
    return sorted(colls)


# In a dump folder: how often the store refused a save of each record here (note_version).
REFUSED = ".refused.json"


def refusals(dump_dir: str, ref: str) -> int:
    """How often a save of `ref` (`<stored collection>/<stored doc id>`) was refused in this
    folder."""
    got = _read_json(os.path.join(dump_dir, REFUSED))
    return int(got.get(ref) or 0) if isinstance(got, dict) else 0


def not_its_claim(item: dict, chat: str) -> str:
    """Why a chat may not write to this item, or "": another chat claims it now. The pinned
    version is no guard, since a chat whose lease ran out reads the item afresh, re-claimed,
    and its write then lands on the other chat's claim (the release review, 2026-11-03)."""
    who = str(item.get("claimed_by") or "").strip()
    chat = str(chat or "").strip()
    if chat and who and who != chat:
        return ("another chat took this job on after this one went quiet, and it is that "
                f"chat's now ({who}): write nothing more to it, and stop")
    return ""


BLOCKED_LINE = "Waiting for you: Claude asked to go ahead with a step, in the Claude app."


def mark_blocked(db: dict, work_id: str, now: dt.datetime, out_dir: str) -> dict:
    """A job running in a chat of its own that stopped on a question to the person (its chat's
    status reads blocked, get_session): said on its card, in one line, with its lease kept, so
    it is never taken for stopped and ended while it waits on them (the stranger audit, X-7
    and X-8). Its own next pin clears it. {work, batches}."""
    import app_model
    doc = (db.get("work") or {}).get(safe_id(work_id))
    if doc is None:
        raise KeyError(f"no work {work_id!r} in the dump; read work again")
    item = dict(doc["data"])
    if str(item.get("status") or "") in ("done", "failed", "stopped"):
        raise KeyError(f"work {work_id!r} has finished; write nothing more to it")
    at = app_model.stamp(now)
    fields = {"blocked_at": at,
              "lease_until": app_model.stamp(now + dt.timedelta(seconds=LEASE_S))}
    steps = list(item.get("steps") or [])
    if not steps or steps[-1].get("text") != BLOCKED_LINE:
        fields["steps"] = (steps + [{"at": at, "text": BLOCKED_LINE}])[-50:]
    w = Writes(out_dir)
    w.add("update", "work", work_id, fields, if_version=doc["version"])
    return {"work": work_id, "batches": w.save("blocked")}


def pin(db: dict, work_id: str, now: dt.datetime, out_dir: str, stage=None, line: str = "",
        count: dict | None = None, left_s: int | None = None, dump_dir: str = "",
        chat: str = "") -> dict:
    """One pinned update of a running item: its stage (stage_at only when the stage moves
    on), one plain line in its steps, how many of how many are done, how long is left
    (`left_s`, as of `left_at`), and its lease, renewed, so long work is never taken for
    stopped. The page reads `left_s` as the stage's own estimate: a search that says
    "15 min left" is not shown as late at ten. {work, stage, count, left_s, batches}.
    `chat`: the id the job was claimed under; another chat's claim is a KeyError."""
    import app_model
    doc = (db.get("work") or {}).get(safe_id(work_id))
    if doc is None:
        raise KeyError(f"no work {work_id!r} in the dump; read work again")
    item = dict(doc["data"])
    if str(item.get("status") or "") in ("done", "failed", "stopped"):
        raise KeyError(f"work {work_id!r} has finished; write nothing more to it")
    taken = not_its_claim(item, chat)
    if taken:
        raise KeyError(taken)
    if item.get("stop_asked"):
        # They tapped Stop: no stage is pinned, the work is stopped (the app skill, step 4).
        return {"work": work_id, "stop_asked": True, "batches": []}
    at = app_model.stamp(now)
    fields: dict = {"status": "running",
                    "lease_until": app_model.stamp(now + dt.timedelta(seconds=LEASE_S))}
    if item.get("blocked_at"):
        fields["blocked_at"] = None          # it moved on: no longer waiting on the person
    if stage is not None:
        idx = stage_index(str(item.get("kind") or ""), stage, item.get("stages"))
        if idx != item.get("stage") or not item.get("stage_at") \
                or str(item.get("status") or "") != "running":
            # A new stage starts with its own count and its own estimate.
            fields.update(stage=idx, stage_at=at, count=None, left_s=None, left_at=None)
    if line:
        fields["steps"] = (list(item.get("steps") or []) + [{"at": at, "text": line}])[-50:]
    if count and int(count.get("total") or 0) > 0:
        fields["count"] = {"done": int(count.get("done") or 0), "total": int(count["total"]),
                           **({"word": str(count["word"])} if count.get("word") else {})}
    if left_s is not None:
        fields.update(left_s=max(0, int(left_s)), left_at=at)
    w = Writes(out_dir)
    w.add("update", "work", work_id, fields, if_version=doc["version"])
    # The other postings of a batch, renewed with it and shown at its stage: pinned alone, the
    # leader kept its lease while they read "may have stopped" half an hour in and were
    # handed to a second job (engine audit, 2026-11-03). One they asked to stop is named, for
    # the job to finish it stopped.
    stopped = []
    for mid, mdoc in sorted(members(db, work_id).items()):
        m = mdoc["data"]
        if m.get("stop_asked"):
            stopped.append(mid)
            continue
        mf = {"status": "running", "lease_until": fields["lease_until"]}
        # Moved with it only where they are the same kind of work: a search's drafts (one job
        # with it, search_drafts) keep their own stages, and its count is the search's alone.
        for k in ("stage", "stage_at", "count", "left_s", "left_at") \
                if m.get("kind") == item.get("kind") else ():
            if k in fields:
                mf[k] = fields[k]
        w.add("update", "work", mid, mf, if_version=mdoc["version"])
    batches = w.save("pin")
    if dump_dir:
        # The folder as it will be once the pin lands, kept the way every other batch is
        # (keep_landed), so a refused pin is put back whole by `app.py version`. Moved on
        # outside that record, a pin refused for one posting left the leader and the rest one
        # ahead of the page, and the pin run again was refused for them (the maintainer's
        # copy, 2026-11-06: if_version 3 with the page at 2).
        keep_landed(dump_dir, batches)
    return {"work": work_id, "stop_asked": False, "stage": fields.get("stage", item.get("stage")),
            "count": fields.get("count", item.get("count")),
            "left_s": fields.get("left_s", item.get("left_s")),
            **({"stopped": stopped} if stopped else {}), "batches": batches}


def members(db: dict, work_id: str) -> dict:
    """{id: doc} of the items claimed `with` this one (a draft batch's other postings, a
    tweak's others) that are still going, under the same chat's claim."""
    work = db.get("work") or {}
    lead = (work.get(safe_id(work_id)) or {}).get("data") or {}
    by = str(lead.get("claimed_by") or "")
    return {wid: d for wid, d in work.items()
            if str(d["data"].get("with") or "") == work_id and wid != work_id
            and str(d["data"].get("status") or "") in ACTIVE
            and str(d["data"].get("claimed_by") or "") == by}


def plain_busy(value, db: dict | None = None) -> str | None:
    """A busy line the page may show: a few words, never a work id (claim wrote the id there
    before 4.4)."""
    text = " ".join(str(value or "").split())
    if not text or " " not in text or text in ((db or {}).get("work") or {}):
        return None
    return text[:120]


def busy_beat(db: dict, chat_id: str, chat_kind: str, now: dt.datetime, out_dir: str,
              line: str | None, dump_dir: str = "") -> list[str]:
    """This chat's heartbeat saying what it is doing for the person in the chat (`line`, a
    few plain words), or that it is done (None). The page shows "Claude is busy in your
    chat: <line>" while it is there, so work asked in a chat is never invisible."""
    import app_model
    mine = (db.get("chats") or {}).get(safe_id(chat_id))
    busy = plain_busy(line) if line else None
    if line and busy is None:
        raise ValueError("say what it is doing in a few words")
    w = Writes(out_dir)
    if mine is None:
        fields = heartbeat(chat_id, chat_kind, now, busy=busy)
        w.add("set", "chats", chat_id, fields)
        version = 1
    else:
        beat = {"busy": busy, "seen_at": app_model.stamp(now)}
        w.add("update", "chats", chat_id, beat, if_version=mine["version"])
        fields, version = dict(mine["data"], **beat), int(mine["version"] or 1) + 1
    if dump_dir:
        _keep_dump(dump_dir, "chats", chat_id, fields, version)
    return w.save("busy")


# ------------------------------------------------------------------ finishing and asking, by code

# A chat wrote these by hand, a write at a time, and looked up their shape each time (a
# pasted reply took about fifteen steps before the person saw the draft, 2026-11-03). Now
# one command makes each batch: `app.py done` and `reply.py finish` the finished item,
# `app.py ask` a new one, the same documents the page itself writes.
SUMMARY_WORDS = 15
_SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")


def summary_problem(summary: str) -> str:
    """Why a finished item's summary will not do, or "": one short sentence of what is
    ready, SUMMARY_WORDS words at most. The page shows its first sentence only; a paragraph
    was too wordy to read (2026-10-30)."""
    s = " ".join(str(summary or "").split())
    if not s:
        return "say what is ready in one short sentence"
    if len(s.split()) > SUMMARY_WORDS:
        return (f"the summary has {len(s.split())} words: one short sentence of what is ready, "
                f"{SUMMARY_WORDS} words at most (the detail goes in the work itself)")
    if len([p for p in _SENTENCE_END.split(s) if p.strip()]) > 1:
        return "the summary is one sentence: the detail goes in the work itself"
    return ""


def _drop_from_dump(dump_dir: str, collection: str, doc_id: str) -> None:
    where = os.path.join(dump_dir, STORE.get(collection, collection))
    for name in (safe_id(doc_id), safe_id(doc_id).replace("~", "@")):
        try:
            os.remove(os.path.join(where, name + ".json"))
        except OSError:
            pass


def message_id(now: dt.datetime) -> str:
    """A new message's id, the way the page makes one: "m", the time, four random letters."""
    import random
    import string
    return "m" + now.strftime("%Y%m%dT%H%M") + "".join(
        random.choice(string.ascii_lowercase + string.digits) for _ in range(4))


# How a chat leaves an item: finished (done, failed, stopped at the person's Stop) or put to
# them with a question (`needs_you`), each by `app.py done`, never written by hand: a hand
# write carried no version, the next write was pinned to the wrong one and refused, and the
# item sat stranded (engine audit, 2026-11-03).
LEAVES = ("done", "failed", "stopped", "needs_you")
STOPPED_SAID = "Stopped, as you asked."


# A file's age and a claim's, each on its own clock (file_clock), read a moment apart.
SAVED_SLACK_S = 120


UNSAVED_SEARCH = ("the search's shortlist is not saved yet, so Jobs would show nothing new: "
                  "wait for run_round.py to end (it saves the shortlist as it ends), then finish")
_STAMP = re.compile(r"^(round|work): (\S+)\s*$", re.M)


def search_run(work_id: str = "") -> str:
    """The round this search's run is writing, by what its round.log says (run_round.py
    round_stamp), or "": the one that names this work item, else the newest round run in
    this copy. Read from the logs, never the files' times: a job chat is a fresh copy made
    after the claim, where every saved round is newer than the claim."""
    import person
    runs = []
    for log in glob.glob(os.path.join(glob.escape(person.state("rounds")), "*", "round.log")):
        try:
            with open(log, encoding="utf-8", errors="replace") as fh:
                said = _STAMP.findall(fh.read())
        except OSError:
            continue
        names = [v for k, v in said if k == "round"]
        if not names:
            continue
        works = {v for k, v in said if k == "work"}
        num = re.match(r"^r(\d+)", names[-1])
        runs.append((bool(work_id) and safe_id(work_id) in {safe_id(w) for w in works},
                     int(num.group(1)) if num else -1, names[-1]))
    return max(runs)[2] if runs else ""


def search_unsaved(item: dict, work_id: str = "") -> str:
    """Why a search may not be marked done yet, in plain words, or "": its shortlist is not
    saved where Jobs reads it (documents/rounds). A search marked done while run_round.py
    still ran in the background said "Your shortlist of 60 ranked jobs is ready" over a Jobs
    that said "Nothing new" (2026-11-04). Its own round decides (search_run): its shortlist
    must be saved. Only where no round was run in this copy is the newest saved round's age
    weighed against the claim's. No profile here (the app itself) checks nothing."""
    import app_model
    import person
    try:
        run = search_run(work_id or str(item.get("id") or ""))
        if run:
            saved = os.path.isfile(person.state("documents", "rounds", run + ".json"))
            return "" if saved else UNSAVED_SEARCH
        newest = app_model.newest_round()
    except person.NoProfile:
        return ""
    since = app_model.parse_time(item.get("claimed_at") or item.get("asked_at"))
    # The round's age on the files' clock, the claim's on Python's, and only the two ages
    # compared: a file's time against a claim's time mixed the two, and with Python's clock
    # moved on a shortlist saved a minute ago read as saved before the search (2026-11-05).
    try:
        import file_clock
        saved_ago = file_clock.age(newest) if newest else None
    except OSError:
        saved_ago = None
    claimed_ago = (dt.datetime.now(dt.timezone.utc) - since).total_seconds() if since else None
    if saved_ago is None or (claimed_ago is not None
                             and saved_ago > claimed_ago + SAVED_SLACK_S):
        return UNSAVED_SEARCH
    return ""


def finish(db: dict, work_id: str, now: dt.datetime, out_dir: str, summary: str = "",
           status: str = "done", error: str = "", links=(), reply: str = "", thread: str = "",
           chat_kind: str = "cloud", dump_dir: str = "", chat: str = "",
           question: str = "", about: str = "", answer: dict | None = None,
           answered=(), left_out: str = "", outcome: str = "") -> dict:
    """The batch that finishes one work item (the app skill, step 5): the item `done` (or
    `failed`, with `error` in plain words, or `stopped` after their Stop), its one-sentence
    summary and links, pinned to the version read; each of its locks the dump holds, deleted
    and pinned; and with `reply`, the chat's answer in the thread,
    `talk/<thread>/messages/<id>` (`thread` defaults to the item's own, for work from the
    page's chat). With `question` the item goes to the person instead (`needs_you`, the
    question in `note`), its locks freed; their answer puts it back in the queue. `about`
    (the exact words it concerns) and `answer` ({kind, choices, min, max, time}: the kind of
    answer it needs, tools/app_actions.py ANSWER_KINDS) go with it as `needs`, and the page
    draws the control that fits on the card (templates/app/DESIGN.md, "Asking the person").
    {work, status, thread, message, locks, batches}. Raises ValueError, in plain words, for a
    summary that will not do or a reply with no thread; KeyError for an item not in the dump
    or already finished."""
    import app_model
    doc = (db.get("work") or {}).get(safe_id(work_id))
    if doc is None:
        raise KeyError(f"no work {work_id!r} in the dump; read work again")
    item = dict(doc["data"])
    if str(item.get("status") or "") in FINISHED:
        made = finished_here(dump_dir, work_id) if dump_dir else None
        if made:
            # Finished by this folder, its batch kept: the same batch again, never refused,
            # so a finish that was never sent is never lost (two finishes in a row wrote one
            # file, and the second refused the first as already finished, 2026-11-09).
            return made
        raise KeyError(f"work {work_id!r} has already finished; write nothing more to it")
    taken = not_its_claim(item, chat)        # `chat`: the id the job was claimed under
    if taken:
        raise KeyError(taken)
    refused = computer_only(item, claimed_kind(item, chat_kind, chat))
    if refused and not (status == "stopped" and item.get("stop_asked")):
        raise ValueError(f"not finished: {refused}")
    if chat and str(item.get("status") or "queued") == "queued" and not item.get("claimed_by") \
            and status != "stopped":
        # Read before its claim landed: pinned to the version before the claim, the finish was
        # refused, and the holds the claim made were never freed (a person's computer,
        # 2026-11-09: a hold deleted by hand).
        raise KeyError(f"this folder was read before {work_id!r} was claimed: read work and "
                       "holds into it again, then run this again")
    outcome = str(outcome or "").strip().lower().replace(" ", "_")
    if outcome and outcome not in OUTCOMES:
        raise ValueError(f"--outcome is one of {', '.join(OUTCOMES)}")
    question = " ".join(str(question or "").split())
    if question:
        status = "needs_you"
    if status not in LEAVES:
        raise ValueError(f"a finished item is done, failed or stopped, not {status!r}")
    error = " ".join(str(error or "").split())
    if status == "failed" and not error:
        raise ValueError("say what went wrong, in plain words")
    if status == "needs_you" and not question:
        raise ValueError("ask the person one plain question (--question)")
    summary = " ".join(str(summary or "").split()) or (
        error if status == "failed" else STOPPED_SAID if status == "stopped" else "")
    problem = summary_problem(summary) if status == "done" or (
        status == "failed" and summary != error) else ""
    if not problem and status == "done" and str(item.get("kind") or "") == "search":
        problem = search_unsaved(item, work_id)
        if not problem and drafts_all(item) and not _drafted(db, item.get("drafts") or [])[1]:
            problem = ("its drafts are still being written: finish each one as it is made "
                       "(app.py done --work <its id>), and the search finishes with the last, "
                       "once app.py search-drafts --last has run")
    if problem:
        raise ValueError(problem)
    args = item.get("args") if isinstance(item.get("args"), dict) else {}
    thread = str(thread or "").strip() or (str(args.get("thread") or "").strip()
                                           if reply else "")
    # Work with no conversation of its own (a change to a draft, asked with its pencil): the
    # answer is kept on the item, and its card shows it where the change would have shown.
    # "Name its thread" refused it, and a plain answer could not be given at all (2026-11-09).
    answer_text = ""
    if str(reply or "").strip() and not thread:
        answer_text = str(reply).strip()[:ANSWER_MAX]
        reply = ""
    at = app_model.stamp(now)
    if status == "needs_you":
        import app_actions
        kind = clean = None
        if answer:
            clean = app_actions.clean_ask(dict(answer, key=answer.get("key") or "answer",
                                               label=answer.get("label") or ""))
            kind = clean["kind"] if clean else None
        needs = {"question": question[:600], "about": " ".join(str(about or "").split())[:600],
                 "work": work_id, "answer": clean or {"key": "answer", "label": "",
                                                      "kind": "text", "type": "text"}}
        fields = {"status": status, "note": question[:600], "lease_until": None,
                  "claimed_by": None, "asked_you_at": at, "needs": needs,
                  # The choices as pages before 4.10 read them: their words alone.
                  "choices": [c["label"] for c in (clean or {}).get("choices") or []]
                  if kind in ("choice", "yesno") else None}
    else:
        fields = {"status": status, "finished_at": at, "lease_until": None,
                  "result": {"summary": summary, "links": [dict(x) for x in links or ()]},
                  "error": error or None}
        # A form's questions answered, as the form asked them: the card that asked says Done
        # once each is on it, and "Finished: putting it on your page" until then.
        said = [" ".join(str(q).split())[:300] for q in answered or () if str(q).strip()]
        if said:
            fields["result"]["questions"] = said
        # A job's draft that ended because the job is not one they can take: its reason, so the
        # page says it and never offers Try again, which drafted a job already ruled out (the
        # maintainer, 2026-11-06).
        if str(left_out or "").strip():
            fields["result"]["left_out"] = " ".join(str(left_out).split())[:300]
        if answer_text:
            fields["result"]["answer"] = answer_text
        # It finished and changed nothing on the page (held, set aside, or not possible): its
        # card says so at once, never "putting the new version on your page" while waiting for
        # a change that will not come (a held change's spinner turned for good, 2026-11-09).
        if outcome:
            fields["result"]["outcome"] = outcome
    w = Writes(out_dir)
    mid = ""
    if str(reply or "").strip():
        mid = message_id(now)
        w.add("set", f"talk/{safe_id(thread)}/messages", mid,
              {"from": chat_kind if chat_kind in ("cloud", "computer") else "cloud",
               "text": str(reply).strip(), "at": at, "work": work_id})
    w.add("update", "work", work_id, fields, if_version=doc["version"])
    freed = []
    for lid, lock in sorted((db.get("locks") or {}).items()):
        if str((lock.get("data") or {}).get("work") or "") == work_id and not lock.get("old"):
            w.add("delete", "locks", lid, if_version=lock["version"])
            freed.append(lid)
    # A draft of a search that drafts what it finds: the search's card counts it, and the
    # last one finishes the search once it has found all it will.
    lead = _search_counted(db, item, work_id, status, now, w)
    got = {"work": work_id, "status": status, "thread": thread or None, "message": mid or None,
           "locks": freed, **({"search": lead} if lead else {}),
           # Each finish's batch a file of its own: two finishes in a row wrote one file, and
           # the first was lost (2026-11-09).
           "batches": w.save("finish-" + body_name(safe_id(work_id)))}
    if dump_dir:
        # The folder as it will be once the finish lands, kept the way every other batch is
        # (keep_landed): the next command over it sees the item finished and its holds gone,
        # and a refused finish is put back whole by `app.py version`, so the same `done` makes
        # it again. Moved on outside that record, the refused finish could never be made again
        # ("already finished"), and the item was one version behind for good (2026-11-09).
        keep_landed(dump_dir, got["batches"])
        _keep_finished(dump_dir, work_id, got)
    return got


# How a finish that changed nothing on the page ended (`done --outcome`): its card says it.
OUTCOMES = ("held", "set_aside", "unchanged")
# A written answer to work with no conversation of its own, kept on the item (`result.answer`).
ANSWER_MAX = 4000
FINISHED_HERE = ".finished.json"    # in a dump folder: each finish made here, with its batches


def _keep_finished(dump_dir: str, work_id: str, got: dict) -> None:
    side = os.path.join(dump_dir, FINISHED_HERE)
    have = _read_json(side)
    have = have if isinstance(have, dict) else {}
    have[safe_id(work_id)] = got
    try:
        with open(side, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(have, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass


def finished_here(dump_dir: str, work_id: str) -> dict | None:
    """The finish this folder made for `work_id` (what `finish` returned, its batch files
    still there), marked `again`, or None."""
    have = _read_json(os.path.join(dump_dir, FINISHED_HERE))
    got = have.get(safe_id(work_id)) if isinstance(have, dict) else None
    if not isinstance(got, dict) or not got.get("batches") or \
            not all(os.path.isfile(p) for p in got["batches"]):
        return None
    return dict(got, again=True)


def _drafted(db: dict, ids, also: dict | None = None) -> tuple[int, bool]:
    """(how many of these drafts are done, whether every one has finished), `also` being the
    statuses about to be written."""
    work = db.get("work") or {}
    also = also or {}
    states = [also.get(i) or str(((work.get(safe_id(i)) or {}).get("data") or {}).get("status")
                                 or "") for i in ids]
    return sum(1 for s in states if s == "done"), all(s in FINISHED for s in states)


def _search_counted(db: dict, item: dict, work_id: str, status: str, now: dt.datetime,
                    w: "Writes", dump_dir: str = "") -> str:
    """The search a finished draft was drafted for (`for_search`), updated: its count, "x of N
    drafted", and once it has found all it will (`drafts_last`) and every draft has finished,
    the search itself done, saying how many were drafted. Its id, or "" when there is none."""
    import app_model
    sid = str(item.get("for_search") or "")
    sdoc = (db.get("work") or {}).get(safe_id(sid)) if sid else None
    if sdoc is None or str(sdoc["data"].get("status") or "") in FINISHED:
        return ""
    s = dict(sdoc["data"])
    ids = [str(x) for x in s.get("drafts") or []]
    done, over = _drafted(db, ids, {work_id: status})
    total = int((s.get("count") or {}).get("total") or len(ids) or 1)
    at = app_model.stamp(now)
    fields: dict = {"count": {"done": done, "total": total, "word": DRAFTED},
                    "steps": (list(s.get("steps") or []) + [{"at": at, "text": f"{done} of {total} "
                                                                         f"{DRAFTED}."}])[-50:]}
    if s.get("drafts_last") and over:
        fields.update(status="done", finished_at=at, lease_until=None, error=None,
                      result={"summary": drafted_said(done, total, len(ids)), "links": []})
        _free_locks(db, sid, w, dump_dir)
    w.add("update", "work", sid, fields, if_version=sdoc["version"])
    if dump_dir:
        _keep_dump(dump_dir, "work", sid, dict(s, **fields), int(sdoc["version"] or 1) + 1)
    return sid


def drafted_said(done: int, total: int, tried: int) -> str:
    """The one short sentence (SUMMARY_WORDS) a search that drafted what it found ends with."""
    if total == 1:
        return ("Found 1 job that passes every rule, and drafted it." if done else
                "Found 1 job that passes every rule; its card says why it is not drafted.")
    if done == total:
        return f"Found {total} jobs that pass every rule, and drafted all {total}."
    return (f"Found {total} jobs that pass every rule, and drafted {done}; the others say why."
            if tried > done else f"Found {total} jobs that pass every rule, and drafted {done}.")


def search_drafts(db: dict, work_id: str, rows: list[dict], now: dt.datetime, out_dir: str,
                  chat: str = "", left: dict | None = None, last: bool = False,
                  dump_dir: str = "", listed=None) -> dict:
    """A search that drafts what it finds, given the jobs its Found list holds now that pass
    every rule (`rows`, in its order: {round, rank, url, company, title}, the job card's own
    draft args): a draft queued for each, up to the number asked for, claimed with the search
    (`with`, `for_search`) so the search's own chat drafts them together and no other chat takes
    one; a draft whose job has left the list since (`listed`, the links Jobs still holds, to
    draft, drafted or applied for) stopped, saying why where `left` ({link: why}) has it, and the
    next job taken; the search moved to drafting each one, its count "x of N drafted". With
    `last`, the search has found all it will: N is what it found, and it finishes with its last
    draft. A draft whose employer another job is writing for waits in the queue, still counted.
    {work, queued, stopped, drafted, total, batches}. KeyError for an item not in the dump,
    finished or another chat's; ValueError for a search that drafts nothing."""
    import app_model
    from lookup_score import norm
    work = db.get("work") or {}
    doc = work.get(safe_id(work_id))
    if doc is None:
        raise KeyError(f"no work {work_id!r} in the dump; read work again")
    item = dict(doc["data"])
    if str(item.get("status") or "") in FINISHED:
        raise KeyError(f"work {work_id!r} has finished; write nothing more to it")
    taken = not_its_claim(item, chat)
    if taken:
        raise KeyError(taken)
    if not drafts_all(item):
        raise ValueError("this search was not asked to draft what it finds")
    if item.get("stop_asked"):
        return {"work": work_id, "stop_asked": True, "queued": [], "stopped": [], "batches": []}
    at = app_model.stamp(now)
    until = app_model.stamp(now + dt.timedelta(seconds=LEASE_S))
    w = Writes(out_dir)
    left = {norm(str(k)) or str(k): v for k, v in (left or {}).items()}
    have = [str(x) for x in item.get("drafts") or []]
    stopped = []
    listed = None if listed is None else {norm(str(u)) for u in listed} - {None, ""}
    for wid in list(have):
        d = (work.get(safe_id(wid)) or {}).get("data") or {}
        url = norm(str((d.get("args") or {}).get("url") or ""))
        if not url or str(d.get("status") or "") in FINISHED or listed is None or url in listed:
            continue
        # Its job has left Jobs since it was queued: it fails a rule now (an employer judged
        # or turned down since), or the person set it aside. Drafting it is work for nothing.
        why = " ".join(str(left.get(url) or "it is no longer on your Jobs list").split())
        # One short sentence on the card: the reason itself, its rule's name left to the step.
        words = (why if len(why.split()) <= SUMMARY_WORDS - 2 else why.split(": ")[-1])
        words = words.rstrip(".").split()
        said = "Not drafted: " + " ".join(words[:SUMMARY_WORDS - 3]) + (
            "..." if len(words) > SUMMARY_WORDS - 3 else ".")
        fields = {"status": "stopped", "finished_at": at, "lease_until": None,
                  "result": {"summary": said, "links": []}, "error": None,
                  "steps": (list(d.get("steps") or []) + [{"at": at, "text": f"Not drafted: "
                                                                             f"{why}"}])[-50:]}
        w.add("update", "work", wid, fields, if_version=work[safe_id(wid)]["version"])
        _free_locks(db, wid, w, dump_dir)
        if dump_dir:
            _keep_dump(dump_dir, "work", wid, dict(d, **fields),
                       int(work[safe_id(wid)]["version"] or 1) + 1)
        have.remove(wid)
        stopped.append(wid)
    total = draft_total(item)
    held = held_locks(db, now)
    queued = []
    for r in rows:
        if len(have) >= total:
            break
        wid = safe_id(app_model.draft_work_id(r.get("url") or "", r.get("company"), r.get("title")))
        if wid in have:
            continue
        old = work.get(wid)
        if old is not None and str(old["data"].get("status") or "") not in FINISHED:
            continue                    # already on its way, by another job: not this one's
        noun = _noun()
        mine = {"kind": "draft", "args": {k: r.get(k) for k in ("round", "rank", "url", "company",
                                                                "title")}}
        busy = [lk for lk in locks_for(mine) if lk in held and held[lk] != wid]
        d = dict(mine, title=f"{noun[:1].upper() + noun[1:]} and letter: {r.get('company')}, "
                             f"{r.get('title')}",
                 to=str(item.get("to") or "cloud"), answers={}, asked_at=at,
                 asked_from={"work": work_id}, priority=0, for_search=work_id, stage=0,
                 stages=[{"name": s["name"], "est_s": s["est_s"]}
                         for s in progress("draft")["stages"]])
        if busy:
            d["status"] = "queued"
        else:
            d.update(status="claimed", claimed_by=chat, claimed_at=at, lease_until=until,
                     **{"with": work_id})
            for lock in locks_for(mine):
                lold = (db.get("locks") or {}).get(safe_id(lock))
                w.add("set", "locks", lock, {"work": wid, "chat": chat, "since": at, "until": until},
                      if_version=lold["version"] if lold else None)
                held[lock] = wid
        w.add("set", "work", wid, d, if_version=old["version"] if old else None)
        if dump_dir:
            _keep_dump(dump_dir, "work", wid, d, int(old["version"] or 1) + 1 if old else 1)
        have.append(wid)
        queued.append({"work": wid, **mine["args"], "waits": bool(busy)})
    done, _ = _drafted(db, have)
    n = len(have) if last else max(total, len(have))
    stages = item_stages(item)
    idx = [s["key"] for s in stages].index(SEARCH_DRAFT_STAGE[0])
    line = (f"Found {len(have)} that pass every rule: drafting each one." if last else
            f"Drafting {len(have)} found so far, as the search goes on.")
    fields = {"status": "running", "lease_until": until, "drafts": have,
              "stages": [{"name": s["name"], "est_s": s["est_s"]} for s in stages],
              "count": {"done": done, "total": max(n, 1), "word": DRAFTED},
              "steps": (list(item.get("steps") or []) + [{"at": at, "text": line}])[-50:]}
    if item.get("stage") != idx:
        fields.update(stage=idx, stage_at=at, left_s=None, left_at=None)
    if last:
        fields["drafts_last"] = True
    over = last and (not have or _drafted(db, have)[1])
    if over:
        fields.update(status="done", finished_at=at, lease_until=None, error=None,
                      result={"summary": drafted_said(done, len(have), len(have)) if have else
                              "Found no job that passes every rule, so nothing was drafted.",
                              "links": []})
        _free_locks(db, work_id, w, dump_dir)
    w.add("update", "work", work_id, fields, if_version=doc["version"])
    if dump_dir:
        _keep_dump(dump_dir, "work", work_id, dict(item, **fields), int(doc["version"] or 1) + 1)
    return {"work": work_id, "queued": queued, "stopped": stopped, "drafted": done,
            "total": fields["count"]["total"], "batches": w.save("drafts")}


def _noun() -> str:
    """What the person calls the document (person.json documents.noun), as _job_draft names
    a draft."""
    try:
        import person
        return str(person.get("documents.noun", "resume") or "resume")
    except Exception:  # noqa: BLE001  no profile here: the app's word
        return "resume"


def _free_locks(db: dict, wid: str, w: "Writes", dump_dir: str = "") -> None:
    """Each lock this item holds, deleted and pinned, as finishing it does."""
    for lid, lock in sorted((db.get("locks") or {}).items()):
        if str((lock.get("data") or {}).get("work") or "") == wid and not lock.get("old"):
            w.add("delete", "locks", lid, if_version=lock["version"])
            if dump_dir:
                _drop_from_dump(dump_dir, "locks", lid)


# Kinds the page runs one at a time (templates/app/app.js KIND_CAP_ONE).
ONE_AT_A_TIME = ("search", "update", "network")


def work_id(kind: str, now: dt.datetime) -> str:
    """A new item's id, the way the page makes one: its kind, the time, four random letters."""
    import random
    import string
    return f"{kind}~{now.strftime('%Y%m%dT%H%M')}-" + "".join(
        random.choice(string.ascii_lowercase + string.digits) for _ in range(4))


def queued(kind: str, title: str, args: dict, now: dt.datetime) -> dict:
    """A work item's fields, queued with no one asking, as `ask` writes one: the kind's own
    stages, its usual place to run. What the drafts rerun queues for an application it
    made again and that failed (tools/remake_drafts.py, through tools/app.py view)."""
    import app_model
    if kind not in WORK_KINDS:
        raise ValueError(f"there is no kind of work {kind!r}")
    return {"kind": kind, "title": " ".join(str(title or "").split())[:140],
            "to": "cloud" if WORK_KINDS[kind]["to"] == "cloud" else "either",
            "args": dict(args or {}), "asked_at": app_model.stamp(now),
            "asked_from": {"tab": "chat"}, "priority": 0, "status": "queued",
            "stages": progress(kind)["stages"], "stage": 0, "stage_at": None, "steps": [],
            "claimed_by": None, "claimed_at": None, "stop_asked": False, "attempt": 1}


def ask(db: dict, kind: str, title: str, now: dt.datetime, out_dir: str, args: dict | None = None,
        to: str = "", chat_id: str = "", item_id: str = "", dump_dir: str = "",
        here: bool = False, chat_kind: str = "cloud") -> dict:
    """A new work item, queued from a chat as the page's own Ask would queue it
    (templates/app/app.js createWork): the same fields, the kind's own stages, and, for a
    kind the page runs one at a time, refused while one is going. {work, batches}. Raises
    ValueError, in plain words, for a kind there is none of, no title, or one already going.

    `here`: the chat the person asked does it itself, now (a search, drafts, a prep asked in
    a chat). The item is made claimed by that chat and running at its first stage, marked
    `in_chat`, so the page's work list shows it, its stages and its result like work asked
    on the page; only a busy line showed before, and nobody could see what ran or what was
    done (the maintainer, 4 November). That chat pins it and finishes it (`app.py pin`,
    `app.py done`); no other chat ever starts it again."""
    import app_model
    if kind not in WORK_KINDS:
        raise ValueError(f"there is no kind of work {kind!r}; one of "
                         f"{', '.join(sorted(WORK_KINDS))}")
    title = " ".join(str(title or "").split())
    if not title:
        raise ValueError("say what it is, in a few plain words (--title)")
    if args is not None and not isinstance(args, dict):
        raise ValueError("args is a JSON object, like {\"contact\": \"<contact id>\"}")
    if kind in ONE_AT_A_TIME:
        for d in (db.get("work") or {}).values():
            w = d["data"]
            if w.get("kind") == kind and str(w.get("status") or "") in ("queued",) + ACTIVE:
                raise ValueError(f"one at a time: \"{w.get('title') or kind}\" is still going")
    wid = safe_id(item_id) if item_id else work_id(kind, now)
    if wid in (db.get("work") or {}):
        raise ValueError(f"work {wid!r} is already there")
    to = to or ("cloud" if WORK_KINDS[kind]["to"] == "cloud" else "either")
    if to not in ("cloud", "computer", "either") or (
            to != "either" and to not in WORK_KINDS[kind]["can"]):
        raise ValueError(f"a {kind} runs in " + " or ".join(WORK_KINDS[kind]["can"]))
    fields = {"kind": kind, "title": title[:140], "to": to, "args": dict(args or {}),
              "asked_at": app_model.stamp(now), "asked_from": {"tab": chat_id or "chat"},
              "priority": 0, "status": "queued", "stages": progress(kind)["stages"], "stage": 0,
              "stage_at": None, "steps": [], "claimed_by": None, "claimed_at": None,
              "stop_asked": False, "attempt": 1}
    if here:
        if not chat_id:
            raise ValueError("this chat's id is not known: run it again with --chat <this "
                             "chat's id>")
        held = held_locks(db, now)
        busy = [lk for lk in locks_for(fields) if lk in held]
        if busy:
            other = ((db.get("work") or {}).get(held[busy[0]]) or {}).get("data") or {}
            raise ValueError(f"\"{other.get('title') or 'another job'}\" is running for the "
                             "same thing: wait for it to finish")
        at = app_model.stamp(now)
        fields.update(status="running", claimed_by=chat_id, claimed_at=at, stage_at=at,
                      lease_until=app_model.stamp(now + dt.timedelta(seconds=LEASE_S)),
                      in_chat=True, asked_from={"tab": "chat", "chat": chat_id},
                      to=chat_kind if chat_kind in WORK_KINDS[kind]["can"] else to)
    w = Writes(out_dir)
    w.add("set", "work", wid, fields)
    batches = w.save("ask")
    if dump_dir:
        # As every other batch is kept (keep_landed), so a refused one is put back.
        keep_landed(dump_dir, batches)
    return {"work": wid, "batches": batches}


# Kinds of work whose finish leaves PDFs the page should hold: they run in a chat of their own,
# which cannot put a file in the page's store (only a chat with the Artifact tool allowed can,
# and a job's chat carries ArtifactData and ArtifactComments alone), so the chat that started
# them uploaded each by hand, or the person tapped "Get my files ready" (the maintainer, 4
# November).
FILES_AFTER = ("draft", "resume_for_contact")


def queue_files(db: dict, apps: list, now: dt.datetime, out_dir: str, dump_dir: str = "",
                chat_id: str = "") -> dict | None:
    """One `files` item for every drafted application in `apps` (app_model.files_missing)
    that no files work still going already covers, made as the page's own "Get my files
    ready" makes it (templates/app/app.js askFiles): for the chat that answers the page,
    which can upload, all of them in one piece of work. The page rings for it with the
    person's next tap, like any work no chat was told of. None when nothing is left."""
    import app_model
    work = db.get("work") or {}
    covered: set = set()
    for d in work.values():
        x = d.get("data") or {}
        if x.get("kind") != "files" or str(x.get("status") or "queued") not in ("queued",) + ACTIVE:
            continue
        a = x.get("args") if isinstance(x.get("args"), dict) else {}
        covered |= {str(i) for i in a.get("applications") or []}
        if a.get("application"):
            covered.add(str(a["application"]))
    left = [x for x in apps or [] if str(x.get("id") or "") and str(x["id"]) not in covered]
    if not left:
        return None
    wid = safe_id("files~" + str(left[0]["id"]))
    title = "Make the files downloadable: " + (f"{len(left)} applications" if len(left) > 1
                                               else str(left[0].get("company") or "")
                                               or "your application")
    # `applications` even for one: each card finds the work its files wait on by it
    # (templates/app/app.js filesWorkFor), whatever the item's id is spelled as.
    args = {"application": str(left[0]["id"]),
            "applications": [str(x["id"]) for x in left],
            "files": [n for x in left for n in x.get("files") or []],
            "paths": [p for x in left for p in x.get("paths") or []]}
    fields = {"kind": "files", "title": title[:140], "to": "either", "args": args,
              "asked_at": app_model.stamp(now), "asked_from": {"tab": "chat",
                                                               **({"chat": chat_id} if chat_id else {})},
              "priority": 0, "status": "queued", "stages": progress("files")["stages"],
              "stage": 0, "stage_at": None, "steps": [], "claimed_by": None, "claimed_at": None,
              "stop_asked": False, "attempt": 1}
    old = work.get(wid)
    w = Writes(out_dir)
    # One with this id already finished (an earlier upload of the first of them): asked
    # again, pinned to it, as the page's own "redo" does.
    w.add("set", "work", wid, fields, if_version=old["version"] if old else None)
    if dump_dir:
        _keep_dump(dump_dir, "work", wid, fields, int(old["version"] or 1) + 1 if old else 1)
    return {"work": wid, "applications": [str(x["id"]) for x in left], "batches": w.save("files")}


# ------------------------------------------------------------------ keeping the store small

KEEP_DAYS = 60      # what the page shows of the past: its newest 300 actions and 500 receipts
DRAFT_BATCH = 10    # drafts one job takes at most: the workflow's own batch
# Follow-ups one job takes at most: each is drafted in code, so the bound is the finishing
# batch (two writes each, BATCH_MAX a batch).
FOLLOW_UP_BATCH = 20
PRUNE_CAP = 150     # deletes a wake sends at most, so one wake never sends a long batch


def prune(db: dict, now: dt.datetime, out_dir: str, keep_days: int = KEEP_DAYS,
          cap: int = PRUNE_CAP) -> list[str]:
    """Batches deleting what is finished and older than `keep_days`: an applied action with
    its receipt, and finished work. A page's store holds at most 25,000 records (db.d.ts:
    "prune old ones"), and nothing deleted them before 4.3 (contract audit, 2026-10-29).
    Nothing still waiting is touched: an action without a receipt stays, and so does work
    that is not finished."""
    cutoff = (now - dt.timedelta(days=keep_days)).strftime("%Y-%m-%dT%H:%M:%S")
    w = Writes(out_dir)
    n = 0
    receipts = db.get("receipts") or {}
    actions = db.get("actions") or {}
    for aid, doc in sorted(receipts.items(), key=lambda kv: str((kv[1].get("data") or {}).get("applied_at") or "")):
        if n >= cap:
            break
        at = str((doc.get("data") or {}).get("applied_at") or "")
        if not at or at[:19] >= cutoff:
            continue
        # A receipt goes only with its action, both or neither: one deleted alone at the cap
        # left its action with no receipt, and it was applied again (engine audit, 2026-11-03).
        pair = 2 if aid in actions else 1
        if n + pair > cap:
            break
        w.add("delete", "receipts", aid, if_version=doc.get("version"))
        n += 1
        if aid in actions:
            w.add("delete", "actions", aid, if_version=actions[aid].get("version"))
            n += 1
    for wid, doc in sorted((db.get("work") or {}).items()):
        if n >= cap:
            break
        d = doc.get("data") or {}
        at = str(d.get("finished_at") or d.get("asked_at") or "")
        if str(d.get("status") or "") in FINISHED and at and at[:19] < cutoff:
            w.add("delete", "work", wid, if_version=doc.get("version"))
            n += 1
    return w.save("prune") if n else []
