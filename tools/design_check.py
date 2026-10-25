#!/usr/bin/env python3
"""Check a rendered resume or letter against its design's rules, and prove every design and
every font on this computer's TeX.

What an applicant tracking system and a printer both need, read off the PDF itself rather
than off the .tex, so a font or a TeX install that behaves differently is caught:

  - the page is the size the design asked for (Letter or A4), and one page
  - nothing smaller than MIN_TEXT_PT, and the body (the size most words are in) at least
    MIN_BODY_PT
  - every word at least MIN_EDGE_MM from every edge of the page: text in the outer band is
    where parsers look for running headers and footers and drop them, and where printers clip
  - one column: the text, in the order a parser reads it, runs down the page, never back up
    (a two-column layout reads its second column after the first has reached the foot)

    python3 tools/design_check.py <resume.pdf> [--design <name>] [--page letter|a4]
    python3 tools/design_check.py --fonts     # every font in every engine, read back as an ATS would
    python3 tools/design_check.py --all [--out DIR]   # every design rendered and checked

`--all` renders the example person's application in every design (templates/doc_design.py
DESIGNS) in a scratch copy of the app, fits it, runs tools/verify_batch.sh and these rules on
both documents, and exits 1 on any finding. CI runs it on Linux, macOS and Windows.

Exit 0 all pass, 1 a finding, 2 usage.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "tools"), os.path.join(ROOT, "templates")]

MIN_TEXT_PT = 8.5      # a footnote's size; the contact line and the dates may sit near it
MIN_BODY_PT = 9.8      # the size most words are in: guides ask 10pt at least (11pt type set \small)
MIN_EDGE_MM = 10.0     # every word this far from every edge
PAGES = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}
MM = 72 / 25.4


def _mul(m, n):
    """The product of two PDF matrices [a b c d e f]: m applied first, then n."""
    return [m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3],
            m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
            m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5]]


def runs(pdf):
    """[(page, text, x, y, size)] for every text-showing operation, in the order a parser
    reads them: where each starts on the page and its size there.

    Read from the content stream's own operators rather than pypdf's text visitor, which
    reports a later run on a line at the page's origin for some XeTeX output (seen
    2026-10-25), and a position check is only as good as its positions. Within a line the
    start of each run is what is measured, which is all the edge and column checks need."""
    from pypdf import PdfReader
    from pypdf.generic import ContentStream
    reader = PdfReader(pdf)
    out = []
    ident = [1, 0, 0, 1, 0, 0]
    for n, page in enumerate(reader.pages):
        contents = page.get_contents()
        if contents is None:
            continue
        ops = ContentStream(contents, reader).operations
        cm, stack = list(ident), []
        tm, tlm, size, lead = list(ident), list(ident), 0.0, 0.0
        for operands, op in ops:
            op = op.decode("latin-1") if isinstance(op, bytes) else op
            if op == "q":
                stack.append(list(cm))
            elif op == "Q":
                cm = stack.pop() if stack else list(ident)
            elif op == "cm":
                cm = _mul([float(x) for x in operands], cm)
            elif op == "BT":
                tm, tlm = list(ident), list(ident)
            elif op == "Tf":
                size = float(operands[1])
            elif op == "TL":
                lead = float(operands[0])
            elif op in ("Td", "TD"):
                tx, ty = float(operands[0]), float(operands[1])
                if op == "TD":
                    lead = -ty
                tlm = _mul([1, 0, 0, 1, tx, ty], tlm)
                tm = list(tlm)
            elif op == "Tm":
                tlm = [float(x) for x in operands]
                tm = list(tlm)
            elif op in ("T*", "'", '"'):
                tlm = _mul([1, 0, 0, 1, 0, -lead], tlm)
                tm = list(tlm)
            if op in ("Tj", "TJ", "'", '"'):
                arg = operands[-1] if operands else ""
                if op == "TJ":
                    text = "".join(str(x) for x in arg if not isinstance(x, (int, float))
                                   and not hasattr(x, "as_numeric"))
                else:
                    text = str(arg)
                m = _mul(tm, cm)
                out.append((n, text, m[4], m[5], abs(size) * math.hypot(m[0], m[1])))
    return out


def _texts(pdf):
    """The page's words as a parser reads them (pypdf), for the size count."""
    from pypdf import PdfReader
    out = []
    for page in PdfReader(pdf).pages:
        def visit(text, cm, tm, _font, size):
            if text and text.strip():
                a = tm[0] * cm[0] + tm[1] * cm[2]
                b = tm[0] * cm[1] + tm[1] * cm[3]
                out.append((0, text, 0, 0, abs(size) * math.hypot(a, b)))
        page.extract_text(visitor_text=visit)
    return out


