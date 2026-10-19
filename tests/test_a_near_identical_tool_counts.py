"""A tool the posting names and the person lacks, beside one they hold that does the same job.

Tableau asked for and Power BI held, Azure asked for and AWS held: in any field the
two are the same work with different menus. Only a person's own BRIDGES said so, so
a field /setup never wrote one for docked the posting in full and the resume showed
neither tool. Now the held one is shown and scored as a near match. The one asked for
is never claimed.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import bridges  # noqa: E402
import fit  # noqa: E402
import skills_block  # noqa: E402


def test_a_held_tool_of_the_same_family_bridges_one_asked_for():
    got = {a.asked: a for a in bridges.assess("Strong Looker skills required.")}
    assert got["Looker"].verdict == bridges.BRIDGE and "Power BI" in got["Looker"].have
    assert bridges.strength_of("Looker") == "near"
    assert "Looker" not in got["Looker"].line and "Power BI" in got["Looker"].line
    # Held already, or nothing held in the family: no bridge is invented.
    assert not [a for a in bridges.family_bridges("Power BI dashboards") if a.asked == "Power BI"]
    assert bridges.family_bridges("Xero and QuickBooks experience") == []


def test_any_family_reads_for_whoever_holds_one_member(monkeypatch):
    monkeypatch.setattr(bridges, "_HELD_RX", [("AWS", re.compile(r"\bAWS\b"))])
    got = bridges.family_bridges("Experience with Azure is essential.")
    assert [(a.asked, a.have) for a in got] == [("Azure", ("AWS",))]


def test_the_score_treats_it_as_near_and_the_resume_shows_the_held_tool():
    assert fit._bridge_multiplier("Strong Looker skills required.") == fit.BRIDGE_MULTIPLIER["near"]
    posting = "You will build Looker dashboards and forecasts in SQL and Python."
    line = skills_block.render("SQL, Python", posting=posting)
    assert "Power BI" in line and "Looker" not in line


def test_a_bridge_is_one_step_and_never_chains(monkeypatch):
    # Only a tool the person really holds bridges, and only within its own family:
    # bridged tools are never treated as held, so nothing spreads from family to family.
    monkeypatch.setattr(bridges, "_HELD_RX", [("AWS", re.compile(r"\bAWS\b"))])
    assert bridges.family_bridges("BigQuery and Snowflake experience required.") == []
    got = bridges.family_bridges("Azure, then BigQuery on top of it.")
    assert [a.asked for a in got] == ["Azure"]
    assert all(set(a.have) <= {"AWS"} for a in got)
