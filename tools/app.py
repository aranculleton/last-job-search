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


def computer_seen(db: dict, now) -> dict | None:
    """The computer's state from the page's database (tools/computer.py), or None where it
    cannot be read: the page then shows what it showed before (computer.seen)."""
    import computer
    return computer.seen(db, now)


def cmd_model(a) -> int:
    import app_model
    today, now = app_model.clock(a.today, a.now)
    # The computer's row as a page with nothing from it yet shows it, so `model` and a
    # `view` of a page the computer never wrote to are the same model, rev and all.
    model, _ = _build(today, now, computer=computer_seen({}, now))
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


COMPUTER_READS = "network~read~"


def unread_why(cid: str, model: dict, now) -> str:
    """Is this person still owed a read before their first note, by this copy itself, never
    by the page's own list alone (it holds what the page last drew)? Not when they already have
    a fresh reading, when the note has gone or a request waits (their status is past never
    written to, or the message log says so), or when they are held back on purpose (their
    employer full: app_model.employer_held). A read queued for eight people, six read that day
    and five already written to, was the third for the same people in a day (the maintainer,
    2026-11-10). Unsure (no contact book to read): kept, as before. "" when they are still
    owed a read, else why not, in plain words, so the job can name who it left out; a reading
    is judged fresh on the person's own day, never the computer's (the review of NW-8,
    2026-11-11)."""
    try:
        import reading
        got = reading.load(cid)
        if got and reading.fresh(got, person.today()):
            return "read on %s" % got.get("read_on")
    except Exception:  # noqa: BLE001  no reading to look at: the rest decides
        pass
    for m in model.get("messages") or []:
        if str(m.get("contact") or "") == cid and m.get("hold_why") == "employer_full":
            return "held back while their employer has enough people waiting"
    try:
        from network import schema, state
        rows = state.load_contacts(state.CONTACTS_CSV)
        row = next((r for r in rows if str(r.get("contact_id") or "").strip() == cid), None)
        if row is None:
            return ""
        threads = state.load_threads(state.THREADS_CSV) if os.path.exists(state.THREADS_CSV) \
            else []
        msgs = [t for t in threads if str(t.get("contact_id") or "").strip() == cid]
        if state.effective_status(row, msgs) not in schema.NEVER_SENT:
            return "written to already"
        if state.request_pending(msgs):
            return "a connection request to them is waiting"
        if any(str(t.get("direction") or "") == "outbound" for t in msgs):
            return "written to already"
    except Exception:  # noqa: BLE001  no contact book here: kept
        return ""
    return ""


def computer_reads(model: dict, work: dict, now) -> tuple[str, dict] | None:
    """The notes waiting for their person's profile, read on the person's computer with no one
    pressing anything, where it is known ready (model person.computer: computer.reads_there)
    and they read in the browser: one `network` item sent `to: computer` (page_db.computer_only
    keeps it there), `args.read_first` with `args.contacts`, each read there and its note
    rewritten in one run. None when nothing waits, or each is already on its way. Its id is
    the day and the people, so a view run again queues nothing more, and one the computer
    could not finish is tried again the next day, never in a loop. Without it the note said
    "press Read them in To do" with no such card there (the maintainer, 2026-11-10)."""
    import hashlib
    import page_db
    if not (model.get("person") or {}).get("computer"):
        return None
    reading = (model.get("linkedin") or {}).get("reading") or {}
    if reading.get("setting") != "browser" or reading.get("paused"):
        return None
    want = [str(q.get("contact") or "") for q in reading.get("queue") or []] \
        + [str(c) for c in (model.get("to_read") or {}).get("contacts") or []]
    going: set = set()
    day = now.date().isoformat().replace("-", "")
    for wid, doc in work.items():
        d = (doc or {}).get("data") or {}
        if d.get("kind") != "network":
            continue
        a = d.get("args") if isinstance(d.get("args"), dict) else {}
        # Today's read, finished too: its people are not queued again until tomorrow. A read
        # that finished with some still unread was written over by the next page update, under
        # the same id, as a new job with its clock reset (the maintainer's page, 2026-11-10).
        today = str(wid).startswith(page_db.safe_id(f"{COMPUTER_READS}{day}~"))
        # Read on the computer and kept there, not yet in this copy (computer.saved_here): its
        # people are never queued again meanwhile, or the same profiles were read twice.
        if (str(d.get("status") or "queued") not in page_db.FINISHED or today
                or d.get("saved_here")) and (a.get("rewrite") or a.get("read_first")):
            going |= {str(c) for c in a.get("contacts") or []} | {str(a.get("contact") or "")}
    cids, left = [], []
    for c in dict.fromkeys(want):
        if not c or c in going:
            continue
        why = unread_why(c, model, now)
        (left.append({"contact": c, "why": why}) if why else cids.append(c))
    if not cids:
        return None
    first = {str(q.get("contact") or ""): str(q.get("first_name") or "")
             for q in reading.get("queue") or []}
    key = hashlib.sha1(" ".join(sorted(cids)).encode("utf-8")).hexdigest()[:10]
    title = (f"Reading {first.get(cids[0]) or 'their'}'s profile on your computer"
             if len(cids) == 1 and first.get(cids[0]) else
             f"Reading {len(cids)} profiles on your computer")
    # Who it left out and why, named on the job, never dropped without a word (NW-8).
    fields = page_db.queued("network", title, {"contacts": cids, "read_first": True,
                                               "rewrite": True, "auto": True,
                                               **({"left_out": left} if left else {})}, now)
    fields["to"] = "computer"
    wid = page_db.safe_id(f"{COMPUTER_READS}{day}~{key}")
    if wid in work:
        return None                     # never written over, whatever it holds now
    return wid, fields


def self_fixes(db: dict | None, model: dict, out_dir: str, now, dump_dir: str = "",
               work: str = "") -> list[str]:
    """The batches that queue, once each, what a draft on the page needs and Claude can do
    with no one asking: its remake where a check failed with a fix Claude makes (the checks
    alert's own `draft` work, its `redo`; never one the drafts rerun handed to the person,
    tools/remake_drafts.py's "todo"), and one `files` item for the drafts whose PDFs the page
    lacks that no files work has ever covered (page_db.queue_files). Each id is a create the
    store refuses twice, so a view run again queues nothing more."""
    import app_model
    import page_db
    # A chat bringing the page up to date at the end of one job of its own (`view --work`)
    # queues nothing for the page: that is the chat that answers it, which reads the whole
    # work list (the audit of 2026-11-10, PE-3: self_fixes ignored --work).
    if db is None or work:
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
    # A prep already waiting or running for an interview, whoever asked for it (a chat's own
    # "prep~<stamp>" item as much as this one's "prep~<interview>"): never a second. Booking a
    # round made the pack out of date while a chat was building it, and the next update queued
    # another for the same interview (the maintainer's copy, 2026-11-10).
    going = set()
    for doc in work.values():
        d = (doc or {}).get("data") or {}
        a = d.get("args") if isinstance(d.get("args"), dict) else {}
        if d.get("kind") == "prep" and a.get("interview") and \
                str(d.get("status") or "queued") not in page_db.FINISHED:
            going.add(str(a["interview"]))
    for iv in model.get("interviews") or []:
        prep = iv.get("prep") or {}
        if not prep.get("stale") or iv.get("past") or not iv.get("id") or str(iv["id"]) in going:
            continue
        wid = page_db.safe_id("prep~" + str(iv["id"]))
        have = work.get(wid) or {}
        d = have.get("data") or {}
        # One the person stopped stays stopped: a redraw queued it again (the audit of
        # 2026-11-10, PE-3); their own "Update it" asks again.
        if d and (str(d.get("status") or "queued") == "stopped"
                  or str(d.get("status") or "queued") not in page_db.FINISHED
                  or str(d.get("finished_at") or d.get("asked_at") or "") >= str(prep.get("stale_since") or "")):
            continue
        title = f"Interview prep: {iv.get('company') or ''}, {iv.get('role') or ''}"
        if d:
            # A prep that ran before goes again as Try again sends it (page_db.retried), its
            # own record kept: a `set` wrote a fresh record over it (the audit, PE-3). A new
            # run, never a try again: counted as one, each change of the plan of rounds took
            # a try, so one stop failed it as "stopped part way twice" and two left a card
            # saying "Tap Try again" with no button (the engine review, 2026-11-11).
            args = dict(d.get("args") or {}, interview=iv["id"], note=None, auto=True)
            w.add("update", "work", wid, dict(page_db.retried(d, app_model.stamp(now), "engine"),
                                              attempt=1, args=args, title=title),
                  if_version=have.get("version"))
        else:
            w.add("set", "work", wid, page_db.queued(
                "prep", title, {"interview": iv["id"], "note": None, "auto": True}, now),
                if_version=None)
    got = computer_reads(model, work, now)
    if got:
        w.add("set", "work", got[0], got[1], if_version=None)
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
    before = _git("rev-parse", "HEAD")[1]
    behind = app_setup.take_master()
    if behind:
        print(_dump({"rev": None, "batches": [], "for_claude": [behind]}), end="")
        return 3
    if not os.environ.get(VIEW_AGAIN) and app_setup.code_moved(before):
        # Master brought in code (an update another chat took): the modules above are the
        # copy's old ones and the rest would be new, so the page is drawn by a fresh run on
        # the new code, once (audit SV-1).
        import subprocess
        sys.stdout.flush()
        return subprocess.run([sys.executable, os.path.abspath(__file__)] + list(a.argv),
                              env=dict(os.environ, **{VIEW_AGAIN: "1"})).returncode
    today, now = app_model.clock(a.today, a.now)
    import page_reads
    planned = bool(a.dump) and os.path.isfile(os.path.join(a.dump, page_reads.PLAN))
    end = bool(getattr(a, "end", False))
    if planned:
        page_reads.assemble(a.dump, now)
        need = page_reads.needs(a.dump)
        # The end of a wake's work reads what came in while it ran, so a tap made meanwhile
        # is applied in this batch, never left for the person's next message.
        late = page_reads.late_queries(a.dump, now) \
            if end and answers_page(page_db.load(a.dump), a.chat) else []
        if need or late:
            print(_dump({"rev": None, "batches": [], "for_claude": (
                [page_reads.NEED_SCREENS.format(colls=" and ".join(need), dump=a.dump,
                                                keep=page_reads.keep_step(a.dump))]
                if need else []) + ([page_reads.say_late(
                    late, a.dump, app_setup.page_record().get("url") or "<the page>")]
                    if late else [])}), end="")
            return 2
    late_batches: list = []
    late_lines: list = []
    if planned and end and page_reads.late_read(a.dump):
        got = late_taps(a.dump, a.chat, now, os.path.join(a.out_dir, "late"))
        if got.get("claim"):
            print(_dump({"rev": None, "batches": got["batches"],
                         "for_claude": got["lines"]}), end="")
            return 2
        late_batches, late_lines = got["batches"], got["lines"]
    elif a.dump:
        # Marks first, in any chat that draws the page: they ring nobody, so whichever chat
        # works on the search next keeps them, before the page is drawn from the copy.
        got = marks_first(a.dump, app_listen_chat(a.chat), now, os.path.join(a.out_dir, "marks"),
                          work=getattr(a, "work", "") or "")
        if got.get("claim"):
            print(_dump({"rev": None, "batches": got["batches"],
                         "for_claude": got["lines"]}), end="")
            return 2
        late_batches, late_lines = got.get("batches") or [], got.get("lines") or []
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
                return ahead_of_us[theirs_sha] or holds_unlanded(d)
        theirs = str(d.get("base") or "")
        return bool(base) and bool(theirs) and theirs > base

    def holds_unlanded(d: dict) -> bool:
        """Was it drawn, a little while ago, from a copy holding work of its own not landed
        yet that this copy lacks? A reply drafted and committed in the person's own chat was
        on the page until the helper, drawing from master, put the old draft back on their
        card until the save landed (the maintainer, 2026-11-10). Kept only for
        UNLANDED_KEEP_S, so a save that never lands never stops this chat drawing for good."""
        head = str(d.get("head_sha") or "")
        made = app_model.parse_time(d.get("made_at"))
        if not head or made is None or (now - made).total_seconds() > UNLANDED_KEEP_S:
            return False
        if ("head", head) not in ahead_of_us:
            ahead_of_us[("head", head)] = commit_ahead(
                head, os.environ.get("LJS_HEAD_SHA") or os.environ.get("LJS_BASIS_SHA") or "HEAD")
        # Never seen here, or not in this copy's history: work this copy does not have.
        return ahead_of_us[("head", head)] is not False
    kept: list = []
    head_sha = copy_head_sha()
    stamp = {"by": by, **({"base": base} if base else {}),
             # Only where this copy holds commits master does not have yet (holds_unlanded).
             **({"head_sha": head_sha} if head_sha and head_sha != base_sha else {}),
             **({"base_sha": base_sha} if base_sha else {})}
    # The suggestions already on the page keep their day, so no more than three new ones
    # reach it a day.
    full: dict = {}
    # A save a retired chat gave up on: one To do card, its record gone once saved (HC-3).
    unsaved, unsaved_gone = unsaved_saves(db, now) if db else ([], [])
    model, _ = _build(today, now, shown=app_alerts.shown_in(db.get("view") or {}), full=full,
                      work_time=page_db.work_times(db, now) if db else None,
                      # A message Claude's own change held is on hold on every screen.
                      held_work=app_model.held_by_work(db.get("work")) if db else None,
                      computer=computer_seen(db or {}, now), unsaved=unsaved)
    w = page_db.Writes(a.out_dir)
    for doc_id, version in unsaved_gone:
        w.add("delete", "meta", doc_id, if_version=version)
    views = (db.get("view") or {}) if db else {}
    # Only what changed is written: every update rewrote all 37 documents, about 1.5 MB, when
    # one card had changed (2026-11-03). The page takes each document newer than its own copy,
    # so one left as it was still shows; a part of a section is written only when what it
    # holds changed, and the head names what each part holds, so its parts never mix two
    # copies (D6).
    # Each whole list, in parts under 256 KiB, for the page's "Show" (tools/app_lists.py).
    # A part is left as it is only while it holds the same items under the same rev (what it
    # holds, app_lists.part_rev) in a list of as many parts: the page joins each part by the
    # rev the newest lists, so a part kept from before that listing, under the page's rev,
    # would never join, and one kept saying an old count sent it after a part gone (D6).
    import app_lists
    import app_page
    # Written as the published page's code joins them until it is republished: sent the new
    # way to a page still on the old code, big sections and every "Show" list were blank on a
    # fresh load for the minutes between an update and its republish (the review of
    # 2026-11-11).
    by_hold = app_page.joins_by_hold()
    list_docs = app_lists.docs(full, model["made_at"], model["rev"], by_hold=by_hold)
    as_they_are = app_lists.kept_as_they_are(list_docs, views, by_hold=by_hold)
    for doc_id, doc in list_docs:
        old = views.get(doc_id)
        if doc_id in as_they_are:
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
    for name in dict.fromkeys(tuple(app_model.SECTIONS) + ("people_count", "coming_up", "lists",
                                                           "listener", "schedule")):
        if name not in model:
            continue
        docs = page_db.split(name, {"rev": model["rev"], "made_at": model["made_at"],
                                    "data": model[name], **stamp}, by_hold=by_hold)
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
            written.append(doc_id)
            if page_db.same_part(old, doc):
                continue        # it holds what it held: never written again for its stamp (D6)
            w.add("set", "view", doc_id, doc, if_version=old["version"] if old else None)
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
    fixes: list = []
    if a.dump:
        try:
            fixes = self_fixes(db, model, os.path.join(a.out_dir, "self"), now, dump_dir=a.dump,
                               work=getattr(a, "work", "") or "")
            batches = list(batches) + fixes
        except Exception:  # noqa: BLE001  nothing to read it against: nothing queued
            pass
    # Work no chat will take up again (stopped part way twice, asked to stop, or begun in a chat
    # gone quiet) is ended on every redraw, in a batch of its own after the screens, so its card
    # offers Try again: only the listener's check-in ended it, and with no listener a dead job
    # said "May have stopped" for good (the audit of 2026-11-10, PE-4).
    if a.dump and db:
        try:
            ended = page_db.fail_stranded(db, now, os.path.join(a.out_dir, "stranded"))
            batches = list(batches) + list(ended["batches"])
        except Exception:  # noqa: BLE001  nothing read to judge it by: nothing ended
            pass
    # Work this update queued for itself (a remake, the files, a computer read) wakes nobody by
    # itself: the brief's run starts a fresh helper for it (app_listen.brief_wakes).
    lines = app_listen.view_renewal(db, a.chat, now, queued=bool(fixes))
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
    if late_lines:
        lines = list(late_lines) + list(lines or [])
    first = own_tests_first()
    if first:
        lines = [first] + list(lines or [])
    stale = page_code_behind()
    if stale:
        lines = list(lines or []) + stale
    if getattr(a, "end", False):
        lines = list(lines or []) + end_of_batch(a.chat, getattr(a, "message", "") or "", now)
        try:
            import app_listen
            import app_setup
            late = app_listen.rings_meanwhile(a.dump, app_setup.page_record().get("url") or "")
        except Exception:  # noqa: BLE001  never a reason the page is not answered
            late = ""
        if late:
            lines.append(late)
    # The taps that came in while the work ran go first: the screens are drawn with them.
    batches = list(late_batches) + list(batches)
    # Pinned to numbers no read confirmed: said first, with the step that takes the store's
    # own from the read's lines (app.py versions), never refused, so a chat whose read kept
    # them by an old hook, or none at all, still sends (the audit of 2026-11-10, PE-2).
    if a.dump and batches:
        unsure = page_db.stamped_only(a.dump, batches)
        if unsure:
            lines = [page_db.STAMPED_ONLY.format(n=len(unsure), some=", ".join(unsure[:3]),
                                                 dump=a.dump)] + list(lines or [])
    print(_dump({"rev": model["rev"], "batches": batches,
                 **({"send": SEND_IN_ORDER} if len(batches) > 1 else {}),
                 **({"kept_newer": kept} if kept else {}),
                 **({"for_claude": lines} if lines else {})}), end="")
    return 0


