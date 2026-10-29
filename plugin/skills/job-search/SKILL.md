---
name: job-search
description: Set up or open the person's job search. Use when they say "set me up", "set this up", "set up my job search", "open my job search", "job search", "my page", or hand over the link github.com/aranculleton/last-job-search with any request to set it up or start it.
---

# Your job search

This plugin is the front door. The search lives in the person's own private copy of the app
(a copy on their GitHub account) and on their private page in Claude.

**Do every step yourself. Ask nothing, offer no choices, and never say copy, repository,
branch, master, template, clone, push, empty or any git or GitHub word to the person.** The
only things that are theirs: signing in to GitHub once (step 2), and the setup questions,
which their page asks. Say one short plain line while you work, at most: "Setting up your
job search." Then the next thing they see is their page.

`APP` is `https://github.com/aranculleton/last-job-search`. Never set anyone up in the app
itself: anything written there is public, and its start command refuses.

## 1. Already here

The current folder has `tools/app.py`: go to step 5.

Otherwise look for a folder that has both `tools/app.py` and `profile/`: `~/job-search`,
`~/my-job-search`, `~/*job-search*`, `~/Documents/*job*search*`, `~/Desktop/*job*search*`.
Found one: work there, step 5. More than one: the one changed most recently.

## 2. Signed in to GitHub

`gh auth status`. Not signed in, or `gh` missing: follow COMPUTER.md in `APP`, steps 1 to 3
(it installs what is missing and signs them in with one code they type on GitHub's page).

## 3. Their copy

- Their message names one (`github.com/OWNER/NAME`): use it.
- Otherwise `gh repo list --limit 100 --json name,owner,isPrivate` and take a private one
  whose name has "job" and "search" in it.
- None: make it, private, from the app:
  `gh repo create my-job-search --private --template aranculleton/last-job-search`
  (`my-job-search-2` if the name is taken). Then wait about ten seconds: GitHub fills it.

## 4. Put it in a folder of its own

`~/my-job-search` (or the name of their copy, in their home folder), new and empty, then:

- `gh repo clone OWNER/NAME <folder>`.
- **The copy has nothing in it yet** (the clone says it is empty, or has no files): fill it
  from the app, silently, keeping the app's history so its updates merge cleanly later. In
  the folder: `git fetch -q https://github.com/aranculleton/last-job-search master`, then
  `git checkout -q -B master FETCH_HEAD`, `git push -q origin master` and
  `gh repo edit OWNER/NAME --default-branch master`. That is exactly what making it from
  the app would have given them.

## 5. Start

In that folder, `python3 tools/env_check.py --fix` in the background, then:

`python3 tools/app.py start --on "<this chat's model>" --tools "<browser tools: browser, chrome, enable, or none>"`

and do what it prints, in order. It brings in the newest version, publishes their page,
opens it, and the page asks the setup questions. From here their copy's own instructions
(its `CLAUDE.md`) take over.
