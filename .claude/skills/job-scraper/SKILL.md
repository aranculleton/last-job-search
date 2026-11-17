---
name: scrape
description: >
  Finds new job postings matching your profile via installed portal-search CLIs
  (LinkedIn, freehire, local job boards, and any skills added with /add-portal; whichever
  are on, per tools/portals.py) and employer ATS boards. Deduplicates
  across runs. Triggers on: job scrape, find jobs, search jobs, new jobs, job search,
  scrape jobs, /scrape
allowed-tools: Read, Write, Edit, Glob, Grep, Bash(bun --version), Bash(bun run .agents/skills/*/cli/src/cli.ts *), WebFetch, WebSearch, Agent, AskUserQuestion
---

# Job Scraper

The card a chat runs a search from: the one command, what it prints and what to pass on, and
where to stop. Why each rule is what it is, and where the code keeps it, is `rules.md` beside
this file: read it only when changing the round or when the person asks why.

**How a round scores: by rule, with no model.** `run_round.py` spends no model tokens (its log
says "0 model tokens" at each stage): the search's free gates (age, place, title, language),
the stated-fact screen, fit (`fit.py`: would they call back) times opportunity
(`opportunity.py`: how good the job is) for the order, the rules a posting decides, and one
role per employer. The score shown is the fit, 0-100. Say it that way, never as model-scored or
checked, and never score the list again with a model or `/rank`. The model-tiered path is
`manual-round.md`, for when the round cannot run.

## The rules every search keeps

- **When the user asks to run a job search, scan, or scrape, run the search end to end and stop at the ranked shortlist.**
- **Rank down, do not cut.** A missing skill, a year of experience, a preferred degree or a range under target lowers a score; the role still surfaces.
- **Only these are hard cuts**, each on the sentence it was cut on: an eligibility bar, a language, a place the person cannot work in, a professional credential, a different discipline, internal applicants only, and a stated range topping out below `SALARY_CUT_BELOW`.
- **A posting with no stated salary is not penalized.**
- **Every posting presented, and every posting documents are drafted for, carries a clickable apply link.**
- **Yield target: at least 5 postings scoring 60+, of which 2 score 75+.** `--expand` widens, up to 3 rounds. Never pad a thin run with sub-60 postings, and never relax a gate or the location filter to hit the number.
- **Stop there and ask** which ones to take forward. Draft nothing unasked.
- **Before drafting anything, confirm the user has not already applied.** The tracker knows only what was made through this repo.
- Never present a posting that no search or page returned.

## One command

`python3 tools/run_round.py` runs every stage in order and stops at the ranked shortlist, searching the person's own window (`JOB_AGE_DAYS`; pass `--jobage <days>` only when they ask for another window for this one search: the round's first line says which it used). Leave `--out` off: the round names itself and prints its folder (`round: r12, its files in ...`). See `RUNBOOK.md`, step 1. The options a chat uses:

- `--table`: asked in the chat, end by printing the counts line and the table (Step 5).
- `--show <N>`: the number asked for; a round that finds fewer checks itself and searches wider.
- `--employers "A, B, C"`: only these employers, their own job sites and searches by their names; pass on the line naming any with no open roles.
- `--recut --out <the round's folder> --show <N>`: cut the round again, searching nothing, after a ruling or a judgement.
- `--fresh`: ask every site again. A round run again within a few hours reuses what the sites answered.

**Employers nobody has judged are judged inside the round, before anything is passed on.** Where the round prints `unjudged:`, start the `employer-judge` agent (it runs on the small model, in the background) with the brief the line names, then run `python3 tools/run_round.py --recut --out <the round's folder> --judged` (with `--table` and `--show <N>` as before): it waits for the agent's answer for at most three minutes, keeps each judgement for good and cuts again. Pass on that cut, not the first. An employer still unjudged ranks below judged ones; when the agent's answer comes after the wait, `--recut --out <the round's folder>` once more takes it.

**Asked in a chat, the search is on the page's work list first, as its own card**, so the person sees it start, go and finish (asked on the page, its item is there already). Before the round: `python3 tools/app.py ask "$D" --kind search --title "<a few plain words>" --here --chat <your chat id>` (`work` and `holds` read into `$D` first; over an older read it names the read to make, then run it again), and send its batch. Give the round its id (`--work <its id>`), pin it while it runs (`python3 tools/app.py pin "$D" --work <its id> --chat <your chat id> --stage scrape --log <the round's folder>/round.log`, every ten minutes or so), and end with `app.py done "$D" --work <its id> --summary "<one sentence>"` once the shortlist is saved. A people search asked with it is a second ask, its own card (`/network`), never one busy line for both.

**Exit codes.** 0: the target was met. 2: missed, or not a full picture (a site down, employer job sites not read): pass on what it says, never as a thin market. 1: a stage broke: say so plainly, never paper over it.

**Pass on, as printed:** the counts line and the table; `shortlist: found N of M asked for`; `left out: N ...`; each `portal health: <site> DOWN` line; the `employer job sites not read: ...` line; and anything under "Tell the person, in these words". `/scrape health` probes the sites only (`manual-round.md` Step 4.75).

### Step 5: Present Results

On the person's page first (CLAUDE.md, "Every output is shown"): the round reaches Jobs through `python3 tools/app.py view`. Asked in the chat, or where there is no page, the chat shows it in full too: one line of counts, then the table, then a line only for what is off. Asked on the page, the chat says only the counts line and where it is.

**The round prints the table; never build it from the JSON.** Run it with `--table` (`python3 tools/run_round.py --table`; `--recut --out <the round's folder> --table` prints it again). It prints the counts line and the table, columns `# | Score | Verdict | Title | Company | Location | Salary | Deadline | Check | Apply`, warm routes already in Check: pass both on exactly as printed, and under them the line `python3 tools/what_works.py brief search` prints when it reports a clear difference (whether the scores have been predicting interviews). The cut fills the number asked for from the next rows that pass every rule, and what it rules out is off the page already. A row that fails a rule the round could not see: `python3 tools/exclude.py add <url> --title "<title>" --company "<company>" --reason "<why>"`, then `--recut`; never drop a row from the table by hand.

A line under it only when something is off: `skipped (disabled): <sites>`; `fallback (websearch): <sites>` when results came from the search fallback (omit the line when every portal ran its CLI); `health: <site> - <what>` for a site found broken, then offer to switch it off (`PORTALS` in `profile/search.py` for LinkedIn or freehire, `enabled: false` in a person's own site's `SKILL.md`), only on their yes.

### Step 5.5: Stop at the shortlist

Unless they asked for every job drafted as it is found (`args.draft`), ask once:
> "Which of these should I take forward? And have you already applied to any of them?"

A yes to the second is recorded with `python3 tools/confirm.py applied` (`--new --company --role --url --on <date> --source chat` for one the tracker never had), and its lines shown to them. Each pick goes to `/apply`, named by its row's employer and title (`Employer::title words`), never by number alone. Do not suggest `/rank` after a round: it is for scoring again after a profile change (`/rank --all`) or a backlog added by hand.

### Step 6: Update Tracker (Optional)

`/apply` writes the tracker row (job-application-assistant Step 3b): do not add a second row here. Only for an application made outside that path, add one as `/outcome` Step 1 says.

## A board the chat cannot reach, and a round that comes back thin

- **A job board the session cannot reach** may be blocked by the chat's cloud settings: check `curl -sS "$HTTPS_PROXY/__agentproxy/status"` for `connect_rejected`. That is a policy denial, not a bug: do not route around it. Tell the person what `python3 tools/env_check.py --say` prints, word for word (a round prints the same under "Tell the person"). Until it is fixed, run no search: a web search in its place finds old, closed jobs. `/apply <pasted posting text>` still works.
- **And it keeps going without being asked.** A thin round, a good posting from a board not covered, an employer with no board on file, a gate that cuts wrongly for their market: propose the fix, do the research (`/add-portal` after checking robots.txt; `tools/ats_boards.py --find "<Employer>"`), and record it in `profile/`, cited.
