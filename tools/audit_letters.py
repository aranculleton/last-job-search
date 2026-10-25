"""Read every cover letter the way a hiring manager does, and flag what fails.

Structure checks read the draft fields, which know where the opening and the
closing are. Rendering checks read the compiled PDF text, which is what the
reader sees. Each rule is one from 03-writing-style.md or
06-cover-letter-templates.md that a letter in this repo has actually broken.
"""
import re, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_application as R
from fit_to_page import body_words, load
import docpaths
import person
import company_key
import doc_name
import locale_rules

# The opening must name one of the candidate's employers: that is the
# credential. It is matched as people write it (render_application's
# EMPLOYER_NAMED: "Brindle & Hart" names Brindle & Hart Logistics), not as the
# exact string in roles.py. The pronoun is the one the profile gives, for the
# drafter-text check below. The banned nouns (the document word the market does
# NOT use: "CV" where it is a resume, "resume" where it is a CV) and the banned
# characters are the profile's, from tools/locale_rules.py, the copy the resume
# and message checks read too.
_EMPLOYERS = R.EMPLOYER_NAMED
_POSS = re.escape(person.get("identity.pronouns.possessive", "their"))
_LOCALE = locale_rules.LOCALE
_SAL_PREFIX = person.get("documents.salutation_prefix", "Dear")
_SAL_SUFFIX = R._SALUTATION_SUFFIX.strip()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The shapes a concession actually takes in drafted letters: "I have not
# managed a team", "is new to me", "three years in rather than five", "rather
# than the six listed", "fewer than the seven", "would start here rather than
# continue", "rather than SAP and Oracle". The old pattern matched "four years
# of experience", which is the profile's positive claim, and missed "I have not
# built", "no direct experience" and "not yet".
# The candidate as a sentence's subject: "I", "my", or their own name ("Morgan's
# exposure"). The softer shapes below count only about them: "operations managers with
# little experience of SQL" and "teams with limited exposure to the data" are the people
# the work was for, and "let 30 managers get up to speed" is a result.
_NAMES = [n for n in {str(person.get("identity.first", "") or "").strip(),
                      str(person.get("identity.name", "") or "").strip()} if n]
_THEIR = ("|".join(re.escape(n) + r"'s" for n in sorted(_NAMES, key=len, reverse=True))
          or r"(?!x)x")
_THEY = "|".join(re.escape(n) for n in sorted(_NAMES, key=len, reverse=True)) or r"(?!x)x"
CONCEDE = re.compile(
    r"\b(?:I have not (?:yet )?(?!only\b)\w+|I haven'?t (?:yet )?(?!only\b)\w+|"
    r"I have (?:had )?no (?:direct |formal |prior |hands-on )?experience|"
    r"not yet\b|have yet to|(?:is|would be|are) new to me|I lack\b|"
    r"(?:fewer|less|shorter) than the|short of the|"
    r"rather than (?:the )?(?:\d+|five|six|seven|eight|nine|ten|business|continue|(?-i:[A-Z]{2,}))|"
    r"years? in rather than|would start here|is the one .*? I have not|"
    # The softer shapes a gap arrives in, which the two above let through: "my exposure
    # to insurance data so far is limited", "would be a new domain for me", "keen to
    # build my experience of claims data", "I would learn it fast". Each is said of the
    # candidate.
    r"(?:my|" + _THEIR + r") (?:[\w-]+ ){0,3}(?:exposure|experience|background|familiarity|"
    r"knowledge)\b[^.]{0,40}\b(?:is|has been|remains|was) (?:so far |still |fairly |quite |"
    r"relatively )?(?:limited|light|modest|narrow)|"
    r"(?:(?-i:I)(?:'ve| have| had)?|(?-i:" + _THEY + r") (?:has|had)) (?:(?:had|got|gained|built|"
    r"only|so far|yet|still|a|some|rather|relatively|fairly) ){0,3}(?:limited|little|modest|no real) "
    r"(?:exposure|experience|familiarity|background) (?:to|with|in|of)\b|"
    r"(?:my|" + _THEIR + r") (?:own )?(?:relatively |fairly )?(?:limited|little|modest) "
    r"(?:exposure|experience|familiarity|background) (?:to|with|in|of)\b|"
    r"new (?:domain|area|field|sector|industry|world|territory|space) (?:for|to) me|"
    r"(?:(?-i:I)(?:'m| am|'d be| would be| will be|'ll be)|(?-i:" + _THEY + r") is) (?:really |"
    r"very |particularly |especially )?(?:keen|eager|excited|looking|hoping|happy) to (?:build|"
    r"grow|develop|deepen|broaden|gain|strengthen) (?:up )?(?:my )?(?:[\w-]+ ){0,3}(?:experience|"
    r"exposure|knowledge|understanding|skills?)|"
    r"(?:keen|eager|excited|looking|hoping|happy) to (?:build|grow|develop|deepen|broaden|gain|"
    r"strengthen) (?:up )?my (?:[\w-]+ ){0,3}(?:experience|exposure|knowledge|understanding|skills?)|"
    r"build (?:up )?my (?:\w+ )?(?:experience|knowledge|exposure) (?:of|in|with)\b|"
    r"I(?:'d| would| will| can| could) (?:learn|pick up|master) (?:it|this|them|that|the \w+) "
    r"(?:fast|quickly|soon)\b|"
    r"(?-i:I)(?:'d|'ll| would| will| can| could| should| expect to| aim to| plan to| hope to)?"
    r"(?: (?:quickly|soon|rapidly|fast))? get (?:myself )?up to speed\b|"
    r"get(?:ting)? myself up to speed\b|(?:outside|beyond) (?:of )?my (?:direct |current )?"
    r"(?:experience|background|expertise)\b|(?-i:I) (?:haven'?t|have not) (?:yet )?had the "
    r"(?:chance|opportunity))", re.I)


