# Automation: what runs on a clock

One scheduled task keeps the search moving without anyone asking: **a brief, twice a
week**. A scheduled job round is there too, for anyone who wants new postings found on a
clock, but it is off by default: "find me jobs" in any chat runs one. The instructions live
in `prompts/`, in git, so changing what a task does is a pull request and never an edit to
the task. Which tasks exist, when they run and where they report is the person's own
registry, `profile/routines.json` (`profile.example/routines.json` shows the shape).

| Task | What it delivers |
|---|---|
| **Job search: morning brief**, twice a week (Monday and Thursday suit most searches) | Led by where the search is (an interview to prep, replies owed, applications waiting, or too little going out), then what is owed with the replies and nudges drafted, the counts since the last brief, three things to do before the next one, and the news that matters. Every run also looks at the app and says once when an update is waiting; it never takes one, which waits for the person's word (`prompts/morning_brief.md`). |
| **Job search: shortlist**, optional and off by default | A scored round of new postings, best first (`prompts/job_round.md`). Reply with picks in the same chat and it drafts, verifies and records them. |

**If no brief has arrived two hours after its time on one of its days, the automation is
broken.** The brief is sent on each of its days even when nothing is due, so silence always
means something failed.
Tell any Claude chat "the scheduled tasks are down" and point it at this file.

## Set it up

**Setup makes the brief for you, and asks nothing.** At the end of `/setup` a cloud chat makes
it: its own chat, **Job search: morning brief**, on your private repo; a task bound to that
chat, Mondays and Thursdays at 7:38 your time; and one first brief a few minutes later, so you
see it work (`python3 tools/routines.py brief` prints the calls). Say "move my brief" to change
the days or the time. Anywhere it was not made, say "set up my brief" in any chat.

Two set-ups work reliably, and they trade the same thing: where the briefing arrives. Setup
makes (a).

| | (a) One chat per briefing | (b) A routine, a new chat each run |
|---|---|---|
| Where the briefing arrives | A reply in that briefing's own chat | A new chat each run |
| Push to your phone | No | Yes, where the app notifies you of the run |
| Where you reply to the shortlist | The "Job search: shortlist" chat | The chat that run opened |
| Set up from | A chat (Claude does it) | A routine (Claude, where its chat has the tool; otherwise you, once) |

Both run on **your private repo**, never on the public app: a chat on the app holds none of
your state, and anything it pushed would be public.

**From your own computer.** Say "set up my brief" there too. Claude first checks whether a
brief already exists (`python3 tools/routines.py brief`), by your registry or a task's own
prompt and never its title, so a second is never made. The brief always runs in the cloud,
so it arrives when your computer is off. Where the chat on your computer has the tool for
routines, Claude makes it itself, as (b); otherwise you make it, once:

<!-- claude-surface: routines-cloud -->
<!-- checked 2026-10-25; https://code.claude.com/docs/en/routines -->
To make the brief in the cloud:
1. Open claude.ai/code/routines and choose New task (in the desktop app's Code tab:
   Scheduled, then New task).
2. Name it Job search: morning brief, choose your copy, set it weekly at your time, paste
   the prompt I give you, and save.
3. Open it again, choose Custom, and paste the schedule I give you, so it runs on both days.

Screens change: if yours looks different, tell Claude what you see.
<!-- /claude-surface -->

A scheduled task that runs on your computer is never used for it:

<!-- claude-surface: routines-local -->
<!-- checked 2026-10-18; https://code.claude.com/docs/en/desktop-scheduled-tasks -->
A desktop scheduled task made with Local runs on the computer, and only while the desktop
app is running and the computer is awake, so it is never used for the brief.
<!-- /claude-surface -->

Claude cannot start a cloud chat from its own shell on your computer, so it never tries:

<!-- claude-surface: cli-cloud claim -->
<!-- checked 2026-10-18; https://code.claude.com/docs/en/claude-code-on-the-web -->
claude --cloud starts a cloud chat from a terminal. It needs the terminal version of Claude
Code, installed apart from the desktop app and signed in to the same claude.ai account, and
it refuses to run without an interactive terminal: Claude cannot run it from its own shell,
only the person can, in theirs.
<!-- /claude-surface -->

