"""A helper that starts its fresh successor hands the page on at once and stops listening.

After its create_session the old helper went on watching and answering until its next
check-in, a whole wake on a nearly full chat, and its own saves' notifications woke it too;
`listen --hand` existed but nothing said to use it (second audit A7). The renewal now says to
hand the page to the new chat with its id as soon as it is made, which stops this chat's watch.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import app_listen  # noqa: E402


def test_the_renewal_hands_the_page_to_the_new_chat():
    line = " ".join(app_listen.renew_line({"title": "Job search page"}).split())
    assert "listen" in line and "--hand <its id>" in line
    assert line.index("create_session") < line.index("--hand")
    assert "on: false" in line