# The "not X, but Y" shape, in every phrasing that arrives. This is the one to
# avoid above all: the sentence reads as balanced to the writer and as a
# disqualification to the reader, because a skim keeps the negation and drops
# the recovery. There is no acceptable version of it, so unlike CONCEDE
# there is no allowance at all.
CONTRAST = re.compile(
    r"\b(?:while|although|though|whilst|even though)\b[^.]{0,90}"
    r"\b(?:I (?:have|had)n[o']?t|I have not|no direct|not worked|not used|"
    r"limited|less)\b"
    r"|\bI (?:have )?(?:not|never) (?:worked with|used|built|run|shipped)\b[^.]{0,90}\bbut\b"
    r"|\b(?:have|has) not[^.]{0,60}\b,?\s*but\b"
    r"|\bI would pick (?:it |them |that |[a-z]+ )?up\b"
    r"|\bconfident I (?:could|can|would) (?:learn|pick up|get up to speed)\b"
    r"|\bhappy to (?:learn|get up to speed on)\b"
    r"|\bnot (?:yet )?(?:in|part of) my (?:toolkit|stack|experience)\b", re.I)


def _plain(s):
    s = re.sub(r"\\textasciitilde\{\}", "~", s or "")
    s = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", s)
    return s.replace("\\%", "%").replace("\\$", "$").replace("\\&", "&")


def sentences(s):
    return R.split_sentences(_plain(s))


def runs(words, n=6):
    """Every run of `n` consecutive words."""
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def shared_runs(texts, n=6):
    """{run: the indices of the texts carrying it}, for every six-word run that
    more than one of `texts` carries. verify_batch.sh's SHARED_PHRASE check runs
    this over a resume's bullets; the letter audit runs it against them."""
    seen = {}
    for i, t in enumerate(texts):
        for r in runs(str(t).lower().split(), n):
            seen.setdefault(r, set()).add(i)
    return {r: v for r, v in seen.items() if len(v) > 1}


# A bullet's mark in a resume's text layer, with whatever space a reader puts after it.
_MARK = re.compile(r"\n[ \t\u00a0]*\u2022[ \t\u00a0]*")


def resume_bullets(text, start, end):
    """The bullets of a resume's text layer between two headings, each one whole: its mark,
    the line after a mark left alone on its own line, and its wrapped lines, as one text.
    A reader on a Mac put each mark on a line of its own, and verify_batch.sh, reading line
    by line, saw every bullet as empty and every resume as repeating one (2026-10-24)."""
    body = str(text or "")
    if start and start in body:
        body = body.split(start, 1)[1]
    if end and end in body:
        body = body.split(end, 1)[0]
    parts = _MARK.split("\n" + body)[1:]
    return [b for b in (re.sub(r"\s+", " ", p).strip() for p in parts) if b]


