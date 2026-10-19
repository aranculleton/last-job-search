"""Render tailored-application JSON into resume + cover letter .tex via gen.py."""
import sys, re
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "templates"))
import resume_gen as gen          # templates/resume_gen.py, the committed copy
from resume_gen import resume, letter
import skills_block
import check_claims
import bullet_library as LIBRARY
import allocate
import doc_name
import person
import company_key

# Every bullet the profile supports, themed. The generator used to draw from
# fourteen strings in the template, so a logistics resume and a retail
# resume were permutations of the same sentences. The profile's bullets.py
# holds the lot, and allocate.py decides who gets how many for THIS posting.
BULLETS = dict(LIBRARY.TEXT)
for _a, _t in LIBRARY.RENDER_ALIASES.items():   # old ids, kept for old drafts
    BULLETS[_a] = LIBRARY.TEXT[_t]

# Summary: three lines, not four. Everything past ~48 words on the fourth line
# is a bullet some employer did not get.
MAX_SUMMARY_WORDS = 52
# A floor as well as a ceiling. cap_summary drops whole sentences to fit the
# budget, so a 50-word summary whose first sentence is 16 words rendered as a
# 16-word stub, and stubs shipped that way. Below this,
# the next sentence is kept and trimmed at a clause boundary instead of dropped.
MIN_SUMMARY_WORDS = 36
# The profile's roles, most recent first. What the resume prints for each:
# dates (spaced hyphen: "2025-Present" is one token to a whitespace tokenizer),
# title, location, and the \needspace lines when not the default.
ROLES = person.module("roles").ROLES
META = {r["employer"]: dict(dates=r["dates"], title=r["title"], loc=r["loc"],
                            **({"ns": r["ns"]} if "ns" in r else {}))
        for r in ROLES}
_NO_SKILLS = {r["employer"] for r in ROLES if r.get("skills_context") is False}
_SALUTATION_SUFFIX = person.get("documents.salutation_suffix", " hiring team")
AWS_KERN = re.compile(r"\bAWS\b")


def kern_aws(s):
    """pypdf reads the LM Sans A-W kern pair as a word gap: "A WS S3". A zero
    kern keeps the glyphs where they are and the extractor's heuristic quiet."""
    return AWS_KERN.sub(r"A\\kern0pt WS", s)
DASH = re.compile(r"[–—]")

# Reverse-chronological, always. Ordering the employers by relevance to the
# posting once put a role that ended last year above the current one, so the
# page read as a career going backwards and any ATS date parser saw an
# unexplained inversion. Relevance is expressed by which bullets are chosen and
# how they are framed, never by moving a job out of its place in time.
CHRONO = [r["employer"] for r in ROLES]

# Bullets that say the same thing. A bullet that merges two others, rendered
# beside either, printed the same figure twice in consecutive bullets. It
# shipped that way once.
CONFLICTS = {k: set(v) for k, v in LIBRARY.CONFLICTS.items()}
# A render-only alias is an older name for its target: it conflicts with
# everything the target conflicts with, and with the target itself, in both
# directions.
for _a, _t in LIBRARY.RENDER_ALIASES.items():
    _alias = {_t} | CONFLICTS.get(_t, set())
    CONFLICTS[_a] = set(_alias)
    for _k in _alias:
        CONFLICTS.setdefault(_k, set()).add(_a)


def dedupe(keys):
    """Drop bullets superseded by an earlier one, and exact repeats.

    Walked in order, so a redundant pair keeps whichever the tailor put first
    rather than cancelling both out.
    """
    out, blocked = [], set()
    for k in keys:
        if k in out or k in blocked:
            continue
        out.append(k)
        blocked |= CONFLICTS.get(k, set())
    return out

# A held skill beside the work it describes used to be stripped out of prose
# here, on the reasoning that the pairing read as an unsupported claim. A rule
# written after something genuinely unheld reached sent resumes had generalized
# a fabrication guard into one that suppressed a true sentence, and it would
# have stripped the keyword from precisely the postings that ask for it by
# name. Fabrication is check_claims.py's job, against the profile. Omitting a
# held skill is not the safe side of this trade; it is a missed match.


