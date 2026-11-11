#!/usr/bin/env python3
"""What a wake reads from the page's database: only what changed since the last read.

Each wake read every collection whole (the taps and their receipts, two months of work, the
big screen documents, the page's addresses), and the read tool lists every record it saved,
a line each, into the chat that made it: some hundreds of lines a tap, read again at every
later step of that chat (the maintainer, 2026-11-05). Now this checkout keeps a copy of what
it last read and wrote (the mirror, in its git folder, never committed), and a wake reads:

- whole, the small collections: `meta` (the listener and the page's revision, `meta/now`),
  `beats` (each chat's heartbeat) and `holds` (the locks);
- only what changed since the cursor: taps (`actions`) by when they were made, receipts by
  when they were applied, and work that is not finished, or was asked for or finished since;
- never the screen documents or the page's addresses: the mirror holds them, as this
  checkout last read or drew them.

`assemble` then lays the mirror under the read, so every command over the folder sees the
whole database as before. The cursor is the older of the last read and the oldest tap still
waiting, less CLOCK_SLACK_S for the person's own clock. Whatever the mirror holds wrongly is
caught by the store itself: every write is pinned to a version, a refused one names the
right number (`app.py version`), and the next read is a whole one. A whole read also comes
with the first wake of each day, every FULL_EVERY_S, on a new page address, and when asked
(`--full`).

The page may say its own revision with its ring (`[rev:<n>]`, a number it raises with each
write it makes): a ring whose revision this checkout already read needs no read at all.

    python3 tools/app.py reads --in <a folder> [--full] [--rev N]   (makes and names w<n> there)
    python3 tools/app.py reads <dump> [--full] [--rev N]

Standard library only.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

MIRROR = "ljs-page-mirror"            # in the copy's git folder: the last read, never committed
MIRROR_META = ".mirror.json"          # in the mirror: {url, full_at, read_at, last_dump, rev, full_next}
PLAN = ".reads.json"                  # in a dump folder: what was read, and from when
# The person's own clock stamps a tap (`at`) and a work item asked for on the page: read back
# this far before the last read, so a device a little behind never hides a tap until the next
# whole read. Taps are few: two hours of them is a handful of records.
CLOCK_SLACK_S = 2 * 3600
FULL_EVERY_S = 6 * 3600
LIMIT = 1000
# Read whole every time: a few records each.
WHOLE = ("meta", "beats", "holds")
# Read whole only on a whole read; else kept from the mirror.
KEPT = ("screen", "addr")
# Every folder the mirror keeps (the store's own names).
MIRRORED = ("actions", "receipts", "work") + WHOLE + KEPT
FINISHED = ("done", "failed", "stopped")
# Every collection of a whole read, as a wake always read them (the talk threads are read
# for the one item in hand, never here).
FULL_READS = ("actions", "receipts", "work", "beats", "holds", "meta", "screen", "addr")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _stamp(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _time(value) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _read(path: str):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def mirror_dir() -> str:
    """LJS_PAGE_MIRROR (tests), else the copy's git folder, else a hidden folder in the state."""
    given = os.environ.get("LJS_PAGE_MIRROR")
    if given:
        return given
    import person
    root = person.state()
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--absolute-git-dir"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=10, stdin=subprocess.DEVNULL)
        d = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        d = ""
    return os.path.join(d, MIRROR) if d else os.path.join(root, "." + MIRROR)


def _meta() -> dict:
    got = _read(os.path.join(mirror_dir(), MIRROR_META))
    return got if isinstance(got, dict) else {}


def _save_meta(meta: dict) -> None:
    try:
        _write(os.path.join(mirror_dir(), MIRROR_META), meta)
    except OSError:
        pass


def want_full() -> None:
    """The next read is a whole one: a write was refused, so what the mirror holds may be
    wrong somewhere."""
    meta = _meta()
    meta["full_next"] = True
    _save_meta(meta)


def _url() -> str:
    try:
        import app_setup
        return str(app_setup.page_record().get("url") or "")
    except Exception:  # noqa: BLE001  no profile: no address
        return ""


def _zone() -> str:
    try:
        import person
        return person.home_zone_named(person.directory()) or "UTC"
    except Exception:  # noqa: BLE001
        return "UTC"


