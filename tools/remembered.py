#!/usr/bin/env python3
"""What one page build works out once: an employer's tier and verdict, a posting's pay.

Building the page's model asked the same questions hundreds of times (the second audit of
2026-11-10, D8, profiled on a person's copy at about 12 seconds a build): each job's employer
against the person's lists twice (`bar.verdict`, then `bar.listed`, each through
`opportunity.tier`), each posting's pay range twice (`bar.verdict` and `text_screen.screen`).
Within one build nothing they read changes, so each answer is kept for the build and thrown
away with it: outside a build nothing is kept, so no answer can outlive what it was read
from (a list the person edits, a test that sets one). The few inputs a build can see change
are part of the key (`bar.verdict` keys on the judgements file's time and size).

    with remembered.build():
        ... remembered.get("tier", company, lambda: _tier(company)) ...

Standard library only.
"""
from __future__ import annotations

import contextlib

_STACK: list[dict] = []


@contextlib.contextmanager
def build():
    """Within it, `get` keeps each answer; nested, the outer build's are kept."""
    _STACK.append(_STACK[-1] if _STACK else {})
    try:
        yield
    finally:
        _STACK.pop()


def active() -> bool:
    return bool(_STACK)


def get(kind: str, key, make):
    """`make()`, once a build for (`kind`, `key`); every time outside one."""
    if not _STACK:
        return make()
    memo = _STACK[-1]
    k = (kind, key)
    try:
        return memo[k]
    except KeyError:
        got = memo[k] = make()
        return got


def day():
    """The person's own day, read once a build (`person.today()` reads their zone each time),
    so every answer kept in a build is for the same day; outside a build, read now."""
    import person
    return get("day", None, person.today)
