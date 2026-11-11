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
| **Job search: daily upkeep**, made by itself where the brief does not run every day | Nothing to read: once a day, silently, it takes the app's updates, brings the page's data up to date and starts any work still waiting, so a page opened with no chat running is today's. The chat that answers the page makes it in its daily tidy-up, moves it with itself as it renews (deleting the old copy, never piling copies up), and takes it away once a brief runs every day (`prompts/upkeep.md`). |
| **Job search: shortlist**, optional and off by default | A scored round of new postings, best first (`prompts/job_round.md`). Reply with picks in the same chat and it drafts, verifies and records them. |
| **App builder: weekly fixes and release**, the app maintainer's alone, on the app itself | Nothing to read: every Wednesday night it fixes every issue reported on the app that week and releases the fixes; what it did is on the app's GitHub, in its issues and release notes, never in a brief (`prompts/builder_week.md`; MAINTAINING.md, "Bugs from the maintainer's copy"). Nobody else has it. |

**Where it arrives.** Each brief is a reply in the chat it runs in, and on your Brief where you
have a page. At the end of each run it sends its headline to your phone; that notification may
not arrive; the brief itself is the record, and where it was not sent, your next message in
that chat says so. A brief that does not come is noticed by the next chat that starts or wakes
(`routines.py calls` owes it one look at the scheduled tasks, and `routines.py brief` says what
is wrong and how to mend it); nobody has to watch for it.

## Set it up

**Nothing to do: it is on from the start.** Set-up turns it on, with or without a page, and a
copy set up before 4.3 gets it by itself. It runs in a chat of its own, "Job search: morning
brief", made with your copy attached, every day at 7:38 your time (5:38 on the US west coast
and in Mountain time, where 7:38 falls in the hours the scheduler runs late), and a first one
runs a few minutes later so you see it work (`python3 tools/routines.py brief` prints the
calls). Never in the chat that answers your page: a chat that approves access to your
computer can run no scheduled task from then on, and the brief would stop. 7:38 is the app's own choice for 8:00, a few minutes before the hour because a run set
on the hour can start several minutes late, and your page says so in one line. No new chat is
made. Change its days or time, or turn it off, from the same bell or in Settings, Your brief: a
time you pick there is kept to the minute, 8:00 stays 8:00. Your page shows when it really
comes, the scheduler's own late start included where it reports one. Take a break from the
whole search there too. With no page, say "move
my brief" or "stop my brief" in any chat. It is one short run each morning in its own chat,
the one chat it ever adds; if that chat is deleted, archived or approves computer access, the
daily tidy-up makes it again by itself. If set-up stops before its end, one reminder runs a
day after your page went up, in a chat of its own, saying only that set-up waits there.

Two set-ups work reliably, and they trade the same thing: where the briefing arrives. The bell
makes (a).

| | (a) In a chat of its own | (b) A routine, a new chat each run |
|---|---|---|
| Where the briefing arrives | Your Brief, and a reply in the brief's own chat | A new chat each run |
| Push to your phone | Each run sends its headline (seen sent from a cloud chat); where it is not sent, your next message there says so | Yes, where the app notifies you of the run |
| Where you reply to the shortlist | The chat that answers your page | The chat that run opened |
| What happens if its chat goes | The daily tidy-up makes a new one by itself | Nothing: each run is a new chat |
| Set up from | The bell (Claude does it) | A routine, made by you, once |

<!-- claude-surface: chat-push claim -->
<!-- checked 2026-11-03; https://code.claude.com/docs/en/tools-reference -->
A chat can send the person a phone notification with the PushNotification tool. The docs
name it a phone push while Remote Control is connected, and Push when Claude decides
(agentPushNotifEnabled, off by default) lets Claude send one; a cloud chat reads that
setting from the copy's own .claude/settings.json, which turns it on. A scheduled run in a
cloud chat was seen to send one: the tool answered Mobile push requested, with the push
sent. A scheduled task bound to a chat has no notification of its own (create_trigger's
notifications are only for a task that starts a new chat each run, and such a run gets no
copy of the files and no add_repo to fetch one), so a brief that runs in a chat sends its
headline this way; where the tool answers not sent, the person's next message in that chat
says the brief is there.
<!-- /claude-surface -->