def full_due(meta: dict, now: dt.datetime, url: str = "") -> str:
    """Why this read must be whole, or ""."""
    if meta.get("full_next"):
        return "a write was refused"
    if not os.path.isdir(os.path.join(mirror_dir(), "screen")) and \
            not os.path.isdir(os.path.join(mirror_dir(), "view")):
        return "nothing kept yet"
    if url and meta.get("url") and meta.get("url") != url:
        return "a new page address"
    full = _time(meta.get("full_at"))
    if full is None:
        return "nothing kept yet"
    import app_model
    zone = _zone()
    if app_model.local_day(now, zone) > app_model.local_day(full, zone):
        return "a new day"
    if (now - full).total_seconds() >= FULL_EVERY_S:
        return "the last whole read is old"
    return ""


def _oldest_waiting(folder: str) -> dt.datetime | None:
    """The oldest tap in `folder` with no receipt there."""
    acts = os.path.join(folder, "actions")
    if not os.path.isdir(acts):
        return None
    have = set()
    rec = os.path.join(folder, "receipts")
    if os.path.isdir(rec):
        have = {os.path.splitext(n)[0] for n in os.listdir(rec)}
    oldest = None
    for name in os.listdir(acts):
        if not name.endswith(".json") or os.path.splitext(name)[0] in have:
            continue
        got = _read(os.path.join(acts, name))
        data = (got.get("data") if isinstance(got, dict) and isinstance(got.get("data"), dict)
                else got) or {}
        t = _time(data.get("at")) if isinstance(data, dict) else None
        if t is not None and (oldest is None or t < oldest):
            oldest = t
    return oldest


def absorb(dump: str) -> None:
    """The mirror takes what `dump` holds now (a whole picture once assembled, with what this
    folder's writes left, as page_db.keep_landed keeps it)."""
    if not dump or not os.path.isdir(dump):
        return
    plan = _read(os.path.join(dump, PLAN))
    if not isinstance(plan, dict) or not plan.get("assembled"):
        return
    root = mirror_dir()
    # The store's own numbers this folder knows go with its files (page_db's versions index):
    # laid back from the copy kept, a screen known by its stamp alone was taken for one no read
    # confirmed, every time (the review, 2026-11-11).
    import page_db
    known = page_db.listed_versions(dump)
    colls = MIRRORED + ("view", "chats", "locks")
    os.makedirs(root, exist_ok=True)
    page_db.index_versions(root, {k: v for k, v in known.items() if k.split("/")[0] in colls},
                           drop=[k for k in page_db.listed_versions(root) if k.split("/")[0] in colls])
    for coll in colls:
        src = os.path.join(dump, coll)
        dst = os.path.join(root, coll)
        if not os.path.isdir(src):
            # An empty collection leaves no folder: once assembled, the folder is the whole
            # truth, so the mirror holds nothing of it either.
            shutil.rmtree(dst, ignore_errors=True)
            continue
        tmp = dst + f".{os.getpid()}.new"
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            shutil.copytree(src, tmp)
            shutil.rmtree(dst, ignore_errors=True)
            os.replace(tmp, dst)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)


def keep_work(dump: str, ids) -> None:
    """The mirror takes `dump`'s own record of each work item in `ids`, unless it holds a newer
    one: a claim or a resume just made from that folder (as page_db.keep_landed left it), or
    the item as the chat just read it. A read of someone queued work reads is refused by what
    the mirror says (reading.queued_on_page), and only a planned read moved it on: the chat that
    claimed the work, or took it with `resume`, was refused its own read, and one finished
    since the mirror was read refused every later read of that person for good (the engine
    review, 2026-11-11). Nothing where this checkout keeps no copy of the page's work."""
    import page_db
    where = os.path.join(mirror_dir(), "work")
    if not dump or not os.path.isdir(where):
        return
    listed = page_db.listed_versions(dump)
    for wid in dict.fromkeys(str(w or "") for w in ids or ()):
        if not wid:
            continue
        stem = page_db.safe_id(wid)
        names = (stem.replace("~", "@") + ".json", stem + ".json")
        src = next((os.path.join(dump, "work", n) for n in names
                    if os.path.isfile(os.path.join(dump, "work", n))), "")
        got = _read(src) if src else None
        if not isinstance(got, dict):
            continue
        new = page_db._version_of(got)[1]
        olds = [os.path.join(where, n) for n in dict.fromkeys(names)
                if os.path.isfile(os.path.join(where, n))]
        had = [page_db._version_of(_read(p))[1] for p in olds]
        if isinstance(new, int) and any(isinstance(v, int) and v > new for v in had):
            continue
        try:
            for p in olds:
                os.remove(p)
            _write(os.path.join(where, names[0]), got)
        except OSError:
            continue
        key = "work/" + names[0][:-5]
        if isinstance(listed.get(key), int):
            page_db.index_versions(mirror_dir(), {key: listed[key]})
        else:
            page_db.index_versions(mirror_dir(), {}, drop=[key, "work/" + stem])


