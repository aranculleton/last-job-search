"""A two-page resume does not end on a near-empty page, nor a page on a lone heading.

`documents.resume_pages: 2` lets a resume run to a second page, and the design check
read each page alone: its size, its sizes, its edges, its column. Two failures across the
break passed every check and the page count. A second page holding a few lines reads as an
unfinished document, and a section heading at the foot of page 1 with its content on page 2
reads as a heading with nothing under it. Adapted from ai-job-search's verify_layout.py
(#378), measured here from pypdf's positions like the rest of the design check, and only
where two pages are allowed: a one-page resume has neither. The documents are invented.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "templates"))

import design_check  # noqa: E402

needs_tex = pytest.mark.skipif(not shutil.which("lualatex") or not importlib.util.find_spec("pypdf"),
                               reason="lualatex or pypdf is not installed")
TOOL = os.path.join(ROOT, "tools", "design_check.py")


def _job(i, n):
    return {"dates": f"{2010 + i}--{2011 + i}", "title": f"Planning Analyst {i}",
            "employer": f"Kestrel Mutual {i}", "loc": "Leeds",
            "bullets": [f"Built weekly demand forecasts in Python and SQL for {k + 3} depots, "
                        f"cutting stock-outs by {k + 5}% across the north over two years."
                        for k in range(n)]}


def _resume(abbr, bullets, break_before=None):
    """The app's own resume template (templates/resume_gen.py), compiled as the app does.
    `break_before` names a section heading ("education") to start on a new page."""
    import fit_to_page
    import person
    import resume_gen
    for d in ("cv", "cover_letters"):
        os.makedirs(person.state(d), exist_ok=True)
    tex = resume_gen.resume({"abbr": abbr, "company": "Kestrel Mutual", "role": "Analyst",
                             "summary": "Analyst who builds forecasts for operations teams.",
                             "skills": "Python, SQL, dbt, Airflow",
                             "jobs": [_job(i, n) for i, n in enumerate(bullets)]})
    if break_before:
        head = "\\section{%s}" % resume_gen._tex(resume_gen._H[break_before])
        with open(tex, encoding="utf-8") as fh:
            body = fh.read()
        assert body.count(head) == 1, head
        with open(tex, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body.replace(head, "\\newpage\n" + head))
    pages = fit_to_page.compile_resume(abbr, passes=2)
    return pages, fit_to_page.resume_pdf(abbr)


def _near_the_foot(abbr, section, room):
    """The app's own resume with `section`'s heading set where only `room` lines are left on
    the page: a filler from where the page stands now to that point, so it is the same on
    every TeX install. Anything the template keeps before the heading stays after the filler."""
    import fit_to_page
    import person
    import resume_gen
    for d in ("cv", "cover_letters"):
        os.makedirs(person.state(d), exist_ok=True)
    tex = resume_gen.resume({"abbr": abbr, "company": "Kestrel Mutual", "role": "Analyst",
                             "summary": "Analyst who builds forecasts for operations teams.",
                             "skills": "Python, SQL, dbt, Airflow",
                             "jobs": [_job(i, 4) for i in range(3)]})
    with open(tex, encoding="utf-8") as fh:
        body = fh.read()
    head = "\\section{%s}" % resume_gen._tex(resume_gen._H[section])
    at = re.search(r"(?:\\needspace\{[^}]*\}\s*)?" + re.escape(head), body)
    filler = ("\\par\\vspace*{\\dimexpr\\pagegoal-\\pagetotal-%d\\baselineskip\\relax}\n" % room)
    with open(tex, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body[:at.start()] + filler + body[at.start():])
    pages = fit_to_page.compile_resume(abbr, passes=2)
    return pages, fit_to_page.resume_pdf(abbr)


@needs_tex
def test_a_section_heading_never_stays_behind_at_the_foot_of_a_page():
    """The template kept each role's heading with its bullets (\\needspace before each
    entry) and had nothing before a section's heading: with seven lines left, the Experience
    heading fitted, its first role did not, and the heading sat alone at the foot of page 1
    (it did from five lines left to eight). Each section now asks for room for its heading
    and what starts under it."""
    pages, pdf = _near_the_foot("Foot", "experience", room=7)
    assert pages == 2
    assert not any(f.startswith("HEADING_AT_FOOT") for f in design_check.layout(pdf, pages=2)), \
        design_check.layout(pdf, pages=2)


@needs_tex
def test_a_line_low_on_the_first_page_is_read_as_a_line_not_as_the_page_number():
    """The template lets page 1 run three lines lower than the rest (\\enlargethispage), so
    its last lines can sit under the 45pt the check set aside for the page number. They
    were left out: a heading above them read as alone at the foot, and page 1 counted short.
    Only what is printed at the same height on every page there is the page number."""
    pages, pdf = _near_the_foot("Low", "skills", room=5)
    assert pages == 2
    by = design_check.printed_lines(design_check.runs(pdf))
    lowest = min(y for y, _size in by[0])
    assert lowest < design_check.FOOT_BAND_PT, "the skills line no longer sits in the band"
    assert not any(f.startswith("HEADING_AT_FOOT") for f in design_check.layout(pdf, pages=2))
    # The page number itself is still never a line.
    footer = [y for p, t, _x, y, _s in design_check.runs(pdf)
              if y < design_check.FOOT_BAND_PT and p == 1 and str(t).strip()]
    assert footer and all(abs(y - f) > 1 for f in footer for y, _s in by[1])


def _thin(abbr):
    """Two pages, the second holding only what the page break put there: three roles on
    page 1, the education (and any certifications) on page 2. Where the class breaks a page
    on its own is no part of it, so it is the same on every TeX install: moderncv 2.3.1 sets
    about 43 lines on page 1 and 2.6.1 about 55, so seven roles were two pages on one and
    one page on the other (Windows CI, 2026-11-11)."""
    return _resume(abbr, [4, 4, 4], break_before="education")


def _article(folder, stem, body):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, stem + ".tex"), "w", encoding="utf-8") as fh:
        fh.write("\\documentclass[11pt,a4paper]{article}\n\\usepackage[margin=25mm]{geometry}\n"
                 f"\\pagestyle{{empty}}\n\\begin{{document}}\n{body}\n\\end{{document}}\n")
    subprocess.run(["lualatex", "-interaction=nonstopmode", stem + ".tex"], cwd=folder,
                   capture_output=True, timeout=300)
    return os.path.join(folder, stem + ".pdf")


LINE = "Built weekly demand forecasts in Python and SQL for the depots across the north."


@needs_tex
def test_a_second_page_of_a_few_lines_is_found():
    pages, pdf = _thin("Thin")
    assert pages == 2
    found = design_check.layout(pdf, pages=2)
    assert len(found) == 1 and found[0].startswith("THIN_LAST_PAGE"), found
    # The rules a parser needs are a different question, and this resume passes them.
    assert design_check.check(pdf, pages=2) == []
    # Where one page is all the profile allows, the page count says it, not this.
    assert design_check.layout(pdf, pages=1) == []
    # What the fit estimates its cut from: the last page's lines, and a full line's width.
    import fit_to_page
    lines, width = fit_to_page._thin_lines("Thin")
    assert lines == 4 and width > 40
    assert fit_to_page._bullet_lines("no such bullet", width) == 1


@needs_tex
def test_a_second_page_with_its_share_passes():
    pages, pdf = _resume("Full", [4] * 12)
    assert pages == 2
    assert design_check.layout(pdf, pages=2) == []


@needs_tex
def test_a_heading_left_at_the_foot_of_a_page_is_found(tmp_path):
    lines = "\n\n".join(LINE for _ in range(40))
    stranded = _article(str(tmp_path), "stranded",
                        f"\\section*{{Experience}}\n{lines}\n\n\\section*{{Education}}\n"
                        f"\\newpage\nBSc Economics, University of Leeds.\n\n{lines[:2000]}")
    found = design_check.layout(stranded, pages=2)
    assert any(f.startswith("HEADING_AT_FOOT: page 1") for f in found), found
    kept = _article(str(tmp_path), "kept",
                    f"\\section*{{Experience}}\n{lines}\n\n\\newpage\\section*{{Education}}\n"
                    f"BSc Economics, University of Leeds.\n\n{lines[:2000]}")
    assert not any(f.startswith("HEADING_AT_FOOT") for f in design_check.layout(kept, pages=2))


@needs_tex
def test_the_command_says_it_apart_from_a_parsers_rules(tmp_path):
    _pages, pdf = _thin("Thin2")
    profile = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), profile)
    p = profile / "person.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["documents"]["resume_pages"] = 2
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run([sys.executable, TOOL, pdf], capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       env=dict(os.environ, LJS_PROFILE=str(profile)))
    assert r.returncode == design_check.EXIT_LAYOUT, r.stdout + r.stderr
    assert "THIN_LAST_PAGE" in r.stdout


def test_verify_batch_and_the_page_say_it_in_its_own_words():
    import app_model
    src = open(os.path.join(ROOT, "tools", "verify_batch.py"), encoding="utf-8").read()
    assert "LAYOUT_RESUME" in src
    assert "nearly empty" in app_model.VERIFY_WORDS["LAYOUT_RESUME"]


def _fitting(monkeypatch, tmp_path, thin, fits_at, lines=0, jobs=(("a1", "a2", "a3"), ("b1", "b2"))):
    """fit_to_page with its compiles counted: a trim takes one bullet, a compile is one page
    while the resume holds `fits_at` bullets or fewer, and the last page holds `lines`
    lines. Each compile writes its bullet count into the PDF, so what is on disk can be
    told."""
    import fit_to_page
    a = {"abbr": "Thin", "jobs": [{"bullets": list(j)} for j in jobs]}
    pdf = tmp_path / "Thin.pdf"
    pdf.write_bytes(b"as it was")
    renders, sources = [], []

    def trim(d):
        for j in reversed(d["jobs"]):
            if len(j["bullets"]) > 1:
                j["bullets"] = j["bullets"][:-1]
                return True
        return False

    def render(d):
        n = sum(len(j["bullets"]) for j in d["jobs"])
        renders.append(n)
        pdf.write_bytes(b"%d bullets" % n)
        return 1 if n <= fits_at else 2
    monkeypatch.setattr(fit_to_page, "_thin_end", lambda abbr: thin)
    monkeypatch.setattr(fit_to_page, "_thin_lines", lambda abbr: (lines, 80), raising=False)
    monkeypatch.setattr(fit_to_page, "trim_resume", trim)
    monkeypatch.setattr(fit_to_page, "_render_resume", render)
    monkeypatch.setattr(fit_to_page, "_too_close", lambda abbr: False)
    monkeypatch.setattr(fit_to_page, "resume_pdf", lambda abbr: str(pdf))
    monkeypatch.setattr(fit_to_page.R, "build", lambda d: d)
    monkeypatch.setattr(fit_to_page.R, "resume", lambda d: sources.append(
        sum(len(j["bullets"]) for j in d["jobs"])))
    return fit_to_page, a, renders, pdf, sources


def test_the_fit_puts_a_thin_last_page_back_on_one_page_fewer(monkeypatch, tmp_path):
    fit_to_page, a, renders, pdf, sources = _fitting(monkeypatch, tmp_path, thin=True, fits_at=3)
    a["thin_end"] = fit_to_page.THIN_KEPT          # an earlier fit's, now out of date
    trimmed = set()
    assert fit_to_page.settle_thin_end(a, 2, trimmed) == 1
    assert "thin_end" not in a
    assert a["jobs"][1]["bullets"] == ["b1"] and a["jobs"][0]["bullets"] == ["a1", "a2"]
    assert trimmed == {"b2", "a3"}
    # The fewest bullets that reach a page fewer, with that resume's PDF and source on disk.
    assert pdf.read_bytes() == b"3 bullets" and sources[-1:] in ([3], [])


def test_where_the_floors_keep_two_pages_every_bullet_goes_back(monkeypatch, tmp_path):
    fit_to_page, a, renders, pdf, _sources = _fitting(monkeypatch, tmp_path, thin=True, fits_at=0)
    assert fit_to_page.settle_thin_end(a, 2, set()) == 2
    assert a["jobs"][0]["bullets"] == ["a1", "a2", "a3"] and a["jobs"][1]["bullets"] == ["b1", "b2"]
    # And the draft says so, for the check to read.
    assert a["thin_end"] == fit_to_page.THIN_KEPT
    assert pdf.read_bytes() == b"as it was"


def test_the_cut_is_estimated_from_the_last_pages_lines_not_found_a_compile_at_a_time(
        monkeypatch, tmp_path):
    """It compiled after every bullet, up to twelve times and once more to put them back:
    minutes a resume on a Windows computer. The trim's steps are worked out first, and the
    first compile is where they add up to the last page's lines."""
    jobs = (tuple(f"a{i}" for i in range(8)), tuple(f"b{i}" for i in range(7)))
    fit_to_page, a, renders, pdf, _s = _fitting(monkeypatch, tmp_path, thin=True, fits_at=9,
                                                lines=6, jobs=jobs)
    trimmed = set()
    assert fit_to_page.settle_thin_end(a, 2, trimmed) == 1
    assert len(trimmed) == 6 and renders == [9, 10]          # it was six compiles
    assert pdf.read_bytes() == b"9 bullets"


