"""The model guide speaks only when the model is a poor fit, and never guesses a family."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

import model_guide as G  # noqa: E402


def test_a_fitting_model_gets_no_line():
    assert G.advise("apply", "claude-opus-5-5") == ""
    assert G.advise("/scrape", "Sonnet 5.5") == ""


def test_too_little_and_too_much_are_both_said():
    assert "Switch up" in G.advise("interview", "claude-sonnet-5-5")
    assert "saves tokens" in G.advise("threads", "claude-opus-5-5")


def test_a_family_it_does_not_know_is_never_guessed():
    line = G.advise("apply", "claude-newfamily-9")
    assert "does not know" in line


def test_every_command_has_an_entry():
    commands = os.listdir(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       ".claude", "commands"))
    for c in commands:
        name = c[:-3]
        if name in ("setup", "network", "interview", "apply"):
            continue
        G.task_for(name)           # raises KeyError for a command the guide forgot
    for name in ("setup", "network", "interview", "apply", "scrape", "upskill"):
        G.task_for(name)


def test_fable_is_known_and_never_told_it_falls_short():
    assert G.tier_of("claude-fable-5-1") == G.tier_of("Fable 5.1") == "frontier"
    for work in G.TASKS:
        line = G.advise(work, "claude-fable-5-1")
        assert line and "Switch up" not in line, work
    # For the work that wants the strongest model, Opus is never sold as losing nothing.
    assert "loses nothing" not in G.advise("apply", "claude-fable-5-1")
    assert "allowance" in G.advise("apply", "claude-fable-5-1")


def test_the_days_check_says_what_fits_and_what_wants_another():
    sonnet = G.summary("claude-sonnet-5-5")
    assert "right for searches" in sonnet and "applications" in sonnet and "(Opus)" in sonnet
    assert "Sonnet covers searches" in G.summary("claude-opus-5-5")
    assert "more than any of this needs" in G.summary("claude-fable-5-1")
    assert "does not know" in G.summary("claude-newfamily-9")


def test_the_days_sync_carries_the_check(capsys):
    # A line in CLAUDE.md asking for the check was skipped, so the sync every session
    # runs prints it, and says how to get it when it was not given the model.
    import sync_app
    sync_app.model_check("claude-sonnet-5-5")
    assert "Model check (Sonnet)" in capsys.readouterr().out
    sync_app.model_check("")
    assert '--on "<the model' in capsys.readouterr().out


def test_a_chat_started_for_page_work_gets_the_model_that_work_needs():
    """A child chat started for a kind of page work runs on the model the work needs
    (G18): search on a cheaper one, and drafting, the audits and anything a contact reads
    never below the chat that started it (11-cost-model.md: the session's own)."""
    import page_db
    strongest = {"draft", "resume_for_contact", "tweak", "prep", "network", "reply",
                 "follow_up", "brief"}
    for kind in page_db.WORK_KINDS:
        assert kind in G.WORK, kind              # every kind the page queues is placed
    for kind in strongest:
        assert G.TASKS[G.WORK[kind]][0] == "strongest", kind
        for on in ("Fable 5.1", "Opus 5.5", "claude-opus-5-5"):
            assert G.for_work(kind, on)["model"] is None, (kind, on)      # its own
        for on in ("Sonnet 5.5", "Haiku 5.5"):
            assert G.for_work(kind, on)["model"] == "opus", (kind, on)    # up, never down
        assert G.for_work(kind, "")["model"] is None
        assert G.for_work(kind, "Mystery 9")["model"] is None             # never guessed
    assert G.for_work("search", "Opus 5.5")["model"] == "sonnet"
    assert G.for_work("search", "Sonnet 5.5")["model"] is None
    assert G.for_work("search", "Haiku 5.5")["model"] == "sonnet"         # what it needs
    assert G.for_work("listen", "Fable 5.1")["model"] == "sonnet"
