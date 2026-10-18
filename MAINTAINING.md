# Maintaining the app

The app is public and has one maintainer; each person's repo made from it is private and
has one operator. This is the maintainer's guide: the conventions that keep several
ephemeral Claude sessions, running in parallel containers against the same repo, from
undoing each other's work. To report a bug or suggest something, see
[CONTRIBUTING.md](CONTRIBUTING.md).

Upstream's contributor policy, which this replaced, is at
[MadsLorentzen/ai-job-search/CONTRIBUTING.md](https://github.com/MadsLorentzen/ai-job-search/blob/master/CONTRIBUTING.md)
and still applies to anything sent back there.

## Developer rules: changing the app itself

These apply whenever the change is to the app, whichever repo the session started in.

- **Changes are made in the app**, on a branch, through a pull request, and merged only with
  CI green. The app is public, so its Actions minutes are free and its CI is the evidence.
  The maintainer's own repo takes it on its next sync; everyone else takes it when it is
  released ("Releasing", below).
- **Nothing reaches the app until the leak scan has passed on the exact tree being pushed,
  branches included**: a public repo's branches are public, and its history is permanent. From
  the maintainer's own repo, `python3 tools/build_app.py <dir> --tokens-out <dir>/tokens`
  writes the denylist from their profile; then `python3 tools/leak_scan.py <app checkout>
  --tokens <dir>/tokens` scans the app checkout with it. The app's CI scans again with the
  `LEAK_TOKENS` secret, but CI only sees what is already public, so the local scan is the gate.
- **No example may be a disguised person.** An example resume, story, message or incident is
  invented, or it is the example person in `profile.example/`. A real case with the names
  swapped is still that person.
- Small PRs and batched commits. A change that touches how documents, scores or messages
  come out is checked by rendering the same inputs before and after and comparing the
  outputs; any difference is named in the PR, or it is a bug.
- **Never ship a feature that only works after a person does something nobody told them
  about.** If an existing user has to act for a change to reach them (a `/setup` section, a
  portal built or rebuilt with `/add-portal`, a re-render, a new state file or column, a
  profile name with no safe default), register it in `tools/profile_upgrades.py` with a
  `pending()` that checks their repo for the trace the action leaves, and name it in the
  CHANGELOG entry (`Profile upgrade: <id>`). Make it `needs="nobody"`, which `/upgrade` applies
  in the background with no one asking, unless it truly needs the person's answer or consent.
  A new profile name with a safe default goes in `SAFE_DEFAULTS` with the reason.
  `tests/test_profile_upgrades.py` fails on either missing.
- **A better way of doing any part of the build reaches every older repo by itself.** Each
  part that leaves something behind in a person's repo (a `/setup` section, the boards, prep
  documents, unsent drafts, interview packs, research, contacts, screening, routines) is a
  versioned method in `tools/build_versions.py`, and every other app file is in its
  `KEEPS_NOTHING` with the reason. Changing a method's files fails
  `tests/test_build_versions.py` until a version is added saying what changed and `rerun`:
  True when what an older version made should be made again (a better board search, a
  fixed prep document), False for wording. With True, every older repo redoes it with no one
  asking: `/upgrade` in the background, the sync itself for an instant one, or every round
  for screening. A new app file fails the same test until it is placed in a method or in
  `KEEPS_NOTHING`. The decision can be made either way; it cannot be skipped.
- **Anything the app says about the Claude app lives in `tools/claude_surfaces.json`**: what a
  chat on the computer, a cloud chat, a phone, the browser pane or a routine can do, and how a
  person reaches each. An entry carries the official page, a quote from it, `verified_on`,
  `verified_against` and `ui_sensitive`. Messages read it (`claude_surfaces.say`), a person's
  docs carry it in `<!-- claude-surface: <id> -->` blocks (`claude_surfaces.py sync-docs`
  rewrites them), and Claude's own instructions name the entry by id. A path is written as a
  destination, "At the time of writing", with the official page beside it, and never tells
  anyone to press, click, tap or find. `tests/test_claude_surfaces.py` fails on a vocabulary
  phrase outside the registry. **The weekly watch** (`.github/workflows/claude-surfaces-watch.yml`,
  the app only) opens the "Claude surfaces to re-check" issue when a quote has left its page, an
  entry is older than 60 days, or a Claude Code release is newer than `checked_version`: re-read
  the page, correct the entry, set `verified_on` and `checked_version`, run `sync-docs`, and
  merge. Decide what a chat can do by the tools it has, never by where it was started: which
  app started a cloud chat is not documented.

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

## Releasing

