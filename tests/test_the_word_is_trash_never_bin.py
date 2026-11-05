"""The word a person reads is trash, never bin (the maintainer, 2026-11-05: "can we refer to
the 'bin' as 'trash' throughout the app in tips and functionality etc? like trash icon not
bin icon, trash it etc"). Every sentence the page and the tips can show is checked; code
names (data-bin, icon("bin")), patterns and file paths are not words a person reads."""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = re.compile(r"\b[Bb]in(?:ned|s|ning)?\b")
# Not sentences: CSS selectors, regular expressions, file paths, shell lines.
NOT_WORDS = re.compile(r"data-bin|\\b|\(\?:|/bin|bin/|\[data-|#!/")


def _sentences(path):
    s = open(os.path.join(ROOT, path), encoding="utf-8").read()
    for q in ('"', "'", "`"):
        for m in re.finditer(q + r"((?:[^" + q + r"\\\n]|\\.)*)" + q, s):
            t = m.group(1)
            if " " in t and BIN.search(t) and not NOT_WORDS.search(t):
                ln = s.count("\n", 0, m.start()) + 1
                line = s.splitlines()[ln - 1].lstrip()
                if line.startswith(("//", "#")):      # a quote inside a comment
                    continue
                yield ln, t


def test_no_sentence_a_person_reads_says_bin():
    found = [f"{p}:{ln}: {t[:90]}" for p in ("templates/app/app.js", "tools/tips.py",
                                              "tools/app_actions.py", "tools/app_model.py")
             for ln, t in _sentences(p)]
    assert not found, "\n".join(found)


def test_the_guides_a_person_reads_say_trash_too():
    """The README still said "the bin" after 4.10.0 (the maintainer, 2026-11-05): the guides a
    person reads say it as the page does, every line but a path or a command."""
    found = []
    for p in ("README.md", "START_HERE.md", "HELP.md"):
        with open(os.path.join(ROOT, p), encoding="utf-8") as fh:
            for ln, line in enumerate(fh, 1):
                if BIN.search(line) and not NOT_WORDS.search(line) and "-bin-" not in line:
                    found.append(f"{p}:{ln}: {line.strip()[:90]}")
    assert not found, "\n".join(found)