# A wake's folder is the code's to choose. Asked to name it short (`w1`), each fresh subagent
# chose `w1`: a second ring read into a folder holding the first one's finished wake
# (`.wake.json` saying done), so `wake` sent nothing and never applied the tap, and the first
# read's versions mark (`.versions.json`) stood for the new read (the review of 2026-11-11,
# E-18 and E-6). So `reads --in <a folder>` makes the next free `w<n>` there and names it, and
# a read is never planned into a folder that holds anything: it goes into a fresh one beside
# it, named the same way.
FRESH_STEM = "w"


def fresh(parent: str, stem: str = FRESH_STEM, start: int = 1) -> str:
    """A new, empty folder `<parent>/<stem><n>`, the lowest n from `start` that is free, made
    now (two chats at once never get the same one)."""
    os.makedirs(parent, exist_ok=True)
    n = max(1, int(start))
    while True:
        path = os.path.join(parent, f"{stem}{n}")
        try:
            os.mkdir(path)
            return path
        except FileExistsError:
            n += 1


def used(folder: str) -> bool:
    """Does `folder` hold anything (an earlier read, wake or job)?"""
    try:
        return bool(os.listdir(folder))
    except OSError:
        return False


def fresh_beside(folder: str) -> str:
    """A new folder beside `folder`, which is in use: a short name the code made with the next
    free number (`w1` to `w2`), any other name with `.2`, `.3`... after it (`page-data` to
    `page-data.2`, a job's `j-draft-r9-3` to `j-draft-r9-3.2`, never another job's name)."""
    folder = os.path.abspath(folder.rstrip("/\\") or folder)
    name = os.path.basename(folder) or FRESH_STEM
    m = re.fullmatch(rf"({re.escape(FRESH_STEM)})(\d+)", name) or re.fullmatch(r"(.+\.)(\d+)", name)
    if m:
        return fresh(os.path.dirname(folder), m.group(1), int(m.group(2)) + 1)
    return fresh(os.path.dirname(folder), name + ".", 2)


JOB_MARK = ".job.json"                # in a job's folder: the run its first command began


def job_folder(work: str) -> str:
    """The name of a job's own folder, after its work id: each job of a chat its own, so a job
    chat's second job never reads into the first one's (the release review, 2026-11-03)."""
    return "j-" + (re.sub(r"[^A-Za-z0-9_-]+", "-", str(work or "")).strip("-")[:60] or "job")


def job_begun(folder: str, work: str, chat: str, now: dt.datetime | None = None) -> str:
    """A job's first command over its folder: "" when the folder is this run's own (its mark
    written now), else a fresh folder beside it, made now, for the read again: the folder holds
    an earlier run's read, whose state and versions would stand for this one."""
    mark = os.path.join(folder, JOB_MARK)
    if os.path.exists(mark):
        return fresh_beside(folder)
    _write(mark, {"work": str(work), "chat": str(chat or ""), "at": _stamp(now or _now())})
    return ""


