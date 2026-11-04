"""A page owed is published in the chat the person is in, and they are told once what it is.

A stranger's chat printed "page to publish" and went on with what she asked; nothing held it,
nothing told her a page existed, and one chat that could not publish turned the page off for
every chat of the copy for a month (the chat-only review, S1; the stranger audit, X-21,
X-25). Now the app's one hook holds a turn the person opened while this chat owes the page,
at most three times a chat a day, with this chat's own way out; the first publish says one
plain line with the link; a page published before without a word is introduced once. Every
person, page and chat id here is invented.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tests")]

import pytest  # noqa: E402

import learned  # noqa: E402
import person  # noqa: E402
from test_one_chat_answers_the_page import Copy, PAGE  # noqa: E402


@pytest.fixture
def copy(tmp_path, monkeypatch):
    c = Copy(tmp_path)
    for k, v in c.env(LJS_CHAT="session_EXAMPLECHAT1").items():
        monkeypatch.setenv(k, v)
    for k in ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        monkeypatch.delenv(k, raising=False)
    person._modules.clear()
    person._data.clear()
    yield c
    person._modules.clear()
    person._data.clear()
    sys.path.remove(c.root)


def _transcript(tmp_path, *said, origin="human"):
    lines = []
    for text in said:
        entry = {"type": "user", "message": {"role": "user", "content": text}}
        if origin != "human":
            entry["origin"] = {"kind": origin}
        lines += [entry,
                  {"type": "assistant", "message": {"role": "assistant", "stop_reason": "tool_use",
                   "content": [{"type": "tool_use", "name": "Bash",
                                "input": {"command": "python3 tools/app.py start"}}]}},
                  {"type": "user", "message": {"role": "user", "content": [
                      {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}}]
    path = tmp_path / "t.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return str(path)


def _stop(path):
    return learned.hook({"hook_event_name": "Stop", "transcript_path": path,
                         "stop_hook_active": False})


def test_a_turn_the_person_opened_is_held_while_this_chat_owes_the_page(copy, tmp_path):
    """S1: no page yet, the person asked for something: the turn is held, three times a day
    in this chat, then let go; the prompt hook says it beside their message too."""
    path = _transcript(tmp_path, "can you find me some jobs?")
    held = [_stop(path) for _ in range(5)]
    assert [h.get("decision") for h in held] == ["block"] * 3 + [None, None], held
    assert "python3 tools/app.py start" in held[0]["reason"]
    assert "published none --why" in held[0]["reason"]
    assert learned._page_due({"hook_event_name": "UserPromptSubmit",
                              "prompt": "can you find me some jobs?"})


def test_a_published_page_or_this_chats_no_ends_the_hold(copy, tmp_path):
    path = _transcript(tmp_path, "hi")
    copy.run("published", "none", "--why", "no Artifact tool in this chat",
             LJS_CHAT="session_EXAMPLECHAT1")
    assert _stop(path) == {}                     # this chat said it cannot publish
    # Another chat of the same copy still owes it: the no was this chat's alone (X-21).
    os.environ["LJS_CHAT"] = "session_EXAMPLECHAT2"
    assert _stop(path).get("decision") == "block"
    # Its start still prints the publish steps, and no copy-wide record was written.
    said = copy.run("start", "--on", "m", "--tools", "none", LJS_CHAT="session_EXAMPLECHAT2")
    assert "Build the person's page" in said, said
    assert "none" not in json.load(open(os.path.join(copy.profile, "app.json"))) \
        if os.path.exists(os.path.join(copy.profile, "app.json")) else True
    copy.run("published", PAGE, LJS_CHAT="session_EXAMPLECHAT2")
    assert _stop(path) == {}


def test_nobody_there_or_nothing_sure_holds_nothing(copy, tmp_path):
    """A scheduled run, a ring or a job chat has nobody to tell; a record left mid-merge is
    never read as a page never made; a count that cannot be kept never holds every turn."""
    assert _stop(_transcript(tmp_path, "<task-notification>scheduled</task-notification>",
                             origin="task-notification")) == {}
    assert _stop(_transcript(tmp_path, "Scheduled run: morning brief. python3 tools/brief.py")) == {}
    assert _stop(_transcript(tmp_path, "Do one piece of work: python3 tools/app.py start --work "
                                       "work~apply-7")) == {}
    with open(os.path.join(copy.profile, "app.json"), "w", encoding="utf-8") as fh:
        fh.write('<<<<<<< HEAD\n{"url": "%s"}\n=======\n{}\n>>>>>>> origin/master\n' % PAGE)
    assert _stop(_transcript(tmp_path, "hi")) == {}
    os.remove(os.path.join(copy.profile, "app.json"))
    # Another chat is setting them up: that chat publishes, never this one (the chat-only
    # review: a chat told "start nothing" was then held to publish a second page).
    import app_setup
    with open(os.path.join(copy.profile, "place.json"), "w", encoding="utf-8") as fh:
        json.dump({"setup": {"started": "2026-11-03", "chat": "session_OTHERSETUP"}}, fh)
    assert app_setup.page_owed("session_EXAMPLECHAT1") == ""
    assert _stop(_transcript(tmp_path, "hi")) == {}
    os.remove(os.path.join(copy.profile, "place.json"))
    # The count's file cannot be written: no hold at all.
    held = os.path.join(copy.state, ".ljs-page-held.json")
    if os.path.exists(held):
        os.remove(held)
    os.makedirs(held)
    assert _stop(_transcript(tmp_path, "hi")) == {}


def test_the_first_page_is_named_once_in_one_plain_line(copy):
    """X-25: the first publish of a set-up search says what the page is, with its link, once,
    before the pin; a page published before without a word is introduced once by start."""
    said = copy.run("published", PAGE)
    intro = [ln for ln in said.splitlines() if "has its own page now" in ln]
    assert len(intro) == 1 and PAGE in intro[0], said
    line = intro[0].split("\"")[1]
    assert len(line) <= 200
    assert said.index("has its own page now") < said.index("pin")
    assert "has its own page now" not in copy.run("published", PAGE)
    # A copy whose page went up silently before this version: start says it once.
    rec = json.load(open(os.path.join(copy.profile, "app.json")))
    rec.pop("introduced")
    json.dump(rec, open(os.path.join(copy.profile, "app.json"), "w"))
    copy.page(current=True)
    said = copy.run("start", "--on", "m", "--tools", "none")
    assert "has its own page now" in said, said
    assert "has its own page now" not in copy.run("start", "--on", "m", "--tools", "none")
    # During setup its own line says it ("Your setup is on your page"): never a second line
    # that also says "nothing more" (the chat-only review).
    os.remove(os.path.join(copy.profile, "app.json"))
    os.remove(os.path.join(copy.profile, "person.json"))
    assert "has its own page now" not in copy.run("published", PAGE)


def test_a_copy_wide_no_from_an_older_version_hides_the_page_from_no_chat(copy):
    """X-21's repair: an older version wrote `none` into profile/app.json for the whole copy.
    It is another chat's word: every chat publishes again, and the first publish drops it."""
    with open(os.path.join(copy.profile, "app.json"), "w", encoding="utf-8") as fh:
        json.dump({"none": "2026-11-03"}, fh)
    said = copy.run("start", "--on", "m", "--tools", "none", LJS_CHAT="session_EXAMPLECHAT3")
    assert "Build the person's page" in said and "page to publish" in said.splitlines()[0], said
    copy.run("published", PAGE, LJS_CHAT="session_EXAMPLECHAT3")
    assert "none" not in json.load(open(os.path.join(copy.profile, "app.json"), encoding="utf-8"))


