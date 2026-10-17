# Start here

This is a job search that Claude runs for you, end to end: it finds postings, scores them
against you, writes a resume and cover letter for the ones you pick, checks them, and helps
you reach the right people. It never sends anything. You do that.

You need a GitHub account and Claude Code, which has no free tier: these steps use it through
a Claude subscription. Five steps, about fifteen minutes, and no coding. Using a different agent
tool instead? Start at [AGENTS.md](AGENTS.md).

---

## 1. Make your own private copy

On this page on GitHub, click the green **Use this template** button, then **Create a new
repository**.

- **Owner:** you.
- **Repository name:** anything, for example `my-job-search`.
- Tick **Private**. This matters: your copy will hold your work history, your salary
  expectations and the names of people you talk to.
- Click **Create repository**.

**Never fork this repository.** A fork of a public repository is public too, and everything
you put in it would be visible to anyone.

## 2. Let Claude see your copy

Go to [claude.ai/connect-github](https://claude.ai/connect-github) and connect your GitHub
account. When GitHub asks which repositories the Claude app may access, choose **Only select
repositories** and pick the copy you just made.

## 3. Open it in Claude Code

Go to [claude.ai/code](https://claude.ai/code), start a new session, and choose your copy as
the repository.

The first time only, change two settings so it can make PDFs and reach job boards. Open the
cloud environment menu in the session's title bar and click **Edit**:

- **Setup script:** copy and paste this line exactly. You do not need to understand it: it
  installs the tools that turn your resume into a PDF, once, and they are kept for next time.

  ```
  apt-get update -qq && apt-get install -y --no-install-recommends texlive-luatex texlive-latex-extra texlive-xetex texlive-fonts-recommended poppler-utils && pip3 install --upgrade cffi && pip3 install pytest pypdf pyyaml openpyxl ruff
  ```

- **Network access:** the search has to reach job boards. Choose full internet access, or
  a custom list that keeps the default package managers and adds these allowed domains:
  `linkedin.com`, `www.linkedin.com`, `freehire.me`, `boards-api.greenhouse.io`,
  `api.lever.co`, `api.ashbyhq.com`, `*.myworkdayjobs.com`, and `api.openalex.org` if your
  field publishes research papers. The details are in
  [the cloud environment docs](https://code.claude.com/docs/en/cloud-environments#network-access).

Save, and start a new session so the settings apply. If you skip this, Claude can still
help, but it will stop and say what is missing the first time it needs it.

Would rather run it on your own computer? Steps 1 and 2 are the same; then go to
[On your own computer](#on-your-own-computer) below.

## 4. Say "set me up"

Claude checks your copy is private, then asks you about yourself in plain words: where you
live and would work, your right to work there, the kind of work you want, what you have done,
your salary hopes, and anything you will not do. If you have a resume or CV, paste it in and
it asks only about what is missing.

You will never be asked to name a job board or set a value. Claude researches your market
itself (which boards cover your city, what employers there post where, what pay looks like,
how documents are written locally) and writes your profile. At the end it makes a test resume
and cover letter so you can see the result.

## 5. Use it

Just talk to it. For example:

- **"Find me jobs"** gives you a scored shortlist with links, then asks which to take further.
- **Paste a posting** (or a link) and it writes a tailored resume and cover letter, and checks
  them.
- **"Who should I talk to at Acme?"** finds people worth contacting and drafts a first note,
  inside LinkedIn's limits (50 connection requests a week). It reads someone's profile in
  your own browser only if you agree to that, and starts with people you already know if you
  give it your LinkedIn connections export.
- **"What do I owe?"** lists replies and follow-ups that are due.
- **"Prep me for my interview at Acme"** gives you likely questions and your best answers.
- **"I got an interview"** or **"they replied"** updates the record and says what is next.
- **"Check my email"**, **"make me a dashboard"** or **"what should I learn?"** do what they
  say. It can also read your LinkedIn job alerts into each search, copy your pipeline into
  Notion, use your own resume template, or start your search over. You connect Gmail and
  Notion yourself, once, at [claude.ai/customize/connectors](https://claude.ai/customize/connectors).

You do not need to remember any commands. If you react to something ("too formal", "not this
kind of company"), it remembers for next time, until you say you have changed your mind.

**Which model to pick.** In the model menu, the strongest model (Opus today) is worth it for
writing applications, interview prep and setting up; the balanced one (Sonnet) is enough for
searching and keeping track. You do not have to remember this: Claude says so in one line
when the model you are on is more, or less, than a task needs.

Each new version of the app reaches your copy by itself the first day you use it, in a new
chat or one you kept open. Nothing about you is ever sent back.

For a twice-weekly brief of what you owe and what changed, say **"set up my brief"**: Claude
sets it up ([automation/README.md](automation/README.md)).

## On your own computer

Everything works the same in the Claude desktop app's Code tab or the `claude` command in a
terminal, with your copy on your own disk. The brief still runs in the cloud, so it arrives
when your computer is off. Signed in with an Anthropic API key instead of a plan, everything
works except the brief: scheduled tasks and cloud chats need a paid plan.

1. Steps 1 and 2 above. Step 2 is what lets the brief, in the cloud, read your copy.
2. Install Claude Code, the desktop app or the terminal version:
   [code.claude.com/docs](https://code.claude.com/docs/en/overview).
3. Put your copy on your computer (on its GitHub page, **Code**, then **Open with GitHub
   Desktop**, or `git clone` if you use git) and open that folder in Claude Code, as a local
   session.
4. Say "set me up". Claude checks the tools and installs what it can itself, Bun for the job
   searches included. The rest ask for your computer's password, so they are yours, once: on
   a Mac, [Homebrew](https://brew.sh) and then the one MacTeX line Claude prints; on Windows,
   [MiKTeX](https://miktex.org/download) and Poppler (`choco install poppler`). Until then
   Claude can search and write, but cannot make or check the PDFs.
5. Say "set up my brief". Claude starts a cloud chat for it (`claude --cloud`), and that
   chat creates the brief the same way a cloud session does
   ([automation/README.md](automation/README.md), set-up (a)). The desktop app's Routines
   screen works too: choose **Cloud**, because a local task runs only while the app is open
   and the computer awake.

**Already using it in the cloud?** Nothing moves: open your copy locally as in step 3 and
carry on. Cloud and local chats can be mixed, because your copy on GitHub is what they share,
and Claude merges each session's work into it, so the brief sees it. Never archive the chats
your brief is bound to.

**On a phone, or in a browser,** there is no local session: use claude.ai/code as in step 3.
The brief is set up from a chat there, so a phone is enough for that too.

---

If something goes wrong, tell Claude what you see. It can read this repository's own
documentation and will say what to change and where.
