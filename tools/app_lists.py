"""Lists show what is live; only finished history folds away (UX_DECISIONS, 2026-10-25).

The person: "Dont just hide everything. I dont expect to have to click show more or
immediately do filters." So the model embedded in the page carries every live thing
whatever its age (an application still open, a conversation going or a reply owed, a
draft not sent, an interview ahead) and the finished history inside its fold window:

    applications   closed or rejected ones for FOLD_DAYS["applications"] after their last word
    people         contacts who never replied for 60 days after the last message; the rest of
                   the book (people not written to yet) by recency, up to PEOPLE_BYTES
    ready          what was sent, for 14 days (so a tick can be undone where it was made)
    interviews     past ones for 14 days after the last stage
    work           finished work for a day (the page's own list, in its database)

Everything older is in the page's database for "Show": `app.py view` writes each list
whole as `view/list~<name>~<n>` documents, each under CHUNK_BYTES, every item cut to the
fields the page's filters read, never a contact detail. `lists.<name>` in the model says
what each list holds: how many in all, how many embedded, how many folded and after how
many days, how many documents hold the whole list, and the count of every filter value
over the whole list, so a filter chip shows its count before anything is fetched.
"""
from __future__ import annotations

import datetime as dt
import json

FOLD_DAYS = {"applications": 30, "people": 60, "ready": 14, "interviews": 14, "work": 1}
# Each `view/list~...` document stays well under the database's 256 KiB a document.
CHUNK_BYTES = 200_000
# The embedded people beyond the live ones, by recency, until their JSON reaches this.
PEOPLE_BYTES = 150_000
# Filter chips over the whole list, by field; an employer list keeps its most common.
FILTERS = {
    "jobs": ("status", "remote", "band", "pay", "posted"),
    "applications": ("status", "employer", "applied"),
    "people": ("status", "route", "employer", "contacted", "replied"),
    "ready": ("status",),
    "interviews": ("status", "past"),
}
VALUES_MAX = 40
DAYS = (7, 30, 90)
POSTED = (3, 7, 14)


def ago(day, today: dt.date) -> int | None:
    from dates import as_date
    d = as_date(day, iso_only=True) if day else None
    return None if d is None else (today - d).days


def bucket(days, edges=DAYS) -> str:
    """"7", "30", "90" (within that many days), "older", or "never"."""
    if days is None:
        return "never"
    for e in edges:
        if days <= e:
            return str(e)
    return "older"


def counts(items: list[dict], fields) -> dict:
    """{field: {value: how many}} over `items`, most common first, at most VALUES_MAX values
    a field (the rest summed under "other")."""
    out = {}
    for f in fields:
        got: dict = {}
        for it in items:
            v = it.get(f)
            for one in (v if isinstance(v, list) else [v]):
                key = "none" if one in (None, "") else str(one).lower() if isinstance(one, bool) \
                    else str(one)
                got[key] = got.get(key, 0) + 1
        ranked = sorted(got.items(), key=lambda kv: (-kv[1], kv[0]))
        top = dict(ranked[:VALUES_MAX])
        rest = sum(n for _, n in ranked[VALUES_MAX:])
        if rest:
            top["other"] = top.get("other", 0) + rest
        out[f] = top
    return out


def size(obj) -> int:
    return len(_COMPACT.encode(obj).encode("utf-8"))


_COMPACT = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))  # json.dumps's, made once


def stored(obj) -> int:
    """Its bytes as page_db.Writes stores it inside a part's `items` (indented, keys sorted,
    two levels in).

    Counted, not written out: json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True)
    is the one-line text (separators "," and ": ") with a line break and an indent before
    each item and each closing bracket of a list or object that is not empty, so its bytes
    are the one-line text's and those (`_layout`). Before Python 3.13 an indented dump is
    written in Python a value at a time, and a big search's lists took a tenth of a second
    to measure (2026-11-03)."""
    text = _SORTED.encode(obj)
    extra, lines = _layout(obj, 1) if isinstance(obj, (dict, list, tuple)) else (0, 0)
    return len(text.encode("utf-8")) + extra + 2 * (lines + 1) + 2


_SORTED = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ": "))


def _layout(obj, level: int) -> tuple[int, int]:
    """(the characters indent=1 adds inside `obj`, a container `level` deep, and its line
    breaks): before each of its n items a line break and `level` spaces, and before its
    closing bracket a line break and `level - 1`; an empty one stays "[]" or "{}"."""
    values = obj.values() if isinstance(obj, dict) else obj
    if not values:
        return 0, 0
    n = len(values)
    extra, lines = n * (1 + level) + level, n + 1
    for v in values:
        if isinstance(v, (dict, list, tuple)):
            e, b = _layout(v, level + 1)
            extra += e
            lines += b
    return extra, lines


