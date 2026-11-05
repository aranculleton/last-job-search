"""A rerun of the drafts records the version only for what passed, and hands each failure on.

A live session (the maintainer, 2026-11-05): the `method-drafts` upgrade made 17 unsent
applications again, 14 passed, 3 cover letters still failed the check for copying the posting
word for word, and the upgrade was recorded done anyway, with no redraft queued and no To do
card for the three. They would have sat failing until someone noticed. The method was a
sentence for an agent; it is code now (tools/remake_drafts.py): the version is kept on each
application that passes (its verify.json), each that fails is handed its way forward (a
redraft of just the part that copied, queued on the page by itself, or one To do card where
only the person can settle it), the person hears one plain line at most, and the repo's
drafts version is recorded only once every unsent application has passed. A tracker row an
older version wrote naming a letter for a draft with none is put right on the same run.

A mixed set, the example person's: one clean application, one whose letter's opening copies
the posting, one whose resume runs to two pages, one resume alone whose tracker row still
names a letter, and one already sent, which is never touched. Rendering and the PDF checks
are stood in for (no LaTeX here); every decision after them is the real code's. Invented
employers throughout.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import app_model  # noqa: E402
import build_versions as B  # noqa: E402
import csv_store  # noqa: E402
import docpaths  # noqa: E402
import outreach  # noqa: E402
import person  # noqa: E402
import profile_upgrades as U  # noqa: E402
import record_drafts  # noqa: E402
try:
    import remake_drafts as M  # noqa: E402
except ImportError:            # before it: the rerun was a sentence for an agent
    M = None
import tweak  # noqa: E402
import verify_batch  # noqa: E402

from test_one_drafting_call_per_posting import FIXTURE  # noqa: E402

TODAY = "2026-11-05"
LETTER = ("p1", "p2", "lead", "cl_bullets", "p4")
POSTING = FIXTURE["posting"]
# Eleven words of the posting's own first sentence, in the letter's opening.
COPIED = ("You will build weekly forecasts of claims volumes so our claims handling teams can "
          "staff ahead of demand, which is the work I did at Brindle & Hart Logistics.")

APPS = {
    "clean": ("Wexmoor Lending", "Forecasting Analyst", {}),
    "copies": ("Ottergate Foods", "Pricing Analyst", {"p1": COPIED}),
    "too_long": ("Quillfield Retail", "Supply Analyst", {}),
    "alone": ("Brightwater Freight", "Planning Analyst", {"resume_only": True}),
    "sent": ("Harrowgate Mills", "Data Analyst", {}),
}


@pytest.fixture
def state(tmp_path, monkeypatch):
    """The example person's state, copied, and the five applications kept as /apply keeps
    them (draft.json, job_posting.md), each with its tracker row."""
    st = tmp_path / "state"
    shutil.copytree(os.path.join(ROOT, "profile.example", "state"), st)
    monkeypatch.setenv("LJS_STATE", str(st))
    record = tmp_path / "build_versions.json"
    shutil.copyfile(os.path.join(ROOT, "profile.example", B.RECORD), record)
    data = json.loads(record.read_text(encoding="utf-8"))
    data["drafts"] = {"version": 62, "date": "2026-11-01"}       # two reruns behind
    record.write_text(json.dumps(data), encoding="utf-8")
    real_path = person.path
    monkeypatch.setattr(person, "path", lambda *p: str(record) if p == (B.RECORD,)
                        else real_path(*p))
    rows = []
    for key, (company, role, more) in APPS.items():
        abbr = company.split()[0]
        # The fixture's letter and posting, made this employer's.
        own = json.loads(json.dumps(FIXTURE["draft"]).replace("Kestrel Mutual", company))
        d = dict(own, company=company, role=role, abbr=abbr,
                 posting=POSTING.replace("Kestrel Mutual", company), **more)
        if more.get("resume_only"):
            d.update(p1="", p2="", lead="", cl_bullets=[], p4="")
        outreach.write(d, {}, "2026-10-20")
        rows.append({"date": "2026-10-20", "company": company, "role": role,
                     "status": "applied" if key == "sent" else "drafted",
                     "cv_file": docpaths.resume_rel(abbr),
                     # The resume alone was recorded by an older version, naming a letter.
                     "cover_letter_file": docpaths.letter_rel(abbr)})
    csv_store.write_rows(str(st / "job_search_tracker.csv"),
                         csv_store.read_rows(str(st / "job_search_tracker.csv")) + rows,
                         record_drafts.HEADER)
    return st


@pytest.fixture
def stand_in(monkeypatch):
    """Rendering and the PDF checks stood in for: each made again is counted, and the check
    writes verify.json as verify_batch does, from its real per-application reading (the
    letters check included) plus a resume too long for Quillfield."""
    made = []

    def render(path):
        made.append(os.path.basename(os.path.dirname(path)))
        return 0, ""

    def check(path):
        d = M._loaded(path)
        flags = ["RESUME_2p"] if d["company"] == "Quillfield Retail" else []
        flags += verify_batch._batch_flags(d["abbr"], d, not docpaths.has_letter(d), d, [d])
        flags = [f for f in flags if f not in ("CLAIMS", "NUMBERS", "VOICE")]
        verify_batch._record(d, flags, 1, None if not docpaths.has_letter(d) else 1,
                             docpaths.has_letter(d))
        return (1 if flags else 0), ""
    monkeypatch.setattr(M, "render", render)
    monkeypatch.setattr(M, "check", check)
    return made


def _apps():
    return {a["row"]["company"]: a for a in M.unsent()}


def _tracker():
    return {r["company"]: r for r in csv_store.read_rows(person.state("job_search_tracker.csv"))}


def test_a_mixed_rerun_records_only_what_passed_and_hands_each_failure_on(state, stand_in):
    assert U.by_id("method-drafts").pending()
    got = M.run(TODAY)
    # Each unsent one made again, never the one already sent.
    assert sorted(got["made"]) == sorted(f"{c} | {r}" for k, (c, r, _m) in APPS.items()
                                         if k != "sent")
    assert "Harrowgate Mills | Data Analyst" not in " ".join(got["made"])
    assert sorted(got["passed"]) == ["Brightwater Freight | Planning Analyst",
                                     "Wexmoor Lending | Forecasting Analyst"]
    assert got["redraft"] == ["Ottergate Foods | Pricing Analyst"]
    assert got["todo"] == ["Quillfield Retail | Supply Analyst"]

    # The version is kept on what passed, and only there.
    apps, now = _apps(), B.current("drafts")
    assert M.made_at(apps["Wexmoor Lending"]["folder"]) == (now, True)
    assert M.made_at(apps["Brightwater Freight"]["folder"]) == (now, True)
    assert M.made_at(apps["Ottergate Foods"]["folder"])[1] is False
    assert M.made_at(apps["Quillfield Retail"]["folder"])[1] is False
    # And not on the repo: three failures left, so the drafts version is not recorded...
    assert not got["recorded"] and B.behind("drafts")
    # ...but nothing is left for the upgrade either: each failure has its way forward.
    assert U.by_id("method-drafts").pending() == ""

    # The letter that copied: a redraft of just its opening, queued as the page's own
    # Tweak box queues one, which the tweak code accepts.
    rec = M.handed(apps["Ottergate Foods"]["folder"])
    assert rec["way"] == "redraft" and rec["version"] == now
    [work] = rec["work"]
    assert work["kind"] == "tweak"
    assert work["args"]["target"] == {"id": apps["Ottergate Foods"]["id"], "output": "letter",
                                      "rev": ""}
    assert work["args"]["changes"] == [{"p": "L4", "v": ["p1"]}]
    assert [c["p"] for c in tweak.check(work)] == ["L4"]
    # Put on the page by itself, once: a page that has it already is not given it again.
    assert [w["id"] for w in M.page_work({"work": {}})] == [work["id"]]
    assert M.page_work({"work": {work["id"]: {"data": {}, "version": 1}}}) == []
    # As the batch tools/app.py view sends beside the screens: one create, queued.
    import datetime as dt
    [batch] = M.page_writes({"work": {}}, str(state / "out"),
                            dt.datetime(2026, 11, 5, 9, tzinfo=dt.timezone.utc))
    [entry] = json.loads(open(batch, encoding="utf-8").read())
    assert (entry["op"], entry["collection"]) == ("set", "work") and "if_version" not in entry
    body = json.loads(open(entry["file_path"], encoding="utf-8").read())
    assert body["kind"] == "tweak" and body["status"] == "queued" and body["args"] == work["args"]

    # The page too long: one To do card naming it, with Make it again; none for the redraft.
    model, targets = app_model.build(only={"needs_you"})
    cards = {c["id"]: c for c in model["needs_you"] if c["id"].startswith("q-remade-")}
    assert list(cards) == [f"q-remade-{apps['Quillfield Retail']['id']}"]
    card = next(iter(cards.values()))
    assert "Quillfield Retail" in card["title"] and "pages" in card["body"]
    assert card["options"][0]["label"] == "Make it again"
    assert card["options"][0]["work"]["args"]["redo"] is True
    assert targets[card["id"]]["kind"] == "tracker"

    # The person hears one plain line.
    assert got["say"] == ("Made 4 unsent applications again with the newest checks: 1 is being "
                          "rewritten where it copied the posting and 1 needs you, in To do.")

    # The tracker put right on the same run: the resume alone names no letter now; the
    # others keep theirs, and the one sent is untouched.
    rows = _tracker()
    assert got["tracker"] == ["Brightwater Freight | Planning Analyst"]
    assert rows["Brightwater Freight"]["cover_letter_file"] == ""
    assert rows["Wexmoor Lending"]["cover_letter_file"] == docpaths.letter_rel("Wexmoor")
    assert rows["Harrowgate Mills"]["cover_letter_file"] == docpaths.letter_rel("Harrowgate")


def test_a_second_run_makes_nothing_twice_and_records_once_all_pass(state, stand_in):
    M.run(TODAY)
    stand_in.clear()
    again = M.run(TODAY)
    assert stand_in == [] and again["made"] == [] and not again["say"]
    assert not again["recorded"]
    # Their way forward done: the redraft and Make it again pass their checks.
    for name in ("Ottergate Foods", "Quillfield Retail"):
        d = M._loaded(_apps()[name]["draft"])
        verify_batch._record(d, [], 1, 1, True)
    assert M.pending() == "record" and U.by_id("method-drafts").pending()
    last = M.run(TODAY)
    assert last["made"] == [] and last["recorded"]
    assert not B.behind("drafts") and U.by_id("method-drafts").pending() == ""
    model, _ = app_model.build(only={"needs_you"})
    assert not [c for c in model["needs_you"] if c["id"].startswith("q-remade-")]
    assert M.page_work({"work": {}}) == []


def test_a_check_that_could_not_run_is_neither_a_pass_nor_handed_on(state, monkeypatch):
    monkeypatch.setattr(M, "render", lambda path: (0, ""))
    monkeypatch.setattr(M, "check", lambda path: (3, ""))
    got = M.run(TODAY)
    assert got["passed"] == [] and len(got["unchecked"]) == 4
    assert not got["redraft"] and not got["todo"] and not got["recorded"]
    assert U.by_id("method-drafts").pending()            # tried again on the next run


def test_the_upgrade_runs_the_code_and_never_records_it_by_hand():
    u = U.by_id("method-drafts")
    assert u.run.startswith("python3 tools/remake_drafts.py")
    assert "build_versions.py record" not in u.run


def _kept(company):
    import fit_to_page
    folder = outreach.app_folder(company, next(r for c, r, _m in APPS.values() if c == company))
    return fit_to_page.load(os.path.join(folder, "draft.json"))[0][0]


def test_a_letter_that_copies_the_posting_is_recorded_as_failing(state):
    # Its own record said "flags": [] while the batch failed on its letter, so a rerun read
    # it as passing.
    d = _kept("Ottergate Foods")
    assert "LETTERS" in verify_batch._batch_flags(d["abbr"], d, False)
    clean = _kept("Wexmoor Lending")
    assert "LETTERS" not in verify_batch._batch_flags(clean["abbr"], clean, False)


def test_a_computer_with_no_latex_keeps_every_pdf_and_tries_again_later(state, tmp_path,
                                                                         monkeypatch):
    """A computer with no LaTeX cannot make the documents again. The rerun used to run the
    real render anyway: fit_to_page deleted each resume's PDF before a compile that could
    not start, the failure was handed on as a To do, and every unsent PDF was gone. No
    engine is now a check that could not run (tried again next run), and nothing is lost."""
    bare = tmp_path / "bin"
    bare.mkdir()
    monkeypatch.setenv("PATH", str(bare))         # no lualatex, no xelatex
    pdfs = {}
    for company, a in _apps().items():
        pdf = docpaths.resume_pdf(M._kept(a["draft"])["abbr"])
        os.makedirs(os.path.dirname(pdf), exist_ok=True)
        with open(pdf, "wb") as fh:
            fh.write(b"%PDF-1.4 the resume as it was\n")
        pdfs[company] = pdf
    got = M.run(TODAY)
    assert not got["todo"] and not got["redraft"] and not got["recorded"], got
    assert len(got["unchecked"]) == 4
    assert all(os.path.isfile(p) for p in pdfs.values()), "a PDF was deleted"
    assert not [a for a in _apps().values() if os.path.isfile(os.path.join(a["folder"], M.REMAKE))]
    assert U.by_id("method-drafts").pending()            # tried again on the next run


def test_a_compile_that_makes_nothing_leaves_the_earlier_pdf_in_place(tmp_path):
    """_compile deleted the old PDF before running LaTeX, so a compile that could not start
    (or failed) left no document at all. It is now set aside and put back on any failure,
    and only a new PDF replaces it."""
    import fit_to_page
    (tmp_path / "r.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}",
                                    encoding="utf-8")
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4 the earlier one\n")
    with pytest.raises(fit_to_page.CompileFailed):
        fit_to_page._compile("no-such-latex-engine", "r.tex", str(tmp_path), str(pdf))
    assert pdf.read_bytes() == b"%PDF-1.4 the earlier one\n"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["r.pdf", "r.tex"]
