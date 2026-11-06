#!/usr/bin/env python3
"""Which job portals a round searches, and how: the portal's own say, then the person's.

Two kinds of portal live under .agents/skills/:

- **The app's**, `linkedin-search` and `freehire-search`, which work in any
  country. Their SKILL.md files are the app's: a person never edits them,
  because `tools/sync_app.py` would put them back. A person's choice about them
  goes in profile/search.py, which overrides the default for each one it names:

      PORTALS = {"freehire-search": False}

- **The person's own**, built for their country, field and level by
  `/add-portal` (and offered by `/setup`). Those folders are personal files
  (`tools/personal_paths.py`), so their SKILL.md is the person's to edit and is
  never synced over. The app ships none of them: a board that serves one market
  belongs to the people in that market.

`tools/scrape_wide.py`, `tools/hydrate.py` and /scrape all read this, so a
portal that is off is sent no request at all, and every portal that is on and
follows the portal contract (`/add-portal`) is searched in every round, a
scheduled one included. `python3 tools/portals.py` prints what the next round
will search, how, and the boards researched for this person but not built.

## What a portal says about itself

A person's portal declares, in its SKILL.md frontmatter, what a round needs to
call it politely. `/add-portal` writes these from what it found:

    enabled: true
    contract: 1           # its CLI takes the round's calls; without it, /scrape only
    url: https://www.example-board.test     # the board, for tools/env_check.py
    crawl-delay: 5        # seconds between requests: robots.txt's, else 1
    location: free-text   # takes -l <place>; `none` for a board with no location filter
    remote: true          # takes --remote: remote postings only (absent: no such filter)
    detail: true          # false where the posting page may not be fetched (robots.txt)
    pages: 2              # how deep a query goes
    canary-query: nurse   # a word the board always has postings for (health probe)

The places a round passes as `-l` are the person's: profile/search.py
`PORTAL_LOCATIONS = {"<portal>": ["<place as the board writes it>"]}`, and
otherwise every one of `SCRAPE_LOCATIONS` (the first deep, the rest two pages),
the way LinkedIn is searched. A board that can filter for remote postings is
also searched with `--remote` and no place.

## linkedin-search, and what its default means

It ships on, and it stays on: in most markets it carries more postings than every
other source together. It reads LinkedIn's public job listings with no LinkedIn
account, so it cannot get anyone's account restricted; what LinkedIn can do is slow
or refuse the machine sending the requests. LinkedIn's robots.txt disallows its
guest job endpoints for crawlers it does not name, and a round sends it thousands of
requests, so the person should know that, and `/setup` tells them. Only the person
switches it off (`PORTALS = {"linkedin-search": False}` in profile/search.py): no tool,
upgrade or session ever does, and none suggests it (tests/test_linkedin_stays_on.py).
"""

from __future__ import annotations

import functools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, ".agents", "skills")


def _unquote(value: str) -> str:
    """A YAML scalar as written, less its quotes: `detail: "false"` is false."""
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1].strip()
    return v


def _flag(skill_md: str) -> bool:
    """A SKILL.md's `enabled:` value. A portal with no key is enabled."""
    with open(skill_md, encoding="utf-8") as fh:
        head = fh.read(4000)
    for line in head.splitlines():
        s = line.strip()
        if s.startswith("enabled:"):
            value = _unquote(s.split(":", 1)[1].split("#", 1)[0]).lower()
            return value not in ("false", "no", "0")
    return True


# The two portals the app itself calls by name in tools/scrape_wide.py, with
# their own request shapes. Every other portal is called through the contract.
APP_PORTALS = ("linkedin-search", "freehire-search")
# A person's portal that names no crawl-delay is still sent one request a second
# at most: a board nobody asked about has not said it can take more.
DEFAULT_DELAY = 1.0
DEFAULT_PAGES = 2
MAX_PAGES = 10


