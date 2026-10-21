"""A skill the profile already covers under another name is not asked about.

The unheld-skill question asked whether the person could claim "Azure" when their
profile lists Azure Data Factory, and "model deployment" when it lists model serving and
MLflow. A held part covers the whole it belongs to, and a listed synonym covers its
term, so neither is a question now. It only removes questions: what the skills line
prints is unchanged, and a covered skill is never a yes. The profile here is invented.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import bridges  # noqa: E402
import skills_block  # noqa: E402

POSTING = ("You will build pipelines on Azure, own model deployment for our pricing models, "
           "and report from Google Cloud.")


@pytest.fixture
def held(monkeypatch):
    """A profile holding AWS, Azure Data Factory and model serving, whose map bridges
    model deployment rather than holding it, as a real one did."""
    monkeypatch.setattr(bridges, "_HELD_RX", [
        ("AWS (S3, Redshift)", re.compile(r"\bAWS\b|\bS3\b|\bRedshift\b")),
        ("Azure Data Factory", re.compile(r"\bazure data factory\b|\bADF\b", re.I)),
        ("MLflow, model serving", re.compile(r"\bMLflow\b|\bmodel serving\b", re.I)),
    ])
    monkeypatch.setattr(bridges, "_COMPILED", [(
        re.compile(r"\bmlops\b|\bmodel serving\b|\bmodel deployment\b", re.I),
        {"asked": "MLOps or model serving", "verdict": bridges.BRIDGE, "strength": "mid",
         "have": ["platform QA tests"], "line": "", "note": "lead with the platform work"})])


def test_a_held_part_and_a_listed_synonym_are_not_asked_about(held):
    asked = [x["skill"] for x in bridges.unheld_asked(POSTING)]
    assert "Azure" not in asked and "model deployment" not in asked
    # Something the profile does not cover is still asked, beside the tool it sits next to.
    got = {x["skill"]: x for x in bridges.unheld_asked(POSTING)}
    assert got["Google Cloud"]["have"] == ["AWS (S3, Redshift)"]
    assert bridges.covered_by("Microsoft Azure") == ["Azure Data Factory"]
    assert bridges.covered_by("model deployment") == ["MLflow, model serving"]
    assert bridges.covered_by("Azure DevOps") == []


def test_it_never_changes_what_a_document_says(held, monkeypatch):
    before = skills_block.render("SQL, Python", posting=POSTING)
    monkeypatch.setattr(bridges, "_COVERED_RX", [])
    assert skills_block.render("SQL, Python", posting=POSTING) == before
    assert "Azure," not in before and "model deployment" not in before
