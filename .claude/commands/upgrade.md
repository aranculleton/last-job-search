# /upgrade - Apply the profile upgrades this repo still needs

Works through the profile upgrades Claude can do alone (`tools/profile_upgrades.py`,
`needs: "nobody"`), most urgent first, and hands back the questions only the person can
answer. Nobody has to know which upgrades exist or ask for them: RUNBOOK.md, "Start of
a session", step 5, starts this in a background agent whenever the sync lists one, and
every scheduled run (the morning brief, and the optional round) runs it first
(`automation/prompts/_common.md` step 2). The person's own request never
waits for it.

`$ARGUMENTS` may hold a time budget in minutes (default 30) or upgrade ids to do only those.

---

## Step 1: The plan

```bash
python3 tools/profile_upgrades.py --plan
```

A JSON list, most urgent first: `id`, `needs`, `why` (what is missing), `run` (what does
it), `gives`, `time`. Keep the `needs: "you"` entries aside for Step 5. Exit 2 with a line
instead of a list means this checkout is older than the repo's last update: run the merge
it names, then the plan again; never apply anything from an older checkout. An empty list while
the sync said upgrades are pending means another chat brought the update in and is
applying them: stop here, with nothing to report. Where the plan holds fewer than the sync
listed, it says which are already in place (an instant one ran, or another chat landed it):
do nothing for those, and the report names each as already in place.

## Step 2: Each upgrade, alone, in order

For each `needs: "nobody"` entry, until the budget is spent:

0. `python3 tools/profile_upgrades.py --check <id>` first: an upgrade done earlier in this
   list can have done this one too (`boards` and `method-boards` both run the boards
   section), and another chat may have landed it on master since the plan was made (it
   checks master each time). If it prints `done`, skip it; `done on master` means merge
   master instead, never apply it again here.
1. Do its `run` on its own: the `/setup` section it names, run alone on the existing
   profile (setup.md, "Run for a profile upgrade"); `/add-portal`; or the edit it
   describes. Touch nothing else in the profile.
2. **Never ask the person.** Every answer comes from `profile/01-candidate-profile.md`,
   the rest of the profile and research you cite. Where `/setup` would ask, choose what
   the profile supports and say so in the commit message. What you cannot ground, write
   as `[CONFIRM: <the question>]` where the value goes: the session asks it at the end
   (the `unconfirmed-facts` upgrade), so nothing is ever guessed.
3. Keep to every rule `/setup` and `/add-portal` keep: robots.txt decides which boards
   are built (a board it disallows is never built here: that is the person's own call, in
   `/add-portal`), nothing personal goes into an app-owned file, research is cited.
4. If its `run` ends with `python3 tools/build_versions.py record <name>` (the
   `method-*` upgrades: a part of the build the app now does better), run that once it is
   redone. A redo keeps what is there and adds what the current method adds; a value it
   would change goes beside the old one as `[CONFIRM: ...]`. Then check it: `python3 tools/profile_upgrades.py --check <id>` must
   print `done`. If it does not, undo what you changed for it and record why.
5. Commit only what this upgrade changed, on its own:
   `Profile upgrade: <id>` as the subject, one line saying what was written as the body,
   in plain words for the person: the page's Updates section shows that line, with an undo
   (`app.py apply` runs `git revert` of this commit when they tap it), so each commit is one
   change and nothing else.
6. **On the page.** Where the person has a page (`profile/app.json` holds its address) and
   this chat can write its database (ArtifactData), the run is one work item of kind `update`,
   `update~upgrades-<YYYYMMDD>`: `status: running` and one plain line in `steps` at each
   upgrade boundary, in the same message as the next upgrade's first command, `done` with
   `result.summary` at the end (the `app` skill). Never ask the person anything from here:
   the questions go to the page as cards by themselves (Step 5).
   Profile files take a plain `git add`; `python3 tools/save_state.py` stages the rest
   (RUNBOOK.md step 4), and nothing else is forced in.

Stop at the budget even mid-list: the rest are picked up next session. An upgrade cut off
part way is undone, never committed half done.

## Step 3: What the person taught it

Before changing any setting, `python3 tools/learned.py locked`. A setting it lists is the
person's: never change it, whatever the upgrade says. If the upgrade would have changed
it, record the offer instead and move on:
`python3 tools/learned.py offer --setting "<file SETTING>" --new "<what the app now does>" --why "<why it may be better>" --version "<upgrade id>"`.
The session asks it with its other questions. A redo also follows every rule
`python3 tools/learned.py brief` lists.

## Step 4: Never

- Never edit an app-owned file, the tracker, the contact book or the threads, and nothing
  in `documents/` except what a `method-*` upgrade's `run` names (an unsent draft
  re-rendered, a live interview's pack written beside the old one). Nothing sent is ever
  touched.
- Never send, submit or post anything.
- Never switch off a portal or narrow the search on your own: an upgrade adds what is
  missing; a change of the person's mind is theirs to make.

## Step 5: Report

Return, in this order and nothing else:

1. One line per upgrade applied: what it changed, its commit, and `undo: git revert <sha>`;
   then one line naming any the plan said were already in place.
2. One line per upgrade skipped or undone, and why.
3. The questions for the person: each `needs: "you"` entry's `ask`, word for word, and
   every `[CONFIRM: ...]` now in the profile (`python3 tools/profile_upgrades.py --check
   unconfirmed-facts` lists them), as plain questions. Never their `steps` or `why_ask`:
   the session gives a question's steps only after a yes and its reason only after "why?".
4. The branch these commits are on, if it is not the session's own.

With a page, the session merges the branch and brings the page's data up to date
(`python3 tools/app.py view`): the page shows each change with its undo, and asks the
questions from 3 itself, one card each (Yes, or Not now), so the chat says nothing about them.
Without one, the session merges the branch, gives the person the plain part of each line from
1 (what it changed, never the commit or the command) at the end of its reply,
and asks at most three of the questions from 3, each short and alone: no list of ids, no
version numbers, no paragraph. A yes brings that question's steps (five at most, under the
line saying when they were checked and the page to check them against, which is checked
that day before they are given: CLAUDE.md, "Talking to the person"; an entry's
`check` line in the plan is yours, never said); a
"why?" brings its one-sentence reason; a no gets "No problem, I'll ask again in a month."
and `python3 tools/profile_upgrades.py --no <id>`. Answers go into the profile where their
markers were, committed like any other profile change.