def meta(name: str, root: str | None = None) -> dict[str, str]:
    """A portal's SKILL.md frontmatter: its one-line `key: value` entries."""
    root = root or SKILLS
    try:
        with open(os.path.join(root, name, "SKILL.md"), encoding="utf-8") as fh:
            lines = fh.read(8000).splitlines()
    except OSError:
        return {}
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line[:1] in (" ", "\t") or ":" not in line:
            continue                       # a folded description's continuation
        key, value = line.split(":", 1)
        out[key.strip()] = _unquote(value.split(" #", 1)[0])
    return out


def short(name: str) -> str:
    """The name a posting carries in its `portal` field: `linkedin` for linkedin-search."""
    return name[:-len("-search")] if name.endswith("-search") else name


def skill_of(portal: str, root: str | None = None) -> str | None:
    """The portal folder a posting's `portal` field came from, or None."""
    for name in defaults(root):
        if portal in (name, short(name)):
            return name
    return None


def crawl_delay(name: str, root: str | None = None) -> float:
    """Seconds between two requests to this portal. The app's two portals keep
    the pace they always had (parallel requests, backoff on 429 inside their
    CLIs), so they return 0 here."""
    if name in APP_PORTALS:
        return 0.0
    try:
        value = float(meta(name, root).get("crawl-delay", DEFAULT_DELAY))
    except ValueError:
        return DEFAULT_DELAY
    return value if value >= 0 else DEFAULT_DELAY


def takes_location(name: str, root: str | None = None) -> bool:
    return meta(name, root).get("location", "free-text").lower() not in ("none", "no", "false")


def takes_remote(name: str, root: str | None = None) -> bool:
    """Whether its CLI takes `--remote` (remote postings only). A board with no
    such filter still shows remote postings filed under a place it searches."""
    return meta(name, root).get("remote", "false").lower() in ("true", "yes", "1")


def has_detail(name: str, root: str | None = None) -> bool:
    return meta(name, root).get("detail", "true").lower() not in ("false", "no", "0")


def pages(name: str, root: str | None = None) -> int:
    try:
        n = int(meta(name, root).get("pages", DEFAULT_PAGES))
    except ValueError:
        return DEFAULT_PAGES
    return min(max(n, 1), MAX_PAGES)


def url(name: str, root: str | None = None) -> str:
    return meta(name, root).get("url", "")


# ------------------------------------------------------------ what a site is, in plain words
#
# Every job site the page shows has a plain name and one line saying what it is, and a site
# that needs a key says so with the steps to get one. This is the one place that holds it:
# the page's Settings, Job sites, reads it through tools/app_model.py. "api.adzuna.com" stood
# where "Adzuna" should have, and its tick turned itself off after a visit because the site
# had no key (the maintainer, 2026-11-06).
#
# A person's own portal can say all of it in its SKILL.md frontmatter (/add-portal writes
# these): `label: Built In Toronto`, `note: <one line>`, `key-env: CITYBOARD_API_TOKEN`
# (the variables its CLI reads), `key-url: <where to sign up>` and `key-free: true`. A site
# named here needs none of them, and a portal built before those lines existed still shows
# its key: its CLI's own MISSING_CREDENTIALS check names the variables (`key_names`).
#
# A sign-up's steps are the job site's own, read from its official page on `checked`
# (`source`, for Claude); the last step is always the chat, where Claude shows the person
# where the key goes (SETUP.md, "A job site that needs a key").
SITES: dict[str, dict] = {
    "linkedin": {"label": "LinkedIn", "note": "LinkedIn's own job search, in every country."},
    "freehire": {"label": "Freehire", "note": "A free board that gathers jobs from many sites."},
    "adzuna": {
        "label": "Adzuna",
        "note": "Jobs gathered from many sites in the UK and over a dozen other countries, "
                "many of them from agencies.",
        "key": {
            "free": True,
            "url": "https://developer.adzuna.com/signup",
            "source": ("https://developer.adzuna.com/signup",
                       "https://developer.adzuna.com/overview",
                       "https://developer.adzuna.com/docs/terms_of_service"),
            "checked": "2026-11-06",
            "steps": (
                "Open developer.adzuna.com/signup.",
                "Fill in a username, your email and a password.",
                "For the organisation's name and website, give your own name and a page "
                "about you.",
                "Under \"Your application of the Adzuna API\", choose \"Personal job search\".",
                "Under \"Average Monthly Visitors\", choose \"N/A\".",
                "Choose your market, then register.",
                "Keep the two codes Adzuna gives you: an app ID and an app key.",
            ),
        },
    },
    "indeed": {"label": "Indeed", "note": "One of the largest job boards, in many countries."},
    "glassdoor": {"label": "Glassdoor", "note": "Jobs beside what staff say about working there."},
    "jobbank": {"label": "Job Bank", "note": "The Government of Canada's own job board."},
    "reed": {"label": "Reed", "note": "A large UK job board."},
    "cvlibrary": {"label": "CV-Library", "note": "A large UK job board."},
}
# What a site's row says where no line says more.
DEFAULT_NOTE = "A job site Claude set up for your search."
# The last step of every key's steps: how the key reaches the app, in a chat.
KEY_LAST_STEP = ("In a chat with Claude, say \"I have my {label} key\". Claude shows you "
                 "the safe place for it, and the site is searched from then on.")
