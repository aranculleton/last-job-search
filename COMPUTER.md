# On your own computer

**For you:** open the Claude desktop app, choose **Code**, pick a new empty folder, and
paste the line your other chat gave you, which starts "Open my job search on this
computer" (or type that, with a link to this page). Claude does the rest. The only things
that are yours: copying one code into GitHub's page to sign in, and on a Mac with nothing
set up, clicking **Install** in a window from Apple.

**Using it, once it is set up.** You never need to keep a chat open on your computer. Keep
the Claude app open there, with your computer awake, and that is all: when something needs
your computer (reading someone's LinkedIn profile before Claude writes to them), Claude
starts a chat there by itself, called "Job search · what it is doing · your computer's
name", does the work and puts it on your page. Those chats are safe to delete. To watch one,
open it in the Claude app on your computer. If your computer is off, your page says so in one
line and the work waits; nothing else is asked of you.

---

The rest of this page is for Claude. Follow it in order. Install everything yourself;
never send the person to Homebrew, winget, an installer or a terminal. Nothing here needs
an administrator password. Say one plain line per step at most, and never show a command,
a path, a branch or the word "repository" to the person. Put nothing on top of the steps:
no notes about browsers, accounts or automation.

The person's message reads like "Open my job search on this computer. My copy is
github.com/OWNER/NAME. Follow github.com/aranculleton/last-job-search/blob/master/COMPUTER.md".
A chat that is to give them that line prints it with `python3 tools/app.py start --paste`.

`APP` below is a fresh shallow copy of the public app, kept outside the person's folder:
`~/.cache/last-job-search-app` on a Mac or Linux, `%LOCALAPPDATA%\last-job-search-app` on
Windows. `OWNER/NAME` is the person's own private copy, made from the app.

## 1. What shell you have

Run `uname -s` in the Bash tool. `Darwin` is a Mac, `Linux` is Linux; follow 2a. If there
is no Bash tool, or it fails and a PowerShell tool works, this is Windows with no Git yet;
follow 2b. Windows with Git Bash (`uname -s` says `MINGW64_NT...`) also follows 2b, from
its step 2, using `python` where a command here says `python3` until step 5 has run.

## 2a. Mac or Linux

1. `git --version`. On a Mac with no developer tools this opens Apple's window: tell the
   person "A window from Apple asks to install some tools: click Install. It takes a few
   minutes." Then check every 30 seconds with `xcode-select -p` until it succeeds. On
   Linux with no Git, Git comes only from the system, which asks for their password: ask
   them to open Terminal and run `sudo apt-get install -y git` (`sudo dnf install -y git`
   on Fedora, `sudo pacman -S git` on Arch), and say "done".
2. `git clone -q --depth 1 https://github.com/aranculleton/last-job-search APP` (or
   `git -C APP pull -q` when it is there).
3. `python3 APP/tools/installs.py gh`. It puts GitHub's command line in `~/.local/bin`.

## 2b. Windows

1. In PowerShell:
   `curl.exe -fsSL -o "$env:TEMP\computer_setup.ps1" https://raw.githubusercontent.com/aranculleton/last-job-search/master/tools/computer_setup.ps1`
   Read the file. Then run it in the background:
   `powershell -NoProfile -ExecutionPolicy Bypass -File "$env:TEMP\computer_setup.ps1"`.
   It installs Git, Python and GitHub's command line into the person's own folders, only
   what is missing, and ends with `READY` and the full path of each. Use those paths
   until the app is restarted: this chat's shell was started before they existed.
2. `git clone -q --depth 1 https://github.com/aranculleton/last-job-search APP`, with the
   `git:` path it printed.

When it printed `restart:`, Git Bash is new: after the copy is set up (step 5), tell the
person once, "Close the Claude app and open it again, so it can use what I installed.",
and say that this chat can be continued after.

## 3. Sign in to GitHub

1. `gh auth status`. Signed in: go to step 4.
2. Otherwise start `gh auth login --web --git-protocol https --hostname github.com` in the
   background. It prints a one-time code. Tell the person: "Open github.com/login/device,
   type this code: ABCD-1234, then press Authorize." Wait for the command to finish.
3. `gh auth setup-git`, so Git uses the same sign-in.

## 4. Put their copy in this folder

Ask nothing here and offer no choice: every case below has one right answer.

1. Which copy: the one named in the person's message, else `python3 APP/tools/find_copy.py`.
   One name: use it. Two or more: the one changed most recently. None: make it, private,
   from the app: `gh repo create my-job-search --private --template
   aranculleton/last-job-search` (`my-job-search-2` if the name is taken), and wait about
   ten seconds while GitHub fills it.
2. This folder empty: `gh repo clone OWNER/NAME .`. Not empty (the app may have put a
   `.claude` folder here): `git init -q`, `git remote add origin
   https://github.com/OWNER/NAME.git`, `git fetch -q origin`, then
   `git checkout -q -B master --track origin/master` (the copy's own default branch, if
   `git remote show origin` names another).
3. **Their copy has nothing in it** (made empty on GitHub rather than from the app: the
   clone says it is empty, or the fetch brings nothing): fill it from the app yourself,
   keeping the app's history so its updates merge cleanly, and say nothing about it:
   `git fetch -q https://github.com/aranculleton/last-job-search master`,
   `git checkout -q -B master FETCH_HEAD`, `git push -q origin master`, then
   `gh repo edit OWNER/NAME --default-branch master`. That is exactly what making it from
   the app gives them.

## 5. Finish, without asking anything

1. `python3 tools/env_check.py --fix` in the background (on Windows, `python` for
   `python3` until it has run once: it adds the `python3` command). It installs LaTeX,
   Bun and the Python packages where they are missing, and says one line each.
2. `python3 tools/app.py start --on "<this chat's model>" --tools "<its browser tools>"`,
   the one start every chat runs, then by its first line:
   - `app start: set up` (or `set up elsewhere`, which it brings in first): ask nothing and
     run no setup. Say one line: the search is ready on this computer too. Do what else it
     prints (it says whether this chat looks after the page: usually another chat does, and
     then this one neither publishes nor watches it), then the networking skill's "On a new
     computer" step.
   - `app start: setup going in another chat`: say its line, that their setup is still going
     in their other chat, and start nothing.
   - `app start: setup stopped`: say its line and, on their "carry on", run `/setup`, which
     finishes it from what is written. `setup self`: this chat is the one setting up; carry
     on with `/setup`.
   - `app start: setting up`: run `/setup` and carry on there (a new chat in this same folder
     works too).
3. When the install in step 1 ends, say its outcome in one line (or nothing, if it all
   went through), and the restart line from 2b if there was one.

## 6. Use your computer for LinkedIn (once)

The one thing a computer is needed for is reading LinkedIn in the Claude desktop app's own
browser. This stage makes that happen with no chat for the person to keep open. `/setup` runs
it for a new person who works on a computer (`--section computer`), and an existing copy gets
it as one card (the `computer-linkedin` profile upgrade). Each step below is one plain line
to the person from `python3 tools/claude_surfaces.py steps <id>`, checked against its
official page that day, and each is checked by Claude after it, so the person never has to
know whether it worked. The keys and menus differ between a Mac, Windows and Linux, so the
steps are that computer's own: run on the computer, the command reads it itself; in a cloud
chat, `python3 tools/computer.py steps <id> "$D" --envs <list_environments saved> --folders
<list_computer_folders saved>` reads it from the computer's heartbeat or the lists, and with
neither the steps say all three in one line. Never pass on a Mac's keys to anyone else.

1. **Let Claude start its chats there** (`remote-control-settings`). Check: in a cloud chat,
   `list_environments` lists this computer as an active environment of kind `bridge`
   (`computer-bridge`). Not listed after they say done: give the steps once more, then the
   fallbacks below still work.
2. **The one approval** (`computer-bridge`), held by one small chat of its own, "Job search:
   starts chats on your computer" (`tools/computer.py` STARTER_TITLE). A chat that approves is
   tied to the person's devices for good: no chat can archive it, itself included, no
   scheduled task may fire into it and no other chat's message reaches it. So the page's
   helper and the brief never approve: their `route` makes the starter once (`create_session`)
   and later wakes it by republishing its bell, a tiny page it published and watches. The
   starter's own `route` prints the `create_session` on the computer; refused as an untrusted
   device, it runs `trust-check`, then `confirm_repository_trust`: one card, once.
3. **Auto, once.** A chat started on the computer gets Auto only when the chat starting it is
   in Auto itself ("requires the parent session to be in auto mode (parent is default)",
   2026-11-10, from a helper whose mode menu showed Auto). So on that refusal the person is
   asked once to switch the helper to Auto, and the call is made again; every chat after it
   then starts in Auto (`app_listen.MODE_REFUSED` says each step).
4. **Signed in to LinkedIn, and staying signed in** (`browser-pane-stay-signed-in`, whose
   steps include keeping the sign-in). Check: a chat already at work on the computer says what
   its own tab shows in its heartbeat (`computer.py beat --linkedin in`), and opens nothing
   extra for it; who looks in each case is the table below. No chat can read whether the
   browser keeps sign-ins, so it is judged by its effect: a sign-in lost by the next look, one
   made on the page or seen by a read between two looks included, marks it off
   (`computer.cookies_seen`). The page then asks once, before the next sign-in, to keep it
   (`browser-pane-keep-cookies`), the person's Done records it on, and a sign-in that holds
   for a day clears it. A sign-in page before anything was read since they signed in is a
   sign-in that did not last, never friction: nothing stops (`reading.signout`, lost).
5. **No scheduled task.** An hourly task on the computer started a Claude run every hour the
   app was open, waiting work or not, and needed its own Auto switch and a first run by hand
   (2026-11-09). The cloud already starts a chat on the computer when work waits, so none is
   made or asked for. One a person made earlier can be deleted from Scheduled in the sidebar.
6. **The test**: that chat reads one profile, then `python3 tools/computer.py ready --name
   <the computer>` dates it in `profile/place.json`, which ends the upgrade card.

Nothing about the app's behaviour is written into a chat's own memory: the person's settings
live in `profile/`, and the start command removes a note in memory that disagrees with them,
once, saying one line (`computer.py memory`).

### Who looks at LinkedIn's sign-in (for Claude)

One owner for each case; nothing else opens LinkedIn to look (the builder audit, 2026-11-10,
CC-20).

| The case | Who looks | The command |
|---|---|---|
| The day's look, whether anything waits or not | the page, once a day, when it opens in the Claude desktop app; no chat opens LinkedIn only to check | `python3 tools/network/reading.py linkedin-check` says passed, signed-out or due |
| How the computer is, while a job runs there | the chat the app started on the computer, from the tab it already has; it opens nothing extra | `python3 tools/computer.py beat --linkedin in`, `out` or `unknown` |
| A job stopped on a sign-in, seen signed in again | the chat on the computer that waits for it (`computer.py signin-wait`) | `python3 tools/computer.py signed-in --work <id>` |

### How the work reaches the computer (for Claude)

Work that needs a LinkedIn read is `to: computer` and is refused to any cloud chat
(`tools/page_db.py` `computer_only`). The page's helper runs `python3 tools/computer.py
waiting` on each wake, and the brief on each run, and, while something waits, `route`, which picks the first that works:
a chat already on the computer; a chat started there from the cloud (`create_session` on the
bridge by the computer starter, woken by its bell, in Auto, titled `Job search · <job> ·
<computer>`, its prompt complete, its results back through the page and the copy and never
`send_message`, archived by the starter once its work is finished or waits on the person: a
chat that finds LinkedIn signed out opens its sign-in page in Claude's browser, puts the Sign
in to LinkedIn card on the page and looks again by itself for a quarter of an hour
(`computer.py signin-wait`), carrying on the moment they are signed in; only after that does
it ring the bell, its chat is put away, and a fresh one starts once they sign in; the person
saying in that chat that they signed in, or asking it to do queued work there, is `app.py resume`,
which takes the work into that chat so nothing starts it twice); the scheduled task; a folder the computer offers (`folder-attach`); a cloud
chat lent the computer's browser (`cloud-linked-browser`); and last, the page's one line and
the paste. On the computer the work runs in the chat itself (`app.py next --kind computer
--computer-only`), never as a background agent, which has no browser, and it is the whole
networking run: the people searches, the short list, each profile read in Claude's browser
(`reading.py route --tools browser` says `here`), every note written from what was read and
checked, and the page brought up to date. A networking run asked in a cloud chat while the
computer is ready is sent there the same way (`app.py ask`), never half done in the cloud. Each run is measured
from its own transcript (`computer.py measure`) and its heartbeat says how the computer is,
so the page shows one line and, only while work waits on the person, one To do card.

## If something does not work

- A download fails: say the computer seems to be offline, and try again when they say so.
- `env_check.py --fix` says something is theirs (a Linux package, Apple's window): give
  that one line, nothing else.
- Everything it installs can be checked any time with `python3 tools/env_check.py`.
