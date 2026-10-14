#!/usr/bin/env python3
"""Which job portals a round searches: the app's default, then the person's say.

Every portal under .agents/skills/ declares `enabled:` in its SKILL.md. That is
the app's default, and those files are the app's: a person never edits them,
because `tools/sync_app.py` would put them back. A person's own choice goes in
profile/search.py, and overrides the default for each portal it names:

    PORTALS = {"jobindex-search": True}

`tools/scrape_wide.py`, `tools/hydrate.py` and /scrape all read this, so a
portal that is off is sent no request at all. `python3 tools/portals.py` prints
what the next round will search and why.

## linkedin-search, and what its default means

It ships on: in most markets it carries more postings than every other source
together. LinkedIn's robots.txt disallows its guest job endpoints for crawlers
it does not name, and a round sends it thousands of requests, so the person
should know that, and `/setup` tells them. Turning it off is one line:
`PORTALS = {"linkedin-search": False}`.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(ROOT, ".agents", "skills")


def _flag(skill_md: str) -> bool:
    """A SKILL.md's `enabled:` value. A portal with no key is enabled."""
    with open(skill_md, encoding="utf-8") as fh:
        head = fh.read(4000)
    for line in head.splitlines():
        s = line.strip()
        if s.startswith("enabled:"):
            value = s.split(":", 1)[1].split("#", 1)[0].strip().lower()
            return value not in ("false", "no", "0")
    return True


def defaults(root: str = SKILLS) -> dict[str, bool]:
    """{portal: enabled} as the app ships it, read from each SKILL.md."""
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


def enabled(chosen: dict[str, bool] | None = None, root: str = SKILLS) -> dict[str, bool]:
    """{portal: on} for every installed portal: the default, then the person's say."""
    chosen = overrides() if chosen is None else chosen
    base = defaults(root)
    return {name: chosen.get(name, on) for name, on in base.items()}


def unknown(chosen: dict[str, bool] | None = None, root: str = SKILLS) -> list[str]:
    """Names in PORTALS that match no installed portal: a typo switches nothing."""
    chosen = overrides() if chosen is None else chosen
    base = defaults(root)
    return sorted(k for k in chosen if k not in base)


def is_enabled(name: str) -> bool:
    return enabled().get(name, False)


def main() -> int:
    base, chosen = defaults(), overrides()
    for name, on in enabled(chosen).items():
        why = ("profile/search.py PORTALS" if name in chosen
               else "the app's default (its SKILL.md)")
        print(f"  {'ON ' if on else 'off'}  {name:20} {why}")
    for name in unknown(chosen):
        print(f"  ??   {name:20} named in PORTALS, but no portal has that name: "
              f"it switches nothing. Installed: {', '.join(base)}")
    return 1 if unknown(chosen) else 0


if __name__ == "__main__":
    sys.exit(main())