def sizes(rs):
    """(body size, smallest size), weighting each run by its letters."""
    weight = {}
    small = None
    for _p, text, _x, _y, size in rs:
        letters = len(re.findall(r"[^\W\d_]", text))
        if letters < 2 or size < 1:
            continue
        s = round(size, 1)
        weight[s] = weight.get(s, 0) + letters
        small = s if small is None else min(small, s)
    body = max(weight, key=weight.get) if weight else None
    return body, small


def check(pdf, page=None, one_page=True):
    """[finding] for one PDF: page size and count, sizes, edges, one column."""
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    found = []
    if one_page and len(reader.pages) != 1:
        found.append(f"PAGES {len(reader.pages)}: the design must keep one page")
    w, h = (float(v) for v in reader.pages[0].mediabox[2:])
    if page:
        ew, eh = PAGES[page]
        if abs(w - ew) > 2 or abs(h - eh) > 2:
            found.append(f"PAGE_SIZE {w:.0f}x{h:.0f}pt, not {page} ({ew:.0f}x{eh:.0f})")
    rs = runs(pdf)
    if not rs:
        return found + ["NO_TEXT: the PDF has no text layer a parser can read"]
    body, small = sizes(_texts(pdf))
    if body is not None and body < MIN_BODY_PT:
        found.append(f"BODY_SIZE {body}pt, under {MIN_BODY_PT}pt")
    if small is not None and small < MIN_TEXT_PT:
        found.append(f"TEXT_SIZE {small}pt somewhere, under {MIN_TEXT_PT}pt")
    edge = MIN_EDGE_MM * MM
    for _p, _text, x, y, _size in rs:
        if x < edge - 0.5 or y < edge - 0.5 or y > h - edge + 0.5 or x > w - edge:
            found.append(f"EDGE: text at {x / MM:.0f}mm across, {(h - y) / MM:.0f}mm down sits "
                         f"within {MIN_EDGE_MM:g}mm of the page's edge, where parsers drop "
                         "headers and footers")
            break
    # One column: in reading order, each line is no higher than the lowest line read so far,
    # give or take a line (a right-aligned date shares its title's line, a superscript sits
    # a little above). A second column is read after the first has reached the foot.
    low = None
    for _p, _text, x, y, size in rs:
        if low is not None and y > low + max(size, 10) * 1.5:
            found.append(f"COLUMNS: text at {x / MM:.0f}mm across, {(h - y) / MM:.0f}mm down is "
                         "read after text below it: a parser reads this page out of order")
            break
        low = y if low is None else min(low, y)
    return found


# --- every font, every engine ---------------------------------------------------------------

PROBE = ["Zo\u00eb \u00c5ngstr\u00f6m-N\u00fa\u00f1ez",
         "\u0141\u00f3d\u017a and M\u00e1laga, \u00d8rsted, Soci\u00e9t\u00e9 G\u00e9n\u00e9rale",
         "Certified workflow office affluent efficient fifty fluent",
         "SQL, Python, dbt, Power BI", "+44 7700 900123", "zoe.angstrom@example.com",
         "Reduced forecast error from 22% to 14% across 2,400 SKUs",
         "\u00a31.1M saved, \u20ac40k, 30+ managers"]


def probe_font(name, engine, workdir):
    """[finding] for one font in one engine: the probe lines must read back as typed."""
    import doc_design
    from pypdf import PdfReader
    opts, stem = doc_design.fontspec_options(name, workdir)
    body = "\n\n".join(x.replace("%", "\\%") for x in PROBE)
    tex = ("\\documentclass[11pt]{article}\n\\usepackage{fontspec}\n"
           f"\\setmainfont[{opts}]{{{stem}}}\n\\begin{{document}}\n{body}\n\n"
           f"{{\\bfseries {body}}}\n\n{{\\itshape {body}}}\n\\end{{document}}\n")
    job = f"probe_{name}_{engine}"
    with open(os.path.join(workdir, job + ".tex"), "w", encoding="utf-8") as fh:
        fh.write(tex)
    subprocess.run([engine, "-interaction=nonstopmode", job + ".tex"], cwd=workdir,
                   capture_output=True, timeout=300)
    pdf = os.path.join(workdir, job + ".pdf")
    if not os.path.exists(pdf):
        return ["COMPILE: no PDF"]
    text = " ".join(PdfReader(pdf).pages[0].extract_text().split())
    found = []
    if re.search("[\ufb00-\ufb06]", text):
        found.append("LIGATURE: a ligature character in the text layer")
    if "\ufffd" in text or "(cid:" in text:
        found.append("REPLACEMENT: a character the font cannot map back")
    missing = [x for x in PROBE if text.count(x) < 3]
    if missing:
        found.append("READS_AS: " + "; ".join(missing[:2]) + " (words run together, or a "
                     "letter lost, in the regular, bold or italic)")
    return found


