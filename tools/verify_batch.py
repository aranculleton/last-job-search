#!/usr/bin/env python3
"""Verify every rendered application in a drafts.json: the resume within the
profile's page count (documents.resume_pages, default 1), a one-page letter, chronology,
bullets per employer, clean text layer (pypdf, which also catches words run together),
contact details, every line of the draft in the text layer in order (the round trip),
the pinned skill, no parentheses in the skills block, no duplicated bullets. Then
claims and letters.

    python3 tools/verify_batch.py rounds/r1/drafts.json
    tools/verify_batch.sh rounds/r1/drafts.json           # the same, by its old name

Exit 0 all pass, 1 a finding, 3 nothing failed but the spacing check or the design check
was skipped because pypdf is unavailable (which is not a pass).

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
    `drop_end` leaves out the lines that begin with `end`, as `{/^end/d;p;}` did. No `end`
    reads to the last line (the section is the page's last)."""
    s = re.compile("^" + re.escape(start))
    e = re.compile("^" + re.escape(end)) if end else re.compile(r"(?!x)x")
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


def next_heading(want, heading):
    """The heading of the section after `heading` on the page (documents.section_order), or
    "" when it is the last. Every range here ran to Education, which a profile that puts
    Education first has above Skills: the Skills range then ran to the foot of the page and
    read a certification's "(2024)" as a parenthesis on the skills line."""
    try:
        i = [w.strip().lower() for w in want].index(heading.strip().lower())
    except ValueError:
        return ""
    return want[i + 1] if i + 1 < len(want) else ""


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
    did: a line opening with an employer starts its count, `education` (the heading after
    Experience) stops counting. The longest name a line opens with is its employer: with
    "Acme" and "Acme Labs" both employers, every Acme Labs line was counted as Acme's."""
    order = sorted(range(len(names)), key=lambda i: len(names[i]), reverse=True)
    rx = [(i, re.compile("^" + re.escape(names[i]))) for i in order]
    edu = re.compile("^" + re.escape(education)) if education else re.compile(r"(?!x)x")
    n: dict = {}
    e = ""
    # Two roles at one employer open with the same name: the k-th time it opens is the k-th
    # role of that name, in profile order.
    opened: dict = {}
    for line in lines:
        hit = next((i for i, r in rx if r.search(line)), None)
        if hit is not None:
            same = [j for j in range(len(names)) if names[j] == names[hit]]
            k = opened.get(names[hit], 0)
            opened[names[hit]] = k + 1
            e = str(same[min(k, len(same) - 1)])
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
            # A heading's own escapes ("Skills \& Tools") are the words it prints.
            from verify_pdf import tex_plain
            secs = [tex_plain(x) for x in
                    re.findall(r"\\section\{((?:[^{}\\]|\\.)*)\}", fh.read())]
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


def _unaudited(entry: dict) -> list:
    """[(field, sentence)] for each sentence of the draft that no claim-map entry holds (a
    part of one is held: the renderer cuts a long summary at a clause), or [] when the draft
    carries no claim map (a general resume, a draft from before the map)."""
    cm = [c for c in entry.get("claim_map") or [] if isinstance(c, dict)]
    if not cm:
        return []
    import draft_audit
    have = [h for h in (draft_audit._norm(c.get("sentence", "")) for c in cm) if h]
    out = []
    for field, sentence in draft_audit.field_sentences(entry):
        if field == "outreach_body":
            continue
        want = draft_audit._norm(sentence)
        if want and not any(want in h for h in have):
            out.append((field, sentence))
    return out