def test_start_says_page_to_publish_only_beside_the_steps(copy):
    """X-21: with this chat unable to publish, start never heads its steps "page to publish"
    and never says the page shows anything."""
    copy.run("published", "none", "--why", "no Artifact tool")
    said = copy.run("start", "--on", "m", "--tools", "none")
    head = said.splitlines()[0]
    assert "page to publish" not in head and "Build the person's page" not in said, said
    assert "The page shows the updates" not in said
    # And a chat that can publish is told what to do if it turns out it cannot.
    said = copy.run("start", "--on", "m", "--tools", "none", LJS_CHAT="session_EXAMPLECHAT9")
    assert "page to publish" in said.splitlines()[0] and "published none --why" in said, said


def test_a_dead_page_is_put_up_afresh_and_its_new_address_said_once(copy):
    """X-44: a page that cannot be published to any more is replaced: the steps say how, and
    `published` with the new address claims the new page and says the new link once."""
    copy.page(current=False)
    said = copy.run("start", "--on", "m", "--tools", "none")
    assert "not there or not this person's" in said and "no --url" in said, said
    new = "https://claude.ai/code/artifact/example-page-two"
    said = copy.run("published", new, LJS_CHAT="session_EXAMPLECHAT1")
    assert f"Your page has a new address: {new}" in said
    assert "listener now" in said                  # the new page's store is claimed afresh


