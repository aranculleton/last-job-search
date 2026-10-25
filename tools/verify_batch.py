#!/usr/bin/env python3
"""Verify every rendered application in a drafts.json: the resume within the
profile's page count (documents.resume_pages, default 1), a one-page letter, chronology,
bullets per employer, clean text layer (pypdf, which also catches words run together),
contact details, every line of the draft in the text layer in order (the round trip),
the pinned skill, no parentheses in the skills block, no duplicated bullets. Then
claims and letters.

    python3 tools/verify_batch.py rounds/r1/drafts.json
    tools/verify_batch.sh rounds/r1/drafts.json           # the same, by its old name

Exit 0 all pass, 1 a finding, 3 nothing failed but the spacing check was
skipped because pypdf is unavailable (which is not a pass).

Everything about the person (the filename prefix, the employers in resume
order with their column codes and minimum bullets, the email and phone the
text layer must carry, the pinned skill, the section headings, the document
noun the market does not use) comes from the profile via tools/docpaths.py.

It was a bash script that read every PDF with Poppler's pdftotext and pdfinfo, which a
Mac has only through Homebrew and Windows only through winget, and whose sed and awk
read differently on a Mac than on Linux. The checks are the same ones, in the same
order, with the same flags and exit codes, read with pypdf (tools/pdftext.py): plain
pypdf text starts every line at column 0, as `pdftotext -layout` did for each line a
check reads.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)

import docpaths  # noqa: E402
import pdftext  # noqa: E402
import person  # noqa: E402
from audit_letters import duplicate_bullets, resume_bullets, shared_runs  # noqa: E402

PY = sys.executable
BULLET = re.compile(r"^ *•")


def sed_range(lines, start, end, drop_end=False):
    """The lines `sed -n "/^start/,/^end/p"` prints: from each line beginning with
    `start` to the next line beginning with `end`, inclusive (the end is looked for from
    the line after the start, as sed does), as often as a start comes round again.
    `drop_end` leaves out the lines that begin with `end`, as `{/^end/d;p;}` did."""
    s = re.compile("^" + re.escape(start))
    e = re.compile("^" + re.escape(end))
    out, inside = [], False
    for line in lines:
        if not inside:
            if s.search(line):
                inside = True
                if not (drop_end and e.search(line)):
                    out.append(line)
            continue
        if not (drop_end and e.search(line)):
            out.append(line)
        if e.search(line):
            inside = False
    return out


def role_order(lines, names, experience, education):
    """The employers as their sections open between Experience and Education, each
    followed by ">", as `grep -oE "^(A|B)" | tr '\\n' '>'` gave it. Longest name first:
    grep's alternation takes the longest match, Python's the first."""
    alt = re.compile("^(" + "|".join(re.escape(n) for n in
                                      sorted(names, key=len, reverse=True)) + ")")
    got = []
    for line in sed_range(lines, experience, education):
        m = alt.search(line)
        if m:
            got.append(m.group(1))
    return "".join(g + ">" for g in got)


def bullets_per_role(lines, names, education):
    """Bullets counted under each employer, "n/n/n" in profile order, as the awk program
    did: a line opening with an employer starts its count, Education stops counting."""
    rx = [re.compile("^" + re.escape(n)) for n in names]
    edu = re.compile("^" + re.escape(education))
    n: dict = {}
    e = ""
    for line in lines:
        for i, r in enumerate(rx):
            if r.search(line):
                e = str(i)
        if edu.search(line):
            e = ""
        if BULLET.search(line):
            n[e] = n.get(e, 0) + 1
    return "/".join(str(n.get(str(i), 0)) for i in range(len(names)))


def section_layout(tex_path, want):
    """The section layout, read off the .tex where it is exact rather than off the
    rendered text where a heading can wrap. Resumes written before the generator
    carried Core Competencies with no Summary at all, and only COMPETENCIES was ever
    checked, so a missing Summary, a merged "Education and Certifications" and a wrong
    section order all passed."""
    try:
        with open(tex_path, encoding="utf-8", errors="replace") as fh:
            secs = re.findall(r"\\section\{([^}]*)\}", fh.read())
    except OSError:
        return ""
    out = []
    if any(re.search(r"education.*certif|certif.*education", x, re.I) for x in secs):
        out.append("MERGED_EDU_CERT")
    if not any(x.strip().lower() == want[0].lower() for x in secs):
        out.append("NO_SUMMARY")
    if [x.strip() for x in secs] != want:
        out.append("SECTION_ORDER")
    return " ".join(out)


def _run3(args):
    """(exit code, stdout, stderr) of one of the app's tools."""
    p = subprocess.run([PY, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", stdin=subprocess.DEVNULL)
    return p.returncode, p.stdout or "", p.stderr or ""


def _run(args):
    """(exit code, stdout and stderr together) of one of the app's tools."""
    code, out, err = _run3(args)
    return code, out + err


def _say(text):
    if text:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip().split("\n\n")[1])
        return 0 if argv else 2
    drafts = argv[0]
    try:
        v = docpaths.values()
        roles = person.module("roles").ROLES
    except Exception:  # noqa: BLE001  any profile it cannot read is the one answer
        print("verify_batch: cannot read the profile")
        return 1
    if not pdftext.reader():
        print("verify_batch: nothing here can read a PDF: the Python package pypdf is "
              "missing. `python3 tools/env_check.py --fix` installs it")
        return 1
    with open(drafts, encoding="utf-8") as fh:
        batch = json.load(fh)
    abbrs = [a["abbr"] for a in batch]
    # A general resume has no letter (tools/general_resume.py): its letter checks are skipped.
    general = {a["abbr"] for a in batch if a.get("general")}
    names = [r["employer"] for r in roles]
    want = json.loads(v["SECTIONS"])
    pages_allowed = int(v["RESUME_PAGES"])
    banned = (re.compile(r"\b(" + "|".join(re.escape(n) for n in
                                          person.get("documents.banned_nouns", [])) + r")\b",
                         re.I) if v["BANNED_NOUNS"] else None)
    mins = [(int(i), int(m), short) for i, m, short in
            (x.split(":", 2) for x in v["ROLE_MINS"].split())]

    fail = tb = n = skipped = 0
    readers: list = []
    _say("%-9s %-4s %-4s %-14s %s" % ("ABBR", "pgs", "blt", v["ROLE_HEADER"], "flags"))
    for a in abbrs:
        r_pdf = docpaths.resume_pdf(a)
        c_pdf = None if a in general else docpaths.letter_pdf(a)
        if not (os.path.isfile(r_pdf) and (c_pdf is None or os.path.isfile(c_pdf))):
            _say(f"{a} MISSING PDF")
            fail = 1
            continue
        try:
            rt_text = pdftext.text(r_pdf)
            ct_text = pdftext.text(c_pdf) if c_pdf else ""
        except pdftext.Unreadable as exc:
            _say(f"{a} UNREADABLE PDF ({exc})")
            fail = 1
            continue
        r_lines = rt_text.splitlines()
        flat = re.sub(" +", " ", rt_text.replace("\n", " "))
        p = ""
        rp = pdftext.pages(r_pdf)
        cp = pdftext.pages(c_pdf) if c_pdf else None
        rp_s = "" if rp is None else str(rp)
        cp_s = "-" if not c_pdf else ("" if cp is None else str(cp))
        if not (rp is not None and 1 <= rp <= pages_allowed):
            p += f" RESUME_{rp_s}p"
        if c_pdf and cp != 1:
            p += f" LETTER_{cp_s}p"
        if role_order(r_lines, names, v["H_EXPERIENCE"], v["H_EDUCATION"]) != v["ROLE_ORDER"]:
            p += " CHRONO"
        if "Core Competencies" in rt_text:
            p += " COMPETENCIES"
        lay = section_layout(docpaths.resume_tex(a), want)
        if lay:
            p += " " + lay
        if re.search("—|–", rt_text + "\n" + ct_text):
            p += " DASH"
        if re.search(r"cid:|\ufffd|::|MOBILE-ALT|Envelope", rt_text):
            p += " TEXTLAYER"
        # The letter's text layer too: a sign its font lacks prints as a replacement
        # character, and only the resume was ever read for one.
        if re.search(r"cid:|\ufffd", ct_text):
            p += " TEXTLAYER_LETTER"
        # Only pypdf catches words run together: pdftotext infers spaces from glyph
        # positions, so a fallback to it passed them without a word. So pypdf is
        # required; exit 3 means it is unavailable, the rest of the text-layer check runs
        # on pdftotext, and the batch says the spacing check was SKIPPED.
        said = []
        for pdf, flag in ((r_pdf, "SPACING_RESUME"), (c_pdf, "SPACING_LETTER")):
            if not pdf:
                continue
            st, out = _run([os.path.join(TOOLS, "verify_pdf.py"), "--require", "pypdf", pdf])
            if st == 3:
                skipped = 1
                st, out = _run([os.path.join(TOOLS, "verify_pdf.py"), pdf])
                if st != 0:
                    p += " " + flag
            elif st != 0:
                p += " " + flag
            said.append(out)
        readers += re.findall(r"extractor: ([a-z]+)", "\n".join(said))
        # The design's rules, read off each PDF: its page size, one page, no text too small,
        # nothing at the page's edge where parsers drop headers and footers, one column
        # (tools/design_check.py).
        for pdf, flag in ((r_pdf, "DESIGN_RESUME"), (c_pdf, "DESIGN_LETTER")):
            if pdf and _run([os.path.join(TOOLS, "design_check.py"), pdf, "--for", drafts,
                             "--abbr", a])[0] != 0:
                p += " " + flag
        if not (v["EMAIL"] in flat and v["PHONE"] in flat):
            p += " CONTACT"
        # The round trip: every line the draft put on the page (contacts, headings, the
        # summary, each role's heading line and bullets, each skills line, education,
        # certifications) must be in the text layer, in order. A swallowed % or a glyph
        # the font lacks passed every check above; this names the line it broke.
        st, rt = _run([os.path.join(TOOLS, "verify_pdf.py"), r_pdf, "--roundtrip", drafts,
                       "--abbr", a])
        if st != 0:
            p += " ROUNDTRIP"
        if v["PINNED"] and v["PINNED"] not in flat:
            p += " NO_PINNED_SKILL"
        # Skills sits between Professional Experience and Education.
        if any(re.search(r"[()]", line) for line in
               sed_range(r_lines, v["H_SKILLS"], v["H_EDUCATION"], drop_end=True)):
            p += " SKILLPARENS"
        if banned and (banned.search(rt_text) or banned.search(ct_text)):
            p += " " + v["BANNED_FLAG"]
        # Six words in a row shared by two bullets (audit_letters.shared_runs, which also
        # reads each letter's bullets against the resume's), and a bullet on the page
        # twice, read as whole bullets however a reader places the marks.
        bul = resume_bullets(rt_text, v["H_EXPERIENCE"], v["H_EDUCATION"])
        shared, dups = len(shared_runs(bul)), len(duplicate_bullets(bul))
        if dups:
            p += " DUPBULLET"
        if shared:
            p += f" SHARED_PHRASE({shared})"
        cnt = bullets_per_role(r_lines, names, v["H_EDUCATION"])
        # A role the profile gives a verify_min must carry at least that many.
        got = cnt.split("/")
        for i, m, short in mins:
            if int(got[i]) < m:
                p += f" {short}_LT_{m}"
        b = sum(1 for line in r_lines if BULLET.search(line))
        tb += b
        n += 1
        _say("%-9s %s/%s  %-4s %-14s %s" % (a, rp_s, cp_s, b, cnt, p))
        if " ROUNDTRIP" in p:
            _say("\n".join("          " + line for line in rt.splitlines()))
        if p:
            fail = 1
    _say(f"mean bullets: {tb // n if n else 0}")
    used = " ".join(sorted(set(readers)))
    if "pdftotext" in used.split():
        _say(f"text layer read with: {used or 'nothing'} (pdftotext fallback: "
             "words run together are NOT caught; "
             "python3 tools/env_check.py --fix installs pypdf, or "
             "pip3 install --upgrade cffi if it is installed and panics)")
    else:
        _say(f"text layer read with: {used or 'nothing'}")
    resumes = [docpaths.resume_tex(a) for a in abbrs]
    letters = [docpaths.letter_tex(a) for a in abbrs if a not in general]
    _say("=== claims ===")
    # Its findings and its own exit status: a failing check once hid behind a pipe's.
    st, out = _run([os.path.join(TOOLS, "check_claims.py"),
                    *[x for a in abbrs for x in ((docpaths.resume_tex(a),) if a in general
                      else (docpaths.resume_tex(a), docpaths.letter_tex(a)))]])
    _say("\n".join([line for line in out.splitlines()
                    if re.search(r"^[0-9]+ error|ERROR", line)][:10]))
    if st != 0:
        _say("CLAIMS: FAILURES ABOVE")
        fail = 1
    _say("=== letters ===")
    # The flagged letters are the output worth having, not only the count.
    st, out, err = _run3([os.path.join(TOOLS, "audit_letters.py"), drafts])
    _say("\n".join(line for line in out.splitlines() if re.search(r"^!!|letters clean", line)))
    if err:
        sys.stderr.write(err)       # what stopped it, whole: a missing letter, a traceback
    if st != 0:
        _say("LETTERS: FAILURES ABOVE")
        fail = 1
    _say("=== numbers ===")
    # check_claims.py catches errors the grounding reviewer already found. It cannot
    # catch a metric nobody has invented yet, and SECURITY.md ranks a fabricated claim
    # reaching an employer as the worst thing this system can do: every number in the
    # resume must exist in the profile. The letters are read from the drafts, not the
    # .tex, because only the draft knows which paragraph holds a verified company fact.
    st, out = _run([os.path.join(TOOLS, "check_numbers.py"), "--drafts", drafts, *resumes])
    _say(out)
    if st != 0:
        _say("NUMBERS: FAILURES ABOVE")
        fail = 1
    _say("=== keywords (a report: nothing here fails the batch or changes a document) ===")
    # What the posting names against what the page carries. A skill the profile does not
    # hold is listed as not held, never as one to add.
    for a in abbrs:
        _st, out = _run([os.path.join(TOOLS, "verify_pdf.py"), docpaths.resume_pdf(a),
                         "--keywords", drafts, "--abbr", a])
        _say("\n".join(f"{a}: {line}" for line in out.splitlines()))
    _say("=== voice ===")
    # Soft findings are a smell and do not fail the batch; hard ones do.
    if letters:
        st, out = _run([os.path.join(TOOLS, "voice_check.py"), "--soft-ok", *letters])
        _say(out)
        if st != 0:
            _say("VOICE: FAILURES ABOVE")
            fail = 1
    else:
        _say("no letters: a general resume")
    if skipped:
        _say("=== SPACING CHECK SKIPPED ===")
        _say("pypdf is not available, so words run together were NOT checked on any document.")
        _say("python3 tools/env_check.py --fix installs it (or pip3 install --upgrade cffi if "
             "it is installed and panics); then run this again.")
    if fail:
        _say("BATCH: FAILURES ABOVE")
        return 1
    if skipped:
        _say("BATCH: NOT ALL PASS, the spacing check was SKIPPED")
        return 3
    _say("BATCH: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
