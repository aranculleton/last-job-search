#!/usr/bin/env bun
// @bun

// .agents/skills/freehire-search/cli/src/helpers.ts
var DEFAULT_BASE_URL = "https://freehire.me";
function baseUrl() {
  const raw = (process.env.FREEHIRE_API_URL ?? "").trim();
  return (raw || DEFAULT_BASE_URL).replace(/\/+$/, "");
}
function writeError(error, code) {
  process.stderr.write(JSON.stringify({ error, code }) + `
`);
}
var UA = "freehire-search-skill/1.0 (+https://freehire.me)";
async function apiGet(path) {
  const url = `${baseUrl()}${path}`;
  const maxRetries = 6;
  let delay = 500;
  for (let attempt = 0;attempt <= maxRetries; attempt++) {
    let response;
    try {
      response = await fetch(url, {
        headers: { "User-Agent": UA, Accept: "application/json" },
        redirect: "follow",
        signal: AbortSignal.timeout(15000)
      });
    } catch (e) {
      throw new Error(`could not reach the freehire API at ${baseUrl()} (${e instanceof Error ? e.message : String(e)})`);
    }
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`freehire API request failed: ${response.status} ${response.statusText}`);
      }
      await sleep(delay + Math.floor(Math.random() * 500));
      delay = Math.min(delay * 2, 8000);
      continue;
    }
    if (response.status === 404)
      return null;
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(body?.error || `freehire API request failed: ${response.status} ${response.statusText}`);
    }
    if (!body)
      throw new Error("freehire API returned an unparseable response body");
    return body;
  }
  throw new Error("freehire API request failed after retries");
}
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
function toResult(j) {
  return {
    id: j.public_slug,
    title: j.title || "(untitled)",
    company: j.company || null,
    company_slug: j.company_slug || null,
    location: j.location || null,
    date: j.posted_at,
    url: j.url,
    work_mode: j.work_mode || null,
    regions: j.regions,
    countries: j.countries,
    skills: j.skills,
    description: j.description || null
  };
}
function toDetail(j) {
  const e = j.enrichment;
  return {
    ...toResult(j),
    cities: j.cities,
    seniority: e.seniority || null,
    category: e.category || null,
    employment_type: e.employment_type || null,
    salary: formatSalary(e),
    description: cleanHtml(j.description)
  };
}
function formatSalary(e) {
  if (e.salary_min == null && e.salary_max == null)
    return null;
  const cur = e.salary_currency ? `${e.salary_currency} ` : "";
  if (e.salary_min != null && e.salary_max != null)
    return `${cur}${e.salary_min}–${e.salary_max}`;
  return `${cur}${e.salary_min ?? e.salary_max}`;
}
function numericEntity(cp) {
  return cp >= 0 && cp <= 1114111 ? String.fromCodePoint(cp) : "";
}
function decodeHtmlEntities(text) {
  return text.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&apos;/g, "'").replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10))).replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16))).replace(/&nbsp;/g, " ");
}
function cleanHtml(html) {
  if (!html)
    return null;
  const withBreaks = html.replace(/<\s*br\s*\/?>/gi, `
`).replace(/<\/(p|li|ul|ol|div|h\d)>/gi, `
`);
  const text = decodeHtmlEntities(withBreaks.replace(/<[^>]+>/g, " ")).replace(/[ \t]+/g, " ").replace(/ *\n */g, `
`).replace(/\n{3,}/g, `

`).trim();
  return text || null;
}
function normalizeSlug(input) {
  const trimmed = input.trim();
  if (!trimmed)
    return null;
  const m = trimmed.match(/\/jobs\/([^/?#]+)/);
  if (m)
    return m[1];
  if (/^[a-z0-9][a-z0-9-]*$/i.test(trimmed))
    return trimmed;
  return null;
}

// .agents/skills/freehire-search/cli/src/commands/search.ts
var SEARCH_PATH = "/api/v1/agent/jobs/search";
var DESCRIPTION_FORMATS = ["markdown", "text", "html"];
function buildQuery(opts) {
  const p = new URLSearchParams;
  if (opts.query)
    p.set("q", opts.query);
  p.set("limit", String(opts.limit));
  p.set("offset", String((opts.page - 1) * opts.limit));
  p.set("semantic_ratio", "0");
  const hydrate = opts.includeDescription !== false;
  p.set("include_description", hydrate ? "true" : "false");
  if (hydrate)
    p.set("description_format", opts.descriptionFormat);
  if (opts.jobage > 0 && opts.jobage < 9999)
    p.set("posted_within_days", String(opts.jobage));
  if (opts.workMode)
    p.set("work_mode", opts.workMode);
  if (opts.company)
    p.set("company_slug", opts.company);
  const facets = [
    ["regions", opts.regions],
    ["countries", opts.countries],
    ["cities", opts.cities],
    ["seniority", opts.seniority],
    ["category", opts.category],
    ["skills", opts.skills],
    ...Object.entries(opts.facets)
  ];
  for (const [param, values] of facets) {
    for (const value of values)
      p.append(param, value);
  }
  return p;
}
function shortDate(date) {
  return date ? date.slice(0, 10) : "—";
}
function renderTable(rows) {
  if (rows.length === 0)
    return "No results.";
  const columns = [
    { header: "SLUG", width: Math.max(4, ...rows.map((r) => r.id.length)), cell: (r) => r.id },
    { header: "TITLE", width: 38, cell: (r) => r.title },
    { header: "COMPANY", width: 22, cell: (r) => r.company ?? "—" },
    { header: "LOCATION", width: 20, cell: (r) => r.location ?? "—" },
    { header: "DATE", width: 10, cell: (r) => shortDate(r.date) }
  ];
  const row = (cells) => cells.map((c, i) => c.slice(0, columns[i].width).padEnd(columns[i].width)).join("  ");
  const header = row(columns.map((c) => c.header));
  const body = rows.map((r) => row(columns.map((c) => c.cell(r))));
  return [header, "-".repeat(header.length), ...body].join(`
`);
}
function renderPlain(rows) {
  if (rows.length === 0)
    return "No results.";
  const block = (r) => [
    r.title,
    `  ${r.company ?? "—"} · ${r.location ?? "—"} · ${shortDate(r.date)}`,
    `  slug: ${r.id}`,
    `  ${r.url}`
  ].join(`
`);
  return rows.map(block).join(`

`);
}
async function runSearch(opts) {
  try {
    const env = await apiGet(`${SEARCH_PATH}?${buildQuery(opts).toString()}`);
    if (!env) {
      writeError(`${SEARCH_PATH} not found — this freehire instance predates the agent search endpoint; upgrade it or unset FREEHIRE_API_URL to use the hosted API`, "SEARCH_FAILED");
      return 1;
    }
    let rows = (env.data ?? []).map(toResult);
    if (opts.includeDescription === false) {
      rows = rows.map((r) => ({ ...r, description: null }));
    }
    const total = env.meta?.total ?? rows.length;
    if (opts.format === "table") {
      process.stdout.write(renderTable(rows) + `
`);
    } else if (opts.format === "plain") {
      process.stdout.write(renderPlain(rows) + `
`);
    } else {
      process.stdout.write(JSON.stringify({ meta: { count: rows.length, page: opts.page, total }, results: rows }, null, 2) + `
`);
    }
    return 0;
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED");
    return 1;
  }
}

// .agents/skills/freehire-search/cli/src/commands/detail.ts
async function runDetail(opts) {
  const slug = normalizeSlug(opts.id);
  if (!slug) {
    writeError(`could not parse a freehire slug from "${opts.id}"`, "BAD_ID");
    return 1;
  }
  try {
    const env = await apiGet(`/api/v1/jobs/${encodeURIComponent(slug)}`);
    if (!env) {
      writeError("job not found", "NOT_FOUND");
      return 1;
    }
    const job = toDetail(env.data);
    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"}`,
        job.date ? `Posted: ${job.date.slice(0, 10)}` : "",
        job.seniority ? `Seniority: ${job.seniority}` : "",
        job.category ? `Category: ${job.category}` : "",
        job.employment_type ? `Employment: ${job.employment_type}` : "",
        job.salary ? `Salary: ${job.salary}` : "",
        job.skills.length ? `Skills: ${job.skills.join(", ")}` : "",
        "",
        job.description || "(no description)",
        "",
        `URL: ${job.url}`,
        `slug: ${job.id}`
      ].filter((l) => l !== "");
      process.stdout.write(lines.join(`
`) + `
`);
    } else {
      process.stdout.write(JSON.stringify(job, null, 2) + `
`);
    }
    return 0;
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "DETAIL_FAILED");
    return 1;
  }
}

