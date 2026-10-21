"""hydrate sends a paced board one request at a time, a crawl-delay after the last ended.

A board with a crawl-delay got as many detail workers as the shared pool, and `pace`
spaced their starts but not their ends: with a fetch slower than the delay, the next
request to the board was sent while the last was still running, two or more in flight
at once. The scrape's own sweep of the same board is strictly one at a time, with the
delay after each.
"""
from __future__ import annotations

import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import hydrate  # noqa: E402
import portals  # noqa: E402

DELAY, FETCH = 0.3, 0.5


def test_one_request_in_flight_and_the_delay_after_each(monkeypatch):
    monkeypatch.setattr(portals, "crawl_delay", lambda skill: DELAY)
    monkeypatch.setattr(portals, "skill_of", lambda portal: "cityboard-search")
    monkeypatch.setattr(portals, "has_cli", lambda skill: True)
    monkeypatch.setattr(portals, "is_enabled", lambda skill: True)
    monkeypatch.setattr(portals, "has_detail", lambda skill: True)
    monkeypatch.setattr(hydrate, "portal_cli", lambda skill: os.devnull)
    hydrate._PACE.clear()
    inflight, peak, spans, lock = [0], [0], [], threading.Lock()

    def fetch(cmd, timeout=60, empty=None):
        with lock:
            inflight[0] += 1
            peak[0] = max(peak[0], inflight[0])
        began = time.monotonic()
        time.sleep(FETCH)
        with lock:
            inflight[0] -= 1
            spans.append((began, time.monotonic()))
        return {"description": "A body long enough to read. " * 30}, None

    monkeypatch.setattr(portals, "run_cli", fetch)
    jobs = [{"id": str(i), "url": f"https://cityboard.example/{i}", "portal": "cityboard",
             "title": "Analyst"} for i in range(4)]
    out = hydrate.hydrate_all(jobs, workers=10, progress_every=999)
    hydrate._PACE.clear()
    assert all(j.get("desc") for j in out)
    assert peak[0] == 1
    spans.sort()
    for (_, ended), (began, _) in zip(spans, spans[1:]):
        assert began - ended >= DELAY - 0.02
