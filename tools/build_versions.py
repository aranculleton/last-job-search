#!/usr/bin/env python3
"""How each part of the build is done, by version, and which version made what a person has.

The app's code reaches a person's repo on every sync. What the code made before the
sync does not change by itself: the profile /setup wrote, the job boards it built, the
call-prep documents, the drafts waiting to be sent, the postings ruled out under older
rules. When the app learns to do one of those better, an older repo keeps the old
result and its owner cannot know to ask. The maintainer searched two weak job boards for
days after the app learned to research and build the ones that serve a market.

So every part of the build that leaves something behind in a person's repo is a
versioned METHOD, and every other file is in KEEPS_NOTHING with the reason it needs no
version. Nothing is in neither: tests/test_build_versions.py lists every app file and
fails on one that is unaccounted for.

- A method's text is fingerprinted: the files that say how it is done, and for a part of
  /setup the regions of setup.md marked `<!-- section: <name> -->`. Change one byte and
  the test fails until a version is added saying what changed and whether what an older
  version made should be redone (`rerun`). A wording fix costs nobody anything; a better
  method reaches everyone. The decision cannot be skipped, only made.
- profile/build_versions.json records which version made what this repo has. With no
  record, a part of /setup is dated from when the profile was created (git), and
  anything else is version 1.
- What redoes it, by `by`:
    upgrade  tools/profile_upgrades.py lists `method-<name>`, and /upgrade redoes it in
             the background with no one asking
    instant  the sync itself redoes it (`redo <name>`) and commits it
    round    every round applies it by itself (see throttle.ruled_out)
    network  every /network run applies it first, in a chat that can read the people
             it writes to (step 1 there): a background agent in a cloud chat cannot
    you      it needs the person's consent, so it is asked, a few at a time

    python3 tools/build_versions.py                   # each method: this repo's version, the app's
    python3 tools/build_versions.py record boards     # this repo now holds the app's boards version
    python3 tools/build_versions.py record --setup    # after a full /setup
    python3 tools/build_versions.py redo prep-docs    # an instant method: redo it and record it
    python3 tools/build_versions.py behind network-notes  # what is better now; exit 1 if any
    python3 tools/build_versions.py fingerprints      # for a developer adding a version
"""

from __future__ import annotations

import csv
import datetime as dt
import fnmatch
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import person  # noqa: E402
from personal_paths import is_personal  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = ".claude/commands/setup.md"
RECORD = "build_versions.json"
FIRST_RELEASE = "2026-10-14"
# Marked in setup.md for what no re-run would redo (empty state files).
NOT_VERSIONED = "none"


def _first(what: str = "the first release") -> tuple:
    return (1, FIRST_RELEASE, False, what)


