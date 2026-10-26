"""A person with no resume is offered one in setup's first message and leaves with one.

The maintainer, 2026-10-25: "what if the person doesnt have a resume and wants to do it
through us? should be an option in the app ... more obvious and also better process". So
setup's first message says "No resume? Say "build one with me"", the guided history asks one
job a message, newest first, three things at most (tools/history_interview.py), and setup
ends with a one-page general resume, no letter, rendered and checked by the same tools every
application uses (tools/general_resume.py, `stage_picks.py general`).

A phone chat is never asked for a file, a download or a PDF and is told it can talk instead
of typing (Claude's mobile apps take dictation); a computer chat, Windows or Mac, has no step
outside the chat. A LinkedIn download saved the Windows way (cp1252) or with a byte-order mark
is read right. The general resume takes the person's colour rule and draws in it, and in
black by default.
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools" / "network"), str(ROOT / "templates")]
import claude_surfaces  # noqa: E402
import doc_style  # noqa: E402
import fit_to_page  # noqa: E402
import general_resume as G  # noqa: E402
import history_interview as H  # noqa: E402
import place  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "linkedin_export"
US = re.compile(r"\b(?:color|favor|center|organiz|recogniz|realiz|customiz|analyz|"
                r"prioritiz|license)\w*", re.I)
FILE_ASK = re.compile(r"\b(?:attach\w*|upload\w*|download\w*|pdf|files?|export\w*)\b", re.I)
OUTSIDE = re.compile(r"\b(?:terminal|powershell|command|python3?|cmd|finder|explorer)\b", re.I)


def _clean(text: str) -> None:
    assert "—" not in text and "–" not in text
    assert not US.search(text), US.search(text).group(0)
    assert not claude_surfaces.BANNED.search(text), claude_surfaces.BANNED.search(text).group(0)


# --- making it obvious --------------------------------------------------------------------

def test_setups_first_message_offers_it_as_its_own_line():
    setup = (ROOT / ".claude" / "commands" / "setup.md").read_text(encoding="utf-8")
    first = setup.split("Then say, in about these words and nothing more:")[1].split("---")[0]
    assert '> 1. Your resume: attach it (PDF or Word) or paste it.\n' in first
    assert '>    No resume? Say "build one with me" and I\'ll make it with you.\n' in first
    for doc in ("README.md", "START_HERE.md", "HELP.md"):
        text = re.sub(r"\s+", " ", (ROOT / doc).read_text(encoding="utf-8")).lower()
        assert "build one with me" in text, doc
    skill = (ROOT / ".claude" / "skills" / "job-application-assistant" / "SKILL.md").read_text(
        encoding="utf-8")
    head = re.sub(r"\s+", " ", skill.split("---")[1])
    for phrase in ("build my resume", "build one with me", "no resume", "show me around"):
        assert phrase in head, phrase


def test_setups_end_offers_the_tour_and_keeps_three_lines():
    setup = (ROOT / ".claude" / "commands" / "setup.md").read_text(encoding="utf-8")
    end = setup.split("> **You're set up.**")[1].split("Nothing more about LinkedIn")[0]
    assert end.count("\n> - ") == 3
    assert "Updates arrive by themselves" not in end
    assert '> Want a quick tour of everything else? Say **"show me around"**.' in end
    assert "python3 tools/tips.py tour" in end


# --- the guided history -------------------------------------------------------------------

@pytest.mark.parametrize("on", H.PLACES)
def test_every_message_is_short_one_job_and_three_questions_at_most(on):
    seeded = H.seed(str(FIXTURE))
    for s in (None, seeded):
        msgs = H.walk(on, s, jobs=4)
        assert len(msgs) >= 3
        for m in msgs:
            _clean(m)
            assert H.words(m) <= place.SHORT_WORDS, (H.words(m), m)
            assert m.count("?") + len(re.findall(r"^\d\. ", m, re.M)) <= 3, m
            assert not OUTSIDE.search(m), OUTSIDE.search(m).group(0)
        # One job a message: a seeded message names one employer of the seed.
        if s:
            for m in msgs[:len(s["jobs"])]:
                assert sum(j["employer"] in m for j in s["jobs"]) == 1, m


def test_a_phone_is_never_asked_for_a_file_and_is_told_it_can_talk():
    for s in (None, H.seed(str(FIXTURE))):
        msgs = H.walk("phone", s, jobs=4)
        for m in msgs:
            assert not FILE_ASK.search(m), FILE_ASK.search(m).group(0)
            assert "paste" not in m.lower() and "computer" not in m.lower()
        assert H.MIC in msgs[0] and not any(H.MIC in m for m in msgs[1:])


def test_a_computer_may_paste_its_page_and_has_no_step_outside_the_chat():
    msgs = H.walk("computer", None, jobs=2)
    assert msgs[0].endswith(H.PASTE)
    assert not any(H.MIC in m for m in msgs)
    assert not any(FILE_ASK.search(m) for m in msgs)


def test_the_first_message_gives_an_example_line():
    m = H.ask("phone", 0)
    assert m.startswith("Let's build it together, newest job first.")
    assert "Like: " + H.EXAMPLE in m


def test_a_seed_is_newest_first_and_asks_only_what_it_lacks():
    s = H.seed(str(FIXTURE))
    assert [j["employer"] for j in s["jobs"]] == [
        "Brindle & Hart Logistics", "Oakmere Foods", "Saltmarsh Analytics"]
    assert s["education"] and s["certifications"]
    first = H.ask("phone", 0, s)
    assert first.startswith("I have your jobs from LinkedIn")
    assert "Brindle & Hart Logistics, Manchester, Mar 2023 to now." in first
    # A job with a description is asked only for a result; the last message skips what the
    # download already holds.
    assert "Anything to add, a result with a number" in first
    assert H.ask("phone", s=s, rest=True).startswith("Last one: anything to add to your education")


def _copy_fixture(tmp_path) -> Path:
    d = tmp_path / "export"
    shutil.copytree(FIXTURE, d)
    return d


def test_a_download_with_a_byte_order_mark_is_read(tmp_path):
    d = _copy_fixture(tmp_path)
    p = d / "Positions.csv"
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes().lstrip(b"\xef\xbb\xbf"))
    s = H.seed(str(d))
    assert s["jobs"][0]["employer"] == "Brindle & Hart Logistics" and s["note"] == ""


def test_a_download_saved_the_windows_way_is_read_and_said_in_one_line(tmp_path):
    d = _copy_fixture(tmp_path)
    p = d / "Positions.csv"
    text = p.read_text(encoding="utf-8-sig").replace("Oakmere Foods", "Café Brûlé")
    p.write_bytes(text.encode("cp1252"))
    s = H.seed(str(d))
    assert "Café Brûlé" in [j["employer"] for j in s["jobs"]]
    assert s["note"].startswith("Positions.csv was saved the Windows way")
    assert s["note"].count("\n") == 0
    _clean(s["note"])
    # Read as UTF-8 again once it is fixed.
    p.write_text(text, encoding="utf-8")
    assert H.seed(str(d))["note"] == ""


# --- the general resume -------------------------------------------------------------------

def test_the_general_draft_aims_at_the_search_with_no_letter():
    a = G.draft()
    assert a["general"] is True and a["company"] == G.COMPANY
    assert all(a[k] in ("", []) for k in ("p1", "p2", "lead", "cl_bullets", "p4"))
    assert a["role"] == "Supply Chain Analyst"
    assert a["posting"].startswith("A general CV for Supply Chain Analyst, Operations Analyst, "
                                   "Demand Planning Analyst")
    assert a["summary"] == G.canonical_summary() and "22% to 14%" in a["summary"]
    assert "Tableau" not in a["tools"] and "SQL" in a["tools"]     # SECONDARY stays off
    assert "style" not in a                                         # black, by default
    assert G.draft(role="data analyst")["role"] == "Data Analyst"


def test_fit_checks_a_general_resume_by_its_pages_alone():
    assert not fit_to_page.needs_check(1, 0, 0, general=True)
    assert fit_to_page.needs_check(2, 0, 0, general=True)
    assert fit_to_page.needs_check(1, 0, 0)          # an application still needs its letter


def test_its_colour_is_its_own_then_the_default_then_the_kind_then_black(monkeypatch):
    assert G.style_for() == ("black", "no style is set")
    assert G.style_for("teal") == ("teal", "this resume's own choice")
    with pytest.raises(ValueError):
        G.style_for("neon")
    monkeypatch.setattr(doc_style, "setting", lambda: {"kinds": {"bank": "navy",
                                                                 "startup": "teal"}})
    monkeypatch.setattr(G, "_target_employers",
                        lambda: ["Kestrel Mutual", "Larkspur Labs", "Fernhill Bank"])
    kinds = {"Kestrel Mutual": ["bank"], "Larkspur Labs": ["startup"], "Fernhill Bank": ["bank"]}
    monkeypatch.setattr(doc_style, "kinds_of", lambda name: kinds.get(name, []))
    assert G.style_for() == ("navy", "most of their target employers are a bank")
    assert G.draft()["style"] == "navy"
    monkeypatch.setattr(doc_style, "setting", lambda: {"default": "forest",
                                                       "kinds": {"bank": "navy"}})
    assert G.style_for() == ("forest", "documents.styles default")
    assert G.style_for("plum")[0] == "plum"


def test_the_short_copy_fits_a_reply():
    a = G.draft()
    full, short = G.plain_text(a), G.plain_text(a, short=True)
    assert full.startswith("Morgan Ellis\n") and "morgan.ellis@example.com" in full
    assert "EDUCATION" in full and "EDUCATION" not in short and "University of Leeds" not in short
    assert short.count("\n- ") == 3                 # one bullet for each of the three jobs
    assert len(short.split()) < len(full.split()) * 0.6
    _clean(short.replace("optimisation", ""))


needs_tex = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("lualatex", "pdftotext", "pdfinfo")),
    reason="lualatex and Poppler are not installed here")


def _colours(pdf):
    from tests.test_a_resume_is_black import _colours as c
    return {x for x in c(pdf) if max(x) - min(x) > 0.01}


def _rgb(hexcolour):
    return tuple(round(int(hexcolour[i:i + 2], 16) / 255, 2) for i in (0, 2, 4))


@needs_tex
def test_a_real_general_resume_is_one_page_checked_kept_and_black(tmp_path, monkeypatch):
    pytest.importorskip("pypdf")
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    got = G.make(str(tmp_path / "general"))
    assert got["pages"] == 1 and got["verify"] == 0, got["verify_out"]
    assert got["verify_out"].splitlines()[-1] == "BATCH: ALL PASS"
    assert "no letters: a general resume" in got["verify_out"]
    assert got["kept"] and got["pdf"].endswith(os.path.join("documents", "cv",
                                                            "Morgan_Ellis_CV_current.pdf"))
    import docpaths
    assert docpaths.current_resume() == "documents/cv/Morgan_Ellis_CV_current.pdf"
    assert not os.path.exists(docpaths.letter_pdf("General"))
    with open(got["txt"], encoding="utf-8") as fh:
        assert fh.read() == G.plain_text(got["draft"])
    assert _colours(got["pdf"]) == set()
    with open(got["drafts"], encoding="utf-8") as fh:
        assert json.load(fh)[0]["general"] is True


@needs_tex
@pytest.mark.parametrize("style", ["navy", "forest"])
def test_a_real_general_resume_in_a_style_draws_its_accent(tmp_path, monkeypatch, style):
    pytest.importorskip("pypdf")
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    got = G.make(str(tmp_path / "general"), style=style, keep=False)
    assert got["pages"] == 1 and got["verify"] == 0, got["verify_out"]
    assert _colours(got["pdf"]) == {_rgb(doc_style.STYLES[style][0])}
    assert not got["kept"]


def test_the_entry_point_is_stage_picks_general():
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "stage_picks.py"), "general",
                        "--help"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0 and "--summary-file" in r.stdout and "--style" in r.stdout
