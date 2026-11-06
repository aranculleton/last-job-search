#!/usr/bin/env python3
"""Setup, a setup left part-way, an old install and the app's updates, all through the page.

The person says "set me up" in a chat, once. From then on the questions are asked on their
page, one at a time with "2 of 6", the research shows its progress there, and what only
they can do outside it (their private copy, the cloud setting that lets the chat reach job
sites) is a card with dated steps from tools/claude_surfaces.json and the official link.
Signing in to LinkedIn is the page's own reading card (app.js readingCard), in the Claude
desktop app: no chat on the computer is set up or offered (4.3).

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
import time

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
KINDS = ("app", "public", "fork", "private", "unknown", "none")
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
    """What the person answered on the page, by step: profile/setup_answers.json. A typed
    "that's all" saved as a job before 3 November (X-40) is read as the end of the jobs, so a
    setup part way through takes it right, and /setup never writes it into a profile."""
    got = _read_json(os.path.join(profile_dir(), ANSWERS), {})
    h = got.get("history") if isinstance(got, dict) else None
    if isinstance(h, dict) and isinstance(h.get("jobs"), list) and \
            any(isinstance(j, str) and ENOUGH.match(j) for j in h["jobs"]):
        got["history"] = dict(h, jobs=[j for j in h["jobs"]
                                       if not (isinstance(j, str) and ENOUGH.match(j))],
                              done=True)
    return got


def save_answers(data: dict) -> str:
    return _write_json(os.path.join(profile_dir(), ANSWERS), data)


def page_record() -> dict:
    """The page's own address and when it was published: profile/app.json."""
    return _read_json(os.path.join(profile_dir(), PAGE), {})


def parts_held(folder: str) -> list[str]:
    """The code files a page built in parts (app.py page --out-dir) loads, from its page.html:
    what the published page holds once every publish the build printed went through."""
    try:
        with open(os.path.join(folder, "page.html"), encoding="utf-8") as fh:
            page = fh.read()
    except OSError:
        return []
    return sorted(set(re.findall(r'<(?:script src|link rel="stylesheet" href)="(code/[^"]+)"',
                                 page)))


def record_page(url: str, chat: str = "", now: dt.datetime | None = None,
                parts: str = "", current: bool = True) -> str:
    """Keep the page's address once a chat has published it, and mark the page's build part
    done at this version (tools/build_versions.py "page"). `parts`: the folder it was built
    in, in parts, every publish gone through: which code files the page holds (`code`) and
    the capabilities it was declared with (`caps`) are kept, so the next publish sends only
    what changed. Without it nothing is assumed, and the next publish sends every file."""
    import app_model
    url = str(url or "").strip()
    if not re.match(r"^https://claude\.ai/\S+$", url):
        raise ValueError("that is not a claude.ai page address")
    got = page_record()
    held = parts_held(parts) if parts else []
    if held:
        import app_page
        got.update(code=held, caps=app_page.caps_hash())
    else:
        got.pop("code", None)
        got.pop("caps", None)
    got.pop("none", None)        # a chat published it: whatever a chat said before is past
    got.update(url=url, published_at=app_model.stamp(now or dt.datetime.now(dt.timezone.utc)),
               by=chat or got.get("by") or "", title_name=_first_name())
    path = _write_json(os.path.join(profile_dir(), PAGE), got)
    # `current` False: the address kept again from a chat's own history (learned._heal_page),
    # not a publish just made, so whether the page's code is current is left as recorded.
    if current and set_up():
        try:
            import build_versions
            build_versions.record(["page"])
        except Exception:  # noqa: BLE001  the address is kept either way
            pass
    return path


# ------------------------------------------------------------------ git and GitHub


def _git(*args, timeout: int = 30, root: str = "") -> tuple[int, str]:
    # A git command another one holds index.lock against (a landing's commit, the update
    # check) is refused at once: tried again for a few seconds, as tools/land.py does.
    for wait in (0.5, 1, 2, None):
        try:
            r = subprocess.run(["git", "-C", root or ROOT, *args], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=timeout,
                               stdin=subprocess.DEVNULL,
                               env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
        except (OSError, subprocess.TimeoutExpired):
            return 1, ""
        if r.returncode == 0 or wait is None or "index.lock" not in (r.stderr or ""):
            return r.returncode, r.stdout
        time.sleep(wait)
    return r.returncode, r.stdout


def take_master() -> str:
    """Bring what other chats have landed on master into this copy before the page is drawn
    from it. A chat's copy holds other chats' work only once it takes master, and a page
    update drawn from a copy behind master dropped another chat's results: a finished search
    could undo a finished draft, and the next update the search (the release review,
    2026-11-03). "" when nothing was needed, it was taken, or it cannot be checked (no
    network, not a person's copy); otherwise the line saying why the page was left as it
    is. Never in the app itself, whose copies are not a person's."""
    if not os.path.isfile(os.path.join(ROOT, "profile", "person.json")):
        return ""
    owner, name = origin()
    if not owner or f"{owner}/{name}" == APP_REPO:
        return ""
    try:
        import land
        held = land._holding(ROOT)
        mine = held.__enter__()
    except Exception:  # noqa: BLE001  an older land.py: taken as before
        held, mine = None, True
    try:
        if not mine:
            # The landing merges master itself, and two merges at once fought over git's
            # index (the release review, 2026-11-03): the page is drawn from the copy as it
            # is. The landing's own lock, taken in one step for the merge below, so a landing
            # starting this moment waits its turn too (2026-11-06).
            return ""
        return _take_master()
    finally:
        if held is not None:
            held.__exit__(None, None, None)


def _take_master() -> str:
    if _merging():
        # A merge being settled by hand: a merge here failed on it, and the abort that
        # followed threw the settling away (the release review, 2026-11-03).
        return ("app: a merge is being settled in this copy: finish it (or git merge --abort), "
                "then run this again. The page was left as it is.")
    if _git("fetch", "-q", "origin", "master", timeout=60)[0] != 0:
        return ""
    if _git("merge-base", "--is-ancestor", "origin/master", "HEAD")[0] == 0:
        return ""
    # The row-by-row driver set first, and a file two chats changed settled, never left: a
    # job's chat is a fresh clone that never ran the sync, and its page update stopped on two
    # appended tracker rows (the stranger audit, 2026-11-03, X-2).
    try:
        import land
        ok, _said = land.merge_in(ROOT, "origin/master")
    except Exception:  # noqa: BLE001  the merge as it was
        ok = _git("merge", "--no-edit", "-q", "origin/master", timeout=120)[0] == 0
        if not ok and _merging():
            _git("merge", "--abort")
    if ok:
        return ""
    return ("app: this copy is behind master, and taking master stopped on a change of this "
            "chat's own in the same file: save this chat's work first, then run this again. The "
            "page was left as it is, so nothing another chat saved is lost from it.")


def _merging() -> bool:
    return _git("rev-parse", "-q", "--verify", "MERGE_HEAD")[0] == 0


def origin() -> tuple[str, str]:
    """(owner, name) of this copy on GitHub, or ("", "") when it has none: one reader of the
    address for every form (sync_app.repo_of), a cloud chat's proxy included."""
    code, url = _git("remote", "get-url", "origin")
    if code != 0:
        return "", ""
    import sync_app
    return sync_app.repo_of(url)


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
    """"private", "public", "fork" (a public fork, which GitHub never lets be made private:
    "You cannot change the visibility of a fork by itself", docs.github.com, About forks,
    read 2026-11-03), or "" when GitHub could not be asked. Never changed here."""
    if not owner:
        return ""
    code, out = _gh("api", f"repos/{owner}/{name}", "--jq", '"\\(.private) \\(.fork)"',
                    runner=runner)
    words = out.strip().splitlines()[-1].strip().lower().split() if code == 0 and out.strip() \
        else []
    seen = {"true": "private", "false": "public"}.get(words[0] if words else "", "")
    return "fork" if seen == "public" and words[1:2] == ["true"] else seen


def repo_kind(runner=None) -> dict:
    """What this folder is: {"kind": "app" | "public" | "fork" | "private" | "unknown" |
    "none", "owner", "name"}. "app" is the app itself; "fork" a public fork of it, which can
    never be made private, so it is replaced by a new private copy; "public" any other public
    copy; "none" a folder with no copy on GitHub behind it."""
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
    return {"kind": seen if seen in ("private", "public", "fork") else "unknown",
            "owner": owner, "name": name}


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
     # The page's store keeps a PDF or a text file; a Word file it refuses (journeys 21).
     "fields": [{"key": "resume", "kind": "upload-or-paste",
                 "label": "Your resume (a PDF or a text file), or paste it"}],
     "options": [{"label": "Build one with me", "action": "setup.build_resume"}]},
    # Both are needed before anything can be searched: never "(if you like)" (journeys 21).
    {"id": "work", "kind": "text", "question": "What work do you want next, and where?",
     "help": "In your own words: a job title or two is plenty.",
     "fields": [{"key": "work", "kind": "text", "label": "The work you want next",
                 "required": True},
                {"key": "place", "kind": "place", "label": "Where you'd like to work",
                 "required": True}]},
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
# Then the last question of building one (history_interview.ask rest=True): where they
# studied, certificates, languages. It was marked done with the jobs and never asked, so a
# resume built with Claude had no education and the language gate knew only English (X-40).
HISTORY_REST = {"id": "history_rest", "kind": "text",
                "fields": [{"key": "text", "kind": "text", "label": "In your words"}]}
