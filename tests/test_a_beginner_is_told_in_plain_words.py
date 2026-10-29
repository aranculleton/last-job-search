"""What a person new to all of this is told, said in plain words, with one recommendation.

From a real repo (2026-10-20): a cloud chat said the job boards were "blocked from this
environment again", and a person who had only ever used the cloud was told to "edit the
environment" and add hosts to "Allowed domains". They had never heard of an environment.
Every message here says what happened, recommends one fix as numbered steps, and stays
short; the only technical word allowed is a button's own name, quoted from the screen.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools")]

import claude_surfaces  # noqa: E402
import env_check  # noqa: E402
import place  # noqa: E402
import scrape_wide  # noqa: E402

# Words a beginner cannot act on. "Edit cloud environment" is the button's own name, so it
# is taken out before the check. CONNECT is the proxy's word in capitals; "connect GitHub"
# is the screen's own.
JARGON = re.compile(r"\b(?:proxy|allow-?list(?:ed)?|egress|network polic\w*|domains?|hosts?|"
                    r"(?-i:CONNECT)|403|407|repository|repo|worktree|branch|CLI|config\w*|YAML|"
                    r"environment variables?|connect_rejected)\b", re.I)
BUTTONS = ("Edit cloud environment", "Network access", "Setup script", "Create a new repository",
           "Create repository from template", "Create repository", "Only select repositories",
           "Change repository visibility", "Make this repository private")


def _plain(text: str) -> None:
    said = " ".join(text.split())
    for b in BUTTONS:
        said = said.replace(b, "")
    said = re.sub(r"https?://\S+", "", said)
    assert not JARGON.search(said), JARGON.search(said).group(0)
    assert "environment" not in said.lower(), said
    assert "—" not in text


def test_a_cloud_chat_that_cannot_reach_job_sites_says_why_and_one_fix_in_steps():
    said = env_check.blocked_say(["LinkedIn", "freehire"])
    _plain(said)
    lines = said.splitlines()
    assert lines[0] == "This chat can't reach job sites yet (LinkedIn, freehire). To let it, once:"
    assert re.search(r"^1\. .+\n2\. Set Network access to Full", said, re.M)
    # No search runs in its place: a web search there turned up jobs closed for months,
    # shown as leads (2026-10-22).
    assert said.endswith("Say \"done\" once it's changed.")
    assert "won't search" in said
    # 107 words said "done" twice and promised to "search again" before any search (2026-10-25).
    assert said.count("done") == 1 and "search again" not in said
    assert len(said.split()) <= 70


def test_a_round_in_the_cloud_tells_the_person_the_fix_and_off_the_cloud_says_nothing(monkeypatch):
    monkeypatch.setattr(env_check, "blocked_names", lambda: ["LinkedIn"])
    monkeypatch.setattr(scrape_wide, "CLOUD", True)
    said = scrape_wide.blocked_say({"linkedin": "403 Forbidden"})
    assert said.startswith("This chat can't reach job sites yet (LinkedIn)")
    monkeypatch.setattr(scrape_wide, "CLOUD", False)
    assert scrape_wide.blocked_say({"linkedin": "403 Forbidden"}) == ""
    monkeypatch.setattr(scrape_wide, "CLOUD", True)
    monkeypatch.setattr(env_check, "blocked_names", lambda: [])
    assert scrape_wide.blocked_say({"linkedin": "403 Forbidden"}) == ""   # refused elsewhere


def test_the_environment_check_names_no_proxy_and_ends_with_the_fix(monkeypatch, capsys):
    monkeypatch.setattr(env_check, "CLOUD", True)
    monkeypatch.setattr(env_check, "probe", lambda url: ("blocked", "blocked by this chat's "
                                                         "cloud settings (proxy 403): the fix "
                                                         "is below"))
    env_check.main([])
    out = capsys.readouterr().out
    assert "Tell the person, in these words, once:" in out
    _plain(out.split("Tell the person, in these words, once:", 1)[1])


def test_every_message_the_place_check_says_unasked_is_plain():
    for name in dir(place):
        if name.startswith("SHORT_") and isinstance(getattr(place, name), str):
            _plain(getattr(place, name))
    _plain(place.CHATS)


def test_what_a_person_hears_about_their_page_after_an_update_is_one_short_sentence():
    """A chat that took an update (2026-10-26) asked whether to bring the page up, explained
    a safety check, offered the pin again, set up a helper in two sentences and reported a
    timer running out. Each of these is all the person hears about one of those, said whole."""
    import app_listen
    for line in (app_listen.SAY_UPDATED, app_listen.SAY_UPDATING, app_listen.SAY_NOT_UPDATED):
        _plain(line)
        assert line.endswith(".") and line.count(". ") == 0 and "?" not in line, line
        assert len(line.split()) <= 15, line
        for word in ("listener", "republish", "safety", "timer", "update check", "pin"):
            assert word not in line.lower(), (word, line)


def test_the_steps_a_beginner_follows_are_numbered_and_plain():
    for eid in ("cloud-internet", "cloud-setup-script", "make-copy", "connect-github",
                "make-private", "local-chat", "routines-cloud"):
        steps = claude_surfaces.entry(eid)["steps"]
        assert 2 <= len(steps) <= 4, eid
        for s in steps:
            _plain(s)
            assert len(s.split()) <= 30, (eid, s)


def _read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def _prose(text):
    """What a reader sees: comments, links' addresses and code spans left out."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return re.sub(r"`[^`]*`", "", text)


