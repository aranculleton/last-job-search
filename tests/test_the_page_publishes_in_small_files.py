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


def _listing(out: str, drop: tuple = (), resize: tuple = (), extra: tuple = ()) -> str:
    """What Artifact, action list, scope files printed for a page published from `out`, in
    the host's own words (read off a real publish, 2026-11-04): a file left out (`drop`), at
    another size (`resize`), or one the build no longer makes (`extra`)."""
    rows = []
    for root, _, names in os.walk(os.path.join(out, "code")):
        for n in names:
            rel = os.path.relpath(os.path.join(root, n), out).replace(os.sep, "/")
            if rel in drop:
                continue
            size = os.path.getsize(os.path.join(root, n)) + (7 if rel in resize else 0)
            kind = "text/css" if rel.endswith(".css") else "text/javascript"
            rows.append(f'- "{rel}"  {kind}  {size} bytes')
    rows += [f'- "{p}"  text/javascript  10 bytes' for p in extra]
    rows.append('- "index.html"  text/html  10372 bytes')
    return f"Published files of {PAGE} (version 1-ab), {len(rows)} files by path:\n" + "\n".join(sorted(rows))


def _with_list(copy, out: str, listing: str, *more: str) -> str:
    path = os.path.join(copy.root, "listing.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(listing)
    return copy.run("page", "--out-dir", out, "--url", PAGE, "--on-page", path, *more)


def test_a_republish_puts_back_what_the_host_lost_and_a_whole_one_sends_everything(copy):
    """The record says what the page holds; the host's own list is what it holds. A file
    the record names and the host lacks (a publish cut short) or holds at another size goes
    up again, a file the build no longer makes comes off, and the page's "did not load
    fully" button (--whole) sends every code file again."""
    copy.page(current=True)
    out = os.path.join(copy.root, "built")
    copy.run("page", "--out-dir", out, "--url", PAGE)
    copy.run("published", PAGE, "--parts", out)
    held = _app_json(copy)["code"]
    js = sorted(p for p in held if p.endswith(".js"))
    lost, bent, stray = js[3], held[0], "code/js/old-part.0123456789.js"
    said = _with_list(copy, out, _listing(out, drop=(lost,), resize=(bent,), extra=(stray,)))
    sent = _files_named(said)
    assert set(sent) == {lost, bent, stray}, said
    assert sent[stray] is None and os.path.isfile(sent[lost]) and os.path.isfile(sent[bent])
    assert "should hold are not on it" in said
    said = _with_list(copy, out, _listing(out), "--whole")
    assert set(_files_named(said)) == set(held), said
    assert "with no capabilities" in said            # the page keeps its own


def test_the_page_s_ask_for_itself_whole_is_taken_by_its_listener(copy, monkeypatch):
    """The work the page's button writes is a republish the listener takes even when the
    page is current, and is closed with nothing published when the page went up since."""
    import app_listen
    import app_setup
    monkeypatch.setenv("LJS_PROFILE", copy.profile)
    item = {"kind": "republish", "args": {"whole": True}, "status": "queued",
            "asked_at": "2026-11-04T09:00:00Z"}
    db = {"work": {"republish~whole": {"data": item, "version": 3}}}
    monkeypatch.setattr(app_listen, "record", lambda d: ({"chat": "session_L"}, None))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": PAGE, "published_at": "2026-11-04T08:00:00Z"})
    got = app_listen.next_republish(db, "session_L", None)
    assert got["whole"] is True and got["already"] is False, got
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": PAGE, "published_at": "2026-11-04T09:05:00Z"})
    assert app_listen.next_republish(db, "session_L", None)["already"] is True


def test_a_chat_reads_only_small_files_to_publish_a_big_search(copy):
    """X-3: a search with hundreds of contacts made a page of over a megabyte. In parts, the
    page a chat reads is small however big the search, and every code file fits one read."""
    app_state.large(copy.state, tracker_rows=150, contacts=400, threads=600)
    out = os.path.join(copy.root, "built")
    said = copy.run("page", "--out-dir", out, "--now", "2026-10-25T18:00:00Z",
                    "--today", "2026-10-25")
    page = os.path.join(out, "page.html")
    assert os.path.getsize(page) <= app_page.PAGE_MAX, os.path.getsize(page)
    # It says when it was built, so a file missing minutes later reads as an update under way.
    assert 'data-built="2026-10-25T18:00:00Z"' in open(page, encoding="utf-8").read()
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
    # A page published as one file before: its list holds only the page itself.
    first = _with_list(copy, out, '- "index.html"  text/html  900 bytes')
    assert len(_files_named(first)) > 20, first       # never published in parts: every file
    copy.run("published", PAGE, "--parts", out)
    held = _app_json(copy).get("code")
    assert held and all(p.startswith("code/") for p in held)
    # Published without the folder (an older chat's steps), nothing is assumed held.
    copy.run("published", PAGE)
    assert "code" not in _app_json(copy)
    copy.run("published", PAGE, "--parts", out)
    said = copy.run("page", "--out-dir", out, "--url", PAGE)
    # A published page is read and its files listed first; nothing is published before.
    assert "action list, scope files" in said and "Artifact, action publish" not in said, said
    assert f"--url {PAGE} --on-page -" in said, said
    said = _with_list(copy, out, _listing(out))
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
    assert r["parts"]["broken"] is None            # every file arrived: no "did not load fully"
    for sid, text in r["whole"]["sections"].items():
        assert text and r["parts"]["sections"][sid] == text, sid


def _runner():
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
    return proc, Runner(proc)


# The moment the harness opens every page on (tests/app_page/harness.js, `open`), and a page
# built a minute before it (a republish under way) or twenty minutes before (one that stopped).
OPENED = "2026-10-25T09:00:00Z"
MOMENTS_AGO = "2026-10-25T08:59:00Z"
LONG_AGO = "2026-10-25T08:40:00Z"


def _open_broken(tmp_path, how: str, built: str, tap: bool = True, later: int = 0) -> dict:
    """The page in parts built at `built`, opened at OPENED with one code file withheld, a
    stylesheet withheld, or a part that throws ("throws then withheld": a part throws and a
    later one is missing too)."""
    model = json.load(open(FIXTURE, encoding="utf-8"))
    page, files = app_page.render_parts(model, built=built)
    (tmp_path / "parts.html").write_text(app_page.standalone(page), encoding="utf-8")
    for rel, text in files.items():
        p = tmp_path.joinpath(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    js = [p for p in files if p.endswith(".js")]
    css = [p for p in files if p.endswith(".css")]
    if how.startswith("throws"):
        f = tmp_path.joinpath(*js[1].split("/"))
        f.write_text(f.read_text(encoding="utf-8") + "\nthrow new Error(\"a part that throws\");\n", encoding="utf-8")
    if how in ("withheld", "throws then withheld"):
        tmp_path.joinpath(*js[len(js) // 2].split("/")).unlink()
    elif how == "no-style":
        tmp_path.joinpath(*css[-1].split("/")).unlink()
    stored = app_page._from_store()
    seed = {f"view/{k}": {"rev": model["rev"], "made_at": model["made_at"], "data": v}
            for k, v in model.items() if k in stored}
    proc, run = _runner()
    try:
        if not run.first().get("ready"):
            pytest.skip("Chromium would not start")
        return run("broken", parts=str(tmp_path / "parts.html"), seed=seed, tap=tap, clock=OPENED,
                   later=later)
    finally:
        proc.stdin.close()
        proc.wait(timeout=60)


def _asks_for_itself_whole(r: dict, how: str) -> None:
    assert r["box"] and r["box"].startswith("Your page did not load fully."), r
    assert r["button"], r
    assert not r["opening"], r                       # never "Opening your job search…" for ever
    if how != "no-style":
        assert not r["shell"], r                     # nothing half drawn left on show
    assert r["rings"] == [{"text": "[app] [work:republish~whole]", "active": True}], r
    w = r["work"]
    assert w["kind"] == "republish" and w["status"] == "queued" and w["args"]["whole"] is True, w
    if not how.startswith("throws"):
        assert w["args"]["missing"], w
    assert "Claude has been told" in r["note"], r


@pytest.mark.parametrize("how", ["withheld", "no-style"])
def test_a_page_built_moments_ago_with_a_file_still_coming_says_it_is_being_updated(tmp_path, how):
    """A republish goes up in batches, each with the new page.html, so a page opened between
    them finds a code file not there yet. That is an update under way, not a page that
    failed: built minutes ago, it says it is being updated, offers no button and rings
    nothing, and opens itself again until its files are all there."""
    r = _open_broken(tmp_path, how, MOMENTS_AGO, later=46_000)
    assert r["built"] == MOMENTS_AGO, r                # the page carries when it was built
    assert r["box"] == "Your page is being updated. It will be ready in a moment.", r
    assert not r["button"], r
    assert r["rings"] == [] and r["work"] is None, r
    assert not r["opening"], r
    if how != "no-style":
        assert not r["shell"], r
    # 45 seconds on, it has opened itself again, and still waits on its update.
    assert r["reloads"] == 1 and r["later"] == r["box"], r


@pytest.mark.parametrize("how", ["withheld", "throws", "no-style"])
def test_a_page_whose_code_did_not_all_arrive_says_so_and_asks_for_itself_whole(tmp_path, how):
    """A code file still missing, or one that throws, twenty minutes after the page was built
    (no update takes that long): the page never sits blank or half drawn. It says in one line
    that it did not load fully, and its one button writes the request for the whole page and
    then rings Claude, inside the tap."""
    r = _open_broken(tmp_path, how, LONG_AGO)
    assert r["built"] == LONG_AGO, r
    _asks_for_itself_whole(r, how)


@pytest.mark.parametrize("how", ["throws", "throws then withheld"])
def test_a_part_that_throws_is_never_said_to_be_updating(tmp_path, how):
    """A part that arrived and threw is a fault, not an update under way: whatever the build
    moment, the page says at once that it did not load fully, with its button, even when a
    later part is missing too."""
    r = _open_broken(tmp_path, how, MOMENTS_AGO)
    assert r["built"] == MOMENTS_AGO, r
    _asks_for_itself_whole(r, how)