# The words of a host that are never the site's name.
_HOST_NOISE = {"www", "api", "jobs", "job", "careers", "developer", "m", "app",
               "com", "co", "org", "net", "uk", "ca", "au", "nz", "ie", "de", "fr",
               "in", "io", "gov", "gc"}


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", str(text or "").lower()) if w]


def site_of(name: str, root: str | None = None) -> str:
    """The SITES entry a portal is, by its folder's words or its address's ("" for none):
    `adzuna-search` and a portal at api.adzuna.com are both "adzuna"."""
    import urllib.parse
    folder = _words(short(name))
    host = _words(urllib.parse.urlparse(url(name, root)).netloc)
    joined = "".join(folder)
    for key in SITES:
        if key in folder or key in host or key == joined:
            return key
    return ""


def _heading(name: str, root: str | None = None) -> str:
    """The portal's own SKILL.md title, less "Search Skill": "# Built In Toronto Job Search"
    is Built In Toronto."""
    root = root or SKILLS
    try:
        with open(os.path.join(root, name, "SKILL.md"), encoding="utf-8") as fh:
            text = fh.read(8000)
    except OSError:
        return ""
    m = re.search(r"^# +(.+?)\s*$", text, re.M)
    if not m:
        return ""
    words = re.sub(r"(?:\s+(?:jobs?\s+search|search|skill|cli))+$", "",
                   m.group(1).strip(), flags=re.I).strip()
    return words if words and "." not in words else ""


def label(name: str, root: str | None = None) -> str:
    """A site's plain name, never its address ("api.adzuna.com") nor a folder's
    ("adzuna-search"): its own `label:`, the name SITES gives it, its SKILL.md title, then
    its folder's words."""
    own = meta(name, root).get("label", "").strip()
    if own:
        return own
    key = site_of(name, root)
    if key:
        return SITES[key]["label"]
    heading = _heading(name, root)
    if heading:
        return heading
    words = [w for w in re.split(r"[-_]+", short(name)) if w and w.lower() not in _HOST_NOISE]
    return " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in words) or short(name)


def note(name: str, root: str | None = None) -> str:
    """One line saying what the site is: its own `note:`, SITES's, what the board research
    found it covers (PORTAL_RESEARCH `covers`), else a plain default."""
    own = meta(name, root).get("note", "").strip()
    if own:
        return own
    key = site_of(name, root)
    if key:
        return SITES[key]["note"]
    import urllib.parse
    host = urllib.parse.urlparse(url(name, root)).netloc.lower().removeprefix("www.")
    for r in research():
        at = urllib.parse.urlparse(str(r.get("url") or "")).netloc.lower().removeprefix("www.")
        same = (host and at and host == at) or r.get("portal") == name
        if same and str(r.get("covers") or "").strip():
            said = str(r["covers"]).strip()
            return said[:1].upper() + said[1:] + ("" if said.endswith(".") else ".")
    return DEFAULT_NOTE


