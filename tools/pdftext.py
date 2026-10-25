"""What a PDF holds, read with pypdf: how many pages, its text, and its fonts.

These three jobs were Poppler's (pdfinfo, pdftotext, pdffonts), which is a system
package: on a Mac it came from Homebrew, on Windows from winget, and on Linux from
sudo apt. None of those is something a person should need before the app works, and
fit_to_page.py crashed with a traceback where pdfinfo was missing. pypdf is a Python
package in requirements.txt, so it installs with the rest of the Python side, the
same way on every computer, with no password.

One reader everywhere also means one answer everywhere. pdftotext's layout differed
between a Mac and Linux (a Mac's put each bullet's mark on a line of its own), so the
same resume could pass on one and fail on the other. pypdf's plain extraction starts
every line at column 0, as `pdftotext -layout` did for the lines the checks read (a
heading, an employer's line, a bullet), and it does not infer spaces from where glyphs
sit, which is why verify_pdf.py already read with it first.

Poppler is still used where it is already installed and pypdf cannot run at all (a
container whose system `cryptography` is broken panics inside pyo3 on import): then
`text()` falls back to `pdftotext -layout`, and says so through `reader()`.

    python3 tools/pdftext.py <file.pdf>        pages, reader, fonts, then the text
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


class Unreadable(RuntimeError):
    """Nothing on this computer could read the PDF."""


def _pypdf():
    """The PdfReader class, or None. BaseException, not ImportError: a broken
    `cryptography` panics inside pyo3, and pyo3's PanicException is a direct
    subclass of BaseException (verify_pdf._extract_pypdf has the long story)."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import local_path
        local_path.use_venv()        # where env_check.py --fix installs it on a computer
    except Exception:                # noqa: BLE001  reading a PDF must not need it
        pass
    try:
        from pypdf import PdfReader
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return None
    return PdfReader


def pypdf_ok() -> bool:
    return _pypdf() is not None


def _open(pdf):
    reader_cls = _pypdf()
    if reader_cls is None:
        return None
    try:
        return reader_cls(str(pdf))
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return None


def pages(pdf) -> int | None:
    """The page count, or None when the file cannot be read (missing, damaged, or no
    reader here). Never a guess: a caller decides what an unreadable PDF means."""
    if not os.path.exists(str(pdf)):
        return None
    r = _open(pdf)
    if r is not None:
        try:
            return len(r.pages)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            return None
    exe = shutil.which("pdfinfo")
    if not exe:
        return None
    out = subprocess.run([exe, str(pdf)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def reader() -> str:
    """Which reader `text()` uses here: "pypdf", "pdftotext", or "" for none."""
    if pypdf_ok():
        return "pypdf"
    return "pdftotext" if shutil.which("pdftotext") else ""


def text(pdf) -> str:
    """Every page's text, pages joined by a newline. Raises Unreadable when no reader
    on this computer can read it, rather than returning "" (an empty text layer passed
    every check that looks for something wrong)."""
    if not os.path.exists(str(pdf)):
        raise Unreadable(f"there is no PDF at {pdf}")
    r = _open(pdf)
    if r is not None:
        try:
            return "\n".join((p.extract_text() or "") for p in r.pages)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            if not shutil.which("pdftotext"):
                raise Unreadable(f"pypdf could not read {os.path.basename(str(pdf))}: "
                                 f"{type(exc).__name__}") from None
    exe = shutil.which("pdftotext")
    if not exe:
        raise Unreadable("nothing here can read a PDF: the Python package pypdf is "
                         "missing. `python3 tools/env_check.py --fix` installs it")
    got = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(pdf), "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if got.returncode != 0:
        raise Unreadable(f"pdftotext could not read {pdf}: {got.stderr.strip()[:200]}")
    return got.stdout


def _obj(x):
    return x.get_object() if hasattr(x, "get_object") else x


def _fonts_in(resources, out: dict, seen: set) -> None:
    res = _obj(resources) or {}
    for _key, ref in (_obj(res.get("/Font")) or {}).items():
        f = _obj(ref)
        name = str(f.get("/BaseFont") or f.get("/Name") or "[none]").lstrip("/")
        sub = str(f.get("/Subtype") or "").lstrip("/")
        desc = f.get("/FontDescriptor")
        if sub == "Type0":
            kids = _obj(f.get("/DescendantFonts")) or []
            if kids:
                d = _obj(kids[0])
                desc = d.get("/FontDescriptor")
                sub = "Type0/" + str(d.get("/Subtype") or "").lstrip("/")
        desc = _obj(desc) or {}
        embedded = sub == "Type3" or any(k in desc for k in ("/FontFile", "/FontFile2",
                                                              "/FontFile3"))
        out.setdefault(name, {"name": name, "type": sub, "embedded": embedded})
    # Forms carry their own resources, and a font used only inside one is still on the page.
    for _key, ref in (_obj(res.get("/XObject")) or {}).items():
        x = _obj(ref)
        if str(x.get("/Subtype")) == "/Form" and id(x) not in seen and x.get("/Resources"):
            seen.add(id(x))
            _fonts_in(x.get("/Resources"), out, seen)


def fonts(pdf) -> list[dict] | None:
    """Each font the PDF uses, once: {"name", "type" (Type1, TrueType, Type0/CIDFontType0C,
    Type3, ...), "embedded"}. The same facts pdffonts printed. None when the PDF cannot
    be read with pypdf (the caller then has nothing to report, as when pdffonts was
    missing)."""
    r = _open(pdf) if os.path.exists(str(pdf)) else None
    if r is None:
        return None
    out: dict = {}
    try:
        for page in r.pages:
            _fonts_in(page.get("/Resources"), out, set())
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return None
    return list(out.values())


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.strip().splitlines()[-1].strip())
        return 0 if args else 2
    pdf = args[0]
    n = pages(pdf)
    if n is None:
        print(f"cannot read {pdf}", file=sys.stderr)
        return 1
    print(f"pages: {n}")
    print(f"reader: {reader() or 'none'}")
    for f in fonts(pdf) or []:
        print(f"font: {f['name']} {f['type']} {'embedded' if f['embedded'] else 'NOT embedded'}")
    print(text(pdf))
    return 0


if __name__ == "__main__":
    sys.exit(main())
