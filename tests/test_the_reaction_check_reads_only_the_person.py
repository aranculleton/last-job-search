"""The reaction check reads the person's own words, compares rules about the same thing, and
takes every group of rules the page shows.

From a real copy, 2026-11-05: the prompt hook held "reads like" as a reaction, and it came
from the page's own text in the wrapper Claude Code puts around a comment from the page; a
rule about how quickly taps are done was said to clash with an older rule about a follow-up's
words, because both used "update"; and `learned.py record --area brief` was refused although
the brief is one of the page's groups of rules. Every person, employer and rule here is
invented.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import learned  # noqa: E402
import person  # noqa: E402

# A comment from the page as Claude Code hands it to the chat: its header in brackets, the
# page's own text the comment was left on, then the doorbell.
WRAPPED = ("[Artifact comment sent to Claude] on Job search page (thread=th_example1)\n"
           "Your note to Juno reads like a first note. Ready to send.\n"
           "[app] [work:talk~1]")


@pytest.fixture
def profile(tmp_path, monkeypatch):
    d = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), d)
    monkeypatch.setenv(person.ENV, str(d))
    person._modules.clear()
    person._data.clear()
    yield d
    person._modules.clear()
    person._data.clear()


def test_the_pages_wrapper_around_a_comment_is_never_the_persons_reaction():
    assert learned.reaction(WRAPPED) == ""
    assert learned.approval(WRAPPED) == ""
    # A message of theirs before it, sent while the chat worked, is still theirs, and only it.
    said = "why does it take so long to mark things\n\n" + WRAPPED
    assert learned.reaction(said) == "so long"
    assert "reads like" not in learned.own_words(said)
    # The wrapper in the middle of their message is taken out with the page's text under it.
    mid = "this is too formal\n" + WRAPPED + "\n\nand keep it short"
    assert learned.own_words(mid).split() == ["this", "is", "too", "formal", "and", "keep", "it",
                                              "short"]


def test_rules_about_different_things_do_not_clash_and_the_check_says_what_it_compared(profile):
    learned.record("messages", "never ask for an update", "Follow-ups never ask them for an update",
                   never_say=["an update"], today="2026-11-01")
    speed = learned.record("other", "why does it take so long",
                           "A tap like applied should update the page in seconds, never minutes",
                           today="2026-11-05")
    assert speed["conflicts"] == []
    # About the same thing, the same words still clash, and the reason quotes what matched.
    same = learned.record("messages", "ask them", "Ask them for an update after two weeks",
                          today="2026-11-05")
    (n, _old, why), = same["conflicts"]
    assert n == 1 and 'never "an update"' in why and '("Ask them for an update' in why


def test_every_group_of_rules_the_page_shows_is_accepted_by_record(profile):
    with open(os.path.join(ROOT, "templates", "app", "app.js"), encoding="utf-8") as fh:
        js = fh.read()
    body = js[js.index("const TWEAK = {"):]
    body = body[:body.index("\n  };\n")]
    groups = re.findall(r"^    ([a-z_]+): \{what:", body, re.M)
    areas = {a for x in re.findall(r"area: \[([^\]]*)\]", body) for a in re.findall(r'"(\w+)"', x)}
    assert set(groups) == set(learned.PAGE_GROUPS) and "brief" in groups
    for word in set(groups) | areas:
        assert learned.area_of(word) in learned.AREAS, word
    # The brief's rules are the ones its panel reads ("other").
    assert learned.area_of("brief") == "other" and "other" in areas
    env = dict(os.environ, **{person.ENV: str(profile)})
    got = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "learned.py"), "record",
                          "--area", "brief", "--said", "only one news item a day",
                          "--rule", "the brief carries one news item a day"],
                         capture_output=True, text=True, encoding="utf-8", env=env)
    assert got.returncode == 0, got.stderr
    assert "learned: other: the brief carries one news item a day" in got.stdout
