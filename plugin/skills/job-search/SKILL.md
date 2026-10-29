---
name: job-search
description: Open the person's job search page, or set it up the first time. Use when they say "open my job search", "job search", "set me up", "start my job search", "my page", or anything about their job search outside its own folder.
---

# Your job search

This plugin is only the front door. The search itself lives in the person's own private
copy of last-job-search (a repository on their GitHub account) and on their private page in
Claude. Find their copy, hand over to it, and say as little as possible: plain words, one
line a step, never a command, a folder name or a git word.

## 1. Inside their copy already

When the current folder has `tools/app.py` and `profile/`, run, as its own command:

`python3 tools/app.py start --on "<this chat's model>" --tools "<browser tools: browser, chrome, enable, or none>"`

and do what it prints, in order. It opens or refreshes their page and says where setup
stands. From here the copy's own instructions (its `CLAUDE.md`) take over.

## 2. Their copy is on this computer somewhere else

Look, in this order, for a folder holding both `tools/app.py` and `profile/`:
`~/job-search`, `~/my-job-search`, `~/last-job-search*`, `~/Documents/*job*search*`,
`~/Desktop/*job*search*`. Found: work there (step 1). Found more than one: the one changed
most recently.

## 3. No copy yet: set one up

Their copy is private and theirs; never use the public app itself (anything about a person
written there would be public, and its start command refuses).

1. When `gh auth status` succeeds: `gh repo create my-job-search --private --template
   aranculleton/last-job-search --clone` in their home folder, then step 1 in
   `~/my-job-search`. Setup runs on the page from there.
2. Otherwise give them these steps, word for word, then wait for them:
   1. Open github.com/new?template_owner=aranculleton&template_name=last-job-search&owner=%40me&name=my-job-search&visibility=private
      signed in to GitHub, and choose Create repository. Keep it Private.
   2. Come back here and say "done".
   Then clone it (`git clone https://github.com/<their GitHub name>/my-job-search.git
   ~/my-job-search`; git asks them to sign in to GitHub the first time) and do step 1.

The twice-weekly brief and phone use need the copy in Claude's cloud too: once setup is
done on the page, the start command walks them through it.

## Never

- Never run the job search from the plugin's own folder or from the public app.
- Never ask them which command to run, and never show one.
