# Discovery playbook

## Before searching a company at all

Three checks, in order. Each one that fails saves two searches.

1. **Does the city house the function?** A large employer's office in the
   target city can be only sales and production; a data search there returns
   Account Executives and Client Partners. A company can have no data science
   presence in the country at all. Check before spending a call.
2. **Is the name ambiguous?** `discovery.COLLISIONS` holds the known ones (read
   from `NAME_COLLISIONS` in `profile/employers.py`). Acme the AI lab is not
   Acme Health. Verify entity, industry and headquarters.
3. **Has it been searched already?** `company_research/<key>.json` holds the
   verdict as `network_presence`, dated. A company recorded as having no relevant
   presence is not re-searched until its `review_after` date
   (`discovery.presence_ruled_out()`), because teams get stood up.

## Search order per company

Alumni first, cold last. The response rate difference is large enough that
running them in the wrong order wastes the good hooks.

Every query below runs with `allowed_domains=["linkedin.com", "<country>.linkedin.com"]`,
and every returned URL goes through `discovery.resolve_result()` first (`is_person_url()`
alone would discard the post permalinks where tier-1 signals live). The `site:`
operator is not used in these profile queries: see "Searching LinkedIn for people" in
`SKILL.md` for what happened when it was.

| Order | Mode | Query shape |
|---|---|---|
| 1 | `alumni_employer` | `"linkedin.com/in" "Acme Analytics" "<City>" "data"` |
| 2 | `hiring_team` | names on the live posting, no search needed |
| 3 | `alumni_school` | `"linkedin.com/in" "<University>" <City> data` |
| 4 | `cold` | `"linkedin.com/in" "data science manager" OR "head of data" Acme <City>` |

The user's past employers and school, for alumni searches, are the ones in
`profile/01-candidate-profile.md`. Search every name a former colleague's profile
might show for each employer, not only the one on the resume. Every employer they have
left gets a turn: the one most recently left leads every run, and the others take turns
behind it a day at a time (`sources.py` `_alumni_order`), so an older employer's alumni are
searched too. The one they work at now gets none: people there are colleagues, not alumni, and a job
search is often kept from the current employer.

**An employer's legal entity can differ from its brand, so search both.** Where a
past employer trades under one name and employs people through another, searching the
trading name alone misses everyone whose profile shows the entity.

**Run alumni before cold, every time.** Alumni answer far more often than cold
contacts, and that gap is why the order in the table above is not a preference. A run
that opens with cold outreach has spent its connection requests on the worst channel
available.

## Why a title query returns executives, and what to do instead

Measured over several discovery runs. The title sets in
`discovery.TITLE_SETS` are correctly pitched: `hiring_authority` tops out at
VP Data and Head of Data, and `senior_ic` is Staff, Principal, Lead and Senior
Data Scientist. The queries ask for the right grade. **The channel returns the
wrong people anyway.**

Public web search indexes press releases, leadership pages, award announcements
and conference programmes. A Chief Data Officer appears in all four. A Senior
Manager in retail risk modelling appears in none, and their LinkedIn profile is
behind a login wall, so a query naming their exact title returns the CDAO of the
same bank, a job-board page, or nothing.

**Run both, every time.** In an early run every mid-level name came from a roster or an
org chart, and the title queries produced chief data officers and global heads of data. A
later measurement over five employers in one city (2026-10-17, counts only) turned it
round: the title queries found 26 people in 10 searches, mostly individual contributors
and managers, and the rosters 33 in 16 calls, two thirds of them directors or above.
Which source pays depends on the market and the week, so a run reads the rosters once
(one page serves every employer in it) and runs the title queries per company. The
rosters for the candidate's market are `ROSTERS` in `profile/networking.py`, in the order
to read them, and `discovery.roster_first()` returns them. The kinds of source that paid, in order:

1. A practitioner ML conference's speaker page - practitioners rather than
   executives
2. The widest regional data summit's full speaker list - the source that reaches
   the most employers
3. An industry data summit's speaker page
4. `theorg.com/org/<company>/org-chart` - names below the executive line
5. A named person's own blog post or conference bio
6. In a field that publishes, the employer's recent papers (`tools/network/openalex.py`,
   when `OPENALEX` is on) - the researchers no roster lists

Ask a roster for **everyone**, not for the relevant ones. A fetch that says
"list every speaker with title and company" returns thirty usable names; the
same page asked for "data leaders at banks" returns eight executives, because
the filtering happens before you see the list.

**Rosters go stale too.** A roster name can have left the named employer within
months, or be impossible to find at all. Verify every roster name against a
second source before it is sent, and put the date on the row.

## Reading a snippet

What is worth extracting, in priority order:

1. **A hiring quote.** Anything matching `discovery.HIRING_SIGNAL`. Capture it
   verbatim: it is both the tier-1 justification and the hook for the message.
2. **Title and team.** Decides tier 2 versus 3, and whether the function matches.
3. **Location on `worksFor`.** The title can say <City> while the person sits
   in New York.
4. **Recency markers.** "my last day", "excited to share I've joined" mean the
   person has moved and the row is stale.

## The target is the number asked for. Reporting short is a failure, not a finding.

Standing rule: **when a number is asked for, produce that number.** A run that
returns two names and a paragraph explaining why two was all there was has not
done the job, and "the search was thin" is almost never true. It usually turns
out to mean the wrong source was being queried.

If a run is struggling, the fault is the method, and the order to check it in:

1. **Has `network_contacts.csv` been read before anything was searched for?**
   This is first because it is cheapest and it is the check most often skipped.
   A store can hold `not_contacted` rows with a real name, a real title and a
   real employer and **no `linkedin_url`** - the only thing standing between
   them and a sendable note. Resolving a URL is one search against a name that
   is already known, against the several searches a new name costs. Mine the
   store first, every time.
2. **Was only one source tried?** Title queries and rosters reach different people. Run both, above.
3. **Is the roster being filtered before it is read?** Ask for every speaker,
   not for the relevant ones.
4. **Has the source list been exhausted, or just the first source?** The
   rosters in `profile/networking.py` are a start and there are more: vendor summits, meetup
   organiser pages, university partner pages, podcast guest lists, a named
   person's own conference bio.
5. **Is a company on `do_not_target.json`?** An entry there is a real stop, and
   the honest answer is to name it and pick a different employer, not to return
   nothing.

Only after all five is "exhausted" a real answer, and it has to name what was
tried. Stopping early and calling it thin wastes the user's turn and hides a
fixable method problem behind a market claim.

## What a good run produces

Against five companies: a handful of searches, three to eight correctly filtered
named people, **at least one tier 1 with the hiring signal quoted**, drafts under
the character limit, and an honest list of dead ends with reasons.

Twenty mediocre names is a failure, not a bigger success.

## Free company discovery

Job-board aggregator pages surface constantly during people searches and list
other companies hiring the same role in the same city. Harvest those company
names into the next run's target list. They cost nothing: the call was already
spent.