def test_the_job_sites_card_names_no_chat_that_does_not_exist(copy, monkeypatch):
    """X-49: on the default network, the page's To do sent a new person to "your helper chat
    (Job search helper)", which no chat of theirs was called, and said "This chat" on a page.
    Every chat of theirs shares the setting, so any of them will do."""
    import app_setup
    monkeypatch.setattr(app_setup, "job_sites", lambda: {"blocked": ["LinkedIn", "freehire"],
                                                         "checked": "2026-11-03"})
    items = app_setup.outside_items({}, {"kind": "private", "owner": "o", "name": "n"})
    card = next(i for i in items if i["about"]["step"] == "job-sites")
    text = json.dumps(card)
    assert "Job search helper" not in text and "helper chat" not in text
    assert not card["body"].startswith("This chat")
    assert "any of your chats" in " ".join(card["steps"] + card["more"]["steps"])


def test_work_asked_for_in_the_chat_is_given_in_the_chat():
    """X-12: with a page, a shortlist, an application, an interview pack or a call prep asked
    for in the chat came back as one pointer line, and the chat then asked her to choose from a
    table it never showed. Asked in a chat, the chat gets it in full too, and the page as well."""
    def text(rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return " ".join(fh.read().split())
    assert "asked in a chat, the chat gets it in full too" in text("CLAUDE.md")
    assert "one line says what is new and where" not in text("CLAUDE.md")
    for rel in (".claude/skills/job-scraper/SKILL.md", ".claude/commands/apply.md",
                ".claude/commands/interview.md", ".claude/commands/prep.md"):
        assert "sked in the chat, or where there is no page" in text(rel), rel


def test_setup_answers_given_in_the_chat_are_kept_as_the_pages_are(copy):
    """X-58: with a page, setup was told to read answers only from the page, so someone who
    typed their answers or pasted their resume in the chat was never set up. Now an answer
    given in the chat is kept exactly as the page keeps one, and start says how."""
    import app_setup
    copy.run("answer", "work", "--field", "work=Operations analyst", "--field", "place=Leeds")
    copy.run("answer", "resume", "--text", "Operations analyst, 2019 to now, Kestrel Mutual.")
    got = app_setup.answers()
    assert got["work"]["work"] == "Operations analyst" and got["work"]["place"] == "Leeds"
    assert got["resume"]["source"] == "pasted"
    with open(person.state(got["resume"]["file"]), encoding="utf-8") as fh:
        assert "Kestrel Mutual" in fh.read()
    # A copy part-way through setup is told how to keep them.
    os.remove(os.path.join(copy.profile, "person.json"))
    said = copy.run("start", "--on", "m", "--tools", "none")
    assert "python3 tools/app.py answer <step>" in said, said


def test_a_page_another_chat_published_is_taken_never_made_twice(copy, tmp_path, monkeypatch):
    """X-57: a second chat opened during setup, before the first chat's work landed, saw no
    page and published another. A page on any branch of the copy is taken whole instead, the
    one published last winning, as a merge keeps it: a branch left days ago holds an older,
    abandoned page, never the one in use."""
    import subprocess
    import app_setup
    import place
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "master", str(repo)], check=True)
    (repo / "profile").mkdir()
    first = {"url": "https://claude.ai/code/artifact/example-first", "published_at": "2026-11-03T09:00:00Z"}
    second = {"url": "https://claude.ai/code/artifact/example-second", "published_at": "2026-11-03T10:00:00Z"}
    git = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c",  # noqa: E731
                                     "user.email=t@example.com", *a], check=True, capture_output=True)
    (repo / "README").write_text("x")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("update-ref", "refs/remotes/origin/master", "HEAD")
    for name, rec in (("claude/chat-two", second), ("claude/chat-one", first)):
        git("checkout", "-qb", name, "master")
        (repo / "profile").mkdir(exist_ok=True)
        (repo / "profile" / "app.json").write_text(json.dumps(rec))
        git("add", "-A")
        git("commit", "-qm", name)
        git("update-ref", f"refs/remotes/origin/{name}", "HEAD")
    git("checkout", "-q", "master")
    monkeypatch.setattr(place, "ROOT", str(repo))
    monkeypatch.setattr(app_setup, "ROOT", str(repo))
    monkeypatch.setenv(person.ENV, str(repo / "profile"))
    assert app_setup.adopt_page_elsewhere() is True
    assert app_setup.page_record()["url"] == second["url"]