def duplicate_bullets(bullets, n=8):
    """The bullets that open with the same `n` words as an earlier one: the same bullet put
    on the page twice. Whole words, so two bullets that only start alike are not one."""
    seen, out = set(), []
    for b in bullets:
        key = " ".join(_words(b).split()[:n])
        if len(key.split()) < 4:
            continue
        if key in seen:
            out.append(b)
        seen.add(key)
    return out


def _words(text):
    """Lower-case words with the LaTeX and the punctuation gone, so a letter's
    "22% to 14%" meets a bullet's "22\\% to 14\\%". A figure stays one word:
    "2,400" split in two made "across 2,400 SKUs and 6" a six-word repeat."""
    words = re.sub(r"[^\w%£$.,]+", " ", _plain(text).lower()).split()
    return " ".join(w.strip(".,") for w in words if w.strip(".,"))


def resume_repeats(a, n=6):
    """[(label, run)] for each letter bullet that repeats a resume bullet the
    allocator chose for this draft. 06-cover-letter-templates.md cuts "any
    bullet duplicating the resume": the reader has both pages in front of them,
    and a sentence read twice is a sentence wasted."""
    chosen = [_words(R.BULLETS[b]) for j in a.get("jobs") or []
              for b in j.get("bullets") or [] if b in R.BULLETS]
    out = []
    for b in a.get("cl_bullets") or []:
        mine = _words(b.get("text", "") if isinstance(b, dict) else " ".join(b[1:]))
        common = {r for r, ix in shared_runs([mine] + chosen, n).items() if 0 in ix}
        if common:
            label = b.get("label", "") if isinstance(b, dict) else b[0]
            out.append((label, sorted(common)[0]))
    return out


# A run of this many words copied from the posting into what the candidate wrote. Pasted
# posting text reads as spam to the person who wrote the posting, and it is the cheapest
# keyword stuffing there is: the posting's exact term, used once in a real sentence, is the
# right amount. The resume's bullets are the profile's own words, so a run they share with
# the posting is not a copy; the summary and every part of the letter are written fresh.
POSTING_RUN = 6
_WRITTEN = (("summary", "the resume summary"), ("p1", "the opening"),
            ("p2", "the company paragraph"), ("lead", "the line before the bullets"),
            ("p4", "the close"))


def _own_words():
    """Every run the person's own words carry: the bullet library and the profile."""
    texts = list(R.BULLETS.values())
    try:
        with open(person.file("candidate_profile", "01-candidate-profile.md"),
                  encoding="utf-8") as fh:
            texts.append(fh.read())
    except OSError:
        pass
    return texts


def posting_copies(a, n=POSTING_RUN, own=None):
    """[(where, the copied words)] for each part of the summary or the letter that repeats
    `n` or more words in a row from the posting, the longest stretch in each part. A run
    the person's own words also carry (the profile, the bullet library) is theirs."""
    posting = _words(a.get("posting") or "").split()
    if len(posting) < n:
        return []
    theirs = runs(posting, n)
    mine = set()
    for t in (own if own is not None else _own_words()):
        mine |= runs(_words(t).split(), n)
    parts = [(where, a.get(k) or "") for k, where in _WRITTEN]
    parts += [("the %s bullet" % (b.get("label") or "letter").rstrip(": ") if isinstance(b, dict)
               else "a letter bullet", b.get("text", "") if isinstance(b, dict) else " ".join(b[1:]))
              for b in a.get("cl_bullets") or []]
    out = []
    for where, text in parts:
        words = _words(text).split()
        hits = [i for i in range(len(words) - n + 1)
                if " ".join(words[i:i + n]) in theirs and " ".join(words[i:i + n]) not in mine]
        if not hits:
            continue
        # The longest stretch of overlapping runs, shown whole.
        stretches, start, prev = [], hits[0], hits[0]
        for i in hits[1:]:
            if i != prev + 1:
                stretches.append((start, prev))
                start = i
            prev = i
        stretches.append((start, prev))
        first, last = max(stretches, key=lambda x: x[1] - x[0])
        out.append((where, " ".join(words[first:last + n])))
    return out


