"""Every value that reaches a .tex file is escaped for the place it lands, by one function.

A draft's words, a posting's title, the hiring manager's name the research read off the
posting and the profile's plain settings all land inside LaTeX. `clean()` escaped
`% & $ # _ ~ ^` and left `\\`, `{` and `}` alone, and the company, the role and the
requisition number went raw into `%` comment lines, where a line break ends the comment:
`\\input{<a file>}` in the salutation printed another file into the letter, and a newline in
the requisition ran a command, while the batch reported ALL PASS. A percent-encoded LinkedIn
address (every accented name) commented out the rest of the contact block, an underscore in
an email address was read as a subscript, and "Skills & Tools" printed "Skills Tools"
(tools/tex_escape.py, the one copy of each rule).

Every name and value here is invented; the candidate is the example person.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "templates")]

import tex_escape as T  # noqa: E402

# Every character LaTeX reads as markup, a command that reads a file, one that writes to
# the shell, and a line break in the middle.
HOSTILE = "a\\input{/x/secret.txt} \\write18{rm -rf} {b} 50% #1 $5 & c_d ~e ^f\ng"
COMMANDS = re.compile(r"\\(?:input|write18|write|openin|catcode|AtBeginDocument"
                      r"|lettercontent)(?![a-zA-Z])")

with open(os.path.join(ROOT, "tests", "fixtures", "design_draft.json"), encoding="utf-8") as fh:
    DRAFT = json.load(fh)


def _no_markup(tex: str) -> bool:
    """Nothing in `tex` is markup but the escapes text() writes."""
    rest = re.sub(r"\\[%&$#_{}]|\\text(?:asciitilde|asciicircum|backslash)\{\}|-\\kern0pt-", "", tex)
    return not re.search(r"[\\{}%&$#_~^\n\r]", rest)


# --- the four places a value lands --------------------------------------------------------

def test_text_escapes_everything_and_twice_is_once():
    out = T.text(HOSTILE)
    assert _no_markup(out), out
    assert not COMMANDS.search(out)
    assert T.text(out) == out
    # Already escaped by a drafter, left alone; a line break of any kind is a space.
    assert T.text("22\\% to 14\\% \\& more") == "22\\% to 14\\% \\& more"
    for brk in ("\n", "\r\n", "\r", "\u2028", "\u2029", "\x0b", "\x0c", "\x85"):
        assert T.text("one" + brk + "two") == "one two", repr(brk)
    # Two hyphens are two hyphens, unless the prose asked LaTeX for a dash.
    assert T.text("morgan--ellis") == "morgan-\\kern0pt-ellis"
    assert T.text("quality--the rest", dashes=True) == "quality--the rest"


def test_a_comment_value_stays_on_its_line():
    out = T.comment("R-2291\n\\AtBeginDocument{\\lettercontent{x}}%\r\nmore\u2028last")
    assert "\n" not in out and "\r" not in out and "\u2028" not in out
    assert out.startswith("R-2291 \\AtBeginDocument")      # inert after the "%"


def test_a_url_keeps_its_encoding_and_loses_its_markup():
    assert (T.url("https://www.linkedin.com/in/example-jos%C3%A9-garc%C3%ADa")
            == "https://www.linkedin.com/in/example-jos\\%C3\\%A9-garc\\%C3\\%ADa")
    out = T.url("https://example.com/a b{c}\\d?q=1&r=2#top josé_~")
    assert "{" not in out.replace("\\string", "") and " " not in out and "é" not in out
    assert "\\&" in out and "\\#" in out and "\\_" in out and "%C3%A9".replace("%", "\\%") in out


def test_an_email_prints_and_links_from_one_argument():
    assert T.email("morgan_ellis@example.com") == "morgan\\_ellis@example.com"
    with pytest.raises(ValueError):
        T.email("morgan ellis@example.com\n\\input{x}")


# --- every field of a draft, into both .tex files -------------------------------------------

def _hostile_draft():
    a = copy.deepcopy(DRAFT)
    for k in ("summary", "tools", "p1", "p2", "lead", "p4", "contact_person", "req_id",
              "company", "role", "letter_date"):
        a[k] = (a.get(k) or "x") + " " + HOSTILE
    a["company"] = "Larkspur Freight " + HOSTILE
    a["cl_bullets"] = [{"label": "Forecasting " + HOSTILE, "text": "Better " + HOSTILE}]
    a["consented_skills"] = ["Looker " + HOSTILE]
    a["declined_skills"] = ["Spark " + HOSTILE]
    return a


def test_no_field_of_a_draft_or_the_profile_runs_as_latex(tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import render_application as R
    gen = R.gen
    for d in ("cv", "cover_letters"):
        (tmp_path / d).mkdir()
    # The profile's plain settings too: every one a person types.
    for key in ("location", "phone", "linkedin_label", "name", "first", "last"):
        monkeypatch.setitem(gen._ID, key, "Morgan " + HOSTILE)
    monkeypatch.setitem(gen._ID, "linkedin", "https://www.linkedin.com/in/example-x%C3%A9 " + HOSTILE)
    for key in ("closing", "page_label", "salutation_prefix", "pdf_keywords"):
        monkeypatch.setitem(gen._DOC, key, "W " + HOSTILE)
    monkeypatch.setitem(gen._DOC, "resume_extra", ["Right to work " + HOSTILE])
    for key in list(gen._H):
        monkeypatch.setitem(gen._H, key, "Head & " + HOSTILE)
    monkeypatch.setattr(R, "_SALUTATION_SUFFIX", " team " + HOSTILE)
    monkeypatch.setattr(R.skills_block, "LABELS",
                        [(c, "Label " + HOSTILE) for c, _l in R.skills_block.LABELS])
    a = _hostile_draft()
    d = R.build(a)
    for path in (gen.resume(d), gen.letter(d)):
        with open(path, encoding="utf-8") as fh:
            tex = fh.read()
        # What LaTeX reads: each line up to a "%" that is not escaped. Inside a comment the
        # draft's words are inert, as long as the comment kept its line.
        read = "\n".join(re.sub(r"(?<!\\)%.*", "", ln) for ln in tex.splitlines())
        found = COMMANDS.findall(read)
        # The template's own \AtBeginDocument and \lettercontent are the only ones.
        template = gen.RESUME_HEAD if path == docpaths.resume_tex(d["abbr"]) else gen.LETTER
        assert len(found) == len(COMMANDS.findall(template)), (path, found)
        for line in tex.splitlines():
            # Nothing the draft wrote opens a line of its own: each comment kept its line.
            assert not line.startswith(("g ", "g}", "\\input", "\\write")), (path, line)
        assert "\\textbackslash{}input\\{/x/secret.txt\\}" in tex


def test_the_addressee_is_only_ever_the_name_the_research_gives():
    import draft_audit
    d = dict(copy.deepcopy(DRAFT), contact_person="Jane Doe \\input{/x/secret.txt}")
    assert [f["rule"] for f in draft_audit.research_findings(
        d, {"company": d["company"]}, {"named_contact": "Jane Doe"})] == ["contact"]
    for ok in ("Jane Doe", "Dr Jane Doe", "Jane O'Neill-Doe"):
        d["contact_person"] = ok
        assert draft_audit.research_findings(
            d, {"company": d["company"]}, {"named_contact": "Dr Jane O'Neill-Doe"}) == [] or \
            ok == "Jane Doe", ok
    d["contact_person"] = "Jane Doe Smith"          # a word the research never gave
    assert draft_audit.research_findings(d, {"company": d["company"]},
                                         {"named_contact": "Jane Doe"})


# --- compiled, with the profile values that broke the page ---------------------------------

needs_tex = pytest.mark.skipif(not (shutil.which("xelatex") and shutil.which("lualatex"))
                               or not importlib.util.find_spec("pypdf"),
                               reason="xelatex, lualatex or pypdf is not installed here")


def _profile(tmp_path):
    dst = tmp_path / "profile"
    shutil.copytree(os.path.join(ROOT, "profile.example"), dst)
    p = dst / "person.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["identity"].update(
        email="morgan_ellis@example.com",
        linkedin="https://www.linkedin.com/in/example-jos%C3%A9-garc%C3%ADa",
        linkedin_label="linkedin.com/in/morgan--ellis-example")
    data["documents"]["headings"].update(skills="Skills & Tools",
                                         education="Education & Training")
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    skills = dst / "skills.py"
    skills.write_text(skills.read_text(encoding="utf-8").replace(
        '"BI, tooling and delivery"', '"BI, tooling & delivery"'), encoding="utf-8")
    return dst


@needs_tex
def test_the_compiled_pages_print_what_the_values_say(tmp_path):
    state = tmp_path / "state"
    for d in ("cv", "cover_letters"):
        (state / d).mkdir(parents=True)
    for f in ("OpenFonts", "cover.cls"):
        os.symlink(os.path.join(ROOT, "cover_letters", f), state / "cover_letters" / f)
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET-FROM-ANOTHER-FILE\n", encoding="utf-8")
    a = copy.deepcopy(DRAFT)
    a["contact_person"] = "Jane Doe \\input{%s}" % secret.as_posix()
    a["req_id"] = "R-2291\n\\AtBeginDocument{\\lettercontent{Ref: \\input{%s}}}%%" % (
        secret.as_posix())
    drafts = state / "drafts.json"
    drafts.write_text(json.dumps([a], ensure_ascii=False), encoding="utf-8")
    env = dict(os.environ, LJS_PROFILE=str(_profile(tmp_path)), LJS_STATE=str(state))
    fit = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fit_to_page.py"),
                          str(drafts)], capture_output=True, text=True, env=env)
    assert fit.returncode == 0, fit.stdout + fit.stderr
    assert "CHECK" not in fit.stdout
    import pdftext
    abbr = json.loads(drafts.read_text(encoding="utf-8"))[0]["abbr"]
    resume = pdftext.text(str(state / "cv" / f"Morgan_Ellis_CV_{abbr}.pdf"))
    letter = pdftext.text(str(state / "cover_letters" / f"Morgan_Ellis_Cover_Letter_{abbr}.pdf"))
    assert "SECRET" not in resume + letter
    flat = " ".join(resume.split())
    for line in ("morgan_ellis@example.com", "linkedin.com/in/morgan--ellis-example",
                 "Right to work in the UK", "Skills & Tools", "Education & Training",
                 "BI, tooling & delivery"):
        assert line in flat, line
    assert "morgan_ellis@example.com" in " ".join(letter.split())
    from pypdf import PdfReader
    uris = [an.get_object().get("/A", {}).get("/URI")
            for page in PdfReader(str(state / "cv" / f"Morgan_Ellis_CV_{abbr}.pdf")).pages
            for an in page.get("/Annots") or []]
    assert "https://www.linkedin.com/in/example-jos%C3%A9-garc%C3%ADa" in uris
    assert "mailto:morgan_ellis@example.com" in uris
    verify = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "verify_batch.py"),
                             str(drafts)], capture_output=True, text=True, env=env)
    assert "BATCH: ALL PASS" in verify.stdout, verify.stdout + verify.stderr
