#!/usr/bin/env python3
"""The app's page and its chats: one command for each thing a chat does with the page.

    python3 tools/app.py model [--out F] [--today D] [--now T]   the view model, as JSON
    python3 tools/app.py view <out dir> [--dump DIR]             the model as view/* writes
    python3 tools/app.py page [--out F]                          the whole page, to publish
    python3 tools/app.py apply <dump dir> [--chat ID] [--claim]  the page's actions, applied
    python3 tools/app.py next <dump dir> --chat ID --kind cloud|computer [--claim-out DIR]
                                                                 [--no-sessions]: where it runs
    python3 tools/app.py pin <dump dir> --work ID --stage S [--line L] [--done N --total M]
                                         [--left-s S] [--log round.log]   progress, as it goes
    python3 tools/app.py busy <dump dir> "<a few words>" | --done
                                                                 what this chat does in the chat
    python3 tools/app.py progress <kind of work>                 its stages and their seconds
    python3 tools/app.py check [--model F]                       the model against the contract
    python3 tools/app.py start [--on M] [--tools T] [--page URL] [--chat ID] [--listen]
                               [--work ID]                       what this chat does next, in any
                                                                 state: set up, part-way, old, new
    python3 tools/app.py start --paste                           the line for a chat on a computer
    python3 tools/app.py published <url>|none [--chat ID]        the page's address, once published
    python3 tools/app.py listen <dump dir> --chat ID [--listen] [--helper] [--hand ID]
                                                                 is this chat the page's listener?
    python3 tools/app.py republish <out dir>                     the page's own code changed: ask
                                                                 the listener to publish it
    python3 tools/app.py pinned yes|no                           their answer to pinning the page
    python3 tools/app.py resume-saved <file> [--asset ID]        the resume from the page, saved
    python3 tools/app.py files-saved <path> <asset id> [...]     a document put in the page's file store
    python3 tools/app.py propose "<role>"...                     the roles setup asks about

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
import json
import os
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


def cmd_view(a) -> int:
    """The model as one document a section (`view/<section>`, in parts when it is too big for
    one: page_db.split) plus `meta/current` (stored as `meta/now`), so an open page updates live with no republish.
    Sets on documents that exist are pinned to the versions in `--dump`."""
    import app_model
    import page_db
    import app_alerts
    today, now = app_model.clock(a.today, a.now)
    db = page_db.load(a.dump) if a.dump else {}
    # The suggestions already on the page keep their day, so no more than three new ones
    # reach it a day.
    full: dict = {}
    model, _ = _build(today, now, shown=app_alerts.shown_in(db.get("view") or {}), full=full)
    w = page_db.Writes(a.out_dir)
    # Each whole list, in parts under 256 KiB, for the page's "Show" (tools/app_lists.py).
    import app_lists
    for doc_id, doc in app_lists.docs(full, model["made_at"], model["rev"]):
        old = (db.get("view") or {}).get(doc_id) if db else None
        w.add("set", "view", doc_id, doc, if_version=old["version"] if old else None)
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
        for doc_id, doc in page_db.split(name, {"rev": model["rev"], "made_at": model["made_at"],
                                                "data": model[name]}):
            old = (db.get("view") or {}).get(doc_id) if db else None
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
        reach = app_model.reach_docs(app_model.Ctx(today, now).contacts, ids)
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
    old = (db.get("meta") or {}).get("current") if db else None
    w.add("set", "meta", "current", {"rev": model["rev"], "made_at": model["made_at"],
                                     "model": model["model"], "by": a.chat},
          if_version=old["version"] if old else None)
    print(_dump({"rev": model["rev"], "batches": w.save("view")}), end="")
    return 0


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


def cmd_next(a) -> int:
    """The queued work this chat should take, with the model a chat started for it gets
    (tools/model_guide.py for_work), and `run`: where it is done (where_it_runs). A big job
    is never `here`. A republish goes to the page's listener alone, and first: the page's
    own code changed under every open window."""
    import app_listen
    import app_model
    import model_guide
    import page_db
    _, now = app_model.clock(None, a.now)
    db = page_db.load(a.dump)
    chosen = app_listen.next_republish(db, a.chat, now)
    if chosen is None:
        chosen = page_db.next_item(app_listen.without_republish(db), a.kind, now)
    if chosen is None:
        return 0
    info = model_guide.for_work(chosen["kind"], a.on)
    heavy = bool(page_db.WORK_KINDS.get(chosen["kind"], {}).get("heavy"))
    chosen.update(model=info["model"], effort=info["effort"], heavy=heavy)
    chosen.update(where_it_runs(chosen, a.chat, a.kind, a.no_sessions))
    if a.claim_out:
        chosen["batches"] = page_db.claim(db, chosen, a.chat, a.kind, now, a.claim_out)
    print(_dump(chosen), end="")
    return 0


# A big job (page_db.WORK_KINDS "heavy": a search, drafts, a resume for a contact, an
# interview prep, a networking run) never runs in the chat that answers the page. Run there,
# even as background agents, a search and a networking run held it for 15 and 23 minutes and
# the page waited on every tap (2026-10-29). Each gets a cloud chat of its own instead.
CHILD_TITLE = "Job search: {title}"


def child_prompt(chosen: dict, parent: str, url: str, session: bool = True) -> str:
    """What a chat (or, where none can be started, a background agent) is told for one big
    job: run that item, pin its progress, finish it, land it, and say it is finished. It
    never publishes, watches or answers the page."""
    wid, kind = chosen["work"], chosen["kind"]
    keys = ", ".join(s["key"] for s in chosen.get("stages") or [] if s.get("key"))
    where = "in a chat of its own" if session else "as a background agent"
    tell = (f"send_message to {parent}: " if session else "end with one line: ")
    lines = [
        f"Do one piece of work for this person's job search page, {where}, so the chat that "
        f"answers the page stays free. The work: \"{chosen.get('title') or kind}\" (work item "
        f"{wid}, a {kind}), already claimed for you. The page: {url}. The chat that answers "
        f"it: {parent}.",
        f"1. python3 tools/app.py start --on \"<your model>\" --tools none --work {wid}, and do "
        "what it prints. Never publish, watch or answer the page, and never write its view.",
        "2. Load ArtifactData (ToolSearch, select:ArtifactData). Read the page's database "
        f"into a fresh folder in your scratchpad, $D: ArtifactData query, url {url}, "
        "collection work, then holds, each with out_dir $D.",
        f"3. Do it as .claude/skills/app/SKILL.md says for a {kind}: step 4 (its row, and "
        "\"Progress costs nothing extra\") and step 5. Read only those parts.",
        f"4. At each stage ({keys}): python3 tools/app.py pin \"$D\" --work {wid} --stage "
        "<stage> --line \"<one plain line>\", and send the batch it prints (ArtifactData "
        f"batch, url {url}). On a long stage, pin it again with a new line every ten minutes "
        "or so: the page counts a job with no word for half an hour as stopped. "
        "\"stop_asked\": true means they tapped Stop: finish it stopped. A refused pin: read "
        "work again and pin once more; claimed by another chat, write nothing else and stop.",
    ]
    if kind == "search":
        lines.append(
            f"{len(lines)}. Run run_round.py in the background (Bash, run_in_background). "
            f"While it runs, every five minutes or so: python3 tools/app.py pin \"$D\" --work "
            f"{wid} --stage scrape --log <the round's folder>/round.log, and send its batch, "
            "so the page shows how many job sites are done and how long is left.")
    if session:
        lines.append(
            f"{len(lines)}. No ArtifactData in this chat: instead of each batch, send_message "
            f"to {parent}: \"Progress {wid}: <stage> | <one plain line>\", and at the end "
            f"\"Finished {wid}: <what was made, in a line>\". It writes them to the page.")
    lines.append(
        f"{len(lines)}. Finish as step 5 says, without its heartbeat line and without app.py "
        f"view. Save and land your work on master (CLAUDE.md, \"Saving\"). Then {tell}"
        f"\"Finished {wid}, on master: bring the page up to date.\" Never write to the "
        "person: the page shows how it went.")
    return "\n".join(lines)


def where_it_runs(chosen: dict, chat: str, kind: str, no_sessions: bool = False) -> dict:
    """`run`: `here` for light work; for a big job, `child session` with the create_session
    call to make (its prompt runs the item and pins its progress), or, where a chat cannot
    start one (a chat on a computer, or no create_session tool), `background agent` with
    the Agent call. A big job is never `here`."""
    if not chosen.get("heavy"):
        return {"run": "here"}
    import app_setup
    url = app_setup.page_record().get("url", "") or "<url>"
    parent = chat or "<your chat id>"
    owner, name = app_setup.origin()
    title = CHILD_TITLE.format(title=" ".join(str(chosen.get("title") or chosen["kind"])
                                              .split())[:60])
    if kind == "cloud" and not no_sessions and owner and name:
        call = {"title": title, "prompt": child_prompt(chosen, parent, url),
                "source_url": f"https://github.com/{owner}/{name}"}
        if chosen.get("model"):
            call["model"] = chosen["model"]
        return {"run": "child session", "create_session": call}
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
    try:
        got = page_db.pin(db, a.work, now, a.out or os.path.join(a.dump, "out"),
                          stage=stage, line=a.line, count=count, left_s=left, dump_dir=a.dump)
    except KeyError as e:
        print(f"app: {e.args[0]}", file=sys.stderr)
        return 2
    print(_dump(got), end="")
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
    code, lines = app_setup.start(on=a.on or "", tools=a.tools or "", page_url=a.page or "")
    lines = app_listen.shape(code, lines, chat=app_listen.this_chat(a.chat), listen=a.listen,
                             helper=a.helper, on=a.on or "", work=a.work or "")
    print("\n".join(lines))
    return code


def cmd_published(a) -> int:
    import app_listen
    import app_model
    import app_setup
    if a.url == "none":
        app_setup.record_no_page()
        print("app: noted: this chat has no pages, so setup and the updates stay in the chat; "
              "the sync stops asking for a month")
        return 0
    first = not app_setup.page_record().get("url")
    chat = app_listen.this_chat(a.chat)
    try:
        path = app_setup.record_page(a.url, chat=chat)
    except ValueError as e:
        print(f"app: {e}")
        return 2
    import local_path
    print(f"app: the page's address is kept in {local_path.rel(path, person.ROOT)}; save it "
          "with the rest (python3 tools/save_state.py)")
    _, now = app_model.clock(None, None)
    import tempfile
    out = a.out or tempfile.mkdtemp(prefix="ljs-listen-")      # never inside the profile
    for line in app_listen.published_lines(a.url, chat, first, out, now):
        print(line)
    if a.dump:
        import page_db
        got = app_listen.close_republish(page_db.load(a.dump), out, now)
        if got["batches"]:
            print("app: the page no longer shows this update as waiting: send this batch "
                  f"(ArtifactData batch, url {a.url}): " + " ".join(got["batches"]))
    return 0


def cmd_listen(a) -> int:
    import app_listen
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    out = a.out or os.path.join(a.dump, "listen_out")
    db = page_db.load(a.dump)
    # A page a 4.2 chat left keeps its records under the old names: they move to the new
    # ones once, in code, before anything is written to them (2026-10-29).
    more = page_db.to_read(a.dump, db)
    if more:
        print("listen: this page was made by an older version of the app, and its records "
              "move to their new names once, now. ArtifactData query, once for each of the "
              f"collections {', '.join(more)} (url <the page>, out_dir the same folder, limit "
              "1000), then run this again with the same folder. Say nothing about it to the "
              "person.")
        return 0
    move = page_db.move(db, a.dump, os.path.join(out, "move"),
                        app_listen._stamp(now), app_listen.this_chat(a.chat))
    if move["batches"]:
        page_db.moved_into(a.dump, move)
    got = app_listen.decide(move["db"], app_listen.this_chat(a.chat), out, now,
                            listen=a.listen, helper=a.helper, hand_to=a.hand,
                            update=a.update)
    if move["batches"]:
        print("listen: the page's records take their new names: send these batches first, in "
              "order, asking nobody. If one is refused, another chat did it already: read "
              "again into a new folder and run this once more.")
        for path in move["batches"]:
            print(path)
    for line in got["lines"]:
        print(line)
    for path in got["batches"]:
        print(path)
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
            print(f"upkeep: {len(closed)} application(s) gone quiet were closed as no reply "
                  "(followups.py --close-quiet); save them with the rest, after this wake's "
                  "work (python3 tools/save_state.py)")
        # An interview's time said in a note or a message goes on the interview's own
        # record, so the page shows it and nobody is asked to add it (2026-10-29).
        try:
            import interview_pack
            zone = person.home_zone_named(person.directory()) or "UTC"
            timed = interview_pack.take_times(today=app_model.local_day(now, zone).isoformat())
        except Exception:  # noqa: BLE001  no profile or no interview yet: nothing to take
            timed = []
        if timed:
            print(f"upkeep: {len(timed)} interview time(s) said in a note or a message were "
                  "saved on the interview; save them with the rest and bring the page up to "
                  "date (python3 tools/app.py view), asking nobody")
        # The page's store kept small, in code: finished records over two months old go.
        old = page_db.prune(page_db.load(a.dump), now, os.path.join(a.out or os.path.join(a.dump, "listen_out"), "prune"))
        if old:
            print("upkeep: old finished records the page no longer shows are deleted: send "
                  "these batches after this wake's work, asking nobody:")
            for path in old:
                print(path)
    if got["role"] == "listener" and app_listen.chat_kind() == "cloud":
        import tidy
        if tidy.due():
            print("tidy: once today, after this wake's work and asking nobody: the app's own "
                  "old chats (tools/tidy.py). list_sessions (mine: true) and list_triggers, every "
                  "page, each saved to a file in the scratchpad; python3 tools/tidy.py plan "
                  "--dump \"$D\" --sessions <each> --triggers <each>; do what it prints.")
    return 0


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
    p = clocked(sub.add_parser("page", help="the whole page as one HTML file"))
    p.add_argument("--out")
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
    p.add_argument("--work", required=True, help="the work item's id")
    p.add_argument("--stage", default=None, help="the stage's key or number")
    p.add_argument("--line", default="", help="one plain line of what happened")
    p.add_argument("--done", type=int, default=0)
    p.add_argument("--total", type=int, default=0)
    p.add_argument("--left-s", dest="left_s", type=int, default=None,
                   help="seconds left in this stage, when the work itself says")
    p.add_argument("--log", default="", help="a search's round.log: the count and time left")
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
    p = sub.add_parser("published", help="keep the page's address once it is published")
    p.add_argument("url")
    p.add_argument("--chat", default="")
    p.add_argument("--out", default="", help="where the listener's batch goes")
    p.add_argument("--dump", default="", help="the page's waiting republish requests, read")
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
    p = sub.add_parser("republish", help="ask the listener to publish the page's new code")
    p.add_argument("out_dir")
    p.add_argument("--now", default=None)
    p = sub.add_parser("pinned", help="their answer to pinning the page")
    p.add_argument("answer", choices=("yes", "no"))
    p = sub.add_parser("resume-saved", help="the resume the page held, saved in the copy")
    p.add_argument("file")
    p.add_argument("--asset", default="")
    p = sub.add_parser("files-saved", help="documents put in the page's file store, each "
                                           "with its asset id")
    p.add_argument("items", nargs="+", metavar="PATH ASSET")
    p = sub.add_parser("propose", help="the roles setup asks the person about")
    p.add_argument("roles", nargs="+")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2
    # Every command runs before there is a profile too: setup itself is on the page.
    return {"model": cmd_model, "view": cmd_view, "page": cmd_page, "apply": cmd_apply,
            "next": cmd_next, "pin": cmd_pin, "busy": cmd_busy,
            "progress": cmd_progress, "check": cmd_check,
            "start": cmd_start, "published": cmd_published, "resume-saved": cmd_resume_saved,
            "files-saved": cmd_files_saved, "propose": cmd_propose, "listen": cmd_listen,
            "republish": cmd_republish, "pinned": cmd_pinned}[a.cmd](a)


if __name__ == "__main__":
    import csv_store
    try:
        sys.exit(main())
    except csv_store.Conflicted as e:  # a merge left markers: say which file, read nothing
        print(f"app: {e}")
        sys.exit(1)