def pdf_text(abbr):
    """The letter's text layer. Raises rather than returning "".

    An empty string passed every page check below: a missing PDF, or no
    pdftotext on the machine, reported a clean letter.
    """
    pdf = docpaths.letter_pdf(abbr)
    if not os.path.exists(pdf):
        raise FileNotFoundError(f"no compiled letter at {pdf}; render it before auditing")
    try:
        out = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", pdf, "-"],
                             capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("pdftotext is not installed; see SETUP.md") from exc
    if out.returncode != 0:
        raise RuntimeError(f"pdftotext failed on {pdf}: {out.stderr.strip()[:200]}")
    return out.stdout


# The opener 03-writing-style.md bans: a first sentence that announces the
# application ("I am applying for the <role> role", "I am writing to express
# my interest"). The portal already told the reader which role this is, and
# the one sentence a recruiter is guaranteed to read is spent on it.
ANNOUNCES = re.compile(
    r"\b(?:I am|I['’]m)\s+(?:writing\s+(?:to|in)\b|applying\b|"
    r"(?:delighted|pleased|excited|keen|happy|eager|thrilled)\s+to\s+apply\b|"
    r"interested\s+in\s+(?:the|this|your)\b)"
    r"|\bI\s+(?:would\s+like|wish|want)\s+to\s+(?:apply|express|submit)\b"
    r"|\bplease\s+(?:accept|find)\b|\bmy\s+application\s+for\b"
    r"|\bto\s+apply\s+for\b|\bapplication\s+for\s+the\b"
    r"|\bwith\s+(?:great|much)\s+(?:interest|enthusiasm)\b", re.I)


def role_named(role, opening):
    """Any two consecutive words of the role title, in order, in the opening.
    A one-word title ("Analyst") is named when that word appears."""
    words = [w for w in re.findall(r"[A-Za-z]+", role) if len(w) > 2 or w.isupper()]
    o = opening.lower()
    if len(words) == 1:
        return re.search(r"(?<!\w)" + re.escape(words[0].lower()) + r"(?!\w)", o) is not None
    return any(f"{words[i].lower()} {words[i+1].lower()}" in o for i in range(len(words) - 1))


def page_flags(t):
    """The locale rules on the letter's text layer: the banned nouns and dashes."""
    flags = [f"says {n.word}" for n in _LOCALE.nouns if n.document.search(t)]
    if _LOCALE.dashes(t):
        flags.append("dash")
    return flags


def audit(a, batch=()):
    """The flags for one letter. `batch` is every draft rendered with it: two
    roles at one employer is the case where the letter must name its role."""
    flags = draft_flags(a, batch)
    for lab, run in resume_repeats(a):
        flags.append(f"letter bullet ({lab.rstrip(': ')[:20]}) repeats the resume: \"{run}\"")
    return flags + page_text_flags(a), body_words(a)


