"""The person's page is published as a small page and small code files, never one big file.

The Artifact tool has a chat read every file it did not write, whole, before it publishes it.
The page was one document of 0.7 to 1.6 MB (about 200,000 tokens), so a chat whose window
holds 200,000 could not publish it at all, and every republish read it all again (the
stranger audit, 3 November, X-3). Now `app.py page --out-dir` writes the page in parts: a
small page.html, whatever the size of the search (the search reaches the page through its
own store), and one small file for each section of the page's code. A file the published
page already holds is left out of the next publish, so a change to one section sends one
small file. Every person, page and chat id here is invented.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests"),
                os.path.join(ROOT, "templates", "app")]

import pytest  # noqa: E402

import app_page  # noqa: E402
import app_state  # noqa: E402
from test_one_chat_answers_the_page import Copy, PAGE  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "app_model_sample.json")


@pytest.fixture
def copy(tmp_path):
    c = Copy(tmp_path)
    yield c
    sys.path.remove(c.root)


def _app_json(c) -> dict:
    p = os.path.join(c.profile, "app.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def _files_named(said: str) -> dict:
    """{published path: local path} from every files map the plan prints."""
    out = {}
    for m in re.finditer(r"files (\{.*?\})(?=[,.;]? |$)", said, re.M):
        out.update(json.loads(m.group(1)))
    return out


def test_a_chat_reads_only_small_files_to_publish_a_big_search(copy):
    """X-3: a search with hundreds of contacts made a page of over a megabyte. In parts, the
    page a chat reads is small however big the search, and every code file fits one read."""
    app_state.large(copy.state, tracker_rows=150, contacts=400, threads=600)
    out = os.path.join(copy.root, "built")
    said = copy.run("page", "--out-dir", out, "--now", "2026-10-25T18:00:00Z",
                    "--today", "2026-10-25")
    page = os.path.join(out, "page.html")
    assert os.path.getsize(page) <= app_page.PAGE_MAX, os.path.getsize(page)
    files = _files_named(said)
    assert files, said
    for rel, path in files.items():
        assert rel.startswith("code/") and os.path.getsize(path) <= app_page.PART_MAX, rel
    # The plan says to read each file whole first, and names the page as the one to publish.
    assert f"file_path {page}" in said and "read each" in said.lower()
    # The first publish carries the capabilities; it is a new page, so it is published with
    # the briefcase icon and no address yet.
    assert "capabilities" in said and "icon briefcase" in said


def test_a_republish_sends_only_the_files_that_changed(copy, tmp_path, monkeypatch):
    """Once a page is published in parts, a change to one section of the page's code sends
    that one file, the rest is left out (and kept), and the capabilities are not declared
    again, so the publish never stops on an approval nobody is there to give (X-8)."""
    copy.page(current=True)
    out = os.path.join(copy.root, "built")
    first = copy.run("page", "--out-dir", out, "--url", PAGE)
    assert len(_files_named(first)) > 20, first       # never published in parts: every file
    copy.run("published", PAGE, "--parts", out)
    held = _app_json(copy).get("code")
    assert held and all(p.startswith("code/") for p in held)
    # Published without the folder (an older chat's steps), nothing is assumed held.
    copy.run("published", PAGE)
    assert "code" not in _app_json(copy)
    copy.run("published", PAGE, "--parts", out)
    said = copy.run("page", "--out-dir", out, "--url", PAGE)
    assert _files_named(said) == {}, said              # nothing changed: only the page
    publish = said.split("Artifact, action publish", 1)[-1].split("\n")[0]
    assert "--capabilities" not in publish and "with no capabilities" in publish
    # One section of app.js changed: its one file is new, the old one goes.
    tpl = tmp_path / "tpl"
    import shutil
    shutil.copytree(app_page.TEMPLATE_DIR, tpl)
    js = (tpl / "app.js").read_text(encoding="utf-8")
    js = js.replace("  // ------------------------------------------------------------------ dates and words",
                    "  // ------------------------------------------------------------------ dates and words\n"
                    "  const CHANGED_FOR_A_TEST = 1;", 1)
    (tpl / "app.js").write_text(js, encoding="utf-8")
    monkeypatch.setattr(app_page, "TEMPLATE_DIR", str(tpl))
    import app_setup
    monkeypatch.setenv("LJS_PROFILE", copy.profile)
    built = app_page.write_parts({"model": 1, "person": {"first_name": "Morgan"}}, out)
    got = app_page.plan(built, held, _app_json(copy).get("caps", ""), PAGE)
    assert len(got["new"]) == 1 and got["new"][0].startswith("code/js/dates-and-words."), got
    assert len(got["gone"]) == 1 and got["gone"][0].startswith("code/js/dates-and-words."), got
    assert got["capabilities"] is False
    assert app_setup  # the record read above is the copy's own


def test_a_chat_the_app_starts_is_granted_only_what_this_chat_holds(monkeypatch):
    """X-8: a job's chat and a fresh helper were said to carry Artifact so they "never stop on
    a permission prompt", but create_session drops a tool its caller has not pre-approved, and
    nothing pre-approves Artifact. What they are given is what .claude/settings.json allows."""
    import datetime as dt
    import app
    import app_listen
    allow = set(json.load(open(os.path.join(ROOT, ".claude", "settings.json"),
                               encoding="utf-8"))["permissions"]["allow"])
    assert set(app.CHILD_TOOLS) <= allow
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    monkeypatch.setattr(app_listen, "context_tokens", lambda: 0)
    monkeypatch.setattr(app_listen, "seen", lambda: {})
    monkeypatch.setattr(app_listen, "_save_seen", lambda got: None)
    monkeypatch.setattr("app_setup.origin", lambda: ("example-owner", "my-job-search"))
    rec = {"chat": "session_H", "kind": "cloud", "helper": True, "since": "2026-11-01T08:00:00Z"}
    got = app_listen.renewal(rec, {"work": {}}, "session_H",
                             dt.datetime(2026, 11, 3, 12, tzinfo=dt.timezone.utc))
    assert got and set(got["extra_allowed_tools"]) <= allow


def test_two_chats_that_each_republished_merge_with_nothing_to_ask():
    """What the published page holds (`code`, `caps`) goes with the publish dated later, and
    the day the person was told what their page is is a date: two chats that each republished
    and each said it merge with nothing left for the person to settle."""
    import merge_state
    base = json.dumps({"url": "https://claude.ai/code/artifact/x", "published_at": "2026-11-01T08:00:00Z",
                       "code": ["code/js/a.1.js"], "caps": "c1"})
    ours = json.dumps({"url": "https://claude.ai/code/artifact/x", "published_at": "2026-11-03T08:00:00Z",
                       "code": ["code/js/a.2.js"], "caps": "c1", "introduced": "2026-11-03"})
    theirs = json.dumps({"url": "https://claude.ai/code/artifact/x", "published_at": "2026-11-03T09:00:00Z",
                         "code": ["code/js/a.3.js"], "caps": "c2", "introduced": "2026-11-02"})
    text, problems = merge_state.merge(base, ours, theirs, "profile/app.json")
    got = json.loads(text)
    assert problems == [], problems
    assert got["code"] == ["code/js/a.3.js"] and got["caps"] == "c2"
    assert got["introduced"] in ("2026-11-02", "2026-11-03")


def test_the_page_in_parts_loads_its_own_files_only():
    """The small page loads its code from beside it, in order, and nothing from anywhere
    else; every script part parses on its own and they share one scope."""
    model = json.load(open(FIXTURE, encoding="utf-8"))
    page, files = app_page.render_parts(model)
    srcs = re.findall(r'<script src="([^"]+)"', page)
    links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', page)
    assert srcs and links and set(srcs) | set(links) == set(files)
    assert not re.search(r"(src|href)=\"https?:", page)
    assert len(page.encode("utf-8")) <= app_page.PAGE_MAX
    # The search is not in the page: it comes from the page's own store.
    embedded = json.loads(re.search(r'id="ljs-model">(.*?)</script>', page, re.S).group(1))
    assert embedded.get("slim") is True and "jobs" not in embedded and "people" not in embedded
    assert embedded["person"] == model["person"]
    # Joined again, the parts are the page's whole script, nothing lost or doubled.
    whole = app_page.compact_js(app_page._read("app.js"))
    for p in srcs:
        body = files[p].split("\n", 1)[1]
        assert body.strip() and body.strip().split("\n")[0] in whole


def test_the_parts_draw_what_the_whole_page_draws(tmp_path):
    """In a real browser: the page in parts, its search coming from its store, draws every
    section exactly as the page as one document does, with no error and no empty screen
    drawn before the store answers."""
    from test_the_page_works_in_a_browser import Runner, _node_env  # noqa: F401
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("no Node here, so no browser")
    env = _node_env()
    if subprocess.run([node, "-e", "require('playwright')"], env=env, capture_output=True).returncode:
        pytest.skip("Playwright for Node is not installed here")
    harness = os.path.join(ROOT, "tests", "app_page", "harness.js")
    proc = subprocess.Popen([node, harness], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env)
    run = Runner(proc)
    try:
        if not run.first().get("ready"):
            pytest.skip("Chromium would not start")
        model = json.load(open(FIXTURE, encoding="utf-8"))
        whole = tmp_path / "whole.html"
        whole.write_text(app_page.standalone(app_page.render(model)), encoding="utf-8")
        page, files = app_page.render_parts(model)
        parts = tmp_path / "parts.html"
        parts.write_text(app_page.standalone(page), encoding="utf-8")
        for rel, text in files.items():
            p = tmp_path.joinpath(*rel.split("/"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        stored = app_page._from_store()
        seed = {f"view/{k}": {"rev": model["rev"], "made_at": model["made_at"], "data": v}
                for k, v in model.items() if k in stored}
        r = run("parts", whole=str(whole), parts=str(parts), seed=seed)
    finally:
        proc.stdin.close()
        proc.wait(timeout=60)
    assert not r["parts"]["errors"], r["parts"]["errors"]
    assert not r["whole"]["errors"], r["whole"]["errors"]
    assert r["parts"]["title"] == r["whole"]["title"]
    for sid, text in r["whole"]["sections"].items():
        assert text and r["parts"]["sections"][sid] == text, sid
