# documents/

Two kinds of thing live here, and it helps to know which is which.

**Input** is what a person puts in: `cv/`, `linkedin/`, `diplomas/`, `references/`,
`postings/`. `/setup` and `/expand` read these to build the candidate profile at
`profile/01-candidate-profile.md`.

**Output** is what the tools write and commit: `applications/`, `rounds/`, `network/`,
`interview/`. This is the record of what the search has done, and it is why a session
starting in a fresh container knows anything at all. It is the whole of that record: every
posting's own text, every round's shortlist with the scores it was ranked on, every
application the tracker knows about including the ones made outside this repo, the answers
given to a portal's own questions, a call-prep document for every contact, a prep pack for
every interview stage, and the questions interviews actually asked.

Nothing in here is sent. Every resume, letter and outreach note stops as a file on disk,
and submitting one is the candidate's own act.

Get the two backwards and you either edit a generated file or wait for `/setup` to find
something nobody put there.

```
documents/
├── cv/              IN    master resume (.pdf or .tex), the fullest version
├── linkedin/        IN    profile export (.pdf)
├── diplomas/        IN    degree certificates and transcripts
├── references/      IN    reference letters
├── postings/        IN    posting text pasted by hand when a page will not fetch
│
├── applications/    OUT   one folder per application
├── rounds/          OUT   each search round's shortlist, bodies stripped
├── network/         OUT   one call-prep document per contact
└── interview/       OUT   the question bank, across every application
```

## applications/

One folder per application, written by `/apply` at draft time and maintained by
`/outcome`. Postings expire fast and a scratch directory dies with the container, so the
posting text is saved here on the way past, because later questions about what a role
actually asked for have nowhere else to go. The note sent to a person at the employer, the
answers typed into the portal's own form and the prep for each interview stage land in the
same folder, so nothing about one application is left in a second system.

**Subfolder naming:** `<company>_<role>_<abbr>` - lowercase, underscores for spaces.
Every run of characters that is not a letter or digit becomes a single underscore (so
`Oakmere Foods A/S` becomes `oakmere_foods_a_s`), and leading and trailing underscores are
trimmed. The name is truncated to 80 characters before the abbreviation is appended. If the derived name is empty, stop and ask the user for a company or
role containing at least one letter or digit; do not create a file or directory. Every non-empty
result is therefore a single path component whatever the posting contains.

**This block is the only home for that rule.** `/apply`, `/outcome`, `/interview` and
`tools/outreach.py` all cite it instead of restating it, because a second copy is how the
first two drifted apart. `slug()` in `tools/outreach.py` is the implementation, and
`python3 tools/outreach.py --folder "<Company>" "<Role>"` is how every command finds an
application's folder: the one already on disk, under whichever name it was written, or the
name this rule gives.

The `_<abbr>` suffix is load-bearing. Without it, two roles at one employer with the same
title overwrite each other, and so do two titles long enough to agree for eighty
characters. Both happen. A pair of folders holding the same posting under different names
leaves nothing to say which one is live.

An `<abbr>` that is only the employer's own name, or the start of it (`Kestrel` for
Kestrel Mutual), is left off, since the name already starts with the employer:
`kestrel_mutual_claims_analyst`, not `kestrel_mutual_claims_analyst_kestrel`. Only one
application at an employer is filed under its plain name; every other one carries a role
token, which stays. Folders written before 2026-10-26 keep the name they have, and
`tools/docpaths.py` `app_folder()` finds them under it: every tool that writes into an
application's folder or reads one asks it, given the abbreviation where it knows one.

Each folder holds:

- **`job_posting.md`** - the posting with its source URL, portal and retrieval date.
- **`screening_answers.md`** - the eight to twelve closed fields a portal asks before it
  will accept a submission (sponsorship, work authorisation, salary expectation),
  written by `/apply` Step 6b on every application.
- **`outreach.md`** - a sub-80-word note to the hiring manager or recruiter, built from
  the cover letter's verified company fact. Sending it is the candidate's call. For a
  resume drafted for a contact who asked for it (`stage_picks.py --for-contact`), no cold
  note: their thread, what they asked, and the command that logs the resume with its file.
- **`form_fields.txt`** - answers given to the portal's own questions, so a follow-up or
  a second application does not contradict the first.
- **`interview_prep.md`** - the one living prep document for this hiring process, written
  by `tools/interview_pack.py` when `/interview` runs and rebuilt in place at every stage.
  What the person writes in it is kept on every rebuild: Your answers, To rework, Notes, and
  what they found out about where they live. Packs an older version wrote one per stage
  (`interview_prep_<stage>.md`) stay as history.
- **`campaign.json`** - the person's answer to the offer of a chat just for this employer:
  `{"chat", "started"}` or `{"declined"}`. Written once by `interview_pack.py campaign`;
  `tools/open_actions.py` and the brief leave an employer with a campaign chat to it.
