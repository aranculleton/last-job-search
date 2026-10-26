# /add-portal - Generate a Job-Portal Search Skill for Your Local Market

You are building a job-portal search skill for a board that serves this person's market: their country or city, their field, their level. The app ships two portals that work in any country, `linkedin-search` and `freehire-search`; every other board is built here, for the person, by this command. `/setup` runs it for the boards its research found, and it is run again whenever a round comes back thin or a good posting arrives from a board nothing covers.

The generator works for any portal in any market and language. What it builds is the person's: `.agents/skills/<name>/` is a personal path (`tools/personal_paths.py`), so a sync never touches it, it is never reported as drift, and the app never carries it (the app's leak scan fails if it did). Once it passes Step 4, every round searches it, a scheduled one included, with nothing else to wire.

`$ARGUMENTS` may contain a subcommand, a portal URL, or nothing.

Follow these steps **in order**.

---

## Step 0: Parse Arguments

- If `$ARGUMENTS` contains `--list`: use Glob with `.agents/skills/*/SKILL.md`, print a table of installed portal skills (name, market from the description, data source from `url-reference.md`), and stop.
- If `$ARGUMENTS` contains a URL: treat it as the portal URL and carry it into Step 1.
- Otherwise: go to Step 1.

---

## Step 1: Portal Basics, worked out, never asked

Nobody is asked to name a job board or a config value (`/setup`, Step 2: "Never ask them to
name a job board"). Work each out, and say what you chose in one line:

1. **Portal URL** - from `$ARGUMENTS`, else the board `profile/search.py` `PORTAL_RESEARCH`
   names with no portal yet (`python3 tools/portals.py` lists them), else found the way
   `/setup`'s boards section researches one for this person's market and field.
2. **Skill name** - kebab-case from the board's own name, suffixed `-search` (e.g.
   `seek-search`, `stepstone-search`), never one already in `.agents/skills/`.
3. **Market and language** - the country or region the board covers and the language its
   postings use, from its own pages and `profile/person.json`. This drives the trigger
   phrases in `SKILL.md` (include the market's own terms, e.g. "Stellenangebote",
   "Jobsuche" for a German board).
4. **A realistic test query** - the first of `profile/search.py` `SCRAPE_QUERIES`, used for
   the live test in Step 4.

---

## Step 2: Investigate the Portal

Do reconnaissance before writing any code. Use WebFetch (or `curl` via Bash) on the portal:

1. **Find the search URL pattern.** Load the portal's search page, run a search in the URL bar mentally or via fetch, and identify: the search endpoint, the query parameter, and any parameters for location, posting age, and pagination. Prefer a JSON API if one backs the site (check for `/api/` XHR endpoints in the page source); otherwise plan to parse the HTML results page. An RSS feed is tempting and often ignores free-text parameters: check that a feed for two different queries returns two different lists before relying on it.
   - **Location.** Many boards filter on an internal place id rather than a name (`locationparam=22437` for one city). Find the lookup the site's own search box calls (an autocomplete or suggest endpoint) so the CLI can turn a plain place name into the id itself. A round always passes `-l "<place>"` as a person would type it, never an id, and it passes **every** place in `profile/search.py` `SCRAPE_LOCATIONS`, written the way LinkedIn writes them ("Salford, England, United Kingdom"): the CLI tries the whole name, then the part before the first comma, so each one resolves. Where the board has a distance or radius filter, the CLI applies the widest setting within a commute (about 25 km or 15 miles, or the board's own default where that is wider), so a search for a town also returns the places around it that a posting may name instead.
   - **Remote.** Find how the board marks remote work: a work-from-home filter, a "Remote" place, a contract or workplace type. Where it has one, the CLI takes `--remote` and returns remote postings only (with no `-l`, every remote posting the board has for the query), and the frontmatter says `remote: true`. Where it has none, say so in the Notes: remote postings filed under the country still reach a round through its country-wide place.
