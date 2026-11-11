#!/usr/bin/env python3
"""What the chat that answers the page costs: a line a wake and a hand-over, one number a day.

The page's helper grew by hundreds of thousands of tokens a day and nobody could say what a
tap cost (the maintainer, 2026-11-05). Each wake ends with `app.py view --end`, which records
here, from files this computer already holds and with no tool call:

- `listener`: the history the helper's chat re-reads at each of its steps (its last turn's
  input, from its own session file under ~/.claude/projects);
- `agent_in` / `agent_out`: what the wake's short-lived subagent read and wrote over all its
  turns (its own file, under the session's `subagents` folder), thrown away after;
- `est_usd`: an estimate from those, at the list prices in RATES (cache reads, mostly), or
  the cost get_session reported where it was given (`--usage`, its answer saved to a file:
  its fields are read where they are there, never required).

A hand-over (a fresh helper started) is recorded with the old chat's size. The record is
`documents/helper_usage.json`, a list only ever added to and kept KEEP_DAYS, merged entry by
entry (tools/merge_state.py).

    python3 tools/helper_usage.py day [--day YYYY-MM-DD]     one line: the day's number
    python3 tools/helper_usage.py record wake --chat ID [--usage FILE]

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

FILE = ("documents", "helper_usage.json")
KEEP_DAYS = 30
# Dollars per million tokens, by kind: the list prices of the model the helper runs on by
# default, an estimate only (get_session's own cost, when given, is used instead).
RATES = {"input": 5.0, "cache_write": 6.25, "cache_read": 0.5, "output": 25.0}
# A wake costs the listener about two of its steps: the subagent's call and its answer.
LISTENER_STEPS = 2


def path() -> str:
    import person
    return os.path.join(person.state(), *FILE)


def _projects() -> str:
    return os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"),
                        "projects")


def _newest(files: list[str]) -> str:
    files = [f for f in files if os.path.isfile(f)]
    return max(files, key=os.path.getmtime) if files else ""


def session_file() -> str:
    """The newest top-level session file: the chat this runs in (a subagent's own files sit
    one level down, under its session's `subagents` folder)."""
    root = _projects()
    try:
        return _newest([os.path.join(root, d, f) for d in os.listdir(root)
                        if os.path.isdir(os.path.join(root, d))
                        for f in os.listdir(os.path.join(root, d)) if f.endswith(".jsonl")])
    except OSError:
        return ""


def agent_file(session: str = "") -> str:
    """The newest subagent file of `session` (the wake's own, while it runs), or ""."""
    session = session or session_file()
    if not session:
        return ""
    folder = os.path.join(os.path.splitext(session)[0], "subagents")
    try:
        return _newest([os.path.join(folder, f) for f in os.listdir(folder)
                        if f.endswith(".jsonl")])
    except OSError:
        return ""


def _at(stamp) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def _usages(file: str, since: str = ""):
    """Each turn's usage once, in order. Claude Code writes one line for each block of a
    message (its text, each tool call), every one carrying that message's usage: counted per
    line, a turn was counted several times (audit CS-2, 2026-11-10). By message id, the last
    line's usage stands. `since`: only the turns from that time."""
    t0 = _at(since) if since else None
    by_id: dict = {}
    try:
        with open(file, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh):
                if '"usage"' not in line:
                    continue
                try:
                    ev = json.loads(line)
                    msg = ev["message"]
                    u = msg["usage"]
                except (ValueError, KeyError, TypeError):
                    continue
                if not isinstance(u, dict):
                    continue
                if t0 is not None:
                    at = _at(ev.get("timestamp"))
                    if at is None or at < t0:
                        continue
                key = msg.get("id") if isinstance(msg, dict) and msg.get("id") else ("line", n)
                by_id.pop(key, None)                    # kept in the order last written
                by_id[key] = u
    except OSError:
        return
    yield from by_id.values()


def totals(file: str, since: str = "") -> dict:
    """{"input", "cache_write", "cache_read", "output", "last_in"} over every turn in `file`
    (from `since`, when given), each message counted once."""
    t = {"input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "last_in": 0}
    for u in _usages(file, since):
        i, w, r = (int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                "cache_read_input_tokens"))
        t["input"] += i
        t["cache_write"] += w
        t["cache_read"] += r
        t["output"] += int(u.get("output_tokens") or 0)
        t["last_in"] = i + w + r
    return t


def estimate(t: dict) -> float:
    return sum(t.get(k, 0) * RATES[k] for k in RATES) / 1_000_000


def _given_cost(usage) -> float | None:
    """A cost get_session reported, where its answer has one (field names vary: read what is
    there, never required)."""
    if not isinstance(usage, dict):
        return None
    for key in ("total_cost_usd", "cost_usd", "cost"):
        v = usage.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    for key in ("usage", "session_context", "external_metadata"):
        got = _given_cost(usage.get(key))
        if got is not None:
            return got
    return None


def _a_persons_copy() -> bool:
    """Is the state a person's own (a test's LJS_STATE, or a copy with a profile)? The app's
    own checkout is never written to."""
    import person
    return bool(os.environ.get(person.STATE_ENV)) or \
        os.path.isfile(os.path.join(person.state(), "profile", "person.json"))


def _load() -> dict:
    try:
        with open(path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def _stamp(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(kind: str, chat: str, now: dt.datetime | None = None, tokens: int | None = None,
           usage=None, listener_file: str = "", agent: str | None = None) -> dict:
    """Add one entry ("wake" or "handover") and keep the file. Never raises for a file it
    cannot read; returns the entry."""
    now = now or dt.datetime.now(dt.timezone.utc)
    lf = listener_file or session_file()
    lt = totals(lf) if lf else {}
    listener = int(tokens if tokens is not None else lt.get("last_in", 0))
    entry = {"at": _stamp(now), "chat": chat or "", "kind": kind, "listener": listener}
    if kind == "wake":
        af = agent_file(lf) if agent is None else agent
        at = totals(af) if af else {}
        entry["agent_in"] = int(at.get("input", 0) + at.get("cache_write", 0)
                                + at.get("cache_read", 0))
        entry["agent_out"] = int(at.get("output", 0))
        est = estimate(at) + LISTENER_STEPS * listener * RATES["cache_read"] / 1_000_000
    else:
        est = 0.0
    given = _given_cost(usage)
    entry["est_usd"] = round(given if given is not None else est, 4)
    if given is not None:
        entry["cost_from"] = "get_session"
    if not _a_persons_copy():
        return entry                # the app itself, or a test with no state of its own
    got = _load()
    cutoff = _stamp(now - dt.timedelta(days=KEEP_DAYS))
    entries = [e for e in got.get("entries") or [] if isinstance(e, dict)
               and str(e.get("at") or "") >= cutoff]
    entries.append(entry)
    got["entries"] = sorted(entries, key=lambda e: (str(e.get("at")), str(e.get("kind"))))
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=1, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, p)
    return entry


def day(day_iso: str, zone: str = "UTC") -> dict:
    """{"wakes", "handovers", "tokens", "usd"} for one day in `zone`."""
    import app_model
    out = {"wakes": 0, "handovers": 0, "tokens": 0, "usd": 0.0}
    for e in _load().get("entries") or []:
        t = app_model.parse_time(e.get("at")) if isinstance(e, dict) else None
        if t is None or app_model.local_day(t, zone).isoformat() != day_iso:
            continue
        if e.get("kind") == "handover":
            out["handovers"] += 1
            continue
        out["wakes"] += 1
        out["tokens"] += int(e.get("agent_in") or 0) + LISTENER_STEPS * int(e.get("listener") or 0)
        out["usd"] += float(e.get("est_usd") or 0)
    out["usd"] = round(out["usd"], 2)
    return out


def day_line(day_iso: str, zone: str = "UTC") -> str:
    """The day's one number, in a line: "" when nothing was recorded."""
    d = day(day_iso, zone)
    if not d["wakes"] and not d["handovers"]:
        return ""
    return (f"Answering your page cost about ${d['usd']:.2f} on {day_iso} "
            f"({d['wakes']} tap{'s' if d['wakes'] != 1 else ''}, about "
            f"{round(d['tokens'] / 1000):,}k tokens).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="helper_usage.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("day")
    p.add_argument("--day", default="")
    p = sub.add_parser("record")
    p.add_argument("kind", choices=("wake", "handover"))
    p.add_argument("--chat", default="")
    p.add_argument("--usage", default="", help="get_session's answer, saved to a file")
    a = ap.parse_args(argv)
    if a.cmd == "day":
        import person
        try:
            zone = person.home_zone_named(person.directory()) or "UTC"
        except Exception:  # noqa: BLE001
            zone = "UTC"
        print(day_line(a.day or person.today().isoformat(), zone) or "Nothing recorded that day.")
        return 0
    if a.cmd == "record":
        usage = None
        if a.usage:
            try:
                with open(a.usage, encoding="utf-8") as fh:
                    usage = json.load(fh)
            except (OSError, ValueError):
                usage = None
        import app_listen
        e = record(a.kind, app_listen.this_chat(a.chat), usage=usage)
        print(f"usage: {e['kind']} recorded, about ${e['est_usd']:.2f}.")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