Both run on **your private repo**, never on the public app: a chat on the app holds none of
your state, and anything it pushed would be public.

**From your own computer.** Press the same bell. The brief always runs in the cloud, in a
chat of its own, so it arrives when your computer is off. Where your page is answered by the chat on
your computer and there is no helper yet, the same tap opens the helper's chat: press Send
there, once. Nothing else is asked, and no other chat is made. A scheduled task that runs
on your computer is never used for it:

<!-- claude-surface: routines-local -->
<!-- checked 2026-11-09; https://code.claude.com/docs/en/desktop-scheduled-tasks -->
A desktop scheduled task made with Local runs on the computer, in a fresh chat each time it
is due, and only while the desktop app is running and the computer is awake: a time the
computer sleeps through is skipped, with one catch-up run when it wakes. A chat in the
desktop app makes one itself when asked to, as often as every minute, in the folder it
names; a run waits on any step its permission mode does not cover. So it is never used for
the brief; on the computer it is what takes the work waiting for the computer when no cloud
chat is awake to start one there.
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

- **"Set up my brief" is set-up (a), asking nothing**: `/setup` Step 5 (with or without a
  page), the bell's work item (`brief` with `args.setup`, done by the chat that answers the
  page), the brief-daily upgrade (`--own-initiative`) or the words in a chat. First list the
  account's scheduled tasks (`list_triggers`, every page) and run `python3 tools/routines.py
  brief --triggers <each page>`: a brief that exists, whatever it is called, is attached to
  and never made twice, and a task that only looks like one is asked about. Any `mend` call it
  prints gives one of the app's tasks the line that gets its files in any chat: make it, then
  `routines.py mended`.
- **In a cloud chat** with none, `brief` prints the calls to make, in order: `create_session`
  for the brief's own chat ("Job search: morning brief", the copy as its `source_url`);
  `create_trigger` bound to that new chat (`persistent_session_id`, never the chat that
  answers the page or this chat), `CRON_TZ=<their zone> 38 7 * * *` (5:38 where 7:38 falls in
  the scheduler's slow hours), the stub as its prompt, and no `connectors` field (some
  organizations refuse it); and a one-off `run_once_at` first brief bound to the same chat,
  never `fire_trigger`. Then `routines.py record --own-chat`, and land it. Never a task that
  starts a new chat each run (it gets no copy of the files). A refused `create_session` makes
  nothing; the next chat that starts tries again.
- **On their computer**, `brief` prints the one line to tell them: turn it on from the bell
  on their Brief, and with no page, make the page first (`app.py start`). The bell sends it to
  the chat in the cloud that answers the page (a brief only runs there, `tools/page_db.py`
  `can_take`) and starts the helper where there is none. Never make a desktop scheduled task
  for the brief, never start a cloud chat from your own shell, and never make a routine for
  it from there.
- **A time the person picks is kept to the minute.** Only the app's own default moves off the
  hour (8:00 to 7:38, Claude's scheduling guidance), and `record --asked` keeps what it stood
  for so the page says why. A time asked for on the page or in a chat ("move my brief to 8")
  goes through `python3 tools/routines.py move --time 08:00` and its owed `update_trigger`
  carries exactly that minute: never move it off the hour or half hour yourself, whatever a
  tool's own guidance says, since their choice wins. What the scheduler reports of a late start
  (`next_run_at`, the last run's `fired_at`) is kept by `routines.py brief --triggers` and the
  daily tidy-up, and the page shows that time with one line why, never the time it is set for.
- The lines `routines.py brief` prints are for you: act on them, and tell the person only the
  one line it gives (where and when it comes, and how to change it), never its file, id or
  task name.
- The final reply of a run is the message; nothing depends on `fire_trigger`. A run asked to
  push is told so by `brief.py`'s own lines, the one place that asks. Only a change of schedule
  needs `update_trigger` or the routine's own page; a change to what a task does is a pull
  request on its prompt file.
- **What code mends by itself** (`routines.py calls`, at every start, wake and brief): a break
  whose day has passed is lifted and the brief turned on again, a time zone this computer does
  not know is rewritten to the person's own, and a brief that did not come owes one look at
  the scheduled tasks. Make each call it lists, then `routines.py called <n>`.
- **A brief whose chat cannot open the files** (its task fired with no record of that day's
  brief left, or it now wakes another chat than the one it was bound to: its chat was made
  again empty) is never "set up": `brief` says `lost:` and prints the `move` calls that give
  it a new chat of its own, with one run there of the brief that did not come. Make them in
  order, stopping at the first that fails, and tell the person only the one line it gives.
- **A brief in a chat not made for it** (the chat that answers the page, an old helper, a
  fresh chat each run, or a chat that approved computer access) is never "set up" either:
  `brief` says `elsewhere:` and prints the same `move` calls, said to nobody. The daily
  tidy-up (`tools/tidy.py`) does the same where the brief's own chat is gone, archived or
  approved computer access, and the brief is never carried from helper to helper as the
  page's helper renews.
- **Set no reminder or check-in for yourself** (`send_later`, a one-off task bound to your
  own chat): a chat that approves computer access can run none of them. What waits is picked
  up by the brief's next run or the page's next check-in.
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

### (a) In a chat of its own

Press the bell on your Brief, or say **"set up my brief"** in any cloud chat in your repo.
Claude lists your scheduled tasks and runs `python3 tools/routines.py brief --triggers <each
page>`, so a brief that already exists, under any name, is never made twice. With none, it
makes the brief's own chat with your copy attached (`create_session`), binds a task to it
(`create_trigger` with that chat's id, `CRON_TZ=<your zone> 38 7 * * *`, the morning brief
stub below as its prompt, no connectors), and a one-off first run a few minutes later bound
to the same chat; then `routines.py record --own-chat` (with `--asked 08:00`, what 7:38
stands for) writes `profile/routines.json` and it lands on master. You answer nothing: the
days and the time are defaults, and the zone is the one your profile names.

Only if you want new postings searched on a schedule as well, say "set up my shortlist" in
the same chat (`python3 tools/routines.py stub job_round` prints its prompt): it runs in the
chat that answers your page. Most people do not need it: "find me jobs" in any chat runs a
round. Test each one as below; each briefing arrives as a reply in the brief's chat, and the
run sends its headline to your phone; your next message in that chat says so when it was not
sent.

The brief is never moved to a task that starts a new chat each run: such a run gets no copy of
your files and no way to fetch one, so it could only say it could not start.

**Old chats tidy themselves away.** Before 4.3 the brief had a chat of its own, long work could
start a child chat, and a replaced helper stayed in the list. A big job's chat puts itself away
once its work is saved and nothing else waits (it messages no other chat); one that could not is
put away by the chat that answers the page (`tidy.py close`, for an older one that still
reports) or by the daily tidy-up. Once a day, and at once after a hand-over to a fresh helper, the chat that
answers the page archives the app's own chats it no longer uses: never one the person named,
one a scheduled task that is on still uses, a live campaign's chat, one used in the last two
days (an old helper excepted: only the live one, "Job search page", is ever kept), or one
whose work is not on master yet. A shortlist that works where it is stays there; one whose
chat no longer works (deleted, or a helper the page no longer uses) moves into the chat that
answers the page. The brief moves only into a new chat of its own (a new task on the same
days and time, the old one turned off, and deleted once it has been off a week). Old tasks
that can no longer run are cleaned away by the same tidy-up: a one-off a day past its time is
turned off, and so is a task bound to the chat that approved computer access whose last run
failed (`routines.cleanup`). An archived chat is kept, read-only, and comes back on request (`python3
tools/tidy.py undo`).

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
   the app sends one. Reply to the shortlist in the chat that run opened. The list of chats
   Claude reads leaves out the ones a scheduled task started, so where you have a page, the
   day's tidy-up reads each run's chat from your scheduled tasks, remembers it, and puts it
   away once it is two days old (archived, never deleted: `tools/tidy.py`).

### Test it, without fire_trigger

**Never test a chat-bound task with `fire_trigger`.** It ignores the task's chat and starts
a new one with no repo, which fails, so a manual test cannot show the bound run
(claude_surfaces: routine-bound-chat). Instead, in the task's own chat, say:

> Create a one-off scheduled task bound to this chat, with `run_once_at` three minutes from
> now and the same prompt as this chat's scheduled task. Do not use fire_trigger.

It disables itself after it fires. Then check that the reply arrived in the chat; the chat
checks for itself that the run's work was saved (its pull request merged into master), says so
in one plain line, and takes the test task away (`delete_trigger`). Make it in the task's own
chat only, never in the chat that answers your page or one that approved computer access,
where no scheduled run can start; the daily tidy-up turns off one left a day past its time. A Routines-screen task runs once with **Run now** on its page.

### A long-lived chat keeps its whole window

The chat that answers your page lives for weeks, and Claude Code squeezes its history only
when the model's own window is nearly full. The app sets nothing here on purpose: a smaller
cap made a chat forget what it was doing every few steps. Nothing to set up.

### Check the registry

`python3 tools/routines.py check` reads `profile/routines.json` and fails on a prompt file
that does not exist, a malformed or repeated trigger or chat id, or a cron without
`CRON_TZ=<your time zone>` (which would fire in UTC). Given the task listing too
(`--triggers <what list_triggers returned>`), it also fails a brief whose task fires in a chat
the registry names neither as its own nor as the older ops chat. `./tools/ci_local.sh` runs it whenever
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
- **If it is lost, do not rebuild it.** Nothing to do: the task then wakes a new empty chat
  with no copy of your files, and the next daily tidy-up in the chat that answers your page
  gives the brief a new chat of its own (`tools/tidy.py`). A trigger's bound chat cannot be changed
  in place, so a new task is made there and the old one turned off, never deleted.

## Changing something: say it to any Claude chat in your repo

| Ask | What the chat does |
|---|---|
| "Make the brief shorter", "add X to the TLDR", "stop drafting on Fridays" | Writes it into `profile/CLAUDE.md`, section "This search's automation", which every run reads and which is yours. The prompt files under `prompts/` are the app's: a sync puts an edit to them back. Takes effect on the next run. |
| "Move the brief to 7:30", "run the round on Wednesdays too" | For the brief, `python3 tools/routines.py move --days <days> --time <time>` (the page's own way too: its action `brief.move`) writes `cron` in `profile/routines.json` and keeps the one call owed; for another task, edit its `cron`. Then, for (a), `update_trigger` on that `trigger_id` with the new cron (`CRON_TZ=<zone>` first); for (b), the same where it can see the task, and otherwise says what to change on the routine's own page; `routines.py called <n>` once made. Merges the registry. |
| "I'm taking a break until 8 November", "pause my search" | `python3 tools/routines.py pause --until <date>` (the page's `brief.pause`): every follow-up is held (a contact's next action opens `HOLD until <date>`, a live application carries `DO NOT CHASE until <date>`), and the calls it lists turn the brief off and make one brief for the day they come back, bound to a chat with the copy, which lifts the break. If that one fails, the first start, wake or brief after the day lifts it all the same (`routines.py calls`). `routines.py resume` (`brief.resume`) ends it early and puts each hold back as it was. |
| "Switch everything to <city> time" | Changes `timezone` and every `cron` to `CRON_TZ=<IANA zone>` at the same local times, applies them the same way, merges. |
| "Add a task that does Y" | A new kind of task needs its own prompt file in the app (`prompts/<key>.md`), so it is a change to the app: the maintainer makes it, anyone else gets it written up as an issue. Until then, what an existing task should also do goes in `profile/CLAUDE.md`. |
| "Pause the shortlist" | `update_trigger` with `enabled: false` (or the routine's own page), and `"paused": "<date> <reason>"` on the entry. |

## Cost

Each run is one turn on the chat's model. News gathering is done by the news-reader subagent
on the smallest model, with at most six searches built and eight run: the employers in play,
then what the person's own list watches (person.json `brief.watch`), each only as often as
it changes. A run in a fresh chat costs about $1 to $2, most of it loading the repo's
instructions. A chat bound to its task keeps every run's history, about 100,000 tokens a day,
and the cache does not last the night, so each morning's run pays for the whole history again:
measured at about $6.8 a run on its second day (2026-11-10). So once its chat holds more than
250,000 tokens, the run gives the brief a fresh chat of its own (`routines.py fresh`), and the
daily tidy-up puts the old one away. The brief's chat never answers the page, so taps there
wake nothing.
