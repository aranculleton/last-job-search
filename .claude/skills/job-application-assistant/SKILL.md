---
name: job-application-assistant
description: >
  Assists with job applications: evaluating job postings, tailoring resumes, writing cover
  letters, verifying the compiled PDFs, and preparing for interviews. Triggers on keywords
  like: job posting, job application, CV, cover letter, resume, interview prep, job fit,
  career, application, apply, tailor, ATS, shortlist
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Bash, Edit, Write, AskUserQuestion
framework_version: 1.5.6
---

# Job Application Assistant

---

## Workflow

When the user provides a job posting (URL or text), follow this workflow:

### Step 1: Research & Evaluate Fit
- Follow **`/apply` Steps 0 to 1c** (`.claude/commands/apply.md`) exactly: the posting fetched (a 403 is not a dead end, `09-web-research.md`), its **full posting text verbatim** kept for Step 3b to archive (never a summary), the score looked up or derived against `profile/04-job-evaluation.md`, the evaluation table and verdict presented, the plan, the already-applied question and the skills question, then stop until the user answers. It is stated there once so the two paths cannot drift.
- Beside the verdict, suggest whether the candidate should call the employer before applying (`04-job-evaluation.md`, "Pre-Application: Call the Employer").

### Step 2: Tailor CV
- Both documents come from **`/apply` Step 2**, the same pipeline a batch from a round takes: staged with `tools/stage_picks.py`, drafted and audited by the `draft-applications` workflow, bullets allocated per posting by `tools/allocate.py`, rendered and fitted by `tools/fit_to_page.py`, checked by `check_claims.py` and `verify_batch.sh`. **Never write the `.tex` by hand**, and never start from an existing resume in `cv/`: a hand-written document bypasses every check. Only a custom template (`profile/templates/ACTIVE.md`) is drafted by hand, and `/apply` Step 2H says how.
- On that custom-template path, before writing either document, derive `<company>_<role>` once by the **Subfolder naming** rule in `documents/README.md` and reuse that exact value for the CV, the cover letter and the Step 3b archive path. If the rule says to stop because the derived name is empty, stop before creating any file. (On the pipeline path `stage_picks.py` names the files.)

### Step 3: Write Cover Letter
- The letter comes from the same draft object as the resume in Step 2, under `03-writing-style.md` (critical: no em or en dashes, no cliches) and `06-cover-letter-templates.md`, connecting specific experience to the role's requirements.

### Drafting several, or from a round
- A batch, or `/apply` through the pipeline, is drafted by the `draft-applications` workflow, not by hand: `tools/stage_picks.py stage`, then `tools/draft_pack.py build` (the drafting pack: the profile's facts with ids, the person's rules, the voice corpus and the field contract, compiled by code so no drafter re-reads them), then the workflow, then `tools/stage_picks.py audit` (the grounding audit, code first; the model auditor reads only what it flags) and `assemble`. RUNBOOK.md step 2 has the commands.

### Step 3b: Record the Application
- On the pipeline path, `/apply` Step 2 already records it (`tools/record_drafts.py`). The rest of this step is for a custom template, once both documents exist. A CV or cover letter drafted alone is not yet an application.
- Follow **`/apply` Step 6b** (`.claude/commands/apply.md`) exactly: same header, same match-then-update rule, same `drafted` row, same posting archive, same prohibition on touching `job_scraper/seen_jobs.json`. It is stated there once so the two paths cannot drift. Four of its values are named in `/apply`'s own terms: `cv_file`/`cover_letter_file` are the paths written in Steps 2 and 3 here, `source` is the posting URL from Step 1, `deadline` is the application deadline from the posting text Step 1 keeps verbatim (empty when the posting states none - never guess one), and the posting text item 7 archives is the one Step 1 read.
- This step exists here because `/scrape` Step 5 routes straight into this skill. Without it, that path writes two documents and records nothing.

### Step 4: Interview Preparation
- Follow **`/interview`** (`.claude/commands/interview.md`) exactly, every step: the application's archive, the research, the person's learned rules and stories, the pack `tools/interview_pack.py` builds and saves beside the application, and the mock interview. It is stated there once so the two paths cannot drift, the same way Step 3b defers to `/apply` Step 6b.
- A request in passing ("help me prepare for an interview at [company]") is the same request: it gets the same pack, never a shorter one written here.

---

## Reference Files

The person's own documents live in `profile/`, not here: everything in them is about one
candidate, and the app ships none of it. The rest are the app's and live beside this file.

| File | Purpose |
|------|---------|
| `profile/01-candidate-profile.md` | Education, experience, skills, publications, awards. The source of truth for every fact |
| `profile/02-behavioral-profile.md` | Behavioral assessment, strengths, ideal environments |
| `03-writing-style.md` | Tone, structure, do's and don'ts |
| `04-job-evaluation.md` | The scoring framework (gates, dimensions, weighting, research cache) and the template /setup fills |
| `profile/04-job-evaluation.md` | The candidate's filled-in copy, with their targets and bands: what scoring reads |
| `05-cv-templates.md` | LaTeX CV structure and tailoring rules |
| `06-cover-letter-templates.md` | LaTeX cover letter structure and tailoring rules |
| `07-interview-prep.md` | STAR method and roleplay guidelines; its STAR examples are the fictional example person's |
| `profile/07-interview-prep.md` | The person's own STAR examples and hard-question answers: what interview prep uses |
| `08-application-forms.md` | Portal free-text fields: self-introduction, project entries, character-limited pitches |
| `09-web-research.md` | Fetching postings and company pages: trust boundary, the WebFetch 403 fallback, escalation order, claim verification |
| `profile/10-triage-blockers.md` | The short knockout card, derived from the profile. The only context a cheap triage agent needs, before any full scoring |
| `11-cost-model.md` | Where lifecycle tokens actually go, and which model each stage should run on |
| `profile/12-scoring-brief.md` | The compact Tier 3 scoring brief, derived from the profile - the only file a scoring agent needs to produce a score |
| `profile/13-positioning.md` | How to win a role once it is worth going after: brand, framing, voice and what not to do |

---

## Quick Commands

The user may also ask for individual steps without the full workflow:
- "Evaluate this job posting" - Step 1 only
- "Write a CV for [company]" or "Write a cover letter for [role] at [company]" - Steps 2 and 3, through `/apply` Step 2, which renders both from one draft
- "Help me prepare for an interview at [company]" - Step 4 only, which is `/interview <company>`
- "What jobs should I look for?" - Career strategy discussion using profile + evaluation framework