def _batch_flags(abbr: str, entry: dict, general: bool, loaded: dict | None = None,
                 batch=()) -> list:
    """The whole-batch checks, read for one application's documents: CLAIMS for an error
    check_claims.py finds in its resume or letter, NUMBERS for a figure check_numbers.py
    cannot ground in its resume, letter or summary, LETTERS for a rule its letter breaks
    (tools/audit_letters.py) and VOICE for wording its letter must never carry. Read here,
    in this process, so each application's record carries its own; a check that cannot
    run says nothing."""
    out = []
    try:
        import check_claims
        paths = [docpaths.resume_tex(abbr)] + ([] if general else [docpaths.letter_tex(abbr)])
        if any(sev == "ERROR" for path in paths if os.path.isfile(path)
               for sev, *_rest in check_claims.check(path)):
            out.append("CLAIMS")
    except Exception:  # noqa: BLE001
        pass
    try:
        import check_numbers
        found = check_numbers.check_draft(entry) if entry else []
        tex = docpaths.resume_tex(abbr)
        if os.path.isfile(tex):
            with open(tex, encoding="utf-8") as fh:
                found += check_numbers.check(fh.read(), tex)
        if found:
            out.append("NUMBERS")
    except Exception:  # noqa: BLE001
        pass
    if general:
        return out
    # The letter's own checks, read for this letter: they failed the whole batch and left
    # "flags": [] on the application, so a letter copying the posting was recorded as passing
    # and a rerun of the drafts took it as made (the maintainer, 2026-11-05). `loaded` is
    # the draft with its posting, read back as the letters check reads it.
    try:
        import remake_drafts
        d = loaded if isinstance(loaded, dict) and loaded else entry
        if remake_drafts.letter_flags(d, batch):
            out.append("LETTERS")
    except Exception:  # noqa: BLE001
        pass
    tex = docpaths.letter_tex(abbr)
    if os.path.isfile(tex) and _run([os.path.join(TOOLS, "voice_check.py"), "--soft-ok",
                                     tex])[0] != 0:
        out.append("VOICE")
    return out


def _role_keys(roles) -> list:
    """Each role's key into the allocator's caps (allocate.role_keys): two titles at one
    employer are two roles with caps of their own."""
    try:
        import allocate
        return allocate.role_keys(roles)
    except Exception:  # noqa: BLE001  no allocator to read: the employer, as it was
        return [r["employer"] for r in roles]


def _caps(entry: dict) -> dict:
    """{employer: the most bullets it may carry} for this draft's posting, or {} when the
    allocator cannot be read (a profile with no bullets for it)."""
    # Without the posting a cap_unless cannot be read, and every role would be held to its
    # lower cap: nothing is read then, rather than a false finding.
    if not str(entry.get("posting") or "").strip():
        return {}
    try:
        import allocate
        return allocate.caps_for(str(entry.get("posting") or ""))
    except Exception:  # noqa: BLE001  no caps known is no cap read, never a crash
        return {}


