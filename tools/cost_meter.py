#!/usr/bin/env python3
"""What a scheduled brief run reads, before and after, as an ESTIMATE of tokens.

Tokens here are characters / 4. No tokenizer is used, so every number is an estimate, and
the report says so on every line that matters. It is still the right instrument for a
comparison: the same counting, on the same invented person, for two ways of doing the run.

What it counts, for one run of the brief:

- the fixed load every model call carries: the app's CLAUDE.md and the person's summary it
  imports (the example person's here), the same before and after;
- what the run reads: the stub, the two prompt files (from git for "before", from the
  working tree for "after"), and the output of every command the procedure has the model
  run, produced by running those commands now on a scratch copy of the example person's
  state (profile.example), so nothing real is read or written;
- the parts no command on the example can produce (the day's update check, the news, the
  landing commands, the reply itself) as fixed sizes, each marked as such;
- how many model calls the procedure takes, and the tokens those calls process in all:
  every call reads the whole conversation so far, so a long procedure costs far more than
  the sum of what it reads.

    python3 tools/cost_meter.py brief                    # before (newest v3 release) and after
    python3 tools/cost_meter.py brief --before <rev>     # "before" from another revision
    python3 tools/cost_meter.py brief --json

The procedures are written down below as data (BEFORE, AFTER): each a list of steps, a step
being a command it runs or a fixed size. When a prompt changes how the brief runs, change
the matching list in the same change, or the meter measures a run nobody makes.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "profile.example")
TODAY = "2026-10-25"
CHARS_PER_TOKEN = 4

# Sizes no command on the example can produce, in characters, each with where it comes from.
SIZES = {
    "sync": (242, "the day's update check when current (cost audit, 2026-10-25)"),
    "setup": (60, "setup_env.sh --python when installed"),
    "git": (120, "a git or PR command's own output"),
    "ci_full": (7541, "ci_local.sh --quick, whole (cost audit, 2026-10-25)"),
    "ci_tail": (160, "ci_local.sh --quick, its last three lines"),
    "news_pages": (15000, "three publisher pages opened in the main chat, about 5,000 each "
                          "(cost audit: 3,000 to 10,000 each)"),
    "news_agent_old": (2000, "a sonnet agent's list of items with URL, publisher, date and quote"),
    "news_lines": (1300, "the news reader's six lines, about 220 characters each"),
    "reply": (1200, "the message itself, under 200 words"),
    "write_record": (2500, "the brief's record, written by the model"),
    "drafts_written": (900, "three drafts written by the model"),
    "news_in": (1100, "the news lines handed back to brief.py news"),
}

# Each step: (label, kind, what). kind "cmd" runs `what` (argv, run in the scratch copy), "file"
# reads a prompt file (resolved by the side), "size" is a key of SIZES, "out" is model output
# (a SIZES key), "agent" a subagent call whose returned text is a SIZES key.
BEFORE = [
    ("stub: git fetch", "size", "git"),
    ("read _common.md", "file", "automation/prompts/_common.md"),
    ("read morning_brief.md", "file", "automation/prompts/morning_brief.md"),
    ("git switch", "size", "git"),
    ("sync_app.py --if-stale", "size", "sync"),
    ("earlier ops branches", "size", "git"),
    ("setup_env.sh --python", "size", "setup"),
    ("read the last brief", "cmd", ["brief_record"]),
    ("read profile/CLAUDE.md", "cmd", ["profile_md"]),
    ("learned.py brief messages", "cmd", ["python3", "tools/learned.py", "brief", "messages"]),
    ("open_actions.py", "cmd", ["python3", "tools/open_actions.py", "--today", TODAY]),
    ("open_actions.py --due", "cmd", ["python3", "tools/open_actions.py", "--due", "--today", TODAY]),
    ("read the last follow-up pack", "cmd", ["pack"]),
    ("read each owed contact's thread", "cmd", ["threads"]),
    ("compose.validate on each draft", "cmd", ["validate_each"]),
    ("reading.py send-time", "cmd", ["send_time"]),
    ("write the pack", "out", "drafts_written"),
    ("prep.py --stale-only", "cmd", ["python3", "tools/network/prep.py", "--stale-only", "--dry-run",
                                     "--today", TODAY]),
    ("followups.py --close-quiet", "cmd", ["python3", "tools/followups.py", "--close-quiet",
                                           "--dry-run", "--today", TODAY]),
    ("what_works.py brief search", "cmd", ["python3", "tools/what_works.py", "brief", "search"]),
    ("own_profile.py due", "cmd", ["python3", "tools/network/own_profile.py", "due"]),
    ("export.py due", "cmd", ["python3", "tools/network/export.py", "due"]),
    ("news: a sonnet agent", "agent", "news_agent_old"),
    ("news: pages opened and read", "size", "news_pages"),
    ("write the brief record", "out", "write_record"),
    ("git add", "size", "git"),
    ("ci_local.sh --quick", "size", "ci_full"),
    ("git commit and push", "size", "git"),
    ("open the PR", "size", "git"),
    ("merge it", "size", "git"),
    ("tips.py brief", "cmd", ["python3", "tools/tips.py", "brief"]),
    ("the message", "out", "reply"),
]
AFTER = [
    ("stub: git fetch", "size", "git"),
    ("read _common.md", "file", "automation/prompts/_common.md"),
    ("read morning_brief.md", "file", "automation/prompts/morning_brief.md"),
    ("git switch && brief.py --start --write", "cmd", ["python3", "tools/brief.py", "--today", TODAY]),
    ("followup_drafts.py context --due", "cmd", ["python3", "tools/followup_drafts.py", "context",
                                                 "--due", "--today", TODAY]),
    ("news-reader (haiku, no CLAUDE.md)", "agent", "news_lines"),
    ("followup_drafts.py check - --pack", "out", "drafts_written"),
    ("brief.py news, save, commit, ci tail, push", "out", "news_in"),
    ("open the PR", "size", "git"),
    ("merge it", "size", "git"),
    ("the message", "out", "reply"),
]


def tokens(chars: int) -> int:
    return (chars + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def scratch_state() -> str:
    """A copy of the example person, profile and state, so a command run here reads and
    writes nothing real (a tip line keeps its record in the profile)."""
    d = tempfile.mkdtemp(prefix="ljs-cost-")
    shutil.copytree(os.path.join(EXAMPLE, "state"), os.path.join(d, "state"))
    shutil.copytree(EXAMPLE, os.path.join(d, "profile"),
                    ignore=shutil.ignore_patterns("state", "tips.json"))
    return os.path.join(d, "state")


def _env(state: str) -> dict:
    env = dict(os.environ)
    env.update({"LJS_PROFILE": os.path.join(os.path.dirname(state), "profile"),
                "LJS_STATE": state, "PYTHONIOENCODING": "utf-8"})
    env.pop("CLAUDE_CODE_REMOTE", None)
    return env


def run(argv, state: str) -> str:
    """A command's whole output, as the model would read it."""
    special = {"brief_record": _brief_record, "pack": _pack, "threads": _threads,
               "validate_each": _validate_each, "send_time": _send_time,
               "profile_md": _profile_md}
    if argv[0] in special:
        return special[argv[0]](state)
    argv = [sys.executable if a == "python3" else a for a in argv]
    try:
        r = subprocess.run(argv, cwd=ROOT, env=_env(state), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return "(could not run: %s)" % type(e).__name__
    return (r.stdout or "") + (r.stderr or "")


def _py(code: str, state: str) -> str:
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=_env(state), capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=120)
    return (r.stdout or "") + (r.stderr or "")


