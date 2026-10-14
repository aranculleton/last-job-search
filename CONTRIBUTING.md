# Working in this repo

The app is public and has one maintainer; each person's repo made from it is private and
has one operator. Neither takes outside contributions: ideas for the app are welcome as
issues. What follows is not a contributor policy in the open-source sense. It is the set
of conventions that keep several ephemeral Claude sessions, running in parallel
containers against the same repo, from undoing each other's work.

Upstream's contributor policy, which this replaced, is at
[MadsLorentzen/ai-job-search/CONTRIBUTING.md](https://github.com/MadsLorentzen/ai-job-search/blob/master/CONTRIBUTING.md)
and still applies to anything sent back there.

## The failure this is all defending against

> A session's branch runs far past master. A second session starts from master, correctly
> reports that nothing in the repo holds some piece of state, and builds a second store
> for it, because the first session's file is sitting on a branch it cannot see.
> Reconciling the two takes longer than the work in either.

Every rule below follows from that.

## Master is the trunk

1. **Start by pulling master.** `git fetch origin master && git merge origin/master`,
   before writing anything, not before pushing. Another session may have merged since
   this container was built.
2. **Finish by getting the work onto master.** Not "pushed to the branch": on master.
   Open the PR, get CI green (`./tools/ci_local.sh` on a private repo, Actions on the
   public app), merge it. A branch left behind is work the next session
   cannot see and will duplicate.
3. **Never leave a merged branch around**, and never start new work on an old one.
4. If the work genuinely cannot be finished this session, say so in the last message and
   name the branch, so the next session is told where to look.

The one thing not negotiable in the other direction: **do not push to master without CI
green.** It is the branch every other session starts from, so a broken master breaks all
of them at once.

## Commit state at the moment it changes

Not at the end of the session. A session that runs out of context mid-task loses
everything uncommitted, and the stop hook is a backstop, not a plan.

The table in CLAUDE.md under "Memory: the repo remembers, the chat does not" says what
goes where. The short version: an application, a message sent or received, a fact learned
about an employer, a posting ruled out, a contact whose situation changed. All of it is a
file edit, and the edit happens before the reply.

## What gets rejected here

- **A fix that weakens a guard instead of satisfying it.** `.gitignore` is enforced by
  `tools/security_guards.py`. The answer to a file that will not commit is `git add -f`
  on that specific path, never an edit to the ignore rules.
- **A change to a rule with no failing case behind it.** Almost every invariant in
  `tools/` carries a comment naming the application it shipped as a defect on. The
  chronology check exists because a resume went out with an earlier employer above the
  current one. The `PIPESTATUS` handling in `verify_batch.sh` exists because a failing
  check hid behind `grep | head` and the script reported ALL PASS over 16 bad letters.
  Removing one of these needs an argument about the original failure, not about tidiness.
- **A second source of truth.** `profile/01-candidate-profile.md` holds the facts and
  `profile/CLAUDE.md` carries a working copy; where they disagree, the profile wins and
  the disagreement is a bug to fix rather than a choice to make. The same applies to
  derived views: `open_actions.py` output is never hand-edited, because it is rebuilt
  from the state files on every run.
- **Relaxing a gate to hit a number.** A thin round is reported as a thin round. Never
  pad a run with sub-60 postings, and never loosen the location filter or an eligibility
  gate to make the yield target.
- **Model-shaped solutions to mechanical problems.** If a rule can be enforced in Python,
  it is enforced in Python. A rule that lives only in a prompt gets followed most of the
  time, and "most of the time" is what produced the defects above.

## Before pushing

Run what CI runs:

```bash
python3 tools/lint_skills.py
python3 tools/security_guards.py
python3 -m pytest tests -q
```

In a touched portal CLI, also `bun run typecheck` and `bun test`.

Note the runner: **pytest, not `unittest discover`**. The discover runner collects
`TestCase` subclasses only, and most of this suite is module-level functions using
`parametrize`, `tmp_path` and `monkeypatch`. Those passed locally and never ran in CI at
all, the screened-posting regression corpus among them, which is the one suite whose
whole job is to stop a known bad hit coming back.

If the change touches document generation, also compile and read the PDFs. "Looks fine in
the .tex" is not acceptable: LaTeX page-break decisions are not predictable from source.

```bash
python3 tools/fit_to_page.py <drafts.json>
tools/verify_batch.sh <drafts.json>
```

## Adding a test

Put Python tool tests in `tests/`, portal CLI tests in `.agents/skills/<name>/cli/tests/`
(bun test, network-free).

**Reproduce on the real path, not a constructed input.** A test that fails before the fix
and passes after is necessary but not sufficient: the failing input has to be one the
pipeline actually produces. The corpus in `tests/fixtures/screened_postings/` is the model
to follow. Each file is a real posting, named `pass__*` or `cut__*` for what must happen
to it, and it pins both directions: the ones that must keep being cut, and the ones that
must keep passing because each was wrongly cut once.

## Conventions in the output

These are in the verification checklist and worth knowing before writing anything an
employer sees:

- Spelling follows the profile (`profile/person.json` `documents.spelling`). Never mixed
  within a document.
- The document's noun is the profile's (`documents.noun`), never one of
  `documents.banned_nouns`, in anything the employer sees.
- **No em dashes anywhere.**
- Filenames are human-looking: `<Prefix>_Resume_<ABBR>`, where `<Prefix>` is
  `identity.file_prefix` in `profile/person.json`, no requisition numbers or date stamps
  unless disambiguating two roles at one employer.
- Any document rule of the candidate's own, in `profile/CLAUDE.md`, is followed exactly
  like these.

## Upstream

`.github/workflows/upstream-watch.yml` runs weekly, sorts the upstream commits this fork
lacks into worth-reviewing versus probably-skip, and writes a rolling issue. It never
merges or pushes.

Port by hand, and read the diff rather than trusting a clean cherry-pick. On a fork,
"applies cleanly" is not "correct": a commit fixing a portal this app no longer ships (the
upstream's Danish boards, deleted here in 2026-10) means nothing here.
