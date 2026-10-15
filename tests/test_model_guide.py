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
