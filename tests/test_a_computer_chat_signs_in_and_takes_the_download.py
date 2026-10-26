"""A chat on the person's computer reads LinkedIn signed in, and takes its download, unasked.

The maintainer, 2026-10-25, of a person's first computer chat: it read LinkedIn signed out
and never said so, so they did not know signing in was there to do or that a signed-out
page shows far less; it never asked for their data download; and getting past its
questions and warnings was convoluted. Now the first page of a reading session is checked
(`signed_in`), a signed-out one is met with two plain lines asking them to sign in once,
reading in the chat's browser needs no question first, and `export.py status` says the next
step for the download from what is recorded. Every person and employer is invented.
"""
from __future__ import annotations

import datetime
import io
import json
import os
import re
import sys
import zipfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network")]

import export  # noqa: E402
import merge_state  # noqa: E402
import profile_upgrades  # noqa: E402
import reading  # noqa: E402

TODAY = datetime.date.today()
BANNED = re.compile(r"\brisk|\brestrict|user agreement|\bterms\b|\bban\b|\bbanned\b|suspend|"
                    r"\bsafe|your call|any time|at your own", re.I)

# A profile as LinkedIn shows it signed out, read by the extractor: the bar says Join now and
# Sign in, and the card and sections come back as if it were whole.
GUEST_EXTRACT = json.dumps({
    "url": "https://www.linkedin.com/in/example-rosalind-achterberg",
    "title": "Rosalind Achterberg - Kestrel Mutual | LinkedIn",
    "nav": "LinkedIn\nArticles\nPeople\nJobs\nJoin now\nSign in",
    "top": "Rosalind Achterberg\nHead of Pricing Analytics at Kestrel Mutual\n"
           "Manchester, England, United Kingdom",
    "sections": [{"heading": "About", "text": "About\nI run pricing analytics for a mutual."},
                 {"heading": "Experience", "text": "Experience\nHead of Pricing Analytics\n"
                                                   "Kestrel Mutual\n2021 - Present"}]})
SIGNED_IN_EXTRACT = json.dumps(dict(json.loads(GUEST_EXTRACT),
                                    nav="Home\nMy Network\nJobs\nMessaging\nNotifications\nMe"))
GUEST_TEXT = ("Rosalind Achterberg\nHead of Pricing Analytics at Kestrel Mutual\n"
              "Sign in to view Rosalind's full profile\nJoin now\nSign in\n")
FEED_SIGNED_IN = "Home\nMy Network\nJobs\nMessaging\nNotifications\nMe\nStart a post\n"

@pytest.fixture(autouse=True)
def _today():
    """TODAY is the day each test runs, not the day this file was loaded: a run that
    crossed midnight compared the one with the other (Windows, 2026-10-26)."""
    global TODAY
    TODAY = datetime.date.today()



def _state(tmp_path, monkeypatch):
    monkeypatch.setattr(reading.person, "state", lambda *p: str(tmp_path.joinpath(*p)))
    monkeypatch.setenv("LJS_LEDGER", str(tmp_path / "ledger"))
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    monkeypatch.setattr(reading, "on_shortlist", lambda cid: True)
    monkeypatch.setattr(reading, "gate_state", lambda *a, **k: {"kind": "go"})


def _read(monkeypatch, text, *extra):
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))
    return reading.main(["read", "kestrel_achterberg", "-", "--source", "browser", "--json",
                         "--name", "Rosalind Achterberg", "--company", "Kestrel Mutual",
                         *extra])


# ------------------------------------------------------------------ signed in or not

def test_signed_in_is_read_off_the_page_and_the_extractors_bar():
    for page in (GUEST_TEXT, GUEST_EXTRACT,
                 "Join LinkedIn\nEmail or phone\nAgree & Join\nAlready on LinkedIn? Sign in\n"):
        assert reading.signed_in(page) is False, page[:40]
    for page in (SIGNED_IN_EXTRACT, FEED_SIGNED_IN):
        assert reading.signed_in(page) is True, page[:40]
    assert reading.signed_in("Rosalind Achterberg\nHead of Pricing Analytics") is None
    assert "out.nav" in reading.EXTRACTOR and "header" in reading.EXTRACTOR


# ------------------------------------------------------------------ the prompt