# What ends the jobs when it is typed rather than chosen: it was saved as a job (X-40).
ENOUGH = re.compile(r"^\s*(?:that'?s (?:all|it)|that is (?:all|it)|thats (?:all|it)|done|"
                    r"no more|nothing (?:more|else)|none)\s*[.!]*\s*$", re.I)
# A setup whose answers are all in, and no chat finishing it: the page shows it stopped.
SETUP_STOPPED = ("Your setup stopped part-way, with every answer in. Carry on, and Claude "
                 "finishes it from your answers.")


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


COUNTRY_WORDS = "the country you work in"
# The names a sentence gives a country with "the" before it.
_THE = {"GB": "the UK", "US": "the US", "NL": "the Netherlands", "AE": "the UAE",
        "PH": "the Philippines", "CZ": "the Czech Republic"}


def country_name(code: str) -> str:
    """A country as a sentence says it ("Germany", "the UK"), from its two-letter code and
    the market tables (tools/markets/<cc>.json "name"); "" for anything that is not one."""
    code = str(code or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", code):
        return ""
    if code in _THE:
        return _THE[code]
    got = read_json(os.path.join(ROOT, "tools", "markets", code.lower() + ".json"), {})
    name = str(got.get("name") or "") if isinstance(got, dict) else ""
    return {"CA": "Canada", "AU": "Australia", "IE": "Ireland", "NZ": "New Zealand"}.get(
        code, name)


def _country() -> str:
    """The country the right-to-work question names: a country's name, never a code or a
    city ("Can you work in DE", "Can you work in Recife", "in ON" for "Toronto, ON": X-82)."""
    a = answers().get("work") or {}
    place = str(a.get("place") or "")
    if set_up():
        try:
            c = person.country()
        except Exception:  # noqa: BLE001
            c = ""
        if country_name(c):
            return country_name(c)
    last = place.split(",")[-1].strip() if "," in place else ""
    # "Leeds, UK", "Lyon, France": the last part, when it names a country.
    alias = {"UK": "GB", "USA": "US", "U.S.": "US", "UAE": "AE", "ENGLAND": "GB",
             "SCOTLAND": "GB", "WALES": "GB", "BRITAIN": "GB", "UNITED KINGDOM": "GB",
             "UNITED STATES": "US"}
    if last.upper() in alias:
        return country_name(alias[last.upper()])
    folder = os.path.join(ROOT, "tools", "markets")
    for f in sorted(os.listdir(folder)) if last and os.path.isdir(folder) else []:
        if f.endswith(".json") and len(f) == 7:
            name = country_name(f[:2])
            raw = str(read_json(os.path.join(folder, f), {}).get("name") or "")
            if name and last.lower() in (raw.lower(), name.lower(),
                                         re.sub(r"^the ", "", name.lower())):
                return name
    return COUNTRY_WORDS


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


def _answers_quiet(a: dict, hours: float, now: dt.datetime | None = None) -> bool:
    """Whether the newest answer is older than `hours` (no answer with a time: not quiet)."""
    got = []
    for v in a.values():
        try:
            got.append(dt.datetime.fromisoformat(str(v.get("at") or "").replace("Z", "+00:00")))
        except (AttributeError, ValueError):
            continue
    got = [g if g.tzinfo else g.replace(tzinfo=dt.timezone.utc) for g in got]
    if not got:
        return False
    now = now or dt.datetime.now(dt.timezone.utc)
    now = now if now.tzinfo else now.replace(tzinfo=dt.timezone.utc)
    return (now - max(got)).total_seconds() > hours * 3600


def _history_rest_question(a: dict) -> str:
    try:
        import history_interview
        return history_interview.ask("computer", rest=True)
    except Exception:  # noqa: BLE001
        return ("Last one: where you studied (subject and years), any certificates, the "
                "languages you speak, and anything else you're good at?")


def setup_section(today: dt.date, targets: dict, now: dt.datetime | None = None) -> dict:
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
        order.insert(2, dict(HISTORY_REST, question=_history_rest_question(a)))
    for n, spec in enumerate(order, 1):
        sid = spec["id"]
        known, source = _known(sid)
        mine = a.get(sid) if isinstance(a.get(sid), dict) else {}
        if sid == "history":
            is_done = bool(mine.get("done"))
        elif sid == "history_rest":
            is_done = bool(mine)
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
                "question": spec["question"].replace("{country}", _country())
                if sid not in ("history", "history_rest") else spec["question"],
                "help": spec.get("help", ""), "fields": fields,
                "options": [dict(o) for o in spec.get("options", [])],
                "known_from": source if (known and not mine) else ("your answer" if mine else ""),
                "status": status, "waiting": waiting,
                "skippable": sid in ("pay", "avoid", "right_to_work", "history_rest"),
                "rev": app_model.rev_of(sid, mine, known)}
        steps.append(item)
        targets[item["id"]] = {"kind": "setup_step", "step": sid, "rev": item["rev"]}
    total = len(steps)
    st = _setup_state()
    state, say = st["state"], st["say"]
    # Every answer in: a chat is finishing setup (the research and the first round), or none
    # is. The page showed a finished checklist under "6 short questions" either way, with
    # nothing to tap (X-29). "searching" while a chat is on it, whose freshness the page
    # judges by its own clock (stalled_hours), and "stopped" once nothing is.
    import place
    if total and done == total and state in ("self", "going", "partial", "stopped"):
        # "partial": no chat has marked setup as its own; it is on while the last answer is
        # fresh, and stopped once STALLED_HOURS pass with nothing (a chat that runs `view`
        # for something else must not show it searching for ever).
        quiet = state == "partial" and _answers_quiet(a, place.STALLED_HOURS, now)
        state, say = (("searching", "") if state in ("self", "going") or
                      (state == "partial" and not quiet) else ("stopped", SETUP_STOPPED))
    elif state == "stopped":
        say = SETUP_STOPPED.replace(", with every answer in", "")
    targets["setup"] = {"kind": "setup", "rev": app_model.rev_of("setup", state, done)}
    return {"state": state, "say": say, "id": "setup", "rev": targets["setup"]["rev"],
            "stalled_hours": place.STALLED_HOURS,
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
    # A file holding only "outside" is the told records a copy wrote there before they had a
    # file of their own (SAID): no answer, so an old copy that wrote one stays set up.
    return not set(_read_json(os.path.join(profile_dir(), ANSWERS), {})) - {"outside"}


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
    # A cloud chat outside Auto waits for the person to allow each step the app's settings
    # do not pre-approve, in a chat they are not reading (the stranger audit, X-7).
    "auto": ("cloud-auto", "Claude then carries on while you're away, instead of waiting "
                           "for you to allow a step"),
    # Every new cloud chat installs the PDF tools before its first draft without it, and the
    # line was offered only while job sites were blocked (X-59).
    "setup-script": ("cloud-setup-script", "Each new chat then starts with the PDF tools in "
                                           "place, instead of installing them before a draft"),
    # The line offered before 3 November stopped every new chat from starting when one
    # install failed (X-60): a copy whose chats start with the tools gets the new line once.
    "setup-script-line": ("cloud-setup-script", "The line from before 3 November stops every "
                                                "new chat from starting if one install fails. "
                                                "This one never does"),
}
# 4.0 recommends no chat on the computer (UX_DECISIONS, "Chats"): there is no card for one.
# The things said once, outside the page's own answers: profile/said_once.json holds the day
# of each (a card's Done, or `app.py told <key>` from a chat with no page). They were kept in
# setup_answers.json under "outside" before 4 November, which made a finished copy read as
# setup unfinished after its first one: those are still read, never written there again.
SAID = "said_once.json"
TOLD = tuple(OUTSIDE) + tuple("report-" + s for s in ("page", "setup", "waiting"))