def plan(dump: str, now: dt.datetime | None = None, full: bool = False,
         rev: int | None = None) -> dict:
    """{"nothing": True} when the ring's revision was read already; else {"full": why or "",
    "cursor": stamp or None, "queries": [{collection, query}], "dump": the folder it goes
    into}, kept in that folder for assemble. A `dump` that holds anything is never read into
    (an earlier wake's state and versions would stand for this one): the read goes into a
    fresh folder beside it, and "moved_from" names the one asked for."""
    now = now or _now()
    moved = ""
    if used(dump):
        moved, dump = dump, fresh_beside(dump)
    meta = _meta()
    last = meta.get("last_dump")
    if last and os.path.abspath(str(last)) != os.path.abspath(dump):
        absorb(str(last))
    url = _url()
    why = "asked" if full else full_due(meta, now, url)
    if rev is not None and not why and isinstance(meta.get("rev"), int) and rev <= meta["rev"]:
        return {"nothing": True, "rev": rev}
    queries: list[dict] = []
    cursor = None
    if why:
        for coll in FULL_READS:
            queries.append({"collection": coll, "query": {"limit": LIMIT}})
    else:
        read_at = _time(meta.get("read_at")) or now
        waiting = _oldest_waiting(mirror_dir())
        start = min(t for t in (read_at, waiting) if t is not None)
        cursor = _stamp(start - dt.timedelta(seconds=CLOCK_SLACK_S))
        for coll in WHOLE:
            queries.append({"collection": coll, "query": {"limit": LIMIT}})
        queries += [
            {"collection": "actions", "query": {"limit": LIMIT, "where": [["at", ">=", cursor]]}},
            {"collection": "receipts",
             "query": {"limit": LIMIT, "where": [["applied_at", ">=", cursor]]}},
            {"collection": "work",
             "query": {"limit": LIMIT, "where": [["status", "not-in", list(FINISHED)]]}},
            {"collection": "work",
             "query": {"limit": LIMIT, "where": [["finished_at", ">=", cursor]]}},
            {"collection": "work",
             "query": {"limit": LIMIT, "where": [["asked_at", ">=", cursor]]}},
        ]
    os.makedirs(dump, exist_ok=True)
    _write(os.path.join(dump, PLAN), {"full": why, "cursor": cursor, "at": _stamp(now),
                                      "url": url, "queries": queries})
    if rev is not None:
        meta["rev"] = max(int(meta.get("rev") or 0), int(rev))
        _save_meta(meta)
    return {"full": why, "cursor": cursor, "queries": queries, "dump": dump,
            **({"moved_from": moved} if moved else {})}


def seen_rev(rev: int) -> bool:
    """Was the page at revision `rev` (or later) read already? A new one is kept as seen: the
    ring that named it is being passed on now."""
    meta = _meta()
    have = meta.get("rev")
    if isinstance(have, int) and rev <= have:
        return True
    meta["rev"] = int(rev)
    _save_meta(meta)
    return False


def _fields(path: str) -> dict:
    got = _read(path)
    if isinstance(got, dict) and isinstance(got.get("data"), dict):
        return got["data"]
    return got if isinstance(got, dict) else {}


def _before(value, cursor: str) -> bool:
    """Was this record's time before the cursor (so the read could not have seen it)?"""
    t = _time(value)
    c = _time(cursor)
    return t is not None and c is not None and t < c


def _keep_from_mirror(coll: str, fields: dict, cursor: str) -> bool:
    """Would the read have returned this record had it still been there? If so, and it was
    not returned, it is gone (or changed past what the mirror knows): never laid back."""
    if coll == "actions":
        return _before(fields.get("at"), cursor)
    if coll == "receipts":
        return _before(fields.get("applied_at"), cursor)
    if coll == "work":
        return (str(fields.get("status") or "") in FINISHED
                and _before(fields.get("finished_at") or fields.get("asked_at"), cursor)
                and (not fields.get("asked_at") or _before(fields.get("asked_at"), cursor)))
    return True


def _now_doc(folder: str) -> dict:
    for name in ("now.json", "current.json"):
        got = _fields(os.path.join(folder, "meta", name))
        if got:
            # Neither number is the record: the stamp, and the store's own version a read
            # keeps beside the fields (page_db.keep_listed), which a write never carries.
            return {k: v for k, v in got.items() if k not in ("_v", "__version__")}
    return {}


def drawn_here(dump: str, root: str) -> bool:
    """Is the page's revision (`meta/now`, just read) the one the mirror holds, so nobody
    drew the screens since this checkout last read or drew them?"""
    fresh, mine = _now_doc(dump), _now_doc(root)
    return bool(mine) and fresh == mine