def _run3(args):
    """(exit code, stdout, stderr) of one of the app's tools."""
    p = subprocess.run([PY, *args], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", stdin=subprocess.DEVNULL)
    return p.returncode, p.stdout or "", p.stderr or ""


def _entry(batch, abbr) -> dict:
    return next((x for x in batch if x.get("abbr") == abbr), {})


# What the fit left on a draft whose short last page nothing could take back
# (fit_to_page.THIN_KEPT), or that the person left as space (THIN_SPACE), and how it is said.
THIN_NOTES = {
    "kept": "its last page is short: every job is already at its fewest lines, so it cannot "
            "go onto one page fewer, and nothing true is left to fill it",
    "space": "its last page is short, which is the space you asked to leave",
}


def _thin_kept(entry: dict, found: str) -> str:
    """The note for a layout finding that is only a short last page the fit has already
    settled, or "" when it is to fail: a heading left at the foot, or a short last page the
    fit never tried."""
    lines = [x.strip() for x in found.splitlines() if x.strip().startswith(
        ("THIN_LAST_PAGE", "HEADING_AT_FOOT"))]
    if not lines or any(not x.startswith("THIN_LAST_PAGE") for x in lines):
        return ""
    return THIN_NOTES.get(str(entry.get("thin_end") or ""), "")


def _run(args):
    """(exit code, stdout and stderr together) of one of the app's tools."""
    code, out, err = _run3(args)
    return code, out + err


def _say(text):
    if text:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    sys.stdout.flush()


def _drafts_version() -> int:
    """The drafts method's version these checks ran under (tools/build_versions.py)."""
    try:
        import build_versions
        return build_versions.current("drafts")
    except Exception:  # noqa: BLE001  no version known: 0, never checked by it
        return 0


def _record(entry: dict, flags: list, resume_pages, letter_pages, letter: bool,
            checked: bool = True) -> None:
    """This application's checks, kept beside it as verify.json for the page's "the checks
    that ran" (FUNCTIONS_SPEC 1.3): each flag this run raised, the pages, the day, the
    drafts version it ran under and whether it passed (no flag, and every check ran). A
    run that cannot place the application (no company or role) keeps nothing. What a
    rerun of the drafts treats as made by a version (tools/remake_drafts.py)."""
    if not entry.get("company") or not entry.get("role"):
        return
    try:
        import datetime as dt
        import outreach
        # With the abbreviation the documents were written under, as outreach.py names it:
        # without it, before the tracker had a row, this was a second folder (2026-10-26).
        folder = outreach.app_folder(entry["company"], entry["role"], entry.get("abbr") or "")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "verify.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       "abbr": entry.get("abbr"), "flags": flags,
                       "pages": {"resume": resume_pages,
                                 "letter": letter_pages if letter else None},
                       "drafts": _drafts_version(), "passed": not flags and checked},
                      fh, indent=1)
            fh.write("\n")
    except Exception:  # noqa: BLE001  a record that cannot be kept never fails the checks
        pass


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
    # A general resume has no letter (tools/general_resume.py), nor has a resume asked for alone
    # (docpaths.has_letter): their letter checks are skipped.
    general = {a["abbr"] for a in batch if not docpaths.has_letter(a)}
    names = [r["employer"] for r in roles]
    want = json.loads(v["SECTIONS"])
    pages_allowed = int(v["RESUME_PAGES"])
    banned = (re.compile(r"\b(" + "|".join(re.escape(n) for n in
                                          person.get("documents.banned_nouns", [])) + r")\b",
                         re.I) if v["BANNED_NOUNS"] else None)
    mins = [(int(i), int(m), short) for i, m, short in
            (x.split(":", 2) for x in v["ROLE_MINS"].split())]

    fail = tb = n = skipped = design_skipped = 0
    readers: list = []
    records: dict = {}
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
        after_exp = next_heading(want, v["H_EXPERIENCE"])
        shown = role_order(r_lines, names, v["H_EXPERIENCE"], after_exp)
        if shown != v["ROLE_ORDER"]:
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
        layout_note = ""
        for pdf, flag in ((r_pdf, "DESIGN_RESUME"), (c_pdf, "DESIGN_LETTER")):
            if not pdf:
                continue
            st, found = _run([os.path.join(TOOLS, "design_check.py"), pdf, "--for", drafts,
                              "--abbr", a])
            if st == 3:
                design_skipped = 1          # no pypdf: not checked, which is not a pass
            elif st == 4 and flag == "DESIGN_RESUME":
                # The parser's rules pass; a page of two ends badly (design_check.layout).
                # A short last page the fit tried to take back, with every role at its floor,
                # or one the person left as space, is said, never failed: nothing is left
                # for anyone to do about it.
                layout_note = _thin_kept(_entry(batch, a), found)
                if not layout_note:
                    p += " LAYOUT_RESUME"
            elif st != 0:
                p += " " + flag
        # Every contact line the resume prints, not the email and the phone alone: a bare
        # "%" in a LinkedIn address commented out the LinkedIn line and the line after it,
        # and only the round trip, if anything, said so.
        lost = [c for c in json.loads(v["CONTACT_LINES"]) if c not in flat]
        if lost:
            p += " CONTACT"
        # The letter's header carries the email and the phone too.
        if c_pdf and any(x and x not in " ".join(ct_text.split())
                         for x in (v["EMAIL"], v["PHONE"])):
            p += " CONTACT_LETTER"
        # A word of the letter read with a space inside it ("L TV"): the resume's round trip
        # names these, and the letter has no round trip of its own.
        split = []
        if c_pdf:
            import verify_pdf
            draft = next((x for x in batch if x.get("abbr") == a), None)
            split = verify_pdf.letter_splits(draft, ct_text) if draft else []
        if split:
            p += " SPLIT_LETTER"
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
        # The Skills block, to the heading after it, carries no parenthesis.
        if any(re.search(r"[()]", line) for line in
               sed_range(r_lines, v["H_SKILLS"], next_heading(want, v["H_SKILLS"]),
                         drop_end=True)):
            p += " SKILLPARENS"
        if banned and (banned.search(rt_text) or banned.search(ct_text)):
            p += " " + v["BANNED_FLAG"]
        # Six words in a row shared by two bullets (audit_letters.shared_runs, which also
        # reads each letter's bullets against the resume's), and a bullet on the page
        # twice, read as whole bullets however a reader places the marks.
        bul = resume_bullets(rt_text, v["H_EXPERIENCE"], after_exp)
        shared, dups = len(shared_runs(bul)), len(duplicate_bullets(bul))
        if dups:
            p += " DUPBULLET"
        if shared:
            p += f" SHARED_PHRASE({shared})"
        cnt = bullets_per_role(r_lines, names, after_exp)
        # A role the profile gives a verify_min must carry at least that many.
        got = cnt.split("/")
        for i, m, short in mins:
            if int(got[i]) < m:
                p += f" {short}_LT_{m}"
        # And no more than its cap for this posting (the profile's cap, lowered by its
        # cap_unless off its territory): only the floor was read, and a role held to one
        # bullet off its territory printed two (2026-11-03).
        entry = next((x for x in batch if x.get("abbr") == a), {})
        # Every sentence on the page is one the audits read: a summary changed after them
        # ("with four years" where the audited sentence said "4+ years") was the one sent,
        # and the audit's record was of text never shipped (2026-11-03).
        unaudited = _unaudited(entry)
        if unaudited:
            p += " UNAUDITED"
        caps = _caps(entry)
        keys = _role_keys(roles)
        for i, r in enumerate(roles):
            cap = caps.get(keys[i])
            if cap is not None and i < len(got) and int(got[i]) > cap:
                p += f" {r.get('short') or i}_GT_{cap}"
        b = sum(1 for line in r_lines if BULLET.search(line))
        tb += b
        n += 1
        records[a] = (entry, p.split(), rp, cp, bool(c_pdf))
        _say("%-9s %s/%s  %-4s %-14s %s" % (a, rp_s, cp_s, b, cnt, p))
        if layout_note:
            _say("          " + layout_note)
        if lost:
            _say("          contact lines not on the page: " + "; ".join(lost))
        for line in split:
            _say("          " + line)
        if " CHRONO" in p:
            # Which job is missing or out of place, said, never only the flag.
            want_roles = v["ROLE_ORDER"].rstrip(">").split(">")
            got_roles = shown.rstrip(">").split(">")
            gone = [x for x in dict.fromkeys(want_roles) if got_roles.count(x) < want_roles.count(x)]
            _say("          the jobs on the page are not the profile's, in order: "
                 + ("missing " + ", ".join(gone) if gone else "shown as " + " > ".join(got_roles)))
        if " ROUNDTRIP" in p:
            _say("\n".join("          " + line for line in rt.splitlines()))
        for field, sentence in unaudited[:5]:
            _say(f"          not read by the audits ({field}): {sentence[:110]}; audit it "
                 "again (stage_picks.py audit) or put back the audited words")
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
        _say("no letters: a general resume, or the resume alone as asked")
    # Each application's record says what the whole-batch checks found on its own documents
    # too: a claim, a number or a letter the batch failed on, with "flags": [] beside it, read
    # on the page as checked and clean (2026-11-03).
    try:
        from fit_to_page import load
        with_posting = {x.get("abbr"): x for x in load(drafts)[0] if isinstance(x, dict)}
    except Exception:  # noqa: BLE001  no posting to read back: the letter is read as it is
        with_posting = {}
    lettered = [x for x in with_posting.values() if docpaths.has_letter(x)]
    for a, (entry, flags, rp_, cp_, has_letter) in records.items():
        _record(entry, flags + _batch_flags(a, entry, a in general, with_posting.get(a),
                                            lettered),
                rp_, cp_, has_letter, checked=not (skipped or design_skipped))
    if skipped:
        _say("=== SPACING CHECK SKIPPED ===")
        _say("pypdf is not available, so words run together were NOT checked on any document.")
        _say("python3 tools/env_check.py --fix installs it (or pip3 install --upgrade cffi if "
             "it is installed and panics); then run this again.")
    if design_skipped:
        _say("=== DESIGN CHECK SKIPPED ===")
        _say("pypdf is not available, so the page size, the text sizes, the margins and the "
             "single column were NOT checked on any document.")
        _say("python3 tools/env_check.py --fix installs it; then run this again.")
    if fail:
        _say("BATCH: FAILURES ABOVE")
        return 1
    if skipped or design_skipped:
        what = [w for w, on in (("the spacing check", skipped),
                                ("the design check", design_skipped)) if on]
        _say("BATCH: NOT ALL PASS, " + " and ".join(what)
             + (" was" if len(what) == 1 else " were") + " SKIPPED")
        return 3
    _say("BATCH: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
