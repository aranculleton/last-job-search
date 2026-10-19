"""verify_batch.sh says which reader read the text layer.

Only pypdf sees a text layer whose words run together; pdftotext infers the spaces
and passes it. When pypdf was missing the batch fell back to pdftotext with its
output thrown away, so a pass did not say that half of it had not been checked.
"""
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parent.parent / "tools" / "verify_batch.sh").read_text()


def test_the_reader_is_kept_and_said():
    assert 'verify_pdf.py" "$R" >/dev/null' not in SCRIPT
    assert "text layer read with:" in SCRIPT
    assert "words run together are NOT caught" in SCRIPT