def test_where_nothing_can_be_taken_back_it_costs_one_compile(monkeypatch, tmp_path):
    jobs = (tuple(f"a{i}" for i in range(8)), tuple(f"b{i}" for i in range(7)))
    fit_to_page, a, renders, pdf, _s = _fitting(monkeypatch, tmp_path, thin=True, fits_at=0,
                                                lines=40, jobs=jobs)
    assert fit_to_page.settle_thin_end(a, 2, set()) == 2
    assert renders == [3]                                  # it was thirteen
    assert a["thin_end"] == fit_to_page.THIN_KEPT and pdf.read_bytes() == b"as it was"
    assert sum(len(j["bullets"]) for j in a["jobs"]) == 15


def test_a_full_last_page_or_one_page_is_left_alone(monkeypatch, tmp_path):
    fit_to_page, a, renders, _pdf, _s = _fitting(monkeypatch, tmp_path, thin=False, fits_at=0)
    assert fit_to_page.settle_thin_end(a, 2, set()) == 2
    assert fit_to_page.settle_thin_end(a, 1, set()) == 1
    assert a["jobs"][0]["bullets"] == ["a1", "a2", "a3"] and renders == []


THIN = ("Morgan_Ellis_Thin_CV.pdf: body 10.0pt, smallest 10.0pt\n"
        "  THIN_LAST_PAGE: page 2 holds 4 lines against 27 on page 1, which reads as unfinished\n")