def test_start_here_recommends_one_fix_for_the_cloud_and_one_way_onto_a_computer():
    text = _read("START_HERE.md")
    cloud = text.split("## 3. Say \"set me up\"", 1)[1].split("## On your computer", 1)[0]
    local = text.split("## On your computer", 1)[1].split("## Then use your page", 1)[0]
    for part in (cloud, local):
        assert "recommended" in part.lower()
        for word in ("proxy", "egress", "allowlist", "Allowed domains", "worktree"):
            assert word not in part, word
    assert "Network access to Full" in cloud and "COMPUTER.md" in local
    assert "GitHub Desktop" not in text and "Terminal" not in text


def test_the_pages_a_beginner_reads_first_are_short_and_plain():
    """The README's start, START_HERE and HELP are the first things a person reads: 1,870
    words, a repeated question and GitHub Desktop were in the way (2026-10-25)."""
    readme = _read("README.md")
    at = readme.index("## Get started")
    start = readme[at:readme.index("\n## ", at)]                    # to the next section
    assert len(_prose(start).split()) <= 100
    for rel, cap in (("START_HERE.md", 600), ("HELP.md", 400)):
        said = _prose(_read(rel))
        assert len(said.split()) <= cap, (rel, len(said.split()))
    for said in (start, _read("START_HERE.md"), _read("HELP.md")):
        _plain(_prose(said).replace("repositories", "").replace("GitHub App", ""))
        assert "claude.ai/connect-github" not in said and "fifteen minutes" not in said
        assert "GitHub Desktop" not in said


def test_what_setup_says_to_the_person_is_plain_and_short():
    """The lines /setup gives the person in quotes, word for word."""
    setup = _read(".claude/commands/setup.md")
    quoted = ["\n".join(ln[2:] for ln in block.splitlines())
              for block in re.findall(r"(?:^> .*\n?)+", setup, re.M)]
    assert quoted
    first = quoted[0]
    assert len(first.split()) <= 60 and "documents/" not in first
    assert "attach" in first.lower() and "paste" in first.lower()
    for said in quoted:
        _plain(said.replace("<employer>", "").replace("<country>", ""))
    four = next(q for q in quoted if q.startswith("Thanks."))
    assert len(re.findall(r"^\d\. ", four, re.M)) == 4
    # Where they will work is never asked (the maintainer, 2026-10-29: no question with a
    # clear default): setup says so, and the place tool has no question to hand over.
    assert "is never asked" in setup and not hasattr(place, "QUESTION")


def test_the_brief_is_made_with_nothing_for_the_person_to_type():
    import routines
    readme = _read("automation/README.md")
    # The bell does it; without a page, four words in the chat they already use.
    paste = re.search(r'\*\*"(set up my brief)"\*\*', readme)
    assert paste and "Press the bell on your Brief" in readme
    said = routines.default("Europe/London")["say"]
    _plain(said)
    assert said.startswith("Your brief is on: every day at 7:38")
    for line in claude_surfaces.steps("routines-cloud"):
        _plain(line)


def test_every_upgrade_says_what_it_gives_and_asks_in_plain_words(monkeypatch):
    import person
    monkeypatch.setenv(person.ENV, os.path.join(ROOT, "profile.example"))
    import profile_upgrades
    for u in profile_upgrades.REGISTRY:
        for field in ("gives", "ask", "why_ask"):
            if getattr(u, field, ""):
                _plain(getattr(u, field))


def test_blocked_job_sites_are_checked_by_every_chat_in_the_cloud(sync_steps):
    """Each cloud chat runs on its own computer with its own settings, so a chat opened on a
    day already checked is checked too, not only the day's first."""
    for stale in (False, True):
        rc, steps = sync_steps("--if-stale", stale=stale)
        assert rc == 0 and "network_check" in steps, (stale, steps)
