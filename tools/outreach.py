"""Persist each application's posting and write a hiring-manager outreach note.

Two things an application needs beyond the two PDFs.

The posting itself, saved as documents/applications/<slug>/job_posting.md. The
scratchpad where postings were being kept dies with the session, so every
earlier round left the tracker pointing at documents whose source text no
longer existed. Interview prep, the /outcome record and any later "what did
this posting actually ask for" question all need the text.

An outreach note, saved beside it as outreach.md. A cold application is one
of hundreds in a queue; the same application with a short note to the hiring
manager or recruiter on LinkedIn is read by a person. The note is built from
what the cover letter already established, so it carries the one verified
company fact and the one matching credential and nothing else: under eighty
words, no attachment, one ask. Sending it is the candidate's call; the file
just makes it a thirty-second decision rather than a blank page.
"""
import hashlib
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_application as R
import untrusted
import docpaths
import person

try:
    from throttle import warm_routes, pending_outreach
    from company_key import key as _company_key
except ImportError:           # the note is still worth writing without them
    warm_routes = pending_outreach = None
    _company_key = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_NOTE_WORDS = 80   # "under eighty words": 79 is the most a note may carry


def slug(company, role, abbr=""):
    """Directory name for one application. The abbreviation is part of it, so
    two roles at one employer with the same title (one employer posted "Senior
    Business Analyst" twice), or two long titles that agree for eighty
    characters (one role advertised in two cities), never overwrite each other.

    Raises ValueError when company and role together hold no letter or digit.
    The caller joins the result into a path, so returning "" wrote the
    application's files straight into documents/applications/ rather than into
    a folder of its own. documents/README.md has always stated that as the
    rule; nothing enforced it, because the test covering the rule
    reimplemented it instead of calling this function, and the two had drifted
    apart on four of six cases.

    The second strip is after the truncation, not before. An 80-character cut
    can land on an underscore, and appending the abbreviation then produced the
    doubled underscore the same rule says cannot occur.

    Non-ASCII letters are dropped rather than transliterated, so `Ørsted`
    derives `rsted`. That is ugly and it is deliberate: the folder names in
    documents/applications/ were all written under this behaviour, and changing
    it would orphan every one of them."""
    s = f"{company} {role}".lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:80].strip("_")
    if not s:
        raise ValueError(
            "no folder name can be derived from company=%r role=%r: between them "
            "they hold no letter or digit. Ask for a company or role that does, "
            "and do not create a file or directory." % (company, role))
    if abbr:
        s += "_" + re.sub(r"[^a-z0-9]+", "", abbr.lower())
    return s


def _plain(s):
    """Strip the LaTeX the drafts carry so the note reads as plain text."""
    s = re.sub(r"\\textasciitilde\{\}", "~", s or "")
    s = re.sub(r"\\textbullet\{\}", "-", s)
    s = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", s)
    s = s.replace("\\%", "%").replace("\\$", "$").replace("\\&", "&")
    return re.sub(r"\s+", " ", s).strip()


def first_sentence(s):
    sents = R.split_sentences(_plain(s))   # "U.S." and "Inc." are not sentence ends
    return sents[0] if sents else ""


# The opening's "I am applying for" sentence, in any of its forms. The note
# already says that; repeating it read as a form letter.
APPLYING = re.compile(r"\b(?:applying for|I am applying|applied for|application for|"
                      r"I am writing|I would like to apply)\b", re.I)


def _within(text, budget):
    """Cut a sentence back to at most `budget` words at a clause boundary,
    and as a last resort at a word, terminated once."""
    if len(text.split()) <= budget:
        return text
    words = text.split()
    head = " ".join(words[:budget])
    cut = max(head.rfind(", "), head.rfind("; "), head.rfind(" and "))
    if cut > len(head) // 2:
        head = head[:cut]
    return head.rstrip(" ,;:.") + "."


