"""An invisible character hides nothing from the checks.

Text copied from a web page, a chat window or a model can carry characters that show
nothing: a zero-width space, a soft hyphen, a byte order mark. `tone._plain()` only
straightened curly quotes, so one of them inside "just checking in" or "leverage", or
inside a name, made the phrase and the name fail to match and the draft went through
the one gate it exists to stop. They are read past now, everywhere a message is checked.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools", "network"))

import advice  # noqa: E402
import compose  # noqa: E402
import tone  # noqa: E402

ZWSP, SHY, BOM = "​", "­", "﻿"


def _rules(found):
    return {v.rule for v in found}


def test_a_check_in_with_a_zero_width_space_in_it_is_still_refused():
    text = f"Hi Riley, just che{ZWSP}cking in on my note. Would you have ten minutes?"
    assert "check_in" in _rules(compose.validate(text, "message", name="Riley Reed"))


def test_a_banned_phrase_split_by_a_soft_hyphen_is_still_found():
    assert "banned_phrase" in _rules(tone.check(f"I hope to lev{SHY}erage my skills here."))


def test_a_name_with_a_hidden_character_is_greeted_whole():
    assert tone.first_name(f"Ri{ZWSP}ley Reed") == "Riley"
    assert tone.first_name(f"{BOM}Riley Reed") == "Riley"


def test_the_length_still_counts_what_the_platform_counts():
    note = "Hi Riley, " + "a" * 285 + " ok?"           # 299 characters
    assert not {"too_long"} & _rules(compose.validate(note, "connection", name="Riley Reed"))
    hidden = note.replace("ok?", f"ok{ZWSP}{ZWSP}?")    # 301 characters as sent
    assert "too_long" in _rules(compose.validate(hidden, "connection", name="Riley Reed"))


def test_a_rewrite_from_offsets_stays_in_place():
    # advice.spoken() replaces spans found in the checked text; with the characters gone
    # from that text but not from the one rewritten, every span would land off by one.
    out = advice.spoken(f"Hi Riley,{ZWSP} I am glad to help.")
    assert ZWSP not in out and out.startswith("Hi Riley, I")
