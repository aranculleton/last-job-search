"""A text layer whose words run together is caught by pypdf, or the batch says it was not.

`verify_pdf.py` falls back to pdftotext when pypdf is missing or broken, and
pdftotext infers spaces from where glyphs sit: it reads a resume whose words
run together as if it were fine. So a batch verified on a container without a
working pypdf passed the one failure its spacing check exists for. `--require
pypdf` refuses the fallback with its own exit status, and verify_batch.sh reports
the spacing check as SKIPPED, never as ALL PASS.
"""
from __future__ import annotations

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


def test_the_batch_requires_pypdf_and_says_when_it_could_not():
    with open(os.path.join(ROOT, "tools", "verify_batch.sh"), encoding="utf-8") as fh:
        script = fh.read()
    assert script.count('verify_pdf.py" --require pypdf') == 2
    assert "SPACING CHECK SKIPPED" in script
    assert 'BATCH: NOT ALL PASS, the spacing check was SKIPPED"; exit 3' in script
    # ALL PASS is printed only after both the findings and the skip were ruled out.
    tail = script[script.index('[ $fail -eq 0 ] || { echo "BATCH: FAILURES ABOVE"'):]
    assert tail.index("SKIPPED") < tail.index("BATCH: ALL PASS")