# Each version: (number, date, rerun, what changed). `rerun` says whether what an
# earlier version made should be made again. Version 1 is the first release's method.
METHODS: dict[str, dict] = {
    # ---- the parts of /setup: each writes part of the profile once
    "boards": {
        "setup": True, "by": "upgrade", "priority": 2, "time": "~20 min",
        "gives": "the job boards that serve your market found, built and searched every round",
        "run": "/setup --section boards",
        "files": (".claude/commands/add-portal.md", "tools/robots_check.py",
                  "tools/ats_boards.py", "tools/portals.py", "tools/openroles/*"),
        "versions": (
            _first("the first release: LinkedIn and freehire, and /add-portal offered"),
            (2, "2026-10-15", True, "the boards that serve your country, field and level researched "
                                    "and cited, the best one or two built and searched every round, "
                                    "employer boards probed, the LinkedIn notice, the job-alerts question"),
            (3, "2026-10-15", True, "every board you have searches all your places, not just your "
                                    "home city, covers the towns around each, and searches remote "
                                    "roles where the board can filter for them"),
            (4, "2026-10-15", False, "an invented example in place of a real city"),
            (5, "2026-10-15", False, "employer boards date a posting by when it was first published, not last edited"),
            (6, "2026-10-15", False, "--find locates an employer's board from its name or careers page (through the vendored openroles), and Lever postings include their requirement lists"),
            (7, "2026-10-15", True, "Workday boards whose listing leaves the location out are read again: the place comes from each posting's path, so a board probed as '0 in range' for that reason now counts"),
            (8, "2026-10-18", False, "Workday details read on Python 3.9, a Mac's own python3"),
            (9, "2026-10-18", False, "LinkedIn's job search stays on and uses no LinkedIn account; only the person switches it off"),
            (10, "2026-10-19", False, "a docstring's example Workday location is invented"),
            (11, "2026-10-19", False, "an employer's own board counts a posting in any town of the person's metro, its dates are read the one way, a Workday search reads past its second page, a Greenhouse or Lever posting is kept when any place it lists is wanted, and Lever's EU instance is read"),
            (12, "2026-10-19", True, "every hiring system openroles reads is searched (Workable, Teamtailor, Personio, Recruitee, Rippling, JazzHR, Gem, Polymer, Manatal, Homerun and ClearCompany besides the first four) and careers sites that publish their jobs for search engines: each target employer's board is looked for again on all of them"),
            (13, "2026-10-19", False, "a private name the board reader no longer has says, in its own error, what that means and where to look; --find says when a board was only guessed from a name, with its size and roles, and reads each board once"),
            (14, "2026-10-19", False, "a metro name is matched at its edges the way every other name is; nothing to search again"),
        ),
        "fingerprint": "bec86bbb11182c28",
    },
    "search": {
        "setup": True, "by": "upgrade", "priority": 2, "time": "~20 min",
        "gives": "postings scored in your field's words, at your level",
        "run": "/setup --section search",
        "files": (),
        "versions": (
            _first(),
            (2, "2026-10-15", True, "the scoring vocabulary, level patterns, screen flags and years "
                                    "of experience written for your field, not the example analyst's"),
            (3, "2026-10-15", False, "asks for your LinkedIn plan with the rest of networking.py "
                                     "and keeps the note's pieces short enough for a free account; "
                                     "the plan reaches older profiles as its own question"),
            (4, "2026-10-17", False, "asks whether Claude may read LinkedIn profiles in your own browser before writing to someone"),
            (5, "2026-10-17", False, "the browser-read question says it reads only the people a search surfaced, at a person's pace"),
            (6, "2026-10-17", False, "the browser-read question names screenshots as the way that works on a phone"),
            (7, "2026-10-18", False, "the profile-reads question says finding people never needs a read, and that a read is for the best ten a run finds"),
            (8, "2026-10-19", False, "skills.py may list the tools a field treats as interchangeable (FAMILIES); the app's own list applies without it"),
        ),
        "fingerprint": "214fc1cce51145ba",
    },
    "market": {
        "setup": True, "by": "upgrade", "priority": 3, "time": "~15 min",
        "gives": "eligibility, pay and places checked the way your market words them",
        "run": "/setup --section market",
        "files": (".claude/skills/job-application-assistant/04-job-evaluation.md",),
        "versions": (
            _first(),
            (2, "2026-10-15", True, "eligibility written for any work status, your country, your "
                                    "working week, and the internal-only and probe words in your "
                                    "market's language"),
            (3, "2026-10-15", True, "the places a round searches cover your whole metro area and "
                                    "your country, and remote roles filed under the wider regions "
                                    "an employer abroad hiring where you live posts them in"),
            (4, "2026-10-15", False, "docs corrected against the code: what the commands, skills and guides say now matches what the tools do"),
            (5, "2026-10-17", False, "salary and market research reads the one company-research cache and its freshness rule"),
        ),
        "fingerprint": "4ed21873e30e4440",
    },
    "documents": {
        "setup": True, "by": "upgrade", "priority": 3, "time": "~10 min",
        "gives": "resumes and letters in your market's form and your own headings",
        "run": "/setup --section documents",
        "files": (),
        "versions": (
            _first(),
            (2, "2026-10-15", True, "Skills headings in your own words, page count and section order "
                                    "for your career, and a letter that greets in your language"),
            (3, "2026-10-18", False, "asks early where the person will mostly work and records it in profile/place.json"),
        ),
        "fingerprint": "50f6d57697d40f52",
    },
    "voice": {
        "setup": True, "by": "upgrade", "priority": 3, "time": "~10 min",
        "gives": "summaries and outreach in your own voice, aimed at your own field's people",
        "run": "/setup --section voice",
        "files": (),
        "versions": (
            _first(),
            (2, "2026-10-15", True, "your statement templates in your profile, /network looking for "
                                    "your own function's people, outreach in your words"),
            (3, "2026-10-17", False, "OPENALEX is turned on only for a field where people publish"),
            (4, "2026-10-17", False, "researches where the person's people are named (PEOPLE_SOURCES) and asks once for their connections export"),
        ),
        "fingerprint": "9c3a92a6c1812e82",
    },
    "history": {
        "setup": True, "by": "upgrade", "priority": 3, "time": "~15 min",
        "gives": "your roles, bullets and stories in a form every tool reads",
        "run": "/setup --section history",
        "files": (".claude/skills/job-application-assistant/07-interview-prep.md",),
        "versions": (
            _first(),
            (2, "2026-10-15", True, "role headings the tools can read, bullet themes cued in your "
                                    "field's words, and STAR examples kept in your profile"),
            (3, "2026-10-15", False, "asks whether you pay for LinkedIn Premium"),
            (4, "2026-10-19", False, "every STAR story ends on a Use for line naming the questions it answers"),
            (5, "2026-10-19", False, "the interview template's permit answer follows your own disclosure rule, and a stock answer can name the kinds of employer it is not for"),
        ),
        "fingerprint": "05446dfa33327399",
    },
    # ---- what the build makes over time and keeps
    "prep-docs": {
        "by": "instant", "priority": 3, "applies": "prep_docs",
        "gives": "every call-prep document rewritten by the current prep",
        "run": "python3 tools/build_versions.py redo prep-docs",
        # Only what an older prep wrote: --all rewrote every document, hundreds in one
        # repo, and created one for every contact who never had a call.
        "command": ("python3", "tools/network/prep.py", "--stale-only"),
        "paths": ("documents/network/*",),
        "files": ("tools/network/prep.py", "tools/network/profile_facts.py", "tools/bridges.py",
                  ".claude/commands/prep.md"),
        "versions": (
            _first(),
            (2, "2026-10-14", True, "role headings that end in a city are read, so your roles and "
                                    "their evidence appear in every prep document"),
            (3, "2026-10-15", False, "the prep document is shown in full in the reply, "
                                    "never only its path"),
            (4, "2026-10-15", False, "a gap asked only as a preference is never a reason not to apply"),
            (5, "2026-10-15", False, "docs corrected against the code: what the commands, skills and guides say now matches what the tools do"),
            (6, "2026-10-17", True, "the prep document says what was read about them: the history you share and what they have posted"),
            (7, "2026-10-17", False, "one research cache with its freshness rule: stale research, roles open there you scored well, the letter's fact and concessions, and the cache's own cautions in the call prep"),
            (8, "2026-10-19", False, "each document is stamped with the prep that wrote it, and only an older one is rewritten; a tool you lack is never claimed unless you say yes"),
            (9, "2026-10-19", False, "a quote from a reading is cut at a word, never mid-word"),
            (10, "2026-10-19", False, "business days skip your public holidays; a name is matched at its edges whatever it ends on"),
            (11, "2026-10-19", True, "call preps name the referrer, speak to a recruiter in your employer-facing words, mark profile wording to rewrite and keep your rewritten answers, point a recruiter screen to its process's own document, and are rebuilt when research, the tracker or an approaching call changes what they should say"),
            (12, "2026-10-20", False, "--all leaves a prep document alone when only its date would change, and counts the ones already current; a prep asked for one contact is still written fresh"),
            (13, "2026-10-20", False, "a researched fragment inside a question is cut where a clause ends; a fact about what a team does is followed by a question about its work, never about how it is set up"),
        ),
        "fingerprint": "49cb05d9b71dd6d3",
    },
    "drafts": {
        "by": "upgrade", "priority": 2, "applies": "unsent_drafts", "time": "~5 min",
        "gives": "applications not yet sent re-rendered and re-checked by the current build",
        "run": "for each tracker row still at `drafted`, python3 tools/fit_to_page.py "
               "documents/applications/<slug>/draft.json, then tools/verify_batch.sh on them; "
               "never one already sent",
        "files": ("templates/*", "tools/render_application.py", "tools/fit_to_page.py",
                  "tools/skills_block.py", "tools/allocate.py", "tools/bullet_library.py",
                  "tools/docpaths.py", "tools/doc_name.py", "tools/outreach.py",
                  "tools/screening_answers.py", "tools/record_drafts.py", "tools/stage_picks.py",
                  "tools/check_claims.py", "tools/check_numbers.py", "tools/voice_check.py",
                  "tools/locale_rules.py",
                  "tools/audit_letters.py", "tools/verify_pdf.py", "tools/verify_batch.sh",
                  "tools/untrusted.py", "tools/bridges.py",
                  ".claude/commands/apply.md", ".claude/commands/add-template.md",
                  ".claude/skills/job-application-assistant/03-writing-style.md",
                  ".claude/skills/job-application-assistant/05-cv-templates.md",
                  ".claude/skills/job-application-assistant/06-cover-letter-templates.md",
                  ".claude/skills/job-application-assistant/08-application-forms.md",
                  ".claude/skills/job-application-assistant/verification-checklist.md",
                  ".claude/workflows/draft-applications.js", ".claude/agents/grounding-auditor.md",
                  "RUNBOOK.md", "texmf/*", "cv/main_example.tex", "cover_letters/cover.cls",
                  "cover_letters/cover_example.tex", "cover_letters/OpenFonts/*"),
        "versions": (
            _first(),
            (2, "2026-10-15", False, "the outreach note checked by the networking tone rules, "
                                    "with a connection-sized version and no referral ask to "
                                    "someone who has not replied"),
            (3, "2026-10-15", False, "reads what the person has taught it (tools/learned.py) before drafting, flags the phrases they never want, their wording replaces the defaults, and every output is shown in the reply"),
            (4, "2026-10-15", False, "learns from results: a resume that reached an interview "
                                    "lifts the bullets it used, and drafting reads it first "
                                    "(tools/what_works.py)"),
            (5, "2026-10-15", False, "a single /apply drafts, renders and verifies through the "
                                    "same pipeline as a batch, keeps its draft.json, and asks "
                                    "first whether you have already applied"),
            (6, "2026-10-15", False, "a refused outreach note no longer stops the batch, '8+ years' and 'per cent' are checked, a draft with no posting is said, the deadline reaches the tracker, and the bullet split no longer swings on a fraction of a point"),
            (7, "2026-10-15", False, "the verification checklist and the tools table moved out of CLAUDE.md into files read when they are needed, so every session starts lighter"),
            (8, "2026-10-15", False, "docs corrected against the code: what the commands, skills and guides say now matches what the tools do"),
            (9, "2026-10-15", False, "stage_picks.py reminds a chat that has not checked the app today; what it stages is unchanged"),
            (10, "2026-10-17", False, "the runbook lists tools/network/reading.py among the tools run directly"),
            (11, "2026-10-17", False, "one source for the document-language rules (dashes, spelling in every locale, the document's noun, a status not held) and one voice filter shared with messages"),
            (12, "2026-10-17", False, "rulings name the blocker or gate they rest on (rank, the scraper skill); the day's sync carries the model check"),
            (13, "2026-10-18", False, "fit_to_page runs on Python 3.9"),
            (14, "2026-10-18", False, "RUNBOOK names the people ladder and the Claude surfaces registry"),
            (15, "2026-10-19", True, "a document already sent is never rendered over; a letter's figures are checked; a trimmed resume keeps the line that describes each job; a letter keeps its date, drops legal forms from the employer's name, is addressed to the person the employer names, and is flagged where it repeats the resume; a claimed skill the profile does not hold is caught, a held tool of the same family stands in for one a posting names that the person lacks; and every skill a posting names that the profile does not hold is asked about before drafting, and only a yes puts it on the resume"),
            (16, "2026-10-19", False, "an application from any employer board openroles reads is recorded as applied online"),
            (17, "2026-10-19", False, "RUNBOOK says what to do when a person's own tests fail after an update; an application's folder is found when its role carries a requisition number"),
            (18, "2026-10-19", False, "The person is asked in plain words before any of their own failing tests is deleted; wording only, nothing to redo"),
            (19, "2026-10-19", False, "the voice check skips a quoted list of words to avoid, so a document that warns against a phrase is not flagged for it"),
            (20, "2026-10-19", False, "every command prints its usage instead of crashing with no arguments, the voice check reads a never-say phrase however it is punctuated, and your own never-write rules are checked"),
            (21, "2026-10-19", False, "the PDF check's missing-Poppler error gives the winget command on Windows, not Chocolatey"),
            (22, "2026-10-19", False, "the PDF check finds Poppler where a Mac or Windows installs it, even when the shell's PATH lacks it; the voice check hears short spoken answers as spoken and catches a third-person headline; form answers read a profile with no screening.py"),
            (23, "2026-10-19", False, "RUNBOOK: what to do when two chats applied the same profile upgrade"),
            (24, "2026-10-20", False, "the voice check skips HTML comments; texmf's README says nothing links ~/texmf; the grounding auditor passes a pasted note's reader to validate()"),
            (25, "2026-10-20", False, "an answer that opens on a short framing line is in the first person when it says I by its third sentence"),
        ),
        "fingerprint": "78c00e4738ecee9c",
    },
    "interview": {
        "by": "upgrade", "priority": 2, "applies": "live_interviews", "time": "~15 min",
        "gives": "the prep pack for each interview still running rewritten the current way",
        "run": "for each tracker row at `interview`, /interview <company> again, its pack "
               "written beside the old one",
        "files": (".claude/commands/interview.md", "tools/interview_pack.py"),
        "versions": (
            _first(),
            (2, "2026-10-15", False, "reads what the person has taught it (tools/learned.py) before drafting, flags the phrases they never want, their wording replaces the defaults, and every output is shown in the reply"),
            (3, "2026-10-15", False, "finds the application's folder under whichever name it "
                                    "was written, instead of starting a second one"),
            (4, "2026-10-15", False, "docs corrected against the code: what the commands, skills and guides say now matches what the tools do"),
            (5, "2026-10-17", False, "interview research reads the one company-research cache and its freshness rule"),
            (6, "2026-10-19", True, "the pack is built by tools/interview_pack.py: sourced, one screen first, the money the form already named, the question bank, warm routes, an offer branch, mock feedback kept, and each skill you said yes to claiming flagged as one to expect a question on"),
            (7, "2026-10-19", True, "a pack finds its application however the role is written (a requisition number in it), reads a hand-written outcome's rounds, finds the referrer from every record, and never tells you to message someone whose row says to leave them be"),
            (8, "2026-10-19", True, "a pack treats waiting on someone's reply as leave them be, says booked only when the round has a date, quotes rows whole or cut at a word, carries every section of a hand-written outcome file, keeps its do-not-say list out of the voice check, and prepares a question you were told about as reported, with its source"),
            (9, "2026-10-19", True, "one living document per hiring process, a process with no application included: answers written to be said and checked, what each interviewer is assessing and wants to hear, the format, small talk with a purpose, and what the employer's people have been told"),
            (10, "2026-10-19", True, "the person's own reasons are asked, never drafted; stock answers matched through employer names and Use for:, and checked against the employer; what each person there was told, and which messages have no text; the warm route by stored status; the recruiter assumed for a screen; the format of this round only; which team, and the process at a screen; just arrived honoured; a posting file for every process"),
            (11, "2026-10-20", True, "Likely questions is notes, never words to say, and never repeats an answer already written; a stock answer marked Not for this kind of employer, or holding a fill-in, is left out with the reason; notes beside an answer are kept and never checked; a rebuild keeps the person's own layout and never adds the Checking line twice; a screen asks its standard questions first; hooks are whole sentences"),
        ),
        "fingerprint": "85cc60101210f4c4",
    },
    "research": {
        "by": "upgrade", "priority": 3, "applies": "live_applications", "time": "~5 min each",
        "gives": "the research behind every live application gathered the current way",
        "run": "the employer-researcher again for each employer with an application at "
               "`drafted` or `interview`, refreshing company_research/<key>.json",
        "files": (".claude/agents/employer-researcher.md",
                  ".claude/skills/job-application-assistant/09-web-research.md",
                  "tools/company_research.py"),
        "versions": (
            _first(),
            (2, "2026-10-17", False, "one company-research cache (tools/company_research.py): load, save, the freshness rule in one constant, and the workflow's research stage following the employer researcher"),
            (3, "2026-10-19", False, "a cached finding's age is read the one way every tool reads a date"),
            (4, "2026-10-19", False, "a site answering 503 has a fallback, a fact known only from a search summary is labelled unread, and teams and how the employer interviews are kept for the pack"),
        ),
        "fingerprint": "efea1c5929a0e202",
    },
    "networking": {
        "by": "upgrade", "priority": 3, "applies": "contacts", "time": "~15 min",
        "gives": "the people worth contacting at your target employers found the current way",
        "run": "for each employer already in network_contacts.csv, rungs 1 to 3 of /network's "
               "ladder only: their connections there (`sources.py connections`), the two plain "
               "title searches from `discovery.queries_for()` run through `sources.py harvest`, "
               "and a profile check from the results; add only people not already in the book, "
               "with their evidence and profile status, as not_contacted, each draft written with "
               "`reading.py draft` (it waits on a read). Then re-check every not_contacted "
               "contact a search found against today's matching (`discovery.same_employer`, "
               "`discovery.profile_status`): close any it would not keep, with the reason in "
               "`outcome`. No profile is read in the background and nothing is sent",
        "files": ("tools/network/compose.py", "tools/network/advice.py", "tools/network/tone.py",
                  "tools/network/reply.py",
                  "tools/network/discovery.py", "tools/network/openalex.py", "tools/network/schema.py",
                  "tools/network/sources.py", "tools/network/why.py",
                  ".claude/skills/networking/*", ".claude/commands/network.md",
                  ".claude/commands/reply.md"),
        "versions": (
            _first(),
            (2, "2026-10-15", False, "a no read as a no and 'not hiring, but happy to "
                                    "chat' as a yes, never a second nudge, InMail with a "
                                    "subject, limits from your LinkedIn plan"),
            (3, "2026-10-15", False, "people matched by profile URL and in any script, tier 1 "
                                    "only for a dated post about your own work, nobody ruled "
                                    "out for a missing location, and your own connections used"),
            (4, "2026-10-15", False, "fixes to version 3: a lowercase clause after the "
                                    "greeting, a named city read before 'remote', a "
                                    "plain no counted, '<City>, ON' at home, and the "
                                    "messages shown with the people"),
            (5, "2026-10-15", False, "reads what the person has taught it (tools/learned.py) before drafting, flags the phrases they never want, their wording replaces the defaults, and every output is shown in the reply"),
            (6, "2026-10-15", False, "drafts against the messages that drew replies, and says "
                                    "which message drew one when a reply is logged "
                                    "(tools/what_works.py)"),
            (7, "2026-10-15", False, "a pending request is never nudged, a bare acceptance gets "
                                    "a first message, calls are not messages, names keep their "
                                    "capital, check-ins are refused, tier 1 needs a post about "
                                    "your work, and the question in a first note is optional"),
            (8, "2026-10-15", False, "a reply after 'no action unless they reply' is owed, nobody is nudged against it, a dated close is not reopened, a catch-up message is not a connection request, and plain job asks are caught"),
            (9, "2026-10-15", False, "docs corrected against the code: what the commands, skills and guides say now matches what the tools do"),
            (10, "2026-10-17", False, "a note is written from what was read about the person (their profile, posts and public work), refuses a common ground nothing read supports, and no two notes in a batch say the same thing"),
            (11, "2026-10-17", False, "reads the people a run surfaced until the batch is full, skips anyone the page shows has moved on or is based elsewhere and reads the next, and reaches the desktop app's browser from a cloud session"),
            (12, "2026-10-17", False, "screenshots from the LinkedIn app, read like a paste, so a profile is read on a phone or in a web session"),
            (13, "2026-10-17", False, "a declined or thin people search goes to connections, rosters and the People tab, never a rephrased query"),
            (14, "2026-10-17", False, "profiles are read at a person's pace with sitting and day caps, each opened once, public sources first, and rosters read every run alongside the title queries"),
            (15, "2026-10-17", False, "the request budget is 50 a week and 25 a day, reads 30 an hour and 80 a day, and research papers are an optional source"),
            (16, "2026-10-17", False, "people found through the person's own source plan, ranked by why them, each note in the shape that suits them"),
            (17, "2026-10-17", False, "shared definitions: dates, places, recruiter test, ruled-out employers, employer names without a legal suffix, an application there and a route's clear reply rate in why-them"),
            (18, "2026-10-17", False, "alumni searches give every employer left a turn, the most recent leading and the rest taking turns a day at a time, and never search the current employer"),
            (19, "2026-10-18", False, "message checks run on Python 3.9; a new contact-book column goes at the end of the header"),
            (20, "2026-10-18", False, "LinkedIn's first sign-in is a wait, reads only for people written to that day at a person's pace, finds with no LinkedIn profile and finds on old pages are marked, a short batch stops and says why, and alumni searches go in the order their alumni have replied"),
            (21, "2026-10-18", False, "people are found in bulk from any chat (connections, search results with their own titles, a profile check), plain one-title searches, and only the best ten are read or the best three pasted"),
            (22, "2026-10-18", True, "discovery runs again over every employer already in the contact book with the plain searches, which found nearly three times as many people at an employer; account-free rungs only, nothing read, nothing sent"),
            (23, "2026-10-18", True, "discovery runs again over every employer already in the "
                 "contact book with the plain searches, and the people found are cleaned before "
                 "any is added: a title that says former drops them, a post about another company "
                 "is not taken as working at the employer, a short surname is never cut as if it "
                 "were letters after the name, and someone whose job the result does not give "
                 "ranks below a known title"),
            (24, "2026-10-18", False, "the line saying why someone was found names the job a title search looked for, and nothing else: no search operators, never the person's own name"),
            (25, "2026-10-18", True, "people searches spend the budget where people are found: both title searches run first, a name check keeps only that person with the job the page gave them and is capped at three an employer, a post is dated so an old one no longer counts, and AVP, SVP and EVP read as senior"),
            (26, "2026-10-19", True, "people are matched to an employer only where their result names it as where they work, people at its ratings or analytics arm or under its brand line count, and contacts already added on a name alone are re-checked"),
            (27, "2026-10-19", True, "people are kept only when they are people at the employer: a university's or the employer's own post is not a contact, a first name that spells the employer proves nothing on a name check, the employer before a place is read, a brand line after a job or a dash is the employer, a post naming another of the employer's names counts, and a job is never read as a place; contacts already added are re-checked"),
            (28, "2026-10-19", False, "your connections export is saved from the file or from LinkedIn's whole archive, reading only Connections.csv, and one employer's 1st-degree people can be pasted while it is on its way, each drafted a message with no connection request"),
            (29, "2026-10-19", False, "business days skip your public holidays, employer names with a web address or initials join, and a state file a merge left conflict markers in is refused"),
            (30, "2026-10-19", False, "reads go where cheap checks cannot decide, requests sent outside the app are recorded, people set aside are dropped rather than closed, and a result title keeps the employer however it is written"),
            (31, "2026-10-20", False, "first messages fitted to who reads them (work authorization and the role wanted by reader type), true reasons for writing (how they were found, a parallel in their path, a confirmed mutual connection; no claim to have read what the sender did not), contractions allowed, a late employer warned not refused, warnings with a rewrite for phrases that read as generated, stacked hedges, exits, unhedged claims and credentials with no reason, an InMail of subject and body in the shape that drew a reply, a phrase bank varied per contact, a read-aloud check, revenue titles skipped unless in the person's function, a peer given the standard length, a decision-maker given the senior work-authorization wording, the app's own asks in words the person's voice check passes, a note checked for the reader it was written for, a referrer's name kept capitalized, and ordinary sentences (wanting to understand how their role changed) no longer read as asking for the job"),
            (32, "2026-10-20", False, "a people page lists each card with the person's address and best first by how close the title is to their function, cutting IT support, operations and the like; a people search can be built from a company number and is confirmed by the first page of results; a sign-in page is an expired session or friction by the hours since the last page or sign-in"),
            (33, "2026-10-20", False, "profile reads back to 3.2.5's caps (30 an hour, 80 a day), reading for the week's requests, no slow start before a signal, a lifted cap lifting the ramp and the loads cap, and the place check said once in a chat"),
            (34, "2026-10-20", False, "the voice checks from one round (a round's InMails built alike, a bare close, guessing from a level, flattery, vague comparisons, hedges by default, repeated words, a VOICE setting), and the tool fixes (rows from readings, pending invitations, no Connect button, InMail refunds, company numbers, research titles, two a company, the time where they are, a page loaded too soon kept)"),
        ),
        "fingerprint": "7bc9bc0f875ea42b",
    },
    "network-notes": {
        "by": "network", "priority": 2, "applies": "queued_notes", "time": "~10 min",
        "gives": "every first note still waiting to be sent rewritten from what was read "
                 "about the person, not from a search snippet",
        "run": "python3 tools/network/reading.py queue; for each contact it lists, /network "
               "step 5 (their public work, and their profile in the browser only if "
               "PROFILE_READS is \"browser\"), then rewrite "
               "documents/network/<contact_id>/draft.md with compose.first_note(..., reading=) "
               "and reading.same_ground() across them; update any file of theirs that lists "
               "the old notes (a send pack) to match, and show the new notes; nothing is sent",
        "files": ("tools/network/reading.py",),
        "versions": (
            _first(),
            (2, "2026-10-17", True, "each note rests on something read about the person: "
                                    "history you share, a recent post, a talk or an article, "
                                    "and no two notes say the same thing"),
            (3, "2026-10-17", False, "a person the page shows has moved on is skipped, and the ceiling on reads is far above a run"),
            (4, "2026-10-17", False, "screenshots count as a read of the person's page"),
            (5, "2026-10-17", False, "posts dated in words, current employers with no employment type, and new candidates read without a contact row"),
            (6, "2026-10-17", False, "a reading keeps the connection degree and whether a request is pending, and the browser reads are paced and capped"),
            (7, "2026-10-17", False, "the request budget is 50 a week and 25 a day, reads 30 an hour and 80 a day, and research papers are an optional source"),
            (8, "2026-10-17", False, "shared dates and employer names, so a shared employer is found without its legal suffix"),
            (9, "2026-10-17", False, "the candidate's current employer is read from the role dates"),
            (10, "2026-10-18", False, "the read keeps the headline and the top card's employer, grounds a note on them, skips anyone the person's location gate fails, and leaves old press out"),
            (11, "2026-10-18", False, "the route offers the move to the desktop app or a paste when a cloud chat has no browser, in the place check's words"),
            (12, "2026-10-18", False, "a browser read is for the day's short list only, a paste is offered for the best three, and the route says what works in this chat"),
            (13, "2026-10-19", False, "a comment's example employer is invented"),
            (14, "2026-10-19", False, "a comment names the place check's new rhythm, once and then weekly"),
            (15, "2026-10-19", False, "applied by /network itself; several profiles can be pasted at once; a note nobody has read for says so at its top"),
            (16, "2026-10-19", False, "only notes written before notes rested on a reading are redone, and a note written from someone's public work leaves the queue"),
            (17, "2026-10-19", True, "a batch of queued notes is checked for sentences they share, so notes that all end the same way are written again"),
            (18, "2026-10-20", False, "sent invitations read card by card with each note kept, only requests the page can show called gone, names matched however written, Experience kept role by role with path parallels and mutual connections, a top card place unlike the current role's a caution, the channel set from the page only where it shows a degree, the whole About kept, and the files that change on every read kept out of the repo, or in the old file where this computer's ledger cannot be written"),
            (19, "2026-10-20", False, "a sign-in page hours after the last page is an expired session, not a stop; a sign-out stop is lifted on the person's word with reading.py resume, once a day, and the stop names it"),
            (20, "2026-10-20", False, "the reading list sized to the week's requests, and its words"),
            (21, "2026-10-20", False, "notes drafted with the new voice checks; unsent drafts are not redrafted, and reading.py batch flags any built alike"),
        ),
        "fingerprint": "dd202e833fc29cf8",
    },
    "screening": {
        "by": "round", "priority": 2,
        "gives": "postings ruled out under older screening looked at again",
        "run": "every round, by itself: an exclusion dated before the latest re-run version "
               "stops blocking (tools/throttle.py ruled_out)",
        "files": ("tools/text_screen.py", "tools/prefilter.py", "tools/fit.py",
                  "tools/opportunity.py", "tools/score_posting.py", "tools/throttle.py",
                  "tools/bar.py", "tools/sector.py", ".claude/commands/rank.md",
                  "tools/exclude.py", "tools/places.py"),
        "versions": (
            _first(),
            (2, "2026-10-15", False, "a skip the throttle re-derives every run (a referral "
                                    "hold, do-not-target, the company throttle, the bar) "
                                    "and a round's queue decision never block a posting for "
                                    "good; postings on a Workday internal site are dropped"),
            (3, "2026-10-15", False, "exclusions the current rules only rank (a years bar, or a reason naming only the stage that wrote it) are screened again, while a range or degree knockout stands; '<City>, ON, CA', refused permits, private equity, residence abroad, 'asset' and 'bonus', loan sizes as pay, and short names in brackets are read right"),
            (4, "2026-10-15", False, "docs corrected against the code: what the commands, skills and guides say now matches what the tools do"),
            (5, "2026-10-17", False, "one definition of a preference, an equivalence route and the years bar; rulings that lapse when the person's rules change (tools/exclude.py); places from one list"),
            (6, "2026-10-17", False, "a ruling in the person's own words is never lifted by a better screen or a scoring rule, only by them"),
            (7, "2026-10-17", False, "a ruling lapses only when the part of the rules it rests on changes; restamp keeps the ones that still hold"),
            (8, "2026-10-18", False, "the text screen runs on Python 3.9; a pension plan's full and short names key as one employer"),
            (9, "2026-10-19", True, "a posting is cut only while today's rules would cut it: relists aged by first sight, a remote role for another country flagged or cut, a region cutting only when it leaves home out, a home city beside a country code read as home, and the pronoun us never a country"),
            (10, "2026-10-19", False, "every employer board openroles reads is a live board, copies of one posting in a round are as old as the oldest, and an internal Workday site is caught at either of Workday's addresses"),
            (11, "2026-10-19", False, "pay is read with no currency mark, by the hour, under a heading, and per place; a posting it now reads below your cut line is cut on its next round, and nothing ruled out before needs looking at again"),
            (12, "2026-10-19", False, "a hiring process with no application is read as a process, never as an application to the same role"),
            (13, "2026-10-20", False, "a round in the cloud tells the person, in plain words, the one fix when the chat's settings block the job sites"),
        ),
        "fingerprint": "cd1651c6ecb67b79",
    },
    "routines": {
        "by": "you", "priority": 3, "applies": "routines",
        "gives": "your scheduled tasks set up the current way",
        "run": "automation/README.md, for the tasks a newer version adds or changes",
        "ask": "The app's scheduled tasks have changed. Shall I set yours up the new way?",
        "files": ("automation/README.md", "tools/routines.py"),
        "versions": (
            _first(),
            (2, "2026-10-15", False, "docs corrected against the code: what the commands, skills and guides say now matches what the tools do"),
            (3, "2026-10-15", False, "The default set-up is one task, a twice-weekly brief that takes the app's updates; the scheduled round is optional. Existing tasks keep their schedules"),
            (4, "2026-10-17", False, "how to set up the brief from a session on your own computer"),
            (5, "2026-10-18", False, "finds an existing brief by the registry or its prompt, never its title, so a second is never made"),
            (6, "2026-10-18", False, "the words for making the brief from a computer come from the registry, and Claude never starts a cloud chat from its own shell"),
        ),
        "fingerprint": "e80ecf2bb60066a6",
    },
    "expand": {
        "by": "upgrade", "priority": 4, "time": "~15 min",
        "gives": "competencies hidden in your documents found the current way",
        "run": "/expand, with each new item written as [CONFIRM: ...] rather than asked",
        "files": (".claude/commands/expand.md",),
        "versions": (
            _first(),
            (2, "2026-10-15", False, "docs corrected against the code: what the commands, skills and guides say now matches what the tools do"),
        ),
        "fingerprint": "7fe28c77d24d08c2",
    },
    "upskill": {
        "by": "upgrade", "priority": 4, "applies": "upskill_plans", "time": "~10 min",
        "gives": "your upskilling plans redone the current way",
        "run": "/upskill again for each plan in upskill/",
        "files": (".claude/skills/upskill/SKILL.md",),
        "versions": (
            _first(),
            (2, "2026-10-15", False, "no em dashes in the report it writes, and an invented "
                                    "example in place of a real one"),
            (3, "2026-10-15", False, "docs corrected against the code: what the commands, skills and guides say now matches what the tools do"),
            (4, "2026-10-19", False, "no longer points at the removed Notion sync"),
        ),
        "fingerprint": "5f54c98c7e8293ba",
    },
}

