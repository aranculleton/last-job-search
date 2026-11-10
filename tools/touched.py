#!/usr/bin/env python3
"""What a piece of work changed on the page, and the buttons its answer carries there.

A Chat answer used to paste the whole result (a drafted reply, a note, a list) or say "it's in
Contacts", and the person went looking for it (the maintainer, 2026-11-10). Now every command
that writes a record the page shows notes it here, as a place on the page and the id there,
and `app.py done` turns what its work wrote into the answer's buttons ("Updated in Contacts",
"Ready in Jobs"), each opening that exact card. No chat types a button, and an answer that
changed nothing has none.

    python3 tools/touched.py note <section> <id> [--work W]    noted by hand (rarely needed)
    python3 tools/touched.py list [--work W]                     what is noted, not yet taken

The record is this checkout's own (`ljs-touched.json` in its git folder, never committed), one
row a change: {section, id, work, chat, at}. A row with no work belongs to the work this chat
is running: `done` takes the rows its work names, and this chat's rows written since it began
that work, then clears them. A row older than two days is dropped.

A place on the page is written `page:<section>/<id>`; the page understands it, never shows it
as an address, and opens the card in place (templates/app/app.js `openPage`). Several jobs are
one button, `page:jobs/<id>,<id>`, each marked; every other change is a button of its own.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Each place a change lands, the words of its button, in the page's own names for its screens
# (Drafts are shown in Jobs, interviews in Coming up, the profile is "Your profile"). The one
# home of these words: the page draws what is stored and never makes its own.
SECTIONS = {
    "contacts": "Updated in Contacts",
    "jobs": "Updated in Jobs",
    "drafts": "Ready in Jobs",
    "interviews": "Ready in Coming up",
    "you": "Updated in Your profile",
    "work": "Running in Claude's work",
}
# Many of one kind that are one button: a search's twenty jobs are one "Updated in Jobs" with
# each marked, never four buttons and "and 16 more".
GROUPED = ("jobs",)
MOST = 4                                # buttons on one answer; the rest are "and N more"
PREFIX = "page:"
FILE = "ljs-touched.json"
KEEP_S = 2 * 24 * 3600
# An answer that pastes what is now on a card: longer than this, with a button to the card,
# it is refused unless the person asked to see it in the thread (`--in-thread`).
THREAD_WORDS = 60


def address(section: str, ids=()) -> str:
    """`page:<section>/<id>[,<id>]`, each id quoted so a comma or a slash in it stays its own."""
    ids = [str(i) for i in ids or () if str(i)]
    return PREFIX + section + ("/" + ",".join(urllib.parse.quote(i, safe="") for i in ids)
                               if ids else "")


def parse(addr: str) -> tuple[str, list[str]] | None:
    """(section, ids) of a page address, or None for anything else."""
    addr = str(addr or "").strip()
    if not addr.startswith(PREFIX):
        return None
    section, _, rest = addr[len(PREFIX):].partition("/")
    if section not in SECTIONS:
        return None
    return section, [urllib.parse.unquote(x) for x in rest.split(",") if x]


def clean(section: str, item: str = "") -> tuple[str, str]:
    """(section, id) checked: ValueError, in plain words, for a section the page has not."""
    section = str(section or "").strip().lower()
    if section not in SECTIONS:
        raise ValueError(f"{section!r} is not a place on the page: one of {', '.join(SECTIONS)}")
    return section, " ".join(str(item or "").split())


def from_arg(raw: str) -> tuple[str, str]:
    """`--touched section:id` (or a page address) as (section, id)."""
    raw = str(raw or "").strip()
    got = parse(raw)
    if got:
        return got[0], (got[1] or [""])[0]
    section, _, item = raw.partition(":")
    return clean(section, item)


def buttons(touched) -> list[dict]:
    """What an answer carries for what its work changed: [{label, to}], one a change (the jobs
    together), at most MOST, then "and N more" opening the place with the most changes."""
    seen, order = set(), []
    for section, item in touched or ():
        section, item = clean(section, item)
        if (section, item) not in seen:
            seen.add((section, item))
            order.append((section, item))
    if not order:
        return []
    entries: list[tuple[str, list[str]]] = []
    for section, item in order:
        if section in GROUPED:
            hit = next((e for e in entries if e[0] == section), None)
            if hit:
                if item:
                    hit[1].append(item)
                continue
        entries.append((section, [item] if item else []))
    out = [{"label": SECTIONS[s], "to": address(s, ids)} for s, ids in entries[:MOST]]
    rest = len(entries) - MOST
    if rest > 0:
        tally: dict[str, int] = {}
        for section, _ in order:
            tally[section] = tally.get(section, 0) + 1
        busiest = max(tally, key=lambda s: (tally[s], -list(tally).index(s)))
        out.append({"label": f"and {rest} more", "to": address(busiest)})
    return out


def pasted(reply: str, made: list, in_thread: bool = False) -> str:
    """Why an answer may not go in the thread as written, or "": with a button to where the
    change is, the answer is a line or two saying what changed, never the thing itself pasted
    (a drafted reply, a resume, a list of jobs), unless the person asked to see it there."""
    if in_thread or not made:
        return ""
    words = len(str(reply or "").split())
    if words <= THREAD_WORDS:
        return ""
    return (f"the answer is {words} words and pastes what its button opens: say in a line or two "
            "what changed (the button takes them there), or give --in-thread when they asked to "
            "see it in the thread")


# ------------------------------------------------------------------ the record


def _path() -> str:
    import app_listen
    return app_listen.checkout_file(FILE)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _stamp(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _when(s) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(str(s or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def load() -> list[dict]:
    try:
        with open(_path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return []
    return [r for r in got if isinstance(r, dict)] if isinstance(got, list) else []


def _save(rows: list[dict]) -> None:
    import app_listen
    path = _path()
    cut = _now() - dt.timedelta(seconds=KEEP_S)
    rows = [r for r in rows if (_when(r.get("at")) or _now()) > cut]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
    app_listen._replace(tmp, path)


def _chat(chat: str = "") -> str:
    import app_listen
    return app_listen.this_chat(chat)


def note(section: str, item: str = "", work: str = "", chat: str = "",
         now: dt.datetime | None = None) -> dict:
    """Keep one change for the answer of the work that made it. Never stops the command that
    made the change: a record it cannot write is a button fewer, nothing more."""
    section, item = clean(section, item)
    row = {"section": section, "id": item, "work": _wid(work), "chat": _chat(chat),
           "at": _stamp(now or _now())}
    try:
        _save(load() + [row])
    except OSError:
        pass
    return row


def _wid(work) -> str:
    """A work id however it was given: a dump's file names write ~ as @ (page_db.load)."""
    return str(work or "").strip().replace("@", "~")


