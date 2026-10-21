"""The compiled resume's text layer must say, in order, what its draft put on the page.

Every check of a rendered resume asked whether its text layer was readable; none asked
whether it said what the draft said. An unescaped % ate the rest of a bullet, a glyph the
font lacks dropped a letter, a swallowed brace lost a skills line, and the PDF was one
page that extracted cleanly. `verify_pdf.py --roundtrip` now checks each line the draft
put on the page (contacts, headings, the summary, each role's heading line and bullets,
each skills line, education, certifications) against the text layer, allowing for
hyphenation and spacing, and names the line that is missing or out of order.
verify_batch.sh runs it on every resume.

The application is invented; the candidate is the example person.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import verify_pdf as V  # noqa: E402

DRAFT = {"company": "Wrenfield Freight Ltd", "role": "Supply Chain Analyst",
         "posting": "Supply Chain Analyst. Strong SQL and Python; Power BI a plus.",
         "summary": "Operations analyst with seven years turning warehouse, transport and "
                    "supplier data into forecasts. Most recently cut forecast error from 22% to "
                    "14% across 2,400 SKUs at Brindle & Hart Logistics, working in Python, SQL "
                    "and dbt with reporting in Power BI.",
         "tools": "Python, SQL, dbt, Power BI, Tableau",
         "jobs": [{"employer": "Brindle & Hart Logistics",
                   "bullets": ["BH_FORECAST", "BH_ROUTING", "BH_PIPE"]},
                  {"employer": "Oakmere Foods", "bullets": ["OF_WASTE", "OF_SUPPLIER"]},
                  {"employer": "Saltmarsh Analytics", "bullets": ["SALT_FORECAST"]}],
         "p1": "At Brindle & Hart I forecast by depot.", "p2": "Wrenfield moves goods.",
         "lead": "Where I would start:",
         "cl_bullets": [{"label": "Forecasting", "text": "Weekly models by depot."}],
         "p4": "I am in Manchester."}


def _page(groups):
    """A text layer as a reader returns one: every line in order, hyphenated across lines
    the way LaTeX breaks them, with layout spacing."""
    out = []
    for _label, fields in groups:
        for _what, text in fields:
            out.append(text.replace("forecasting", "fore-\ncasting").replace(", ", " ,  "))
    return "\n".join(out)


def test_every_line_of_the_draft_is_read_in_page_order():
    groups = V.roundtrip_fields(DRAFT)
    labels = [label for label, _f in groups]
    assert labels[:4] == ["Contact details", "the heading Profile", "Profile (the summary)",
                          "the heading Professional Experience"]
    assert "Brindle & Hart Logistics, bullet 1" in labels and "Skills, line 1" in labels
    assert labels.index("Oakmere Foods, its heading line") > labels.index(
        "Brindle & Hart Logistics, bullet 3")
    contact = dict(groups[0][1])
    assert contact["your email"] == "morgan.ellis@example.com"
    bullet = dict(groups[labels.index("Brindle & Hart Logistics, bullet 1")][1])["bullet"]
    assert "22% to 14%" in bullet and "£1.1M" in bullet and "\\" not in bullet
    assert V.roundtrip(groups, _page(groups)) == []


def test_a_line_cut_short_is_named_with_where_it_stops():
    groups = V.roundtrip_fields(DRAFT)
    # What an unescaped % does: the rest of the line is a comment, never printed.
    page = _page(groups).replace("22% to 14% and freeing an estimated £1.1M of safety stock",
                                 "22")
    [why] = V.roundtrip(groups, page)
    assert why.startswith('missing: Brindle & Hart Logistics, bullet 1 ("Built weekly demand-')
    assert why.endswith('the text layer has it only as far as "distribution centres, cutting '
                        'forecast error from"')


def test_a_dropped_glyph_is_a_missing_line():
    groups = V.roundtrip_fields(DRAFT)
    [why] = V.roundtrip(groups, _page(groups).replace("£1.1M", "1.1M"))
    assert "Brindle & Hart Logistics, bullet 1" in why


def test_a_line_out_of_order_is_named():
    groups = V.roundtrip_fields(DRAFT)
    lines = _page(groups).split("\n")
    i = next(n for n, ln in enumerate(lines) if ln.startswith("Modelled shelf-life"))
    j = next(n for n, ln in enumerate(lines) if ln.startswith("Segmented 140"))
    lines[i], lines[j] = lines[j], lines[i]
    [why] = V.roundtrip(groups, "\n".join(lines))
    # Bullet 1 is found where it now sits, after bullet 2, so bullet 2 is the one out of place.
    assert why.startswith('out of order: Oakmere Foods, bullet 2 ("Segmented 140 suppliers')
    assert why.endswith("comes before Oakmere Foods, bullet 1")


def test_a_page_break_inside_a_line_is_not_a_loss():
    groups = V.roundtrip_fields(DRAFT)
    page = _page(groups).replace("cost to serve,", "cost\nMorgan Ellis  Page 1/2\nto serve,")
    assert V.roundtrip(groups, page) == []


def test_a_line_that_is_not_there_at_all_says_so():
    groups = V.roundtrip_fields(DRAFT)
    page = "\n".join(ln for ln in _page(groups).split("\n") if not ln.startswith("Delivered"))
    [why] = V.roundtrip(groups, page)
    assert why.startswith("missing: Saltmarsh Analytics, bullet 1")
    assert why.endswith("it is not in the text layer at all")


# ------------------------------------------------------------------ with LaTeX

needs_latex = pytest.mark.skipif(not (shutil.which("lualatex") and shutil.which("pdftotext")),
                                 reason="lualatex and Poppler are not installed here")


@needs_latex
def test_a_real_render_passes_and_a_swallowed_percent_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import fit_to_page as F
    import render_application as R
    (tmp_path / "cv").mkdir()
    a = json.loads(json.dumps(DRAFT))
    R.resume(R.build(a))
    tex, pdf = docpaths.resume_tex(a["abbr"]), docpaths.resume_pdf(a["abbr"])
    drafts = tmp_path / "drafts.json"
    drafts.write_text(json.dumps([a]), encoding="utf-8")

    def run():
        F._compile("lualatex", os.path.basename(tex), os.path.dirname(tex), pdf)
        return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "verify_pdf.py"),
                               pdf, "--roundtrip", str(drafts), "--abbr", a["abbr"]],
                              capture_output=True, text=True, env=dict(os.environ))
    ok = run()
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "lines the draft put on the page are in the text layer, in order" in ok.stdout
    with open(tex, encoding="utf-8") as fh:
        body = fh.read()
    with open(tex, "w", encoding="utf-8") as fh:
        fh.write(body.replace("from 22\\% to 14\\% and freeing",
                              "from 22% to 14\\% and freeing", 1))
    bad = run()
    assert bad.returncode == 1
    assert "missing: Brindle & Hart Logistics, bullet 1" in bad.stdout
    assert 'only as far as "distribution centres, cutting forecast error from"' in bad.stdout

