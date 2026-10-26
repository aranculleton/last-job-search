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
import local_path  # noqa: E402
from personal_paths import is_personal  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP = ".claude/commands/setup.md"
# How each part of /setup is done, section by section: setup.md is the order and the
# questions, and holds no section of its own since it was cut to a flow Claude keeps after
# compaction (2026-10-25). Both are read, in this order, for every setup method's text.
SECTIONS = ".claude/skills/job-application-assistant/setup-sections.md"
SETUP_FILES = (SETUP, SECTIONS)
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
            (15, "2026-10-21", False, "/add-portal says a board robots.txt disallows is built only on the person's yes while they are present, never by a background upgrade"),
            (16, "2026-10-21", False, "Employer boards are read while the portals are searched, share one body cap and one portal runner, and honour a round's own seen file"),
            (17, "2026-10-21", False, "robots_check splits reading a policy from deciding; same verdicts"),
            (18, "2026-10-21", False, "The employer-board reader is openroles 0.3.0: one posting's odd field or pay never stops a board being read, a posting with no readable id or title is left out, dates are real dates or empty, hostile pages are read in linear time, and every Workday posting keeps its id; nothing about your boards needs redoing"),
            (19, "2026-10-22", False, "the probe reads the boards side by side, the same verdicts in the same order"),
            (20, "2026-10-22", False, "add-portal works out the board, its name, market and test query instead of asking"),
            (21, "2026-10-22", False, "the boards section no longer asks about job-alert emails"),
            (22, "2026-10-25", False, "portals run under Node or Bun, whichever the computer has; with neither a round stops with one plain line and never reads as a thin market; command output is read as UTF-8 on every computer; setup's board research runs in the background, every target employer's hiring system looked up at once, and the lookup works before the profile is finished; hidden text on employer boards is removed; board research starts from the market tables, and a board from them is built only through /add-portal; /add-portal names /setup for the rule that nobody is asked to name a board (the short CLAUDE.md of 4.0); employer boards are read by openroles 0.4.0: hidden text left out by its own rule, Lever, Ashby and Gem read from their HTML, inline tags join the words around them, and a robots.txt with many wildcards is matched at once"),
        ),
        "fingerprint": "30dd4f711127d1ce",
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
            (9, "2026-10-22", False, "the setup question on reading profiles says reads go one page at a time and stop at LinkedIn's first sign"),
            (10, "2026-10-25", False, "setup's search section moved to setup-sections.md with the same rules; what the person was not asked is written from a default, never a question; a field's titles and interchangeable tools come from the market tables first"),
        ),
        "fingerprint": "5159c542e7ce331a",
    },
    "market": {
        "setup": True, "by": "upgrade", "priority": 3, "time": "~15 min",
        "gives": "eligibility, pay and places checked the way your market words them",
        "run": "/setup --section market",
        "files": (".claude/skills/job-application-assistant/04-job-evaluation.md",
                  "tools/markets.py", "tools/markets/*"),
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
            (6, "2026-10-21", False, "Wording"),
            (7, "2026-10-25", False, "setup's market section moved to setup-sections.md; pay, eligibility wording and place names are researched in the background while the person answers; setup reads the market tables the app ships first (boards with their robots.txt verdicts, eligibility wording, document conventions, pay sources and place names for 20 countries, 18 fields, four career levels, regional and remote boards, each fact cited and checked by code) and researches only what they lack; a profile already made is not redone; the tool families quote only the tools' own names, never a vendor's"),
        ),
        "fingerprint": "b8e92bc46b539082",
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
            (4, "2026-10-25", False, "setup's documents section moved to setup-sections.md; the local conventions are researched in the background; a new person's page design is chosen per kind of employer (classic or modern), never asked; the conventions come from the market tables first"),
        ),
        "fingerprint": "d4be7bd7b396ebc9",
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
            (5, "2026-10-22", False, "the instructions say an export is taken first and the merge runs alone; wording only"),
            (6, "2026-10-25", False, "setup's voice section moved to setup-sections.md; tone defaults to plain and confident, corrected by the person's reactions; where the people they should meet are named is researched in the background"),
        ),
        "fingerprint": "c4f27b2335e3d4b9",
    },
    "history": {
        "setup": True, "by": "upgrade", "priority": 3, "time": "~15 min",
        "gives": "your roles, bullets and stories in a form every tool reads",
        "run": "/setup --section history",
        "files": (".claude/skills/job-application-assistant/07-interview-prep.md",
                  "tools/history_interview.py"),
        "versions": (
            _first(),
            (2, "2026-10-15", True, "role headings the tools can read, bullet themes cued in your "
                                    "field's words, and STAR examples kept in your profile"),
            (3, "2026-10-15", False, "asks whether you pay for LinkedIn Premium"),
            (4, "2026-10-19", False, "every STAR story ends on a Use for line naming the questions it answers"),
            (5, "2026-10-19", False, "the interview template's permit answer follows your own disclosure rule, and a stock answer can name the kinds of employer it is not for"),
            (6, "2026-10-20", False, "the interview guide lets an answer be drafted when the person asks, marked for them to confirm, and points its examples at their own stories"),
            (7, "2026-10-25", False, "setup reads the resume they attach or paste (never a folder to drop it in), takes the rest from it or a default marked to confirm, and asks four questions in one message; no resume is fine: say \"build one with me\" and a short guided interview, one job per message and phone-sized, builds the history, seeded from their LinkedIn where it can be, never inventing a result; on the app page, setup asks its questions one at a time and resumes a setup left part-way"),
        ),
        "fingerprint": "ab8d5582cd337899",
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
            (13, "2026-10-20", True, "a researched fragment inside a question is cut where a clause ends; a fact about what a team does is followed by a question about its work, never about how it is set up; an answer drafted on request is marked as a draft; call preps answer from the interview pack's own answers (stock answers, why you are looking, work authorization), read the team research the pack reads, use the same posting, and send a booked screen with no application to /interview, so call preps already written are rebuilt, keeping what the person wrote"),
            (14, "2026-10-21", False, "a release rewrites only a live conversation's prep, and never one whose only change is its date and stamp; an answer written as a quote is read as the answer, and a placeholder fails the check"),
            (15, "2026-10-21", False, "A call prep is written before the employer is researched, saying so at the top, and a prepared answer that states where the person lives or moved from is flagged when that employer was told another place"),
            (16, "2026-10-21", True, "Nothing personal read about a contact (age, family, health, religion, politics, sexuality) is shown, and the answer check flags an answer far over its time or saying we where they asked what you did"),
            (17, "2026-10-21", False, "bridges.py gains the learn-or-show nudge; preps unchanged"),
            (18, "2026-10-21", False, "bridges.py gains COVERED_BY; no document text changes"),
            (19, "2026-10-21", True, "What is personal about a contact is read as their own life (IVF, an illness, a vote, a death), never a field of work (pensions, mental health services, cancer research), so a call prep shows their work and leaves their life out; recording what an employer heard or changing a stock answer rebuilds a live prep; and the daily run's dry run counts only what a real run writes"),
            (20, "2026-10-22", False, "the prep document is sent with the part to read, not pasted whole"),
            (21, "2026-10-22", False, "ends with a short first-time note or an occasional tip, not a line every session"),
            (22, "2026-10-22", False, "a prep document is sent as a copy named for whose it is; an older pack for the round the document covers is folded in, not counted as a round already told"),
            (23, "2026-10-25", True, "the research a prep cites is named by its real file; a copy sent is named apart from every other (requisition numbers and levels kept, the label never cut), carries no tool comments, and is remade when a hand edit passes the check; a path printed across two Windows drives no longer stops it; a prep finds its application from one index of the tracker, so a brief rebuilding every prep is twice as fast; tool families of one name merge into one; a prep goes on the person's page first, and in the chat only where there is no page; an application's folder is found by the paths module, not the outreach one"),
        ),
        "fingerprint": "d8de77d2f374a467",
    },
    "drafts": {
        "by": "upgrade", "priority": 2, "applies": "unsent_drafts", "time": "~5 min",
        "gives": "applications not yet sent re-rendered and re-checked by the current build",
        "run": "for each tracker row still at `drafted`, python3 tools/fit_to_page.py "
               "documents/applications/<slug>/draft.json, then tools/verify_batch.sh on them; "
               "never one already sent",
        "files": ("templates/*.py", "templates/README.md", "tools/render_application.py",
                  "tools/fit_to_page.py",
                  "tools/posting_profile.py", "tools/draft_pack.py", "tools/draft_audit.py",
                  "tools/draft_cost.py",
                  "tools/skills_block.py", "tools/allocate.py", "tools/bullet_library.py",
                  "tools/docpaths.py", "tools/doc_name.py", "tools/outreach.py",
                  "tools/screening_answers.py", "tools/record_drafts.py", "tools/stage_picks.py",
                  "tools/check_claims.py", "tools/check_numbers.py", "tools/voice_check.py",
                  "tools/locale_rules.py",
                  "tools/audit_letters.py", "tools/verify_pdf.py", "tools/verify_batch.sh",
                  "tools/verify_batch.py", "tools/pdftext.py", "tools/general_resume.py",
                  "tools/design_check.py", "tools/apply_link.py",
                  "tools/untrusted.py", "tools/bridges.py",
                  ".claude/commands/apply.md", ".claude/commands/add-template.md",
                  ".claude/skills/job-application-assistant/03-writing-style.md",
                  ".claude/skills/job-application-assistant/05-cv-templates.md",
                  ".claude/skills/job-application-assistant/06-cover-letter-templates.md",
                  ".claude/skills/job-application-assistant/08-application-forms.md",
                  ".claude/skills/job-application-assistant/verification-checklist.md",
                  ".claude/workflows/draft-applications.js", ".claude/agents/grounding-auditor.md",
                  "RUNBOOK.md", "texmf/*", "cv/main_example.tex", "cover_letters/cover.cls",
                  "cover_letters/cover_example.tex", "cover_letters/OpenFonts/*", "tools/tex_escape.py"),
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
            (25, "2026-10-20", False, "an answer that opens on a short framing line is in the first person when it says I by its third sentence; an application's outreach note is checked by the same gate as every networking message"),
            (26, "2026-10-21", False, "RUNBOOK names bar.py judge and unjudged"),
            (27, "2026-10-21", False, "One definition of a grounded claim (the profile's grounding sources, 01 winning a disagreement), en dashes banned in the guides as in the checks, and RUNBOOK holds the local merge steps, the follow-up schedule and the draft re-render command"),
            (28, "2026-10-21", False, "New checks: the resume's text layer holds every line of its draft in order, a letter copying six or more words of the posting is flagged, a character the font cannot print or a font left out stops the render, counts must count the same thing, and a keyword report"),
            (29, "2026-10-21", False, "The outreach note check skips the greeting rule its stand-in name would trip"),
            (30, "2026-10-21", False, "stage points out a file name in capitals when it is picked; dead code removed"),
            (31, "2026-10-21", False, "RUNBOOK names export.py and own_profile.py"),
            (32, "2026-10-21", False, "Staging prints what each posting is and holds a fixed-term contract, pay for another place, an application already in or a second role at one employer until the person answers; a listed skill the posting names in a phrase is kept; no question about a skill the profile covers under another name"),
            (33, "2026-10-21", False, "Each posting is drafted in one call from a compiled pack and checked by code first; the model auditor reads one packet only for a draft code flags; the outreach body is optional; a batch's cost is kept"),
            (34, "2026-10-21", False, "A resume drafted for a contact who asked carries them into the tracker row and its folder (stage_picks.py --for-contact); no unsent draft renders differently"),
            (35, "2026-10-21", False, "Staging reads a past ruling on a title only while that posting is relisted, as the round does"),
            (36, "2026-10-21", True, "Every draft that will be sent gets the code audit and the model audit; numbers written as words are checked like digits, posting figures never lend themselves to the candidate's work, every research fact a letter cites is checked against its fetched page, a trimmed letter keeps its closing sentence, and a symbol the letter's font lacks is caught. Unsent drafts are re-rendered and re-checked"),
            (37, "2026-10-21", True, "Staging reads long-term, project-duration, day-rate, IR35 and interim-reporting wording as permanent and pay for your own area as yours; a draft counts as a pick's only for that exact role; file names skip requisition codes and gender markers; the audit reads concessions only about the candidate, skips call lengths, time words and dates, checks decades and factors, folds accents in names, and survives half an emoji; a contact's apply-and-name-me route is said one way in the tracker note and outreach.md. Unsent drafts are re-checked"),
            (38, "2026-10-22", False, "A notice period or start date the profile does not hold is flagged with where to write it (01-candidate-profile.md), and is clean once written there."),
            (39, "2026-10-22", False, "a notice period hint only for notice wording, beside the audit's own advice"),
            (40, "2026-10-22", False, "shorter instructions: one stop before drafting, no hand reruns of checks verify_batch and the code audit run, a one-line checklist report"),
            (41, "2026-10-22", False, "the instructions no longer name the job-alert email reader"),
            (42, "2026-10-22", False, "ends with a short first-time note or an occasional tip, not a line every session"),
            (43, "2026-10-22", False, "the writing guide says work authorization goes to a recruiter by default, and to a decision-maker once the person's approved messages say it"),
            (44, "2026-10-22", False, "the runbook names what the networking state shows: requests sent and InMail credits left"),
            (45, "2026-10-22", False, "A first note to an employer called Visa, or to a reader whose first name is an approved example's surname, is no longer refused for it; checks only, nothing to redo"),
            (46, "2026-10-22", False, "landing steps run each command alone, the merge never chained; wording only"),
            (47, "2026-10-22", False, "an audit ruling matches its flag quoted whole or cut, the packet holds the draft object it returns, a verdict keeps what it leaves out, a lead's edit to the corrected draft is kept and checked again"),
            (48, "2026-10-23", False, "applications are delivered one way: per role one file-sending call with resume and letter, captioned role, employer, pay, location and apply link, then one index table; paths as plain text, never markdown links. An audit ruling no longer settles a longer sentence edited after it, an edit to the outreach note is kept in the note, and a newer model correction is never overwritten by an older edit"),
            (49, "2026-10-24", False, "the posting profile reads a degree's other way in past a semicolon, as the score does; the run book saves with tools/save_state.py and tells nobody but the maintainer of a problem with the app; verify_batch reads whole bullets for repeats and its skills check runs under a Mac's sed; every resume's text is black (name, headings, rule, contact line, links, bullet marks), with nothing else moved; drafts made before keep theirs until re-rendered; voice_check counts the person's own wording in a message (their opener and close, a message they approved) as theirs, never a finding, and a letter is held to the house style as before; save_state.py stages a file of the person's that was taken away as removed; on moderncv 2.4 and later (a Mac's TeX) the name is drawn 9.5pt higher, its box unchanged, so a text extractor reads it apart from the city and nothing else moves"),
            (50, "2026-10-24", False, "a resume and its letter can take a colour per kind of employer (person.json documents.styles, templates/doc_style.py), or one a draft names; black when nothing chooses one, so every draft renders exactly as before; a colour moves no word, and the claims check reads no font key as a word"),
            (51, "2026-10-25", True, "PDFs are read with pypdf, Poppler only where present; verify_batch runs in Python with the same checks and exit codes; a LaTeX compile stops after 300 s and says so; compiles run where the files were written; an employer's accented letters stay in file names (existing names kept); every file is read and written as UTF-8; a general resume, for their main target role with no posting, is staged with `stage_picks.py general`, fitted, checked (no letter) and kept as their current resume, in their default colour or black; a design per kind of employer, employer, person or draft sets the fonts, sizes, margins, page and alignment (person.json documents.design and designs, templates/doc_design.py), the template exactly when none is chosen, and verify_batch checks each PDF against the rules an ATS needs (tools/design_check.py); a path printed across two Windows drives no longer stops a step; a pick's apply link is cleaned of tracking and checked against the employer's own listing; a redraft keeps the row's date; the run book names the update setting; the grounding auditor starts without the app's CLAUDE.md, which it never needed, and each audit costs about 13,000 fewer tokens; every design is checked with the app's own Python, which reads PDFs; staging quotes no posting above the fence, dates relists as the round does, and never calls a sibling board's posting closed; works in folders with brackets in their names; the drafting pack is written with plain line ends; pages are counted with pdftotext alone; the general resume's fallback runs under Git Bash; every value reaching a .tex is escaped for where it lands; a LaTeX error is never a clean fit; neither audit can be skipped; two-page resumes and letter paper pass the design check; every contact line is checked; non-Latin employer names get their own file name; posting words are fenced; one summary budget and one requisition rule. Unsent drafts are made again; a font reached through a folder with a space goes beside the document; an application's folder is found with one read of the tracker; a document can be tweaked on demand: look, size, spacing, colour, a bullet swapped for another true one, who the letter is to, and wording redrafted through both audits; tool families of one name merge into one, so a tool both name is assessed once; the session rules the long CLAUDE.md carried (the start, the command map, saving and landing on master, delivering in a chat, what goes where, learning the person) now live in RUNBOOK.md, and an application goes on the person's page first; an application's folder and its name live in docpaths, still offered by outreach under the same names; new optional document settings (fill, letter words, skills count, style) and a verify record each page reads; where setup stands is said by app.py start alone, and one chat answers the page while every other leaves it alone; the run book says every state file the app writes merges between two chats; a PDF's pages are counted from pdftotext when pdfinfo gives no count"),
            (52, "2026-10-26", False, "templates/app/palettes.py, which this method's templates/*.py takes in, moved the page to the rosé pine colours; a page action that changed the tracker reads it again at once (docpaths.forget_abbreviations); the em dash check cites the writing guide's rule 1; no document changes"),
        ),
        "fingerprint": "935ec28ac9b29ecc",
    },
    "interview": {
        "by": "upgrade", "priority": 2, "applies": "live_interviews", "time": "~15 min",
        "gives": "the prep pack for each interview still running rewritten the current way",
        "run": "for each tracker row at `interview`, /interview <company> again, its pack "
               "written beside the old one. A pack the person wrote by hand is refused and "
               "left as it is (exit 1, said in a plain line): that pack is done, so record "
               "the version once the others are rebuilt",
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
            (11, "2026-10-20", True, "Likely questions is notes, never words to say, and never repeats an answer already written; a stock answer marked Not for this kind of employer, or holding a fill-in, is left out with the reason; notes beside an answer are kept and never checked; a rebuild keeps the person's own layout and never adds the Checking line twice; a screen asks its standard questions first; hooks are whole sentences; and an answer drafted on request carries a Draft line that check lists until the person confirms it"),
            (12, "2026-10-21", False, "a question about what you would do differently is no longer matched to the stock answer for why now; an employer your own catalogue calls professional services is a consulting firm; a fact still to confirm is never printed as where you live; advice and guesses in outcome.md are never what you were told; a rebuild keeps the round's fuller name and the stories the last build used"),
            (13, "2026-10-21", False, "a pack says the place each employer heard when it was told another (tools/told.py), with no move or settling-in for it; an answer written as a quote is read as the answer; a placeholder is never fit to say; a question answered under any heading is checked"),
            (14, "2026-10-21", False, "A prepared answer that states where the person lives or moved from is flagged in the pack and by its check when that employer was told another place"),
            (15, "2026-10-21", False, "Packs choose stories across the whole plan, say they are for before and after an interview and never during one, list where the resume invites a push, quote-check mock feedback, flag over-long and all-we answers, and drop anything personal read about a person"),
            (16, "2026-10-21", False, "process_channel is read by the drafting step too; no pack changes"),
            (17, "2026-10-21", False, "The pack says which resume each contact at the employer was sent, from the message log"),
            (18, "2026-10-21", True, "A rebuild changes only what the tool wrote: every line and section you wrote stays where you put it, a rebuild that would lose one writes nothing, and a document written by hand is never rebuilt over; a later round is prepared with stories that employer has not heard; and the place each employer heard is checked only where an answer says where you live, under any heading and where they will push"),
            (19, "2026-10-22", False, "the pack is built before the stage is asked, and sent once per turn that changed it"),
            (20, "2026-10-22", False, "ends with a short first-time note or an occasional tip, not a line every session"),
            (21, "2026-10-22", False, "the document is sent as a copy named for the employer and role; an older pack for the round it covers, under any name, is folded in rather than listed as an earlier round"),
            (22, "2026-10-25", True, "the pack's one screen stops asking for a reason they already wrote; a stage booked with the pack is written into outcome.md; the questions asked are recorded under the right role; a path printed across two Windows drives no longer stops it; works in folders with brackets in their names; the pack goes on the person's page first, and in the chat only where there is no page; an application's folder is found by the paths module, not the outreach one; rebooking a stage keeps the blank line after it, so the next heading no longer runs into it"),
            (23, "2026-10-26", False, "a stage booked with a time keeps it on its outcome.md line (scheduled <day> HH:MM), and booked again for the same day with no time it stays; the page reads the pack's one screen, its practice questions with the person's own answers and its format (one_screen, practice, format_of); an answer kept to work on is written once and can be taken off again; a process registered from the page keeps its call's time; next_stage is public; packs already made stay as they are"),
        ),
        "fingerprint": "d0bce9e5a955d68f",
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
            (5, "2026-10-21", False, "Research fetches through company_research.py fetch: robots.txt first, crawl delay kept, a feed or sitemap behind a bot check, a note per host, 12 requests an employer a day, fresh facts never fetched again, quotes checked, saves that append"),
            (6, "2026-10-21", False, "Employer research follows robots.txt redirects, keeps the crawl delay from the first request, shares one daily budget across runs, refuses a quote under six words, and marks a search summary as not read"),
            (7, "2026-10-21", False, "A page file name survives a URL holding half an emoji; every other page keeps its name"),
            (8, "2026-10-22", False, "a fresh cached fact no kept page can check has its page fetched again instead of being refused for 30 days"),
            (9, "2026-10-25", False, "research file names work for any script and on Windows (no reserved names, a short hash where a name has no Latin letters); a path printed across two Windows drives no longer stops it; the researcher starts without the app's CLAUDE.md, which it never needed; works in folders with brackets in their names"),
        ),
        "fingerprint": "2709e97e10d4266b",
    },
    "networking": {
        "by": "upgrade", "priority": 3, "applies": "contacts", "time": "~15 min",
        "gives": "the people worth contacting at your target employers found the current way",
        "run": "for each employer already in network_contacts.csv, rungs 1 to 3 of /network's "
               "ladder only: their connections there (`sources.py connections`), the two plain "
               "title searches from `discovery.queries_for()` run through `sources.py harvest`, "
               "and a profile check from the results; add only people not already in the book, "
               "with their evidence and profile status, as not_contacted, each draft written with "
               "`reading.py draft <id> <file> --wait-for-read` (it waits on a read, and nothing unread can be sent). Then re-check every not_contacted "
               "contact a search found against today's matching (`discovery.same_employer`, "
               "`discovery.profile_status`): close any it would not keep, with the reason in "
               "`outcome`. No profile is read in the background and nothing is sent",
        "files": ("tools/network/compose.py", "tools/network/advice.py", "tools/network/tone.py",
                  "tools/network/reply.py",
                  "tools/network/discovery.py", "tools/network/openalex.py", "tools/network/schema.py",
                  "tools/network/sources.py", "tools/network/why.py", "tools/network/export.py",
                  "tools/network/surface.py",
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
            (34, "2026-10-20", False, "the voice checks from one round (a round's InMails built alike, a bare close, guessing from a level, flattery, vague comparisons, hedges by default, repeated words, a VOICE setting), and the tool fixes (rows from readings, pending invitations, no Connect button, InMail refunds, company numbers, research titles, two a company, the time where they are, a page loaded too soon kept); and the reading limits: a read stops counting once its note is sent, the person's own caps outrank every preset cap of their period, one budget line before a round; and one check for every composer, agreeing with what the composers write (no warning on a sentence about the sender, on the topic word said again, or on a question; a note to someone connected checked at its own length; an outreach note checked as a message)"),
            (35, "2026-10-21", False, "compose.advise(company=) warns of a draft naming the person's own city to an employer told another; state.py set changes a contact's status, next action, date or notes by command"),
            (36, "2026-10-21", False, "/network judges an employer the bar does not know yet instead of reading its none as a fail"),
            (37, "2026-10-21", False, "The networking skill says both title searches go first, as sources.py does, and that its tiers are not the scraper's"),
            (38, "2026-10-21", False, "An automatic reply is not a reply, one person in two rows is raised, a note must greet the person it is for, invisible characters hide nothing from the checks, and what has worked is judged by Fisher's exact test at 20 a group"),
            (39, "2026-10-21", False, "Dead code removed"),
            (40, "2026-10-21", False, "The LinkedIn export's messages and invitations come into the message log, pending invitations are listed for withdrawal, and the person's own profile is looked over when due"),
            (41, "2026-10-21", False, "Reading estimates, card-only recruiter drafts, labelled pastes and the Experience heading decide a render, follow-ups logged by command, a dm kind, headline idioms, CONNECTIONS_PER_WEEK, title searches across employers, notes with nothing read refused, batch frames flagged, approved examples shown, recruiter and gatekeeping asks refused, quieter warnings, friction said as what happened, the company limit at draft, location a note"),
            (42, "2026-10-21", False, "Reply guidance names which resume goes and how to log it; a bare 'I'll pass' is a no and 'I'll pass it on' a referral"),
            (43, "2026-10-21", False, "why.py reads the highest numbered saved round as the newest"),
            (44, "2026-10-21", False, "Logging and checking fixes: a nudge after answering their reply is the one nudge, unsend and resent act on the latest message, the export adds a wordless message once, a reply to someone who wrote first is a reply, approved examples lend their shape and none of their facts, a greeting that starts their given name is theirs, sources.py answers --help"),
            (45, "2026-10-21", False, "A decline is a decline: passing on the opportunity or the call, a polite 'not sure I can help', and a no that points on is a referral, not a no; the export knows the app's own resume names and logs a resume once; a greeting another contact answers to is refused; a warm intro naming its referrer saves, with an override kept with its reason"),
            (46, "2026-10-22", False, "the networking skill and /network say fast is the default pace and a slow load only doubles the next pause"),
            (47, "2026-10-22", False, "a shorter reply per person, one version of each note, queued drafts in the same reply, no separate batch check before saving"),
            (48, "2026-10-22", False, "ends with a short first-time note or an occasional tip, not a line every session"),
            (49, "2026-10-22", False, "work authorization to a recruiter by default and to a decision-maker once approved messages say it; notes nobody would say aloud flagged; a never-say phrase written as a sentence opens bans only that sentence"),
            (50, "2026-10-22", False, "advise() warns of telling them what they do, a googled detail, underselling, a vague close, swap notes, it looks like (out of the hedge bank), Since you, a recruiter's own path, a thread between us, pretty much, sometime, the X side and hoping to; a batch logged as sent reads the sent list first; an Open Profile channel apart from InMail credits; a paragraph labelled by its subject"),
            (51, "2026-10-22", False, "no best hour to send and nothing held for one; a reader in another time zone gets it in their working day"),
            (52, "2026-10-22", False, "no reading limit and no connection cap of the app's own; reads stop only on LinkedIn's own signals; an employer written without spaces is that employer"),
            (53, "2026-10-22", False, "An employer's own name is never read as work authorization, and the reader's own name never as borrowed from an example; checks only, nothing to redo"),
            (54, "2026-10-22", False, "first notes vary their sentence order by contact (order= to choose); no close is held to ASK word for word"),
            (55, "2026-10-22", False, "a LinkedIn download is taken whole (saved and its history imported) by export.py take and the connections import, kept in the main folder; files says when the history was never saved; the linkedin-history upgrade brings it to a repo that kept only connections; a repeat imported the same day keeps the time it was sent, and a name with no surname gets an id"),
            (56, "2026-10-23", False, "one check before anyone is shown (surface.py): the book by id, address or name at either employer, the whole thread on every channel, the bar, a hold; follow-ups by the person's own FOLLOW_UP_DAYS and MAX_UNANSWERED with the date on each contact; a fortnightly LinkedIn download and what changed since the last; the due list and the import read the log once"),
            (57, "2026-10-24", False, "a second message to someone on a day one already went is refused unless --also; no-reply for a message that needs no answer; attach names the file on the newest message; the app's own follow-up line comes off anyone who has written since"),
            (58, "2026-10-24", False, "a headline that writes the employer short (\"at <Name>\" for \"<Name> Asset Management\") and a card count (\"500+\" on its own line) no longer read as having moved on; the number of people at one employer is the person's (PEOPLE_PER_EMPLOYER, more-at); an InMail is drafted only once their message window says free or credits allow"),
            (59, "2026-10-24", False, "a bare 'happy to connect' is no longer a referral offer; a chat offered is its own reading (settle a time); a phrase from a message the person approved is their own wording in every message; the first-round tip is not shown to someone whose log shows notes already sent; a chat declined ('not available to chat') is still a no, a talk with somebody else is not a chat offered; the same-day refusal counts messages only, never a call, an acceptance or a request; 'National Bank' for 'National Bank of <place>' is the same employer; the later word for one employer stands"),
            (60, "2026-10-25", False, "their reply is logged by command (state.py received); a referral asked for in a first note is refused; a reading checks first whether LinkedIn is signed in and, signed out, asks them once to sign in, with nothing else said about it; profiles are read in the browser unless the person said paste or off; contact ids are names every computer accepts; the LinkedIn download has a status (request, waiting, take, fresh) and is found in Windows and OneDrive folders; the tracker is read whatever a spreadsheet saved it as; their own LinkedIn download's positions, education and skills can seed a resume; a nudge is drafted by code first (tools/followup_drafts.py), and a hand-written one is checked in one call; messages from a LinkedIn download are dated on the person's own clock; a referral ask goes only to someone who has replied; the close ends with a full stop; an export saved with Windows line ends reads the same; job rows and drafts carry the near matches a posting asks for; the outreach rules the long CLAUDE.md repeated live in the skill's \"The rules every outreach keeps\"; a message's type, subject, body, count and warnings for the page, one plan reader and one greeting helper, and a sent message logged once"),
            (61, "2026-10-26", False, "two printed lines name the command that closes a contact (state.py set --status closed); the message log's direction is public (state.direction); nothing to redo"),
        ),
        "fingerprint": "883f09aaef2cb9b9",
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
        "files": ("tools/network/reading.py", "tools/network/parts.py"),
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
            (22, "2026-10-21", False, "A saved note that greets someone other than its contact is refused"),
            (23, "2026-10-21", False, "Dead code removed"),
            (24, "2026-10-21", True, "Queued first notes are re-checked: one with nothing read, a blunt recruiter ask, a gatekeeping question or one template frame across a batch is refused"),
            (25, "2026-10-21", False, "Drafts are read without the notes below their line of dashes, someone who replied is not counted as waiting, a nearly empty page counts as a page loaded, and a waiting note that carries an approved example's names is listed for a rewrite"),
            (26, "2026-10-21", False, "Saving and the queue judge a note against its referrer and the people it could really be for"),
            (27, "2026-10-22", False, "fast pauses by default and the same counts at every preset; a slow load never stops a day or starts the ramp; the break an upgrade wrote is freed"),
            (28, "2026-10-22", False, "search-url takes the employer first and a company number already read; the footer is never About; a third-degree page with no Experience is read as it is; grouped roles read as one employer; --remove repeats; card-enough recruiters leave the read list; the extractor's output reaches read as it came; a batch opening on the person's own line and a note that does not read aloud are not saved"),
            (29, "2026-10-22", False, "drafts and the queue check are held to the plan's length; a short request for a chat or call is always an allowed close; the sent list logs each note's words and says how far back it reached; a second-degree page with Follow and Message says Connect is under More"),
            (30, "2026-10-22", False, "reads and saves hold nothing back of the app's own; a page loaded after LinkedIn stopped the day is kept and stops the run"),
            (31, "2026-10-22", False, "a batch of six or more notes all in one sentence order is not saved, and reading.py batch says so; the queue is checked at the next save or batch, not redone; a removed reading limit's own comment goes with it"),
            (32, "2026-10-23", False, "a card-only note to someone known only from a connection made long ago is refused until their profile is read"),
            (33, "2026-10-24", False, "drafts honour the person's number at one employer (more-at) and hold an InMail until their message window is checked; an Open Profile note is held to an InMail's length; a reading is judged on the day given (grounded today=); nothing is kept in the example person"),
            (34, "2026-10-25", False, "a phone is asked only for what a phone can send, in its short wording; the Chrome wording names the tab Claude opened; a path printed across two Windows drives no longer stops a reading; works in folders with brackets in their names; moved reading-ledger files are named with /; a first note keeps the parts it was built from, so a tweak rebuilds it without a rewrite; a reading the page made is logged as a computer chat's is"),
        ),
        "fingerprint": "9e0304be7b9bb02e",
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
            (14, "2026-10-21", False, "sector.kind reads what the person's catalogue calls an employer, for the interview pack; screening unchanged"),
            (15, "2026-10-21", False, "The bar says when an employer is on none of the profile's lists, and reads a judgement recorded once with bar.py judge"),
            (16, "2026-10-21", False, "The tracker status vocabulary lives in one place; an older interviewing spelling reads as a live interview"),
            (17, "2026-10-21", True, "Pay for your own place read with the one place matcher, regions beside remote judged by whether they take in your country, one degree list and an abbreviation-aware sentence splitter, cut wording defined once, Hybrid and Sr. variants are one posting, the extracted screen cuts pay only below the cut line, and the throttle reads each state file once"),
            (18, "2026-10-21", False, "throttle.py gains a public same_title wrapper"),
            (19, "2026-10-21", True, "A second language asked as a plus or named as a market is ranked, not cut, and the rulings it saved are released; a remote region that takes in home passes beside any country, home written as a code is home, a time zone is hours, a country the profile does not list is flagged; 'U.S. Citizen' reaches the eligibility gate; a data role beside a profession and supply-chain Master terms are read right; a ruling on one posting no longer hides a new opening months later, and a skip recorded for a score no longer blocks; bar.py judge keeps every judgement for its own employer"),
            (20, "2026-10-21", True, "A second language, or your own, asked as a nice-to-have ('a huge plus', 'Bonus:', or under a 'Nice to have:' heading) is ranked, not cut, while one in the same sentence as an unrelated preference word still cuts; inclusion wording never lifts the credential gate; a sentence ending 'in the U.S.' is not joined to the next as a citizenship condition; a remote role in a state abroad is flagged and an on-site home-town name abroad fails; a region alone is read by both gates the same way; a heading word inside a sentence no longer splits it"),
            (21, "2026-10-22", False, "A home town's name that starts a longer town's name (Bury St Edmunds, Bolton-on-Dearne) is flagged for a closer read, and so is one beside a state of home the profile does not place (Manhattan, KS for New York). Nothing ruled out before would now pass, so no ruling is released."),
            (22, "2026-10-22", False, "a province code between hyphens and a home town named like a state are home again"),
            (23, "2026-10-22", False, "the hand-run round moved to manual-round.md; the round's reply is shorter"),
            (24, "2026-10-22", False, "ends with a short first-time note or an occasional tip, not a line every session"),
            (25, "2026-10-22", False, "no search runs while job sites are blocked; a web-search lead is shown only once its page proves it open"),
            (26, "2026-10-22", False, "plain words to the person: no file, id, command or pull request link"),
            (27, "2026-10-22", False, "a graduate degree offered beside a bachelor's is no graduate bar, in the screen and the posting profile as in the score; curly apostrophes read like straight ones"),
            (28, "2026-10-23", False, "a bachelor's named after the graduate degree, or written B.Sc., B.S. or B.A., is read as the other way in, and a PhD offered beside a master's either way round is a master's bar; flags and scores only, nothing to redo"),
            (29, "2026-10-24", False, "a years bar is lost only to a preference word that governs it, not one about tech or a marketplace in the same sentence; experience in business operations is not a company's age; a degree's other way in is read in its own words (through work, research or projects, practical experience, in lieu of a degree); a degree's other way in counts only in the degree's own sentence, and a preference after another figure belongs to that figure"),
            (30, "2026-10-25", False, "job-alert dates are no longer read (the mail reader was removed); every screen reads its files as UTF-8; a years bar and a degree route are read in more words (N or more years, years' experience, 7+ years in a field, an equivalent combination); a language named as a market is ranked, not cut, and its rulings are released; one role per employer keeps the best fit; a posting past its deadline stays out; bringing a relist back lifts the ruling that dropped it; the bar reads the tech list as the sector does; a referral in progress holds cold applications by its stored status; a round keeps each job's apply link and its check, made from the boards the round already read; /rank points at RUNBOOK.md for what a reaction changes; the throttle reads the tracker through the one loader"),
            (31, "2026-10-26", False, "the seen-jobs file's reader and writer and the status spellings have public names the page's engine calls (exclude.load_seen, save_seen, reason_group, throttle.spellings); nothing screened differently"),
        ),
        "fingerprint": "6f3cd0d27ac0cd82",
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
            (7, "2026-10-21", False, "The job round judges employers the bar does not know yet before applying the bar"),
            (8, "2026-10-22", False, "plain words to the person: no file, id, command or pull request link"),
            (9, "2026-10-25", False, "the brief is made at the end of setup with no questions (Mondays and Thursdays at 07:38 in the person's own zone, in a chat of its own); list_triggers' own shape is read and a brief under any name is found; a brief turned off or whose last run failed is flagged; push alone is enough for the old relay; a task set to run more than once a day is refused, since every run pays a whole chat again; Claude's rules for setting the brief up moved from CLAUDE.md to automation/README.md; the brief's days and time are moved, and a break is taken until a date, from the page (routines.py move, pause and resume: the brief and every follow-up held, put back exactly on return), with the scheduled-task calls only a chat can make kept until it makes them"),
            (10, "2026-10-26", False, "at_most_daily is public; the page moves the brief and takes a break through move, pause and resume, the one break the search has"),
        ),
        "fingerprint": "ac65ce319ce5a64d",
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
    "page": {
        "by": "upgrade", "priority": 2, "applies": "app_page", "time": "~1 min",
        "gives": "your app page published again with the current design",
        # Every version of the page is its own code changing under every open window, and an
        # open page has it only from a republish: a wording fix entered with rerun False never
        # reached one. So every version reruns (`behind`), and only the chat that answers the
        # page publishes it; any other asks that chat to (tools/app_listen.py).
        "every_version": True,
        "run": "ask the chat that answers the page to republish it, never publishing it from "
               "here: python3 tools/app.py republish <scratch>/republish, then send the batch "
               "it prints to the page (ArtifactData batch, to the profile/app.json url)",
        "files": ("templates/app/*", "tools/app_page.py"),
        "versions": (
            _first("no page: everything was shown in the chat"),
            (2, "2026-10-25", True, "the app page: everything the search shows, live progress "
                                    "for every job, ticks with undo, talking to Claude in it; the page also carries setup, updates, alerts with one suggestion per card, lists that show everything live and fold finished history, and links between a job, its drafts, its contacts and its interview; contact addresses are owner-only documents in the page's database"),
            (3, "2026-10-26", True, "the page in the rosé pine colours on the layout spec: one summary and one row of controls a screen, every tap sent in the engine's own shape with its item's rev, the engine's stage and cost tables embedded, links only by the engine's own; outcomes, replies, calls and referrals on the page; message cards with copy, counts, open and I sent it; waves; the item view; the LinkedIn download and profile reading; where Claude works, your search, your brief, and the one listener; the work list knows the republish kind"),
        ),
        "fingerprint": "b1c809b85f10d7dc",
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
            (5, "2026-10-21", True, "Says which gaps to learn and which to show evidence for, and counts what stopped skipped postings"),
        ),
        "fingerprint": "0c894b60c8eb9290",
    },
}