# Batches made from one read go in order, and a refused one stops the rest: those after it
# were made from the same read, a section's other parts among them, and sent anyway the page
# mixed two versions of one section (the audit of 2026-11-10, PE-9; the review of 2026-11-11).
SEND_IN_ORDER = ("Send these in order, each after the one before is accepted. Once one is "
                 "refused, send none after it: put it right (python3 tools/app.py version, as the "
                 "refusal says), then run this command again and send what it prints.")


def page_code_behind() -> list[str]:
    """The republish, where the page's own code is older than this copy's: a chat that took an
    update only refreshed the page's data, and the person saw the old buttons until they asked
    for a republish (the maintainer, 2026-11-09). Every `view` says it, so no update's page
    change waits on one chat following one step. [] when the page is current or not set up."""
    try:
        import app_listen
        import app_setup
        url = str(app_setup.page_record().get("url") or "")
        if not url or not app_setup.set_up() or app_setup._page_current():
            return []
        return ["Claude: the page's own code is older than this copy (an update changed it): "
                "republish it now, after sending these batches, saying nothing first:"] + \
            app_listen._publish_now(url, 1)
    except Exception:  # noqa: BLE001  the data still goes
        return []


def app_listen_chat(chat: str) -> str:
    """This chat's id, given or from the session (app_listen.this_chat)."""
    import app_listen
    return app_listen.this_chat(chat)


def answers_page(db: dict, chat: str) -> bool:
    """Is this chat the one the page's record names as answering it?"""
    import app_listen
    rec, _ = app_listen.record(db)
    mine = {c for c in (app_listen.this_chat(""), app_listen.this_chat(chat)) if c}
    return bool(rec.get("chat")) and str(rec.get("chat")) in mine


LATE_CLAIM = ("view: {n} tap{s} came in while the work ran, and applying {them} changes your "
              "copy: send this claim, and once it is accepted run this same command again: it "
              "applies them and brings the page up to date in one batch. Refused: as any "
              "refused write (the app skill, \"Rules that hold everywhere\").")
LATE_WORK = ("late: work is waiting that this chat takes before it ends ({ids}): once this "
             "batch is sent, take it: python3 tools/app.py wake \"{dump}\" --chat {chat} (the "
             "same folder), do what it prints, then end with this same command again. It is "
             "named at every end until it is taken.")


MARKS_CLAIM = ("view: {n} mark{s} the person made on the page (applied, sent, set aside and "
               "the like) {are} kept first, before the page is drawn, and keeping {them} changes "
               "your copy: send this claim, and once it is accepted run this same command again: "
               "it applies {them} and brings the page up to date in one batch. Refused: as any "
               "refused write (the app skill, \"Rules that hold everywhere\").")


def taps_now(dump: str, chat: str, now, out_dir: str, only=None, said: str = "taps made while "
             "the work ran", claim_line: str = LATE_CLAIM) -> dict:
    """The pending taps in `dump` (or those in `only`), claimed and applied as a wake applies
    them: {"claim": True, "batches", "lines"} when one changes the copy and its claim must be
    accepted first (the same command is run again once it is), else {"batches", "lines"}
    with the receipts in one batch where they fit."""
    import app_actions
    import page_db
    db = page_db.load(dump)
    todo = app_actions.pending(db, chat, now)
    if only is not None:
        todo = [t for t in todo if t[0] in set(only)]
    batches: list = []
    lines: list[str] = []
    if not todo:
        return {"batches": batches, "lines": lines}
    need = app_actions.to_claim(todo, chat, now)
    changes = {aid for aid, act, _v in todo
               if str(act.get("action") or "") not in app_actions.DB_ONLY}
    claim = app_actions.claim(dump, chat, now, os.path.join(out_dir, "taps"),
                              only=need)["batches"] if need else []
    if changes & set(need):
        n = len(todo)
        return {"claim": True, "batches": claim, "lines": [claim_line.format(
            n=n, s="s" if n != 1 else "", them="them" if n != 1 else "it",
            are="are" if n != 1 else "is")]}
    got = app_actions.apply_dir(dump, chat, now, os.path.join(out_dir, "apply"),
                                only=[t[0] for t in todo])
    page_db.keep_landed(dump, got["batches"], skip=("actions",))
    batches = _one_batch(list(claim) + list(got["batches"]), os.path.join(out_dir, "send"))
    counts = [f"{len(got[k])} {w}" for k, w in (("ok", "applied"), ("stale", "changed since "
              "they saw it"), ("conflict", "could not be done"), ("again", "applied before"))
              if got.get(k)]
    if counts:
        lines.append(said + ": " + ", ".join(counts) + " (in this batch; each receipt says it "
                     "on the page)")
    if got.get("fetch"):
        lines.append("fetch: a tap made while the work ran names files the person added: "
                     f"python3 tools/app.py apply \"{dump}\" --chat {chat} --assets "
                     f"\"{dump}/assets\" once each is read there (Artifact read, path the "
                     "asset id), as a wake's fetch line says.")
    return {"batches": batches, "lines": lines}


def marks_first(dump: str, chat: str, now, out_dir: str, work: str = "") -> dict:
    """The marks waiting in `dump` (app_actions.MARKS), kept before the page is drawn by any
    chat that draws it: a mark rings nobody, so the next chat that works on the search keeps
    it (taps_now). {} when there is none, or this chat may not keep them."""
    import app_actions
    import app_listen
    import page_db
    if not chat or not os.path.isdir(os.path.join(dump, "actions")):
        return {}
    db = page_db.load(dump)
    marks = [aid for aid, act, _v in app_actions.pending(db, chat, now)
             if str(act.get("action") or "") in app_actions.MARKS]
    if not marks or not app_listen.draws_screens(db, chat, work, now)[0]:
        return {}
    return taps_now(dump, chat, now, out_dir, only=marks, said="marks kept first",
                    claim_line=MARKS_CLAIM)


def late_taps(dump: str, chat: str, now, out_dir: str) -> dict:
    """What the reads that end a batch found (page_reads.late_queries), after they were made
    into `dump`: the taps made while the work ran, claimed and applied as a wake applies them
    ({"claim": True, ...} when one changes the copy and its claim must be accepted first),
    and one line naming the work this chat takes before ending. {"batches", "lines"}."""
    import app_listen
    import page_reads
    chat = app_listen.this_chat(chat)
    got = taps_now(dump, chat, now, out_dir)
    if got.get("claim"):
        return got
    batches, lines = got["batches"], got["lines"]
    # Work waiting that this chat would take next (the same choice a wake makes, so never an
    # item it cannot take: another chat's kind, past the heavy-job cap, or locked), named at
    # every end until it is taken. Named once, two follow-ups asked for while a pass ran sat
    # "starts in a moment" after it ended, until a pass was started by hand (the maintainer's
    # copy, 2026-11-05).
    new = waiting_for(dump, chat, now)
    if new:
        lines.append(LATE_WORK.format(ids=", ".join(new[:6]) + (" ..." if len(new) > 6 else ""),
                     dump=dump, chat=chat))
    page_reads.late_handled(dump, again=bool(new), ids=new, chat=chat, now=now)
    return {"batches": batches, "lines": lines}


def waiting_for(dump: str, chat: str, now) -> list[str]:
    """The queued work this chat takes, in the order a wake takes it (choose, nothing
    claimed): each item and those it is taken with, a few at most. [] when there is none."""
    import app_listen
    import page_db
    db = page_db.load(dump)
    rec, _ = app_listen.record(db)
    kind = str(rec.get("kind") or "") if str(rec.get("chat") or "") == chat else ""
    work = {k: dict(v) for k, v in (db.get("work") or {}).items()}
    db = dict(db, work=work)
    out: list[str] = []
    while len(out) < 7:
        got = choose(db, chat, kind or app_listen.chat_kind(), now,
                     no_sessions=app_listen.nested(chat))
        if not got:
            break
        ids = [got["work"]] + [str(w.get("work") or "") for w in got.get("with") or []]
        out += ids
        for wid in ids:
            # As taken, so the next choice is the one after it.
            if wid in work:
                work[wid] = dict(work[wid], data=dict(work[wid]["data"], status="taken"))
    return out


def _one_batch(paths: list, out_dir: str) -> list:
    """`paths` as one batch the store takes whole, where it fits and writes no document
    twice (a claim refused takes the receipts with it); else as they are."""
    import page_db
    entries: list = []
    seen: set = set()
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            got = json.load(fh)
        docs = {(e["collection"], e["doc_id"]) for e in got}
        if docs & seen:
            return list(paths)
        seen |= docs
        entries += got
    if len(paths) < 2 or len(entries) > page_db.BATCH_MAX:
        return list(paths)
    w = page_db.Writes(out_dir)
    w.entries = entries
    return w.save("late")


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


# How long screens drawn from a copy with work not landed yet are kept from a chat whose copy
# lacks it (cmd_view's holds_unlanded): a landing takes minutes, and one that never comes must
# not keep any chat from drawing them for good.
UNLANDED_KEEP_S = 30 * 60


def copy_head_sha() -> str:
    """This copy's newest commit, its own not landed yet included: screens carry it as
    `head_sha` where it is not `base_sha`, so a chat whose copy lacks that work does not draw
    over them before it lands. "" where it cannot be told. LJS_HEAD_SHA is for tests (with
    LJS_BASIS_SHA alone, the copy is taken to hold nothing unlanded)."""
    given = os.environ.get("LJS_HEAD_SHA", os.environ.get("LJS_BASIS_SHA"))
    if given is not None:
        return given
    if not os.path.isfile(os.path.join(person.ROOT, "profile", "person.json")):
        return ""
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
           claim_out: str | None = None, job_chat: bool = False,
           computer_only: bool = False, lent: bool = False, beat: bool = True) -> dict | None:
    """The queued work this chat should take (None: nothing is), with the model a chat
    started for it gets (tools/model_guide.py for_work), `run`: where it is done
    (where_it_runs), and with `claim_out` the claim as batch files. Small work done here is
    claimed running at its first stage, so no progress pin follows it. Work sent to the
    computer is always done here, in the chat with the browser (`computer_only`: the chat
    the app started on the computer takes nothing else). `lent`: a cloud chat lent the
    computer's browser or folder, claiming as a computer chat; its heartbeat, like a big job's
    own chat's, never counts as a chat listening (page_db.heartbeat `watching`)."""
    import app_listen
    import model_guide
    import page_db
    chosen = app_listen.next_republish(db, chat, now)
    if chosen is None:
        # Each big job in a cloud chat of its own runs on its own computer: ten at once there.
        cap = page_db.HEAVY_CAP_CHATS if kind == "cloud" and not no_sessions else page_db.HEAVY_CAP
        chosen = page_db.next_item(app_listen.without_republish(db), kind, now, cap=cap,
                                   heavy_only=job_chat and not computer_only,
                                   to_only="computer" if computer_only else "")
    if chosen is None:
        return None
    # Sent to the computer: a LinkedIn read. It runs in this chat, which has the browser,
    # never as a background agent with none (`--tools none`), which the computer's chat had
    # to overrule by hand (2026-11-09).
    sent_here = bool(page_db.computer_only((((db.get("work") or {}).get(
        page_db.safe_id(chosen["work"])) or {}).get("data") or {}), "cloud"))
    # A networking run taken by a chat on the computer whatever it was sent to: the whole run
    # here, its reads in this chat's browser. Sent anywhere (the computer not known ready
    # yet), a chat on the computer that answers the page handed it to a background agent with
    # no browser, which found people from search results and left every note waiting on a
    # read (the maintainer, 2026-11-10: "not just ... half-assed networking").
    reads_here = (not sent_here and kind == "computer"
                  and chosen["kind"] in page_db.READS_ON_COMPUTER and _reads_in_browser())
    info = model_guide.for_work(chosen["kind"], on)
    heavy = bool(page_db.WORK_KINDS.get(chosen["kind"], {}).get("heavy"))
    chosen.update(model=info["model"], effort=info["effort"], heavy=heavy)
    # The names of the job chats still at work, so a new one is never called the same.
    taken = {str(d.get("chat_title") or "") for d in
             ((doc.get("data") or {}) for doc in (db.get("work") or {}).values())
             if str(d.get("status") or "") in ("claimed", "running")} - {""}
    chosen.update(where_it_runs(chosen, chat, kind, no_sessions, taken=taken))
    if job_chat or sent_here or reads_here:
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
            chosen["steps"] = job_steps(chosen, chat, url, session=True, first=1,
                                        chat_kind=kind, computer_only=sent_here or reads_here,
                                        own_chat=job_chat or (computer_only and not lent))
    if claim_out:
        # A chat the app started on the computer for its work (`computer_only`) does that work
        # and nothing else: never counted as the computer's chat listening. Counted so, route
        # said "Your computer's chat takes it" for twenty minutes after it had stopped (the
        # builder audit, 2026-11-10, CC-16).
        # A chat on the computer taking work for it (`computer_only`, never a lent cloud chat
        # nor one the person opened, which run plain `next`) is recorded as the work's chat on
        # the computer when nothing else is, so the starter puts it away once it is finished,
        # whoever started it (a task, a chat started by an earlier helper): only the starter's
        # own were put away, and the others stayed open (the second audit, C6).
        item = (((db.get("work") or {}).get(page_db.safe_id(chosen["work"])) or {})
                .get("data") or {})
        extra = {"computer_session": {"id": chat, "at": app_model_stamp(now), "own": True}} \
            if computer_only and not lent and chat.startswith("session_") and \
            not (item.get("computer_session") or {}).get("id") else None
        chosen["batches"] = page_db.claim(db, chosen, chat, kind, now, claim_out,
                                          running=chosen.get("run") == "here",
                                          watching=not (lent or job_chat or computer_only),
                                          beat=beat, extra=extra)
    return chosen