A person's repo follows the app's **releases**, the newest `vX.Y.Z` tag, and the
maintainer's own repo follows **master** (`tools/sync_app.py`, `channel()`: a repo whose
GitHub owner is the app's follows master, and `"app_channel"` in `profile/person.json`
overrides either way). So master can move several times a day while everyone else gets only
what has already run in the maintainer's copy. A first sync takes master, because a repo is
made from a snapshot of it; after that, stable never goes backwards.

**When**: once the maintainer's copy has run the changes in `[Unreleased]` for a day or two
without trouble, and never inside the hours their own scheduled tasks run.

**How**:

1. A small PR that renames `## [Unreleased]` in `CHANGELOG.md` to
   `## [X.Y.Z] - <date>` and opens a fresh `## [Unreleased]` above it. Minor for new
   behaviour, patch for fixes only. Merge it with CI green.
2. On GitHub: Releases, **Draft a new release**, tag `vX.Y.Z` on master, title `vX.Y.Z`,
   the CHANGELOG section as the notes, **Publish**. The tag is what every repo's next sync
   reads; nothing else needs doing.

A broken release is fixed forward: a fix on master and a new patch release. Never move or
delete a published tag, because repos that already took it would then hold history the
app no longer names.

## Commit state at the moment it changes

Not at the end of the session. A session that runs out of context mid-task loses
everything uncommitted, and the app ships no hook that would catch it (`tools/security_guards.py`
keeps the hook allowlist empty).

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
pipeline actually produces. A person's screened-postings corpus (`profile/tests/fixtures/screened_postings/`, read by
`tools/score_eval.py`; the app has none of its own) is the model to follow. Each file is a real posting, named `pass__*` or `cut__*` for what must happen
to it, and it pins both directions: the ones that must keep being cut, and the ones that
must keep passing because each was wrongly cut once.

## Conventions in the output

These are in the verification checklist and worth knowing before writing anything an
employer sees:

- Spelling follows the profile (`profile/person.json` `documents.spelling`). Never mixed
  within a document.
- The document's noun is the profile's (`documents.noun`), never one of
  `documents.banned_nouns`, in anything the employer sees.
- **No em or en dashes anywhere.**
- Filenames are human-looking: `<Prefix>_Resume_<ABBR>`, where `<Prefix>` is
  `identity.file_prefix` in `profile/person.json`, no requisition numbers or date stamps
  unless disambiguating two roles at one employer.
- Any document rule of the candidate's own, in `profile/CLAUDE.md`, is followed exactly
  like these.

## Upstream

`.github/workflows/upstream-watch.yml` runs weekly, sorts the upstream commits this fork
lacks into worth-reviewing versus probably-skip, and writes a rolling issue. It never
merges or pushes. `python3 tools/upstream_triage.py --remote upstream --branch master` makes
the same report locally, and `python3 tools/check_upstream_updates.py` names the methodology
files an update would touch, by `framework_version` marker. A person's copy has no
`upstream` remote, and the workflow runs only in the app.

Port by hand, and read the diff rather than trusting a clean cherry-pick. On a fork,
"applies cleanly" is not "correct": a commit fixing a portal this app no longer ships (the
upstream's Danish boards, deleted here in 2026-10) means nothing here.

## CI on a private repo

**On a private repo, green is established locally, and that is the rule, not the
fallback.** GitHub bills a private repo per job, rounded up to the minute; a
public repo's minutes are free. Every job in `.github/workflows/ci.yml` now runs only on a
public repo (the app) or on a manual dispatch, so here the
checks show as skipped and cost nothing. Every check in that file is a script in this repo:

```bash
./tools/ci_local.sh            # every check CI runs, under two minutes
./tools/ci_local.sh --quick    # skips the LaTeX compile
```

A clean run is the evidence, and merging on it is allowed. Say in the PR that
`ci_local.sh` was green and name anything it reported as SKIP. Dispatch the workflow by
hand (Actions, CI, Run workflow) only when a SKIP matters for the change, and tick
`latex` only when LaTeX changed. That is the one case worth a billed minute here.

CI's second Python leg runs the oldest Python the app supports, 3.9
(`tools/python_floor.py`), because that is a Mac's own `python3`: a bare `import tomllib`
once passed locally and failed there, and `zip(strict=)`, a 3.10 keyword, crashed the merge
driver on a person's Mac. `ci_local.sh` runs that leg the way CI does (a fresh 3.9
environment with pytest and nothing else), on the system `python3.9` or one `uv` fetches in
seconds; the containers may not ship one. Only where neither exists is the leg reported SKIP, never
passed silently. What a local run cannot be is a second machine; the app's own CI, which
is free, is that for every change made there.

**Still worth doing, because no setting enforces it: batch the commits and push once.**
Push when a unit of work is finished, not to watch CI think, and prefer a PR to a direct
push to master.
