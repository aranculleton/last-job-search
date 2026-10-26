#!/usr/bin/env python3
"""Setup, a setup left part-way, an old install and the app's updates, all through the page.

The person says "set me up" in a chat, once. From then on the questions are asked on their
page, one at a time with "2 of 6", the research shows its progress there, and what only
they can do outside it (their private copy, the cloud setting that lets the chat reach job
sites, signing in to LinkedIn on their computer, the chat on their computer) is a card
with dated steps from tools/claude_surfaces.json and the official link.

`start()` is the one entry point for every state a copy can be in. It reads the copy,
decides, and returns the lines a chat follows, written as instructions so that a chat whose
CLAUDE.md is older than this still acts on them (the sync's printed lines reach every chat;
CLAUDE.md does not). Whether a search is set up is `place.setup_state`, the one detector.

What the page asks is the `setup` section of the view model; what the updates did is its
`updates` section. The person's answers are written by `app.py apply` into
profile/setup_answers.json, and /setup reads them from there: never from the chat, and never
asked twice. The page's own address is profile/app.json.

    python3 tools/app.py start [--on <model>] [--tools <browser tools>] [--page <url>]
    python3 tools/app.py published <url> [--chat ID]      after a publish: the address kept
    python3 tools/app.py resume-saved <file> [--asset ID]  the resume added on the page, saved
    python3 tools/app.py propose "<role>"...               the roles setup will ask about

Pure code, standard library only, Python 3.9. No model call; the only network a start
uses is git's own fetch through the sync, GitHub's answer to "is this copy private", and in
a cloud chat the job-site check the day's sync already runs.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "network"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import person  # noqa: E402

ROOT = os.path.dirname(_HERE)
ANSWERS = "setup_answers.json"
PAGE = "app.json"
JOB_SITES = "ljs-job-sites.json"     # in the git folder: the last check of the job sites
APP_REPO = "aranculleton/last-job-search"
# What this folder is, said instead of asked: for the app's own tests, which run inside the
# app's checkout, and for a rehearsal on throwaway copies GitHub has never seen.
COPY_ENV = "LJS_COPY"
KINDS = ("app", "public", "private", "unknown", "none")
COPY_NAME = "my-job-search"
# The make-copy entry's own link (tools/claude_surfaces.json), as a full address.
COPY_LINK = ("https://github.com/new?template_owner=aranculleton&template_name=last-job-search"
             f"&owner=%40me&name={COPY_NAME}&visibility=private")
# /setup's own targets: about six questions, under 400 words before the shortlist.
QUESTION_WORDS = 400

# ------------------------------------------------------------------ where things are


def profile_dir() -> str:
    """The profile folder in use, whether or not it exists yet."""
    p = os.environ.get(person.ENV) or person.DEFAULT
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(ROOT, p))


def set_up() -> bool:
    """Is there a profile the tools can run on (its person.json written)?"""
    return os.path.isfile(os.path.join(profile_dir(), "person.json"))


def read_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, type(default)) else default
    except (OSError, ValueError):
        return default


_read_json = read_json  # the module's own name for it; other modules call read_json


def write_json(path: str, data) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path


_write_json = write_json  # the module's own name for it; other modules call write_json


def answers() -> dict:
    """What the person answered on the page, by step: profile/setup_answers.json."""
    return _read_json(os.path.join(profile_dir(), ANSWERS), {})


def save_answers(data: dict) -> str:
    return _write_json(os.path.join(profile_dir(), ANSWERS), data)


def page_record() -> dict:
    """The page's own address and when it was published: profile/app.json."""
    return _read_json(os.path.join(profile_dir(), PAGE), {})


def record_page(url: str, chat: str = "", now: dt.datetime | None = None) -> str:
    """Keep the page's address once a chat has published it, and mark the page's build part
    done at this version (tools/build_versions.py "page")."""
    import app_model
    url = str(url or "").strip()
    if not re.match(r"^https://claude\.ai/\S+$", url):
        raise ValueError("that is not a claude.ai page address")
    got = page_record()
    got.update(url=url, published_at=app_model.stamp(now or dt.datetime.now(dt.timezone.utc)),
               by=chat or got.get("by") or "")
    path = _write_json(os.path.join(profile_dir(), PAGE), got)
    if set_up():
        try:
            import build_versions
            build_versions.record(["page"])
        except Exception:  # noqa: BLE001  the address is kept either way
            pass
    return path


# ------------------------------------------------------------------ git and GitHub


def _git(*args, timeout: int = 30, root: str = "") -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", root or ROOT, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           stdin=subprocess.DEVNULL,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return r.returncode, r.stdout


def origin() -> tuple[str, str]:
    """(owner, name) of this copy on GitHub, or ("", "") when it has none."""
    code, url = _git("remote", "get-url", "origin")
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip()) if code == 0 else None
    return (m.group(1), m.group(2)) if m else ("", "")