def assemble(dump: str, now: dt.datetime | None = None) -> dict:
    """Lay the mirror under what was read into `dump` (once), then keep the result as the
    mirror. {"full": bool, "read": n records read, "kept": n laid from the mirror}."""
    now = now or _now()
    path = os.path.join(dump, PLAN)
    p = _read(path)
    if not isinstance(p, dict):
        return {}
    read = sum(len([n for n in os.listdir(os.path.join(dump, c)) if n.endswith(".json")])
               for c in os.listdir(dump) if os.path.isdir(os.path.join(dump, c)))
    if p.get("assembled"):
        return {"full": bool(p.get("full")), "read": p.get("read", read),
                "kept": p.get("kept", 0)}
    kept = 0
    import page_db
    laid_known: dict = {}
    laid: set = set()
    if not p.get("full"):
        cursor = str(p.get("cursor") or "")
        root = mirror_dir()
        mirror_known = page_db.listed_versions(root)
        colls = ("actions", "receipts", "work")
        # The screens as this checkout last read or drew them stand only while nobody else
        # drew since: `meta/now` (read whole every time) names who drew last. Another chat's
        # drawing means the kept screens are old, and laying them would let a page update
        # write over a newer one: `view` asks for them to be read instead.
        if drawn_here(dump, root):
            colls += KEPT + ("view",)
        else:
            p["need"] = list(KEPT)
        for coll in colls:
            src = os.path.join(root, coll)
            if not os.path.isdir(src):
                continue
            dst = os.path.join(dump, coll)
            for name in os.listdir(src):
                if not name.endswith(".json") or os.path.exists(os.path.join(dst, name)):
                    continue
                if coll not in KEPT and coll != "view" and \
                        not _keep_from_mirror(coll, _fields(os.path.join(src, name)), cursor):
                    continue
                os.makedirs(dst, exist_ok=True)
                shutil.copy(os.path.join(src, name), os.path.join(dst, name))
                kept += 1
                if coll in KEPT + ("view",):
                    laid.add(coll)
                stem = f"{coll}/{name[:-5]}"
                if stem in mirror_known:
                    laid_known[stem] = mirror_known[stem]
    if laid_known:
        page_db.index_versions(dump, laid_known)
    p.update({"assembled": True, "read": read, "kept": kept, "laid": sorted(laid)})
    _write(path, p)
    meta = _meta()
    meta.update({"url": p.get("url") or meta.get("url"), "read_at": p.get("at"),
                 "last_dump": os.path.abspath(dump)})
    if p.get("full"):
        meta["full_at"] = p.get("at")
        meta.pop("full_next", None)
    _save_meta(meta)
    absorb(dump)
    return {"full": bool(p.get("full")), "read": read, "kept": kept}


def screens_read(dump: str) -> bool:
    """Were the page's screens read into this dump just now (a whole read, asked for by name,
    or read again when asked), so a screen it lacks is truly not on the page? Not when they
    were laid from the mirror, or asked for and never read: then a write to one with no
    version is refused. A folder made by hand, with no plan, was read by the chat itself."""
    p = _read(os.path.join(dump, PLAN))
    if not isinstance(p, dict) or p.get("full"):
        return True
    here = os.path.isdir(os.path.join(dump, "screen"))
    asked = {str((q or {}).get("collection") or "") for q in p.get("queries") or ()}
    if "screen" in asked:
        return True
    if any(c in (p.get("laid") or ()) for c in ("screen", "view")):
        return False
    return here and ("screen" in (p.get("need") or ()) or bool(p.get("screens_reread")))


def read_screens_again(dump: str) -> bool:
    """Mark the screens to be read whole into `dump` (once): a page update found screens it
    would write with no version while they came from the mirror. True when marked now."""
    path = os.path.join(dump, PLAN)
    p = _read(path)
    if not isinstance(p, dict) or p.get("screens_reread"):
        return False
    for coll in ("screen", "view"):
        shutil.rmtree(os.path.join(dump, coll), ignore_errors=True)
    p.update({"screens_reread": True, "laid": [c for c in p.get("laid") or ()
                                               if c not in ("screen", "view")]})
    _write(path, p)
    return True


NEED_SCREENS = ("view: another chat drew the page since this copy last did, so its screens are "
                "read now: ArtifactData query, collections {colls}, url <the page>, limit 1000, "
                "out_dir \"{dump}\" (the same folder; never list or open what they save), {keep}then "
                "run this again.")


SCREENS_AGAIN = ("view: the copy this checkout keeps of the page lacks a screen the page holds, so "
                 "its screens are read now: ArtifactData query, collection screen, url {url}, "
                 "limit 1000, out_dir \"{dump}\" (the same folder; never list or open what they "
                 "save), {keep}then run this again.")


