# Automation: what runs on a clock

One scheduled task keeps the search moving without anyone asking, once the person wants it:
**a brief each morning**, turned on from the bell on their Brief. A scheduled job round is there too, for anyone who wants new postings found on a
clock, but it is off by default: "find me jobs" in any chat runs one. The instructions live
in `prompts/`, in git, so changing what a task does is a pull request and never an edit to
the task. Which tasks exist, when they run and where they report is the person's own
registry, `profile/routines.json` (`profile.example/routines.json` shows the shape).

| Task | What it delivers |
|---|---|
| **Job search: morning brief**, every morning once it is turned on (weekdays or other days in one tap) | Led by where the search is (an interview to prep, replies owed, applications waiting, or too little going out), then what is owed with the replies and nudges drafted, the counts since the last brief, three things to do before the next one, and the news that matters. Every run also takes the app's updates, so the copy stays current when no chat is opened (`prompts/morning_brief.md`). |
| **Job search: shortlist**, optional and off by default | A scored round of new postings, best first (`prompts/job_round.md`). Reply with picks in the same chat and it drafts, verifies and records them. |

**If no brief has arrived two hours after its time on one of its days, the automation is
broken.** The brief is sent on each of its days even when nothing is due, so silence always
means something failed.
Tell any Claude chat "the scheduled tasks are down" and point it at this file.

## Set it up

**Nothing to do: it is on from the start.** Set-up turns it on, and a copy set up before 4.3
gets it by itself. The chat that answers your page sets the brief up in itself, every day at 7:38 your time, and runs a first one a few minutes later so you see
it work (`python3 tools/routines.py brief` prints the calls). No new chat is made. Change its
days or time, or turn it off, from the same bell or in Settings, Your brief; take a break from
the whole search there too. With no page, say "set up my brief" in any chat. It is one
short run each morning in a chat that already exists, so it never adds a chat.

Two set-ups work reliably, and they trade the same thing: where the briefing arrives. The bell
makes (a).

| | (a) In the chat that answers your page | (b) A routine, a new chat each run |
|---|---|---|
| Where the briefing arrives | Your Brief, and a reply in that chat | A new chat each run |
| Push to your phone | No | Yes, where the app notifies you of the run |
| Where you reply to the shortlist | The chat that answers your page | The chat that run opened |
| Set up from | The bell (Claude does it) | A routine, made by you, once |

Both run on **your private repo**, never on the public app: a chat on the app holds none of
your state, and anything it pushed would be public.

**From your own computer.** Press the same bell. The brief always runs in the cloud, in
Claude's helper, so it arrives when your computer is off. Where your page is answered by the chat on
your computer and there is no helper yet, the same tap opens the helper's chat: press Send
there, once. Nothing else is asked, and no other chat is made. A scheduled task that runs
on your computer is never used for it:

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

### For Claude: the rules of setting it up

- **"Set up my brief" is set-up (a), asking nothing**: the bell's work item (`brief` with
  `args.setup`, done by the chat that answers the page) or the words in a chat. `/setup`
  never makes it. First list the account's scheduled tasks (`list_triggers`, every page) and
  run `python3 tools/routines.py brief --triggers <each page>`: a brief that exists, whatever
  it is called, is attached to and never made twice, and a task that only looks like one is
  asked about.
