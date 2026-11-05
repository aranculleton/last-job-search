"""Nothing the person reads on the page mentions chats, helpers or sessions.

The page's answers said "You'll need to make that change in the main chat", "I can't edit the
saved message or change how future replies are written from here", and named the old
"finishing up" helper and "your chat" (the maintainer, 2026-11-05: "YOU'RE NOT MEANT TO USE
THE MAIN CHAT FOR ANYTHING"). Claude's own answers are held by the app skill's rules
(docs/rule_map.json, page-chat-does-it and page-no-chat-words); the words the engine itself
writes onto the page are held here: every receipt's note and refusal (tools/app_actions.py),
every line a work card is given (tools/page_db.py, its *_SAID and *_LINE), and a tweak's
refusal (tools/tweak.py). Each says Claude did it or will, or asks Claude, never a chat.
"""
from __future__ import annotations

import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORDS = re.compile(r"\b(main chat|chats?|helpers?|sessions?|finishing up)\b", re.I)
# Said on the app's own public page, before the person has a copy: a new copy starts with a
# chat of its own, since nothing there answers a page yet.
ALLOWED = {'Open a chat on your new copy and say "set me up". This page carries on there.'}
NOTE_KEYS = ("note", "undo_note")


def _texts(node) -> str:
    """The words a node writes, an f-string's fixed parts joined."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant))
    if isinstance(node, ast.BinOp):
        return _texts(node.left) + _texts(node.right)
    return ""


def _said(path: str, constants=False, summaries=False) -> list[tuple[int, str]]:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", "")
            if name == "Refused" and n.args:
                out.append((n.lineno, _texts(n.args[0])))
            if name == "_receipt" and len(n.args) > 1:
                out.append((n.lineno, _texts(n.args[1])))
        if isinstance(n, ast.Dict):
            pairs = {k.value: v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant)}
            for k in NOTE_KEYS:
                if k in pairs:
                    out.append((n.lineno, _texts(pairs[k])))
            status = pairs.get("status")
            if summaries and "summary" in pairs and isinstance(status, ast.Constant):
                out.append((n.lineno, _texts(pairs["summary"])))
        if isinstance(n, ast.Assign) and len(n.targets) == 1:
            t = n.targets[0]
            if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) \
                    and t.slice.value in NOTE_KEYS:
                out.append((n.lineno, _texts(n.value)))
            if constants and isinstance(t, ast.Name) and re.search(r"_(SAID|LINE)$", t.id):
                out.append((n.lineno, _texts(n.value)))
    return [(ln, s) for ln, s in out if s.strip()]


def _leaks(said):
    return [(ln, s) for ln, s in said if WORDS.search(s) and s not in ALLOWED]


def test_receipts_never_name_a_chat():
    said = _said("tools/app_actions.py")
    assert len(said) > 50, "the scan found too few receipts: has the code moved?"
    assert _leaks(said) == []


def test_a_work_cards_own_lines_never_name_a_chat():
    said = _said("tools/page_db.py", constants=True)
    import sys
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import page_db
    assert (0, page_db.CHAT_STRANDED_SAID) in [(0, s) for _, s in said]
    assert _leaks(said) == []


def test_a_tweaks_answer_never_names_a_chat():
    said = _said("tools/tweak.py", summaries=True)
    assert any("changed since" in s for _, s in said)
    assert _leaks(said) == []


def test_the_scan_catches_what_was_said():
    """The words the page said on 2026-11-05 are caught."""
    for s in ("Only a chat can take this back: say so in a chat.",
              "You'll need to make that change in the main chat.",
              "Your chat writes it in.", "the old helper is finishing up"):
        assert WORDS.search(s), s