def clean(s):
    """Kill em/en dashes and repair LaTeX escapes the model may have missed.

    Idempotent: an already-escaped character is left alone, so the fit loop
    can call this on every pass. A dash between two digits is a range
    ("2018-2022") and becomes a hyphen; anywhere else it becomes a comma, which
    is how the style guide replaces a dash in prose. A bare "$" is escaped
    wherever it sits: "$ 10M" and "$M" opened math mode and broke the compile.
    """
    s = s or ""
    s = re.sub(r"(?<=\d)[–—](?=\d)", "-", s)
    s = DASH.sub(", ", s)
    # ~ and ^ are LaTeX actives and were not escaped. A bare ~ is a
    # non-breaking space, so a drafted "~5%" rendered as "5%" while a bullet two
    # inches lower still said "~5%": one page, one figure, two different
    # precision claims. ^ superscripts silently.
    # Done before the %&$#_ pass so the inserted backslashes are not re-escaped.
    s = re.sub(r"(?<!\\)~", r"\\textasciitilde{}", s)
    s = re.sub(r"(?<!\\)\^", r"\\textasciicircum{}", s)
    s = re.sub(r"(?<!\\)([%&$#_])", r"\\\1", s)
    return s


# One sentence splitter for the whole generator, so the summary cap, the
# letter trimmer, the audit and the outreach note agree on where a sentence
# ends. "e.g.", "i.e.", "vs." and a single capital ("U.S.") are not ends.
SENT_SPLIT = re.compile(r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<!\betc\.)(?<!\bInc\.)"
                        r"(?<!\bLtd\.)(?<![A-Z]\.)(?<=[.!?])\s+")


def split_sentences(text):
    return [x for x in SENT_SPLIT.split((text or "").strip()) if x]

# The legal forms are company_key's, one list shared with the people search.
# "Group", "Holdings" and "Company" are part of the name, not a legal suffix:
# Harbour Group is Harbour Group. Only entity types come off. The letter audit
# reads LEGAL_SUFFIX to catch one left on a salutation.
LEGAL_SUFFIX = company_key.LEGAL_FORM


def strip_legal(name):
    """The name with every trailing legal form removed, one at a time:
    "Acme Pty Ltd" is Acme, not "Acme Pty"."""
    return company_key.strip_legal_forms(name)


def short_name(company):
    """The name a person would use: "Acme", "Harbour Group", "Northwind".

    A bracketed qualifier and the legal suffix come off ("Acme Analytics Inc.
    (UK)" is Acme Analytics). A leading "The" comes off. "Group" comes off only
    when it was part of the legal entity ("The Northwind Group Limited" is the
    entity; the brand is Northwind), never from a brand that carries it
    ("Harbour Group" stays Harbour Group). Shared by the salutation, the letter
    audit and the outreach note so all three agree on what the company is called.
    """
    name = company_key.drop_brackets(company)
    stripped = company_key.display_name(name).strip(" ,.")
    if stripped != name.strip(" ,."):
        stripped = re.sub(r"\s+(group|holdings)$", "", stripped, flags=re.I)
    return re.sub(r"^the\s+", "", stripped, flags=re.I).strip(" ,.")


# The candidate's employers as people write them. A letter says "at Brindle &
# Hart", not "at Brindle & Hart Logistics", and an exact match on the legal
# string failed letters the style guide asks for. Accepted, per role: the name
# in roles.py; its short_name and company key; the profile's COMPANY_ALIASES
# that resolve to the same key; `known_as` on the role (a string or a list:
# "Oakmere" for Oakmere Foods); and its leading words, two or more, when the
# name has three or more. Matched across any punctuation, so "Brindle & Hart"
# and "Brindle and Hart" are one form only when the profile says so.
_NAME_STOP = {"of", "and", "the", "de", "du", "des", "for", "la", "le", "et", "in", "at", "y"}


def _name_words(s):
    return re.sub(r"[^\w]+", " ", (s or "").lower()).split()


def _employer_forms(roles):
    aliases = company_key.ALIASES
    forms = set()
    for r in roles:
        emp = r["employer"]
        k = company_key.key(emp)
        known = r.get("known_as") or ()
        names = [emp, short_name(emp), k, *(a for a, v in aliases.items() if v == k),
                 *([known] if isinstance(known, str) else known)]
        words = _name_words(short_name(emp))
        names += [" ".join(words[:n]) for n in range(2, len(words))
                  if words[n - 1] not in _NAME_STOP]
        forms |= {" ".join(_name_words(n)) for n in names if _name_words(n)}
    return sorted(forms, key=len, reverse=True)


