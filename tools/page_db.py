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


def unwrap(obj) -> tuple[dict, int | None]:
    """(the document's fields, its version) from one dumped file. A dump holds either the
    fields themselves, or a wrapper {id, version, data}. The version is the wrapper's, else
    `__version__` or `_version` beside the fields, else the record's own `_v`, else 1: a
    record from before `_v` that a chat never rewrote was made once, by the page."""
    if not isinstance(obj, dict):
        return {}, None
    if isinstance(obj.get("data"), dict) and set(obj) <= _WRAPPER:
        version = obj.get("version", obj.get("__version__", obj.get("_version")))
        fields = dict(obj["data"])
    else:
        fields = {k: v for k, v in obj.items() if k not in ("__version__", "_version")}
        version = obj.get("__version__", obj.get("_version"))
    own = fields.pop(VERSION_FIELD, None)
    if not isinstance(version, int) or isinstance(version, bool):
        version = own if isinstance(own, int) and not isinstance(own, bool) and own > 0 else 1
    return fields, version


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def load(dump_dir: str) -> dict:
    """{collection: {doc_id: {"data": fields, "version": n or None}}} for every collection
    the chat dumped into `dump_dir`. A collection not dumped is empty.

    A record read under its 4.2 name (`view/jobs`, `meta/listener`) stands for its new one
    only while the new one does not exist, and then with no version and `"old": True`: its
    version is the old record's, which the new name never had, so a write pinned to it was
    refused (2026-10-29). The first write makes the new record, and `move()` makes them all."""
    out: dict = {c: {} for c in COLLECTIONS}
    for coll in COLLECTIONS:
        new = STORE.get(coll, coll)
        # The old name first, so a record under its new name always wins.
        for where in dict.fromkeys((coll, new)):
            for path in sorted(glob.glob(os.path.join(dump_dir, where, "*.json"))):
                got = _read_json(path)
                if got is None:
                    continue
                fields, version = unwrap(got)
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


class Writes:
    """The writes one chat turn sends back, each body in a file of its own.

    `add()` keeps the body under `<out>/files/<collection>/<doc_id>.json` (its name spelled by
    `body_name`) and the entry ({op, collection, doc_id, file_path, if_version}); `save()`
    writes the entries as batch files of at most 50, and returns their paths."""

    def __init__(self, out_dir: str):
        self.out_dir = out_dir
        self.entries: list[dict] = []

    def add(self, op: str, collection: str, doc_id: str, data: dict | None = None,
            if_version: int | None = None) -> dict:
        if op not in ("set", "update", "delete"):
            raise ValueError(f"page_db: no write {op!r}")
        collection, doc_id = stored(collection, safe_id(doc_id))
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
            n = os.path.getsize(e["file_path"]) if e.get("file_path") else 0
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
}
assert set(STAGES) == set(WORK_KINDS)
# Three big jobs at once (a search, a networking run and an interview prep, the maintainer's
# own example, 2026-10-29), and an urgent one more. The work and its cost are the same run side
# by side or one after another; the cap only keeps the cloud computer's disk and memory clear
# (a search round's stage files, a batch's LaTeX compiles).
HEAVY_CAP = 3
ACTIVE = ("claimed", "running")
FINISHED = ("done", "failed", "stopped")
# A claim not moved on in this long is not believed: a lock it holds is free again.
LEASE_S = 30 * 60


def progress(kind: str) -> dict:
    """The default stages of a kind of work, with their usual seconds."""
    if kind not in STAGES:
        raise KeyError(f"no kind of work {kind!r}; one of {', '.join(sorted(STAGES))}")
    stages = [{"key": k, "name": n, "est_s": s} for k, n, s in STAGES[kind]]
    return {"kind": kind, "stages": stages, "total_s": sum(s["est_s"] for s in stages)}