def app_model_stamp(t) -> str:
    import app_model
    return app_model.stamp(t)


def _reads_in_browser() -> bool:
    """Does the person have LinkedIn profiles read in the browser (their reading setting,
    tools/network/reading.py reads_now), so a networking run on the computer reads them?"""
    try:
        sys.path.insert(0, os.path.join(_HERE, "network"))
        import reading
        return reading.reads_now() == "browser"
    except Exception:  # noqa: BLE001  no setting to read: the default, read in the browser
        return True


def cmd_next(a) -> int:
    """The queued work this chat should take, with the model a chat started for it gets
    (tools/model_guide.py for_work), and `run`: where it is done (where_it_runs). A big job
    is never `here`. A republish goes to the page's listener alone, and first: the page's
    own code changed under every open window."""
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    # A chat on the computer ends work no chat will take up again before it looks for its
    # own, as the listener's check-in and every redraw do: with no listener checking in, a
    # read whose chat on the computer died twice said "May have stopped" for good (the audit
    # of 2026-11-10, PE-4).
    ended: dict = {"ended": [], "batches": []}
    if (a.kind or "") == "computer":
        try:
            ended = page_db.fail_stranded(page_db.load(a.dump), now,
                                          os.path.join(a.claim_out or a.dump, "stranded"))
        except Exception:  # noqa: BLE001  nothing read to judge it by: nothing ended
            ended = {"ended": [], "batches": []}
        if ended["batches"]:
            page_db.keep_landed(a.dump, ended["batches"])
    try:
        chosen = choose(page_db.load(a.dump), a.chat, a.kind, now, on=a.on,
                        no_sessions=a.no_sessions, claim_out=a.claim_out,
                        job_chat=getattr(a, "job_chat", False),
                        computer_only=getattr(a, "computer_only", False),
                        lent=getattr(a, "lent", False),
                        beat=page_db.read_has(a.dump, "beats"))
    except ValueError as e:
        print(f"app: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
    if chosen is None:
        if ended["batches"]:
            print(_dump({"work": None, "ended": ended["ended"], "batches": ended["batches"]}),
                  end="")
        return 0
    if ended["batches"]:
        chosen = dict(chosen, ended=ended["ended"],
                      batches=list(ended["batches"]) + list(chosen.get("batches") or []))
    if chosen.get("batches") and (getattr(a, "computer_only", False) or (
            (a.kind or "") == "computer" and chosen.get("run") == "here"
            and chosen.get("kind") in page_db.READS_ON_COMPUTER)):
        # The id it was claimed under, kept on this computer for a chat that compacts and loses
        # it (computer.py prompt says it again; the builder audit, 2026-11-10, CC-25). A read
        # taken here by a chat on the computer with plain `next` (route's `here`) or lent its
        # browser is the page's work too, so it is kept the same way: unkept, its sign-in was
        # asked in a chat nobody reads (the local review, 2026-11-11, 4).
        import app_setup
        for wid in [chosen["work"]] + [str(o.get("work") or "") for o in chosen.get("with") or []]:
            try:
                app_setup.record_claim(wid, a.chat, lent=bool(getattr(a, "lent", False)))
            except OSError:
                pass
        # The person's sign-in answered on the page lifts today's sign-out stop, once, in code
        # (reading.resume_from_page): signed in there, every read was still refused.
        try:
            sys.path.insert(0, os.path.join(_HERE, "network"))
            import reading
            reading.resume_from_page(((page_db.load(a.dump).get("work") or {}).get(
                page_db.safe_id(chosen["work"])) or {}).get("data") or {})
        except Exception:  # noqa: BLE001  nothing to lift, or no ledger here
            pass
    if chosen.get("batches"):
        # Claimed, as it will be once sent: the pins and the finish made from this folder are
        # pinned to the claim's versions and free the holds it makes. Left as read, the first
        # pin was refused and the finish left a hold behind, deleted by hand (a person's
        # computer, 2026-11-09).
        page_db.keep_landed(a.dump, chosen["batches"])
        _claimed_here(a.dump, chosen)
    print(_dump(chosen), end="")
    return 0


def _claimed_here(dump: str, *chosen) -> None:
    """The copy this checkout keeps of the page (page_reads' mirror) takes each claim just made
    from `dump`: a read of someone the work reads is refused while the copy says it waits
    (reading.queued_on_page), and the chat that had just claimed it was refused its own read
    (the engine review, 2026-11-11)."""
    ids = [str(c.get("work") or "") for c in chosen if c] + \
        [str(o.get("work") or "") for c in chosen if c for o in c.get("with") or []]
    try:
        import page_reads
        page_reads.keep_work(dump, ids)
    except Exception:  # noqa: BLE001  no copy kept here: nothing refuses on it
        pass


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
# the call says to put the id in first: the job's chat is started under it (it no longer
# messages that chat: it saves, updates the page and puts itself away).
PARENT = "<your chat id>"
SKILL_DIR = os.path.join(os.path.dirname(_HERE), ".claude", "skills", "app")
# Step 4's table, where every kind of work's row is kept: `wake` prints the item's own row, so
# the chat reads none of the table for it (E-3).
SKILL = os.path.join(SKILL_DIR, "work.md")


def work_row(kind: str) -> str:
    """What the app skill's table (step 4, work.md) says a chat runs for this kind of work,
    word for word, or "" when the skill has no row for it."""
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


def job_command(chosen: dict, parent: str, session: bool = True) -> str:
    """The one command that prints a big job's own steps (`app.py job`): everything they are
    made from is on its line, so the job's chat reads nothing first to have them."""
    wid, kind = chosen["work"], chosen["kind"]
    mates = [str(o.get("work") or "") for o in chosen.get("with") or [] if o.get("work")]
    return (f"python3 tools/app.py job --work {wid} --kind {kind} --chat {parent}"
            + "".join(f" --with {m}" for m in mates)
            + (f" --draft-all {int(chosen['draft_all'])}" if chosen.get("draft_all") else "")
            + ("" if session else " --agent"))


def child_prompt(chosen: dict, parent: str, url: str, session: bool = True) -> str:
    """What a chat (or, where none can be started, a background agent) is told for one big
    job: run that item, pin its progress, finish it, land it and bring the page up to date. It
    never publishes, watches or answers the page. `parent` is the chat that claimed it.

    Short, with its steps printed by `app.py job` in the job's own chat: the chat that answers
    the page typed the whole 7,000-character prompt into create_session, once a job, and wake
    printed it again inside the call (the efficiency audit, E-8). The job's chat starts on
    the copy as it is saved, which can be older than the chat that took the day's update and
    started it: there is no `job` there until it takes the update (the review of 2026-11-11).
    It takes it with the plain sync, which honours their setting: where the person said "only
    update when I say", no tool tells a chat to force one, so the job stops and says it waits."""
    wid, kind = chosen["work"], chosen["kind"]
    where = "in a chat of its own" if session else "as a background agent"
    return "\n".join([
        f"Do one piece of work for this person's job search page, {where}, so the chat that "
        f"answers the page stays free. The work: \"{chosen.get('title') or kind}\" (work item "
        f"{wid}, a {kind}), already claimed for you. The page: {url}. The chat that answers "
        f"it: {parent}.",
        f"1. python3 tools/app.py start --on \"<your model>\" --tools none --work {wid}, and do "
        "what it prints. Never publish, watch or answer the page.",
        f"2. {job_command(chosen, parent, session)}, and do every step it prints, in order: "
        "this job's own read, commands, progress pins and finish. If app.py says it has no "
        "`job` (this copy is older than the chat that started you): python3 "
        "tools/sync_app.py, then this step again; if it says an update is waiting, the person "
        "updates only when they say so: stop, and say in plain words that this work waits "
        "until they choose to update."])


def job_chosen(work: str, kind: str, mates=(), draft_all: int = 0) -> dict:
    """A claimed big job as `job_steps` takes it, from what `job_command` put on its line."""
    import page_db
    args = {"draft": True} if draft_all else {}
    got = {"work": work, "kind": kind,
           "stages": page_db.item_stages({"kind": kind, "args": args}),
           "with": [{"work": m} for m in mates if m]}
    if draft_all:
        got["draft_all"] = int(draft_all)
    return got


def cmd_job(a) -> int:
    """A big job's own steps, for the chat (or background agent) started for it (job_command)."""
    import app_setup
    import page_db
    if a.kind not in page_db.STAGES:
        print(f"app: no kind of work {a.kind!r}", file=sys.stderr)
        return 2
    url = a.url or app_setup.page_record().get("url", "") or "<url>"
    chosen = job_chosen(a.work, a.kind, a.mates or [], a.draft_all)
    session = not a.agent
    print("\n".join(job_steps(chosen, a.chat, url, session=session, first=3,
                              report_to=a.chat if session else "")))
    return 0


def _versions_said(dump: str, fresh_chat: bool = False) -> str:
    """The step after a read that keeps each record's own version (page_db.versions_step),
    or "" where the app's hook keeps them: a chat that starts now (`fresh_chat`, a job's own)
    runs the hooks its copy's settings register (page_db.after_read)."""
    import page_db
    return page_db.after_read(dump, fresh_chat=fresh_chat)


def job_steps(chosen: dict, claimer: str, url: str, session: bool = True,
              first: int = 1, report_to: str = "", chat_kind: str = "cloud",
              computer_only: bool = False, own_chat: bool = True) -> list[str]:
    """The steps for one big job, numbered from `first`, every one naming this job's own id,
    its own folder ($D, read afresh), its kind's commands and its pins (a search's round.log
    as well), with `--chat <claimer>` (the id it was claimed under) on each write. A job
    chat's second job reused the first one's id and $D, and had no search pin unless the
    first was a search (the release review, 2026-11-03): `next --job-chat` prints these."""
    wid, kind = chosen["work"], chosen["kind"]
    keys = ", ".join(s["key"] for s in chosen.get("stages") or [] if s.get("key"))
    row = work_row(kind)
    lines: list[str] = []
    # Claimed as a computer chat (a cloud chat lent the computer's browser or folder too):
    # every finish says so. Without it, app.py done took the chat's own kind, cloud, and a
    # LinkedIn read could not be finished by the chat that did it (the release review,
    # 2026-11-09).
    kf = " --kind computer" if chat_kind == "computer" else ""

    def step(text: str) -> None:
        lines.append(f"{first + len(lines)}. {text}")

    # Work and holds alone: its pins and finish need nothing else, and the page's screens
    # (about 4 MB) are read at the finish, where the page is brought up to date (the second
    # audit of 2026-11-10, C4). A chat on the computer also reads meta, which its route and
    # starter steps need (the builder audit, 2026-11-10, section 12).
    reads = "work, holds and meta" if computer_only else "work and holds"
    # A job's own chat starts now, with the hooks its copy registers; a chat on the computer
    # doing it may be older than them, and keeps the versions by hand (E-6).
    keep = _versions_said("$D", fresh_chat=session and own_chat and not computer_only)
    import page_reads
    # Named after the job, so each job of a chat has its own: one name for every job (`j1`)
    # brought back a job chat's second job reading into the first one's folder (the review of
    # 2026-11-11, E-18), and the job's first command refuses a folder an earlier run read into.
    step("Load ArtifactData (ToolSearch, select:ArtifactData). Read the page's database "
         f"into a fresh folder in your scratchpad named {page_reads.job_folder(wid)}, "
         f"$D, in one go: "
         f"ArtifactData query, url {url}, once for each of the collections {reads}, "
         f"each with out_dir $D and limit 1000"
         + ("; " + keep if keep else "") + ". The item, its args and the "
         f"`answers` the person already gave on the page (never asked again) are in "
         f"$D/work/{wid.replace('~', '@')}.json.")
    if session:
        # This chat's own id on the job first (`run_by`, page_db.run_by): a job's chat writes
        # under the id of the chat that started it, so a second chat started for the same job
        # after this one paused could not be told from it (the second audit, C1).
        step(f"Say on the job that this chat runs it: python3 tools/app.py pin \"$D\" --work {wid} "
             f"--chat {claimer} --line \"Started.\" --first, and send the batch it prints "
             f"(ArtifactData batch, url {url}); where it says to read again or keep the read's "
             "versions first, do that, then run it again.")
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
         "nothing of the app skill but step 5 of .claude/skills/app/wake.md, for the finish."
         if row else
         f"Do it as the app skill says for a {kind}: its row in .claude/skills/app/work.md, "
         "\"Progress costs nothing extra\" in .claude/skills/app/jobs.md and step 5 of "
         ".claude/skills/app/wake.md. Read only those parts.")
    if computer_only and kind in ("network",):
        import computer
        # The whole run on the computer: finding, the short list, each profile read in this
        # chat's browser, every note written from it and checked. Told only "the networking
        # skill", the chat on the computer queued its reads "for the page" and left every note
        # waiting on a read, for a second chat there to finish (the maintainer, 2026-11-10).
        # LinkedIn signed out is the one thing that stops it, and it goes on the page: told
        # only "never queue a profile for the page", the chat on a Mac kept the sign-in and its
        # steps in its own conversation, "rather than parking it on your page" (the maintainer,
        # 2026-11-11).
        step("This chat has Claude's own browser on the person's computer, so the whole run is "
             "done here, in this chat: the people searches opened in that browser, the short "
             "list, each person's profile read in it (python3 tools/network/reading.py route "
             "--tools browser says `here`: reading.py next, then reading.py read <id> - "
             "--source browser, one at a time), and every note written from what was read "
             "and checked. Never queue a profile for the page to read, never --wait-for-read, "
             "and never hand any of it to another chat or a background agent. "
             + computer.SIGNED_OUT_ON_PAGE)
    step(f"At each stage ({keys}): python3 tools/app.py pin \"$D\" --work {wid} --chat "
         f"{claimer} --stage <stage> --line \"<one plain line>\", and send the batch it prints "
         f"(ArtifactData batch, url {url}). On a long stage, pin it again with a new line every "
         "ten minutes or so: the page counts a job with no word for half an hour as stopped. "
         "\"stop_asked\": true means they tapped Stop (`stopped` names others of the job they "
         f"stopped): end each with app.py done --work <its id> --chat {claimer}{kf} --stopped. A "
         "question only the person can answer: app.py done --work <its id> --chat "
         f"{claimer}{kf} --question \"<one plain question>\" puts it on their page, and their "
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
    done = (f"each draft's own app.py done, with --chat {claimer}{kf}: {wid} finishes with the last"
            if kind == "search" and chosen.get("draft_all")
            else f"its app.py done with --work {wid} --chat {claimer}{kf}")
    # A draft's PDFs: this chat cannot upload (Artifact is not among its tools), so its
    # app.py done queues one `files` item for the chat that answers the page, and nothing is
    # uploaded here (the maintainer, 4 November).
    files = (" Its PDFs reach the page's file store by themselves: app.py done queues the "
             "upload for the chat that answers the page (send every batch it prints), so upload "
             "nothing here." if kind in ("draft", "resume_for_contact") else "")
    if session:
        # A job's chat lands its work and brings the page up to date itself, then takes the
        # next job: it never messages the chat that started it. send_message asks the person
        # for approval every time, and was refused (the maintainer, 2026-11-10); the helper's
        # daily tidy archives the finished chat (tools/tidy.py). Two writers of the page are
        # safe: each write is pinned and drawn from master (2026-11-03).
        if computer_only:
            # Measured, never guessed: a computer run's own report of its time and steps was
            # wrong by a third (2026-11-09). Its transcript says what it took (tools/computer.py).
            step(f"Before it finishes: python3 tools/computer.py measure \"$D\" --work {wid} "
                 f"--chat {claimer}, and send its batch; say its line, never your own count.")
        if computer_only:
            # The page first, from this copy, then the save in a process of its own: a chat on
            # the computer held the page for its save's three minutes and more, and its save
            # ends at its push, the chat in the cloud merging it (land.on_computer; the
            # maintainer's computer, 2026-11-10). Nothing about saving is the person's.
            step(f"Finish as step 5 says ({done}), without its heartbeat line.{files} Then bring "
                 f"the page up to date at once, from this copy: {_finish_read(url)}; python3 "
                 f"tools/app.py view \"$D/view\" --dump \"$D/page\" --chat <this chat's id> --work "
                 f"{wid}; and send every batch it prints (ArtifactData batch). "
                 f"{REFUSED_ONCE} Only then save, in the background: python3 tools/land.py "
                 "--detach --message \"<what changed>\" (an ordinary call that returns at once; "
                 "the chat in the cloud brings it to master). Never wait for it, and never say "
                 "anything about saving, pull requests or merging: the page shows how it went.")
            step(_next_job(url, kind=chat_kind, computer_only=computer_only) if own_chat else
                 "Then carry on as the chat that answers the page: the app skill's step 3 again "
                 "(wake with a fresh read), so work queued meanwhile starts now. Never put this "
                 "chat away: it answers the page.")
            return lines
        step(f"Finish as step 5 says ({done}), without its heartbeat line.{files} "
             f"{LAND_AND_WAIT} Then, landed or not (a failed check leaves the work for the "
             f"next chat to land, and this step still runs), bring the page up to date yourself: "
             f"{_finish_read(url)}; python3 tools/app.py view \"$D/view\" --dump \"$D/page\" "
             f"--chat <this chat's id> --work {wid} (it takes master first, so the page has every other chat's work too, "
             "and never writes over a screen drawn from a newer copy than this one); and send "
             f"every batch it prints (ArtifactData batch). {REFUSED_ONCE} Never message another "
             "chat, and never write to the person: "
             "the page shows how it went.")
        step(_next_job(url, kind=chat_kind, computer_only=computer_only))
    else:
        step(f"Finish as step 5 says ({done}), without its heartbeat line and without app.py "
             f"view.{files} {LAND_AND_WAIT} Then end with "
             f"one line, landed or not: \"Finished {wid}, on master: bring the page up to "
             f"date.\", or where the check failed and the work waits on its branch, \"Finished "
             f"{wid}, not landed: bring the page up to date.\" Never write to the person: the "
             "page shows how it went.")
    return lines


def _finish_read(url: str) -> str:
    """The read a job's finish draws the page from: through the copy this checkout keeps
    (app_listen.READ_STEP), whole only for the first read of the day, then only what changed.
    It read screen, meta and addr whole at every finish (the review of 2026-11-11, 2C-4)."""
    import app_listen
    return app_listen.READ_STEP.format(url=url, dump="$D/page").rstrip(".")


# A refused batch, in one line: the version command reads again just what moved on since the
# read (the record it names, and the screens, meta and heartbeats other chats keep moving:
# page_db.read_again) and the same command runs once more. "Read those four again" read all
# four collections, and a second record moved on was refused again (2026-11-10).
REFUSED_ONCE = ("A refused batch: python3 tools/app.py version \"$D\" <the record> <the version> "
                "the refusal names, which reads again just what moved on, then the same command "
                "once more and send what it prints.")


# How a job's chat saves and waits for the save before its next step: land.py in the
# foreground, which ends when the landing has. A chat told only to "wait until the landing has
# ended" waited with `until ! pgrep -f tools/land.py`, which matched its own command line and
# never ended (2026-11-10).
LAND_AND_WAIT = ("Save and land your work on master (CLAUDE.md, \"Saving\"): run python3 "
                 "tools/land.py in the foreground (never --detach, never in the background), so the "
                 "command itself ends when the landing has, then make the calls it prints. Never "
                 "wait on it with a pgrep loop: it matches its own command line and never ends.")


def _next_job(url: str, first_word: str = "Then", kind: str = "cloud",
              computer_only: bool = False) -> str:
    # A chat on the computer takes the next piece of work sent there, as a computer chat:
    # told "--kind cloud --job-chat", it would have taken cloud work and refused its own.
    what, flags = (("piece of work for this computer", f"{kind} --computer-only")
                   if computer_only else ("big job", f"{kind} --job-chat"))
    # A chat the app started on the computer never puts itself away: its prompt's last steps
    # (the heartbeat, the earlier chats, waking the starter, whose land.py brings this chat's
    # saved work to master) come after this one, and the starter archives it. Told to archive
    # itself here, it never reached them (the builder audit, 2026-11-10, CC-2).
    nothing = ("Nothing named: go on with step 7 of your prompt, then steps 8 and 9 (the "
               "heartbeat, this computer's earlier chats, waking the chat that started you). "
               "Never archive this chat: the chat that started you puts it away."
               if computer_only else
               "Nothing named: your work is saved and on the page, so put this chat away "
               "yourself: get_session with no id first, and where its status says archived, it "
               "is archived already: stop there. Otherwise archive_session with this chat's own "
               "id (refused, or not among your tools: leave it, the chat that answers the page "
               "puts it away), then stop. A finished job's chat stayed idle in the sidebar for "
               "up to a day (2026-11-10).")
    return (f"{first_word}, the next {what} waiting, so a queue keeps moving with nobody to "
            f"start it: ArtifactData query, url {url}, collections work, holds and beats, out_dir a "
            f"fresh folder $E; python3 tools/app.py next \"$E\" --chat <this chat's id> --kind "
            f"{flags} --on \"<your model>\" --claim-out \"$E/claim\". {nothing} "
            "One named: send its claim batch (refused: another chat has it, stop), then "
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
    call to make (its prompt runs the item, pins its progress, saves, brings the page up to
    date and puts itself away, messaging no chat), or, where a chat cannot start one (a chat on a computer, or no
    create_session tool), `background agent` with the Agent call. A big job is never `here`.
    `taken`: the names of the job chats still at work."""
    if not chosen.get("heavy"):
        return {"run": "here"}
    import app_listen
    import app_setup
    url = app_setup.page_record().get("url", "") or "<url>"
    # The chat the job's chat is started from: this chat's own. Where it is not known here,
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
                "extra_allowed_tools": list(CHILD_TOOLS),
                "permission_mode": app_listen.SESSION_MODE}
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


def _me(claimed_under: str = "") -> str:
    """This chat's own id, where it is not the one the work was claimed under: a job's chat
    writes under the id of the chat that started it (page_db.not_its_claim)."""
    import app_listen
    me = app_listen.this_chat("")
    return "" if me == str(claimed_under or "") else me


def cmd_pin(a) -> int:
    """One running item's progress, pinned: its stage, a plain line, a count, the time left
    (or a search's round.log, which says all three), with its lease renewed."""
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    if getattr(a, "first", False):
        # A job's first command over its folder (`--first`, job_steps): a job's own chat is
        # told no versions step where its copy's settings hold the app's hook, but a chat runs
        # the hooks it started with, so its read may have kept none; and a folder an earlier
        # run read into would stand for this one (the review of 2026-11-11, E-6 and E-18).
        import page_reads
        n = page_db.unkept(a.dump)
        if n:
            print(f"app: this read's {n} records have no version kept yet, so nothing is "
                  "written: " + page_db.versions_step(a.dump)[len("then "):] + ". Then run "
                  "this again.")
            return 2
        again = page_reads.job_begun(a.dump, a.work[0], a.chat, now)
        if again:
            print(f"app: {a.dump} holds an earlier run's read, so nothing is written: read the "
                  f"page again as the job's first step says into {again}, which is $D from "
                  "here on, then run this again with it.")
            return 2
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
    if getattr(a, "blocked", False) or getattr(a, "alive", False):
        # Written by the chat that answers the page, about a job in a chat of its own whose
        # status reads blocked (its card says it waits on the person there), or still working
        # (its lease renewed, so it is never started twice).
        mark = page_db.mark_blocked if getattr(a, "blocked", False) else page_db.mark_alive
        batches = []
        for wid in works:
            try:
                batches += mark(db, wid, now, os.path.join(out, page_db.safe_id(wid)))["batches"]
            except KeyError as e:
                print(f"app: {e.args[0]}", file=sys.stderr)
                return 2
        print(_dump({"blocked" if getattr(a, "blocked", False) else "alive": works,
                     "batches": batches}), end="")
        return 0
    # A posting claimed `with` another item named here is renewed and moved by that item's own
    # pin. Written again on its own, from the same read, it went in two batches pinned to one
    # version: whichever was sent second was refused, and a refused leader's batch left the
    # folder one ahead of the page (the maintainer's copy, 2026-11-06).
    named = {page_db.safe_id(w) for w in works}
    led: dict = {}
    for wid in works:
        for mid in page_db.members(db, page_db.safe_id(wid)):
            if mid in named and mid != page_db.safe_id(wid):
                led.setdefault(mid, wid)
    got_by: dict = {}
    for wid in works:
        if page_db.safe_id(wid) in led and led[page_db.safe_id(wid)] not in led:
            continue
        try:
            got_by[wid] = page_db.pin(db, wid, now, out if len(works) == 1 else
                                      os.path.join(out, page_db.safe_id(wid)),
                                      stage=stage, line=a.line, count=count, left_s=left,
                                      dump_dir=a.dump, chat=a.chat, me=_me(a.chat))
        except KeyError as e:
            print(f"app: {e.args[0]}", file=sys.stderr)
            return 2
    got_all = []
    for wid in works:
        if wid in got_by:
            got_all.append(got_by[wid])
            continue
        lead = got_by.get(led[page_db.safe_id(wid)]) or {}
        got_all.append({"work": wid, "with": led[page_db.safe_id(wid)],
                        "stop_asked": page_db.safe_id(wid) in (lead.get("stopped") or []),
                        "stage": lead.get("stage"), "batches": []})
    # Each pin renews its lease: kept on this computer too, where reading.py next gates a
    # read on it after a long gap (claim_gate; the independent review, 2026-11-11).
    import app_setup
    for g in got_all:
        try:
            app_setup.renew_claim(str(g.get("work") or ""))
        except OSError:
            pass
    if len(got_all) == 1:
        print(_dump(got_all[0]), end="")
    else:
        print(_dump({"works": got_all, "stop_asked": any(g["stop_asked"] for g in got_all),
                     "batches": [b for g in got_all for b in g["batches"]]}), end="")
    return 0


def cmd_resume(a) -> int:
    """Work taken into this chat because the person said so here (page_db.resume): their
    answer to its question given in this chat, or queued work they asked this chat to do now.
    Claimed by this chat and running, so nothing starts it elsewhere; then pin and finish it
    as any claimed work."""
    import app_listen
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    db = page_db.load(a.dump)
    try:
        got = page_db.resume(db, a.work, a.chat, a.kind or app_listen.chat_kind(), now,
                             a.out or os.path.join(a.dump, "out"), answer=a.answer,
                             dump_dir=a.dump)
    except (KeyError, ValueError) as e:
        # The work as the chat just read it, taken or not: one finished since this checkout
        # last read the page refused every read of its people, and this was the step the
        # refusal named (the engine review, 2026-11-11).
        _claimed_here(a.dump, {"work": a.work})
        print(f"app: not taken: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
    _claimed_here(a.dump, got)
    print(_dump(dict(got, then="Send the batch (ArtifactData batch), then do the work here: pin "
                              "it as it goes and finish it with app.py done, --chat this chat's id.")),
          end="")
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


# A scheduled run starts with the command every chat starts with (CLAUDE.md, which names no
# exception for a run and is at its size limit), and it runs that task's own start: the
# brief's prompt said brief.py --start, and a run obeying CLAUDE.md spent minutes on a
# person's start (second audit B11).
SCHEDULED_STARTS = ("morning_brief",)


def cmd_start(a) -> int:
    import app_listen
    import app_setup
    scheduled = getattr(a, "scheduled", "")
    if scheduled:
        if scheduled not in SCHEDULED_STARTS:
            print(f"app: no start of its own for the scheduled run {scheduled!r}: follow its "
                  "prompt file's first step", file=sys.stderr)
            return 2
        import brief
        return brief.start(["--on", a.on, "--write"], a.on)
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
    if a.work and os.environ.get(START_UPDATED) is None and app_listen.chat_kind() == "computer":
        # A job's chat on the person's computer works in their own folder, which holds master
        # as of the last save made there, days old perhaps: it takes master first, as every
        # chat's start does (the day's check), so who was written to since, and the contact
        # book, are read as they are. It took no update check, and nothing before the job's
        # end took master: people another chat had written to were shown again (the engine
        # review, 2026-11-11). Code it brings in runs the start again on the new code.
        before = app_setup._git("rev-parse", "HEAD")[1].strip()
        line = app_setup.take_master()
        if line:
            print(line)
        if app_setup.code_moved(before):
            import subprocess
            sys.stdout.flush()
            return subprocess.run([sys.executable, os.path.abspath(__file__)] + list(a.argv),
                                  env=dict(os.environ, **{START_UPDATED: ""})).returncode
    # The day's update check runs here, in this command, and where it took an update the
    # rest of the start runs again on the new code. Printed as a step, the chat ran the check
    # and then, on almost every update, was told to run the whole start again (D1, H-2,
    # 2026-11-10: 12 of 15 updates changed the files the start is made of).
    # A new helper's first words, the page's link, said before the update check runs: run
    # first, the check held the "say this at once" line back until it ended (the review of D3,
    # 2026-11-11). Printed once, by the first run; the run made again on new code leaves it.
    url = ""
    if a.helper and not a.work:
        url = str(app_setup.page_record().get("url") or "")
        if url and app_listen.role(app_listen.this_chat(a.chat), a.listen, url) \
                in ("claim", "listener"):
            if os.environ.get(START_UPDATED) is None:
                print(app_listen.helper_first(url), flush=True)
        else:
            url = ""
    said: list[str] = []
    if not a.work and os.environ.get(START_UPDATED) is None:
        check = days_check(a.on, app_listen.this_chat(a.chat), a.tools or "")
        if check.get("ran"):
            said = check["said"].rstrip("\n").splitlines()
            if check.get("landed"):
                import subprocess
                path = os.path.join(app_setup._local_file("ljs-start-sync.txt"))
                try:
                    with open(path, "w", encoding="utf-8", newline="\n") as fh:
                        fh.write(check["said"])
                except OSError:
                    path = ""
                sys.stdout.flush()
                env = dict(os.environ, **{START_UPDATED: path})
                return subprocess.run([sys.executable, os.path.abspath(__file__)] + list(a.argv),
                                      env=env).returncode
    elif os.environ.get(START_UPDATED):
        try:
            with open(os.environ[START_UPDATED], encoding="utf-8") as fh:
                said = fh.read().rstrip("\n").splitlines()
        except OSError:
            said = []
    code, lines = app_setup.start(on=a.on or "", tools=a.tools or "", page_url=a.page or "",
                                  work=a.work or "",
                                  checked=bool(said) or START_UPDATED in os.environ)
    lines = app_listen.shape(code, lines, chat=app_listen.this_chat(a.chat), listen=a.listen,
                             helper=a.helper, on=a.on or "", work=a.work or "",
                             link_said=bool(url))
    step = own_tests_first() if code == 0 else ""
    if step:
        lines = lines[:1] + [step] + lines[1:]
    if said:
        # This start already runs on whatever code the check brought in: its "run start again"
        # is said of a start from before, never of this one.
        said = [ln for ln in said if not ln.startswith(app_setup.START_CHANGED[:40])
                and ln.strip() != app_setup.PAGE_NOT_YET]
        lines = lines[:2] + [
            "Before the steps below: the day's update check ran in this command (python3 "
            f"tools/sync_app.py --if-stale; {app_setup.SYNC_DO}{app_setup.SYNC_PAGE}). What it "
            "printed:"] + ["  " + ln for ln in said] + [
            "(end of what the update check printed)"] + lines[2:]
    print("\n".join(lines))
    return code


# Set on the start run again on the code the day's update check brought in: the file holding
# what the check printed, or "" when it could not be kept. Never a third run.
START_UPDATED = "LJS_START_UPDATED"


def own_tests_first() -> str:
    """The step that brings the person's own tests in line after an update, while they still
    fail (sync_app.own_tests_step), for every command that starts work to say first; "" in
    the app itself, and whenever there is nothing to bring in line."""
    try:
        import sync_app
        if sync_app.is_the_app():
            return ""
        return sync_app.own_tests_step()
    except Exception:  # noqa: BLE001  an older or half-made copy: the work goes on
        return ""


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
                  f"(ArtifactData batch, url {a.url}):")
            for path in got["batches"]:      # a line each: a folder name may hold a space
                print(path)
    return 0


def running_elsewhere(db: dict, chat: str) -> list[tuple[str, str]]:
    """[(work id, chat id)] for work running in a cloud chat of its own (claimed by another
    session_ chat), not already said to wait on the person."""
    out = []
    for wid, doc in sorted((db.get("work") or {}).items()):
        d = doc.get("data") or {}
        # The job's own chat where it has said so (`run_by`, its first pin): a job chat works
        # under the id of the chat that started it, so this one's own were never listed, and
        # after a hand-over the old helper was taken for a job chat (the second audit, C1).
        by = str(d.get("run_by") or d.get("claimed_by") or "")
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
             hand: str = "", update: bool = False, partial: bool = False,
             lineage: tuple[int, int] | None = None) -> dict:
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
                            hand_to=hand, update=update, lineage=lineage)
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
        # A note set aside for now whose day has come is offered again, in code, on the same
        # wake: "for now" held them for good (the rules review, 2026-11-11).
        try:
            from network import state as _contacts
            back = _contacts.reopen_set_aside(app_model.local_day(
                now, person.home_zone_named(person.directory()) or "UTC"))
        except Exception:  # noqa: BLE001  no profile or no contact book yet
            back = []
        if back:
            upkeep.append(f"upkeep: {len(back)} note(s) set aside for now were offered again, "
                          "their day come; save them with the rest (python3 "
                          "tools/save_state.py)")
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
        # Asked about once each RETIRE_AGAIN_S (tidy.retire_due): in between, the day's sweep.
        retire = tidy.retiring(got.get("record"), now) if tidy_due and tidy.retire_due(now) else ""
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
             "no file. Shortened, keep for each chat id, title, origin, session_status and "
             "updated_at, and for each task id, name, enabled, persistent_session_id, "
             "cron_expression, run_once_at, created_at, last_run and prompt: the plan reads "
             "nothing else. Do what it prints.")