def said_once() -> dict:
    """{key: the day}: every thing said once, the old answers file's "outside" under it."""
    a = answers()
    old = a.get("outside") if isinstance(a, dict) else None
    got = _read_json(os.path.join(profile_dir(), SAID), {})
    return {**(old if isinstance(old, dict) else {}), **(got if isinstance(got, dict) else {})}


DOORBELLS = "doorbells-cleared"


def doorbells_pending() -> bool:
    """A page is published and no chat has yet cleared the rings it piled up (the day is kept
    with the things said once, so two chats merge it by the later day)."""
    return bool(page_record().get("url")) and not said_once().get(DOORBELLS)


def doorbells_due(today) -> bool:
    """The page's rings have not been cleared today. Every tap that wakes Claude leaves a
    comment, and one resolved by no wake (a ring during a busy pass, a subagent's wake, a
    quick answer) stayed unread in the Claude app: cleared once ever, they had piled up to 18
    (the maintainer, 2026-11-05: "still says 18 unread up top"). The daily tidy clears them."""
    day = today.isoformat() if hasattr(today, "isoformat") else str(today or "")
    return bool(page_record().get("url")) and str(said_once().get(DOORBELLS) or "") < day


def told(key: str) -> str:
    """The day the person was told, or did, `key` (an OUTSIDE card or a report), or ""."""
    return str(said_once().get(key) or "")


def save_said(key: str, day: str) -> str:
    """Keep `day` for `key` in profile/said_once.json (merge_state: the later day stands)."""
    path = os.path.join(profile_dir(), SAID)
    if person.in_example(path):
        return path                   # the app's example person records nothing
    got = _read_json(path, {})
    got = dict(got if isinstance(got, dict) else {}, **{key: day})
    return _write_json(path, got)


def record_told(key: str, today: dt.date | None = None) -> str:
    if key not in TOLD:
        raise ValueError(f"not something said once: {key}")
    return save_said(key, (today or dt.date.today()).isoformat())


def _cloud() -> bool:
    return os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true"


def _tex() -> bool:
    return bool(shutil.which("lualatex") or shutil.which("xelatex"))


def _setup_env_ran() -> bool:
    """tools/setup_env.sh installed the tools in this computer itself (its mark in the git
    folder), so tools present without it came from the line in the cloud settings."""
    d = _git_dir()
    return bool(d) and os.path.isfile(os.path.join(d, "ljs-setup-env"))


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
    if key == "linkedin":
        # The page opens LinkedIn in the Claude app's own browser itself (host:claude_browser,
        # preview_start); the registry's steps stay under More for when it cannot.
        item["title"] = "Sign in to LinkedIn in Claude's browser, once"
        item["body"] = "Then Claude can read people's profiles before you write to them."
        item["browser"] = {"label": "Open LinkedIn", "url": "https://www.linkedin.com/login"}
    if key == "copy":
        # GitHub fills in its new-repository form from these (docs.github.com, "Creating a
        # repository from a URL query", read 2026-10-25): one tap opens it with the app as
        # the template and Private chosen. The steps are the way when it opens empty.
        item["open"] = {"label": "Make my private copy", "url": COPY_LINK}
    return item


def outside_items(targets: dict, kind: dict | None = None) -> list:
    """The cards for this copy now: its privacy and the job sites, each only while it is
    still to do. LinkedIn is the page's own reading card, never one of these: the card here
    showed for ever to anyone with a computer chat, keyed on a file the reads no longer
    write (2026-10-29)."""
    out = []
    owner, name = (kind or {}).get("owner", ""), (kind or {}).get("name", "")
    k = (kind or {}).get("kind", "")
    if k in ("app", "fork"):
        # A fork can never be made private (GitHub, About forks): a new private copy instead.
        out.append(outside_item("copy"))
    elif k == "public":
        out.append(outside_item("private", owner, name))
    blocked = job_sites().get("blocked") or []
    if blocked:
        # Found by code (env_check reaching the boards), never asked; the next check ticks
        # it off by itself once the setting is changed.
        import claude_surfaces
        item = outside_item("job-sites")
        # "Claude", not "This chat": the person reads it on their page, and every chat of theirs
        # shares the setting (the stranger audit, X-49).
        item["body"] = (f"Claude can't reach job sites yet ({', '.join(blocked[:3])}). "
                        "I won't search before then: it would only find old jobs.")
        more = claude_surfaces.steps("cloud-setup-script", page=True)
        item["more"] = {"title": more[0].rstrip(":"), "steps": [ln for ln in more[1:] if ln],
                        "copy": setup_script_line(),
                        "checked": claude_surfaces.entry("cloud-setup-script").get("verified_on", "")}
        out.append(item)
    if _cloud() and k not in ("app", "public", "fork", "none"):
        if not told("auto"):
            out.append(outside_item("auto"))
        # The line in its own card, whenever a cloud chat starts without the PDF tools: it
        # was offered only beside blocked job sites, so it went with them (X-59). A chat that
        # starts with the tools it never installed has the line in its cloud settings: the old one is
        # replaced once (X-60).
        script = ("setup-script" if not _tex() and not blocked else
                  "setup-script-line" if _tex() and not _setup_env_ran() else "")
        if script and not told(script) and not (script == "setup-script-line"
                                                and told("setup-script")):
            item = outside_item(script)
            item["more"] = {"title": "The line to paste", "steps": [], "copy": setup_script_line(),
                            "checked": item["checked"]}
            out.append(item)
    if k not in ("app", "public", "fork", "none"):
        out += report_items()
    for item in out:
        targets[item["id"]] = {"kind": "outside", "key": item["about"]["step"], "rev": item["rev"]}
    return out


