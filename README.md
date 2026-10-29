# last-job-search

**The last job search tool you'll ever need.** Claude finds jobs that fit you, scores each one,
writes and checks a resume and cover letter for the ones you choose, finds the people worth
talking to and drafts what to say, keeps track of every application and conversation, reminds
you when to follow up, and gets you ready for interviews. It all happens on one private page
that Claude keeps up to date: you tap, and Claude does the work. It never sends anything. You
stay in charge of what goes out.

> **Find jobs** → **score each one** → **you choose** → **write and check** → **find the people** → **follow up**

[![CI](https://github.com/aranculleton/last-job-search/actions/workflows/ci.yml/badge.svg)](https://github.com/aranculleton/last-job-search/actions/workflows/ci.yml)

<p align="center">
  <img src="docs/images/page-demo.webp" width="720"
       alt="Your page: what needs you, the jobs worth a look, your drafts, your contacts and your interviews">
  <br>
  <sub>Your page, with an invented search on it. Every name is made up.</sub>
</p>

## What you need

- A GitHub account (free).
- Claude Code, which comes with a paid Claude plan. On your own computer an Anthropic API
  key works instead and you pay only for what you use, often cheaper if you search now and
  then, but the scheduled brief and cloud chats need a plan.
  - Another agent tool (ChatGPT Codex, Google's Gemini CLI, the Cursor editor)? The core
    works in any agent that can read files and run commands; [AGENTS.md](AGENTS.md) covers
    the Claude Code parts.
- No coding, and nothing to install first. A phone is enough.

## Get started

1. Make your own private copy: on this page, **Use this template**, then **Create a new
   repository**, with **Private** chosen. Never fork it: a fork is public.
2. Open [claude.ai/code](https://claude.ai/code), connect GitHub when it asks, and install the
   [Claude GitHub App](https://github.com/apps/claude/installations/new) on your copy only.
3. Choose your copy and say **"set me up"**. Claude asks a few plain questions, does the
   research and opens your page with your first shortlist on it.

[START_HERE.md](START_HERE.md) has each step for a phone, a browser or a computer, and
[HELP.md](HELP.md) what to do if something goes wrong.


## What it looks like

<p align="center">
  <img src="docs/images/page-contacts.webp" width="62%"
       alt="Contacts on a computer, in the dark look: who is waiting on whom, with Claude working in the background">
  &nbsp;
  <img src="docs/images/page-interviews-phone.webp" width="18%" alt="Interviews on a phone">
  <br>
  <sub><b>Contacts</b> on a computer: who is waiting on whom &nbsp;·&nbsp; <b>Interviews</b> on a phone: what is coming up</sub>
</p>

## What you do on your page

Tap, or say it in any chat. Claude does the work in the background and shows its progress.

| You do | You get |
|---|---|
| **Search again** | New jobs, each scored 0 to 100 against you, with the reasons |
| **Draft** on a job you like | A resume and cover letter written for that job, checked |
| **Add a job** (paste a link or the posting) | The same, for a job you found yourself |
| **Prepare** on an interview | Likely questions, your best answers and questions to ask |
| **Contacts** | People worth talking to at the employers you want, and a first note for each. You send it |
| **To do** | Replies and follow-ups that are due, drafted for you |
| **Tweak** on anything Claude made | A change of look, length or tone, before you approve it |
| "They replied" or "I got an interview" | The record updated, and what to do next |

No resume yet? Say "build one with me". It never asks for your email: new jobs and what is
due reach you on your page and in your twice-weekly brief.

## On a computer: open it from any chat (optional)

The app also comes as a Claude Code plugin: a front door, not a second copy. Installed on your
computer, "open my job search" in any chat there opens your page, and the first time it makes
your private copy for you. Your search still lives in your own private copy, which keeps
itself up to date; the plugin only finds it. Chats in the cloud and on a phone do not load
plugins, and do not need it.

<!-- claude-surface: plugin-install -->
<!-- checked 2026-10-28; https://code.claude.com/docs/en/discover-plugins -->
To open your job search from any chat on your computer:
1. In Claude Code on your computer (the Claude desktop app's Code tab, or a terminal), type:
   /plugin install last-job-search --marketplace aranculleton/last-job-search
2. When it asks where to install it, choose your user account.
3. From then on, say "open my job search" in any chat on that computer.

Screens change: if yours looks different, tell Claude what you see.
<!-- /claude-surface -->

## Why it works differently

- **It ranks, it does not hide.** A job advert is a wish list. A missing skill lowers a score;
  it does not throw the job away. Only a few things rule a job out, such as needing a right to
  work you do not have, or a language you do not speak. Rulings based on your rules are
  re-checked when the rules change; ones in your own words stay until you change your mind.
- **It works your network, not just the job boards.** It looks where people in your field
  are actually named (team pages, meetups, speaker lists, alumni), says in a line why each
  person is worth writing to, and writes every message in the shape that suits them: the first
  note (which asks for a conversation, not a job), the replies and the referral ask. It tracks
  every thread and warns you before a cold application lands on top of a warm introduction.
- **It reminds you.** When a follow-up is due, on an application or a conversation, it says so
  and drafts the nudge. Setup ends by making your brief: what you owe, what changed and the
  next three things to do, in one message, twice a week.
- **It checks its own work.** Every resume is compiled, read back and checked the way an
  applicant tracking system reads it, and every claim against what you told it.
- **It remembers.** Applications, conversations and what is due live in files in your copy,
  not in a chat that ends.
- **It learns what you like.** Say "too formal" or "stop suggesting recruiters" once, and it
  sticks. It also notices which messages got replies and which applications got interviews.
- **It keeps itself up to date.** Each release reaches your copy by itself the next time you
  use it, even in a chat kept open for weeks. Nothing about you is ever sent back.

## Your data and security

Everything about you stays in your private copy, and nothing is submitted for you: every
document stops as a file, and you send it. Job postings are written by strangers, so their text
is treated as data, never as instructions, and a link inside one is never opened. A check
fails any change that weakens the permission allowlist or lets personal files into the app.
[SECURITY.md](SECURITY.md) has the details.

## For the technically curious

You never need any of this to use it.

| | |
|---|---|
| Set up a computer or a cloud environment by hand | [SETUP.md](SETUP.md) |
| What a search does, step by step | [RUNBOOK.md](RUNBOOK.md) |
| How each stage works and what it costs | [ARCHITECTURE.md](ARCHITECTURE.md) |
| The rules every chat follows, and where every other rule lives | [CLAUDE.md](CLAUDE.md) |
| The twice-weekly brief and scheduled searches | [automation/README.md](automation/README.md) |
| Scoring rubric, writing style, cost model | [`.claude/skills/job-application-assistant/`](.claude/skills/job-application-assistant/) |
| Reporting a bug or suggesting something | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Working on the app itself | [MAINTAINING.md](MAINTAINING.md) |

Searching, filtering and scoring are plain Python and Bash, so a search reads thousands of
postings without using the model. The model starts only when you pick what to write. The
tests run in CI on macOS and Linux, and on any copy through `./tools/ci_local.sh`. The
employer-board reader is also published as [openroles](https://github.com/aranculleton/openroles).

## Credits and licence

Built on [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (v1.7.0
plus the commits through PR #413), which supplied the LaTeX scaffolding, the job-board CLI
pattern, the skills-and-commands layout and the drafter-reviewer idea. Everything before the
shortlist, the bullet allocator, the checks and the networking layer were built here.

MIT. [LICENSE](LICENSE) carries both copyrights. Not affiliated with Anthropic.
