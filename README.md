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
       alt="A walk through your page: the Brief, To do, Jobs and Drafts, Contacts and Messages, Interviews, then an interview prep opened">
  <br>
  <sub>A walk through your page, with an invented search on it. Every name is made up.</sub>
</p>

## What you need

- A GitHub account (free).
- A paid Claude plan, which comes with Claude Code: your search runs in its cloud chats.
  - Another agent tool (ChatGPT Codex, Google's Gemini CLI, the Cursor editor)? The core
    works in any agent that can read files and run commands; [AGENTS.md](AGENTS.md) covers
    the Claude Code parts.
- No coding, and nothing to install first. A phone is enough.

## Get started

1. On this page, **Use this template**, then **Create a new repository**, **Private**.
2. Open [claude.ai/code](https://claude.ai/code), connect GitHub, and install the
   [Claude GitHub App](https://github.com/apps/claude/installations/new) on your copy only.
3. Choose your copy and say **"set me up"**.

That works from a phone or any browser: everything runs in the cloud. On a computer, open your
page in the Claude desktop app once: it reads the LinkedIn profiles of people you write to,
in Claude's own browser, so each note fits them. Nothing to install beyond the app.

[START_HERE.md](START_HERE.md) has each step; [HELP.md](HELP.md) helps if something goes wrong.

## What it looks like

<p align="center">
  <img src="docs/images/page-brief.webp" width="720"
       alt="The Brief: today's interview, the next three things to do, who is waiting on you, the best new jobs, news and your numbers">
  <br>
  <sub><b>The Brief</b>, your home screen: the day at a glance</sub>
</p>

<p align="center">
  <img src="docs/images/page-contacts.webp" width="62%"
       alt="Contacts on a computer: who needs you first, with Claude working in the background">
  &nbsp;
  <img src="docs/images/page-interviews-phone.webp" width="18%" alt="Interviews on a phone">
  <br>
  <sub><b>Contacts</b> on a computer: who needs you first &nbsp;·&nbsp; <b>Interviews</b> on a phone: what is coming up</sub>
</p>

## What you do on your page

You tap; Claude does the work in the background and shows how far it has got.

| You tap | You get |
|---|---|
| Open your page | **The Brief**: today, the next three steps, who is waiting on you, the best new jobs, news for your search, your numbers |
| **Find jobs** | New jobs, each scored 0 to 100 against you, with the reasons |
| **Draft this** on a job you like | A resume and cover letter written for that job, checked |
| **Add a job** (paste a link or the posting) | The same, for a job you found yourself |
| **Find people** | People worth talking to at the employers you want, and a first note for each. You send it |
| **To do** | What needs you, five at a time: replies and follow-ups that are due, drafted for you |
| **I heard back**, or **Got a message?** | The record updated, a reply drafted, and what to do next |
| **Prepare me** on an interview | Likely questions, your best answers and questions to ask |
| **Tweak** on anything Claude made | A change of look, length or tone |
| The **bin** on anything | It goes, and you say why once: the next search or note learns |
| The **bell** on your Brief | A short note each morning: what is due, and news for your search |

Anything else, ask in **Chat** on the page. No resume yet? Say "build one with me" there. It
never asks for your email: everything reaches you on your page.

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
  and drafts the nudge. A short note each morning, on from the start: what you owe, what
  changed and the next three things to do (the bell on your Brief changes it).
- **One chat does the work.** Your page is answered by one chat, which also writes the brief
  and runs long jobs inside itself. The app never starts chats by itself, and old ones from
  earlier versions tidy themselves away, with nothing in them lost.
- **It checks its own work.** Every resume is compiled, read back and checked the way an
  applicant tracking system reads it, and every claim against what you told it.
- **It remembers.** Applications, conversations and what is due live in files in your copy,
  not in a chat that ends.
- **It learns what you like.** Tweak a note, or bin a job and say why, once, and it sticks. It also notices which messages got replies and which applications got interviews.
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
| The morning brief and scheduled searches | [automation/README.md](automation/README.md) |
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