def report_items(today: dt.date | None = None) -> list:
    """A card for each state the copy has been stuck in for a day or more, said once: what
    it is, and a link to tell the app's makers that carries nothing of the person's
    (tools/report.py). Nothing is sent: the person opens it, or bins the card."""
    import app_model
    import report
    try:
        st = {"repo": repo_kind_offline(), "setup": _setup_state(), "page": page_record(),
              "answers": answers(), "set_up": set_up()}
        got = report.stuck(today, st)
    except Exception:  # noqa: BLE001  nothing to read: nothing stuck
        return []
    out = []
    for s in got:
        key = "report-" + s["state"]
        if told(key):
            continue
        since = dt.date.fromisoformat(s["since"])
        out.append({"id": f"q-setup-{key}", "kind": "setup",
                    "title": s["say"].rstrip("."),
                    "body": (f"Since {since.day} {since.strftime('%B')}. "
                             "Claude is told each time it starts. If it stays like this, you "
                             "can tell the app's makers: the link opens a public page that "
                             "carries nothing of yours, and nothing is sent unless you send it."),
                    "steps": [], "link": "", "checked": "",
                    "open": {"label": "Tell the app's makers", "url": s["link"]},
                    "options": [{"label": "Done", "action": "setup.done"}],
                    "about": {"step": key}, "rev": app_model.rev_of(key, s["since"])})
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
            # --grep matches any line of the message: the app's own commits that came in with
            # every sync say "Profile upgrade:" in their bodies, under subjects with no colon,
            # and reading their id crashed the whole section, on every copy (X-15).
            if not subject.startswith("Profile upgrade:"):
                continue
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
        # What this copy's channel takes, never the app's master as such: between releases
        # master is ahead of the newest one, and a copy on releases was told an update waited
        # that "update" could not take, and its queued work held behind it (X-28).
        target = sync_app.channel_target()
        text = _app_changelog(target) if target else ""
        if text:
            secs = release.sections(text)
            newest = secs[0]["version"] if secs else version
        sha = sync_app.waiting(target) if text else ""
        if sha:
            line = sync_app.waiting_line(None, False, target)
            migration = is_migration(target)
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
    except Exception as e:  # noqa: BLE001  said, never silent: it hid X-15 on every copy
        print(f"app: what the updates did could not be read ({type(e).__name__}: {e})",
              file=sys.stderr)
        pending = []
    # The whole history, for anyone who wants more than the last few (the maintainer,
    # 2026-10-31): the app's own changelog, at the address the sync takes updates from.
    try:
        import sync_app
        base = sync_app.app_url().rstrip("/")
        changelog = base + "/blob/master/CHANGELOG.md" if base.startswith("https://github.com/") else ""
    except Exception:  # noqa: BLE001  no address: no link
        changelog = ""
    # Changes merged since that release (CHANGELOG's [Unreleased] has a line): a copy that
    # follows master runs them, so "version 4.5.1" alone would undersell it.
    try:
        import release
        with open(release.CHANGELOG, encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r"^## \[Unreleased\][^\n]*\n(.*?)(?=^## \[)", text, re.M | re.S)
        since = bool(m and re.search(r"^- ", m.group(1), re.M))
    except Exception:  # noqa: BLE001  no changelog: nothing said
        since = False
    return {"version": version, "newest": newest, "mode": mode, "waiting": waiting,
            "changed": changed, "done": done, "pending": pending, "changelog": changelog,
            "since": since}


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


def _first_name() -> str:
    """The name the page is called by ("Morgan's job search"): empty until setup knows it."""
    try:
        import person
        name = str(person.get("identity.name", "") or "")
        return str(person.get("identity.first", "") or "") or (name.split() or [""])[0]
    except Exception:  # noqa: BLE001  no profile yet
        return ""


def _page_current() -> bool:
    if not page_record().get("url"):
        return False
    if not set_up():
        return True
    # Published before the person's name was known ("Your job search"): published once more,
    # so the page and its card in Claude carry their name (the maintainer, 2026-10-29).
    # A page published under another name (the person changed theirs) is published again;
    # one from before the name was kept takes it at the next change to the page's code.
    named = page_record().get("title_name")
    if _first_name() and named is not None and named != _first_name():
        return False
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
    import app_listen
    if url:
        lines += [f"{n}. The person's page is {url}, and an update changed it: republish it now, "
                  "never asking first. Build it again, in parts: python3 tools/app.py page "
                  f"--out-dir <your scratchpad>/page --url {url}",
                  f"{n + 1}. Do exactly the steps the build printed: read the page, list its "
                  "files and give that list to the build, then publish only the small files it "
                  "then names, each read whole first; the page keeps the rest. If the publish is "
                  "refused, read the page again and publish once more. If the read says the page "
                  f"is not there or not this person's, build a new one ({app_listen.REBUILD}) "
                  "and publish that instead. Only if a publish is refused twice, tell the person "
                  f"\"{app_listen.say(app_listen.SAY_NOT_UPDATED, url)}\" and go on. Then "
                  f"python3 tools/app.py published <its url> --parts <your scratchpad>/page, and "
                  f"tell the person only: \"{app_listen.say(app_listen.SAY_UPDATED, url)}\" (or "
                  "the one line it prints, for a page with a new address)"]
    else:
        lines += [f"{n}. Build the person's page, in parts: python3 tools/app.py page --out-dir "
                  "<your scratchpad>/page",
                  f"{n + 1}. Publish it (Artifact, action publish, icon briefcase): exactly the "
                  "publishes the build printed, each file they name read whole first (every one "
                  "is small). Then keep its address: python3 tools/app.py published <the url the "
                  "publish gave> --parts <your scratchpad>/page, and do what it prints (it says "
                  f"the one line that tells the person what their page is). {NO_PUBLISH}"]
    lines.append(f"{n + 2}. Publishing makes this chat watch the page. If the publish result "
                 "says this chat is not watching it, watch it (ArtifactComments, watch).")
    return lines


# How start words the day's update check, and `app.py wake` the same check it ran itself.
SYNC_DO = "the day's update check; do what it prints, then carry on"
SYNC_PAGE = ". What it says about the person's page is done at once, and is never a question"


SAY_ON_PAGE = ("Your setup is on your page: <its url>. Answer there, one question at a time; "
               "I'll do the rest.")
SAY_FINISHING = ("Your answers are all in, so I'm finishing your setup now. Your first jobs "
                 "will be on your page: <its url>.")
SAY_CARRYING_ON = ("Your setup stopped part-way, so I'm carrying it on now from your answers. "
                   "Your first jobs will be on your page: <its url>.")
# Read by the day's first chat (start, after the update check).
ASK_IN_CHAT = ("If the update check listed questions under \"These need you\" (facts to confirm, "
               "a question an improvement needs), ask at most three, in plain words, at the end "
               "of your reply, as .claude/commands/upgrade.md says: the page asks them too, and "
               "an answer in either place counts.")
