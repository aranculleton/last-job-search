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
know whether it worked.

1. **Let Claude start its chats there** (`remote-control-settings`). Check: in a cloud chat,
   `list_environments` lists this computer as an active environment of kind `bridge`
   (`computer-bridge`). Not listed after they say done: give the steps once more, then the
   fallbacks below still work.
2. **The one approval** (`computer-bridge`). From the cloud chat, `python3 tools/computer.py
   route` prints the `create_session` call; refused as an untrusted device, run its
   `trust-check` first (a chat that approves is tied to their devices for good, so no
   scheduled task may fire into it), then `confirm_repository_trust`: one card, once.
3. **Auto, once.** A chat started on the computer from the cloud is refused Auto and starts
   in Manual (seen 2026-11-09, from a cloud chat that was in Auto itself). The desktop app keeps
   a mode chosen in a folder for the chats after it there, so the person switches the first
   one once: "On your computer, in the chat named <its title>, change Manual to Auto at the
   bottom" (`app_listen.MODE_REFUSED` says it). Every chat started there after it runs in Auto.
4. **Signed in to LinkedIn, and staying signed in** (`browser-pane-stay-signed-in`). Check:
   the chat on the computer reads one LinkedIn page and writes its heartbeat
   (`computer.py beat --linkedin in`).
5. **The scheduled task** (`routines-local`): the chat on the computer makes it itself where
   it can (`python3 tools/computer.py task` prints exactly what), so work still starts with
   no cloud chat awake. Never asked of the person.
6. **The test**: that chat reads one profile, then `python3 tools/computer.py ready --name
   <the computer>` dates it in `profile/place.json`, which ends the upgrade card.

Nothing about the app's behaviour is written into a chat's own memory: the person's settings
live in `profile/`, and the start command reports any memory that disagrees with them
(`computer.py memory`).

### How the work reaches the computer (for Claude)

Work that needs a LinkedIn read is `to: computer` and is refused to any cloud chat
(`tools/page_db.py` `computer_only`). The page's helper runs `python3 tools/computer.py
waiting` on each wake and, while something waits, `route`, which picks the first that works:
a chat already on the computer; a chat started there from the cloud (`create_session` on the
bridge, in Auto, titled `Job search · <job> · <computer>`, its prompt complete, its results
back through the page and the copy and never `send_message`, archived by the helper once its
work is finished); the scheduled task; a folder the computer offers (`folder-attach`); a cloud
chat lent the computer's browser (`cloud-linked-browser`); and last, the page's one line and
the paste. On the computer the work runs in the chat itself (`app.py next --kind computer
--computer-only`), never as a background agent, which has no browser. Each run is measured
from its own transcript (`computer.py measure`) and its heartbeat says how the computer is,
so the page shows one line and, only while work waits on the person, one To do card.

## If something does not work

- A download fails: say the computer seems to be offline, and try again when they say so.
- `env_check.py --fix` says something is theirs (a Linux package, Apple's window): give
  that one line, nothing else.
- Everything it installs can be checked any time with `python3 tools/env_check.py`.
