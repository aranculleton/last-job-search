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
# is taken out before the check.
JARGON = re.compile(r"\b(?:proxy|allow-?list(?:ed)?|egress|network polic\w*|domains?|hosts?|"
                    r"CONNECT|403|407|repository|repo|worktree|branch|CLI|config\w*|YAML|"
                    r"environment variables?|connect_rejected)\b", re.I)
BUTTONS = ("Edit cloud environment", "Network access", "Setup script")


def _plain(text: str) -> None:
    said = text
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
    assert "can't reach the job sites (LinkedIn, freehire)" in lines[0]
    assert "Recommended, once:" in said
    assert re.search(r"^1\. .+\n2\. Set Network access to Full", said, re.M)
    # No search runs in its place: a web search there turned up jobs closed for months,
    # shown as leads (2026-10-22).
    assert said.endswith("Say \"done\" once it's changed.")
    assert "won't search" in said
    assert len(said.split()) <= 110


def test_a_round_in_the_cloud_tells_the_person_the_fix_and_off_the_cloud_says_nothing(monkeypatch):
    monkeypatch.setattr(env_check, "blocked_names", lambda: ["LinkedIn"])
    monkeypatch.setattr(scrape_wide, "CLOUD", True)
    said = scrape_wide.blocked_say({"linkedin": "403 Forbidden"})
    assert said.startswith("This chat can't reach the job sites (LinkedIn)")
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
    for line in (place.QUESTION, place.TRADE_OFF, place.RECOMMEND, place.TWO_CHATS):
        _plain(line)


def test_the_steps_a_beginner_follows_are_numbered_and_plain():
    for eid in ("cloud-internet", "cloud-setup-script", "clone-copy", "local-chat"):
        steps = claude_surfaces.entry(eid)["steps"]
        assert 2 <= len(steps) <= 4, eid
        for s in steps:
            _plain(s)
            assert len(s.split()) <= 30, (eid, s)


def test_start_here_recommends_one_fix_for_the_cloud_and_one_way_onto_a_computer():
    text = open(os.path.join(ROOT, "START_HERE.md"), encoding="utf-8").read()
    cloud = text.split("Go to [claude.ai/code]", 1)[1].split("## 4.", 1)[0]
    local = text.split("## On your own computer", 1)[1].split("**On a phone, or in a browser,**")[0]
    for part in (cloud, local):
        assert "recommended" in part.lower()
        for word in ("proxy", "egress", "allowlist", "Allowed domains", "worktree"):
            assert word not in part, word
    assert "Network access to Full" in cloud and "Install GitHub Desktop" in local


def test_every_upgrade_says_what_it_gives_and_asks_in_plain_words(monkeypatch):
    import person
    monkeypatch.setenv(person.ENV, os.path.join(ROOT, "profile.example"))
    import profile_upgrades
    for u in profile_upgrades.REGISTRY:
        for field in ("gives", "ask", "why_ask"):
            if getattr(u, field, ""):
                _plain(getattr(u, field))