# The same for the page's helper, whose last reply is one line and which nobody reads: its
# start said to ask up to three questions and give the changes at the end of the reply, then
# that the reply was only "ready" (the maintainer's live run, 2026-11-05). On the page they
# go, as CLAUDE.md says of every question for the person (app_listen.shape swaps them in).
ASK_ON_PAGE = ("If the update check listed questions under \"These need you\" (facts to "
               "confirm, a question an improvement needs), ask none of them in this chat: the "
               "page asks each as a To do card, and an answer there counts.")
SHOWN_ON_PAGE = "its progress goes on the page"
SHOWN_IN_REPLY = "at the end of your reply give one plain line per change it made, never a command"


def _answered(st: dict) -> int:
    """The six questions answered on the page or already held in the profile, as the page
    counts them (setup_section)."""
    got = 0
    for sid in STEP_IDS:
        known, source = _known(sid)
        if (st["answers"].get(sid) or {}) or (known and source == "your profile"
                                              and _complete(sid, known)):
            got += 1
    return got


def _said_once(st: dict, no_page: bool, leave: tuple = ()) -> str:
    """The one thing this chat tells the person once and never again, or "": a state stuck
    for a day or more with the link to tell the app's makers (X-20), choosing Auto in a cloud
    chat (X-7), the line that puts the PDF tools in every new chat (X-59). With a page, its
    To do carries each as a card, so the chat says only what the page cannot: a page never
    made. One at a time, the most pressing first. `leave`: the stuck states this start says
    and mends otherwise (a page it publishes, work waiting that it lands), never said twice."""
    try:
        import report
        stuck = [s for s in report.stuck(st=st)
                 if s["state"] not in leave and not told("report-" + s["state"])]
    except Exception:  # noqa: BLE001  nothing to read: nothing stuck
        stuck = []
    page = bool(st["page"].get("url"))
    for s in stuck:
        if not page or s["state"] == "page":
            return (f"This has been stuck since {s['since']}: tell the person once, in these "
                    f"words: \"{s['say']} I'm on it. If it keeps happening, you can tell the "
                    f"app's makers here; it carries nothing of yours, and nothing is sent unless "
                    f"you send it: {s['link']}\" Then python3 tools/app.py told "
                    f"report-{s['state']}, and carry on with what fixes it.")
    if page or not _cloud():
        return ""
    import claude_surfaces
    if not told("auto"):
        lines = " ".join(claude_surfaces.steps("cloud-auto"))
        return (f"Tell the person once, in these words: \"{lines}\" Then python3 tools/app.py "
                "told auto.")
    if not _tex() and not told("setup-script"):
        lines = " ".join(claude_surfaces.steps("cloud-setup-script"))
        return (f"Tell the person once, in these words: \"{lines} The line: "
                f"{setup_script_line()}\" Then python3 tools/app.py told setup-script.")
    return ""


# A fork of a public project is public, and GitHub never lets one be made private.
FORK_SAY = ("Your copy is a fork, and GitHub never lets a fork be made private. Make a new "
            "private copy instead (your fork holds nothing of yours, so it can simply be left):")


NO_PUBLISH = ("If this chat cannot publish (no Artifact tool, or a publish refused again after "
              "one more try), run python3 tools/app.py published none --why \"<why, in a few "
              "words>\": that is this chat only, and every other chat still publishes. Then carry "
              "on in this chat (during setup, ask setup's questions here, as "
              ".claude/commands/setup.md says) and say nothing about a page.")


def adopt_page_elsewhere() -> bool:
    """A page another chat published whose work has not reached this checkout (on master
    or on a chat's branch not yet landed): its record taken whole, so this chat makes no
    second page and the two records merge as one. The one published last wins, as a merge
    keeps it (tools/merge_state.py, JSON_FILES "newest"): every publish stamps it anew, and a
    branch left days ago holds an older, abandoned page. False when there is none, or it
    cannot be told."""
    if os.path.normcase(profile_dir()) != os.path.normcase(os.path.join(ROOT, "profile")):
        return False          # a profile kept elsewhere: this copy's branches hold not it
    try:
        import place
        place._git("fetch", "-q", "origin", timeout=60)
        refs = ["origin/master"] + [
            b.strip() for b in place._git("branch", "-r", "--no-merged",
                                          "origin/master").splitlines()
            if b.strip() and "->" not in b]
        found = []
        for ref in refs:
            text = place._at(ref, f"profile/{PAGE}")
            if not text or "<<<<<<<" in text:
                continue
            try:
                rec = json.loads(text)
            except ValueError:
                continue
            if isinstance(rec, dict) and re.match(r"^https://claude\.ai/\S+$", str(rec.get("url") or "")):
                found.append((str(rec.get("published_at") or ""), rec))
        if not found:
            return False
        _write_json(os.path.join(profile_dir(), PAGE), sorted(found, key=lambda x: x[0])[-1][1])
        return True
    except Exception:  # noqa: BLE001  nothing found: this chat publishes as before
        return False


PAGE_HISTORY = 60


def newer_page_kept() -> str:
    """Where the page's record names another page than one this copy's history recorded
    later (a merge put an older page back: a report from a person's copy, 2026-11-04, whose
    next start moved everything to an abandoned page), that newer record is kept again,
    whole, by the merge's own rule (tools/merge_state.py, JSON_FILES "newest"), and the line
    saying so is returned; "" otherwise, or where git cannot say."""
    if os.path.normcase(profile_dir()) != os.path.normcase(os.path.join(ROOT, "profile")):
        return ""
    try:
        import merge_state
        rule = merge_state.json_rules("profile/" + PAGE)["newest"]
        now = page_record()
        if not now.get(rule["key"]) or page_conflicted():
            return ""
        code, out = _git("log", f"-{PAGE_HISTORY}", "--format=%x01%H", "-p", "--unified=0",
                         "--", f"profile/{PAGE}")
        if code != 0:
            return ""
        best, at, commit = str(now.get(rule["stamp"]) or ""), "", ""
        mark = re.compile(r'^\+\s*"%s":\s*"([^"]+)"' % re.escape(rule["stamp"]))
        for line in out.splitlines():
            if line.startswith("\x01"):
                commit = line[1:].strip()
                continue
            m = mark.match(line)
            if m and merge_state._later_of(m.group(1), best) == "a":
                best, at = m.group(1), commit
        if not at:
            return ""
        code, text = _git("show", f"{at}:profile/{PAGE}")
        then = json.loads(text) if code == 0 else {}
        if not isinstance(then, dict) or not then.get(rule["key"]) or \
                then.get(rule["key"]) == now.get(rule["key"]):
            return ""
        was = now.get(rule["key"])
        for f in rule["with"]:
            if f in then:
                now[f] = then[f]
            else:
                now.pop(f, None)
        _write_json(os.path.join(profile_dir(), PAGE), now)
        return (f"The page's record had gone back to an older page ({was}): a merge put it "
                f"over the one published later, {now[rule['key']]}, which is kept again and is "
                "the page from here on. Say nothing about it to the person.")
    except Exception:  # noqa: BLE001  the record stays as it is; the start goes on
        return ""


def _resume_to_save(st: dict) -> str:
    """The step that saves a resume the person added on the page, or "" when none waits."""
    resume = (st["answers"].get("resume") or {}) if isinstance(st["answers"], dict) else {}
    if not (resume.get("asset") and not resume.get("file")):
        return ""
    url = st["page"].get("url") or "<the page's url>"
    return (f"The person added their resume on the page. Save it: Artifact, action read, url "
            f"{url}, path {resume['asset']}, out_dir documents/cv. Then python3 tools/app.py "
            f"resume-saved <the file it saved> --asset {resume['asset']}, and delete it from "
            f"the page (Artifact, action delete, url {url}, path {resume['asset']}): the page "
            "is no place to keep it.")


