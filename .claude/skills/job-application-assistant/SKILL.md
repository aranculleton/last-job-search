---
name: job-application-assistant
description: >
  Assists with job applications: evaluating job postings, tailoring resumes, writing cover
  letters, verifying the compiled PDFs, and preparing for interviews. Triggers on keywords
  like: job posting, job application, CV, cover letter, resume, interview prep, job fit,
  career, application, apply, tailor, ATS, shortlist
allowed-tools: Read, Glob, Grep, WebFetch, WebSearch, Bash, Edit, Write, AskUserQuestion
framework_version: 1.5.4
---

# Job Application Assistant

---

## Workflow

When the user provides a job posting (URL or text), follow this workflow:

### Step 1: Research & Evaluate Fit
- Fetch the job posting content (use WebFetch for URLs). **A 403 is not a dead end** - follow the escalation order in `09-web-research.md` before concluding a page is unavailable, and prefer the employer's own careers posting over an aggregator listing
- Keep the **full posting text verbatim** for Step 3b to archive - never a summary
- Analyze the posting for required competencies, keywords, and priorities
- Research the company (website, LinkedIn, mission, recent news), per `09-web-research.md`
- Score the posting against the candidate's profile using the framework in `profile/04-job-evaluation.md`
- Present the evaluation table and verdict
- Suggest whether the candidate should call the employer before applying (see `profile/04-job-evaluation.md` for guidance)
- Ask the user if they want to proceed with an application

### Step 2: Tailor CV
- Before writing either document, derive `<company>_<role>` once by the **Subfolder naming** rule in `documents/README.md`; reuse that exact value for the CV, cover letter, and Step 3b archive path. If the rule says to stop because the derived name is empty, stop before creating any file.
- Read the most relevant existing CV variant from `cv/` as a starting point
- Follow the guidelines in `05-cv-templates.md`
- Create `cv/<Prefix>_Resume_<ABBR>.tex` with tailored content (`<Prefix>` is `profile/person.json` `identity.file_prefix`)
- Adjust: profile statement, skills section, experience bullet emphasis (the section order is the profile's and never varies per posting)

### Step 3: Write Cover Letter
- Follow the writing style rules in `03-writing-style.md` (critical: no em-dashes, no cliches)
- Follow the template structure in `06-cover-letter-templates.md`
- Create `cover_letters/<Prefix>_Cover_Letter_<ABBR>.tex`
- Ensure the letter connects specific experience to the role requirements

### Step 3b: Record the Application
- Run this once both documents exist. A CV or cover letter drafted alone is not yet an application.
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
- "Write a CV for [company]" - Step 2 only
- "Write a cover letter for [role] at [company]" - Step 3 only
- "Help me prepare for an interview at [company]" - Step 4 only, which is `/interview <company>`
- "What jobs should I look for?" - Career strategy discussion using profile + evaluation framework
