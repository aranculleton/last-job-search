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

Each item's links to the rest at its employer (`related`, `link`) are kept beside the items in
the database, in `view/links~<n>` records cut by employer (`apart`, `links_docs`), and the page
puts them back as it reads the items (issue 254).
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


# Where a whole list is cut: after an item whose own text says so, by its hash, with a chance in
# proportion to its size (about one cut each CHUNK_SPAN bytes), or where the next item would
# pass the limit. Cut wherever the size fell, one item grown by a line moved every later cut,
# and every part of the list went again (the second audit, 2026-11-10, D6). Cut only once a
# part held 48 KB, eight people put in at its start moved its cut, and the next, and every
# later part of the list went again for them (issue 254): a cut now rests on its item alone.
CHUNK_SPAN = 64_000


def _ends_chunk(item, n: int) -> bool:
    """Does `item` (`n` bytes as stored) end its part, by its own text alone?"""
    import hashlib
    text = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], 16) % CHUNK_SPAN < n


def chunks(items: list[dict], limit: int = CHUNK_BYTES) -> list[list[dict]]:
    """`items` in order, cut into lists that stay under `limit` bytes as stored, ending where
    an item says (_ends_chunk). Never empty: an empty list is one empty part, so the page
    always finds part 1."""
    out, part, used = [], [], 2
    for it in items:
        n = stored(it)
        if part and used + n > limit:
            out.append(part)
            part, used = [], 2
        part.append(it)
        used += n
        if _ends_chunk(it, n):
            out.append(part)
            part, used = [], 2
    if part or not out:
        out.append(part)
    return out


def part_rev(items: list) -> str:
    """What one part of a list holds, as a short hash of its items."""
    import hashlib
    text = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def summary(name: str, full: list[dict], shown: int, folded: int | None = None) -> dict:
    return {"total": len(full), "shown": shown,
            "folded": {"count": len(full) - shown if folded is None else folded,
                       "days": FOLD_DAYS.get(name)},
            "parts": len(chunks(full)), "doc": f"list~{name}",
            "counts": counts(full, FILTERS.get(name, ()))}


def docs(full: dict, made_at: str, rev: str, by_hold: bool = True) -> list[tuple[str, dict]]:
    """(doc id, document) for every part of every whole list, for `view/`. `by_hold` False: for
    a published page whose code is from before parts were joined by what each holds
    (app_page.joins_by_hold): every part under the page's `rev`, which that code joins by."""
    out = []
    for name, items in full.items():
        parts = chunks(items)
        # Each part's rev is what it holds, and every part lists them all (`revs`), so a part
        # left as it was joins with the ones written since (the page reads the newest's list).
        revs = [part_rev(part) for part in parts] if by_hold else [rev] * len(parts)
        for n, part in enumerate(parts, 1):
            out.append((f"list~{name}~{n}", {"list": name, "part": n, "parts": len(parts),
                                             "rev": revs[n - 1],
                                             **({"revs": revs} if by_hold else {}),
                                             "made_at": made_at, "items": part}))
    return out


def kept_as_they_are(docs_: list, views: dict, by_hold: bool = True) -> set:
    """The ids of the list parts `docs_` (from `docs`) that the store (`views`, as load() gives
    it) already holds as they would be written, so a page update leaves them. By what each
    holds, part by part (`unchanged`); for a page whose code joins parts by the newest's rev
    (`by_hold` False), a list's parts are left only all together, when every one holds the
    same items in a list of as many parts under one rev, and are otherwise written again."""
    def held(doc_id):
        got = (views or {}).get(doc_id)
        return got.get("data") if isinstance(got, dict) else None
    if by_hold:
        return {doc_id for doc_id, doc in docs_ if unchanged(held(doc_id), doc)}
    groups: dict = {}
    for doc_id, doc in docs_:
        groups.setdefault(doc["list"], []).append((doc_id, doc))
    out: set = set()
    for parts in groups.values():
        olds = [held(doc_id) for doc_id, _ in parts]
        if all(isinstance(o, dict) and not o.get("revs") and o.get("parts") == d["parts"]
               and o.get("items") == json.loads(json.dumps(d["items"], ensure_ascii=False))
               for o, (_, d) in zip(olds, parts)) and len({o.get("rev") for o in olds}) == 1:
            out.update(doc_id for doc_id, _ in parts)
    return out


def unchanged(held, doc: dict) -> bool:
    """Does the store already hold this part of a list (`held`, its fields) as `doc` would
    write it: the same items under the same rev, in a list of the same number of parts? A list
    that lost its last part with the rest as they were left every part it kept saying the old
    count, so the page looked for the part just taken off and its "Show" was empty until
    another part changed (the review of 2026-11-11, D6)."""
    return isinstance(held, dict) and held.get("rev") == doc["rev"] \
        and held.get("parts") == doc["parts"] \
        and held.get("items") == json.loads(json.dumps(doc["items"], ensure_ascii=False))


def stale(full: dict, view: dict) -> list[str]:
    """The `view/list~...` documents the database holds that the lists no longer fill: a
    list that shrank by a part, or one that is gone."""
    want = {doc_id for doc_id, _ in docs(full, "", "")}
    return sorted(d for d in (view or {}) if d.startswith("list~") and d not in want)


