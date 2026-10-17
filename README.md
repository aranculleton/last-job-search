# last-job-search

**The last job search tool you'll ever need.** Claude finds jobs that fit you, scores each one,
writes and checks a resume and cover letter for the ones you choose, finds the people worth
talking to and drafts what to say, keeps track of every application and conversation, reminds
you when to follow up, and gets you ready for interviews. It never sends anything. You stay in
charge of what goes out.

> **Find jobs** → **score each one** → **you choose** → **write and check** → **find the people** → **follow up**

[![CI](https://github.com/aranculleton/last-job-search/actions/workflows/ci.yml/badge.svg)](https://github.com/aranculleton/last-job-search/actions/workflows/ci.yml)

## What you need

- A GitHub account (free).
- Claude Code, which comes with a paid Claude plan. On your own computer an Anthropic API
  key works instead and you pay only for what you use, often cheaper if you search now and
  then, but the scheduled brief and cloud chats need a plan.
  - Another agent tool (Codex, Gemini CLI, Cursor)? The core works in any agent that can
    read files and run commands; [AGENTS.md](AGENTS.md) covers the Claude Code parts.
- About fifteen minutes. No coding.

## Get started

1. Click the green **Use this template** button, then **Create a new repository**. Tick
   **Private**. Your copy will hold your work history and the names of people you talk to.
   **Never fork it**: a fork of a public repository is public.
2. Connect GitHub to Claude at [claude.ai/connect-github](https://claude.ai/connect-github),
   and give it access to your new copy only.
3. Open [claude.ai/code](https://claude.ai/code), choose your copy, and say **"set me up"**.

Claude asks you plain questions about yourself and does the rest. [START_HERE.md](START_HERE.md)
has the full walk-through, and the steps for running it on your own computer instead.

## What you can say to it

| You say | You get |
|---|---|
| "Find me jobs" | A scored shortlist with links, then a question: which ones? |
| A job posting, pasted or linked | A resume and cover letter written for that job, checked |
| "Who should I talk to at Acme?" | People worth contacting there, and a first note to send |
| "What do I owe?" | Replies and follow-ups that are due |
| "Prep me for my interview at Acme" | Likely questions, your best answers and questions to ask |
| "They replied" or "I got an interview" | The record updated, and what to do next |
| "Check my email" | Interview invites, offers and rejections from Gmail, recorded once you say yes |
| "Make me a dashboard" | One page showing every application and how far it got |

It also says what to learn next, copies your pipeline into Notion, reads your LinkedIn job
alerts and takes your own resume template. Gmail and Notion are connected once, at
[claude.ai/customize/connectors](https://claude.ai/customize/connectors).

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
  and drafts the nudge. Say "set up my brief" and what you owe, what changed and the next
  three things to do arrive in one message, twice a week.
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
| The rules Claude follows, and the command map | [CLAUDE.md](CLAUDE.md) |
| Daily briefings and scheduled searches | [automation/README.md](automation/README.md) |
| Scoring rubric, writing style, cost model | [`.claude/skills/job-application-assistant/`](.claude/skills/job-application-assistant/) |
| Reporting a bug or suggesting something | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Working on the app itself | [MAINTAINING.md](MAINTAINING.md) |

Searching, filtering and scoring are plain Python and Bash, so a search reads thousands of
postings without using the model. The model starts only when you pick what to write. Over
1,200 tests run in CI and through `./tools/ci_local.sh`. The employer-board reader is also
published as [openroles](https://github.com/aranculleton/openroles).

## Credits and licence

Built on [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search) (v1.7.0
plus the commits through PR #413), which supplied the LaTeX scaffolding, the job-board CLI
pattern, the skills-and-commands layout and the drafter-reviewer idea. Everything before the
shortlist, the bullet allocator, the checks and the networking layer were built here.

MIT. [LICENSE](LICENSE) carries both copyrights. Not affiliated with Anthropic.
