# Automation: what runs on a clock

One scheduled task keeps the search moving without anyone asking: **a brief, twice a
week**. A scheduled job round is there too, for anyone who wants new postings found on a
clock, but it is off by default: "find me jobs" in any chat runs one. The instructions live
in `prompts/`, in git, so changing what a task does is a pull request and never an edit to
the task. Which tasks exist, when they run and where they report is the person's own
registry, `profile/routines.json` (`profile.example/routines.json` shows the shape).

| Task | What it delivers |
|---|---|
| **Job search: morning brief**, twice a week (Monday and Thursday suit most searches) | Led by where the search is (an interview to prep, replies owed, applications waiting, or too little going out), then what is owed with the replies and nudges drafted, the counts since the last brief, three things to do before the next one, and the news that matters. Every run also takes the app's updates, so the copy stays current when no chat is opened (`prompts/morning_brief.md`). |
| **Job search: shortlist**, optional and off by default | A scored round of new postings, best first (`prompts/job_round.md`). Reply with picks in the same chat and it drafts, verifies and records them. |

**If no brief has arrived two hours after its time on one of its days, the automation is
broken.** The brief is sent on each of its days even when nothing is due, so silence always
means something failed.
Tell any Claude chat "the scheduled tasks are down" and point it at this file.

## Set it up: pick one of two

Only two set-ups work reliably, and they trade the same thing: where the briefing arrives.

| | (a) One chat per briefing | (b) The Routines screen |
|---|---|---|
| Where the briefing arrives | A reply in that briefing's own chat | A new chat each run |
| Push to your phone | No | Yes, where the app notifies you of the run |
| Where you reply to the shortlist | The "Job search: shortlist" chat | The chat that run opened |
| Set up from | A chat (Claude does it) | The Claude app's Routines screen (you do it) |

Both run on **your private repo**, never on the public app: a chat on the app holds none of
your state, and anything it pushed would be public.

**From your own computer.** Ask a local session to set up the brief. A local session cannot
create a cloud task directly, so it starts a cloud chat with `claude --cloud "<the paste in
(a) step 2>"` on your private repo, and that chat does (a). The desktop app's Routines screen
also does (b): choose **Cloud**, since a local task runs only while the app is open and the
computer awake. `/schedule` in a local terminal session makes the same cloud routine.

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

Say **"set up my brief"** in any chat in your repo. Where it can, Claude starts the brief's
own chat with the paste in step 2, and you answer its two questions there. Otherwise:

1. In Claude Code (claude.ai/code, or the Claude app's Code tab), start a **new chat with
   your private repo selected**. Name it after its task: **Job search: morning brief**.
   (Optional, and cheaper over months: first make the capped environment in "Keep a
   long-lived chat small" below, and start the chat in it.)
2. Paste this into it:

   > Set up my brief in this chat. Ask me which two days and what time I want it and which
   > city I am in, then create a scheduled task that fires into this chat, named Job search: morning
   > brief, with the morning brief stub in `automation/README.md` as its prompt. Record it
   > in `profile/routines.json` (`setup` `chat_per_briefing`, this chat's session id and
   > title under `chat`, the trigger id), run `python3 tools/routines.py check` and
   > `./tools/ci_local.sh --quick`, and land it on master through a PR.

   Claude asks two questions and writes the schedule itself; you never type one.
3. Only if you want new postings searched on a schedule as well: start a second new chat
   with the repo selected, named **Job search: shortlist**, and paste the same with
   "shortlist" in place of "brief". Most people do not need it: "find me jobs" in any chat
   runs a round. Each task is independent.
4. Test each one as below. Each briefing then arrives as a reply in its chat, with no push.
   If you would rather scroll one chat, bind both tasks to the same one.

### (b) The Routines screen

1. In the Claude app, open **Routines** and create a new one for each task.
2. **Name:** Job search: morning brief. **Repository:** tick your private repo.
   **Schedule:** weekly, on the first of your two days (Monday and Thursday suit most
   searches), at your time; the screen offers set frequencies, so step 4 adds the second
   day. **Prompt:** the morning brief stub above, exactly. Turn on notifications for it if
   the app offers them.
3. Only if you want a scheduled search too: the same for **Job search: shortlist**, with its
   stub and its days.
4. Ask any chat in your repo: "add my Routines-screen tasks to `profile/routines.json`, with
   `setup` set to `routines_screen`, and give the brief its second day". It records each
   name, cron and prompt file, with `"notifications": {"push": true}` on each
   (`routines.py check` fails without it, because a task nobody hears from is broken), and
   the trigger ids from `list_triggers` if it can see them (they are optional here). Where
   it can see the task it sets both days itself with `update_trigger`; otherwise it says
   what to ask `/schedule update` in Claude Code on your computer, which does not run inside
   a cloud chat.
5. Every run is a new chat, and its final reply is the briefing, and the notification where
   the app sends one. Reply to the shortlist in the chat that run opened.

### Test it, without fire_trigger

**Never test a chat-bound task with `fire_trigger`.** It ignores the task's chat and starts
a new one with no repo, which fails. Instead, in the task's own chat, say:

> Create a one-off scheduled task bound to this chat, with `run_once_at` three minutes from
> now and the same prompt as this chat's scheduled task. Do not use fire_trigger.

It disables itself after it fires. Then check three things: the reply in the chat, the PR
it opened, and that the PR merged into master. A Routines-screen task runs once with
**Run now** on its page.

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
| "Move the brief to 7:30", "run the round on Wednesdays too" | Edits `cron` in `profile/routines.json` and, for (a), calls `update_trigger` on that `trigger_id` with the new cron (`CRON_TZ=<zone>` first); for (b), the same where it can see the task, and otherwise says what to change in the Routines screen. Merges the registry. |
| "Switch everything to <city> time" | Changes `timezone` and every `cron` to `CRON_TZ=<IANA zone>` at the same local times, applies them the same way, merges. |
| "Add a task that does Y" | A new kind of task needs its own prompt file in the app (`prompts/<key>.md`), so it is a change to the app: the maintainer makes it, anyone else gets it written up as an issue. Until then, what an existing task should also do goes in `profile/CLAUDE.md`. |
| "Pause the shortlist" | `update_trigger` with `enabled: false` (or the Routines screen), and `"paused": "<date> <reason>"` on the entry. |

## Cost

Each run is one turn on the chat's model. News gathering for the TLDR is done by a sonnet
subagent with a cap of about ten searches. An empty run in a fresh chat cost $0.82 in a
test, most of it loading the repo's instructions; a chat that is bound to its task reuses
that context from cache on later runs, and is compacted automatically as it grows.