def _brief_record(state: str) -> str:
    """The last brief, as the old procedure read it: the record today's would be."""
    return _py("import sys; sys.path[:0]=['tools','tools/network']\n"
               "import datetime as dt, brief\n"
               "b = brief.gather(dt.date.fromisoformat(%r))\n"
               "print(brief.record_text(b))" % TODAY, state)


def _pack(state: str) -> str:
    return _py("import sys; sys.path[:0]=['tools','tools/network']\n"
               "import followup_drafts as f\n"
               "items, c, t, tr = f.load(%r)\n"
               "print(f.render_pack(%r, f.drafts(items, c, t, tr, %r), c))" % (TODAY, TODAY, TODAY),
               state)


def _profile_md(state: str) -> str:
    with open(os.path.join(EXAMPLE, "CLAUDE.md"), encoding="utf-8") as fh:
        return fh.read()


def _owed_ids(state: str) -> list[str]:
    out = _py("import sys; sys.path[:0]=['tools','tools/network']\n"
              "import followup_drafts as f\n"
              "items, c, t, tr = f.load(%r)\n"
              "print(' '.join(i.get('contact_id') or '' for i in items if i.get('half') == 'contact'))"
              % TODAY, state)
    return [x for x in out.split() if x]


def _threads(state: str) -> str:
    import csv
    ids = set(_owed_ids(state))
    path = os.path.join(state, "network_threads.csv")
    with open(path, encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    return "\n".join(",".join(r) for r in rows if r and r[0] in ids)


def _validate_each(state: str) -> str:
    return "\n".join("compose.validate(...) -> []  # %s" % cid for cid in _owed_ids(state))


def _send_time(state: str) -> str:
    ids = _owed_ids(state)
    return run(["python3", "tools/network/reading.py", "send-time"] + ids, state) if ids else ""


def prompt_file(path: str, rev: str | None) -> str:
    if rev is None:
        with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
            return fh.read()
    r = subprocess.run(["git", "show", "%s:%s" % (rev, path)], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def newest_v3() -> str:
    r = subprocess.run(["git", "tag", "--list", "v3.*", "--sort=-v:refname"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tags = (r.stdout or "").split()
    return tags[0] if tags else "HEAD"


def fixed_load() -> dict:
    """The project's own load on every call: CLAUDE.md and the summary it imports."""
    parts = {}
    for label, path in (("CLAUDE.md", os.path.join(ROOT, "CLAUDE.md")),
                        ("profile/CLAUDE.md (example)", os.path.join(EXAMPLE, "CLAUDE.md"))):
        try:
            with open(path, encoding="utf-8") as fh:
                parts[label] = len(fh.read())
        except OSError:
            parts[label] = 0
    return parts


def measure(steps, rev: str | None, state: str) -> dict:
    """Each step's characters, the calls it takes, and the tokens processed over the run."""
    base = sum(fixed_load().values())
    rows, convo, processed, calls = [], 0, 0, 0
    for label, kind, what in steps:
        if kind == "file":
            chars, note = len(prompt_file(what, rev)), "file"
        elif kind == "cmd":
            chars, note = len(run(what, state)), "measured"
        else:
            chars, note = SIZES[what][0], "fixed size: " + SIZES[what][1]
        calls += 1
        processed += tokens(base + convo)    # the call reads everything so far
        convo += chars
        rows.append({"step": label, "chars": chars, "tokens": tokens(chars), "how": note})
    return {"steps": rows, "calls": calls, "read_chars": convo, "read_tokens": tokens(convo),
            "processed_tokens": processed + tokens(base + convo)}


def report(before: dict, after: dict, rev: str) -> str:
    fixed = fixed_load()
    out = ["Brief run, ESTIMATED tokens (characters / 4; no tokenizer), on the example person",
           "", "Fixed load on every call, the same before and after:"]
    out += ["  %-36s %7d tokens" % (k, tokens(v)) for k, v in fixed.items()]
    for name, m in (("BEFORE (%s)" % rev, before), ("AFTER (this tree)", after)):
        out += ["", name]
        out += ["  %-44s %7d  %s" % (r["step"], r["tokens"], r["how"] if r["how"] != "measured" else "")
                for r in m["steps"]]
        out.append("  %-44s %7d tokens read, %d model calls" % ("total", m["read_tokens"], m["calls"]))
        out.append("  %-44s %7d tokens (estimate)" % ("processed over the run", m["processed_tokens"]))
    if before["processed_tokens"]:
        saved = 1 - after["processed_tokens"] / before["processed_tokens"]
        out += ["", "Processed over a run: %d -> %d tokens, about %d%% less (estimate)."
                % (before["processed_tokens"], after["processed_tokens"], round(100 * saved))]
    out.append("Not counted: Claude Code's own system prompt and tool definitions (on every call, "
               "before and after alike), and the news reader's own searches, which run on haiku "
               "in a context of their own without CLAUDE.md.")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=["brief"])
    ap.add_argument("--before", default=None, help="the revision holding the old prompts "
                                                   "(default: the newest v3 release)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rev = a.before or newest_v3()
    state = scratch_state()
    try:
        before = measure(BEFORE, rev, state)
        shutil.rmtree(os.path.dirname(state), ignore_errors=True)
        state = scratch_state()
        after = measure(AFTER, None, state)
    finally:
        shutil.rmtree(os.path.dirname(state), ignore_errors=True)
    if a.json:
        print(json.dumps({"estimate": "characters / 4", "before_rev": rev, "fixed": fixed_load(),
                          "before": before, "after": after}, indent=1))
    else:
        sys.stdout.write(report(before, after, rev))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
