# last-job-search

**The last job search tool you'll ever need.** Claude finds jobs that fit you, scores each one,
writes and checks a resume and cover letter for the ones you choose, finds the people worth
talking to and drafts what to say, keeps track of every application and conversation, reminds
you when to follow up, and gets you ready for interviews. It never sends anything. You stay in
charge of what goes out.

[![CI](https://github.com/aranculleton/last-job-search/actions/workflows/ci.yml/badge.svg)](https://github.com/aranculleton/last-job-search/actions/workflows/ci.yml)

## What you need

- A GitHub account (free).
- Claude Code. It has no free tier: you need a Claude subscription or, running it on your own
  computer, Anthropic API credits (pay as you go, often cheaper if you only use it now and then).
- About fifteen minutes. No coding.

Using a different agent tool (Codex, Gemini CLI, Cursor, Antigravity)? Start at
[AGENTS.md](AGENTS.md). It is built for Claude Code, but the search, scoring, documents,
checks and tracking are plain Python and written procedures that any agent which can read
files and run commands can follow. A few extras, such as the scheduled daily brief, are
Claude-only.

## Get started

1. Click the green **Use this template** button, then **Create a new repository**. Tick
   **Private**. Your copy will hold your work history and the names of people you talk to.
   **Never fork it**: a fork of a public repository is public.
2. Connect GitHub to Claude at [claude.ai/connect-github](https://claude.ai/connect-github),
   and give it access to your new copy only.
3. Open [claude.ai/code](https://claude.ai/code), choose your copy, and say **"set me up"**.

Claude asks you plain questions about yourself and does the rest. The full walk-through, with
the one setting to paste in the first time, is [START_HERE.md](START_HERE.md).

## What you can say to it

| You say | You get |
|---|---|
| "Find me jobs" | A scored shortlist with links, then a question: which ones? |
| A job posting, pasted or linked | A resume and cover letter written for that job, checked |
| "Who should I talk to at Acme?" | People worth contacting there, and a first note to send |
| "What do I owe?" | Replies and follow-ups that are due |
| "Prep me for my interview at Acme" | Likely questions, your best answers and questions to ask |
| "They replied" or "I got an interview" | The record updated, and what to do next |

## Why it works differently

- **It ranks, it does not hide.** A job advert is a wish list. A missing skill lowers a score;
  it does not throw the job away. Only a few things rule a job out, such as needing a right to
  work you do not have, or a language you do not speak.
- **It works your network, not just the job boards.** It finds former colleagues, fellow
  alumni and the right people at each employer, and writes every message: the first note
  (which asks for a conversation, not a job), the replies and the referral ask. It tracks every
  thread and warns you before a cold application lands on top of a warm introduction.
- **It reminds you.** When a follow-up is due, on an application or a conversation, it says so
  and drafts the nudge. Set up a daily brief and what you owe arrives on your phone each morning.
- **It checks its own work.** Every resume is compiled, read back, and checked the way an
  applicant tracking system reads it, and every claim is checked against what you told it.
- **It remembers.** Applications, conversations and what is due live in files in your copy,
  not in a chat that ends.
- **It learns what you like.** Say "too formal" or "stop suggesting recruiters" once, and it
  sticks. It also notices which messages got replies and which applications got interviews.
- **It keeps itself up to date.** Improvements to this app reach your copy by themselves at
  the start of a session. Nothing about you is ever sent back.

## Your data

Everything about you stays in your private copy, in the `profile/` folder and a few files
beside it. Nothing is submitted for you: every document stops as a file, and you send it.

## Security

The assistant reads job postings written by strangers next to your personal data. Posting text
is treated as data, never as instructions, and a link found inside a posting is never opened.
A check fails any change that weakens the permission allowlist or the rules that keep personal
files out of the app. [SECURITY.md](SECURITY.md) says where those controls stop.

## For the technically curious

You never need any of this to use it.

| | |
|---|---|
| Set up a computer or a cloud environment by hand | [SETUP.md](SETUP.md) |
| What a search does, step by step | [RUNBOOK.md](RUNBOOK.md) |
| How each stage works and what it costs | [ARCHITECTURE.md](ARCHITECTURE.md) |
| The rules Claude follows, and the command map | [CLAUDE.md](CLAUDE.md) |
| Daily briefings and scheduled searches | [automation/README.md](automation/README.md) |
| Scoring rubric, writing style, cost model | [`.claude/skills/job-application-assistant/`](.claude/skills/job-application-assistant/) |
| Reporting a bug or suggesting something | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Working on the app itself | [MAINTAINING.md](MAINTAINING.md) |

The employer-board reader is also published on its own, as the open-source library
[openroles](https://github.com/aranculleton/openroles). Scraping, filtering and scoring are Python and Bash, so a search can read thousands of
postings at no model cost; the model is used once you have chosen what to write. Over 900
tests run in the app's CI and, in your copy, through `./tools/ci_local.sh`.

## Credits and licence

Built on [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (v1.7.0
plus the commits through PR #413), which supplied the LaTeX scaffolding, the job-board CLI
pattern, the skills-and-commands layout and the drafter-reviewer idea. Everything before the
shortlist, the bullet allocator, the checks and the networking layer were built here.

MIT. [LICENSE](LICENSE) carries both copyrights. Not affiliated with Anthropic.