TIDY_COMPLETED = (" This week's sweep: list_triggers with include_completed: true, so the one-off "
                  "tasks that have fired are found and the app's own cleaned away.")
TIDY_SAID = ("tidy: once today, after this wake's work and asking nobody: the app's own "
             "old chats (tools/tidy.py). " + TIDY_GIVE)
# After a hand-over only the helper taken over from is judged, from one get_session of it: the
# whole listing typed back by hand was slow, costly and cut short (H-4; second audit A6, R3).
TIDY_NOW = ("tidy: now, once the batches above are sent, asking nobody: the app's chat this one "
            "took the page over from, {old}, is put away as soon as its work is saved "
            "(tools/tidy.py). get_session (session_id {old}); then python3 tools/tidy.py retire "
            "--dump \"$D\" --stdin with {{\"details\": <what get_session returned>}} in a quoted "
            "heredoc; do what it prints, and archive nothing by hand.")


def cmd_listen(a) -> int:
    import app_listen
    import app_model
    _, now = app_model.clock(None, a.now)
    out = a.out or os.path.join(a.dump, "listen_out")
    got = check_in(a.dump, app_listen.this_chat(a.chat), now, out, listen=a.listen,
                   lineage=app_listen.read_lineage(getattr(a, "lineage", "")),
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
        if got.get("retire"):
            print(TIDY_NOW.format(old=got["retire"]))
        else:
            # Once a week the sweep also asks for the tasks that have fired, so the app's
            # one-off check-ins are cleaned away; every day it swelled the listing typed back.
            import tidy
            day = now.date().isoformat()
            weekly = tidy.completed_due(day)
            print(TIDY_SAID + (TIDY_COMPLETED if weekly else ""))
            if weekly:
                tidy.mark_completed(day)
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
# Set on the page update run again on the code taking master brought in (cmd_view): never a
# third run.
VIEW_AGAIN = "LJS_VIEW_AGAIN"
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
           "tools/app.py reads --in <your scratchpad> first, which makes and names it: a whole "
           "read)")


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


