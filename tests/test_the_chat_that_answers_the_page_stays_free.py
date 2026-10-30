"""The chat that answers the page stays free, and the page says truly what is going on.

From a person's copy, 2026-10-29: a search that was fine showed "Stalled" and blamed the
plan's usage limit; something asked for in a chat never showed on the page; a search and a
networking run held the chat that answers the page for 15 and 23 minutes; and the landing
check held it again for minutes, running the person's own tests twice. Now:

- a running item's progress is pinned with its lease renewed (`app.py pin`), and a search's
  job sites say how far they are and how long is left (`--log`, run_round.py's round.log),
  so the page times it by that and not by the usual minutes;
- a chat says on the page what it is doing for the person (`app.py busy`);
- `next` never hands a big job to the chat that answers the page (start `--work` is the chat
  that runs one: it does that and nothing about the page);
- the landing check runs in the background, runs their own tests once, and the page says
  "Saving your work" meanwhile.

The page's side is in tests/test_the_page_works_in_a_browser.py. Every person, company,
page and chat id is invented.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app  # noqa: E402
import app_model  # noqa: E402
import app_setup  # noqa: E402
import page_db  # noqa: E402
import scrape_wide  # noqa: E402
import tidy  # noqa: E402
from test_a_tick_on_the_page_is_applied_once import APP, NOW, Search, _w  # noqa: E402

PAGE = "https://claude.ai/code/artifact/example-page"
LATER = "2026-10-25T18:12:00Z"


@pytest.fixture
def search(tmp_path):
    return Search(str(tmp_path))


def _app(search, *args):
    """app.py with the search's own state, the whole result: stdout, stderr and exit."""
    env = dict(os.environ, LJS_PROFILE=search.profile, LJS_STATE=search.state,
               LJS_COPY="private")
    for k in ("LJS_TODAY", "LJS_CHAT", "CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID",
              "CLAUDE_CODE_BRIDGE_SESSION_ID"):
        env.pop(k, None)
    return subprocess.run([sys.executable, APP, *args], env=env, capture_output=True,
                          encoding="utf-8", errors="replace", timeout=120)


def _writes(batches):
    """{(collection, doc id): (entry, body)} for every write in the batch files."""
    got = {}
    for path in batches:
        with open(path, encoding="utf-8") as fh:
            for e in json.load(fh):
                body = None
                if e.get("file_path"):
                    with open(e["file_path"], encoding="utf-8") as fh2:
                        body = json.load(fh2)
                got[(e["collection"], e["doc_id"])] = (e, body)
    return got


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _stamp(text, minutes=0):
    import datetime as dt
    return app_model.stamp(app_model.parse_time(text) + dt.timedelta(minutes=minutes))


def _round_log(path):
    """A round.log as run_round.py writes it, from scrape_wide's own progress lines."""
    first = scrape_wide.Tally("Example Jobs", 80)
    first.sent = 40
    early = first.line(left=12 * 60)
    first.sent = 60
    board = scrape_wide.Tally("Example Board", 50)
    board.sent = 10
    finished = scrape_wide.Tally("Fernhill Careers", 32)
    finished.sent = 31
    finished.failure("HTTP 404")
    finished.finished = True
    lines = ["+ python3 tools/scrape_wide.py --out 00_scrape", early,
             first.line(left=10 * 60), board.line(left=3 * 60), finished.line()]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return lines


# ------------------------------------------------------------------ a search says how far it is

def test_a_search_says_how_far_its_job_sites_are_and_how_long_is_left(tmp_path):
    lines = _round_log(str(tmp_path / "round.log"))
    assert lines[2] == "progress: Example Jobs 60/80 sent, 0 failed, 10 min left"
    got = page_db.round_progress("\n".join(lines))
    # Each site's last line counts; a finished one counts whole; the longest time left wins.
    assert got == {"done": 60 + 10 + 32, "total": 80 + 50 + 32, "left_s": 600, "sending": 2}
    assert page_db.round_progress("+ python3 tools/scrape_wide.py") is None
    done = scrape_wide.Tally("Example Board", 50)
    done.sent, done.stopped = 12, "rate-limited"
    assert page_db.round_progress(done.line())["left_s"] == 0


