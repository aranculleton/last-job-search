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
            (23, "2026-10-26", False, "every file it writes has plain line ends on Windows too"),
            (24, "2026-10-29", False, "unused helpers removed (workday_paths, PortalDown); boards are read as before"),
            (25, "2026-10-30", False, "an employer board's posting is judged by its own location, its office tags only where it names no place; searches already run stay as they are"),
            (26, "2026-11-03", False, "a site this chat's cloud settings refuse is said as that, with the one fix, never only as unconfirmed"),
            (27, "2026-11-06", False, "every job site has a plain name and a one-line note, and one that needs a key says so with the steps to get one (Adzuna: a paid plan, since its free plan's 25 searches go within one search here); /add-portal writes label, note and the key's lines; nothing to build again"),
            (28, "2026-11-06", False, "the app's example person lists only the app's own job sites, never the copy's own, so the app's checks pass in a person's copy; nothing to build again"),
            (29, "2026-11-11", False, "the robots.txt check names the new page fetcher it gates (tools/fetch_page.py); no board changes"),
            (30, "2026-11-11", False, "openroles 0.5.1 reads the boards: a robots.txt with a byte-order mark or a percent-encoded rule is obeyed and one with a rule that cannot be read is a no, a host that says slow down is sent nothing until its pause has passed, a Greenhouse or Gem posting is where its own location says, not where its office tags are, a posting listed on two pages comes back once, and what a description left out is counted for every part of it, text hidden by an inline style of any kind included"),
        ),
        "fingerprint": "66a9ac7874b3ff41",
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
            (11, "2026-10-29", False, "a search runs as a background job inside the one helper chat, beside up to two other big jobs; what it finds and scores is as before"),
            (12, "2026-11-03", False, "setup writes every language held and the screen cuts any other a posting requires, and a title in one; where the market posts in another language its own titles are researched; every pay figure is a year's"),
        ),
        "fingerprint": "c6252b5fe10c3050",
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
            (8, "2026-10-26", False, "every file it writes has plain line ends on Windows too"),
            (9, "2026-10-29", False, "the Gulf pay guide is listed by its title"),
            (10, "2026-11-03", False, "the market brief names the country's languages and says the field tables' titles and tools are US English, and setup researches the local ones; pay stated by the month is read as twelve months"),
            (11, "2026-11-11", False, "every page the market brief reads is fetched at the address as written, never as a list of addresses; nothing made changes"),
        ),
        "fingerprint": "21783d07128058a8",
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
            (5, "2026-11-03", False, "spelling is one of four varieties, read from the market tables' wording too; a letter in another language records its language so it is dated in it; a promotion is two roles at one employer"),
        ),
        "fingerprint": "1b1febaa9dad7e6c",
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
            (8, "2026-10-26", False, "every file it writes has plain line ends on Windows too"),
            (9, "2026-11-03", False, "the profile's summary sits under its exact heading, which the general resume starts from (a profile without it is an upgrade), and a resume built with Claude asks its last question, where they studied, certificates and languages, on its own"),
            (10, "2026-11-10", False, "the interview guide's question to ask about growth fits any role (bigger, more strategic decisions), not only a software engineer's; nothing made before needs making again"),
            (11, "2026-11-10", False, "the interview guide's questions to ask read as they are said, with no slash (how a piece of work goes from idea to production; working from home some of the week; new work against keeping things running); nothing made before needs making again"),
        ),
        "fingerprint": "108db9a2cdb0b91c",
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
            (24, "2026-10-26", False, "every file it writes has plain line ends on Windows too"),
            (25, "2026-11-03", True, "a call prep says a reason to ask you first in plain words (Claude asks you first), with no command in it, and a document an older version wrote is still read; a stock answer naming a place that employer did not hear, or a pay figure beside another band, is left out, never offered as prepared; the check fails on a gap to fill under any heading, a number the profile does not hold and a place the profile no longer says; months are counted as said; one line per resume sent; a skill held under another name (Azure Data Factory is Azure) is never offered as a near match; a manager's leadership answer leads with the team they ran; asked for in a chat, a call prep is given in the chat in full as well as on the page"),
            (26, "2026-11-07", False, "a label on a line of its own above the words to say (\"SAY.\", \"Say this:\") is never said, never shown as a line of its own, and fails the check; a line opening \"Note to you, not to say:\" is a note; documents are written as before"),
        ),
        "fingerprint": "5247ebda28f11685",
    },
    "drafts": {
        "by": "upgrade", "priority": 2, "applies": "unsent_drafts", "time": "~5 min",
        "gives": "applications not yet sent re-rendered and re-checked by the current build",
        # All of it in code: each unsent application made again and checked, the version
        # kept on each that passes, a redraft or a To do card for each that fails, the
        # tracker put right, and the method recorded only once every one has passed. Said
        # as a sentence for an agent, it rendered 17, three failed, and it was recorded done
        # with nothing made for the three (the maintainer, 2026-11-05).
        "run": "python3 tools/remake_drafts.py, which never touches one already sent; say the "
               "one line it prints, if any, and nothing else",
        "records": True,
        "check": "remake_drafts.pending",
        "files": ("templates/*.py", "templates/README.md", "tools/render_application.py", "tools/bullet_rewording.py",
                  "tools/remake_drafts.py",
                  "tools/fit_to_page.py",
                  "tools/posting_profile.py", "tools/draft_pack.py", "tools/draft_audit.py",
                  "tools/draft_cost.py",
                  "tools/skills_block.py", "tools/allocate.py", "tools/bullet_library.py",
                  "tools/docpaths.py", "tools/doc_name.py", "tools/outreach.py",
                  "tools/screening_answers.py", "tools/form_answers.py", "tools/record_drafts.py", "tools/stage_picks.py",
                  "tools/check_claims.py", "tools/check_numbers.py", "tools/voice_check.py",
                  "tools/locale_rules.py",
                  "tools/audit_letters.py", "tools/verify_pdf.py", "tools/verify_batch.sh",
                  "tools/verify_batch.py", "tools/pdftext.py", "tools/general_resume.py",
                  "tools/design_check.py", "tools/apply_link.py",
                  "tools/untrusted.py", "tools/bridges.py", "tools/skill_answers.py",
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
            (52, "2026-10-26", False, "templates/app/palettes.py, which this method's templates/*.py takes in, moved the page to the rosé pine colours; a page action that changed the tracker reads it again at once (docpaths.forget_abbreviations); the em dash check cites the writing guide's rule 1; no document changes; every file it writes has plain line ends on Windows too; and the page's accent is rose pine's lilac, its cards closer together"),
            (53, "2026-10-26", False, "RUNBOOK: saying update in any words is enough and the page is brought up to date at once, unasked; the pin is offered once ever; a timer or background job that brings nothing is never mentioned; one folder per application, named once for its employer (Profile upgrade: one-folder-each moves strays); no pay question raised from the employer's revenue; a resume bullet can name a skill the person said yes to, for that application only (same numbers and tools, only the yes added, only into related work, checked by both audits and the renderer); with no rewording every document renders as before"),
            (54, "2026-10-29", False, "the page's light colours, kept beside the document templates, cooled; every document renders as before"),
            (55, "2026-10-29", False, "an employer researched recently is drafted from its saved research, with no research agent; the outreach note is written by the final check; long work on another model runs as an agent inside the chat that answers the page, never a chat of its own; work from the page goes to whichever chat answers it, cloud or computer; documents render as before"),
            (56, "2026-10-29", False, "RUNBOOK.md says how an interview's time is saved on its record (interview_pack.py book and times); documents render and are checked as before; a big job runs in a chat of its own, never in the chat that answers the page, and the landing check runs in the background with the person's own tests run once; documents render as before"),
            (57, "2026-10-30", False, "RUNBOOK.md says a cloud chat unsubscribes from the pull request it opens at once; a recorded reaction says to save it with the turn's work; documents render and are checked as before"),
            (58, "2026-10-31", False, "a rule the person says again replaces the older one by itself, keeping what it held; one that may contradict an older rule is judged by the chat recording it, and only one it truly cannot call reaches the page as a single, seldom question; adding to a list of employers is no longer read as a contradiction; documents render and are checked as before"),
            (59, "2026-11-02", False, "the RUNBOOK says where a booking goes: a call's time and zone in its next action, and anything else booked into Coming up with upcoming.py add"),
            (60, "2026-11-02", False, "the RUNBOOK says where a request to watch something in the brief's news goes (brief.py watch); documents render and are checked as before"),
            (61, "2026-11-02", False, "the page's palette gains a green for today and a gold for tomorrow; documents render and are checked as before"),
            (62, "2026-11-03", False, "the RUNBOOK lands a chat's work with one background command, tools/land.py, once the answer is out; independent commands go together as separate calls; documents render and are checked as before; the RUNBOOK says the interview prep is in plain words; documents render and are checked as before"),
            (63, "2026-11-03", True, "filling the page stops before the margin the verification checks, so a fitted resume never fails it for text too near the edge; a yes is written into the candidate profile when it is recorded and refused anywhere the profile does not hold it; a letter copying the research's own sentence or saying where you are twice is held back; a role over its cap for the posting is held to it and checked; a sentence changed after the audits, and a claim or number the batch failed on, are recorded on the application; a resume that breaks your own rules is never offered; references lines, passed dates and a start your notice does not allow are refused; a skill held under another name (Azure Data Factory is Azure) is never offered as a near match; the RUNBOOK says a landing brings in what an earlier chat left waiting and settles a file two chats changed without losing either side, and that a chat that cannot start the improvements says why; the drafting skill no longer grants itself any command or web fetch, only the app's own checks; the general resume's stop says to write the summary into the profile under its exact heading; a promotion prints both titles under their own dates and a job with no achievement on file as its title line, a letter in another language is dated in it (an unsent letter keeps its day in its own language), the close states the right to work only where the person's status needs saying, the outreach note offers an InMail only on a plan that has them, and a pick today's screen would leave out is asked about before drafting; an application asked for in a chat is given in the chat in full as well as on the page"),
            (64, "2026-11-04", False, "on Windows, a PDF in a folder named with an accent is read by Poppler too, where pypdf cannot run, and a skill you said no to straight after a yes is refused again at once; nothing made before needs making again"),
            (65, "2026-11-04", False, "a resume is offered to a contact only when it is the one the app made and checked and your own rules do not say never to send it; an older hand-made file is never offered, and with none the guidance says to make one"),
            (66, "2026-11-04", False, "a resume can be drafted alone (stage_picks.py --resume-only, a draft's resume_only from the page): no letter is drafted, audited, made or named in the tracker, which names a document only once it is on disk and is read back after writing; documents with a letter render and are checked as before, so nothing made before needs making again"),
            (67, "2026-11-05", True, "a skill the profile holds that the posting names goes into one to three of the resume's own bullets, lightly reworded with the same numbers and never asked about, and the check holds back a resume that leaves it, or a yes, on the skills line alone where a bullet could take it; a tool the profile names at an employer can be named in that employer's bullets; the skills line names each skill once, a yes inside a grouped item included, so unsent applications are made again to take the repeat out"),
            (68, "2026-11-05", False, "a skill question nobody answered is never a no: the answer is one record per skill that every chat and application reads (tools/skill_answers.py), the later answer winning, a question still open put to the person once on their page while the draft goes on without the skill, waiting on it, and a yes redoing every resume drafted that day with it; a draft with no skill waiting renders and is checked as before, so nothing made before needs making again"),
            (69, "2026-11-05", False, "the runbook lists reading.py linkedin-check; no document changes"),
            (70, "2026-11-05", True, "a resume drafted alone, or a draft missing its letter, has its summary checked like any other and is made once both checks pass, and the tracker names a letter only where one was written; a reworded bullet the check passed is printed whenever the resume is made again, even without the posting beside it; a sentence ends after a name in capitals (AWS., SQL.) and never after an initial (U.S.), so a summary is cut where it should be and no sentence shows as unchecked; the drafting steps and the check read a research fact the same way, so a draft is never held back for a mismatch that was not there; unsent applications are made again"),
            (71, "2026-11-05", True, "making unsent applications again is done by the app's own code: each is checked, the newest version is kept only on the ones that pass, one that fails is given its own way forward by itself (its copied part rewritten, or one To do card where only you can settle it), a letter breaking its own rules now counts as failing on its record, and a tracker row naming a letter for an application with none is put right; this is recorded done only when every one has passed, so applications an earlier run left failing are made again and handed on"),
            (72, "2026-11-05", False, "the run book names the whole command that records a no to an improvement's question, python3 tools/profile_upgrades.py --no <id>, never --no alone"),
            (73, "2026-11-05", False, "a computer with no LaTeX leaves unsent applications as they are and tries again later, and a compile that fails puts the earlier PDF back; a skill whose reworded bullet the model audit removed or refused stays on the skills line with a note, never demanded again; a yes reaches every unsent resume waiting on it, whatever day it was drafted; the run book's round needs no folder named; documents render and are checked as before, so nothing made before needs making again"),
            (74, "2026-11-05", False, "a form's own questions (why us, why this role, a time you used a tool) are answered from your profile and the posting and kept with the application in its screening_answers.md (tools/form_answers.py), an example you asked for marked as a draft for you to confirm; the resume and the letter are never changed by it"),
            (75, "2026-11-05", False, "the page's colour pairs (templates/app/palettes.py) hold a soft button's edge in a card's suggestion box; no document is made differently"),
            (76, "2026-11-05", False, "a role kept for a referral in progress carries its note (referral_note) into the picks and the tracker row; documents are made as before"),
            (77, "2026-11-05", False, "a skill question has a third answer, just for this role: the skill goes on that role's resume and bullets through the draft's own yes, never into the profile or onto another role, which a later posting asks again; a yes and a no work as before, so nothing made before needs making again"),
            (78, "2026-11-05", False, "a resume made for a contact who asked for one with no role named is kept in their own folder, named for them and shown on their card, never in place of the person's own; nothing made before needs making again"),
            (79, "2026-11-06", False, "the run book says rules the app has since built in are retired once after an update, and a complaint about the app is never kept as a rule; no document changes; RUNBOOK.md says the brief asks for a new LinkedIn download once it is due by export.every_days (weekly while the person is messaging people, a fortnight otherwise, or as they chose); documents render and are checked as before; the run book says the person's own tests an update broke are brought in line by a background step while each save sets them aside; the run book says how a search limited to the employers the person names is run (run_round.py --employers)"),
            (80, "2026-11-06", False, "a new resume and letter are named the person, the employer, then the document (<Prefix>_<ABBR>_Resume, <Prefix>_<ABBR>_Cover_Letter); one made before keeps its name and every reader finds both orders; the file you download or send is named by Settings, File names; nothing made before needs making again"),
            (81, "2026-11-06", False, "the landing steps unsubscribe from a save's pull request as soon as it is opened, before its merge, so a save no longer wakes the chat twice more"),
            (82, "2026-11-06", False, "a general resume's summary goes through the grounding audit's own questions, a written one with its claim map (stage_picks.py general --claims-file), and one questioned is never made; its draft is kept (documents/cv/general/draft.json) so the pencil changes its bullets, its look and its summary as an application's, the summary through both audits, which ask a general draft only grounding questions; one made before has no pencil until a fresh one is made, and nothing made before needs making again"),
            (83, "2026-11-09", False, "a hold on a contact with no end day lifts on the day beside it; the runbook says where every hold is listed"),
            (84, "2026-11-10", False, "a resume made for a contact is named as the person's own (<Prefix>_<Noun>.pdf) in the contact's folder, never _For_<them>: the contact receives the file; older ones keep their names"),
            (85, "2026-11-10", True, "every font on a resume is set with no kerning, so an applicant tracking system reads AWS, VAT or Vancouver as one word (a kern pair read as a space split \"AWS\" in summaries, and \"V ancouver\" under the classic design); the cover letter's fonts likewise (it read \"L TV\"); the round trip names any word the text layer splits, verify_batch flags one in a letter (SPLIT_LETTER), and the font probe reads kern pairs; unsent applications are made again so none goes out with a split word"),
            (86, "2026-11-10", False, "a resume made for a contact goes into the page's store as it is made, so its Get it downloads at once; a job's own chat lands its work with land.py in the foreground and brings the page up to date itself, never messaging another chat; a networking item sent to the computer with args.read_first reads each profile there before rewriting its note"),
            (87, "2026-11-10", False, "how a draft's work is saved changed: a save of only the person's own files lands after a data check with no code checks, and a chat on the person's computer saves to GitHub and leaves the merge to the chat that answers the page; nothing made before needs making again"),
            (88, "2026-11-10", False, "a draft recorded in the tracker notes where it is on the page, so the answer that made it carries a Ready in Jobs button to that draft; nothing made before needs making again"),
            (89, "2026-11-10", False, "assembling a batch names each pick still held for the person's answer, with its question, never leaving it out without a word"),
            (90, "2026-11-11", False, "functions nothing in the app called are retired (render_application.strip_legal, general_resume.for_contact_word); nothing made changes"),
            (91, "2026-11-10", False, "record_drafts.py check names a cover letter on disk its row does not name, a document no row names and a row naming a document not there, changing nothing; applications already made stay as they are"),
            (92, "2026-11-10", True, "a letter's close is checked in code, as the drafting contract already asked: it says where the person is (the place this employer heard, else their own), their right to work where their status needs saying, and never ends on \"I would welcome the chance to discuss\"; unsent letters are checked again, and one without its close is redrafted"),
            (93, "2026-11-10", False, "the resume check writes a resume's text only beside it, as a .txt in cv/ or cover_letters/, never anywhere else; nothing made before changes"),
            (94, "2026-11-11", False, "a posting a 403 refused is fetched again through tools/fetch_page.py, robots.txt read at every redirect and only what a reader sees kept; nothing made before changes"),
            (95, "2026-11-11", False, "where the profile allows a resume two pages, a last page of a few lines is put back on one page fewer when filling it finds nothing more to add, and the check says a near-empty last page or a heading alone at a page's foot in its own words (LAYOUT_RESUME); drafts made before are checked when next rendered"),
            (96, "2026-11-11", False, "a role the job board lists as a contract, temporary or an internship, whose posting never says how it is held, is asked about before it is drafted for someone who wants a permanent job; the posting's own words still decide wherever they speak; drafts made before are not made again"),
            (97, "2026-11-11", False, "the save steps a chat follows say land.py --detach, and what an ending of saved to master asks; nothing made changes"),
            (98, "2026-11-11", False, "RUNBOOK's map says /reply belongs to no skill, and the networking skill owns /network, /threads and /prep"),
            (99, "2026-11-11", False, "the experience section's heading moves to the next page with its first role rather than staying alone at the foot of a page; a resume whose heading never sat there comes out the same; RUNBOOK.md says a computer chat's save finishes there where the chat that answers the page is on the computer too"),
        ),
        "fingerprint": "36b55cdc4f0767ca",
    },
    "interview": {
        # Only a process with a round still to come is prepared again: a prep for a round
        # already held is history, and drawn as it was (the live prep, 2026-11-10).
        "by": "upgrade", "priority": 2, "applies": "interviews_ahead", "time": "~15 min",
        "gives": "the prep for each interview still ahead rewritten the current way",
        "run": "for each tracker row at `interview` with a round still to come, /interview "
               "<company> again, its pack written beside the old one and its live prep made "
               "(Step 3b). A pack the person wrote by hand is refused and left as it is (exit "
               "1, said in a plain line): that pack is done, so record the version once the "
               "others are rebuilt",
        "files": (".claude/commands/interview.md", "tools/interview_pack.py",
                  "tools/interview_live.py"),
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
            (23, "2026-10-26", False, "a stage booked with a time keeps it on its outcome.md line (scheduled <day> HH:MM), and booked again for the same day with no time it stays; the page reads the pack's one screen, its practice questions with the person's own answers and its format (one_screen, practice, format_of); an answer kept to work on is written once and can be taken off again; a process registered from the page keeps its call's time; next_stage is public; packs already made stay as they are; every file it writes has plain line ends on Windows too"),
            (24, "2026-10-29", False, "interview prep reads the saved employer research first and starts a research agent only when none is recent; no separate chat is offered for an employer, and a campaign chat started before carries on"),
            (25, "2026-10-29", False, "the pack asks which team the call is for only when the employer has another posting for the role, and lists the other postings, not the one the call is for; the same role on two boards is one posting and a posting past its deadline is none; an interview's time said in the chat, an invite, a message or a contact's note is saved on its record (interview_pack.py book and times, and --time when a stage is booked), so the page shows it instead of time not set; packs already made stay as they are"),
            (26, "2026-10-30", True, "a prep the page asks for after a booked stage's day has gone is for what comes next, never the stage already held, and the pack says which stage it is for in its first line"),
            (27, "2026-11-02", False, "a stage is booked with its kind (due by a day, or a meeting), its length and its time zone's own name (interview_pack.py book --due --minutes, --zone America/Toronto), so Coming up reads them rather than guessing from English words; packs are built as before; a time given on rebooking makes a test a meeting, and a zone it cannot place gives no time"),
            (28, "2026-11-03", True, "a stage booked with no day yet says so in its notes instead of an empty date; the prep reads in plain words for the minutes before a call: one screen with what they are checking, three to five things to say and two or three questions to ask, the one or two things not to say that matter (the rest kept under the gaps), every source said as what it is to you (never a file, a path or a command), contacts' states in words, what you sent named as your resume and cover letter, notes never repeated under Likely questions, \"Draft\" only above an answer that is one, and what Claude still has to look up or ask said plainly; the whole prep reaches the page, never cut; a stage keeps the zone its time was given in, its length and where it is, an invitation that offers several days keeps them and the day to answer by until one is chosen, a round moved under another name is moved rather than booked twice, the next round is the earliest by its day, a test is ticked when done, and a thank-you sent some other way is marked as sent; the outcome keeps one status once resolved, and a pack's stock answers follow the place and the band each employer heard; a manager's leadership answer leads with the team they ran; a pack asked for in a chat is given in the chat in full as well as on the page"),
            (29, "2026-11-05", False, "a booked round can be not confirmed yet, written on its line and cleared when booked again without it; a new day for the same round keeps its prep current, and a prep for an earlier plan of rounds is updated by itself; nothing made before needs making again"),
            (30, "2026-11-06", False, "a pack knows a resume or letter by either order of its name (<Prefix>_<ABBR>_Resume, or <Prefix>_Resume_<ABBR> before); packs are built as before"),
            (31, "2026-11-07", False, "a label on a line of its own above the words to say (\"SAY.\", \"**Say this:**\", \"Talking point\") is never shown as a bullet or said as part of an answer, the words under it are; a note to you (\"Note to you, not to say: ...\") is shown apart, under what it is about; the check fails a pack that still has such a label; the page reads every pack this way at once, so nothing needs making again"),
            (32, "2026-11-10", False, "an interview booked or registered notes where it is on the page, so the answer that booked it carries a Ready in Coming up button to it; nothing made before needs making again"),
            (33, "2026-11-10", True, "each interview still ahead gets a live prep beside its living document, in the order the interview runs and its own shape (a recruiter screen, a hiring manager, a technical round or a take-home, a case with a personal experience interview, a panel, a final): what to say first in each part with the questions it is likely to prompt, every likely question with who asks it, other ways it is put, a Simple and a Detailed answer and follow-ups by who asks, the stories each once, the role's words explained in the employer's own work with a worked example, the questions to ask them with what to ask next, the time each part takes at your own speaking speed, the questions they are known to ask answered first, and notes just for you; it is checked before it is kept (answers two to four sentences, the detailed one a little fuller, no long dashes, nothing assuming an earlier conversation, every term explained, every figure your profile's own); a prep for a round already held stays as it is"),
            (34, "2026-11-10", True, "each interview still ahead gets a live prep beside its living document, one interview in the order it runs, its stages from the interview's own kind and minutes from its length: a recruiter or HR screen, a hiring manager, a technical round (warm-up and background, a problem worked aloud, the probes and trade-offs, their questions), a timed test or exercise (how it works, how to take each kind of item, pacing, items to practise), a case (structure, the maths aloud, the answer in a minute), a personal experience interview, a take-home presented back, a panel, a final, and any of these combined in one sitting in the order they are named (a personal experience interview then live coding); a format set once with --format holds for every rebuild, an acronym nobody spelled out is never read as a kind and the closest kind is said to be assumed, and a short round prepares fewer questions than a long one. In each part: what to say first with the questions it is likely to prompt and a line to end on, every likely question with who asks it (hiring manager, technical interviewer, HR, future peer, senior leader, recruiter, partner), other ways it is put, a Simple and a Detailed answer and follow-ups by who asks; the stories each once; the role's words explained in the employer's own work with a worked example, one phrase for one word, and the words already explained for another role at that employer reused; the questions to ask them with what to ask next; the time each part takes at your own speaking speed; the questions they are known to ask answered first; and notes just for you. It is checked before it is kept (answers two to four sentences written as flowing sentences and never clipped fragments, the detailed one a little fuller, something to say first in every part, no long dashes, nothing assuming an earlier conversation, every term explained, every figure your profile's own). A skill, a tool or a certificate the posting names is asked in the part where the work is tested, never in the one story told in depth, and a posting's line reads inside a sentence with its capital only where it is a name. Preps asked for together are made as one job; a prep for a round already held stays as it is"),
            (35, "2026-11-10", False, "what kind of round it is, given when an interview is registered or booked (interview_pack.py process, book or pack --format), is kept under its stage on its record, and every prep for that round is built as it; a live prep that had to guess the kind says so when it is built; preps already made stay as they are"),
            (36, "2026-11-10", True, "each round is prepared as the kind its own words name: a round's number (Second round, Stage 2) is never read as a hiring manager's, and the kind is then said to be a guess; PEI is a personal experience interview; an online assessment, OA or a coding test on HackerRank or CodeSignal taken alone is a timed test with no hello and nothing to ask anyone, and a HackerRank round with nobody named is a test said to be a guess; a technical screen is a 45 minute technical round; a technical round at a consulting firm is not taken for its case; a behavioural, values or competency interview, a recorded video interview and several interviews back to back (a superday, a virtual onsite, an assessment centre) each have their own parts, and a day is timed as the whole day (four interviews of 45 minutes is three hours; two hours is 120 minutes); preps for interviews still ahead are made again"),
            (37, "2026-11-10", True, "a line of the posting reads as a question a person would ask (\"Familiarity with dbt\" is your experience with dbt, \"Excellent communication skills\" an example of your communication skills, \"Ability to work under pressure\" a time you had to), common words like inventory start small inside a question, and a credential the posting names is asked as whether you hold it (\"Are you a member of CIPS?\"), never as your experience with it; preps for interviews still ahead are made again"),
            (38, "2026-11-10", True, "the notes just for you read as sentences: how to put a place they may push comes first, then what your profile holds, each ending where it ends (no run-on, nothing cut mid-way), a line to say is marked as one, and each gap is said once, a credential as one you never claim with no example offered for it; preps for interviews still ahead are made again"),
            (39, "2026-11-10", False, "Claude writes only the words of a live prep, keyed by part and question, and the engine puts them in their place (live --fill takes the words; a whole filled copy is still taken); nothing made before needs making again"),
            (40, "2026-11-10", False, "an answer that says plainly you do not hold a qualification (\"No, I'm not a member of CIPS\") is never refused as a claim, and a gap's note reads as two sentences; nothing made before needs making again"),
            (41, "2026-11-10", True, "a simple answer is short lines to glance at, a sentence a line and none over 30 words, the detailed one prose; preps for interviews still ahead are made again"),
            (42, "2026-11-10", False, "a prep the page asked for with the kind of interview the person tapped is built with that format, kept on the round's record; nothing made before needs making again"),
            (43, "2026-11-10", False, "a qualification you do not hold is named in your notes in the posting's own words (CIPS membership); nothing made before needs making again"),
            (44, "2026-11-10", True, "every part a person answers in has its questions, each asked where it belongs: a part the records hold nothing for takes the questions its kind of interview usually brings (a manager's examples and why this role, the probes, a take-home's what you left out), every part keeps its first question within the round's time, a technical screen has the basics a screen checks in a part of their own, a case asks no experience question as its case, and a test taken alone practises no interview questions; preps for interviews still ahead are made again"),
            (45, "2026-11-10", False, "a live prep for a test taken alone is kept only once it has items to practise, each with how to take it and the worked answer; nothing made before needs making again"),
            (46, "2026-11-10", False, "saying you do not hold a qualification passes the grounding check only where the negation governs its name (I'm not a member of CIPS), never where a no sits elsewhere in the sentence; nothing made before needs making again"),
            (47, "2026-11-10", True, "the format given decides whether anyone is in the room whatever the stage is called (a CodeSignal or HackerRank assessment, an online test or an OA is a test taken alone), a test named by what it tests (SQL test, technical test) is a test said to be a guess, an assessment day and interviews counted as 4 x 45 min or three 45-minute interviews are a day timed as the whole day, onsite says where rather than what, and a count of questions the invite gives is the count prepared; preps for interviews still ahead are made again"),
            (48, "2026-11-10", True, "a posting's line reads as a question for every kind of line: a qualifier after it (is a plus, is desirable) is left off, a passion for something is what draws you to it, comfortable with something is a time you dealt with it, a degree said any way is what you studied, a line written to you (You have shipped production code) is when have you, and a one-word trait, a language or a duty is not asked; preps for interviews still ahead are made again"),
            (49, "2026-11-10", False, "a words file of the wrong shape is refused in plain words, never with a traceback, and a new question given an id already a question's is refused, so no Likely to prompt link is repointed; nothing made before needs making again"),
            (50, "2026-11-10", False, "a time ahead written in words (the first six months) and a figure inside a question asked of them are never refused as a number the profile does not hold; nothing made before needs making again"),
            (51, "2026-11-10", False, "a live prep made for another kind of round than its record now says is marked out of date, on the page and by live-check, so it is made again; nothing made before needs making again"),
            (52, "2026-11-10", True, "a part for a problem worked aloud leads with the problem as it is set and is not kept without one, and a question the stories already bring as a follow-up (What would you do differently now?) is asked there once, never also as a question of its own; preps for interviews still ahead are made again"),
            (53, "2026-11-11", False, "an interview's record, its posting and the questions kept from it are dated on the person's own day, never the computer's, and the next round booked is chosen against that day; the follow-ups that come after any story (What was your part in it, exactly?) are said once in each part a story is told in, never under each of its questions, and a follow-up written under two questions of a part is said once there; a prep saved before is read this way at once, so nothing needs making again"),
            (54, "2026-11-11", False, "a line of what to say first is read however it was written (plain words, or under t, text, line or say), a line with no words is refused when it is written and left out of a prep saved with one, so the page never shows Say first or Open with over empty lines, and live-check names each part left with nothing to say first; nothing is made again, and a chat writes only those lines with live --fill, every other word kept"),
        ),
        "fingerprint": "c330584f959cba7d",
    },
    "research": {
        "by": "upgrade", "priority": 3, "applies": "live_applications", "time": "~5 min each",
        "gives": "the research behind every live application gathered the current way",
        "run": "the employer-researcher again for each employer with an application at "
               "`drafted` or `interview`, refreshing company_research/<key>.json",
        "files": (".claude/agents/employer-researcher.md",
                  ".claude/skills/job-application-assistant/09-web-research.md",
                  "tools/company_research.py", "tools/fetch_page.py"),
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
            (10, "2026-10-26", False, "every file it writes has plain line ends on Windows too"),
            (11, "2026-10-29", False, "profile reading is written on wherever setup runs, and the LinkedIn download is asked for on the page; nothing researched changes; a research lock read before its time is written waits for it, so two writers at once both land"),
            (12, "2026-11-02", False, "two research writers at one moment on Windows both land: a lock refused for a moment is waited for, never a lost fact"),
            (13, "2026-11-03", False, "an employer's site this chat's cloud settings refuse is said to the person with the one fix, once, instead of a quietly thinner letter"),
            (14, "2026-11-10", False, "company_research.py check names a research file missing its employer, or, where it holds facts, its fetched day or sources, and one named apart from its key, changing nothing"),
            (15, "2026-11-11", False, "the 403 retry is tools/fetch_page.py, through this fetcher: robots.txt read at every redirect and only the words a reader sees printed, fenced; a page is read in the character set its own <meta> names, and one naming a set Python does not know no longer stops the run; nothing researched before needs doing again"),
        ),
        "fingerprint": "819b8785e0485253",
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
                  "tools/network/surface.py", "tools/network/inmail_pick.py",
                  "tools/network/candidates.py",
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
            (61, "2026-10-26", False, "two printed lines name the command that closes a contact (state.py set --status closed); the message log's direction is public (state.direction); nothing to redo; every file it writes has plain line ends on Windows too; and a page with thousands of contacts is built faster: the same dates, names and message words are read once, not thousands of times"),
            (62, "2026-10-26", False, "a draft is held to its own limit when saved (a follow-up to the nudge's), never-say rules about moving catch every way of saying it, and a draft that ignores or repeats the person's unanswered last message is refused"),
            (63, "2026-10-29", False, "no chat reads LinkedIn: the short list is queued for the person's page, which reads each profile with its Experience, Education and activity pages in the Claude desktop app, and every note waiting on those reads is rewritten as one piece of work; a run never waits on a read, and the people found are as before"),
            (64, "2026-10-30", False, "a run the page asked for brings back as many people as the person chose, 5 when not given"),
            (65, "2026-11-03", False, "a reply is two commands: reply.py prepare finds who wrote, logs their message, saves an interview time it gives and prints everything the draft needs; reply.py finish checks the draft, saves it for the page and writes the page's finishing batch; someone new is added by command (state.py add), never a second row for someone already in the book; an acceptance is recorded by command (state.py accepted) and the follow-up counts from it; their words pasted again on another day are not logged twice; one person in two conversations of a LinkedIn download is one line; nothing to redo"),
            (66, "2026-11-03", False, "an export's connections fill in the employer and title of a contact whose record has none, only where the row is surely theirs: their profile address, or their name with a request to them logged; a follow-up says only what they offered, a reply needs something of theirs to answer, a connection request with no note is a connection (a first message owed), an attachment after their ask is the resume sent, one person on two rows is one thread, a never-say phrase holds in its other forms and a name the profile says to write in full bans its initials; their message logged moves what is owed to the day it came, our answer to it sets the next follow-up by the person's rule, and thanks for a resume already sent is never read as asking for another; the person's own surface rules are one check (surface.held) for To do, Contacts, Messages and the brief: their limit of unanswered messages counted from the log, an employer their bar turns down (replies too), a country their search says is not home, a request nobody accepted and a closed thread; a booked call stays booked against the message that booked it; a reaction alone never reopens a thread; a role is never a sentence about someone; only a bar the person's own profile states turns an employer down or holds its people for a judgement, so a stranger's follow-ups and people at ordinary employers are shown again; a call invitation in its usual words (free for a 20 minute call, set up a call) is read as one, a question in another language ends on a question mark, a recruiter hears the person's status unasked only where it needs saying, and an application follow-up writes its dates by name and waits for the closing date"),
            (67, "2026-11-04", False, "a big contact book is read faster: a reply is read for a resume asked for before the checks that can only turn an ask down, and the check before anyone is shown takes the message log already grouped; nothing to redo; a nudge keeps the capital on an employer named in the books read now, never the books read when the chat began"),
            (68, "2026-11-04", False, "a LinkedIn download fills the name, employer and title a contact lacks from its connections, never over one already recorded, and says what it filled; the same download taken again on the page fills again rather than stopping at Already taken"),
            (69, "2026-11-04", False, "nobody is owed a follow-up message who cannot receive one: someone only ever sent an InMail, with no acceptance and no word back, is not listed, because a second would be a second InMail"),
            (70, "2026-11-04", False, "a follow-up finished with reply.py finish is checked as the follow-up it is, so one to someone who never wrote back is saved where Messages shows it instead of refused as a reply with nothing to answer, and its line says follow-up; nothing to redo"),
            (71, "2026-11-04", False, "a recruiter at a recruitment or staffing agency is no longer hidden from Messages because the agency clears none of your bar: the bar judges where you would work; an employer you named, and an in-house recruiter at one you turned down, still hold"),
            (72, "2026-11-04", False, "a short thank-you is no longer refused for sharing their name, their employer or thank with what they wrote, and a note naming no place is no longer warned that it named the wrong one"),
            (73, "2026-11-04", False, "nobody at their limit of unanswered messages, closed, set aside or gone cold is given a date by any writer (state.put_next), so a follow-up run never brings them back as owed; the check before anyone is shown reads their limit from the same place (state.at_limit); nothing to redo"),
            (74, "2026-11-05", False, "the networking skill and /network say the page looks at LinkedIn once a day and opens nothing by itself, with reading.py linkedin-check for whether today's look is due; nothing to redo"),
            (75, "2026-11-05", False, "the app skill and /reply say a draft is shown on the person's card in Contacts, and followup_drafts prints where; nothing made before changes"),
            (76, "2026-11-05", False, "a message in LinkedIn's download is matched to one already logged whatever its quote marks or dashes (curly or straight), so it is not logged again; copies an older import wrote are taken out by the export-repeats profile upgrade, statuses set again from the log"),
            (77, "2026-11-05", False, "a message the download shows was sent earlier in a day goes before a reply already logged that day, and the tidy puts a day an older import misordered in the order sent, so nobody reads as owed a reply they answered; a check that passed is said as the documents and their length alone"),
            (78, "2026-11-05", False, "a contact closed or cleared by hand parks their draft as the page's stop does; a draft written before their newest message is set aside and never offered; a thank-you to a kind close sets no follow-up; a pasted conversation logs only their messages; the person's own address never reads as a request; a message plainly not the draft teaches no edit"),
            (79, "2026-11-05", False, "several messages answering one of theirs count once toward the limit of unanswered messages, and a reply drafted to their message is logged as an answer, never a chase; a booked call can be not confirmed yet; a resume asked for over 60 days ago with nothing from them since closes by itself and the brief says so once; a no answer owed mark is dated no earlier than the message it answers; dates and lines are read again on the next run, so nothing needs redoing"),
            (80, "2026-11-05", False, "on a plan with InMail credits a people search decides by itself who is worth an InMail instead of a note (a recruiter or hiring leader at a target employer a request would reach badly, at most two a run, one credit kept back), keeps the note beside it to switch to, and asks for the balance LinkedIn shows once a week; nothing older needs redoing"),
            (81, "2026-11-05", False, "where someone lives is read from their profile as read when their row has none, so the person's own place rule holds every follow-up as it holds a first note: none is drafted for them, one written by hand is not kept, and the item says why once; held people come off the due list by themselves, so nothing older needs redoing"),
            (82, "2026-11-05", False, "LinkedIn's download finds someone already in the book by a message already logged, or by their first name with the surname in the record's id or notes, before listing them as new, and fills the employer, title and address the record lacks; a row closed as the same person as another gives it what it lacks (state.py same-person), and the check names two rows sharing one message; nothing older needs redoing"),
            (83, "2026-11-05", False, "export.py one-record joins two rows the message log shows are one person (one message, the same day and words, under exactly two rows and nothing on them saying two people) and fills a first-name-only row from the one connection that is them, each change written in the row's notes; the one-record upgrade does it for every older book by itself, so nothing needs redoing here"),
            (84, "2026-11-06", False, "the LinkedIn download is asked for weekly while the person has sent notes or messages in the last two weeks, every two weeks otherwise, or as they chose (EXPORT_REMIND: every two weeks, every month, or not at all), worked out once in export.every_days and said so in /network; put away from its trash, the next ask counts from that day; nothing older needs redoing"),
            (85, "2026-11-06", False, "a logged resume or letter is known by either order of its name (<Prefix>_<ABBR>_Resume, or <Prefix>_Resume_<ABBR> before); nothing older needs redoing"),
            (86, "2026-11-06", True, "a follow-up code cannot write goes to Claude after it looks for something new (their profile as read, news and roles at their employer, the person's own profile), never to the person as a question, and a question an older run asked is taken back; a rule about not repeating a message never switches plain follow-ups off; a plain follow-up varies its opener, greets a name with a leading initial by the given name and goes to Claude to fit the person's own message rules; a contact whose log holds only our request and their acceptance reads as connected"),
            (87, "2026-11-09", False, "someone waiting holds their employer by the person's follow-up rule from the last contact (or EMPLOYER_WAIT_DAYS), never a fixed 45 days from the first note, and with no date not at all"),
            (88, "2026-11-09", False, "who to write to is one call (candidates.py check): the search result's headline is filtered on the person's settings (a recruiter for another function is out), every list check runs at once, the per-employer limit included in the one surfacing check, and the list is ranked by who is likeliest to help and filled to the number asked, widening to more employers rather than padding; the InMail chooser picks only from what is known; LinkedIn is never fetched over the web and read only in the signed-in browser on the person's computer; a draft is held with state.py hold, never over another; the people already found need nothing redone"),
            (89, "2026-11-10", False, "someone waiting holds their employer for one follow-up wait from the last contact, a request nobody accepted no longer than the days to withdraw it, and a conversation with no answer in GONE_COLD_DAYS (90) is closed as gone cold by itself, recorded and opened again by a reply; a people run ranks the kind of reader who answers the person first, then a hiring signal in the headline, and fills with peers only once the hiring side at every employer has been tried, saying so; a headline that reads as selling is out; someone chosen stays chosen; someone an earlier run closed (not the person) is checked again; candidates.py order searches the employers with people known in the place first and skips one found empty there for 30 days; a run's time is split into searching and reading; the people already found need nothing redone"),
            (90, "2026-11-10", False, "a reply finished for the page's Chat says in one line that it is on their card, with an Updated in Contacts button opening it, and puts the draft in the thread only with --in-thread; a contact added or changed notes where it is, for the answer's button; nothing made before needs making again"),
            (91, "2026-11-10", False, "a chat with Claude's own browser on the person's computer does the whole networking run there, reading the short list itself and writing every note from what it read, never queuing the reads for a second chat; a run asked in a cloud chat while the computer is ready is sent there; notes already waiting on a read are still rewritten as before"),
            (92, "2026-11-10", False, "someone who offered to refer the person once a role comes up waits on hold until one is posted at their employer, with no draft on their card, and the referral ask is written then for that role; code no longer writes one follow-up on their offer for everyone; a draft that is another person's with the name and the employer swapped is refused (not_written_for_its_reader); a hold on a contact's row holds the follow-up due to them, and says the day it was made so a later message of theirs is still owed a reply"),
            (93, "2026-11-10", False, "who looks at LinkedIn's sign-in in each case (the page's daily look, a chat at work on the computer, one waiting on a sign-in) is one table in COMPUTER.md, which the networking skill points to"),
            (94, "2026-11-10", False, "a connection note LinkedIn's download lists again among the messages is never added beside the request already logged (nor a request beside the same note logged as a message), the download's copy of a message logged from its draft and edited before it went gives that row its words and day instead of a row of its own, and a tidy takes out a note's copy an older import added"),
            (95, "2026-11-10", False, "a first note to a decision-maker asks for a short chat about the work or a pointer to the right person, never whether anything is coming up, and offers no resume before they reply (both refused as asks for the job, unless the person's own TEMPLATES say them); the skill's table and the page's sample say the same"),
            (96, "2026-11-10", False, "a reply in a live thread loads no skill: reply.py prepare prints the guidance, the thread and the person's own rules, and finish holds the checks; the networking skill no longer triggers on a reply"),
            (97, "2026-11-11", False, "every networking date and default (the message log's commands, a note on a contact, a follow-up's due day, the download's checks, the reply and follow-up composers) counts the person's own day, never the computer's"),
            (98, "2026-11-11", False, "LinkedIn's download is matched to the book by each employer's own name (company_key.row_key), never a stored key an alias has since made stale, and an event's name is never taken for an employer"),
            (99, "2026-11-11", False, "a contact's follow-up cap and an application's have names of their own (schema.CONTACT_NUDGES, followups.APPLICATION_NUDGES), each bound once; MAX_NUDGES stays for callers"),
            (100, "2026-11-11", False, "the request caps the app never reads (connections_per_week, connections_per_day) are named in LINKEDIN_LIMITS and taken out by the linkedin-limits-ignored upgrade"),
            (101, "2026-11-11", False, "the LinkedIn limits are read again whenever the person's networking settings change (schema.limits_now), so a running process checks a note against the plan they have now"),
            (102, "2026-11-11", False, "compose brings its kind limits in line with the plan at every check, whatever reloaded the limits before"),
            (103, "2026-11-11", False, "a contact's next step reads plainly from the engine's own count: \"Sent 22 Oct, no reply yet: follow up after 14 days (one left), then stop\", and at the limit the page's own \"No reply to 2 messages: leave it unless they write back\"; the older wordings are still read as the app's own and rewritten"),
            (104, "2026-11-10", False, "a chat's judgement that an employer clears none of the bar holds its people back for 90 days from the day it was made (bar.JUDGED_NONE_DAYS), then the employer is judged again; one with no day holds nobody; the surfacing check reads it on its own day"),
            (105, "2026-11-11", False, "an earlier run's finding of no team at an employer is read on the person's own day, not the computer's"),
            (106, "2026-11-10", False, "the one check before anyone is shown reads the person's own quiet days after a message (networking.py QUIET_AFTER_SEND_DAYS; unset, nothing changes), and a rule in their instructions that runs a script of theirs instead is an upgrade; the view by employer groups the contacts with no employer recorded instead of passing them by; the people already found need nothing redone"),
            (107, "2026-11-10", False, "a connection note LinkedIn's download lists again among the messages is never added beside the request already logged (nor a request beside the same note logged as a message), the download's copy of a message logged from its draft and edited before it went gives that row its words and day instead of a row of its own, and a tidy takes out a note's copy an older import added"),
            (108, "2026-11-10", False, "a first note to a decision-maker asks for a short chat about the work or a pointer to the right person, never whether anything is coming up, and offers no resume before they reply (both refused as asks for the job, unless the person's own TEMPLATES say them); the skill's table and the page's sample say the same"),
            (109, "2026-11-10", False, "a reply in a live thread loads no skill: reply.py prepare prints the guidance, the thread and the person's own rules, and finish holds the checks; the networking skill no longer triggers on a reply"),
            (110, "2026-11-11", False, "every networking date and default (the message log's commands, a note on a contact, a follow-up's due day, the download's checks, the reply and follow-up composers) counts the person's own day, never the computer's"),
            (111, "2026-11-11", False, "LinkedIn's download is matched to the book by each employer's own name (company_key.row_key), never a stored key an alias has since made stale, and an event's name is never taken for an employer"),
            (112, "2026-11-11", False, "a contact's follow-up cap and an application's have names of their own (schema.CONTACT_NUDGES, followups.APPLICATION_NUDGES), each bound once; MAX_NUDGES stays for callers"),
            (113, "2026-11-11", False, "the request caps the app never reads (connections_per_week, connections_per_day) are named in LINKEDIN_LIMITS and taken out by the linkedin-limits-ignored upgrade"),
            (114, "2026-11-11", False, "the LinkedIn limits are read again whenever the person's networking settings change (schema.limits_now), so a running process checks a note against the plan they have now"),
            (115, "2026-11-11", False, "compose brings its kind limits in line with the plan at every check, whatever reloaded the limits before"),
            (116, "2026-11-11", False, "a contact's next step reads plainly from the engine's own count: \"Sent 22 Oct, no reply yet: follow up after 14 days (one left), then stop\", and at the limit the page's own \"No reply to 2 messages: leave it unless they write back\"; the older wordings are still read as the app's own and rewritten"),
            (117, "2026-11-11", False, "a request is never read as an edited copy of a message, and the import gives a logged message the download's words only where nothing of theirs sits between and the logged one has no exact copy of its own"),
            (118, "2026-11-11", False, "the swap check takes names, employers, role titles and links out before it counts the words, and compose.referral_ask takes line=, the sentence about the role written for its reader, and refuses an ask that is another's waiting draft swapped"),
            (119, "2026-11-11", False, "a first note's ask in the person's own words is theirs wherever they set it (OPENER, ASK, ABOUT_ME, TEMPLATES, an approved message), and a question about their plans (anything exciting coming up on the roadmap) is no job ask"),
            (120, "2026-11-11", False, "an employer whose name holds an event word (Summit Partners, The Conference Board) is kept from the download; only an event's own shape is refused"),
            (121, "2026-11-11", False, "the person's follow-up rule (FOLLOW_UP_DAYS, MAX_UNANSWERED and the follow-ups it leaves) is read again with the plan whenever their networking settings change"),
            (122, "2026-11-11", False, "a lint finding taken out of schema.limits_now; nothing changes"),
        ),
        "fingerprint": "24f3451b6e86f794",
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
            (35, "2026-10-26", False, "every file it writes has plain line ends on Windows too; a composed note's parts wait in this computer's ledger, never among the person's files, until a draft takes them"),
            (36, "2026-10-26", False, "the same checks on saving a note; the page flags a waiting draft that ignores or repeats the person's last message"),
            (37, "2026-10-29", False, "unused helpers removed (last_browser_read, reads_today); notes are written as before; a note waiting on a read is rewritten with every other read since Claude last ran, in one piece of work"),
            (38, "2026-11-03", False, "the person's own time zone and a place's are read the one way the whole app reads them (tools/person.py), from their own words, never from when their brief is scheduled; notes are written as before"),
            (39, "2026-11-05", False, "a profile read queued before midnight and made after it is kept, not refused as off today's list; notes are written as before"),
            (40, "2026-11-05", False, "reading.py linkedin-check says whether today's look at LinkedIn's sign-in is passed, signed-out or due, on the person's own day, and signin --page opens nothing once the day has passed; notes are written as before"),
            (41, "2026-11-05", False, "a note written keeps beside it what of the person's messages it answers, so one they send later sets it aside; notes are written as before"),
            (42, "2026-11-05", False, "a note to someone the person has already talked to (a follow-up or a reply) never opens on WAITS ON A READ, and a follow-up takes the place of a first note left marked from before the conversation"),
            (43, "2026-11-09", False, "the company limit counts someone waiting only by the person's follow-up rule from the last contact; a note with no date holds nothing"),
            (44, "2026-11-09", False, "a batch on the person's own approved recipe saves: the opening and closing lines of the notes they approved, every variant, and any shape two of them share are theirs to repeat; a profile read takes its Experience page too where LinkedIn's newer layout keeps it apart; place-ids keeps a place's location number; notes already saved need nothing redone"),
            (45, "2026-11-10", False, "the company limit frees an employer one follow-up wait after the last contact; today's short list is kept on the person's own day and a removal takes off that one alone; reading.py batch checks the run's own notes against the whole queue and says only what involves them; notes are written as before"),
            (46, "2026-11-10", False, "a profile whose roles are grouped under one employer, with a place or a kind of work under its name instead of the time there, keeps that employer as theirs: the first role's title was read as the employer and someone still there was skipped as having moved on"),
            (47, "2026-11-10", False, "someone whose thread the follow-up rule has closed (two unanswered messages from you) no longer counts towards their employer's limit, so the next person there is not held until somebody replies"),
            (48, "2026-11-10", False, "on the person's computer each note is written from the profile read in that same run, never saved to wait on a read; nothing written before needs writing again"),
            (49, "2026-11-10", False, "a read is dated, and today's short list looked for, on the person's own day, never the computer's, which in a far time zone is a day off; notes are written as before"),
            (50, "2026-11-10", False, "a 429 page and what reading.py page sees stop the day's reads; signed out is judged on the address, bar and top card only; a chat the app started on the computer puts a sign-in on the page instead of asking in its chat, and waits for it one fresh look every three minutes"),
            (51, "2026-11-10", False, "after a gap longer than its hold on the work, a chat the app started on the computer reads nobody more until the work is read again: still its own, it carries on; taken or ended, it stops"),
            (52, "2026-11-11", False, "a note saved past the usual number at an employer, on the person's word, says how many with it, the usual number and their own number there"),
            (53, "2026-11-11", False, "a message log that cannot be read refuses the per-employer limit in plain words: the short list adds nobody at an employer and saving notes saves nothing until it can be read"),
            (54, "2026-11-10", False, "a grouped Experience reads a title with commas, a bare work mode and the group's own place, and an employer that reads like a job title keeps the contact with a caution, never a skip for having moved on; only the contact's own dated posts ground a note or a verdict, never another's post, a reaction, a repost or an undated item; a read keeps its page text, `reading.py reparse` reads a misread profile again from it, and a read fills its contact's blank employer; the short list names who it leaves out; notes already written keep theirs"),
            (55, "2026-11-10", False, "a read waits for its claim to be checked after a gap counted from the claim or its last pin, on the work the chat holds now; a chat whose work is done holds nothing, and asks for a sign-in in the chat again"),
            (56, "2026-11-10", False, "every sign-in seen in a chat the app started on the computer (signin --page, --done, --url) names the step that sends its parked job back to work"),
            (57, "2026-11-10", False, "an HTTP error page (999, 429) is judged on the page's head alone, so an error number in someone's About is no stop"),
            (58, "2026-11-10", False, "a profile read in a chat of a person whom work waiting on the page reads is refused until that work is taken into the chat, so nobody is read twice; the chat that claimed or took the work, and work that has ended, refuse nothing; a number the person gave for one employer (more-at --up-to) is obeyed, a lower one included, and only Open it now's room is never below their usual number"),
        ),
        "fingerprint": "1b04cb5fe13ae193",
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
            (31, "2026-10-26", False, "the seen-jobs file's reader and writer and the status spellings have public names the page's engine calls (exclude.load_seen, save_seen, reason_group, throttle.spellings); nothing screened differently; every file it writes has plain line ends on Windows too"),
            (32, "2026-10-26", True, "bar.py lists the employers of people with a follow-up owed that nobody has judged (unjudged --contacts), for the brief to judge once; money about the employer (revenue, funding, valuation) is never pay, and a single labelled figure in the person's currency is read"),
            (33, "2026-10-29", False, "an unused helper removed from the free filters; screening is as before"),
            (34, "2026-10-29", False, "a ruling on a remote posting holds for the same role on another board, whichever place that board names, except a ruling on where the posting is, which holds only for that place; and a posting read without its place is ruled out exactly when it would be with it"),
            (35, "2026-11-03", False, "the search window holds for an employer's own board as for every other source, read from the posting's own date where the board gives one; nothing ruled out before needs looking at again"),
            (36, "2026-11-03", False, "the bar reads a public body its names miss from its own posting (\"is a provincial agency\", \"an agency of the Government of\"), where the profile excludes public bodies, so it is cut before the shortlist like one named; the paid exception holds; only the employer saying it of itself counts (\"We are a\", \"<employer> is a\", \"join the ... Public Service\"), never a client or a regulator the posting names, and only for an employer on none of the lists and judged by nobody"),
            (37, "2026-11-03", False, "a posting that only names the person's skills no longer scores 100: above 90 a point counts half and the posting alone stops at 98, so the top of a ranking tells rows apart; a live contact or an earlier interview still reaches 100; scores of 90 or under are unchanged; a years bar stated per degree is read for the degree held; an employer that clears none of the bar waits on the person before drafting; the pay answer on the form moves with the posting's own range; the search window is any whole number of days the person sets, not only 7, 14 or 30; a role applied to that went quiet is never surfaced again; a public body counts as paid only when the bottom of its stated range reaches the target, and gets no lift from an employer tier; a posting the person cleared stays cleared under every copy of it; a reply recorded as parked or no way in is not a warm route; a skill held under another name is never a near match; a bar of pay, prestige or signal applies only where the person's own profile states one (an employer tier or a frontier list), never because a chat judged an employer, and with none no employer is judged or ruled out for it; every language the person does not hold is a cut, in English or the posting's own words, and a title in one; pay, years, terms and degrees are read in German, French, Spanish, Portuguese, Italian, Dutch, Polish and Swedish; pay by the month is read as twelve months, and a pay ruling made on a monthly band is released by itself"),
            (38, "2026-11-04", False, "the staffing-agency test is one named reading of the person's agency lists; screening is as before"),
            (39, "2026-11-05", False, "a job title written in two languages (\"Data Analyst // Analyste de données\") is in the one you work in: the title gate and the screen no longer cut it as the other, and whether that language is required is read from the posting; a ruling made on such a title is released by itself, and the title gate's drops are decided again on every round, so nothing needs redoing; a kind of employer you ruled out can be turned back on from Your rules (search.py BAR_EXCLUDED_OFF)"),
            (40, "2026-11-05", False, "a referral in progress keeps its employer's roles in the filter before scoring as in the throttle, one rule for both (throttle.employer_stops), each carrying a note never to apply cold; a skip for it was never kept, so nothing needs redoing"),
            (41, "2026-11-05", False, "a live contact or an earlier interview is counted before the top of the scale, not added after it, so the strong roles at one employer keep their order instead of all reading 100; nothing is screened differently"),
            (42, "2026-11-09", False, "a do-not-target entry with no review day stops 90 days after it was recorded, and with no date at all holds nothing; an application with no date holds its employer back for no time"),
            (43, "2026-11-11", False, "a function only a test called is retired (text_screen.other_language_named); nothing screened changes"),
            (44, "2026-11-11", False, "the throttle counts the person's own day, never the computer's, for a wait and an application's age"),
            (45, "2026-11-11", False, "a reply makes an employer a warm route while it is recent (45 days), while its record says what it is for, or whatever its age where a referral is in flight or a call booked; an old reply with nothing recorded adds no points and no DO NOT APPLY COLD"),
            (46, "2026-11-11", False, "one rule for who is a way in (throttle.route_rows), which the brief reads too; a referral in flight recorded on the row is a route whatever the log's reading"),
            (47, "2026-11-10", False, "a chat's judgement that an employer clears none of the bar cuts its jobs for 90 days from the day it was made (bar.JUDGED_NONE_DAYS), then the employer is judged again before anything is cut for it; one with no day cuts nothing; a round reads it on its own day; nothing needs redoing"),
            (48, "2026-11-10", False, "Look again now under Held back for now takes back a chat's judgement that an employer clears none of the bar (bar.unjudge), so it is judged again; nothing is screened differently"),
            (49, "2026-11-11", False, "what the search holds back is counted on the person's own day, never the computer's: a do-not-target entry's review day, an application's wait, the relist window, a past deadline and the day a ruling or a judgement is dated; nothing needs redoing"),
            (50, "2026-11-11", False, "the employers judged against the bar are read again whenever their file changes, by its time and its size, so a judgement taken back in another chat is never read as still there"),
            (51, "2026-11-11", False, "a note in the code says why a second posting with the same title, employer and city, seen while the first is listed, is read as its copy; nothing is screened differently"),
            (52, "2026-11-11", False, "a posting skipped as the role already applied to is decided from the tracker's current row every round, never kept out by the old skip, so a row put right in the tracker brings it back; nothing needs redoing"),
            (53, "2026-11-11", False, "a role the person set aside holds for about six months (exclude.SET_ASIDE_DAYS, search.py SET_ASIDE_DAYS), for good only where their own words say so (never, at all, no more ... ever), then is shown once more, marked with the day and their reason, and its ruling lifted; nothing needs redoing: older rulings end from the day they were made"),
            (54, "2026-11-11", False, "an employer's name is looked for only where the text holds it, the same verdicts made much faster"),
            (55, "2026-11-10", False, "C++, C# and C in a job title are three roles: an application, a ruling or a sighting of one no longer stands for another at the same employer; rulings are read from their titles each round, so nothing needs looking at again"),
            (56, "2026-11-11", False, "rank.md names the page fetcher for a posting a 403 refused (tools/fetch_page.py); a draft a chat stopped because the job is not one the person can take holds that posting alone, as a role they set aside does (about six months, then shown once more), never judged again against the rules"),
        ),
        "fingerprint": "174e7be1f1930e6e",
    },
    "routines": {
        "by": "you", "priority": 3, "applies": "routines",
        "gives": "your scheduled tasks set up the current way",
        "run": "automation/README.md, for the tasks a newer version adds or changes",
        "ask": "The app's scheduled tasks have changed. Shall I set yours up the new way?",
        "files": ("automation/README.md", "tools/routines.py", "tools/tidy.py"),
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
            (10, "2026-10-26", False, "at_most_daily is public; the page moves the brief and takes a break through move, pause and resume, the one break the search has; every file it writes has plain line ends on Windows too"),
            (11, "2026-10-29", False, "the brief is on from the start: set-up turns it on with no question, every day at 7:38, and a copy set up before with none gets it (profile upgrade brief-daily); the bell on the Brief, or Settings, changes it or turns it off; it runs in the chat that answers the page, so no chat is made for it; off and on keep its days and time; a brief that already runs keeps its schedule, and one in a chat of its own from before moves into the page's chat by itself (tools/tidy.py); a brief never makes a chat, and from a chat on the computer it is turned on from the bell, which runs it in the cloud; the app's settings squeeze every chat's history at 200,000 tokens, so the long-lived chat stays cheap"),
            (12, "2026-10-29", False, "chats keep the model's whole window again: the 200,000-token cap made a chat forget its work every few steps, so the app sets nothing and the security guard refuses the cap"),
            (13, "2026-10-30", False, "the brief can move to another time zone from the page, and every scheduled task keeps its clock time there"),
            (14, "2026-10-31", False, "a brief in the older ops chat moves into the page's chat by itself once that chat is gone (the task had been waking a new empty chat with no copy of the files every morning); a brief back from a break runs in the ops chat, never a new empty one; a brief bound to a chat with a copy of the files is never moved, a moved one follows a new helper, and a time zone move owes an update for every task, not only the last"),
            (15, "2026-10-31", False, "a brief's stored prompt says how to get a copy of the files when its chat has none, so it runs in any chat it lands in; the day's tidy-up gives an older stored brief that line, once"),
            (16, "2026-11-02", False, "a silent daily upkeep where the brief does not run every day, made and kept bound to the chat that answers the page by the daily tidy-up; a brief or upkeep moved off the helper that chat replaced is deleted there, not left turned off"),
            (17, "2026-11-02", False, "the cost note says what the news costs now: the smallest model, six searches at most, the slow ones weekly"),
            (18, "2026-11-02", False, "the brief searches what the person's own list watches (person.json brief.watch) and the employers in play, no fixed kinds of news; it republishes the page when an update changed the page's code, and asks for the watch list where none is written"),
            (19, "2026-11-03", False, "the brief stays bound to the chat that holds the copy, where it works: never made, moved or brought back from a break as a task that starts a new chat each run, and a working brief is never moved by the day's tidy-up (only one whose chat is deleted or a retired helper, and the shortlist with it); a brief bound to a chat sends its headline as a push at the end of each run, asked by brief.py alone, and where it was not sent the next message in that chat says so once; the line that sets it up says where and when it comes, with or without a page, and 5:38 where 7:38 falls in the scheduler's slow hours; a break whose day has passed, a zone this computer does not know and a brief that did not come are mended at any start, wake or brief; every task the app made gets the line for its files from any chat; run chats are remembered and tidied; the silent upkeep runs only on the brief's off days and needs no push in a routine's set-up; one setup reminder a day after the page goes up while setup waits; the tidy-up puts away only a chat the app started, never one you write in, and brings back once a chat of yours it put away before; a brief that did not come is judged by the page's own clock"),
            (20, "2026-11-04", False, "a brief whose chat cannot open the files (its task fired and left no record of that day's brief, or it now wakes another chat) is said plainly, never as set up, with the calls that move it into the chat that answers the page"),
            (21, "2026-11-04", False, "the page is told whether the brief\'s own run sends its phone notification, so Settings offers that choice only there"),
            (22, "2026-11-04", False, "the chat of a big job (an interview prep, a search, a batch of drafts) is put away soon after its job ends, not after two quiet days: the tidy-up is due again when such a job finishes, and archives its chat once its work is saved; a helper the page was taken from is renamed to finishing up at once and archived at the next check-in"),
            (23, "2026-11-05", False, "a big job's chat reports back to the chat that started it once its work is on master, and that chat puts the results on the page and archives it at once (tidy.py close and closed), the daily tidy-up kept for one that never reported; the tidy-up keeps each archived chat's real title itself, never through the shell, judges a chat it put away before by the title it has now, never brings one back for an empty stored title, and puts away again one of the app's chats an older tidy-up brought back by mistake; the live page helper is called Job search page, every older helper (Job search helper, finishing up) is put away as soon as its work is on master, never kept for being used lately, the brief moved into the live helper first (made, recorded, the old one turned off) and a chat holding a brief that is off kept for it; the first tidy-up after this update runs even if the day's already ran, so the helpers left over from before go by themselves; after a hand-over the tidy-up runs at once and again half an hour on, for a day, while the old helper still runs or holds unsaved work"),
            (24, "2026-11-05", False, "the tidy-up never puts away a chat still at work: running or working by the sessions list's status or get_session's (a listing trimmed to status is read), an old helper used in the last ten minutes or waiting on the person, any task that is on firing into it (a one-time reminder as much as the brief) unless this same tidy-up moves that task, or a branch GitHub does not hold yet while it was used in the last two days; a brief bound to a chat kept for any of these stays where it is"),
            (25, "2026-11-05", False, "a chat you started yourself is never put away by the tidy-up, whatever its title; a brief whose task still runs in the helper a hand-over replaced moves into the live helper, and that old helper is put away"),
            (26, "2026-11-05", False, "after a hand-over the live helper asks for its own check-in half an hour on while the helper it replaced is still finishing, so that one is put away that day, not the next morning; an archive that is refused is tried again at that check-in and never handed to the person"),
            (27, "2026-11-05", False, "a scheduled task the app prints carries no connectors field, which some organizations refuse"),
            (28, "2026-11-05", False, "the tidy-up run from a folder read before this chat took the page over goes by the take-over this chat recorded, so the brief moves into this chat and never into the helper it replaced"),
            (29, "2026-11-05", False, "a page helper renews only near the most a chat can hold or after a day with nothing to answer, never in its first hour or while its own hand-over is open; the helper it replaced is put away at once once get_session calls it idle, and its brief moves into the live helper in that same pass"),
            (30, "2026-11-05", False, "a tidy-up check-in that fires in a chat which has handed the page on does nothing; the chat that answers tidies every old helper and the brief at its own take-over"),
            (31, "2026-11-05", False, "the tidy-up takes the chat and task listings in one JSON object on standard input, as the tools returned them, never typed into files"),
            (32, "2026-11-05", False, "a helper that can make no scheduled task (chats nested too deep) leaves the brief and its chat where they are for the fresh helper to move, and every task call the tidy-up prints says what to do when it is refused so"),
            (33, "2026-11-05", False, "where the brief runs is read from the task listing, never the registry: a brief the registry already named the helper for, still firing in the old chat, is moved, and the plan says where it fires so a move is reported only once the listing shows it"),
            (34, "2026-11-05", False, "routines.py brief and the tidy-up check that the brief's task fires in the chat answering the page, and print the move where it still fires in a chat that handed the page on, never \"set up\" or \"nothing to tidy\" over it"),
            (35, "2026-11-05", False, "the tidy-up knows a page helper by the page's own record of the chats that answered it as one, however it was started and whatever it is called: a finished old helper the person started from the page is put away, the live one kept"),
            (36, "2026-11-05", False, "the daily tidy clears the page's open rings every day, not once, so none stay unread in the Claude app"),
            (37, "2026-11-06", False, "a brief time the person picks is kept to the minute, 8:00 stays 8:00; only the app's own default is moved off the hour, recorded beside what it stood for (record --asked) and said in one line; what the scheduler reports of a late start (next_run_at, the last fired time) is kept from the task listing by routines.py brief and the daily tidy-up so the page shows the real time; a brief made before keeps its schedule and is read the same way; where both earlier times fall in the slow hours (Alaska, 9:38) the line says later than 8:00, never earlier"),
            (38, "2026-11-06", False, "a hand-over from an earlier day in the person's own zone no longer holds the next day's fresh helper: an old helper put away by hand left the hand-over open, and the first page update of the morning asked for no fresh helper"),
            (39, "2026-11-06", False, "a finished job chat whose work never reached GitHub is asked once to save it (land.py --keep), and if it still is not there its work's own card says plainly that it was lost, with Try again, once, and the chat is put away; it no longer sits in the list with nothing said"),
            (40, "2026-11-07", False, "after a hand-over the new page helper comes back half an hour on whenever it kept the old one, for any reason: one kept because git could not yet say its save was on master stayed in the list all day"),
            (41, "2026-11-09", False, "tidying reads chats' details however they arrive (a plain list was dropped, so the same chats were asked for again), and every chat the app starts asks for Auto"),
            (42, "2026-11-09", False, "the chats the app starts on your computer, \"Job search \u00b7 <job> \u00b7 <computer>\", are known as the app's by the daily tidy-up"),
            (43, "2026-11-10", False, "the brief runs in a chat of its own, made with create_session and the copy attached, never bound to the chat that answers the page nor carried from helper to helper; the daily tidy-up makes that chat again where it is gone, archived or approved computer access; the setup reminder gets a chat of its own too, and no helper sets itself a reminder (the brief-own-chat upgrade moves an existing brief)"),
            (44, "2026-11-10", False, "the brief's run starts the fresh page helper itself when the helper's day is up or work waits that no chat is awake to take, and routes work for the computer; one small chat of its own, \"Job search: starts chats on your computer\", holds the computer approval and starts and puts away the chats there, woken by republishing its bell page, so a helper never approves and archives itself as designed; a computer job stopped at the LinkedIn sign-in has its chat put away at once and starts again only once the person answers; a sign-in that did not last says to keep the sign-in, and a signed-out LinkedIn leads the brief"),
            (45, "2026-11-10", False, "a big job's chat puts itself away once its work is saved and nothing else waits; the tidy-up reads the page again for a job its folder does not hold, never keeping a finished chat a day for an old read"),
            (46, "2026-11-10", False, "the tidy-up never asks a job chat on the person's computer to save, nor says its work lost, while its branch has not reached GitHub: the computer starter brings it in"),
            (47, "2026-11-10", False, "a chat archived already is never archived again; the helper just taken over from is judged even when the list of chats lacks it; the daily tidy-up deletes a brief task off for over a week that another replaced, and turns off a one-off a day past its time and a task bound to the chat that approved computer access whose last run failed"),
            (48, "2026-11-10", False, "a finished job's chat is judged from one fresh read of the page, never asked to read again when the page no longer holds its work item; the docs say a job's chat puts itself away"),
            (49, "2026-11-10", False, "a chat of the app's archived by itself, another chat or by hand is recorded as put away by the next tidy-up, so the tidy-up rests and Undo can bring it back"),
            (50, "2026-11-10", False, "the brief keeps the chat made for it: record --own-chat names it in every set-up and leaves the old relay and ops chat where nothing else uses them, a later record never drops it, the tidy-up records a chat made for the brief that its task already fires in rather than making another, a chat missing from a listing is read with get_session before it is called gone, and routines.py check --triggers fails a brief that fires in a chat the registry does not name"),
            (51, "2026-11-10", False, "a brief that did not come is judged by the records on the saved copy, so a record written and never saved no longer passes"),
            (52, "2026-11-10", False, "where the person's notes on their automation name another time for the brief than its task runs at, routines.py check notes it and the brief asks them once which they want"),
            (53, "2026-11-10", False, "right after a hand-over the helper taken over from is judged from one get_session of it (tidy.py retire), never the whole listing typed back by hand"),
            (54, "2026-11-10", False, "a chat that handed the page on is never recorded as the brief's own: a brief still firing there moves into a chat of its own"),
            (55, "2026-11-10", False, "once the brief's chat holds more than 250,000 tokens the run gives the brief a fresh chat of its own (routines.py fresh), and the Cost section says what a run costs"),
            (56, "2026-11-10", False, "the day's tidy-up is marked on the page (meta/tidy) as well as in the container, so a chat in a fresh container does not run it again"),
            (57, "2026-11-10", False, "docs corrected: the README's test of a task takes its one-off task away and makes it only in the task's own chat"),
            (58, "2026-11-11", False, "the daily tidy-up reads one-off tasks that have fired too (include_completed) and deletes the app's own a week after they fired"),
            (59, "2026-11-10", False, "the tidy-up counts a job to the job chat that ran it, so a finished job chat is put away and its unsaved work looked for"),
            (60, "2026-11-10", False, "a finished job chat asked to save its work is asked by one message and answers by none: the next tidy-up finds the work saved or says it was lost"),
            (61, "2026-11-11", False, "the day's tidy of old chats is said on the page, so a chat starting fresh does not tidy again what another did that day"),
            (62, "2026-11-10", False, "a chat archived already is never archived again; the helper just taken over from is judged even when the list of chats lacks it; the daily tidy-up deletes a brief task off for over a week that another replaced, and turns off a one-off a day past its time and a task bound to the chat that approved computer access whose last run failed"),
            (63, "2026-11-10", False, "a finished job's chat is judged from one fresh read of the page, never asked to read again when the page no longer holds its work item; the docs say a job's chat puts itself away"),
            (64, "2026-11-10", False, "a chat of the app's archived by itself, another chat or by hand is recorded as put away by the next tidy-up, so the tidy-up rests and Undo can bring it back"),
            (65, "2026-11-10", False, "the brief keeps the chat made for it: record --own-chat names it in every set-up and leaves the old relay and ops chat where nothing else uses them, a later record never drops it, the tidy-up records a chat made for the brief that its task already fires in rather than making another, a chat missing from a listing is read with get_session before it is called gone, and routines.py check --triggers fails a brief that fires in a chat the registry does not name"),
            (66, "2026-11-10", False, "a brief that did not come is judged by the records on the saved copy, so a record written and never saved no longer passes"),
            (67, "2026-11-10", False, "where the person's notes on their automation name another time for the brief than its task runs at, routines.py check notes it and the brief asks them once which they want"),
            (68, "2026-11-10", False, "right after a hand-over the helper taken over from is judged from one get_session of it (tidy.py retire), never the whole listing typed back by hand"),
            (69, "2026-11-10", False, "a chat that handed the page on is never recorded as the brief's own: a brief still firing there moves into a chat of its own"),
            (70, "2026-11-10", False, "once the brief's chat holds more than 250,000 tokens the run gives the brief a fresh chat of its own (routines.py fresh), and the Cost section says what a run costs"),
            (71, "2026-11-10", False, "the day's tidy-up is marked on the page (meta/tidy) as well as in the container, so a chat in a fresh container does not run it again"),
            (72, "2026-11-10", False, "docs corrected: the README's test of a task takes its one-off task away and makes it only in the task's own chat"),
            (73, "2026-11-11", False, "the daily tidy-up reads one-off tasks that have fired too (include_completed) and deletes the app's own a week after they fired"),
            (74, "2026-11-11", False, "the daily clean-up acts only on this copy's own app tasks (their prompt names this copy), and asks for tasks that have fired once a week"),
            (75, "2026-11-11", False, "the helper taken over from puts itself away (only it can see whether its work reached GitHub): the new helper records it once archived, records a deleted one as gone, and archives it only after a day of quiet; a kept one is asked about again half an hour on"),
            (76, "2026-11-11", False, "only this copy's chats found archived are recorded as put away (the helper taken over from, the page's job chats and helpers, or one of this copy used within the week)"),
            (77, "2026-11-11", False, "closing a job's chat keeps one still running or holding any item it claimed that has not ended, whatever work id it was given"),
            (78, "2026-11-11", False, "only clock times are read from the person's notes (07:56, 8am), never a release number or a price"),
            (79, "2026-11-11", False, "the brief starts its fresh chat before the landing (so the registry it changes is saved), and never within three levels of how deep chats go"),
            (80, "2026-11-11", False, "a task listing that does not say whether a task is on reads it as unknown, never on: nothing is changed on such a task"),
            (81, "2026-11-11", False, "only the tasks this copy's registry names are given the line that gets the files, never another copy's"),
            (82, "2026-11-11", False, "an old registry is rewritten: the upgrade is due for the older ops shape until a listing is read, a chat titled for the brief with this copy is adopted whatever its exact words (routines.py adopt), and a brief still relaying from the ops chat is noted"),
            (83, "2026-11-10", False, "the tidy-up counts a job to the job chat that ran it, so a finished job chat is put away and its unsaved work looked for"),
            (84, "2026-11-10", False, "a finished job chat asked to save its work is asked by one message and answers by none: the next tidy-up finds the work saved or says it was lost"),
            (85, "2026-11-10", False, "a job chat that stopped on a question to you counts as finished for the tidy-up while the question waits and after your answer; a job chat that reports one job while blocked part way through another it runs is kept, never put away at work; asking routines.py for help never changes the registry"),
        ),
        "fingerprint": "edd785189717635f",
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
            (3, "2026-10-26", True, "the page in the rosé pine colours on the layout spec: one summary and one row of controls a screen, every tap sent in the engine's own shape with its item's rev, the engine's stage and cost tables embedded, links only by the engine's own; outcomes, replies, calls and referrals on the page; message cards with copy, counts, open and I sent it; waves; the item view; the LinkedIn download and profile reading; where Claude works, your search, your brief, and the one listener; the work list knows the republish kind; the page's accent is rose pine's lilac, its cards sit closer together, and the morning brief is one line per item with its extra lines opening in place"),
            (4, "2026-10-26", True, "To do groups follow-ups, unsent-note checks and repeated warnings into checklist cards, hides follow-ups at employers turned down, questions from updates move to Settings; a cost is a gauge; a reason sits behind a question mark; quiet counts on Jobs, Drafts and Interviews; Find jobs and Find people head their sections; a bin on each job asks why; Add a job links who sent it and can draft straight after; Progress opens on the last 30 days; Drafts keeps only what is still to send; Tweak is a pencil on the card; work not yet picked up says waiting and can be called off; the tour names Find jobs, the bin, They sent me a job, Find people and Chat's screenshots; Jobs' first tab is Not applied yet and each card says whether the posting is still open; a Chat button bottom right opens the same conversation from any section; the chat takes pictures (paste, drop or add) and says what it can do, with starters that fit the person; Contacts has Got a message?; detail views styled as screens of their own; Applied lists only what was sent; a request nobody accepted offers no follow-up; a contact whose note is written has See the note; days late counted from the due date everywhere; waiting work has no spinner; a cog for Settings; secondary buttons keep an edge in the dark; Add a job asks the day only when you applied; a section too big for one record arrives in parts and is joined whole; on a phone the Chat button is a small round icon; an unaccepted connection request is said plainly on its row"),
            (5, "2026-10-29", True, "the page wakes its one helper chat by itself (and starts one fresh only when that chat is gone), so work no longer waits for a press and no chat is made per task; queued work it has asked for says Starting, running work has a Stop button, late work offers Ask Claude again, and finished work says so on screen with See it; Settings opens on Your profile (jobs, skills, education, certificates and your resume) with add, change and take off, each one change made by Claude, and To do asks to finish a thin profile; a walkthrough opens each section in turn, skippable a step at a time or all at once, offered once and from a ? on every section, and the chat answers how-to questions with Show me; on a phone Chat is the tab alone; empty sections say what they are for and offer the next step; a sent message cannot go twice and shows Claude typing; an interview's prep is on the page itself, with Read your prep in place of Practice questions; Contacts filter by who they are and search by name or employer; Side by side is gone; stopped work folds away after two minutes and Nudge reads Follow up with; the light theme is cooler; on a computer with a mouse the page is sized like the Claude app's own text; a phone fits more (tighter cards, one-column jobs) and Settings has a Size for the device; taps close together wake Claude once; a question from running work can be answered on the page; the buttons the engine refused (search changes, Yes I applied, pasted profiles, keep waiting) work"),
            (6, "2026-10-29", True, "a Brief page is the home screen (today, the next three steps, who is waiting by name, the best new jobs, news, numbers and a tip, on one laptop screen); seven places instead of eight (Drafts and Applied inside Jobs, messages inside Contacts, numbers on the Brief); To do starts with five; Contacts opens on who needs you; Your profile is its own page from Settings; Settings is regrouped with how the app runs folded; names open the person and a bin offers the usual choices; more job filters; Add a job takes a typed name; calmer draft cards; the prep reads as a document beside what was sent; three sizes, Standard the old Small and Larger the old Standard; the light look is as light as Claude's; every record the page writes carries its version and the busiest live under new names; the page is published without comments; no chat is ever started for the page; To do is today first (five, then Show N more, then Coming up) with one count everywhere and each card opening its own job or person; Contacts folds who owes nothing below who needs you; a phone is drawn smaller with full-size tap areas and buttons drawn the size of their words; jobs sort by their number, with a hover saying what it means; a question mark follows its last word, three at most a screen; a bell on the Brief turns the brief on, off or to other days through the same sheet as Settings; waiting work says it waits its turn in the same chat, and an update shows as a moving line under the header; each bin choice does what it says (an employer not wanted any more closes everyone there not yet written to and turns it down by name; in touch another way keeps the route and sets the note aside); the Where long tasks run setting is gone, work going to the chat that answers the page; a brief asked for from a page answered on the computer goes to the cloud and opens the helper in the same tap; tips and the Brief's next steps name the page's buttons; bringing old chats back and pinning the page are buttons; LinkedIn profiles read by the page itself in the desktop app (a profile and its Experience, Education and activity pages), Write my notes after a batch, I paste them as a setting, big jobs side by side, a big LinkedIn download sent in parts; on an iPhone the tweak panel opens at full size (it opened 2px tall), and the filter footer no longer reads null; on a laptop the filter panel opens under its button in every browser; focus goes back to the button after a panel closes on an updated page"),
            (7, "2026-10-29", True, "finished work says Done with no bar and folds itself away a minute later; Find jobs and Find people turn into what is going while a run is, so a second tap shows the work instead of starting another; Find people takes a note in your own words, as Find jobs does; each screen says when Claude is working on it; a bin on a job or draft is a row of short choices with Too old, and only No more from an employer turns that employer down; the bin on a To do row takes the row away as it is chosen; Contacts counts as needing you only who does, with follow-ups you could send counted apart; the progress bar's shine glides; slow work says it is taking longer than usual and that Claude is still on it, never Stalled or the usage limit; a search is timed by how long its job sites say is left; the usage limit shows only when Claude says so, and Try again only when the work has stopped; work asked for in a chat shows as Claude is busy in your chat; once the job sites are done, a search says which step it is on instead of a time left; the bin on a To do row hides only what the chat will close, so a reply you are owed stays; an interview ended on the page shows again when a chat books a new stage; screen readers hear the label before a fix or a suggestion"),
            (8, "2026-10-30", True, "no write to the page asks a person: its files are named so Claude Code never reads them as a disguised short name; work Claude has picked up says Starting, and the step it is on has a clock in seconds that ticks on the page; slow work shows how long it has run with no words about being slow; a finished job's summary is one short sentence, with a bin that puts it away; the resume card says one thing to do; like items in To do are one checklist card, five shown and the rest one tap below, and people who have not answered two messages are closed rather than drafted to; the News card says when it was gathered; LinkedIn is checked quietly once a week on a computer where it works, its sign-in page opens by itself when it does not, and the page says the tab can be closed; the line after an update gives the page's link, a chat with the update takes the page from a chat quiet for an hour, and publishing closes the request still waiting; Find jobs and Find people ask how many, a few by default; drafts asked together run as one job; Tweak is Edit; the Brief opens on points with whole news and labelled bars; Contacts say who someone came through; Settings show lists as chips, a time picker and an editable time zone, what each Left out rule left out, and no Undo in What's new; stopped work can be put away; a long prep scrolls on a phone; the chat that answers the page renews itself daily; the page offers to pin itself on the Brief and while the first search runs, a Not now coming back a month later and three answers the last; tips are said in plain words"),
            (9, "2026-10-30", False, "the Brief's numbers grow to fit, so How far they got and Since the last brief are never cut off; a tip from an older version starts with a capital"),
            (10, "2026-10-31", False, "a control or card fades only under the pointer: Safari faded every button a section drew in from the text colour"),
            (11, "2026-10-31", False, "Refresh asks Claude to bring the page up to date instead of reloading the same data; the work pill opens Claude's work on the Brief; the time a job has run counts from its start; each week of the Brief's chart says its count; News reads in points; What's new links every change; work answered or waiting on a starting helper says so; the resume for no job in particular is linked from every Jobs tab and offered when there is none"),
            (12, "2026-11-01", False, "a second ask soon after the first rings Claude too, instead of being folded into the first ring"),
            (13, "2026-11-02", True, "Coming up: everything booked or due in one place by day (interview stages, tests due, calls booked, the closing day of anything drafted and not sent, and anything you add yourself), each into Google Calendar, Outlook, Apple Calendar or any other app with its calendar-with-a-plus and nothing connected, an interview's title opening its prep, with an Interviews view of each card; the Brief says each thing once (Today the interview this week with its prep and likely questions, then Coming up, Next three, Waiting on you, Jobs, the news and your numbers, each leaving out what another shows), fits one laptop screen with lists that grow or shrink to the room, and reads in the order a day is acted on on a phone; a call's time shows on the person; old news no longer promises a next brief; an icon-only button says what it does under the pointer; a free day on the Brief's two weeks adds something to it"),
            (14, "2026-11-02", True, "Edit the brief shows and changes what the news watches; Settings has when the next interview leads the Brief and when calendar reminders come; the strip's day letters follow the person's language; an open page checks for new data when it is looked at again, and reloads itself to a newer version; Refresh asks Claude only for data older than today, shows what that costs, and is a soft button where it shows; Today leads with what is on today, and the strip marks today red and tomorrow amber; fitting the Brief to the window takes the item whose going saves most, never one beside white space, and keeps Today two questions; each person's next step and its day sit in one column; the brief's opening section shows; Edit the brief can watch again what was stopped; day names that would repeat use the language's short form"),
            (15, "2026-11-02", True, "today and tomorrow stand out in a clear green and gold on the strip and on Coming up's day headings, never red"),
            (16, "2026-11-02", True, "the News panel is never empty while a recent brief had news, and each point says what happened, how to use it and where it is from; Today is the most pressing thing with what matters about it beside it; Coming up lists what is due next when nothing else is booked; a person is shown once; the update line glides"),
            (17, "2026-11-03", True, "a message to Claude that fails on an old thread goes again on a fresh one, and anything not sent goes with the next tap, so nothing waits for next time and there is no Ask Claude again; work says Not sent yet, Waking Claude with its clock, or No answer yet; a request typed in Chat goes to Claude in the same tap; a pasted message is always saved and sent; a booking shows in Coming up at once and can have no day yet; Today says what the person last said; News fits the window; someone with no employer on record is shown by name alone; one tap drafts, with an Undo in its toast; a job put in the bin leaves the list at once; ten big jobs run at once in the cloud; every reason in a bin is one tap; a card you finish leaves its list, its one Undo in the toast; what someone asked for leads, with its button (Make a CV for them); one date a card, said one way; counts that agree; a draft's files are its one filled button; Coming up sits with the main places in the side menu; no Pay not stated, no Not now beside the bin, no tour after the first visit; a person's page shows their conversation, and Draft a reply never asks for words already kept; a thread at its limit of unanswered messages offers Close, never another follow-up, and Close closes it; Contacts counts the follow-ups To do lists; a row says what is next without naming the person again; nobody reads \"at\" with no employer after it; a networking run's first notes are one card in To do; an interview's prep on the page: who and when, then Before you go in in big type (what they are checking, what to say, what to ask, pay, what to be careful of), then each likely question with your answer and the rest folded one tap each, with no file names, paths or commands; Draft only on an answer that is one; an offer reads as your offer, a round with nothing booked after it as waiting to hear, an interview that ended as they said no, you withdrew or no reply (never Passed), with no bin and no prep line; the Brief's Today and the practice read the prep's own questions; every time is said one way, in your own time zone with this device's beside it where it differs, and Settings has Your time zone, asked for in To do when nothing says it; an invitation offering several days asks which, one tap a day, and its card, To do and the strip say the days until one is chosen; a pasted invitation's card shows only its own booking; an interview moved or cancelled is its own choice in the bin; a round over leaves Coming up at its end; something added stays once saved; I heard back answers for the interview's own application; a prep for an earlier plan of rounds says so; I have an interview lists those interviewing first, in one list; the Brief's Coming up holds only what is booked; a made application offers its files on a computer that cannot count PDF pages; anything for Claude is written before Claude is woken for it, and nothing rings when nothing was written; a tap Claude could not do says why in its own words, with the field to give what it needs, on its card and in To do; work waiting its turn stays In line with Claude's own line; drafts written together show as one batch with one Stop; a yes or no question is answered in one tap; the chat shows its newest messages, says when its work failed or was called off, and holds a whole posting; a big search opens and changes screen in a fraction of the time (no person asked about every due row inside a sort, one date format kept), a burst of updates draws once, and the store sends only what changed since the page was made; Settings gives the page's own link, counts Where Claude works by what it shows, says Jobs you hid and pay in plain words and asks before bringing back many, opens long lists on their first few with a search, keeps Save in reach, says each rule to you, and gives a tablet full finger targets; nobody listening is said in the header and its card has no bin, with Open Claude its one button when nothing can hear; a read-only view says so once at the tap; a failed save is said once; one update indicator and no Stop on an update; the side rail shows only with work, the footer is the privacy line, and the gear says where you are on a phone; a resume that breaks your own rules is never offered: its card says why and makes a fresh one, and a failed whole-batch check is said on the draft; a double tap, a held key or a second window is one action and one Undo takes it all back; an Undo too late, or one that did not save, says so; a tap made offline is saved once the page is back; a part of the page that cannot be drawn says so and the rest still works; Change back holds after a reload; every application is one card with its own interview; a draft waiting on your answer says so on its job, a draft that did not finish says why; an interview that has passed says when, never Passed; It went asks no more than the day; setup answers count before a chat takes them; Something looks wrong can go straight to the app's makers; where each person stands is the engine's one answer (one group, one button, one line, counted once for the header, its filters and To do), held by the person's own rules, so nobody past their limit, at an employer they turned down or outside where they look is offered anything; a draft that breaks their rules says so and offers Fix it, never Copy or I sent it; replies lead Messages; a filter shows its people; a search is not a filter; a reply logged or a person let go changes their row at once; one word for each status; Chat opens on its newest message, marks a message that got no answer, and dots its tab for an answer not seen; a job card says when it was posted and, under More, why it scored what it did; a drafted role's I have applied is on its draft only; a closed posting offers only setting it aside; Also at names each person once and never the card's own role; Apply on LinkedIn where the link goes there; a screening answer left to you has no Copy, and each answer shows its note; Applied says what it counts and flags a late follow-up; the weeks say their average; a stage name leads its heading with a capital; news carried from an earlier brief says today's search found nothing newer; the Brief's search link is Find jobs; a setup with every answer in says Claude is finishing it, and one stopped for hours says so with one Carry on; building a resume asks job after job until That's all, typed or tapped, then its last question; on a phone the reading card offers I'll paste them instead, and a note written before its profile was read is never offered to send; a part that cannot be drawn reaches Something looks wrong by its kind; the page is published as a small page and small files for its code, so a chat reads only what changed and a republish sends one small file for each part that changed, its search coming from its own store, and every republish first lists what the page holds and puts back any part it lacks; a page whose code did not all arrive says so in one line, with one button that asks Claude to put the whole page up again, and a page opened while an update is still going up says it is being updated and opens itself again until it is all there, with nothing to tap; the Wake link types plain words; a page that cannot reach Claude says Claude isn't listening, with Open Claude, never a spinner; the page is published as a small page and small files for its code, so a chat reads only what changed and a republish sends one small file for each part that changed, its search coming from its own store; a draft written with a batch that stops on its own question shows its question with Answer, never the batch's progress, and the batch's Try again leaves it waiting on you; To do says how many more people who need you are in Contacts; Chat opens on its newest message with the box under it on a phone too, where the box held at the foot of the screen had left the newest message screens below, the moment it opens, and Back to Chat no longer jumps to the top; a paste longer than the box says it was cut in every browser, Firefox included; a double tap on Try again rings Claude once, never a second time from Send to Claude drawn under the finger"),
            (18, "2026-11-04", True, "the Brief's Since your last brief and its earlier briefs stay open when the page redraws, so a tap on them always opens them; the Brief shows as many of each list as it should for the newest data, so pressing Brief on a phone shows the same Brief as it first did; an opened setting puts its buttons at the right on a wide screen, a short choice is a row of chips, the LinkedIn download has one button, a saved tap says what it waits behind with a link to it in Claude's work, and a phone scrolling the Brief no longer meets a blank page while it updates"),
            (19, "2026-11-04", True, "Settings has Phone notification under Your brief, off unless chosen, and turning the brief on asks whether you want one"),
            (20, "2026-11-04", True, "Claude\'s work opens and closes from the pill on every screen; closed and stopped rows leave their lists at once; a finished follow-up opens that person\'s message; held work counts the running work before the update; the settings gear is even and the Brief icon has clear gaps; a run of like work is one card; a card of notes to check says what it is; the edit panel leads with your words and has one button; a card being changed says so"),
            (21, "2026-11-04", True, "a To do row whose message is drafted says Draft ready and opens the draft, never drafts it again, an application\'s follow-up included; two or more drafted messages are one card, N messages ready to send, a row a person opening their draft and one button opening Messages; nobody listening is said once, on its card in To do, with Wake Claude its one button, never again in the line under the header; Open Claude, which leaves the Claude app, is offered only where nothing can hear the page and never on a phone; a LinkedIn download Claude has saved leaves To do, and one that brought nothing new says so, with nothing to take back; a sheet's foot with Cancel never covers its last choice"),
            (22, "2026-11-04", True, "To do never lists someone who has not answered your limit of messages: nothing to do is not a To do, so the card to close them all is gone; in Contacts they wait below the fold with the others who need nothing from you, their row saying to leave it unless they write back, with Close"),
            (23, "2026-11-04", True, "a job's More offers Draft the resume only, the resume without a letter, as one tap"),
            (24, "2026-11-05", True, "LinkedIn is looked at once a day, and the look is kept in your search's own store, so switching to another chat and back never loads LinkedIn again that day; the page never opens Claude's browser by itself (Open LinkedIn opens the sign-in at your tap), reads the tab it keeps as it stands before loading anything, and someone whose page did not load is read again the next day or with Read them, never at every opening"),
            (25, "2026-11-05", True, "Contacts is one page: each person's card carries the message drafted to them, open, until I sent it, and people with one come first; They replied opens a labelled box under the person, whose line says where the reply stands, with Cancel while it waits or runs, Finished until the draft is on the card and Try again after a failure; an old Messages address and To do's messages ready to send open Contacts on the person; the card says the latest exchange only, and when you first wrote and how many each way are under More"),
            (26, "2026-11-05", True, "a question is answered on its card with the control its answer needs: a refused day with a date picker and its time, a choice as chips, a yes or no in one tap, a number, a slider, never Say it in Chat; a question Claude stops on shows the words it is about, quoted, and its control on its To do card and in Claude's work, and the answer carries the work on; Coming up adds a missing time with a time picker on its row; a card has one bin and says Not done once; Show N more goes once it has shown them; a card's actions are one row of pills, the next step semibold, More a pill, and the Brief's tile links are pills too; the menu folds to its icons from beside the page's title, Settings last under one rule; finished work says Finished: putting it on your page until the page has it; an interview leads To do only when it is today or tomorrow or has no prep; the fold of what is not due yet is Not due yet (N)"),
            (27, "2026-11-05", True, "Find jobs can draft every one as it is found, as one job: its card counts them, \"2 of 5 drafted\" (a count says its own word)"),
            (28, "2026-11-05", True, "a bin's choices are whole above its foot, or scroll clear of it with a fade saying there is more, and Cancel is a soft pill; the gauge is beside every control that wakes Claude and says this copy's own minutes for that kind of work, from its finished work; a booked interview or call is moved from its Coming up row with its pencil; a double tap on Try again is one write in Firefox too"),
            (29, "2026-11-05", True, "Contacts round two: a draft that breaks the person's rules is fixed by Claude by itself, queued by the engine with no tap, its line on the card (Claude is fixing it), and offered as ready only once it passes; no Fix it button; the pencil sits beside Copy, the words changed in place (what is copied and logged as sent) or Claude asked to change them (Shorter, Warmer, More formal, or in their words); what wakes Claude carries its cost; More holds only what is rare; when you first wrote is on their page; the header is one short line with Paste a message beside Find people"),
            (30, "2026-11-05", True, "a message being changed with the pencil says so on its card until the new words are there; a control that wakes Claude names its kind so its gauge is drawn"),
            (31, "2026-11-05", True, "To do counts cards, a checklist one with its own x of N done; it says how far today has gone and when all is done; Done today replaces Recent changes; a row is put off to tomorrow or next week in the engine from its bin; help that asks nothing today is one line at the end, and a computer-only card is not shown on a phone"),
            (32, "2026-11-05", False, "More is a full tap target on a phone; work finished says Done once a section the chat wrote after it is on the page, Finished: putting it on your page until then; the words changed under the pencil are sent trimmed"),
            (33, "2026-11-05", True, "what a search left out reads as one row a rule in plain words, with its count, when it last cut, three examples, its rows behind See them with a search box, Check a few and the pencil for the rule's own setting; Settings has Your rules, each rule one sentence with the day it was set, your words, what it left out lately, its pencil and its bin, and a quiet Still right? on an old busy one; the Brief says so at most once a month"),
            (34, "2026-11-05", True, "Jobs is one list of the jobs you might apply to, each once at its own stage, with Applied beside it; a drafted job is its draft's card with the job's fit and reasons; one line of facts (the employer, the town, posted and found, the pay) ending with its details fold (Why, Details); More holds only the rare; every action a pill, the next step marked the same on every card; a pencil beside the resume's and the letter's own words opens the Tweak panel, and one on a job corrects its title, pay or place; a draft's remake and its files are queued by the view, never Make it again or Get my files ready; Questions on the form under More, its answers on the card; every control that wakes Claude carries the gauge; the header has no line about a search, and Add a job and your resume are soft pills beside Find jobs"),
            (35, "2026-11-05", True, "To do has one card an act and a person: every message to send on one card counted as Contacts counts it, a person's rows and their referral on one card, the small questions one at a time, Done on checklist rows with They replied in the bin, no fix buttons (Claude fixes a failing application by itself), a closed posting set aside by itself and a referral a note; an interview's actions are the same on To do and Coming up; headers are one line"),
            (36, "2026-11-05", False, "the Jobs count beside the menu is read aloud as jobs to apply, the list it counts"),
            (37, "2026-11-05", True, "the word a person reads is trash, never bin, in the page's help and its tips"),
            (38, "2026-11-05", False, "one way to answer a quick question, with Another day? after It went"),
            (39, "2026-11-05", True, "a job being drafted says how its draft is going with Cancel and stays in To apply; a job's question is on its own card; the Brief counts drafts being made apart; put off is not done; who needs you is one count; follow-ups on applications are one card; every control that wakes Claude shows its gauge and every card keeps to its budget; switches are whole-row taps; the foot keeps to the column"),
            (40, "2026-11-05", True, "a job you added shows at the top of Jobs while Claude scores it, with its work line and Cancel"),
            (41, "2026-11-05", True, "a burst of live writes is folded into the next frame again, so a card shows its new state as soon as it is written"),
            (42, "2026-11-05", True, "away from the desktop app the page is not drawn again a second and a half after opening unless that changed what it says; a Tweak panel opened on a wide screen shows at once, without waiting for the next redraw"),
            (43, "2026-11-05", True, "what a late capability changes is drawn once it settles"),
            (44, "2026-11-05", False, "Icons only is its own section at the top of the side menu, a row like the others under one rule; every screen is the whole width; a feed back after failing counts as up only once it has stayed up a second, so the header never says Connected for a moment while it reconnects"),
            (45, "2026-11-05", True, "a card's More stays beside its other buttons when opened and opens under the row, on every card; its buttons are one row that wraps only when it must; and Something else, last under every live card's More, opens the Chat about that card, what you send from it going to Claude as work about that card"),
            (46, "2026-11-05", True, "a LinkedIn read the page started by itself and that did not finish (Claude's browser closed, the page left) holds automatic reading until the next day, kept where every opening sees it, so a profile no longer opens in Claude's browser at each return to the page; a browser step that never answers gives up after a minute and a half"),
            (47, "2026-11-05", True, "Something else opens a box under its card instead of the Chat: the question goes to Claude in that card's own thread and Claude's answer shows under the card, with its work line while it runs; the Chat no longer fills with them; Paste a message, an interview not on the list, Tell Claude, Tidy these up and Bring them back answer where they are asked too; a draft that sends the resume carries the file; an answer is never left saying it is being put on your page"),
            (48, "2026-11-05", True, "web addresses in the Brief's news are short links named by their site; Jobs has a search beside Filter, as Contacts does; a draft's check says the documents and their length, never \"Made, right length\""),
            (49, "2026-11-05", True, "a Brief step about an application opens it in Jobs, Applied; someone put away on the page leaves the Brief's steps at once; with nothing new found, the Brief's Jobs panel lists the drafts ready to apply, best fit first"),
            (50, "2026-11-05", True, "a draft's pencil opens a box asking what to change, room for a pasted message, its quick choices filling it and one Ask Claude (Cmd or Ctrl+Enter) with one gauge; Edit the words yourself makes the words the field"),
            (51, "2026-11-05", True, "every visit opens the whole list, never a filter left on; Contacts sorts who is waiting on you first, with a Sort by beside it; the filters on Contacts and Jobs are the few that matter; the pencil box has Cancel"),
            (52, "2026-11-05", True, "the page rings a fresh thread once another chat answers it, so a new page chat hears every tap"),
            (53, "2026-11-05", True, "several drafted at once read as one line with one Cancel all and a word a row; finished answers group in Claude's work, folded ones too; a message sent while Claude answers the last goes to Claude; a chat message that does not save says so"),
            (54, "2026-11-05", True, "every trash sheet whose card has a box ends with Something else, opening that box; a skill question answered on a job card leaves it at once with only its answer ticked, and has a third answer, just for this role; Coming up and the Brief say Not confirmed yet, with its box wherever a day is given, and a call called off leaves Coming up at once; an I sent it the store never answers says Saving, then Not saved. Tap I sent it again., with the message back on its card"),
            (55, "2026-11-05", True, "Chat opens on its newest message and stays there until scrolled up, a Latest button when it is, and the last day shown with earlier messages twenty at a time"),
            (56, "2026-11-05", True, "a downloaded resume or letter is named your name, the document and the employer, never the role run together; Chat's Latest sits above its box on a phone; Not confirmed yet is a small pill; on a phone Jobs' search has its own row; the pencil's box takes the cursor"),
            (57, "2026-11-05", True, "a form's answers ready to copy are opened by the line that says so, Show it, where it said under More"),
            (58, "2026-11-05", True, "a question the quick answer fails or never answers goes to Claude, and one left unanswered when the page closed goes to Claude at the next visit"),
            (59, "2026-11-05", True, "a role marked applied leaves To apply at once, and Applied opens on today's and yesterday's as a filter, shown with Clear all"),
            (60, "2026-11-05", False, "an InMail's card says why it was chosen and the credit it spends, clips its body with More, and switches to a connection note and back; a question asking for a number takes it in place, with the steps to find it under the question"),
            (61, "2026-11-05", True, "a laptop's Brief fits its window in two rows, the privacy line and the tip on its last row; Stop Claude calls off Claude's work everywhere; Claude's work says one short state a card and finished work is one row that opens where it belongs; Dismiss on suggestions; a card's answer offers the draft it made and opens the people it names, shows its latest with Earlier, and a hidden one leaves a Show line; a pencil change is said once under the draft, New version only once it is there; nothing owed at an employer turned down stays in Next or To do; the chat bubble can be made bigger"),
            (62, "2026-11-05", True, "a mark (applied, not applying, I sent it, set aside, put off) rings nobody and never makes the page say Claude is not listening: the next chat that works on the search keeps it first"),
            (63, "2026-11-05", True, "finished work's toast opens where its record lives, a person's in Contacts on them, never Jobs; a Brief line naming someone at an employer opens that person; a filter taken off leaves no chip without words; a search box on screen always searches, and a surname finds the person"),
            (64, "2026-11-05", True, "a resume made for someone is on their card to get; a row closed as the same person as another is never listed beside it, its messages shown on the one kept"),
            (65, "2026-11-05", True, "an I sent it or skip on a message counts only for the version it was made on, so the next message to that person stays to send"),
            (66, "2026-11-05", True, "Latest on the Chat page stops with the field at the foot of the screen; an answer written with its work waits until the page holds what that work changed"),
            (67, "2026-11-06", False, "the weekly bars draw past weeks in the second chart colour at full strength and this week in the mark, so neither looks grey in the dark"),
            (68, "2026-11-06", False, "a laptop's Brief keeps each row as tall as what it holds, never stretched to the window into empty panels"),
            (69, "2026-11-06", False, "a laptop's Brief that nearly fills the window is stretched to its foot, panels lined up edge to edge; a sparse one keeps each row to what it holds"),
            (70, "2026-11-06", False, "this week's bar in the second chart colour and past weeks in the rose; the dates and the line under the bars in the text's colour; news links underlined in their own colour, thinner; the menu's words centred on their icons"),
            (71, "2026-11-06", False, "the weekly bars' dates show every other week and this week's at every width, never cut"),
            (72, "2026-11-06", True, "Settings: employers turned down are one row, learned rules one home grouped by area with what is now part of the app folded, long lists show their first few, Something looks wrong opens in place, What's new shows the version, Smaller and Larger drawn in their size, Advanced only for what costs time; Job sites each by its plain name with one line, a site needing a key says what it needs (Adzuna: a paid plan, its free 25 searches gone within one search here) with the steps, and a refused tick says why on its own row; a search setting changed starts no search, its row saying Used from your next search with Find jobs beside it; the LinkedIn download reminder's trash offers Every 2 weeks, Every month and Stop asking, one tap with Undo, and Settings > LinkedIn has the same choice as chips; the download's line there shows only just after a tap, never a Done from days ago nor that only a chat can take it back; Your brief shows the time it really comes, with one line where it is not the time asked for (the app's own 7:38 for 8:00, or the scheduler starting it late), and a time picked in its sheet is kept to the minute; a LinkedIn read cut short holds the reads until the person\'s own tomorrow, in their time zone, never the device\'s date"),
            (73, "2026-11-06", False, "Settings, under You, has File names: three ways to name the files you download, each shown as an example from your own name and latest employer, the person, employer, document recommended; a download takes the engine's name for it"),
            (74, "2026-11-06", False, "Safari's measures are turned into the window's own px, so its laptop Brief fills the window and Latest stops at the field; a computer reporting no pointer gets the laptop's type, as Firefox with no mouse it could see did not"),
            (75, "2026-11-06", False, "the Brief takes its compact shape whenever the whole of it does not fit, so a window between 661 and about 800px tall no longer scrolls; News shows the number of points chosen under Edit the brief (3 unless chosen), a point written with \"Use it:\" set in its two parts; Jobs lists up to eight where it has room; Your progress's chart takes its panel's room and each number opens where those things are; a person's trash in To do opens their box under that card; \"In line\" says \"Waiting its turn\""),
            (76, "2026-11-06", False, "the Chat button and its panel sit at the right or the left, chosen by the panel's arrow or Settings > Look, big or small; its Open in Chat and Close are soft pills; earlier messages come only by Show"),
            (77, "2026-11-06", False, "a new text size fits the Brief to the window again: the fit was kept by the window's size alone"),
            (78, "2026-11-06", True, "profile reading never loads a page in the tab in front of the person: every automatic look and read goes to the page's own tab, opened only by a tap, a sign-out met while reading by itself is one To do card that says where the reading happens, a run left unfinished tries again two hours on, someone dropped on the page is not read; an I sent it tap that kept no version counts only for its own words; a follow-up row shows its person's work being drafted however it was asked for"),
            (79, "2026-11-06", False, "Cancel under a draft's pencil puts back the words edited by hand; Done editing keeps them"),
            (80, "2026-11-06", False, "Your CV's card has the pencil where its draft is kept: the Tweak panel opens on Bullets, each a choice, the ones ticked swapped for another true one from the same job and never kept as a usual"),
            (81, "2026-11-06", False, "a toast shows its time left as a ring round its close, two at most with the rest counted; a job tapped keeps its place on Jobs while the person stays; a job left out as not a fit says why in Claude's work and never offers Try again"),
            (82, "2026-11-06", False, "one card left over is shown in place, never folded, on To do and on Jobs, and a fold at a list's end is a quiet line, never a bar the width of the page"),
            (83, "2026-11-07", False, "a laptop's Brief panels use the room their row gives them: a short list's rows each in a soft box and spread a step apart, the pills just under a panel with little to show, Your progress's chart grown into its room, and Jobs' new jobs headed \"New, best fit first\" under its drafts' line; two panels of one row as tall as each other give way together; in a prep's folded sections a note to you is a quieter line under the words it is about, never a bullet among the words to say; a referral's end is one tap a choice (turned down, withdrew, not happening, Something else opening the person's box), also first in their trash while it is in flight, and the other choose-then-Save sheets are buttons; an interview had and waiting to hear reads \"You had it 2 Nov\" below what is ahead, counted apart by the engine, with a long stored round name titled short; Help Claude do more sits right after today's things with what it gives; a note waiting for their profile says once when it is read (the page's own reading, in the Claude app on a computer), with Paste beside it gauged as one note's rewrite; everyone waiting is one To do card, never rows of Messages to send; a character count is grey within its limit, amber only while editing near it, red over"),
            (84, "2026-11-09", False, "Settings, Your rules: Held back for now, what the person's rules hold back today with the day each opens and what lifts it, and every rule that holds anything one tap below"),
            (85, "2026-11-09", False, "Settings shows your computer in one line from how it last checked in (off, signed out of LinkedIn, not switched on, or ready), with the steps only where you are needed, and one To do card only while work waits for it; Find people goes to your computer once it is set up or has checked in lately, and its card says where it is starting"),
            (86, "2026-11-09", False, "a change that finished with nothing changed (held, set aside, not possible) says so on its card at once, with Claude's own answer where it wrote one, never a spinner waiting for a new version; one whose new version is late stops spinning after a few minutes; a person whose draft a change set aside is never told \"Reply written\"; a message to Claude carries its words on its work item"),
            (87, "2026-11-09", False, "the Brief greets by the clock of the device it is read on, and a ready message has Open their profile on its face beside I sent it"),
            (88, "2026-11-10", False, "a reply that sends a resume shows the one Claude is making for that person, never the general one, while it is made"),
            (89, "2026-11-10", False, "a work card's count joins its line without a stray full stop; each people search asked from the page has its own id, so a second one the same day never overwrites the first"),
            (90, "2026-11-10", False, "a work card's count joins its line without a stray full stop"),
            (91, "2026-11-10", False, "Your progress counts people as well as jobs: up to four numbers chosen for you (applied, interviews, messages sent, replies, calls, referrals and the like), never a nought beside real work, one line on what is working when your own numbers show it, and the weeks as applications and messages sent"),
            (92, "2026-11-10", False, "a note waiting for its person's profile names only what is there: with your computer ready, it says Claude reads it on your computer by itself and the read is sent there with nothing pressed, and \"press Read them\" only while To do shows that button; a reply that sends the resume made for that person offers that one, from the page's store; a finished resume made for someone opens their card in Contacts; Help Claude do more is one soft card after today's things with its one pill to start; the page being updated turns a small ring in its own colours"),
            (93, "2026-11-10", False, "coming back to the page from LinkedIn, the message whose Copy or Open their profile was pressed last is brought into view and ringed for a few seconds, its I sent it the filled pill, until I sent it or a tap elsewhere; work started in a chat on your computer says so on its card while it runs, and that you can delete that chat when it's done"),
            (94, "2026-11-10", False, "a job that stopped because LinkedIn is signed out in Claude's browser says so on its card with Sign in to LinkedIn, which signs the person in inside the Claude app in the page's own LinkedIn panel and sends the job back by itself once the page sees them signed in, never an Answer box asking them to find a chat on their computer; the Brief's Next panel says how many are in To do only where To do holds more than it shows"),
            (95, "2026-11-10", False, "work waiting for the computer says Waiting for your computer, with no clock and never Claude has picked this up or No answer from Claude, until a chat there starts it; an answer tapped on a card whose work has finished since does nothing and says so, never sending the job round again"),
            (96, "2026-11-10", False, "a first note held back because people at its employer already wait on a reply says On hold and why, with Go ahead anyway, never that Claude reads the profile by itself"),
            (97, "2026-11-10", False, "work for the computer that Claude called off before it began says why on its card"),
            (98, "2026-11-10", False, "a draft written in one chat stays on its person's card while that chat's save lands, never drawn over by a copy that lacks it; a name searched for in Contacts is found whatever the filters, those a filter hides said as N more hidden by your filter with Show them; a message Claude held is on hold on its card with why, when and Send it anyway, and on the person's record, never offered as ready under Finished: held"),
            (99, "2026-11-10", False, "a Chat answer, or one under a card's Something else, that changed something carries a button for each place it changed (Updated in Contacts, Updated in Jobs, Ready in Jobs, Ready in Coming up, Updated in Your profile, Running in Claude's work), at most four then and N more, worked out by app.py done from what its work wrote; each opens that card in place, scrolled into view and marked, and one set aside or gone opens its screen with a short note; the answer is a line or two, never the draft pasted, unless asked"),
            (100, "2026-11-10", False, "the Brief's lists count a panel as full, not overflowing, within two px, as Safari rounds its measures: its Jobs panel showed four of eleven with room for six there"),
            (101, "2026-11-10", False, "the Brief's lists take the room its rows share in turns, the most needed first, rather than one list taking all it can before the next: in Safari Coming up took a fourth row and left Jobs four of eleven"),
            (102, "2026-11-10", False, "an interview's live prep opens full screen from its card: its parts in order with chips to each, the time each takes, what they are known to ask, what to say first with its Likely to prompt links to the answer, each question with who asks it and other ways it is put, one Simple or Detailed switch for every answer and one on each, follow-ups that open by who asks, your stories, every term a dotted word that opens beside the page or from the bottom on a phone with Back, the words A to Z, the questions to ask them, notes just for you, Open all, and a bar that stays at the top with search, Hide the answers (which puts each answer behind Start and a small timer) and a chip to every part and to the stories, the words and your notes; the pay and notice to say are at the top, the questions to ask them read as you would say them, and an answer is drawn a step larger; the Brief's Likely to come up reads it; an interview with none reads as before"),
            (103, "2026-11-10", False, "an interview's live prep opens full screen from its card, laid out as one calm page in the order the interview runs: a short line on what it is, Practise with Claude, search, Open all and Close all, one Simple or Detailed switch for every answer, and a chip to every part, the stories, the words and your notes; then the timing and what they are known to ask with where it comes up; then each part under its own rule with what to say first, its Likely to prompt and Full answer lines going to the answer and marking it, a line to end on, and its questions as cards with who asks, other ways it is put, the answer with its own switch and its follow-ups folded by who asks; the questions to ask them in the last part; your stories, each with the questions it answers; every word A to Z, folded; and your notes, pay and notice among them, last. A term is a dotted word that opens beside the page or from the bottom on a phone, with Back through a term inside a term. Practice is Practise with Claude alone; a guessed kind of interview says so with one tap to the right one; the Brief's Likely to come up reads it; a part's name inside a sentence starts small (the longest stop is a problem, worked aloud); an interview with none reads as before"),
            (104, "2026-11-10", False, "people on hold are one folded group at the foot of Contacts, titled with its count and the reason they share (On hold: 2, waiting for a role to be posted), each card saying On hold with why and until when, any draft folded away with Send it anyway inside; they are not counted in to send or need you, not in To do or on the Brief, and come back by themselves when the hold ends, a role posted bringing Draft the referral ask"),
            (105, "2026-11-11", False, "functions nothing in the app called are retired (app_model.owed_button, app_page.code_files, app_listen.grown_tokens); nothing on the page changes"),
            (106, "2026-11-11", False, "the Brief, before setup, gives the same count of questions as To do (6 short questions), never \"a few\""),
            (107, "2026-11-10", True, "the live interview prep opens on what to say at a glance (the line to open with, what they are known to ask with its part, two questions to ask them, a guessed kind said there with one tap to put it right), with search, Open all and Close all folded under Tools beside the answers switch, the timing one line on its fold, a simple answer a sentence a line, and a one-line introduction"),
            (108, "2026-11-10", True, "on a phone the live prep's who-asks pill sits over its question, so a title never breaks after a word or two beside it, the search box takes its row with Open all and Close all together under it, and a known question's part is said inside its link at a glance"),
            (109, "2026-11-10", True, "a live prep that had to guess the kind of interview offers each kind one tap away (a recruiter or HR screen, a hiring manager, behavioural, technical or coding, a test you take alone, a case, a personal experience interview, a take-home, several back to back, or something else in your own words), and the prep is made again as it"),
            (110, "2026-11-10", True, "practice is in reach: the live prep's answers switch has a third side, Hidden, each answer behind Show the answer to say it first and then check it; two days before and the day before an interview its card says to practise 3 questions today, about 10 minutes, and its first pill opens the prep with the answers hidden at the first likely question (Practise with Claude beside Read your prep where there is no live prep), the calendar under More on those days"),
            (111, "2026-11-10", True, "Coming up's interview row has Read your prep as its pill, in To do's words, where it said Prep ready as a small underlined link; Prepare me and Update my prep are pills too"),
            (112, "2026-11-10", True, "a live prep for a test taken alone reads as one (Keep in mind, no talk timed, Before you start at a glance, drawn even before it has questions), and a day of interviews is said in hours"),
            (113, "2026-11-10", True, "with the answers hidden, Show the answer is a small pill beside Say rather than a bar across the answer"),
            (114, "2026-11-10", False, "the computer row and its To do card say when the chat that starts Claude on the computer waits for the person's approval or is not answering, naming the work that waits, instead of ready"),
            (115, "2026-11-11", False, "Your rules lists the roles you set aside under one folded row, Roles you set aside, each with the day it ends (or for good) and a bin that brings it back"),
            (116, "2026-11-10", False, "an answer given on a card clears its question from the work as the engine does, and is written over the work as it stands now, so a late tap on a finished job changes nothing"),
            (117, "2026-11-10", False, "where you let Claude read LinkedIn profiles, and in Settings beside it, one plain line says LinkedIn's rules do not allow automated tools and it can limit an account it thinks uses one; reading stays on"),
            (118, "2026-11-10", False, "work waiting for Claude says on its card that it starts by itself the next time one of your Claude chats is open, and the one thing that starts it now; on a wide screen the pill says 1 waiting for Claude"),
            (119, "2026-11-10", False, "a draft Claude makes again by itself says what its check found, never that a check needs you; one not made yet says it is made next"),
            (120, "2026-11-10", False, "one banner over Claude's work counts the jobs with no word from Claude for a while, says they are tried again by themselves, and stops them in one tap; work waiting on you is never counted"),
            (121, "2026-11-10", False, "the line at the head of Jobs is one sentence whose total is the tab's: 5 to apply to: 3 ready, 1 being made, 1 to look at"),
            (122, "2026-11-10", False, "a job whose chat has been quiet less than half an hour past its time says Waiting for its chat, never May have stopped, and is not counted in the banner"),
            (123, "2026-11-10", False, "a checklist card in To do offers Plan a time: a day and a time, then the calendar sheet Coming up uses, with nothing sent"),
            (124, "2026-11-10", False, "a day you set yourself (a follow-up, a nudge, a message to send, a thank-you) is ready past it, never Overdue or days late; a checklist counts what is left (7 to send) until one is done; only a date someone else set is overdue"),
            (125, "2026-11-10", False, "Progress leads with this week's own work (applications and messages sent), the funnel says what is usual beside it with the counts in words one tap down, and a finding is a next step"),
            (126, "2026-11-11", False, "the page's code is cut into smaller files that each change on their own, so an update of the page reads about half what it did, and the page is read once however many times it is published"),
            (127, "2026-11-11", False, "a part of a long section or list holds what it holds and is written again only when that changes, so updating the page writes far less"),
            (128, "2026-11-10", True, "the live interview prep opens on what to say at a glance (the line to open with, what they are known to ask with its part, two questions to ask them, a guessed kind said there with one tap to put it right), with search, Open all and Close all folded under Tools beside the answers switch, the timing one line on its fold, a simple answer a sentence a line, and a one-line introduction"),
            (129, "2026-11-10", True, "on a phone the live prep's who-asks pill sits over its question, so a title never breaks after a word or two beside it, the search box takes its row with Open all and Close all together under it, and a known question's part is said inside its link at a glance"),
            (130, "2026-11-10", True, "a live prep that had to guess the kind of interview offers each kind one tap away (a recruiter or HR screen, a hiring manager, behavioural, technical or coding, a test you take alone, a case, a personal experience interview, a take-home, several back to back, or something else in your own words), and the prep is made again as it"),
            (131, "2026-11-10", True, "practice is in reach: the live prep's answers switch has a third side, Hidden, each answer behind Show the answer to say it first and then check it; two days before and the day before an interview its card says to practise 3 questions today, about 10 minutes, and its first pill opens the prep with the answers hidden at the first likely question (Practise with Claude beside Read your prep where there is no live prep), the calendar under More on those days"),
            (132, "2026-11-10", True, "Coming up's interview row has Read your prep as its pill, in To do's words, where it said Prep ready as a small underlined link; Prepare me and Update my prep are pills too"),
            (133, "2026-11-10", True, "a live prep for a test taken alone reads as one (Keep in mind, no talk timed, Before you start at a glance, drawn even before it has questions), and a day of interviews is said in hours"),
            (134, "2026-11-10", True, "with the answers hidden, Show the answer is a small pill beside Say rather than a bar across the answer"),
            (135, "2026-11-10", True, "Hidden is for one practice and never kept, so Read your prep afterwards shows every answer; with the answers hidden, what to say first, at a glance and in each part, waits behind Show what to say"),
            (136, "2026-11-10", True, "the live prep shows only the stories a question in it is answered with, and no Stories chip when there are none"),
            (137, "2026-11-10", True, "on a practice day Coming up's interview row leads with Practise 3 questions, as To do and the interview's card do: one rule for every place"),
            (138, "2026-11-10", False, "the computer row and its To do card say when the chat that starts Claude on the computer waits for the person's approval or is not answering, naming the work that waits, instead of ready"),
            (139, "2026-11-10", False, "a LinkedIn sign-in made on the page softens the computer's signed-out row to Checking sign-in rather than clearing it"),
            (140, "2026-11-10", False, "work for the computer past its start window says it has not started there yet, and offers Start it now, one tap that wakes Claude to start it"),
            (141, "2026-11-10", False, "the page spends its room on words, not padding: on a phone it is drawn at its own size (Smaller is the old 85%), its density from 12px card edges and pills 8px apart; a message's Copy and pencil sit on its heading line, never in its words; Coming up says what a booking is and whether its prep is ready on one line, its icons in fixed places; Stop Claude sits on its clock's line; a checklist row is one line near its button; putting off on To do says Later with a clock; Got it, Add all to your calendar, Add the time, Hide, Close and Change are soft pills; Progress opens on its weeks; the connection dot is a ring while it waits; the gauge says 2 min of Claude; a Brief row wraps from its start; a screen's pills sit on its summary line; the Brief's bell and pencil stay beside the greeting on a phone"),
            (142, "2026-11-10", False, "an answer given on a card clears its question from the work as the engine does, and is written over the work as it stands now, so a late tap on a finished job changes nothing"),
            (143, "2026-11-10", False, "where you let Claude read LinkedIn profiles, and in Settings beside it, one plain line says LinkedIn's rules do not allow automated tools and it can limit an account it thinks uses one; reading stays on"),
            (144, "2026-11-10", False, "work waiting for Claude says on its card that it starts by itself the next time one of your Claude chats is open, and the one thing that starts it now; on a wide screen the pill says 1 waiting for Claude"),
            (145, "2026-11-10", False, "a draft Claude makes again by itself says what its check found, never that a check needs you; one not made yet says it is made next"),
            (146, "2026-11-10", False, "one banner over Claude's work counts the jobs with no word from Claude for a while, says they are tried again by themselves, and stops them in one tap; work waiting on you is never counted"),
            (147, "2026-11-10", False, "the line at the head of Jobs is one sentence whose total is the tab's: 5 to apply to: 3 ready, 1 being made, 1 to look at"),
            (148, "2026-11-10", False, "a job whose chat has been quiet less than half an hour past its time says Waiting for its chat, never May have stopped, and is not counted in the banner"),
            (149, "2026-11-10", False, "a checklist card in To do offers Plan a time: a day and a time, then the calendar sheet Coming up uses, with nothing sent"),
            (150, "2026-11-10", False, "a day you set yourself (a follow-up, a nudge, a message to send, a thank-you) is ready past it, never Overdue or days late; a checklist counts what is left (7 to send) until one is done; only a date someone else set is overdue"),
            (151, "2026-11-10", False, "Progress leads with this week's own work (applications and messages sent), the funnel says what is usual beside it with the counts in words one tap down, and a finding is a next step"),
            (152, "2026-11-10", False, "a double tap on an answer writes it once"),
            (153, "2026-11-10", False, "Try again and Stop write exactly what the engine writes for them: a fresh try clears its last chat, question and error, and a stop of waiting work ends it with its question"),
            (154, "2026-11-10", False, "work waiting for Claude says what really starts it: the helper for the page when it next answers, or the next brief"),
            (155, "2026-11-10", False, "the quiet-work banner says what happens to each job (started again, ended with Try again, sent again with your next tap); only work begun in a chat or run by a chat of its own waits for its chat half an hour"),
            (156, "2026-11-10", False, "the Jobs line counts each draft once where it is: ready only when nothing waits on it, waiting on you, being made only while its work goes, still to make when nothing makes it"),
            (157, "2026-11-10", False, "Plan a time writes its event in UTC from your own zone, with your reminder and folded lines, and the Messages to send card has it too"),
            (158, "2026-11-10", False, "the person's own dates are told from someone else's as the engine writes them (an interview's test or day to choose, an offer's reply-by), and no row, card or Brief line of their own says days late or Follow-up due"),
            (159, "2026-11-10", False, "the Brief's tiles lead with this week's applications and messages sent; Progress's counts in words sit under the funnel; the next step reads plainly; a question after the Jobs line is its own sentence"),
            (160, "2026-11-11", True, "an interview's prep, a person and an application open full screen in the Claude app on a Mac and stay open: a move the app's frame made to the sheet's address closed it the instant it opened, so Read your prep and Practise 3 questions did nothing"),
            (161, "2026-11-11", False, "a live prep's line to say first with no words is never drawn, as an empty bullet under Say first or as Open with; nothing to make again"),
        ),
        "fingerprint": "aaad9ba731dbdd7b",
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
    ".claude-plugin/*": "the plugin's marketplace listing: read by Claude Code on a computer, "
                        "nothing kept in a person's copy",
    "plugin/*": "the optional front door on a computer: finds or makes the person's copy and "
                "hands over to it, and keeps nothing of its own",
    "tools/dates.py": "reads a date; every tool that keeps something is versioned where it keeps it",
    "tools/holds.py": "says what the person's rules hold back today and when each ends, worked "
                      "out afresh from their files on every page build; keeps nothing",
    "tools/offline_boards.py": "a test seam: canned board answers inside a test, nothing kept",
    "tools/try_personal_tests.py": "the maintainer's pre-release check; reads a copy, keeps nothing",
    "tools/rehearse_sync.py": "the maintainer's pre-release rehearsal of a sync on throwaway "
                              "copies; keeps nothing",
    "tools/holidays.py": "works out public holidays when a date is counted; writes nothing, and "
                         "a person's own dates live in their search.py PUBLIC_HOLIDAYS",
    "tools/local_path.py": "finds the tools a computer installed (bun, TeX) for the session that "
                           "runs; keeps nothing",
    "tools/local_path.sh": "the same, for the shell scripts; keeps nothing",
    "tools/file_clock.py": "reads the clock files are stamped with, to measure a file's age; "
                           "the file it writes for that is removed at once, so it keeps nothing",
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
    "tools/followup_drafts.py": "drafts afresh every run, checking again the draft waiting for "
                                "each person; a pack is the day's",
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
    "tools/rules_view.py": "reads the rules and what each left out for the page on every run; the day a rule was set and a Still right? kept are the person's own records, never remade",
    "tools/upcoming.py": "derives Coming up from the records on every run; what the person adds is their own record (documents/upcoming.json), never remade",
    "tools/page_db.py": "reads and writes the page's database dumps; keeps nothing of its own",
    "tools/page_reads.py": "what a wake reads from the page's database, and the copy of it this "
                           "checkout keeps in its git folder, never committed; read afresh at "
                           "every wake",
    "tools/helper_usage.py": "a log of what answering the page cost, added to as it goes; "
                             "nothing it made before is made again",
    "tools/computer.py": "routes work for the computer and writes its heartbeat, its run log "
                         "and the setup's dated mark as it goes; nothing it made before is "
                         "made again (the computer stage itself is the computer-linkedin "
                         "profile upgrade)",
    "tools/app_actions.py": "writes the person's own answers through confirm, exclude, state.py, learned and settings; nothing it wrote is remade",
    "docs/images/*": "the README's pictures, from the test sample, each named after its own contents (tools/readme_pictures.py); never in a person's search",
    "tools/touched.py": "keeps where each piece of work changed something on the page, for its answer's buttons, in a record in the git folder that is never committed and is cleared once the answer is written",
    "tools/app_listen.py": "names the one chat that answers the page, in the page's own database and a record in the git folder that is never committed; read afresh at every start",
    ".claude/skills/app/SKILL.md": "the chat's procedure when the page rings, read afresh each time",
    ".claude/skills/app/wake.md": "the app skill's steps for one wake, read afresh each time",
    ".claude/skills/app/work.md": "the app skill's table of what each kind of work runs, read afresh each time",
    ".claude/skills/app/chat.md": "the app skill's part on a message in the page's chat, read afresh each time",
    ".claude/skills/app/jobs.md": "the app skill's part on big jobs and the daily tidy, read afresh each time",
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
    "tools/remembered.py": "keeps each answer for one page build only, in memory; keeps nothing",
    "tools/readme_pictures.py": "names the README's pictures after their contents; keeps nothing in a person's repo",
    "tools/public_names.py": "development tooling: checks no public name goes unannounced, keeps nothing",
    "tools/public_names.json": "the names the last release shipped, read by a check; keeps nothing",
    "docs/removed_names.json": "the public names the app took away on purpose, read by a check; "
                               "keeps nothing",
    "tools/name_guard_allow.txt": "the name guard's list of invented names; keeps nothing",
    "tools/build_app.py": "development tooling",
    "tools/save_state.py": "stages the person's files for a commit; leaves nothing of its own",
    "tools/land.py": "lands a chat's work on master (save, commit, merge, check, push); leaves "
                     "nothing of its own",
    "tools/security_guards.py": "development tooling",
    "tools/lint_skills.py": "development tooling",
    "tools/ci_local.sh": "development tooling",
    "tools/push_gate.sh": "the maintainer's checks before a push to the app; keeps nothing",
    "tools/everywhere.sh": "release checks in other engines, fonts, languages, time zones and clocks; keeps nothing",
    "docs/NEXT_BUILDER.md": "notes from one builder chat to the next; never in a person's search",
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
    "tools/report.py": "builds a link to the app's makers and reads how long a copy has been "
                       "stuck, from what the copy already holds; it writes nothing",
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


def _interviews_ahead() -> bool:
    """A process at `interview` with a round still to come on its outcome record: only those
    are prepared again, never a round already held."""
    import csv_store
    import docpaths
    import what_works
    today = person.today().isoformat()
    try:
        rows = csv_store.read_rows(person.state("job_search_tracker.csv"))
    except OSError:
        return False
    for r in rows:
        if (r.get("status") or "").strip().lower() != "interview":
            continue
        folder = docpaths.app_folder(r.get("company") or "", r.get("role") or "")
        try:
            with open(os.path.join(folder, "outcome.md"), encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if any(s["date"] and not s["done"] and s["date"] >= today
               for s in what_works.outcome_stages(text, today)):
            return True
    return False


APPLIES = {
    "prep_docs": lambda: bool(glob.glob(person.state("documents", "network", "*", "prep.md"))),
    "queued_notes": lambda: _older_notes(),
    "unsent_drafts": lambda: "drafted" in _tracker_statuses(),
    "live_interviews": lambda: "interview" in _tracker_statuses(),
    "interviews_ahead": lambda: _interviews_ahead(),
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
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
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