def _mine(row: dict, work: str, chat: str, since: dt.datetime | None) -> bool:
    if str(row.get("work") or ""):
        return _wid(row["work"]) == _wid(work)
    if str(row.get("chat") or "") != chat:
        return False
    at = _when(row.get("at"))
    return since is None or (at is not None and at >= since)


def gather(work: str, item: dict | None = None, chat: str = "") -> tuple[list, list]:
    """(the changes `work` made, the rows they came from): rows naming it, and this chat's
    unnamed rows since it began it (its claim, else when it was asked)."""
    item = item or {}
    since = _when(item.get("claimed_at") or item.get("asked_at"))
    chat = _chat(chat)
    rows = [r for r in load() if _mine(r, str(work or ""), chat, since)]
    return [(str(r.get("section") or ""), str(r.get("id") or "")) for r in rows
            if str(r.get("section") or "") in SECTIONS], rows


def clear(rows) -> None:
    """Take rows `gather` returned out of the record, once their answer is written."""
    rows = list(rows or ())
    if not rows:
        return
    gone = [json.dumps(r, sort_keys=True) for r in rows]
    try:
        _save([r for r in load() if json.dumps(r, sort_keys=True) not in gone])
    except OSError:
        pass


def page_links(links) -> tuple[list, list]:
    """`done --link` values split: (page places as changes, the rest as links)."""
    places, rest = [], []
    for x in links or ():
        got = parse(str((x or {}).get("url") or ""))
        if got:
            places.extend((got[0], i) for i in (got[1] or [""]))
        else:
            rest.append(x)
    return places, rest


# ------------------------------------------------------------------ where each record is on the page


def draft_ids(pairs, tracker=None) -> list[str]:
    """The page's ids of the drafts for (company, role) pairs, as Jobs and its drafts name them
    (app_model.tracker_ids): `app-<employer>_<role>`."""
    import app_model
    import person
    if tracker is None:
        import csv_store
        tracker = csv_store.tracker(person.state("job_search_tracker.csv"), refuse=False)
    ids = app_model.tracker_ids(tracker)
    want = {(_k(c), _k(r)) for c, r in pairs}
    out = []
    for row, rid in zip(tracker, ids):
        if (_k(row.get("company")), _k(row.get("role"))) in want and rid not in out:
            out.append(rid)
    return out


def tweak_place(target: dict) -> tuple[str, str] | None:
    """Where a change asked with a card's pencil lands (its work's `target`), as the page's own
    `workPlace` reads it: a message on its person's card, a pack on its interview, the job list
    in Jobs, and a resume or a letter on its draft. None for the Brief, which has no card."""
    t = target if isinstance(target, dict) else {}
    out, item = str(t.get("output") or ""), str(t.get("id") or "")
    if out == "message":
        return "contacts", str(t.get("contact") or "") or item
    if out in ("prep", "interview"):
        return "interviews", item
    if out == "jobs":
        return "jobs", ""
    if out == "brief":
        return None
    return "drafts", item


def interview_id(rid: str) -> str:
    """An application's interview on Coming up, from its tracker id."""
    return "int-" + rid[4:] if rid.startswith("app-") else rid


def _k(s) -> str:
    return " ".join(str(s or "").lower().split())


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("note", help="a change, kept for the answer of the work that made it")
    n.add_argument("section", choices=list(SECTIONS))
    n.add_argument("id", nargs="?", default="")
    n.add_argument("--work", default="")
    n.add_argument("--chat", default="")
    ls = sub.add_parser("list", help="what is noted and not yet taken")
    ls.add_argument("--work", default="")
    a = ap.parse_args(argv)
    if a.cmd == "note":
        note(a.section, a.id, work=a.work, chat=a.chat)
        print(f"touched: kept for its answer: {SECTIONS[a.section]}")
        return 0
    rows = [r for r in load() if not a.work or str(r.get("work") or "") == a.work]
    print(json.dumps(rows, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
