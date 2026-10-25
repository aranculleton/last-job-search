"""Persist each application's posting and write a hiring-manager outreach note.

Two things an application needs beyond the two PDFs.

The posting itself, saved as documents/applications/<slug>/job_posting.md. The
scratchpad where postings were being kept dies with the session, so every
earlier round left the tracker pointing at documents whose source text no
longer existed. Interview prep, the /outcome record and any later "what did
this posting actually ask for" question all need the text.

A resume drafted for a contact who asked for it (stage_picks.py --for-contact) gets no
cold note: its outreach.md is headed with that contact's thread, what they asked and when,
and the one command that logs the resume with its file once it goes (`for_contact_md`).

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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "network"))
try:
    import schema as _schema          # the person's LinkedIn limits
    import tone as _tone
except ImportError:                   # the note is still worth writing without them
    _schema = _tone = None
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


def _abbr_on_file(company, role):
    """The abbreviation the tracker's row for this application was written under."""
    import csv_store
    csv_store.refuse_conflicts(person.state("job_search_tracker.csv"))
    try:
        rows = csv_store.dict_rows(person.state("job_search_tracker.csv"), refuse=False)
    except OSError:
        return ""
    want = (_company_key(company) if _company_key else company.lower(), slug("x", role))
    rx = docpaths.resume_name_rx()
    for r in reversed(rows):
        got = (_company_key(r.get("company")) if _company_key else str(r.get("company")).lower(),
               slug("x", r.get("role") or "x"))
        m = rx.search(r.get("cv_file") or "")
        if got == want and m:
            return m.group(1)
    return ""


# A requisition number written into the role by the tracker or a board:
# "Data Scientist II (R_1234567)", "Analyst [JR166447]", "Planner - REQ-20931".
_REF = re.compile(r"\s*(?:[\(\[]\s*(?:req(?:uisition)?|job|ref|id)?\s*[#:]?\s*[A-Za-z]{0,4}[-_ ]?"
                  r"\d{4,}[\w-]*\s*[\)\]]|[-\u2013|]\s*(?:req(?:uisition)?\s*[#:]?\s*)?"
                  r"[A-Za-z]{0,4}[-_]?\d{4,}\w*)\s*$", re.I)


def without_ref(role) -> str:
    """The role with a trailing requisition number taken off, else unchanged."""
    return _REF.sub("", str(role or "")).strip() or str(role or "")


def app_folder(company, role, abbr=""):
    """The folder one application lives in (documents/README.md, Subfolder naming).

    The commands wrote `<company>_<role>/` while the tools wrote
    `<company>_<role>_<abbr>/`, so /outcome and /interview missed the folder a
    batch had written and started a second one beside it. The folder already
    there wins: the full name, then the name without the abbreviation, then the
    one folder for this company and role under any abbreviation. Otherwise the
    full name, which is the rule.

    A role carrying its requisition number, "Data Scientist II (R_1234567)", is also
    looked for without it: the folder was named before the number was written into the
    tracker, and the interview pack built itself from an empty folder.
    """
    base = person.state("documents", "applications")
    abbr = abbr or _abbr_on_file(company, role)
    stem = slug(company, role)
    full = slug(company, role, abbr) if abbr else stem
    bare = without_ref(role)
    plain = slug(company, bare) if bare != role else stem
    for name in dict.fromkeys((full, stem, plain)):
        if os.path.isdir(os.path.join(base, name)):
            return os.path.join(base, name)
    try:
        hits = [d for d in sorted(os.listdir(base)) for st in dict.fromkeys((stem, plain))
                if d.startswith(st + "_") and "_" not in d[len(st) + 1:]
                and os.path.isdir(os.path.join(base, d))]
    except OSError:
        hits = []
    return os.path.join(base, hits[0] if len(hits) == 1 else full)


