#!/usr/bin/env python3
"""The app's page and its chats: one command for each thing a chat does with the page.

    python3 tools/app.py model [--out F] [--today D] [--now T]   the view model, as JSON
    python3 tools/app.py view <out dir> [--dump DIR]             the model as view/* writes
    python3 tools/app.py page [--out F]                          the whole page, to publish
    python3 tools/app.py apply <dump dir> [--chat ID] [--claim]  the page's actions, applied
    python3 tools/app.py next <dump dir> --chat ID --kind cloud|computer [--claim-out DIR]
                                                                 [--no-sessions]: where it runs
    python3 tools/app.py pin <dump dir> --work ID --stage S [--line L] [--done N --total M]
                                         [--left-s S] [--log round.log] [--chat ID]
                                                                 progress, as it goes
    python3 tools/app.py pin <dump dir> --work ID --blocked      its own chat waits on the person
    python3 tools/app.py busy <dump dir> "<a few words>" | --done
                                                                 what this chat does in the chat
    python3 tools/app.py progress <kind of work>                 its stages and their seconds
    python3 tools/app.py check [--model F]                       the model against the contract
    python3 tools/app.py start [--on M] [--tools T] [--page URL] [--chat ID] [--listen]
                               [--work ID] [--dump DIR]          what this chat does next, in any
                                                                 state: set up, part-way, old, new
    python3 tools/app.py start --paste                           the line for a chat on a computer
    python3 tools/app.py page --out-dir D [--url U]              the page in parts, and the
         [--on-page FILE|-] [--whole]                            publishes that put it up (with
                                                                 a url: after listing its files)
    python3 tools/app.py published <url> [--parts D]|none [--why W]
                                                                 the page's address, once published
    python3 tools/app.py answer <step> [--text T] [--field k=v]  a setup answer given in the chat
    python3 tools/app.py listen <dump dir> --chat ID [--listen] [--helper] [--hand ID]
                                                                 is this chat the page's listener?
    python3 tools/app.py wake <dump dir> --chat ID [--on M] [--kind K] [--no-sessions]
                                                                 a ring, after one read: the day's
                                                                 check, the check-in, the taps and
                                                                 the next work, with the batches
    python3 tools/app.py republish <out dir>                     the page's own code changed: ask
                                                                 the listener to publish it
    python3 tools/app.py pinned yes|no                           their answer to pinning the page
    python3 tools/app.py resume-saved <file> [--asset ID]        the resume from the page, saved
    python3 tools/app.py files-saved <path> <asset id> [...]     a document put in the page's file store
    python3 tools/app.py propose "<role>"...                     the roles setup asks about
    python3 tools/app.py done <dump dir> --work ID --summary "<one sentence>"
                              [--reply-file F [--thread T]] [--failed "<why>"] [--link L]
                              [--chat ID]                        a finished item, in one batch
    python3 tools/app.py ask <dump dir> --kind K --title "<words>" [--args '<json>']
                             [--here]                            work queued from a chat message,
                                                                 or (--here) begun in this chat

`<dump dir>` is where ArtifactData's `out_dir` saved the page's database: `actions/`,
`receipts/`, `work/`, `locks/`, `chats/`, one JSON file a document. What a chat sends back
is always a batch file (a list of writes, each with a `file_path`), printed as a path, so
nothing passes through the conversation but the paths.

The model is CONTRACT.md section 1 (tools/app_model.py); the actions and their receipts are
tools/app_actions.py; the work list's rules (kinds, stages, claims, locks) are
tools/page_db.py; which one chat answers the page is tools/app_listen.py. Pure code: no
network, no model call, the same answer on every computer.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402


def _out(text: str, path: str | None) -> None:
    if path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(path)
    else:
        sys.stdout.write(text)


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def with_page_parts(model: dict) -> dict:
    """The parts of the page this file adds where the model does not carry them yet: who
    answers the page and the link that wakes one (`listener`), the footer's privacy line
    (`app.privacy`), and the brief's days, time and any break (`schedule`). Each only when
    absent, and the rev made again, so a model that grows them itself is left as it is."""
    import app_listen
    import app_model
    grew = False
    if "listener" not in model:
        model["listener"] = app_listen.model_part(str((model.get("person") or {}).get("repo")
                                                      or ""))
        grew = True
    if isinstance(model.get("app"), dict) and "privacy" not in model["app"]:
        model["app"]["privacy"] = app_listen.privacy()
        grew = True
    if "schedule" not in model:
        try:
            import routines
            model["schedule"] = routines.page_part()
            grew = True
        except Exception:  # noqa: BLE001  the page shows no brief row
            pass
    if grew:
        model["rev"] = app_model.model_rev(model)
    return model


def _build(today, now, **kw):
    import app_model
    model, got = app_model.build(today, now, **kw)
    return with_page_parts(model), got


def cmd_model(a) -> int:
    import app_model
    today, now = app_model.clock(a.today, a.now)
    model, _ = _build(today, now)
    _out(_dump(model), a.out)
    return 0


def _published() -> dict:
    """The page version last published and when, for meta/now: an open page whose own code is
    older reloads itself to it (templates/app/app.js, `newerPage`). Without it nothing ever
    told an open page a newer one was out (2026-11-02)."""
    try:
        import app_setup
        import build_versions
        rec = app_setup.page_record()
        return {"page": int(build_versions.recorded().get("page") or 0),
                "published_at": str(rec.get("published_at") or "")}
    except Exception:  # noqa: BLE001  no page record yet
        return {}


def fix_work(messages: list, have: dict, now) -> list:
    """(work id, fields) for each draft's fix not yet asked for: the tweak the page's own Fix it
    asked for until 2026-11-04, now queued by the engine (app_model.message_fix)."""
    import app_model
    import page_db
    out = []
    for m in messages:
        fix = m.get("fix") or {}
        wid = fix.get("work")
        if not wid or wid in have:
            continue
        mine = page_db.safe_id(f"tweak~{m['id']}~fix~")
        if sum(1 for k in have if k.startswith(mine)) >= app_model.FIX_TRIES["must" if fix.get("must") else "may"]:
            continue
        what = "note" if m.get("kind") == "first_note" else "message"
        target = {"id": m["id"], "output": "message", "rev": m.get("rev")}
        if m.get("employer"):
            target["company"] = m["employer"]
        if m.get("contact"):
            target["contact"] = m["contact"]
        out.append((wid, {"kind": "tweak", "title": f"Fix the {what} to {m.get('first_name') or 'them'}",
                          "to": "either", "args": {"v": 1, "target": target, "changes": [],
                                                   "text": fix["text"], "keep": None, "auto": True},
                          "asked_at": app_model.stamp(now), "asked_from": {"tab": "engine"},
                          "priority": 0, "status": "queued", "stage": 0, "stage_at": None,
                          "stages": [x for x in page_db.progress("tweak")["stages"]
                                     if "PDF" not in x["name"]],
                          "steps": [], "claimed_by": None, "claimed_at": None,
                          "stop_asked": False, "attempt": 1}))
    return out
def no_screen(dump: str, db: dict) -> str:
    """The line `view` stops with when its dump holds none of the page's `screen` documents
    while the page has some, else "". The page has them once it was drawn under the new
    names (`meta/current`, stored as `meta/now`); a page a 4.2 chat left (only `view`, and
    `meta/current` under its old name) and one never drawn have none yet, and their first
    view creates them (an empty collection leaves no folder in a dump, so a fresh page's has
    no meta either). Every set it printed went with no version, against documents that
    exist, and all 43 were refused (the maintainer's live run, 2026-11-05: a dump of the old
    `view` collection, left at version 3, and meta)."""
    import glob
    if glob.glob(os.path.join(dump, "screen", "*.json")):
        return ""
    cur = (db.get("meta") or {}).get("current") or {}
    if not (cur.get("data") and not cur.get("old")):
        return ""                                   # never drawn, or a 4.2 page: its first view
    return ("view: nothing was written: this folder holds no dump of the page's screen "
            "collection, where its view is kept (view is an old name), so every write would "
            "be refused. Read the page's screen, meta, addr and work collections into a fresh "
            "folder (ArtifactData query, one for each, out_dir that folder, limit 1000) and "
            "run this again with --dump that folder.")


def self_fixes(db: dict | None, model: dict, out_dir: str, now, dump_dir: str = "") -> list[str]:
    """The batches that queue, once each, what a draft on the page needs and Claude can do
    with no one asking: its remake where a check failed with a fix Claude makes (the checks
    alert's own `draft` work, its `redo`; never one the drafts rerun handed to the person,
    tools/remake_drafts.py's "todo"), and one `files` item for the drafts whose PDFs the page
    lacks that no files work has ever covered (page_db.queue_files). Each id is a create the
    store refuses twice, so a view run again queues nothing more."""
    import app_model
    import page_db
    if db is None:
        return []
    work = db.get("work") or {}
    try:
        import remake_drafts
        theirs = {c["app"] for c in remake_drafts.todo_cards()}
    except Exception:  # noqa: BLE001  no rerun record: none is the person's
        theirs = set()
    w = page_db.Writes(out_dir)
    for item in model.get("ready") or []:
        if item.get("status") != "drafted" or item.get("id") in theirs:
            continue
        for al in item.get("alerts") or []:
            act = al.get("action") or {}
            wid = page_db.safe_id(str(act.get("id") or ""))
            if al.get("kind") != "checks" or act.get("type") != "work" or act.get("kind") != "draft" \
                    or not wid or wid in work:
                continue
            w.add("set", "work", wid, page_db.queued("draft", act.get("title") or "",
                                                     dict(act.get("args") or {}, auto=True), now),
                  if_version=None)
    # A prep made for an earlier plan of rounds is updated by itself once the plan changes,
    # never waiting for an "Update it" tap (the maintainer, 2026-11-05): once a change, under
    # the prep's own work id, so the card shows it going. Work on its way, or one finished or
    # stopped since the plan changed, is left as it is.
    for iv in model.get("interviews") or []:
        prep = iv.get("prep") or {}
        if not prep.get("stale") or iv.get("past") or not iv.get("id"):
            continue
        wid = page_db.safe_id("prep~" + str(iv["id"]))
        have = work.get(wid) or {}
        d = have.get("data") or {}
        if d and (str(d.get("status") or "queued") not in page_db.FINISHED
                  or str(d.get("finished_at") or d.get("asked_at") or "") >= str(prep.get("stale_since") or "")):
            continue
        w.add("set", "work", wid, page_db.queued(
            "prep", f"Interview prep: {iv.get('company') or ''}, {iv.get('role') or ''}",
            {"interview": iv["id"], "note": None, "auto": True}, now),
            if_version=have.get("version") if have else None)
    out = w.save("self") if w.entries else []
    ever = set()
    for d in work.values():
        x = d.get("data") or {}
        if x.get("kind") == "files":
            args = x.get("args") if isinstance(x.get("args"), dict) else {}
            ever |= {str(i) for i in args.get("applications") or []} | {str(args.get("application") or "")}
    missing = [x for x in app_model.files_missing() if str(x.get("id") or "") not in ever]
    if missing:
        q = page_db.queue_files(db, missing, now, os.path.join(out_dir, "files"), dump_dir=dump_dir)
        if q:
            out = out + list(q["batches"])
    return out


def cmd_view(a) -> int:
    """The model as one document a section (`view/<section>`, in parts when it is too big for
    one: page_db.split) plus `meta/current` (stored as `meta/now`), so an open page updates live with no republish.
    Sets on documents that exist are pinned to the versions in `--dump`."""
    import app_model
    import page_db
    import app_alerts
    import app_setup
    behind = app_setup.take_master()
    if behind:
        print(_dump({"rev": None, "batches": [], "for_claude": [behind]}), end="")
        return 3
    today, now = app_model.clock(a.today, a.now)
    import page_reads
    planned = bool(a.dump) and os.path.isfile(os.path.join(a.dump, page_reads.PLAN))
    if planned:
        page_reads.assemble(a.dump, now)
        need = page_reads.needs(a.dump)
        if need:
            print(_dump({"rev": None, "batches": [], "for_claude": [
                page_reads.NEED_SCREENS.format(colls=" and ".join(need), dump=a.dump)]}), end="")
            return 2
    db = page_db.load(a.dump) if a.dump else {}
    missing = no_screen(a.dump, db) if a.dump else ""
    if missing:
        print(_dump({"rev": None, "batches": [], "for_claude": [missing]}), end="")
        return 2
    import app_listen
    # Any chat draws the page's screens but an old helper that handed the page on: two
    # helpers in a hand-over rewrote whole screens over each other, and every update bounced
    # (the maintainer, 4 November), and only the listener drawing them left the page stale
    # after "I applied" in the person's own chat (the engine review, 2026-11-05).
    draws, said = app_listen.draws_screens(db, a.chat, getattr(a, "work", "") or "", now)
    if not draws:
        print(_dump({"rev": None, "batches": [], "for_claude": [said]}), end="")
        return 0
    base = copy_basis()
    base_sha = copy_basis_sha()
    me = {c for c in (app_listen.this_chat(""), app_listen.this_chat(a.chat)) if c}
    by = app_listen.this_chat("") or a.chat
    ahead_of_us: dict = {}

    def newer(old) -> bool:
        """Is the page's copy drawn by another chat from a newer copy than this one? Never
        written over: a copy behind another's would put back what that one moved on. Judged
        by its commit where this copy knows it (theirs is newer when it is not in this copy's
        history), and by the time only where it does not: by the time alone, a job chat's
        commit not landed yet, or a computer with a fast clock, kept the listener from ever
        writing its screens again."""
        d = (old or {}).get("data") if isinstance(old, dict) else None
        if not isinstance(d, dict) or str(d.get("by") or "") in me:
            return False
        theirs_sha = str(d.get("base_sha") or "")
        if theirs_sha and base_sha:
            if theirs_sha not in ahead_of_us:
                # In this copy's whole history, its own commits not landed yet included.
                ahead_of_us[theirs_sha] = commit_ahead(
                    theirs_sha, os.environ.get("LJS_BASIS_SHA") or "HEAD")
            if ahead_of_us[theirs_sha] is not None:
                return ahead_of_us[theirs_sha]
        theirs = str(d.get("base") or "")
        return bool(base) and bool(theirs) and theirs > base
    kept: list = []
    stamp = {"by": by, **({"base": base} if base else {}),
             **({"base_sha": base_sha} if base_sha else {})}
    # The suggestions already on the page keep their day, so no more than three new ones
    # reach it a day.
    full: dict = {}
    model, _ = _build(today, now, shown=app_alerts.shown_in(db.get("view") or {}), full=full,
                      work_time=page_db.work_times(db, now) if db else None)
    w = page_db.Writes(a.out_dir)
    views = (db.get("view") or {}) if db else {}
    # Only what changed is written: every update rewrote all 37 documents, about 1.5 MB, when
    # one card had changed (2026-11-03). The page takes each document newer than its own copy,
    # so one left as it was still shows; a section in parts is kept or rewritten whole, so
    # its parts never mix two revs.
    volatile = ("rev", "made_at", page_db.VERSION_FIELD, "by", "base", "base_sha")

    def unchanged(doc_id, doc):
        old = (views.get(doc_id) or {}).get("data")
        if not isinstance(old, dict):
            return False
        strip = lambda d: {k: v for k, v in d.items() if k not in volatile}  # noqa: E731
        return strip(old) == json.loads(json.dumps(strip(doc), ensure_ascii=False))
    # Each whole list, in parts under 256 KiB, for the page's "Show" (tools/app_lists.py).
    import app_lists
    for doc_id, doc in app_lists.docs(full, model["made_at"], model["rev"]):
        old = views.get(doc_id)
        if unchanged(doc_id, doc):
            continue
        if newer(old):
            kept.append(doc_id)
            continue
        w.add("set", "view", doc_id, dict(doc, **stamp),
              if_version=old["version"] if old else None)
    for doc_id in app_lists.stale(full, db.get("view") or {}):
        if db["view"][doc_id]["version"] is not None:      # read under 4.2's name: kept
            w.add("delete", "view", doc_id, if_version=db["view"][doc_id]["version"])
    # The model builds `listener` and `schedule` itself now; each document is written once.
    # A section too big for one document (a long search's jobs, a big contact book) goes as
    # parts the page joins again (page_db.split), never cut short.
    written = []
    for name in dict.fromkeys(tuple(app_model.SECTIONS) + ("people_count", "lists", "listener",
                                                           "schedule")):
        if name not in model:
            continue
        docs = page_db.split(name, {"rev": model["rev"], "made_at": model["made_at"],
                                    "data": model[name], **stamp})
        if views and page_db.joined(views, name) == json.loads(json.dumps(model[name],
                                                                           ensure_ascii=False)):
            # Unchanged: the section's documents stay as they are, parts and all.
            head = (views.get(name) or {}).get("data") or {}
            n = head.get("in_parts") if isinstance(head.get("in_parts"), int) else 0
            written.extend([name] + [page_db.part_id(name, i) for i in range(1, n + 1)])
            continue
        if newer(views.get(name)):
            # A section is kept or rewritten whole, so its parts never mix two copies.
            head = (views.get(name) or {}).get("data") or {}
            n = head.get("in_parts") if isinstance(head.get("in_parts"), int) else 0
            written.extend([name] + [page_db.part_id(name, i) for i in range(1, n + 1)])
            kept.append(name)
            continue
        for doc_id, doc in docs:
            old = views.get(doc_id)
            w.add("set", "view", doc_id, doc, if_version=old["version"] if old else None)
            written.append(doc_id)
    for doc_id in page_db.stale_parts(db.get("view") or {}, written):
        if db["view"][doc_id]["version"] is not None:      # read under 4.2's name: kept
            w.add("delete", "view", doc_id, if_version=db["view"][doc_id]["version"])
    # Where each message goes (Open profile, Open in email): the address in an owner-only
    # document per contact, read by the page only for its owner and never embedded in it.
    ids = [m["contact"] for m in model.get("messages") or [] if m.get("contact")] + \
        [p["id"] for p in model.get("people") or []] + \
        [q["contact"] for q in ((model.get("linkedin") or {}).get("reading") or {})
         .get("queue") or []]
    try:
        ctx = app_model.Ctx(today, now)
        reach = app_model.reach_docs(ctx.contacts, ids)
        # What each person waiting on a reply last said, beside their address, owner-only.
        owed = [str(d.get("item") or "") for d in model.get("due") or [] if d.get("item")]
        for cid, words in app_model.last_words(ctx, owed + ids).items():
            reach.setdefault(cid, {"linkedin": None, "email": None})["said"] = words
    except Exception:  # noqa: BLE001  no profile yet: nobody to reach
        reach = {}
    # In a few owner-only documents, each contact always in the same one, and only a
    # document whose contacts changed is written: one per contact meant hundreds of writes
    # on every refresh, and reading them back hundreds of lines (2026-10-29).
    have = (db.get("addr") or {}) if db else {}
    for doc_id, doc in sorted(page_db.addr_docs(reach).items()):
        old = have.get(doc_id)
        if old and old["data"].get("contacts") == doc["contacts"]:
            continue
        w.add("set", "addr", doc_id, doc, if_version=old["version"] if old else None)
    for doc_id, old in sorted(have.items()):
        if doc_id not in page_db.addr_docs(reach):
            w.add("delete", "addr", doc_id, if_version=old["version"])
    # A draft that fails a check with a clear fix is fixed by Claude by itself, the moment the
    # check finds it: its tweak queued here, with no tap (the maintainer, 2026-11-04). Never a
    # second time for the same draft and reasons, and only so many tries a draft.
    if a.dump:
        for doc_id, fields in fix_work(model.get("messages") or [], db.get("work") or {}, now):
            w.add("set", "work", doc_id, fields)
    old = (db.get("meta") or {}).get("current") if db else None
    # Who wrote it, by this session's own id where there is one: the brief passed the word
    # "brief", which no listener rule could compare with a chat (engine audit, 2026-11-03).
    if not newer(old):
        w.add("set", "meta", "current", {"rev": model["rev"], "made_at": model["made_at"],
                                         "model": model["model"], **stamp, **_published()},
              if_version=old["version"] if old else None)
    batches = w.save("view") if w.entries else []
    # A redraft the drafts rerun handed out (tools/remake_drafts.py) goes on the work list by
    # itself, once: read against the page's own work list, and sent in a batch of its own,
    # so a refusal can never hold back the screens (each is a create, which the store refuses
    # for an id it holds). Without a dump of the page there is nothing to read it against,
    # and nothing is queued.
    if a.dump:
        try:
            import remake_drafts
            batches = list(batches) + remake_drafts.page_writes(
                db, os.path.join(a.out_dir, "remade"), now)
        except Exception:  # noqa: BLE001  nothing remade to read: nothing to queue
            pass
    # What a draft needs that Claude can do by itself is queued by itself, once: a check
    # with its fix in hand made again, and the PDFs the page lacks put on it. Never "Make it
    # again" or "Get my files ready" for the person to tap (the maintainer, 2026-11-05).
    if a.dump:
        try:
            batches = list(batches) + self_fixes(db, model, os.path.join(a.out_dir, "self"), now,
                                                 dump_dir=a.dump)
        except Exception:  # noqa: BLE001  nothing to read it against: nothing queued
            pass
    lines = app_listen.view_renewal(db, a.chat, now)
    # A yes the person gave, in another chat or on the page, that an unsent resume still
    # leaves off: this chat redoes it, unasked (tools/skill_answers.py). Work already on its way
    # for it is left to run.
    try:
        import skill_answers
        going = {wid for wid, doc in ((db.get("work") or {}) if db else {}).items()
                 if str((doc.get("data") or {}).get("status") or "") not in page_db.FINISHED}
        redo = skill_answers.redo_line(skill_answers.redo_due(
            today=today, ready=model.get("ready") or [], queued=going))
    except Exception:  # noqa: BLE001  no profile, or nothing asked
        redo = ""
    if redo:
        lines = list(lines or []) + [redo]
    if getattr(a, "end", False) and a.dump:
        # The save runs on by itself and wakes nobody: the page's "Saving your work" is
        # cleared with the batch's own page update, never by a later turn.
        me = app_listen.this_chat("") or app_listen.this_chat(a.chat)
        beat = ((db.get("chats") or {}).get(page_db.safe_id(me)) or {}).get("data") or {}
        if me and beat.get("busy"):
            batches = list(batches) + page_db.busy_beat(
                db, me, app_listen.chat_kind(), now, os.path.join(a.out_dir, "busy"), None)
    if planned:
        # The folder, and the copy this checkout keeps, as they will be once the batches are
        # sent: the next wake pins to the versions they leave, with no screen read.
        page_db.keep_landed(a.dump, batches)
        page_reads.absorb(a.dump)
    if getattr(a, "end", False):
        lines = list(lines or []) + end_of_batch(a.chat, getattr(a, "message", "") or "", now)
    print(_dump({"rev": model["rev"], "batches": batches,
                 **({"kept_newer": kept} if kept else {}),
                 **({"for_claude": lines} if lines else {})}), end="")
    return 0


def end_of_batch(chat: str, message: str, now) -> list[str]:
    """The end of a batch of the page's work (`view --end`): the save started in a process of
    its own (land.py --detach), once for the batch and waking no chat when it ends, and the
    wake's cost kept (helper_usage). Lines only for what is left to do."""
    import app_listen
    import person
    out: list[str] = []
    root = person.state()
    try:
        import land
        if land.git_dir(root) and not land._the_app(root):
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = land.detach(root, message or "Answer the page")
            if code != 0:
                out.append(buf.getvalue().strip())
    except Exception:  # noqa: BLE001  never a reason the page is not answered
        pass
    try:
        import helper_usage
        helper_usage.record("wake", app_listen.this_chat("") or app_listen.this_chat(chat), now)
    except Exception:  # noqa: BLE001  the log never stops a wake
        pass
    return [ln for ln in out if ln]


def copy_basis() -> str:
    """When the newest commit in this copy was made, in UTC ("2026-11-04T09:12:00Z"), or ""
    where it cannot be told (the app itself, no git). Each screen carries it as `base`, so a
    chat whose copy is behind another's never writes over that one's screens. LJS_BASIS is
    for tests."""
    given = os.environ.get("LJS_BASIS")
    if given is not None:
        return given
    if not os.path.isfile(os.path.join(person.ROOT, "profile", "person.json")):
        return ""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", person.ROOT, "log", "-1", "--format=%ct", "HEAD"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=10, stdin=subprocess.DEVNULL)
        secs = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        secs = 0
    if not secs:
        return ""
    return dt.datetime.fromtimestamp(secs, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_out(*args: str) -> tuple[int, str]:
    import subprocess
    try:
        r = subprocess.run(["git", "-C", person.state(), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10,
                           stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def copy_basis_sha() -> str:
    """The commit this copy is based on, which each screen carries as `base_sha`: the newest
    of this copy's commits that master has (so a commit not landed yet, which no other chat
    can know, never hides it), else this copy's newest. "" where it cannot be told (the app
    itself, no git). LJS_BASIS_SHA is for tests."""
    given = os.environ.get("LJS_BASIS_SHA")
    if given is not None:
        return given
    if not os.path.isfile(os.path.join(person.ROOT, "profile", "person.json")):
        return ""
    code, out = _git_out("merge-base", "HEAD", "origin/master")
    if code != 0 or not out:
        code, out = _git_out("rev-parse", "HEAD")
    return out if code == 0 else ""


def commit_ahead(theirs: str, ours: str) -> bool | None:
    """Whether commit `theirs` is ahead of this copy's `ours`: True when this copy knows it
    and it is not in ours's history, False when it is, None when this copy has never seen it
    (the caller then goes by the time)."""
    if _git_out("cat-file", "-e", theirs + "^{commit}")[0] != 0:
        return None
    code, _out = _git_out("merge-base", "--is-ancestor", theirs, ours)
    if code not in (0, 1):
        return None
    return code == 1


def cmd_page(a) -> int:
    path = os.path.join(_HERE, "app_page.py")
    if not os.path.isfile(path):
        print("app: the page is not in this version of the app yet (tools/app_page.py is "
              "missing); `app.py model` builds what it will show.")
        return 1
    # Loaded by its path: it may not exist yet, so no import statement names it.
    import importlib.util
    spec = importlib.util.spec_from_file_location("app_page", path)
    app_page = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_page)
    if getattr(a, "out_dir", "") and hasattr(app_page, "write_parts"):
        # The page to publish: a small page and small code files, and the publishes that put
        # up only what the page lacks (app_listen.parts_plan). A chat reads every file it did
        # not write, whole, before it publishes it; one file of a megabyte could not be read.
        import app_listen
        import app_model
        today, now = app_model.clock(a.today, a.now)
        model, _ = _build(today, now)
        built = app_page.write_parts(model, a.out_dir)
        # The reads it asks for are set aside from the growth that renews a helper (a new
        # helper that put an update up was told to hand over twenty minutes on, 2026-11-05).
        app_listen.republish_started(app_listen.this_chat(""), now)
        listing = None
        if getattr(a, "on_page", None) is not None:
            if a.on_page == "-":
                listing = sys.stdin.read()
            else:
                with open(a.on_page, encoding="utf-8") as fh:
                    listing = fh.read()
        for line in app_listen.parts_plan(built, a.url or "", listing=listing,
                                          whole=bool(getattr(a, "whole", False))):
            print(line)
        return 0
    if hasattr(app_page, "render"):
        import app_model
        today, now = app_model.clock(a.today, a.now)
        model, _ = _build(today, now)
        _out(app_page.render(model), a.out)
        return 0
    return int(app_page.main(["--out", a.out] if a.out else []) or 0)


def cmd_apply(a) -> int:
    import app_actions
    import app_model
    _, now = app_model.clock(None, a.now)
    out = a.out or os.path.join(a.dump, "out")
    if a.claim:
        got = app_actions.claim(a.dump, a.chat, now, out)
    else:
        got = app_actions.apply_dir(a.dump, a.chat, now, out, assets_dir=a.assets)
    print(_dump(got), end="")
    return 0


def choose(db: dict, chat: str, kind: str, now, on: str = "", no_sessions: bool = False,
           claim_out: str | None = None, job_chat: bool = False) -> dict | None:
    """The queued work this chat should take (None: nothing is), with the model a chat
    started for it gets (tools/model_guide.py for_work), `run`: where it is done
    (where_it_runs), and with `claim_out` the claim as batch files. Small work done here is
    claimed running at its first stage, so no progress pin follows it."""
    import app_listen
    import model_guide
    import page_db
    chosen = app_listen.next_republish(db, chat, now)
    if chosen is None:
        # Each big job in a cloud chat of its own runs on its own computer: ten at once there.
        cap = page_db.HEAVY_CAP_CHATS if kind == "cloud" and not no_sessions else page_db.HEAVY_CAP
        chosen = page_db.next_item(app_listen.without_republish(db), kind, now, cap=cap,
                                   heavy_only=job_chat)
    if chosen is None:
        return None
    info = model_guide.for_work(chosen["kind"], on)
    heavy = bool(page_db.WORK_KINDS.get(chosen["kind"], {}).get("heavy"))
    chosen.update(model=info["model"], effort=info["effort"], heavy=heavy)
    # The names of the job chats still at work, so a new one is never called the same.
    taken = {str(d.get("chat_title") or "") for d in
             ((doc.get("data") or {}) for doc in (db.get("work") or {}).values())
             if str(d.get("status") or "") in ("claimed", "running")} - {""}
    chosen.update(where_it_runs(chosen, chat, kind, no_sessions, taken=taken))
    if job_chat:
        # A big job's own chat takes the next big job waiting and does it itself: no chat
        # can tell the one that answers the page that a slot is free, so a queue of drafts
        # waited behind the cap with nobody to start it (2026-11-03).
        chosen.update(run="here")
        chosen.pop("create_session", None)
        chosen.pop("agent", None)
        if chosen.get("heavy"):
            # Its own steps, for this chat to follow: its id, a fresh folder, its kind's
            # commands and pins. "Do it here from step 3" reused the first job's (the release
            # review, 2026-11-03).
            import app_setup
            url = app_setup.page_record().get("url", "") or "<url>"
            chosen["steps"] = job_steps(chosen, chat, url, session=True, first=1)
    if claim_out:
        chosen["batches"] = page_db.claim(db, chosen, chat, kind, now, claim_out,
                                          running=chosen.get("run") == "here")
    return chosen


def cmd_next(a) -> int:
    """The queued work this chat should take, with the model a chat started for it gets
    (tools/model_guide.py for_work), and `run`: where it is done (where_it_runs). A big job
    is never `here`. A republish goes to the page's listener alone, and first: the page's
    own code changed under every open window."""
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    chosen = choose(page_db.load(a.dump), a.chat, a.kind, now, on=a.on,
                    no_sessions=a.no_sessions, claim_out=a.claim_out,
                    job_chat=getattr(a, "job_chat", False))
    if chosen is None:
        return 0
    print(_dump(chosen), end="")
    return 0


# A big job (page_db.WORK_KINDS "heavy": a search, drafts, a resume for a contact, an
# interview prep, a networking run) never runs in the chat that answers the page. Run there,
# even as background agents, a search and a networking run held it for 15 and 23 minutes and
# the page waited on every tap (2026-10-29). Each gets a cloud chat of its own instead.
CHILD_TITLE = "Job search: {title}"
# The page's data tools, which .claude/settings.json pre-approves. Artifact is not among them
# (publishing or deleting a page still asks, tools/security_guards.py), and create_session
# drops a tool its caller has not pre-approved, so naming it carried nothing (the stranger
# audit, X-8). A job's chat never publishes the page; the page's own republish declares no
# capabilities once the page has them (app_listen.parts_plan), so it is not asked about.
CHILD_TOOLS = ("ArtifactData", "ArtifactComments")
# Where the chat starting a job's chat does not know its own id, the prompt carries this, and
# the call says to put the id in first, so the job's chat can report back to it.
PARENT = "<your chat id>"
SKILL = os.path.join(os.path.dirname(_HERE), ".claude", "skills", "app", "SKILL.md")


def work_row(kind: str) -> str:
    """What the app skill's table (step 4) says a chat runs for this kind of work, word for
    word, or "" when the skill has no row for it."""
    try:
        with open(SKILL, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    for line in text.splitlines():
        if not line.startswith("| ") or " | " not in line[2:]:
            continue
        kinds, rest = line[2:].split(" | ", 1)
        if kind in [k.strip() for k in kinds.split(",")]:
            return rest.rstrip().rstrip("|").strip()
    return ""


def child_prompt(chosen: dict, parent: str, url: str, session: bool = True) -> str:
    """What a chat (or, where none can be started, a background agent) is told for one big
    job: run that item, pin its progress, finish it, land it, and say it is finished. It
    never publishes, watches or answers the page. `parent` is the chat that claimed it."""
    wid, kind = chosen["work"], chosen["kind"]
    where = "in a chat of its own" if session else "as a background agent"
    lines = [
        f"Do one piece of work for this person's job search page, {where}, so the chat that "
        f"answers the page stays free. The work: \"{chosen.get('title') or kind}\" (work item "
        f"{wid}, a {kind}), already claimed for you. The page: {url}. The chat that answers "
        f"it: {parent}.",
        f"1. python3 tools/app.py start --on \"<your model>\" --tools none --work {wid}, and do "
        "what it prints. Never publish, watch or answer the page.",
    ]
    return "\n".join(lines + job_steps(chosen, parent, url, session=session, first=2,
                                       report_to=parent if session else ""))


def job_steps(chosen: dict, claimer: str, url: str, session: bool = True,
              first: int = 1, report_to: str = "") -> list[str]:
    """The steps for one big job, numbered from `first`, every one naming this job's own id,
    its own folder ($D, read afresh), its kind's commands and its pins (a search's round.log
    as well), with `--chat <claimer>` (the id it was claimed under) on each write. A job
    chat's second job reused the first one's id and $D, and had no search pin unless the
    first was a search (the release review, 2026-11-03): `next --job-chat` prints these."""
    wid, kind = chosen["work"], chosen["kind"]
    keys = ", ".join(s["key"] for s in chosen.get("stages") or [] if s.get("key"))
    row = work_row(kind)
    lines: list[str] = []

    def step(text: str) -> None:
        lines.append(f"{first + len(lines)}. {text}")

    step("Load ArtifactData (ToolSearch, select:ArtifactData). Read the page's database "
         f"into a fresh folder in your scratchpad for this job alone, $D, in one go: "
         f"ArtifactData query, url {url}, once for each of the collections work, holds, screen, "
         f"meta and addr, each with out_dir $D and limit 1000. The item, its args and the "
         f"`answers` the person already gave on the page (never asked again) are in "
         f"$D/work/{wid.replace('~', '@')}.json.")
    mates = [str(o.get("work") or "") for o in chosen.get("with") or [] if o.get("work")]
    if mates:
        # Every posting of a batch by its id: named only by its leader, a job drafted one of
        # three and pinned one lease, and the other two were taken again by a second job
        # (engine audit, 2026-11-03).
        step(f"This job is {len(mates) + 1} items claimed together, each its own card: {wid} "
             f"and {', '.join(mates)} (`with` {wid} in their files). Do them in one run, as the "
             f"row below says for the item and each in `with`. Pin {wid} alone: its pin renews "
             "the others and moves them with it, and names any they asked to stop under "
             "`stopped`. Each one ends with its own app.py done (--work <its id>), as the "
             "finish below says.")
    # The commands themselves, so the chat reads none of the skill for them: reading it was
    # steps and context before the job even started (2026-11-03).
    step(f"Do it, as the app skill's own table says for a {kind}: {row.rstrip('.')}. Read "
         "nothing of .claude/skills/app/SKILL.md but its step 5, for the finish." if row else
         f"Do it as .claude/skills/app/SKILL.md says for a {kind}: step 4 (its row, and "
         "\"Progress costs nothing extra\") and step 5. Read only those parts.")
    step(f"At each stage ({keys}): python3 tools/app.py pin \"$D\" --work {wid} --chat "
         f"{claimer} --stage <stage> --line \"<one plain line>\", and send the batch it prints "
         f"(ArtifactData batch, url {url}). On a long stage, pin it again with a new line every "
         "ten minutes or so: the page counts a job with no word for half an hour as stopped. "
         "\"stop_asked\": true means they tapped Stop (`stopped` names others of the job they "
         f"stopped): end each with app.py done --work <its id> --chat {claimer} --stopped. A "
         "question only the person can answer: app.py done --work <its id> --chat "
         f"{claimer} --question \"<one plain question>\" puts it on their page, and their "
         "answer puts it back in the queue; never wait in the chat. A refused write names the "
         "record's version: python3 tools/app.py version \"$D\" <collection>/<doc id> "
         "<that version>, and run it once more; refused again, read work again; claimed by "
         "another chat, write nothing else and stop.")
    if kind == "search":
        step("Run run_round.py in the background (Bash, run_in_background), with no --out: "
             "the round names itself and its first line says its folder (\"round: r12, its "
             "files in ...\"). When it ends, read what the person did on the page meanwhile "
             f"(ArtifactData query, url {url}, collections actions and receipts, out_dir $D) "
             "and cut it again with it: python3 tools/run_round.py --recut --out <its folder> "
             "--show <the same number> --dump \"$D\", so a job they set aside while it ran is "
             "passed over and the next one taken. Finish only after that: app.py done "
             "refuses a search whose shortlist is not saved yet. While it runs, "
             f"every ten minutes or so (its lease is thirty): python3 tools/app.py pin \"$D\" "
             f"--work {wid} --chat {claimer} --stage scrape --log <the round's folder>/round.log, "
             "and send its batch, so the page shows how many job sites are done and how long "
             "is left.")
    if kind == "search" and chosen.get("draft_all"):
        # One job, not two searches and 13 chats run by hand (the maintainer, 2026-11-05): the
        # search drafts each job as it is found, in this chat, the drafts written together.
        draft = work_row("draft")
        step(f"This search drafts every job it finds, {chosen['draft_all']} at most, in this "
             "chat, each as it is found. Each time one of its shortlists is saved (the round's "
             "log says \"shortlist summary:\"; a wider round saves its own), and once more with "
             f"--last after its --recut: python3 tools/app.py search-drafts \"$D\" --work {wid} "
             f"--chat {claimer}, and send its batch. It queues a draft of each job that passes "
             "every rule, claimed with this search (its card counts them, \"2 of 5 drafted\"), and "
             "stops a draft not begun whose job fails a rule now, taking the next. Draft what it "
             "queued at once, while the search goes on, all of them in one run, as the app "
             f"skill's table says for a draft: {draft.rstrip('.')}. Pin this search alone (--stage "
             "draft). As each draft's documents are made and checked, finish it on its own "
             f"(app.py done --work <its id> --chat {claimer}; one that stops because the job is "
             "not one they can take: --left-out \"<why, plain>\"), send its batch and bring the "
             "page up to date (the finish step below), so it is in Drafts at once. The search "
             "finishes by itself with its last draft; never app.py done it yourself.")
    done = (f"each draft's own app.py done, with --chat {claimer}: {wid} finishes with the last"
            if kind == "search" and chosen.get("draft_all")
            else f"its app.py done with --work {wid} --chat {claimer}")
    # A draft's PDFs: this chat cannot upload (Artifact is not among its tools), so its
    # app.py done queues one `files` item for the chat that answers the page, and nothing is
    # uploaded here (the maintainer, 4 November).
    files = (" Its PDFs reach the page's file store by themselves: app.py done queues the "
             "upload for the chat that answers the page (send every batch it prints), so upload "
             "nothing here." if kind in ("draft", "resume_for_contact") else "")
    if session and report_to:
        # A job's chat tells the chat that started it, which puts the results on the page and
        # archives it at once (claude_surfaces: cloud-chat-reports-back): finished chats sat in
        # the sidebar until the next day's tidy-up, and nobody could tell whether one was still
        # working (the maintainer, 2026-11-04). Landed or not: a failed check leaves the work for
        # the next chat to land, and said nothing, so the page stayed stale with its card
        # already Done (the audit, 2026-11-03).
        step(f"Finish as step 5 says ({done}), without its heartbeat line and without bringing "
             f"the page up to date.{files} Save and land your work on master (CLAUDE.md, \"Saving\"), "
             "and wait until the landing has ended.")
        step("Then, landed or not, tell the chat that started you, in one message, and stop: "
             "load send_message and get_session (ToolSearch, select:"
             "mcp__claude-code-remote__send_message,mcp__claude-code-remote__get_session); your "
             f"own id is get_session with no session_id; send_message, session_id {report_to}, "
             f"message \"{REPORT.format(work=wid, landed='on master', chat='<your own id>')}"
             f"<what it made, in a few plain words>.\", or \"not landed\" in place of \"on "
             "master\" where the check failed and the work waits on its branch. That chat puts "
             "the results on the page and closes this chat at once, so do nothing after it. "
             "Never write to the person: the page shows how it went.")
        # Where the message cannot go (the chat that started it was replaced by a fresh helper
        # and archived, or the tool is not here), the old way: the page brought up to date
        # from here, and the next job waiting taken here, so a queue keeps moving.
        step(f"Only where send_message is not there or is refused: bring the page up to date "
             f"yourself: ArtifactData query, url {url}, collections screen, meta, addr and "
             f"work, out_dir $D; python3 tools/app.py view \"$D/view\" --dump \"$D\" --chat "
             f"<your own id> --work {wid} (it takes master first, so the page has every other chat's work "
             "too); and send every batch it prints (ArtifactData batch). A refused batch: read "
             "those four again and run it once more. Then the next big job waiting, as below.")
        step(_next_job(url, first_word="Only in that case"))
    elif session:
        # A job's chat started by another job's chat (`next --job-chat`) has nobody it was
        # started by to tell: it brings the page up to date itself and takes the next one.
        step(f"Finish as step 5 says ({done}), without its heartbeat line.{files} Save and land "
             f"your work on master (CLAUDE.md, \"Saving\"). Then, landed or not (a failed check "
             f"leaves the work for the next chat to land, and this step still runs), bring the "
             f"page up to date yourself: "
             f"ArtifactData query, url {url}, collections screen, meta, addr and work, out_dir "
             f"$D; python3 tools/app.py view \"$D/view\" --dump \"$D\" --chat <this chat's id> "
             f"--work {wid} (it takes master first, so the page has every other chat's work too, "
             "and never writes over a screen drawn from a newer copy than this one); and send "
             "every batch it prints (ArtifactData batch). A refused batch: read those four again "
             "and run it once more. Never write to the person: the page shows how it went.")
        step(_next_job(url))
    else:
        step(f"Finish as step 5 says ({done}), without its heartbeat line and without app.py "
             f"view.{files} Save and land your work on master (CLAUDE.md, \"Saving\"). Then end with "
             f"one line, landed or not: \"Finished {wid}, on master: bring the page up to "
             f"date.\", or where the check failed and the work waits on its branch, \"Finished "
             f"{wid}, not landed: bring the page up to date.\" Never write to the person: the "
             "page shows how it went.")
    return lines


def _next_job(url: str, first_word: str = "Then") -> str:
    return (f"{first_word}, the next big job waiting, so a queue keeps moving with nobody to "
            f"start it: ArtifactData query, url {url}, collections work and holds, out_dir a "
            f"fresh folder $E; python3 tools/app.py next \"$E\" --chat <this chat's id> --kind "
            f"cloud --job-chat --on \"<your model>\" --claim-out \"$E/claim\". Nothing named: "
            "stop. One named: send its claim batch (refused: another chat has it, stop), then "
            "follow the `steps` it printed, in order: that job's own, with its id, its folder and "
            "its commands, never this one's. At most three jobs in this chat, so its history "
            "stays short.")


# What a job's chat sends the chat that started it once its work is landed (send_message),
# then the few plain words of what it made. "[app]" brings that chat the app skill, which
# says what to do with it ("A job's chat reports back").
REPORT = "[app] Finished {work}, {landed}, in chat {chat}: "
REPORTED = re.compile(r"\[app\] Finished (\S+), (on master|not landed), in chat (session_\w+)")


def distinct_title(title: str, taken) -> str:
    """`title`, or with (2), (3)... where a job chat still at work already has it: no two of
    the person's chats share a name (the maintainer, 2026-11-04). Short enough for the tidy-up
    to know it as the app's (tidy.APP_TITLE)."""
    taken = set(taken or ())
    if title not in taken:
        return title
    head, _, text = title.partition(": ")
    n = 2
    while True:
        got = f"{head}: {text[:55].rstrip()} ({n})"
        if got not in taken:
            return got
        n += 1


def where_it_runs(chosen: dict, chat: str, kind: str, no_sessions: bool = False,
                  taken=()) -> dict:
    """`run`: `here` for light work; for a big job, `child session` with the create_session
    call to make (its prompt runs the item, pins its progress and reports back to `chat`, which
    then archives it), or, where a chat cannot start one (a chat on a computer, or no
    create_session tool), `background agent` with the Agent call. A big job is never `here`.
    `taken`: the names of the job chats still at work."""
    if not chosen.get("heavy"):
        return {"run": "here"}
    import app_setup
    url = app_setup.page_record().get("url", "") or "<url>"
    # The id the job's chat reports back to: this chat's own. Where it is not known here,
    # the call carries the placeholder and says to put the id in first (get_session).
    parent = chat or PARENT
    owner, name = app_setup.origin()
    title = distinct_title(CHILD_TITLE.format(title=" ".join(
        str(chosen.get("title") or chosen["kind"]).split())[:60]), taken)
    if kind == "cloud" and not no_sessions and owner and name:
        # The page's own tools, carried into the job's chat as create_session documents
        # (extra_allowed_tools: "pre-approved without a user permission prompt", kept only
        # where this chat has them pre-approved): a draft's chat stopped on "ArtifactData
        # requests permission" while the person was away (2026-11-03).
        call = {"title": title, "prompt": child_prompt(chosen, parent, url),
                "source_url": f"https://github.com/{owner}/{name}",
                "extra_allowed_tools": list(CHILD_TOOLS)}
        if chosen.get("model"):
            call["model"] = chosen["model"]
        got = {"run": "child session", "create_session": call}
        if parent == PARENT:
            got["first"] = (f"put this chat's own id, from get_session with no session_id, "
                            f"wherever its prompt says {PARENT}, so the job's chat can report "
                            "back to this one")
        return got
    agent = {"description": title, "prompt": child_prompt(chosen, parent, url, session=False),
             "run_in_background": True, "isolation": "worktree"}
    if chosen.get("model"):
        agent["model"] = chosen["model"]
    return {"run": "background agent", "agent": agent}


def cmd_pin(a) -> int:
    """One running item's progress, pinned: its stage, a plain line, a count, the time left
    (or a search's round.log, which says all three), with its lease renewed."""
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    db = page_db.load(a.dump)
    count = {"done": a.done, "total": a.total} if a.total else None
    left, stage = a.left_s, a.stage
    if a.log:
        try:
            with open(a.log, encoding="utf-8", errors="replace") as fh:
                seen = page_db.round_progress(fh.read())
        except OSError:
            seen = None
        if seen:
            count = {"done": seen["done"], "total": seen["total"]}
            left = seen["left_s"] if seen["left_s"] is not None else left
            # The round's own log knows which step it is on; the chat pins "scrape" throughout.
            stage = seen["stage"] or stage
    # Every item named, each its own write: with --work given for each member of a batch,
    # only the last got one, and the rest read as stopped (the drafting child, 2026-11-03).
    works = list(dict.fromkeys(a.work))
    out = a.out or os.path.join(a.dump, "out")
    if getattr(a, "blocked", False):
        # Written by the chat that answers the page, about a job in a chat of its own whose
        # status reads blocked: its card says it waits on the person there.
        batches = []
        for wid in works:
            try:
                batches += page_db.mark_blocked(db, wid, now, os.path.join(out, page_db.safe_id(wid)))["batches"]
            except KeyError as e:
                print(f"app: {e.args[0]}", file=sys.stderr)
                return 2
        print(_dump({"blocked": works, "batches": batches}), end="")
        return 0
    got_all = []
    for wid in works:
        try:
            got_all.append(page_db.pin(db, wid, now, out if len(works) == 1 else
                                       os.path.join(out, page_db.safe_id(wid)),
                                       stage=stage, line=a.line, count=count, left_s=left,
                                       dump_dir=a.dump, chat=a.chat))
        except KeyError as e:
            print(f"app: {e.args[0]}", file=sys.stderr)
            return 2
    if len(got_all) == 1:
        print(_dump(got_all[0]), end="")
    else:
        print(_dump({"works": got_all, "stop_asked": any(g["stop_asked"] for g in got_all),
                     "batches": [b for g in got_all for b in g["batches"]]}), end="")
    return 0


def cmd_busy(a) -> int:
    """What this chat is doing for the person in the chat, on the page, or (--done) that it
    has finished."""
    import app_listen
    import app_model
    import page_db
    if not a.done and not a.line:
        print("app: say what Claude is doing in a few words, or --done", file=sys.stderr)
        return 2
    _, now = app_model.clock(None, a.now)
    db = page_db.load(a.dump)
    chat = app_listen.this_chat(a.chat)
    try:
        batches = page_db.busy_beat(db, chat, a.kind or app_listen.chat_kind(), now,
                                    a.out or os.path.join(a.dump, "out"),
                                    None if a.done else a.line, dump_dir=a.dump)
    except ValueError as e:
        print(f"app: {e}", file=sys.stderr)
        return 2
    print(_dump({"chat": chat, "busy": None if a.done else page_db.plain_busy(a.line),
                 "batches": batches}), end="")
    return 0


def cmd_progress(a) -> int:
    import app_listen
    import page_db
    if a.kind == "republish" and a.kind not in page_db.STAGES:
        stages = [{"key": k, "name": n, "est_s": s} for k, n, s in app_listen.STAGES]
        print(_dump({"kind": a.kind, "stages": stages,
                     "total_s": sum(x["est_s"] for x in stages)}), end="")
        return 0
    try:
        print(_dump(page_db.progress(a.kind)), end="")
    except KeyError as e:
        print(f"app: {e.args[0]}")
        return 2
    return 0


def cmd_check(a) -> int:
    import app_model
    if a.model:
        with open(a.model, encoding="utf-8") as fh:
            model = json.load(fh)
    else:
        today, now = app_model.clock(a.today, a.now)
        model, _ = app_model.build(today, now)
    bad = app_model.check(model)
    if bad:
        print(f"app: the model breaks the contract in {len(bad)} place"
              f"{'s' if len(bad) != 1 else ''}:")
        for line in bad:
            print(f"  {line}")
        return 1
    print(f"app: the model keeps the contract (rev {model.get('rev')})")
    return 0


def paste_line(owner: str, name: str) -> str:
    """What a person pastes into the first chat on their computer: their copy and the page
    that chat follows (COMPUTER.md), in the registry's own words (claude_surfaces local-chat,
    its last step), so a doc and a chat say one thing."""
    import place
    return place.computer_paste(owner, name)


def cmd_start(a) -> int:
    import app_listen
    import app_setup
    if a.paste:
        owner, name = app_setup.origin()
        if not owner:
            print("app: this copy has no GitHub address to name", file=sys.stderr)
            return 1
        print(paste_line(owner, name))
        return 0
    if a.work:
        # Every later message of this chat is the job's too: the app's hook reads this.
        try:
            app_setup.record_job_chat(a.work)
        except OSError:
            pass
    code, lines = app_setup.start(on=a.on or "", tools=a.tools or "", page_url=a.page or "",
                                  work=a.work or "", data_current=data_current(a.dump))
    lines = app_listen.shape(code, lines, chat=app_listen.this_chat(a.chat), listen=a.listen,
                             helper=a.helper, on=a.on or "", work=a.work or "")
    print("\n".join(lines))
    return code


def data_current(dump: str) -> bool:
    """Does the page already hold the data this copy would write now? Its `meta/current`, in
    a read the chat has made (`dump`), carries the rev of the model built now. False with no
    read: then the data is written, as before. A start with nothing changed wrote the page's
    every section again, a step and a batch for nothing (2026-11-03)."""
    if not dump or not os.path.isdir(dump):
        return False
    try:
        import app_alerts
        import app_model
        import page_db
        db = page_db.load(dump)
        cur = ((db.get("meta") or {}).get("current") or {})
        if cur.get("old"):
            return False                  # read under 4.2's name: the move writes it anyway
        rev = str((cur.get("data") or {}).get("rev") or "")
        if not rev:
            return False
        today, now = app_model.clock(None, None)
        # Built as `view` builds it: the suggestions on the page keep their day.
        model, _ = _build(today, now, shown=app_alerts.shown_in(db.get("view") or {}), full={})
        return rev == str(model.get("rev") or "")
    except Exception:  # noqa: BLE001  no profile, or a model that cannot be built: write it
        return False


def cmd_published(a) -> int:
    import app_listen
    import app_model
    import app_setup
    if a.url == "none":
        app_setup.record_no_page(chat=a.chat, why=a.why)
        print("app: noted for this chat only: it cannot publish, so setup and the updates stay "
              "in this chat, and it is not asked again for a month. Every other chat still "
              "publishes the page.")
        return 0
    was = str(app_setup.page_record().get("url") or "")
    first = not was
    chat = app_listen.this_chat(a.chat)
    try:
        path = app_setup.record_page(a.url, chat=chat, parts=a.parts)
    except ValueError as e:
        print(f"app: {e}")
        return 2
    # A page that could no longer be published to was put up afresh (X-44): the new one has
    # an empty store, so this chat claims it as at a first publish, and the person hears the
    # new address once.
    replaced = bool(was) and was != a.url
    import local_path
    print(f"app: the page's address is kept in {local_path.rel(path, person.ROOT)}; save it "
          "with the rest (python3 tools/save_state.py)")
    _, now = app_model.clock(None, None)
    app_listen.republish_done(chat, now)        # what the publish read is set aside for good
    import tempfile
    out = a.out or tempfile.mkdtemp(prefix="ljs-listen-")      # never inside the profile
    for line in app_listen.published_lines(a.url, chat, first, out, now, replaced=replaced):
        print(line)
    if a.dump:
        import page_db
        got = app_listen.close_republish(page_db.load(a.dump), out, now)
        if got["batches"]:
            print("app: the page no longer shows this update as waiting: send this batch "
                  f"(ArtifactData batch, url {a.url}): " + " ".join(got["batches"]))
    return 0


def running_elsewhere(db: dict, chat: str) -> list[tuple[str, str]]:
    """[(work id, chat id)] for work running in a cloud chat of its own (claimed by another
    session_ chat), not already said to wait on the person."""
    out = []
    for wid, doc in sorted((db.get("work") or {}).items()):
        d = doc.get("data") or {}
        by = str(d.get("claimed_by") or "")
        if str(d.get("status") or "") in ("claimed", "running") and by.startswith("session_") \
                and by != chat and not d.get("blocked_at"):
            out.append((wid, by))
    return out


def cmd_answer(a) -> int:
    """A setup answer the person gave in the chat rather than on the page, kept exactly as the
    page's own answer is (app_actions setup.answer, into profile/setup_answers.json), so setup
    carries on from it: a person who typed their answers or pasted their resume in the chat
    was never set up (the stranger audit, X-58)."""
    import tempfile
    import app_actions
    import app_model
    import app_setup
    import page_db
    step = a.step
    if step not in app_setup.STEP_IDS and step != "history":
        print(f"app: {step} is not a setup question: one of {', '.join(app_setup.STEP_IDS)}")
        return 2
    value: dict = {}
    for pair in a.field or []:
        key, _, val = pair.partition("=")
        if key:
            value[key.strip()] = val.strip()
    text = a.text
    if a.text_file:
        with open(a.text_file, encoding="utf-8") as fh:
            text = fh.read()
    if text:
        fields = sorted(app_actions._setup_fields(step)) if step not in ("resume", "history") else []
        value.setdefault("text" if not fields else fields[0], text)
    today, now = app_model.clock(None, None)
    try:
        zone = person.home_zone_named(person.directory()) or "UTC"
    except Exception:  # noqa: BLE001  no profile yet: the day is the clock's
        zone = "UTC"
    act = {"action": "setup.answer", "value": value, "at": app_model.stamp(now)}
    run = app_actions.Run(f"chat-{step}", act, {"step": step}, {},
                          page_db.Writes(tempfile.mkdtemp(prefix="ljs-answer-")), "chat", zone, now)
    try:
        got = app_actions._setup_answer(run)
    except app_actions.Refused as e:
        print(f"app: not kept: {e}")
        return 1
    done = sum(1 for s in app_setup.STEP_IDS if app_setup.answers().get(s))
    print(f"app: kept as the answer to {step} ({done} of {len(app_setup.STEP_IDS)} answered): "
          f"{got.get('note') or 'Saved.'} Carry on as .claude/commands/setup.md says; the page "
          "shows it answered.")
    return 0


def check_in(dump: str, chat: str, now, out: str, listen: bool = False, helper: bool = False,
             hand: str = "", update: bool = False, partial: bool = False) -> dict:
    """The listener's check-in over a dump, as `listen` and `wake` both do it: {"read": the
    collections to read first, or []; "move": a 4.2 page's batches, first; "got":
    app_listen.decide's answer; "upkeep": lines; "prune": batches for after the wake's work;
    "tidy": whether the daily tidy is due}."""
    import app_listen
    import app_model
    import page_db
    db = page_db.load(dump)
    # A page a 4.2 chat left keeps its records under the old names: they move to the new
    # ones once, in code, before anything is written to them (2026-10-29).
    more = page_db.to_read(dump, db)
    if more:
        return {"read": more}
    move = page_db.move(db, dump, os.path.join(out, "move"), app_listen._stamp(now), chat)
    if move["batches"]:
        page_db.moved_into(dump, move)
    got = app_listen.decide(move["db"], chat, out, now, listen=listen, helper=helper,
                            hand_to=hand, update=update)
    upkeep: list[str] = []
    old: list[str] = []
    ended: dict = {"ended": [], "batches": []}
    if got["role"] == "listener":
        # The search's own upkeep, whether or not a brief is on (the brief did it alone
        # before 4.3, and it is off until asked for): applications gone quiet are closed,
        # in code, on a wake of the chat that answers the page. Nothing to do, nothing said.
        try:
            import followups
            closed = followups.close_quiet()
        except Exception:  # noqa: BLE001  no profile or no tracker yet: nothing to close
            closed = []
        if closed:
            upkeep.append(f"upkeep: {len(closed)} application(s) gone quiet were closed as no "
                          "reply (followups.py --close-quiet); save them with the rest, after "
                          "this wake's work (python3 tools/save_state.py)")
        # A call whose day has passed is no longer booked: the stored status moves on, in
        # code, on every wake of the chat that answers the page (with or without a brief).
        try:
            from network import state as _contacts
            _contacts.advance_past_calls(app_model.local_day(
                now, person.home_zone_named(person.directory()) or "UTC"))
        except Exception:  # noqa: BLE001  no profile or no contact book yet
            pass
        # An interview's time said in a note or a message goes on the interview's own
        # record, so the page shows it and nobody is asked to add it (2026-10-29).
        try:
            import interview_pack
            zone = person.home_zone_named(person.directory()) or "UTC"
            timed = interview_pack.take_times(today=app_model.local_day(now, zone).isoformat())
        except Exception:  # noqa: BLE001  no profile or no interview yet: nothing to take
            timed = []
        if timed:
            upkeep.append(f"upkeep: {len(timed)} interview time(s) said in a note or a message "
                          "were saved on the interview; save them with the rest and bring the "
                          "page up to date (python3 tools/app.py view), asking nobody")
        # A job whose chat stopped twice (or that they asked to stop) is ended, in code, so
        # its card offers Try again and nothing waits behind it (engine audit, 2026-11-03).
        ended = page_db.fail_stranded(page_db.load(dump), now, os.path.join(out, "stranded"))
        if ended["batches"]:
            page_db.keep_landed(dump, ended["batches"])
        # The page's store kept small, in code: finished records over two months old go,
        # from a whole read only (the day's first wake reads whole).
        old = [] if partial else page_db.prune(page_db.load(dump), now,
                                               os.path.join(out, "prune"))
    tidy_due = retire = False
    if got["role"] == "listener" and app_listen.chat_kind() == "cloud":
        import tidy
        tidy_due = bool(tidy.due(db=move["db"], skip=chat, listener=got.get("record"), now=now))
        # The helper this chat took the page over from is put away now, not at tomorrow's
        # tidy-up (the maintainer, 2026-11-04: at most two such chats, ever).
        retire = tidy_due and bool(tidy.retiring(got.get("record"), now))
    return {"read": [], "move": move["batches"], "got": got, "upkeep": upkeep, "prune": old,
            "tidy": tidy_due, "retire": retire, "stranded": ended["batches"]}


READ_FIRST = ("listen: this page was made by an older version of the app, and its records "
              "move to their new names once, now. ArtifactData query, once for each of the "
              "collections {more} (url <the page>, out_dir the same folder, limit "
              "1000), then run this again with the same folder. Say nothing about it to the "
              "person.")
PRUNE_SAID = ("upkeep: old finished records the page no longer shows are deleted: send "
              "these batches after this wake's work, asking nobody:")
# How the listings reach the tidy-up: in one heredoc, as the tools returned them, never typed
# into files first (the maintainer's copy, 2026-11-05).
TIDY_GIVE = ("list_sessions (mine: true) and list_triggers, every page; then python3 "
             "tools/tidy.py plan --dump \"$D\" --stdin with one JSON object on standard input "
             "(a quoted heredoc): {\"sessions\": <what list_sessions returned>, \"triggers\": "
             "<what list_triggers returned>}, each page as it came (a list of them for several), "
             "no file; do what it prints.")
TIDY_SAID = ("tidy: once today, after this wake's work and asking nobody: the app's own "
             "old chats (tools/tidy.py). " + TIDY_GIVE)
TIDY_NOW = ("tidy: now, once the batches above are sent, asking nobody: the app's chat this one "
            "took the page over from is put away as soon as its work is saved, the brief "
            "moved here first (tools/tidy.py). " + TIDY_GIVE)


def cmd_listen(a) -> int:
    import app_listen
    import app_model
    _, now = app_model.clock(None, a.now)
    out = a.out or os.path.join(a.dump, "listen_out")
    got = check_in(a.dump, app_listen.this_chat(a.chat), now, out, listen=a.listen,
                   helper=a.helper, hand=a.hand, update=a.update)
    if got["read"]:
        print(READ_FIRST.format(more=", ".join(got["read"])))
        return 0
    if got["move"]:
        print("listen: the page's records take their new names: send these batches first, in "
              "order, asking nobody. If one is refused, another chat did it already: read "
              "again into a new folder and run this once more.")
        for path in got["move"]:
            print(path)
    for line in got["got"]["lines"]:
        print(line)
    for path in got["got"]["batches"]:
        print(path)
    if got.get("stranded"):
        print("listen: work whose chat stopped twice is ended, so the page offers Try again: "
              "send this batch too, asking nobody:")
        for path in got["stranded"]:
            print(path)
    for line in got["upkeep"]:
        print(line)
    if got["prune"]:
        print(PRUNE_SAID)
        for path in got["prune"]:
            print(path)
    if got["tidy"]:
        print(TIDY_NOW if got.get("retire") else TIDY_SAID)
    return 0


# ------------------------------------------------------------------ a ring, in one command
#
# Each model step of a chat re-reads its whole history, so a step is the cost. A ring took
# about fifteen before the person saw an answer: the update check, the read, the check-in
# and its batch, the taps' claim, its batch, the taps applied, their batches, `next`, its
# claim (2026-11-03). `wake` runs all of that in code after the one read, and prints only
# the batches, in the order they must be sent, and the one thing left to do.

WAKE_STATE = ".wake.json"            # in the wake's folder: how far this wake has got
# Small work done here that one wake takes together, each claimed in the same pass: one talk
# a wake, each followed by a new read, took ten questions about 15 minutes and some 30 reads
# (the maintainer's copy, 2026-11-05). Never an update or a republish (they change the code or
# the page itself) and never a brief.
BATCH_HERE = ("talk", "reply", "follow_up", "tweak", "evaluate", "own_profile", "form_answers",
              "files", "profile", "general_resume", "research")
BATCH_MAX = 10
WAKE_UPDATED = "LJS_WAKE_UPDATED_FROM"
WAKE_SAID = "LJS_WAKE_SYNC_SAID"
# What a wake reads, once: steps 1 to 3's records, and the page's view (`screen`), `meta` and
# `addr`, so step 5's `app.py view` needs no second read.
WAKE_READS = ("actions", "receipts", "work", "beats", "holds", "meta", "screen", "addr")
# What each batch is, as `wake` says it beside the batch. Batches that may be refused
# together are sent as one, which the store takes whole or not at all: a refusal then means
# another chat took the page or holds something claimed in it, and a new read and wake leave
# that to it. Nothing in the copy has changed before such a batch is accepted.
SEND = {"move": "the page's records take their new names, once",
        "listen": "the check-in: this chat answers the page",
        "taps": "what the person did, claimed",
        "applied": "what the person did, applied, with its receipts",
        "work": "the work below, claimed"}
REFUSED = ("Refused: another chat {who}, or a record's own stored number was wrong. First keep "
           "the version the refusal names: python3 tools/app.py version \"{dump}\" "
           "<collection>/<doc id> <that version> (a wrong number is put right that way, never "
           "bounced on). Then read again into a new folder and wake once more (python3 "
           "tools/app.py reads <it> first: a whole read)")


def _wake_state(dump: str) -> dict:
    try:
        with open(os.path.join(dump, WAKE_STATE), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_wake_state(dump: str, state: dict) -> None:
    os.makedirs(dump, exist_ok=True)
    with open(os.path.join(dump, WAKE_STATE), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
        fh.write("\n")


def _git(*args: str) -> tuple[int, str]:
    import subprocess
    try:
        r = subprocess.run(["git", "-C", os.path.dirname(_HERE), *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60,
                           stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def days_check(on: str, chat: str) -> dict:
    """The day's update check, as `brief.py --start` runs it: `sync_app.py --if-stale`, and
    only while today's has not run. {"ran", "rc", "said", "landed", "before"}."""
    import subprocess
    try:
        import sync_app
        stale = sync_app.stale()
    except Exception:  # noqa: BLE001  never a reason not to answer the page
        stale = False
    if not stale:
        return {"ran": False}
    before = _git("rev-parse", "HEAD")[1]
    # The chat's id goes with it, so the update's page steps know which chat this is.
    env = dict(os.environ, **({"LJS_CHAT": chat} if chat else {}))
    r = subprocess.run([sys.executable, os.path.join(_HERE, "sync_app.py"), "--if-stale",
                        "--on", on or "<this chat's model>"], cwd=os.path.dirname(_HERE),
                       env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    after = _git("rev-parse", "HEAD")[1]
    return {"ran": True, "rc": r.returncode, "said": (r.stdout or "") + (r.stderr or ""),
            "landed": bool(before and after and before != after), "before": before}


def update_stops(before: str) -> list[str]:
    """What an update taken since `before` changed that a wake cannot carry on over: "page"
    (the page's own code, which is put up first) and "skill" (this chat already holds the
    app skill it loaded)."""
    import app_setup
    out = []
    try:
        if app_setup.page_record().get("url") and app_setup.set_up() and \
                not app_setup._page_current():
            out.append("page")
    except Exception:  # noqa: BLE001
        pass
    if before and _git("diff", "--quiet", before, "HEAD", "--",
                       ".claude/skills/app/SKILL.md")[0] == 1:
        out.append("skill")
    return out


def _again(a, chat: str) -> str:
    flags = (f" --kind {a.kind}" if a.kind else "") + \
        (f" --on \"{a.on}\"" if a.on else "") + (" --no-sessions" if a.no_sessions else "")
    return f"python3 tools/app.py wake \"{a.dump}\" --chat {chat}{flags}"


# The ring is a comment sent to Claude; left open it stays unread in the Claude app for ever.
RESOLVE_RING = ("last, once this wake's work is done: ArtifactComments resolve (url {url}, "
                "thread_id: the thread this wake came on, which the notification that woke you "
                "names as thread=...). Resolving is not answering: leave no reply. A wake with "
                "no such thread (a timer, a run by hand) has nothing to resolve.")


def cmd_wake(a) -> int:
    """A ring from the page, after one read into `dump` (WAKE_READS): the day's update check
    when it is due, the listener's check-in, the person's taps claimed and applied, and the
    next work claimed, all in code. Prints the batches in the order they are sent and the
    one thing left to do. A tap that changes the copy is applied only once its claim is
    accepted, so that wake prints the claim and is run again over the same folder; run again
    after it finished, it takes the next work (step 3 again)."""
    import app_actions
    import app_listen
    import app_model
    import app_setup
    import page_db
    _, now = app_model.clock(None, a.now)
    chat = app_listen.this_chat(a.chat)
    kind = a.kind or app_listen.chat_kind()
    url = app_setup.page_record().get("url") or "<the page>"
    st = _wake_state(a.dump)
    run = int(st.get("runs") or 0) + 1
    rd = os.path.join(a.dump, "wake", str(run))
    phase = str(st.get("phase") or "new")
    head: list[str] = []
    notes: list[str] = []
    # (batch file, what it is, whether it goes in one batch with the one before)
    sends: list[tuple[str, str, bool]] = []
    after: list[str] = list(st.get("after") or [])
    tidy_due = bool(st.get("tidy"))
    applied_any = False
    copy_now = False             # this run applies taps that change the copy, claimed before

    if phase == "new":
        if os.environ.get(WAKE_UPDATED):
            # Run again by the wake before this one, on the code its update brought in.
            try:
                with open(os.environ.get(WAKE_SAID) or "", encoding="utf-8") as fh:
                    said = fh.read()
            except OSError:
                said = ""
            check = {"ran": True, "rc": 0, "said": said, "landed": True,
                     "before": os.environ[WAKE_UPDATED]}
        else:
            check = days_check(a.on, chat)
            if check.get("landed"):
                # The update brought new code: the rest of this wake runs on it, not on the
                # copy this process loaded before the update.
                import subprocess
                path = os.path.join(a.dump, ".wake-sync.txt")
                os.makedirs(a.dump, exist_ok=True)
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(check["said"])
                sys.stdout.flush()
                env = dict(os.environ, **{WAKE_UPDATED: check["before"], WAKE_SAID: path})
                return subprocess.run([sys.executable, os.path.abspath(__file__)] + list(a.argv),
                                      env=env).returncode
        if check.get("ran"):
            said = check["said"].rstrip("\n").splitlines()
            stops = update_stops(check["before"]) if check.get("landed") else []
            # Worded as start words the same check, for the same steps.
            sync_line = (f"python3 tools/sync_app.py --if-stale --on \"{a.on or '<your model>'}\""
                         f"   ({app_setup.SYNC_DO}{app_setup.SYNC_PAGE}): this command ran it; "
                         "what it printed is below.")
            if stops:
                what = " and ".join({"page": "the page's own code", "skill": "this skill"}[s]
                                    for s in stops)
                out = [f"wake: the day's update check took an update that changes {what}: this "
                       "wake stops here and has written nothing.", "Claude, do this:",
                       "1. " + sync_line]
                n = 2
                if "skill" in stops:
                    out.append(f"{n}. Claude: .claude/skills/app/SKILL.md changed. This chat is "
                               "still following the copy it loaded: read it again now, before "
                               "going on.")
                    n += 1
                out.append(f"{n}. Then read the page again into a new folder (python3 "
                           "tools/app.py reads <the new folder>, and its queries) and wake once "
                           "more with it: "
                           + _again(a, chat).replace(f"\"{a.dump}\"", "\"<the new folder>\""))
                out.append("What the day's update check printed:")
                print("\n".join(out + said))
                return 0
            head = [sync_line] + said + ["(end of what the update check printed)"]
        reads = {}
        try:
            import page_reads
            if os.path.isfile(os.path.join(a.dump, page_reads.PLAN)):
                reads = page_reads.assemble(a.dump, now)
        except Exception:  # noqa: BLE001  a read made without `reads`: the folder as it is
            reads = {}
        got = check_in(a.dump, chat, now, os.path.join(rd, "listen"),
                       partial=bool(reads) and not reads.get("full"))
        if got["read"]:
            print("\n".join(head + [READ_FIRST.format(more=", ".join(got["read"]))]))
            return 0
        decided = got["got"]
        if not chat:
            print("\n".join(head + decided["lines"]))
            return 2
        if decided["role"] != "listener":
            print("\n".join(head + decided["lines"] + [
                "wake: this chat does not answer the page: write nothing else and end the "
                "turn; the chat that answers it takes this."]))
            return 0
        sends += [(p, "move", False) for p in got["move"]]
        sends += [(p, "listen", i > 0) for i, p in enumerate(decided["batches"])]
        sends += [(p, "listen", True) for p in got.get("stranded") or []]
        notes += [ln for ln in decided["lines"]
                  if not ln.startswith(("listen: this chat answers the page.",
                                        "listen: this chat answers the page now."))]
        notes += got["upkeep"]
        if reads:
            notes.append(page_reads.summary(page_db.load(a.dump), chat, reads))
        after, tidy_due = list(got["prune"]), bool(got["tidy"])
        todo = app_actions.pending(page_db.load(a.dump), chat, now)
        phase = "next"
        if todo:
            # Only what is not this chat's already: a tap it claimed on an earlier wake (one
            # that stopped before applying it), or applied whose receipt never landed, is
            # applied or receipted now, never claimed again (the maintainer's copy, 2026-11-05).
            need = app_actions.to_claim(todo, chat, now)
            if need:
                claim = app_actions.claim(a.dump, chat, now, os.path.join(rd, "taps"),
                                          only=need)
                sends += [(p, "taps", True) for p in claim["batches"]]
            phase = "apply"
            changes = [aid for aid, act, _v in todo
                       if str(act.get("action") or "") not in app_actions.DB_ONLY]
            copy_now = bool(changes)
            if set(changes) & set(need):
                # A tap that changes the copy waits for its claim: if another chat holds it,
                # nothing here may have changed.
                _save_wake_state(a.dump, {"phase": "claimed", "runs": run, "after": after,
                                          "tidy": tidy_due})
                _print_wake(head, notes, _send_as(sends, rd, a.dump), url, then=[
                    "then: send these, and once every one is accepted, run this again with the "
                    "same folder: it applies what the person did (it changes your copy, so "
                    "never before the claim is accepted) and takes the next work: "
                    + _again(a, chat)])
                return 0
    elif phase == "claimed":
        phase = "apply"
    # Everything from the check-in on goes as one batch, unless this run changed the copy: a
    # batch refused after that would leave its receipts unsent, and a new read would apply
    # the taps again from a folder without this one's ledger.
    joined = st.get("phase") is None and not copy_now

    if phase == "apply":
        got = app_actions.apply_dir(a.dump, chat, now, os.path.join(rd, "apply"))
        sends += [(p, "applied", joined) for p in got["batches"]]
        # The receipts and any work a tap queued, as they will be once sent: `next` below
        # sees that work and pins to the versions the batch leaves.
        page_db.keep_landed(a.dump, got["batches"], skip=("actions",))
        counts = [f"{len(got[k])} {w}" for k, w in (("ok", "applied"), ("stale", "changed since "
                  "they saw it"), ("conflict", "could not be done"), ("again", "applied before"))
                  if got.get(k)]
        if counts:
            notes.append("taps: " + ", ".join(counts) + " (each receipt says it on the page)")
        applied_any = applied_any or bool(got.get("ok"))
        if got.get("fetch"):
            ids = sorted({x for f in got["fetch"] for x in f.get("assets") or []})
            notes.append(
                "fetch: an action names files the person added on the page: Artifact read each "
                f"(url {url}, path the asset id: {', '.join(ids)}) into \"{a.dump}/assets\", "
                f"then python3 tools/app.py apply \"{a.dump}\" --chat {chat} --assets "
                f"\"{a.dump}/assets\", send every batch it prints, and delete each asset a "
                "receipt names in remove_assets (Artifact delete, url, path).")
        # A setup answer or a resume given on the page: setup carries on here and now, as
        # start says; a wake said only "nothing else is waiting" (journeys audit 13).
        acts = page_db.load(a.dump).get("actions") or {}
        if any(str(((acts.get(x) or {}).get("data") or {}).get("action") or "")
               .startswith("setup.") for k in ("ok", "again") for x in got.get(k) or []):
            notes += app_setup.carry_on()
        try:
            import routines
            if routines.calls():
                notes.append("brief: a tap moved the brief or paused the search: python3 "
                             "tools/routines.py calls lists the scheduled-task calls; make each, "
                             "then python3 tools/routines.py called <n> (--id <the new task's "
                             "id> for one it created).")
        except Exception:  # noqa: BLE001  no profile yet, or no registry
            pass

    db = page_db.load(a.dump)
    away = running_elsewhere(db, chat)
    if away:
        # A job's own chat can stop on a question to the person (an approval it needs), with
        # nobody there to see it: the page said only "may have stopped" (X-7, X-8).
        notes.append("jobs in chats of their own: get_session each ("
                     + ", ".join(f"{c} for {w}" for w, c in away) + "); for one whose "
                     f"status_bucket is blocked: python3 tools/app.py pin \"{a.dump}\" --work "
                     "<its work id> --blocked, and send the batch it prints. Say nothing about "
                     "it in the chat: its card on the page says it.")
    chosen = choose(db, chat, kind, now, on=a.on, no_sessions=a.no_sessions,
                    claim_out=os.path.join(rd, "work"))
    then: list[str] = []
    if chosen:
        sends += [(p, "work", joined) for p in chosen["batches"]]
        # Claimed, as it will be once sent: run again over this folder, `next` takes the one
        # after it, pinned to the versions this claim leaves.
        page_db.keep_landed(a.dump, chosen["batches"])
        also: list[dict] = []

        def small(c):
            return bool(c) and c.get("run") == "here" and c.get("kind") in BATCH_HERE \
                and not c.get("heavy")
        if small(chosen):
            # Every other small item waiting is taken in this same pass, each its own claim
            # pinned to the versions the one before leaves (BATCH_HERE).
            while len(also) < BATCH_MAX - 1:
                nxt = choose(page_db.load(a.dump), chat, kind, now, on=a.on,
                             no_sessions=a.no_sessions,
                             claim_out=os.path.join(rd, f"work{len(also) + 2}"))
                if not small(nxt):
                    break
                sends += [(p, "work", False) for p in nxt["batches"]]
                page_db.keep_landed(a.dump, nxt["batches"])
                also.append(nxt)
        more = choose(page_db.load(a.dump), chat, kind, now, on=a.on,
                      no_sessions=a.no_sessions) is not None
        shown = dict(chosen)

        def with_item(c):
            item = ((db.get("work") or {}).get(c["work"]) or {}).get("data") or {}
            return dict(c, **{k: item[k] for k in ("args", "answers", "note") if k in item})
        if chosen.get("run") == "here":
            shown = with_item(chosen)
            # Finishing it writes the item, its locks and this chat's heartbeat, which this
            # folder does not see: the next item is taken from a new read.
            # Every follow-up claimed here is one run of one command, in code: never the
            # networking skill or a draft by hand each (the maintainer, 2026-11-05).
            ups = [c for c in [chosen] + also if c.get("kind") == "follow_up"]
            n_ups = sum(1 + len(c.get("with") or []) for c in ups)
            run_ups = (f"python3 tools/app.py follow-ups \"{a.dump}\" --chat {chat}, which "
                       f"drafts the {n_ups} follow-up{'s' if n_ups != 1 else ''} claimed here in "
                       "code and finishes them in one batch (load no skill for them), and do "
                       "what it prints")
            if not also and ups:
                what = "run " + run_ups
            else:
                what = (f"do it here, now, as step 4's row says for a {chosen['kind']}" if not also
                        else f"do each here, now, in order (the one under next:, then each "
                             f"also:), as step 4's row says for its kind; they are "
                             f"{len(also) + 1} items, every one claimed in this pass" +
                             (f"; for the follow-ups, one run: {run_ups}" if ups else ""))
            then.append(f"then: once {'its claim is' if not also else 'their claims are'} "
                        f"accepted, {what}. Its claim marks it running at its first "
                        "stage, so no progress pin follows; " + (
                            "it finishes them itself." if not also and ups else
                            "finish it as step 5 says.") + (
                            " More is waiting: then read again into a new folder and wake "
                            "once more (step 3 again)." if more else ""))
        else:
            call = "create_session" if chosen.get("run") == "child session" else "Agent"
            then.append(f"then: only once the work's claim is accepted, make the {call} call "
                        "in `next` below exactly as it is printed" + (
                            f" (first {chosen['first']})" if chosen.get("first") else "") +
                        ", and never wait for it." + (
                            " More is waiting: then run this again with the same folder (step "
                            "3 again): " + _again(a, chat) if more else ""))
        then.append("next: " + _dump(shown).rstrip("\n"))
        for c in also:
            then.append("also: " + _dump(with_item(c)).rstrip("\n"))
    else:
        then.append("then: nothing else is waiting for this chat. " + (
            "Commit what the taps changed (python3 tools/save_state.py) with this wake's "
            "other work, then end the turn." if applied_any else "End the turn."))
    _save_wake_state(a.dump, {"phase": "done", "runs": run})
    last = [RESOLVE_RING.format(url=url)]
    if phase in ("next", "apply") and (after or tidy_due):
        last.append("after this wake's work, asking nobody:")
        if after:
            last += [PRUNE_SAID] + after
        if tidy_due:
            last.append(TIDY_SAID)
    _print_wake(head, notes, _send_as(sends, rd, a.dump), url, then=then + last)
    return 0


def _send_as(sends, out_dir: str, dump: str = "$D") -> list[tuple[str, str]]:
    """[(batch file, what it is and what a refusal means)]: each run of batches that go
    together joined into one file the store takes whole, where it fits in one."""
    import page_db

    def docs(path):
        with open(path, encoding="utf-8") as fh:
            return {(e["collection"], e["doc_id"]) for e in json.load(fh)}

    groups: list[tuple[list[str], list[str], set]] = []
    for path, what, join in sends:
        mine = docs(path)
        # One write a document in a batch (the work a tap queued, then its claim, go apart).
        if join and groups and groups[-1][1][-1] != "move" and not mine & groups[-1][2]:
            groups[-1][0].append(path)
            groups[-1][1].append(what)
            groups[-1][2].update(mine)
        else:
            groups.append(([path], [what], set(mine)))
    out = []
    # What a refusal means is said in full once, beside the first batch it applies to; every
    # later one says only who: the same 300 characters beside each batch were read again at
    # every later step of the chat (the maintainer, 2026-11-05).
    told = False

    def refused(who: str, tail: str = "") -> str:
        nonlocal told
        if told:
            return f". Refused: another chat {who}; as above"
        told = True
        return ". " + REFUSED.format(who=who, dump=dump) + tail
    for n, (paths, whats, _docs) in enumerate(groups, 1):
        names = list(dict.fromkeys(whats))
        said = "; ".join(SEND[w] for w in names)
        if names == ["move"]:
            said += refused("did it already")
        elif names == ["work"]:
            said += refused("took it")
        elif names != ["applied"]:
            said += refused("took the page or holds something claimed here",
                            ", which leaves that to it")
        files = paths
        if len(paths) > 1:
            entries = []
            for p in paths:
                with open(p, encoding="utf-8") as fh:
                    entries += json.load(fh)
            if len(entries) <= page_db.BATCH_MAX:
                w = page_db.Writes(os.path.join(out_dir, "send"))
                w.entries = entries
                files = w.save(f"send-{n}")
        out += [(f, said) for f in files]
    return out


def _print_wake(head, notes, sends, url, then) -> None:
    out = list(head)
    lead = ("wake: this chat answers the page; " + (f"{len(sends)} batch"
            f"{'es' if len(sends) != 1 else ''} to send" if sends else "nothing to send") + ".")
    out.append(lead)
    out += notes
    if sends:
        out.append(f"send, in this order, each as one ArtifactData batch (url {url}, its "
                   "entries as writes), one at a time, each after the one before is accepted:")
        out += [f"{i}. {p}   ({why})" for i, (p, why) in enumerate(sends, 1)]
    out += then
    print("\n".join(out))


def cmd_republish(a) -> int:
    import app_listen
    import app_model
    _, now = app_model.clock(None, a.now)
    got = app_listen.republish(a.out_dir, now)
    print("app: send this batch to the page (ArtifactData batch); a refusal means the request "
          "is already there. The listener publishes it.")
    for path in got["batches"]:
        print(path)
    return 0


def cmd_pinned(a) -> int:
    import app_listen
    app_listen.record_pin(a.answer)
    print("app: noted; the chat never offers the pin again" + (
        "" if a.answer == "yes" else ", and the page offers it again after a month at most"))
    return 0


def cmd_told(a) -> int:
    """Something said to the person once, from a chat with no page to carry it (choosing Auto,
    the PDF tools' line, a state stuck for days): kept with their answers, so no chat says it
    again (the page's card for it is ticked off by the same record)."""
    import app_setup
    try:
        app_setup.record_told(a.key)
    except ValueError as e:
        print(f"app: {e}; one of {', '.join(app_setup.TOLD)}")
        return 2
    print("app: noted; it is not said again. Save it with the rest (python3 tools/save_state.py)")
    return 0


def cmd_doorbells(a) -> int:
    """The page's old rings, cleared once: each tap leaves a comment sent to Claude that nothing
    resolved, and the Claude app counts them as unread. The chat resolves them, then notes it."""
    import app_setup
    if a.done:
        app_setup.save_said(app_setup.DOORBELLS, dt.date.today().isoformat())
        print("app: noted; the page's old rings are not cleared again. Save it with the rest "
              "(python3 tools/save_state.py)")
        return 0
    url = app_setup.page_record().get("url") or "<the page>"
    print(f"doorbells: ArtifactComments read (url {url}), following the cursor while there is "
          "more; resolve each thread whose first comment starts with [app] (ArtifactComments "
          "resolve, the url and that thread's id), never any other thread, and leave no reply. "
          "Then: python3 tools/app.py doorbells --done")
    return 0


def cmd_resume_saved(a) -> int:
    import app_model
    import app_setup
    if not os.path.isfile(a.file):
        print(f"app: there is no file at {a.file}")
        return 2
    got = app_setup.answers()
    resume = dict(got.get("resume") or {})
    if a.asset and resume.get("asset") not in (None, a.asset):
        print("app: that is not the resume the page holds; nothing changed")
        return 1
    resume.update(file=app_model.rel(os.path.abspath(a.file)), source=resume.get("source") or "asset")
    resume.pop("asset", None)
    got["resume"] = resume
    app_setup.save_answers(got)
    print("app: the resume is noted as saved; /setup reads it from there")
    return 0


def cmd_files_saved(a) -> int:
    """After `files` work uploaded documents to the page's file store (Artifact publish with
    asset true): each path with the id the upload gave, kept so the model offers the file
    for download and never asks for it again while the file is unchanged."""
    import app_model
    pairs = list(zip(a.items[0::2], a.items[1::2]))
    if not pairs or len(a.items) % 2:
        print("app: give each file's path and the asset id its upload returned, in pairs")
        return 2
    try:
        done = app_model.record_assets(pairs)
    except ValueError as e:
        print(f"app: {e}")
        return 1
    print(f"app: {len(done)} file{'s' if len(done) != 1 else ''} on your page: "
          + ", ".join(done))
    return 0


def cmd_propose(a) -> int:
    import app_model
    import app_setup
    roles = [" ".join(r.split()) for r in a.roles if r.strip()][:8]
    if not roles:
        print("app: name the roles to propose")
        return 2
    got = app_setup.answers()
    got["proposed_roles"] = {"roles": roles, "at": app_model.stamp(app_model.clock()[1])}
    app_setup.save_answers(got)
    print(f"app: the page asks about {len(roles)} roles next")
    return 0


def _links(given) -> list:
    """`--link` values as the page shows them: "<label>=<address>", or the address alone."""
    out = []
    for raw in given or ():
        label, sep, url = str(raw).partition("=")
        if not sep or "://" in label:
            label, url = "Open", str(raw)
        out.append({"label": " ".join(label.split()) or "Open", "url": url.strip()})
    return out


def cmd_done(a) -> int:
    """A finished work item as one batch (the app skill, step 5): done with its one-sentence
    summary (or failed, saying why), its locks removed, and with --reply-file the chat's
    answer in its conversation. No chat writes these by hand."""
    import app_listen
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    db = page_db.load(a.dump)
    reply = ""
    if a.reply_file == "-":
        reply = sys.stdin.read().strip()
    elif a.reply_file:
        try:
            with open(a.reply_file, encoding="utf-8") as fh:
                reply = fh.read().strip()
        except OSError as e:
            print(f"app: cannot read {a.reply_file}: {e.strerror or e}", file=sys.stderr)
            return 2
        if not reply:
            print("app: the answer file is empty", file=sys.stderr)
            return 2
    left = " ".join(str(getattr(a, "left_out", "") or "").split())
    if left:
        # A draft that stops because the job is not one they can take (where it is open, a hard
        # rule): the job leaves Jobs in the same step, ruled out with its reason, so the Brief and
        # Jobs stop counting it. Left to a second command, it stayed in "10 jobs to look at"
        # (2026-10-30) and a search's drafting left 18 of 37 to clear by hand (2026-11-05).
        item = ((db.get("work") or {}).get(page_db.safe_id(a.work)) or {}).get("data") or {}
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        if not args.get("url"):
            print("app: not finished: --left-out is for a job's draft, and this one names no "
                  "posting to take off Jobs", file=sys.stderr)
            return 2
        import exclude
        import person
        exclude.add(str(args["url"]), left, title=str(args.get("title") or ""),
                    company=str(args.get("company") or ""), basis="rules",
                    # The person's own day, never the computer's UTC date.
                    today=person.today(now).isoformat(),
                    path=person.state("job_scraper", "seen_jobs.json"))
        a.stopped, a.summary = True, a.summary or f"Not drafted: {left.rstrip('.')}."
    try:
        got = page_db.finish(db, a.work, now, a.out or os.path.join(a.dump, "out"),
                             summary=a.summary, status="failed" if a.failed else
                             "stopped" if a.stopped else "done",
                             error=a.failed, links=_links(a.link), reply=reply, thread=a.thread,
                             chat_kind=a.kind or app_listen.chat_kind(), dump_dir=a.dump,
                             chat=a.chat, question=a.question, about=a.about,
                             answer=_answer(a), answered=a.answered)
    except (KeyError, ValueError) as e:
        print(f"app: not finished: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
    kind = str((((db.get("work") or {}).get(page_db.safe_id(a.work)) or {}).get("data") or {})
               .get("kind") or "")
    if got["status"] == "done" and kind in page_db.FILES_AFTER:
        # The PDFs it made reach the page with no one asking: one `files` item for the chat
        # that answers the page, for every draft whose files the page lacks (a job's own chat
        # cannot upload them).
        try:
            missing = app_model.files_missing()
        except Exception:  # noqa: BLE001  no profile or no tracker: nothing to put up
            missing = []
        queued = page_db.queue_files(page_db.load(a.dump), missing, now,
                                     os.path.join(a.out or os.path.join(a.dump, "out"), "files"),
                                     dump_dir=a.dump, chat_id=app_listen.this_chat(a.chat)) \
            if missing else None
        if queued:
            got["files"] = {"work": queued["work"], "applications": queued["applications"]}
            got["batches"] = list(got["batches"]) + queued["batches"]
    print(_dump(got), end="")
    return 0


def _answer(a) -> dict | None:
    """The kind of answer a --question needs, as `done` takes it: --answer <kind>, each
    --choice "<value>=<words>" (or just its words), --min and --max for a number or a scale."""
    if not a.answer:
        return None
    choices = []
    for c in a.choice or []:
        value, _, words = str(c).partition("=")
        choices.append({"value": value.strip(), "label": (words or value).strip()})
    out = {"kind": a.answer, "choices": choices}
    for k in ("min", "max"):
        v = getattr(a, k)
        if v is not None:
            out[k] = int(v) if float(v).is_integer() else v
    if a.time_key:
        out["time"] = a.time_key
    return out


def cmd_search_drafts(a) -> int:
    """A search that drafts what it finds: a draft of each job on Jobs now that passes every
    rule, up to the number asked for, claimed with the search so this chat drafts them
    together (page_db.search_drafts); a draft not begun whose job fails a rule now stopped and
    the next taken. Run each time one of the search's shortlists is saved, and with --last
    once the round has ended."""
    import app_model
    import page_db
    from lookup_score import norm
    today, now = app_model.clock(a.today, a.now)
    db = page_db.load(a.dump)
    ctx = app_model.Ctx(today, now)
    jobs = app_model._jobs(ctx, {})
    rows = [dict(r["draft_work"]["args"]) for r in jobs["rows"]
            if app_model.to_look_at(r) and not r.get("from_round") and not r.get("added")]
    listed = {norm(str(r["draft_work"]["args"].get("url") or "")) for r in jobs["rows"]
              if r["status"] in ("new", "ready", "applied")}
    # Why a job left Jobs, in plain words: a ruling on it, the newest search's left-out list,
    # or the page's own read of the rules.
    why = {k: str(e.get("exclusion_reason") or "") for k, e in ctx.seen.items()
           if str(e.get("status") or "").lower() == "excluded"}
    try:
        import filtered
        newest = os.path.splitext(os.path.basename(app_model.newest_round()))[0]
        for e in (filtered.load(newest).get("filtered") or []) if newest else ():
            if isinstance(e, dict) and e.get("url"):
                why.setdefault(norm(str(e["url"])), str(e.get("reason") or ""))
    except SystemExit:
        pass                       # no left-out list for it: the rulings and the page say why
    why.update({norm(str(row.get("url") or "")): w
                for _n, _k, row, w in ctx._got.get("jobs_left_out") or []})
    left = {u: app_model.left_words(w)[len("Left out: "):] for u, w in why.items() if u and w}
    try:
        got = page_db.search_drafts(db, a.work, rows, now, a.out or os.path.join(a.dump, "out"),
                                    chat=a.chat, left=left, last=a.last, dump_dir=a.dump,
                                    listed=listed)
    except (KeyError, ValueError) as e:
        print(f"app: no drafts queued: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
    print(_dump(got), end="")
    return 0


FOLLOW_UP_DONE = "Your follow-up to {first} is ready to send."
FOLLOW_UP_NONE = "No follow-up is owed to {first} now."
FOLLOW_UP_ASK = "What should the follow-up to {first} say? I could not write one: {why}."


def _next_dir(base: str) -> str:
    n = 1
    while os.path.exists(os.path.join(base, str(n))):
        n += 1
    return os.path.join(base, str(n))


def follow_ups(dump: str, chat: str, now, today: str, out_dir: str,
               written: list | None = None) -> dict:
    """Every follow-up this chat holds (claimed together, `with` one another: page_db
    next_item), drafted in one run: code drafts each (followup_drafts.drafts, the gate
    included), keeps each clean draft where Messages shows it and finishes those items, all in
    one batch. What code could not write is left `to_write`, with one context block for all of
    it; `written` ([{"id": <contact id>, "text"}]) is what the chat wrote for those, gated the
    same way, kept and finished. One needing the person is put to them as a question; an
    application's or an interview's is left `by_hand` (/outcome Step 2b).
    {done, to_write, asked, by_hand, refused, context, batches}."""
    import followup_drafts
    import page_db
    db = page_db.load(dump)
    held = sorted(((str(d["data"].get("asked_at") or ""), wid) for wid, d in
                   (db.get("work") or {}).items()
                   if d["data"].get("kind") == "follow_up"
                   and str(d["data"].get("status") or "") in page_db.ACTIVE
                   and str(d["data"].get("claimed_by") or "") == chat))
    out = {"done": [], "to_write": [], "asked": [], "by_hand": [], "refused": [],
           "context": "", "batches": []}
    if not held:
        return out
    with followup_drafts.FoldersOnce():
        items, contacts, threads, tracker = followup_drafts.load(today)
        got = followup_drafts.drafts(items, contacts, threads, tracker, today)
        by_contact = {str(i.get("contact_id") or ""): i for i in got if i.get("half") == "contact"}
        names = {str(c.get("contact_id") or "").strip(): str(c.get("name") or "")
                 for c in contacts}
        passed: dict = {}
        if written:
            checked = followup_drafts.check(written, contacts, threads, today, got)
            followup_drafts.keep_checked(checked, contacts)
            passed = {c["id"]: c for c in checked if c["ok"]}
            out["refused"] = [{"id": c["id"], "findings": c["findings"]}
                              for c in checked if not c["ok"]]
        finishes: list[dict] = []
        keep = []
        for _at, wid in held:
            item = db["work"][wid]["data"]
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            cid = str(args.get("contact_id") or args.get("contact") or "")
            if not cid:
                out["by_hand"].append(wid)
                continue
            import app_model
            first = app_model.first_name(names.get(cid) or "") or "them"
            due = by_contact.get(cid)
            d = (due or {}).get("draft") or {}
            answered = item.get("answers") or args.get("answers")
            if cid in passed:
                finishes.append({"work": wid, "summary": FOLLOW_UP_DONE.format(first=first)})
            elif due is None or d.get("status") == "none":
                finishes.append({"work": wid, "summary": FOLLOW_UP_NONE.format(first=first)})
            elif d.get("status") == "ready" and not answered:
                keep.append(due)
                finishes.append({"work": wid, "summary": FOLLOW_UP_DONE.format(first=first)})
            elif d.get("status") == "write" and d.get("who") == "you" and not answered:
                why = " ".join(str(d.get("why") or "").split()).rstrip(".")
                finishes.append({"work": wid, "question": FOLLOW_UP_ASK.format(
                    first=first, why=why or "nothing on file to follow up on")})
            else:
                # Advise flagged code's draft, a reply is owed, or the person answered a
                # question about it: written here, from the thread, in one go with the rest.
                if d.get("status") == "check":
                    keep.append(due)
                out["to_write"].append({"work": wid, "contact": cid,
                                        **({"answers": answered} if answered else {})})
        followup_drafts.keep_drafted(keep)
        if out["to_write"]:
            out["context"] = followup_drafts.context(
                [t["contact"] for t in out["to_write"]], contacts, threads, today, got)
    entries: list[dict] = []
    for f in finishes:
        res = page_db.finish(page_db.load(dump), f["work"], now,
                             os.path.join(out_dir, "each", f["work"].replace("~", "@")),
                             summary=f.get("summary", ""), chat=chat, dump_dir=dump,
                             question=f.get("question", ""),
                             answer={"kind": "text"} if f.get("question") else None)
        for path in res["batches"]:
            with open(path, encoding="utf-8") as fh:
                entries += json.load(fh)
        out["asked" if f.get("question") else "done"].append(f["work"])
    if entries:
        w = page_db.Writes(out_dir)
        w.entries = entries
        out["batches"] = w.save("follow-ups")
    return out


def cmd_follow_ups(a) -> int:
    """Every follow-up this chat holds, drafted and finished in one run (follow_ups)."""
    import app_listen
    import app_model
    import app_setup
    import person
    _, now = app_model.clock(a.today, a.now)
    today = a.today or person.today(now).isoformat()
    chat = app_listen.this_chat(a.chat)
    written = None
    if a.written:
        try:
            raw = sys.stdin.read() if a.written == "-" else open(a.written, encoding="utf-8").read()
            written = json.loads(raw)
            written = written if isinstance(written, list) else [written]
        except (OSError, ValueError) as e:
            print(f"app: --written is a JSON list of {{\"id\": \"<contact id>\", \"text\": "
                  f"\"...\"}}: {e}", file=sys.stderr)
            return 2
    out_dir = a.out or _next_dir(os.path.join(a.dump, "follow-ups"))
    got = follow_ups(a.dump, chat, now, today, out_dir, written=written)
    url = app_setup.page_record().get("url") or "<the page>"
    said = [f"follow-ups: {len(got['done'])} finished, each draft on its person's card in "
            f"Messages; {len(got['asked'])} put to the person as a question; "
            f"{len(got['to_write'])} to write here; {len(got['by_hand'])} by hand."]
    if got["batches"]:
        said.append(f"send each as one ArtifactData batch (url {url}, its entries as writes), "
                    "in order:")
        said += got["batches"]
    for r in got["refused"]:
        said.append(f"refused, write it again: {r['id']}: " + "; ".join(r["findings"]))
    if got["to_write"]:
        said.append(
            f"then: write these {len(got['to_write'])} in one go, from what is below (an "
            "`answers` is what the person said on the page), and pass them all at once: "
            f"python3 tools/app.py follow-ups \"{a.dump}\" --chat {chat} --written - with "
            "[{\"id\": \"<contact id>\", \"text\": \"...\"}] on its input. It gates each, keeps "
            "the ones that pass on their cards and finishes them.")
        said += [f"to write: {t['contact']} (work {t['work']})" + (
            f", their answer: {json.dumps(t['answers'], ensure_ascii=False)}"
            if t.get("answers") else "") for t in got["to_write"]]
        said.append(got["context"].rstrip("\n"))
    for wid in got["by_hand"]:
        said.append(f"by hand: {wid}, an application's or an interview's follow-up: /outcome "
                    "Step 2b, then its own app.py done.")
    if got["done"] or got["asked"]:
        said.append(f"last: once for all of them, python3 tools/app.py view \"{a.dump}/view\" "
                    f"--dump \"{a.dump}\" --chat {chat}, and send its batch (step 5).")
    print("\n".join(said))
    return 0


def cmd_ask(a) -> int:
    """Work queued from something said in a chat, as the page's own Ask queues it, so no chat
    writes a work item by hand. `next` takes it like any other."""
    import app_listen
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    try:
        args = json.loads(a.args) if a.args else {}
    except ValueError:
        print("app: --args is JSON, like '{\"contact\": \"<contact id>\"}'", file=sys.stderr)
        return 2
    try:
        got = page_db.ask(page_db.load(a.dump), a.kind, a.title, now,
                          a.out or os.path.join(a.dump, "out"), args=args, to=a.to,
                          chat_id=app_listen.this_chat(a.chat), item_id=a.id, dump_dir=a.dump,
                          here=a.here, chat_kind=app_listen.chat_kind())
    except ValueError as e:
        print(f"app: not asked: {e}", file=sys.stderr)
        return 2
    print(_dump(got), end="")
    return 0


def cmd_version(a) -> int:
    """A refused write named a record's current version: kept in the folder, so the same
    command run again pins to it (once; a second refusal means read again)."""
    import page_db
    try:
        kept = page_db.note_version(a.dump, a.record, a.version)
    except (KeyError, ValueError) as e:
        print(f"app: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
    try:
        import page_reads
        page_reads.want_full()
    except Exception:  # noqa: BLE001  nothing kept to read wholly
        pass
    print(f"app: {kept} is at version {a.version} in this folder; run the refused command "
          "again, once")
    return 0


def cmd_reads(a) -> int:
    """What a wake reads: the queries, one line each (page_reads)."""
    import app_model
    import app_setup
    import page_reads
    _, now = app_model.clock(None, a.now)
    if not a.dump:
        # The listener's own look at a ring that names the page's revision: no read at all.
        if a.rev is None:
            print("app: give a folder to read into, or --rev <the ring's revision>",
                  file=sys.stderr)
            return 2
        print(page_reads.say_plan({"nothing": True}, "", "") if page_reads.seen_rev(a.rev)
              else "reads: new since the last read: pass the ring on (the app skill, step 0).")
        return 0
    got = page_reads.plan(a.dump, now, full=a.full, rev=a.rev)
    url = app_setup.page_record().get("url") or "<the page>"
    print(page_reads.say_plan(got, a.dump, url))
    try:
        import land
        waiting = land.github_waiting()
    except Exception:  # noqa: BLE001  nothing kept of a landing
        waiting = ""
    if waiting:
        print(waiting)
    return 0


CLAIMED_UNDER = ("the chat id this job was claimed under (app.py next --chat): a job another "
                 "chat has taken on since is refused, and nothing is written to it")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="app.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd")

    def clocked(p):
        p.add_argument("--today", default=None, help="YYYY-MM-DD (else LJS_TODAY, else today)")
        p.add_argument("--now", default=None, help="an ISO time in UTC, for a fixed clock")
        return p

    p = clocked(sub.add_parser("model", help="the view model, as JSON"))
    p.add_argument("--out")
    p = clocked(sub.add_parser("view", help="the model as view/* database writes"))
    p.add_argument("out_dir")
    p.add_argument("--dump", default="", help="a dump of view/ and meta/, for the versions")
    p.add_argument("--chat", default="chat")
    p.add_argument("--work", default="", help="the job this chat was started for: a job's own "
                                              "chat draws the page once it is done, as the chat "
                                              "that answers the page does")
    p.add_argument("--end", action="store_true",
                   help="the end of this batch of work: start the save in the background (once "
                        "for the batch) and keep what the wake cost")
    p.add_argument("--message", default="", help="with --end: what changed, for the save")
    p = clocked(sub.add_parser("page", help="the page to publish: in parts with --out-dir, "
                                            "else as one HTML file"))
    p.add_argument("--out")
    p.add_argument("--out-dir", dest="out_dir", default="",
                   help="write the page in parts here and print the publishes to make")
    p.add_argument("--url", default="", help="the page's address, when it is published already")
    p.add_argument("--on-page", dest="on_page", default=None,
                   help="what the published page holds, as Artifact list (scope files) printed "
                        "it: a file, or - for what comes in")
    p.add_argument("--whole", action="store_true",
                   help="put every code file up again, not only the ones the page lacks")
    p = sub.add_parser("apply", help="apply the page's actions, with receipts")
    p.add_argument("dump")
    p.add_argument("--chat", default="chat", help="this chat's id, for the receipts")
    p.add_argument("--claim", action="store_true",
                   help="only claim the pending actions (a pinned batch), apply nothing")
    p.add_argument("--out", default=None, help="where the batch files go (default <dump>/out)")
    p.add_argument("--assets", default=None,
                   help="the folder the page's assets an action names were fetched into "
                        "(Artifact read, path = the asset id): a LinkedIn download's files")
    p.add_argument("--now", default=None)
    p = sub.add_parser("next", help="the queued work item this chat should take")
    p.add_argument("dump")
    p.add_argument("--job-chat", dest="job_chat", action="store_true",
                   help="this chat is a big job's own: take only big work, and do it here")
    p.add_argument("--chat", required=True)
    p.add_argument("--kind", required=True, choices=("cloud", "computer"))
    p.add_argument("--claim-out", dest="claim_out", default=None,
                   help="also write the claim as a batch file in this folder")
    p.add_argument("--on", default="", help="this chat's model: a child gets the model its "
                                            "work needs")
    p.add_argument("--no-sessions", dest="no_sessions", action="store_true",
                   help="this chat cannot start a chat of its own (no create_session): a big "
                        "job runs as a background agent instead")
    p.add_argument("--now", default=None)
    p = sub.add_parser("pin", help="a running item's progress, with its lease renewed")
    p.add_argument("dump")
    p.add_argument("--work", required=True, action="append",
                   help="the work item's id; once for each member of a batch")
    p.add_argument("--stage", default=None, help="the stage's key or number")
    p.add_argument("--line", default="", help="one plain line of what happened")
    p.add_argument("--done", type=int, default=0)
    p.add_argument("--total", type=int, default=0)
    p.add_argument("--left-s", dest="left_s", type=int, default=None,
                   help="seconds left in this stage, when the work itself says")
    p.add_argument("--log", default="", help="a search's round.log: the count and time left")
    p.add_argument("--chat", default="", help=CLAIMED_UNDER)
    p.add_argument("--out", default="", help="where the batch goes (default <dump>/out)")
    p.add_argument("--now", default=None)
    p.add_argument("--blocked", action="store_true",
                   help="its own chat waits on the person (get_session says blocked)")
    p = sub.add_parser("busy", help="what this chat is doing for the person, on the page")
    p.add_argument("dump")
    p.add_argument("line", nargs="?", default="", help="a few plain words")
    p.add_argument("--done", action="store_true", help="it has finished")
    p.add_argument("--chat", default="")
    p.add_argument("--kind", default="", choices=("", "cloud", "computer"))
    p.add_argument("--out", default="", help="where the batch goes (default <dump>/out)")
    p.add_argument("--now", default=None)
    p = sub.add_parser("progress", help="the stages of a kind of work, with their seconds")
    p.add_argument("kind")
    p = clocked(sub.add_parser("check", help="check a model against the contract"))
    p.add_argument("--model", default=None, help="a model file (default: build one now)")
    p = sub.add_parser("start", help="what this chat does next, whatever the copy's state")
    p.add_argument("--on", default="", help="this chat's model, for the day's check")
    p.add_argument("--tools", default="", help="the browser tools this chat has")
    p.add_argument("--page", default="", help="a page already published for this person")
    p.add_argument("--chat", default="", help="this chat's id (else Claude Code's own)")
    p.add_argument("--listen", action="store_true",
                   help="the person asked this chat to look after the page")
    p.add_argument("--helper", action="store_true", help="this chat is the page's helper")
    p.add_argument("--work", default="", help="this chat was started for one work item")
    p.add_argument("--dump", default="", help="a read of the page's meta: its data is not "
                                              "written again when it is already current")
    p.add_argument("--paste", action="store_true",
                   help="print the line a person pastes into a chat on their computer")
    p = sub.add_parser("published", help="keep the page's address once it is published")
    p.add_argument("url")
    p.add_argument("--chat", default="")
    p.add_argument("--out", default="", help="where the listener's batch goes")
    p.add_argument("--dump", default="", help="the page's waiting republish requests, read")
    p.add_argument("--parts", default="", help="the folder app.py page --out-dir built and "
                                               "every publish it printed went through")
    p.add_argument("--why", default="", help="with none: why this chat cannot publish")
    p = sub.add_parser("listen", help="is this chat the page's listener? and its check-in")
    p.add_argument("dump")
    p.add_argument("--chat", default="")
    p.add_argument("--listen", action="store_true", help="the person asked this chat to")
    p.add_argument("--update", action="store_true",
                   help="this chat has the page's new code: it takes the page from a quiet one")
    p.add_argument("--helper", action="store_true")
    p.add_argument("--hand", default="", help="give the page to this chat (the new helper)")
    p.add_argument("--out", default="")
    p.add_argument("--now", default=None)
    p = sub.add_parser("wake", help="a ring from the page, in one command: the day's check, "
                                    "the check-in, the taps and the next work")
    p.add_argument("dump")
    p.add_argument("--chat", default="")
    p.add_argument("--kind", default="", choices=("", "cloud", "computer"),
                   help="this chat's kind (default: what Claude Code says)")
    p.add_argument("--on", default="", help="this chat's model")
    p.add_argument("--no-sessions", dest="no_sessions", action="store_true",
                   help="this chat cannot start a chat of its own: a big job runs as a "
                        "background agent")
    p.add_argument("--now", default=None)
    p = sub.add_parser("republish", help="ask the listener to publish the page's new code")
    p.add_argument("out_dir")
    p.add_argument("--now", default=None)
    p = sub.add_parser("answer", help="a setup answer the person gave in the chat, kept as "
                                      "the page keeps one")
    p.add_argument("step", help="the setup question it answers (resume, work, ...)")
    p.add_argument("--field", action="append", default=[], help="key=value, for a question "
                                                                  "with more than one field")
    p.add_argument("--text", default="", help="their words")
    p.add_argument("--text-file", dest="text_file", default="", help="their words, in a file")
    p = sub.add_parser("pinned", help="their answer to pinning the page")
    p.add_argument("answer", choices=("yes", "no"))
    p = sub.add_parser("told", help="something said to the person once, never again")
    p.add_argument("key")
    p = sub.add_parser("doorbells", help="the page's old rings, cleared once")
    p.add_argument("--done", action="store_true", help="note they are cleared")
    p = sub.add_parser("resume-saved", help="the resume the page held, saved in the copy")
    p.add_argument("file")
    p.add_argument("--asset", default="")
    p = sub.add_parser("files-saved", help="documents put in the page's file store, each "
                                           "with its asset id")
    p.add_argument("items", nargs="+", metavar="PATH ASSET")
    p = sub.add_parser("propose", help="the roles setup asks the person about")
    p.add_argument("roles", nargs="+")
    p = sub.add_parser("done", help="a work item left as one batch: done, failed, stopped "
                                    "or asked about, its locks removed, and the answer in its "
                                    "conversation")
    p.add_argument("dump")
    p.add_argument("--work", required=True, help="the work item's id")
    p.add_argument("--summary", default="", help="one short sentence of what is ready")
    p.add_argument("--reply-file", dest="reply_file", default="",
                   help="the answer for the person, shown in the conversation; - reads it "
                        "from the input")
    p.add_argument("--thread", default="", help="the conversation (default: the item's own)")
    p.add_argument("--failed", default="", help="it did not finish: why, in plain words")
    p.add_argument("--stopped", action="store_true", help="they tapped Stop: it stops here")
    p.add_argument("--question", default="",
                   help="it needs the person first: one plain question, asked on the page; "
                        "their answer puts it back in the queue. Only when it cannot be "
                        "finished honestly without them (templates/app/DESIGN.md, \"Asking "
                        "the person\")")
    p.add_argument("--about", default="",
                   help="with --question: the exact words of the draft or of their message "
                        "it is about, shown quoted over it")
    p.add_argument("--answer", default="", choices=("", "yesno", "choice", "date", "time",
                                                    "number", "scale", "text"),
                   help="with --question: the kind of answer, so the page draws its control "
                        "(a Yes and a No, chips, a date picker, a time, a number, a slider); "
                        "text only when nothing else fits")
    p.add_argument("--choice", action="append", default=[],
                   help="with --answer choice: \"<value>=<words>\", two to six of them")
    p.add_argument("--min", type=float, default=None, help="with --answer number or scale")
    p.add_argument("--max", type=float, default=None, help="with --answer number or scale")
    p.add_argument("--time-key", dest="time_key", default="",
                   help="with --answer date: ask the time beside the day")
    p.add_argument("--link", action="append", default=[],
                   help="\"<label>=<address>\" shown with it (more than one allowed)")
    p.add_argument("--chat", default="", help=CLAIMED_UNDER)
    p.add_argument("--kind", default="", choices=("", "cloud", "computer"))
    p.add_argument("--answered", action="append", default=[],
                   help="a form's question answered (form_answers), in the form's own words: "
                        "its card says Done once each is on it (more than one allowed)")
    p.add_argument("--out", default="", help="where the batch goes (default <dump>/out)")
    p.add_argument("--left-out", dest="left_out", default="",
                   help="a draft stopped because the job is not one they can take: why, in "
                        "plain words; the job leaves Jobs, ruled out with that reason")
    p.add_argument("--now", default=None)
    p = sub.add_parser("search-drafts", help="a search that drafts what it finds: a draft of "
                                             "each job that passes every rule, claimed with it")
    p.add_argument("dump")
    p.add_argument("--work", required=True, help="the search's work id")
    p.add_argument("--chat", default="", help=CLAIMED_UNDER)
    p.add_argument("--last", action="store_true",
                   help="the round has ended: the search has found all it will")
    p.add_argument("--out", default="", help="where the batch goes (default <dump>/out)")
    clocked(p)
    p = sub.add_parser("follow-ups", help="every follow-up this chat holds, drafted in code "
                                          "and finished in one batch")
    p.add_argument("dump")
    p.add_argument("--chat", required=True, help=CLAIMED_UNDER)
    p.add_argument("--written", default="",
                   help="what this chat wrote for those code could not: a JSON list of "
                        "{id, text}, or - for what comes in")
    p.add_argument("--out", default="", help="where the batch goes (default <dump>/follow-ups)")
    clocked(p)
    p = sub.add_parser("ask", help="work queued from a chat message, as the page queues it")
    p.add_argument("dump")
    p.add_argument("--kind", required=True, help="the kind of work (app.py progress <kind>)")
    p.add_argument("--title", required=True, help="what it is, in a few plain words")
    p.add_argument("--args", default="", help="its args, as JSON (the app skill, step 4)")
    p.add_argument("--to", default="", choices=("", "cloud", "computer", "either"))
    p.add_argument("--id", default="", help="its id (default: made the way the page makes one)")
    p.add_argument("--here", action="store_true",
                   help="this chat does it itself, now: the item is claimed by this chat and "
                        "running, so the page's work list shows it, its stages and its result")
    p.add_argument("--chat", default="")
    p.add_argument("--out", default="", help="where the batch goes (default <dump>/out)")
    p.add_argument("--now", default=None)
    p = sub.add_parser("reads", help="what a wake reads: only what changed since the last "
                                     "read, as ArtifactData queries")
    p.add_argument("dump", nargs="?", default="")
    p.add_argument("--full", action="store_true", help="read every collection whole")
    p.add_argument("--rev", type=int, default=None,
                   help="the revision the page's ring named, when it names one")
    p.add_argument("--now", default=None)
    p = sub.add_parser("version", help="a refused write named a record's version: keep it "
                                       "in the folder, then run the command again")
    p.add_argument("dump")
    p.add_argument("record", help="<collection>/<doc id>, as the refusal named it")
    p.add_argument("version", type=int)
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2
    a.argv = list(sys.argv[1:] if argv is None else argv)
    # Every command runs before there is a profile too: setup itself is on the page.
    return {"model": cmd_model, "view": cmd_view, "page": cmd_page, "apply": cmd_apply,
            "next": cmd_next, "pin": cmd_pin, "busy": cmd_busy,
            "progress": cmd_progress, "check": cmd_check,
            "start": cmd_start, "published": cmd_published, "resume-saved": cmd_resume_saved,
            "files-saved": cmd_files_saved, "propose": cmd_propose, "listen": cmd_listen,
            "republish": cmd_republish, "pinned": cmd_pinned, "told": cmd_told, "doorbells": cmd_doorbells, "done": cmd_done,
            "ask": cmd_ask, "wake": cmd_wake, "version": cmd_version, "reads": cmd_reads, "search-drafts": cmd_search_drafts,
            "follow-ups": cmd_follow_ups,
            "answer": cmd_answer}[a.cmd](a)


def stopped_on(e: BaseException) -> str:
    """One line for Claude in place of a traceback: what stopped, and the person's file it
    stopped in where it was one of theirs. A profile missing a setting, or a full disk, broke
    every page update with a raw traceback, and nothing said which file (the stranger audit,
    2026-11-03, X-39, X-45)."""
    import errno
    import re
    import traceback
    if isinstance(e, OSError) and e.errno == errno.ENOSPC:
        return ("app: the disk here is full, so nothing was written. Delete this chat's own "
                "scratch files (never the person's) and run this again; if it is still full, "
                "tell the person once: \"This chat's computer has run out of space. Please start "
                "a new chat and ask it to carry on.\"")
    said = " ".join(str(e).split())[:240]
    m = re.search(r"module '(?:ljs_profile_)?(\w+)' has no attribute '(\w+)'", said)
    where = (f"profile/{m.group(1)}.py has no {m.group(2)}" if m and "ljs_profile_" in said
             else "")
    if not where:
        for fr in reversed(traceback.extract_tb(e.__traceback__)):
            f = fr.filename.replace(os.sep, "/")
            if "/profile/" in f:
                where = f"in profile/{f.rsplit('/profile/', 1)[1]}, line {fr.lineno}"
                break
    return (f"app: stopped: {type(e).__name__}: {said}" + (f" ({where})" if where else "") +
            ". Claude: a file of the person's is likely missing a setting or damaged: compare "
            "it with profile.example/ and with the last commit where it worked (git log -p -- "
            "<the file>), put back what is missing, save it, and run this again. Nothing for "
            "the person unless it needs their answer.")


if __name__ == "__main__":
    import csv_store
    try:
        sys.exit(main())
    except csv_store.Conflicted as e:  # a merge left markers: say which file, read nothing
        print(f"app: {e}")
        sys.exit(1)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:  # noqa: BLE001  one line for Claude, never a traceback
        print(stopped_on(e))
        sys.exit(1)
