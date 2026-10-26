#!/usr/bin/env python3
"""The app's page and its chats: one command for each thing a chat does with the page.

    python3 tools/app.py model [--out F] [--today D] [--now T]   the view model, as JSON
    python3 tools/app.py view <out dir> [--dump DIR]             the model as view/* writes
    python3 tools/app.py page [--out F]                          the whole page, to publish
    python3 tools/app.py apply <dump dir> [--chat ID] [--claim]  the page's actions, applied
    python3 tools/app.py next <dump dir> --chat ID --kind cloud|computer [--claim-out DIR]
    python3 tools/app.py progress <kind of work>                 its stages and their seconds
    python3 tools/app.py check [--model F]                       the model against the contract
    python3 tools/app.py start [--on M] [--tools T] [--page URL] [--chat ID] [--listen]
                                                                 what this chat does next, in any
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
    """The model as one document a section (`view/<section>`) plus `meta/current`, so an open
    page updates live with no republish. Sets on documents that exist are pinned to the
    versions in `--dump`."""
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
        w.add("delete", "view", doc_id, if_version=db["view"][doc_id]["version"])
    # The model builds `listener` and `schedule` itself now; each document is written once.
    for name in dict.fromkeys(tuple(app_model.SECTIONS) + ("people_count", "lists", "listener",
                                                           "schedule")):
        if name not in model:
            continue
        old = (db.get("view") or {}).get(name) if db else None
        w.add("set", "view", name, {"rev": model["rev"], "made_at": model["made_at"],
                                    "data": model[name]},
              if_version=old["version"] if old else None)
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
    have = db.get("reach") or {} if db else {}
    for cid, doc in sorted(reach.items()):
        old = have.get(page_db.safe_id(cid))
        if old and {k: old["data"].get(k) for k in doc} == doc:
            continue
        w.add("set", "reach", page_db.safe_id(cid), doc,
              if_version=old["version"] if old else None)
    for cid, old in sorted(have.items()):
        if cid not in {page_db.safe_id(c) for c in reach}:
            w.add("delete", "reach", cid, if_version=old["version"])
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
    (tools/model_guide.py for_work). A republish goes to the page's listener alone, and
    first: the page's own code changed under every open window."""
    import app_listen
    import app_model
    import model_guide
    import page_db
    _, now = app_model.clock(None, a.now)
    db = page_db.load(a.dump)
    chosen = app_listen.next_republish(db, a.chat, now)
    if chosen is None:
        either = app_model.setting_values().get("work_either", "cloud")
        chosen = page_db.next_item(app_listen.without_republish(db), a.kind, now,
                                   either_to=either)
    if chosen is None:
        return 0
    info = model_guide.for_work(chosen["kind"], a.on)
    chosen.update(model=info["model"], effort=info["effort"])
    if a.claim_out:
        chosen["batches"] = page_db.claim(db, chosen, a.chat, a.kind, now, a.claim_out)
    print(_dump(chosen), end="")
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
                             helper=a.helper, on=a.on or "")
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
    return 0


def cmd_listen(a) -> int:
    import app_listen
    import app_model
    import page_db
    _, now = app_model.clock(None, a.now)
    got = app_listen.decide(page_db.load(a.dump), app_listen.this_chat(a.chat),
                            a.out or os.path.join(a.dump, "listen_out"), now,
                            listen=a.listen, helper=a.helper, hand_to=a.hand)
    for line in got["lines"]:
        print(line)
    for path in got["batches"]:
        print(path)
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
    print("app: noted; the pin is never offered again")
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
    p.add_argument("--paste", action="store_true",
                   help="print the line a person pastes into a chat on their computer")
    p = sub.add_parser("published", help="keep the page's address once it is published")
    p.add_argument("url")
    p.add_argument("--chat", default="")
    p.add_argument("--out", default="", help="where the listener's batch goes")
    p = sub.add_parser("listen", help="is this chat the page's listener? and its check-in")
    p.add_argument("dump")
    p.add_argument("--chat", default="")
    p.add_argument("--listen", action="store_true", help="the person asked this chat to")
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
            "next": cmd_next, "progress": cmd_progress, "check": cmd_check,
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
