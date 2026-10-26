"""A text layer whose words run together is caught by pypdf, or the batch says it was not.

`verify_pdf.py` falls back to pdftotext when pypdf is missing or broken, and
pdftotext infers spaces from where glyphs sit: it reads a resume whose words
run together as if it were fine. So a batch verified on a container without a
working pypdf passed the one failure its spacing check exists for. `--require
pypdf` refuses the fallback with its own exit status, and verify_batch.sh reports
the spacing check as SKIPPED, never as ALL PASS.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import verify_pdf as V  # noqa: E402

TEXT = "Professional Experience and a page of ordinary words with their spaces. " * 8


@pytest.fixture
def pdf(tmp_path):
    p = tmp_path / "resume.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    return p


def test_without_pypdf_a_required_read_is_unavailable_not_failed(pdf):
    with patch.object(V, "pypdf_available", return_value=False):
        with pytest.raises(V.ReaderUnavailable):
            V.extract_text_layer(pdf, require="pypdf")
        assert V.main([str(pdf), "--require", "pypdf"]) == V.EXIT_NO_READER
    assert V.EXIT_NO_READER not in (0, 1, 2)


def test_pypdf_reading_nothing_is_a_finding_and_never_falls_back(pdf):
    with patch.object(V, "pypdf_available", return_value=True), \
            patch.object(V, "_extract_pypdf", return_value=None), \
            patch.object(V, "_extract_pdftotext", return_value=(TEXT, 1)) as fallback:
        assert V.main([str(pdf), "--require", "pypdf"]) == 1
        fallback.assert_not_called()


def test_without_require_the_fallback_still_reads(pdf):
    with patch.object(V, "_extract_pypdf", return_value=None), \
            patch.object(V, "_extract_pdftotext", return_value=(TEXT, 1)):
        assert V.verify_pdf(pdf)[0] == "pdftotext"
    with patch.object(V, "pypdf_available", return_value=True), \
            patch.object(V, "_extract_pypdf", return_value=(TEXT, 1)):
        assert V.verify_pdf(pdf, require="pypdf")[0] == "pypdf"


def _batch(tmp_path, monkeypatch, spacing_exit, design_exit=None):
    """tools/verify_batch.py over one invented application whose text layer is clean, with
    the spacing check (verify_pdf.py --require pypdf) answering `spacing_exit` and every
    other tool clean. Returns (exit code, what it printed, the verify_pdf calls)."""
    import verify_batch as B
    monkeypatch.setenv("LJS_PROFILE", os.path.join(ROOT, "profile.example"))
    monkeypatch.setenv("LJS_STATE", str(tmp_path))
    import docpaths
    import person
    person.reset()
    for p in (docpaths.resume_pdf("Acme"), docpaths.letter_pdf("Acme")):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(b"%PDF-1.4\n")
    v = docpaths.values()
    page = "\n".join(json.loads(v["CONTACT_LINES"]) + [v["H_EXPERIENCE"]]
                      + [line for n in json.loads(v["ROLE_NAMES"])
                         for line in (n, "• Built the weekly forecast", "• Ran the reporting")]
                      + [v["H_EDUCATION"]])
    monkeypatch.setattr(B.pdftext, "text", lambda pdf: page)
    monkeypatch.setattr(B.pdftext, "pages", lambda pdf: 1)
    monkeypatch.setattr(B.pdftext, "reader", lambda: "pypdf")
    monkeypatch.setattr(B, "section_layout", lambda tex, want: "")
    monkeypatch.setattr(B, "resume_bullets", lambda *a: [])
    calls = []

    def run3(args):
        calls.append(args)
        if args[0].endswith("verify_pdf.py") and "--require" in args:
            return spacing_exit, "", ""
        if args[0].endswith("verify_pdf.py") and len(args) == 2:
            return 0, "extractor: pdftotext\n", ""
        if args[0].endswith("design_check.py"):
            # The design check reads positions with pypdf alone: where pypdf is missing it
            # answers "not checked" too (3), as the real one does
            # (tests/test_the_design_check_reads_each_document_as_it_was_set.py).
            code = design_exit if design_exit is not None else (
                3 if spacing_exit == V.EXIT_NO_READER else 0)
            return code, "", ""
        return 0, "letters clean\n" if args[0].endswith("audit_letters.py") else "", ""
    monkeypatch.setattr(B, "_run3", run3)
    drafts = tmp_path / "drafts.json"
    drafts.write_text(json.dumps([{"abbr": "Acme"}]), encoding="utf-8")
    import contextlib
    import io
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = B.main([str(drafts)])
    return code, said.getvalue(), calls


def test_the_batch_requires_pypdf_and_says_when_it_could_not(tmp_path, monkeypatch):
    code, said, calls = _batch(tmp_path, monkeypatch, V.EXIT_NO_READER)
    # Both documents were asked for with pypdf required, then read the fallback way.
    assert sum(1 for c in calls if "--require" in c) == 2
    assert code == 3
    assert "SPACING CHECK SKIPPED" in said and "DESIGN CHECK SKIPPED" in said
    assert ("BATCH: NOT ALL PASS, the spacing check and the design check were SKIPPED"
            in said)
    assert "BATCH: ALL PASS" not in said
    assert "DESIGN_RESUME" not in said and "DESIGN_LETTER" not in said
    # The design check alone not run is not a pass either, and a design finding is one.
    code, said, _ = _batch(tmp_path, monkeypatch, 0, design_exit=3)
    assert code == 3 and "BATCH: NOT ALL PASS, the design check was SKIPPED" in said
    code, said, _ = _batch(tmp_path, monkeypatch, 0, design_exit=1)
    assert code == 1 and "DESIGN_RESUME DESIGN_LETTER" in said
    # With pypdf there, the same batch passes, and says so only then.
    code, said, _ = _batch(tmp_path, monkeypatch, 0)
    assert code == 0 and said.rstrip().endswith("BATCH: ALL PASS"), said
    assert "SKIPPED" not in said