def _versioned(path, version):
    rows = [json.loads(x) for x in open(path, encoding="utf-8").read().splitlines() if x]
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            if version:
                r["version"] = version
            fh.write(json.dumps(r) + "\n")
    return path


def test_the_hold_takes_the_form_the_chats_claude_code_honours(copy, tmp_path):
    """Ported from the chat-only branch's third round: Stop's own feedback keeps a turn going
    only from Claude Code 2.1.163, shown to the person as no error; an older one ignores it
    and lets the turn end, so there, and where no version is known, the hold is a block."""
    import app_setup
    for version, form in (("2.1.317", "hookSpecificOutput"), ("2.1.163", "hookSpecificOutput"),
                          ("2.1.162", "decision"), ("", "decision")):
        held = os.path.join(copy.state, "." + learned.PAGE_HELD)
        if os.path.exists(held):
            os.remove(held)                                  # a fresh day's holds
        out = _stop(_versioned(_transcript(tmp_path, "find me jobs"), version))
        assert form in out, (version, out)
        assert "never been published" in json.dumps(out)
    assert app_setup.page_owed("session_EXAMPLECHAT1") == "new"


def test_a_page_whose_record_was_lost_overnight_is_never_made_twice(copy, tmp_path):
    """Ported from the chat-only branch's third round: the chat published, never saved the
    record, and its computer was replaced overnight. The next day it was held to publish a
    second page, with the first-page line and the pin question again. Its own transcript,
    which comes back with the chat, holds the address: it is kept again, never made twice."""
    import app_listen
    import app_setup
    first = "https://claude.ai/code/artifact/example-page-first"
    lines = [{"type": "user", "message": {"role": "user", "content": "find me jobs"}},
             {"type": "assistant", "message": {"role": "assistant", "stop_reason": "tool_use",
              "content": [{"type": "tool_use", "name": "Bash", "input": {
                  "command": f"python3 tools/app.py published {first} --parts /tmp/x/page"}}]}},
             {"type": "user", "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}},
             {"type": "assistant", "message": {"role": "assistant", "stop_reason": "end_turn",
              "content": [{"type": "text", "text": "Here are five roles."}]}},
             {"type": "user", "message": {"role": "user", "content": "morning"}}]
    path = tmp_path / "lost.jsonl"
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    assert app_setup.page_owed("session_EXAMPLECHAT1") == "new"    # the record went
    said = learned._page_due({"hook_event_name": "UserPromptSubmit", "prompt": "morning",
                              "transcript_path": str(path)})
    assert said == learned.PAGE_HEALED
    assert app_setup.page_record()["url"] == first and app_listen.pin_asked()
    assert _stop(str(path)) == {}
    said = copy.run("published", first, LJS_CHAT="session_EXAMPLECHAT1")
    assert "has its own page now" not in said and "pin" not in said.lower()


def test_no_page_tool_quietly_replaces_a_name_it_defined():
    """The class the chat-only branch's third round found (a second `_OPENS` in learned.py): a
    module-level name bound twice replaces the first for every use above it too. app_model's
    second `_ISO_DAY` meant a contact's next step never read a date in words."""
    import ast
    import app_model
    for mod in ("learned", "app_model", "app_listen", "app_setup", "app_page", "app"):
        with open(os.path.join(ROOT, "tools", mod + ".py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        seen = set()
        for node in tree.body:
            names = [t.id for t in getattr(node, "targets", []) if isinstance(t, ast.Name)]
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                names = [node.name]
            for n in names:
                assert n not in seen, f"{mod}.{n} is bound twice"
                seen.add(n)
    assert app_model.plain_action("Call them on 2026-10-29") == "Call them on Thu 29 Oct"