def _form_pattern(form):
    """Words across any punctuation, case-blind. A one-word form must open on
    a capital, because it can be an ordinary word too: an employer called
    Target is named by "at Target", not by "I target"."""
    words = form.split()
    if len(words) == 1:
        w = words[0]
        return "(?-i:%s)%s" % (re.escape(w[0].upper()), re.escape(w[1:]))
    return r"[\W_]+".join(re.escape(w) for w in words)


_FORMS = _employer_forms(ROLES)
# Shared by the letter audit (the opening must carry a credential) and the
# outreach note (its hook is the sentence that names one), so the two cannot
# disagree about whether a sentence names the candidate's employer.
EMPLOYER_NAMED = re.compile(
    r"\b(?:%s)\b" % "|".join(_form_pattern(f) for f in _FORMS),
    re.I) if _FORMS else re.compile(r"(?!x)x")


def salutation(company):
    """"Dear Acme, Inc hiring team" is not how anyone addresses a person."""
    return short_name(company)


def undouble(label, text):
    """Strip a repeat of the label from the front of the bullet text.

    The template prints the label in bold and then the text, so a draft whose
    text also opened with its own label rendered as "Mathematical grounding
    Mathematical grounding: a BSc in ...". It shipped that way once.
    """
    lab = label.rstrip(": .").strip()
    if not lab:
        return text
    m = re.match(r"\s*" + re.escape(lab) + r"\s*[:.\-]?\s*", text, re.I)
    return text[m.end():] if m else text


def jobs_for(a):
    """Bullet keys per employer for this draft.

    A draft that already carries `jobs` (because the fit loop has been adjusting
    it) is honoured. A fresh draft gets its allocation from the posting text:
    tenure, recency and theme relevance decide who gets how many, and which.
    """
    posting = a.get("posting", "") or a.get("role", "")
    if not str(a.get("posting") or "").strip():
        # Rendered from the title alone, a resume passes every check and is
        # tailored to nothing. Said loudly, every time.
        print(f"WARNING: {a.get('company')}: no posting text in this draft, so the bullets and "
              "skills are chosen for the job title alone. Stage it with tools/stage_picks.py, "
              "or render a kept draft with tools/fit_to_page.py.", file=sys.stderr)
    if not (a.get("jobs") and any(j.get("bullets") for j in a["jobs"])):
        alloc = allocate.allocate(posting, budget=a.get("budget", 12))
        a["jobs"] = [dict(employer=e, bullets=list(b)) for e, b in alloc.items()]
    # Dedupe and order IN PLACE, so the fit loop reasons about what will
    # actually render. A draft listing four bullets for one employer, two of
    # them in conflict, rendered three while grow_resume saw the employer at its
    # cap and never refilled the line. And NON_LEAD held only inside the allocator: a draft
    # whose jobs came from an older run still opened an employer with
    # "Supported a migration".
    scores = allocate.bullet_scores(posting)
    for j in a["jobs"]:
        j["bullets"] = order_bullets(dedupe(j.get("bullets", [])), scores)
    return a["jobs"]


def order_bullets(keys, scores):
    """Strongest lead-eligible bullet first; the rest by score, as allocate does."""
    return sorted(keys, key=lambda k: (k in LIBRARY.NON_LEAD, -scores.get(k, 0.0),
                                       -LIBRARY.WEIGHT.get(k, 0)))


def cap_summary(text):
    """Whole sentences up to the budget, and never a stub below the floor.

    Sentences are accumulated whole while they fit. If stopping there would
    leave the summary under MIN_SUMMARY_WORDS, the next sentence is kept and
    cut back at a clause boundary (", " or "; ") rather than dropped, so the
    reader always gets a full three lines that end as a statement.
    """
    text = (text or "").strip()
    if len(text.split()) <= MAX_SUMMARY_WORDS:
        return text
    sents = split_sentences(text)
    out, n = [], 0
    for sent in sents:
        w = len(sent.split())
        if out and n + w > MAX_SUMMARY_WORDS:
            break
        if not out and w > MAX_SUMMARY_WORDS:
            out, n = [_clause_trim(sent, MAX_SUMMARY_WORDS)], MAX_SUMMARY_WORDS
            break
        out.append(sent)
        n += w
    if n < MIN_SUMMARY_WORDS and len(out) < len(sents):
        nxt = sents[len(out)]
        out.append(_clause_trim(nxt, MAX_SUMMARY_WORDS - n))
    return " ".join(out)


