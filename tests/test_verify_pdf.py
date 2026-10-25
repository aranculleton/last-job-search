import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.verify_pdf import (
    VerificationError,
    extract_text_layer,
    parse_page_count,
    run_tool,
    verify_pdf,
)


class ParsePageCountTests(unittest.TestCase):
    def test_parses_pdfinfo_page_count(self):
        self.assertEqual(parse_page_count("Title: Example\nPages:          2\n"), 2)

    def test_rejects_output_without_page_count(self):
        with self.assertRaisesRegex(VerificationError, "did not contain a page count"):
            parse_page_count("Title: Example\n")


class VerifyPdfTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.pdf = Path(self.temp_dir.name) / "example.pdf"
        self.pdf.touch()

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("tools.verify_pdf._extract_pypdf", return_value=None)
    @patch("tools.verify_pdf.run_tool")
    def test_accepts_expected_pages_and_text(self, mock_run_tool, _pypdf):
        mock_run_tool.side_effect = [
            "Professional\nExperience   [your.email@example.com]\n",
            "Pages:          2\n",
        ]

        verify_pdf(
            self.pdf,
            expected_pages=2,
            min_chars=20,
            required_text=("Professional Experience", "[your.email@example.com]"),
        )

    @patch("tools.verify_pdf._extract_pypdf", return_value=None)
    @patch("tools.verify_pdf.run_tool")
    def test_rejects_wrong_page_count(self, mock_run_tool, _pypdf):
        mock_run_tool.side_effect = ["ok", "Pages:          3\n"]

        with self.assertRaisesRegex(VerificationError, "expected 2 page.*found 3"):
            verify_pdf(self.pdf, expected_pages=2)

    @patch("tools.verify_pdf._extract_pypdf", return_value=None)
    @patch("tools.verify_pdf.run_tool")
    def test_rejects_too_little_extractable_text(self, mock_run_tool, _pypdf):
        mock_run_tool.side_effect = ["short", "Pages:          1\n"]

        with self.assertRaisesRegex(VerificationError, "expected at least 20"):
            verify_pdf(self.pdf, min_chars=20)

    @patch("tools.verify_pdf._extract_pypdf", return_value=None)
    @patch("tools.verify_pdf.run_tool")
    def test_rejects_missing_required_text(self, mock_run_tool, _pypdf):
        mock_run_tool.side_effect = [
            "Readable text, but not the expected section.",
            "Pages:          1\n",
        ]

        with self.assertRaisesRegex(VerificationError, "Professional Experience"):
            verify_pdf(self.pdf, required_text=("Professional Experience",))

    def test_rejects_missing_pdf(self):
        with self.assertRaisesRegex(VerificationError, "PDF does not exist"):
            verify_pdf(Path(self.temp_dir.name) / "missing.pdf")

    @patch("tools.verify_pdf._extract_pypdf", return_value=("Hello ATS body", 1))
    def test_pypdf_is_preferred_over_poppler(self, _pypdf):
        text, pages, extractor = extract_text_layer(self.pdf)
        self.assertEqual(extractor, "pypdf")
        self.assertEqual(text, "Hello ATS body")
        self.assertEqual(pages, 1)

    @patch("tools.verify_pdf._extract_pypdf", return_value=None)
    @patch("tools.verify_pdf.run_tool")
    def test_falls_back_to_pdftotext(self, mock_run_tool, _pypdf):
        mock_run_tool.side_effect = ["poppler text", "Pages:          2\n"]
        text, pages, extractor = extract_text_layer(self.pdf)
        self.assertEqual(extractor, "pdftotext")
        self.assertEqual(text, "poppler text")
        self.assertEqual(pages, 2)
        self.assertEqual(mock_run_tool.call_args_list[0][0][0][:3], ["pdftotext", "-layout", "-enc"])


class RunToolTests(unittest.TestCase):
    @patch("tools.verify_pdf.subprocess.run", side_effect=FileNotFoundError)
    def test_reports_missing_poppler_command(self, _mock_run):
        with self.assertRaisesRegex(VerificationError, r"env_check\.py --fix. installs pypdf"):
            run_tool(["pdftotext", "example.pdf", "-"])

    @patch("tools.verify_pdf.subprocess.run")
    def test_reports_unreadable_pdf(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(
            1, ["pdfinfo", "example.pdf"], stderr="invalid PDF"
        )

        with self.assertRaisesRegex(VerificationError, "invalid PDF"):
            run_tool(["pdfinfo", "example.pdf"])


if __name__ == "__main__":
    unittest.main()


class PypdfFailureFallsBackToPopplerTests(unittest.TestCase):
    """A broken pypdf must degrade to Poppler, not take the process down.

    On a container whose system `cryptography` package is broken, importing
    pypdf aborts inside pyo3 and surfaces as `pyo3_runtime.PanicException`, a
    direct subclass of BaseException. The guards in `_extract_pypdf` were
    `except ImportError` and `except Exception`, and neither sees a
    BaseException, so verify_pdf died with a Rust backtrace while `pdftotext`
    sat installed and working three lines away. The tool that is the last check
    before a document reaches an employer checked nothing.

    PanicException is simulated with a bare BaseException subclass so the test
    does not need a broken container to reproduce the case.
    """

    class FakePanic(BaseException):
        """Stands in for pyo3_runtime.PanicException."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.pdf = Path(self.temp_dir.name) / "example.pdf"
        self.pdf.touch()

    def test_a_base_exception_from_pypdf_falls_back_to_pdftotext(self):
        def boom(_path):
            raise self.FakePanic("Python API call failed")

        with patch("tools.verify_pdf._extract_pypdf", side_effect=boom):
            with self.assertRaises(self.FakePanic):
                extract_text_layer(self.pdf)

    def test_the_guard_inside_extract_pypdf_swallows_a_base_exception(self):
        """The real fix: the guard is inside _extract_pypdf, so None is returned."""
        from tools import verify_pdf as V

        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) \
            else __builtins__.__import__

        def exploding_import(name, *args, **kwargs):
            if name == "pypdf":
                raise self.FakePanic("Python API call failed")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=exploding_import):
            self.assertIsNone(V._extract_pypdf(self.pdf))

    def test_keyboard_interrupt_is_never_swallowed(self):
        """A guard broad enough to catch a panic must not eat Ctrl-C."""
        from tools import verify_pdf as V

        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) \
            else __builtins__.__import__

        def interrupting_import(name, *args, **kwargs):
            if name == "pypdf":
                raise KeyboardInterrupt
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=interrupting_import):
            with self.assertRaises(KeyboardInterrupt):
                V._extract_pypdf(self.pdf)

    def test_the_whole_path_still_reaches_pdftotext(self):
        from tools import verify_pdf as V

        with patch.object(V, "_extract_pypdf", return_value=None), \
             patch.object(V, "_extract_pdftotext", return_value=("fallback text", 1)):
            text, pages, extractor = V.extract_text_layer(self.pdf)
        self.assertEqual((text, pages, extractor), ("fallback text", 1, "pdftotext"))