# Every other app file, and why a change to it needs no version. A glob is matched
# with fnmatch, so `*` crosses folders.
KEEPS_NOTHING: dict[str, str] = {
    "tests/*": "tests change nothing a person has",
    "tools/dates.py": "reads a date; every tool that keeps something is versioned where it keeps it",
    "tools/offline_boards.py": "a test seam: canned board answers inside a test, nothing kept",
    "tools/try_personal_tests.py": "the maintainer's pre-release check; reads a copy, keeps nothing",
    "tools/rehearse_sync.py": "the maintainer's pre-release rehearsal of a sync on throwaway "
                              "copies; keeps nothing",
    "tools/holidays.py": "works out public holidays when a date is counted; writes nothing, and "
                         "a person's own dates live in their search.py PUBLIC_HOLIDAYS",
    "tools/local_path.py": "finds the tools a computer installed (bun, TeX) for the session that "
                           "runs; keeps nothing",
    "tools/local_path.sh": "the same, for the shell scripts; keeps nothing",
    "tools/network/own_profile.py": "looks over the person's own LinkedIn profile when due; its "
                                    "one record, documents/network/own_profile_review.json, is "
                                    "kept by the own-profile-review upgrade and by `due`",
    "tools/told.py": "records, when asked, the place each employer heard in person.json; "
                     "what that changes in a pack or a note is versioned with those",
    "tools/profile_consistency.py": "reads the profile and names what disagrees; the person "
                                    "corrects it, through the profile-consistency upgrade",
    ".github/*": "the app's own CI and issue templates",
    "profile.example/*": "the invented example person; a new profile name in it is a profile "
                         "upgrade or a safe default, which tests/test_profile_upgrades.py holds",
    "*/.gitkeep": "an empty folder's marker",
    "CLAUDE.md": "read afresh by every session",
    "tools/CLAUDE.md": "a note Claude Code loads when a chat opens the app's code; it keeps nothing",
    "docs/rule_map.json": "where each rule of the long CLAUDE.md went, read by a test; it keeps nothing",
    "AGENTS.md": "read afresh by every session",
    "GEMINI.md": "read afresh by every session; it only points to AGENTS.md",
    "README.md": "documentation, read when needed",
    "ARCHITECTURE.md": "documentation, read when needed",
    "CONTRIBUTING.md": "documentation, read when needed",
    "MAINTAINING.md": "documentation, read when needed",
    "SECURITY.md": "documentation, read when needed",
    "SETUP.md": "documentation, read when needed",
    "HELP.md": "documentation, read when needed",
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
    ".claude/skills/job-scraper/manual-round.md": "a round done by hand, read afresh each time",
    ".claude/skills/job-application-assistant/SKILL.md": "routing: which command handles what",
    ".claude/skills/job-application-assistant/11-cost-model.md":
        "which model runs each stage; what it writes is held to the same checks",
    ".claude/workflows/repo-audit.js": "read-only",
    ".claude/commands/upgrade.md": "the machinery that carries changes; it keeps nothing itself",
    ".claude/commands/outcome.md": "records what happened, which a better method does not change",
    ".claude/commands/html-report.md": "a report derived on request, never kept as state",
    ".claude/commands/threads.md": "a view derived from the message log on every run",
    ".claude/commands/reset.md": "removes state on request",
    "tools/sync_app.py": "the machinery that carries changes; it keeps nothing itself",
    "COMPUTER.md": "how a computer is made ready; it leaves only installs, never a record",
    "tools/computer_setup.ps1": "installs on Windows into the person's own folders; keeps nothing",
    "tools/installs.py": "installs into the person's own folders; keeps nothing tracked",
    "tools/find_copy.py": "finds the person's copy on GitHub to clone; keeps nothing",
    "tools/brief.py": "gathers each brief afresh; its records are dated records of one run",
    "tools/followup_drafts.py": "drafts afresh every run; a pack is the day's",
    "tools/cost_meter.py": "development tooling: measures what a run reads, keeps nothing",
    ".claude/agents/news-reader.md": "searches afresh for each brief; keeps nothing",
    "tools/app.py": "the page's view, derived from the state files on every run",
    "tools/tweak.py": "applies a change the person asked for, on demand; the record it keeps of their changes (tweaks.json) is theirs and is never remade",
    "tools/app_setup.py": "builds the setup steps the page shows from the profile, on every run; keeps nothing",
    "tools/app_alerts.py": "derives each card's alerts and its one suggestion from the records, on every run; a No thanks is kept by the page's own action",
    "tools/added_jobs.py": "a job the person added on the page, kept in their own records by the writers that already keep jobs; keeps nothing of its own",
    "tools/profile_set.py": "writes one profile setting the person changed on the page through the profile's own files; keeps nothing of its own",
    "tools/app_lists.py": "derives the page's lists, their folds and filter counts from the records, on every run; keeps nothing",
    "tools/app_model.py": "the page's view, derived from the state files on every run",
    "tools/page_db.py": "reads and writes the page's database dumps; keeps nothing of its own",
    "tools/app_actions.py": "writes the person's own answers through confirm, exclude, state.py, learned and settings; nothing it wrote is remade",
    "docs/images/page-demo.gif": "a short recording of the page for the README, from the test sample; never in a person's search",
    "tools/app_listen.py": "names the one chat that answers the page, in the page's own database and a record in the git folder that is never committed; read afresh at every start",
    ".claude/skills/app/SKILL.md": "the chat's procedure when the page rings, read afresh each time",
    "tools/confirm.py": "writes the person's own word about an application into the tracker; nothing it wrote is ever remade",
    "tools/filtered.py": "shows and brings back a round's filtered postings; the list is rewritten every round",
    "tools/platform_check.py": "the app's own proof on every platform; never runs in a person's search",
    "tools/py.sh": "finds the Python to run; leaves nothing behind",
    "tools/safe_name.py": "makes a file name safe on every computer; computed on every run",
    "tools/tips.py": "says a line now and then; what it said is a record, never something to redo",
    "tools/shown.py": "copies a document to send under its owner's name; the copies are ignored by git and made again on every send",
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
    "tools/lookup_score.py": "a lookup run on demand",
    "salary_lookup.py": "a lookup run on demand",
    "tools/convert_salary_excel.py": "a lookup's data converter, run on demand",
    "tools/leak_scan.py": "development tooling",
    "tools/name_guard.py": "development tooling: checks what the app carries, keeps nothing",
    "tools/app_watch.py": "checks the public app from the maintainer's repo; keeps only a "
                          "note in .git of what it has read",
    "tools/csv_store.py": "reads and writes a state CSV in place; keeps nothing",
    "tools/release.py": "publishes the app's releases from its own CI; keeps nothing in a repo",
    "tools/public_names.py": "development tooling: checks no public name goes unannounced, keeps nothing",
    "tools/public_names.json": "the names the last release shipped, read by a check; keeps nothing",
    "docs/removed_names.json": "the public names the app took away on purpose, read by a check; "
                               "keeps nothing",
    "tools/name_guard_allow.txt": "the name guard's list of invented names; keeps nothing",
    "tools/build_app.py": "development tooling",
    "tools/save_state.py": "stages the person's files for a commit; leaves nothing of its own",
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
                      "record, profile/place.json, is /setup's question",
    "tools/setup_env.sh": "sets up the container, which is new every session",
}

