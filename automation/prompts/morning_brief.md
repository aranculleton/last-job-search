# The brief (each morning once it is on; schedule: `profile/routines.json`)

One message, built around where this person's search is right now. Code gathers all of it;
your part is the news and the message. It does not search for jobs: a fresh shortlist is
one "find me jobs" away whenever they want one. **Never run a search here**, and never read
a state file, a pack or an earlier brief yourself: `tools/brief.py` has read them.

## 1. Start and gather: one command

```
git switch -c claude/ops-<YYYY-MM-DD>-morning_brief origin/master
python3 tools/brief.py --start --on "<the model this run is on>" --write
```

Each on its own, never chained (`-2` on the branch name if it exists). That is `_common.md` steps 1 to 4 and the whole
gather: the app's updates, the Python side, earlier runs' unsaved work, the follow-ups
drafted by code and checked, the preps rebuilt, the quiet applications closed, and the
day's record and pack written. It prints the message with `<NEWS>` still to fill, then the
lines **FOR CLAUDE**, which are yours alone. Where the person has a page, it prints **PAGE
FIRST** instead: do those steps (their ticks there are applied before anything is counted);
the last one prints the message. Act on each FOR CLAUDE line:

- work not saved for a day or more: as its line says;
- `/upgrade 20`: run it; one plain line per change goes at the end of the message;
- questions: at most three, as written, at the end of the message;
- employers to judge: one `bar.py judge` each, from what you know (no search needed);
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

The `news-reader` agent, given every FOR CLAUDE news line as printed. It returns three to six
lines, each ending in how the person can use it, widening rather than coming back empty.
No such agent here (a copy cloned this run loads none): a general one on haiku, its prompt
`.claude/agents/news-reader.md` below its header, then the lines. Nothing else finds the
news; if it cannot run, step 4 gives `brief.py news` nothing.

## 4. Record: one command

```
python3 tools/brief.py news <<'EOF'
<the news-reader's lines, as they came, best first, at most five; nothing if it could not run>
EOF
```

`brief.py news` puts the news in the day's record, leaves out any link an earlier brief
sent, and notes a freeze or layoffs at an employer with a live application on that row.
With a page, bring it up to date as its FOR CLAUDE line says; where a line says its code is
older than this version, republish it first: no other chat will.

## 5. The message

Your final reply: the message brief.py printed, as it is. With a page: the headline, the
lead and the link, never the Owed list, Next three or news, which the page shows. Without one, `<NEWS>` takes the lines `brief.py news` printed for the message,
without links; carried ones say their day. Never "Nothing new", "Quiet week" or any
stand-in for news. Add only what a FOR CLAUDE line asks for (an upgrade's changes, the
questions), and where step 2 put a draft in the pack, its Owed line says "draft ready".
Change a line only where you know it is wrong, and say nothing about how the brief was
made. Under 200 words, for a phone, on each of the brief's days, even when nothing is owed.

With a page, they answer there (its To do). An answer in this chat later is recorded:
`python3 tools/confirm.py applied|not-applied "<Employer>::<role>"` for an application,
`/outcome` for a result, `/reply <name>` for a reply.

## 6. Land, after the message

With the message ready, first the push a FOR CLAUDE line asks for, as it says; then the
one call before your final reply starts `python3 tools/land.py
--message "Brief <YYYY-MM-DD>"` in the background (Bash, `run_in_background`), and the
message follows at once: it goes out before anything lands. When it wakes you, `_common.md`
"Landing work".