def _clause_trim(sent, budget):
    """Cut one sentence back to budget at a clause boundary, terminated once."""
    words = sent.split()
    if len(words) <= budget:
        return sent
    head = " ".join(words[:budget])
    for sep in ("; ", ", "):
        i = head.rfind(sep)
        if i > len(head) // 2:
            head = head[:i]
            break
    return head.rstrip(" ,;:.") + "."


def final_abbr(a):
    """The name build() will write under: derived from the company, plus the
    role token a supplied abbr carries after its first underscore.

    Every tool that opens a draft's files asks this rather than reading
    `abbr`: a draft may carry none, or one build() will replace, and both used
    to end in a bare KeyError or a compile looking for a file never written."""
    company = str(a.get("company") or "").strip()
    if not company:
        raise ValueError(f"a draft has no company, so its files cannot be named: "
                         f"role {a.get('role') or '(none)'!r}, abbr {a.get('abbr') or '(none)'!r}")
    abbr = a.get("abbr") or ""
    return doc_name.suffix(company, abbr.split("_", 1)[1] if "_" in abbr else "")


def build(a):
    jobs = []
    ordered = sorted(jobs_for(a),
                     key=lambda j: CHRONO.index(j["employer"])
                     if j["employer"] in CHRONO else len(CHRONO))
    for j in ordered:
        m = META[j["employer"]]
        keys = dedupe(j["bullets"])
        # An unknown key used to be skipped, and an employer whose keys were all
        # unknown was dropped from the resume entirely, silently. One typo in a
        # bullet id removed a whole employer from the page and the only sign was
        # a shorter document. There is no version of this that is not a bug, so
        # it raises and names the key.
        unknown = [b for b in keys if b not in BULLETS]
        if unknown:
            raise KeyError(
                "unknown bullet id %s for %s. Every id must exist in the "
                "profile's bullets.py; skipping one silently drops the "
                "employer off the resume." % (", ".join(sorted(unknown)), j["employer"]))
        bl = [kern_aws(BULLETS[b]) for b in keys]
        if not bl:
            continue
        jobs.append(dict(employer=j["employer"], bullets=bl, **m))
    # A role the profile marks always_show stays on the page with its default
    # bullet when a draft gives it none: an unexplained gap in the dates reads
    # worse than a short entry.
    have = {j["employer"] for j in jobs}
    for r in ROLES:
        emp = r["employer"]
        if emp not in have and r.get("always_show"):
            jobs.append(dict(employer=emp, bullets=[BULLETS[r["always_show"]]], **META[emp]))
    jobs.sort(key=lambda j: CHRONO.index(j["employer"]))
    summary = cap_summary(clean(a["summary"]))
    # The filename suffix is derived, not chosen. A drafter picking it by hand
    # got it wrong on several documents in one batch, shipping the company
    # name shouted in capitals, not an abbreviation.
    # A supplied abbr is honoured only when it carries a role token, which is
    # the one case doc_name cannot infer (two roles at one employer).
    abbr = a.get("abbr") or ""
    derived = final_abbr(a)
    if derived and derived != abbr:
        a["abbr"] = abbr = derived
    contact = str(a.get("contact_person") or "").strip()
    # The person's answers about the skills their profile does not hold, asked before
    # the draft (stage_picks.py consent): each yes prints on the skills line, and both
    # go into the documents' header, where check_claims.py reads them.
    yes = [str(x).strip() for x in a.get("consented_skills") or [] if str(x).strip()]
    no = [str(x).strip() for x in a.get("declined_skills") or [] if str(x).strip()]
    d = dict(
        abbr=abbr, company=a["company"], role=a["role"],
        summary=summary,
        jobs=jobs,
        # A role the profile marks skills_context=False does not feed the
        # skills line on its own: a short role's tools are not a stack. If the
        # posting asks for them, the posting tier picks them up.
        skills=kern_aws(skills_block.render(
            clean(a.get("tools", "")),
            context=" ".join([summary] + [b for j in jobs if j["employer"] not in _NO_SKILLS
                                          for b in j["bullets"]]),
            posting=a.get("posting", ""), company=a["company"], consented=yes)),
        p1=clean(a["p1"]), p2=clean(a["p2"]), lead=clean(a["lead"]),
        # rstrip(": ") left a trailing period, and the template appends a
        # colon, so a bullet label could render ".:" on a one-page document.
        # Strip the period too.
        cl_bullets=[(clean(b["label"]).rstrip(": .").strip(),
                     clean(undouble(b["label"], b["text"])))
                    for b in a["cl_bullets"]],
        # Every other field goes through clean(); this one did not, so an
        # ampersand or percent in a company name reached the .tex raw. A
        # bare % eats the rest of the line, silently.
        # A person the research found named for this role on the employer's
        # own pages is addressed by name (draft-applications.js says when);
        # otherwise the team, which every letter used to get.
        salutation=(clean(contact) if contact
                    else clean(salutation(a["company"])) + _SALUTATION_SUFFIX),
        # `concession` is the drafter's note about WHERE the concession sits
        # ("conceded in one sentence mid-letter in p2"). It was being prepended
        # to the closing paragraph and shipped in letters. It is metadata.
        p4=clean(a["p4"]),
    )
    if a.get("edu") in gen.EDU_DETAILS and gen.EDU_DETAILS[a["edu"]] != gen.EDU_STD:
        d["edu"] = gen.EDU_DETAILS[a["edu"]]
    # The letter's date is the day it was first rendered, kept in the draft so a
    # re-render from the kept draft.json (a renderer fix reaching an unsent
    # application) prints the date the letter was written, not the day of the fix.
    if not str(a.get("letter_date") or "").strip():
        a["letter_date"] = gen._long_date()
    d["letter_date"] = a["letter_date"]
    # The requisition the letter answers, kept with it (the .tex header) and in
    # the tracker's notes; record_drafts.py writes it there.
    d["req_id"] = str(a.get("req_id") or "").strip()
    d["consent"] = check_claims.consent_header(yes, no)
    return d


