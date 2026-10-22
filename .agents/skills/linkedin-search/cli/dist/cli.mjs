#!/usr/bin/env bun
// @bun

// .agents/skills/linkedin-search/cli/src/helpers.ts
var SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search";
var DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting";
function writeError(error, code) {
  process.stderr.write(JSON.stringify({ error, code }) + `
`);
}
var UA = "Mozilla/5.0 (compatible; linkedin-search-cli/1.0)";
async function htmlFetch(url) {
  const maxRetries = 6;
  let delay = 500;
  for (let attempt = 0;attempt <= maxRetries; attempt++) {
    const response = await fetch(url, {
      headers: {
        "User-Agent": UA,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest"
      },
      redirect: "follow",
      signal: AbortSignal.timeout(15000)
    });
    if (response.status === 999) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`.trim());
    }
    if (response.status === 429 || response.status >= 500) {
      if (attempt === maxRetries) {
        throw new Error(`Request failed: ${response.status} ${response.statusText}`);
      }
      const jitter = Math.floor(Math.random() * 500);
      await new Promise((r) => setTimeout(r, delay + jitter));
      delay = Math.min(delay * 2, 8000);
      continue;
    }
    if (response.status === 404)
      return "";
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status} ${response.statusText}`);
    }
    return response.text();
  }
  throw new Error("Request failed after max retries");
}
function extractDivContent(html, className) {
  const escaped = className.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const openRe = new RegExp(`<div[^>]*class="[^"]*${escaped}[^"]*"[^>]*>`, "i");
  const open = openRe.exec(html);
  if (!open)
    return null;
  let i = open.index + open[0].length;
  let depth = 1;
  while (depth > 0 && i < html.length) {
    const nextOpen = html.indexOf("<div", i);
    const nextClose = html.indexOf("</div>", i);
    if (nextClose === -1)
      return null;
    if (nextOpen !== -1 && nextOpen < nextClose) {
      depth++;
      i = nextOpen + 4;
    } else {
      depth--;
      i = nextClose + 6;
    }
  }
  return html.slice(open.index + open[0].length, i - 6);
}
function numericEntity(cp) {
  return cp >= 0 && cp <= 1114111 ? String.fromCodePoint(cp) : "";
}
function decodeHtmlEntities(text) {
  return text.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&apos;/g, "'").replace(/&#(\d+);/g, (_, dec) => numericEntity(parseInt(dec, 10))).replace(/&#[xX]([0-9a-fA-F]+);/g, (_, hex) => numericEntity(parseInt(hex, 16))).replace(/&nbsp;/g, " ");
}
function stripTags(html) {
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}
function clean(html) {
  return decodeHtmlEntities(stripTags(html));
}
function parseJobCards(html) {
  const results = [];
  const chunks = html.split(/data-entity-urn="urn:li:jobPosting:/).slice(1);
  for (const chunk of chunks) {
    const idMatch = chunk.match(/^(\d+)/);
    if (!idMatch)
      continue;
    const id = idMatch[1];
    const linkMatch = chunk.match(/class="base-card__full-link[^"]*"[^>]*href="([^"]+)"/i);
    const url = linkMatch ? decodeHtmlEntities(linkMatch[1]).split("?")[0] : "";
    let title = null;
    const h3 = chunk.match(/class="base-search-card__title"[^>]*>([\s\S]*?)<\/h3>/i);
    if (h3)
      title = clean(h3[1]);
    if (!title) {
      const sr = chunk.match(/class="sr-only"[^>]*>([\s\S]*?)<\/span>/i);
      if (sr)
        title = clean(sr[1]);
    }
    if (!title)
      continue;
    let company = null;
    let companyUrl = null;
    const sub = chunk.match(/class="base-search-card__subtitle"[^>]*>([\s\S]*?)<\/h4>/i);
    if (sub) {
      const a = sub[1].match(/href="([^"]+)"/i);
      if (a)
        companyUrl = decodeHtmlEntities(a[1]).split("?")[0];
      company = clean(sub[1]) || null;
    }
    const loc = chunk.match(/class="job-search-card__location"[^>]*>([\s\S]*?)<\/span>/i);
    const location = loc ? clean(loc[1]) || null : null;
    const dt = chunk.match(/class="job-search-card__listdate[^"]*"[^>]*datetime="([^"]+)"/i);
    const date = dt ? dt[1] : null;
    results.push({
      id,
      title,
      company,
      companyUrl,
      location,
      date,
      url: url || `https://www.linkedin.com/jobs/view/${id}`
    });
  }
  return results;
}
function parseJobDetail(html, id) {
  const title = html.match(/class="(?:top-card-layout__title|topcard__title)[^"]*"[^>]*>([\s\S]*?)<\/h[12]>/i)?.[1];
  const orgMatch = html.match(/class="topcard__org-name-link[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/i);
  const company = orgMatch ? clean(orgMatch[2]) || null : null;
  const companyUrl = orgMatch ? decodeHtmlEntities(orgMatch[1]).split("?")[0] : null;
  const locMatch = html.match(/class="topcard__flavor topcard__flavor--bullet"[^>]*>([\s\S]*?)<\/span>/i);
  const location = locMatch ? clean(locMatch[1]) || null : null;
  let description = null;
  const descHtml = extractDivContent(html, "show-more-less-html__markup") ?? extractDivContent(html, "description__text");
  if (descHtml) {
    const withBreaks = descHtml.replace(/<\s*br\s*\/?>/gi, `
`).replace(/<\/(p|li|ul|ol|div|h\d)>/gi, `
`);
    description = decodeHtmlEntities(stripTags(withBreaks)).replace(/\n{3,}/g, `

`).trim() || null;
  }
  const criteria = {};
  const itemRe = /class="description__job-criteria-subheader"[^>]*>([\s\S]*?)<\/h3>[\s\S]*?class="description__job-criteria-text[^"]*"[^>]*>([\s\S]*?)<\/span>/gi;
  let cm;
  while ((cm = itemRe.exec(html)) !== null) {
    criteria[clean(cm[1]).toLowerCase()] = clean(cm[2]);
  }
  const descStart = html.search(/class="(?:show-more-less-html__markup|description__text)/i);
  const topcard = descStart === -1 ? html : html.slice(0, descStart);
  const isActive = !/closed-job__flavor|no longer accepting applications/i.test(topcard);
  return {
    id,
    title: title ? clean(title) : "(untitled)",
    company,
    companyUrl,
    location,
    date: null,
    url: `https://www.linkedin.com/jobs/view/${id}`,
    description,
    seniority: criteria["seniority level"] ?? null,
    employmentType: criteria["employment type"] ?? null,
    jobFunction: criteria["job function"] ?? null,
    industries: criteria["industries"] ?? null,
    isActive
  };
}
function jobageToTPR(days) {
  if (!days || days <= 0 || days >= 9999)
    return null;
  return `r${days * 86400}`;
}
function minutesToTPR(minutes) {
  if (!minutes || minutes <= 0)
    return null;
  return `r${minutes * 60}`;
}
function workTypeFlag(mode) {
  switch ((mode || "").toLowerCase()) {
    case "remote":
      return "2";
    case "hybrid":
      return "3";
    case "onsite":
    case "on-site":
      return "1";
    default:
      return null;
  }
}

// .agents/skills/linkedin-search/cli/src/commands/search.ts
function buildUrl(opts) {
  const params = new URLSearchParams;
  if (opts.query)
    params.set("keywords", opts.query);
  if (opts.location)
    params.set("location", opts.location);
  const tpr = opts.jobageMinutes !== undefined ? minutesToTPR(opts.jobageMinutes) : jobageToTPR(opts.jobage);
  if (tpr)
    params.set("f_TPR", tpr);
  const wt = workTypeFlag(opts.remote);
  if (wt)
    params.set("f_WT", wt);
  params.set("start", String((opts.page - 1) * 10));
  return `${SEARCH_URL}?${params.toString()}`;
}
function renderTable(cards) {
  if (cards.length === 0)
    return "No results.";
  const rows = cards.map((c) => {
    const title = (c.title || "").slice(0, 42).padEnd(42);
    const company = (c.company || "—").slice(0, 26).padEnd(26);
    const loc = (c.location || "—").slice(0, 24).padEnd(24);
    const date = c.date || "—";
    return `${c.id.padEnd(11)} ${title} ${company} ${loc} ${date}`;
  });
  const header = "ID".padEnd(11) + " " + "TITLE".padEnd(42) + " " + "COMPANY".padEnd(26) + " " + "LOCATION".padEnd(24) + " DATE";
  return [header, "-".repeat(header.length), ...rows].join(`
`);
}
async function runSearch(opts) {
  try {
    const html = await htmlFetch(buildUrl(opts));
    let cards = parseJobCards(html);
    if (opts.limit !== undefined && opts.limit >= 0)
      cards = cards.slice(0, opts.limit);
    if (opts.format === "table") {
      process.stdout.write(renderTable(cards) + `
`);
    } else if (opts.format === "plain") {
      process.stdout.write(cards.map((c) => `${c.title}
  ${c.company || "—"} · ${c.location || "—"} · ${c.date || "—"}
  id: ${c.id}
  ${c.url}`).join(`

`) + `
`);
    } else {
      process.stdout.write(JSON.stringify({ meta: { count: cards.length, page: opts.page }, results: cards }, null, 2) + `
`);
    }
    return 0;
  } catch (e) {
    writeError(e instanceof Error ? e.message : String(e), "SEARCH_FAILED");
    return 1;
  }
}

// .agents/skills/linkedin-search/cli/src/commands/detail.ts
function normalizeId(input) {
  const urn = input.match(/urn:li:jobPosting:(\d+)/);
  if (urn)
    return urn[1];
  const url = input.match(/-(\d{6,})(?:[\/?]|$)/) || input.match(/\/(\d{6,})(?:[\/?]|$)/);
  if (url)
    return url[1];
  const bare = input.match(/^\d{6,}$/);
  if (bare)
    return input;
  return null;
}
async function runDetail(opts) {
  const id = normalizeId(opts.id);
  if (!id) {
    writeError(`Could not parse a job ID from "${opts.id}"`, "BAD_ID");
    return 1;
  }
  try {
    const html = await htmlFetch(`${DETAIL_URL}/${id}`);
    if (!html) {
      writeError("Job not found", "NOT_FOUND");
      return 1;
    }
    const job = parseJobDetail(html, id);
    if (opts.format === "plain") {
      const lines = [
        job.title,
        `${job.company || "—"} · ${job.location || "—"}`,
        "",
        job.seniority ? `Seniority: ${job.seniority}` : "",
        job.employmentType ? `Employment: ${job.employmentType}` : "",
        job.jobFunction ? `Function: ${job.jobFunction}` : "",
        job.industries ? `Industries: ${job.industries}` : "",
        `Status: ${job.isActive ? "ACTIVE" : "CLOSED / EXPIRED"}`,
        "",
        job.description || "(no description)",
        "",
        `URL: ${job.url}`
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

// .agents/skills/linkedin-search/cli/src/cli.ts
function parseFlags(argv) {
  const flags = { _: [] };
  const alias = { q: "query", l: "location", n: "limit" };
  for (let i = 0;i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--") || a.startsWith("-")) {
      const key = alias[a.replace(/^-+/, "")] ?? a.replace(/^-+/, "");
      const next = argv[i + 1];
      if (next === undefined || next.startsWith("-")) {
        flags[key] = true;
      } else {
        flags[key] = next;
        i++;
      }
    } else {
      flags._.push(a);
    }
  }
  return flags;
}
var HELP = `linkedin-cli \u2014 search jobs on LinkedIn (any country/region, plus remote)

USAGE
  bun run src/cli.ts search --location "<place>" [flags]
  bun run src/cli.ts detail <id|url> [--format json|plain]

SEARCH FLAGS
  --location, -l <text>   Location to search. REQUIRED. e.g. "Mumbai, Maharashtra, India",
                          "Berlin, Germany", "London, United Kingdom", or "Remote".
  --query, -q <text>      Keywords (job title, skill, or role). Recommended.
  --jobage <days>         Posted within N days: 1, 7, 14, 30. Default: all.
  --jobage-minutes <n>    Posted within N minutes (sub-day precision). Conflicts with --jobage.
  --remote <mode>         remote | hybrid | onsite. Filter by workplace type.
  --page <n>              1-indexed page (10 results/page). Default 1.
  --limit, -n <n>         Cap results emitted (client-side).
  --format <fmt>          json (default) | table | plain.

EXAMPLES
  bun run src/cli.ts search -q "data engineer" -l "Bengaluru, Karnataka, India" --jobage 30 --format table
  bun run src/cli.ts search -q "product manager" -l "Berlin, Germany" --remote remote --format table
  bun run src/cli.ts search -q "paralegal" -l "Remote" --format table
  bun run src/cli.ts search -q "engineer" -l "Remote" --jobage-minutes 30 --format table
  bun run src/cli.ts detail 4300011451 --format plain

Personal use only \u2014 uses LinkedIn's public pages; keep volume low (LinkedIn ToS).
`;
var KNOWN_FLAGS = {
  search: new Set([
    "location",
    "query",
    "jobage",
    "jobage-minutes",
    "remote",
    "page",
    "limit",
    "format",
    "help",
    "h"
  ]),
  detail: new Set(["format", "help", "h"])
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
    const location = typeof flags.location === "string" ? flags.location : undefined;
    if (!location) {
      process.stderr.write(JSON.stringify({
        error: 'the --location/-l flag is required (e.g. -l "Mumbai, Maharashtra, India", -l "Berlin, Germany", or -l "Remote")',
        code: "NO_LOCATION"
      }) + `
`);
      return 1;
    }
    const fmt = flags.format || "json";
    if (flags.jobage !== undefined && flags["jobage-minutes"] !== undefined) {
      process.stderr.write(JSON.stringify({
        error: "--jobage and --jobage-minutes both set a freshness window; pass only one",
        code: "CONFLICTING_AGE_FLAGS"
      }) + `
`);
      return 1;
    }
    const parseIntFlag = (name, raw) => {
      const val = parseInt(raw, 10);
      if (isNaN(val)) {
        process.stderr.write(JSON.stringify({ error: `--${name} must be a number, got "${raw}"`, code: "BAD_ARG" }) + `
`);
        return null;
      }
      return val;
    };
    if (flags.jobage !== undefined) {
      const v = parseIntFlag("jobage", flags.jobage);
      if (v === null)
        return 1;
      flags.jobage = String(v);
    }
    if (flags["jobage-minutes"] !== undefined) {
      const raw = flags["jobage-minutes"];
      const v = parseIntFlag("jobage-minutes", raw);
      if (v === null)
        return 1;
      if (v <= 0) {
        process.stderr.write(JSON.stringify({ error: `--jobage-minutes must be a positive number, got "${raw}"`, code: "BAD_ARG" }) + `
`);
        return 1;
      }
      flags["jobage-minutes"] = String(v);
    }
    if (flags.page !== undefined) {
      const v = parseIntFlag("page", flags.page);
      if (v === null)
        return 1;
      flags.page = String(v);
    }
    if (flags.limit !== undefined) {
      const v = parseIntFlag("limit", flags.limit);
      if (v === null)
        return 1;
      flags.limit = String(v);
    }
    const opts = {
      query: typeof flags.query === "string" ? flags.query : undefined,
      location,
      jobage: flags.jobage ? parseInt(flags.jobage, 10) : 9999,
      jobageMinutes: flags["jobage-minutes"] ? parseInt(flags["jobage-minutes"], 10) : undefined,
      remote: typeof flags.remote === "string" ? flags.remote : undefined,
      page: flags.page ? Math.max(1, parseInt(flags.page, 10)) : 1,
      limit: flags.limit ? parseInt(flags.limit, 10) : undefined,
      format: ["json", "table", "plain"].includes(fmt) ? fmt : "json"
    };
    return runSearch(opts);
  }
  if (cmd === "detail") {
    const id = flags._[1];
    if (!id) {
      process.stderr.write(JSON.stringify({ error: "detail requires an <id|url>", code: "NO_ID" }) + `
`);
      return 1;
    }
    const fmt = flags.format || "json";
    const opts = {
      id,
      format: fmt === "plain" ? "plain" : "json"
    };
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