### The prompt each task stores

Every task stores this short stub, with its own name and file, and nothing else. Print the
exact text for your registry with `python3 tools/routines.py stub <key>`.

**Job search: morning brief**

```
Scheduled run: morning brief. Run `git fetch origin master`, then read `automation/prompts/_common.md` and `automation/prompts/morning_brief.md` as they are on origin/master (`git show origin/master:<path>`) and follow them exactly. If either cannot be read, reply with one line saying which file and why.
```

**Job search: shortlist**

```
Scheduled run: job round. Run `git fetch origin master`, then read `automation/prompts/_common.md` and `automation/prompts/job_round.md` as they are on origin/master (`git show origin/master:<path>`) and follow them exactly. If either cannot be read, reply with one line saying which file and why.
```

### (a) One chat per briefing

Say **"set up my brief"** in any cloud chat in your repo, or let `/setup` do it. Claude lists
your scheduled tasks and runs `python3 tools/routines.py brief --triggers <each page>`, so a
brief that already exists, under any name, is never made twice. With none, it makes the
brief's own chat (`create_session` on your private repo, titled **Job search: morning brief**),
a task bound to it (`create_trigger` with that chat's id, `CRON_TZ=<your zone> 38 7 * * 1,4`,
the morning brief stub below as its prompt, no connectors), and a one-off first run a few
minutes later bound to the same chat; then `routines.py record` writes `profile/routines.json`
and it lands on master. You answer nothing: the days and the time are defaults, and the zone
is the one your profile names. Where a chat cannot make chats itself:

1. In a cloud chat (claude.ai/code in a browser, or the Claude app on your phone), start a
   **new chat with your private repo selected**. Name it after its task: **Job search: morning brief**.
   (Optional, and cheaper over months: first make the capped environment in "Keep a
   long-lived chat small" below, and start the chat in it.)
2. Paste this into it:

   > Set up my brief in this chat.

   It makes the task bound to itself, with the defaults above, records it and lands it.
3. Only if you want new postings searched on a schedule as well: start a second new chat
   with the repo selected, named **Job search: shortlist**, and paste the same with
   "shortlist" in place of "brief". Most people do not need it: "find me jobs" in any chat
   runs a round. Each task is independent.
4. Test each one as below. Each briefing then arrives as a reply in its chat, with no push.
   If you would rather scroll one chat, bind both tasks to the same one.

### (b) A routine, a new chat each run

1. Make a routine for each task:

   <!-- claude-surface: routines-cloud -->
   <!-- checked 2026-10-25; https://code.claude.com/docs/en/routines -->
   To make the brief in the cloud:
   1. Open claude.ai/code/routines and choose New task (in the desktop app's Code tab:
      Scheduled, then New task).
   2. Name it Job search: morning brief, choose your copy, set it weekly at your time, paste
      the prompt I give you, and save.
   3. Open it again, choose Custom, and paste the schedule I give you, so it runs on both
      days.

   Screens change: if yours looks different, tell Claude what you see.
   <!-- /claude-surface -->
2. **Name:** Job search: morning brief. **Repository:** tick your private repo.
   **Schedule:** weekly, on the first of your two days (Monday and Thursday suit most
   searches), at your time; the screen offers set frequencies, so Custom adds the second
   day afterwards. **Prompt:** the morning brief stub above, exactly. Turn on notifications
   for it if the app offers them.
3. Only if you want a scheduled search too: the same for **Job search: shortlist**, with its
   stub and its days.
4. Ask any chat in your repo: "add my routines to `profile/routines.json`, with
   `setup` set to `routines_screen`, and give the brief its second day". It records each
   name, cron and prompt file, with `"notifications": {"push": true}` on each
   (`routines.py check` fails without it, because a task nobody hears from is broken), and
   the trigger ids from `list_triggers` if it can see them (they are optional here). Where
   it can see the task it sets both days itself with `update_trigger`; otherwise it gives you
   the words to change it from a chat on your computer, where routines can be changed.
5. Every run is a new chat, and its final reply is the briefing, and the notification where
   the app sends one. Reply to the shortlist in the chat that run opened.

### Test it, without fire_trigger

**Never test a chat-bound task with `fire_trigger`.** It ignores the task's chat and starts
a new one with no repo, which fails. Instead, in the task's own chat, say:

> Create a one-off scheduled task bound to this chat, with `run_once_at` three minutes from
> now and the same prompt as this chat's scheduled task. Do not use fire_trigger.

It disables itself after it fires. Then check that the reply arrived in the chat; the chat
checks for itself that the run's work was saved (its pull request merged into master), and
says so in one plain line. A Routines-screen task runs once with **Run now** on its page.

### Keep a long-lived chat small

A chat a task is bound to grows by a run every time, and without a cap a chat on a
1M-token model can carry hundreds of thousands of tokens into every run. Cap it with an
environment variable on a cloud environment that only the scheduled chats use:

1. In claude.ai/code, create a cloud environment for the scheduled chats (or copy the one
   you use), with the same setup script and network access.
2. Add the environment variable `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000`.
3. Create the scheduled chats in that environment (step 1 of (a)).

Only chats in that environment are capped, whatever their model, and your other chats keep
their full window. Do not put the cap in `.claude/settings.json` instead: that file is the
app's and is synced into every copy, so a `modelSettings.<model>.autoCompactWindow` there
caps every chat on that model, for everyone. See
[Set the auto-compact window](https://code.claude.com/docs/en/model-config#set-the-auto-compact-window).

### Check the registry

`python3 tools/routines.py check` reads `profile/routines.json` and fails on a prompt file
that does not exist, a malformed or repeated trigger or chat id, or a cron without
`CRON_TZ=<your time zone>` (which would fire in UTC). `./tools/ci_local.sh` runs it whenever
the registry exists, and `tests/test_automation.py` runs it on the example in the app's CI,
so a broken set-up fails a check rather than a morning.

## Phone delivery, and the older shared-chat set-up

An older set-up sent every task into one shared chat, which handed each message to a
separate **relay** task (`fire_trigger`) that pushed it to the phone (`setup: "ops_relay"`
in the registry, `prompts/relay.md`). Since 14 October 2026 a newly made chat is refused
that hand-off, whatever the settings or the person says; a chat set up that way before then
can still make it.

- **If yours still works, do not archive, delete or rebuild that chat.** A rebuilt one
  cannot relay. `_common.md` still hands each message to the relay in that set-up, and the
  reply stands on its own if the hand-off is refused.
- **If it is lost, do not rebuild it.** Set up (a) or (b) instead. A trigger's bound chat
  cannot be changed in place, so for (a) delete each old task (`delete_trigger`, after
  reading it with `get_trigger`) and create it again from its new chat.

## Changing something: say it to any Claude chat in your repo

| Ask | What the chat does |
|---|---|
| "Make the brief shorter", "add X to the TLDR", "stop drafting on Fridays" | Writes it into `profile/CLAUDE.md`, section "This search's automation", which every run reads and which is yours. The prompt files under `prompts/` are the app's: a sync puts an edit to them back. Takes effect on the next run. |
| "Move the brief to 7:30", "run the round on Wednesdays too" | Edits `cron` in `profile/routines.json` and, for (a), calls `update_trigger` on that `trigger_id` with the new cron (`CRON_TZ=<zone>` first); for (b), the same where it can see the task, and otherwise says what to change on the routine's own page. Merges the registry. |
| "Switch everything to <city> time" | Changes `timezone` and every `cron` to `CRON_TZ=<IANA zone>` at the same local times, applies them the same way, merges. |
| "Add a task that does Y" | A new kind of task needs its own prompt file in the app (`prompts/<key>.md`), so it is a change to the app: the maintainer makes it, anyone else gets it written up as an issue. Until then, what an existing task should also do goes in `profile/CLAUDE.md`. |
| "Pause the shortlist" | `update_trigger` with `enabled: false` (or the routine's own page), and `"paused": "<date> <reason>"` on the entry. |

## Cost

Each run is one turn on the chat's model. News gathering for the TLDR is done by a sonnet
subagent with a cap of about ten searches. An empty run in a fresh chat cost $0.82 in a
test, most of it loading the repo's instructions; a chat that is bound to its task reuses
that context from cache on later runs, and is compacted automatically as it grows.