2. **Fetch one search-results response** for the test query and identify the per-result fields: **id, title, company, location, posting date, and URL**. For HTML, note the class names / attributes that anchor each field. For JSON, note the field paths.
3. **Find the detail-page pattern** - the URL that returns a single posting's full description, and where the description, deadline, employment type, and apply link live in it.
4. **Check access requirements and terms.**
   - Fetch `robots.txt` and check whether the search/detail paths are disallowed, the way `tools/robots_check.py` does. Note any `Crawl-delay` for `User-agent: *`: it becomes the portal's `crawl-delay:` (Step 3), and every round keeps to it.
   - **Follow the links a result card carries, not only the path you meant to fetch.** Some boards send a job link through a redirect (`/spl/...` answering 302 to `/sandbox?destination=...`) into a path robots.txt disallows. The search page is allowed and the posting page is not, so the portal searches only: `detail: false`, and the search result's teaser is the body a round screens.
   - If the portal requires login/authentication to view listings, **stop**: this pattern only works on public pages. Tell the user and suggest checking whether the portal has an official API.
   - If robots.txt disallows the paths or the portal's terms prohibit automated access, tell the user plainly and let them decide whether to proceed for personal use. That choice is theirs, so it is made only in a `/add-portal` they are present for (on its own or from `/setup`), and only on their explicit yes: where nobody can say yes (`/upgrade` in the background, a scheduled run) such a board is never built, and an employer board robots.txt disallows is refused by `tools/ats_boards.py` whoever asks. If they proceed, the generated `SKILL.md` **must** carry a prominent personal-use-only warning (copy the tone of `linkedin-search`'s "⚠️ Personal use only" section: keep volume low, no commercial or bulk use, own responsibility).

5. **Check whether the portal can be reached without a credential.** Some portals return usable content only through a third-party fetching service (a paid unlocker/proxy API). **This step never overrides Step 2.4:** if `robots.txt` or the portal's terms disallow access, that is decided there, and a paid fetching service does not change the answer. The credential path exists for portals whose `robots.txt` permits access but whose bot protection blocks ordinary fetches. Where that applies and the test fetch succeeds only through such a service, say so to the user **before scaffolding** - a portal that bills per query is a different proposition from a free one, and they may prefer to skip it. Note which service and which environment variable; the handling rules are in the portal-skill contract in Step 3.

Record everything you found - endpoints, parameters, field anchors, quirks - you will write it into `url-reference.md` in Step 3.

---

## Step 3: Scaffold the Skill

**Canonical reference:** read `.agents/skills/linkedin-search/` before generating - it is the zero-dependency worked example of this exact structure. Copy its architecture, not its LinkedIn-specific parsing.

Create `.agents/skills/<name>/` with:

```
<name>/
├── SKILL.md              # Skill definition with trigger phrases
├── url-reference.md      # Endpoint documentation from Step 2
└── cli/
    ├── package.json
    ├── tsconfig.json
    ├── README.md
    ├── src/
    │   ├── cli.ts        # Arg parsing, help text, command dispatch
    │   ├── helpers.ts    # Fetch with backoff, parsers, error writer
    │   └── commands/
    │       ├── search.ts
    │       └── detail.ts
    └── tests/
        └── helpers.ts    # runCLI + parseJSON test utilities (copy from linkedin-search)
```

### The portal-skill contract (every generated skill MUST honor this)

These conventions are what make portal skills interchangeable for `/scrape` and for users reading any skill's docs:

- **Commands:** `search` and `detail <id|url>`.
- **Search flags:** `--query`/`-q`, `--jobage <days>` (posting age; map to the portal's parameter, and where the board has none, still accept the flag and drop results older than it by their `date`: every round sends it), `--page <n>` (1-indexed), `--limit <n>` (client-side cap), `--format json|table|plain` (default `json`). Add `--location`/`-l <place>` if the portal filters by place, taking a plain place name and resolving any id inside the CLI (Step 2.1). If it has no location filter, say `location: none` in the frontmatter and the round sends no `-l`. Add `--remote` where the board can filter for remote work (Step 2.1), and say `remote: true`.
- **JSON output shape:** `{ "meta": { "count": ..., "page": ... }, "results": [...] }` where each result has at least `id`, `title`, `company`, `location`, `date`, `url` (missing values are `null`, never omitted), and `description` when the result card shows any text: a round keeps it as the fallback body when the detail fetch fails, and as the only body when `detail: false`.
- **`detail <id>`** returns `{ "id": ..., "description": "<the whole posting as text>", ... }`. The description must include the requirements and any "who can apply" or eligibility section: those are what the round's free screen cuts on.
- **Errors:** written to **stderr** as `{ "error": "...", "code": "..." }`, exit code `1`. Never write errors to stdout.
- **Fetching:** an honest User-Agent that names the tool (`Mozilla/5.0 (compatible; <portal>-cli/1.0)`, the convention every shipped portal CLI follows) - never a full browser impersonation; if the portal refuses that UA, escalation to browser headers goes through the robots.txt gate in `.claude/skills/job-application-assistant/09-web-research.md`, not through the CLI's default. Exponential backoff with jitter on 429/5xx (max ~6 retries), `""`/`null` on 404 rather than a crash.
- **HTML parsing:** split the response into per-result chunks and parse each independently, so one malformed card cannot break the rest (see `parseJobCards` in `linkedin-search/cli/src/helpers.ts`).
- **Dependencies:** default to **zero runtime dependencies** (plain `bun` + `fetch` + regex parsing) like `linkedin-search` - `bun install` should only pull dev types. Only add a parsing library if the portal's markup genuinely defeats chunked regex parsing, and say so in the README.
- **Credentials:** a skill that needs an API key (Step 2.5) reads it **only** from an environment variable named `<SERVICE>_API_TOKEN`. Never hardcode it, never accept it as a CLI flag (flags leak into shell history and process listings), and never write a real token into `url-reference.md`, a README example, or a test fixture. If the variable is unset, exit `1` with the standard stderr JSON error and code `MISSING_CREDENTIALS`, naming the variable to set - never fall through to an unauthenticated request that fails confusingly. The repo `.gitignore` covers `.env`; do not commit one.

### File specifics

- **`SKILL.md` frontmatter:** `name`, `version: 1.0.0`, a `description` written for skill triggering - it must name the portal, the market, and include trigger phrases in English **and** the market's language; `context: fork`; `allowed-tools: Bash(bun run .agents/skills/<name>/cli/src/cli.ts *)`. Then the lines a round reads (`tools/portals.py`), each on one line:

  ```yaml
  enabled: true
  contract: 1                       # the CLI takes every flag above; rounds call only portals that say so
  url: https://www.<board>          # the board itself; tools/env_check.py probes it
  crawl-delay: 5                    # robots.txt's Crawl-delay for *, else 1
  location: free-text               # or `none` where the board has no place filter
  remote: true                      # only where the CLI takes --remote (Step 2.1); leave it out otherwise
  detail: true                      # false where the posting page may not be fetched
  pages: 2                          # how deep each query goes; 2 suits most boards
  canary-query: <word>              # one word the board always has postings for (the round's health probe)
  ```

  Write `contract: 1` only once Step 4 has shown the CLI takes `search -q <q> [-l <place>] [--remote] --jobage <n> --page <n> --format json` and `detail <id> --format json`: a round sends exactly that, and a portal that rejects a flag fails every request.
- **`SKILL.md` body:** what the skill searches, the personal-use warning if Step 2 found terms restrictions, command reference with flags, 4-6 usage examples using the user's market (real cities, realistic roles), output-format table, and a Notes section recording portal quirks found in Step 2. If Step 2.5 found the portal needs a credential, add a **Setup** section naming the service, the exact environment variable to export, and the fact that every call is billed - stated where the user reads it before running the skill, not after.
- **`url-reference.md`:** the endpoints, parameters table, and response-structure notes from Step 2 - this is the file a future maintainer needs when the portal changes its markup.
- **`package.json`:** name `<portal>-cli`, `"type": "module"`, scripts `start`, `test` (`bun test --timeout 30000`), and `typecheck` (`tsc --noEmit`); dev-only dependencies in the zero-dependency default.
- **`tests/`:** copy `runCLI`/`parseJSON` from `linkedin-search/cli/tests/helpers.ts`, then add a small live smoke-test file: `search` with the test query returns exit code 0 and ≥1 result with non-null `id`/`title`/`url`; a bogus flag or missing required arg exits 1 with a JSON error on stderr.

---

## Step 4: Test-Run a Live Query (MANDATORY)

Never register a portal skill that has not returned real results. Markup assumptions from Step 2 routinely miss quirks that only show up live.

1. Install dev types and typecheck:
   ```bash
   cd .agents/skills/<name>/cli && bun install && bun run typecheck
   ```
2. Run the live search with the user's test query:
   ```bash
   bun run src/cli.ts search -q "<test query>" --limit 5 --format table
   ```
3. Verify the results are real and complete: titles and companies are populated (not empty strings or HTML fragments), URLs resolve to the portal, dates parse. If fields come back null or garbled, fix the parsers in `helpers.ts` and re-run. Iterate until clean. Then run it once with `-l` for every place in `SCRAPE_LOCATIONS`, exactly as written there, and once with `--remote` if the frontmatter says `remote: true`: each must return results or a clean empty list, never an error, because a round sends every one of them.
4. Take one `id` from the results and run `detail`:
   ```bash
   bun run src/cli.ts detail <id> --format plain
   ```
   Verify the description is readable text (entities decoded, tags stripped, paragraph breaks preserved).
5. Run the test suite: `bun run test`.
6. Keep volume low during iteration - a handful of requests, not a crawl. If the portal rate-limits you mid-test, back off and tell the user.

Do not proceed to Step 5 until search, detail, and tests all pass.

7. Build the bundle a round runs, and keep it with the source:
   ```bash
   cd .agents/skills/<name>/cli && bun build src/cli.ts --target node --outfile dist/cli.mjs
   ```
   A scheduled round runs `dist/cli.mjs` with node and builds it only if it is missing, which needs bun in that session. Rebuild it after every change to `src/`.

---

## Step 5: Register

Nothing needs wiring: `tools/scrape_wide.py` and `tools/hydrate.py` search and hydrate every portal that is on and has a CLI, and `/scrape` discovers `.agents/skills/*/SKILL.md`. What is left is the person's settings and the record:

1. **Check what a round will do:** `python3 tools/portals.py` lists the portal as ON, with its pace, depth and whether it fetches details. `NO CLI` means there is no `cli/` at all; `no contract: 1` means the frontmatter line is missing. A missing bundle shows neither: a round builds it with bun if bun is there, and fails that portal if not, which is why Step 4.7 commits it.
2. **Places.** A portal not named in `PORTAL_LOCATIONS` searches every place in `profile/search.py` `SCRAPE_LOCATIONS`, the first one deep and the rest two pages, as LinkedIn does. Only if the CLI cannot resolve those names (LinkedIn's "Austin, Texas, United States" against a board's "Austin, TX"), list the board's own names for every one of them in `PORTAL_LOCATIONS = {"<name>": ["<place>", ...]}`, the home place first; never fewer places than `SCRAPE_LOCATIONS` covers.
3. **The record.** Add or update the board's entry in `profile/search.py` `PORTAL_RESEARCH` with `"portal": "<name>"`, `"status": "built"`, its URL, what it covers and the date. A board looked at and not built gets an entry too, with the reason as its status: a round that misses its yield target names it.
4. **The network.** Run `python3 tools/env_check.py`. A cloud session's network policy can refuse the board's host; if it says so, the person adds the host under Allowed domains (the environment documentation has the steps), or every round reports the portal failing: it stops after three failures in a row, so the round goes on without it, but it searches nothing until the host is allowed.
5. Optionally add WebSearch/`site:` queries for the board in `profile/search-queries.md`, so the fallback path still covers it if the CLI breaks.
6. **Commit it:** `git add .agents/skills/<name> profile/search.py` and commit. It is the person's file, so a plain `git add` is enough and a sync never touches it. `./tools/ci_local.sh` typechecks every portal CLI it finds, this one included; run its tests with `bun run test` in its `cli/` when you change it.

---

## Step 6: Confirm

Present a summary:

> **Portal `<name>` built, verified and on.**
>
> - Files: `.agents/skills/<name>/` (SKILL.md, url-reference.md, CLI with tests and its bundle)
> - Live test: `search "<test query>"` returned <N> results; `detail` verified on one posting (or: search only, because <reason>)
> - Pace: <crawl-delay>s between requests, from <robots.txt or the default>
> - Data source: <endpoint summary>; <personal-use warning noted, if applicable>
>
> Every round now searches it. This portal is yours: it lives in your repo, a sync from the app never touches it, and the app never gets a copy. If the board changes its markup, `url-reference.md` records the parsing anchors to update, and the round's health probe reports it as DOWN rather than as a thin market.

---

## Design Principles

- The generator is country-agnostic; its output is market-specific and stays in the person's repo. The app ships only portals that work anywhere, and its leak scan fails on any other.
- Investigation before scaffolding: the command never generates parsers from guesses - Step 2 fetches real responses first, and Step 4 verifies against live data before anything is registered.
- The portal-skill contract keeps every generated skill interchangeable with the shipped ones: same commands, same flags, same output shape, same error convention.
- Zero runtime dependencies by default, matching `linkedin-search` - a portal skill should run on a fresh clone with nothing but `bun`.
- Access rules are surfaced, not silently bypassed: auth-walled portals are declined, robots.txt/ToS restrictions are reported to the user, restricted portals get a prominent personal-use-only warning in the generated skill, and a declared `crawl-delay` is kept by every round.
- Credentials live in the environment, never in the repo: a generated skill reads its token from an environment variable, fails loudly when it is unset, and never commits it. Per-call cost is disclosed before the skill is generated, not discovered afterwards.