FOOT = "  HEADING_AT_FOOT: page 1 ends on a heading whose section starts on page 2\n"


def test_a_short_last_page_nothing_can_take_back_is_a_note_not_a_failure():
    """Any layout finding failed the batch, so where the floors kept two pages and the fit
    put every bullet back, the application kept a failed check nobody could act on. It is
    said as a note now; a heading at the foot, or a short page the fit never tried, still
    fails."""
    import fit_to_page
    import verify_batch
    kept = {"abbr": "Thin", "thin_end": fit_to_page.THIN_KEPT}
    assert "fewest lines" in verify_batch._thin_kept(kept, THIN)
    space = {"abbr": "Thin", "thin_end": fit_to_page.THIN_SPACE}
    assert "space you asked" in verify_batch._thin_kept(space, THIN)
    assert verify_batch._thin_kept(kept, THIN + FOOT) == ""
    assert verify_batch._thin_kept({"abbr": "Thin"}, THIN) == ""
    assert set(verify_batch.THIN_NOTES) == {fit_to_page.THIN_KEPT, fit_to_page.THIN_SPACE}
    src = open(os.path.join(ROOT, "tools", "verify_batch.py"), encoding="utf-8").read()
    assert "layout_note = _thin_kept(_entry(batch, a), found)" in src


