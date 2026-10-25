# If something goes wrong

Tell Claude what you see, in your own words: it reads this app's own instructions and says
what to change and where. The usual ones:

**"This chat can't reach job sites."** A cloud chat starts with only a few websites allowed.

<!-- claude-surface: cloud-internet -->
<!-- checked 2026-10-25; https://code.claude.com/docs/en/cloud-environments -->
To let this chat reach job sites:
1. At the top of this chat, open the small arrow after its title and choose Edit cloud
   environment.
2. Set Network access to Full, then save. It reaches this chat within about a minute.

Screens change: if yours looks different, tell Claude what you see.
<!-- /claude-surface -->

**Claude can't see your copy, or it isn't in the list.** A private copy needs the Claude
GitHub App installed on it.

<!-- claude-surface: connect-github -->
<!-- checked 2026-10-25; https://code.claude.com/docs/en/web-quickstart -->
To let Claude see your copy:
1. Open claude.ai/code and sign in. When it asks to connect GitHub, follow it and approve.
2. Open github.com/apps/claude/installations/new, choose your account, then Only select
   repositories, pick your copy, and install.
3. Back at claude.ai/code (or the Code tab in the Claude app), choose your copy under the
   message box.

Screens change: if yours looks different, tell Claude what you see.
<!-- /claude-surface -->

**Your copy is public.** Setup stops until it is private, because your copy holds your work
history and the people you talk to.

<!-- claude-surface: make-private -->
<!-- checked 2026-10-25;
https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility
-->
To make your copy private:
1. On your copy's page on GitHub, open Settings.
2. In the Danger Zone section, beside Change repository visibility, choose Change
   visibility, then Private.
3. Confirm, then choose Make this repository private.

Screens change: if yours looks different, tell Claude what you see.
<!-- /claude-surface -->

**On your computer, Claude asks before every step.** Choose Auto in the mode menu under the
message box, where it is offered (step 3 of "On your computer as well" in
[START_HERE.md](START_HERE.md)).

**No brief arrived on one of its days.** The brief comes even when nothing is due, so silence
means it is broken: tell any chat "my brief didn't arrive". [automation/README.md](automation/README.md)
has the rest.

**Something else.** Say what you were doing and what it said. It never sends anything to
anyone, so nothing has gone out while it went wrong.