// .agents/skills/freehire-search/cli/src/helpers.ts
var DEFAULT_BASE_URL2 = "https://freehire.me";
function baseUrl2() {
  const raw = (process.env.FREEHIRE_API_URL ?? "").trim();
  return (raw || DEFAULT_BASE_URL2).replace(/\/+$/, "");
}

// .agents/skills/freehire-search/cli/src/cli.ts
var ALIAS = { q: "query", n: "limit" };
function parseFlags(argv) {
  const flags = { _: [] };
  for (let i = 0;i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("-")) {
      flags._.push(a);
      continue;
    }
    const name = a.replace(/^-+/, "");
    const key = ALIAS[name] ?? name;
    const next = argv[i + 1];
    let value = true;
    if (next !== undefined && !next.startsWith("-")) {
      value = next;
      i++;
    }
    if (key === "facet") {
      const acc = Array.isArray(flags.facet) ? flags.facet : [];
      if (typeof value === "string")
        acc.push(value);
      flags.facet = acc;
    } else {
      flags[key] = value;
    }
  }
  return flags;
}
function stringFlag(raw, whenBare) {
  if (typeof raw === "string")
    return raw;
  if (raw === true)
    return whenBare;
  return;
}
function commaList(raw) {
  if (typeof raw !== "string")
    return [];
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}
var HELP = `freehire-cli \u2014 search the freehire.me job aggregator (many markets, tech-focused)

USAGE
  bun run src/cli.ts search [-q "<keywords>"] [facet flags] [--format json|table|plain]
  bun run src/cli.ts detail <slug|url> [--format json|plain]

SEARCH FLAGS
  --query, -q <text>      Keywords (title, skill, role). Full-text; optional.
  --jobage <days>         Posted within N days (maps to posted_within_days).
  --page <n>              1-indexed page. Default 1.
  --limit, -n <n>         Results per page (API limit). Default 25.
  --format <fmt>          json (default) | table | plain.
  --no-description        Skip description hydration for a cheap discovery pass
                          (results keep every other field; detail fetches the body).
  --description-format    markdown (default) | text | html \u2014 how each result's
                          full description is rendered (json output only).

FACET FILTERS (values from freehire.me's controlled vocabularies; comma = OR)
  --region <codes>        Macro-region: global, eu, us, apac, latam, cis, ...  e.g. --region eu,us
  --country <codes>       ISO-3166 alpha-2, e.g. --country DE,GB
  --city <names>          City name(s), e.g. --city Berlin
  --seniority <levels>    junior, middle, senior, staff, principal, lead, ...
  --category <cats>       backend, frontend, fullstack, devops, ml_ai, qa, ...
  --skill <names>         Canonical skill(s), e.g. --skill go,kubernetes
  --company <slug>        Company slug (from a result's company_slug).
  --remote <mode>         remote | hybrid | onsite (work_mode facet).
  --facet <key=value>     Any other facet param (repeatable), e.g. --facet salary_min=100000

DETAIL
  <slug|url>              A freehire public slug (from a search result's id/slug)
                          or a full https://freehire.me/jobs/<slug> URL.

EXAMPLES
  bun run src/cli.ts search -q "backend engineer" --seniority senior --limit 10 --format table
  bun run src/cli.ts search -q "react" --remote remote --region eu --format table
  bun run src/cli.ts search --category devops --country DE --jobage 14 --format table
  bun run src/cli.ts detail golang-zensar-2bxu6dxm --format plain

Reads are public (no API key). Source: ${baseUrl2()} \u2014 a personal project,
best-effort, no SLA. Override with FREEHIRE_API_URL to use a self-hosted backend.
`;
function parseIntFlag(name, raw) {
  const val = typeof raw === "string" ? Number(raw.trim()) : NaN;
  if (!Number.isInteger(val) || val < 1) {
    process.stderr.write(JSON.stringify({ error: `--${name} must be a whole number of at least 1, got "${raw}"`, code: "BAD_ARG" }) + `
`);
    return null;
  }
  return val;
}
var KNOWN_FLAGS = {
  search: new Set([
    "query",
    "category",
    "city",
    "company",
    "country",
    "facet",
    "format",
    "jobage",
    "limit",
    "page",
    "region",
    "remote",
    "seniority",
    "skill",
    "description-format",
    "no-description",
    "help",
    "h"
  ]),
  detail: new Set(["format", "description-format", "help", "h"])
};
async function main() {
  const argv = process.argv.slice(2);
  const flags = parseFlags(argv);
  const cmd = flags._[0];
  if (!cmd || flags.help || flags.h) {
    process.stdout.write(HELP);
    return cmd ? 0 : 1;
  }
  const knownFlags = KNOWN_FLAGS[cmd];
  if (knownFlags) {
    for (const key of Object.keys(flags)) {
      if (key === "_" || knownFlags.has(key))
        continue;
      process.stderr.write(JSON.stringify({
        error: `unknown flag --${key} for '${cmd}' - flags are never silently ignored, because a discarded filter changes what the search returns; see --help for the supported flags`,
        code: "UNKNOWN_FLAG"
      }) + `
`);
      return 1;
    }
  }
  if (cmd === "search") {
    const fmt = flags.format || "json";
    const descFmt = stringFlag(flags["description-format"]) ?? "markdown";
    if (!DESCRIPTION_FORMATS.includes(descFmt)) {
      const supported = DESCRIPTION_FORMATS.join("|");
      process.stderr.write(JSON.stringify({ error: `--description-format must be one of ${supported}, got "${descFmt}"`, code: "BAD_ARG" }) + `
`);
      return 1;
    }
    for (const name of ["jobage", "page", "limit"]) {
      if (flags[name] !== undefined) {
        const v = parseIntFlag(name, flags[name]);
        if (v === null)
          return 1;
        flags[name] = String(v);
      }
    }
    const facets = {};
    const rawFacets = Array.isArray(flags.facet) ? flags.facet : [];
    for (const kv of rawFacets) {
      const eq = kv.indexOf("=");
      if (eq <= 0) {
        process.stderr.write(JSON.stringify({ error: `invalid --facet "${kv}", want key=value`, code: "BAD_ARG" }) + `
`);
        return 1;
      }
      const key = kv.slice(0, eq);
      const vals = commaList(kv.slice(eq + 1));
      facets[key] = (facets[key] ?? []).concat(vals);
    }
    const opts = {
      query: stringFlag(flags.query),
      jobage: flags.jobage ? parseInt(flags.jobage, 10) : 9999,
      page: flags.page ? Math.max(1, parseInt(flags.page, 10)) : 1,
      limit: flags.limit ? Math.max(1, parseInt(flags.limit, 10)) : 25,
      format: ["json", "table", "plain"].includes(fmt) ? fmt : "json",
      descriptionFormat: descFmt,
      includeDescription: flags["no-description"] === undefined,
      regions: commaList(flags.region),
      countries: commaList(flags.country),
      cities: commaList(flags.city),
      seniority: commaList(flags.seniority),
      category: commaList(flags.category),
      skills: commaList(flags.skill),
      company: stringFlag(flags.company),
      workMode: stringFlag(flags.remote, "remote"),
      facets
    };
    return runSearch(opts);
  }
  if (cmd === "detail") {
    const id = flags._[1];
    if (!id) {
      process.stderr.write(JSON.stringify({ error: "detail requires a <slug|url>", code: "NO_ID" }) + `
`);
      return 1;
    }
    const fmt = flags.format || "json";
    const opts = { id, format: fmt === "plain" ? "plain" : "json" };
    return runDetail(opts);
  }
  process.stderr.write(JSON.stringify({ error: `Unknown command "${cmd}"`, code: "BAD_CMD" }) + `
`);
  return 1;
}
main().then((code) => process.exit(code)).catch((e) => {
  process.stderr.write(JSON.stringify({
    error: e instanceof Error ? e.message : String(e),
    code: "INTERNAL_ERROR"
  }) + `
`);
  process.exit(1);
});