_OPEN = re.compile(r"^<!-- section: ([a-z-]+) -->\s*$")
_CLOSE = re.compile(r"^<!-- /section -->\s*$")


def regions(paths=SETUP_FILES) -> dict[str, list[str]]:
    """{section: [the text of each marked region, in order]} from setup.md and
    setup-sections.md (or the one file named)."""
    out: dict[str, list[str]] = {}
    for path in ([paths] if isinstance(paths, str) else paths):
        if os.path.isfile(os.path.join(ROOT, path)):
            _regions_of(path, out)
    return out


def _regions_of(path: str, out: dict[str, list[str]]) -> None:
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        lines = fh.read().splitlines()
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


def _tracked() -> list[str] | None:
    """Every file git tracks here, or None without git. Only tracked files count: a
    glob over the disk also caught `__pycache__`, so the hash differed between machines."""
    try:
        r = subprocess.run(["git", "-C", ROOT, "ls-files"], text=True, capture_output=True,
                           timeout=20, encoding="utf-8", errors="replace")
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
        rel = local_path.rel(person.path("person.json"), ROOT)
    except person.NoProfile:
        return ""
    if rel.startswith(".."):
        return ""
    try:
        shallow = subprocess.run(["git", "-C", ROOT, "rev-parse", "--is-shallow-repository"],
                                 text=True, capture_output=True, timeout=20,
                                 encoding="utf-8", errors="replace").stdout.strip()
        if shallow != "false":
            return ""
        out = subprocess.run(["git", "-C", ROOT, "log", "--diff-filter=A", "--format=%ad",
                              "--date=short", "--", rel],
                             text=True, capture_output=True, timeout=20,
                             encoding="utf-8", errors="replace").stdout.split()
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
    every = bool(METHODS[name].get("every_version"))
    return [v for v in METHODS[name]["versions"] if v[0] > mine and (v[2] or every)]


# ------------------------------------------------------------------ applies

def _tracker_statuses() -> set[str]:
    path = person.state("job_search_tracker.csv")
    import csv_store
    csv_store.refuse_conflicts(path)
    # Read the way every state file is (a spreadsheet's save included), not as UTF-8
    # alone, which a tracker saved in Windows' own encoding crashed (2026-10-25).
    try:
        return {(r.get("status") or "").strip().lower() for r in csv_store.read_rows(path)}
    except OSError:
        return set()


def _has_rows(path: str) -> bool:
    import csv_store
    try:
        return bool(csv_store.read_rows(path))
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
    "app_page": lambda: person.exists("app.json"),
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