def test_the_prompt_is_two_plain_lines_with_nothing_but_what_to_do():
    pane, other = reading.signed_out_say("pane"), reading.signed_out_say("chrome")
    for said in (pane, other):
        lines = said.split("\n")
        assert len(lines) == 2 and all(len(ln.split()) <= 40 for ln in lines)
        assert not BANNED.search(said), BANNED.search(said)
        for what in ("full experience", "About", "posts", "who you both know"):
            assert what in lines[0]
        assert "Sign in there once" in lines[1] and lines[1].endswith("say done.")
        assert "?" not in said                         # nothing asked before signing in
    assert "Keep cookies" in pane and "Cmd+Shift+B" in pane and "Ctrl+Shift+B" in pane
    assert "the tab I opened" in other and "Chrome" not in other
    assert reading.SIGNIN_SAY == pane


def test_no_warning_remains_where_a_read_was_asked_for(monkeypatch):
    monkeypatch.setattr(reading, "PROFILE_READS", "browser")
    local = {"CLAUDECODE": "1"}
    for tools in (["browser"], ["chrome"], ["enable"]):
        said = reading.route(tools, None, local)["say"]
        assert not BANNED.search(said) and "?" not in said
    for line in reading.signin_steps():
        assert not BANNED.search(line), line
    u = profile_upgrades.by_id("profile-reads")
    assert not BANNED.search(u.ask) and not BANNED.search(u.steps())
    with open(os.path.join(ROOT, ".claude", "skills", "networking", "SKILL.md"),
              encoding="utf-8") as fh:
        skill = fh.read()
    assert "User Agreement" not in skill and "the risk is to their own account" not in skill
    assert "no warning or disclaimer of Claude's own" in skill
    assert "Never call this route safe" in skill


# ------------------------------------------------------------------ no question first

def test_reading_in_the_chats_browser_needs_no_question_first():
    class Unset:
        pass

    class Paste:
        PROFILE_READS = "paste"
    assert reading.reads_setting(Unset()) == "browser"
    assert reading.reads_setting(None) == "browser"
    assert reading.reads_setting(Paste()) == "paste"
    assert profile_upgrades._profile_reads() == ""
    got = reading.route(["browser"], reading.reads_setting(Unset()), {"CLAUDECODE": "1"})
    assert got["route"] == "browser" and got["usable"]


def test_a_phone_with_no_browser_still_says_its_one_line():
    phone = {"CLAUDE_CODE_REMOTE": "true", "CLAUDE_CODE_ENTRYPOINT": "remote_mobile"}
    said = reading.route([], "browser", phone)["say"]
    assert "screenshots of their profile from the LinkedIn app" in said
    import place
    assert len(said.split()) <= place.SHORT_WORDS


# ------------------------------------------------------------------ the read itself

def test_never_signed_in_asks_and_reads_nothing(tmp_path, monkeypatch, capsys):
    _state(tmp_path, monkeypatch)
    assert _read(monkeypatch, GUEST_EXTRACT) == reading.EXIT["signin"]
    out = capsys.readouterr().out
    assert reading.SIGNED_OUT_LESS in out and "say done" in out
    assert reading.load("kestrel_achterberg") is None and reading.asked_to_sign_in()
    assert not reading.stopped()                       # a prompt, never a stop


def test_a_sign_in_page_after_signing_in_today_is_the_stop_not_the_prompt(
        tmp_path, monkeypatch, capsys):
    _state(tmp_path, monkeypatch)
    reading.mark_signed_in()
    assert _read(monkeypatch, GUEST_EXTRACT) == reading.EXIT["check"]
    out = capsys.readouterr().out
    assert "stopped for today" in out and reading.SIGNED_OUT_LESS not in out


def test_not_today_reads_on_signed_out_marked_partial_and_reads_again_once_signed_in(
        tmp_path, monkeypatch, capsys):
    _state(tmp_path, monkeypatch)
    assert reading.main(["signin", "--not-today"]) == 0
    assert reading.declined_sign_in()
    assert _read(monkeypatch, GUEST_EXTRACT) == 0
    out = capsys.readouterr().out
    assert reading.PARTIAL_LINE in out
    got = reading.load("kestrel_achterberg")
    assert got["signed_out"] is True and not reading.signed_in_today()
    assert reading.fresh(got, signed_in_now=False)     # not again while still signed out
    reading.mark_signed_in()
    assert not reading.fresh(got)                       # signed in: read again, inside the days
    assert _read(monkeypatch, SIGNED_IN_EXTRACT) == 0
    assert "signed_out" not in reading.load("kestrel_achterberg")