# A variable a portal's CLI reads its key from: `process.env.X`, `Bun.env["X"]`.
_ENV_READ = re.compile(r"(?:process\.env|Bun\.env|import\.meta\.env)"
                       r"(?:\.([A-Z][A-Z0-9_]*)|\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\])")
_KEYISH = re.compile(r"KEY|TOKEN|SECRET|APP_ID|CLIENT_ID|PASSWORD")


def key_names(name: str, root: str | None = None) -> list[str]:
    """The variables a portal reads its key from: its `key-env:` line, else the ones its
    CLI's sources read where they say MISSING_CREDENTIALS (/add-portal's contract), [] for
    a site that needs none."""
    own = meta(name, root).get("key-env", "")
    if own.strip():
        return [x for x in re.split(r"[\s,]+", own) if x]
    root = root or SKILLS
    src = os.path.join(root, name, "cli", "src")
    texts = []
    for folder, _dirs, files in os.walk(src):
        for f in files:
            if f.endswith((".ts", ".js", ".mjs")):
                try:
                    with open(os.path.join(folder, f), encoding="utf-8") as fh:
                        texts.append(fh.read(200_000))
                except OSError:
                    continue
    if not any("MISSING_CREDENTIALS" in t for t in texts):
        return []
    found = []
    for t in texts:
        for m in _ENV_READ.finditer(t):
            var = m.group(1) or m.group(2)
            if _KEYISH.search(var) and var not in found:
                found.append(var)
    return found


def needs_key(name: str, root: str | None = None) -> bool:
    key = site_of(name, root)
    return bool(key_names(name, root)) or bool(key and SITES[key].get("key"))


def has_key(name: str, root: str | None = None, env=None) -> bool:
    """Whether this computer holds the key a site needs (True for a site that needs none).
    The variables it names must all be set; a site named in SITES whose CLI names none has
    its key where any variable of its name holding a key or token is set."""
    env = os.environ if env is None else env
    if not needs_key(name, root):
        return True
    names = key_names(name, root)
    if names:
        return all(str(env.get(n) or "").strip() for n in names)
    stem = (site_of(name, root) or short(name)).upper().replace("-", "_") + "_"
    return any(k.startswith(stem) and _KEYISH.search(k) and str(v or "").strip()
               for k, v in env.items())


def key_help(name: str, root: str | None = None) -> dict:
    """For a site that needs a key: whether it is free and the numbered steps to get it, one
    action a line, ending with how it reaches the app. {} for a site that needs none."""
    if not needs_key(name, root):
        return {}
    plain = label(name, root)
    key = site_of(name, root)
    known = dict(SITES[key].get("key") or {}) if key else {}
    own = meta(name, root)
    free = own.get("key-free", "").lower() in ("true", "yes", "1") or bool(known.get("free"))
    steps = list(known.get("steps") or ())
    if not steps:
        where = re.sub(r"^https?://(www\.)?", "", own.get("key-url", "").strip() or url(name, root))
        steps = [f"Open {where} and sign up for {'a free' if free else 'a'} key."
                 if where else f"Sign up with {plain} for {'a free' if free else 'a'} key."]
    return {"free": free, "steps": steps + [KEY_LAST_STEP.format(label=plain)]}


def follows_contract(name: str, root: str | None = None) -> bool:
    """Whether the portal says it takes the round's calls (`contract: 1`, which
    /add-portal writes once its CLI accepts `search -q -l --jobage --page
    --format json` and `detail <id>`). A portal without it, such as one built
    before rounds called person portals, is searched by /scrape by hand only."""
    return meta(name, root).get("contract", "") not in ("", "0", "false", "no")