def days_check(on: str, chat: str, tools: str = "") -> dict:
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
                        "--on", on or "<this chat's model>"] + (["--tools", tools] if tools else []),
                       cwd=os.path.dirname(_HERE),
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
    if before and _git("diff", "--quiet", before, "HEAD", "--", ".claude/skills/app")[0] == 1:
        out.append("skill")
    return out


def _again(a, chat: str) -> str:
    flags = (f" --kind {a.kind}" if a.kind else "") + \
        (f" --on \"{a.on}\"" if a.on else "") + (" --no-sessions" if a.no_sessions else "")
    return f"python3 tools/app.py wake \"{a.dump}\" --chat {chat}{flags}"


# The ring is a comment sent to Claude; left open it stays unread in the Claude app for ever.
# The thread it came on, on every ring; the other open rings, each one left open keeping the
# blue dot on Claude's comments button, are the helper's to close (the maintainer,
# 2026-11-10), but listing every open thread and judging each on every ring was a call and a
# read each time (the efficiency audit, E-9): so a wake sweeps them at most once every
# RINGS_SWEPT_EVERY_S, by a mark in this checkout's git folder (the review of 2026-11-11), and
# the daily tidy (`doorbells`) still clears any a quiet day left.
RESOLVE_RING = ("last, once this wake's work is done: ArtifactComments resolve (url {url}, "
                "thread_id: the thread this wake came on, which the notification that woke you "
                "names as thread=...). Resolving is not answering: leave no reply. A wake with "
                "no such thread (a timer, a run by hand) has nothing to resolve.")
RESOLVE_OTHERS = (" Then, as no wake has for a few hours, the page's other open rings: "
                  "ArtifactComments list (url {url}), and resolve any other open thread whose "
                  "first line starts \"[app]\" and whose work is finished or no longer on the "
                  "page, with no reply: each one left open keeps the blue dot on Claude's "
                  "comments button (the maintainer, 2026-11-10).")
RINGS_SWEPT = "ljs-rings-swept"      # in this checkout's git folder: when a wake last swept them
RINGS_SWEPT_EVERY_S = 3 * 3600


def rings_sweep_due(now: dt.datetime) -> bool:
    """Is this wake the first in RINGS_SWEPT_EVERY_S to sweep the page's other open rings?
    If so, the time is kept, so the next few hours of wakes do not."""
    import app_listen
    import app_model
    path = app_listen.checkout_file(RINGS_SWEPT)
    try:
        with open(path, encoding="utf-8") as fh:
            last = app_model.parse_time(fh.read().strip())
    except OSError:
        last = None
    if last is not None and 0 <= (now - last).total_seconds() < RINGS_SWEPT_EVERY_S:
        return False
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(now.strftime("%Y-%m-%dT%H:%M:%SZ") + "\n")
    except OSError:
        return False            # nowhere to keep it: never sweep on every ring
    return True


