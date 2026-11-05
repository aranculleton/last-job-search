"""A chat still at work is never put away, and a new page helper starts cleanly.

From the maintainer's live run of 5 November. The daily tidy-up named the person's old helper
for archiving, and its brief to move, though get_session called it running, it was last used
minutes before, it held a branch not on master and two one-time scheduled tasks still fired
into it; its listings, trimmed, kept only status, persistent_session_id and enabled. The
helper's start sent the page refresh to the old `view` collection, and every one of its 43
writes was refused. A brand-new helper was told to hand over twenty minutes in, after reading
the page's code to republish it. Its start said to put the changes and three questions at the
end of the reply, and then that the reply was one line. And the upgrade prompt's `--no <id>`,
printed under the sync's output, read as a flag of sync_app.py. Every id, title and page here
is invented.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import app_listen  # noqa: E402
import app_setup  # noqa: E402
import routines  # noqa: E402
import tidy  # noqa: E402
from test_one_chat_answers_the_page import Copy  # noqa: E402

REPO = "example-owner/example-copy"
LIVE = "session_EXAMPLEPAGEHELPER"
DESK = "session_EXAMPLEDESKHELPER"
BRANCH = "claude/desk-helper-wip"
TODAY = "2026-11-05"                       # plan's clock: noon that day


@pytest.fixture
def copy(tmp_path, monkeypatch):
    c = Copy(tmp_path)
    for k, v in c.env().items():
        monkeypatch.setenv(k, v)
    git = tmp_path / "git"
    git.mkdir()
    monkeypatch.setattr(tidy, "_git_dir", lambda: str(git))
    yield c
    sys.path.remove(c.root)


def _json(tmp_path, name, value):
    p = tmp_path / name
    p.write_text(json.dumps(value), encoding="utf-8")
    return str(p)


# ------------------------------------------------------------------ 1. a chat at work is kept


REG = {"setup": "chat_per_briefing", "timezone": "Europe/London", "routines": [
    {"key": "morning_brief", "name": "Job search: morning brief", "trigger_id": "trig_EXAMPLEBRIEF",
     "cron": "CRON_TZ=Europe/London 38 7 * * *", "prompt_file": routines.BRIEF_FILE,
     "chat": {"session_id": DESK}}]}


def _tidy(copy, tmp_path, monkeypatch, *, listed="idle", told="idle", used="2026-11-01T08:00:00Z",
          once=True, unmerged=(), github=(BRANCH,)):
    """tidy.py plan over trimmed listings, as the live run had them: sessions with their
    status alone, tasks with persistent_session_id and enabled alone."""
    monkeypatch.setattr(tidy, "_listener", lambda d: {"chat": LIVE, "kind": "cloud", "helper": True})
    monkeypatch.setattr(tidy, "_repo", lambda: REPO)
    monkeypatch.setattr(tidy, "_campaign_chats", lambda: set())
    monkeypatch.setattr(tidy, "unmerged", lambda: set(unmerged))
    monkeypatch.setattr(tidy, "on_github", lambda: set(github), raising=False)
    monkeypatch.setattr(routines, "load", lambda *a, **k: json.loads(json.dumps(REG)))
    sessions = {"data": [{"id": LIVE, "title": "Job search page", "status": "idle"},
                         {"id": DESK, "title": "Job search helper", "status": listed}]}
    tasks = [{"id": "trig_EXAMPLEBRIEF", "persistent_session_id": DESK, "enabled": True}]
    if once:
        tasks += [{"id": "trig_EXAMPLEONCE1", "persistent_session_id": DESK, "enabled": True},
                  {"id": "trig_EXAMPLEONCE2", "persistent_session_id": DESK, "enabled": True}]
    detail = {"id": DESK, "title": "Job search helper", "status": told,
              "status_bucket": "working" if told == "running" else "review_ready",
              "updated_at": used, "session_context": {
                  "sources": [{"git_repository": {"url": f"https://github.com/{REPO}"}}],
                  "outcomes": [{"git_repository": {"git_info": {"repo": REPO, "branches": [BRANCH]}}}]}}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert tidy.main(["plan", "--chat", LIVE, "--today", TODAY, "--verbose",
                          "--sessions", _json(tmp_path, "s.json", sessions),
                          "--triggers", _json(tmp_path, "t.json", {"data": tasks}),
                          "--details", _json(tmp_path, "d.json", detail)]) == 0
    return buf.getvalue()


def test_a_helper_still_at_work_is_never_named_for_archiving(copy, tmp_path, monkeypatch):
    """The live run's chat, every sign at once: kept, and its brief stays where it works. Its
    branch was one GitHub did not hold (the work of a chat on the person's computer), so the
    branch check alone, which knew only branches GitHub holds, let it through."""
    said = _tidy(copy, tmp_path, monkeypatch, listed="running", told="running",
                 used="2026-11-05T11:56:00Z", github=())
    assert f"archive {DESK}" not in said and "brief 1:" not in said, said
    assert f"keep {DESK}:" in said


@pytest.mark.parametrize("sign,kw,why", [
    ("two one-time tasks fire into it", {"once": True}, "a scheduled task that is on runs in it"),
    ("the trimmed list says running", {"once": False, "listed": "running"}, "it is running"),
    ("get_session says running", {"once": False, "told": "running"}, "it is running"),
    ("used minutes ago", {"once": False, "used": "2026-11-05T11:56:00Z"}, "in use moments ago"),
    ("its branch is not merged", {"once": False, "unmerged": {BRANCH}}, "not on master yet"),
    ("its branch never reached GitHub", {"once": False, "github": (),
                                         "used": "2026-11-04T20:00:00Z"}, "not on GitHub yet"),
])
def test_each_sign_of_a_chat_at_work_keeps_it_alone(copy, tmp_path, monkeypatch, sign, kw, why):
    said = _tidy(copy, tmp_path, monkeypatch, **kw)
    assert f"archive {DESK}" not in said and "brief 1:" not in said, (sign, said)
    assert why in next(ln for ln in said.splitlines() if ln.startswith(f"keep {DESK}:")), sign


def test_an_old_helper_at_rest_is_put_away_once_the_brief_has_moved(copy, tmp_path, monkeypatch):
    """With every sign at rest it goes, its brief made in the live helper first."""
    said = _tidy(copy, tmp_path, monkeypatch, once=False)
    assert f"archive {DESK}: Job search helper" in said, said
    assert f'"persistent_session_id": "{LIVE}"' in next(
        ln for ln in said.splitlines() if ln.startswith("brief 1:"))


# ------------------------------------------------------------------ 2. the refresh reads screen


def test_the_refresh_reads_screen_and_view_stops_without_it(copy, tmp_path):
    """The start sends the refresh to screen, meta, addr and work; and `view` given a dump with
    no screen documents of a page drawn before writes nothing, saying so in one line."""
    copy.page()
    said = copy.run("start", "--on", "Sonnet 5.5", "--tools", "none", "--chat", "session_EXAMPLEX")
    step = next((ln for ln in said.splitlines() if "ring the page's data up to date" in ln), "")
    assert step and "screen, meta, addr and work" in step and "view and meta" not in step, said
    first = json.loads(copy.run("view", str(tmp_path / "v1"), "--dump", copy.dump("d1"),
                                "--now", "2026-11-05T09:00:00Z", "--chat", LIVE))
    assert first["batches"] and copy.send("\n".join(first["batches"]))
    stale = copy.dump("d2")
    shutil.rmtree(os.path.join(stale, "screen"))       # the live run dumped view and meta
    got = copy.run("view", str(tmp_path / "v2"), "--dump", stale, "--now", "2026-11-05T09:05:00Z",
                   "--chat", LIVE, ok=(2,))
    out = json.loads(got)
    assert out["batches"] == [] and "no dump of the page's screen" in out["for_claude"][0]
    assert not os.path.exists(tmp_path / "v2" / "files")


# ------------------------------------------------------------------ 3. a republish costs no helper


def test_a_republishs_reads_never_renew_the_helper(copy, monkeypatch):
    """What a republish read, from its build to its record, is left out of the growth that
    renews a helper: a new helper with a big republish behind it stays."""
    now = dt.datetime(2026, 11, 5, 9, 20, tzinfo=dt.timezone.utc)
    rec = {"chat": LIVE, "helper": True, "since": "2026-11-05T09:00:00Z"}
    monkeypatch.setattr(app_listen, "chat_kind", lambda: "cloud")
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    size = {"n": 110_000}
    monkeypatch.setattr(app_listen, "context_tokens", lambda: size["n"])
    app_listen.republish_started(LIVE, now)
    size["n"] = 300_000                                  # the page's code, read whole
    assert app_listen.renewal(rec, {"work": {}}, LIVE, now) is None   # while it is going
    app_listen.republish_done(LIVE, now)
    size["n"] = 345_000                                  # and a little real work since
    assert app_listen.renewal(rec, {"work": {}}, LIVE, now) is None
    size["n"] = 460_000                                  # real growth still renews it
    assert app_listen.renewal(rec, {"work": {}}, LIVE, now)["title"] == "Job search page"
    # The record step sets it aside: `app.py published` says the republish is done.
    import app
    called = []
    monkeypatch.setattr(app_listen, "republish_done", lambda c, n: called.append(c))
    copy.page()
    with contextlib.redirect_stdout(io.StringIO()):
        app.main(["published", "https://claude.ai/code/artifact/example-page", "--chat", LIVE])
    assert called == [LIVE]


# ------------------------------------------------------------------ 4. the helper's start


def test_a_new_helpers_start_puts_its_questions_on_the_page_not_in_its_reply(copy):
    """Its last reply is one line, so nothing above it says to end the reply with the changes
    or questions: they go on the page, each question a To do card."""
    copy.page()
    lines = ["app start: set up", "Claude, do this:",
             "1. 2 improvements to their search have waited since 2026-11-04: start them now, "
             "never asking first: one background agent (model sonnet) that follows "
             ".claude/commands/upgrade.md; at the end of your reply give one plain line per "
             "change it made, never a command.",
             "2. If the update check listed questions under \"These need you\" (facts to confirm, "
             "a question an improvement needs), ask at most three, in plain words, at the end of "
             "your reply, as .claude/commands/upgrade.md says: the page asks them too, and an "
             "answer in either place counts."]
    out = "\n".join(app_listen.shape(0, lines, chat="session_EXAMPLENEWHELPER", listen=True,
                                     helper=True))
    assert "ask at most three" not in out and "give one plain line per change" not in out, out
    assert "ask none of them in this chat" in out and "To do card" in out
    last = out.splitlines()[-1]
    assert "Your job search helper is ready" in last and "none is said in this chat" in last
    # A chat the person writes in still asks, at the end of its reply.
    own = "\n".join(app_listen.shape(0, lines, chat="session_EXAMPLEOWN", listen=True))
    assert "ask at most three" in own


# ------------------------------------------------------------------ 5. the whole --no command


def test_the_upgrade_prompt_names_the_whole_no_command():
    import profile_upgrades as P
    ask = P.Upgrade(id="example-ask", added="2026-11-01", gives="a sharper search",
                    pending=lambda: "a question", run="ask", cost="question",
                    needs="person", ask="Shall I widen your search to Leeds?")
    said = P.block([(ask, "a question")])
    assert "`python3 tools/profile_upgrades.py --no <id>` records it" in said, said
    assert "and `--no <id>` records it" not in said


def test_an_archive_refused_is_tried_again_never_handed_to_the_person(copy, tmp_path, monkeypatch):
    """The live helper's archive of the chat it took over from was refused (it was still
    finishing), and it told the person "you can archive it yourself" (the maintainer's live
    run, 2026-11-05). The plan says a refused archive is never mentioned, and from the live
    helper it asks for one check-in that tries again."""
    said = _tidy(copy, tmp_path, monkeypatch, listed="idle", told="idle",
                 used="2026-11-01T08:00:00Z", once=False)
    assert f"archive {DESK}" in said, said
    line = next(ln for ln in said.splitlines() if "refused" in ln)
    assert "never asked of the person" in line and '"delay_minutes": 31' in line, line