def has_cli(name: str, root: str | None = None) -> bool:
    root = root or SKILLS
    base = os.path.join(root, name, "cli")
    return (os.path.isfile(os.path.join(base, "dist", "cli.mjs"))
            or os.path.isfile(os.path.join(base, "src", "cli.ts")))


def env_var(name: str) -> str:
    """The variable that points a portal at another build: LINKEDIN_CLI."""
    return short(name).upper().replace("-", "_") + "_CLI"


# These pointed at one build in one session's scratchpad directory, named with
# that session's own UUID. A scratchpad does not survive the container, so on
# every fresh checkout the scrape resolved both paths to files that were not
# there and produced nothing, with no error saying why.
#
# The sources are in the repo and carry no runtime dependencies. This finds a
# build if one exists, makes one if bun is there, and says what to run if
# neither. scrape_wide.py and hydrate.py both use this one.
@functools.lru_cache(maxsize=None)
def cli(skill: str, env: str | None = None) -> str:
    """The runnable CLI for a portal, built on demand.

    Returns a path to a bundled `.mjs`. Raises with the build command when the
    sources are present but nothing can build them, because a scrape that
    quietly returns nothing is the failure the scrape exists to avoid.
    """
    env = env or env_var(skill)
    override = os.environ.get(env, "").strip()
    if override:
        if not os.path.exists(override):
            raise FileNotFoundError("%s points at %s, which does not exist"
                                    % (env, override))
        return override
    dist = os.path.join(SKILLS, skill, "cli", "dist", "cli.mjs")
    if os.path.exists(dist):
        return dist
    src = os.path.join(SKILLS, skill, "cli", "src", "cli.ts")
    if not os.path.exists(src):
        raise FileNotFoundError(
            "no CLI for %s: neither a build nor %s. Is .agents/skills/%s present?"
            % (skill, src, skill))
    if not shutil.which("bun"):
        raise RuntimeError(
            "%s needs building and bun is not installed. Install bun, or build "
            "it elsewhere and point %s at the result." % (skill, env))
    os.makedirs(os.path.dirname(dist), exist_ok=True)
    build = subprocess.run(["bun", "build", src, "--target", "node",
                            "--outfile", dist],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if build.returncode or not os.path.exists(dist):
        raise RuntimeError("bun build failed for %s:\n%s"
                           % (skill, (build.stderr or build.stdout)[:800]))
    return dist


class NoRuntime(RuntimeError):
    """Neither Node nor Bun is on this computer, so no portal's CLI can run."""


NO_RUNTIME = ("the job searches need Node or Bun to run, and this computer has neither: "
              "`python3 tools/env_check.py --fix` installs Bun (no password)")


@functools.lru_cache(maxsize=None)
def runtime() -> tuple:
    """The command a portal's built CLI (`dist/cli.mjs`) runs under: Node, else Bun.

    Every call ran `node`, which nothing installed: env_check and setup_env.sh looked for
    Bun alone, so a computer with Bun and no Node had every probe fail with a
    FileNotFoundError, read as "left to the scrape", and the round ended "thin market"
    (exit 2) having searched nothing. The build is plain JavaScript for Node, and Bun runs
    it as it is (`bun run dist/cli.mjs ...`), so either will do. Always two words, so the
    CLI's path is the third word of every command whichever runs it. It raises NoRuntime,
    with what to run, when there is neither; a caller says so rather than calling it a
    thin market."""
    try:
        import local_path
        local_path.extend()       # ~/.bun/bin, which a chat's shell on a Mac lacks
    except Exception:             # noqa: BLE001  finding a runtime must not need it
        pass
    node = shutil.which("node")
    if node:
        return (node, "--no-warnings")
    bun = shutil.which("bun")
    if bun:
        return (bun, "run")
    raise NoRuntime(NO_RUNTIME)


# ------------------------------------------------------------ running a portal's CLI
#
# The one runner for every call to a portal's CLI: a search (tools/scrape_wide.py) and a
# detail fetch (tools/hydrate.py). The second, and a job-alert reader since removed, had
# copies of their own that kept only stderr's last line, so a
# board that said THROTTLED, or that robots.txt disallowed the page, and then printed a
# JSON error, was recorded as the JSON error.

# A line in which a board says it is refusing: THROTTLED, a redirect to a sandbox,
# robots.txt, a missing credential.
REFUSAL_LINE = re.compile(r"\bTHROTTLED\b|/sandbox\b|robots\.txt\s+disallows|disallowed by "
                          r"robots\.txt|\bMISSING_CREDENTIALS\b")
EXIT_PREFIX = re.compile(r"^exit -?\d+:\s*")


def refusal(text: str | None) -> str:
    """The line in which a portal said it is refusing (THROTTLED, a sandbox redirect,
    robots.txt, a missing credential), as it said it, or ""."""
    for line in str(text or "").splitlines():
        line = EXIT_PREFIX.sub("", line.strip())
        if not REFUSAL_LINE.search(line):
            continue
        try:
            body = json.loads(line)
            if isinstance(body, dict) and body.get("error"):
                line = str(body["error"])
        except ValueError:
            pass
        return line[:200]
    return ""


def _no_results(got: dict) -> bool:
    return not got.get("results")


def run_cli(cmd: list[str], timeout: int = 90, empty=None) -> tuple[dict | None, str | None]:
    """(parsed JSON, None) on success; (None, reason) on any failure.

    Failures used to vanish: a blocked or rate-limited portal just produced a
    smaller file with exit 0 and nothing said so. Every failure now has a
    reason, and the scrape (tools/scrape_wide.py) counts them per portal and
    refuses to look healthy when more than a quarter of the requests failed.

    `empty` says when an answer holds nothing: a search with no results (the
    default), a detail with no description. Nothing, with a refusal said, is a
    refusal.

    ## Why stdout goes to a FILE and not a pipe

    A live round reported `freehire: 327/441 requests failed` with
    `JSONDecodeError: Unterminated string starting at: line 363`. Run one at a
    time the same queries succeed every time; run ten at once and all ten fail,
    each returning 65,381 or 65,443 or 65,203 bytes. That is 64 KiB, a pipe
    buffer.

    Node writes to stdout ASYNCHRONOUSLY when stdout is a pipe and
    SYNCHRONOUSLY when it is a regular file. A CLI that calls `process.exit()`
    after writing therefore loses whatever has not drained, and under
    concurrency nothing drains: one query's 160 KB of JSON arrives as the
    first 64 KB, cut mid-string. Exit status is 0, because as far as the
    process is concerned it wrote and exited.

    The failure is silent in the worst way. A truncated body is not an error
    the portal reported, it is a portal that looks slow, and three quarters of
    one of the two enabled sources was being thrown away every round.

    A temporary file costs nothing and removes the buffer entirely. The fix is
    on this side on purpose: the portal CLIs are plug-ins, `/add-portal`
    scaffolds more of them, and every one written the same way would carry the
    same bug.

    ## Why the reason is not always stderr's last line

    One person's board printed `THROTTLED: ... redirecting searches to /sandbox
    (robots.txt disallows it); not followed.` and then its JSON error, and only the
    JSON reached the round. A line that names a refusal is kept wherever it falls, and
    exit 0 with nothing found and a refusal said is a refusal, not an empty market.
    """
    env = dict(os.environ, NODE_USE_ENV_PROXY="1")
    try:
        with tempfile.TemporaryFile("w+", encoding="utf-8") as fh:
            p = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE,
                               text=True, timeout=timeout, env=env,
                               encoding="utf-8", errors="replace")
            fh.seek(0)
            out = fh.read()
        said = refusal(p.stderr)
        if p.returncode != 0:
            err = (p.stderr or "").strip().splitlines()
            why = said or (err[-1].strip()[:120] if err else "no stderr")
            return None, f"exit {p.returncode}: {why}"
        if not out.strip():
            return None, f"exit 0: {said}" if said else "empty output"
        got = json.loads(out)
        if said and isinstance(got, dict) and (empty or _no_results)(got):
            return None, f"exit 0: {said}"
        return got, None
    except subprocess.TimeoutExpired:
        return None, f"timeout after {timeout}s"
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}"


