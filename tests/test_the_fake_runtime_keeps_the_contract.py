"""The page's browser tests run it against a fake of the viewer's runtime: that fake keeps the
runtime's contract, or a page bug passes every test.

On 2026-11-11 Read your prep did nothing on every real device while every test passed: the
runtime hands a snapshot's data over frozen (db.d.ts 0.2.91, "Delivered snapshots and their
data() are frozen"), the page changed one, and the fake had handed out copies anyone could
change. tests/app_page/fake_claude.js now follows the contract's type definitions (the
artifact-capabilities skill serves them for the published page's runtime, 0.2.91) call by
call, and this holds it there: each probe calls window.claude on a page holding nothing else,
in tests/app_page/harness.js's `contract`, and the answer is the contract's.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from test_the_page_works_in_a_browser import run  # noqa: E402

_ = run   # the fixture, used by name


def _probe(run, tmp_path, **fake):
    html = tmp_path / "blank.html"
    html.write_text("<!doctype html><title>Contract</title><p>Nothing but the runtime.</p>", encoding="utf-8")
    fake = dict({"hang": ["tts"], "sample": {"toolCalls": [{"name": "t"}], "reply": "Fine."}}, **fake)
    r = run("contract", html=str(html), fake=fake)
    assert not r["errors"], r["errors"]
    return r


def test_the_fake_runtime_answers_as_the_contract_does(run, tmp_path):
    r = _probe(run, tmp_path)
    # claude.d.ts: `use` alone, one promise a capability, null for anything the page does not
    # declare, the namespace frozen; permissions is built in.
    assert r["oneKey"] == "use" and r["samePromise"] and r["nsFrozen"] and r["permissions"]
    assert r["undeclared"] == [None] * 5
    # db.d.ts: snapshots and their data frozen, all the way down, and the same object while the
    # document has not changed; a change in strict code throws.
    assert r["frozen"] and r["sameDoc"] and r["queryFrozen"], r
    assert r["strictMutation"] == "TypeError"
    assert r["queryOrder"] == ["c", "b", "a"] and r["queryFirstChanges"] == ["added"] * 3
    # The page's own write shows at once, pending, before the store answers, then confirmed; a
    # refused one is taken back.
    assert r["echo"] == [[False, False], [True, True]], r["echo"]
    assert r["confirmed"][-1] == [True, False], r["confirmed"]
    assert r["refused"] == "unavailable" and r["refusedSeen"] == [[False, False], [True, True], [False, False]], r["refusedSeen"]
    # A query listener hears what changed since its last snapshot, and a document that did not
    # change keeps its object; a listener let go before its first delivery is never called.
    assert r["changes"] == ["modified:b"] and r["keptObject"] and r["earlyCalls"] == 0, r
    # What the store refuses: a body that is not an object, over 256 KiB or 32 levels; an
    # update of nothing; a path out of the grammar (a TypeError at once); a query out of its
    # limits (rejected on a read, on the error callback of a subscription).
    assert [r["arrayBody"], r["bigBody"], r["deepBody"], r["updateMissing"]] == ["invalid_argument"] * 4
    assert [r["longSegment"], r["manySegments"], r["oddDoc"], r["badChar"]] == ["TypeError"] * 4
    assert r["queries"] == ["invalid_argument"] * 6 and r["badSub"] == "invalid_argument", r["queries"]
    # At most 64 live subscriptions: the 65th dies on its error callback.
    assert r["cap"] == [64, "resource_exhausted"], r["cap"]
    # A lease's length is clamped, and a busy one says when it ends, never who holds it.
    assert r["lease"] == [True, False, False, True, True], r["lease"]
    # user.d.ts: can() answers its own names only; me() agrees with the accessors.
    assert r["can"] == [True, False] and r["me"]
    # comments.d.ts: a ring's text and target are checked before anything is sent.
    assert r["ring"] == ["invalid"] * 5, r["ring"]
    # downloads.d.ts: only the allowed kinds of file, named and not empty; an ArrayBuffer is
    # handed over and left empty.
    assert r["save"] == ["rejected_extension", "bad_request", "bad_request", "ok"] and r["transferred"], r["save"]
    # assets.d.ts: the closed set of types, exact, never empty; ids of 32; list and delete as typed.
    assert r["upload"] == ["unsupported_type", "invalid_request", "invalid_request", "unsupported_type", "ok", "invalid_request"], r["upload"]
    assert r["assets"] == [32, 2, "bytes,files,maxBytes,maxFiles", True, False], r["assets"]
    # sample.d.ts: a malformed call is refused with nothing sent; an aborted signal cancels; a
    # tool that throws is an answer to Claude, not a failed call; json reads only JSON.
    assert r["sample"] == ["invalid_request", "invalid_request", "invalid_request", "invalid_request", "cancelled",
                           "invalid_request", "invalid_request", "prompt_too_large", "ok"], r["sample"]
    assert r["badJson"] == "invalid_json"
    # mcp.d.ts: only the declared server and tools; Claude's browser outside the desktop app
    # is not connected and not listed.
    assert r["mcp"] == ["not_in_manifest", "not_in_manifest", "server_not_connected"], r["mcp"]
    assert r["listed"] == 0
    # A host that never answers resolves null after ten seconds; access taken away is heard
    # once by each listener, and every later call is refused.
    assert r["hung"] == ["waiting", None], r["hung"]
    assert r["revoked"] == [["revoked"], "revoked", "revoked"], r["revoked"]


def test_a_viewer_who_is_not_the_owner_reads_and_writes_nothing(run, tmp_path):
    """The page is published owner-only (tools/app_page.py capabilities): a viewer it is shared
    with reads nothing from its store and writes nothing to it, gets no assets, cannot send to
    Claude and cannot reach Claude's browser. The fake gave them all of it until 4.15."""
    html = tmp_path / "blank.html"
    html.write_text("<!doctype html><title>Contract</title><p>Nothing but the runtime.</p>", encoding="utf-8")
    r = run("contract", html=str(html), guest=True, fake={"owner": False})
    assert not r.pop("errors")
    assert r == {"read": False, "query": 0, "write": "invalid_argument", "lease": "invalid_argument", "assets": None,
                 "can": "writers_only", "ring": "claude_unavailable", "dataWrite": False, "browser": "server_not_connected"}, r
