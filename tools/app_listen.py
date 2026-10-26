#!/usr/bin/env python3
"""Which chat answers the person's page: one listener, with when it last answered.

A tap on the page writes the request into the page's database and rings: every chat that
watches the page is woken, each at the cost of its whole conversation. A chat that
publishes a page watches it by itself (code.claude.com/docs/en/artifacts, "Let Claude reply
to comments on its own"), so when every chat that ran `app.py start` published, one tap woke
the setup chat, each long chat from before 4.0 and every split screen at full size. Now one
chat answers the page, the listener, and every other chat neither publishes nor watches it.

The record is the page's own database, `meta/listener`: {chat, title, kind, since,
answered_at, took_from}. It is shared at once by every chat and every device, so two chats
that start together cannot both become the listener: each claims it with a write that only
one can win (a create, refused when the document exists, or a write pinned to the version
read). Nothing about it is committed, so two chats never fight over it in a merge. Each
checkout keeps what it last saw in its own git folder (`ljs-listener.json`), never
committed, so a chat that knows another one answers starts with no read at all.

    python3 tools/app.py listen <dump> --chat ID [--listen] [--helper] [--hand ID]
    python3 tools/app.py republish <out dir>       the page's own code changed: queue it

`app.py start` prints the steps (`shape`): the listener keeps its watch on and checks in;
a chat that may become it asks the database; every other chat does neither and says
nothing about it. The listener hands the page to a small chat of its own once setup is
done (`HELPER_TITLE`), so a tap never wakes a long one. When nobody answers, the page shows
"Claude isn't listening" with one link that opens a chat which becomes the listener
(`model_part`, `wake_url`).

A watch that Claude Code started by itself "can end after the artifact goes several hours
without activity"; publishing again or asking Claude to watch starts it again (the same
page). So the listener asks for its watch at every start. In a cloud chat a watch is a wake
subscription the artifact service holds (the ArtifactComments tool's own description).

Pure code, standard library only, no network.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

DOC_COLLECTION, DOC_ID = "meta", "listener"
CACHE = "ljs-listener.json"            # in the git folder: what this checkout last saw
# Work or a tap waiting this long after the listener last answered: nobody is answering.
LAPSE_S = 10 * 60
HELPER_TITLE = "Job search: Claude's helper (keep this)"
# What the page's "Wake Claude" link types for the person; they only press Send. The chat
# that opens runs the command and becomes the listener: a new chat with nothing else to do,
# so it is the helper itself and starts no other.
WAKE_PROMPT = ("Look after my job search page from now on: python3 tools/app.py start "
               "--listen --helper")
HELPER_PROMPT = ("You are the helper for my job search page: it wakes this chat when I tap "
                 "something there. Run python3 tools/app.py start --listen --helper and do "
                 "what it prints. Keep this chat small: anything longer than a couple of "
                 "minutes goes to a chat of its own.")
REPUBLISH_TITLE = "Bringing your page up to date"
# All the person hears about their page after an update: one line. A chat that took an
# update (2026-10-26) asked whether to bring the page up, explained that a safety check had
# blocked its first try, offered the pin again and reported a timer running out; the person
# had asked for none of it.
SAY_UPDATED = "Your page is updated."
SAY_UPDATING = "Your page is being updated."
SAY_NOT_UPDATED = "I couldn't update your page just now."
SAY_HELPER = "Your page now has a small helper chat of its own; please keep it."
# How every page step after an update is done: at once, unasked, one command at a time (a
# chained command goes to the desktop app's safety check whole), with nothing left behind.
NO_ASK = ("Do it now, before anything else, and never ask the person first: bringing their "
          "page up to date after an update is always yes. Run each command on its own, never "
          "chained, and set no timer or reminder for any of it.")
# What start prints, as app_setup words it, so its publish steps can be told apart.
_NUM = re.compile(r"^(\d+)\. ")
_PUBLISH = ("The person's page is ", "Build the person's page", "Read the page first",
            "Publish it (Artifact")
_WATCH = "Publishing makes this chat watch the page"
_BEFORE = ("Setup carries on", "The page shows the updates", "Bring the page's data up to date",
           "Unless the update check above just did it")


# ------------------------------------------------------------------ who this chat is


def this_chat(given: str = "") -> str:
    """This chat's id: the one given, else what Claude Code sets. A cloud chat's id
    (CLAUDE_CODE_REMOTE_SESSION_ID, in `cse_` form) is written in the `session_` form its
    link and create_session use (code.claude.com/docs/en/cloud-environments, "Link output
    back to the session"); a chat on a computer has CLAUDE_CODE_SESSION_ID
    (code.claude.com/docs/en/env-vars). "" when none is known. LJS_CHAT is for tests."""
    if given:
        return given
    env = os.environ
    for key in ("LJS_CHAT", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_BRIDGE_SESSION_ID"):
        v = str(env.get(key) or "").strip()
        if v:
            return re.sub(r"^cse_", "session_", v)
    v = str(env.get("CLAUDE_CODE_SESSION_ID") or "").strip()
    return f"local-{v}" if v else ""


def chat_kind() -> str:
    """"cloud" in a cloud chat (CLAUDE_CODE_REMOTE, documented), else "computer"."""
    return "cloud" if os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true" else "computer"


# ------------------------------------------------------------------ what this checkout saw


def _cache_path() -> str:
    import person
    root = person.state()
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--absolute-git-dir"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=10, stdin=subprocess.DEVNULL)
        d = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        d = ""
    return os.path.join(d, CACHE) if d else os.path.join(root, "." + CACHE)


def seen() -> dict:
    """What this checkout last saw: {"listener": {chat, title, kind, since, seen_at},
    "told": {chat: day}}. Empty when nothing was seen."""
    try:
        with open(_cache_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _replace(tmp: str, path: str) -> None:
    """os.replace, waiting out another chat's replace of the same file: Windows refuses a
    replace while the other is mid-way (PermissionError), where POSIX lets both through."""
    import time
    for i in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if os.name != "nt" or i == 39:
                raise
            time.sleep(0.05)


def _save_seen(data: dict) -> None:
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"     # two chats in one folder each write whole files
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")
    _replace(tmp, path)


def _remember(listener: dict | None, now: dt.datetime, confirmed: bool = True) -> None:
    """Keep what this checkout saw. `confirmed` is False for a claim this chat has only
    sent: until a read of the page shows who won, it decides nothing for another chat."""
    got = seen()
    if listener and listener.get("chat"):
        got["listener"] = {k: listener.get(k) for k in ("chat", "title", "kind", "since",
                                                         "helper")}
        got["listener"].update(seen_at=_stamp(now), confirmed=confirmed)
    else:
        got.pop("listener", None)
    _save_seen(got)


def role(chat: str, listen: bool = False, url: str = "") -> str:
    """What start tells this chat: "first" (no page yet: it publishes and listens),
    "listener" (it answered last time this checkout looked), "claim" (ask the page: it
    listens only where nobody does, or when asked to), or "other"."""
    if not url:
        return "first"
    if listen:
        return "claim"
    got = seen().get("listener") or {}
    known = got.get("chat") or ""
    if chat and known == chat:
        return "listener"            # its check-in reads the page and corrects a lost claim
    if not known or not got.get("confirmed"):
        return "claim"               # nobody, or another chat's claim nobody has seen win
    return "other"


# ------------------------------------------------------------------ the database's answer


def _time(value):
    import app_model
    return app_model.parse_time(value)


def _stamp(t: dt.datetime) -> str:
    import app_model
    return app_model.stamp(t)


def record(db: dict) -> tuple[dict, int | None]:
    """(meta/listener's fields, its version) from a dump; ({}, None) when there is none."""
    doc = (db.get(DOC_COLLECTION) or {}).get(DOC_ID)
    return (dict(doc["data"]), doc["version"]) if doc else ({}, None)


def waiting_since(db: dict) -> dt.datetime | None:
    """When the oldest thing still waiting for a chat was asked: a queued work item, or a
    tap with no receipt and no claim. None when nothing waits (or nothing was dumped)."""
    times = []
    for doc in (db.get("work") or {}).values():
        d = doc["data"]
        if str(d.get("status") or "") == "queued" and not d.get("stop_asked"):
            times.append(_time(d.get("asked_at")))
    receipts = db.get("receipts") or {}
    for aid, doc in (db.get("actions") or {}).items():
        if aid not in receipts and not doc["data"].get("claimed_by"):
            times.append(_time(doc["data"].get("at")))
    times = [t for t in times if t is not None]
    return min(times) if times else None


def lapsed(rec: dict, db: dict, now: dt.datetime) -> bool:
    """Has the listener stopped answering? Something has waited LAPSE_S since it was asked
    and the listener has not answered since. A quiet listener with nothing waiting has not
    lapsed: a watch outlives a quiet week."""
    if not rec.get("chat"):
        return True
    since = waiting_since(db)
    if since is None or (now - since).total_seconds() < LAPSE_S:
        return False
    answered = _time(rec.get("answered_at")) or _time(rec.get("since"))
    return answered is None or answered < since


def _ago(value, now: dt.datetime) -> str:
    t = _time(value)
    if t is None:
        return "never"
    s = max(0, int((now - t).total_seconds()))
    for size, word in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if s >= size:
            n = s // size
            return f"{n} {word}{'s' if n != 1 else ''} ago"
    return "just now"


def decide(db: dict, chat: str, out_dir: str, now: dt.datetime | None = None,
           listen: bool = False, helper: bool = False, title: str = "",
           hand_to: str = "") -> dict:
    """Is this chat the page's listener? {"role": "listener" | "other", "lines": [...],
    "batches": [...], "record": the listener as this chat leaves it}.

    The chat named in meta/listener answers; this chat writes that it answered just now.
    With no record, or one whose chat stopped answering, or when the person asked this chat
    to look after the page (`listen`), it claims the record with a write only one chat can
    win. `hand_to` gives the page to another chat (the helper this one just started)."""
    import page_db
    now = now or dt.datetime.now(dt.timezone.utc)
    rec, version = record(db)
    w = page_db.Writes(out_dir)
    at = _stamp(now)
    lines: list[str] = []
    if not chat:
        return {"role": "other", "batches": [], "record": rec,
                "lines": ["listen: this chat's id is not known, so it cannot answer the page: "
                          "run this again with --chat <this chat's id> (in a cloud chat, "
                          "echo ${CLAUDE_CODE_REMOTE_SESSION_ID/#cse_/session_})"]}
    mine = rec.get("chat") == chat
    if hand_to:
        if not mine:
            return {"role": "other", "batches": [], "record": rec,
                    "lines": ["listen: this chat does not answer the page, so it has nothing "
                              "to hand over"]}
        new = {"chat": hand_to, "title": HELPER_TITLE, "kind": "cloud", "helper": True,
               "since": at, "answered_at": None, "took_from": chat}
        w.add("set", DOC_COLLECTION, DOC_ID, new, if_version=version)
        _remember(new, now, confirmed=False)
        return {"role": "other", "record": new, "batches": w.save("listen"),
                "lines": ["listen: the page is handed to the helper chat. Send the batch "
                          "below, then stop this chat's watch: ArtifactComments, action "
                          "watch, url <the page>, on: false."]}
    take = not mine and (listen or lapsed(rec, db, now))
    if mine:
        w.add("update", DOC_COLLECTION, DOC_ID,
              {"answered_at": at, "watching": True, **({"helper": True} if helper else {})},
              if_version=version)
        rec = dict(rec, answered_at=at, watching=True, **({"helper": True} if helper else {}))
        lines.append("listen: this chat answers the page. Send the batch below (it says this "
                     "chat answered just now). If it is refused, another chat took the page "
                     "over: read meta/listener again and run this once more.")
    elif take:
        new = {"chat": chat, "title": title or ("Job search: Claude's helper" if helper
                                               else "Job search"),
               "kind": chat_kind(), "helper": bool(helper), "since": at, "answered_at": at,
               "watching": True, "took_from": rec.get("chat") or None}
        w.add("set", DOC_COLLECTION, DOC_ID, new, if_version=version)
        lines.append("listen: this chat answers the page now. Send the batch below. If it is "
                     "refused, another chat got there first: read meta/listener again and run "
                     "this once more.")
        if rec.get("chat"):
            lines.append("listen: the chat that answered before stops by itself: its next "
                         "check finds this one.")
        _remember(new, now, confirmed=False)
        return {"role": "listener", "lines": lines, "batches": w.save("listen"), "record": new}
    else:
        _remember(rec, now)
        return {"role": "other", "batches": [], "record": rec,
                "lines": [f"listen: another chat answers the page (it last answered "
                          f"{_ago(rec.get('answered_at') or rec.get('since'), now)}). This "
                          "chat neither publishes the page nor watches it, and says nothing "
                          "about that to the person.",
                          "listen: if this chat watches the page from before (ArtifactComments, "
                          "action watch with no url, lists this chat's watches), stop that "
                          "watch: action watch, url <the page>, on: false."]}
    _remember(rec, now)
    return {"role": "listener", "lines": lines, "batches": w.save("listen"), "record": rec}


def first_claim(chat: str, out_dir: str, now: dt.datetime | None = None,
                title: str = "") -> dict:
    """The claim a chat makes right after the page's first publish: its database is empty,
    so the record is created, and a second chat's create is refused."""
    import page_db
    now = now or dt.datetime.now(dt.timezone.utc)
    w = page_db.Writes(out_dir)
    at = _stamp(now)
    new = {"chat": chat, "title": title or "Job search", "kind": chat_kind(), "helper": False,
           "since": at, "answered_at": at, "watching": True, "took_from": None}
    w.add("set", DOC_COLLECTION, DOC_ID, new)
    _remember(new, now, confirmed=False)
    return {"record": new, "batches": w.save("listen")}


# ------------------------------------------------------------------ republish


def page_version() -> int:
    import build_versions
    return build_versions.current("page")


def republish(out_dir: str, now: dt.datetime | None = None, version: int | None = None) -> dict:
    """The page's own code changed, and this chat does not answer the page: the request to
    republish it, for the listener, as one batch. Its id carries the page's version, so two
    chats asking for the same one make one request (the second create is refused)."""
    import page_db
    now = now or dt.datetime.now(dt.timezone.utc)
    v = version or page_version()
    wid = f"republish~v{v}"
    w = page_db.Writes(out_dir)
    w.add("set", "work", wid, {
        "kind": "republish", "title": REPUBLISH_TITLE, "to": "either",
        "args": {"version": v}, "asked_at": _stamp(now), "asked_from": {"tab": "chat"},
        "status": "queued", "priority": 1})
    return {"work": wid, "batches": w.save("republish")}


STAGES = [("build", "Building the new page", 20), ("publish", "Putting it up", 20)]


def next_republish(db: dict, chat: str, now: dt.datetime) -> dict | None:
    """The queued republish this chat should take: only the listener's, oldest first.
    `already` is True when the page is current, so the item is closed with nothing
    published (a republish reloads every open window)."""
    rec, _ = record(db)
    if not chat or rec.get("chat") != chat:
        return None
    queued = sorted((str(d["data"].get("asked_at") or ""), wid)
                    for wid, d in (db.get("work") or {}).items()
                    if d["data"].get("kind") == "republish"
                    and str(d["data"].get("status") or "") == "queued")
    if not queued:
        return None
    wid = queued[0][1]
    try:
        import build_versions
        already = not build_versions.behind("page")
    except Exception:  # noqa: BLE001  no profile: publish it
        already = False
    return {"work": wid, "version": db["work"][wid]["version"], "kind": "republish",
            "title": REPUBLISH_TITLE, "locks": [], "already": already,
            "stages": [{"key": k, "name": n, "est_s": s} for k, n, s in STAGES]}


def without_republish(db: dict) -> dict:
    """The dump with republish requests left out, for a chat that may not take them."""
    out = dict(db)
    out["work"] = {k: v for k, v in (db.get("work") or {}).items()
                   if v["data"].get("kind") != "republish"}
    return out


# ------------------------------------------------------------------ what the page shows


def wake_url(repo: str = "") -> str:
    """The link the page shows when nobody answers: it opens a new chat on the person's
    copy with WAKE_PROMPT typed (claude.ai/code's documented pre-filled link, `prompt` and
    `repositories`); the chat is made only when they press Send."""
    url = "https://claude.ai/code?prompt=" + urllib.parse.quote(WAKE_PROMPT, safe="")
    return url + ("&repositories=" + urllib.parse.quote(repo, safe="") if repo else "")


def model_part(repo: str = "") -> dict:
    """What the page needs to show "Claude isn't listening": where the listener's record is
    (the page reads it live: `answered_at` is when it last answered), how long something may
    wait before nobody is answering, and the link that opens a chat which becomes the
    listener. No time is embedded, so the model's rev holds while nothing changed."""
    return {"doc": f"{DOC_COLLECTION}/{DOC_ID}", "answered": "answered_at",
            "quiet_after_s": LAPSE_S, "helper": HELPER_TITLE,
            "wake": {"label": "Wake Claude", "url": wake_url(repo), "prompt": WAKE_PROMPT}}


def privacy() -> str:
    """The page's footer line (claude_surfaces: page-share): true while the page is not
    shared, and saying what it holds."""
    import claude_surfaces
    return claude_surfaces.entry("page-share")["line"]


# ------------------------------------------------------------------ the pin


def pin_asked() -> bool:
    """Was the pin ever offered? Offered is enough: the offer is made at most once, answered
    or not (profile/app.json `pin`, kept with the rest of the person's state)."""
    import app_setup
    pin = app_setup.page_record().get("pin") or {}
    return bool(pin.get("asked") or pin.get("offered"))


def record_pin(answer: str, today: dt.date | None = None) -> str:
    """Their answer to "pin it?", so it is asked once: profile/app.json `pin`."""
    if answer not in ("yes", "no"):
        raise ValueError("the answer is yes or no")
    return _write_pin(asked=(today or dt.date.today()).isoformat(), answer=answer)


def record_pin_offered(today: dt.date | None = None) -> str:
    """The pin was offered (its line printed): it is never offered again, whether or not
    the person answered or the chat recorded their answer."""
    return _write_pin(offered=(today or dt.date.today()).isoformat())


def _write_pin(**fields) -> str:
    import app_setup
    got = app_setup.page_record()
    got["pin"] = dict(got.get("pin") or {}, **fields)
    path = os.path.join(app_setup.profile_dir(), app_setup.PAGE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    _replace(tmp, path)
    return path


def pin_line(url: str, n: int | None = None) -> str:
    """The once-only offer to pin the page (claude_surfaces: find-page)."""
    import claude_surfaces
    ask = claude_surfaces.entry("find-page")["ask"]
    head = f"{n}. " if n is not None else ""
    return (f"{head}Ask the person once, in these words: \"{ask}\" On a yes: Artifact, action "
            f"pin, url {url}. Either way, then python3 tools/app.py pinned yes|no. It is "
            "offered this once and never again: never mention pinning otherwise.")


# ------------------------------------------------------------------ start's steps


def _origin() -> tuple[str, str]:
    try:
        import app_setup
        return app_setup.origin()
    except Exception:  # noqa: BLE001
        return ("", "")


def _check_in(chat: str, url: str, claim: bool, listen: bool, helper: bool) -> str:
    flags = (" --listen" if listen else "") + (" --helper" if helper else "")
    if claim:
        return (f"Ask the page which chat answers it, before publishing anything: ArtifactData "
                f"get (url {url}, collection meta, doc_id listener) and query (collection "
                "work, where status == queued), both with out_dir <your scratchpad>/listen; "
                f"then python3 tools/app.py listen <your scratchpad>/listen --chat "
                f"{chat or '<this chat id>'}{flags}, and send the batch it prints. It makes "
                "this chat the listener only where none answers, or where the person asked "
                "this chat to look after the page; otherwise this chat neither publishes nor "
                "watches the page, and says nothing about either.")
    return (f"This chat answers the person's page. Keep its watch on: ArtifactComments, action "
            f"watch, url {url} (a watch that started by itself can end after hours with no "
            "activity; asking for one starts it again). Then check in: ArtifactData get (url "
            f"{url}, collection meta, doc_id listener, out_dir <your scratchpad>/listen), "
            f"python3 tools/app.py listen <your scratchpad>/listen --chat {chat}{flags}, and "
            "send the batch it prints. If it says another chat answers the page now, stop "
            "this chat's watch (watch, url, on: false) and publish nothing.")


def _handover(chat: str, url: str, on: str) -> str:
    owner, name = _origin()
    src = f"https://github.com/{owner}/{name}" if owner else "<the person's copy on GitHub>"
    try:
        import model_guide
        model = model_guide.for_work("listen", on)["model"]
    except Exception:  # noqa: BLE001
        model = None
    return ("If the check-in kept this chat as the listener, give the page a small chat of its "
            "own, so a tap never wakes this one at its size. Where this chat can start cloud "
            f"chats (create_session): create_session with source_url {src}, title "
            f"\"{HELPER_TITLE}\"" + (f", model {model}" if model else "") +
            f", prompt \"{HELPER_PROMPT}\"; then python3 tools/app.py listen <your "
            f"scratchpad>/listen --chat {chat} --hand <the new session's id>, send its batch, "
            f"and stop this chat's watch (ArtifactComments, action watch, url {url}, on: "
            f"false). Tell the person this one sentence, and nothing more about it: "
            f"\"{SAY_HELPER}\" Where this chat cannot start one, carry on and say nothing: it "
            "answers the page while it is open.")


def _numbered(line: str) -> tuple[str, str] | None:
    m = _NUM.match(line)
    return (m.group(1), line[m.end():]) if m else None


def shape(code: int, lines: list[str], chat: str = "", listen: bool = False,
          helper: bool = False, on: str = "") -> list[str]:
    """start's lines, with what this chat does about the page: the listener publishes and
    watches, a chat that may become it asks the page first, any other chat does neither."""
    if code != 0 or len(lines) < 2:
        return lines
    import app_setup
    head = lines[0]
    url = app_setup.page_record().get("url", "") or ""
    who = role(chat, listen, url)
    steps = list(lines[2:])
    text = [(_numbered(ln) or ("", None))[1] for ln in steps]
    found = [i for i, t in enumerate(text) if t is not None and t.startswith(_PUBLISH)]
    watch = [i for i, t in enumerate(text) if t is not None and t.startswith(_WATCH)]
    publish = [text[i] for i in found]
    behind = bool(found) and bool(url)
    at = (found or watch or [None])[0]
    gone = set(found) | set(watch)
    keep = [(text[i] is not None, text[i] if text[i] is not None else ln)
            for i, ln in enumerate(steps) if i not in gone]
    if at is None:
        at = next((i for i, (step, t) in enumerate(keep) if step and t.startswith(_BEFORE)),
                  len(keep))
    else:
        at = sum(1 for i in range(at) if i not in gone)
    add: list[str] = []
    if who == "first":
        if publish:
            add = publish + ["Publishing makes this chat watch the page, which makes it the "
                             "page's listener: the one chat a tap on the page wakes. The "
                             "published step records that and prints one batch to send."]
    elif who == "other":
        got = seen()
        told = got.get("told") or {}
        if (chat or "?") not in told:
            add.append("Another chat answers the person's page. This chat neither publishes it "
                       "nor watches it, and says nothing about that to the person. If it "
                       "watches the page from before (ArtifactComments, action watch with no "
                       "url, lists this chat's watches), stop that watch: action watch, url "
                       f"{url}, on: false.")
            told[chat or "?"] = dt.date.today().isoformat()
            got["told"] = dict(sorted(told.items(), key=lambda kv: kv[1])[-50:])
            _save_seen(got)
        if behind:
            add.append("The page's own code changed: ask the chat that answers it to republish "
                       "it, now and without asking the person. python3 tools/app.py republish "
                       "<your scratchpad>/republish, then send the batch it prints (ArtifactData "
                       f"batch, url {url}); do not wait for it. Tell the person only: "
                       f"\"{SAY_UPDATING}\"")
    else:
        add.append(_check_in(chat, url, who == "claim", listen, helper))
        if publish:
            add += [f"If that left this chat as the listener: {p[:1].lower()}{p[1:]}"
                    for p in publish]
            add.append("Otherwise: python3 tools/app.py republish <your scratchpad>/republish, "
                       f"send the batch it prints (ArtifactData batch, url {url}), and tell "
                       f"the person only: \"{SAY_UPDATING}\"")
        # The pin is offered by the publish step alone (`published_lines`), which records it.
        done = head.startswith("app start: set up") and "elsewhere" not in head
        if done and setup_done() and not helper and not (seen().get("listener") or {}).get("helper"):
            add.append(_handover(chat, url, on))
        try:
            import routines
            if routines.calls():
                add.append("The page asked for a change to the brief's schedule: python3 "
                           "tools/routines.py calls prints each scheduled-task call; make "
                           "it, then python3 tools/routines.py called <its n>.")
        except Exception:  # noqa: BLE001  no profile yet, or no registry
            pass
    keep[at:at] = [(True, a) for a in add]
    out, n = [], 0
    for step, t in keep:
        if step:
            n += 1
            out.append(f"{n}. {t}")
        else:
            out.append(t)
    return lines[:2] + out


def published_lines(url: str, chat: str, first: bool, out_dir: str,
                    now: dt.datetime | None = None) -> list[str]:
    """What `app.py published` says after a publish: the first publish makes this chat the
    listener (its record created on the page), and the pin is offered once."""
    out = []
    if first and chat:
        got = first_claim(chat, out_dir, now)
        out.append("app: this chat is the page's listener now: send this batch (ArtifactData "
                   f"batch, url {url}): " + " ".join(got["batches"]))
    if not pin_asked():
        out.append("app: " + pin_line(url))
        try:
            record_pin_offered()
        except OSError:
            pass
    if first and chat and setup_done():
        out.append("app: " + _handover(chat, url, ""))
    return out


# ------------------------------------------------------------------ after an update


def _publish_now(url: str, n: int) -> list[str]:
    """The republish itself, numbered from `n`: build, read, publish, keep, and one line."""
    return [f"{n}. python3 tools/app.py page --out <your scratchpad>/page.html",
            f"{n + 1}. Artifact, action read, url {url}. Then Artifact, action publish, "
            f"file_path <your scratchpad>/page.html, url {url}, with the capabilities python3 "
            "tools/app_page.py --capabilities prints. If the publish is refused, read the page "
            "again and publish once more; only if that is refused too, tell the person this one "
            f"line and stop: \"{SAY_NOT_UPDATED}\"",
            f"{n + 2}. python3 tools/app.py published {url}, and do what it prints.",
            f"{n + 3}. Tell the person this one line, and nothing else about the page or the "
            f"update: \"{SAY_UPDATED}\""]


def after_update(landed: bool = False, chat: str = "") -> list[str]:
    """What this chat does about the person's page once an update is in: the day's sync,
    `sync_app.py --if-stale`, or `--update` when the person said "update". The page's own
    code changed: republish it now (the listener does; any other chat asks the listener, at
    once). Only its data could have changed (`landed`): `app.py view`. Never a question, and
    one line to the person. [] when there is no page yet (start publishes the first one) or
    nothing changed for it."""
    import app_setup
    url = str(app_setup.page_record().get("url") or "")
    if not url or not app_setup.set_up():
        return []
    behind = not app_setup._page_current()
    if not behind and not landed:
        return []
    chat = this_chat(chat)
    who = role(chat, False, url)
    if not behind:
        return [f"Claude: an update just landed. Bring the person's page up to date now. {NO_ASK}",
                "1. ArtifactData query, once for each of the collections view, meta and reach "
                f"(url {url}, out_dir <your scratchpad>/page-data, limit 1000).",
                "2. python3 tools/app.py view <your scratchpad>/page-writes --dump <your "
                "scratchpad>/page-data" + (f" --chat {chat}" if chat else ""),
                f"3. Send each batch it prints, in order (ArtifactData batch, url {url}). If one "
                "is refused, do steps 1 to 3 once more; only if it is refused again, tell the "
                f"person this one line and stop: \"{SAY_NOT_UPDATED}\"",
                "4. Tell the person this one line, and nothing else about the page or the "
                f"update: \"{SAY_UPDATED}\""]
    head = f"Claude: the update changed the person's page itself. {NO_ASK}"
    ask = ("python3 tools/app.py republish <your scratchpad>/republish, then send the batch it "
           f"prints (ArtifactData batch, url {url}); refused means the request is there "
           "already. Do not wait for it: the page shows its progress. Tell the person this "
           f"one line, and nothing else about the page or the update: \"{SAY_UPDATING}\"")
    if who == "other":
        return [head, "1. Another chat answers the page, so it republishes it: " + ask]
    if who == "listener":
        return [head + " Republish it:"] + _publish_now(url, 1)
    return [head + " Republish it:",
            f"1. Which chat answers the page: ArtifactData get (url {url}, collection meta, "
            "doc_id listener, out_dir <your scratchpad>/listen), then python3 tools/app.py "
            f"listen <your scratchpad>/listen --chat {chat or '<this chat id>'}, and send the "
            "batch it prints.",
            "2. If it says another chat answers the page: " + ask + " Then stop here."] + \
        _publish_now(url, 3)


def setup_done() -> bool:
    """Is setup over (a profile, and no setup started and not finished)? While it runs, the
    chat setting up answers the page: the answers there are what it carries on from."""
    import app_setup
    if not app_setup.set_up():
        return False
    try:
        with open(os.path.join(app_setup.profile_dir(), "place.json"), encoding="utf-8") as fh:
            mark = (json.load(fh) or {}).get("setup") or {}
    except (OSError, ValueError, AttributeError):
        mark = {}
    if mark.get("finished"):
        return True
    return not mark.get("started") and not os.path.isfile(
        os.path.join(app_setup.profile_dir(), app_setup.ANSWERS))
