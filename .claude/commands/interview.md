# /interview - Prepare for an Interview on a Tracked Application

**Not `/prep`.** This is a real interview on an application in the tracker. `/prep`
prepares a networking call from a thread and takes a person's name instead.

You are preparing the user for a real, scheduled interview on one of their applications. The frameworks for this already exist - the person's own `profile/07-interview-prep.md` (STAR examples, hard-question answers) and the app's `07-interview-prep.md` (STAR method, questions to ask, roleplay protocol) and the Company Research Checklist in `profile/04-job-evaluation.md` - and the `/outcome` archive records which stage the user is at and what earlier stages surfaced. This command wires them together into a stage-specific prep pack and an optional mock interview.

`/apply` optimizes what the company reads; `/interview` optimizes what the company hears. The bridge between them is consistency: the interviewer has read the submitted CV and cover letter, so everything prepared here must match what those documents claim.

Follow these steps **in order**.

---

## Step 0: Parse Input

`$ARGUMENTS` may contain a company name (optionally with a role), e.g. `/interview acme`.

- **With an argument:** match against `job_search_tracker.csv` rows (case-insensitive on company, then role). One match → proceed. Several → list and ask. None → this application isn't tracked; suggest `/outcome <company>` to register it first, or accept the posting and role details directly if the user wants to prep anyway.
- **Without an argument:** list tracker rows whose status suggests a live process - an open status per the **Tracker status vocabulary** in `/outcome` (`interview`, `offer`, or recently `applied`; `drafted` is open but nothing was sent, so it never qualifies) - and ask which one. If the tracker is empty, ask for the company, role, and posting.

v1 preps for a **specific application**. Generic no-target practice is out of scope - if asked, prep against a real tracked application instead.

---

## Step 1: Load the Application Context

1. **The archive** (started by `/apply`, maintained by `/outcome`): the folder `python3 tools/outreach.py --folder "<Company>" "<Role>"` prints: the one already on disk, whichever name it was written under, or the one given by the **Subfolder naming** rule in `documents/README.md`. Below, `documents/applications/<company>_<role>/` means that folder.
   - `job_posting.md` - the exact posting the user applied to
   - the resume and cover letter actually submitted, at the paths named in the tracker row's `cv_file` and `cover_letter_file` columns (`cv/<Prefix>_Resume_<ABBR>.tex` and `cover_letters/<Prefix>_Cover_Letter_<ABBR>.tex`, where `<Prefix>` is `identity.file_prefix` in `profile/person.json`, per `documents/README.md` - no copy lives in this folder). **These are what the interviewer read**; every talking point must be consistent with their claims.
   - `outcome.md` - the stage reached so far and any recorded feedback from earlier stages. Feedback from stage N is the highest-value input for stage N+1 prep.
2. **Fallbacks** (the application may predate `/outcome`): posting via WebFetch on the tracker row's `source` URL, or ask the user to paste it; resume via `cv/<Prefix>_Resume_<ABBR>*.tex` and cover letter via `cover_letters/<Prefix>_Cover_Letter_<ABBR>*.tex` (legacy: `cv/main_<company>*.tex`, `cover_letters/cover_<company>_*.tex`). State plainly which context is missing rather than guessing - and suggest `/outcome <company>` to build the archive for next time.
3. **Ask the user what this interview is** (skip anything `outcome.md` already records): stage (phone screen / technical / case / final round), date, format (phone, video, onsite), and who is interviewing (names and titles, if known).
4. **Read the frameworks once** - do not re-read them in later steps:
   - `profile/07-interview-prep.md` - **the person's own** STAR examples and hard-question answers. Every example used in a prep pack comes from here or from `01-candidate-profile.md`
   - `.claude/skills/job-application-assistant/07-interview-prep.md` - the method only: STAR format and the roleplay guidelines. Its STAR examples are the fictional example person's and are never used for a real person
   - `profile/01-candidate-profile.md`
   - `profile/02-behavioral-profile.md`
   - `profile/04-job-evaluation.md`

---

## Step 2: Research the Company (Interview-Focused)

**Hand the research to the `employer-researcher` subagent** (Agent tool; it runs on sonnet and brings its own rules from `.claude/agents/employer-researcher.md`). Its first move is to check the cache, `company_research/<key>.json`, and start from it inside its TTL (`/apply` may already have filled it for this same application); the verification rule below still applies to a cache hit as much as to fresh research. It locates every source independently of the posting, quotes each fact with its URL, and writes the cache back so a later `/apply` or `/interview` run reuses it. Its brief from here: the employer, the role and team, the stage, the interviewers' names if known, and the Company Research Checklist in `04-job-evaluation.md` (company website for mission, values and recent news; review sites; team size and recent hires; media coverage of growth, restructuring or workplace issues), plus the two additions below. Where the Agent tool is not available, do the same yourself under the same rules.

Additions for interview purposes:

- **Interviewer angle:** if interviewer names are known (from Step 1 or the tracker's `contact_person`), look up their public professional profile. A hiring manager probes team fit and motivation; a senior engineer probes technical depth; HR probes the CV timeline. Note the likely angle per interviewer - do not speculate beyond public information.
- **Conversation hooks:** 2-3 recent, verifiable company specifics (a product launch, a stated strategic priority) the user can reference naturally in answers and in the "why this company" moment.

**Verify before using:** every company claim that will appear in the prep pack must be independently confirmed via WebFetch/WebSearch - same rule the repo applies to cover-letter claims. An unverified "fact" delivered confidently in an interview is worse than no fact. On a 403, retry with browser headers per `.claude/skills/job-application-assistant/09-web-research.md` rather than dropping to search snippets; a snippet is a lead, not a source.

---

## Step 3: Build the Prep Pack

First `python3 tools/learned.py brief interview` (and `brief questions`): the questions, depth and tone they have asked for outrank the defaults below.

Assemble a stage-appropriate prep document with these sections:

### 1. Likely questions
Derive from four sources, in priority order:
1. **Recorded feedback from earlier stages** (`outcome.md`) - anything flagged, doubted, or left unresolved will come back
2. **The fit evaluation's gaps** - the requirements where the profile is weakest are the likeliest probes. For each, prepare an honest bridge answer per `07`'s "You don't have [X]" pattern: acknowledge, connect adjacent experience, show the learning path. **Never prepare an answer that invents experience.**
3. **The posting's stated requirements** - competency by competency
4. **The stage type** - phone screens get motivation and timeline questions; technical rounds get the posting's stack; final rounds get values, salary, and "any reservations" questions

### 2. STAR answer mapping
Match the ready-made STAR examples in `profile/07-interview-prep.md` to the likely questions using their "Use for" tags. Then:
- For likely questions **no existing STAR example covers**, draft a new STAR answer grounded strictly in facts from `01-candidate-profile.md` - profile facts arranged into S/T/A/R, not embellished. Include these drafts in the prep pack; offer to append them to `profile/07-interview-prep.md` only if the user explicitly approves.
- If `/setup` left incomplete STAR stubs relevant to this role, surface them: the user should fill in the details before the interview.

### 3. Consistency brief
A short list of the specific claims the submitted CV and cover letter make (achievements, numbers, skills emphasized) that the interviewer is most likely to probe. The rule stated plainly: **no claim in the room that isn't on the paper, and every claim on the paper must be defensible in depth.**

### 4. Tough questions, customized
The relevant entries from `07`'s tough-question list with per-application answers - "Why this company specifically?" must use the verified hooks from Step 2, never a generic line.

### 5. Questions to ask
Pick 4-6 from `07`'s categories, customized to the research and the stage: role and team questions at screens, tech and growth questions at technical rounds, culture and leadership questions by the final round (that is the last chance to detect a deal-breaker). Cut any question the research already answers publicly - asking it signals you didn't look.

### 6. Logistics
The phone/video tips from `07` when the format calls for them, plus date and interviewer names as a header.

Save the pack in the archive folder derived in Step 1 as `interview_prep_<stage>.md` (create the folder if this application predates `/outcome`). The folder is gitignored, so the pack stays personal; one file per stage, so earlier packs remain as history. Present the whole pack in chat, in full - the file is the record, the conversation is the delivery; never only its path.

---

## Step 4: Offer a Mock Interview

Ask if the user wants to practice. If yes, run the roleplay **in this conversation** following the Roleplay Guidelines in the app's `07-interview-prep.md` exactly: warm-up first, then role-specific technical questions, 1-2 behavioral questions tied to the posting's competencies, and one tough question or curveball. After each answer, give brief feedback - what worked, what to sharpen, and which STAR example from the pack would have served better.

Calibrate feedback against `02-behavioral-profile.md`: coach toward the user's natural register, not a generic ideal - the same voice-consistency rule the `/apply` reviewer applies to cover letters.

---

## Step 5: Close the Loop

Once per session for interview packs, one short line inviting change: "Anything about the questions, the depth or the tone you'd have different? It sticks from now on." What they say goes through CLAUDE.md, "Learning the person".

Then end with:

> Good luck. After the interview, run `/outcome <company>` to log the stage and any feedback - it sharpens the prep for the next round, and once the process resolves `tools/what_works.py` counts it towards whether the fit scores are predicting interviews.

If Step 3 drafted new STAR answers the user approved for keeps, remind them those were appended to `profile/07-interview-prep.md` (or offer again if they deferred).

---

## Important Rules

1. **Consistency with the submitted documents.** The interviewer read the archived CV and cover letter; prep must never contradict them or coach claims beyond them.
2. **Honesty on gaps.** Weak matches get bridge answers (acknowledge → adjacent experience → learning path), never invented experience. Same rule as everywhere else in this repo.
3. **Verified research only.** Company specifics go in the pack only after independent confirmation. Interviewer notes stick to public professional information.
4. **Stage-appropriate prep.** A phone screen pack and a final-round pack are different documents; recorded feedback from earlier stages takes priority over generic question lists.
5. **Where it writes, and nowhere else.** The prep pack lands in the archive folder derived in Step 1. Three other files take a write, each for one reason: `company_research/<key>.json`, the employer research (Step 2); `profile/07-interview-prep.md`, user-approved STAR examples appended on explicit request only; and `01-candidate-profile.md`, when a fact surfaces (below). Framework files are not edited, and the app's own `07-interview-prep.md` never is.

   **Why `01-candidate-profile.md`.** Interview prep is where new facts surface most often: the user recalls a metric, corrects a scope, or fills in a STAR stub. When that happens, write the fact into the profile, as well as putting it in the prep pack. A fact recorded only in prep material reads as unsupported to a later drafting session and gets stripped from CVs as a fabrication. Prep files are not a substitute for the profile.
