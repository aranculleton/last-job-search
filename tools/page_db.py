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
               "reach")

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
_SAFE_ID = re.compile(r"[^A-Za-z0-9_\-.~:@+]+")

# ------------------------------------------------------------------ reading a dump

# Fields a document's wrapper may carry beside its data, as a tool or a page writes it.
_WRAPPER = {"id", "doc_id", "version", "data", "path", "collection", "created_at",
            "updated_at", "create_time", "update_time", "__version__", "_version"}


def unwrap(obj) -> tuple[dict, int | None]:
    """(the document's fields, its version) from one dumped file. A dump holds either the
    fields themselves, with the version beside them (`__version__`, `_version`), or a
    wrapper {id, version, data}. Both are read."""
    if not isinstance(obj, dict):
        return {}, None
    if isinstance(obj.get("data"), dict) and set(obj) <= _WRAPPER:
        version = obj.get("version", obj.get("__version__", obj.get("_version")))
        return dict(obj["data"]), version if isinstance(version, int) else None
    fields = {k: v for k, v in obj.items() if k not in ("__version__", "_version")}
    version = obj.get("__version__", obj.get("_version"))
    return fields, version if isinstance(version, int) else None


def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def load(dump_dir: str) -> dict:
    """{collection: {doc_id: {"data": fields, "version": n or None}}} for every collection
    the chat dumped into `dump_dir`. A collection not dumped is empty."""
    out: dict = {c: {} for c in COLLECTIONS}
    for coll in COLLECTIONS:
        for path in sorted(glob.glob(os.path.join(dump_dir, coll, "*.json"))):
            got = _read_json(path)
            if got is None:
                continue
            fields, version = unwrap(got)
            doc_id = os.path.splitext(os.path.basename(path))[0]
            out[coll][doc_id] = {"data": fields, "version": version}
    return out


def safe_id(text: str) -> str:
    """A document id the database takes: letters, digits and _ - . ~ : @ + only."""
    return _SAFE_ID.sub("_", str(text or "")).strip("_")[:200] or "x"


# ------------------------------------------------------------------ a document too big for one

# A document the database would refuse (over DOC_MAX as `Writes` stores it) goes as parts: a
# head without the big field, naming how many parts (`in_parts`), then `part~<doc id>~<n>`,
# each holding a piece of that field's JSON text under `text` and the head's `rev`. The page
# joins them only when every part is there at the head's rev (templates/app/app.js joined()),
# and `joined()` below reads them back the same way. Each part stays well under the cap.
PART_BYTES = 200_000
PART_PREFIX = "part~"


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


class Writes:
    """The writes one chat turn sends back, each body in a file of its own.

    `add()` keeps the body under `<out>/files/<collection>/<doc_id>.json` and the entry
    ({op, collection, doc_id, file_path, if_version}); `save()` writes the entries as
    batch files of at most 50, and returns their paths."""

    def __init__(self, out_dir: str):
        self.out_dir = out_dir
        self.entries: list[dict] = []

    def add(self, op: str, collection: str, doc_id: str, data: dict | None = None,
            if_version: int | None = None) -> dict:
        if op not in ("set", "update", "delete"):
            raise ValueError(f"page_db: no write {op!r}")
        doc_id = safe_id(doc_id)
        self.entries = [e for e in self.entries
                        if not (e["collection"] == collection and e["doc_id"] == doc_id)]
        entry = {"op": op, "collection": collection, "doc_id": doc_id}
        if op != "delete":
            body = json.dumps(data or {}, ensure_ascii=False, indent=1, sort_keys=True)
            if len(body.encode("utf-8")) > DOC_MAX:
                raise ValueError(f"page_db: {collection}/{doc_id} is over 256 KiB"
                                 " (page_db.split() writes it as parts)")
            path = os.path.join(self.out_dir, "files", collection, doc_id + ".json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(body + "\n")
            entry["file_path"] = os.path.abspath(path)
        if if_version is not None:
            entry["if_version"] = int(if_version)
        self.entries.append(entry)
        return entry

    def drop(self, collection: str, doc_id: str) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries
                        if not (e["collection"] == collection and e["doc_id"] == doc_id)]
        return len(self.entries) != before

    def save(self, name: str = "batch") -> list[str]:
        os.makedirs(self.out_dir, exist_ok=True)
        paths = []
        for n in range(0, len(self.entries), BATCH_MAX):
            part = self.entries[n:n + BATCH_MAX]
            suffix = "" if len(self.entries) <= BATCH_MAX else f"_{n // BATCH_MAX + 1}"
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
    "search": [("start", "Getting started", 60), ("scrape", "Searching job sites", 300),
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
    "network": [("start", "Getting started", 60), ("find", "Finding people", 240),
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
}
assert set(STAGES) == set(WORK_KINDS)
HEAVY_CAP = 2
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


def where(item: dict, either_to: str = "cloud") -> str:
    """Which chat a work item is for: its `to`, with "either" going to `either_to`."""
    kind = WORK_KINDS.get(str(item.get("kind") or ""), {})
    to = str(item.get("to") or kind.get("to") or "cloud")
    return either_to if to == "either" else to


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


def next_item(db: dict, chat_kind: str, now: dt.datetime, either_to: str = "cloud",
              cap: int = HEAVY_CAP) -> dict | None:
    """The queued work item this chat should claim, or None.

    Its own chat kind (the item's `to`, "either" by the person's choice), a kind it can do,
    the most urgent first and then the oldest asked, never past the heavy-job cap (urgent
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
        if chat_kind not in kind["can"] or where(item, either_to) != chat_kind:
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
    w.add("set", "chats", chat_id, heartbeat(chat_id, chat_kind, now, busy=chosen["work"]),
          if_version=mine["version"] if mine else None)
    return w.save("claim")