def employer_folders(company) -> list[str]:
    """Every application folder at this employer, by name."""
    base = person.state("documents", "applications")
    try:
        prefix = slug(company, "") + "_"
        return sorted(d for d in os.listdir(base)
                      if d.startswith(prefix) and os.path.isdir(os.path.join(base, d)))
    except (OSError, ValueError):
        return []


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
# The person's word for the document (person.json documents.noun): a CV market
# read "does not fit on a resume" in a note from someone who calls it a CV.
_NOUN = person.get("documents.noun", "resume")
ASKS = tuple(getattr(_VOICE, "OUTREACH_ASKS", (
    f"If it would help to have the context that does not fit on a {_NOUN}, "
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
    # Every rule another outbound message meets, through the one gate: compose.validate()
    # for a "message", the kind for a note to a hiring manager about an application already
    # in, where saying it was applied for is the point. This ran a subset of it (tone and
    # voice_check), and passed "really interested me", which validate refuses as flattery
    # (2026-10-20). Before that, only voice_check ran, and a note claiming citizenship the
    # candidate does not hold went through.
    sent = note.replace("[name]", "Sam")
    try:
        import compose
    except (ImportError, RuntimeError, OSError, AttributeError):
        compose = None                # no networking profile: the checks it can still run
    # "Sam" stands in for a reader nobody has named yet, so a note greeting its real
    # reader is not greeting the wrong one: that check is left to a call that knows them.
    if compose is not None:
        return problems + [f"{v.rule}: {v.text}" for v in compose.validate(
            sent, "message", name="Sam", seniority="senior", reader="decision_maker")
            if v.rule != "greeting_wrong_name"]
    if _tone is not None:
        problems += [f"{v.rule}: {v.text}" for v in
                     _tone.check(sent, recipient_seniority="senior", name="Sam")
                     if v.rule != "greeting_wrong_name"]
    try:
        import voice_check
    except ImportError:
        return problems
    problems += [f"{f['rule']}: {f['match']}" for f in voice_check.hard(note)]
    return problems


def short_note(a, limit=None):
    """The note cut to fit a connection request, for someone not yet connected.

    The note runs to about 470 characters, which goes as a message to a
    connection or as an InMail, never as a connection request (300 characters on
    Premium, 200 on a free account). Same pieces, fewer of them.
    """
    limit = limit or (_schema.LIMITS["connection_note_chars"] if _schema else 200)
    company, role = R.short_name(a["company"]), a["role"]
    opening = OPENING.format(role=role, company=company)
    sents = [s for s in R.split_sentences(_plain(a.get("p1", ""))) if not APPLYING.search(s)]
    hook = next((s for s in sents if CREDENTIAL.search(s)), "")
    ask = _ask_for(a)
    for parts in ((opening, hook, ask), (opening, ask), (opening,)):
        note = " ".join(x for x in parts if x)
        if len(note) <= limit:
            return note
    return ""


def whole_note(company, role, body):
    """The note as it is sent: the fixed opening line, then the drafted body."""
    return f"{OPENING.format(role=role, company=R.short_name(company))} {body.strip()}"


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
        note = whole_note(a["company"], role, body)
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


def folder(a):
    """The folder this draft's files are written to."""
    return person.state("documents", "applications", slug(a["company"], a["role"], a.get("abbr", "")))


def archive_posting(d, a, meta, today):
    """Write job_posting.md once. Returns "written", "kept" or "none".

    An existing file is left alone (/apply Step 6b): the archived copy is what
    was applied to. Re-running this over a batch rewrote it every time, and over
    a kept draft.json, whose posting is named rather than carried, it wrote an
    empty fence over the only copy of the posting. A draft with no posting text
    writes nothing, rather than an archive holding none.
    """
    path = os.path.join(d, "job_posting.md")
    if os.path.exists(path):
        return "kept"
    posting = a.get("posting") or ""
    if not posting.strip():
        return "none"
    url = meta.get("url", "")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {a['role']} - {a['company']}\n\n")
        f.write(f"- **Source:** {url}\n" if url else "")
        f.write(f"- **Retrieved:** {meta.get('date', today)} via {meta.get('portal', 'portal search')}\n")
        f.write(f"- **Location:** {meta.get('location', '')}\n")
        if str(a.get("req_id") or "").strip():
            f.write(f"- **Requisition:** {str(a['req_id']).strip()}\n")
        if str(a.get("contact_person") or "").strip():
            f.write(f"- **Named on the posting:** {str(a['contact_person']).strip()}\n")
        f.write(f"- **{docpaths.noun_word()}:** {docpaths.resume_rel(a['abbr'], '.pdf')}\n")
        f.write(f"- **Cover letter:** {docpaths.letter_rel(a['abbr'], '.pdf')}\n\n")
        # A `---` rule is not a fence: the posting author controls the text and
        # can write one, plus a heading that looks like ours. The nonce cannot
        # be guessed and is stripped from the content before wrapping.
        f.write(untrusted.fence(posting, label="job posting") + "\n")
    return "written"


def for_contact_of(a, meta=None) -> str:
    """The contact_id of whoever this resume was drafted for, or ""."""
    return str((meta or {}).get("for_contact") or a.get("for_contact") or "").strip()


def for_contact_md(a, cid, today) -> str:
    """outreach.md for a resume drafted for a contact: their thread, never a cold note."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "network"))
    import state
    contact = state.already_contacted(state.load_contacts(person.state("network_contacts.csv")),
                                      contact_id=cid) or {}
    name = (state.person_name(contact.get("name")) or str(contact.get("name") or "")
            or str(a.get("for_contact_name") or cid))
    pdf = docpaths.resume_rel(a["abbr"], ".pdf")
    rows = state.threads_for(state.load_threads(person.state("network_threads.csv")), cid)
    asks = [r for r in rows if state.asks_for_resume(r)]
    portal = (str(a.get("for_contact_route") or "") or state.resume_route(rows, cid)) \
        == state.ROUTE_PORTAL
    head = (f"## This goes in through the portal, with {name} named as your referrer"
            if portal else f"## This goes to {name}, who asked for it")
    out = [f"# {_NOUN[:1].upper() + _NOUN[1:]} for {name} - {a['company']}, {a['role']}", "",
           head, ""]
    if asks and not portal:
        words = " ".join(str(asks[-1].get("full_text") or asks[-1].get("summary") or "").split())
        out += [f"They asked on {asks[-1].get('date')}: \"{words[:300]}\"", ""]
    if portal:
        # The route they asked for: apply and name them. Nothing goes to them, so there is
        # no message to log, and RECONCILE asks for none (state.through_portal).
        out += [f"Apply with {pdf} (and the cover letter, if the role is a posted one) "
                f"at {a.get('url') or 'the posting'}, and put {name} where the form asks for a "
                "referrer. Nothing goes to them, so there is no message to log. Tell them in "
                "the thread once it is in. No cold note: they are the route in.", ""]
    else:
        out += [f"Send them {pdf} (and the cover letter, if the role is a posted one) in that "
                "thread or by email. No cold note: they are the route in, and a note to someone "
                "else at the employer would land beside their referral.", "",
                "When it goes, log it with the file, so every chat knows which one they hold:", "",
                "    " + state.log_resume_command(cid, pdf), ""]
    if rows:
        out += ["## The thread so far", ""]
        for r in rows[-6:]:
            who = "you" if state._direction(r) == "out" else (name.split()[0] if name else "them")
            said = " ".join(str(r.get("full_text") or r.get("summary") or "").split())
            out.append(f"- {r.get('date')} {who}: {said[:240]}")
        out.append("")
    return "\n".join(out)


def write(a, meta, today):
    d = folder(a)
    os.makedirs(d, exist_ok=True)
    archived = archive_posting(d, a, meta, today)
    if archived == "none":
        print(f"outreach: {a['company']}: the draft holds no posting text, so no job_posting.md "
              "was written. Archive the posting by hand from the text that was applied to.",
              file=sys.stderr)
    # The draft object is the source both documents are rendered from. Without
    # it a fix to the renderer reaches only the batch still in someone's scratch
    # directory: when the skills line learned "experimentation design", two
    # applications drafted a week earlier and unsent could not be re-rendered
    # because nothing had kept what they were made of.
    # `python3 tools/fit_to_page.py <this file>` rebuilds both from here. The
    # posting is named, not copied: committed posting text lives only inside
    # the fence above, and fit_to_page reads it back through that fence.
    kept = {k: v for k, v in a.items() if k not in ("posting", "posting_from")}
    # What the score rested on: the round's shortlist is pruned away, and the interview
    # pack (tools/interview_pack.py) reads fit_why's deductions weeks later.
    for k in ("fit", "fit_why", "bar", "bar_reason", "for_contact", "for_contact_name",
              "for_contact_channel", "for_contact_route"):
        if meta.get(k) not in (None, "", []) and k not in kept:
            kept[k] = meta[k]
    if os.path.exists(os.path.join(d, "job_posting.md")):
        kept["posting_from"] = "job_posting.md"
    with open(os.path.join(d, "draft.json"), "w", encoding="utf-8") as f:
        json.dump([kept], f, indent=1, ensure_ascii=False)
        f.write("\n")
    cid = for_contact_of(a, meta)
    if cid:
        with open(os.path.join(d, "outreach.md"), "w", encoding="utf-8") as f:
            f.write(for_contact_md(dict(a, url=a.get("url") or meta.get("url", ""),
                                        **{k: v for k, v in kept.items()
                                           if k.startswith("for_contact")}), cid, today))
        return d
    known = _known_contacts(a["company"])
    replied = [p for p in known if p.get("status") not in SENT_NO_REPLY]
    with open(os.path.join(d, "outreach.md"), "w", encoding="utf-8") as f:
        f.write(f"# Outreach note - {a['company']}, {a['role']}\n\n")
        if replied:
            # Without this the note says "message the hiring manager" at an
            # employer where a thread is already open, and the candidate sends a
            # cold introduction to somebody already mid-conversation with them.
            # There is no recovering from that one.
            f.write("## STOP. There is already a live conversation at this employer.\n\n"
                    "Do not send a cold note here. Ask the person below for the referral "
                    "inside that conversation (compose.referral_ask).\n\n")
        elif known:
            # Messaged and silent: asking them for a referral is the third stage
            # sent as the first, and a second message to somebody sitting on the
            # first is the one thing CLAUDE.md says not to do.
            f.write("## Someone here has been messaged and has not replied.\n\n"
                    "Applying is fine. Do not message them again, and do not send this note "
                    "to them: it is for a different person, the hiring manager or recruiter.\n\n")
        if known:
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
        try:
            note = outreach_note(a)
        except ValueError as e:
            f.write(f"**Not ready to send.** The note was refused: {e}. Rewrite its body and run "
                    "`python3 tools/outreach.py` again.\n")
            return d
        limit = _schema.LIMITS["connection_note_chars"] if _schema else 200
        f.write("Send to the hiring manager or the recruiter named on the posting, the same "
                "day as the application. Replace [name]. Do not attach anything.\n\n")
        f.write("---\n\n" + note + "\n\n---\n\n")
        f.write(f"Words: {len(note.split())}. Characters: {len(note)}.\n\n")
        if len(note) > limit:
            short = short_note(a, limit)
            f.write(f"Longer than a connection request ({limit} characters on your LinkedIn "
                    "plan): send it as a message to someone you are already connected with, "
                    "or as an InMail. To someone you are not connected with, send this as the "
                    "connection request instead:\n\n")
            f.write("---\n\n" + (short or "(nothing fits; send the request without a note)")
                    + "\n\n---\n\n")
        problems = check_note(note)
        if problems:
            f.write("**Check before sending:** " + "; ".join(problems) + "\n")
    return d


SENT_NO_REPLY = {"awaiting_reply", "connected_no_reply"}


if __name__ == "__main__":
    import datetime
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("usage: python3 tools/outreach.py <drafts.json> [apps_in.json]\n"
              "       python3 tools/outreach.py --folder \"<Company>\" \"<Role>\" [ABBR]\n"
              "       python3 tools/outreach.py --check-note <note> [--company C --role R]\n\n"
              + __doc__.strip().split("\n\n")[0])
        sys.exit(0 if len(sys.argv) > 1 else 2)
    if sys.argv[1:2] == ["--folder"]:
        # Every command that reads or writes an application's archive asks here,
        # so there is one answer to "which folder is this application's".
        if len(sys.argv) not in (4, 5):
            raise SystemExit('usage: outreach.py --folder "<Company>" "<Role>" [ABBR]')
        print(os.path.relpath(app_folder(*sys.argv[2:]), person.state()))
        sys.exit(0)
    if sys.argv[1:2] == ["--check-note"]:
        # /apply writes its note by hand: the same checks the assembled note meets.
        # A drafted `outreach_body` is checked with --company and --role, which
        # put the fixed opening line in front of it as outreach_note() does: the
        # body alone was checked against the 80 words the whole note must fit.
        import argparse
        ap = argparse.ArgumentParser(prog="outreach.py --check-note")
        ap.add_argument("note", nargs="+")
        ap.add_argument("--company", help="with --role: the note is a body; check it whole")
        ap.add_argument("--role")
        ns = ap.parse_args(sys.argv[2:])
        if bool(ns.company) != bool(ns.role):
            ap.error("--company and --role go together")
        note = " ".join(ns.note)
        if ns.company:
            note = whole_note(ns.company, ns.role, note)
        found = check_note(note)
        for problem in found:
            print(problem)
        sys.exit(1 if found else 0)
    today = datetime.date.today().isoformat()
    # Through the loader fit_to_page uses, so a kept draft.json has its posting
    # read back in through the fence rather than arriving with none.
    import fit_to_page
    drafts, _ = fit_to_page.load(sys.argv[1])
    meta = {}
    if len(sys.argv) > 2:
        raw = json.load(open(sys.argv[2], encoding="utf-8"))
        for m in (raw if isinstance(raw, list) else raw.values()):
            if not m.get("abbr"):
                raise SystemExit(f"{sys.argv[2]}: the row for {m.get('company') or '(no company)'} "
                                 "has no abbr, so no draft can be matched to it; stage it "
                                 "with tools/stage_picks.py")
            meta[m["abbr"].upper()] = m
    refused = []
    for a in drafts:
        # Matched on the abbr the draft arrived with, then on the name its
        # files were written under (fit_to_page settles it), which is the
        # name every path below uses.
        supplied = (a.get("abbr") or "").upper()
        a["abbr"] = R.final_abbr(a)
        # The note is built before anything is written. A refused body raised
        # half way through writing outreach.md, which left a file holding only
        # its heading, and stopped the batch: every later posting lost its
        # archived text and its kept draft.
        m = meta.get(supplied) or meta.get(a["abbr"].upper(), {})
        cid = for_contact_of(a, m)
        try:
            words = 0 if cid else len(outreach_note(a).split())
        except ValueError as e:
            refused.append(f"{a.get('company')}: {e}")
            words = 0
        had = os.path.exists(os.path.join(folder(a), "job_posting.md"))
        d = write(a, m, today)
        print("wrote", os.path.relpath(d, ROOT), "|",
              (f"for {cid}: their thread, no cold note" if cid else f"{words} words")
              + (" | kept the archived job_posting.md" if had else ""))
    if refused:
        print("\nOUTREACH NOTE REFUSED (its outreach.md says so; every other file was written). "
              "Rewrite the body and run this again:\n  " + "\n  ".join(refused))
        sys.exit(1)