def test_a_pin_moves_the_stage_renews_the_lease_and_keeps_the_time_left(search, tmp_path):
    stages = page_db.progress("search")["stages"]
    search.put("work", "search~1", _w("search", status="running", claimed_by="cloud-1",
                                      stage=1, stage_at="2026-10-25T17:40:00Z",
                                      lease_until="2026-10-25T18:10:00Z", stages=stages,
                                      steps=[{"at": "2026-10-25T17:40:00Z",
                                              "text": "Searching 4 job sites"}]), version=3)
    log = str(tmp_path / "round.log")
    _round_log(log)
    got = json.loads(search.run("pin", search.dump, "--work", "search~1", "--stage", "scrape",
                                "--line", "Searching 4 job sites, 102 of 162 done",
                                "--log", log, "--now", NOW))
    assert got["stage"] == 1 and got["count"] == {"done": 102, "total": 162}
    assert got["left_s"] == 600 and got["stop_asked"] is False
    entry, body = _writes(got["batches"])[("work", "search~1")]
    assert entry["op"] == "update" and entry["if_version"] == 3
    # The same stage: it keeps when it started; the lease is renewed from now.
    assert "stage_at" not in body and body["status"] == "running"
    assert body["lease_until"] == _stamp(NOW, 30)
    assert body["left_s"] == 600 and body["left_at"] == NOW
    assert [s["text"] for s in body["steps"]][-1] == "Searching 4 job sites, 102 of 162 done"
    # The next pin from the same folder is pinned to the version this one makes.
    got = json.loads(search.run("pin", search.dump, "--work", "search~1", "--stage", "read",
                                "--line", "Reading 40 postings", "--now", LATER))
    entry, body = _writes(got["batches"])[("work", "search~1")]
    assert entry["if_version"] == 4
    # A new stage starts its own clock, with no count and no time left of the last one.
    assert body["stage"] == 3 and body["stage_at"] == LATER
    assert body["count"] is None and body["left_s"] is None and body["left_at"] is None
    assert body["lease_until"] == _stamp(LATER, 30)
    with pytest.raises(KeyError):
        page_db.stage_index("search", "polish")


def test_a_pin_after_stop_writes_nothing_and_a_finished_item_is_refused(search):
    search.put("work", "network~1", _w("network", "Kestrel Mutual", status="running",
                                       stop_asked=True), version=2)
    got = json.loads(search.run("pin", search.dump, "--work", "network~1", "--stage", "find",
                                "--now", NOW))
    assert got == {"work": "network~1", "stop_asked": True, "batches": []}
    search.put("work", "network~1", _w("network", "Kestrel Mutual", status="done"), version=3)
    r = _app(search, "pin", search.dump, "--work", "network~1", "--stage", "find",
             "--now", NOW)
    assert r.returncode == 2 and "has finished" in r.stderr and r.stdout == ""
    r = _app(search, "pin", search.dump, "--work", "network~9", "--now", NOW)
    assert r.returncode == 2 and "read work again" in r.stderr


# ------------------------------------------------------------------ work asked for in a chat

def test_a_chat_says_on_the_page_what_it_is_doing_and_when_it_is_done(search):
    search.put("beats", "cloud-1", {"kind": "cloud", "title": "Job search (cloud)",
                                    "seen_at": "2026-10-25T17:00:00Z", "busy": None},
               version=2)
    got = json.loads(search.run("busy", search.dump, "Drafting your reply to Juno",
                                "--chat", "cloud-1", "--kind", "cloud", "--now", NOW))
    assert got["chat"] == "cloud-1" and got["busy"] == "Drafting your reply to Juno"
    entry, body = _writes(got["batches"])[("beats", "cloud-1")]
    assert entry["op"] == "update" and entry["if_version"] == 2
    assert body["busy"] == "Drafting your reply to Juno" and body["seen_at"] == NOW
    got = json.loads(search.run("busy", search.dump, "--done", "--chat", "cloud-1",
                                "--now", LATER))
    entry, body = _writes(got["batches"])[("beats", "cloud-1")]
    assert entry["if_version"] == 3 and body["busy"] is None and got["busy"] is None
    # A chat with no heartbeat yet makes one.
    got = json.loads(search.run("busy", search.dump, "Saving your work", "--chat", "mac-1",
                                "--kind", "computer", "--now", NOW))
    entry, body = _writes(got["batches"])[("beats", "mac-1")]
    assert entry["op"] == "set" and "if_version" not in entry
    assert body["kind"] == "computer" and body["busy"] == "Saving your work"