# ------------------------------------------------------------------ what relates to what

RELATED_MAX = 10
# The sections whose items carry `related`, and the field each names its employer by.
LINKED = (("jobs", "company"), ("ready", "company"), ("messages", "employer"),
          ("people", "employer"), ("interviews", "company"), ("applications", "company"),
          ("referrals", "company"), ("due", "company"))


def _linked_items(model: dict, name: str) -> list:
    got = model.get(name)
    if name == "jobs":
        got = (got or {}).get("rows") if isinstance(got, dict) else None
    return got if isinstance(got, list) else []


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
    sections = tuple((name, _linked_items(model, name), field) for name, field in LINKED)
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


# ------------------------------------------------------------------ the links, kept apart

# Each item's `related` names the others at its employer, so one new note there changed the
# record of every colleague, and those sit all through a long section: a page update after a
# "Find people" job of eight rewrote all 34 parts of a big People section, 3.2 MB in six
# batches (issue 254). The page's database keeps them apart from the items (`view/links~<n>`),
# each employer's in one record, so a change at an employer rewrites that record alone; the
# page puts them back on the items it reads (templates/app/app.js withLinks).
LINKS_PREFIX = "links~"
# What one record holds, about: a power of two of them, kept while each stays between a
# quarter of this and twice it, so a book that grows by a few people never moves every link.
LINKS_BYTES = 16_000
LINKS_MAX = 200_000             # one record never passes this (one employer with hundreds)


def apart(model: dict) -> tuple[dict, dict]:
    """(the model as the database keeps it: each linked item without `related` and
    `people_more`, {"<section>/<item id>": {"related": ..., "people_more": n}} for every item
    that had any). The model itself is left as it is."""
    stored = dict(model)
    links: dict = {}
    for name, _field in LINKED:
        items = _linked_items(model, name)
        if not items:
            continue
        out = []
        for it in items:
            if not isinstance(it, dict) or ("related" not in it and "people_more" not in it):
                out.append(it)
                continue
            rel = it.get("related")
            more = it.get("people_more")
            if rel or more:
                links[f"{name}/{it.get('id')}"] = {"related": rel or {},
                                                  **({"people_more": more} if more else {})}
            out.append({k: v for k, v in it.items() if k not in ("related", "people_more")})
        if name == "jobs":
            stored["jobs"] = dict(model["jobs"], rows=out)
        else:
            stored[name] = out
    return stored, links


def _employers(model: dict) -> dict:
    """{"<section>/<item id>": its employer's key} for every linked item of `model`."""
    from company_key import key as company_key
    out = {}
    for name, field in LINKED:
        for it in _linked_items(model, name):
            if isinstance(it, dict):
                out[f"{name}/{it.get('id')}"] = company_key(it.get(field) or "")
    return out


def links_docs(model: dict, links: dict, made_at: str, held: int = 0) -> list[tuple[str, dict]]:
    """(doc id, document) for the links `apart` took out: `links~<n>`, each employer's links in
    one record (the same one while the count of records holds), `held` the count the database
    has now (0: none). A record over LINKS_MAX goes on as `links~<n>~2` and so on."""
    import zlib
    if not links:
        return []
    employer = _employers(model)
    by_employer: dict = {}
    for item_key in links:
        by_employer.setdefault(employer.get(item_key, ""), []).append(item_key)
    total = size(links)
    n = held if held > 0 and LINKS_BYTES // 4 <= total / held <= 2 * LINKS_BYTES else 0
    if not n:
        n = 1
        while total / n > LINKS_BYTES:
            n *= 2
    buckets: dict = {}
    for emp, keys in by_employer.items():
        b = zlib.crc32(emp.encode("utf-8")) % n + 1
        buckets.setdefault(b, []).extend(keys)
    out = []
    for b in sorted(buckets):
        pieces: list[dict] = [{}]
        used = 0
        for item_key in sorted(buckets[b]):
            one = size({item_key: links[item_key]})
            if pieces[-1] and used + one > LINKS_MAX:
                pieces.append({})
                used = 0
            pieces[-1][item_key] = links[item_key]
            used += one
        for j, piece in enumerate(pieces, 1):
            doc_id = f"{LINKS_PREFIX}{b}" + (f"~{j}" if j > 1 else "")
            # `list` brings it to the page with the whole lists, whenever it was written
            # (templates/app/app.js: the store's lists and every record newer than the page).
            out.append((doc_id, {"list": "links", "of": n, "rev": part_rev([piece]),
                                 "made_at": made_at, "links": piece}))
    return out


def links_held(view: dict) -> int:
    """How many link records the database's `view` says it holds (their `of`), or 0."""
    for doc_id, got in (view or {}).items():
        data = got.get("data") if isinstance(got, dict) else None
        if doc_id.startswith(LINKS_PREFIX) and isinstance(data, dict) \
                and isinstance(data.get("of"), int) and data["of"] > 0:
            return data["of"]
    return 0


def links_unchanged(held, doc: dict) -> bool:
    """Does the store already hold this record of links (`held`, its fields) as `doc` writes it?"""
    return isinstance(held, dict) and held.get("of") == doc["of"] \
        and held.get("links") == json.loads(json.dumps(doc["links"], ensure_ascii=False))