def draft_flags(a, batch=()):
    """The flags the draft object alone shows, before anything is rendered: the opening,
    the credential, the employer named, concessions and the contrast construction, a
    bullet repeating its label. The drafting audit (tools/draft_audit.py) runs these on
    every draft; `audit` runs them again on the rendered letter with the page checks."""
    flags = []
    p1, p2, p4 = _plain(a["p1"]), _plain(a["p2"]), _plain(a.get("p4", ""))
    body = " ".join([p1, p2, _plain(a.get("lead", "")), p4]
                    + [_plain(b["text"]) for b in a["cl_bullets"]])
    # The role is NOT required in the opening. 03-writing-style.md: "let the
    # role be obvious", and name it in a subject line or a second clause only
    # when it genuinely needs naming. Requiring it here pushed every letter
    # back to the "I am applying for the <role> role" opener the guide bans.
    first = (sentences(a["p1"]) or [""])[0]
    m = ANNOUNCES.search(first)
    if m:
        flags.append(f"opening announces the application (\"{m.group(0)}\"); open on "
                     f"what you can answer and let the role be obvious")
    # The one case that does need it: several roles at one employer in this
    # batch, where the reader may hold two of the candidate's letters.
    key = company_key.key(a["company"])
    if any(o is not a and company_key.key(o["company"]) == key
           and doc_name._norm(o["role"]) != doc_name._norm(a["role"]) for o in batch) \
            and not role_named(a["role"], body):
        flags.append("another role at this employer is in the batch, and this letter "
                     "never names its own")
    if not _EMPLOYERS.search(p1):
        flags.append("opening names none of the candidate's employers (if it uses a "
                     "name roles.py does not hold, add it to that role's known_as)")
    # A company called "The Something" used to check for "The", which every
    # letter contains.
    short = R.short_name(a["company"]).split()[0]
    if not re.search(r"(?<!\w)" + re.escape(short) + r"(?!\w)", body, re.I):
        flags.append(f"body never names {short}")
    # Zero concessions, not one. Hiring managers and recruiters read a
    # concession as "does not have X, so does not meet the minimum": a reader
    # skims and the negation is what survives the skim, so the whole
    # construction is out.
    conc = [s for s in sentences(body) if CONCEDE.search(s)]
    if conc:
        flags.append(f"{len(conc)} concession sentence(s); the letter volunteers "
                     f"none: \"{conc[0][:70]}\"")
    if any(CONCEDE.search(s) for s in sentences(p4)):
        flags.append("concession in the closing")
    contrast = [s for s in sentences(body) if CONTRAST.search(s)]
    if contrast:
        flags.append(f"contrast construction, the reader keeps the negation: "
                     f"\"{contrast[0][:70]}\"")
    for b in a["cl_bullets"]:
        lab = b["label"].rstrip(": ").strip()
        if lab and _plain(b["text"]).lower().startswith(lab.lower()):
            flags.append(f"bullet text repeats its label ({lab[:20]})")
    for where, run in posting_copies(a):
        flags.append(f"{where} copies the posting word for word: \"{run}\"; say it in your "
                     f"own words, using the posting's term once")
    return flags


def page_text_flags(a):
    """The flags only the compiled letter shows: drafter text on the page, the banned
    nouns and dashes, a doubled phrase, a legal suffix in the salutation."""
    flags = []
    t = pdf_text(R.final_abbr(a))
    # The drafter's own notes must never reach the page. Letters have shipped
    # with "conceded in one sentence mid-letter in p2" in their closing.
    meta = re.search(r"conceded|mid-paragraph|mid-letter|posting's stated|states no gaps|"
                     r"\bin p[124]\b|\bp[124]\b|drafter|framed by adjacency|"
                     r"\b" + _POSS + r"\b (?:SQL|resume|\w+ years)",
                     t, re.I)
    if meta:
        flags.append(f"DRAFTER TEXT ON PAGE: '{meta.group(0)}'")
    flags += page_flags(t)
    if re.search(r"\b(\w+(?: \w+){1,3}) \1\b", t):
        flags.append("doubled phrase in PDF")
    sal = re.search(re.escape(_SAL_PREFIX) + r"\s+(.+?)" + (re.escape(_SAL_SUFFIX)
                                                          if _SAL_SUFFIX else r"\s*,?\s*$"),
                    t, re.M)
    if sal and R.LEGAL_SUFFIX.search(sal.group(1).strip()):
        flags.append("legal suffix in salutation")
    return flags


# The cap in 03-writing-style.md. A letter over it is a finding, not a note.
MAX_BODY_WORDS = 250

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("usage: python3 tools/audit_letters.py <drafts.json>\n\n" + __doc__.strip().split("\n\n")[0])
        sys.exit(0 if len(sys.argv) > 1 else 2)
    # Through fit_to_page's loader: a kept draft.json names its posting, which is read
    # back through its untrusted fence, and the posting-copy check needs it.
    apps, _read_in = load(sys.argv[1])
    # A general resume has no letter (tools/general_resume.py): nothing here to read.
    apps = [a for a in apps if not a.get("general")]
    bad = 0
    for a in apps:
        flags, w = audit(a, apps)
        if w > MAX_BODY_WORDS:
            flags.append(f"{w} body words, over the {MAX_BODY_WORDS} cap")
        print(f"{'!!' if flags else '  '} {R.final_abbr(a):9s} {w:4d} body words  {'; '.join(flags)}")
        bad += bool(flags)
    print(f"\n{len(apps) - bad}/{len(apps)} letters clean")
    # It always exited 0, so `verify_batch.sh` read PIPESTATUS[0], got zero, and
    # printed BATCH: ALL PASS over letters carrying the drafter's own notes on
    # the page. The status is the whole point of running it in a batch.
    sys.exit(1 if bad else 0)