- **In a cloud chat** with none, `brief` prints the calls to make, in order: `create_trigger`
  bound to this chat (`persistent_session_id`, this chat's own id), `CRON_TZ=<their zone> 38 7
  * * *`, the stub as its prompt, `connectors: []`; and a one-off `run_once_at` first brief
  bound to the same chat, never `fire_trigger`. Then `routines.py record`, and land it. No
  chat is ever made for it: where this chat's id cannot be read, `brief` says to ask
  `get_session` (no `session_id`) for it and run again with `--chat <its id>`.
- **On their computer**, `brief` prints the one line to tell them: turn it on from the bell
  on their Brief. The bell sends it to the chat in the cloud that answers the page (a brief
  only runs there, `tools/page_db.py` `can_take`) and starts the helper where there is none.
  Never make a desktop scheduled task for the brief, never start a cloud chat from your own
  shell, and never make a routine for it from there.
- The lines `routines.py brief` prints are for you: act on them, and tell the person only the
  one line it gives ("Your brief is on: every day at 7:38. ..."), never its file, id or task
  name.
- The final reply of a run is the message; nothing depends on `fire_trigger`. Only a change
  of schedule needs `update_trigger` or the routine's own page; a change to what a task does
  is a pull request on its prompt file.
- **Every dated follow-up is automatic by construction**: the brief reads `next_action_due`
  from `network_contacts.csv` and the nudge schedule from the tracker, so a reminder is a
  date written into a state file, never another routine.

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

### (a) In the chat that answers your page

Press the bell on your Brief, or say **"set up my brief"** in any cloud chat in your repo.
Claude lists your scheduled tasks and runs `python3 tools/routines.py brief --triggers <each
page>`, so a brief that already exists, under any name, is never made twice. With none, it
binds a task to the chat doing the work (`create_trigger` with that chat's id, `CRON_TZ=<your
zone> 38 7 * * *`, the morning brief stub below as its prompt, no connectors), and a one-off
first run a few minutes later bound to the same chat; then `routines.py record` writes
`profile/routines.json` and it lands on master. You answer nothing: the days and the time are
defaults, and the zone is the one your profile names. Without a page, say
**"set up my brief"** in the cloud chat you already use: it binds the task to that chat.

Only if you want new postings searched on a schedule as well, say "set up my shortlist" in
the same chat: both tasks run there, and no chat is made for either. Most people do not need
it: "find me jobs" in any chat runs a round. Test each one as below; each briefing arrives as
a reply in that chat, with no push.

**Old chats tidy themselves away.** Before 4.3 the brief had a chat of its own, long work could
start a child chat, and a replaced helper stayed in the list. Once a day the chat that answers
the page moves an older brief into itself (a new task on the same days and time, the old one
turned off and kept) and archives the app's own chats it no longer uses: never one the person
named, one a scheduled task that is on still uses, a live campaign's chat, one used in the
last two days, or one whose work is not on master yet. An archived chat is kept, read-only,
and comes back on request (`python3 tools/tidy.py undo`).

### (b) A routine, a new chat each run

1. Make a routine for each task:

   <!-- claude-surface: routines-cloud -->
   <!-- checked 2026-10-29; https://code.claude.com/docs/en/routines -->
   To make the brief in the cloud:
   1. Open claude.ai/code/routines and choose New task (in the desktop app's Code tab:
      Scheduled, then New task).
   2. Name it Job search: morning brief, choose your copy, set it daily at your time, paste
      the prompt I give you, and save.
   3. Only for days other than every day: open it again, choose Custom, and paste the
      schedule I give you.

   Screens change: if yours looks different, tell Claude what you see.
   <!-- /claude-surface -->
2. **Name:** Job search: morning brief. **Repository:** tick your private repo.
   **Schedule:** daily, at your time (weekdays or other days afterwards with Custom).
   **Prompt:** the morning brief stub above, exactly. Turn on notifications for it if the
   app offers them.
3. Only if you want a scheduled search too: the same for **Job search: shortlist**, with its
   stub and its days.
4. Ask any chat in your repo: "add my routines to `profile/routines.json`, with
   `setup` set to `routines_screen`". It records each
   name, cron and prompt file, with `"notifications": {"push": true}` on each
   (`routines.py check` fails without it, because a task nobody hears from is broken), and
   the trigger ids from `list_triggers` if it can see them (they are optional here).
5. Every run is a new chat, and its final reply is the briefing, and the notification where
   the app sends one. Reply to the shortlist in the chat that run opened. Run chats more than
   two days old are tidied away by themselves (archived, never deleted: `tools/tidy.py`).

### Test it, without fire_trigger

**Never test a chat-bound task with `fire_trigger`.** It ignores the task's chat and starts
a new one with no repo, which fails. Instead, in the task's own chat, say:

> Create a one-off scheduled task bound to this chat, with `run_once_at` three minutes from
> now and the same prompt as this chat's scheduled task. Do not use fire_trigger.

It disables itself after it fires. Then check that the reply arrived in the chat; the chat
checks for itself that the run's work was saved (its pull request merged into master), and
says so in one plain line. A Routines-screen task runs once with **Run now** on its page.

### Keep a long-lived chat small

The chat that answers your page lives for weeks, and every tap and every brief re-reads its
history. On a model with a 1M-token window that history could grow to a million tokens
before Claude Code squeezed it, and each wake paid for all of it. So the app caps it: its own
`.claude/settings.json` sets `CLAUDE_CODE_AUTO_COMPACT_WINDOW` to `200000`, the window every
model had until recently, for every chat in your copy, in the cloud and on your computer
alike. Nothing to set up. Values below 100,000 are raised to it by Claude Code. See
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
- **If it is lost, do not rebuild it.** Press the bell on your Brief instead: that is (a). A
  trigger's bound chat cannot be changed in place, so the old task is read with
  `get_trigger`, turned off with `update_trigger`, and a new one made from the chat that
  answers your page.

## Changing something: say it to any Claude chat in your repo

| Ask | What the chat does |
|---|---|
| "Make the brief shorter", "add X to the TLDR", "stop drafting on Fridays" | Writes it into `profile/CLAUDE.md`, section "This search's automation", which every run reads and which is yours. The prompt files under `prompts/` are the app's: a sync puts an edit to them back. Takes effect on the next run. |
| "Move the brief to 7:30", "run the round on Wednesdays too" | For the brief, `python3 tools/routines.py move --days <days> --time <time>` (the page's own way too: its action `brief.move`) writes `cron` in `profile/routines.json` and keeps the one call owed; for another task, edit its `cron`. Then, for (a), `update_trigger` on that `trigger_id` with the new cron (`CRON_TZ=<zone>` first); for (b), the same where it can see the task, and otherwise says what to change on the routine's own page; `routines.py called <n>` once made. Merges the registry. |
| "I'm taking a break until 8 November", "pause my search" | `python3 tools/routines.py pause --until <date>` (the page's `brief.pause`): every follow-up is held (a contact's next action opens `HOLD until <date>`, a live application carries `DO NOT CHASE until <date>`), and the calls it lists turn the brief off and make one brief for the day they come back, which lifts the break. `routines.py resume` (`brief.resume`) ends it early and puts each hold back as it was. |
| "Switch everything to <city> time" | Changes `timezone` and every `cron` to `CRON_TZ=<IANA zone>` at the same local times, applies them the same way, merges. |
| "Add a task that does Y" | A new kind of task needs its own prompt file in the app (`prompts/<key>.md`), so it is a change to the app: the maintainer makes it, anyone else gets it written up as an issue. Until then, what an existing task should also do goes in `profile/CLAUDE.md`. |
| "Pause the shortlist" | `update_trigger` with `enabled: false` (or the routine's own page), and `"paused": "<date> <reason>"` on the entry. |

## Cost

Each run is one turn on the chat's model. News gathering for the TLDR is done by a sonnet
subagent with a cap of about ten searches. An empty run in a fresh chat cost $0.82 in a
test, most of it loading the repo's instructions; a chat that is bound to its task reuses
that context from cache on later runs, and is compacted automatically as it grows.
