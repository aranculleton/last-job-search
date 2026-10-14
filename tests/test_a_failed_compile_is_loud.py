"""A LaTeX run that produced nothing must not look like a one-page document.

The bug this pins, found by reading the code rather than by a failure:

`compile_resume()` and `compile_letter()` called `subprocess.run` with neither
`check=True` nor any inspection of `.returncode`, and nothing removed the target
PDF before the run. So an aborted recompile left the PREVIOUS run's PDF sitting
on disk, `_pages()` read it as one page, `fit()` reported clean, and every
downstream check ran against a document that did not correspond to its own
.tex: the text-layer extraction, the claims audit, the letter audit, all of it.

The failure is silent by construction. The file exists, it is a valid PDF, and
it is the wrong one. The candidate would have attached last application's
resume to this application.

`_pages()` makes it worse rather than better: it returns 9 when it cannot read
a PDF at all, which reads as "too long", so a genuinely missing document would
have been trimmed against rather than reported.

LaTeX is not installed in the cloud containers this repo runs in, so these
stub the engine rather than invoking it. That is the right level anyway: what
is under test is the contract between the compile step and its callers, not
whether lualatex works.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import fit_to_page as F  # noqa: E402


class _Result:
    def __init__(self, returncode=0, stdout=b""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, b""


class TheCompileStepRefusesToGuess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf = os.path.join(self.tmp.name, "out.pdf")

    def _run(self, engine_writes_pdf, stdout=b"", passes=1):
        def fake(cmd, cwd=None, capture_output=False, **kw):
            if engine_writes_pdf:
                with open(self.pdf, "wb") as fh:
                    fh.write(b"%PDF-1.4\n")
            return _Result(0, stdout)
        with mock.patch.object(F.subprocess, "run", side_effect=fake), \
                mock.patch.object(F, "_pages", return_value=1):
            return F._compile("lualatex", "x.tex", self.tmp.name, self.pdf, passes)

    def test_a_run_that_produces_a_pdf_returns_its_page_count(self):
        self.assertEqual(1, self._run(engine_writes_pdf=True))

    def test_a_run_that_produces_nothing_raises(self):
        with self.assertRaises(F.CompileFailed):
            self._run(engine_writes_pdf=False)

    def test_the_stale_pdf_is_removed_before_the_run(self):
        """The exact shape of the bug: a previous PDF surviving a failed run."""
        with open(self.pdf, "wb") as fh:
            fh.write(b"%PDF-1.4\n% last application's resume\n")
        with self.assertRaises(F.CompileFailed):
            self._run(engine_writes_pdf=False)
        self.assertFalse(os.path.exists(self.pdf),
                         "the previous PDF survived a failed compile, which is "
                         "how the wrong document gets attached")

    def test_the_error_carries_the_latex_error_line(self):
        log = b"This is LuaTeX\n! Undefined control sequence.\nl.42 \\nosuch\n"
        with self.assertRaises(F.CompileFailed) as caught:
            self._run(engine_writes_pdf=False, stdout=log)
        self.assertIn("Undefined control sequence", str(caught.exception))

    def test_a_missing_pdf_is_never_reported_as_a_page_count(self):
        """`_pages` returns 9 for an unreadable PDF; that must not escape."""
        def fake(cmd, cwd=None, capture_output=False, **kw):
            return _Result(0, b"")
        with mock.patch.object(F.subprocess, "run", side_effect=fake):
            with self.assertRaises(F.CompileFailed):
                F._compile("lualatex", "x.tex", self.tmp.name, self.pdf)

    def test_every_pass_runs_and_the_check_is_after_the_last(self):
        calls = []

        def fake(cmd, cwd=None, capture_output=False, **kw):
            calls.append(cmd)
            with open(self.pdf, "wb") as fh:
                fh.write(b"%PDF-1.4\n")
            return _Result(0, b"")
        with mock.patch.object(F.subprocess, "run", side_effect=fake), \
                mock.patch.object(F, "_pages", return_value=1):
            F._compile("lualatex", "x.tex", self.tmp.name, self.pdf, passes=2)
        self.assertEqual(2, len(calls))


class BothEntryPointsGoThroughIt(unittest.TestCase):
    """A second compile path that skipped the check is the whole bug again."""

    def test_neither_entry_point_calls_subprocess_directly(self):
        src = (ROOT / "tools" / "fit_to_page.py").read_text(encoding="utf-8")
        body = src[src.index("def compile_resume"):src.index("def body_words")]
        self.assertNotIn("subprocess.run", body,
                         "compile_resume/compile_letter must delegate to "
                         "_compile, which is where the failure check lives")
        for engine in ("lualatex", "xelatex"):
            self.assertIn(engine, body)


if __name__ == "__main__":
    unittest.main()