def _setup_open(st: dict) -> bool:
    return not st["set_up"] or st["setup"]["state"] in ("none", "partial", "self", "stopped") \
        or not _finished()


def carry_on() -> list[str]:
    """What a chat the page woke does about setup once it has applied the person's setup
    answers: save a resume they added, and carry setup on from the answers. Only `start`
    said it, and a wake from the page never runs start, so answers given on the page sat
    with "nothing printed: end the turn" (journeys audit 13)."""
    try:
        if repo_kind_offline()["kind"] in ("app", "none"):
            return []
        st = {"setup": _setup_state(), "page": page_record(), "answers": answers(),
              "set_up": set_up()}
    except Exception:  # noqa: BLE001  no copy to read: nothing to carry on
        return []
    if st["setup"].get("state") == "going":
        return []            # another chat is setting them up: never two at once (X-65)
    out = []
    saving = _resume_to_save(st)
    if saving:
        out.append("setup: " + saving)
    if _setup_open(st):
        done = sum(1 for s in STEP_IDS if (st["answers"].get(s) or {}))
        out.append(f"setup: carries on from where it is ({done} of {len(STEP_IDS)} answered): "
                   "follow .claude/commands/setup.md, which reads every answer from "
                   "profile/setup_answers.json and never asks one again. The page asks the "
                   "rest, one at a time; this chat asks nothing.")
    return out


def _week_ago() -> str:
    """A week before today, by the person's clock, as the page's stamps are written: the
    taps the start reads (a tap and its receipt are both newer than the tap)."""
    try:
        day = person.today()
    except Exception:  # noqa: BLE001  no profile yet: the computer's day
        day = dt.date.today()
    return (day - dt.timedelta(days=7)).isoformat() + "T00:00:00Z"