def can_take(item: dict, chat_kind: str) -> bool:
    """Whether a chat of this kind can do a work item. One chat answers the page
    (tools/app_listen.py), so work never waits for a chat of the other kind: the item's `to`
    is only where the page expected it to run. A brief alone needs the cloud, since it comes
    with the computer off."""
    kind = WORK_KINDS.get(str(item.get("kind") or ""))
    return kind is not None and chat_kind in kind["can"]


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


def _live_claim(item: dict, now: dt.datetime) -> bool:
    """Is this item held by a chat right now: claimed or running, and moved on lately?"""
    if str(item.get("status") or "") not in ACTIVE:
        return False
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
        if _live_claim(doc["data"], now):
            for lock in locks_for(doc["data"]):
                held[lock] = wid
    for lid, doc in (db.get("locks") or {}).items():
        d = doc["data"]
        owner = str(d.get("work") or "")
        until = _time(d.get("until"))
        item = (work.get(owner) or {}).get("data")
        if item is not None and not _live_claim(item, now):
            continue                   # its job finished or stalled: the lock is free
        if until is not None and until <= now:
            continue
        held.setdefault(lid, owner)
    return held


def next_item(db: dict, chat_kind: str, now: dt.datetime,
              cap: int = HEAVY_CAP) -> dict | None:
    """The queued work item this chat should claim, or None.

    A kind of work it can do (can_take), the most urgent first and then the oldest asked, never past the heavy-job cap (urgent
    may take one more), and never one whose locks another live job holds."""
    work = db.get("work") or {}
    held = held_locks(db, now)
    heavy = sum(1 for d in work.values() if _live_claim(d["data"], now)
                and WORK_KINDS.get(str(d["data"].get("kind") or ""), {}).get("heavy"))
    queued = []
    for wid, doc in work.items():
        item = doc["data"]
        kind = WORK_KINDS.get(str(item.get("kind") or ""))
        if kind is None or str(item.get("status") or "") != "queued" or item.get("stop_asked"):
            continue
        if not can_take(item, chat_kind):
            continue
        queued.append((-int(item.get("priority") or 0), str(item.get("asked_at") or ""), wid))
    # An update that changes how a record file is stored (args.migration) never interrupts
    # running work: it starts once nothing else is running, and work asked for meanwhile
    # waits until it has landed ("Starts after the update"). A code-only update holds
    # nothing but its own lock.
    migrating = after_update(db)
    others_live = any(_live_claim(d["data"], now) for d in work.values()
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
               "stages": progress(item["kind"])["stages"]}
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


def _is_migration(item: dict) -> bool:
    return item.get("kind") == "update" and bool((item.get("args") or {}).get("migration"))


def after_update(db: dict) -> bool:
    """Is a state migration queued or running, so new work starts after it?"""
    return any(_is_migration(d["data"]) and str(d["data"].get("status") or "")
               in ("queued",) + ACTIVE for d in (db.get("work") or {}).values())


def heartbeat(chat_id: str, chat_kind: str, now: dt.datetime, busy: str | None = None,
              title: str = "") -> dict:
    import app_model
    can = sorted(k for k, v in WORK_KINDS.items() if chat_kind in v["can"])
    return {"kind": chat_kind, "title": title or f"Job search ({chat_kind})", "can": can,
            "seen_at": app_model.stamp(now), "busy": busy}