LATE = ("view: before this batch ends, read what came in while the work ran (taps and work "
        "asked for since this wake's read), so a tap made meanwhile is applied now, never left "
        "for the person's next message: ArtifactData query, each of these in one message, url "
        "{url}, out_dir \"{dump}\" (the same folder; never list or open what they save), {keep}then "
        "run this same command again: {queries}")


def keep_step(dump: str) -> str:
    """"<keep the read's versions>, " for a read into a folder already read, where the app's
    hook did not keep that first read's versions (page_db.after_read), else ""."""
    import page_db
    keep = page_db.after_read(dump)
    return keep[len("then "):] + ", " if keep else ""


def late_queries(dump: str, now: dt.datetime | None = None) -> list[dict]:
    """The reads that end a batch of the page's work (`app.py view --end`): the taps,
    receipts and work asked for since this folder's read, by the same cursor a wake reads by.
    Seven "I sent it" taps made while the helper answered another question waited for the
    person's next message: only a wake's start read taps (the maintainer's copy, 2026-11-05).
    Asked once a folder, and again only after `late_handled(again=True)`; [] when the folder
    was not read by `plan` or the reads were asked already."""
    now = now or _now()
    path = os.path.join(dump, PLAN)
    p = _read(path)
    if not isinstance(p, dict) or not p.get("assembled") or p.get("late_asked"):
        return []
    since = _time(p.get("late_from") or p.get("at")) or now
    cursor = _stamp(since - dt.timedelta(seconds=CLOCK_SLACK_S))
    queries = [
        {"collection": "actions", "query": {"limit": LIMIT, "where": [["at", ">=", cursor]]}},
        {"collection": "receipts",
         "query": {"limit": LIMIT, "where": [["applied_at", ">=", cursor]]}},
        {"collection": "work", "query": {"limit": LIMIT, "where": [["asked_at", ">=", cursor]]}},
    ]
    p.update(late_asked=_stamp(now), late_cursor=cursor)
    p.pop("late_done", None)
    _write(path, p)
    return queries


def say_late(queries: list[dict], dump: str, url: str) -> str:
    return LATE.format(url=url, dump=dump, keep=keep_step(dump), queries=" ".join(
        json.dumps(q, separators=(",", ":")) for q in queries))


def late_read(dump: str) -> bool:
    """Were the reads that end a batch asked for in this folder, and not handled yet?"""
    p = _read(os.path.join(dump, PLAN))
    return isinstance(p, dict) and bool(p.get("late_asked")) and not p.get("late_done")


def late_handled(dump: str, again: bool = False, ids=(), chat: str = "",
                 now: dt.datetime | None = None) -> None:
    """The late reads are applied. `again`: work came in with them, which this chat takes
    before ending, so the next end of the batch reads once more, from when these were asked;
    the work named (`ids`, for `chat`) is kept as waiting until an end finds none, so the
    chat that answers the page is held at its turn's end while it waits (`late_waiting`)."""
    path = os.path.join(dump, PLAN)
    p = _read(path)
    if not isinstance(p, dict):
        return
    if again:
        p["late_from"] = p.get("late_asked")
        p.pop("late_asked", None)
        p["late_waiting"] = {"ids": [str(i) for i in ids], "chat": str(chat or ""),
                             "at": _stamp(now or _now())}
    else:
        p["late_done"] = True
        p.pop("late_waiting", None)
    _write(path, p)


# The hold lasts this long after the work was named: past it, the next ring or brief takes it.
LATE_HOLD_S = 2 * 3600


def late_waiting(chat: str, now: dt.datetime | None = None) -> list[str]:
    """The work a pass of the page's helper named at its end and never took (`late_handled`),
    in the folder the last wake read (the mirror's `last_dump`), for `chat`, named in the last
    LATE_HOLD_S and not held for yet. A pass that ended with two follow-ups named left them
    on "starts in a moment" until a pass was started by hand (the maintainer's copy,
    2026-11-05): the chat's turn is held once for them, as land.py's WANTED_FILE has the
    running save take a save asked for meanwhile. [] when there is none."""
    dump = str(_meta().get("last_dump") or "")
    p = _read(os.path.join(dump, PLAN)) if dump else None
    if not isinstance(p, dict) or p.get("late_done"):
        return []
    w = p.get("late_waiting")
    if not isinstance(w, dict) or w.get("held") or not chat or str(w.get("chat") or "") != chat:
        return []
    at = _time(w.get("at"))
    if at is None or ((now or _now()) - at).total_seconds() > LATE_HOLD_S:
        return []
    return [str(i) for i in w.get("ids") or [] if i]