def start(on: str = "", tools: str = "", page_url: str = "", runner=None, work: str = "",
          data_current: bool = False) -> tuple[int, list[str]]:
    """(exit code, the lines a chat follows): what this chat does next, whatever the copy's
    state. Exit 0 with steps to follow; 1 when nothing may be written here.

    `work`: a chat started for one big job (`app.py next`). It takes no update check: the
    chat that answers the page took the day's already, and a job must not take an update
    part way through. Its own steps bring the page up to date at the end, after it lands
    (app.py job_steps), so start says nothing about it (the drafting child, 2026-11-03: start
    said a job chat never did, and its prompt then said to). `data_current`: the page's
    `meta/current` already carries the model this copy makes now, so its data is not
    written again."""
    st = state(runner)
    kind = st["repo"]["kind"]
    sync = (["python3 tools/sync_app.py --pull",
             f"python3 tools/sync_app.py --on \"{on or '<this chat model>'}\" --tools "
             f"\"{tools or '<the browser tools this chat has>'}\""]
            if st["stale"] and not work else [])
    if page_url and not st["page"].get("url") and kind == "private":
        try:
            record_page(page_url)
            st["page"] = page_record()
        except ValueError:
            pass
    out: list[str] = []
    if kind == "none":
        out += ["app start: this folder is not a copy of the job search on GitHub.",
                "Claude: nothing about the person may be written here."]
        if sync and _git("remote", "get-url", "origin")[0] == 0 and \
                os.path.isfile(os.path.join(ROOT, "tools", "sync_app.py")):
            # A copy whose address this version cannot read still takes the update that
            # reads it: a cloud chat's proxy address stopped every start here, before the
            # update check, for good (the stranger audit, X-54).
            out.append("First, in case this is their copy reached by an address this version "
                       "cannot read, run the day's update check, then python3 tools/app.py "
                       "start again:")
            out += [f"  {cmd}" for cmd in sync]
            out.append("If start says the same again, tell them, in these words:")
        else:
            out.append("Tell them, in these words:")
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
    if kind in ("public", "fork"):
        owner, name = st["repo"]["owner"], st["repo"]["name"]
        # The day's update check comes first even here: it changes only the app's own files,
        # and without it a copy that stops here never hears corrected words (a fork was told
        # to make itself private, which GitHub refuses, on every start: the stranger audit,
        # 2026-11-03).
        out += ["app start: this copy is " + ("a fork, which is public" if kind == "fork" else
                                              "public") + ". Nothing about the person may be "
                "written here until it is private, and never change that yourself."]
        if sync:
            out += [f"Claude: first {sync[-1]}   ({SYNC_DO}; it changes only the app's own "
                    "files). If it took an update, run python3 tools/app.py start again: its "
                    "words may have changed."]
        out.append("Claude: tell them why in one line (everything about them, their work "
                   "history, pay and every contact, goes into this copy, which anyone can "
                   "read while it is public), then, in these words:")
        if kind == "fork":
            out.append("  " + FORK_SAY)
            out += ["  " + ln for ln in _steps("make-copy")]
            out.append("  Then open a chat on the new copy and say \"set me up\".")
            return 1, out
        out += ["  " + ln for ln in _steps("make-private", owner=owner, name=name)]
        out.append("  When they say it's done, run python3 tools/app.py start again.")
        return 1, out
    setup = st["setup"]["state"]
    note_start()
    n = 1
    steps: list[str] = []
    if kind == "unknown":
        steps.append(f"{n}. Check the copy is private before anything about the person is "
                     "written: gh api repos/<owner>/<name> --jq .private must say true. Where "
                     "it cannot be checked, ask them once to look: GitHub shows Private or "
                     "Public beside the copy's name. Public: stop, and run this again once it "
                     "is private.")
        n += 1
    for i, cmd in enumerate(sync):
        page = (SYNC_PAGE if i == len(sync) - 1 and st["page"].get("url") else "")
        steps.append(f"{n}. {cmd}   ({SYNC_DO}{page})")
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
    if not st["page"].get("url") and not no_page and kind == "private" and not page_conflicted():
        # Another chat published the page and its work has not reached this checkout: that
        # page is taken, never a second one made beside it (X-57).
        if adopt_page_elsewhere():
            st["page"], st["page_current"] = page_record(), _page_current()
    elif st["page"].get("url") and kind == "private":
        back = newer_page_kept()
        if back:
            st["page"], st["page_current"] = page_record(), _page_current()
            steps.append(f"{n}. {back}")
            n += 1
    # A page already published waits for the day's check: the update it takes can change the
    # page, and the check itself says how to bring it up to date (app_listen.after_update),
    # so the page is published once, from the new code, never once before and once after.
    later = bool(sync) and bool(st["page"].get("url"))
    publishing = (not no_page and not later and not page_conflicted()
                  and (not st["page_current"] or not st["page"].get("url")))
    if publishing:
        steps += _publish_lines(st, n)
        n += 3
    elif page_conflicted():
        steps.append(f"{n}. The page's record (profile/app.json) holds a merge left unsettled: "
                     "settle it first (keep the address published last, with its own "
                     "published_at), and publish nothing until it reads clean. Say nothing about "
                     "it to the person.")
        n += 1
    if os.environ.get("CLAUDE_CODE_REMOTE", "").lower() == "true" and \
            job_sites().get("checked") != dt.date.today().isoformat():
        try:
            check_job_sites()
        except Exception:  # noqa: BLE001  the day's sync checks it too
            pass
    saving = _resume_to_save(st)
    if saving:
        steps.append(f"{n}. {saving}")
        n += 1
    # A page this start publishes is never also said to be stuck unmade, with the link to the
    # app's makers (the re-audit of 4 November).
    leave = ("page",) if publishing else ()
    if _setup_open(st):
        once = _said_once(st, no_page, leave)
        done = _answered(st)
        all_in = done == len(STEP_IDS)
        if no_page:
            steps.append(f"{n}. Setup carries on from where it is ({done} of {len(STEP_IDS)} "
                         "answered), in this chat: this chat has no pages. Follow "
                         ".claude/commands/setup.md; it reads every answer already in "
                         "profile/setup_answers.json and never asks one again.")
            n += 1
        else:
            # Every answer in, the setup stopped or not: there is nothing left to answer, so
            # the chat carries it on now and says so (X-83: "Answer there, one question at a
            # time" was said with all six answered, and the stopped line never at all).
            steps.append(f"{n}. Setup carries on from where it is ({done} of {len(STEP_IDS)} "
                         "answered): follow .claude/commands/setup.md, which reads every "
                         "answer from profile/setup_answers.json and never asks one again. "
                         + ("Every answer is in: carry setup on now, to its end."
                            if all_in else "The page asks the rest, one at a time; this chat "
                            "asks nothing."))
            n += 1
            say = (SAY_FINISHING if all_in and setup != "stopped" else SAY_CARRYING_ON
                   if all_in else SAY_ON_PAGE)
            steps.append(f"{n}. Tell the person one line, and nothing more: \"{say}\""
                         + ("" if all_in else " If they answer in this chat instead, take it: "
                            "python3 tools/app.py answer <step> --text \"<their words>\" for "
                            "each step they answered, then carry on as setup.md says."))
            n += 1
        if once:
            steps.append(f"{n}. {once}")
        head = "app start: " + ("setting up" if setup in ("none", "partial", "") else
                                f"setup {setup}")
        return 0, [head, "Claude, do this, in order:"] + steps
    waits = {} if work else _stranded()
    if waits:
        # Every landing brings in what waits (tools/land.py); work still off master a day on
        # is kept out by something, and nothing ever said so (the stranger audit, X-30).
        days = max(waits.values())
        # Told once a day, not on every start (said_once.json's "unsaved"), and never again
        # beside the stuck line below for the same work (the re-audit of 4 November).
        today = person.today().isoformat()
        tell = told(UNSAVED_KEY) != today
        if tell:
            try:
                save_said(UNSAVED_KEY, today)
            except OSError:
                pass
        steps.append(f"{n}. Work of the person's has waited off their saved copy for {days} "
                     f"day{'s' if days != 1 else ''} ({', '.join(waits)}). Land this chat's "
                     "work now (python3 tools/land.py, in the background): it brings that in. "
                     "Not green: fix what its check names (their own tests after an update: "
                     "RUNBOOK.md, \"Your own tests fail after an update\") and land again."
                     + (f" Tell the person once, in these words: \"{UNSAVED_SAY}\"" if tell
                        else " The person was told today: say nothing of it."))
        n += 1
        leave += ("waiting",)
    once = _said_once(st, no_page, leave)
    url = st["page"].get("url") or ""
    if url and not later:
        import app_listen
        if not app_listen.introduced():
            # A page published before without a word to the person (a copy from before the
            # page, or a first publish that said nothing): told once, here (X-25).
            steps.append(f"{n}. {app_listen.intro_line(url)}")
            n += 1
            app_listen.mark_introduced()
    # The improvements still unstarted, named on every start while they wait, not only by the
    # day's first check: a second chat that day, or one whose turn went to the request, never
    # heard of them again (the stranger audit, X-32). Said by page or no page.
    ups = [] if work else _unstarted()
    shown = SHOWN_ON_PAGE if st["page"].get("url") and not no_page else SHOWN_IN_REPLY
    if ups:
        since = min(d for _i, d in ups)
        steps.append(f"{n}. {len(ups)} improvement{'s' if len(ups) != 1 else ''} to their "
                     f"search {'have' if len(ups) != 1 else 'has'} waited since {since}: start "
                     "them now, never asking first: one background agent (model sonnet) that "
                     f"follows .claude/commands/upgrade.md; {shown}.")
        n += 1
    elif sync:
        steps.append(f"{n}. If the update check listed improvements Claude applies itself, "
                     "start them in this turn, never asking first: one background agent (model "
                     f"sonnet) that follows .claude/commands/upgrade.md; {shown}.")
        n += 1
    if sync:
        # Questions only the person can answer sat on page cards a chat-only person never
        # opened, and the chat was told to say nothing (X-55): the day's first chat asks.
        steps.append(f"{n}. {ASK_IN_CHAT}")
        n += 1
    if once:
        steps.append(f"{n}. {once}")
        n += 1
    if st["page"].get("url") and not work and not (data_current and not sync):
        # The marks the person made on the page (applied, sent, set aside) ring nobody: the
        # next chat to work on the search keeps them first, this one included, so the last
        # week's taps and receipts are read with the screens (app_actions.MARKS).
        week = _week_ago()
        steps.append(f"{n}. " + ("Unless the update check above just did it, b" if sync else "B") +
                     "ring the page's data up to date: read the page's screen, meta, addr and "
                     "work collections into a fresh folder in your scratchpad (ArtifactData "
                     f"query, url {st['page'].get('url')}, one for each, out_dir that folder, "
                     "limit 1000; the page's view is stored as screen, and view is an old name), "
                     "and into the same folder actions where [[\"at\", \">=\", \"" + week +
                     "\"]] and receipts where [[\"applied_at\", \">=\", \"" + week + "\"]], "
                     "then python3 tools/app.py view <your scratchpad>/view --dump <that "
                     "folder> and send the batch it prints (where it first prints a claim for "
                     "the person's marks, send that, then run it once more). Then carry on with "
                     "what the person asked.")
    # "page to publish" only beside the steps that publish it: a chat that cannot publish was
    # told the page waited, with nothing to do about it (X-21).
    head = "app start: set up" + (", page to publish" if publishing else "")
    return 0, [head, "Claude, do this:"] + steps


def _unstarted() -> list[tuple[str, str]]:
    """The improvements the update check listed that nobody has started today
    (profile_upgrades.unstarted, for this chat): [] when none, or when it cannot be told."""
    try:
        import app_listen
        import profile_upgrades
        return profile_upgrades.unstarted(chat=app_listen.this_chat())
    except Exception:  # noqa: BLE001  the start goes on; the hook asks at the turn's end
        return []


UNSAVED_SAY = ("Some of your work from the last few days hadn't been saved yet. I'm saving it "
               "now.")
UNSAVED_KEY = "unsaved"     # its day in profile/said_once.json: said once a day


# Which version of the app this checkout's start last spoke for: an update that changes how a
# chat starts makes the steps it printed out of date, and copies at 4.0 to 4.2 went on with
# their old start's later steps after the update it took (the stranger audit, X-78).
START_HEAD = "ljs-start-head"
START_FILES = ("tools/app_setup.py", "tools/app_listen.py", "tools/app.py")


def _head() -> str:
    code, out = _git("rev-parse", "HEAD")
    return out.strip() if code == 0 else ""


