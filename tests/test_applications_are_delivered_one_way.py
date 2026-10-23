"""Applications, one or a batch, are delivered one way.

From a person's repo on 2026-10-23: CLAUDE.md said to send each document with the
file-sending tool and paste what they need beside it, but said nothing for a batch, and
one session improvised three layouts (one caption with every link; a table of relative
file links, dead in the desktop app; one message per role). The rule is now one: per
role, one file-sending call with the resume and the letter, captioned role, employer,
pay, location and apply link; then one index table, role | apply link; and the paths as
plain text, never markdown links. Every place that hands over an application says it.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_the_rule_is_written_once_and_every_hand_over_points_at_it():
    rule = _read("CLAUDE.md")
    assert "**Applications, one or a batch, are delivered one way**" in rule
    for words in ("Per role, one file-sending call", "pay (or \"pay not stated\")",
                  "role | apply link", "does not open from the desktop app"):
        assert words in rule, words
    for path in ((".claude", "commands", "apply.md"), ("RUNBOOK.md",),
                 ("automation", "prompts", "job_round.md")):
        text = " ".join(_read(*path).split())
        assert "one index table in the reply, role | apply link" in text, path
        assert "never as markdown links" in text, path


def test_no_hand_over_template_links_a_file_in_the_repo():
    # A markdown link whose target is a path in the repo, the kind that does not open.
    link = re.compile(r"\]\((?:\.?/)?(?:cv|cover_letters|documents)/[^)\s]*\)")
    quoted = re.compile(r"`[^`\n]*`")           # an example of what not to write, quoted
    for path in (("CLAUDE.md",), (".claude", "commands", "apply.md"), ("RUNBOOK.md",),
                 ("automation", "prompts", "job_round.md")):
        assert not link.search(quoted.sub("", _read(*path))), path
