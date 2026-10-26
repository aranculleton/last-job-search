"""Render, compile, measure, trim, repeat until the resume is one page.

LaTeX page breaks are not predictable from source length, so the only reliable
way to hit one page is to compile and measure. This trims in a fixed order,
weakest content first, so what survives is always the strongest material:

  1. the lowest-scoring bullet for THIS posting, wherever it sits
  2. never below any employer's floor, and an employer cut to one line keeps
     the line the allocator would give it alone (allocate._pick)
  3. then shorten the tools line

Then it grows the page back: the strongest absent bullet is added and kept
only if the resume is still one page. A bullet the trimmer removed is never
offered back by the grower; the two used to hand the same bullet back and
forth, one overflow per application, at four LaTeX runs a round.

Every compile is measured once and the measurement is carried forward, so
the document on disk always matches the draft and nothing is compiled twice
to learn the same page count.

The cover letter is trimmed in the order 06-cover-letter-templates.md gives:
the bullets, then the close, then any fifth block, then the opening. The
company paragraph is last and only when nothing else got the letter onto the
page, because that file says never to cut it to make room and it holds the one
fact about the employer that was independently verified.
"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_application as R
import allocate
import skills_block
import bullet_library as LIB
import untrusted
import docpaths
import pdftext
import person

# How many pages the resume fills: documents.resume_pages, default one. One page
# is the norm for a few years' experience in most English-speaking markets; a
# long career, an academic CV or a market that expects two says so here.
PAGES = int(person.get("documents.resume_pages", 1) or 1)

# Derived from this file's location, like every other tool here. It was the
# literal string "/home/user/ai-job-search", which is the path the cloud
# container happens to clone into, so it worked in the only environment anybody
# had run it in. Anywhere else, and SETUP.md documents macOS, Windows and Linux
# paths, fit_to_page would have written a resume to a directory that does
# not exist, or worse, to a stale copy at that path.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# The two icon packages moderncv loads, fontawesome5 and academicons, are the
# only things the documents used from texlive-fonts-extra: 1.5 MB of a 1.7 GB
# package that every fresh container had to download. They are vendored in
# texmf/ (see texmf/README.md) and found through TEXMFHOME, so the install is
# a third of the size and nothing else about the compile changes.
TEXMF = os.path.join(ROOT, "texmf")


def tex_env(base=None):
    """The environment for a LaTeX run, with the repo's texmf/ searchable.

    A TEXMFHOME already set is kept, after ours, rather than replaced."""
    env = dict(os.environ if base is None else base)
    prior = env.get("TEXMFHOME")
    env["TEXMFHOME"] = TEXMF if not prior or prior == TEXMF else "{%s,%s}" % (TEXMF, prior)
    return env


# 03-writing-style.md: "200-250 words of BODY text". The body is what the
# candidate wrote; the header, address, date, salutation and signature block
# are template. Counting the whole PDF inflates the figure by roughly 45 words
# and let letters ship over the limit while the fit loop reported them fine.
# Measure the body from the application object, which is exact, rather than
# from the rendered page, which is not.
MAX_BODY_WORDS = 250
RENDERED_PROSE = ("p1", "p2", "lead", "p4")


def _pages(pdf):
    """The page count, read with pypdf (tools/pdftext.py), so no system package is needed.
    9 when the PDF cannot be read, which no caller mistakes for a fit: _compile raises
    first when no PDF was made."""
    n = pdftext.pages(pdf)
    return 9 if n is None else n


def _lines(pdf):
    """Non-blank text lines, for the report only."""
    try:
        return len([l for l in pdftext.text(pdf).splitlines() if l.strip()])
    except pdftext.Unreadable:
        return 0


def resume_pdf(abbr):
    return docpaths.resume_pdf(abbr)


def letter_pdf(abbr):
    return docpaths.letter_pdf(abbr)


# One LaTeX run takes seconds. Nothing stopped one that never ended: MiKTeX asks before
# it installs a package it lacks, and with nobody to answer, the compile, the fit and the
# chat waited for ever.
COMPILE_TIMEOUT = 300


class CompileFailed(RuntimeError):
    """A LaTeX run that did not produce a document.

    Raised rather than returned so that no caller can mistake a failure for a
    page count. `_pages()` returns 9 when it cannot read a PDF, which reads as
    "too long" and would have been silently trimmed against.
    """


def _compile(engine, tex, cwd, pdf, passes=1):
    """Run `engine` over `tex`, and return the page count of what it produced.

    Two things here are the fix for one bug, and it is worth saying which.

    The exit status was never checked. `subprocess.run` was called with neither
    `check=True` nor any inspection of `.returncode`, so a LaTeX run that
    aborted on a syntax error was indistinguishable from one that succeeded.

    Nothing removed the previous PDF first. Put together, an aborted recompile
    left the PREVIOUS run's PDF on disk, `_pages()` read it as one page, the
    fit loop reported clean, and every downstream check, including the text
    layer and the claims audit, ran happily against a document that did not
    correspond to its own .tex. The failure is silent by construction: the file
    is there, it is a valid PDF, and it is the wrong one.

    So the target is deleted before the run and its absence afterwards is the
    failure signal, which is stronger than the exit status alone: lualatex
    exits non-zero on warnings it recovers from, and exits zero in
    nonstopmode on some errors that still produce no output.
    """
    try:
        os.remove(pdf)
    except FileNotFoundError:
        pass
    last = None
    for _ in range(passes):
        try:
            last = subprocess.run([engine, "-interaction=nonstopmode", tex],
                                  cwd=cwd, capture_output=True, env=tex_env(),
                                  stdin=subprocess.DEVNULL, timeout=COMPILE_TIMEOUT)
        except subprocess.TimeoutExpired:
            raise CompileFailed(
                f"{engine} was still running on {os.path.basename(tex)} after "
                f"{COMPILE_TIMEOUT // 60} minutes, so it was stopped. A LaTeX that installs "
                f"what it is missing as it goes (MiKTeX) can wait for a yes that never "
                f"comes: `python3 tools/env_check.py --fix` turns that into a silent "
                f"install. Then render again.") from None
        except FileNotFoundError:
            raise CompileFailed(
                f"{engine} is not on this computer, so the documents cannot be made: "
                f"`python3 tools/env_check.py --fix` installs LaTeX (no password).") from None
    out = (last.stdout or b"").decode("utf-8", "replace") if last else ""
    if not os.path.exists(pdf):
        tail = out.splitlines()
        log = "\n".join(l for l in tail if l.startswith("!"))[:800]
        raise CompileFailed(
            f"{engine} produced no PDF for {tex}"
            + (f"\n{log}" if log else "\n(no error line in the log)"))

    # A font that cannot be loaded is not an absence. `cover.cls` names its
    # fonts by a path relative to the working directory, so a compile started
    # from the wrong place reports "The font Lato-Lig cannot be found", picks
    # a default, writes a perfectly valid one-page PDF and exits 1. Every
    # check after this one passes: the page count is right, the text layer
    # extracts, the claims are grounded. The letter is simply in the wrong
    # typeface from top to bottom, and nothing says so.
    if "fontspec Error" in out or "cannot be found" in out:
        missing = sorted({m for m in re.findall(r'The font "([^"]+)" cannot be found', out)})
        raise CompileFailed(
            f"{engine} could not load {len(missing) or 'some'} font(s) for {tex}"
            + (f": {', '.join(missing[:6])}" if missing else "")
            + f". It substituted defaults and still wrote {os.path.basename(pdf)}, "
            f"so the PDF is valid and wrong. Check the working directory: "
            f"the font paths in the template are relative to it.")
    log = _log(cwd, tex)
    # An error LaTeX recovered from still leaves a PDF: "! Missing $ inserted" printed an
    # email address without its underscore, "! Paragraph ended before \extrainfo was
    # complete" dropped two contact lines, and each fit reported clean. A clean compile has
    # no "!" line at all, so any one is a document that does not say what was written.
    errors = latex_errors(out + "\n" + log)
    if errors:
        raise CompileFailed(
            f"{engine} reported {len(errors)} error(s) in {os.path.basename(tex)} and wrote a "
            f"PDF anyway, so the page may not say what the draft says: "
            + "; ".join(errors[:4])
            + ". Write the value that line names another way, then render again.")
    # A character the font does not have is left out of the page with no error at all: an
    # accented surname or an employer's name loses a letter, a symbol vanishes from a
    # figure, and the PDF is one valid page. LaTeX says so only in its log.
    lost = missing_characters(out + "\n" + log)
    if lost:
        raise CompileFailed(
            f"{engine} could not print {len(lost)} character(s) in {os.path.basename(pdf)}, "
            f"because its font does not have them: {', '.join(lost[:6])}. The PDF leaves them "
            f"out, so it does not say what the draft says. Write them another way (a plain "
            f"letter, or a word for the symbol), or use a font that has them.")
    return _pages(pdf)


_MISSING = re.compile(r"Missing character: There is no (.+?) (?:\((U\+[0-9A-Fa-f]+)\) )?in font "
                      r"\[?([^\]:!\s]+)")


def _log(cwd, tex):
    """The compile's .log, which holds what the terminal may not."""
    try:
        with open(os.path.join(cwd, os.path.splitext(os.path.basename(tex))[0] + ".log"),
                  encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def latex_errors(log):
    """Each error line a compile printed ("! Missing $ inserted."), once, in order. A line
    of the log that opens on "!" is TeX's own mark for an error, never for a warning."""
    seen = []
    for line in (log or "").splitlines():
        line = line.strip()
        if line.startswith("!") and line not in seen:
            seen.append(line)
    return seen


def missing_characters(log):
    """Each character a compile could not print, once: "日 (U+65E5) in lmroman10-regular"."""
    seen = []
    for char, code, font in _MISSING.findall(log or ""):
        item = f"{char}{' (' + code + ')' if code else ''} in {font}"
        if item not in seen:
            seen.append(item)
    return seen


def font_problems(pdf):
    """Plain lines for each font in `pdf` that is not embedded or is a Type 3 (bitmap) font;
    [] when every font is embedded, or the PDF cannot be read. A font left out of the file
    is replaced by whatever the reader's machine has, and a parser may read it wrongly; a
    Type 3 font prints blurred and many parsers read it as nothing. Read with pypdf
    (tools/pdftext.py), the facts Poppler's pdffonts printed, so nothing extra is needed."""
    if not os.path.exists(pdf):
        return []
    out = []
    for f in pdftext.fonts(pdf) or []:
        name = f["name"]
        if not f["embedded"]:
            out.append(f"the font {name} is not embedded in {os.path.basename(pdf)}, so the "
                       f"reader's machine puts another in its place")
        elif f["type"].startswith("Type3"):
            out.append(f"the font {name} in {os.path.basename(pdf)} is a Type 3 (bitmap) font, "
                       f"which prints blurred and many parsers read as nothing")
    return out


def compile_resume(abbr, passes=1):
    r"""lualatex, or xelatex for a design (resume_engine); returns the page count.

    One pass settles the page count, which is all a measurement needs, and the
    second pass doubled the cost of every one. But moderncv's footer carries
    "\thepage/\pageref{lastpage}", and a page reference needs the second pass
    to pick up the current .aux. A resume that was briefly two pages during
    trimming therefore printed "1/2" on a one-page document, and shipped that
    way. So measurements stay at one pass and the final render asks for two.
    """
    # Where the renderer wrote it: the checkout, or LJS_STATE's folder when that is set.
    return _compile(resume_engine(abbr), docpaths.resume_stem(abbr) + ".tex",
                    os.path.dirname(docpaths.resume_tex(abbr)), resume_pdf(abbr), passes)


def resume_engine(abbr):
    """The engine the .tex names on its "Compile with:" line: LuaLaTeX for the template,
    XeLaTeX for a design (templates/doc_design.py ENGINE). LuaLaTeX when it names none."""
    try:
        with open(docpaths.resume_tex(abbr), encoding="utf-8") as fh:
            head = fh.read(600)
    except OSError:
        return "lualatex"
    m = re.search(r"Compile with: (lualatex|xelatex)\b", head)
    return m.group(1) if m else "lualatex"


def compile_letter(abbr):
    """One xelatex pass; returns the page count."""
    return _compile("xelatex", docpaths.letter_stem(abbr) + ".tex",
                    os.path.dirname(docpaths.letter_tex(abbr)), letter_pdf(abbr))


# The shortest a letter body may be asked to run to (Tweak L1, "Short"): the app keeps every
# letter between 200 and 250 words (draft_audit.BODY_WORDS).
MIN_LETTER_WORDS = 205


def letter_words(a) -> int:
    """The most words this letter's body may run to: the draft's own `max_words` (a tweak),
    else the person's documents.letter_words, else MAX_BODY_WORDS; never under
    MIN_LETTER_WORDS or over MAX_BODY_WORDS."""
    want = a.get("max_words") or person.get("documents.letter_words", None) or MAX_BODY_WORDS
    try:
        want = int(want)
    except (TypeError, ValueError):
        want = MAX_BODY_WORDS
    return max(MIN_LETTER_WORDS, min(MAX_BODY_WORDS, want))


def body_words(a):
    """Words the candidate actually wrote: the four blocks plus the bullets,
    labels included (the label is printed, so the reader reads it). This is
    the one body count; audit_letters imports it rather than keeping its own."""
    # Count every prose field the letter carries, not a fixed four.
    #
    # This listed p1, p2, lead and p4 by name. Real letters render five and six
    # prose blocks, so an entire paragraph was invisible to the trim loop: a
    # letter could measure 294 words here and 397 on the page. The 250-word cap
    # was being enforced against a number that was never the number on the
    # page, which is exactly the "word count wrong" that then had to be fixed
    # by hand.
    #
    # Anything that looks like a paragraph counts. A new field added to the
    # application object gets counted automatically rather than silently
    # escaping the cap.
    # `concession` is not counted: build() never renders it (it is the
    # drafter's note about where a concession sits), and counting it made the
    # trimmer cut real sentences to pay for words no reader sees.
    # Only what the letter renders. The template places p1, p2, lead and p4; a
    # p3 counted here was never on the page, and the trimmer cut real sentences
    # from p1 to pay for it. render_application.check_batch refuses a draft
    # carrying a prose field the template cannot place.
    keys = [k for k in RENDERED_PROSE if isinstance(a.get(k), str)]
    parts = [a.get(k, "") for k in keys]
    parts += [f"{b.get('label','')} {b.get('text','')}" for b in a.get("cl_bullets", [])]
    txt = " ".join(parts)
    txt = re.sub(r"\\[a-zA-Z]+\{?|\}|\\%|\\\$", "", txt)
    return len(txt.split())


def _scores(a):
    return allocate.bullet_scores(a.get("posting", "") or a.get("role", ""))


def _employer(j):
    return j["employer"]


def grow_resume(a, caps=None, skip=()):
    """Add back the strongest absent bullet for THIS posting that fits the caps.

    The loop below only ever removed content, so a resume trimmed by one line
    stayed a bullet short of the page for good. Growth is by score, not by
    employer position: on a pricing posting the next bullet in comes from one
    role, on a product posting from another. `skip` holds what the
    trimmer already removed this run; offering it back is a guaranteed
    overflow. `caps` is computed once per fit, not once per call.
    """
    scores = _scores(a)
    caps = caps or allocate.caps_for(a.get("posting", ""))
    have = {b for j in a["jobs"] for b in j["bullets"]}
    blocked = set(skip)
    for b in have:
        blocked |= R.CONFLICTS.get(b, set())
    cands = []
    for j in a["jobs"]:
        e = _employer(j)
        if len(j["bullets"]) >= caps[e]:
            continue
        for b in LIB.LIB[e]:
            if b not in have and b not in blocked:
                cands.append((scores[b], b, j))
    if not cands:
        return None
    _, b, j = max(cands)
    j["bullets"].append(b)
    return b


def trim_resume(a):
    """Remove the weakest bullet for THIS posting, honouring every floor.

    Returns the bullet id removed, "tools" when the tools line was shortened
    instead, or None when nothing more can come off.

    A cut that leaves an employer one line keeps the line `allocate._pick`
    would give it alone, not whichever survived. Removing the globally weakest
    bullet took the one that best describes the job (it scores lowest on a
    posting about something else) and left a sharper line as the role's whole
    description, which the allocator's sole-bullet rule exists to prevent.
    """
    scores = _scores(a)
    cands = [(scores[b], b, j) for j in a["jobs"]
             if len(j["bullets"]) > allocate.FLOOR[_employer(j)]
             for b in j["bullets"]]
    if cands:
        _, b, j = min(cands)
        before = list(j["bullets"])
        j["bullets"].remove(b)
        if len(j["bullets"]) == 1:
            taken = {x for o in a["jobs"] if o is not j for x in o["bullets"]}
            j["bullets"] = allocate._pick(_employer(j), 1, scores, taken) or j["bullets"]
        gone = [x for x in before if x not in j["bullets"]]
        return gone[0] if gone else b
    # Everyone is at floor; shorten the tools line instead.
    parts = [p.strip() for p in a.get("tools", "").split(",")]
    if len(parts) > 8:
        a["tools"] = ", ".join(parts[:-3])
        return "tools"
    return None


def shorten(text, budget):
    """Drop whole trailing sentences until under budget. Never cuts mid-sentence."""
    sents = R.split_sentences(text)
    while len(" ".join(sents).split()) > budget and len(sents) > 1:
        sents.pop()
    return " ".join(sents)


def shorten_close(text, budget, keep=()):
    """Shorten the close without losing what it is for. Its last sentence is the one
    written for this role, and the sentences saying where the candidate is and their
    right to work (the claim map's LOC and AUTH sentences, `keep`; the first sentence when
    there is no claim map) are the same in every letter. Dropping from the end, as
    `shorten` does, left the shared sentence as the letter's closing: the one rule 9 says
    no two letters may have, and a close the person's rule says ends on this role. Only a
    sentence that is neither goes, from the one before the last backwards."""
    sents = R.split_sentences(text)
    norm = [" ".join(x.lower().split()) for x in sents]
    # Kept by place, not by wording: kept by wording, every sentence worded like a kept one
    # was kept too, and a close repeating one line could not be cut at all.
    wanted = [" ".join(str(k).lower().split()) for k in keep]
    held = {norm.index(w) for w in wanted if w in norm} or ({0} if sents else set())
    alive = list(range(len(sents)))
    i = len(sents) - 2
    while len(" ".join(sents[j] for j in alive).split()) > budget and i >= 0:
        if i not in held:
            alive.remove(i)
        i -= 1
    return " ".join(sents[j] for j in alive)


def _close_keeps(a) -> list:
    """The close's sentences that say where the candidate is and their right to work."""
    return [c.get("sentence", "") for c in a.get("claim_map") or [] if isinstance(c, dict)
            and str(c.get("field")) == "p4" and {"LOC", "AUTH"} & set(c.get("cites") or [])]


def _try(a, key, budget, cut=None):
    """Shorten a field only if sentence removal actually changes it.

    shorten() drops whole trailing sentences, so a single long sentence comes
    back unchanged. Returning True on a no-op made the fit loop spin without
    progress until it hit its iteration cap, which is why letters stayed long
    while reporting that trimming had run.
    """
    before = a[key] if isinstance(key, str) else key["text"]
    after = (cut or shorten)(before, budget)
    if after == before:
        return False
    if isinstance(key, str):
        a[key] = after
    else:
        key["text"] = after
    return True


def trim_letter(a, over, page_over=True):
    """Cut in the order 06-cover-letter-templates.md gives, which ends at p2.

    That file's "How to cut, in order" is: the second sentence of any bullet,
    any bullet duplicating the resume, adjectives and scene-setting, a fourth
    bullet. Then: "Never cut the company-specific paragraph to make room."

    p2 is that paragraph. It carried the one fact about the employer that was
    independently verified, and `outreach.py` reads its first sentence as the
    fact the LinkedIn note is built on. It was being cut first, ahead of the
    bullets and the closing, so the cheapest thing to lose was the only thing
    in the letter that could not be written without doing the research.

    It is still reachable, last and only when nothing else got the letter onto
    the page, because a letter that overflows is not delivered at all.

    Any extra paragraph (p3 and beyond) is trimmed before p1, because a letter
    that grew a fifth prose block is long for that reason. This used to trim a
    fixed four fields, so an extra paragraph could not be cut at all and the
    loop would spin to its iteration cap and give up with the letter still
    over. Letters were undercounted, and some were also untrimmable.
    """
    for b in a["cl_bullets"]:
        if len(b["text"].split()) > 22 and _try(a, b, 20):
            return True
    keeps = _close_keeps(a)
    if len(a["p4"].split()) > 35 and _try(a, "p4", max(30, len(a["p4"].split()) - over),
                                          cut=lambda t, b: shorten_close(t, b, keeps)):
        return True
    extras = sorted(k for k in a
                    if re.fullmatch(r"p\d+", k) and k not in ("p1", "p2", "p4")
                    and isinstance(a.get(k), str))
    for k in extras:
        if len(a[k].split()) > 40 and _try(a, k, max(35, len(a[k].split()) - over)):
            return True
    # p1 and p2 are cut only to get the letter onto one page. Over the word cap
    # on a letter that already fits, cutting p1 removed its last sentence (who
    # the candidate is and what they want, the point of the paragraph) from a
    # letter with a third of the page empty. Over the cap and on the page, the
    # report flags it instead.
    if not page_over:
        return False
    if len(a["p1"].split()) > 45 and _try(a, "p1", 42):
        return True
    # Last. See above: losing the researched paragraph beats losing the page.
    if len(a["p2"].split()) > 45 and _try(a, "p2", max(40, len(a["p2"].split()) - over)):
        return True
    return False


def _render_resume(a):
    R.resume(R.build(a))
    return compile_resume(a["abbr"])


def _render_letter(a):
    R.letter(R.build(a))
    return compile_letter(a["abbr"])


def fit(a):
    """Returns ((resume_pages, resume_lines), letter_pages), each the last
    measurement of the document that is on disk when this returns."""
    # The name build() writes under, settled before the first render. Read
    # from the draft as supplied, a hand-written abbr ("FF") was the name the
    # final compile looked for after build() had written the derived one, and
    # the whole fit ended in CompileFailed; a draft with none was a KeyError.
    abbr = a["abbr"] = R.final_abbr(a)
    R.jobs_for(a)                                   # dedupe + order before any cap reasoning
    caps = allocate.caps_for(a.get("posting", ""))  # once per fit
    trimmed = set()
    pages = _render_resume(a)
    for _ in range(9):
        if pages <= PAGES:
            break
        before = {b for j in a["jobs"] for b in j["bullets"]}
        if not trim_resume(a):
            break
        # Everything that came off, which is more than one bullet when a sole
        # line was swapped for the one that describes the job.
        trimmed |= before - {b for j in a["jobs"] for b in j["bullets"]}
        pages = _render_resume(a)
    # A design too big for what must stay on the page (every role at its floor) is made a
    # step smaller, never past a setting's bound, rather than left on two pages. The
    # template has no step: it is fitted by its bullets alone, as it always was.
    while pages > PAGES and R.gen.doc_design.step_down(R.build(a)["design"]) is not None:
        a["design_step"] = int(a.get("design_step") or 0) + 1
        pages = _render_resume(a)
    # Fill the page. Add a bullet, recompile, and keep it only if the resume is
    # still within its pages; otherwise put the page back the way it was and stop.
    # "Leave some space" (Tweak R7): the page is not filled back up to its last line.
    fill = str(a.get("fill") or person.get("documents.fill", "") or "fuller")
    for _ in range(0 if fill == "space" else 8):
        if pages > PAGES:
            break
        snapshot = [list(j["bullets"]) for j in a["jobs"]]
        if not grow_resume(a, caps, skip=trimmed):
            break
        grown = _render_resume(a)
        if grown > PAGES:
            # snapshot is taken from a["jobs"], so a length mismatch is a
            # bug, and silently dropping a job's bullets is the quiet kind
            # that ships. Checked by hand: zip's strict keyword is Python 3.10+.
            if len(a["jobs"]) != len(snapshot):
                raise ValueError("fit_to_page: the bullet snapshot lost a job")
            for j, b in zip(a["jobs"], snapshot):  # noqa: B905
                j["bullets"] = b
            pages = _render_resume(a)   # the PDF on disk must match the draft
            break
        pages = grown
    if a.get("general"):
        # A resume for no posting in particular has no letter (tools/general_resume.py).
        pages = compile_resume(abbr, passes=2)
        fonts = font_problems(resume_pdf(abbr))
        if fonts:
            raise CompileFailed("; ".join(fonts) + ". Use fonts the template embeds (the ones "
                                "it ships with), then render again.")
        return (pages, _lines(resume_pdf(abbr))), 0
    lpages = _render_letter(a)
    most = letter_words(a)
    for _ in range(9):
        words = body_words(a)
        if lpages <= 1 and words <= most:
            break
        if not trim_letter(a, max(8, words - most), page_over=lpages > 1):
            break
        lpages = _render_letter(a)
    # Settle the page reference in the footer now that the layout is final.
    pages = compile_resume(abbr, passes=2)
    fonts = font_problems(resume_pdf(abbr)) + font_problems(letter_pdf(abbr))
    if fonts:
        raise CompileFailed("; ".join(fonts) + ". Use fonts the template embeds (the ones it "
                            "ships with), then render again.")
    return (pages, _lines(resume_pdf(abbr))), lpages


def unheld_report(a):
    """What the draft and its posting ask for that the profile does not hold.

    `skills_block.select()` drops an unheld skill from the tools line silently,
    which is right for the page and wrong for the person: a drafter who asked
    for one wrote a claim, and a posting that names one has a real gap, which
    the letter must bridge (tools/bridges.py) or leave alone, unless the person said yes
    to it for this application (tools/stage_picks.py consent).
    """
    out = []
    # A skill the person said yes to for this posting is theirs to claim, and on the page.
    yes = [str(x) for x in a.get("consented_skills") or []]

    def theirs(k):
        return any(re.search(skills_block.NOT_HELD[k][0], y, re.I) for y in yes)
    asked = {k: v for k, v in skills_block.unheld_requested(a.get("tools", "")).items()
             if not theirs(k)}
    if yes:
        out.append("on the page with the person's yes: " + ", ".join(yes))
    if asked:
        out.append("tools line asked for skills not held, left off: "
                   + "; ".join(f"{k} ({v})" for k, v in asked.items()))
    gaps = {k: v for k, v in skills_block.unheld_requested(a.get("posting", "")).items()
            if k not in asked and not theirs(k)}
    if gaps:
        out.append("the posting names skills not held, and the person said no or was not asked: "
                   + ", ".join(gaps))
    return out


def needs_check(resume_pages, letter_pages, words, general=False):
    """Whether a fitted application is outside its budgets: the resume off the
    profile's page count, the letter off one page, or the body over its cap. A
    general resume (no letter) is held to its pages alone.

    It was `resume_pages == 1`, so every application of a person whose profile
    asks for two pages was flagged CHECK however well it fitted."""
    if general:
        return not 1 <= resume_pages <= PAGES
    return not (1 <= resume_pages <= PAGES and letter_pages == 1 and words <= MAX_BODY_WORDS)


def load(path):
    """The drafts in `path`, and which of them had their posting read in.

    A kept draft (`documents/applications/<slug>/draft.json`, written by
    `tools/outreach.py`) names its posting instead of carrying it, because
    committed posting text lives only inside the untrusted fence in
    `job_posting.md`. It is read back through that fence here.
    """
    with open(path, encoding="utf-8") as fh:
        apps = json.load(fh)
    here = os.path.dirname(os.path.abspath(path))
    read_in = set()
    for i, a in enumerate(apps):
        if "posting" in a or not a.get("posting_from"):
            continue
        with open(os.path.join(here, a["posting_from"]), encoding="utf-8") as fh:
            text = fh.read()
        posting = untrusted.unfence(text)
        if posting == text:
            raise SystemExit(f"{a['posting_from']} has no untrusted fence; not reading it")
        a["posting"] = posting
        read_in.add(i)
    return apps, read_in


def save(path, apps, read_in):
    """Write the drafts back, never with a posting that arrived fenced."""
    out = [{k: v for k, v in a.items() if not (i in read_in and k == "posting")}
           for i, a in enumerate(apps)]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("usage: python3 tools/fit_to_page.py <drafts.json | documents/applications/<slug>/draft.json>\n\n" + __doc__.strip().split("\n\n")[0])
        sys.exit(0 if len(sys.argv) > 1 else 2)
    apps, read_in = load(sys.argv[1])
    # Refuse the whole batch before the first compile, so a name that belongs
    # to another application never gets half a batch rendered over it.
    R.check_batch(apps)
    for a in apps:
        try:
            (rp, rl), lp = fit(a)
        except CompileFailed as exc:
            print(f"fit_to_page: {a.get('abbr') or a.get('company')}: {exc}", file=sys.stderr)
            sys.exit(1)
        if a.get("general"):
            flag = "   <-- CHECK" if needs_check(rp, lp, 0, general=True) else ""
            print(f"{a['abbr']:<12} resume {rp}p/{rl}ln  no letter (a general resume){flag}")
            continue
        bw = body_words(a)
        flag = "   <-- CHECK" if needs_check(rp, lp, bw) else ""
        print(f"{a['abbr']:<12} resume {rp}p/{rl}ln  letter {lp}p/{bw} body words{flag}")
        for line in unheld_report(a):
            print("             " + line)
    save(sys.argv[1], apps, read_in)