def test_a_busy_line_is_plain_words_never_a_work_id(search):
    search.put("work", "search~1", _w("search"), version=1)
    for line in ("search~1", "Drafting"):
        r = _app(search, "busy", search.dump, line, "--chat", "cloud-1", "--kind", "cloud",
                 "--now", NOW)
        assert r.returncode == 2 and "a few words" in r.stderr
    r = _app(search, "busy", search.dump, "--chat", "cloud-1", "--now", NOW)
    assert r.returncode == 2 and "say what Claude is doing in a few words, or --done" in r.stderr
    assert page_db.plain_busy("  Saving   your work ") == "Saving your work"
    assert page_db.plain_busy("search~1", page_db.load(search.dump)) is None


def test_a_claim_keeps_the_chats_busy_line_and_never_writes_the_work_id(search):
    search.put("beats", "cloud-1", {"kind": "cloud", "title": "Job search (cloud)",
                                    "seen_at": "2026-10-25T17:00:00Z",
                                    "busy": "Drafting your reply to Juno"}, version=4)
    search.put("work", "talk~1", _w("talk"), version=1)
    out = os.path.join(search.dump, "claim")
    got = json.loads(search.run("next", search.dump, "--chat", "cloud-1", "--kind", "cloud",
                                "--claim-out", out, "--now", NOW))
    assert got["work"] == "talk~1"
    _, beat = _writes(got["batches"])[("beats", "cloud-1")]
    assert beat["busy"] == "Drafting your reply to Juno"
    # A work id left there by an older version is not a line the page shows.
    search.put("beats", "cloud-1", {"kind": "cloud", "title": "Job search (cloud)",
                                    "seen_at": "2026-10-25T17:00:00Z", "busy": "draft~9"},
               version=5)
    got = json.loads(search.run("next", search.dump, "--chat", "cloud-1", "--kind", "cloud",
                                "--claim-out", out, "--now", NOW))
    _, beat = _writes(got["batches"])[("beats", "cloud-1")]
    assert beat["busy"] is None


# ------------------------------------------------------------------ a big job runs elsewhere

def test_a_big_job_is_never_run_by_the_chat_that_answers_the_page(monkeypatch):
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": PAGE})
    heavy = [k for k, v in page_db.WORK_KINDS.items() if v["heavy"]]
    assert set(heavy) >= {"search", "draft", "prep", "network"}
    for kind in heavy:
        chosen = {"work": f"{kind}~1", "kind": kind, "title": "Analyst roles at Kestrel Mutual",
                  "heavy": True, "model": "sonnet",
                  "stages": page_db.progress(kind)["stages"] if kind in page_db.STAGES else []}
        got = app.where_it_runs(chosen, "listener-1", "cloud")
        assert got["run"] == "child session", kind
        call = got["create_session"]
        assert call["title"] == "Job search: Analyst roles at Kestrel Mutual"
        assert tidy.APP_TITLE.match(call["title"])        # the daily tidy archives it
        assert call["source_url"] == "https://github.com/example-owner/example-copy"
        assert call["model"] == "sonnet"
        said = call["prompt"]
        assert f"--work {kind}~1" in said and "app.py pin" in said and PAGE in said
        assert "Never publish, watch or answer the page" in said
        assert "send_message to listener-1" in said
        assert f"\"Finished {kind}~1, on master: bring the page up to date.\"" in said
        assert ("--log" in said) == (kind == "search")
        # Where no chat can be started: a chat on a computer, no create_session, no address.
        for args in ((chosen, "listener-1", "cloud", True), (chosen, "listener-1", "computer")):
            got = app.where_it_runs(*args)
            assert got["run"] == "background agent" and "create_session" not in got
            agent = got["agent"]
            assert agent["run_in_background"] is True and agent["isolation"] == "worktree"
            assert "app.py pin" in agent["prompt"] and "send_message" not in agent["prompt"]
    monkeypatch.setattr(app_setup, "origin", lambda: ("", ""))
    assert app.where_it_runs(chosen, "listener-1", "cloud")["run"] == "background agent"
    long = dict(chosen, title="An analyst role " * 10)
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    title = app.where_it_runs(long, "listener-1", "cloud")["create_session"]["title"]
    assert len(title) <= len("Job search: ") + 60 and tidy.APP_TITLE.match(title)
    assert app.where_it_runs({"work": "talk~1", "kind": "talk", "heavy": False},
                             "listener-1", "cloud") == {"run": "here"}