# Every other app file, and why a change to it needs no version. A glob is matched
# with fnmatch, so `*` crosses folders.
KEEPS_NOTHING: dict[str, str] = {
    "tests/*": "tests change nothing a person has",
    "tools/dates.py": "reads a date; every tool that keeps something is versioned where it keeps it",
    "tools/offline_boards.py": "a test seam: canned board answers inside a test, nothing kept",
    "tools/try_personal_tests.py": "the maintainer's pre-release check; reads a copy, keeps nothing",
    "tools/holidays.py": "works out public holidays when a date is counted; writes nothing, and "
                         "a person's own dates live in their search.py PUBLIC_HOLIDAYS",
    "tools/local_path.py": "finds the tools a computer installed (bun, TeX) for the session that "
                           "runs; keeps nothing",
    "tools/local_path.sh": "the same, for the shell scripts; keeps nothing",
    "tools/profile_consistency.py": "reads the profile and names what disagrees; the person "
                                    "corrects it, through the profile-consistency upgrade",
    ".github/*": "the app's own CI and issue templates",
    "profile.example/*": "the invented example person; a new profile name in it is a profile "
                         "upgrade or a safe default, which tests/test_profile_upgrades.py holds",
    "*/.gitkeep": "an empty folder's marker",
    "CLAUDE.md": "read afresh by every session",
    "AGENTS.md": "read afresh by every session",
    "GEMINI.md": "read afresh by every session; it only points to AGENTS.md",
    "README.md": "documentation, read when needed",
    "ARCHITECTURE.md": "documentation, read when needed",
    "CONTRIBUTING.md": "documentation, read when needed",
    "MAINTAINING.md": "documentation, read when needed",
    "SECURITY.md": "documentation, read when needed",
    "SETUP.md": "documentation, read when needed",
    "START_HERE.md": "documentation, read when needed",
    "CHANGELOG.md": "documentation, read when needed",
    "CHANGELOG-upstream.md": "documentation, read when needed",
    "LICENSE": "documentation, read when needed",
    "documents/README.md": "documentation, read when needed",
    "tools/README_SALARY_TOOL.md": "documentation, read when needed",
    ".gitignore": "configuration, read on every run",
    ".ruff.toml": "configuration, read on every run",
    "requirements.txt": "installed afresh in every container",
    ".claude/settings.json": "configuration, read on every run",
    "automation/prompts/*": "each scheduled task reads its prompt from master at every run",
    ".agents/skills/linkedin-search/*": "the app's own portal, searched afresh by every round",
    ".agents/skills/freehire-search/*": "the app's own portal, searched afresh by every round",
    ".claude/skills/job-scraper/SKILL.md": "how a round searches; every round runs it afresh",
    ".claude/skills/job-application-assistant/SKILL.md": "routing: which command handles what",
    ".claude/skills/job-application-assistant/11-cost-model.md":
        "which model runs each stage; what it writes is held to the same checks",
    ".claude/agents/gemini-research-expert.md":
        "a general research helper; what it finds is kept by the method that asked",
    ".claude/workflows/repo-audit.js": "read-only",
    ".claude/commands/upgrade.md": "the machinery that carries changes; it keeps nothing itself",
    ".claude/commands/outcome.md": "records what happened, which a better method does not change",
    ".claude/commands/gmail-sync.md": "its cursor is never committed, so every container reads "
                                      "the mailbox afresh with the current method",
    ".claude/commands/html-report.md": "a report derived on request, never kept as state",
    ".claude/commands/threads.md": "a view derived from the message log on every run",
    ".claude/commands/reset.md": "removes state on request",
    "tools/sync_app.py": "the machinery that carries changes; it keeps nothing itself",
    "tools/merge_state.py": "a git merge driver; it changes only what a merge writes",
    "tools/model_guide.py": "says which model suits a piece of work; it keeps nothing",
    ".gitattributes": "configuration, read on every merge",
    "tools/profile_upgrades.py": "the machinery that carries changes; it keeps nothing itself",
    "tools/build_versions.py": "the machinery that carries changes; it keeps nothing itself",
    "tools/learned.py": "the machinery that keeps what the person said; what it keeps is theirs",
    "tools/what_works.py": "counts what already happened from the state files and keeps nothing",
    "tools/profile_names.py": "the machinery that carries changes; it keeps nothing itself",
    "tools/profile_names_baseline.txt": "the machinery that carries changes",
    "tools/personal_paths.py": "the machinery that carries changes; it keeps nothing itself",
    "tools/person.py": "reads the profile; keeps nothing",
    "tools/company_key.py": "a join computed on every run",
    "tools/open_actions.py": "a view derived from the state files on every run",
    "tools/followups.py": "a view derived from the tracker on every run",
    "tools/still_open.py": "a check run on demand; keeps nothing",
    "tools/network/state.py": "a view derived from the contact book and log on every run",
    "tools/network/pace.py": "how fast reads go and the count of pages loaded, kept per "
                             "computer outside the repo; nothing in the person's repo",
    "tools/run_round.py": "runs every round afresh; its shortlists are dated records of one round",
    "tools/scrape_wide.py": "runs every round afresh",
    "tools/hydrate.py": "runs every round afresh",
    "tools/job_alerts.py": "runs every round afresh",
    "tools/lookup_score.py": "a lookup run on demand",
    "salary_lookup.py": "a lookup run on demand",
    "tools/convert_salary_excel.py": "a lookup's data converter, run on demand",
    "tools/leak_scan.py": "development tooling",
    "tools/name_guard.py": "development tooling: checks what the app carries, keeps nothing",
    "tools/app_watch.py": "checks the public app from the maintainer's repo; keeps only a "
                          "note in .git of what it has read",
    "tools/csv_store.py": "reads and writes a state CSV in place; keeps nothing",
    "tools/release.py": "publishes the app's releases from its own CI; keeps nothing in a repo",
    "tools/name_guard_allow.txt": "the name guard's list of invented names; keeps nothing",
    "tools/build_app.py": "development tooling",
    "tools/security_guards.py": "development tooling",
    "tools/lint_skills.py": "development tooling",
    "tools/ci_local.sh": "development tooling",
    "tools/check_framework_version.py": "development tooling",
    "tools/check_upstream_updates.py": "development tooling",
    "tools/upstream_triage.py": "development tooling",
    "tools/actions_budget.py": "development tooling",
    "tools/fleet.py": "development tooling",
    "tools/score_eval.py": "development tooling",
    "tools/env_check.py": "sets up the container, which is new every session",
    "tools/python_floor.py": "the oldest Python the app runs on; it leaves nothing behind",
    "tools/claude_surfaces.py": "reads the registry of what Claude's surfaces can do; it writes "
                                "nothing in a person's repo, and its watch runs in the app only",
    "tools/claude_surfaces.json": "the registry of what Claude's surfaces can do, dated and "
                                  "sourced: the app's words, read in place, never copied",
    "tools/place.py": "says, once in a chat, whether the chat suits the person's settings; its one "
                      "record, profile/place.json, is /setup's question and the work-place upgrade's",
    "tools/setup_env.sh": "sets up the container, which is new every session",
}

