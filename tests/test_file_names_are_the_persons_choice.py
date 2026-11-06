"""What the files a person sends are called is one setting, with a sensible default.

The maintainer, 2026-11-06: "How about a setting for what to put for file names? ... don't
overwhelm the user, sensible defaults ... use standards". One row in Settings, File names,
with three presets, each shown as an example from the person's own name and their latest
employer; the person, the employer, then the document by default, the document's word by
their market (documents.noun, CV or Resume). The files Claude keeps keep their names; only
the copies that leave (the page's download, the chat's copy) follow the setting. The
candidate is the example person, whose word is "CV"; every employer here is invented.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "tools", "network"),
                os.path.join(ROOT, "tests")]

import docpaths  # noqa: E402
import person  # noqa: E402

PRESETS = [p[0] for p in docpaths.FILE_NAME_PRESETS]


@pytest.fixture
def chosen(monkeypatch):
    """Set person.json values for one test, without writing the example profile."""
    real = person.get
    over: dict = {}

    def get(key, default=person._MISSING):
        if key in over:
            return over[key]
        return real(key) if default is person._MISSING else real(key, default)
    monkeypatch.setattr(person, "get", get)
    return over


# ------------------------------------------------------------------ the engine


@pytest.mark.parametrize("preset, want", [
    ("name_employer_document", "Morgan_Ellis_Kestrel_Foods_CV.pdf"),
    ("name_document", "Morgan_Ellis_CV.pdf"),
    ("name_employer_role_document", "Morgan_Ellis_Kestrel_Foods_Data_Analyst_CV.pdf"),
])
def test_each_preset_builds_its_name(preset, want):
    assert docpaths.file_name("CV", "Kestrel Foods Ltd", "Data Analyst", preset) == want
    letter = docpaths.file_name("Cover_Letter", "Kestrel Foods Ltd", "Data Analyst", preset)
    assert letter == want.replace("_CV.pdf", "_Cover_Letter.pdf")


def test_the_default_is_name_employer_document_in_every_market(chosen):
    assert docpaths.FILE_NAMES_DEFAULT == "name_employer_document"
    markets = [f[:-5] for f in os.listdir(os.path.join(ROOT, "tools", "markets"))
               if f.endswith(".json")]
    assert markets and all(docpaths.recommended_file_names(cc) == "name_employer_document"
                           for cc in markets)
    # Nothing chosen, or something no preset is: the default.
    assert docpaths.file_names() == "name_employer_document"
    chosen["documents.file_names"] = "whatever"
    assert docpaths.file_names() == "name_employer_document"
    chosen["documents.file_names"] = "name_document"
    assert docpaths.file_names() == "name_document"


def test_the_document_word_is_the_persons_own_by_market(chosen):
    # A UK profile says CV (the example's own), a US one Resume: documents.noun, which
    # /setup takes from the market.
    assert docpaths.example_file_name(None, "Kestrel") == "Morgan_Ellis_Kestrel_CV.pdf"
    chosen["documents.noun"] = "resume"
    assert docpaths.example_file_name(None, "Kestrel") == "Morgan_Ellis_Kestrel_Resume.pdf"


def test_a_long_role_and_employer_are_cut_the_way_they_read():
    n = docpaths.file_name("CV", "Kestrel Foods & Co.",
                           "Senior Demand Planning Analyst (m/w/d) REQ-2026-0412",
                           "name_employer_role_document")
    # The requisition number and the gender marker go, the legal tail goes, and the role
    # keeps its last words, the job.
    assert n == "Morgan_Ellis_Kestrel_Foods_Planning_Analyst_CV.pdf", n
    head = docpaths.file_name("CV", "Harbourline", "Head of Supply Chain Planning and "
                              "Inventory Optimisation", "name_employer_role_document")
    assert head.startswith("Morgan_Ellis_Harbourline_Head_of_") and not head.endswith(
        "_of_CV.pdf"), head
    for preset in PRESETS:
        for kind in ("CV", "Cover_Letter"):
            got = docpaths.file_name(kind, "The Northern Regional Distribution Cooperative "
                                     "of Greater Manchester", "Principal Data Engineering "
                                     "and Analytics Platform Lead", preset)
            stem = got[:-4]
            assert len(stem) <= docpaths.FILE_NAME_MAX, got
            assert stem.startswith("Morgan_Ellis_") and stem.endswith("_" + kind), got


def test_only_safe_characters_reach_a_name():
    n = docpaths.file_name("CV", "Brévanne & Ørsted / Weißfeld #1", "Analyst (Level 2)",
                           "name_employer_role_document")
    assert n.isascii() and all(c.isalnum() or c in "_." for c in n), n
    assert n.startswith("Morgan_Ellis_Brevanne_and_Orsted"), n


@pytest.mark.parametrize("kept", ["cv/Morgan_Ellis_CV_Kestrel.pdf",
                                  "cv/Morgan_Ellis_Kestrel_CV.pdf"],
                         ids=["old order", "new order"])
def test_a_kept_file_in_either_order_leaves_under_the_chosen_name(kept, chosen):
    assert docpaths.send_name(kept, "Kestrel Foods", "Planner") == \
        "Morgan_Ellis_Kestrel_Foods_CV.pdf"
    chosen["documents.file_names"] = "name_employer_role_document"
    assert docpaths.send_name(kept, "Kestrel Foods", "Planner") == \
        "Morgan_Ellis_Kestrel_Foods_Planner_CV.pdf"
    chosen["documents.file_names"] = "name_document"
    assert docpaths.send_name(kept, "Kestrel Foods", "Planner") == "Morgan_Ellis_CV.pdf"


def test_the_kept_name_never_follows_the_setting(chosen, tmp_path, monkeypatch):
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    for preset in PRESETS:
        chosen["documents.file_names"] = preset
        assert docpaths.resume_rel("Kestrel") == "cv/Morgan_Ellis_Kestrel_CV.tex"
        assert docpaths.letter_rel("Kestrel") == "cover_letters/Morgan_Ellis_Kestrel_Cover_Letter.tex"


def test_the_chats_copy_takes_the_chosen_name(chosen, tmp_path, monkeypatch):
    import csv_store
    import shown
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    (tmp_path / "cv").mkdir()
    pdf = tmp_path / "cv" / "Morgan_Ellis_CV_Kestrel.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    row = {"date": "2026-11-01", "company": "Kestrel Foods", "role": "Data Analyst",
           "status": "drafted", "cv_file": "cv/Morgan_Ellis_CV_Kestrel.tex",
           "cover_letter_file": ""}
    csv_store.write_rows(str(tmp_path / "job_search_tracker.csv"), [row], list(row))
    chosen["documents.file_names"] = "name_employer_role_document"
    got = shown.copy(str(pdf), str(tmp_path))
    assert got == "documents/to_send/Morgan_Ellis_Kestrel_Foods_Data_Analyst_CV.pdf", got
    assert pdf.exists()


# ------------------------------------------------------------------ the page's model and action


def test_the_setting_row_carries_each_presets_example(chosen):
    import app_model

    class Ctx:
        tracker = [{"company": "Larkspur Retail", "role": "Supply Chain Analyst"}]
    targets: dict = {}
    item = next(x for x in app_model._settings(Ctx(), targets) if x["key"] == "file_names")
    assert item["value"] == "name_employer_document"
    assert [c[0] for c in item["choices"]] == PRESETS
    assert item["examples"]["name_employer_document"] == "Morgan_Ellis_Larkspur_Retail_CV.pdf"
    assert item["examples"]["name_document"] == "Morgan_Ellis_CV.pdf"
    assert item["recommended"] == "name_employer_document"
    assert targets["setting-file_names"]["key"] == "file_names"


def test_saving_a_chip_writes_the_setting(tmp_path):
    from test_a_tick_on_the_page_is_applied_once import Search
    page = Search(str(tmp_path))
    item = page.item("setting-file_names")
    assert item["value"] == "name_employer_document" and item["examples"], item
    a = page.act("setting.set", item["id"], value="name_employer_role_document", rev=item["rev"])
    assert page.apply()["ok"] == [a]
    note = page.receipt(a)["note"]
    assert note.startswith("Your files are named like Morgan_Ellis_") and note.endswith("_CV.pdf."), note
    with open(os.path.join(page.profile, "person.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["documents"]["file_names"] == "name_employer_role_document"
    assert data["documents"]["noun"] == "CV", "the rest of documents is kept"
    assert page.item("setting-file_names")["value"] == "name_employer_role_document"
    item = page.item("setting-file_names")
    b = page.act("setting.set", item["id"], value="name_role", rev=item["rev"])
    page.apply()
    assert "not one of the choices" in page.receipt(b)["note"]


# ------------------------------------------------------------------ the page


def _setting(value="name_employer_document"):
    return {"id": "setting-file_names", "key": "file_names", "label": "File names",
            "kind": "choice", "value": value, "rev": "fn1",
            "choices": [[k, label] for k, label, _ in docpaths.FILE_NAME_PRESETS],
            "examples": {"name_employer_document": "Morgan_Ellis_Larkspur_Retail_CV.pdf",
                         "name_document": "Morgan_Ellis_CV.pdf",
                         "name_employer_role_document":
                             "Morgan_Ellis_Larkspur_Retail_Supply_Chain_Analyst_CV.pdf"},
            "recommended": "name_employer_document"}


@pytest.fixture(scope="module")
def run():
    from test_the_page_journeys import browser
    yield from browser()


def test_the_row_shows_the_example_and_a_chip_saves_the_setting(run, tmp_path):
    import app_page
    from test_the_page_journeys import PHONE, _sample
    model = _sample()
    model["settings"] = [s for s in model["settings"] if s.get("key") != "file_names"] + [_setting()]
    path = os.path.join(str(tmp_path), "page.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(app_page.standalone(app_page.render(model)))
    you = "#main section.set-group[aria-label=\"You\"]"
    got = run("engine", html=path, viewport=PHONE, clock="2026-11-06T09:00:00Z",
              fake={"canSend": "available"}, steps=[
                  {"hash": "settings", "read": you},
                  {"open": "set-sum:file_names", "read": you},
                  {"eval": "(document.querySelector('[data-k=\"set-file_names-2\"]').click(), 1)",
                  },
                  {"wait": 1200},
                  {"eval": "(() => { const r = document.querySelector('[data-k=\"set-file_names-2\"]').closest('.choice').getBoundingClientRect();"
                           " return r.right <= window.innerWidth && r.left >= 0; })()"}])
    assert not got["errors"], got["errors"]
    row = got["after"][0]["text"]
    assert "File names" in row and "Morgan_Ellis_Larkspur_Retail_CV.pdf" in row, row
    opened = got["after"][1]["text"]
    for words in ("Name, employer, document", "Name, document", "Name, employer, role, document",
                  "Morgan_Ellis_CV.pdf", "recommended"):
        assert words in opened, (words, opened)
    acts = [a for a in got["actions"] if a["action"] == "setting.set"]
    assert acts and acts[-1]["item"] == "setting-file_names", acts
    assert acts[-1]["value"] == "name_employer_role_document", acts
    assert got["after"][4]["eval"] is True, "a chip stays on a phone's screen"