# The closing ask. Four of them, and which one a note gets is decided by the
# employer and role rather than left to chance.
#
# There was one, on every note: *"If a quick conversation before the resume
# reaches you would help, I'd welcome it."* Two things wrong with that.
#
# It contradicts its own opening. The note starts "I've just applied", so the
# resume has already reached them; there is no before left to offer. A reader
# who notices that reads the whole message as something assembled rather than
# written, which is the one impression this note cannot afford.
#
# And it was identical across all fourteen notes in a batch. These go to people at employers who
# talk to each other, sometimes to two people at the same company, and a shared
# closing sentence is the most detectable tell a mail merge has. The rest of the
# note is already per-posting: the hook comes from the letter's opening and the
# fact from its second paragraph.
#
# Chosen by a stable hash of company and role, not at random, because the same
# draft must produce the same note. A note that changed wording between a dry
# run and the real one would be unreviewable.
#
# These are the app's defaults; a profile's voice.py may set OUTREACH_ASKS.
_VOICE = person.module("voice") if person.exists("voice.py") else None
ASKS = tuple(getattr(_VOICE, "OUTREACH_ASKS", (
    "If it would help to have the context that does not fit on a resume, "
    "I'd welcome a short conversation.",
    "Glad to give you the short version if that is useful.",
    "If you are the right person to ask about the team, I'd welcome a few minutes.",
    "Happy to answer anything the application leaves open.",
)))
OPENING = getattr(_VOICE, "OUTREACH_OPENING",
                  "Hi [name], I've just applied for the {role} role at {company}.")


def _ask_for(a):
    seed = "%s|%s" % (a.get("company", ""), a.get("role", ""))
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return ASKS[digest[0] % len(ASKS)]


# The candidate's employers, from the profile. A note that names none of them
# carries no credential, and the credential is the part that earns a reply.
# Matched as people write them, by the same matcher the letter audit uses
# (render_application.EMPLOYER_NAMED), so the two never disagree.
CREDENTIAL = R.EMPLOYER_NAMED


def check_note(note):
    """What is wrong with a finished note, or []. Run on a note a drafter wrote.

    A drafter writes a better note than a sentence picker can assemble, which
    is why `outreach_body` exists; this is what keeps it inside the rules the
    assembled note meets by construction.
    """
    problems = []
    n = len(note.split())
    if n >= MAX_NOTE_WORDS:
        problems.append(f"{n} words; the most a note may carry is {MAX_NOTE_WORDS - 1}")
    if not CREDENTIAL.search(note):
        problems.append("names none of the candidate's employers, so it carries no credential")
    if len(APPLYING.findall(note)) > 1:
        problems.append("says it has applied more than once")
    try:
        import voice_check
    except ImportError:
        return problems
    problems += [f"{f['rule']}: {f['match']}" for f in voice_check.check(note)
                 if f["severity"] == "hard"]
    return problems


def outreach_note(a):
    """Under eighty words, hard. Hook from the letter's opening, the one
    company fact from its second paragraph, one ask. A draft carrying an
    `outreach_body` gets that body after the opening line instead, checked by
    `check_note` and refused rather than trimmed when it fails.

    The hook is the first opening sentence that is not "I am applying for",
    kept in the tense the letter used: the old "I spent" -> "I've spent"
    rewrite put a role that ended two years earlier in the present perfect.
    """
    company = R.short_name(a["company"])
    role = a["role"]
    opening = OPENING.format(role=role, company=company)
    body = (a.get("outreach_body") or "").strip()
    if body:
        note = f"{opening} {body}"
        problems = check_note(note)
        if problems:
            raise ValueError(f"{a['company']}: outreach_body refused: " + "; ".join(problems))
        return note
    sents = [s for s in R.split_sentences(_plain(a.get("p1", ""))) if not APPLYING.search(s)]
    # The sentence that names one of the candidate's employers, not merely the
    # first one. Letters open on the employer's problem now (03-writing-style.md),
    # so the first sentence is usually about them: one note read "Every fraud
    # rule at <employer> has two costs..." and said nothing about the candidate.
    hook = next((s for s in sents if CREDENTIAL.search(s)), sents[0] if sents else "")
    fact = first_sentence(a.get("p2", ""))
    ask = _ask_for(a)
    note = " ".join(x for x in (opening, hook, fact, ask) if x)
    if len(note.split()) >= MAX_NOTE_WORDS:
        # Drop the company fact first; the credential is the part that earns a reply.
        note = " ".join(x for x in (opening, hook, ask) if x)
    if len(note.split()) >= MAX_NOTE_WORDS:
        room = MAX_NOTE_WORDS - 1 - len(opening.split()) - len(ask.split())
        hook = _within(hook, max(room, 8))
        note = " ".join(x for x in (opening, hook, ask) if x)
    if len(note.split()) >= MAX_NOTE_WORDS:   # a very long role title
        note = " ".join(x for x in (opening, ask) if x)
    return note