def late_held() -> None:
    """The turn was held once for the work `late_waiting` named: never again for it."""
    dump = str(_meta().get("last_dump") or "")
    path = os.path.join(dump, PLAN) if dump else ""
    p = _read(path) if path else None
    if isinstance(p, dict) and isinstance(p.get("late_waiting"), dict):
        p["late_waiting"]["held"] = True
        _write(path, p)


def needs(dump: str) -> list[str]:
    """The kept collections a page update must read into `dump` first: those assemble did
    not lay (another chat drew since) and the folder does not hold yet."""
    path = os.path.join(dump, PLAN)
    p = _read(path)
    if not isinstance(p, dict) or p.get("need_asked"):
        return []                   # asked once: an empty collection leaves no folder
    need = [c for c in p.get("need") or [] if not os.path.isdir(os.path.join(dump, c))]
    if need:
        p["need_asked"] = True
        _write(path, p)
    return need


def partial(dump: str) -> bool:
    """Was this folder read in part (the rest laid from the mirror)?"""
    p = _read(os.path.join(dump, PLAN))
    return isinstance(p, dict) and not p.get("full")


# What follows the reads in a step that brings the page up to date (`app.py reads --for-view`),
# in place of a wake: the step that asked for them names its own view.
FOR_VIEW = ("then go on with the step that asked for this read, with the folder these reads go "
            "into as --dump")


def say_plan(got: dict, dump: str, url: str, then: str = "") -> str:
    """The reads, in a few lines: one ArtifactData query each, all in one message. `then`:
    what follows them, when it is not a wake (FOR_VIEW)."""
    if got.get("nothing"):
        return ("reads: nothing new since this revision was read: no read and no wake; "
                "resolve the ring and end.")
    # No versions step before a wake: whether this chat's hook keeps them shows only once the
    # read is in, and `wake` asks for them then, where it did not (page_db.unkept; E-6). A read
    # for a page update (`then`) is followed by `app.py view`, which only says so after it has
    # pinned its writes (PE-2): there the step is named where this copy registers no hook.
    import page_db
    dump = got.get("dump") or dump
    keep = page_db.after_read(dump, fresh_chat=True) if then else ""
    if got.get("moved_from"):
        where = [f"reads: {got['moved_from']} holds an earlier read, so this one goes into a "
                 f"fresh folder: $D is {dump} from here on, wherever a step names the other."]
    elif got.get("chosen"):
        where = [f"reads: this read's own folder: $D is {dump} from here on."]
    else:
        where = []
    wake = (f"then python3 tools/app.py wake \"{dump}\"" if where
            else "then python3 tools/app.py wake with the same folder")
    head = ("reads: " + (f"a whole read ({got['full']})" if got.get("full")
                         else f"what changed since {got['cursor']}") +
            f". ArtifactData query, each of these in one message, url {url}, out_dir \"{dump}\" "
            "(never list or open what they save), " + (keep + ", " if keep else "") +
            (then or wake) + ":")
    return "\n".join(where + [head] + [json.dumps(q, separators=(",", ":"))
                                       for q in got["queries"]])


def summary(db: dict, chat: str, got: dict) -> str:
    """One line of what the read holds that needs doing: counts and the ids, never the
    records themselves."""
    receipts = db.get("receipts") or {}
    taps = sorted(a for a in (db.get("actions") or {}) if a not in receipts)
    waiting = sorted(w for w, d in (db.get("work") or {}).items()
                     if str((d.get("data") or {}).get("status") or "") == "queued")
    ids = lambda xs: (": " + ", ".join(xs[:6]) + (" ..." if len(xs) > 6 else "")) if xs else ""  # noqa: E731
    return (f"read: {got.get('read', 0)} record(s) read"
            + (f", {got['kept']} kept from the last read" if got.get("kept") else "")
            + f"; {len(taps)} tap(s) waiting{ids(taps)}; {len(waiting)} item(s) queued{ids(waiting)}.")