def check_batch(apps, rows=None):
    """Refuse a batch that would write any name twice or over another application.

    Checked against the tracker AND against the rest of the batch: two roles at
    one employer, neither yet in the tracker, derive the same name, and the
    second render replaced the first one's .tex before either compiled (the
    guard as first written missed it).
    """
    rows = doc_name.tracker_rows() if rows is None else rows
    claimed = {}
    for a in apps:
        stray = sorted(k for k in a if re.fullmatch(r"p\d+|intro|opening|closing", k)
                       and k not in ("p1", "p2", "p4") and str(a.get(k) or "").strip())
        if stray:
            raise SystemExit(f"{a.get('company')}: the letter template places p1, p2, lead and "
                             f"p4 only, and this draft carries {', '.join(stray)}, which would be "
                             "dropped from the letter. Fold it into those four.")
        name = final_abbr(a)
        doc_name.check_free(name, a["company"], a["role"], rows)
        other = claimed.get(name)
        if other and doc_name._norm(other["role"]) != doc_name._norm(a["role"]):
            raise FileExistsError(
                f"{name} is claimed twice in this batch: {other['company']}, {other['role']!r} "
                f"and {a['company']}, {a['role']!r}. Give one a role token "
                "(tools/stage_picks.py picks them).")
        claimed[name] = a


if __name__ == "__main__":
    # Through the same loader fit_to_page uses, so a kept draft's posting_from is
    # read in: a plain json.load rendered every kept draft untailored.
    import fit_to_page
    apps, read_in = fit_to_page.load(sys.argv[1])
    check_batch(apps)
    for a in apps:
        d = build(a)
        resume(d); letter(d)
        a["abbr"] = d["abbr"]
        print("rendered", d["abbr"], "|", d["company"])
    # The derived abbr goes back into the drafts file. Everything downstream
    # reads it from there: verify_batch.sh and audit_letters.py open the PDFs
    # by abbr, and outreach.py names the application folder with it. A draft
    # that leaves the naming to doc_name.py has no abbr to give them, and both
    # tools died on KeyError: 'abbr' rather than deriving it a second time.
    # Saved as fit_to_page saves, so a kept draft's posting, read in through its
    # fence, is never written back into draft.json outside it.
    fit_to_page.save(sys.argv[1], apps, read_in)
