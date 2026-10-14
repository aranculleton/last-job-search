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
    detail: true          # false where the posting page may not be fetched (robots.txt)
    pages: 2              # how deep a query goes
    canary-query: nurse   # a word the board always has postings for (health probe)

The places a round passes as `-l` are the person's: profile/search.py
`PORTAL_LOCATIONS = {"<portal>": ["<place as the board writes it>"]}`, and
otherwise the first of `SCRAPE_LOCATIONS`.

## linkedin-search, and what its default means

It ships on: in most markets it carries more postings than every other source
together. LinkedIn's robots.txt disallows its guest job endpoints for crawlers
it does not name, and a round sends it thousands of requests, so the person
should know that, and `/setup` tells them. Turning it off is one line:
`PORTALS = {"linkedin-search": False}`.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys

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
                           capture_output=True, text=True)
    if build.returncode or not os.path.exists(dist):
        raise RuntimeError("bun build failed for %s:\n%s"
                           % (skill, (build.stderr or build.stdout)[:800]))
    return dist


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