def fonts_matrix():
    """Each font in each engine, compiled where the resume compiles (cv/), so the font's path
    is the one a real document uses: LuaTeX failed to find a font two folders up that it
    found one folder up (2026-10-25), and the documents are only ever one folder away."""
    import doc_design
    work = os.path.join(ROOT, "cv")
    bad = 0
    for name in doc_design.FONTS:
        for engine in ("lualatex", "xelatex"):
            if not shutil.which(engine):
                print(f"{name:18s} {engine:9s} SKIP: {engine} is not installed")
                continue
            try:
                f = probe_font(name, engine, work)
            finally:
                job = os.path.join(work, f"probe_{name}_{engine}")
                for ext in (".tex", ".pdf", ".log", ".aux"):
                    if os.path.exists(job + ext):
                        os.remove(job + ext)
            bad += bool(f)
            print(f"{name:18s} {engine:9s} {'OK' if not f else ' | '.join(f)}")
    return 1 if bad else 0


# --- every design ---------------------------------------------------------------------------

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "design_draft.json")


def _copy_app(dest):
    """The app's files, without git's, the build's or anyone's documents."""
    def ignore(d, names):
        rel = os.path.relpath(d, ROOT)
        skip = {".git", "__pycache__", ".pytest_cache", "node_modules", "rounds", ".venv"}
        out = [n for n in names if n in skip]
        if rel in ("cv", "cover_letters"):
            out += [n for n in names if os.path.splitext(n)[1] in (".pdf", ".aux", ".log", ".out")]
        return out
    shutil.copytree(ROOT, dest, ignore=ignore, symlinks=True)


def all_designs(out_dir=None):
    import doc_design
    tmp = tempfile.mkdtemp(prefix="ljs_designs_")
    app = os.path.join(tmp, "app")
    _copy_app(app)
    env = dict(os.environ, LJS_PROFILE="profile.example", PYTHONUTF8="1")
    env.pop("LJS_STATE", None)
    with open(FIXTURE, encoding="utf-8") as fh:
        draft = json.load(fh)
    bad = 0
    try:
        for name in doc_design.DESIGNS:
            d = dict(draft, design=name)
            path = os.path.join(tmp, f"drafts_{name}.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump([d], fh, ensure_ascii=False)
            fit = subprocess.run([sys.executable, "tools/fit_to_page.py", path], cwd=app, env=env,
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=900)
            found = [] if fit.returncode == 0 else ["FIT: " + (fit.stderr or fit.stdout)[-300:]]
            stem = d.get("abbr") or "Larkspur"
            pdfs = {}
            for kind, folder in (("resume", "cv"), ("letter", "cover_letters")):
                hits = [f for f in os.listdir(os.path.join(app, folder))
                        if f.endswith(f"_{stem}.pdf") and (("Cover_Letter" in f) == (kind == "letter"))]
                pdfs[kind] = os.path.join(app, folder, hits[0]) if hits else None
            page = None
            if not found:
                bash = shutil.which("bash")
                if bash:
                    vb = subprocess.run([bash, "tools/verify_batch.sh", path], cwd=app, env=env,
                                        capture_output=True, text=True, encoding="utf-8",
                                        errors="replace", timeout=900)
                    if vb.returncode != 0:
                        found.append("VERIFY_BATCH: " + " ".join(
                            ln for ln in vb.stdout.splitlines()
                            if re.search(r"FAIL|^\w+\s+\d/\d", ln))[-400:])
                else:
                    found.append("VERIFY_BATCH: SKIP, no bash on this computer")
                page = (doc_design.DESIGNS[name][0].get("page")
                        or _market_page(app, env))
                for kind, pdf in pdfs.items():
                    if not pdf:
                        found.append(f"{kind.upper()}: no PDF")
                        continue
                    found += [f"{kind}: {x}" for x in check(pdf, page)]
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
                        shutil.copy(pdf, os.path.join(out_dir, f"{name}_{kind}.pdf"))
            bad += bool(found)
            print(f"{name:9s} {'ALL PASS' if not found else ''}")
            for x in found:
                print(f"          {x}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if bad else 0


def _market_page(app, env):
    out = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'tools'); "
                          "import person; print(person.paper('resume'))"],
                         cwd=app, env=env, capture_output=True, text=True, encoding="utf-8")
    return "letter" if "letter" in out.stdout else "a4"


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    if argv[0] == "--fonts":
        return fonts_matrix()
    if argv[0] == "--all":
        out = argv[argv.index("--out") + 1] if "--out" in argv else None
        return all_designs(out)
    pdf = argv[0]
    page = argv[argv.index("--page") + 1] if "--page" in argv else None
    found = check(pdf, page)
    body, small = sizes(_texts(pdf))
    print(f"{os.path.basename(pdf)}: body {body}pt, smallest {small}pt"
          + ("" if found else "; all rules pass"))
    for x in found:
        print("  " + x)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