def test_under_leave_some_space_a_short_last_page_is_the_space(monkeypatch):
    """"Leave some space" never fills the page, nor takes a short last page back onto one
    page fewer (which would fill page 1 to its foot): the short page is the space asked
    for, and the draft says so."""
    import fit_to_page
    a = {"abbr": "Thin", "fill": "space", "jobs": [{"employer": "K", "bullets": ["a1"]}]}
    monkeypatch.setattr(fit_to_page, "PAGES", 2)
    monkeypatch.setattr(fit_to_page.R, "final_abbr", lambda d: "Thin")
    monkeypatch.setattr(fit_to_page.R, "jobs_for", lambda d: None)
    monkeypatch.setattr(fit_to_page.allocate, "caps_for", lambda posting: {})
    monkeypatch.setattr(fit_to_page, "hold_to_caps", lambda d, caps=None: [])
    monkeypatch.setattr(fit_to_page, "_render_resume", lambda d: 2)
    monkeypatch.setattr(fit_to_page, "_too_close", lambda abbr: False)
    monkeypatch.setattr(fit_to_page, "_thin_end", lambda abbr: True)
    monkeypatch.setattr(fit_to_page.docpaths, "has_letter", lambda d: False)
    monkeypatch.setattr(fit_to_page, "compile_resume", lambda abbr, passes=1: 2)
    monkeypatch.setattr(fit_to_page, "font_problems", lambda pdf: [])
    monkeypatch.setattr(fit_to_page, "_lines", lambda pdf: 31)
    assert fit_to_page.fit(a) == ((2, 31), 0)
    assert a["thin_end"] == fit_to_page.THIN_SPACE and a["jobs"][0]["bullets"] == ["a1"]
