"""In the maintainer's own copy, every chat the page's helper starts attaches the app too.

Issue 318: each new page helper in the maintainer's copy started with only that copy attached,
so it could not file an app bug by itself (tools/app_bug.py) until the maintainer granted the
app again in that chat, and a grant made in one helper died with it. Issue 245 gave the weekly
builder's chat the app; now the helper's hand-over, the chats it starts for big jobs and Chat
questions, and the chat that starts chats on the computer attach it first as well, in the
maintainer's copy only (`sync_app.maintainers()`). create_session takes one source, the copy
the chat works on, so the chat attaches the app itself (add_repo), as the builder's chat
attaches the copy. Anyone else's copy never gets the app: filing app bugs by itself is the
maintainer's alone. Every id and page here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import pytest  # noqa: E402

import app  # noqa: E402
import app_listen  # noqa: E402
import app_setup  # noqa: E402
import computer  # noqa: E402
import sync_app  # noqa: E402

PAGE = "https://claude.ai/code/artifact/example-page"
LIVE = "session_EXAMPLEPAGEHELPER"
COPY = "https://github.com/example-owner/example-copy"
ATTACH = "add_repo, owner aranculleton, repo last-job-search, access push"


def _calls(monkeypatch, capsys, tmp_path) -> dict:
    """Each create_session the page's helper makes, as the commands give it."""
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": PAGE})
    out = {
        "job": app.where_it_runs({"heavy": True, "kind": "search", "title": "Find jobs",
                                  "work": "search~1", "stages": []}, LIVE, "cloud"),
        "question": app.where_it_runs({"kind": "talk", "work": "talk~1",
                                       "title": "Is my letter ok?"}, LIVE, "cloud",
                                      question=True),
    }
    out = {k: v["create_session"] for k, v in out.items()}
    out["starter"] = computer.starter_call(PAGE, "example-owner/example-copy", "example-owner",
                                           "example-copy")
    out["renewal"] = app_listen.helper_call({}, "example-owner", "example-copy")
    # The hand-over the person asks for, as `app.py hand-over` prints it.
    meta = tmp_path / "d" / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "listen.json").write_text(json.dumps({"chat": LIVE, "helper": True, "_v": 3}),
                                      encoding="utf-8")
    assert app.main(["hand-over", "--chat", LIVE, "--dump", str(tmp_path / "d")]) == 0
    said = capsys.readouterr().out
    line = next(ln for ln in said.splitlines() if ln.startswith("1. create_session "))
    out["hand-over"] = json.JSONDecoder().raw_decode(line, len("1. create_session "))[0]
    return out


def test_in_the_maintainers_copy_every_chat_the_helper_starts_attaches_the_app(
        monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sync_app, "maintainers", lambda: True)
    for name, call in _calls(monkeypatch, capsys, tmp_path).items():
        assert ATTACH in call["prompt"], (name, call["prompt"])
        # Still started on the copy it works on, in Auto, with its own first line first.
        assert call["source_url"] == COPY and call["permission_mode"] == "auto", (name, call)
        assert call["prompt"].index(ATTACH) > call["prompt"].index("\n"), (name, call["prompt"])
    assert app_listen.WAKE_PROMPT in _calls(monkeypatch, capsys, tmp_path)["hand-over"]["prompt"]


def test_anyone_elses_copy_never_gets_the_app_attached(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sync_app, "maintainers", lambda: False)
    for name, call in _calls(monkeypatch, capsys, tmp_path).items():
        assert "add_repo" not in call["prompt"] and "last-job-search" not in call["prompt"], \
            (name, call["prompt"])
        assert call["source_url"] == COPY, (name, call)


@pytest.mark.parametrize("mine", [True, False])
def test_a_chat_on_the_computer_is_never_asked_to_attach_it(monkeypatch, mine):
    """It has no GitHub tools at all, and keeps what it finds for the next cloud chat
    (`app_bug.py --hold`)."""
    monkeypatch.setattr(sync_app, "maintainers", lambda: mine)
    monkeypatch.setattr(app_setup, "origin", lambda: ("example-owner", "example-copy"))
    monkeypatch.setattr(app_setup, "page_record", lambda: {"url": PAGE})
    got = app.where_it_runs({"heavy": True, "kind": "search", "title": "Find jobs",
                             "work": "search~1", "stages": []}, LIVE, "computer")
    assert got["run"] == "background agent" and "add_repo" not in got["agent"]["prompt"]


@pytest.mark.parametrize("first", ["app", "copy"])
def test_a_chat_with_the_app_attached_beside_the_copy_is_judged_on_the_copy(first):
    """With the app attached as well, a chat lists two sources: the tidy-up and the brief's
    adoption judge it by the copy it works on, whichever is listed first, never as a chat on
    another copy kept for good."""
    import datetime as dt
    import routines
    import tidy
    repo = "example-owner/example-copy"
    srcs = [{"git_repository": {"url": f"https://github.com/{app_setup.APP_REPO}"}},
            {"git_repository": {"url": COPY}}]
    d = {"id": "session_EXAMPLEOLDHELPER", "title": "Last Job Search · Page", "status": "idle",
         "updated_at": "2026-11-09T08:00:00Z",
         "session_context": {"sources": srcs if first == "app" else srcs[::-1], "outcomes": []}}
    now = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.timezone.utc)
    assert tidy.retire(d["id"], d, repo, set(), now, set()) == ("archive", d["title"])
    assert routines._copy_of(d) == repo
