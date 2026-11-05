"""The skills line names each skill once, however the inventory groups it.

Seen on resumes (2026-11-04): "Kubeflow, MLflow, model serving, MLflow", "Apache Spark,
PySpark, Apache Kafka, PySpark", and "pandas, scikit-learn" on both the Languages and the BI
lines. `skills_block._final` skipped a yes only when it equalled a whole inventory item, so
a yes inside a grouped item ("Python, pandas") was printed a second time, beside its
neighbour or at the end of the last line. Recording the yes under the grouped name instead
made the bullet guard refuse every rewording for it, so two drafting chats took the skill
out of the bullets, which breaks the person's rule. Now the block is deduplicated one skill
at a time across every line, and a yes recorded under a grouped name is each of its skills.

The candidate is the example person (profile.example), whose inventory groups "Python,
pandas"; the posting and the employer are invented.
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bullet_rewording  # noqa: E402
import skills_block  # noqa: E402

POSTING = ("Wrenfield Grocers is hiring a Supply Analyst. You will need SQL, Python and pandas, "
           "with Power BI reporting for the stores team.")
TOOLS = "SQL, Python, Power BI"


def _skills(lines) -> list[str]:
    """Every single skill the block prints, in page order: each line's items, split where a
    grouped item joins its skills."""
    return [p.strip() for line in lines for p in re.split(r"[,()]", line.split(": ", 1)[1])
            if p.strip()]


def test_a_yes_inside_a_grouped_item_is_printed_once():
    # "pandas" is in the inventory's "Python, pandas"; the person's yes for it reached the
    # BI line as well: "BI, tooling and delivery: Power BI, pandas".
    lines = skills_block.lines(TOOLS, posting=POSTING, consented=["pandas"])
    printed = [s.casefold() for s in _skills(lines)]
    assert printed.count("pandas") == 1, lines
    assert len(printed) == len(set(printed)), lines
    # Still on the page, where the inventory puts it, and the yes is not lost.
    assert any("Python, pandas" in line for line in lines), lines
    # The LaTeX block too, which is what prints.
    tex = skills_block.render(TOOLS, posting=POSTING, consented=["pandas"])
    assert tex.lower().count("pandas") == 1, tex


def test_a_yes_the_block_does_not_hold_is_still_printed_once():
    lines = skills_block.lines(TOOLS, posting=POSTING + " Looker is a plus.",
                               consented=["Looker", "Looker"])
    printed = [s.casefold() for s in _skills(lines)]
    assert printed.count("looker") == 1, lines


def test_two_grouped_items_never_print_one_skill_twice():
    # Two inventory items sharing a skill, on two lines: the later keeps only what the
    # earlier did not show, and an item left with nothing is dropped.
    sel = {"lang": ["SQL", "Python, pandas, scikit-learn"],
           "bi": ["Power BI", "pandas, scikit-learn", "scikit-learn"]}
    got = skills_block._dedupe(sel, ["lang", "eng", "bi"])
    assert got == {"lang": ["SQL", "Python, pandas, scikit-learn"], "bi": ["Power BI"]}
    # A partial overlap keeps the new part, as the inventory spells it.
    got = skills_block._dedupe({"lang": ["Apache Spark, PySpark"],
                                "eng": ["Apache Kafka, PySpark", "Kubeflow"]},
                               ["lang", "eng"])
    assert got == {"lang": ["Apache Spark, PySpark"], "eng": ["Apache Kafka", "Kubeflow"]}
    # An item that loses nothing is printed exactly as written, its LaTeX included.
    assert skills_block._dedupe({"bi": [r"R\&D reporting"]}, ["bi"]) == {"bi": [r"R\&D reporting"]}


def test_a_yes_recorded_under_a_grouped_name_still_names_its_skill_in_a_bullet():
    # The workaround the guard used to refuse: a yes recorded as "Python, pandas", and a
    # bullet naming pandas beside the Python the work already used.
    text = ("Automated the weekly stock-cover report in Python and pandas, saving the "
            "planning team about four hours a week")
    rw = [{"id": "OF_AUTOMATE", "skill": "Python, pandas", "text": text}]
    assert bullet_rewording.problems(rw, ["Python, pandas"]) == []
    # And the skill field may be the single skill, against a grouped yes.
    assert bullet_rewording.problems([dict(rw[0], skill="pandas")], ["Python, pandas"]) == []