def _gh(*args, timeout: int = 60, runner=None) -> tuple[int, str]:
    run = runner or subprocess.run
    try:
        # Found the way the shell finds it: on Windows that includes a gh.cmd or gh.bat
        # launcher, which a bare "gh" never reaches.
        r = run([shutil.which("gh") or "gh", *args], capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return 127, ""
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def visibility(owner: str, name: str, runner=None) -> str:
    """"private", "public", or "" when GitHub could not be asked. Never changed here."""
    if not owner:
        return ""
    code, out = _gh("api", f"repos/{owner}/{name}", "--jq", ".private", runner=runner)
    word = out.strip().splitlines()[-1].strip().lower() if code == 0 and out.strip() else ""
    return {"true": "private", "false": "public"}.get(word, "")


def repo_kind(runner=None) -> dict:
    """What this folder is: {"kind": "app" | "public" | "private" | "unknown" | "none",
    "owner", "name"}. "app" is the app itself; "public" any other public copy, a fork of the
    app included; "none" a folder with no copy on GitHub behind it."""
    import sync_app
    owner, name = origin()
    told = os.environ.get(COPY_ENV, "")
    if told in KINDS:                  # a test, or a rehearsal on a throwaway copy
        return {"kind": told, "owner": owner, "name": name}
    if sync_app.is_the_app(ROOT):
        return {"kind": "app", "owner": owner, "name": name}
    if not owner:
        return {"kind": "none", "owner": "", "name": ""}
    seen = visibility(owner, name, runner)
    return {"kind": seen if seen in ("private", "public") else "unknown", "owner": owner,
            "name": name}


def repo_kind_offline() -> dict:
    """repo_kind without asking GitHub: "app", "copy" (a copy, its privacy not asked) or
    "none". The model is built offline; start asks GitHub before anything is written."""
    told = os.environ.get(COPY_ENV, "")
    if told in KINDS:
        return {"kind": "copy" if told in ("private", "unknown") else told, "owner": "",
                "name": ""}
    try:
        import sync_app
        if sync_app.is_the_app(ROOT):
            return {"kind": "app", "owner": "", "name": ""}
    except Exception:  # noqa: BLE001
        pass
    owner, name = origin()
    return {"kind": "copy" if owner else "none", "owner": owner, "name": name}


def make_copy(name: str = COPY_NAME, runner=None) -> dict:
    """The person's private copy, made from the app with GitHub's own command:
    `gh repo create <name> --template aranculleton/last-job-search --private`. Always
    --private, and checked private after; never anything else. {"ok", "url", "say"}."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(name or COPY_NAME)).strip("-.") or COPY_NAME
    code, out = _gh("repo", "create", name, "--template", APP_REPO, "--private",
                    timeout=120, runner=runner)
    if code == 127:
        return {"ok": False, "url": "", "say": "GitHub's own tool is not on this computer."}
    if code:
        return {"ok": False, "url": "",
                "say": "GitHub said no: " + (out.strip().splitlines() or ["no reason given"])[-1]}
    m = re.search(r"https://github\.com/([^/\s]+)/([^/\s]+)", out)
    if not m:
        return {"ok": False, "url": "", "say": "GitHub made it but did not say where."}
    if visibility(m.group(1), m.group(2), runner) != "private":
        return {"ok": False, "url": m.group(0),
                "say": "It was made, but GitHub did not say it is private: check it before "
                       "anything goes in."}
    return {"ok": True, "url": m.group(0), "say": f"Your private copy is made: {m.group(0)}"}


# ------------------------------------------------------------------ the job sites this chat reaches


def _git_dir() -> str:
    """This checkout's own git folder, where a record no other computer needs is kept."""
    code, out = _git("rev-parse", "--absolute-git-dir", root=person.state())
    return out.strip() if code == 0 else ""


def job_sites() -> dict:
    """The last check of the job sites a cloud chat reaches: {"checked", "blocked": [...]}."""
    d = _git_dir()
    return _read_json(os.path.join(d, JOB_SITES), {}) if d else {}


def check_job_sites(today: str = "") -> dict:
    """In a cloud chat, which job sites its settings block, checked now and kept for the
    page (the day's sync runs the same check, env_check.blocked_names)."""
    if os.environ.get("CLAUDE_CODE_REMOTE", "").lower() != "true":
        return {}
    import env_check
    got = {"checked": today or dt.date.today().isoformat(), "blocked": env_check.blocked_names()}
    d = _git_dir()
    if d:
        _write_json(os.path.join(d, JOB_SITES), got)
    return got


# ------------------------------------------------------------------ the questions

# /setup's questions, as the page asks them: about six, one at a time. Each field is what
# one control writes; `known` reads what the profile already holds, so a half-done setup
# is never asked again.
STEPS = (
    {"id": "resume", "kind": "upload-or-paste",
     "question": "Your resume: add the file, or paste it.",
     "help": "No resume? Choose Build one with me, and I'll make it with you, one job at a time.",
     "fields": [{"key": "resume", "kind": "upload-or-paste",
                 "label": "Your resume (PDF or Word), or paste it"}],
     "options": [{"label": "Build one with me", "action": "setup.build_resume"}]},
    {"id": "work", "kind": "text", "question": "What work do you want next, and where?",
     "help": "In your own words: a job title or two is plenty.",
     "fields": [{"key": "work", "kind": "text", "label": "The work you want next"},
                {"key": "place", "kind": "place", "label": "Where you'd like to work"}]},
    {"id": "right_to_work", "kind": "choice",
     "question": "Can you work in {country} without an employer sponsoring you, now and later?",
     "fields": [{"key": "answer", "kind": "choice", "label": "",
                 "choices": [["yes", "Yes, now and later"],
                             ["for_now", "Yes for now, but I'll need it later"],
                             ["no", "No, I'd need sponsoring"]]},
                {"key": "status", "kind": "text", "label": "Your visa or status, if you like"}]},
    {"id": "pay", "kind": "money",
     "question": "What do you earn now, and what's the least you'd move for?",
     "fields": [{"key": "now", "kind": "money", "label": "Now, a year"},
                {"key": "least", "kind": "money", "label": "The least you'd move for"}]},
    {"id": "roles", "kind": "multi",
     "question": "I'd search for these. Keep the ones you want, and add any.",
     "fields": [{"key": "roles", "kind": "multi", "label": "Roles to search for"}]},
    {"id": "avoid", "kind": "text",
     "question": "Any employers or kinds of work to avoid? And should your employer not find out?",
     "fields": [{"key": "avoid", "kind": "text", "label": "Employers or kinds of work to avoid"},
                {"key": "confidential", "kind": "choice",
                 "label": "Keep it from your current employer?",
                 "choices": [["yes", "Yes, keep it quiet"], ["no", "No need"]]}]},
)
STEP_IDS = tuple(s["id"] for s in STEPS)
# Shown after the six only when they chose to build a resume with Claude.
HISTORY = {"id": "history", "kind": "text",
           "help": "One job at a time, newest first. Say \"that's all\" when you're done.",
           "options": [{"label": "That's all", "action": "setup.answer",
                        "value": {"done": True}}]}


def _module(name: str):
    try:
        return person.module(name)
    except (person.NoProfile, SyntaxError):
        return None


def _profile_text(name: str) -> str:
    try:
        with open(os.path.join(profile_dir(), name), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _known(step: str) -> tuple[dict, str]:
    """(the values the profile already holds for a step, where they came from) or ({}, "")."""
    if not set_up():
        return {}, ""
    search = _module("search")
    if step == "resume":
        return ({"resume": "on file"}, "your profile") if re.search(
            r"^###\s+\S", _profile_text("01-candidate-profile.md"), re.M) else ({}, "")
    if step == "work":
        place = str(person.get("identity.location", "") or "")
        work = ", ".join(getattr(search, "SCRAPE_QUERIES", None) or [])
        return ({"work": work, "place": place}, "your profile") if work and place else (
            {"place": place} if place else {}, "")
    if step == "right_to_work":
        try:
            import screening_answers
            needs = screening_answers.requires_sponsorship()
        except Exception:  # noqa: BLE001  no screening sheet yet
            return {}, ""
        return {"answer": "no" if needs else "yes"}, "your profile"
    if step == "pay":
        floor = getattr(search, "SALARY_FLOOR", None)
        return ({"least": {"amount": floor, "currency": getattr(search, "CURRENCY_CODE", "")}},
                "your profile") if floor else ({}, "")
    if step == "roles":
        roles = list(getattr(search, "SCRAPE_QUERIES", None) or [])
        return ({"roles": roles}, "your profile") if roles else ({}, "")
    if step == "avoid":
        return ({"avoid": "on file"}, "your profile") if hasattr(search, "BAR_EXCLUDED") else ({}, "")
    return {}, ""


def _country() -> str:
    a = answers().get("work") or {}
    place = str(a.get("place") or "")
    if set_up():
        try:
            c = person.country()
        except Exception:  # noqa: BLE001
            c = ""
        if c:
            return {"GB": "the UK", "US": "the US", "CA": "Canada", "AU": "Australia",
                    "IE": "Ireland", "NZ": "New Zealand"}.get(c, c)
    return place.split(",")[-1].strip() if "," in place else (place or "the country you named")


def _proposed() -> list[str]:
    got = answers().get("proposed_roles") or {}
    roles = got.get("roles") if isinstance(got, dict) else got
    return [str(r) for r in roles or [] if str(r).strip()]


def _history_question(a: dict) -> str:
    try:
        import history_interview
        jobs = list((a.get("history") or {}).get("jobs") or [])
        done = bool((a.get("history") or {}).get("done"))
        q = history_interview.ask("computer", done=len(jobs), rest=done) or \
            history_interview.ask("computer", done=len(jobs), rest=True)
        # The page has a box to type in, and nothing to talk into or paste a page from.
        return "\n".join(ln for ln in q.splitlines()
                         if ln.strip() not in (history_interview.PASTE, history_interview.MIC))
    except Exception:  # noqa: BLE001
        return "Tell me about your latest job: title, employer, town and dates."


def setup_section(today: dt.date, targets: dict) -> dict:
    """The model's `setup`: where setup is, each question as the page asks it (what is
    known prefilled, never asked again), what is left, the research and its progress."""
    import app_model
    a = answers()
    finished = _finished()
    if finished:
        return {"state": "done", "say": "", "progress": {"done": len(STEPS), "total": len(STEPS),
                                                          "label": f"{len(STEPS)} of {len(STEPS)}"},
                "next": None, "steps": [], "research": [], "phases": _phases(a, True)}
    steps, nxt, done = [], None, 0
    order = list(STEPS)
    if (a.get("resume") or {}).get("source") == "build":
        order.insert(1, dict(HISTORY, question=_history_question(a),
                             fields=[{"key": "text", "kind": "text",
                                      "label": "This job, in your words"}]))
    for n, spec in enumerate(order, 1):
        sid = spec["id"]
        known, source = _known(sid)
        mine = a.get(sid) if isinstance(a.get(sid), dict) else {}
        if sid == "history":
            is_done = bool(mine.get("done"))
        elif sid == "resume":
            is_done = bool(mine.get("source")) or bool(known)
        else:
            is_done = bool(mine) or bool(known) and source == "your profile" and _complete(sid, known)
        fields = []
        for f in spec["fields"]:
            f = dict(f)
            value = mine.get(f["key"]) if mine else None
            if value is None:
                value = known.get(f["key"])
            if sid == "resume":
                value = ("added" if mine.get("source") in ("asset", "pasted") else
                         "building it with you" if mine.get("source") == "build" else
                         "on file" if known else None)
            if sid == "roles" and f["key"] == "roles":
                f["choices"] = [[r, r] for r in (_proposed() or list(known.get("roles") or []))]
            f["value"] = value
            fields.append(f)
        waiting = None
        if sid == "roles" and not is_done and not _proposed():
            waiting = "I'll suggest these once I've read your resume."
        status = "done" if is_done else ("waiting" if waiting else "next" if nxt is None else "later")
        if status == "done":
            done += 1
        elif status == "next":
            nxt = sid
        item = {"id": f"setup-{sid}", "step": sid, "n": n, "kind": spec["kind"],
                "question": spec["question"].replace("{country}", _country()) if sid != "history"
                else spec["question"],
                "help": spec.get("help", ""), "fields": fields,
                "options": [dict(o) for o in spec.get("options", [])],
                "known_from": source if (known and not mine) else ("your answer" if mine else ""),
                "status": status, "waiting": waiting,
                "skippable": sid in ("pay", "avoid", "right_to_work"),
                "rev": app_model.rev_of(sid, mine, known)}
        steps.append(item)
        targets[item["id"]] = {"kind": "setup_step", "step": sid, "rev": item["rev"]}
    total = len(steps)
    st = _setup_state()
    return {"state": st["state"], "say": st["say"],
            "progress": {"done": done, "total": total, "label": f"{min(done + 1, total)} of {total}"
                         if done < total else f"{total} of {total}"},
            "next": nxt, "steps": steps, "research": _research(a),
            "phases": _phases(a, False)}


def _complete(step: str, known: dict) -> bool:
    if step == "work":
        return bool(known.get("work") and known.get("place"))
    return True


def _finished() -> bool:
    """A setup that ended: person.json and setup's own finished mark (place.py finished), or
    a profile from before the page with no mark and no answers (an old install is set up, and
    never set up again)."""
    if not set_up():
        return False
    mark = (_read_json(os.path.join(profile_dir(), "place.json"), {}).get("setup") or {})
    if mark.get("finished"):
        return True
    if mark.get("started"):
        return False
    return not os.path.isfile(os.path.join(profile_dir(), ANSWERS))


def _setup_state() -> dict:
    """Where setup stands: place.setup_state(), the one detector (its setup mark in
    profile/place.json, and for a copy with no profile, master and the other chats'
    branches, read without fetching), plus "partial": answers from the page or part of a
    profile, and no setup running."""
    try:
        import place
        got = place.setup_state(fetch=False, profile=profile_dir())
    except Exception:  # noqa: BLE001  no git, or place.py missing: judged from the folder
        got = {"state": "here" if set_up() else "none", "say": ""}
    state = got["state"]
    if state == "here" and not _finished():
        state = "partial"
    if state == "none" and os.path.isdir(profile_dir()) and os.listdir(profile_dir()):
        state = "partial"
    return {"state": state, "say": got.get("say", "") if state in ("going", "stopped") else ""}


RESEARCH = (("boards", "Job sites for your work and city"),
            ("market", "Pay for your role and city"),
            ("documents", "How resumes are written where you are"),
            ("voice", "Where the people worth meeting are named"),
            ("employers", "The employers' own job boards"))


def _research(a: dict) -> list:
    """Setup's research, a work item each (`research~<topic>`), done once its part of the
    profile is written (tools/build_versions.py records it)."""
    import page_db
    rec = _read_json(os.path.join(profile_dir(), "build_versions.json"), {})
    out = []
    stages = page_db.progress("research")["stages"]
    for topic, label in RESEARCH:
        done = topic in rec or (topic == "employers" and os.path.isfile(
            os.path.join(profile_dir(), "boards.py")))
        out.append({"topic": topic, "label": label, "status": "done" if done else "waiting",
                    "work": f"research~{topic}", "stages": stages})
    return out


def _phases(a: dict, finished: bool) -> list:
    st = os.path.isfile
    p = profile_dir()
    rounds = os.path.isdir(person.state("documents", "rounds")) and any(
        f.endswith(".json") for f in os.listdir(person.state("documents", "rounds")))
    have = {
        "copy": True,
        "questions": finished or all((a.get(s) or {}) for s in STEP_IDS) or set_up(),
        "profile": st(os.path.join(p, "CLAUDE.md")) and st(os.path.join(p, "person.json")),
        "research": st(os.path.join(p, "build_versions.json")),
        "shortlist": rounds,
        "brief": st(os.path.join(p, "routines.json")),
    }
    labels = (("copy", "Your private copy"), ("questions", "Your answers"),
              ("profile", "Your profile written"), ("research", "The research"),
              ("shortlist", "Your first shortlist"), ("brief", "Your brief"))
    return [{"key": k, "label": label, "status": "done" if have[k] else "waiting"}
            for k, label in labels]


# ------------------------------------------------------------------ what only the person can do

OUTSIDE = {
    # id: (registry entry, what it is for, in a few words)
    "copy": ("make-copy", "Your own private copy, where everything about you is kept"),
    "private": ("make-private", "Your copy must be private before anything about you goes in"),
    "job-sites": ("cloud-internet", "Lets this chat reach job sites"),
    "linkedin": ("browser-pane-stay-signed-in", "Signed in to LinkedIn on your computer"),
}
# 4.0 recommends no chat on the computer (UX_DECISIONS, "Chats"): there is no card for one.


def setup_script_line() -> str:
    """The one line that caches the tools in the cloud's own settings, as
    tools/setup_env.sh's header gives it (the screen's name is the registry's,
    cloud-setup-script)."""
    try:
        with open(os.path.join(_HERE, "setup_env.sh"), encoding="utf-8") as fh:
            m = re.search(r"^#\s{3,}(apt-get .+)$", fh.read(), re.M)
        return m.group(1).strip() if m else ""
    except OSError:
        return ""


def outside_item(key: str, owner: str = "", name: str = "") -> dict:
    """A card for something only the person can do: the numbered steps the registry prints
    (never typed by hand), the official page, and the day the steps were checked."""
    import app_model
    import claude_surfaces
    eid, why = OUTSIDE[key]
    lines = claude_surfaces.steps(eid, name=name or "your copy", owner=owner, page=True)
    entry = claude_surfaces.entry(eid)
    options = [{"label": "Done", "action": "setup.done"}]
    if key == "copy":
        options.insert(0, {"label": "Make it for me", "action": "setup.make_copy"})
    item = {"id": f"q-setup-{key}", "kind": "setup", "title": lines[0].rstrip(":"),
            "body": why + ".", "steps": [ln for ln in lines[1:] if ln.strip()],
            "link": claude_surfaces.official(entry), "checked": entry.get("verified_on", ""),
            "options": options, "about": {"step": key},
            "rev": app_model.rev_of(key, lines)}
    if key == "copy":
        # GitHub fills in its new-repository form from these (docs.github.com, "Creating a
        # repository from a URL query", read 2026-10-25): one tap opens it with the app as
        # the template and Private chosen. The steps are the way when it opens empty.
        item["open"] = {"label": "Make my private copy", "url": COPY_LINK}
    return item


def outside_items(targets: dict, kind: dict | None = None) -> list:
    """The cards for this copy now: its privacy, the job sites, the computer chat and
    LinkedIn, each only while it is still to do."""
    out = []
    owner, name = (kind or {}).get("owner", ""), (kind or {}).get("name", "")
    k = (kind or {}).get("kind", "")
    if k == "app":
        out.append(outside_item("copy"))
    elif k == "public":
        out.append(outside_item("private", owner, name))
    blocked = job_sites().get("blocked") or []
    if blocked:
        # Found by code (env_check reaching the boards), never asked; the next check ticks
        # it off by itself once the setting is changed.
        import claude_surfaces
        item = outside_item("job-sites")
        item["body"] = (f"This chat can't reach job sites yet ({', '.join(blocked[:3])}). "
                        "I won't search before then: it would only find old jobs.")
        more = claude_surfaces.steps("cloud-setup-script", page=True)
        item["more"] = {"title": more[0].rstrip(":"), "steps": [ln for ln in more[1:] if ln],
                        "copy": setup_script_line(),
                        "checked": claude_surfaces.entry("cloud-setup-script").get("verified_on", "")}
        out.append(item)
    if set_up():
        try:
            import place
            # Only for someone who already has a chat on their computer and is not signed in
            # there: nobody is sent to make one.
            if place.has_local() and not place.signed_in_ever():
                out.append(outside_item("linkedin", owner, name))
        except Exception:  # noqa: BLE001
            pass
    for item in out:
        targets[item["id"]] = {"kind": "outside", "key": item["about"]["step"], "rev": item["rev"]}
    return out


# ------------------------------------------------------------------ updates


def _app_changelog(ref: str) -> str:
    code, out = _git("show", f"{ref}:CHANGELOG.md")
    return out if code == 0 else ""


def _upgrade_commits(days: int = 60) -> list[dict]:
    """The background upgrades' own commits ("Profile upgrade: <id>", one plain line in the
    body: upgrade.md Step 2), newest first, and whether each was taken back since."""
    # The search's own history: the state root, which is the repo itself except in a test.
    root = person.state()
    code, out = _git("log", f"--since={days}.days", "--format=%H%x1f%cs%x1f%s%x1f%b%x1e",
                     "--grep=^Profile upgrade:", "HEAD", root=root)
    if code:
        return []
    code, rev = _git("log", f"--since={days}.days", "--format=%b", "--grep=This reverts commit",
                     "HEAD", root=root)
    reverted = set(re.findall(r"This reverts commit ([0-9a-f]{40})", rev))
    got = []
    for rec in out.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) == 4 and parts[0].strip():
            sha, day, subject, body = parts
            said = next((ln.strip() for ln in body.splitlines() if ln.strip()
                         and not ln.startswith(("Co-Authored-By:", "Claude-Session:"))), "")
            got.append({"sha": sha.strip(), "date": day, "id": subject.split(":", 1)[1].strip(),
                        "said": said, "reverted": sha.strip() in reverted})
    return got


# The code that decides how a record file is stored: an update that changes one of these, or
# whose CHANGELOG says "State migration:", changes stored records, so it waits for running
# work to land (UX_DECISIONS, "Updates while work runs").
MIGRATION_FILES = ("tools/merge_state.py", "tools/csv_store.py", "tools/network/schema.py")
MIGRATION_MARK = "State migration:"


def is_migration(ref: str) -> bool:
    code, names = _git("diff", "--name-only", "HEAD", ref)
    if code == 0 and any(n.strip() in MIGRATION_FILES for n in names.splitlines()):
        return True
    code, diff = _git("diff", "HEAD", ref, "--", "CHANGELOG.md")
    return code == 0 and any(ln.startswith("+") and MIGRATION_MARK in ln
                             for ln in diff.splitlines())


def updates_section(today: dt.date, targets: dict) -> dict:
    """The model's `updates`: the version here and the newest, an update waiting (with an
    "Update now" for someone who chose to say when), what changed in plain lines, what the
    background upgrades did (each with its undo) and what is still to come."""
    import app_model
    version, changed = "", []
    try:
        import release
        secs = release.sections()
        version = secs[0]["version"] if secs else ""
        for s in secs[:2]:
            lines = [ln[2:].strip() for ln in release.short(s["notes"]).splitlines()
                     if ln.startswith("- ") and not ln.startswith("- And ")]
            changed.append({"version": s["version"], "date": s["date"], "lines": lines[:6]})
    except Exception:  # noqa: BLE001
        pass
    mode, newest, waiting = "auto", version, None
    try:
        import release
        import sync_app
        import app_model
        try:
            mode = app_model.setting_values().get("app_updates", "auto")
        except Exception:  # noqa: BLE001  no profile yet: updates come by themselves
            mode = "auto"
        text = _app_changelog(sync_app.APP)
        if text:
            secs = release.sections(text)
            newest = secs[0]["version"] if secs else version
        sha = sync_app.waiting() if text else ""
        if sha:
            line = sync_app.waiting_line(None, False)
            migration = is_migration(sync_app.APP)
            import page_db
            est = page_db.progress("update")["total_s"]
            about = "about a minute" if est < 90 else f"about {round(est / 60)} minutes"
            waiting = {"id": "update-now", "line": line, "sha": sha[:12],
                       "kind": "migration" if migration else "code",
                       # A change to how a record file is stored waits for running work to
                       # land, and work asked for meanwhile starts after it; code lands at once.
                       "waits_for": "running work" if migration else None,
                       "hold_line": f"Starts after the update, {about}" if migration else None,
                       "est_s": est,
                       "action": "app.update_now" if mode == "when_asked" else None,
                       "rev": app_model.rev_of(sha, migration)}
            targets["update-now"] = {"kind": "update", "sha": sha, "migration": migration,
                                     "rev": waiting["rev"]}
    except Exception:  # noqa: BLE001  no git here: nothing said to wait
        pass
    done = []
    try:
        import profile_upgrades
        gives = {u.id: u.gives for u in profile_upgrades.REGISTRY}
        for c in _upgrade_commits():
            uid = f"upg-{c['sha'][:10]}"
            line = c["said"] or gives.get(c["id"], "")
            line = (line[:1].upper() + line[1:]).rstrip(".") + "." if line else \
                "An improvement to your search."
            item = {"id": uid, "line": line, "on": c["date"],
                    "undone": c["reverted"], "undo": None if c["reverted"] else "upgrade.undo",
                    "rev": app_model.rev_of(c["sha"], c["reverted"])}
            done.append(item)
            targets[uid] = {"kind": "upgrade", "sha": c["sha"], "rev": item["rev"]}
        listed = profile_upgrades.listed_ids() if set_up() else []
        by = {u.id: u for u in profile_upgrades.REGISTRY}
        pending = [{"id": i, "line": (by[i].gives[:1].upper() + by[i].gives[1:] + "."),
                    "needs": by[i].needs} for i in listed if i in by]
    except Exception:  # noqa: BLE001
        pending = []
    return {"version": version, "newest": newest, "mode": mode, "waiting": waiting,
            "changed": changed, "done": done, "pending": pending}


def upgrade_questions(targets: dict) -> list:
    """The questions an update left for the person, as cards: Yes, or Not now."""
    import app_model
    try:
        import profile_upgrades
        by = {u.id: u for u in profile_upgrades.REGISTRY}
        listed = profile_upgrades.listed_ids() if set_up() else []
    except Exception:  # noqa: BLE001
        return []
    out = []
    for uid in listed:
        u = by.get(uid)
        if u is None or u.needs == "nobody" or not u.ask:
            continue
        nid = f"q-upgrade-{uid}"
        item = {"id": nid, "kind": "question", "title": u.ask, "body": "",
                "options": [{"label": "Yes", "action": "needs.answer", "value": "yes"},
                            {"label": "Not now", "action": "needs.answer", "value": "no"}],
                "about": {}, "rev": app_model.rev_of(uid, u.ask)}
        out.append(item)
        targets[nid] = {"kind": "upgrade_ask", "upgrade": uid, "ask": u.ask, "rev": item["rev"]}
    return out


# ------------------------------------------------------------------ start: one entry point


def _sync_stale() -> bool:
    try:
        import sync_app
        return not sync_app.is_the_app(ROOT) and sync_app.last_checked() < dt.date.today().isoformat()
    except Exception:  # noqa: BLE001
        return True


def _page_current() -> bool:
    if not page_record().get("url"):
        return False
    if not set_up():
        return True
    try:
        import build_versions
        return not build_versions.behind("page")
    except Exception:  # noqa: BLE001
        return True


def state(runner=None) -> dict:
    """Everything start decides on, read once."""
    kind = repo_kind(runner)
    st = _setup_state() if kind["kind"] not in ("app", "none") else {"state": "", "say": ""}
    return {"repo": kind, "setup": st, "page": page_record(), "page_current": _page_current(),
            "stale": _sync_stale(), "answers": answers(), "set_up": set_up()}


def _publish_lines(st: dict, n: int) -> list[str]:
    url = st["page"].get("url", "")
    lines = []
    if url:
        lines += [f"{n}. The person's page is {url}. Build it again: python3 tools/app.py page "
                  "--out <your scratchpad>/page.html",
                  f"{n + 1}. Read the page first (Artifact, action read, url {url}), then "
                  f"publish the new file to that same url with the capabilities "
                  "`python3 tools/app_page.py --capabilities` prints. Then python3 tools/app.py "
                  f"published {url}"]
    else:
        lines += [f"{n}. Build the person's page: python3 tools/app.py page --out <your "
                  "scratchpad>/page.html",
                  f"{n + 1}. Publish it (Artifact, action publish, icon briefcase), with the "
                  "capabilities `python3 tools/app_page.py --capabilities` prints. Then keep its "
                  "address: python3 tools/app.py published <the url the publish gave>"]
    lines.append(f"{n + 2}. Publishing makes this chat watch the page. If the publish result "
                 "says this chat is not watching it, watch it (ArtifactComments, watch).")
    return lines


NO_PUBLISH = ("If this chat cannot publish (no Artifact tool, or the publish is refused), run "
              "python3 tools/app.py published none, ask setup's questions in this chat instead, "
              "as .claude/commands/setup.md says, and say nothing about a page.")


def start(on: str = "", tools: str = "", page_url: str = "", runner=None) -> tuple[int, list[str]]:
    """(exit code, the lines a chat follows): what this chat does next, whatever the copy's
    state. Exit 0 with steps to follow; 1 when nothing may be written here."""
    st = state(runner)
    kind = st["repo"]["kind"]
    sync = (["python3 tools/sync_app.py --pull",
             f"python3 tools/sync_app.py --on \"{on or '<this chat model>'}\" --tools "
             f"\"{tools or '<the browser tools this chat has>'}\""] if st["stale"] else [])
    if page_url and not st["page"].get("url") and kind == "private":
        try:
            record_page(page_url)
            st["page"] = page_record()
        except ValueError:
            pass
    out: list[str] = []
    if kind == "none":
        out += ["app start: this folder is not a copy of the job search on GitHub.",
                "Claude: nothing about the person may be written here. Tell them, in these words:"]
        out += ["  " + ln for ln in _steps("make-copy")]
        out.append("  Then open a chat on the new copy and say \"set me up\".")
        return 1, out
    if kind == "app":
        out += ["app start: this is the app itself, which is public. Nothing about the person "
                "may ever be written here.",
                "Claude: make the person's own private copy first, the first way that works:",
                f"1. On a computer with GitHub's tool signed in (gh auth status says so): ask "
                f"them once, then run gh repo create {COPY_NAME} --template {APP_REPO} --private "
                "(never --public). It prints the new copy's address.",
                "2. Otherwise, tell them, in these words:"]
        out += ["   " + ln for ln in _steps("make-copy")]
        out += ["3. Once the copy exists, carry on in it: clone it into a folder of its own "
                "(gh repo clone <owner>/<name> <folder>), then run python3 tools/app.py start "
                "there, adding --page <url> if this chat already published a page for them. In "
                "a cloud chat, attach it first (add_repo, access push) or ask them to open a "
                "chat on it and say \"set me up\"."]
        return 1, out
    if kind == "public":
        owner, name = st["repo"]["owner"], st["repo"]["name"]
        out += ["app start: this copy is public. Nothing about the person may be written "
                "here until it is private, and never change that yourself.",
                "Claude: tell them why in one line (everything about them, their work history, "
                "pay and every contact, goes into this copy, which anyone can read while it is "
                "public), then, in these words:"]
        out += ["  " + ln for ln in _steps("make-private", owner=owner, name=name)]
        out.append("  When they say it's done, run python3 tools/app.py start again.")
        return 1, out
    setup = st["setup"]["state"]
    n = 1
    steps: list[str] = []
    if kind == "unknown":
        steps.append(f"{n}. Check the copy is private before anything about the person is "
                     "written: gh api repos/<owner>/<name> --jq .private must say true. Where "
                     "it cannot be checked, ask them once to look: GitHub shows Private or "
                     "Public beside the copy's name. Public: stop, and run this again once it "
                     "is private.")
        n += 1
    for cmd in sync:
        steps.append(f"{n}. {cmd}   (the day's update check; do what it prints, then carry on)")
        n += 1
    if setup in ("landed", "branch"):
        steps.append(f"{n}. The search is set up on another chat's work: bring it in first "
                     "(python3 tools/place.py state says how), then run python3 tools/app.py "
                     "start again.")
        return 0, [f"app start: set up elsewhere ({setup})", "Claude, do this:"] + steps
    if setup == "going":
        say = st["setup"]["say"] or ("Your setup is still going in your other chat; I'll be "
                                     "ready here once it's done.")
        steps.append(f"{n}. Start nothing: another chat is setting them up. Tell them, in "
                     f"these words: \"{say}\"")
        return 0, ["app start: setup going in another chat", "Claude, do this:"] + steps
    no_page = _no_page_recently(st["page"])
    if not no_page and (not st["page_current"] or not st["page"].get("url")):
        steps += _publish_lines(st, n)
        n += 3
    if os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true" and \
            job_sites().get("checked") != dt.date.today().isoformat():
        try:
            check_job_sites()
        except Exception:  # noqa: BLE001  the day's sync checks it too
            pass
    resume = (st["answers"].get("resume") or {}) if isinstance(st["answers"], dict) else {}
    if resume.get("asset") and not resume.get("file"):
        url = st["page"].get("url") or "<the page's url>"
        steps.append(f"{n}. The person added their resume on the page. Save it: Artifact, "
                     f"action read, url {url}, path {resume['asset']}, out_dir documents/cv. "
                     "Then python3 tools/app.py resume-saved <the file it saved> --asset "
                     f"{resume['asset']}, and delete it from the page (Artifact, action delete, "
                     f"url {url}, path {resume['asset']}): the page is no place to keep it.")
        n += 1
    if not st["set_up"] or setup in ("none", "partial", "self", "stopped") or not _finished():
        done = sum(1 for s in STEP_IDS if (st["answers"].get(s) or {}))
        if no_page:
            steps.append(f"{n}. Setup carries on from where it is ({done} of {len(STEP_IDS)} "
                         "answered), in this chat: this chat has no pages. Follow "
                         ".claude/commands/setup.md; it reads every answer already in "
                         "profile/setup_answers.json and never asks one again.")
        else:
            steps.append(f"{n}. Setup carries on from where it is ({done} of {len(STEP_IDS)} "
                         "answered): follow .claude/commands/setup.md, which reads every "
                         "answer from profile/setup_answers.json and never asks one again. "
                         "The page asks the rest, one at a time; this chat asks nothing.")
            n += 1
            steps.append(f"{n}. Tell the person one line, and nothing more: \"Your setup is "
                         "on your page: <its url>. Answer there, one question at a time; "
                         "I'll do the rest.\"")
            n += 1
            steps.append(f"{n}. {NO_PUBLISH}")
        head = "app start: " + ("setting up" if setup in ("none", "partial", "") else
                                f"setup {setup}")
        return 0, [head, "Claude, do this, in order:"] + steps
    steps.append(f"{n}. The page shows the updates and what each one did. If the update check "
                 "listed improvements Claude applies itself, start the background /upgrade "
                 "(.claude/commands/upgrade.md); its progress goes on the page.")
    n += 1
    if st["page"].get("url"):
        steps.append(f"{n}. Bring the page's data up to date: python3 tools/app.py view <your "
                     "scratchpad>/view --dump <a dump of the page's view and meta> and send the "
                     "batch it prints. Then carry on with what the person asked.")
    head = "app start: set up" + ("" if st["page_current"] else ", page to publish")
    return 0, [head, "Claude, do this:"] + steps


def _no_page_recently(rec: dict, today: dt.date | None = None) -> bool:
    none = rec.get("none")
    if not none or rec.get("url"):
        return False
    try:
        return ((today or dt.date.today()) - dt.date.fromisoformat(str(none)[:10])).days < NO_PAGE_DAYS
    except ValueError:
        return False


def _steps(eid: str, owner: str = "", name: str = "") -> list[str]:
    import claude_surfaces
    return claude_surfaces.steps(eid, name=name or "your copy", owner=owner)


NO_PAGE_DAYS = 30


def record_no_page(today: dt.date | None = None) -> str:
    """This chat cannot publish (a surface with no pages): the sync stops asking for a month."""
    got = page_record()
    got["none"] = (today or dt.date.today()).isoformat()
    return _write_json(os.path.join(profile_dir(), PAGE), got)


def page_line(today: dt.date | None = None) -> str:
    """The line the sync prints when the person's page is missing or out of date, so a chat
    whose instructions predate the page still sets it up. Quiet for a month after a chat
    said it cannot publish."""
    try:
        if not os.path.isdir(profile_dir()):
            return ""
        if _page_current():
            return ""
        none = page_record().get("none")
        if none and not page_record().get("url"):
            days = ((today or dt.date.today()) - dt.date.fromisoformat(str(none)[:10])).days
            if days < NO_PAGE_DAYS:
                return ""
    except Exception:  # noqa: BLE001
        return ""
    what = "is out of date" if page_record().get("url") else "is not published yet"
    return (f"Claude: the person's page {what}. Before the rest, run python3 tools/app.py start "
            "and do what it prints (it publishes or refreshes the page; nothing to ask them).")