_OPEN = re.compile(r"^<!-- section: ([a-z-]+) -->\s*$")
_CLOSE = re.compile(r"^<!-- /section -->\s*$")


def regions(path: str = SETUP) -> dict[str, list[str]]:
    """{section: [the text of each marked region, in order]} from setup.md."""
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    out: dict[str, list[str]] = {}
    current, buf = None, []
    for n, line in enumerate(lines, 1):
        m = _OPEN.match(line)
        if m:
            if current is not None:
                raise ValueError(f"{path}:{n}: a section opens inside {current!r}")
            current, buf = m.group(1), []
            continue
        if _CLOSE.match(line):
            if current is None:
                raise ValueError(f"{path}:{n}: a section closes that never opened")
            out.setdefault(current, []).append("\n".join(buf).strip())
            current = None
            continue
        if current is not None:
            buf.append(line)
    if current is not None:
        raise ValueError(f"{path}: section {current!r} never closes")
    return out


def _tracked() -> list[str] | None:
    """Every file git tracks here, or None without git. Only tracked files count: a
    glob over the disk also caught `__pycache__`, so the hash differed between machines."""
    try:
        r = subprocess.run(["git", "-C", ROOT, "ls-files"], text=True, capture_output=True,
                           timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.splitlines() if r.returncode == 0 else None


def files(name: str) -> list[str]:
    """The app files that say how a method is done, globs expanded, sorted."""
    out = set()
    tracked = None
    for pat in METHODS[name]["files"]:
        if any(c in pat for c in "*?["):
            if tracked is None:
                tracked = _tracked()
            if tracked is None:
                tracked = [os.path.relpath(os.path.join(d, n), ROOT).replace(os.sep, "/")
                           for d, dirs, names in os.walk(ROOT)
                           if "__pycache__" not in d and "/.git" not in d for n in names]
            out.update(f for f in tracked if fnmatch.fnmatch(f, pat) and not is_personal(f))
        else:
            out.add(pat)
    return sorted(out)


def fingerprint(name: str) -> str:
    """The hash of everything that says how this method is done."""
    h = hashlib.sha256()
    if METHODS[name].get("setup"):
        for text in regions().get(name, []):
            h.update(text.encode("utf-8") + b"\0")
    for f in files(name):
        with open(os.path.join(ROOT, f), "rb") as fh:
            h.update(f.encode("utf-8") + b"\0" + fh.read() + b"\0")
    return h.hexdigest()[:16]


def current(name: str) -> int:
    return METHODS[name]["versions"][-1][0]


def last_rerun(name: str) -> str:
    """The date of the latest version that asks for a redo, or "" if none ever has."""
    days = [v[1] for v in METHODS[name]["versions"] if v[2]]
    return days[-1] if days else ""


def _born() -> str:
    """The day the profile was created, from git, or "" when git cannot say for sure.

    A shallow clone shows its oldest commit as adding every file, which would date an
    old profile too late and skip a redo it needs, so a shallow clone answers "".
    """
    try:
        rel = os.path.relpath(person.path("person.json"), ROOT)
    except person.NoProfile:
        return ""
    if rel.startswith(".."):
        return ""
    try:
        shallow = subprocess.run(["git", "-C", ROOT, "rev-parse", "--is-shallow-repository"],
                                 text=True, capture_output=True, timeout=20).stdout.strip()
        if shallow != "false":
            return ""
        out = subprocess.run(["git", "-C", ROOT, "log", "--diff-filter=A", "--format=%ad",
                              "--date=short", "--", rel],
                             text=True, capture_output=True, timeout=20).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return ""
    return out[-1] if out else ""


def recorded() -> dict[str, int]:
    """{method: the version that made what this repo has}.

    Absent from the record, a part of /setup is at the latest version released before
    the profile was created (strictly before, so a same-day profile redoes it), and
    everything else is at version 1.
    """
    try:
        path = person.path(RECORD)
    except person.NoProfile:
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (OSError, ValueError):
        data = {}
    out = {}
    for name, entry in data.items():
        try:
            out[name] = int(entry["version"] if isinstance(entry, dict) else entry)
        except (KeyError, TypeError, ValueError):
            continue
    born = None
    for name, m in METHODS.items():
        if name in out or not m.get("setup"):
            continue
        born = _born() if born is None else born
        if born:
            out[name] = max([v[0] for v in m["versions"] if v[1] < born] or [1])
    return out


def behind(name: str, have: dict[str, int] | None = None) -> list[tuple]:
    """The versions after this repo's that ask for what an earlier one made to be redone."""
    have = recorded() if have is None else have
    mine = have.get(name, 1)
    return [v for v in METHODS[name]["versions"] if v[0] > mine and v[2]]


# ------------------------------------------------------------------ applies

def _tracker_statuses() -> set[str]:
    path = person.state("job_search_tracker.csv")
    import csv_store
    csv_store.refuse_conflicts(path)
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return {(r.get("status") or "").strip().lower() for r in csv.DictReader(fh)}
    except OSError:
        return set()


def _has_rows(path: str) -> bool:
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return any(True for _ in csv.DictReader(fh))
    except OSError:
        return False


def _older_notes() -> bool:
    """A first note still waiting that was written the older way (network/reading.py
    written_the_older_way). Any draft at all used to count, so the notes the networking
    upgrade writes, each opening on WAITS ON A READ, read as made the older way the
    moment they were written, and every /network run began by rewriting them."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "network"))
    import reading
    return any(reading.written_the_older_way(os.path.basename(os.path.dirname(f)))
               for f in glob.glob(person.state("documents", "network", "*", "draft.md")))


APPLIES = {
    "prep_docs": lambda: bool(glob.glob(person.state("documents", "network", "*", "prep.md"))),
    "queued_notes": lambda: _older_notes(),
    "unsent_drafts": lambda: "drafted" in _tracker_statuses(),
    "live_interviews": lambda: "interview" in _tracker_statuses(),
    "live_applications": lambda: bool({"drafted", "interview"} & _tracker_statuses()),
    "contacts": lambda: _has_rows(person.state("network_contacts.csv")),
    "routines": lambda: person.exists("routines.json"),
    "upskill_plans": lambda: bool(glob.glob(person.state("upskill", "*.md"))),
}


def applies(name: str) -> bool:
    """Whether this repo holds anything the method made. Nothing to redo otherwise."""
    key = METHODS[name].get("applies")
    return True if key is None else bool(APPLIES[key]())


# ------------------------------------------------------------------ record

def record(names: list[str], today: str | None = None) -> dict:
    """Write the app's current version for each named method into the profile."""
    path = person.path(RECORD)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (OSError, ValueError):
        data = {}
    day = today or dt.date.today().isoformat()
    for name in names:
        if name not in METHODS:
            raise SystemExit(f"build_versions: no method {name!r}; known: {', '.join(METHODS)}")
        data[name] = {"version": current(name), "date": day}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(data.items())), fh, indent=2)
        fh.write("\n")
    return data


