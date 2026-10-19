#!/usr/bin/env python3
"""Employer job boards answered from canned responses, for tests: the supported way.

A person's own tests (profile/tests) that pin how their employers' boards are read
fake the network here, and nowhere else. Everything in tools/openroles/ and every name
in tools/ats_boards.py that starts with an underscore can change in any release; this
does not. A person's test that patched the old reader's private pieces broke, 48 of them
at once, when 3.5.0 moved the reading into openroles.

    from offline_boards import offline

    with offline() as web:
        web.routes["boards-api.greenhouse.io/v1/boards/acme/jobs"] = {"jobs": [...]}
        web.robots["acme.wd3.myworkdayjobs.com"] = (200, "User-agent: *\\nDisallow: /\\n")
        rows, why = ats_boards.FETCH["greenhouse"]("Acme", "acme")
        assert web.calls == [...]

`routes` maps a piece of a URL to its answer: JSON, text, `(None, "HTTP 404")`, or a
function of `(url, payload)`. A URL no route matches answers HTTP 404. `robots` maps a
host to `(status, body)` for its robots.txt; a host not named answers 404, which
RFC 9309 reads as no restriction. `calls` records every `(url, payload)` sent. Nothing
reaches the network, and everything is put back on leaving the block.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class Web:
    """What an `offline()` block reads and records."""

    def __init__(self, routes=None, robots=None):
        self.routes: dict = dict(routes or {})
        self.robots: dict = dict(robots or {})
        self.calls: list = []

    def request(self, url, payload=None, accept="application/json"):
        self.calls.append((url, payload))
        for key, answer in self.routes.items():
            if key in url:
                if callable(answer):
                    answer = answer(url, payload)
                return answer if isinstance(answer, tuple) else (answer, None)
        return None, "HTTP 404"

    def request_raw(self, url, payload=None, accept="*/*", limit=0):
        data, err = self.request(url, payload)
        return (data if isinstance(data, str) or data is None else json.dumps(data)), err

    def robots_txt(self, host):
        return self.robots.get(host, (404, ""))


@contextlib.contextmanager
def offline(routes=None, robots=None):
    """Every employer-board request inside the block answered by `Web`."""
    from openroles import _http
    web = Web(routes, robots)
    saved = {name: getattr(_http, name)
             for name in ("request", "request_raw", "robots_txt", "RETRY_PAUSE")}
    _http.request, _http.request_raw, _http.robots_txt = web.request, web.request_raw, web.robots_txt
    _http.RETRY_PAUSE = 0
    try:
        yield web
    finally:
        for name, value in saved.items():
            setattr(_http, name, value)