def defaults(root: str | None = None) -> dict[str, bool]:
    """{portal: enabled} as the app ships it, read from each SKILL.md."""
    root = root or SKILLS
    out = {}
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        skill = os.path.join(root, name, "SKILL.md")
        if os.path.isfile(skill):
            out[name] = _flag(skill)
    return out


def overrides() -> dict[str, bool]:
    """The person's PORTALS, or {} where there is no profile or no setting."""
    try:
        chosen = getattr(person.module("search"), "PORTALS", {}) or {}
    except person.NoProfile:
        return {}
    return {str(k): bool(v) for k, v in dict(chosen).items()}


def enabled(chosen: dict[str, bool] | None = None, root: str | None = None) -> dict[str, bool]:
    """{portal: on} for every installed portal: the default, then the person's say."""
    chosen = overrides() if chosen is None else chosen
    base = defaults(root)
    return {name: chosen.get(name, on) for name, on in base.items()}


def unknown(chosen: dict[str, bool] | None = None, root: str | None = None) -> list[str]:
    """Names in PORTALS that match no installed portal: a typo switches nothing."""
    chosen = overrides() if chosen is None else chosen
    base = defaults(root)
    return sorted(k for k in chosen if k not in base)


def is_enabled(name: str) -> bool:
    return enabled().get(name, False)


