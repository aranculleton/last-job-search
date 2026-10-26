# The brief (twice a week; schedule: `profile/routines.json`)

One message, built around where this person's search is right now. Code gathers all of it;
your part is the news and the message. It does not search for jobs: a fresh shortlist is
one "find me jobs" away whenever they want one. **Never run a search here**, and never read
a state file, a pack or an earlier brief yourself: `tools/brief.py` has read them.

## 1. Start and gather: one command

```
git switch -c claude/ops-<YYYY-MM-DD>-morning_brief origin/master && python3 tools/brief.py --start --on "<the model this run is on>" --write
```

(`-2` on the branch name if it exists.) That is `_common.md` steps 1 to 4 and the whole
gather: the app's updates, the Python side, earlier runs' unsaved work, the follow-ups
drafted by code and checked, the preps rebuilt, the quiet applications closed, and the
day's record and pack written. It prints the message with `<NEWS>` still to fill, then the
lines **FOR CLAUDE**, which are yours alone. Where the person has a page, it prints **PAGE
FIRST** instead: do those steps (their ticks there are applied before anything is counted);
the last one prints the message. Act on each FOR CLAUDE line:

- an earlier run's work not saved: `_common.md` step 3;
- `/upgrade 20`: run it; one plain line per change goes at the end of the message;
- questions: at most three, as written, at the end of the message;
- drafts this run can write: step 2;
- the news searches: step 3.

## 2. Drafts the code could not finish (only when FOR CLAUDE lists them)

In the same turn as step 3's call: `python3 tools/followup_drafts.py context --due`. Write
each draft it lists, short, in the person's voice, answering what they said, claiming
nothing the thread or the profile does not hold, and rewriting a code draft only on what
it flagged. Then one call: `python3 tools/followup_drafts.py check - --pack` with a JSON list
`[{"id": "<contact id>", "text": "<the draft>"}]` on stdin. A draft it refuses is rewritten
once on its findings and checked again; still refused, it stays listed as needs writing.

## 3. The news: one call

The `news-reader` agent, given the searches, the since date, the links already sent and
"what counts" exactly as FOR CLAUDE printed them. It returns at most six lines or "Quiet
week.". Use nothing else for the news; if it cannot run, the news is "No news this time:
the search did not run."

## 4. Record and land: two commands

```
python3 tools/brief.py news <<'EOF'
<the news-reader's lines, as they came, best first, at most five>
EOF
python3 tools/save_state.py && git commit -qm "Brief <YYYY-MM-DD>" && set -o pipefail && ./tools/ci_local.sh --quick 2>&1 | tail -3 && git push -u origin HEAD
```

`brief.py news` puts the news in the day's record, leaves out any link an earlier brief
sent, and notes a freeze or layoffs at an employer with a live application on that row.
Then open the PR and merge it, as `_common.md` "Landing work" says. With a page, bring it up
to date as its FOR CLAUDE line says. Never publish the page or watch it.

## 5. The message

Your final reply: the message brief.py printed, as it is, with `<NEWS>` replaced by at most
three of the news lines, each one line ending in what it means for the person, with no
links (the full brief has them), or "Quiet week". Add only what a FOR CLAUDE line asks for
(an upgrade's changes, the questions), and where step 2 put a draft in the pack, its Owed
line says "draft ready". Change a line it printed only where you know it is wrong, and say
nothing about how the brief was made. Under 200 words, for a phone. It is
sent on each of the brief's days even when nothing is owed: silence is the alarm.

With a page, they answer there (its To do), and the message links it. When they answer in
this chat later, record each answer the way the line asks:
`python3 tools/confirm.py applied|not-applied "<Employer>::<role>"` for an application they
say went or did not, `/outcome` for a result, `/reply <name>` for a reply.
