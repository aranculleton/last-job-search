# Start here

Claude runs your job search: it finds and scores postings, writes and checks a resume and
cover letter for the ones you pick, and helps you reach the right people. It never sends
anything; you do. You need a GitHub account (free) and a paid Claude plan. No coding, and
nothing to install first: a phone is enough. Another agent tool? See [AGENTS.md](AGENTS.md).

## 1. Make your own private copy

<!-- claude-surface: make-copy -->
<!-- checked 2026-10-25;
https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository
-->
To make your own private copy:
1. Open this link, signed in to GitHub:
   github.com/new?template_owner=aranculleton&template_name=last-job-search&owner=%40me&name=my-job-search&visibility=private
   A phone's web browser works too.
2. It opens with the job search as the template and Private chosen. Check Private, then
   choose Create repository.
3. If the form opens empty: on github.com/aranculleton/last-job-search, choose Use this
   template, then Create a new repository, choose Private, then Create repository from
   template.

Screens change: if yours looks different, tell Claude what you see.
<!-- /claude-surface -->

Never fork it instead: a fork of a public project is public.

## 2. Let Claude see it

<!-- claude-surface: connect-github -->
<!-- checked 2026-10-25; https://code.claude.com/docs/en/web-quickstart -->
To let Claude see your copy:
1. Open claude.ai/code and sign in. When it asks to connect GitHub, follow it and approve.
2. Open github.com/apps/claude/installations/new, choose your account, then Only select
   repositories, pick your copy, and install.
3. Back at claude.ai/code (or the Code tab in the Claude app), choose your copy under the
   message box.

Screens change: if yours looks different, tell Claude what you see.
<!-- /claude-surface -->

## 3. Say "set me up"

Claude asks two short rounds of questions, does the research itself and shows your first
shortlist: up to an hour of its time, and you can put it down meanwhile. No resume? Say
"build one with me" and Claude makes it with you, one job at a time. It ends by opening your
private page. If it says it can't reach job sites (recommended, once):

<!-- claude-surface: cloud-internet -->
<!-- checked 2026-10-25; https://code.claude.com/docs/en/cloud-environments -->
To let this chat reach job sites:
1. At the top of this chat, open the small arrow after its title and choose Edit cloud
   environment.
2. Set Network access to Full, then save. It reaches this chat within about a minute.

Screens change: if yours looks different, tell Claude what you see.
<!-- /claude-surface -->

## On your computer as well

Optional, for files you keep there: your page already reads LinkedIn profiles in the Claude
desktop app. The recommended way, if you want one: same copy, nothing moves, and it installs
what it needs.

<!-- claude-surface: local-chat -->
<!-- checked 2026-10-25; https://code.claude.com/docs/en/desktop-quickstart -->
To set up a chat on your computer:
1. Install the Claude desktop app from claude.ai/download (it has a Mac and a Windows
   installer) if you do not have it, and sign in.
2. Open its Code tab. Under the message box choose Local, then Open folder, and make a new,
   empty folder for your search.
3. If the mode menu under the message box offers Auto, choose it: Claude then asks you far
   less.
4. Paste this there: Open my job search on this computer. My copy is
   github.com/YOUR-NAME/YOUR-COPY. Follow
   github.com/aranculleton/last-job-search/blob/master/COMPUTER.md

Screens change: if yours looks different, tell Claude what you see.
<!-- /claude-surface -->

On Linux:

<!-- claude-surface: linux-computer -->
<!-- checked 2026-10-25; https://code.claude.com/docs/en/desktop-linux -->
Use Claude on a Linux computer: on Ubuntu or Debian, the Claude desktop app; elsewhere, in a
terminal, curl -fsSL https://claude.ai/install.sh | bash, then claude --chrome in the folder
of your copy.
<!-- /claude-surface -->

## Then use your page

Setup ends by opening it. Tap **Find jobs**, **Draft this** on a job you like, **Find people**,
and **I heard back** when you do; tweak or bin anything that's off, and it remembers. Anything
else, ask in **Chat** there. Updates arrive by themselves; nothing of yours is sent back.

If something goes wrong, see [HELP.md](HELP.md), or tell Claude what you see.
