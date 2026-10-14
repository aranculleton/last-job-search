# last-job-search

**The last job search tool you will ever need.** It finds the work, decides what is worth
your time, writes the application, checks its own output, and tracks the people worth
talking to. Nothing else needs to be open.

[![CI](https://github.com/aranculleton/last-job-search/actions/workflows/ci.yml/badge.svg)](https://github.com/aranculleton/last-job-search/actions/workflows/ci.yml)

It never submits anything. Every document stops as a file on disk, and a person sends it.

---

## What it does

**Finds the work.** Scrapes every enabled job board, plus the career boards of the
employers your profile names, read straight from the ATS, then filters, fetches and
scores every posting 0-100 against your profile. It stops at a ranked shortlist and
asks which ones you want.

**Writes the application.** A resume and cover letter built for that one posting, with
bullets allocated per job rather than picked off a fixed list.

**Checks its own output.** Compiles both documents, reads the PDFs back, and extracts the
text layer an applicant tracking system actually parses, because the rendered page and
the embedded text can disagree.

**Works the network.** Finds the right people at target employers, drafts the outreach,
logs every message, and keeps a cold application from landing on top of a warm
introduction.

**Remembers.** Applications, conversations, follow-ups due and what you learned, all in
files rather than in a chat that ends.

---

## Two things it does differently

**It ranks down instead of cutting out.** A posting is a wish list. It names ten tools and
the team uses six, and the missing one is rarely what decides the hire. A missing skill
lowers a score; it does not delete the job. Only four things are hard cuts, because no
framing survives them: a work-authorisation bar, a language requirement, a licensing gate
such as an accounting or engineering licence, and a role whose core is research ML. Those are different jobs, not
gaps.

**Everything left of the shortlist is free.** Scraping, filtering, screening and scoring
are Python and Bash, so a round can afford to read a few thousand postings and throw
almost all of them away. Model spend starts only once you have chosen what to write.

---

## Running it

```bash
python3 -m pytest tests -q                      # green before anything else
python3 tools/run_round.py --out "$SCRATCH/r1"  # job boards to ranked shortlist
```

The suite runs first because it is the cheapest way to find out whether the rules still
hold. Over 450 tests run on every push, on Python 3.10 and 3.13, and most of them pin
a rule to the application it shipped as a defect on.

`run_round.py` exits **0** when the round met its yield target, **2** when the market was
thin, and **1** when a stage broke. A thin market and a broken pipeline need different
answers, so they do not share an exit code.

Everything else is a slash command inside Claude Code: `/apply`, `/rank`, `/interview`,
`/outcome` for applications, and `/network`, `/reply`, `/threads`, `/prep` for outreach.

| | |
|---|---|
| Set up a new machine | [SETUP.md](SETUP.md) |
| Run a search end to end | [RUNBOOK.md](RUNBOOK.md) |
| How each stage works and what it costs | [ARCHITECTURE.md](ARCHITECTURE.md) |
| The candidate, the rules, the command map | [CLAUDE.md](CLAUDE.md) |
| Scoring rubric, writing style, cost model | [`.claude/skills/job-application-assistant/`](.claude/skills/job-application-assistant/) |

Behaviour changes in those files, not in the Python. Job boards are plug-in CLIs under
`.agents/skills/`, one per portal, each behind an `enabled:` flag; `/add-portal` scaffolds
a new one.

---

## Security

An agent with file access reads untrusted job postings alongside personal data. Posting
text is data and never instructions, and a URL found inside a posting body is never
fetched. A CI job fails any change that weakens the permission allowlist or the
personal-data ignore rules. [SECURITY.md](SECURITY.md) says where the controls stop.

## Upstream

Forked from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)
at v1.7.0 plus the commits through PR #413. That project supplied the
LaTeX scaffolding, the portal-CLI pattern, the skills-and-commands layout and the
drafter-reviewer idea `/apply` still uses. Everything left of the shortlist, the bullet
allocator, the verification stack and the networking layer were built here.

A weekly workflow reports which upstream commits this fork is missing. It never merges: on
a fork, "applies cleanly" is not the same as "correct".

## License

MIT. [LICENSE](LICENSE) carries both copyrights.