def test_the_chat_started_for_a_job_does_it_and_nothing_about_the_page(tmp_path):
    from test_one_chat_answers_the_page import Copy, _publish_steps
    copy = Copy(tmp_path)
    try:
        copy.page()
        assert copy.send(copy.run("listen", copy.dump(), "--chat", "big-chat"))
        said = copy.run("start", "--on", "Sonnet 5.5", "--tools", "none", "--chat",
                        "session_EXAMPLEJOB", "--work", "search~1")
        assert "This chat does one job for the page (search~1)" in said
        assert not _publish_steps(said) and "Publishing makes this chat watch" not in said
        assert "create_session" not in said
        assert copy.listener()["chat"] == "big-chat"
    finally:
        sys.path.remove(copy.root)


# ------------------------------------------------------------------ saving never holds the chat

def _floor_leg():
    text = _read("tools/ci_local.sh")
    start = text.index("FLOOR_VERSION=3.9")
    end = text.index('\necho\necho "example templates"', start)
    check = re.search(r"^app_check\(\) \{.*?^\}\n", text, re.S | re.M).group(0)
    return check + text[start:end]


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("quick,data_only,ran,skipped", [
    # --quick: the app's tests on the oldest Python, but never the person's own a second time.
    ("1", "0", ["floor"], ["profile/tests"]),
    ("0", "0", ["floor", "profile/tests"], []),
    # Only their own files changed: with --quick no oldest Python is even looked for.
    ("1", "1", [], ["floor"]),
    ("0", "1", ["profile/tests"], ["floor"]),
])
def test_the_quick_landing_check_runs_their_own_tests_once(tmp_path, quick, data_only, ran,
                                                          skipped):
    # A Python 3.9 and its ready environment that answer everything, so only the leg's own
    # choices are tested; `run` and `skip` say what they were asked to do.
    stubs = tmp_path / "bin"
    venv = tmp_path / "tmp" / "ci_local_py39" / "bin"
    for p in (stubs / "python3.9", venv / "python"):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        p.chmod(0o755)
    (tmp_path / "profile" / "tests").mkdir(parents=True)
    script = 'skip() { echo "SKIP|$1|$2"; }\nrun() { echo "RUN|$1"; }\n' + _floor_leg()
    env = dict(os.environ, PATH=f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}",
               TMPDIR=str(tmp_path / "tmp"), QUICK=quick, DATA_ONLY=data_only,
               APP_RELEASE="0", CHANGED="profile/tests/test_my_rules.py")
    r = subprocess.run(["bash", "-c", script], cwd=str(tmp_path), env=env,
                       capture_output=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    floor = "tests on Python 3.9 (CI's floor leg)"
    names = {"floor": floor, "profile/tests": floor + ", profile/tests"}
    lines = r.stdout.splitlines()
    for key in ran:
        assert f"RUN|{names[key]}" in lines, r.stdout
    for key in skipped:
        assert any(ln.startswith(f"SKIP|{names[key]}|") for ln in lines), r.stdout
    assert len([ln for ln in lines if ln.startswith("RUN|")]) == len(ran), r.stdout
    if quick == "1" and data_only == "0":
        assert f"SKIP|{names['profile/tests']}|--quick: your own tests ran once above" in lines


def test_the_landing_check_runs_in_the_background_and_the_page_says_so():
    runbook = _read("RUNBOOK.md")
    four = runbook[runbook.index("## 4. Record and persist, then land on master"):]
    four = " ".join(four[:four.index("\n## 5.")].split())
    assert "start `./tools/ci_local.sh --quick` in the background (Bash, `run_in_background`)" \
        in four
    assert "\"Saving your work\"" in four
    skill = _read(".claude/skills/app/SKILL.md")
    five = " ".join(skill[skill.index("## 5. Finish in one batch"):].split())
    assert "`busy: \"Saving your work\"` while the landing check below runs" in five
    assert "`./tools/ci_local.sh --quick` in the background (Bash, `run_in_background`)" in five
    assert "python3 tools/app.py busy \"$D\" --done" in five
    import save_state
    assert "in the background" in save_state.LAND and "Saving your work" in save_state.LAND
    usage = " ".join(_read("tools/ci_local.sh").replace("\n#", "\n").split())
    assert "the floor leg's second run of the person's own tests" in usage
    assert "--quick    # skips the LaTeX compile and the second run of your own tests" in \
        _read("MAINTAINING.md")