# What `wake` shows of a big job under `next:`: the call to make, and what names it.
SHOWN_BIG = ("work", "kind", "title", "run", "first", "create_session", "agent")


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
    if app_listen.nested(chat):
        # The platform refused this chat a new chat for nesting (`app.py nested`): its big
        # jobs run as background agents, never a create_session that fails again.
        a.no_sessions = True
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
                    out.append(f"{n}. Claude: the app skill (.claude/skills/app) changed. This "
                               "chat is still following the copy it loaded: read SKILL.md and "
                               "the files it named that this chat had read again now, before "
                               "going on.")
                    n += 1
                out.append(f"{n}. Then read the page again into a new folder (python3 "
                           "tools/app.py reads --in <your scratchpad>, which makes and names it, "
                           "and its queries) and wake once more with it: "
                           + _again(a, chat).replace(f"\"{a.dump}\"", "\"<the new folder>\""))
                out.append("What the day's update check printed:")
                print("\n".join(out + said))
                return 0
            head = [sync_line] + said + ["(end of what the update check printed)"]
        reads = {}
        try:
            import page_reads
            planned = os.path.isfile(os.path.join(a.dump, page_reads.PLAN))
        except Exception:  # noqa: BLE001
            planned = False
        if planned and page_db.unkept(a.dump):
            # The read's versions were not kept: this chat runs without the app's hook (it
            # started before its settings held it). Asked here, once the read is in, and only
            # here: asked after every read, a chat retyped them all for nothing (E-6).
            print("\n".join(head + [
                "wake: this read's records have no version kept yet, so nothing is written: "
                + page_db.versions_step(a.dump)[len("then "):] + ". Then run this again: "
                + _again(a, chat)]))
            return 0
        try:
            if planned:
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

    first = own_tests_first()
    if first:
        head = [first] + list(head)
    db = page_db.load(a.dump)
    away = running_elsewhere(db, chat)
    if away:
        # A job's own chat can stop on a question to the person (an approval it needs), with
        # nobody there to see it: the page said only "may have stopped" (X-7, X-8).
        notes.append("jobs in chats of their own: get_session each ("
                     + ", ".join(f"{c} for {w}" for w, c in away) + "); for one whose "
                     f"status_bucket is blocked: python3 tools/app.py pin \"{a.dump}\" --work "
                     "<its work id> --blocked, and for one still working, the same with --alive "
                     "(so it is never started twice); send the batch each prints. Say nothing "
                     "about it in the chat: its card on the page says it.")
    chosen = choose(db, chat, kind, now, on=a.on, no_sessions=a.no_sessions,
                    claim_out=os.path.join(rd, "work"))
    then: list[str] = []
    if chosen:
        sends += [(p, "work", joined) for p in chosen["batches"]]
        # Claimed, as it will be once sent: run again over this folder, `next` takes the one
        # after it, pinned to the versions this claim leaves.
        page_db.keep_landed(a.dump, chosen["batches"])
        _claimed_here(a.dump, chosen)
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
                _claimed_here(a.dump, nxt)
                also.append(nxt)
        more = choose(page_db.load(a.dump), chat, kind, now, on=a.on,
                      no_sessions=a.no_sessions) is not None
        shown = dict(chosen)

        rows_given: set = set()

        def with_item(c):
            item = ((db.get("work") or {}).get(c["work"]) or {}).get("data") or {}
            # Its row of step 4's table, so the chat reads none of the table (E-3), once for
            # each kind: ten tweaks taken in one pass printed the same row ten times (the
            # review of 2026-11-11).
            kind_of = str(c.get("kind") or "")
            row = work_row(kind_of) if kind_of not in rows_given else ""
            if row and not c.get("steps"):
                rows_given.add(kind_of)
            return talk_words(dict(c, **{k: item[k] for k in ("args", "answers", "note")
                                         if k in item}, **({"do": row} if row and not c.get("steps") else {})),
                              a.dump, url)
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
                what = (f"do it here, now, as its `do` says (step 4's row for a "
                        f"{chosen['kind']})" if not also
                        else f"do each here, now, in order (the one under next:, then each "
                             f"also:), as the `do` of the first of its kind says (step 4's row "
                             f"for that kind, printed once); they are "
                             f"{len(also) + 1} items, every one claimed in this pass" +
                             (f"; for the follow-ups, one run: {run_ups}" if ups else ""))
            if chosen.get("steps"):
                # A big job done here (a networking run on the computer, whose reads need this
                # chat's browser): its own steps, pins and finish, never "as step 4's row says"
                # with "no progress pin follows", which a twenty-minute run took at its word.
                then.append("then: once its claim is accepted, follow the `steps` under next: "
                            "below, in order, here in this chat: it has the browser this run "
                            "needs." + (" More is waiting: once it is done, read again into a "
                                        "new folder and wake once more (step 3 again)."
                                        if more else ""))
            else:
                then.append(f"then: once {'its claim is' if not also else 'their claims are'} "
                            f"accepted, {what}. Its claim marks it running at its first "
                            "stage, so no progress pin follows; " + (
                                "it finishes them itself." if not also and ups else
                                "finish it as step 5 says.") + (
                                " More is waiting: then read again into a new folder and wake "
                                "once more (step 3 again)." if more else ""))
        else:
            # Only what the call needs: its stages, locks, claim files and model were printed
            # in it, sent above or read by nothing, every one a line of the listener's (E-8).
            shown = {k: chosen[k] for k in SHOWN_BIG if k in chosen}
            call = "create_session" if chosen.get("run") == "child session" else "Agent"
            import app_listen
            then.append(f"then: only once the work's claim is accepted, make the {call} call "
                        "in `next` below exactly as it is printed" + (
                            f" (first {chosen['first']})" if chosen.get("first") else "") +
                        ", and never wait for it." + (
                            app_listen.MODE_REFUSED if call == "create_session" else "") + (NESTED_JOB.format(chat=chat, dump=a.dump)
                                                      if call == "create_session" else "") + (
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
    last = [RESOLVE_RING.format(url=url)
            + (RESOLVE_OTHERS.format(url=url) if rings_sweep_due(now) else "")]
    if phase in ("next", "apply") and (after or tidy_due):
        last.append("after this wake's work, asking nobody:")
        if after:
            last += [PRUNE_SAID] + after
        if tidy_due:
            last.append(TIDY_SAID)
    _print_wake(head, notes, _send_as(sends, rd, a.dump), url, then=then + last)
    return 0


def talk_words(shown: dict, dump: str, url: str) -> dict:
    """A message from the page's chat, with its words: the page puts them on the item
    (`args.text`); an item made before it did gets them from the thread when the folder holds
    the message, else the one read that fetches it. The item carried only `args.message`, and
    every chat read the thread for the words (2026-11-09)."""
    args = shown.get("args") if isinstance(shown.get("args"), dict) else None
    if shown.get("kind") != "talk" or not args or args.get("text") or not args.get("message"):
        return shown
    th, mid = str(args.get("thread") or ""), str(args["message"])
    import page_db
    for name in (mid.replace("~", "@"), mid):
        got = page_db._read_json(os.path.join(dump, "talk", th, "messages", name + ".json"))
        if isinstance(got, dict):
            fields, _v = page_db.unwrap(got)
            if str(fields.get("text") or "").strip():
                return dict(shown, args=dict(args, text=str(fields["text"])))
    return dict(shown, read_words=(f"ArtifactData get, url {url}, collection talk/{th}/messages, "
                                   f"doc_id {mid}: its `text` is what they said"))


# A job's chat refused because this chat can start no more (chats nest only so deep): the
# job is not lost. Its claim lapses and the next wake runs it as a background agent.
NESTED_JOB = (" If the create_session is refused because this chat cannot start any more "
              "chats: python3 tools/app.py nested \"{dump}\" --chat {chat}, send the batch it "
              "prints, and say nothing: from then on big jobs run here as background agents, "
              "and this one is taken again that way once its claim lapses.")


RETIRED_WAIT_S = 40 * 60
UNSAVED_PREFIX = "unsaved-"      # meta/unsaved-<chat>: a save a retired chat gave up on
UNSAVED_TITLE = "Job search: changes to save, {day}"   # that chat's own name, the card says it
UNSAVED_DAYS = 14                # its card goes after this long, whatever became of the work


def _on_github_sha(sha: str) -> bool:
    """Is this commit on a branch GitHub holds, as the last fetch saw it?"""
    import land
    import person
    if not sha:
        return False
    r = land._git(person.state(), "branch", "-r", "--contains", sha)
    return r.returncode == 0 and bool(r.stdout.strip())


def unsaved_saves(db: dict, now) -> tuple[list[dict], list[tuple[str, int]]]:
    """(records to show, [(doc id, version) to delete]) from the page's meta/unsaved-<chat>
    records (cmd_retired): one is shown until its work is on GitHub or UNSAVED_DAYS old."""
    import app_model
    show, gone = [], []
    for doc_id, doc in ((db or {}).get("meta") or {}).items():
        if not str(doc_id).startswith(UNSAVED_PREFIX):
            continue
        rec = (doc or {}).get("data") or {}
        since = app_model.parse_time(rec.get("since"))
        old = since is None or (now - since).total_seconds() > UNSAVED_DAYS * 86400
        if old or _on_github_sha(str(rec.get("head") or "")):
            gone.append((doc_id, (doc or {}).get("version")))
        else:
            show.append(rec)
    return show, gone
RETIRED_TRIES = 2          # saves started for one retired helper before it stops trying
RETIRED_FILE = "ljs-retired-saves.json"   # in the git folder: tries per chat, never committed


def _retired_record(root: str) -> tuple[str, dict]:
    import land
    d = land.git_dir(root)
    if not d:
        return "", {}
    path = os.path.join(d, RETIRED_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        got = {}
    return path, (got if isinstance(got, dict) else {})


def _retired_tries(root: str, chat: str, reset: bool = False) -> int:
    """The saves of this retired helper that ended without reaching GitHub, kept in the
    checkout's git folder: one is counted only when a save it started has ended (no landing
    runs) and the work is still not there; a save still landing counts nothing (review of
    fix/helpers, item 5: three wakes during one slow landing gave up on it). `reset` forgets
    them. 0 where there is no git folder to keep it in."""
    path, got = _retired_record(root)
    if not path:
        return 0
    rec = got.get(chat) if isinstance(got.get(chat), dict) else {"failed": int(got.get(chat) or 0)}
    if reset:
        rec = {"failed": 0, "started": False}
    elif rec.get("started"):
        rec = {"failed": int(rec.get("failed") or 0) + 1, "started": False}
    got[chat] = rec
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(got, fh)
    except OSError:
        pass
    return int(rec.get("failed") or 0)


def _retired_started(root: str, chat: str) -> None:
    """Note that a save was started for this retired helper, so its end is counted."""
    path, got = _retired_record(root)
    if not path:
        return
    rec = got.get(chat) if isinstance(got.get(chat), dict) else {"failed": int(got.get(chat) or 0)}
    rec["started"] = True
    got[chat] = rec
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(got, fh)
    except OSError:
        pass


def _saved_on_github(root: str) -> bool:
    """Is everything of this chat's on GitHub: nothing unsaved, no landing running, and its
    commit on master or on a branch GitHub holds (where the next landing brings it in)?"""
    import land
    import save_state
    if land.landing(root) or save_state.unsaved(root):
        return False
    head = land._git(root, "rev-parse", "HEAD").stdout.strip()
    if not head:
        return False
    if land._git(root, "merge-base", "--is-ancestor", "HEAD", "origin/master").returncode == 0:
        return True
    return bool(land._git(root, "branch", "-r", "--contains", "HEAD").stdout.strip())


def cmd_retired(a) -> int:
    """A helper that has handed the page on (app_listen.retired_here): no more work. Its own
    save is started where it is not on GitHub yet, with a wait that wakes it once it ends;
    saved, it archives itself at once. A chat that still answers the page is told so."""
    import app_listen
    import person
    chat = app_listen.this_chat(a.chat)
    if not chat or not app_listen.retired_here(chat):
        print("retired: this chat answers the page, or never did: carry on as before.")
        return 0
    root = person.state()
    if getattr(a, "wait", False):
        import time
        import land
        until = time.monotonic() + RETIRED_WAIT_S
        while land.landing(root) and time.monotonic() < until:
            time.sleep(5)
        if land.landing(root):
            # Timed out with the save still running: never said ended, so a stuck save is
            # not taken for a finished one and started again (audit HC-3); the wait is armed
            # again, and nothing starts another save (review of fix/helpers, item 5).
            print("retired: still saving after %d minutes. In the background (run_in_background) "
                  "run python3 tools/app.py retired --chat %s --wait again, and end the turn with "
                  "nothing more: the save goes on by itself." % (RETIRED_WAIT_S // 60, chat))
            return 1
        print("retired: its save has ended: python3 tools/app.py retired --chat " + chat)
        return 0
    if _saved_on_github(root):
        _retired_tries(root, chat, reset=True)
        # Another chat may have put it away already (the tidy-up of the helper that took the
        # page): archiving it again hung for 1m 45s (H-8). So it looks first.
        print("retired: its work is saved. Put this chat away now, as the last calls of the "
              "turn: get_session with no id, and where its status says archived, it is "
              "archived already: end the turn there. Otherwise archive_session "
              + json.dumps({"session_id": chat}) + ". Where "
              "archive_session is not among this chat's tools, end the turn: the tidy-up in "
              "the chat that answers the page puts it away. Say nothing about it.")
        return 0
    import land
    if land.landing(root):
        # One save is still landing: nothing new is started or counted, the wait is armed.
        print("retired: its save is still landing. In the background (run_in_background) run "
              f"python3 tools/app.py retired --chat {chat} --wait, which wakes this chat once it "
              "has ended, and end the turn with one line: \"This chat has handed your page on.\"")
        return 0
    if _retired_tries(root, chat) >= RETIRED_TRIES:
        # Said on the person's page too, as a record the next page update turns into one To
        # do card (audit HC-3), so the work left here is never lost in silence.
        import app_model
        import app_setup
        import land
        import page_db
        _, now = app_model.clock(None, None)
        head = land._git(root, "rev-parse", "HEAD").stdout.strip()
        # A name of its own, which the card gives: every helper is "Job search page", and the
        # person could not tell which chat to open (review of fix/helpers, item 5).
        title = UNSAVED_TITLE.format(day=f"{now.day} {now.strftime('%B')}")
        w = page_db.Writes(os.path.join(land.git_dir(root) or root, "ljs-retired-out"))
        w.add("set", "meta", UNSAVED_PREFIX + chat,
              {"chat": chat, "title": title, "since": app_model.stamp(now), "head": head})
        url = app_setup.page_record().get("url") or "<the page>"
        print("retired: its own save did not reach GitHub after two tries, so no more are "
              "started. First give this chat a name of its own: set_session_title (session_id "
              f"{chat}, title \"{title}\"). Then send this batch (ArtifactData batch, url {url}), "
              "asking nobody: it puts a To do card on their page naming this chat.")
        for p in w.save("unsaved"):
            print(p)
        print("Then leave this chat as it is (never archive it: its work is only here) and "
              "end the turn with one line: \"This chat has handed your page on.\"")
        return 0
    _retired_started(root, chat)
    print("retired: its own save is not on GitHub yet. Run python3 tools/land.py --detach "
          "--message \"The last work of the helper before\" (an ordinary call, it returns at "
          "once), then, in the background (run_in_background), python3 tools/app.py retired "
          f"--chat {chat} --wait, which wakes this chat once the save has ended. End the turn "
          "with one line: \"This chat has handed your page on.\"")
    return 0


def cmd_hand_over(a) -> int:
    """A hand-over the person asked for ("hand over to a fresh helper and archive yourself"),
    past the daily renewal's gates, in one command: the fresh helper, the page handed to it by
    its id, and this chat's own save and archive (second audit A7: it took many turns on a
    chat of 630,000 tokens)."""
    import app_listen
    import app_setup
    import page_db
    chat = app_listen.this_chat(a.chat)
    owner, name = app_setup.origin()
    if not chat or not owner or not name:
        print("app: hand-over needs this chat's id (--chat) and the copy's GitHub address",
              file=sys.stderr)
        return 2
    url = app_setup.page_record().get("url") or "<the page>"
    # Read first, and only the chat that answers the page hands it over: printed first, the
    # create_session left a stray helper that took the page from a retired or other chat
    # (review of fix/helpers, item 12).
    if not a.dump:
        print(f"hand-over: read the page first: ArtifactData query, url {url}, collections meta "
              "and work, out_dir a fresh folder $D, limit 1000; then python3 tools/app.py "
              f"hand-over --chat {chat} --dump \"$D\". Say nothing yet.")
        return 0
    db = page_db.load(a.dump)
    rec, _version = app_listen.record(db)
    if rec.get("chat") != chat or app_listen.retired_here(chat):
        print("hand-over: this chat does not answer the page, so it has nothing to hand over. "
              "Tell the person in one line: \"Another chat already looks after your page.\"")
        return 1
    call = app_listen.helper_call(db, owner, name)
    print("hand-over: do these in order, asking nobody; tell the person one line at the end: "
          "\"A fresh chat looks after your page now.\"")
    print("1. create_session " + json.dumps(call, ensure_ascii=False) + "." +
          app_listen.MODE_REFUSED)
    print(f"2. With its id: ArtifactData query, url {url}, collection meta, out_dir a fresh "
          f"folder $H, limit 1000; python3 tools/app.py listen \"$H\" --chat {chat} --hand "
          f"<its id>; send the batch it prints, then ArtifactComments, action watch, url {url}, "
          "on: false.")
    print(f"3. python3 tools/app.py retired --chat {chat}, and do what it prints: it saves this "
          "chat's work, then puts this chat away.")
    return 0


def cmd_nested(a) -> int:
    """The platform refused this chat a new chat or scheduled task because chats nest only so
    deep (each helper started the next, one level deeper a day, 2026-11-05). Kept in this
    checkout (its wakes run big jobs as background agents, its renewal waits for the brief's
    run) and, with a read of the page, on the page's record, so the brief's next run in a
    chat of its own starts the fresh helper (app_listen.view_renewal)."""
    import app_listen
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    chat = app_listen.this_chat(a.chat)
    if not chat:
        print("app: give this chat's id: --chat <its id>", file=sys.stderr)
        return 2
    app_listen.mark_nested(chat, now)
    out = ["nested: kept. This chat keeps answering the page; its big jobs run as background "
           "agents from now on (wake does so by itself), and the brief's next run starts its "
           "fresh helper. Say nothing about it to the person."]
    batches: list = []
    if a.dump:
        db = page_db.load(a.dump)
        rec, version = app_listen.record(db)
        if rec.get("chat") == chat and version is not None:
            w = page_db.Writes(a.out or os.path.join(a.dump, "nested"))
            w.add("update", app_listen.DOC_COLLECTION, app_listen.DOC_ID,
                  {"nested_at": app_model.stamp(now)}, if_version=version)
            batches = w.save("nested")
            page_db.keep_landed(a.dump, batches)
    if batches:
        import app_setup
        url = app_setup.page_record().get("url") or "<the page>"
        # Each file on a line of its own, as wake prints them: a person's folder may hold a
        # space (a Windows user folder named "First Last"), and a path mid-sentence then reads as two.
        out.append(f"send, as one ArtifactData batch (url {url}, its entries as writes; it tells "
                   "the brief's run to start the fresh helper; refused: leave it, this chat's "
                   "next check-in carries on as it is):")
        out += batches
    print("\n".join(out))
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
        # This chat's judgement on this one posting, held as one the person set aside (dated,
        # ending, under Held back for now, lifted there): written as a ruling by the rules, it
        # was judged again on every page build, and a stop on a degree, a place or pay was back
        # on Jobs at the next one (the engine review, 2026-11-11).
        item = ((db.get("work") or {}).get(page_db.safe_id(a.work)) or {}).get("data") or {}
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        if not args.get("url"):
            print("app: not finished: --left-out is for a job's draft, and this one names no "
                  "posting to take off Jobs", file=sys.stderr)
            return 2
        import exclude
        import person
        exclude.add(str(args["url"]), left, title=str(args.get("title") or ""),
                    company=str(args.get("company") or ""), basis="person", by=exclude.CHAT,
                    # The person's own day, never the computer's UTC date.
                    today=person.today(now).isoformat(),
                    path=person.state("job_scraper", "seen_jobs.json"))
        a.stopped, a.summary = True, a.summary or f"Not drafted: {left.rstrip('.')}."
    made, noted, links, problem = _made(a, db, reply)
    if problem:
        print(f"app: not finished: {problem}", file=sys.stderr)
        return 2
    try:
        got = page_db.finish(db, a.work, now, a.out or os.path.join(a.dump, "out"),
                             summary=a.summary, status="failed" if a.failed else
                             "stopped" if a.stopped else "done",
                             error=a.failed, links=links, reply=reply, thread=a.thread,
                             chat_kind=a.kind or app_listen.chat_kind(), dump_dir=a.dump,
                             chat=a.chat, question=a.question, about=a.about,
                             answer=_answer(a), answered=a.answered, left_out=left,
                             outcome=getattr(a, "outcome", "") or "",
                             signin=getattr(a, "signin", "") or "", go=made, me=_me(a.chat))
    except (KeyError, ValueError) as e:
        print(f"app: not finished: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
    if got.get("status") in ("done", "failed", "stopped") and not got.get("again"):
        import touched
        touched.clear(noted)
    kind = str((((db.get("work") or {}).get(page_db.safe_id(a.work)) or {}).get("data") or {})
               .get("kind") or "")
    if got.get("status") == "done" and (getattr(a, "outcome", "") or "") == "held":
        held = hold_on_record(db, a.work, a.summary, getattr(a, "until", "") or "", now)
        if held:
            got["held"] = held
    if got.get("again"):
        # This folder finished it already: the same batch, to send if it never was.
        got["said"] = ("this folder finished it already: here is that finish again; send it if "
                       "it was never sent (refused, it is the page's newer copy: python3 "
                       "tools/app.py version, as any refusal)")
    elif got["status"] == "done" and kind in page_db.FILES_AFTER:
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
    # Finished here: this chat holds it no more, so no read waits on its claim, and a sign-in
    # goes back to being asked in the chat (reading.app_job_here). A question is no finish: the
    # work waits on the person's page, and a sign-in this chat meets meanwhile goes there too.
    # Ended at the question, a chat on the computer that put the Sign in to LinkedIn card on
    # the page was told the next time to tell the person in its own chat (the maintainer,
    # 2026-11-11).
    try:
        import app_setup
        if got.get("status") == "needs_you":
            app_setup.ask_claim(a.work)
        else:
            app_setup.end_claim(a.work)
    except OSError:
        pass
    print(_dump(got), end="")
    return 0


HELD_KINDS = ("tweak", "reply", "follow_up", "nudge")


def hold_on_record(db: dict, work_id: str, summary: str, until: str, now) -> str:
    """A change or a reply Claude finished by holding the message to someone (`done --outcome
    held`) is put on their record, as their next action ("Hold until <day>: <why>", dated with
    --until), so every screen, the due lists and the brief hold it, never only the card's
    line: the card offered the draft as ready to send under "Finished: held until ..." (the
    maintainer, 2026-11-10). "" where the work names nobody; else the line it wrote."""
    import app_model
    import page_db
    from network import state
    item = ((db.get("work") or {}).get(page_db.safe_id(work_id)) or {}).get("data") or {}
    if str(item.get("kind") or "") not in HELD_KINDS:
        return ""
    args = item.get("args") if isinstance(item.get("args"), dict) else {}
    target = args.get("target") if isinstance(args.get("target"), dict) else {}
    cid = str(target.get("contact") or args.get("contact") or "").strip()
    if not cid and str(target.get("id") or "").startswith("msg-"):
        cid = str(target["id"])[4:]
    if not cid:
        return ""
    why = app_model._HOLD_LEAD.sub("", " ".join(str(summary or "").split()), count=1)
    why = why.strip().rstrip(" .;")
    if until:
        why = re.split(r"\s*;\s*", why)[0].rstrip(" .;")
    # In words the contact's Next line reads well in, and state.hold_lifts ends on the day:
    # "Hold until Kestrel Mutual posts a role, or until 2026-11-23".
    if why.lower().startswith("until ") and until:
        action = f"Hold {why}, or until {until}"
    else:
        action = (f"Hold until {until}" if until else "Hold") + (f": {why}" if why else "")
    # With the day it was made: what they write after it is owed an answer, hold or no hold.
    contacts = state.load_contacts()
    threads = state.load_threads() if os.path.exists(state.THREADS_CSV) else []
    action = state.hold_since(action, person.today(now),
                              [r for r in threads if str(r.get("contact_id") or "").strip() == cid])
    before = state.already_contacted(contacts, contact_id=cid) or {}
    was = {"status": before.get("status") or "", "next_action": before.get("next_action") or ""}
    try:
        state.set_contact(contacts, threads, cid, next_action=action, due=until or None,
                          today=person.today(now).isoformat())
    except ValueError:
        return ""
    state.save_contacts(contacts)
    aside = ""
    if state.role_hold(action) and state.park_draft(cid, was=was):
        # Waiting for a role: the draft written before there is one is set aside, kept, and
        # the message is written for that role once it is posted (state.role_hold).
        aside = "; the draft written before the role is set aside (kept)"
    return f"held on their record: {cid}: {action}{aside}"


def _made(a, db: dict, reply: str = "") -> tuple[list, list, list, str]:
    """What a finishing work item changed on the page, as its answer's buttons
    (tools/touched.py): what the commands it ran noted, each --touched, each --link to a place
    on the page, and a search's own jobs. (buttons, the noted rows to clear once it is
    finished, the other links, why the answer may not go as written or "")."""
    import page_db
    import touched
    item = ((db.get("work") or {}).get(page_db.safe_id(a.work)) or {}).get("data") or {}
    try:
        found, noted = touched.gather(a.work, item, a.chat)
    except Exception:  # noqa: BLE001  a record it cannot read is a button fewer, never a stop
        found, noted = [], []
    places, links = touched.page_links(_links(a.link))
    try:
        given = [touched.from_arg(x) for x in getattr(a, "touched", None) or ()]
    except ValueError as e:
        return [], noted, links, str(e)
    found = found + places + given
    kind = str(item.get("kind") or "")
    args = item.get("args") if isinstance(item.get("args"), dict) else {}
    if kind == "prep" and args.get("interview"):
        found.append(("interviews", str(args["interview"])))
    if kind == "search" and not a.failed and not a.stopped:
        run = page_db.search_run(a.work)
        if not run:
            try:
                import app_model
                newest = app_model.newest_round()
                run = os.path.splitext(os.path.basename(newest))[0] if newest else ""
            except Exception:  # noqa: BLE001  no profile here: no jobs to point at
                run = ""
        if run:
            found.append(("jobs", "round:" + run))
    made = touched.buttons(found) if not (a.failed or a.stopped or a.question) else []
    problem = touched.pasted(reply, made, getattr(a, "in_thread", False))
    return made, noted, links, problem


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
# The person's own rules stop it (where they live, their limit, an employer turned down):
# said once, with the reason, on the finished item (a person's copy, 2026-11-05).
FOLLOW_UP_HELD = "No follow-up for {first}: {why}."


def _held_why(why: str) -> str:
    why = " ".join(str(why or "").split()).rstrip(".")
    for lead in ("Nothing to send: ", "held: "):
        if why.startswith(lead):
            why = why[len(lead):]
    first, _, rest = why.partition(" ")
    return (first.lower() + " " + rest).strip() if first in ("No", "Your", "Their") else why
FOLLOW_UP_ASK = "What should the follow-up to {first} say? I could not write one: {why}."
# Never asked of the person any more (2026-11-06): what code cannot write is Claude's, a note
# waiting on a read is rewritten once it is read, and with nothing new found under a rule to
# follow up only with something new, the item says so and asks nothing.
FOLLOW_UP_WAITS = "The note to {first} waits until their profile is read."
FOLLOW_UP_NOTHING = "No follow-up to {first} yet: nothing new turned up to say."
# They offered to refer the person once there is a role, and none is posted: on hold until one
# is, with nothing drafted, never one follow-up for everyone who offered (2026-11-10).
FOLLOW_UP_ROLE = ("{first} is on hold until a role is posted at their employer: the referral "
                  "ask is written then, for that role.")
# What a finish says when its own words are refused (a name it could not shorten): the batch's
# other items keep their writes.
FOLLOW_UP_PLAIN = {"done": "Your follow-up is ready to send.", "none": "No follow-up is owed now.",
                   "held": "No follow-up: your own rules stop it.",
                   "waits": "The note waits until their profile is read.",
                   "nothing": "No follow-up yet: nothing new turned up to say.",
                   "role": "On hold until a role is posted at their employer."}


def _next_dir(base: str) -> str:
    n = 1
    while os.path.exists(os.path.join(base, str(n))):
        n += 1
    return os.path.join(base, str(n))


def _take_back_asks(db: dict, chat: str, now, dump: str) -> dict:
    """Every follow-up an earlier run put to the person with FOLLOW_UP_ASK, taken back by
    `chat`: {work id: (the fields that claim it again, its version)}. The dump holds it as
    claimed at the version it has, so the run's one write to it (its finish, or the claim
    itself when it is left to write) goes at that version."""
    import app_model
    import page_db
    lead = FOLLOW_UP_ASK.split("{first}")[0]
    got = {}
    at = app_model.stamp(now)
    until = app_model.stamp(now + dt.timedelta(minutes=30))
    for wid, doc in sorted((db.get("work") or {}).items()):
        item = doc["data"]
        if item.get("kind") != "follow_up" or str(item.get("status") or "") != "needs_you":
            continue
        if not str(item.get("note") or "").startswith(lead):
            continue
        # Claimed again by this chat, as every claim is made (page_db.taken).
        fields = page_db.taken(item, chat, "cloud", at, until)
        page_db._keep_dump(dump, "work", wid, page_db.applied(item, fields), int(doc["version"] or 1))
        got[wid] = (fields, doc["version"])
    return got


def _cleared(entries: list, wid: str) -> None:
    """The finish of a follow-up taken back from the person also clears its question."""
    import page_db
    for e in entries:
        if e.get("collection") == "work" and e.get("doc_id") == wid and e.get("file_path"):
            with open(e["file_path"], encoding="utf-8") as fh:
                data = json.load(fh)
            data.update({k: None for k in page_db.ASKED})
            with open(e["file_path"], "w", encoding="utf-8", newline="\n") as fh:
                json.dump(data, fh)


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
    out = {"done": [], "to_write": [], "asked": [], "by_hand": [], "refused": [],
           "context": "", "batches": [], "taken_back": [], "not_finished": []}
    # Its own questions taken back: a follow-up an earlier run put to the person ("What should
    # the follow-up to ... say?") is this command's to answer, so it is claimed again here and
    # drafted with the rest. Only the page could answer one before (2026-11-06).
    entries: list[dict] = []
    taken = _take_back_asks(db, chat, now, dump)
    if taken:
        out["taken_back"] = sorted(taken)
        db = page_db.load(dump)
    held = sorted(((str(d["data"].get("asked_at") or ""), wid) for wid, d in
                   (db.get("work") or {}).items()
                   if d["data"].get("kind") == "follow_up"
                   and str(d["data"].get("status") or "") in page_db.ACTIVE
                   and str(d["data"].get("claimed_by") or "") == chat))
    if not held:
        if entries:
            w = page_db.Writes(out_dir)
            w.entries = entries
            out["batches"] = w.save("follow-ups")
        return out
    with followup_drafts.FoldersOnce():
        items, contacts, threads, tracker = followup_drafts.load(today)
        got = followup_drafts.drafts(items, contacts, threads, tracker, today)
        by_contact = {str(i.get("contact_id") or ""): i for i in got if i.get("half") == "contact"}
        names = {str(c.get("contact_id") or "").strip(): str(c.get("name") or "")
                 for c in contacts}
        passed: dict = {}
        stopped: dict = {}
        # {"id", "none": "<why>"}: Claude looked and found nothing new, under a rule to follow
        # up only with something new: finished saying so, nobody asked.
        nothing = {str(e.get("id") or "").strip() for e in written or ()
                   if isinstance(e, dict) and e.get("none") and not str(e.get("text") or "").strip()}
        written = [e for e in written or () if str((e or {}).get("id") or "").strip() not in nothing]
        if written:
            checked = followup_drafts.check(written, contacts, threads, today, got)
            followup_drafts.keep_checked(checked, contacts)
            passed = {c["id"]: c for c in checked if c["ok"]}
            out["refused"] = [{"id": c["id"], "findings": c["findings"]}
                              for c in checked if not c["ok"] and not c.get("held")]
            stopped.update({c["id"]: c["held"] for c in checked if c.get("held")})
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
            rule = (due or {}).get("rule") or {}
            stop = stopped.get(cid) or (rule.get("said") or "" if (due or {}).get("held") else "")
            if stop and cid not in passed:
                finishes.append({"work": wid, "plain": "held", "summary": FOLLOW_UP_HELD.format(
                    first=first, why=_held_why(stop))})
            elif cid in passed:
                finishes.append({"work": wid, "plain": "done", "summary": FOLLOW_UP_DONE.format(first=first)})
            elif cid in nothing:
                finishes.append({"work": wid, "plain": "nothing",
                                 "summary": FOLLOW_UP_NOTHING.format(first=first)})
            elif d.get("hold_role"):
                # They offered to refer the person and no role is posted: nothing is written,
                # and they go on hold on their record until one is (keep_drafted).
                keep.append(due)
                finishes.append({"work": wid, "plain": "role",
                                 "summary": FOLLOW_UP_ROLE.format(first=first)})
            elif due is None or d.get("status") == "none":
                finishes.append({"work": wid, "plain": "none", "summary": FOLLOW_UP_NONE.format(first=first)})
            elif d.get("status") == "ready" and not answered:
                keep.append(due)
                finishes.append({"work": wid, "plain": "done", "summary": FOLLOW_UP_DONE.format(first=first)})
            elif d.get("status") == "write" and d.get("who") == "read" and not answered:
                finishes.append({"work": wid, "plain": "waits",
                                 "summary": FOLLOW_UP_WAITS.format(first=first)})
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
    for f in finishes:
        each = os.path.join(out_dir, "each", f["work"].replace("~", "@"))
        try:
            res = page_db.finish(page_db.load(dump), f["work"], now, each,
                                 summary=f.get("summary", ""), chat=chat, dump_dir=dump,
                                 question=f.get("question", ""),
                                 answer={"kind": "text"} if f.get("question") else None)
        except ValueError:
            # Its own words refused (a name with a full stop read as two sentences): said
            # plainly instead, and the batch's other items keep their writes (2026-11-06).
            try:
                res = page_db.finish(page_db.load(dump), f["work"], now, each,
                                     summary=FOLLOW_UP_PLAIN.get(f.get("plain") or "", "Done."),
                                     chat=chat, dump_dir=dump)
            except (ValueError, KeyError):
                out["not_finished"].append(f["work"])
                continue
        except KeyError:
            out["not_finished"].append(f["work"])
            continue
        mine = []
        for path in res["batches"]:
            with open(path, encoding="utf-8") as fh:
                mine += json.load(fh)
        if f["work"] in taken:
            _cleared(mine, f["work"])
        entries += mine
        out["asked" if f.get("question") else "done"].append(f["work"])
    # One taken back and left to write here: its claim is written, so the page shows it being
    # drafted rather than waiting on the person.
    finished = set(out["done"]) | set(out["asked"])
    if any(wid not in finished for wid in taken):
        w0 = page_db.Writes(os.path.join(out_dir, "taken"))
        for wid, (fields, version) in sorted(taken.items()):
            if wid not in finished:
                w0.add("update", "work", wid, fields, if_version=version)
        entries = list(w0.entries) + entries
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
    # Work a chat starts is where its answer points: "Running in Claude's work", opening it.
    import touched
    touched.note("work", str(got.get("work") or ""), chat=a.chat)
    print(_dump(got), end="")
    return 0


def cmd_versions(a) -> int:
    """The versions a read listed, kept in the files it saved (page_db.keep_listed): the
    lines on the input, as the read printed them or typed short."""
    import page_db
    text = sys.stdin.read() if not a.lines else "\n".join(a.lines)
    n = page_db.keep_listed(text, a.dump)
    if not n:
        # Asked, and nothing named a version: the folder is marked all the same, so `wake`
        # goes on pinned to the records' own stamps rather than asking again for good.
        page_db.mark_listed(a.dump)
        print("app: no record of this folder was named with its version: give the lines the "
              "read printed (`- \"<id>\"  N bytes  version V  \"<file>\"`), or "
              "`<collection>/<doc id> V` a line", file=sys.stderr)
        return 2
    print(f"versions: {n} record{'s' if n != 1 else ''} in this folder now carry the page's own "
          "version: every write made from it is pinned to that.")
    return 0


def cmd_version(a) -> int:
    """A refused write named a record's current version: kept in the folder, so the same
    command run again pins to it (once; a second refusal means read again)."""
    import page_db
    import page_reads
    # Every other record the refused save pins by its stamp alone is read again first, so the
    # save made again lands at once: one refusal for each, fifty of them for one page update,
    # was a version typed by hand fifty times (a person's computer, 2026-11-09).
    again = page_db.read_again(a.dump, a.record, missing=a.version is None)
    try:
        kept = page_db.take_back(a.dump, a.record) if a.version is None else \
            page_db.note_version(a.dump, a.record, a.version)
    except (KeyError, ValueError) as e:
        print(f"app: {e.args[0] if e.args else e}", file=sys.stderr)
        return 2
    try:
        page_reads.want_full()
    except Exception:  # noqa: BLE001  nothing kept to read wholly
        pass
    if page_db.refusals(a.dump, kept) > 1:
        # The page changed it again while this was saved: never dropped, never a loop.
        print(VERSION_AGAIN.format(record=kept, dump=a.dump))
        return 3
    first = ""
    if again:
        import app_setup
        url = app_setup.page_record().get("url") or "<the page>"
        first = (f" First read {', '.join(again)} again into this folder (ArtifactData query, "
                 f"url {url}, one for each, limit 1000, out_dir \"{a.dump}\"; never list or open "
                 f"what they save), {page_reads.keep_step(a.dump)}so every record it saves "
                 "again is pinned to the page's own number. Then")
    where = (f"at version {a.version} in this folder" if a.version is not None
             else "on the page already, so it is read again first")
    print(f"app: {kept} is {where}, and what the refused batch would have saved is back in it "
          f"to be saved again:{first} run the refused command again, once, and send what it "
          "prints")
    return 0


VERSION_AGAIN = ("app: the page refused this save of {record} again: it changed again while it "
                 "was being saved. Nothing is lost: the save is still waiting in \"{dump}\". "
                 "Read the page again into a new folder (a whole read, which this asked for) and "
                 "run the same command there: it makes the save again from that read. Tell the "
                 "person only if it is refused there too, in these words: \"Something on your "
                 "page kept changing while I saved it. Your work is safe here and goes on your "
                 "page with the next update.\"")


def cmd_reads(a) -> int:
    """What a wake reads: the queries, one line each (page_reads)."""
    import app_model
    import app_setup
    import page_reads
    _, now = app_model.clock(None, a.now)
    within = getattr(a, "within", "") or ""
    if not a.dump and not within:
        # The listener's own look at a ring that names the page's revision: no read at all.
        if a.rev is None:
            print("app: give a folder to read into (--in <your scratchpad>), or --rev <the "
                  "ring's revision>", file=sys.stderr)
            return 2
        print(page_reads.say_plan({"nothing": True}, "", "") if page_reads.seen_rev(a.rev)
              else "reads: new since the last read: pass the ring on (the app skill, step 0).")
        return 0
    if within and not a.dump:
        # The folder is the code's to choose, a fresh short name each read: told to name it
        # short, every fresh subagent chose `w1` (the review of 2026-11-11, E-18).
        made = page_reads.fresh(within)
        got = page_reads.plan(made, now, full=a.full, rev=a.rev)
        if got.get("nothing"):
            try:
                os.rmdir(made)
            except OSError:
                pass
        else:
            got["chosen"] = True
    else:
        got = page_reads.plan(a.dump, now, full=a.full, rev=a.rev)
    url = app_setup.page_record().get("url") or "<the page>"
    print(page_reads.say_plan(got, a.dump, url,
                              then=page_reads.FOR_VIEW if getattr(a, "for_view", False) else ""))
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
    p.add_argument("--computer-only", dest="computer_only", action="store_true",
                   help="this chat was started on the computer for its work: take only work "
                        "sent to the computer, and do it here")
    p.add_argument("--lent", action="store_true",
                   help="a cloud chat lent the computer's browser or folder: its claim is a "
                        "computer chat's, but it is not a chat listening on the computer")
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
    p = sub.add_parser("job", help="a big job's own steps, for the chat started for it")
    p.add_argument("--work", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--chat", required=True, help="the chat that claimed it")
    p.add_argument("--with", dest="mates", action="append", default=[],
                   help="an item claimed with it; once for each")
    p.add_argument("--draft-all", dest="draft_all", type=int, default=0,
                   help="a search that drafts what it finds: how many at most")
    p.add_argument("--agent", action="store_true", help="it runs as a background agent")
    p.add_argument("--url", default="")
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
    p.add_argument("--first", action="store_true",
                   help="a job's first command over its folder: its read's versions kept, and "
                        "the folder its own, before anything is written")
    p.add_argument("--blocked", action="store_true",
                   help="its own chat waits on the person (get_session says blocked)")
    p.add_argument("--alive", action="store_true",
                   help="its own chat is still at work (get_session says working)")
    p = sub.add_parser("resume", help="work taken into this chat because the person said so "
                                      "here: their answer to its question, or do it now")
    p.add_argument("dump")
    p.add_argument("--work", required=True, help="the work item's id")
    p.add_argument("--chat", required=True, help="this chat's id")
    p.add_argument("--answer", default="",
                   help="what they answered its question with, in their words (\"logged in\")")
    p.add_argument("--kind", default="", help="computer, in a chat on the computer")
    p.add_argument("--out", default="", help="where the batch goes (default <dump>/out)")
    p.add_argument("--now", default=None)
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
    p.add_argument("--paste", action="store_true",
                   help="print the line a person pastes into a chat on their computer")
    p.add_argument("--scheduled", default="", help="a scheduled run's task (morning_brief): "
                                                   "its own start, nothing of a person's chat")
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
    p.add_argument("--lineage", default="", help="get_session's lineage for this chat "
                                                 "(<depth>/<limit>): at its limit, nested now")
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
    p = sub.add_parser("nested", help="this chat was refused a new chat or scheduled task "
                                      "because chats nest only so deep: keep it, and tell the "
                                      "brief's run to start the fresh helper")
    p.add_argument("dump", nargs="?", default="", help="a read of the page, for its record")
    p.add_argument("--chat", default="")
    p.add_argument("--out", default="", help="where the batch goes (default <dump>/nested)")
    p.add_argument("--now", default=None)
    p = sub.add_parser("retired", help="a helper that handed the page on: its one step, its "
                                       "save, then archiving itself")
    p.add_argument("--chat", default="")
    p.add_argument("--wait", action="store_true", help="wait for its save to end, then say so")
    p = sub.add_parser("hand-over", help="the person asked for a fresh helper now: the whole "
                                         "hand-over, in order")
    p.add_argument("--chat", default="")
    p.add_argument("--dump", default="", help="a read of the page's work, for the short note")
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
                   help="the answer for the person, shown in the conversation (on the card "
                        "itself for work with none, a change to a draft); - reads it from the "
                        "input")
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
    p.add_argument("--signin", default="", choices=("", "linkedin"),
                   help="with --question: it waits on a sign-in the page itself makes in the "
                        "Claude app, and sends the work back once it sees it")
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
                   help="\"<label>=<address>\" shown with it (more than one allowed); a place "
                        "on the page (page:contacts/<id>) is one of its buttons")
    p.add_argument("--touched", action="append", default=[],
                   help="\"<place>:<id>\" it changed that no command noted (contacts, jobs, "
                        "drafts, interviews, you, work): a button under its answer opens it")
    p.add_argument("--in-thread", dest="in_thread", action="store_true",
                   help="they asked to see it here: the answer may paste what its card holds")
    p.add_argument("--chat", default="", help=CLAIMED_UNDER)
    p.add_argument("--kind", default="", choices=("", "cloud", "computer"))
    p.add_argument("--answered", action="append", default=[],
                   help="a form's question answered (form_answers), in the form's own words: "
                        "its card says Done once each is on it (more than one allowed)")
    p.add_argument("--out", default="", help="where the batch goes (default <dump>/out)")
    p.add_argument("--outcome", default="", choices=("", "held", "set_aside", "unchanged"),
                   help="it finished and changed nothing on the page: held, set aside, or "
                        "unchanged (not possible, or already as asked); its card says so at "
                        "once, with the summary")
    p.add_argument("--until", default="",
                   help="with --outcome held, on a message to someone: the day Claude looks "
                        "again (YYYY-MM-DD); the hold goes on their record with it")
    p.add_argument("--left-out", dest="left_out", default="",
                   help="a draft stopped because the job is not one they can take: why, in "
                        "plain words; the job leaves Jobs, set aside with that reason as one "
                        "they set aside is, and shown under Held back for now")
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
    p.add_argument("--in", dest="within", default="",
                   help="make this read's own folder in this one (the next free w<n>) and name "
                        "it, in place of giving one")
    p.add_argument("--full", action="store_true", help="read every collection whole")
    p.add_argument("--for-view", dest="for_view", action="store_true",
                   help="for a step that brings the page up to date (app.py view), not a wake")
    p.add_argument("--rev", type=int, default=None,
                   help="the revision the page's ring named, when it names one")
    p.add_argument("--now", default=None)
    p = sub.add_parser("version", help="a refused write named a record's version: keep it "
                                       "in the folder, then run the command again")
    p.add_argument("dump")
    p.add_argument("record", help="<collection>/<doc id>, as the refusal named it")
    p.add_argument("version", type=int, nargs="?", default=None,
                   help="the version it named; none when it said the record exists and the "
                        "write carried no version")
    p = sub.add_parser("versions", help="the versions a read listed, kept in the files it saved")
    p.add_argument("dump")
    p.add_argument("lines", nargs="*", help="`<collection>/<doc id> V` (default: the input)")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2
    a.argv = list(sys.argv[1:] if argv is None else argv)
    # Every command runs before there is a profile too: setup itself is on the page.
    return {"model": cmd_model, "view": cmd_view, "page": cmd_page, "apply": cmd_apply,
            "next": cmd_next, "job": cmd_job, "pin": cmd_pin, "resume": cmd_resume,
            "busy": cmd_busy,
            "progress": cmd_progress, "check": cmd_check,
            "start": cmd_start, "published": cmd_published, "resume-saved": cmd_resume_saved,
            "files-saved": cmd_files_saved, "propose": cmd_propose, "listen": cmd_listen,
            "republish": cmd_republish, "pinned": cmd_pinned, "told": cmd_told, "doorbells": cmd_doorbells, "done": cmd_done,
            "ask": cmd_ask, "wake": cmd_wake, "version": cmd_version, "versions": cmd_versions,
            "reads": cmd_reads, "search-drafts": cmd_search_drafts,
            "follow-ups": cmd_follow_ups, "nested": cmd_nested, "retired": cmd_retired, "hand-over": cmd_hand_over,
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