- A process with no application (a referral that led to a recruiter's call) has a folder
  too, made by `interview_pack.py process`: `outcome.md`, the living document and a
  `job_posting.md` (the posting's text when `--posting` gives it, else a line saying it is
  not held yet), and none of the other application files above.
- **`outcome.md`** - written by `/outcome` once there is a result. Later sessions and
  `tools/what_works.py` read it, so the header is fixed:

  ```markdown
  # Outcome: <Company> - <Role>

  **Status:** in_progress | hired | offer_declined | rejected | no_response | interview_only

  **Date resolved:** YYYY-MM-DD   <- only once resolved; omitted while in_progress
  ```

  That `Status:` enum is the archive's, and it is deliberately not the tracker CSV's
  `status` column. `/outcome` cites this block as the definition, so it lives here and
  nowhere else.

  Below it, `## Interview stages reached` holds one checkbox per stage: `- [x] Phone screen
  (YYYY-MM-DD)` once held, and `- [ ] Technical interview (scheduled YYYY-MM-DD, with
  <title or name>)` while booked. `tools/open_actions.py --due` reads the booked line (a
  stage close with no pack, a thank-you not yet on file after it) and `what_works.py brief
  interviews` the ticked ones (how far applications get).

## interview/

`question_bank.csv`: the questions interviews actually asked, with the story told and
whether it landed, one row per question, across every application. `/outcome` adds to it
after a stage (`tools/interview_pack.py asked`); the next pack at any employer leads with
what was asked there before, and `what_works.py brief interviews` names the questions that
keep coming up and the stories that land. The prep packs themselves are per application,
in `applications/` above, not here.

## rounds/

One file per search round, `<round>.json`, written by `tools/run_round.py`. A round leaves
about 55MB of intermediate files behind, thick with third-party posting text. It deletes
those and keeps the top 60 of the shortlist without the bodies, roughly 30KB: each
posting's priority score with the fit and opportunity it came from, title, company,
location, date, portal, the apply link, and any note explaining why a role was surfaced at
an employer that already has an open application.

This is the search's own memory. It answers "was this ever scored, and what did it score" a
month later, when the posting has expired, the round's working files are deleted by design,
and the conversation that ran it is gone with its container.

## network/

One folder per contact, `<contact_id>/prep.md`, written by `tools/network/prep.py`. A fix
to that generator otherwise reaches only whoever is next to run it, so
`python3 tools/network/prep.py --all` rewrites every contact's document at once.
`open_actions.md` sits beside them, written by `python3 tools/open_actions.py --markdown`:
everything owed, employers first, each employer carrying its applications and its contacts
together. It is derived rather than stored, so a gap in it is a state file to fix, not a
line to edit here.

A prep document is read in the five minutes before a call, so it is shorthand: who the
person is and the route in, the thread so far, their team and their employer, a
compensation band only where somebody looked one up, the questions they are likely to ask
with an answer drawn from the profile, and questions to ask them. **Every fact prints with
its source, or it does not print.** The entries that matter most are the ones that begin
"Do not say": a figure that sounded right, got written down, and then got said out loud to
someone who knows the real number.

## Two directories called cv

They are different things and the collision is worth stating out loud:

| | |
|---|---|
| `documents/cv/` | the master resume a person wrote, read by `/setup` and `/expand`; the one named *current* (or the only one, or the latest dated) is what goes to somebody who asks for it and names no role (`docpaths.current_resume`) |
| `cv/` at the repo root | tailored resumes the generator writes, one per application |

Rendered documents live at the repo root. An application folder names them by path in the
tracker row and holds no copies, so there is one file per artifact and no question about
which is current.

## What /setup reads

From `cv/`: titles, companies, dates, bullets, education, skills, contact details. From
`linkedin/`: the same, cross-referenced, plus whatever the resume left out. From
`diplomas/` and `references/`: dates, institutions, and other people's phrasing about the
work, which is the most useful material here and the most often skipped.

Any filename works. Several files beat one: `/setup` reads all of them, and a
disagreement between two is a question worth asking out loud.

**This repo's profile is already populated**, and `/setup` overwrites it. It holds more
than any single resume shows, including the per-role detail the bullet allocator draws
on. Read [SETUP.md](../SETUP.md#resetting) first.

## postings/

For a posting whose page will not fetch: portals behind a login, a PDF attachment, text
pasted from an email. Name the file `<Company> - <Job Title>.txt` and put the full text in
it. `/apply` reads it exactly as it would a fetched page.

This is also the answer when the session's egress policy blocks a portal and the proxy
reports `connect_rejected`. That is policy, not a bug, and pasting the text is the
supported way round it.

## Privacy

Everything here is personal data, and it is why the repo is private. The `documents/**`
ignore rules are enforced by `tools/security_guards.py`, so they are never edited;
artifacts that belong in the repo are force-added by path with `git add -f`, leaving the
guard intact. The list is in RUNBOOK.md, step 4.