def chunks(items: list[dict], limit: int = CHUNK_BYTES) -> list[list[dict]]:
    """`items` in order, cut into lists that stay under `limit` bytes as stored. Never empty:
    an empty list is one empty part, so the page always finds part 1."""
    out, part, used = [], [], 2
    for it in items:
        n = stored(it)
        if part and used + n > limit:
            out.append(part)
            part, used = [], 2
        part.append(it)
        used += n
    out.append(part)
    return out


def summary(name: str, full: list[dict], shown: int, folded: int | None = None) -> dict:
    return {"total": len(full), "shown": shown,
            "folded": {"count": len(full) - shown if folded is None else folded,
                       "days": FOLD_DAYS.get(name)},
            "parts": len(chunks(full)), "doc": f"list~{name}",
            "counts": counts(full, FILTERS.get(name, ()))}


def docs(full: dict, made_at: str, rev: str) -> list[tuple[str, dict]]:
    """(doc id, document) for every part of every whole list, for `view/`."""
    out = []
    for name, items in full.items():
        parts = chunks(items)
        for n, part in enumerate(parts, 1):
            out.append((f"list~{name}~{n}", {"list": name, "part": n, "parts": len(parts),
                                             "rev": rev, "made_at": made_at, "items": part}))
    return out


def stale(full: dict, view: dict) -> list[str]:
    """The `view/list~...` documents the database holds that the lists no longer fill: a
    list that shrank by a part, or one that is gone."""
    want = {doc_id for doc_id, _ in docs(full, "", "")}
    return sorted(d for d in (view or {}) if d.startswith("list~") and d not in want)


# ------------------------------------------------------------------ what relates to what

RELATED_MAX = 10


def link(model: dict) -> None:
    """In place: each job, draft, message, contact, interview, application, referral and due
    row carries `related`, the ids
    of the others in the model at the same employer ({section: [ids]}, people at most
    RELATED_MAX with `people_more` for the rest), and the same role's own links: a job's
    `draft` (its ready item), a draft's `job`, an interview's `draft`."""
    import person
    try:
        import throttle
        from company_key import key
    except person.NoProfile:
        return                  # no profile yet: every list is empty, nothing to link
    sections = (("jobs", (model.get("jobs") or {}).get("rows") or [], "company"),
                ("ready", model.get("ready") or [], "company"),
                ("messages", model.get("messages") or [], "employer"),
                ("people", model.get("people") or [], "employer"),
                ("interviews", model.get("interviews") or [], "company"),
                ("applications", model.get("applications") or [], "company"),
                ("referrals", model.get("referrals") or [], "company"),
                ("due", model.get("due") or [], "company"))
    index: dict = {}
    keys = {}
    for name, items, field in sections:
        for it in items:
            k = key(it.get(field) or "")
            keys[id(it)] = k
            if k:
                index.setdefault(k, {}).setdefault(name, []).append(it["id"])
    # Each list's ids as a set too, so a list the item is not in is copied whole, never read
    # an id at a time against its own: a big search's people, due rows and messages at one
    # employer made some 300,000 comparisons (2026-11-03).
    held = {(k, sec): set(ids) for k, there in index.items() for sec, ids in there.items()}
    for name, items, _field in sections:
        for it in items:
            k = keys[id(it)]
            there = index.get(k) or {}
            rel = {}
            for sec, ids in there.items():
                if sec == name and sec == "people":
                    continue            # a contact is not linked to every colleague
                others = [i for i in ids if i != it["id"]] if it["id"] in held[(k, sec)] \
                    else list(ids)
                if sec == "people" and len(others) > RELATED_MAX:
                    it["people_more"] = len(others) - RELATED_MAX
                    others = others[:RELATED_MAX]
                if others:
                    rel[sec] = others
            it["related"] = rel
    ready = model.get("ready") or []
    for job in (model.get("jobs") or {}).get("rows") or []:
        mine = [a for a in ready if keys[id(a)] == keys[id(job)]
                and throttle.same_title(a.get("role"), job.get("title"))]
        job["draft"] = mine[0]["id"] if mine else None
        for a in mine:
            a["job"] = job["id"]
    for a in ready:
        a.setdefault("job", None)
    ids = {a["id"] for a in ready}
    for i in model.get("interviews") or []:
        own = "app-" + i["id"][4:]
        i["draft"] = own if own in ids else None