def redo(name: str) -> int:
    """An instant method: run its command from the repo root, then record it."""
    cmd = METHODS[name].get("command")
    if not cmd:
        raise SystemExit(f"build_versions: {name} is not instant; /upgrade redoes it")
    argv = [sys.executable if cmd[0] == "python3" else cmd[0], *cmd[1:]]
    rc = subprocess.run(argv, cwd=ROOT).returncode
    if rc == 0:
        record([name])
    return rc


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["fingerprints"]:
        for name in METHODS:
            print(f"  {name:11} {fingerprint(name)}")
        return 0
    if argv[:1] == ["redo"] and len(argv) == 2:
        return redo(argv[1])
    if argv[:1] == ["behind"] and len(argv) == 2:
        late = behind(argv[1]) if applies(argv[1]) else []
        for v in late:
            print(f"now {v[3]}")
        return 1 if late else 0
    if argv[:1] == ["record"]:
        rest = argv[1:]
        names = ([n for n, m in METHODS.items() if m.get("setup")] if rest == ["--setup"]
                 else rest)
        if not names:
            raise SystemExit("build_versions: record which method? (or --setup)")
        record(names)
        print("recorded: " + ", ".join(f"{n} v{current(n)}" for n in names))
        return 0
    have = recorded()
    for name in METHODS:
        late = behind(name, have)
        state = (f"behind: {late[-1][3]}" if late and applies(name)
                 else "nothing here to redo" if late else "current")
        print(f"  {name:11} here v{have.get(name, 1)}, app v{current(name)}  {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
