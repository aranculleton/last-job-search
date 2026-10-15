export const meta = {
  name: 'repo-audit',
  description: 'Read the whole repo in four slices, verify every finding against the files, and rank what is disconnected, stale or wrong',
  whenToUse: 'Monthly, or after a burst of changes by several sessions. Read-only: it reports and changes nothing. Args (optional): {focus: "<extra instruction>"}',
  phases: [
    { title: 'Read', detail: 'four parallel readers, one slice each', model: 'sonnet' },
    { title: 'Verify', detail: 'a sceptic per slice re-checks every finding against the cited lines', model: 'sonnet' },
    { title: 'Rank', detail: 'merge, dedupe and rank across slices' },
  ],
}

// Why four slices and cheap readers: reading is fetching and summarising, which
// 11-cost-model.md puts on sonnet. The ranking stage inherits the session model
// because deciding what matters most is judgement. Nothing here edits a file;
// the session that runs it decides what to fix.

const FINDINGS = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: {
      severity: { type: 'string', enum: ['high', 'medium', 'low'] },
      where: { type: 'string' },
      problem: { type: 'string' },
      evidence: { type: 'string' },
      fix: { type: 'string' },
    }, required: ['severity', 'where', 'problem', 'evidence', 'fix'] } },
  },
  required: ['findings'],
}

const focus = (args && args.focus) ? `\nExtra focus for this run: ${args.focus}\n` : ''
const RULES = `Read-only: do not modify any file and run no git command that writes. Report only what you can evidence from the files (quote them, with file:line). Skip style opinions. A wrong finding costs more than a missed one.${focus}`

const SLICES = [
  { key: 'docs', prompt: `Audit the documentation and rules layer: CLAUDE.md, README.md, ARCHITECTURE.md, RUNBOOK.md, SETUP.md, CONTRIBUTING.md, SECURITY.md, AGENTS.md, CHANGELOG.md, every file in .claude/commands/, .claude/skills/, .claude/workflows/, every .agents/skills/*/SKILL.md, .github/workflows/*.yml and documents/README.md. Find references to files, functions, flags, commands or skills that do not exist; contradictions between documents or between a document and the code; statements written as current that the code or changelog shows have changed; candidate facts in profile/CLAUDE.md that disagree with profile/01-candidate-profile.md; and rules described as enforced in code that no code enforces.` },
  { key: 'code', prompt: `Audit the pipeline and document-generator code: every tools/*.py and tools/*.sh, templates/resume_gen.py, salary_lookup.py. Find code nothing calls (not imported, not in CI or tools/ci_local.sh, not named in any command or skill); real bugs (dates and business days, off-by-one, swallowed exceptions, ignored exit codes, machine-specific paths); field-name mismatches between stages (scrape, prefilter, hydrate, text_screen, opportunity, fit, throttle, render, fit_to_page, verify_batch, outreach); anything that breaks on Python 3.10; and wasted HTTP or recomputation in a round. Run python3 -m pytest tests -q and ./tools/ci_local.sh --quick once each and report the results.` },
  { key: 'network', prompt: `Audit the networking layer and its state: tools/network/*.py, tools/company_key.py, the contact-reading parts of tools/throttle.py, network_contacts.csv, network_threads.csv, documents/network/ and company_research/*.json. Run python3 tools/network/state.py and python3 tools/open_actions.py. Find contact status or next_action the message log contradicts, duplicate people, threads with no contact, company_key joins that fail between contacts and job_search_tracker.csv, stated rules (one nudge, 5 to 7 business days, stop after two nos, connection notes within schema.LIMITS (200 characters on a free LinkedIn account, 300 on Premium), never re-surface someone contacted) that a code path bypasses, and prep documents older than the contact's latest message.` },
  { key: 'records', prompt: `Audit the application records: job_search_tracker.csv, documents/applications/**, cv/*.tex, cover_letters/*.tex, documents/rounds/*.json, job_scraper/do_not_target.json and the structure of job_scraper/seen_jobs.json (summarise with python, never print it). Find tracker rows whose files are missing and files with no row, duplicate rows for one role, rows with no role title, statuses outside the vocabulary tests/test_tracker_status_vocab.py allows, rule breaches in rendered documents (em dashes, the banned nouns in profile/person.json, and anything profile/CLAUDE.md rules out, such as location phrasing, certifications not held or confidential client names), drafted applications gone stale, and do_not_target entries past review_after.` },
]

const results = await pipeline(
  SLICES,
  (s) => agent(`${s.prompt}\n\n${RULES}\nReturn at most 30 findings, most important first.`,
    { label: `read:${s.key}`, phase: 'Read', schema: FINDINGS, model: 'sonnet' }),
  (found, s) => agent(`You are a sceptic. Below are findings another reader made about this repository (slice: ${s.key}). For EACH one, open the cited file and lines and try to refute it. Keep a finding only if the evidence holds exactly as stated; correct its details if they are slightly off; drop it if it does not reproduce. ${RULES}\n\nFindings:\n${JSON.stringify(found.findings, null, 1)}`,
    { label: `verify:${s.key}`, phase: 'Verify', schema: FINDINGS, model: 'sonnet', effort: 'high' })
    .then(v => ({ slice: s.key, findings: (v && v.findings) || [] })),
)

const kept = results.filter(Boolean)
const total = kept.reduce((n, r) => n + r.findings.length, 0)
log(`${total} findings survived verification across ${kept.length} slices`)
if (!total) return { ranked: [], note: 'nothing survived verification' }

phase('Rank')
const ranked = await agent(`Merge these verified findings from four slices of one repository audit. Collapse duplicates (the same defect seen from two slices is one finding, keep the better evidence), then rank by consequence for the job search this repo runs: anything that could put a false claim in front of an employer, lose state, or silently drop a job or a contact ranks first. Do not add findings of your own and do not re-verify.\n\n${JSON.stringify(kept, null, 1)}`,
  { label: 'rank', phase: 'Rank', schema: FINDINGS })
return ranked
