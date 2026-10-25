# Security

The app is public and holds no person. Each person's search runs in their own copy, made
with "Use this template" and kept **private**, because it holds their history, their salary
expectations and every contact they message. This file is a statement of the threat model
and the controls, not a vulnerability intake process.

If you find something, report it privately: the **Security** tab has a **Report a
vulnerability** button
([direct link](https://github.com/aranculleton/last-job-search/security/advisories/new)).
Something minor with no personal details in it can be an ordinary issue. If the finding is in
code inherited from [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search),
it likely affects every fork of that template, and the responsible path is their
[private vulnerability reporting](https://github.com/MadsLorentzen/ai-job-search/security/advisories/new)
rather than an issue here.

## Threat model

An agentic workflow reads untrusted web content (job postings, company pages, LinkedIn
profiles) in the same context as personal data (full employment history, contact details,
salary expectations, and every contact made along with what was said to each). That
combination is the risk surface. It can be narrowed, not eliminated.

### What is actually at stake here

Ranked roughly by how bad it would be:

1. **A fabricated claim reaching an employer.** The worst thing this system can do, even
   though it is not a security bug in the usual sense. Guarded by `tools/check_claims.py`,
   the grounding audit that never runs on a downgraded model, and the rule in
   `11-cost-model.md`: anything that could put a false claim in front of an employer runs
   on the strongest model available, cheapness is never a reason to risk a fabrication.
2. **The contact list leaking.** `network_contacts.csv` names real people, their
   employers, and sometimes what they said in confidence about their own organisation.
   This file is why a person's copy must be private.
3. **Prompt injection from a posting.** A posting body is attacker-controlled text. The
   interesting attack is not "ignore previous instructions": it is a posting that quietly
   steers company research to a URL the attacker controls, so the cover letter cites a
   fact the attacker chose.

   The archived posting is wrapped by `tools/untrusted.py` in a fence whose markers carry
   a random token generated per posting, with the rule stated outside the fence and any
   marker-shaped string stripped from the content first. The previous delimiter was a
   `---` rule, which the posting author can write themselves, followed by a heading that
   looks like the rest of the document. That closes the cheapest attack, a posting that
   writes a plausible instruction block and hopes, and nothing more: the controls that
   carry the real weight are still never fetching a URL found inside a posting, and
   verifying company claims only against independently located sources.
4. **A widened permission allowlist.** The allowlist is what stands between a scripted
   workflow and arbitrary command execution on a machine holding all of the above.

### The controls

- **Untrusted input is data.** `/apply` and `/rank` treat posting text as data, never
  instructions. URLs found inside a posting body are never fetched. Company research
  starts from the confirmed company identity and a source located independently, which
  is what closes threat 3 above. The verification checklist repeats it, so a
  claim sourced from inside a posting fails the check rather than shipping.
  A LinkedIn profile read before a note is written is the same: `tools/network/reading.py`
  keeps only what a note could rest on, strips fence markers from it, and a model sees it
  only through `reading.fenced()`. LinkedIn itself is never fetched from a session; a
  profile is read in the person's own browser only when they chose that, or from their paste.
  That read is opt-in because LinkedIn's terms forbid automated access at any pace, and the
  account at risk is theirs.
- **Permission allowlist, guard-enforced.** `.claude/settings.json` pre-approves only the
  specific commands the workflow needs. `tools/security_guards.py` runs in CI and fails
  any change that widens the allowlist, adds a package-manifest lifecycle script, or
  weakens the personal-data `.gitignore` rules. The allowlist governs Bash; the model's
  native WebFetch and WebSearch are outside its reach, which is exactly why the
  instruction-level rules above have to carry their own weight.
- **`.gitignore` is not edited.** Its rules are asserted by the guard, so weakening them
  fails the build. Artifacts that genuinely belong in a person's private copy are
  force-added with `git add -f`, which leaves the rules intact. The inversion is
  deliberate: upstream ships "never commit the tracker" because its forks are public, and
  a person's copy is private with ephemeral sessions, so uncommitted state is lost state.
- **The app never holds a person.** It is built from a person's repo by removing every
  path `tools/personal_paths.py` lists and scanning what is left for their names and
  facts (`tools/build_app.py`, `tools/leak_scan.py`); the app's CI runs the same scan on
  every push.
- **Nothing is sent.** No command in this repo submits an application, sends a message or
  emails a person, and nothing is copied to any outside service. Every artifact stops at a
  file on disk and waits for a human.
- **Secrets are not in the repo.** `salary_data.json` (licensed third-party data) stays
  uncommitted. No API keys are stored here; the portal CLIs hit public endpoints.
- **No mailbox and no connectors.** Nothing here reads or sends email or connects to any
  outside account. The only accounts a session touches are the person's own GitHub copy and
  Claude itself; a LinkedIn download is a file the person gives it.

### What these controls are not

Instruction-level defences raise the bar. They are not a sandbox, and a model that has
been successfully steered will also happily report that it was not. The real backstop is
that a person reads every document before it goes out, which the workflow enforces by
never sending anything itself.

## Scope notes

- Portal CLIs make live requests only when run. CI never does: it typechecks and runs
  fixture tests. `linkedin-search` is personal-use only per its own terms warning, and
  CI-automating it would breach that. A person can switch it off in `profile/search.py` `PORTALS` (`tools/portals.py` prints
  what is on),
  and `scrape_wide.py` and `hydrate.py` send a portal that is off no request at all.
- `tools/robots_check.py` gates the browser-header retry against `robots.txt`.
- The app ships only the two portals that work in any country. A person's own portals,
  built by `/add-portal`, live in their private repo, are kept to the `crawl-delay` their
  `SKILL.md` declares, and never reach the app: `tools/leak_scan.py` fails on one.