def research() -> list[dict]:
    """The job boards researched for this person (profile/search.py
    PORTAL_RESEARCH): each one built as a portal, or why not, with its source."""
    try:
        rows = getattr(person.module("search"), "PORTAL_RESEARCH", []) or []
    except person.NoProfile:
        return []
    return [dict(r) for r in rows if isinstance(r, dict)]


def not_built() -> list[dict]:
    """Researched boards with no portal here: the coverage a round does not have."""
    have = set(defaults())
    return [r for r in research()
            if r.get("portal") not in have and str(r.get("status", "")).lower() != "built"]


def main() -> int:
    base, chosen = defaults(), overrides()
    for name, on in enabled(chosen).items():
        why = ("profile/search.py PORTALS" if name in chosen
               else "the app's default" if name in APP_PORTALS
               else "your portal (its SKILL.md)")
        how = ""
        if name not in APP_PORTALS:
            how = (f"  {crawl_delay(name):g}s apart, {pages(name)} page(s)"
                   f"{'' if takes_location(name) else ', no location filter'}"
                   f"{', remote searched' if takes_remote(name) else ', no remote filter (/add-portal adds one where the board has it)'}"
                   f"{'' if has_detail(name) else ', search text only (no detail fetch)'}"
                   f"{'' if has_cli(name) else '; NO CLI, so rounds cannot call it'}"
                   f"{'' if follows_contract(name) else '; no `contract: 1`, so rounds skip it (/add-portal)'}")
        print(f"  {'ON ' if on else 'off'}  {name:20} {why}{how}")
    for name in unknown(chosen):
        print(f"  ??   {name:20} named in PORTALS, but no portal has that name: "
              f"it switches nothing. Installed: {', '.join(base)}")
    gaps = not_built()
    if gaps:
        print("researched for you, not built (profile/search.py PORTAL_RESEARCH):")
        for r in gaps:
            print(f"  --   {r.get('board', '?')}: {r.get('status', 'not built')}"
                  f"{'  ' + r['url'] if r.get('url') else ''}")
    return 1 if unknown(chosen) else 0


if __name__ == "__main__":
    sys.exit(main())
