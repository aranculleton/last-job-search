# /upgrade - Apply the profile upgrades this repo still needs

Works through the profile upgrades Claude can do alone (`tools/profile_upgrades.py`,
`needs: "nobody"`), most urgent first, and hands back the questions only the person can
answer. Nobody has to know which upgrades exist or ask for them: CLAUDE.md "Start of
every session" step 5 starts this in a background agent whenever the sync lists one, and
the twice-weekly shortlist runs it before its round. The person's own request never
waits for it.

`$ARGUMENTS` may hold a time budget in minutes (default 30) or upgrade ids to do only those.

---

## Step 1: The plan

```bash
python3 tools/profile_upgrades.py --plan
```

A JSON list, most urgent first: `id`, `needs`, `why` (what is missing), `run` (what does
it), `gives`, `time`. Keep the `needs: "you"` entries aside for Step 5. An empty list while
the sync said upgrades are pending means another chat brought the update in and is
applying them: stop here, with nothing to report.

## Step 2: Each upgrade, alone, in order

For each `needs: "nobody"` entry, until the budget is spent:

0. `python3 tools/profile_upgrades.py --check <id>` first: an upgrade done earlier in this
   list can have done this one too (`boards` and `method-boards` both run the boards
   section). If it prints `done`, skip it.
1. Do its `run` on its own: the `/setup` section it names, run alone on the existing
   profile (setup.md, "Run for a profile upgrade"); `/add-portal`; or the edit it
   describes. Touch nothing else in the profile.
2. **Never ask the person.** Every answer comes from `profile/01-candidate-profile.md`,
   the rest of the profile and research you cite. Where `/setup` would ask, choose what
   the profile supports and say so in the commit message. What you cannot ground, write
   as `[CONFIRM: <the question>]` where the value goes: the session asks it at the end
   (the `unconfirmed-facts` upgrade), so nothing is ever guessed.
3. Keep to every rule `/setup` and `/add-portal` keep: robots.txt decides which boards
   are built, nothing personal goes into an app-owned file, research is cited.
4. If its `run` ends with `python3 tools/build_versions.py record <name>` (the
   `method-*` upgrades: a part of the build the app now does better), run that once it is
   redone. A redo keeps what is there and adds what the current method adds; a value it
   would change goes beside the old one as `[CONFIRM: ...]`. Then check it: `python3 tools/profile_upgrades.py --check <id>` must
   print `done`. If it does not, undo what you changed for it and record why.
5. Commit only what this upgrade changed, on its own:
   `Profile upgrade: <id>` as the subject, one line saying what was written as the body.
   Profile files take a plain `git add`; force-add only what CLAUDE.md's persistence rule
   says to.

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

1. One line per upgrade applied: what it changed, its commit, and `undo: git revert <sha>`.
2. One line per upgrade skipped or undone, and why.
3. The questions for the person: each `needs: "you"` entry's `ask`, word for word, and
   every `[CONFIRM: ...]` now in the profile (`python3 tools/profile_upgrades.py --check
   unconfirmed-facts` lists them), as plain questions. Never their `steps` or `why_ask`:
   the session gives a question's steps only after a yes and its reason only after "why?".
4. The branch these commits are on, if it is not the session's own.

The session merges the branch, gives the person the lines from 1 at the end of its reply,
and asks at most three of the questions from 3, each short and alone: no list of ids, no
version numbers, no paragraph. A yes brings that question's steps (five lines at most); a
"why?" brings its one-sentence reason; a no gets "No problem, I'll ask again in a month."
and `python3 tools/profile_upgrades.py --no <id>`. Answers go into the profile where their
markers were, committed like any other profile change.