def _known_contacts(company):
    """Everyone at this employer who has already been written to, or [].

    Both halves belong here, unlike on a shortlist row. Whether they replied
    decides whether applying is cold; it decides nothing about whether to send
    a second message, and this file is the second message.
    """
    if not (warm_routes and _company_key and company):
        return []
    try:
        k = _company_key(company)
        people = list(warm_routes().get(k, []))
        seen = {p["name"] for p in people}
        people += [q for q in pending_outreach().get(k, []) if q["name"] not in seen]
        return people
    except Exception:
        return []


def write(a, meta, today):
    d = person.state("documents", "applications", slug(a["company"], a["role"], a.get("abbr", "")))
    os.makedirs(d, exist_ok=True)
    url = meta.get("url", "")
    with open(os.path.join(d, "job_posting.md"), "w") as f:
        f.write(f"# {a['role']} - {a['company']}\n\n")
        f.write(f"- **Source:** {url}\n" if url else "")
        f.write(f"- **Retrieved:** {meta.get('date', today)} via {meta.get('portal', 'portal search')}\n")
        f.write(f"- **Location:** {meta.get('location', '')}\n")
        f.write(f"- **Resume:** {docpaths.resume_rel(a['abbr'], '.pdf')}\n")
        f.write(f"- **Cover letter:** {docpaths.letter_rel(a['abbr'], '.pdf')}\n\n")
        # A `---` rule is not a fence: the posting author controls the text and
        # can write one, plus a heading that looks like ours. The nonce cannot
        # be guessed and is stripped from the content before wrapping.
        f.write(untrusted.fence(a.get("posting", ""), label="job posting") + "\n")
    # The draft object is the source both documents are rendered from. Without
    # it a fix to the renderer reaches only the batch still in someone's scratch
    # directory: when the skills line learned "experimentation design", two
    # applications drafted a week earlier and unsent could not be re-rendered
    # because nothing had kept what they were made of.
    # `python3 tools/fit_to_page.py <this file>` rebuilds both from here. The
    # posting is named, not copied: committed posting text lives only inside
    # the fence above, and fit_to_page reads it back through that fence.
    kept = dict({k: v for k, v in a.items() if k != "posting"}, posting_from="job_posting.md")
    with open(os.path.join(d, "draft.json"), "w", encoding="utf-8") as f:
        json.dump([kept], f, indent=1, ensure_ascii=False)
        f.write("\n")
    known = _known_contacts(a["company"])
    with open(os.path.join(d, "outreach.md"), "w") as f:
        f.write(f"# Outreach note - {a['company']}, {a['role']}\n\n")
        if known:
            # Without this the note says "message the hiring manager" at an
            # employer where a thread is already open, and the candidate sends a
            # cold introduction to somebody already mid-conversation with them.
            # There is no recovering from that one.
            f.write("## STOP. There is already a live thread at this employer.\n\n"
                    "Do not send a cold note here. Use the existing thread, or ask "
                    "the person below for the referral.\n\n")
            for p in known:
                line = f"- **{p['name']}**"
                if p.get("title"):
                    line += f", {p['title']}"
                line += f" [{p['status']}]"
                if p.get("next_action"):
                    line += f" {p['next_action']}"
                f.write(line + "\n")
            f.write("\nThe note below is the cold version. Keep it only if none of "
                    "the people above is the right route in.\n\n")
        f.write("Send on LinkedIn to the hiring manager or the recruiter named on the posting, "
                "the same day as the application. Replace [name]. Do not attach anything.\n\n")
        f.write("---\n\n" + outreach_note(a) + "\n\n---\n\n")
        f.write(f"Words: {len(outreach_note(a).split())}\n")
    return d


if __name__ == "__main__":
    import datetime
    today = datetime.date.today().isoformat()
    drafts = json.load(open(sys.argv[1]))
    meta = {}
    if len(sys.argv) > 2:
        raw = json.load(open(sys.argv[2]))
        for m in (raw if isinstance(raw, list) else raw.values()):
            if not m.get("abbr"):
                raise SystemExit(f"{sys.argv[2]}: the row for {m.get('company') or '(no company)'} "
                                 "has no abbr, so no draft can be matched to it; stage it "
                                 "with tools/stage_picks.py")
            meta[m["abbr"].upper()] = m
    for a in drafts:
        # Matched on the abbr the draft arrived with, then on the name its
        # files were written under (fit_to_page settles it), which is the
        # name every path below uses.
        supplied = (a.get("abbr") or "").upper()
        a["abbr"] = R.final_abbr(a)
        d = write(a, meta.get(supplied) or meta.get(a["abbr"].upper(), {}), today)
        print("wrote", os.path.relpath(d, ROOT), "|", len(outreach_note(a).split()), "words")
