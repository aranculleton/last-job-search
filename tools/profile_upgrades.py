#!/usr/bin/env python3
"""Profile upgrades: what an app feature needs on the person's side, for people who set up before it.

/setup runs once. When the app later adds something /setup writes, or something
only an action on the person's side switches on (a portal built with
/add-portal, a profile name with no safe default, a portal rebuilt to a new
contract), `tools/sync_app.py` brings the code and nothing else: an older repo
never gets the new part, nobody can tell, and every round quietly runs without
it. A CHANGELOG line saying "run X" is printed once and then lost.

So every such action is registered here. Each upgrade checks the person's repo
itself for the trace the action leaves (a profile name, a dated record, a
portal folder, a frontmatter line), never a ledger, so it cannot drift: it is
pending exactly while the trace is missing. An empty but dated answer ("looked,
nothing worth building") counts as done.

    python3 tools/profile_upgrades.py            # the pending ones, with what runs each
    python3 tools/profile_upgrades.py --line     # one line for a round summary ("" when none)
    python3 tools/profile_upgrades.py --all      # every upgrade, done or pending, and why
    python3 tools/profile_upgrades.py --after-sync   # sync_app.py: run the instant ones, then list
    python3 tools/profile_upgrades.py --plan     # JSON, most urgent first: what /upgrade works through
    python3 tools/profile_upgrades.py --check boards  # one upgrade: "done" or what is missing
    python3 tools/profile_upgrades.py --no <id>  # their no to a question: kept, dated, asked
                                                 # again when it changes or after REASK_DAYS
    python3 tools/profile_upgrades.py --not-now "<why>"  # this chat cannot start them today

Exit 0 always, except --check while its upgrade is pending: a pending upgrade never
blocks a sync, a round or a session.

**Nobody has to remember these.** A list a person has to read and act on is a list
nobody acts on, so almost every upgrade is `needs="nobody"`: at the start of a session
Claude starts a background agent that runs `/upgrade`, which works through them from
the profile and research while the person's own request goes ahead, commits each on
its own and reports what it wrote and how to undo it. Only an upgrade that needs the
person's answer or consent (`needs="you"`, with its `ask`) is put to them, once, at the
end. The optional scheduled shortlist does the same before its round.

`tools/sync_app.py` runs `--after-sync` after every sync, "up to date"
included; `tools/run_round.py` prints `--line` with its MET or MISSED summary;
CLAUDE.md "Start of every session" says what the session does with them.

Costs:
  instant   a re-render of a derived file, no web, no questions. Run by the
            sync itself and committed on its own, touching only the personal
            paths the upgrade names, or not at all.
  edit      a mechanical change to the person's own files the session makes on
            a yes. Never automatic: those files are the person's record.
  question  asks the person something; minutes.
  research  web research, sometimes a portal build; the time is given.

Adding a feature that needs any of this is not done until it is registered
here: tests/test_profile_upgrades.py fails on a new profile name with no
upgrade and no stated safe default, and on a CHANGELOG entry that tells
existing users to do something without naming its upgrade.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fnmatch
import glob
import json
import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
import local_path  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COSTS = ("instant", "edit", "question", "research")


@dataclass(frozen=True)
class Upgrade:
    id: str
    added: str                      # YYYY-MM-DD the feature shipped
    gives: str                      # one line, in the person's terms
    pending: Callable[[], str]      # "" when done, else what is missing
    run: str                        # what the session runs
    cost: str                       # instant | question | research
    time: str = ""                  # "~5 min"
    names: tuple = ()               # profile names it covers (module.NAME)
    conditional: bool = False       # pending only for some people (a country, a field)
    command: tuple = ()             # instant only: argv, from the repo root
    paths: tuple = field(default=())  # instant only: the personal path globs it may touch
    # 1 something fails until it is done, 2 results are silently worse, 3 a part
    # of the app the person is missing, 4 polish. The order /upgrade works in.
    priority: int = 3
    # "nobody": Claude does it alone, from the profile and research, and says
    # what it wrote. "you": it needs the person's answer or consent (`ask`), so
    # it is asked, never guessed. Nearly everything is "nobody": a list a person
    # has to read and act on is a list nobody acts on.
    needs: str = "nobody"
    # A question is asked short and plain first (`ask`: 40 words at most, no jargon, a
    # yes-or-not-now the person can answer at once). Only a yes brings `steps` (five
    # lines at most, one action each), and only "why?" brings `why` (one sentence). A
    # paragraph pasted at someone who never asked for it is what nobody reads.
    ask: str = ""
    steps: Callable[[], str] | None = None
    why_ask: str = ""
    # A no is an answer for now, never for ever: a question someone said no to comes
    # back when what it offers has changed (ask_version moves on and `changed` says
    # how) or once REASK_DAYS have passed, saying when they said no (`again()`).
    ask_version: int = 1
    changed: str = ""
    # Every item, one a line, for `--check <id>`, where the pending line names only a few.
    every: Callable[[], list] | None = None


# ------------------------------------------------------------------ helpers

# The registry entries the steps just built drew on, so the plan can give Claude their notes
# (an entry old enough to re-check) apart from the lines the person reads.
_DREW_ON: list[str] = []


def _surface_steps(eid: str) -> list[str]:
    """A path from the dated, sourced registry (tools/claude_surfaces.json): the person's
    lines only; `plan()` gives Claude the entry's note, if it has one, as `check`."""
    import claude_surfaces
    _DREW_ON.append(eid)
    return claude_surfaces.steps(eid)


def _steps_and_notes(u) -> tuple[str, list[str]]:
    """An upgrade's steps for the person, and Claude's notes on the entries they drew on."""
    if not u.steps:
        return "", []
    import claude_surfaces
    _DREW_ON.clear()
    text = u.steps()
    return text, claude_surfaces.notes(*_DREW_ON)


def _mod(name: str):
    """profile/<name>.py, or None where there is no profile or no such file."""
    try:
        return person.module(name)
    except person.NoProfile:
        return None


def _dated(value) -> bool:
    try:
        dt.date.fromisoformat(str(value or "")[:10])
        return True
    except ValueError:
        return False


def _missing(module: str, *names: str) -> list[str]:
    m = _mod(module)
    if m is None:
        return []
    return [n for n in names if not hasattr(m, n)]


# ------------------------------------------------------------------ a no, for now

ASKED_FILE = "asked.json"     # in profile/: {upgrade id: {"no": "YYYY-MM-DD", "version": n}}
REASK_DAYS = 30
# The whole answer to a no: one line, and it is true (REASK_DAYS).
NO_REPLY = "No problem, I'll ask again in a month."


def _asked_path() -> str:
    return person.path(ASKED_FILE)