def claim(db: dict, chosen: dict, chat_id: str, chat_kind: str, now: dt.datetime,
          out_dir: str) -> list[str]:
    """The claim for `chosen` (next_item's answer) as batch files: the item pinned to the
    version read, each lock created (a lock left by a finished job is replaced, pinned to
    its version), and the chat's heartbeat. A refused batch means another chat has it."""
    import app_model
    w = Writes(out_dir)
    at = app_model.stamp(now)
    until = app_model.stamp(now + dt.timedelta(seconds=LEASE_S))
    w.add("update", "work", chosen["work"],
          {"status": "claimed", "claimed_by": chat_id, "claimed_at": at, "lease_until": until},
          if_version=chosen.get("version"))
    for other in chosen.get("with") or []:
        w.add("update", "work", other["work"],
              {"status": "claimed", "claimed_by": chat_id, "claimed_at": at, "lease_until": until,
               "with": chosen["work"]}, if_version=other.get("version"))
    for lock in chosen.get("locks") or []:
        old = (db.get("locks") or {}).get(safe_id(lock))
        w.add("set", "locks", lock, {"work": chosen["work"], "chat": chat_id, "since": at,
                                     "until": until},
              if_version=old["version"] if old else None)
    chats = db.get("chats") or {}
    mine = chats.get(safe_id(chat_id))
    # `busy` is the line the page shows for work asked in the chat (busy_beat), never a work
    # id: the page shows the work itself. A line already there is kept.
    line = plain_busy(((mine or {}).get("data") or {}).get("busy"), db)
    w.add("set", "chats", chat_id, heartbeat(chat_id, chat_kind, now, busy=line),
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
    keys = [k for k, _, _ in STAGES.get(kind, [])]
    n = len(given) if given else len(keys)
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
    if plain != path and os.path.exists(plain):
        os.remove(plain)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dict(fields, **{VERSION_FIELD: version}), fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def pin(db: dict, work_id: str, now: dt.datetime, out_dir: str, stage=None, line: str = "",
        count: dict | None = None, left_s: int | None = None, dump_dir: str = "") -> dict:
    """One pinned update of a running item: its stage (stage_at only when the stage moves
    on), one plain line in its steps, how many of how many are done, how long is left
    (`left_s`, as of `left_at`), and its lease, renewed, so long work is never taken for
    stopped. The page reads `left_s` as the stage's own estimate: a search that says
    "15 min left" is not shown as late at ten. {work, stage, count, left_s, batches}."""
    import app_model
    doc = (db.get("work") or {}).get(safe_id(work_id))
    if doc is None:
        raise KeyError(f"no work {work_id!r} in the dump; read work again")
    item = dict(doc["data"])
    if str(item.get("status") or "") in ("done", "failed", "stopped"):
        raise KeyError(f"work {work_id!r} has finished; write nothing more to it")
    if item.get("stop_asked"):
        # They tapped Stop: no stage is pinned, the work is stopped (the app skill, step 4).
        return {"work": work_id, "stop_asked": True, "batches": []}
    at = app_model.stamp(now)
    fields: dict = {"status": "running",
                    "lease_until": app_model.stamp(now + dt.timedelta(seconds=LEASE_S))}
    if stage is not None:
        idx = stage_index(str(item.get("kind") or ""), stage, item.get("stages"))
        if idx != item.get("stage") or not item.get("stage_at") \
                or str(item.get("status") or "") != "running":
            # A new stage starts with its own count and its own estimate.
            fields.update(stage=idx, stage_at=at, count=None, left_s=None, left_at=None)
    if line:
        fields["steps"] = (list(item.get("steps") or []) + [{"at": at, "text": line}])[-50:]
    if count and int(count.get("total") or 0) > 0:
        fields["count"] = {"done": int(count.get("done") or 0), "total": int(count["total"])}
    if left_s is not None:
        fields.update(left_s=max(0, int(left_s)), left_at=at)
    w = Writes(out_dir)
    w.add("update", "work", work_id, fields, if_version=doc["version"])
    if dump_dir:
        _keep_dump(dump_dir, "work", work_id, dict(item, **fields), int(doc["version"] or 1) + 1)
    return {"work": work_id, "stop_asked": False, "stage": fields.get("stage", item.get("stage")),
            "count": fields.get("count", item.get("count")),
            "left_s": fields.get("left_s", item.get("left_s")), "batches": w.save("pin")}


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


# ------------------------------------------------------------------ keeping the store small

KEEP_DAYS = 60      # what the page shows of the past: its newest 300 actions and 500 receipts
DRAFT_BATCH = 10    # drafts one job takes at most: the workflow's own batch
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
        w.add("delete", "receipts", aid, if_version=doc.get("version"))
        n += 1
        if aid in actions and n < cap:
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