def note_start() -> None:
    """start spoke for this version of the app."""
    head = _head()
    if head:
        try:
            with open(_local_file(START_HEAD), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(head + "\n")
        except OSError:
            pass


def start_changed_line() -> str:
    """After a sync: the line telling a chat its start's steps are out of date, when the app
    it took changed how a chat starts since start last spoke (or start never recorded it: a
    version from before this one). Said once a version."""
    head = _head()
    if not head:
        return ""
    try:
        with open(_local_file(START_HEAD), encoding="utf-8") as fh:
            was = fh.read().strip()
    except OSError:
        was = ""
    if was == head:
        return ""
    changed = True
    if was:
        code, out = _git("diff", "--name-only", was, head, "--", *START_FILES)
        changed = code != 0 or bool(out.strip())
    note_start()
    if not changed:
        return ""
    return ("Claude: this update changed how a chat starts. If python3 tools/app.py start printed "
            "steps earlier in this chat, they are out of date: run it again now and follow what "
            "it prints instead, never the steps from before.")


def _stranded() -> dict[str, int]:
    """{branch: days} for the person's work that has waited off master a day or more
    (land.stranded, fetched fresh); {} in the app itself, or when it cannot be told."""
    try:
        import land
        return {} if land._the_app(ROOT) else land.stranded(ROOT, fetch=True)
    except Exception:  # noqa: BLE001  the start goes on; the next one looks again
        return {}


def _local_file(name: str) -> str:
    """A record only this checkout needs, in its own git folder (never committed, never
    merged), or beside the state where there is no git folder (a test's)."""
    d = _git_dir()
    return os.path.join(d, name) if d else os.path.join(person.state(), "." + name)


# Which chats were started for one job (`app.py start --work <id>`): one record a chat, in this
# checkout's git folder. The app's hook knew a job chat only from the turn that ran its start,
# so once the person typed in it, it was given the day's update check and held at the turn's
# end like the chat that answers the page (the re-audit of 4 November). Kept JOB_CHAT_DAYS.
JOB_CHATS = "ljs-job-chats.json"
JOB_CHAT_DAYS = 14


def _chat_keys(session: str = "") -> set[str]:
    """Every name this chat goes by: its id (app_listen.this_chat), and Claude Code's own
    session id, which a hook is given as `session_id` (`session`) and a command reads from
    CLAUDE_CODE_SESSION_ID."""
    import app_listen
    keys = {app_listen.this_chat()}
    for s in (session, "" if session else os.environ.get("CLAUDE_CODE_SESSION_ID") or ""):
        s = str(s or "").strip()
        if s:
            keys |= {s, "local-" + s}
    return {k for k in keys if k}


def record_job_chat(work: str, today: dt.date | None = None) -> bool:
    """Remember that this chat was started for the work item `work`: False when no name for
    it is known (nothing to key it by)."""
    keys = _chat_keys()
    if not keys or not work:
        return False
    day = today or dt.date.today()
    since = (day - dt.timedelta(days=JOB_CHAT_DAYS)).isoformat()
    path = _local_file(JOB_CHATS)
    got = _read_json(path, {})
    got = {k: v for k, v in got.items() if isinstance(v, dict) and str(v.get("day")) >= since}
    for k in keys:
        got[k] = {"work": work, "day": day.isoformat()}
    _write_json(path, got)
    return True


def job_chat(session: str = "") -> str:
    """The work item this chat was started for (record_job_chat), or "". `session` is the
    hook's own `session_id`."""
    got = _read_json(_local_file(JOB_CHATS), {})
    for k in sorted(_chat_keys(session)):
        v = got.get(k)
        if isinstance(v, dict) and v.get("work"):
            return str(v["work"])
    return ""


# Which chats said they cannot publish (`app.py published none`): one record a chat, in this
# checkout's git folder. It was one date in profile/app.json, saved and landed, so one chat
# that could not publish once (a phone chat, a refused approval) hid the page from every chat
# of the copy for a month, the ones that could publish included (the stranger audit, X-21).
NO_PAGE = "ljs-no-page.json"


def _chat_key(chat: str = "") -> str:
    import app_listen
    return app_listen.this_chat(chat) or "this-folder"


def no_page_here(chat: str = "", today: dt.date | None = None) -> bool:
    """Did this chat say, within NO_PAGE_DAYS, that it cannot publish? Never true once the
    page has an address. A copy-wide `none` an older version wrote in profile/app.json is
    another chat's word, and is not this one's."""
    if page_record().get("url"):
        return False
    got = read_json(_local_file(NO_PAGE), {}).get(_chat_key(chat)) or {}
    try:
        day = dt.date.fromisoformat(str(got.get("day") or "")[:10])
    except ValueError:
        return False
    return ((today or dt.date.today()) - day).days < NO_PAGE_DAYS


def _no_page_recently(rec: dict, today: dt.date | None = None) -> bool:
    """start's question, for this chat only (no_page_here)."""
    return not rec.get("url") and no_page_here(today=today)


def page_conflicted() -> bool:
    """profile/app.json left with a merge's conflict markers: read as no record, it would
    look like a page never published, and a second page would be made over the first."""
    try:
        with open(os.path.join(profile_dir(), PAGE), encoding="utf-8") as fh:
            return "<<<<<<<" in fh.read()
    except OSError:
        return False


def page_owed(chat: str = "") -> str:
    """"new" when this chat should publish the person's first page now, else "": a copy of
    the person's own with a profile, no page address, a readable record, this chat never
    having said it cannot publish, and no other chat setting them up (it publishes there)."""
    try:
        if not os.path.isdir(profile_dir()) or page_record().get("url") or page_conflicted():
            return ""
        if repo_kind_offline()["kind"] in ("app", "none", "public"):
            return ""
        if no_page_here(chat):
            return ""
        if _setup_state().get("state") in ("going", "landed", "branch"):
            return ""
        return "new"
    except Exception:  # noqa: BLE001  a question about the page must never break a chat
        return ""


def _steps(eid: str, owner: str = "", name: str = "") -> list[str]:
    import claude_surfaces
    return claude_surfaces.steps(eid, name=name or "your copy", owner=owner)


NO_PAGE_DAYS = 30


def record_no_page(today: dt.date | None = None, chat: str = "", why: str = "") -> str:
    """This chat cannot publish (a surface with no pages, or a publish refused twice): it is
    not asked again for a month. Only this chat: every other chat still publishes."""
    path = _local_file(NO_PAGE)
    got = read_json(path, {})
    got[_chat_key(chat)] = {"day": (today or dt.date.today()).isoformat(),
                            "why": " ".join(str(why or "").split())[:200]}
    # A month's records at most: one a chat, and a chat on a computer is new each session.
    cut = ((today or dt.date.today()) - dt.timedelta(days=NO_PAGE_DAYS)).isoformat()
    got = {k: v for k, v in got.items() if isinstance(v, dict) and str(v.get("day")) >= cut}
    return _write_json(path, got)


def page_line(today: dt.date | None = None, landed: bool = False) -> str:
    """What the sync prints about the person's page, so a chat whose instructions predate
    the page still brings it up to date: once a page is published, the steps after an update
    (app_listen.after_update: republish when its own code changed, else refresh its data when
    an update `landed`); before that, start publishes it. Quiet for a month after a chat said
    it cannot publish."""
    try:
        if not os.path.isdir(profile_dir()):
            return ""
        if page_record().get("url"):
            import app_listen
            return "\n".join(app_listen.after_update(landed=landed))
        if _page_current() or page_conflicted() or no_page_here(today=today):
            return ""
    except Exception:  # noqa: BLE001
        return ""
    return ("Claude: the person's page is not published yet. Before the rest, run python3 "
            "tools/app.py start and do what it prints (it publishes the page; nothing to ask "
            "them).")