def test_the_sign_in_check_says_the_next_step(tmp_path, monkeypatch, capsys):
    _state(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO(GUEST_TEXT))
    assert reading.main(["signin", "--page", "-", "--browser", "chrome"]) == 4
    out = capsys.readouterr().out
    assert "the tab I opened" in out and "--not-today" in out
    monkeypatch.setattr(sys, "stdin", io.StringIO(FEED_SIGNED_IN))
    assert reading.main(["signin", "--page", "-"]) == 0
    assert "signed-in" in capsys.readouterr().out and reading.signed_in_today()


# ------------------------------------------------------------------ the download

def _download(path, when):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Connections.csv", "First Name,Last Name,URL,Company,Position,Connected On\n")
    os.utime(path, (when, when))
    return str(path)


def test_the_download_status_follows_the_record(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "record_path", lambda: str(tmp_path / "linkedin_export.json"))
    monkeypatch.setattr(export, "last_taken", lambda threads=None: (
        export._state().as_date(export.load_record().get("taken_on")), "recorded"))
    got = export.status(TODAY, ["browser"], found=[])
    assert got["state"] == "request" and "none taken yet" in got["line"]
    assert "export.py requested" in got["do"] and "never type it" in got["do"]
    assert "linkedin-export-files" in got["do"]
    asked = export.status(TODAY, [], found=[])
    assert "web search" in asked["do"] and "linkedin.com" in asked["do"]
    export.requested(TODAY)
    got = export.status(TODAY, ["browser"], found=[])
    assert got["state"] == "waiting" and got["requested_on"] == TODAY.isoformat()
    later = (TODAY + datetime.timedelta(days=export.REQUEST_WAIT_DAYS + 1))
    assert export.status(later, ["browser"], found=[])["state"] == "request"
    zip_path = _download(tmp_path / "Basic_LinkedInDataExport.zip",
                         datetime.datetime.combine(TODAY, datetime.time(12)).timestamp())
    got = export.status(TODAY, ["browser"], found=[zip_path])
    assert got["state"] == "take" and got["path"] == zip_path
    assert "export.py take" in got["do"]
    export._record([], TODAY)
    kept = export.load_record()
    assert kept["taken_on"] == TODAY.isoformat() and kept["requested_on"] == TODAY.isoformat()
    got = export.status(TODAY, ["browser"], found=[zip_path])
    assert got["state"] == "fresh" and got["do"] == "nothing"


def test_the_brief_says_a_requested_download_is_on_its_way(tmp_path, monkeypatch):
    monkeypatch.setattr(export, "record_path", lambda: str(tmp_path / "linkedin_export.json"))
    old = TODAY - datetime.timedelta(days=export.EXPORT_EVERY_DAYS + 5)
    monkeypatch.setattr(export, "last_taken", lambda threads=None: (old, "recorded"))
    assert "days old" in export.due(TODAY.isoformat(), threads=[])
    export.requested(TODAY)
    assert "asked for on" in export.due(TODAY.isoformat(), threads=[])


def test_the_record_merges_key_by_key_between_two_chats():
    base = json.dumps({"taken_on": "2026-10-01"})
    ours = json.dumps({"taken_on": "2026-10-01", "requested_on": "2026-10-20"})
    theirs = json.dumps({"taken_on": "2026-10-21", "rows": {"connections": 3}})
    text, problems = merge_state.merge(base, ours, theirs,
                                       "documents/network/linkedin_export.json")
    assert problems == [] and json.loads(text) == {
        "taken_on": "2026-10-21", "requested_on": "2026-10-20", "rows": {"connections": 3}}
    with open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8") as fh:
        assert "documents/network/linkedin_export.json merge=ljs-state" in fh.read()


# ------------------------------------------------------------------ on a new computer

def test_a_new_computer_signs_in_then_takes_the_download_in_that_order(tmp_path, monkeypatch):
    _state(tmp_path, monkeypatch)
    monkeypatch.setattr(export, "status", lambda today=None, tools=(), **k: {
        "state": "request", "line": "request: none taken yet", "do": "ask for it"})
    steps = reading.new_computer(["browser"])
    assert len(steps) == 2 and "signin --page -" in steps[0] and "--browser pane" in steps[0]
    assert "the LinkedIn download" in steps[1]
    reading.mark_signed_in()
    monkeypatch.setattr(export, "status", lambda today=None, tools=(), **k: {
        "state": "fresh", "line": "fresh", "do": "nothing"})
    assert reading.new_computer(["browser"]) == ["nothing to do: carry on"]
    assert "no browser in this chat" in reading.new_computer([])[-1]
    with open(os.path.join(ROOT, ".claude", "skills", "networking", "SKILL.md"),
              encoding="utf-8") as fh:
        assert "## On a new computer" in fh.read()