def asked() -> dict:
    """Every no on record, by upgrade id."""
    try:
        import json
        with open(_asked_path(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError, person.NoProfile):
        return {}


def record_no(uid: str, today: dt.date | None = None) -> str:
    """Their no to one question, dated, with the version of the question it answered."""
    import json
    u = by_id(uid)
    got = asked()
    got[uid] = {"no": (today or person.today()).isoformat(), "version": u.ask_version}
    p = _asked_path()
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(got, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return p


def again(uid: str, version: int, changed: str, today: dt.date | None = None) -> str:
    """Why a question they said no to is asked again now, or "" while their no stands.

    A recorded no stands until the question changes or REASK_DAYS pass. A no with no
    record (given before this was kept) answered the question's first version, no earlier
    than the day it shipped (`added`): asked again at once only when it has changed since, and
    otherwise REASK_DAYS after that day, so a no given last week is not asked again now.
    """
    today = today or person.today()
    rec = asked().get(uid)
    if rec is None:
        known = next((u for u in REGISTRY if u.id == uid), None)
        rec, when, said = {"version": 1}, known.added if known else "", "you said no before"
    else:
        when = rec.get("no", "")
        said = f"you said no on {when}" if when else "you said no before"
    try:
        since = (today - dt.date.fromisoformat(when)).days if when else None
    except ValueError:
        since = None
    if int(rec.get("version") or 0) < version:
        return f"{said}, and it has changed since: {changed}" if changed else f"{said}"
    if since is not None and since >= REASK_DAYS:
        ago = f", {since} days ago" if said != "you said no before" else ""
        return f"{said}{ago}; it is asked once more in case that has changed"
    return ""


def _probe(code: str) -> str:
    """Run `code` in an interpreter of its own against this profile and return what it
    prints. The tools read the profile when imported, so a check that needs one
    of them runs it apart. A probe that fails reports nothing, never noise.

    While a look runs (`pending()`), every probe goes to that look's one interpreter
    (`_WORKER`); outside one, or where that interpreter cannot answer, the probe has a
    fresh interpreter to itself, as it always did."""
    if _LOOK:
        got = _ask(code)
        if got is not None:
            return got
    prelude = "import sys; sys.path[:0] = %r\n" % (_probe_path(),)
    try:
        r = subprocess.run([sys.executable, "-c", prelude + code], cwd=ROOT, env=_utf8_child(),
                           capture_output=True, text=True, timeout=PROBE_SECONDS,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


PROBE_SECONDS = 120


def _utf8_child() -> dict:
    """The environment for a Python this reads the output of as UTF-8: told to write it.
    On a Windows terminal in cp1252 (or PYTHONIOENCODING=cp1252) a probe printing "café –"
    wrote cp1252, which read back as two stand-in characters, and the same probe answered
    differently alone and inside a look."""
    return dict(os.environ, PYTHONIOENCODING="utf-8")


def _probe_path() -> list[str]:
    return [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]


# One interpreter answers every probe of one look. Sixteen fresh ones, each importing the
# same tools again, were three of the ten seconds the day's first check spent here
# (2026-10-22). Nothing a probe reads changes while a look runs, so a tool imported once
# gives each later probe what it would have read itself. Each probe still runs as `-c`
# code would: in a namespace of its own, with what it prints caught (its children's too,
# in the order a pipe gives them), and only a clean finish, or exit 0, counts. Replies
# travel on a copy of the interpreter's output, so nothing printed is taken for one.
_WORKER = r"""
import contextlib, io, json, os, sys, tempfile
sys.path[:0] = %r
reply = os.fdopen(os.dup(1), "w", encoding="ascii")
asked = sys.stdin
sys.stdin = open(os.devnull)
for line in asked:
    out, ok = io.StringIO(), True
    with tempfile.TemporaryFile() as raw:
        os.dup2(raw.fileno(), 1)
        try:
            with contextlib.redirect_stdout(out):
                exec(compile(json.loads(line), "<probe>", "exec"), {"__name__": "__main__"})
        except SystemExit as e:
            ok = e.code in (None, 0)
        except BaseException:
            ok = False
        raw.seek(0)
        text = raw.read().decode("utf-8", "replace") + out.getvalue()
    reply.write(json.dumps([ok, text]) + "\n")
    reply.flush()
"""
_LOOK: list = []        # while pending() runs: [that look's interpreter, or None before the first probe]


@contextlib.contextmanager
def _one_interpreter():
    _LOOK.append(None)
    try:
        yield
    finally:
        proc = _LOOK.pop()
        if proc is not None:
            _stop(proc)


def _start_worker():
    try:
        proc = subprocess.Popen([sys.executable, "-c", _WORKER % (_probe_path(),)], cwd=ROOT,
                                env=_utf8_child(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, encoding="ascii",
                                errors="replace")
    except OSError:
        return None
    replies: queue.Queue = queue.Queue()

    def read() -> None:
        # A thread, not select(): Windows cannot wait on a pipe.
        for line in proc.stdout:
            replies.put(line)
        replies.put("")                             # the interpreter has gone

    threading.Thread(target=read, daemon=True).start()
    proc.replies = replies
    return proc


def _stop(proc, kill: bool = False) -> None:
    try:
        if not kill:
            proc.stdin.close()
            proc.wait(timeout=5)
            return
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    try:
        proc.kill()
        proc.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _ask(code: str) -> str | None:
    """What `code` prints, from the look's interpreter; None where it cannot say, so the
    probe runs on its own instead. Out of time is "", as it is for a probe on its own,
    and never run twice."""
    proc = _LOOK[-1]
    if proc is None or proc.poll() is not None:
        proc = _LOOK[-1] = _start_worker()
        if proc is None:
            return None
    try:
        proc.stdin.write(json.dumps(code) + "\n")
        proc.stdin.flush()
        line = proc.replies.get(timeout=PROBE_SECONDS)
    except queue.Empty:
        _stop(proc, kill=True)
        _LOOK[-1] = None
        return ""
    except (OSError, ValueError):
        line = ""
    try:
        ok, out = json.loads(line)
    except (ValueError, TypeError):
        _stop(proc, kill=True)
        _LOOK[-1] = None
        return None
    return out.strip() if ok else ""


# Countries whose working week does not end on Saturday and Sunday. A country
# missing here keeps the Saturday and Sunday default, as every repo had before
# WEEKEND existed; one listed by mistake costs a question.
OTHER_WEEKEND = {"AF", "BD", "BH", "BN", "DJ", "DZ", "EG", "IL", "IQ", "IR", "JO", "KW", "LY",
                 "MV", "NP", "OM", "QA", "SA", "SD", "SY", "YE"}
# Markets whose postings are written in English. Elsewhere the English defaults
# for internal-only vacancies and the portal probe word match nothing.
ENGLISH_MARKETS = {"GB", "US", "CA", "AU", "NZ", "IE", "IN", "SG", "ZA", "PH", "MY", "HK",
                   "NG", "KE", "GH", "PK", "JM", "TT"}
# Resume headings written in English: a profile whose headings are not all in
# this set writes its documents in another language.
from locale_rules import ENGLISH_HEADINGS  # noqa: E402,F401  (one definition, beside the dates)


# ------------------------------------------------------------------ checks

def _boards() -> str:
    s = _mod("search")
    if s is None:
        return ""
    if not hasattr(s, "PORTALS"):
        return ("you were never told what LinkedIn's robots.txt says about the search every "
                "round sends it, and no boards were researched for you")
    if not hasattr(s, "PORTAL_RESEARCH"):
        return ("profile/search.py has no PORTAL_RESEARCH: nobody has looked for the job "
                "boards that serve your market, so rounds search LinkedIn and freehire only")
    rows = [r for r in (s.PORTAL_RESEARCH or []) if isinstance(r, dict)]
    if not any(_dated(r.get("checked")) for r in rows):
        return "PORTAL_RESEARCH holds no dated look at your job boards"
    return ""


def _learned_choices() -> str:
    try:
        import learned
    except ImportError:
        return ""
    waiting = learned.offers()
    if not waiting:
        return ""
    return "%d app improvement(s) would change something you chose: %s" % (
        len(waiting), "; ".join(learned.question(o) for _, o in waiting[:3]))


def _updates_choice() -> str:
    """A rule about how updates arrive that an older version wrote the wrong way round: read
    again with today's reader (learned.updates_said), the newest such rule says otherwise than
    person.json's app_updates (audit SV-1, PD-5: "App updates come by themselves; never ask
    him again" was written as when_asked). Asked once, never changed unasked: the person may
    have changed their mind on the page since."""
    try:
        import learned
        import person
        rows = [r for r in learned.entries()
                if "profile/person.json app_updates" in (r.get("applied_to") or [])]
        if not rows:
            return ""
        newest = rows[-1]
        meant = learned.updates_said(str(newest.get("said") or "")) or \
            learned.updates_said(str(newest.get("rule") or ""))
        have = "when_asked" if str(person.get("app_updates", "") or "").strip().lower() \
            == "when_asked" else "auto"
    except Exception:  # noqa: BLE001  no profile or no rules: nothing to ask
        return ""
    if not meant or meant == have:
        return ""
    say = {"auto": "by themselves", "when_asked": "only when you say"}
    return (f"your words \"{newest.get('said')}\" say updates come {say[meant]}, but the "
            f"setting says {say[have]}")


def _updates_said() -> str:
    """A rule about how updates arrive that an older version read as no setting at all: 4.15.0
    set nothing from "Only update when I say", and _updates_choice re-reads only the rules that
    did set it. Every active rule newer than the last one that set it is read again with
    today's reader (learned.updates_said); where the newest that says either way differs
    from the setting, the person is asked once (a To do card), never changed unasked: their
    setting may be what they chose since. Their answer is recorded as a rule of its own,
    newer than the one asked about, so it is never asked again (the review of 2026-11-11)."""
    if _updates_choice():
        return ""                       # the same question is already asked
    try:
        import learned
        rows = learned.entries()
        last = max((i for i, r in enumerate(rows)
                    if "profile/person.json app_updates" in (r.get("applied_to") or [])),
                   default=-1)
        meant, said = "", ""
        for r in reversed(rows[last + 1:]):
            # As learned.known_settings reads it: their own words first, then the rule.
            meant = learned.updates_said(str(r.get("said") or "")) or \
                learned.updates_said(str(r.get("rule") or ""))
            if meant:
                said = str(r.get("said") or "")
                break
        have = "when_asked" if str(person.get("app_updates", "") or "").strip().lower() \
            == "when_asked" else "auto"
    except Exception:  # noqa: BLE001  no profile or no rules: nothing to ask
        return ""
    if not meant or meant == have:
        return ""
    say = {"auto": "by themselves", "when_asked": "only when you say"}
    return (f"your words \"{said}\" say updates come {say[meant]}, but the setting says "
            f"{say[have]}")


def _brief_push() -> str:
    """A brief whose own run would send the phone notification, and nobody asked whether they
    want one: off until they say (brief.push_wanted), and asked once, as the setup sheet asks.
    Never asked where the brief already sent one: that copy keeps it (brief-push-kept)."""
    try:
        import brief
        import person
        import routines
        reg = routines.load()
        if routines._brief(reg) is None or routines.brief_pushes_itself(reg):
            return ""
        if person.get("brief_push", None) is not None or brief.pushed_before():
            return ""
    except Exception:  # noqa: BLE001  no profile or no brief: nothing to ask
        return ""
    return ("your brief can send a notification to your phone each morning, and nobody has "
            "asked whether you want one (profile/person.json has no brief_push), so it sends "
            "none")


def _brief_push_kept() -> str:
    """A brief that already sent a phone notification each morning, in a copy that never
    answered whether it wants one: it keeps it (brief.push_wanted), and the setting says so."""
    try:
        import brief
        import person
        if person.get("brief_push", None) is not None or not brief.pushed_before():
            return ""
    except Exception:  # noqa: BLE001  no profile: nothing to keep
        return ""
    return ("your brief has been sending a notification to your phone each morning, and "
            "profile/person.json has no brief_push, so Settings shows it off")


def _linkedin_plan() -> str:
    if _missing("networking", "LINKEDIN_PLAN"):
        return ("nobody has asked whether you pay for LinkedIn Premium (profile/networking.py "
                "has no LINKEDIN_PLAN), so notes are kept to a free account's 200 characters "
                "and no InMail is drafted")
    return ""


def _computer_linkedin() -> str:
    """Pending for someone who works on a computer and whose computer side is not set up and
    tested yet (`computer_ready` in profile/place.json, written by tools/computer.py ready)."""
    try:
        import place
        rec = place.place_record()
    except Exception:  # noqa: BLE001
        return ""
    if rec.get("works_on") not in ("computer", "both") and not rec.get("computer_chat"):
        return ""
    if rec.get("computer_ready"):
        return ""
    return ("your computer is not set up for Claude to start its LinkedIn reads there by "
            "itself, so a \"Find people\" run waits until you open a chat there")


def _profile_never_say() -> str:
    import learned
    got = learned.unadopted()
    if got:
        return ("profile/CLAUDE.md says never to write " + ", ".join('"%s"' % p for p, _ in got[:4])
                + (" and more" if len(got) > 4 else "") + ", and nothing checks a draft for it")
    return ""


def _learned_tidy() -> str:
    """Pending where a rule the person taught is said again, or contradicted, by a later one:
    rules recorded before 2026-10-31 were kept side by side, waiting for the person to say
    which stood, so the list grew repeats and opposites."""
    import learned
    try:
        got = learned.tidy(dry=True)
    except Exception:  # noqa: BLE001  no rules file yet: nothing to tidy
        return ""
    return (f"{len(got)} of the rules you taught are said again, or contradicted, by a later "
            "one" if got else "")


def _learned_review() -> str:
    """Pending until the rules made before 2026-10-31, kept side by side while the person was
    asked which stood, have been judged once for contradictions."""
    import learned
    try:
        if learned.reviewed():
            return ""
        got = learned.clashes()
    except Exception:  # noqa: BLE001  no rules file yet: nothing to judge
        return ""
    return f"{len(got)} pair(s) of your rules may contradict each other" if got else ""


def _built_in_rules() -> str:
    """Pending while a rule the person taught may only repeat something the app now does by
    itself (learned.BUILT_IN) and has not been judged against it: once after each update that
    adds such a behaviour, never again for the same one (learned.built_in_done)."""
    import learned
    try:
        got = learned.built_in_candidates()
    except Exception:  # noqa: BLE001  no rules file yet: nothing to judge
        return ""
    return (f"{len(got)} of the rules you taught may now be done by the app itself"
            if got else "")


def _public_holidays() -> str:
    """Pending where no rules cover the person's country and their own list has no date
    in the coming year: follow-ups would count every public holiday as a working day."""
    import datetime
    import holidays
    country, _region, extra = holidays._settings()
    if not country or country in holidays.RULES:
        return ""
    year = datetime.date.today().year + 1
    if any(str(d)[:4] == str(year) for d in extra):
        return ""
    return (f"no public holidays on file for {country} for {year} (profile/search.py "
            "PUBLIC_HOLIDAYS), so follow-ups count them as working days")


def _profile_reads() -> str:
    """Nothing to ask, ever: unset, PROFILE_READS reads in the browser a chat has
    (tools/network/reading.py reads_setting), and "paste" or "off" is the person's own word.
    The question it asked first, with its warnings, kept a computer chat from reading at all
    (the maintainer, 2026-10-25); the upgrade stays registered so a recorded no still names
    something."""
    return ""


def _people_sources() -> str:
    if _mod("networking") is not None and _missing("networking", "PEOPLE_SOURCES"):
        return ("/network searches the same default places for everyone (profile/networking.py "
                "has no PEOPLE_SOURCES), not the places people in your field, level and country "
                "are actually named")
    return ""


def _rulings_review() -> str:
    if _mod("search") is None:
        return ""
    n = _probe("import exclude; print(len(exclude.unreviewed()))").strip()
    if n.isdigit() and int(n):
        return (f"{n} postings are ruled out on reasons that say nothing about the rules they "
                "rest on, so they never lapse when your rules change, and some may be wrong "
                "by the rules as they are now")
    return ""


def _alumni_text() -> str:
    """The plan's alumni line names the employer they work at now, which is never searched."""
    if _mod("networking") is None:
        return ""
    code = ("import reading\n"
            "net = reading._NET\n"
            "lines = [str(r[1]) for r in (getattr(net, 'PEOPLE_SOURCES', None) or ())\n"
            "         if r and r[0] == 'alumni_employer' and len(r) > 1]\n"
            "h = reading.history()\n"
            "now = [n for names in h['employers'] if names[0] in h['current'] for n in names]\n"
            "print(sorted({n for n in now for t in lines if reading._has(n, t)}))")
    got = _probe(code).strip()
    if got and got != "[]":
        return (f"the alumni line in PEOPLE_SOURCES names {got.strip('[]')}, where you work "
                "now: alumni searches never search a current employer, so the line says "
                "something the plan does not do")
    return ""


def _brief_daily() -> str:
    """A morning brief on file, on or turned off by the person; else what is missing. On by
    default from 4.3 (the maintainer, 2026-10-29): a copy set up before then has none until
    the bell is pressed, and most never find the bell."""
    try:
        import routines
        reg = routines.load()
    except Exception:  # no profile or no registry yet: setup makes it
        return "no morning brief yet"
    return "" if any(routines._is_brief(r) for r in routines.work(reg or {})) else "no morning brief yet"


def _copy_line() -> str:
    """A scheduled task made before its stored prompt said how to get the copy, where its chat
    has none: one whose chat was deleted wakes a new, empty chat and replied "could not read
    the file" there every morning. Only the chat that answers the page mended it, so a copy
    with no page, and a welcome-back or shortlist task, never got the line (X-43). The trace:
    `copy` on each task in profile/routines.json (routines.py record, rebind, mended)."""
    try:
        import routines
        reg = routines.load()
    except Exception:  # noqa: BLE001  no registry: nothing scheduled
        return ""
    if routines.setup_of(reg) == "routines_screen":
        return ""                      # each run is a new chat with the copy ticked
    old = [r.get("name") or r.get("key") for r in routines.work(reg)
           if r.get("trigger_id") and not r.get("copy") and r.get("key") != routines.UPKEEP_KEY]
    return ("%s may not run if the chat it was set up in is gone" % ", ".join(old)) if old else ""


def _brief_own_chat() -> str:
    """A brief bound to the chat that answers the page (or any chat not made for it), or set
    to a fresh chat each run: the first fails every morning once that chat approves computer
    access, the second has no copy of the files (the maintainer, 2026-11-10). The trace:
    `own` on the brief's chat in profile/routines.json (routines.py record --own-chat)."""
    try:
        import routines
        reg = routines.load()
    except Exception:  # noqa: BLE001  no registry: nothing scheduled
        return ""
    r = next((x for x in routines.work(reg or {}) if routines._is_brief(x)), None)
    if not r or not r.get("trigger_id"):
        return ""
    why = routines.needs_own_chat(reg, r, None, routines.trusted_chat())
    if not why and routines.old_ops_shape(reg):
        # Read with no listing, the older shape said nothing was due, and the registry was
        # never rewritten (audit PD-7; review of fix/helpers, item 19).
        why = "the registry does not say which chat it runs in"
    return f"the morning brief needs a chat of its own ({why})" if why else ""


def _brief_own_steps() -> str:
    """A rule in profile/CLAUDE.md says every brief runs a script of the person's own, and
    brief.before does not name it, so nothing runs it (audit BT-4). The trace: the script in
    person.json `brief.before` (brief.py before --adopt)."""
    try:
        import brief
        got = brief.unadopted_steps()
    except Exception:  # noqa: BLE001  no profile: nothing of theirs to run
        return ""
    return ("your own rules say every brief runs " + ", ".join(got) +
            ", and nothing runs it") if got else ""


_RULE_CMD = re.compile(r"`(?:python3?\s+)?(tools/[\w/.-]+\.py)([^`]*)`")


def profile_command_problems() -> list[str]:
    """One line for each `python3 tools/...` command the person's own rules name
    (profile/CLAUDE.md) that the app has no tool for, whose step the tool does not have, or
    that only previews without --apply: a rule said to run export.py history without it, and
    nothing was ever saved (audit PD-9). Read from the tool's own source and usage lines,
    never by running it."""
    try:
        with open(person.path("CLAUDE.md"), encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, person.NoProfile):
        return []
    out: list[str] = []
    for tool, rest in _RULE_CMD.findall(text):
        cmd = (tool + rest).strip()
        path = os.path.join(ROOT, tool)
        if not os.path.isfile(path):
            line = f"`{cmd}`: the app has no {tool}"
        else:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            words = rest.split()
            sub = words[0] if words and re.fullmatch(r"[a-z][\w-]*", words[0]) else ""
            usage = [ln for ln in src.splitlines()
                     if re.search(r"python3 " + re.escape(tool) + r"\s+" + re.escape(sub) + r"\b",
                                  ln)] if sub else []
            if sub and f'"{sub}"' not in src and f"'{sub}'" not in src:
                line = f"`{cmd}`: {tool} has no step called {sub}"
            elif usage and any("--apply" in ln for ln in usage) and "--apply" not in rest:
                line = (f"`{cmd}`: without --apply it only shows what it would do and saves "
                        "nothing")
            else:
                continue
        if line not in out:
            out.append(line)
    return out


def _profile_commands() -> str:
    got = profile_command_problems()
    return ("your own rules name a command that does not do what they say: " + "; ".join(got)
            ) if got else ""


def _doorbells() -> str:
    """Every tap on the page left a comment sent to Claude that nothing resolved, so the Claude
    app shows a growing unread count on the page. The trace: the day in said_once.json."""
    try:
        import app_setup
        return "the page's old rings are still open" if app_setup.doorbells_pending() else ""
    except Exception:  # noqa: BLE001
        return ""


def _setup_reminder() -> str:
    """A page published, setup not finished, and nothing scheduled: nobody was ever reminded
    (X-23)."""
    try:
        import routines
        return "setup waits on the page, and nothing will remind them" if routines.remind_due() else ""
    except Exception:  # noqa: BLE001
        return ""


def _bar_unstated() -> str:
    """Postings a chat ruled out as failing "the candidate's bar" in a profile that states
    none: the job round's prompt had every chat judge employers on one person's words (pay,
    prestige or signal) and rule them out (X-18). Code re-cuts what the person's own rules
    exclude, so lifting every such ruling loses nothing."""
    if _mod("search") is None:
        return ""
    n = _probe("import bar, exclude; d = exclude._load(exclude.SEEN); print(0 if bar.applies() "
               "else sum(1 for e in d['seen'].values() if isinstance(e, dict) and str(e.get("
               "'status') or '').lower() == 'excluded' and str(e.get('exclusion_reason') or '')"
               ".startswith(\"candidate's bar\") and bar.verdict(e.get('company'))[0] != "
               "bar.EXCLUDED))").strip()
    n = int(n) if n.isdigit() else 0
    return ("%d posting(s) ruled out on a bar for employers your profile never set" % n) if n else ""


def _brief_watch() -> str:
    """What the brief's news watches, written from the person's own profile (4.7): a copy set
    up before then searched five fixed kinds of news for everyone (the maintainer, 2026-11-02:
    "dont different things affect everyones situation? why would you hardcode this")."""
    try:
        import brief
        return brief.watch_needs_writing()
    except Exception:  # noqa: BLE001  no profile yet: setup writes it
        return ""


def _work_place_retired() -> str:
    """Retired 2026-10-25 with the place question's "if you have one you can use, say yes":
    4.0 recommends no chat on a computer (the page and the cloud chats Claude makes do
    everything, and the page reads LinkedIn profiles itself in the desktop app), so nobody
    set up before the question needs to be asked it. /setup still asks it where a chat cannot
    tell, with no recommendation. Kept so a no recorded against it still reads."""
    return ""


def _ruling_parts() -> str:
    if _mod("search") is None:
        return ""
    n = _probe("import exclude; print(sum(len(es) for _, es in exclude.unnamed()))").strip()
    if n.isdigit() and int(n):
        return (f"{n} postings ruled out by your rules say nothing of which rule they rest on, "
                "so changing any one rule, one number even, puts every one of them back to be "
                "screened again")
    return ""


def _connections_export() -> str:
    if _mod("networking") is None:
        return ""
    root = os.environ.get("LJS_STATE") or ROOT
    root = root if os.path.isabs(root) else os.path.join(ROOT, root)
    if os.path.exists(os.path.join(root, "documents", "linkedin", "Connections.csv")):
        return ""
    if not os.environ.get("LJS_STATE") and os.path.exists(
            person.local_state("documents", "linkedin", "Connections.csv")):
        return ""                                   # in the main checkout, read from a worktree
    if _download_on_its_way():
        return ""
    if getattr(_mod("networking"), "CONNECTIONS_EXPORT", None) == "declined":
        u = by_id("connections-export")
        return again("connections-export", u.ask_version, u.changed)
    return ("every networking run starts from strangers, because the people you already know "
            "on LinkedIn are not on file (documents/linkedin/Connections.csv)")


def _download_on_its_way() -> bool:
    """A LinkedIn download asked for and not here yet (`export.py status` says "waiting"):
    the person has done their part, so neither download question is asked meanwhile. The
    chat taking it when it lands is export.py's, from the same record."""
    return _probe("import export; print(export.status()['state'])") == "waiting"


def _linkedin_history() -> str:
    """Pending where the connections from LinkedIn's download were saved but not its
    messages: the connections import kept Connections.csv alone until 2026-10-23, and a chat
    then read the messages straight from the download and kept none of them."""
    if _mod("networking") is None:
        return ""
    have = os.path.exists(person.local_state("documents", "linkedin", "Connections.csv"))
    if not have or os.path.exists(person.local_state("documents", "linkedin", "messages.csv")):
        return ""
    if _download_on_its_way():
        return ""
    if "linkedin-history" in asked():
        u = by_id("linkedin-history")
        return again("linkedin-history", u.ask_version, u.changed)
    return ("your LinkedIn connections are on file but not your messages from the same "
            "download (documents/linkedin/messages.csv), so no chat sees who you already talked to")


def _own_profile_review() -> str:
    """Pending until the person's own LinkedIn profile has been looked over once, or while a
    no stands (asked again after REASK_DAYS). Later looks are tools/network/own_profile.py
    `due`'s, not an upgrade's: it runs from every networking run and prints nothing until
    something has changed or outreach is plainly not working."""
    if _mod("networking") is None:
        return ""
    path = person.state("documents", "network", "own_profile_review.json")
    try:
        with open(path, encoding="utf-8") as fh:
            if (json.load(fh) or {}).get("reviews"):
                return ""
    except (OSError, ValueError, AttributeError):
        pass
    if "own-profile-review" in asked():
        u = by_id("own-profile-review")
        return again("own-profile-review", u.ask_version, u.changed)
    return ("your own LinkedIn profile has never been looked over for anything that would "
            "stop people replying (documents/network/own_profile_review.json)")


def _own_profile_steps() -> str:
    """After a yes: the export's profile files, from the registry's dated steps, or a paste."""
    return "\n".join(_surface_steps("linkedin-export-files")
                     + ["Or paste your profile's text here instead (headline, location, About, "
                        "each job with its dates, certifications). I only read it; nothing is "
                        "sent."])


def _contract() -> str:
    try:
        import portals
        on = portals.enabled()
        old = [n for n, v in on.items() if v and n not in portals.APP_PORTALS
               and portals.has_cli(n) and not portals.follows_contract(n)]
    except Exception:
        return ""
    if old:
        return (f"{', '.join(old)} {'is' if len(old) == 1 else 'are'} on but not built to the "
                f"portal contract (no `contract: 1`), so rounds skip {'it' if len(old) == 1 else 'them'}")
    return ""


def _unknown_portal() -> str:
    try:
        import portals
        gone = portals.unknown()
    except Exception:
        return ""
    if gone:
        return (f"profile/search.py PORTALS names {', '.join(gone)}, which this repo no longer "
                f"has, so it searches nothing")
    return ""


def _skills_headings() -> str:
    k = _mod("skills")
    if k is None:
        return ""
    labels = list(getattr(k, "LABELS", ()) or ())
    if not labels:
        return "profile/skills.py has no LABELS, so no resume renders (no Skills headings)"
    lines = {line for line, _ in labels} | set(getattr(k, "MERGE", {}) or {})
    lost = sorted({row[0] for row in getattr(k, "ITEMS", ()) or ()} - lines)
    if lost:
        return (f"skills in {', '.join(lost)} sit under no Skills line (LABELS or MERGE), "
                f"so they never print")
    return ""


def _fit_missing_shape() -> str:
    s = _mod("search")
    bad = [e for e in getattr(s, "FIT_MISSING", []) or [] if len(e) != 3] if s else []
    if bad:
        return (f"{len(bad)} FIT_MISSING entr{'y' if len(bad) == 1 else 'ies'} in the old "
                f"two-part shape, so scoring stops at the first posting")
    return ""


NETWORKING_NAMES = ("TITLE_SETS", "FUNCTION_TITLE", "HANDS_ON_TITLE", "HIRING_ROLE_NOUNS",
                    "HIRING_HEADLINE_NOUNS", "OTHER_FUNCTIONS", "OTHER_FUNCTIONS_MOVED",
                    "OWN_FUNCTION_WORDS")


def _networking() -> str:
    n = _mod("networking")
    if n is None:
        return ""
    gone = [x for x in NETWORKING_NAMES if not hasattr(n, x)]
    groups = dict(getattr(n, "TITLE_SETS", {}) or {})
    empty = [g for g in ("hiring_authority", "senior_ic", "function", "recruiting")
             if not groups.get(g)]
    if gone or empty:
        return ("/network has no titles of your own to search for ("
                + ", ".join(gone + [f"TITLE_SETS[{g!r}]" for g in empty if "TITLE_SETS" not in gone])
                + ")")
    return ""


LEVEL_NAMES = ("FIT_BELOW_LEVEL", "OPP_BELOW_LEVEL", "OPP_ABOVE_LEVEL")


def _level() -> str:
    gone = _missing("search", *LEVEL_NAMES)
    if gone:
        return (f"profile/search.py has no {', '.join(gone)}: no title is ranked down for "
                f"being above or below your level")
    return ""


def _themes() -> str:
    out = _probe("import allocate; print(', '.join(allocate.uncued_themes()))")
    return f"bullet themes no posting word matches: {out}" if out else ""


def _scoring() -> str:
    out = _probe("import prefilter\n"
                 "S = prefilter.person.module('search')\n"
                 "print(', '.join(q for q in getattr(S, 'SCRAPE_QUERIES', ())\n"
                 "                if prefilter.title_verdict(q)[0] == 'FAIL'))")
    if out:
        return (f"your own search titles fail your own title gate ({out}): the scoring "
                f"vocabulary is not yours")
    return ""


def _role_headings() -> str:
    out = _probe("import profile_facts as F\n"
                 "lines = F._read()\n"
                 "bad = [h for h in F._experience_headings(F.sections(lines), lines)\n"
                 "       if not F._ROLE_HEADING.match(h)]\n"
                 "print('; '.join(sorted(bad)))")
    if out:
        return (f"role headings the tools cannot read ({out[:120]}), so call-prep "
                f"documents carry none of your employers")
    return ""


# Each job in 01-candidate-profile.md is a role in roles.py, and one whose achievements the
# profile holds has bullets of its own. The renderer keyed everything by employer, so a
# promotion or a job with no bullets failed the resume's check with nothing kept, and a
# chat could make it pass by merging the two titles or deleting the job: what was lost is
# listed here, and the bullets of an older title at one employer are pointed at it.
_ROLES_CHECK = r"""
import json, re, person, profile_facts as F, company_key as K, allocate
lines = F._read()
secs = F.sections(lines)
roles = person.module("roles").ROLES
keys = allocate.role_keys(roles)
lib = person.module("bullets").LIB if person.exists("bullets.py") else {}
def same(a, b):
    return re.sub(r"\W+", " ", a.lower()).strip() == re.sub(r"\W+", " ", b.lower()).strip()
out = []
for h in sorted(F._experience_headings(secs, lines)):
    m = F._ROLE_HEADING.match(F._plain(h))
    if not m:
        continue
    title, company = m.group("title"), m.group("company")
    hit = [k for k, r in zip(keys, roles) if K.key(r["employer"]) == K.key(company)
           and same(r["title"], title)]
    if not hit:
        out.append("%s at %s is in your profile and not on your resume" % (title, company))
    elif hit[0] not in lib and any(re.match(r"\s*[-*]\s+\S", x) for x in secs.get(h, [])):
        out.append("%s at %s prints with no achievement, though your profile holds some"
                   % (title, company))
print("; ".join(out))
"""


def _roles_per_employer() -> str:
    if not (person.exists("roles.py") and person.exists("01-candidate-profile.md")):
        return ""
    return _probe(_ROLES_CHECK)


def _statement_templates() -> str:
    if not person.exists("CLAUDE.md"):
        return ""
    with open(person.path("CLAUDE.md"), encoding="utf-8") as fh:
        heads = [ln for ln in fh if ln.lstrip().startswith("#")]
    if not any(re.search(r"statement", h, re.I) for h in heads):
        return "profile/CLAUDE.md has no profile statement templates of your own"
    return ""


def _summary_statement() -> str:
    """The general resume is drafted from the profile's Canonical Summary Statement and stops
    without it; a setup that left the heading out met the stop every time (X-73)."""
    if not person.exists("01-candidate-profile.md"):
        return ""
    try:
        import general_resume
        if general_resume.canonical_summary():
            return ""
    except Exception:  # noqa: BLE001  nothing to read it with: nothing to say
        return ""
    return ("01-candidate-profile.md has no Canonical Summary Statement for the general resume "
            "to start from")


def _dropped_rows() -> str:
    """Contacts closed only because a queue was set aside before anything went: they read as
    dead ends, and discovery hid their employers as "already covered"."""
    found = _probe("import state; print(len(state.closed_but_dropped(state.load_contacts(), "
                   "state.load_threads())))")
    n = int(found) if found.isdigit() else 0
    return ("%d contact(s) closed when a queue was set aside, though nothing was ever sent to "
            "them" % n) if n else ""


def _export_repeats() -> str:
    """Messages an older import of LinkedIn's download logged a second time, its quote marks
    curly where the app's were straight: an old message added after the person's answer made
    someone already answered read as owed a reply, and a second reply was drafted (2026-11-05)."""
    found = _probe("import export; print(len(export.logged_twice(export._state().load_threads())))")
    n = int(found) if found.isdigit() else 0
    return ("%d message(s) from your LinkedIn download logged twice" % n) if n else ""


def _one_record() -> str:
    """One person kept as two rows, or as a first name with nothing else, in a book made
    before the export matched people by a shared message or a surname in the record: one
    recruiter showed as two cards, the one kept with no employer (2026-11-05). Only what the
    message log or exactly one of their own connections makes certain is counted."""
    found = _probe("import export; g = export.one_record(dry=True); "
                   "print(sum(len(r) for _, r in g['joined']), len(g['filled']))").split()
    n, f = (int(x) for x in found) if len(found) == 2 and all(x.isdigit() for x in found) \
        else (0, 0)
    said = []
    if n:
        said.append("%d contact(s) kept twice, the same message logged under both" % n)
    if f:
        said.append("%d contact(s) known by a first name only that your LinkedIn download names"
                    % f)
    return "; ".join(said)


def _follow_up_dates() -> str:
    """Contacts waiting on a reply with no follow-up date on their row: the brief reads the
    date from the row, so a thread imported from LinkedIn's download, or logged before the
    dates were written, was never brought back (2026-10-23)."""
    found = _probe("import person, state; c = state.load_contacts(); print(len("
                   "state.write_follow_ups([dict(r) for r in c], state.load_threads(), "
                   "person.today(), only_undated=True)))")
    n = int(found) if found.isdigit() else 0
    return ("%d contact(s) waiting on a reply have no follow-up date on their row" % n
            if n else "")


def _sends_counted_once() -> str:
    """Rows the app marked at the limit of unanswered messages while one note logged as a
    request and again as a message counted as two: their one follow-up was withheld and the
    line itself kept them there (the audit, 2026-11-10: about 60 people in one book)."""
    found = _probe("import person, state; c = state.load_contacts(); print(len("
                   "state.recount([dict(r) for r in c], state.load_threads(), person.today())))")
    n = int(found) if found.isdigit() else 0
    return ("%d contact(s) marked as at your limit of unanswered messages, though one of "
            "them was the same note logged twice" % n if n else "")


def _linkedin_limits_ignored() -> str:
    """Keys of LINKEDIN_LIMITS the app drops (connections_per_week, connections_per_day): one
    profile kept both, and nothing said they did nothing (the audit, 2026-11-10)."""
    found = _probe("import profile_set, schema\n"
                   "try:\n    v = profile_set.get('networking.py', 'LINKEDIN_LIMITS')\n"
                   "except Exception:\n    v = None\n"
                   "print(len(schema.ignored_limits(v if isinstance(v, dict) else {})))")
    n = int(found) if found.isdigit() else 0
    return ("profile/networking.py LINKEDIN_LIMITS sets %d request cap(s) the app never reads"
            % n if n else "")


def _stop_lines_dated() -> str:
    """Rows at the limit of unanswered messages that still carry a date, or the old "If still
    silent by the date, close it": the follow-up run skipped closed rows and old threads, so 19
    rows in one book kept them (the audit, 2026-11-10)."""
    found = _probe("import state; print(sum(1 for c in state.load_contacts() "
                   "if state.stop_line_dated(c)))")
    n = int(found) if found.isdigit() else 0
    return ("%d contact(s) at your limit of messages still carry a date or \"close it\"" % n
            if n else "")


def _gone_cold() -> str:
    """Conversations still read as waiting on a reply with no answer in months: imported
    threads from years back and notes sent a season ago were counted against their employer
    and shown as owed a follow-up (2026-11-10). Closing them as gone cold is instant, and a
    reply from them opens one again."""
    found = _probe("import person, state; c = state.load_contacts(); print(len("
                   "state.close_gone_cold([dict(r) for r in c], state.load_threads(), "
                   "person.today())))")
    n = int(found) if found.isdigit() else 0
    return ("%d conversation(s) with no answer in months still read as waiting on a reply" % n
            if n else "")


def _set_asides_dated() -> str:
    """Roles the person set aside before a set-aside had an end, with no day of their own:
    the first search after the update would bring every one back at once, or count it from a
    day long gone (2026-11-11). Giving each its months from the update is instant."""
    found = _probe("import exclude; print(len(exclude.undated_set_asides()))")
    n = int(found) if found.isdigit() else 0
    return "%d role(s) you set aside have no day to count from" % n if n else ""


def _notes_aside_dated() -> str:
    """First notes set aside on the page before "for now" had an end: each held them for good
    (2026-11-11). Giving each its months from the update is instant."""
    found = _probe("import exclude, person, state; c = state.load_contacts(); print(len("
                   "state.date_page_drops(c, person.today(), exclude.set_aside_days())))")
    n = int(found) if found.isdigit() else 0
    return "%d note(s) you set aside for now have no day to come back" % n if n else ""


def _drafts_before_a_role() -> str:
    """Drafts waiting on a card for someone who is on hold until a role is posted, and the
    follow-up on their offer to refer that code wrote the same for everyone: two cards
    carried one message with the name and the employer swapped (2026-11-10). Setting them
    aside (kept) is instant; each is written for its role once one is posted."""
    found = _probe("import followup_drafts; print(len(followup_drafts.drafts_before_a_role()))")
    n = int(found) if found.isdigit() else 0
    return ("%d draft(s) were written before the role they wait for" % n if n else "")


def _old_sweep_cursor() -> str:
    """3.7.0 kept the slow boards' resume point at documents/rounds/.sweep.json, beside the
    round summaries, and a person's own test that reads every documents/rounds/*.json as a
    round failed on it from their first round on. Moving it is instant: no web, no question."""
    old = person.state("documents", "rounds", ".sweep.json")
    return ("documents/rounds/.sweep.json sits among your round summaries, where a check "
            "that every file there is a round reads it" if os.path.exists(old) else "")


def _old_jobs_tweaks() -> str:
    """4.10 kept the record of tweaks to the person's search at documents/rounds/tweaks.json,
    among the round summaries, and a person's own test that reads every documents/rounds/*.json
    as a round failed on it (the maintainer's copy, 2026-11-06), as it had on the sweep cursor
    (sweep-cursor-moved). Moving it is instant: no web, no question."""
    old = person.state("documents", "rounds", "tweaks.json")
    return ("documents/rounds/tweaks.json sits among your round summaries, where a check that "
            "every file there is a round reads it" if os.path.exists(old) else "")


def _general_draft_kept() -> str:
    """4.12 kept a general resume as its PDF alone; from 4.13 its draft is kept beside it
    (documents/cv/general/draft.json), which its pencil changes. One made before has no
    pencil until it is made again from the profile, by the same command, which checks it."""
    try:
        import docpaths
        import general_resume
        have = docpaths.current_resume()
        kept = os.path.isfile(general_resume.draft_file())
    except Exception:  # noqa: BLE001  no profile, no resume: nothing to make again
        return ""
    return ("your resume for when no job is named was made before it could be changed with "
            "its pencil" if have and not kept else "")


def _job_alerts_retired() -> str:
    """Retired 2026-10-22, with the job-alert reader it asked about. It asked to read the
    person's LinkedIn alert emails into each round, and came back every month after a no;
    nothing asks for anyone's email now, and anything like an alert reaches them inside
    Claude (the brief, the job round). Kept so a no recorded against it still reads."""
    return ""


def _read_break() -> str:
    """Retired 2026-10-22. It wrote the app's break into the profile at the app's value, and
    written there it read as the person's own setting, so no later change to the pace could
    reach them. Since then the app sets no break at all, and `reading-limits-gone` takes
    out the line it wrote."""
    return ""


def _frozen_break() -> str:
    """Retired 2026-10-22: the break line it took out is one of the reading limits
    `reading-limits-gone` takes out with the rest."""
    return ""


def _reading_limits_gone() -> str:
    """A reading limit the app removed on 2026-10-22, still written in the profile: read by
    nothing, it says something the app no longer does."""
    import importlib
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
        reading = importlib.import_module("reading")
        found = reading.retired_settings()
    except Exception:
        return ""
    return ("profile/networking.py still sets %s, reading limits the app no longer has: "
            "profile reads go as fast as the browser loads them" % ", ".join(
                n for n, _f, _l in found)) if found else ""


def _move_and_area() -> str:
    """identity.moved and identity.area: an interview pack prepares honest small talk for
    someone who moved in the last year, and asks nothing of anyone else."""
    if not person.exists("person.json"):
        return ""
    ident = person.data("person").get("identity") or {}
    missing = [k for k in ("moved", "area") if k not in ident]
    if missing:
        return ("person.json has no identity.%s: an interview pack cannot tell whether you moved "
                "recently, or where you live" % " or identity.".join(missing))
    # A marker where the date goes: the first version of this upgrade had no form for a
    # profile that only confirms they were there by a date, and wrote one.
    moved = str(ident.get("moved") or "").strip()
    # "per employer": they tell each employer their own place (tools/told.py), so nothing
    # single is said for everyone, and the question is answered for good. Without it the
    # change stayed pending for someone who would never state one place, and a no lasted a
    # month.
    # "[CONFIRM: when you moved]": what this change's own instruction writes when the profile
    # cannot say. It is a question for the person, which `unconfirmed-facts` asks; counted
    # as pending here as well, this change could never finish, and /upgrade undid its own
    # work every session (2026-10-21).
    if CONFIRM.search(moved):
        return ""
    if not re.fullmatch(r"none|just arrived|per employer|(?:by\s+)?\d{4}-\d{2}(?:-\d{2})?",
                        moved, re.I):
        return ("person.json identity.moved is %r, not a date or \"none\": the interview pack's "
                "small talk for someone who moved recently stays off" % moved[:60])
    return ""


def _work_auth_employer() -> str:
    """WORK_AUTH["employer"]: the wording a recruiter or employer hears. Without it a call
    prep falls back to the senior networking line, which is not always the person's own
    employer-facing sentence."""
    net = _mod("networking")
    if net is None:
        return ""
    auth = getattr(net, "WORK_AUTH", None)
    if isinstance(auth, dict) and "employer" in auth:
        return ""
    return ("profile/networking.py WORK_AUTH has no \"employer\" line: a recruiter would hear "
            "the networking wording rather than your employer-facing one")


def _interview_prep() -> str:
    if person.exists() and not person.exists("07-interview-prep.md"):
        return "profile/07-interview-prep.md is missing: /interview has no STAR examples of yours"
    return ""


def _interview_tags() -> str:
    if not person.exists("07-interview-prep.md"):
        return ""
    found = _probe("import interview_pack; print('\\n'.join(interview_pack.untagged()))")
    bare = [t for t in found.splitlines() if t.strip()]
    if not bare:
        return ""
    return (f"{len(bare)} STAR stor{'y' if len(bare) == 1 else 'ies'} in "
            "profile/07-interview-prep.md say which questions they answer nowhere, so an "
            "interview pack cannot match them: " + "; ".join(bare[:3])
            + (f"; {len(bare) - 3} more" if len(bare) > 3 else ""))


def _process_postings() -> str:
    """A process folder with no job_posting.md: 3.7.0's `process` wrote none, and the app's
    folder test then failed the person's own CI, so they could not land work."""
    found = _probe("import interview_pack as p; print(len(p.missing_postings()))")
    n = int(found) if found.isdigit() else 0
    return ("%d hiring process folder(s) with no job_posting.md: the folder check in your own "
            "CI fails until each has one" % n) if n else ""


def _twin_folders() -> str:
    """One application in two folders: until 2026-10-26 verify_batch.py named the folder
    without the abbreviation outreach.py named it with, so its verify.json sat apart from
    the rest and the page never showed the checks that ran."""
    found = _probe("import docpaths as d; print(len(d.twin_folders()))")
    n = int(found) if found.isdigit() else 0
    return ("%d application(s) kept in two folders: the checks that ran sit apart from the "
            "note and documents, and the folder check in your own CI fails until each is "
            "one" % n) if n else ""


def _own_tests() -> str:
    """The person's own tests an update broke by changing what the app does, and the ones
    that read the app's source as text, which the next rewrite of that file breaks however
    it behaves. Read from the record the sync's own-tests run leaves; run again only when
    the tests have changed since. A test that used a part the update removed is the sync's
    question to the person (deleting their file is theirs to say), not this."""
    # The tests of the profile in use: with the example person in use (the app's own tests,
    # run in a person's repo), the person's tests are not its, and counting them turned the
    # app's "the example is fully upgraded" test red there.
    prof = os.path.normpath(person.path())
    if os.path.basename(prof) != "profile" or not os.path.isdir(os.path.join(prof, "tests")):
        return ""
    root = os.path.dirname(prof)
    import sync_app
    why = []
    # Read through own_tests_owed, which runs them again when the record is out of date: it
    # was keyed on the tests' own tree alone, so a record made before an update still read
    # "all pass" after it, and an update another chat took reached this copy with no record
    # changed at all (a person's copy, 2026-11-05: five failed, and this said nothing).
    sync_app.own_tests_owed(root, clean_too=True)
    rec = sync_app.own_tests_record(root)
    changed = [f[0] for f in (rec or {}).get("failures") or [] if len(f) > 2 and not f[2]]
    if changed:
        why.append("%d of your own test(s) check what an update changed: %s"
                   % (len(changed), "; ".join(changed[:3])))
    reads = sorted(f for f, v in sync_app.own_test_risks(root).items()
                   if any(x.startswith("the source of ") for x in v))
    if reads:
        why.append("%d of your own test file(s) read the app's code as text, so the next "
                   "rewrite of that code breaks them however it behaves: %s"
                   % (len(reads), "; ".join(reads[:3])))
    return "; ".join(why)


def _runtime_files() -> str:
    """The reading pace files an older copy kept in documents/network, which change on every
    read: once committed, every read left the repo dirty and the sync refused to run."""
    if not person.exists():
        return ""
    found = _probe("import reading as r, os, person as p; "
                   "print(sum(os.path.exists(p.state(*f)) for f in r.RUNTIME_FILES))")
    n = int(found) if found.isdigit() else 0
    return ("%d reading file(s) in documents/network that change on every read, so the "
            "repo is never clean and the sync refuses to run" % n) if n else ""


def _missing_texts() -> str:
    """Messages that drew a reply, logged without their words: what_works cannot learn from
    them. The message that drew a senior reader's reply in three hours reached the log days
    later, and earlier ones were logged as "approach" with no text."""
    # Never put to the person: the LinkedIn download they give every fortnight brings the
    # words in by itself (tools/network/export.py), so nobody is asked to paste them (the
    # maintainer, 2026-10-28: "make these types of decisions for them").
    return ""


# The wording the app's own defaults used to put in a person's voice settings: "I am" and
# "I would" at every sentence start, and an ask that repeated in every note. The person
# said it read "like someone who just learned English as a second language".
_STIFF = re.compile(r"^I am\b|\.\s+I am\b|^I would\b|\.\s+I would\b|how (?:your|the) team works",
                    re.I)


def _stiff_voice() -> str:
    """Their OPENER, ABOUT_ME or ASK in the stiff form the app used to write, and not a
    choice they recorded (learned.py locked)."""
    if not person.exists("networking.py"):
        return ""
    found = _probe("import json, person, learned; n = person.module('networking'); "
                   "locked = ' '.join(learned.locked()); "
                   "print(json.dumps([k for k in ('OPENER', 'ABOUT_ME', 'ASK') "
                   "if str(getattr(n, k, '') or '') and k not in locked]))")
    try:
        names = json.loads(found) if found else []
    except ValueError:
        return ""
    stiff = []
    for name in names:
        got = _probe("import person; print(getattr(person.module('networking'), %r, ''))" % name)
        if _STIFF.search(got):
            stiff.append(name)
    return ("%s in profile/networking.py still in the stiff wording the app used to write "
            "(\"I am\", \"I would\" at every sentence start)" % ", ".join(stiff)) if stiff else ""


def _campaign_notes() -> str:
    """Notes kept by hand for an employer with a hiring process, from before its living prep
    document existed: what was decided in them is lost to the next chat until it is folded
    in."""
    if not person.exists():
        return ""
    found = _probe("import json, interview_pack as p; print(json.dumps(p.handkept_notes()))")
    try:
        rows = json.loads(found) if found else []
    except ValueError:
        return ""
    if not rows:
        return ""
    return ("%d note file(s) kept by hand for a hiring process that its prep document has not "
            "folded in: %s" % (len(rows), "; ".join("%s (%s)" % (r["path"], r["company"])
                                                      for r in rows[:3])))


def _profile_consistency() -> str:
    """Facts a screen checks first, said differently in two places of the profile."""
    if not person.exists():
        return ""
    found = _probe("import json, profile_consistency as c; print(json.dumps(c.findings()))")
    try:
        rows = json.loads(found) if found else []
    except ValueError:
        return ""
    if not rows:
        return ""
    return ("your profile says %s differently in %d place(s): %s" % (
        " and ".join(sorted({r["fact"] for r in rows})), len(rows),
        "; ".join("%s:%s says \"%s\"" % (r["file"], r["line"], r["said"]) for r in rows[:3]
                  if r["said"])))


def _one_surface_check() -> str:
    """A rule in the person's CLAUDE.md that runs a script of their own before anyone is
    shown, where the script never calls the app's one check (tools/network/surface.py)."""
    if not person.exists("CLAUDE.md"):
        return ""
    found = _probe("import json, surface; print(json.dumps(surface.bypassing()))")
    try:
        rows = json.loads(found) if found else []
    except ValueError:
        return ""
    if not rows:
        return ""
    return ("your instructions check people with %s before showing them, which misses what "
            "the app's own check knows (holds, people written to on another channel, the "
            "employers you turned down, profile addresses)" % ", ".join(r for r, _ in rows))


def _readings_linked() -> str:
    """Contacts with no employer whose saved profile read names one: every check made per
    employer passed them by (the audit's NW-6, NW-28 and PD-20)."""
    found = _probe("import reading, state; print(len(reading.linkable(state.load_contacts())))")
    n = int(found) if found.isdigit() else 0
    return ("%d contact(s) with no employer recorded, though their read profile names one"
            % n) if n else ""


def _records_agree() -> str:
    """What the person's own records disagree about that a chat can put right, from the three
    checks nothing else runs: a letter on disk its row does not name (record_drafts.py
    check), a research file with no employer or named apart from its key (company_research.py
    check), and a reading kept under a name only one contact has (reading.py unlinked). What
    nobody can put right is said by those commands, and never keeps this waiting (the review
    of NW-23, NW-28 and NW-32, 2026-11-11)."""
    found = _probe(
        "import json, record_drafts, company_research, reading, state\n"
        "letters = len(record_drafts.unrecorded()['letters'])\n"
        "research = sum(1 for p in company_research.shape_problems() "
        "if p['why'] == 'no company' or p['why'].startswith('named apart'))\n"
        "readings = sum(1 for u in reading.unlinked(state.load_contacts()) if u['maybe'])\n"
        "print(json.dumps([letters, research, readings]))")
    try:
        letters, research, readings = json.loads(found) if found else (0, 0, 0)
    except (ValueError, TypeError):
        return ""
    parts = [("%d letter(s) on disk their application's row does not name" % letters)
             if letters else "",
             ("%d research file(s) without their employer, or named apart from it" % research)
             if research else "",
             ("%d reading(s) kept under a name their contact does not have" % readings)
             if readings else ""]
    return "; ".join(x for x in parts if x)


def _country() -> str:
    if person.exists("person.json") and not person.get("identity.country", ""):
        return ("person.json has no identity.country: paper size, working week and "
                "market language cannot follow it")
    return ""


def _market_week() -> str:
    if person.country() in OTHER_WEEKEND and _missing("search", "WEEKEND"):
        return "follow-up dates count Saturday and Sunday as the weekend, not yours"
    return ""


def _field_titles() -> set:
    """Every title the field tables hold, lower case: US English, from O*NET."""
    import glob
    import json
    out = set()
    for path in glob.glob(os.path.join(ROOT, "tools", "markets", "fields", "*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                rows = json.load(fh).get("titles") or []
        except (OSError, ValueError):
            continue
        for t in rows:
            out |= {re.sub(r"\s*\(.*\)$", "", str(v)).strip().lower() for v in t.get("value") or []}
    return out


def _market_language() -> str:
    c = person.country()
    if c and c not in ENGLISH_MARKETS:
        gone = _missing("search", "INTERNAL_ONLY", "INTERNAL_ONLY_TITLE", "CANARY_QUERY")
        if gone:
            return (f"{', '.join(gone)} still in English, so internal-only vacancies in your "
                    f"market's language are not cut and the portal probe may misfire")
        # Searches seeded only with the field tables' US English titles find little on a
        # market's own boards, where the work is posted in its own language.
        queries = [str(q).strip().lower() for q in getattr(_mod("search"), "SCRAPE_QUERIES", ())
                   or ()]
        english = [q for q in queries if q in _field_titles()]
        if english and len(english) == len(queries):
            return (f"your searches use only the field tables' English titles ({', '.join(english[:3])}), "
                    f"where your market posts this work in its own language")
    return ""


def _letter_language() -> str:
    if not person.exists("person.json"):
        return ""
    import locale_rules
    spelling = person.get("documents.spelling", "")
    if locale_rules.unknown_spelling(spelling):
        # An English variety the checks cannot read checks no spelling at all.
        return (f"your documents' spelling setting \"{spelling}\" is not one the checks "
                f"read, so no spelling is checked in them")
    heads = person.get("documents.headings", {}) or {}
    values = heads.values() if isinstance(heads, dict) else heads
    other = [v for v in values if isinstance(v, str) and v.strip().lower() not in ENGLISH_HEADINGS]
    if other and (person.get("documents.salutation_prefix", None) is None
                  or person.get("documents.page_label", None) is None):
        return "your letters print 'Dear' and 'Page' in a document written in another language"
    if other and locale_rules.dated_in_english(person.get("documents", {}) or {}):
        return ("your letters are dated in English although they are written in another "
                "language: the documents' language is not recorded")
    return ""


# What /setup, /upgrade or anyone else could not ground is written `[CONFIRM: what]`
# in the profile, never guessed. Each one is a question only the person can answer.
CONFIRM = re.compile(r"\[CONFIRM(?::\s*([^\]]*))?\]")
_SKIP_DIRS = {"tests", "__pycache__"}


def unconfirmed() -> list[tuple[str, str]]:
    """(profile file, what to confirm) for every `[CONFIRM: ...]` left in the profile."""
    try:
        root = person.directory()
    except person.NoProfile:
        return []
    out = []
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in _SKIP_DIRS and not d.startswith("."))
        for f in sorted(fns):
            if not f.endswith((".md", ".py", ".json")):
                continue
            path = os.path.join(dp, f)
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            rel = local_path.rel(path, os.path.dirname(root))
            out += [(rel, (m.group(1) or "").strip() or "a fact marked unconfirmed")
                    for m in CONFIRM.finditer(text)]
    rest = _built_without_rest(root)
    if rest:
        out.append(rest)
    return out


BUILT_REST = ("Where you studied (subject and years), any certificates, and the languages you "
              "speak")


def _built_without_rest(root: str) -> tuple[str, str] | None:
    """A resume built with Claude on the page before 3 November never asked its last question
    (where they studied, certificates, languages: the stranger audit, X-40), so a profile set
    up that way with no Education heading is asked it like any unconfirmed fact."""
    try:
        with open(os.path.join(root, "setup_answers.json"), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(got, dict) or (got.get("resume") or {}).get("source") != "build" \
            or got.get("history_rest"):
        return None
    try:
        with open(os.path.join(root, "01-candidate-profile.md"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    if re.search(r"^#{2,4}\s+Education\b", text, re.M | re.I):
        return None
    return (local_path.rel(os.path.join(root, "01-candidate-profile.md"),
                           os.path.dirname(root)), BUILT_REST)


def _unconfirmed() -> str:
    found = unconfirmed()
    if not found:
        return ""
    shown = "; ".join(f"{what} ({where})" for where, what in found[:3])
    return (f"{len(found)} fact{'s' if len(found) != 1 else ''} in your profile only you can "
            f"confirm: {shown}{' ...' if len(found) > 3 else ''}")


def _screen_flags() -> str:
    gone = _missing("search", "SCREEN_WRONG_FAMILY", "SCREEN_HOMONYMS")
    if gone:
        return (f"profile/search.py has no {' or '.join(gone)}: the screen flags no posting "
                f"as the wrong job family for you")
    return ""


def _required() -> str:
    """Every name a tool reads with no default, that this profile lacks. Read
    off the code (tools/profile_names.py), so a new required name is caught the
    day it ships, with nothing to register."""
    if not person.exists():
        return ""
    try:
        import profile_names
        names = profile_names.collect()
        keys = profile_names.collect_person()
    except Exception:
        return ""
    gone = [] if person.exists("person.json") else ["profile/person.json"]
    for module, entries in sorted(names.items()):
        need = [n for n, e in entries.items() if e["required"]]
        if not need:
            continue
        if not person.exists(module + ".py"):
            gone.append(f"profile/{module}.py")
            continue
        gone += [f"{module}.{n}" for n in _missing(module, *need)]
    for key, e in sorted(keys.items()):
        if e["required"] and person.exists("person.json") and person.get(key, None) is None:
            gone.append(f"person.json {key}")
    if gone:
        return "needed by the tools and missing: " + ", ".join(gone[:8]) + (" ..." if len(gone) > 8 else "")
    return ""


# A line in the profile that tells a draft to use a phrase the person later said never to
# use: "in outbound messages say 'I made the move'" stayed in two profile files after the
# person's never-say for it, so every draft read both. Only a line that prescribes the
# phrase counts; one that forbids it, or a sentence of theirs that merely contains it,
# is left alone (tone.py and voice_check.py still flag it in anything drafted).
_PRESCRIBES = re.compile(r"\b(?:say|says|said as|line is|write|use|wording is|phrase is)"
                         r"\W{0,4}$", re.I)
_FORBIDS = re.compile(r"\b(?:never|not|don'?t|avoid|without|no)\b", re.I)


def _prescribed() -> list[str]:
    try:
        import learned
        phrases = learned.never_say()
        d = person.directory()
    except (ImportError, person.NoProfile):
        return []
    if not phrases:
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if not name.endswith((".md", ".py")):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(lines, 1):
            for phrase, rx in phrases:
                for m in rx.finditer(line):
                    before = line[max(0, m.start() - 40):m.start()].rstrip(" \"'\u201c\u2018")
                    if _PRESCRIBES.search(before) and not _FORBIDS.search(before):
                        out.append(f"profile/{name}:{n} ({phrase!r})")
    return out


def _never_said() -> str:
    found = _prescribed()
    if not found:
        return ""
    return ("your profile still tells drafts to use wording you said never to use: "
            + "; ".join(found[:4]) + (f"; {len(found) - 4} more" if len(found) > 4 else ""))


def documents_lost() -> list[str]:
    """The application folders (documents/applications/<slug>) whose resume or letter the
    tracker names and no disk or commit holds, while their saved draft is there: a resume
    named in the person's own word (Lebenslauf, currículo) was never saved, and went with its
    chat (the stranger audit, 2026-11-03, X-22). Made again from the draft, they come back."""
    import csv_store
    path = person.state("job_search_tracker.csv")
    if not os.path.exists(path):
        return []
    drafts = {}
    for p in sorted(glob.glob(person.state("documents", "applications", "*", "draft.json"))):
        try:
            with open(p, encoding="utf-8") as fh:
                abbr = str((json.load(fh) or {}).get("abbr") or "").strip().upper()
        except (OSError, ValueError, AttributeError):
            continue
        if abbr:
            drafts[abbr] = os.path.basename(os.path.dirname(p))
    if not drafts:
        return []
    lost = []
    for r in csv_store.read_rows(path):
        for col in ("cv_file", "cover_letter_file"):
            rel = str(r.get(col) or "").strip()
            if not rel or os.path.exists(person.state(rel)):
                continue
            abbr = os.path.splitext(os.path.basename(rel))[0].rsplit("_", 1)[-1].upper()
            if abbr in drafts:
                lost.append(drafts[abbr])
    return sorted(set(lost))


def _documents_lost() -> str:
    lost = documents_lost()
    if not lost:
        return ""
    return (f"{len(lost)} application{'s' if len(lost) != 1 else ''} whose tailored resume or "
            f"letter was never saved: {', '.join(lost[:3])}" + (" ..." if len(lost) > 3 else ""))


# ------------------------------------------------------------------ registry

REGISTRY: tuple[Upgrade, ...] = (
    Upgrade("documents-saved", "2026-11-03",
            "every tailored resume and letter your applications name is saved again, made "
            "from its saved draft",
            _documents_lost, "for each folder the check names, python3 tools/fit_to_page.py "
            "documents/applications/<folder>/draft.json, which makes its resume and letter "
            "again from the saved draft; then tools/verify_batch.sh on them, and commit the "
            "files with the rest (python3 tools/save_state.py now saves them whatever their "
            "name). Never send anything", "edit", "~2 min an application", conditional=True,
            priority=2),
    Upgrade("unconfirmed-facts", "2026-10-15",
            "every fact in your profile confirmed by you, never guessed",
            _unconfirmed, "ask the person, at most three at the end of a session, and write "
            "each answer where its [CONFIRM] marker was", "question", "~1 min a fact",
            priority=2, needs="you",
            every=lambda: [f"{what} ({where})" for where, what in unconfirmed()]),
    Upgrade("required", "2026-10-15",
            "every setting the tools need and cannot default, written for you",
            _required, "/setup --section <the section that writes it>", "question", "~5 min",
            priority=1),
    Upgrade("boards", "2026-10-14",
            "the job boards that serve your market found, checked and built, so rounds search them",
            _boards, "/setup --section boards", "research", "~15 min a board",
            names=("search.PORTAL_RESEARCH", "search.PORTALS"),
            priority=2),
    Upgrade("portal-contract", "2026-10-15",
            "your own portals searched in every round, not only by hand",
            _contract, "/add-portal <the portal named>: check it takes the round's flags, "
            "then add `contract: 1`", "research", "~10 min a portal",
            priority=2),
    Upgrade("missing-portal", "2026-10-14",
            "no portal switched on that no longer exists",
            _unknown_portal, "/add-portal to build it again, or take it out of PORTALS",
            "question", "~2 min",
            priority=2),
    Upgrade("never-said", "2026-10-18",
            "no line in your profile telling a draft to use wording you said never to use",
            _never_said, "for each line listed, rewrite it so it no longer tells a draft to use "
            "the phrase: keep the fact, take the wording from the later rule that forbade it "
            "(python3 tools/learned.py list), change nothing else; one commit, and its git "
            "revert line in the reply", "research", "~2 min", priority=2),
    Upgrade("job-alerts", "2026-10-15",
            "nothing: retired with the job-alert email reader, since nothing asks for your email",
            _job_alerts_retired, "nothing to do", "question", "~0 min", priority=3),
    Upgrade("learned-choices", "2026-10-15",
            "app improvements to things you chose, offered rather than imposed",
            _learned_choices, "ask each `python3 tools/learned.py offers` question; record the "
            "answer with `python3 tools/learned.py decide <n> keep|switch` and apply a switch",
            "question", "~1 min",
            priority=3,
            needs="you",
            ask="An update would change something you chose yourself. Want to hear the new way "
                "and decide, or keep yours for now?"),
    Upgrade("linkedin-plan", "2026-10-15",
            "connection notes and InMail sized to the LinkedIn account you actually have",
            _linkedin_plan, "write LINKEDIN_PLAN = \"free\" or \"premium\" in profile/networking.py "
            "from their answer", "question", "~1 min",
            names=("networking.LINKEDIN_PLAN",),
            priority=2,
            needs="you",
            ask="Do you pay for LinkedIn Premium?",
            why_ask="It decides how long your connection messages can be, and whether you can "
                    "message people you are not connected to."),
    Upgrade("people-sources", "2026-10-17",
            "people found where people in your field are actually named, not only by job title",
            _people_sources, "research and write PEOPLE_SOURCES in profile/networking.py as "
            "/setup's voice section says (its 'Where their people are named' step), and only "
            "that", "research", "~5 min",
            names=("networking.PEOPLE_SOURCES",),
            priority=2),
    Upgrade("rulings-review", "2026-10-17",
            "every posting still ruled out is ruled out by your rules as they are now",
            _rulings_review, "follow `python3 tools/exclude.py review`: judge each group "
            "against the four hard cuts (eligibility, language, a professional credential, a "
            "discipline the profile names as a different job) and the person's own "
            "deal-breakers in profile/CLAUDE.md. A group that is one of those: `exclude.py stamp "
            "\"<words>\" --basis rules`, with `--rests-on \"<part>\"` when it plainly rests on "
            "one part `exclude.py parts` lists, or `--basis person` where it is their own call. "
            "Any other "
            "(a salary, years, seniority, a degree, a score): `exclude.py lift \"<words>\" --why "
            "\"the current rules rank this, never cut it\"`. Report the count per group, and list "
            "the person's own calls so they can say if one has changed", "research", "~5 min",
            priority=2),
    Upgrade("alumni-text", "2026-10-18",
            "the plan's description of its alumni searches matches what they search",
            _alumni_text, "rewrite only the description of the alumni_employer entry in "
            "PEOPLE_SOURCES (profile/networking.py) to name the employers they have left, the "
            "one whose alumni reply most first (`python3 tools/network/sources.py` shows the "
            "order), and never the one they work at now; change nothing else", "edit", "~1 min",
            priority=4),
    Upgrade("public-holidays", "2026-10-19",
            "follow-ups that skip your country's public holidays, the way offices do",
            _public_holidays, "look up the person's country's public holidays (and their "
            "region's, from identity.location) for this year and next on its government's own "
            "page, and write them as ISO dates in profile/search.py PUBLIC_HOLIDAYS with the "
            "page's URL in a comment beside them; `python3 tools/holidays.py` then lists them",
            "research", "~5 min",
            names=("search.PUBLIC_HOLIDAYS",),
            conditional=True,
            priority=3),
    Upgrade("profile-never-say", "2026-10-19",
            "every phrase your own rules say never to write caught in every draft, not only "
            "when the drafting model remembers it",
            _profile_never_say, "python3 tools/learned.py adopt-profile-rules", "instant",
            command=("python3", "tools/learned.py", "adopt-profile-rules"),
            paths=("profile/learned.json",),
            priority=2),
    Upgrade("learned-tidy", "2026-10-31",
            "the rules you have taught it kept to one each: a rule you said again, or changed "
            "your mind on, gives way to the newest, and nothing it held is lost",
            _learned_tidy, "python3 tools/learned.py tidy", "instant",
            command=("python3", "tools/learned.py", "tidy"),
            paths=("profile/learned.json",),
            priority=3),
    Upgrade("learned-review", "2026-10-31",
            "where you changed your mind, the rule you gave last is the one followed, with the "
            "older one put away",
            _learned_review, "`python3 tools/learned.py tidy --clashes` lists the pairs; for "
            "each, retire the older only where the later plainly reverses it "
            "(`python3 tools/learned.py retire <n>`); where they only share words, or it is not "
            "certain, leave both. At most one pair you truly cannot call, and that changes what "
            "is drafted, goes on their page: `python3 tools/learned.py ask <older> <newer>`. "
            "Then `python3 tools/learned.py tidy --reviewed`",
            "edit", "~3 min", priority=3),
    Upgrade("built-in-rules", "2026-11-06",
            "rules you taught it that the app now does by itself come off your list, marked "
            "Now part of the app, so the list holds only what is yours",
            _built_in_rules, "`python3 tools/learned.py built-in` lists each rule the app may "
            "now do by itself, beside what the app does; put one away only where that covers "
            "all of it (`python3 tools/learned.py built-in --retire <n>=<id>`), leave the rest, "
            "then `python3 tools/learned.py built-in --done`. The line it prints for the person "
            "is the commit's body, word for word; with none, the body says nothing changed",
            "edit", "~2 min", priority=4),
    Upgrade("brief-daily", "2026-10-29",
            "a short note every morning on your Brief: what is due today, and news that matters "
            "to your search",
            _brief_daily, "in a cloud chat, with or without a page: `list_triggers` (every "
            "page), `python3 tools/routines.py brief --triggers <each page> --own-initiative` "
            "(it makes the brief a chat of its own with the copy attached, never the chat "
            "that answers the page), the calls it prints, and the one line it prints to say, which names where "
            "and when it comes. In a chat on their computer it prints the line instead (one "
            "press of the bell starts it from the cloud; with no page, it says to make the page "
            "first): put it on their page as a To do", "edit", "~1 min", priority=3),
    Upgrade("brief-copy-line", "2026-11-03",
            "your morning brief and your other scheduled tasks run even when the chat they "
            "were set up in is gone",
            _copy_line, "`list_triggers` (every page), `python3 tools/routines.py brief "
            "--triggers <each page>`, make each `mend` call it prints, then `python3 "
            "tools/routines.py mended`. Say nothing about it", "edit", "~1 min", priority=2),
    Upgrade("brief-own-chat", "2026-11-10",
            "your morning brief keeps coming every day, in a chat of its own, whatever you "
            "approve in your other chats",
            _brief_own_chat, "in a cloud chat: `list_triggers` (every page), `python3 "
            "tools/routines.py brief --triggers <each page>`, and make each `move` call it "
            "prints, in order, stopping at the first that fails (where it names get_session "
            "and `routines.py adopt`, those: a chat made for the brief is recorded as its own). In a chat on their computer "
            "nothing: the chat in the cloud that answers the page does it at its daily tidy-up. "
            "Say nothing about it", "edit", "~1 min", priority=1),
    Upgrade("brief-own-steps", "2026-11-10",
            "a step your own rules say every brief runs is run by the brief itself, every "
            "morning, without anyone remembering it",
            _brief_own_steps, "python3 tools/brief.py before --adopt", "instant",
            command=("python3", "tools/brief.py", "before", "--adopt"),
            paths=("profile/person.json",),
            priority=2),
    Upgrade("profile-commands", "2026-11-11",
            "every command your own notes tell Claude to run exists and does what the note says",
            _profile_commands, "for each command `python3 tools/profile_upgrades.py --check "
            "profile-commands` lists, read the tool's own usage (the top of its file) and correct "
            "the command in profile/CLAUDE.md to the one that does what the rule says (add "
            "--apply where the rule means to save). Say nothing about it", "edit", "~2 min",
            priority=2, every=lambda: profile_command_problems()),
    Upgrade("doorbells", "2026-11-04",
            "your page stops showing a number of unread messages that never goes away",
            _doorbells, "`python3 tools/app.py doorbells` prints what to do: resolve each "
            "page thread whose first comment is a ring, no other, then `python3 tools/app.py "
            "doorbells --done`. Say nothing about it", "edit", "~1 min", priority=3),
    Upgrade("setup-reminder", "2026-11-03",
            "one reminder a day after your page went up, if setup is waiting on you there",
            _setup_reminder, "`python3 tools/routines.py remind`, and make the call it prints, "
            "then the `reminded` line it gives. Say nothing about it", "edit", "~1 min",
            priority=2),
    Upgrade("bar-unstated", "2026-11-03",
            "jobs at employers a chat ruled out on a bar you never set come back to your search",
            _bar_unstated, "python3 tools/exclude.py lift \"candidate's bar\" --why \"the "
            "profile states no bar for employers\"", "instant",
            command=("python3", "tools/exclude.py", "lift", "candidate's bar", "--why",
                     "the profile states no bar for employers"),
            paths=("job_scraper/seen_jobs.json",), conditional=True, priority=2),
    Upgrade("brief-watch", "2026-11-02",
            "the news in your brief follows what moves your own search, in your words, and you "
            "can change it in Edit the brief",
            _brief_watch, "read the person's profile (profile/CLAUDE.md and "
            "01-candidate-profile.md), then write what their brief watches: `python3 "
            "tools/brief.py watch --help` says the shape and what belongs on it; `python3 "
            "tools/brief.py watch write` with the list. Report the list in one plain line",
            "edit", "~1 min", priority=2),
    Upgrade("work-place", "2026-10-18",
            "nothing: retired, since no chat on a computer is recommended any more",
            _work_place_retired, "nothing to do", "question", "~0 min", priority=4),
    Upgrade("ruling-parts", "2026-10-17",
            "a change to one of your rules puts back only the postings ruled out by that rule",
            _ruling_parts, "run `python3 tools/exclude.py cite`, then follow `python3 "
            "tools/exclude.py unnamed`: for each group, `exclude.py restamp \"<words>\" "
            "--rests-on \"<part>\"` where the reason plainly rests on one part `exclude.py parts` "
            "lists (a blocker row, a gate setting), and `--rests-on all` where it rests on more "
            "than one or it is not plain which. Never a part the reason does not plainly rest "
            "on: a wrong part keeps a posting out after the rule it really rests on changes. "
            "Report the count per part", "research", "~3 min",
            priority=3),
    Upgrade("connections-export", "2026-10-17",
            "every networking run starting from the people you already know",
            _connections_export, "save what they attach with `python3 tools/network/sources.py "
            "import-connections <file>` (the whole download, the ZIP or its folder, is saved "
            "for the files the app reads and its message history imported, and the line it "
            "prints says so), or, if they would rather not, write "
            "CONNECTIONS_EXPORT = \"declined\" in profile/networking.py and run `python3 "
            "tools/profile_upgrades.py --no connections-export`. While the file is on its way, "
            "after giving the steps, offer once, in its words, what `python3 "
            "tools/network/sources.py while-you-wait` prints: one employer's 1st-degree "
            "people, pasted, go through `python3 tools/network/sources.py people-paste "
            "\"<employer>\" <file>`, and the steps for that, if they want them, are `python3 "
            "tools/claude_surfaces.py steps linkedin-people-at-employer`", "question", "~2 min",
            names=("networking.CONNECTIONS_EXPORT",),
            priority=3,
            needs="you",
            ask_version=2,
            changed="networking now finds people in bulk from any chat, and your own "
                    "connections are the first and strongest place it looks",
            ask="Want me to start from the people you already know on LinkedIn? That means "
                "requesting one file from LinkedIn, which arrives anything from ten minutes "
                "to a day later, and I'll walk you through it. Yes, or not now?",
            steps=lambda: "\n".join(_surface_steps("linkedin-connections")
                                    + ["I only read it. Nothing is sent to anyone."]),
            why_ask="People you already know can be messaged directly, with no connection "
                    "request, and they reply far more often than strangers."),
    Upgrade("computer-linkedin", "2026-11-09",
            "LinkedIn read on your own computer by itself, with no chat for you to keep open "
            "there",
            _computer_linkedin, "/setup --section computer (COMPUTER.md, \"Use your computer "
            "for LinkedIn\"): each step from tools/claude_surfaces.py, checked after it, ending "
            "with python3 tools/computer.py ready --name <the computer>. A no is python3 "
            "tools/profile_upgrades.py --no computer-linkedin", "question", "~5 min",
            conditional=True,
            priority=2,
            needs="you",
            ask="Want Claude to read LinkedIn on your computer by itself, so Find people never "
                "waits for you? It takes about five minutes, once. Yes, or not now?",
            # The plan only: each screen's own steps come from the registry at its stage
            # (remote-control-settings, browser-pane-stay-signed-in), checked that day.
            steps=lambda: "\n".join([
                "To let Claude read LinkedIn on your computer by itself:",
                "1. On your computer, switch it on once in the Claude app's settings: I give you "
                "each switch as you go.",
                "2. Approve the one card Claude shows you, once.",
                "3. Sign in to LinkedIn in Claude's browser there, and keep the sign-in.",
                "Then I check it works by reading one profile."]),
            why_ask="Reading someone's profile is what makes a note fit them, and only your "
                    "own computer, signed in to LinkedIn, can do it."),
    Upgrade("linkedin-history", "2026-10-23",
            "every chat seeing your past LinkedIn conversations, not only the ones written here",
            _linkedin_history, "on their computer, first `python3 tools/network/export.py take "
            "--find`: it looks for the download in Downloads, Desktop and Documents and, found, "
            "saves it and imports the history, and nothing is asked. Only where it finds none, "
            "ask; after a yes, `python3 tools/network/export.py take <what they attach>`. A no "
            "is `python3 tools/profile_upgrades.py --no linkedin-history`", "question", "~2 min",
            priority=2,
            needs="you",
            ask="You gave me your LinkedIn connections before, but not the messages in the same "
                "download. Can I have that download again, so every chat sees who you've "
                "already talked to? Yes, or not now?",
            steps=lambda: "\n".join(["Attach the same LinkedIn download you gave me before, "
                                     "the ZIP or the folder it opened into. I only read it; "
                                     "nothing is sent to anyone. If it's gone:"]
                                    + _surface_steps("linkedin-export-files")),
            why_ask="Without your messages, a chat can't see who you've already talked to, and "
                    "may write to someone twice."),
    Upgrade("own-profile-review", "2026-10-21",
            "your own LinkedIn profile looked over once for anything that would stop people "
            "replying: a wrong city, a job that does not match your resume, a certificate you "
            "do not hold, a confidential search on show",
            _own_profile_review, "after a yes, get their own profile: the export's profile "
            "files saved with `python3 tools/network/export.py save <file>... --only profile`, "
            "or their paste written into the shape `python3 tools/network/own_profile.py shape` "
            "prints (their page read in their own browser only where PROFILE_READS is "
            "\"browser\"). Then `python3 tools/network/own_profile.py check`, ask its yes-or-no "
            "questions once, then `own_profile.py brief` and judge it as it says; record what "
            "they decide with `own_profile.py decide`, and a finding they do not care about "
            "with `own_profile.py dismiss`. A no is `python3 tools/profile_upgrades.py --no "
            "own-profile-review`", "question", "~5 min",
            priority=3,
            needs="you",
            ask="Want me to look over your own LinkedIn profile once, for anything that would "
                "stop people replying?",
            steps=_own_profile_steps,
            why_ask="A stranger reads your profile before replying, and one thing in it that "
                    "contradicts your resume can cost every note you send."),
    Upgrade("profile-reads", "2026-10-17",
            "a note to each person built from their own profile, not a search snippet",
            _profile_reads, "write PROFILE_READS = \"browser\" or \"paste\" in "
            "profile/networking.py from their answer; \"paste\" again is also `python3 "
            "tools/profile_upgrades.py --no profile-reads`", "question", "~1 min",
            priority=2,
            needs="you",
            ask_version=2,
            changed="finding people no longer needs any read, and a read is now only of the best "
                    "ten a run finds, paced, in a chat on your computer",
            ask="Should I read the LinkedIn profiles of the people I write to in your browser, "
                "or work from ones you paste?",
            steps=lambda: ("With your page open in the Claude desktop app, it reads each one in the "
                           "browser there.\n"
                           "Pasting instead: open their profile, select all, copy, and paste it "
                           "here."),
            why_ask="A message that mentions something real about the person gets far more "
                    "replies than one built from a search result."),
    Upgrade("screen-flags", "2026-10-15",
            "postings from the wrong job family for you flagged, in your field's terms",
            _screen_flags, "/setup --section search", "question", "~5 min",
            names=("search.SCREEN_WRONG_FAMILY", "search.SCREEN_HOMONYMS"),
            priority=3),
    Upgrade("skills-headings", "2026-10-14",
            "a resume that renders, its Skills lines headed in your own words",
            _skills_headings, "/setup --section documents", "question", "~5 min",
            names=("skills.LABELS", "skills.MERGE"),
            priority=1),
    Upgrade("fit-missing-shape", "2026-10-14",
            "scoring that runs: each FIT_MISSING entry as (pattern, points, why)",
            _fit_missing_shape, "/setup --section search: rewrite each FIT_MISSING entry as "
            "(pattern, points, why); the example weighs one at -8", "edit", "~2 min",
            priority=1),
    Upgrade("networking-titles", "2026-10-14",
            "/network searching for your own colleagues and hiring managers, not a data team's",
            _networking, "/setup --section voice", "research", "~10 min",
            names=tuple(f"networking.{n}" for n in NETWORKING_NAMES),
            priority=1),
    Upgrade("level", "2026-10-14",
            "titles above or below your level ranked down in your terms",
            _level, "/setup --section search (and drop any junior-title bonus added to "
            "cancel the old built-in penalty)", "question", "~5 min",
            names=tuple(f"search.{n}" for n in LEVEL_NAMES),
            priority=2),
    Upgrade("bullet-themes", "2026-10-14",
            "resume bullets chosen for each posting by the words your field uses",
            _themes, "/setup --section history: add THEME_CUES in profile/bullets.py for "
            "each theme named", "research", "~10 min",
            names=("bullets.THEME_CUES", "bullets.CUE_WHOLE_WORD"),
            conditional=True,
            priority=3),
    Upgrade("scoring-vocabulary", "2026-10-14",
            "postings scored and gated on your field's words, not the example analyst's",
            _scoring, "/setup --section search: write the FIT_* and OPP_* vocabulary for "
            "your field, then score two or three invented postings", "research", "~20 min",
            priority=2),
    Upgrade("role-headings", "2026-10-14",
            "call-prep documents that carry your employers and their evidence",
            _role_headings, "/setup --section history: write each role heading as "
            "'Title - Employer (dates), City', then python3 tools/network/prep.py --all",
            "edit", "~2 min",
            priority=3),
    Upgrade("summary-statement", "2026-11-03",
            "a general resume made at once, from your profile's own summary",
            _summary_statement, "/setup --section history: write two or three sentences from "
            "the profile in 01-candidate-profile.md, under the exact heading the example "
            "has (## Canonical Summary Statement), as a '> ' quote", "edit",
            "~2 min", priority=2),
    Upgrade("roles-per-employer", "2026-11-03",
            "every job on your resume under its own title and dates, a promotion included",
            _roles_per_employer, "/setup --section history: give each job in "
            "01-candidate-profile.md its own ROLES entry in roles.py, most recent first; an "
            "older title at the same employer takes its bullets under a LIB key of its own, "
            "named by lib= on its role; a job with none prints as its title line",
            "edit", "~5 min",
            priority=2),
    Upgrade("statement-templates", "2026-10-14",
            "resume summaries drafted from your own statement templates",
            _statement_templates, "/setup --section voice", "question", "~5 min",
            priority=3),
    Upgrade("interview-prep", "2026-10-14",
            "/interview working from your own STAR examples",
            _interview_prep, "/setup --section history", "question", "~10 min",
            priority=3),
    Upgrade("interview-tags", "2026-10-19",
            "each of your interview stories matched to the questions it answers",
            _interview_tags, "add one `Use for:` line to each STAR story listed, naming the "
            "interview questions it answers, read from the story's own words (setup.md's "
            "history section says how); change nothing else in the file", "edit", "~2 min",
            priority=2),
    Upgrade("profile-consistency", "2026-10-19",
            "your pay band, notice, sponsorship and permit answer said the same way everywhere",
            _profile_consistency, "python3 tools/profile_consistency.py, then ask the person "
            "which is right for each fact it lists and correct the other place(s); never pick "
            "for them. Where they say both are right on purpose, record that with "
            "`python3 tools/profile_consistency.py --reviewed <file>:<line>` and change "
            "nothing", "question", "~2 min", priority=2, needs="you",
            ask="Your profile gives two different answers on something a recruiter checks "
                "first. Can I show you which, so you pick the right one?",
            why_ask="A form, a letter and an interview pack each read one of them, and a "
                    "recruiter remembers whichever they heard first."),
    Upgrade("one-surface-check", "2026-11-10",
            "one check, the app's own, decides who is shown to you for a message, with your "
            "own rules in it",
            _one_surface_check, "for each script it names: read the script and the rule in "
            "profile/CLAUDE.md that runs it. Write the rule's own numbers into "
            "profile/networking.py (its days since anyone was last written to as "
            "QUIET_AFTER_SEND_DAYS, its unanswered limit as MAX_UNANSWERED) where they are "
            "not set already; change the rule to run `python3 tools/network/surface.py "
            "\"<name>\" --company \"<employer>\"` (people new to you) and `python3 "
            "tools/open_actions.py --due` (people already written to) instead; and make the "
            "script a thin call to surface.check() so anything that still runs it gets the "
            "same answer. Keep every rule the script had that surface.py does not; change "
            "nothing else", "edit", "~5 min", priority=2),
    Upgrade("readings-linked", "2026-11-11",
            "every contact whose profile was read has the employer it names",
            _readings_linked, "python3 tools/network/reading.py link-all", "instant",
            command=("python3", "tools/network/reading.py", "link-all"),
            paths=("network_contacts.csv",), priority=2, conditional=True),
    Upgrade("records-agree", "2026-11-11",
            "your tracker, documents, research and profile reads agree with each other",
            _records_agree, "run `python3 tools/record_drafts.py check`, `python3 "
            "tools/company_research.py check` and `python3 tools/network/reading.py "
            "unlinked`. Put right only these: name each letter on disk in its application's "
            "cover_letter_file; give a research file with none its `company`, and save one "
            "named apart from its employer's key under the key (company_research.file_key) "
            "with its contents unchanged; move a reading kept under another name into the "
            "folder of the one contact with that name. Delete nothing, invent no date or "
            "source, and say in one plain line what was put right and what stays as it is",
            "edit", "~5 min", priority=4, conditional=True),
    Upgrade("process-postings", "2026-10-19",
            "every hiring process folder keeps a copy of its job posting, so your own checks stay green",
            _process_postings, "python3 tools/interview_pack.py postings", "instant",
            command=("python3", "tools/interview_pack.py", "postings"),
            paths=("documents/applications/*/job_posting.md",), priority=1, conditional=True),
    Upgrade("one-folder-each", "2026-10-26",
            "each application's checks kept in its one folder, beside its note and documents",
            _twin_folders, "python3 tools/docpaths.py merge-twins", "instant",
            command=("python3", "tools/docpaths.py", "merge-twins"),
            paths=("documents/applications/*",), priority=1, conditional=True),
    Upgrade("runtime-files", "2026-10-19",
            "the files that change on every profile read kept out of your copy on GitHub, so the "
            "day's update check never stops on them",
            _runtime_files, "python3 tools/network/reading.py move-runtime", "instant",
            command=("python3", "tools/network/reading.py", "move-runtime"),
            paths=("documents/network/.reads_stopped.json", "documents/network/.shortlist.json",
                   "documents/network/.page_reads.json", "documents/network/.signed_in.json"),
            priority=1, conditional=True),
    Upgrade("own-tests", "2026-10-19",
            "your own checks kept in line with each update, and the ones that read the app's "
            "code rewritten to check what it does, so an update cannot break them",
            _own_tests, "python3 tools/sync_app.py --own-tests lists the failing ones and why; "
            "python3 tools/sync_app.py --own-test-risks lists the ones that read the app's code. "
            "For a test that checks behaviour an update changed: bring its expectation in line "
            "with the CHANGELOG entry that changed it, keeping everything it checks about the "
            "person's own data; where the change looks wrong for them, bring it in line all the "
            "same (a failing test holds every save back) and, in the maintainer's own repo, "
            "report it the way its profile says. For a test that reads the app's code as text: "
            "rewrite it to run the code and check what it does, through the app's public names "
            "(a job board through tools/offline_boards.py), keeping every assertion's intent. "
            "Never weaken a test to pass; one that uses a part the update removed is rewritten "
            "through the app's public names, or retired, by Claude with nothing asked "
            "(RUNBOOK.md, \"Your own tests fail after an update\"). Change only what the update "
            "changed (the CHANGELOG lines of the versions it took say what), only in "
            "profile/tests, never the person's own data or profile. Run python3 -m pytest "
            "profile/tests -q before committing, with the body \"Your own checks were brought in "
            "line with the update.\" Until this runs, each save sets the tests the update broke "
            "aside and lands the work", "edit", "~15 min", priority=2, conditional=True),
    Upgrade("message-texts", "2026-10-19",
            "your messages that got replies kept with their words, so drafts follow what "
            "worked for you rather than the app's defaults",
            _missing_texts, "python3 -c \"import sys; sys.path[:0]=['tools','tools/network']; "
            "import state, what_works as w; [print(c['contact_id'], c['date'], c['name'], "
            "c['company']) for c in w.message_cases(state.load_contacts(), state.load_threads()) "
            "if c['won'] and not c['text']]\" lists them. After a yes, for each one the person "
            "pastes (from LinkedIn's sent messages, as it went): python3 tools/network/state.py "
            "text <contact_id> --date <date> --text-file <the paste>. Skip any they cannot find",
            "question", "~5 min", priority=2, needs="you", conditional=True,
            ask="Some messages you sent that got a reply aren't saved with their words. Could "
                "you paste them in once, so I can learn from what worked?",
            why_ask="Drafts follow the shape of your messages that got replies, and a message "
                    "kept without its words can't be one of them."),
    Upgrade("voice-refresh", "2026-10-19",
            "your saved intro and ask rewritten the way you write, so every note stops "
            "opening on \"I am\" and ending on the same line",
            _stiff_voice, "Show the person their OPENER, ABOUT_ME and ASK from "
            "profile/networking.py beside a rewrite in their own voice: contractions, plain "
            "English, built from their messages that drew replies (python3 "
            "tools/network/compose.py examples) and every rule python3 tools/learned.py brief "
            "messages lists, with every fact kept. After a yes, write the new values (and, "
            "where they want variety, TEMPLATES with two or three asks), then record it: "
            "python3 tools/learned.py record --area voice --said \"<their words>\" --rule "
            "\"<the new voice>\" --applied-to \"profile/networking.py ABOUT_ME\" (and ASK)",
            "question", "~3 min", priority=2, needs="you", conditional=True,
            ask="Your saved intro and ask use stiff wording, like \"I am\" and \"I would\". "
                "Can I rewrite them the way you write, from your messages that got replies?",
            why_ask="Every first note is built from them, so the stiffness lands in every "
                    "message you send."),
    Upgrade("campaign-notes", "2026-10-19",
            "notes you kept by hand for an interview, before its prep document existed, "
            "folded into it so the next chat has them",
            _campaign_notes, "python3 -c \"import sys; sys.path[:0]=['tools','tools/network']; "
            "import json, interview_pack as p; print(json.dumps(p.handkept_notes(), indent=1))\""
            " lists each file and its prep document. For each: build the document "
            "if it is missing (interview_pack.py pack \"<employer>\" --write); put each answer "
            "the file holds under its question in Your answers, and each decision in Notes, as "
            "it is written there; a fact about the person goes to profile/01-candidate-profile.md "
            "instead, and a stock answer to profile/07-interview-prep.md (interview_pack.py "
            "motive); then add to Notes \"- Folded in from <path> on <date>.\" Leave the file "
            "where it is", "edit", "~5 min", priority=2, conditional=True),
            # Done by Claude alone: folding notes in loses nothing and asks nothing of the
            # person (the maintainer, 2026-10-28: "make these types of decisions for them")
    Upgrade("export-repeats", "2026-11-05",
            "messages your LinkedIn download logged a second time taken out, so nobody you have "
            "already answered reads as waiting on you",
            _export_repeats, "python3 tools/network/export.py tidy", "instant",
            command=("python3", "tools/network/export.py", "tidy"),
            paths=("network_threads.csv", "network_contacts.csv"), priority=2),
    Upgrade("sends-counted-once", "2026-11-10",
            "people written to once, whose note was logged twice and read as two messages with "
            "no reply, given back the one follow-up your rule allows",
            _sends_counted_once, "python3 tools/network/state.py recount --apply", "instant",
            command=("python3", "tools/network/state.py", "recount", "--apply"),
            paths=("network_contacts.csv",), priority=2),
    # Asked, never done by itself: the setting is the person's, and a test of theirs may read
    # it, which an upgrade deleting it would break on every save (the review, 2026-11-11).
    Upgrade("linkedin-limits-ignored", "2026-11-11",
            "your LinkedIn settings without the weekly and daily request caps the app never "
            "reads, so nothing there says it keeps a cap it does not",
            _linkedin_limits_ignored, "only after a yes: take connections_per_week and "
            "connections_per_day out of LINKEDIN_LIMITS in profile/networking.py, keeping the "
            "rest (python3 tools/network/state.py linkedin-limits names them), and bring any "
            "test of theirs in profile/tests that reads them in line", "question", "~1 min",
            names=("networking.LINKEDIN_LIMITS",), conditional=True, priority=4, needs="you",
            ask="Your LinkedIn settings hold a weekly cap on connection requests that the app "
                "never uses. Shall I take it out?",
            why_ask="The app keeps no cap of its own, and LinkedIn tells you when its limit is "
                    "reached."),
    Upgrade("stop-lines-undated", "2026-11-10",
            "no date and no \"close it\" beside anyone who has had your limit of messages with "
            "no reply, so none of them comes back as due",
            _stop_lines_dated, "python3 tools/network/state.py stop-lines --apply", "instant",
            command=("python3", "tools/network/state.py", "stop-lines", "--apply"),
            paths=("network_contacts.csv",), priority=2),
    Upgrade("threads-gone-cold", "2026-11-10",
            "conversations with no answer in months closed as gone cold, so they no longer "
            "count as waiting or hold their employer; a reply from them opens one again",
            _gone_cold, "python3 tools/network/state.py gone-cold", "instant",
            command=("python3", "tools/network/state.py", "gone-cold"),
            paths=("network_contacts.csv",), priority=2),
    Upgrade("set-asides-dated", "2026-11-11",
            "roles you set aside before they had an end each held for about six months from "
            "the update, so they come back one by one, never all at once",
            _set_asides_dated, "python3 tools/exclude.py date-set-asides", "instant",
            command=("python3", "tools/exclude.py", "date-set-asides"),
            paths=("job_scraper/seen_jobs.json",), conditional=True, priority=2),
    Upgrade("notes-aside-dated", "2026-11-11",
            "first notes you set aside for now on the page each offered again about six "
            "months from the update, one by one, never all at once",
            _notes_aside_dated, "python3 tools/network/state.py date-page-drops", "instant",
            command=("python3", "tools/network/state.py", "date-page-drops"),
            paths=("network_contacts.csv",), conditional=True, priority=2),
    Upgrade("drafts-before-a-role", "2026-11-10",
            "drafts written before the role they wait for set aside (kept), and their people "
            "put on hold until a role is posted, so no card carries one message with the name "
            "swapped; each is written for its role then",
            _drafts_before_a_role, "python3 tools/followup_drafts.py role-holds", "instant",
            command=("python3", "tools/followup_drafts.py", "role-holds"),
            paths=("network_contacts.csv", "documents/network/*/draft*"), priority=2),
    Upgrade("one-record", "2026-11-05",
            "anyone kept twice in your contacts joined into one, and people you knew only by "
            "first name given the surname, employer and title your LinkedIn download shows",
            _one_record, "python3 tools/network/export.py one-record", "instant",
            command=("python3", "tools/network/export.py", "one-record"),
            paths=("network_contacts.csv", "network_threads.csv"), priority=2),
    Upgrade("dropped-rows", "2026-10-19",
            "people you set aside before writing, kept apart from real dead ends and easy to "
            "reopen",
            _dropped_rows, "python3 tools/network/state.py dropped-rows --apply", "instant",
            command=("python3", "tools/network/state.py", "dropped-rows", "--apply"),
            paths=("network_contacts.csv",), priority=2),
    Upgrade("sweep-cursor-moved", "2026-10-19",
            "the slow boards' resume point moved out from among your round summaries, so a "
            "check that every file there is a round passes again",
            _old_sweep_cursor, "python3 tools/scrape_wide.py --move-cursor", "instant",
            command=("python3", "tools/scrape_wide.py", "--move-cursor"),
            paths=("documents/rounds/.sweep.json", "documents/rounds/.sweep/cursor.json"),
            priority=1),
    Upgrade("general-resume-draft", "2026-11-06",
            "the resume you send when no job is named can be changed with its pencil: its "
            "bullets, its look and its summary",
            _general_draft_kept, "python3 tools/stage_picks.py general <a scratch folder>: "
            "it makes the general resume again from the profile, checks it and keeps its draft; "
            "if a check fails, leave the one there and say nothing", "edit", "~2 min",
            conditional=True, priority=3),
    Upgrade("tweaks-record-moved", "2026-11-06",
            "the record of changes you asked for to your search moved out from among your round "
            "summaries, so a check that every file there is a round passes again",
            _old_jobs_tweaks, "python3 tools/tweak.py move-record", "instant",
            command=("python3", "tools/tweak.py", "move-record"),
            paths=("documents/rounds/tweaks.json", "documents/rounds/tweaks/tweaks.json"),
            priority=1),
    Upgrade("read-break", "2026-10-19",
            "the pause between bursts of profile reads written in your profile, yours to change",
            _read_break, "add PROFILE_READ_BREAK_MINUTES = (5, 12) to profile/networking.py "
            "beside PROFILE_READS_PER_HOUR, with a comment: the break, in minutes, chosen at "
            "random in that range between bursts of browser reads; a shorter break raises the "
            "risk to their LinkedIn account. Change nothing else", "edit", "~1 min",
            conditional=True, priority=3),
    Upgrade("read-break-freed", "2026-10-22",
            "profile reads at the app's pace, not one an earlier update wrote into your profile",
            _frozen_break, "python3 tools/network/reading.py free-break", "instant",
            command=("python3", "tools/network/reading.py", "free-break"),
            paths=("profile/networking.py",), conditional=True, priority=3),
    # Not instant: a person who has already said their own rule in words (two weeks, two
    # messages) would get the app's six business days written on every row first.
    Upgrade("follow-up-dates", "2026-10-23",
            "every conversation waiting on a reply has its follow-up date on the contact, by "
            "your rule, so the brief brings it back on the day",
            _follow_up_dates, "first, where the person has said a follow-up rule of their own "
            "(python3 tools/learned.py brief people, and profile/CLAUDE.md), write it into "
            "profile/networking.py as FOLLOW_UP_DAYS (days of silence before a follow-up) and "
            "MAX_UNANSWERED (messages in a row with no reply before stopping); invent nothing, "
            "and with no rule said leave both unset, so the app's own stands. Then python3 "
            "tools/network/state.py follow-ups --write, which dates every contact waiting on a "
            "reply and leaves every date and note of the person's own as it is", "edit",
            "~2 min", conditional=True, priority=2),
    Upgrade("reading-limits-gone", "2026-10-22",
            "profile reads with no waiting: the old reading limits taken out of your profile",
            _reading_limits_gone, "python3 tools/network/reading.py retired-settings --apply",
            "instant",
            command=("python3", "tools/network/reading.py", "retired-settings", "--apply"),
            paths=("profile/networking.py",), conditional=True, priority=2),
    Upgrade("move-and-area", "2026-10-19",
            "honest small talk prepared for an interview when you moved recently",
            _move_and_area, "read profile/01-candidate-profile.md and profile/CLAUDE.md; write "
            "person.json identity.moved as YYYY-MM or YYYY-MM-DD when they record when they moved "
            "in the last year, as \"by YYYY-MM-DD\" when the profile only confirms they were "
            "there by a date (\"in <city>, confirmed <date>\"), as \"just arrived\" when their "
            "own rule (learned.py brief interview) is to say only that, with no date, as "
            "\"per employer\" in both when they tell each employer their own place (record "
            "each with python3 tools/told.py \"<Employer>\" \"<place>\"), else \"none\"; and "
            "identity.area as the neighbourhood and city they give (else the location); invent "
            "nothing, and where the profile cannot say, write a short marker "
            "(\"[CONFIRM: when you moved]\", \"[CONFIRM: where you live]\"), never the whole "
            "question", "edit", "~1 min",
            names=("person.json:identity.moved", "person.json:identity.area"), priority=3),
    Upgrade("work-auth-employer", "2026-10-19",
            "recruiters hear your work authorization in your own employer-facing words",
            _work_auth_employer, "add WORK_AUTH[\"employer\"] to profile/networking.py: the "
            "sentence the profile says to use with employers and recruiters, in its own words "
            "(where it names none, the \"senior\" line), and extend WORK_AUTH_CLAUSE so it "
            "matches it; change nothing else", "edit", "~1 min",
            names=("networking.WORK_AUTH",), priority=2),
    Upgrade("country", "2026-10-14",
            "paper size, working week and market language that follow your country",
            _country, "/setup --section market", "question", "~1 min",
            names=("person.json:identity.country",),
            priority=3),
    Upgrade("market-week", "2026-10-14",
            "follow-up dates counted on your own working week",
            _market_week, "/setup --section market", "question", "~1 min",
            names=("search.WEEKEND",),
            conditional=True,
            priority=3),
    Upgrade("market-language", "2026-10-14",
            "internal-only vacancies cut and portals probed in your market's language",
            _market_language, "/setup --section market (and /setup --section search for "
            "titles in the market's own language)", "research", "~10 min",
            names=("search.INTERNAL_ONLY", "search.INTERNAL_ONLY_TITLE", "search.CANARY_QUERY"),
            conditional=True,
            priority=3),
    Upgrade("updates-choice", "2026-11-11",
            "updates arriving the way you said, where an older version wrote it the wrong way "
            "round",
            _updates_choice, "write their answer as the page's Settings does (How updates "
            "arrive), or python3 tools/learned.py record with their words, which reads it back",
            "question", "~0 min", conditional=True, priority=2,
            needs="you",
            ask="Should the app's updates come by themselves, or only when you say?",
            why_ask="An older version may have saved what you said about this the wrong way "
                    "round, so your setting may not be what you meant."),
    Upgrade("updates-said", "2026-11-11",
            "updates arriving the way you said, where an older version saved nothing from your "
            "words",
            _updates_said, "python3 tools/learned.py record --area other --said \"<their answer, "
            "in their words>\" --rule \"<how updates arrive, as they said>\", which writes the "
            "setting and reads it back; their answer is newer than the words asked about, so the "
            "question is not asked again",
            "question", "~0 min", conditional=True, priority=2,
            needs="you",
            ask="Should the app's updates come by themselves, or only when you say?",
            why_ask="Something you said about updates was never saved as your setting by an "
                    "older version, so your setting may not be what you meant."),
    Upgrade("brief-push", "2026-11-04",
            "a phone notification each morning when your brief is ready, only if you want one",
            _brief_push, "write \"brief_push\": \"on\" or \"off\" into profile/person.json from "
            "their answer (Settings, Phone notification, is the same setting)", "question",
            "~0 min", conditional=True, priority=4,
            needs="you",
            ask="Do you want a notification on your phone each morning when your brief is ready?",
            why_ask="It is off unless you say, and your brief still comes on your page and in "
                    "its chat either way."),
    Upgrade("brief-push-kept", "2026-11-05",
            "the phone notification your brief already sent each morning keeps coming, and "
            "Settings shows it on",
            _brief_push_kept, "python3 tools/brief.py keep-push", "instant",
            command=("python3", "tools/brief.py", "keep-push"),
            paths=("profile/person.json",), conditional=True, priority=2),
    Upgrade("letter-language", "2026-10-14",
            "letters that greet, date and number pages in your document language, spelled as you spell",
            _letter_language, "/setup --section documents", "question", "~2 min",
            names=("person.json:documents.salutation_prefix", "person.json:documents.page_label",
                   "person.json:documents.spelling", "person.json:documents.language"),
            conditional=True,
            priority=4),
)

# One upgrade per versioned method of the build (tools/build_versions.py): pending while
# a version this repo predates says what it made should be made again, and the repo
# holds something that method made. This is what carries a quiet improvement to
# everyone who set up before it: a better board search, a fixed prep document, a
# sharper eligibility question. Nobody has to know it happened. Methods a round or a
# /network run applies by itself (`by: "round"`, `by: "network"`) are not listed:
# there is nothing to run, and a chat that cannot do the work (rewriting a note needs
# the person read, which a cloud chat cannot do) was being told to do it.
def _method_check(name: str):
    def check() -> str:
        import build_versions as B
        late = B.behind(name)
        if not late or not B.applies(name):
            return ""
        hook = B.METHODS[name].get("check")
        if hook:
            # A method that keeps a version on each thing it made (the drafts rerun keeps one
            # on each application) says itself whether anything is left for it: nothing,
            # once each failure has been handed its way forward (tools/remake_drafts.py).
            import importlib
            mod, fn = hook.rsplit(".", 1)
            if not getattr(importlib.import_module(mod), fn)():
                return ""
        if name == "page" and _page_published():
            # The sync's own lines bring a published page up to date at once (say_page,
            # app_listen.after_update). Listed here as well, it started a background agent
            # that asked for a republish already done, and came back with nothing changed.
            return ""
        # Said in the person's terms: what is better now. A version number means
        # nothing to them, and this line reaches them.
        return f"made the older way; now {late[-1][3]}"
    return check


def _page_published() -> bool:
    try:
        import app_setup
        return bool(app_setup.page_record().get("url"))
    except Exception:  # noqa: BLE001  listed as before
        return False


def _method_upgrades() -> tuple:
    import build_versions as B
    out = []
    for name, m in B.METHODS.items():
        if m["by"] in ("round", "network"):
            continue
        rerun = [v for v in m["versions"] if v[2]]
        instant = m["by"] == "instant"
        # A method whose own command records what passed (`records`) is never recorded by
        # hand after it: that is how one was marked done with three failures left.
        run = m["run"] if instant or m.get("records") else (
            f"{m['run']}, alone, on what is already there; then "
            f"python3 tools/build_versions.py record {name}")
        out.append(Upgrade(
            f"method-{name}", (rerun[-1][1] if rerun else B.FIRST_RELEASE), m["gives"],
            _method_check(name), run,
            "instant" if instant else "question" if m["by"] == "you" else "research",
            m.get("time", ""),
            command=("python3", "tools/build_versions.py", "redo", name) if instant else (),
            paths=(*m.get("paths", ()), f"profile/{B.RECORD}") if instant else (),
            priority=m["priority"],
            needs="you" if m["by"] == "you" else "nobody",
            ask=m.get("ask", "")))
    return tuple(out)


REGISTRY = REGISTRY + _method_upgrades()

# Profile names added since the first release that need no upgrade, and why. A
# new name goes here or in an upgrade's `names`; tests/test_profile_upgrades.py
# fails on one in neither.
SAFE_DEFAULTS: dict[str, str] = {
    # Written only by the page's Tweak panel, "Keep this for next time" (tools/tweak.py,
    # 2026-10-25); with none, every document and search is as it was before the setting.
    "person.json:documents.fill": "\"fuller\": the page is filled with bullets, as before",
    "person.json:documents.letter_words": "none: a letter is held to 200 to 250 words, as "
                                          "before",
    "person.json:documents.skills_max": "\"standard\": the skills line keeps its 18 "
                                        "skills, as before",
    "person.json:documents.style": "none: the colour comes from documents.styles or is "
                                   "black, as before",
    "search.JOB_AGE_DAYS": "14, the search window run_round.py used before it was a setting",
    # How long a role the person set aside holds before it is shown once more
    # (tools/exclude.py, 2026-11-11); with none, about six months.
    "search.SET_ASIDE_DAYS": "182, about six months; a role set aside held for ever before it "
                             "was a setting",
    # Written only by Your rules' bin on a kind of employer ruled out (tools/app_actions.py
    # rule.drop, 2026-11-05); with none, every BAR_EXCLUDED rule applies, as before.
    "search.BAR_EXCLUDED_OFF": "[]: every kind of employer the profile rules out stays ruled out",
    # Read in the browser a chat has, with no question first, since 2026-10-25: the question
    # and its warnings kept a person's computer chat from reading at all.
    "networking.PROFILE_READS": "\"browser\": the profiles of the people a run writes to are "
                                "read in the browser the chat has; \"paste\" or \"off\" is "
                                "the person's own word (tools/network/reading.py reads_setting)",
    # The number written to at one employer while nobody there has answered; a setting
    # since 2026-10-24, when the person wanted more at four employers.
    "networking.PEOPLE_PER_EMPLOYER": "2, the people written to at one employer while "
                                      "nobody there has answered, as before it was a "
                                      "setting; reading.py more-at raises it for one "
                                      "employer on the person's word",
    # Since 2026-11-04 a follow-up with nothing new to say is drafted short and plain, where
    # code before left it unwritten; a rule of the person's own already kept says either way
    # (followup_drafts.plain_nudge_allowed reads their learned rules when this is unset).
    "networking.PLAIN_NUDGE": "unset is yes: a follow-up with nothing new to say is a short "
                              "plain one, unless a rule the person gave says to wait for "
                              "something new; False is their word (learned.py record writes it)",
    "person.json:documents.styles": "none, so every resume and letter is black, as before "
                                    "the setting existed; a colour is the person's choice "
                                    "per kind of employer (templates/doc_style.py)",
    "person.json:documents.design": "none, so every resume and letter keeps the template's "
                                    "layout, as before designs existed; the person's own "
                                    "fonts, sizes and margins when they choose "
                                    "(templates/doc_design.py)",
    "person.json:documents.designs": "none, so no kind of employer or employer takes a "
                                     "design of its own until the person or /setup sets "
                                     "one (templates/doc_design.py)",
    # Read since before the first release through a one-argument getter (network/reply.py
    # _w) that tools/profile_names.py could not see; nothing about how it is read changed.
    "networking.HOME_ADJECTIVE": "unset, the nationality word in a reply's status and "
                                 "presence checks matches nothing, as it always did for a "
                                 "profile without it",
    # What the reading tools need to know (tools/network/pace.py), none of them a limit on
    # pace: the app sets none since 2026-10-22.
    "networking.CONTRACTIONS": "\"allow\": opening a sentence on \"I'm\" is natural speech; "
                               "\"warn\" or \"refuse\" bring back the old rule for a person "
                               "who wants it",
    "networking.ELIGIBILITY": "work authorization for a recruiter, never a peer, and for a "
                              "decision-maker only once most of the messages the person "
                              "approved for one say it (2026-10-22); recruiters always had it",
    "networking.SAY_THE_ROLE": "a recruiter and a decision-maker may be told the role wanted, "
                               "a peer is not; before, only a recruiter",
    "networking.INMAIL_WORDS": "a warning only, past 170 words to a decision-maker or recruiter "
                               "and 130 to a peer; the 200-word ceiling is unchanged",
    "networking.VOICE": "no contractions suggested and no shorthand used: every draft reads "
                        "exactly as before until the person lists how they speak",
    "networking.EMPLOYERS_FIRST": "\"warn\": a late employer is a warning with the reordering, "
                                  "never a refusal, as the message that drew a reply had it",
    "networking.SENIOR_NOTE_CHARS": "220, the brief note's length before it was a setting",
    "networking.FOLLOW_UP_DAYS": "unset, a follow-up is due after six business days of "
                                 "silence, as before it was a setting",
    "networking.MAX_UNANSWERED": "unset, two messages in a row with no reply (the first and one "
                                 "nudge), as before it was a setting",
    "networking.QUIET_AFTER_SEND_DAYS": "unset, nobody is held for being written to lately: "
                                        "the follow-up rule alone decides, as before it was "
                                        "a setting",
    # Since 2026-11-09 the days someone waiting holds their employer follow the follow-up
    # rule, from the last contact, where a fixed 45 days from the first note held it.
    # Since 2026-11-10 one follow-up wait, not one for every message the limit allows: notes
    # three weeks old held big employers shut through a run.
    "networking.EMPLOYER_WAIT_DAYS": "unset, the person's own follow-up rule decides: one "
                                     "follow-up wait from the last contact, and a request "
                                     "nobody accepted no longer than the days to withdraw it",
    "networking.GONE_COLD_DAYS": "unset, 90: a conversation with no answer that long after the "
                                 "last message is closed as gone cold, recorded, and opened "
                                 "again by a reply",
    "networking.EXPORT_EVERY_DAYS": "unset, the brief asks for a new LinkedIn download once the "
                                    "last is 14 days old; 0 never asks",
    "networking.EXPORT_REMIND": "\"auto\": the LinkedIn download is asked for weekly while "
                                "the person has sent notes or messages in the last two "
                                "weeks, every two weeks otherwise (their own "
                                "EXPORT_EVERY_DAYS, where set, as before); the page's "
                                "Settings or the reminder's trash writes another",
    "networking.SUBJECT": "none: the InMail subject is built from roles.py, who you are",
    "networking.TEMPLATES": "none: the phrase bank, then the person's OPENER and ASK, as before",
    "networking.PROFILE_READ_UNPLACED": "10 people nothing has placed yet on a day's list",
    "networking.PROFILE_PASTE_TOP": "3 profiles offered for a paste, as before",
    "networking.PROFILE_READ_FRESH_DAYS": "a reading stands for 30 days, as before",
    "networking.PROFILE_SESSION_EXPIRY_HOURS": "4 hours: a sign-in page that long after the last "
                                                "page or sign-in is a session that expired, not "
                                                "friction; within it, the day stops as before",
    "networking.REPLY_RATES": "{}: the reply rate of each kind of reader is counted from their "
                              "own message log, and the app's order (founders, hiring leaders, "
                              "recruiters, then peers) stands until there are enough",
    "networking.RECRUITER_NEAR": "(): a recruiter for their own function ranks first, one whose "
                                 "headline names nothing is kept unranked, and one for another "
                                 "family of work is left out",
    "networking.SKIP_HEADLINES": "None: no headline is left out on their word alone; the app's "
                                 "own function and revenue-role checks still run",
    "networking.PER_EMPLOYER_PER_RUN": "None: a run takes people at one employer up to the "
                                       "per-employer limit, counting those already waiting",
    "networking.VARY_ABOUT_ME": "False: the line about themselves is theirs to repeat in every "
                                "note; True holds it to the same rule as anything else a batch "
                                "repeats",
    "search.SCRAPE_PAGES": "5 result pages a search in the cloud, 2 on their own computer, where "
                           "every request leaves from their own address",
    "search.SCRAPE_WORKERS": "10 searches at once in the cloud, 4 on their own computer",
    "search.SCRAPE_MAX_REQUESTS": "no cap in the cloud; 300 requests to each app portal a round on "
                                  "their own computer",
    "search.HOLIDAY_REGION": "read from identity.location (a province, a UK nation, a US "
                             "state); with none named, the country's common holidays",
    "search.HOURS_PER_YEAR": "2,080 hours, a full-time year of 40 hours a week, to read a band "
                             "stated by the hour as a year's pay; a market that works fewer "
                             "hours sets its own",
    "networking.UNSUPPORTED_WHY": "the reason printed beside an unsupported-status finding in a "
                                  "resume or letter; unset, it says 'check it'",
    "networking.OPENALEX": "off: research papers find people only in fields that publish, and "
                           "/setup turns it on for one",
    "search.PORTAL_LOCATIONS": "defaults to every SCRAPE_LOCATION; /add-portal writes it "
                               "only when a board cannot read those names",
    "search.WORKDAY_INTERNAL_SITES": "the app drops Workday's 'Privileged' site already; a "
                                     "profile adds an employer's own internal site names "
                                     "once a round has shown one",
    "networking.GREETING": "'Hi' until the person says how they greet people",
    "networking.REFERRAL_LINE": "the app's sentence until the person says how they would ask",
    "networking.REFERRAL_CLOSE": "the app's sentence until the person says how they would ask",
    "networking.AUTHORITY_TITLE": "English management titles; a market in another language "
                                  "writes its own",
    "networking.SENIOR_IC_TITLE": "English seniority words; a market in another language, or a "
                                  "field where 'staff' is not senior, writes its own",
    "networking.HOME_COUNTRY": "discovery adds it to REGION_WORDS when present; the region "
                               "words alone decide without it",
    "networking.LINKEDIN_LIMITS": "the plan's own limits apply; set only for a plan with more "
                                  "InMail credits than Premium's",
    "search.OPP_SCALE": "computed from the profile's own opportunity weights when absent",
    "skills.MAX_PER_LINE": "six items a line unless the person wants another number",
    "skills.FAMILIES": "none: the app's own families of interchangeable tools apply "
                       "(tools/bridges.py); a field's own are added here",
    "skills.COVERED_BY": "none: the app's own parts and synonyms apply (tools/bridges.py); "
                         "it only removes a question, so absent costs one extra question",
    "skills.MIN_PER_CATEGORY": "one item makes a line worth printing; rarely changed",
    "networking.NOT_HIRING_REASON": "a neutral sentence any field reads correctly",
    "networking.NOT_HIRING_TITLES": "the built-in revenue titles, the same list every older "
                                    "repo used; None turns it off",
    "networking.SPAM_BULK_ROLES": "the built-in staffing-spam roles, the same list every older "
                                  "repo used",
    "person.json:documents.resume_pages": "one page, what every older repo printed; a long "
                                          "career sets two in /setup --section documents",
    "person.json:documents.section_order": "the standard order every older repo printed",
    "person.json:documents.file_names": "the person, the employer, then the document "
                                        "(docpaths.FILE_NAMES_DEFAULT), the order every repo "
                                        "makes from 2026-11-06; Settings > File names changes it",
    "person.json:documents.letter_paper": "follows documents.paper, then the country",
    "person.json:identity.places_told": "none: every employer hears the person's own place, "
                                        "what every older repo assumed; tools/told.py records "
                                        "one that heard another",
    "search.MANAGES_PEOPLE": "no direct reports, what every older repo assumed; /setup "
                             "--section search sets it for someone who has managed people",
    "search.OPP_CONTRACT": "contract work docked, what every older repo did; /setup --section "
                           "search turns it off for someone who wants contract work",
}


def by_id(uid: str) -> Upgrade:
    for u in REGISTRY:
        if u.id == uid:
            return u
    raise KeyError(uid)


def pending() -> list[tuple[Upgrade, str]]:
    """[(upgrade, what is missing)] for every upgrade still pending, most urgent first."""
    with _one_interpreter():
        return _pending()


def _pending() -> list[tuple[Upgrade, str]]:
    out = []
    for u in sorted(REGISTRY, key=lambda u: (u.priority, u.added, u.id)):
        try:
            why = u.pending()
        except Exception as e:          # a check must never break a sync or a round
            why = ""
            print(f"profile upgrades: the {u.id} check failed ({type(e).__name__}: {e})",
                  file=sys.stderr)
        if why:
            out.append((u, why))
    return out


def block(rows: list[tuple[Upgrade, str]]) -> str:
    """What the sync prints. Each line is written to reach the person as it is: what they
    gain, and what they do (nothing, or one short question). The id in brackets is for
    Claude, never for them."""
    if not rows:
        return ""
    alone = [(u, why) for u, why in rows if u.needs == "nobody"]
    yours = [(u, why) for u, why in rows if u.needs != "nobody"]
    lines = [f"Improvements waiting for your search ({len(rows)}):"]
    if alone:
        lines.append("  Claude applies these itself, in the background. Nothing for you to do:")
        for u, _why in alone:
            lines.append(f"    - {u.gives[:1].upper() + u.gives[1:]}.  [{u.id}]")
    if yours:
        lines.append("  These need you: one short question each, on the page as a To do card:")
        for u, why in yours:
            lines.append(f"    - {u.ask or why}  [{u.id}]")
            if why.startswith("you said no"):
                # Asked again: the person hears when they said no and what has changed.
                lines.append(f"      (asked again: {why})")
    # Said here as well as in CLAUDE.md: the session that runs the sync which brings
    # this in is still reading the CLAUDE.md from before it.
    lines.append("  Claude: "
                 + ("start one background agent now (model sonnet) that follows "
                    ".claude/commands/upgrade.md, and carry on with the person's request. "
                    if alone else "")
                 + "Never show an id, a version or the word upgrade. "
                 + ("At the end of your reply give one line per change it made. " if alone else "")
                 # As start says it (app_setup.ASK_ON_PAGE, ASK_IN_CHAT): the sync's own words
                 # told the page's helper to ask in its chat, which nobody reads, while its
                 # start said the page asks them (the maintainer's copy, 2026-11-05).
                 + "Each question is on the page as a To do card, and an answer there counts. "
                 "The chat that answers the page asks none of them in its chat; a chat the "
                 "person writes in asks at most three, at the end of its reply, each as "
                 "written, short and alone. Only a yes "
                 "brings its steps and only \"why?\" its reason (`--plan` has both); a no gets "
                 # The whole command: printed under the sync's own output, `--no <id>` alone
                 # read as a flag of sync_app.py and failed (the maintainer's live run,
                 # 2026-11-05).
                 f"\"{NO_REPLY}\", and `python3 tools/profile_upgrades.py --no <id>` records "
                 "it.")
    return "\n".join(lines)


# The round's one line was worked out afresh on every call, and working it out is a look at
# the whole profile (an interpreter started, the tools imported, sixty checks): about five
# seconds, paid again by every round and by every test that runs one. The answer only
# changes when something the checks read changes, so it is kept for the process, under a
# key of what they read: the profile's files and the search's state files with their
# times and sizes, the two folders that move them, the day (a "no" is asked again after a
# number of days) and the registry. A change in the same process (a profile file written,
# a tracker row added, LJS_PROFILE pointed elsewhere) makes a new key, so it is looked at
# again; `forget_line()` is the clear reset. Only the no-argument call is kept: a caller
# that passes its own rows gets its own answer.
_LINE_KEPT: dict = {}
_SKIP_NAMES = {"__pycache__", ".git", "node_modules", ".pytest_cache"}
_STATE_FOLDERS = ("documents", "rounds", "company_research", "networking", "upskill",
                  "job_scraper", "handoff")


def forget_line() -> None:
    """Drop the kept round line, so the next `line()` looks again."""
    _LINE_KEPT.clear()


def _stamp(path: str) -> tuple:
    try:
        st = os.stat(path)
    except OSError:
        return (path, None, None)
    return (path, st.st_mtime_ns, st.st_size)


def _stamps(folder: str, depth: int) -> list[tuple]:
    """Every entry of `folder` and, `depth` levels down, of the folders in it, with its
    time and size: what changes when a file there is written, added or taken away."""
    try:
        with os.scandir(folder) as it:
            entries = sorted((e for e in it if e.name not in _SKIP_NAMES),
                             key=lambda e: e.name)
    except OSError:
        return [(folder, None, None)]
    out = []
    for e in entries:
        out.append(_stamp(e.path))
        if depth > 1:
            try:
                if e.is_dir(follow_symlinks=False):
                    out.extend(_stamps(e.path, depth - 1))
            except OSError:
                pass
    return out


def _line_key() -> tuple:
    """What the checks read, as a value that differs when any of it differs. Never raises:
    a key that cannot be read is one that never matches, so the line is worked out."""
    try:
        try:
            profile = person.directory()
            files = _stamps(profile, 3)
        except person.NoProfile:
            profile, files = "", []
        state = os.environ.get(person.STATE_ENV) or ROOT
        state = state if os.path.isabs(state) else os.path.join(ROOT, state)
        kept = _stamps(state, 1)
        for name in _STATE_FOLDERS:
            kept += _stamps(os.path.join(state, name), 2)
        return (ROOT, profile, state, person.today().isoformat(), id(REGISTRY), len(REGISTRY),
                tuple(files), tuple(kept))
    except Exception:  # noqa: BLE001  an unreadable key is a miss, never an error
        return (object(),)


def line(rows: list[tuple[Upgrade, str]] | None = None) -> str:
    if rows is None:
        key = _line_key()
        if key in _LINE_KEPT:
            return _LINE_KEPT[key]
        text = _line_of(pending())
        _LINE_KEPT.clear()
        _LINE_KEPT[key] = text
        return text
    return _line_of(rows)


def _line_of(rows: list[tuple[Upgrade, str]]) -> str:
    if not rows:
        return ""
    alone = [u.id for u, _ in rows if u.needs == "nobody"]
    yours = [u.id for u, _ in rows if u.needs != "nobody"]
    parts = []
    if alone:
        parts.append(f"{len(alone)} you apply yourself")
    if yours:
        parts.append(f"{len(yours)} short question{'s' if len(yours) != 1 else ''} for the person")
    # For Claude: a round prints it in its log, and a chat passed the command on with it.
    # What the person hears is CLAUDE.md step 5's, in plain words.
    return ("Claude: improvements waiting: " + "; ".join(parts)
            + " (python3 tools/profile_upgrades.py lists them; never say the command).")


def plan(rows: list[tuple[Upgrade, str]] | None = None) -> list[dict]:
    """The pending upgrades as /upgrade works through them, most urgent first."""
    rows = pending() if rows is None else rows
    out = []
    for u, why in rows:
        steps, check = _steps_and_notes(u)
        out.append({"id": u.id, "priority": u.priority, "needs": u.needs, "ask": u.ask,
                    "steps": steps, "check": check, "why_ask": u.why_ask,
                    "gives": u.gives, "why": why, "run": u.run, "cost": u.cost,
                    "time": u.time})
    return out


# ------------------------------------------------------------------ instant

def _git(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", ROOT, *args], text=True, capture_output=True, check=check,
                          encoding="utf-8", errors="replace")


def _changed() -> set[str]:
    out = _git("status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    return {ln[3:].split(" -> ")[-1].strip('"') for ln in out if ln.strip()}


# ------------------------------------------------------------------ which chat

# Several chats run against one repo at once, each in its own container, and each one
# syncs when it starts work. Every one of them used to find the same new upgrades, start
# the same background /upgrade and ask the same questions. The chat whose own sync
# brought the update in owns it. A chat that got the update by merging master, where
# that chat landed it, stays quiet until the owner has had OWNER_MINUTES to finish, then
# takes over whatever is still pending. It was two hours, and a person who had closed the
# other chats was told by the only one left to do nothing for two hours. A background
# /upgrade takes minutes; twenty is room for it, and `--take` hands them over at once
# when the person says no other chat is open.
OWNER_MINUTES = 20
SYNC_SUBJECT = "^Sync from the app: "
# Two commands, each run on its own: a chain goes to the desktop app's safety check whole.
MERGE_MASTER = "git fetch origin master, then git merge origin/master"


def _marker() -> str:
    d = _git("rev-parse", "--git-common-dir").stdout.strip()
    return os.path.join(d if os.path.isabs(d) else os.path.join(ROOT, d), "ljs-upgrade-owner")


MASTER = "refs/remotes/origin/master"


def _personal_repo() -> bool:
    """A person's own repo, with its profile at the root: the only place another chat's work
    can be waiting on master. The app (and its tests) never fetches from here."""
    return os.path.isdir(os.path.join(ROOT, "profile"))


# A claim on an update's upgrades, pushed to the person's own repository the moment a chat
# takes them: one ref per app commit, whose value is the claiming chat's sync. Git takes the
# first push and refuses a different second one, so of two chats that synced the same update
# a minute apart, the second learns at once that the first has it, before either has landed
# anything on master. Where the push cannot go (offline, or the session may push only its
# own branch), the check against master below still holds.
CLAIM_REFS = "refs/ljs/upgrades/"
CLAIMS_SEEN = "refs/remotes/origin-ljs-upgrades/"


def fetch_master() -> None:
    """origin/master as it is now, and every chat's claim, so what another chat landed or
    took is seen before this one starts the same work. Best effort: offline, the last fetch
    stands. One fetch for both, which halves the wait; where git refuses it, the claims are
    fetched alone, as they were before."""
    claims = "+%s*:%s*" % (CLAIM_REFS, CLAIMS_SEEN)
    if not _fetch("master", claims):
        _fetch(claims)


def _fetch(*spec: str) -> bool:
    try:
        return subprocess.run(["git", "-C", ROOT, "fetch", "-q", "origin", *spec],
                              capture_output=True, text=True, timeout=60,
                              encoding="utf-8", errors="replace").returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _sync_head() -> tuple:
    """(this chat's latest sync commit, its time, the app commit it brought in) or ("", 0, "")."""
    r = _git("log", "-1", "--format=%H %ct %P", f"--grep={SYNC_SUBJECT}", "HEAD").stdout.split()
    if len(r) < 2:
        return "", 0, ""
    return r[0], int(r[1]), (r[3] if len(r) > 3 else "")


def push_claim() -> str:
    """Push this chat's claim on the update its sync brought in: "claimed", "taken" (another
    chat's claim is there already) or "" (no merge to claim, or the push could not go)."""
    sha, _when, app = _sync_head()
    if not app or not _personal_repo():
        return ""
    # Never a prompt: a push that wants a password or a passphrase fails at once and the
    # check against master stands, rather than hanging a sync on the person's computer.
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    # The person's own ssh command (core.sshCommand, or one already in the environment)
    # stays theirs, with the no-prompt option added to it.
    ssh = env.get("GIT_SSH_COMMAND") or _git("config", "core.sshCommand").stdout.strip() or "ssh"
    if "BatchMode" not in ssh:
        ssh += " -o BatchMode=yes"
    env["GIT_SSH_COMMAND"] = ssh
    try:
        r = subprocess.run(["git", "-C", ROOT, "push", "-q", "origin",
                            "%s:%s%s" % (sha, CLAIM_REFS, app)],
                           capture_output=True, text=True, timeout=60, env=env,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if r.returncode == 0:
        _git("update-ref", CLAIMS_SEEN + app, sha)
        return "claimed"
    err = (r.stderr or "") + (r.stdout or "")
    # Only git's own refusal of a second, different value means another chat has it. A
    # server that refuses the push for its own reasons ("remote rejected") says nothing
    # about other chats.
    if "(fetch first)" in err or "(non-fast-forward)" in err or "(already exists)" in err:
        fetch_master()
        return "taken"
    return ""


def _claimed_elsewhere(sha: str, app: str) -> int:
    """When another chat's claim on this app commit is on file, the time of that chat's sync;
    else 0."""
    if not app:
        return 0
    got = _git("rev-parse", "-q", "--verify", CLAIMS_SEEN + app).stdout.strip()
    if not got or got == sha:
        return 0
    when = _git("log", "-1", "--format=%ct", got).stdout.strip()
    return int(when) if when.isdigit() else 0


def done_on_master() -> set[str]:
    """The upgrades another chat applied and landed on master that this chat does not hold
    yet: a `Profile upgrade: <id>` commit on origin/master that HEAD does not contain. Two
    chats once applied the same four upgrades and the same own-test fixes, and merging
    master conflicted on five files with the same intent."""
    if _git("rev-parse", "-q", "--verify", MASTER).returncode != 0:
        return set()
    out = _git("log", "--format=%s", f"HEAD..{MASTER}", "--grep=^Profile upgrade: ").stdout
    return {ln.split(":", 1)[1].strip() for ln in out.splitlines()
            if ln.startswith("Profile upgrade: ") and ln.split(":", 1)[1].strip()}


def _landed_elsewhere(sha: str, parents: list[str]) -> int:
    """When another chat's sync brought the same update onto master first, the time its sync
    was made; else 0. Both chats sync the same app commit, each in its own commit: the one
    on master owns it, whichever chat claimed it locally."""
    app = parents[1] if len(parents) > 1 else ""
    if not app or _git("rev-parse", "-q", "--verify", MASTER).returncode != 0:
        return 0
    if _git("merge-base", "--is-ancestor", sha, MASTER).returncode == 0:
        return 0                                    # this chat's own sync is the one landed
    if _git("merge-base", "--is-ancestor", app, MASTER).returncode != 0:
        return 0                                    # master does not carry this update yet
    for ln in _git("log", "--merges", "--format=%H %ct %P", f"--grep={SYNC_SUBJECT}",
                   MASTER).stdout.splitlines():
        f = ln.split()
        if len(f) >= 3 and app in f[2:]:
            return int(f[1])
    return 0


def owner_elsewhere(now: float | None = None) -> str:
    """"" when this chat owns the pending upgrades, else the time another chat's turn ends."""
    return owner(now)[0]


# Why another chat has the pending upgrades, said as it is: the sync once said they belonged
# to "the one whose sync brought this update in" and that this chat "got the update by
# merging master" when the other chat had only claimed it, and nothing of its had reached
# master.
OWNER_WHY = {
    "claimed": "another chat on this repo took this update first (its claim is on GitHub); "
               "its sync has not reached master yet",
    "landed": "another chat's sync of this update reached master first",
    "merged": "this chat got the update by merging master, where another chat's sync put it",
}


def owner(now: float | None = None) -> tuple[str, str]:
    """("", "") when this chat owns the pending upgrades, else (the time another chat's turn
    ends, the OWNER_WHY key saying why it is theirs)."""
    import time
    r = _git("log", "-1", "--format=%H %ct %P", f"--grep={SYNC_SUBJECT}", "HEAD").stdout.split()
    if len(r) < 2:
        return "", ""
    sha, when = r[0], int(r[1])
    try:
        with open(_marker(), encoding="utf-8") as f:
            if f.read().strip() == "taken " + sha:
                return "", ""                       # handed over by --take: no other chat open
    except OSError:
        pass
    # Checked before this chat's own claim: two chats that synced the same update a minute
    # apart each claimed it, and both applied it. The one whose claim was pushed first owns
    # it; where no claim could be pushed, the one whose sync reached master first. A pushed
    # claim outranks the landing order, or the chat that claimed would wait on the one that
    # was told to wait on it.
    app = r[3] if len(r) > 3 else ""
    mine = bool(app) and _git("rev-parse", "-q", "--verify",
                              CLAIMS_SEEN + app).stdout.strip() == sha
    claimed = 0 if mine else _claimed_elsewhere(sha, app)
    theirs = claimed or (0 if mine else _landed_elsewhere(sha, r[2:]))
    if theirs:
        ends = theirs + OWNER_MINUTES * 60
        if (now if now is not None else time.time()) >= ends:
            return "", ""
        return time.strftime("%H:%M UTC", time.gmtime(ends)), "claimed" if claimed else "landed"
    try:
        with open(_marker(), encoding="utf-8") as f:
            if f.read().strip() == sha:
                return "", ""                       # this chat claimed it earlier
    except OSError:
        pass
    master = "refs/remotes/origin/master"
    if _git("rev-parse", "-q", "--verify", master).returncode != 0:
        return "", ""
    if _git("merge-base", "--is-ancestor", sha, master).returncode != 0:
        return "", ""                               # this chat's own sync, not landed yet
    ends = when + OWNER_MINUTES * 60
    if (now if now is not None else time.time()) >= ends:
        return "", ""
    return time.strftime("%H:%M UTC", time.gmtime(ends)), "merged"


def claim(taken: bool = False) -> None:
    """Mark the update this chat's sync brought in as this chat's, for its background
    /upgrade too: worktrees share the git directory the marker lives in. Chats on other
    computers learn of it from the pushed claim (`push_claim`). `taken` is the person's word
    that no other chat is open (--take), which outranks another chat's claim or landed
    sync."""
    r = _git("log", "-1", "--format=%H", f"--grep={SYNC_SUBJECT}", "HEAD").stdout.strip()
    if r:
        try:
            with open(_marker(), "w", encoding="utf-8", newline="\n") as f:
                f.write(("taken " if taken else "") + r + "\n")
        except OSError:
            pass


# What the sync listed, so the plan a background /upgrade reads a few minutes later can
# say what has happened to each one. The sync listed eleven, the plan held seven, and the
# chat could not tell whether the other four were done, skipped or lost: they had been
# done, by an instant upgrade or by another chat, and nothing said so.
def _listed_path() -> str:
    return os.path.join(os.path.dirname(_marker()), "ljs-upgrades-listed.json")


def _listed() -> dict:
    try:
        with open(_listed_path(), encoding="utf-8") as fh:
            got = json.load(fh)
    except (OSError, ValueError):
        return {}
    return got if isinstance(got, dict) else {}


def _save_listed(got: dict) -> bool:
    try:
        with open(_listed_path(), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(got, fh)
        return True
    except OSError:
        return False


def _day(today: dt.date | None = None) -> str:
    """The person's own day (person.today), the one the app's hook counts by: on the
    computer's clock, `--plan` on a Toronto evening in a cloud chat marked the improvements
    started tomorrow, and the hook held the next turn to start them again (2026-11-03)."""
    return (today or person.today()).isoformat()


def _chat() -> str:
    """This chat's id, as the page's listener knows it (app_listen.this_chat), or ""."""
    try:
        import app_listen
        return app_listen.this_chat()
    except Exception:  # noqa: BLE001
        return ""


def remember_listed(rows: list[tuple[Upgrade, str]], elsewhere: bool = False,
                    today: dt.date | None = None) -> None:
    """What the sync listed, with the day each was first listed (kept across syncs, so one
    left waiting for days is known as such), whether another chat has them (`elsewhere`),
    and today's start, each chat's reason not to, and the holds, which last the day."""
    sha, _when, _app = _sync_head()
    was = _listed()
    since = was.get("since") if isinstance(was.get("since"), dict) else {}
    day = _day(today)
    got = {"sync": sha, "ids": [u.id for u, _ in rows], "day": day,
           "since": {u.id: str(since.get(u.id) or day) for u, _ in rows},
           "elsewhere": bool(elsewhere)}
    # A start stands for the update it was made for: a second update the same day (the
    # master channel takes several) is owed its own, or own tests it broke waited for tomorrow.
    if isinstance(was.get("started"), dict) and was["started"].get("day") == day \
            and was.get("sync") in (sha, None):
        got["started"] = was["started"]
    for key in ("not_now", "held"):
        kept = {c: v for c, v in (was.get(key) or {}).items()
                if isinstance(v, dict) and v.get("day") == day} \
            if isinstance(was.get(key), dict) else {}
        if kept:
            got[key] = kept
    _save_listed(got)


def queue_own_tests(root: str | None = None, today: dt.date | None = None) -> bool:
    """The own-tests improvement queued for this copy's latest update, at once: a landing that
    finds the person's own tests an update broke (an update another chat took, so no sync
    here listed it) sets them aside for its save and queues this, and the app's hook has the
    next chat that is not on one big job start it in the background. One already listed and
    not started stays as it is; one started for an earlier update is owed again. True when
    it is queued."""
    global ROOT
    was_root = ROOT
    ROOT = root or ROOT
    try:
        sha = _sync_head()[0]
        if not sha:
            return False
        got = _listed()
        day = _day(today)
        if got.get("sync") != sha:
            got = {"sync": sha, "ids": [], "day": day, "since": {}, "elsewhere": False}
        ids = [i for i in (got.get("ids") or []) if isinstance(i, str)]
        if "own-tests" in ids:
            # Listed for this update already: waiting, started (a background agent may be on
            # it now), or another chat's. Left exactly as it is: popping the start had the hook
            # hold the next chat for a second agent on the same tests, and every chat's
            # "not now" for the day was deleted (the release review, 2026-11-06).
            return True
        started = got.get("started") if isinstance(got.get("started"), dict) else None
        if started is not None and not isinstance(started.get("ids"), list):
            started["ids"] = list(ids)   # the start covers what was listed then, not this
        ids.append("own-tests")
        got["ids"] = ids
        since = got.get("since") if isinstance(got.get("since"), dict) else {}
        since.setdefault("own-tests", day)
        got["since"] = since
        return _save_listed(got)
    except Exception:  # noqa: BLE001  a landing must never stop on it
        return False
    finally:
        ROOT = was_root


def listed_ids() -> list[str]:
    got = _listed()
    return [i for i in (got.get("ids") or []) if isinstance(i, str)] \
        if got.get("sync") == _sync_head()[0] else []


def mark_started(today: dt.date | None = None) -> None:
    """A chat started /upgrade on what the sync listed (its plan was read, or the app's hook
    saw it start): nothing more is owed on them today, in any chat on this computer."""
    got = _listed()
    if got:
        got["started"] = {"day": _day(today)}
        _save_listed(got)


def not_now(why: str, chat: str = "", today: dt.date | None = None) -> dict:
    """Why this chat cannot start the listed improvements today: kept with the listing, for
    this chat alone, and its turns are no longer held for them until tomorrow."""
    why = " ".join(str(why or "").split())
    if not why:
        raise SystemExit("profile_upgrades: --not-now needs the reason they cannot start now")
    got = _listed()
    rec = {"day": _day(today), "why": why[:300]}
    got.setdefault("not_now", {})[chat or _chat() or "this chat"] = rec
    _save_listed(got)
    return rec


def _done_since(sha: str) -> set[str]:
    """The ids of the upgrades committed here since the sync that listed them: done, never
    started again (an improvement applied yesterday was announced as waiting and started a
    second time the next morning, 2026-11-03)."""
    if not sha:
        return set()
    out = _git("log", "--format=%s", f"{sha}..HEAD", "--grep=^Profile upgrade: ").stdout
    return {ln.split(":", 1)[1].strip() for ln in out.splitlines()
            if ln.startswith("Profile upgrade: ")}


def unstarted(today: dt.date | None = None, chat: str = "") -> list[tuple[str, str]]:
    """[(id, the day it was first listed)] for each improvement Claude makes alone that this
    chat's sync listed and nobody has started today: what the app's hook holds a turn for.
    Files and two git calls only; never raises. A chat-only person's copy listed upgrades
    every morning for days and nothing started them, since starting them was a printed line
    (2026-11-03).

    A listing from an earlier day's check stands until today's check lists again only where
    nobody ever started it: one an /upgrade took may be in place by now. One committed since
    it was listed is done."""
    try:
        got = _listed()
        ids = listed_ids()
        day = _day(today)
        if not ids or got.get("elsewhere"):
            return []
        mine = (got.get("not_now") or {}).get(chat or _chat() or "this chat") \
            if isinstance(got.get("not_now"), dict) else None
        if isinstance(mine, dict) and mine.get("day") == day:
            return []
        started = got.get("started") if isinstance(got.get("started"), dict) else None
        if started and (str(got.get("day") or day) < day or started.get("day") == day):
            # A start covers what was listed when it was made: own-tests queued after it
            # (queue_own_tests) is owed on its own, and nothing the start took is owed twice.
            covered = started.get("ids")
            if not isinstance(covered, list):
                return []
            ids = [i for i in ids if i not in covered]
        done = _done_since(str(got.get("sync") or ""))
        since = got.get("since") if isinstance(got.get("since"), dict) else {}
        known = {u.id: u for u in REGISTRY}
        return [(i, str(since.get(i) or day)) for i in ids
                if i in known and known[i].needs == "nobody" and i not in done]
    except Exception:  # noqa: BLE001  the hook's check must never break the chat
        return []


HOLDS_A_DAY = 3


def hold_once(chat: str = "", today: dt.date | None = None) -> bool:
    """Count one hold of this chat's turn for the unstarted improvements: True while it is
    within HOLDS_A_DAY today. False when the count cannot be kept: a hold that cannot be
    counted could never let go."""
    got = _listed()
    if not got:
        return False
    day = _day(today)
    held = got.get("held") if isinstance(got.get("held"), dict) else {}
    key = chat or _chat() or "this chat"
    rec = held.get(key) if isinstance(held.get(key), dict) and held[key].get("day") == day \
        else {"day": day, "n": 0}
    if int(rec.get("n") or 0) >= HOLDS_A_DAY:
        return False
    rec["n"] = int(rec.get("n") or 0) + 1
    held[key] = rec
    got["held"] = held
    return _save_listed(got)


_listed_ids = listed_ids  # the module's own name for it; other modules call listed_ids


def already_in_place(rows: list[tuple[Upgrade, str]]) -> list[str]:
    """The ids this chat's sync listed that are no longer pending: in place since."""
    now = {u.id for u, _ in rows}
    return [i for i in _listed_ids() if i not in now]


def _looked_at() -> tuple:
    """What a look reads that the rest of a run after a sync can change: the commit (an
    instant upgrade, the state files' line endings), the files in the checkout, and the
    record of the person's own tests (run once for each update)."""
    import sync_app
    rec = sync_app.own_tests_record(ROOT)
    return (_git("rev-parse", "HEAD").stdout.strip(), sorted(_changed()),
            json.dumps(rec, sort_keys=True) if rec is not None else None)


def _look_again(first: list[tuple[Upgrade, str]], seen: tuple, landed: set[str],
                ran: bool) -> list[tuple[Upgrade, str]]:
    """What is still pending once the instant upgrades have run: the first look again
    where none was due (`ran`) and nothing the look reads has changed since, which is most
    days and took four seconds to work out a second time; else a new look, since an
    instant upgrade can write files git ignores and commit nothing. Either way without what
    another chat has already landed on master, which the second look used to list again as
    waiting, for this chat to make a second time."""
    rows = first if not ran and _looked_at() == seen else pending()
    return [(u, why) for u, why in rows if u.id not in landed]


def _instant_due(rows: list[tuple[Upgrade, str]]) -> bool:
    return any(u.cost == "instant" and u.command for u, _ in rows)


def run_instant(rows: list[tuple[Upgrade, str]]) -> list[str]:
    """Run each pending instant upgrade and commit it on its own. An upgrade that
    touches anything outside its own personal paths is undone, never committed."""
    from personal_paths import is_personal
    notes = []
    if _changed():
        return ["instant upgrades not run: the repo has uncommitted changes"]
    for u, _why in rows:
        if u.cost != "instant" or not u.command:
            continue
        # The Python running this one, not whatever `python3` names: on a Windows computer
        # with python.org's Python `python3` is a Store stand-in that exits 49, and the
        # upgrade said "not applied" on every sync (build_versions.redo does the same).
        argv = [sys.executable if u.command[0] == "python3" else u.command[0], *u.command[1:]]
        try:
            rc = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True, timeout=600,
                                encoding="utf-8", errors="replace").returncode
            failed = f"exit {rc}" if rc else ""
        except (OSError, subprocess.TimeoutExpired) as e:
            failed = f"it could not run: {type(e).__name__}"
        touched = sorted(_changed())
        stray = [p for p in touched
                 if not is_personal(p) or not any(fnmatch.fnmatch(p, g) for g in u.paths)]
        if failed or stray:
            _git("checkout", "--", ".")
            _git("clean", "-fdq", "--", *touched) if touched else None
            notes.append(f"{u.id}: not applied ("
                         + (failed or f"it touched {', '.join(stray[:3])}, outside its own files")
                         + ")")
            continue
        if touched:
            _git("add", "-f", "--", *touched)
            c = _git("commit", "-q", "-m", f"Profile upgrade: {u.id}", "-m", u.gives)
            if c.returncode != 0:
                # No git identity in this session, a hook, anything: undo rather
                # than leave the person's files changed and uncommitted.
                _git("reset", "-q", "--", *touched)
                _git("checkout", "--", ".")
                _git("clean", "-fdq", "--", *touched)
                why = ((c.stderr or c.stdout).strip().splitlines() or ["no error text"])[-1]
                notes.append(f"{u.id}: not applied (the commit failed: {why[:120]})")
                continue
            notes.append(f"{u.id}: applied, {len(touched)} file(s), committed")
    return notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--line", action="store_true")
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--after-sync", dest="after", action="store_true")
    mode.add_argument("--plan", action="store_true",
                      help="the pending upgrades as JSON, most urgent first (/upgrade reads it)")
    mode.add_argument("--check", metavar="ID",
                      help="one upgrade: 'done', or what is missing; exit 1 while pending")
    mode.add_argument("--take", action="store_true",
                      help="this chat applies the pending upgrades now: no other chat is open")
    mode.add_argument("--no", metavar="ID",
                      help="record the person's no to one question, dated: it is asked again "
                           "when the question changes or after REASK_DAYS")
    mode.add_argument("--not-now", metavar="WHY", dest="not_now",
                      help="why this chat cannot start the listed improvements today")
    a = ap.parse_args(argv)
    if not person.exists():
        return 0                                    # the app, or a repo before /setup
    if a.not_now is not None:
        not_now(a.not_now)
        print("profile_upgrades: noted for today; the next chat, or this one tomorrow, starts "
              "them. Say nothing about it to the person.")
        return 0
    if a.no:
        p = record_no(a.no)
        print(f"profile_upgrades: their no to {a.no} kept in {local_path.rel(p, ROOT)}; asked "
              f"again when the question changes or after {REASK_DAYS} days. Say only: "
              f"\"{NO_REPLY}\"")
        return 0
    if a.take:
        claim(taken=True)
        print("profile_upgrades: this chat owns the pending upgrades now; apply them "
              "(`profile_upgrades.py --plan`, then /upgrade in the background)")
        return 0
    if a.plan or a.check:
        # An /upgrade worktree made from a commit before the sync lists the upgrades of an
        # older app, and named an upgrade it did not have as a KeyError.
        import sync_app
        behind = sync_app.behind_sync(ROOT)
        if behind:
            print(behind)
            return 2
    if a.check:
        # Right before an upgrade starts, master is checked: another chat may have landed it.
        if _personal_repo():
            fetch_master()
        if a.check in done_on_master():
            print(f"done on master by another chat: merge it ({MERGE_MASTER}), never apply "
                  "it again here")
            return 0
        try:
            upgrade = by_id(a.check)
        except KeyError:
            print(f"There is no change called {a.check!r} in this copy of the app: it is "
                  "older than the update that named it, or the name is mistyped. Update this "
                  f"checkout first ({MERGE_MASTER}), then check again.")
            return 2
        why = upgrade.pending()
        print(why or "done")
        if why and upgrade.every:
            # The pending line names a few; /upgrade asks about each (upgrade.md step 5).
            for item in upgrade.every():
                print(f"  - {item}")
        return 1 if why else 0
    if _personal_repo() and (a.after or a.plan):
        fetch_master()
    rows = pending()
    first, seen = rows, (_looked_at() if a.after else None)
    landed = done_on_master() if rows else set()
    if landed:
        # Applied by another chat and on master already: this chat merges them, never makes
        # them again, so the two never meet as a conflict.
        rows = [(u, why) for u, why in rows if u.id not in landed]
        if not a.plan:
            print(f"Profile upgrades: {len(landed)} already in place on master, applied by "
                  f"another chat ({', '.join(sorted(landed))}): merge master ({MERGE_MASTER}); "
                  "nothing to do for them here; where one of "
                  "their files conflicts, take master's copy, since an upgrade makes the same "
                  "change wherever it runs.")
    if a.after:
        import merge_state
        merge_state.install(ROOT)
        # The copy of sync_app.py that ran this sync may predate the own-tests check; this
        # file is always the one the sync brought in, so the check runs from here too.
        import sync_app
        sync_app.own_tests_after_sync(ROOT)
        # And the day's check is recorded: a sync run by an older copy of sync_app.py wrote
        # no stamp, so every tool the new copy brought said "not checked for updates today"
        # straight after the update.
        sync_app._record_check(ROOT)
        # And the state files get plain line endings in their own commit, from here too: the
        # copy of sync_app.py that ran this sync may predate it.
        said = sync_app.plain_state_endings(ROOT)
        if said:
            print("profile upgrades: " + said)
        # The steps an older start printed are out of date once the update changed how a chat
        # starts (X-78): said from here, the file the sync just brought in.
        try:
            import app_setup
            said = app_setup.start_changed_line()
        except Exception:  # noqa: BLE001  never breaks the sync
            said = ""
        if said:
            print(said)
    if rows and _setup_unfinished():
        # Setup is still writing the profile (here or in another chat): an upgrade would write
        # the same files beside it from a half-written profile (the stranger audit, X-65).
        if a.plan:
            print("[]")
            return 0
        if not a.line:
            print(f"Profile upgrades: {len(rows)} pending; they wait until setup is finished. "
                  "Claude: start nothing about them and say nothing about them to the person.")
        say_page()
        return 0
    if a.after and rows and _personal_repo() and not owner_elsewhere():
        # Pushed before this chat decides it owns them: of two chats that both found no other
        # claim, git takes one push and refuses the other, and the refused one sees the
        # winner's claim below. A chat another chat's claim or landed sync already covers
        # pushes nothing, so it never stakes a claim on top of theirs.
        push_claim()
    elsewhere, why_theirs = owner() if rows and (a.after or a.plan or a.line) else ("", "")
    if elsewhere:
        # Another chat brought this update in and is applying it: say so once, start
        # nothing and ask nothing. The instant ones still run below; they are the same
        # commit everywhere, so they merge cleanly.
        if a.plan:
            print("[]")
            return 0
        if a.after:
            for note in run_instant(rows):
                print(f"profile upgrades: {note}")
            rows = _look_again(first, seen, landed, _instant_due(rows))
            remember_listed(rows, elsewhere=True)
            for ln in say_changed():
                print(ln)
        if rows and a.line:
            print(f"Profile upgrades: {len(rows)} pending, being applied by another chat "
                  f"until {elsewhere}.")
        elif rows:
            done = (f", and {len(landed)} of its changes are on master already" if landed
                    else ", and none of its changes has reached master yet")
            if why_theirs == "claimed" and not landed:
                done = ""        # OWNER_WHY says it already: said twice, it read as a stutter
            print(f"Profile upgrades: {len(rows)} pending. They belong to another chat until "
                  f"{elsewhere}: {OWNER_WHY[why_theirs]}{done}. "
                  f"Claude: start nothing and ask nothing about them; merge master first "
                  f"({MERGE_MASTER}). After {elsewhere} the next sync hands what is still pending "
                  "to this chat, whenever it runs: set no timer or reminder for it, and say "
                  "nothing about it to the person. If the person says no other chat is open, "
                  "take them now: python3 tools/profile_upgrades.py --take")
        else:
            print("Profile upgrades: none pending.")
        say_page()
        return 0
    if a.after:
        claim()
    if a.plan:
        if rows:
            mark_started()                  # /upgrade's first step: they are under way
        print(json.dumps(plan(rows), indent=1))
        done = sorted(set(already_in_place(rows)) | (landed & set(_listed_ids())))
        if done:
            print("Already in place since the sync listed them (an instant one, or another "
                  f"chat's): {', '.join(done)}. Nothing to do for them; the report says each "
                  "is already in place.", file=sys.stderr)
        return 0
    if a.line:
        text = line(rows)
        if text:
            print(text)
        return 0
    if a.all:
        open_ = {u.id: why for u, why in rows}
        for u in sorted(REGISTRY, key=lambda u: (u.added, u.id)):
            state = f"PENDING: {open_[u.id]}" if u.id in open_ else "done"
            print(f"  {u.id:16} ({u.added}) [{u.cost}] {state}")
        return 0
    if a.after:
        for note in run_instant(rows):
            print(f"profile upgrades: {note}")
        rows = _look_again(first, seen, landed, _instant_due(rows))
        remember_listed(rows)
        for ln in say_changed():
            print(ln)
    text = block(rows)
    print(text or "Profile upgrades: none pending.")
    say_page()
    return 0


def _setup_unfinished() -> bool:
    """Has setup started (profile/place.json's setup mark) and not finished?"""
    try:
        with open(person.path("place.json"), encoding="utf-8") as fh:
            mark = (json.load(fh) or {}).get("setup") or {}
        return bool(mark.get("started") and not mark.get("finished"))
    except (OSError, ValueError, AttributeError, person.NoProfile):
        return False


LANDED = "LJS_UPDATE_LANDED"     # set to "1" by sync_app.py when its run took an update


# Read once, when a chat starts or a skill is first used, and kept: an update that changed one
# left a chat that answers the page handling every ring for the rest of the day with the old
# skill in mind, told only that CLAUDE.md changed (the stranger audit, 2026-11-03, X-36).
# sync_app.py names CLAUDE.md and AGENTS.md; the copy of it that ran may predate this, so the
# skills are named here, from this file, which is always the one the update brought in.
HELD_FILES = (".claude/skills/*/SKILL.md",)


def say_changed() -> list[str]:
    """One line for each kept instruction file the update this run took changed. Never
    raises."""
    if os.environ.get(LANDED) != "1":
        return []
    sha, _when, _app = _sync_head()
    if not sha:
        return []
    r = _git("diff", "--name-only", f"{sha}^1", sha, "--", *HELD_FILES)
    out = []
    for p in sorted(p for p in r.stdout.split() if p) if r.returncode == 0 else []:
        # Only a chat that has read it holds an old copy: one that never loaded this skill
        # reads the new one when it first needs it, and re-reading every changed skill cost an
        # open chat 70 to 110 KB a release for nothing (the cost audit, 4.12).
        out.append(f"Claude: {p} changed. If this chat has already read it, it is following the "
                   f"old copy: read {p} again now, before going on. If not, nothing to do.")
    return out


def say_page() -> None:
    """The person's page, missing or out of date, said where every sync prints: this file is
    always the copy the sync just brought in, so a chat whose instructions predate the page
    still publishes it (tools/app_setup.py page_line). `LANDED` in the environment is the
    sync's word that this run took an update, so the page's data is refreshed too. Never
    breaks the sync."""
    try:
        import app_setup
        said = app_setup.page_line(landed=os.environ.get(LANDED) == "1")
    except Exception:  # noqa: BLE001
        said = ""
    if said:
        print(said)


if __name__ == "__main__":
    sys.exit(main())
