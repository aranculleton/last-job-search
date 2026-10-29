/* The page's browser tests, run by tests/test_the_page_works_in_a_browser.py.

   One long-lived Node process holds one Chromium. It reads one JSON request a line on
   stdin ({id, scenario, args}) and answers one JSON line ({id, ok, result | error}). Each
   scenario opens a fresh browser context: the page is served from a made-up origin,
   https://ljs.test/, every other request is refused (so nothing reaches the network, fonts
   included), and window.claude is the fake in fake_claude.js, backed by a store held here so
   that two tabs of one test share it, as two windows of the real page share one db. A
   chat is simulated by writing to that store directly, pinned to a version as ArtifactData
   writes are. */
"use strict";
const fs = require("fs");
const path = require("path");
const readline = require("readline");
const playwright = require("playwright");
// The engine, language and time zone the page is opened in. Chrome's engine, British English
// and London unless a release check asks otherwise (MAINTAINING.md, "Releasing"): the Claude
// app on an iPhone draws the page with Safari's engine, and claude.ai opens in any browser,
// language and time zone (2026-10-29).
const ENGINE = process.env.LJS_PW_ENGINE || "chromium";
// What the page copied: the clipboard itself in Chrome's engine, which lets a test read it
// back; elsewhere what the page handed to it (fake_claude.js keeps it).
const copied = (page) => page.evaluate((chromium) => chromium ? navigator.clipboard.readText() : (window.__ljsCopied || ""), ENGINE === "chromium");
const LOCALE = process.env.LJS_PW_LOCALE || "en-GB";
const ZONE = process.env.LJS_PW_TZ || "";

const FAKE = path.join(__dirname, "fake_claude.js");
const SHOTS = process.env.LJS_SHOTS || "";
// A one-page PDF saying "Device check: this PDF saved correctly." (from the device check page).
const PDF = Buffer.from("JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyAvUGFnZXMgMiAwIFIgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL1R5cGUgL1BhZ2VzIC9LaWRzIFszIDAgUl0gL0NvdW50IDEgPj4KZW5kb2JqCjMgMCBvYmoKPDwgL1R5cGUgL1BhZ2UgL1BhcmVudCAyIDAgUiAvTWVkaWFCb3ggWzAgMCA2MTIgNzkyXSAvQ29udGVudHMgNCAwIFIgL1Jlc291cmNlcyA8PCAvRm9udCA8PCAvRjEgNSAwIFIgPj4gPj4gPj4KZW5kb2JqCjQgMCBvYmoKPDwgL0xlbmd0aCA3MCA+PgpzdHJlYW0KQlQgL0YxIDI0IFRmIDcyIDcwMCBUZCAoRGV2aWNlIGNoZWNrOiB0aGlzIFBERiBzYXZlZCBjb3JyZWN0bHkuKSBUaiBFVAplbmRzdHJlYW0KZW5kb2JqCjUgMCBvYmoKPDwgL1R5cGUgL0ZvbnQgL1N1YnR5cGUgL1R5cGUxIC9CYXNlRm9udCAvSGVsdmV0aWNhID4+CmVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMDkgMDAwMDAgbiAKMDAwMDAwMDA1OCAwMDAwMCBuIAowMDAwMDAwMTE1IDAwMDAwIG4gCjAwMDAwMDAyNDEgMDAwMDAgbiAKMDAwMDAwMDM2MSAwMDAwMCBuIAp0cmFpbGVyCjw8IC9TaXplIDYgL1Jvb3QgMSAwIFIgPj4Kc3RhcnR4cmVmCjQzMQolJUVPRgo=", "base64");

// ---------------------------------------------------------------- the shared store
const clone = (x) => (x === undefined ? undefined : JSON.parse(JSON.stringify(x)));
function merge(a, b) {
  const out = Object.assign({}, a);
  for (const k of Object.keys(b)) {
    const v = b[k];
    if (v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" && !Array.isArray(out[k])) out[k] = merge(out[k], v);
    else out[k] = clone(v);
  }
  return out;
}
// Where the store keeps a record (tools/page_db.py STORE, STORE_DOC): a test names it by
// what it is, as the engine's code does, and the store holds it under 4.3's own name. A
// contact's address goes into the few records that hold them all (page_db.addr_docs).
function storedPath(p) {
  if (p === "meta/listener") return "meta/listen";
  if (p === "meta/current") return "meta/now";
  return p.replace(/^view\//, "screen/").replace(/^chats\//, "beats/").replace(/^locks\//, "holds/");
}
// An action by what it is (its item and action): every tap has an id of its own from 4.3, the
// item and action then a stamp (app.js actionId).
function actionAt(store, base) {
  const p = store.list("actions/").find((x) => x === base || x.startsWith(base + "~"));
  return p ? store.get(p) : null;
}
class Store {
  constructor(seed) {
    this.docs = new Map();
    this.leases = new Map();
    this.pages = new Set();
    this.v = 0;
    for (const [p, d] of Object.entries(seed || {})) {
      if (p.startsWith("reach/")) {
        const cur = this.docs.get("addr/part~1") || {data: {contacts: {}}, version: 0};
        cur.data.contacts[p.slice(6)] = clone(d);
        this.docs.set("addr/part~1", {data: cur.data, version: ++this.v});
        continue;
      }
      this.docs.set(storedPath(p), {data: clone(d), version: ++this.v});
    }
  }
  change(p, data) {
    const version = ++this.v;
    if (data === null) this.docs.delete(p); else this.docs.set(p, {data, version});
    const ch = [{path: p, data, version}];
    for (const page of this.pages) page.evaluate((c) => window.__ljsPush && window.__ljsPush(c), ch).catch(() => {});
    return ch;
  }
  handle(op, a) {
    if (op === "dump") return [...this.docs.entries()];
    if (op === "set") return {changes: this.change(a.path, clone(a.data))};
    if (op === "update") {
      const cur = this.docs.get(a.path);
      if (!cur) return {error: "invalid_argument"};
      return {changes: this.change(a.path, merge(cur.data, a.data))};
    }
    if (op === "delete") return {changes: this.change(a.path, null)};
    if (op === "acquire") {
      const t = Date.now();
      const l = this.leases.get(a.path);
      if (l && l.until > t && l.holder !== a.holder) return {acquired: false, expiresAt: new Date(l.until).toISOString()};
      this.leases.set(a.path, {holder: a.holder, until: t + (a.ttlMs || 30000)});
      const cur = this.docs.get(a.path);
      return {acquired: true, version: cur ? cur.version : 0, holder: a.holder};
    }
    return {error: "invalid_argument"};
  }
  get(p) { const d = this.docs.get(storedPath(p)); return d ? clone(d.data) : null; }
  version(p) { const d = this.docs.get(storedPath(p)); return d ? d.version : 0; }
  // A chat's write: ArtifactData pinned to the version it read, refused when it moved on.
  chat(p, data, ifVersion, op) {
    p = storedPath(p);
    if (ifVersion !== undefined && this.version(p) !== ifVersion) return {refused: true};
    const cur = this.docs.get(p);
    const next = op === "update" && cur ? merge(cur.data, data) : clone(data);
    this.change(p, next);
    return {ok: true, version: this.v};
  }
  list(prefix) { return [...this.docs.keys()].filter((k) => k.startsWith(prefix)); }
}

// ---------------------------------------------------------------- opening a page
let browser = null;
const DRAWN_RECT = `Element.prototype.__drawnRect = function () {
  const r = this.getBoundingClientRect(), b = document.body;
  if (!b || !b.offsetWidth || !b.contains(this)) return r;
  const d = (parseFloat(b.style.zoom) || 1) / (b.getBoundingClientRect().width / b.offsetWidth);
  return Math.abs(d - 1) < 0.001 ? r : new DOMRect(r.x * d, r.y * d, r.width * d, r.height * d);
};`;
async function open(o) {
  const ctx = await browser.newContext({
    viewport: o.viewport || {width: 375, height: 812}, colorScheme: o.scheme || "light", deviceScaleFactor: o.scale || 1,
    reducedMotion: o.reducedMotion || "no-preference", locale: LOCALE, timezoneId: o.timezoneId || ZONE || "Europe/London",
    // Only Chrome's engine takes clipboard permissions; the others allow a copy on a tap.
    permissions: o.clipboard === false || ENGINE !== "chromium" ? [] : ["clipboard-read", "clipboard-write"], hasTouch: !!o.touch,
    forcedColors: o.forcedColors || "none", contrast: o.contrast || "no-preference",
    javaScriptEnabled: o.javaScriptEnabled !== false,
  });
  const store = o.store || new Store(o.seed);
  await ctx.exposeBinding("__ljsStore", (src, op, args) => store.handle(op, args));
  await ctx.route("**/*", (route) => {
    const url = route.request().url();
    if (url.startsWith("https://ljs.test/")) {
      const u = new URL(url);
      if (u.pathname.startsWith("/_blob/")) return route.fulfill({status: o.blobStatus || 200, contentType: "application/pdf", body: PDF});
      let body = fs.readFileSync(o.html, "utf8");
      for (const [from, to] of o.replace || []) body = body.split(from).join(to);
      return route.fulfill({status: 200, contentType: "text/html; charset=utf-8", body});
    }
    // A picture the page holds in memory is not the network: Safari's engine routes it here,
    // where aborting it left a pasted screenshot without its preview (2026-10-29).
    if (url.startsWith("blob:") || url.startsWith("data:")) return route.continue();
    return route.abort();
  });
  await ctx.addInitScript({content: "window.__LJS_FAKE = " + JSON.stringify(o.fake || {}) + ";"});
  // Every box the harness measures, as drawn. The page zooms its body; Chrome and Firefox
  // measure after that zoom and Safari before it (probed 2026-10-29), so a Safari box read
  // 10 to 15% too big against the screen. The page's own code is left to measure natively.
  await ctx.addInitScript({content: DRAWN_RECT});
  // What this viewer chose before (kept on their device), the Claude app's own appearance
  // choice on the root, or storage refused altogether: each set before any page script runs.
  if (o.look) await ctx.addInitScript({content: "try { " + Object.entries(o.look).map(([k, v]) => "localStorage.setItem(" + JSON.stringify("ljs:" + k) + ", " + JSON.stringify(v) + ");").join(" ") + " } catch (e) {}"});
  // The root may not exist yet when an init script runs: set it the moment it does.
  const onRoot = (body) => "(function () { const go = () => { const r = document.documentElement; " + body + " }; if (document.documentElement) go(); else new MutationObserver((m, ob) => { if (document.documentElement) { ob.disconnect(); go(); } }).observe(document, {childList: true}); })();";
  if (o.hostTheme) await ctx.addInitScript({content: onRoot("r.setAttribute('data-theme', " + JSON.stringify(o.hostTheme) + ");")});
  if (o.noStorage) await ctx.addInitScript({content: "for (const n of ['localStorage', 'sessionStorage']) Object.defineProperty(window, n, {configurable: true, get() { throw new DOMException('refused', 'SecurityError'); }});"});
  if (o.watchPaint) await ctx.addInitScript({content: "window.__paint = {}; new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__paint[e.name] = e.startTime; }).observe({type: 'paint', buffered: true}); " +
    // One observer: its records come in the order the changes were made.
    onRoot("const P = window.__paint; P.n = 0; new MutationObserver((ms) => { for (const m of ms) { " +
      "if (m.type === 'attributes' && m.target === document.documentElement && !P.attr) P.attr = ++P.n; " +
      "for (const n of m.addedNodes || []) { if (n.nodeName === 'STYLE' && n.parentNode === document.body && !P.style) P.style = ++P.n; if (n.id === 'shell' && !P.content) P.content = ++P.n; } } })" +
      ".observe(document, {childList: true, subtree: true, attributes: true, attributeFilter: ['data-look']});")});
  await ctx.addInitScript({path: FAKE});
  const errors = [];
  const pages = [];
  for (let i = 0; i < (o.tabs || 1); i++) {
    const page = await ctx.newPage();
    store.pages.add(page);
    page.on("pageerror", (e) => errors.push(String(e && e.stack || e)));
    page.on("console", (m) => { if (m.type() === "error" && !/net::ERR_FAILED|Failed to load resource/.test(m.text())) errors.push(m.text()); });
    // Every page runs on the sample's own morning unless a scenario sets another time, so what
    // is due, late or this week does not move with the day the tests run.
    await page.clock.install({time: new Date(o.clock || process.env.LJS_TEST_NOW || "2026-10-25T09:00:00Z")});
    // A fresh load never opens on Settings (4.3): a test that starts there arrives the way a
    // person does, from the page itself.
    if (o.hash === "settings") { await page.goto("https://ljs.test/"); await settle(page); await page.evaluate(() => { location.hash = "settings"; }); }
    else await page.goto("https://ljs.test/" + (o.hash ? "#" + o.hash : ""));
    pages.push(page);
  }
  if (o.javaScriptEnabled !== false) for (const p of pages) await settle(p);
  return {ctx, page: pages[0], pages, store, errors};
}
async function turn(page, n) {
  for (let i = 0; i < (n || 3); i++) {
    await page.evaluate(() => new Promise((r) => { const c = new MessageChannel(); c.port1.onmessage = () => r(); c.port2.postMessage(0); }));
  }
}
async function settle(page) {
  // The page started first: before it has, there is nothing to wait on, and a step taken then
  // (a section set in the address) is read by a page that has not started (Firefox under load,
  // the Everywhere check, 2026-10-29).
  await page.waitForFunction(() => !!window.LJS, null, {timeout: 15000}).catch(() => {});
  await page.evaluate(() => (window.LJS && window.LJS.settled) || null);
  await turn(page, 4);
}
async function shot(page, name, full) {
  if (!SHOTS) return null;
  const file = path.join(SHOTS, name + ".png");
  fs.mkdirSync(path.dirname(file), {recursive: true});
  await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => null);
  await page.screenshot({path: file, fullPage: !!full});
  return file;
}
async function goto(page, id) {
  // Set to the address it already has, nothing happens: no hashchange. After a reload the
  // address is already the section's, while the page may have opened on its first one.
  await page.evaluate((h) => { if (location.hash === "#" + h) location.hash = "_"; location.hash = h; }, id);
  await turn(page, 4);
  // To do shows five first (4.3); a scenario that goes there reads and taps the whole list.
  if (id === "todo") { await page.$$eval("details.band-more:not([open])", (ds) => ds.forEach((d) => { d.open = true; })); await turn(page, 2); }
}
const T = (page, sel) => page.$$eval(sel, (els) => els.map((e) => e.innerText.trim()));
const one = async (page, sel) => { const el = await page.$(sel); return el ? (await el.innerText()).trim() : null; };
// A list's quiet actions sit behind its ⋯ menu (LAYOUT_SPEC 5.2): open it, pick one.
async function menuPick(page, name) {
  await page.locator("#main summary.menu-btn").first().click();
  await page.locator("#main .menu-panel .menu-item", {hasText: name}).first().click();
  await turn(page, 3);
}
// A setting is a row that opens in place to its choices (LAYOUT_SPEC 4.10).
async function openSetting(page, key) {
  // How the app runs is folded at the end of Settings (4.3): unfold it first.
  await page.$$eval("details.set-advanced:not([open])", (ds) => ds.forEach((d) => { d.open = true; }));
  await turn(page, 2);
  const sum = page.locator('[data-k="set-sum:' + key + '"]').first();
  const open = await sum.evaluate((el) => el.parentElement.open);
  if (!open) { await sum.click(); await turn(page, 3); }
}
const calls = (page) => page.evaluate(() => window.__calls.slice());
const overflow = (page) => page.evaluate(() => ({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth}));
const visible = (page, sel) => page.evaluate((s) => { const el = document.querySelector(s); if (!el) return false; const st = getComputedStyle(el); return st.display !== "none" && st.visibility !== "hidden" && el.getClientRects().length > 0; }, sel);
async function clickText(page, role, name, opts) {
  await page.getByRole(role, Object.assign({name, exact: true}, opts || {})).first().click();
  await turn(page, 4);
}

// ---------------------------------------------------------------- an accessibility sweep, offline
function a11yProbe() {
  const out = [];
  const shown = (el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden";
  const describe = (el) => el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + (el.className && typeof el.className === "string" ? "." + el.className.split(" ").join(".") : "") + " \"" + (el.textContent || "").trim().slice(0, 40) + "\"";
  const nameOf = (el) => {
    const al = el.getAttribute("aria-label");
    if (al && al.trim()) return al.trim();
    const lb = el.getAttribute("aria-labelledby");
    if (lb) return lb.split(/\s+/).map((id) => (document.getElementById(id) || {}).textContent || "").join(" ").trim();
    if (el.labels && el.labels.length) return [...el.labels].map((l) => l.textContent).join(" ").trim();
    if (el.tagName === "IMG") return el.alt || "";
    return (el.textContent || "").trim();
  };
  for (const el of document.querySelectorAll("button, a[href], input, select, textarea, [role=progressbar], svg[role=img], [role=region], [role=group]")) {
    if (!shown(el) || el.type === "hidden") continue;
    if (!nameOf(el)) out.push("no name: " + describe(el));
  }
  const ids = {};
  for (const el of document.querySelectorAll("[id]")) ids[el.id] = (ids[el.id] || 0) + 1;
  for (const k of Object.keys(ids)) if (ids[k] > 1) out.push("duplicate id: " + k);
  for (const el of document.querySelectorAll("[aria-labelledby], [aria-describedby], label[for]")) {
    const refs = (el.getAttribute("aria-labelledby") || "") + " " + (el.getAttribute("aria-describedby") || "") + " " + (el.getAttribute("for") || "");
    for (const id of refs.split(/\s+/).filter(Boolean)) if (!document.getElementById(id)) out.push("points at a missing id " + id + ": " + describe(el));
  }
  const levels = [...document.querySelectorAll("h1, h2, h3, h4")].filter(shown).map((h) => Number(h.tagName[1]));
  for (let i = 1; i < levels.length; i++) if (levels[i] > levels[i - 1] + 1) out.push("heading jumps from h" + levels[i - 1] + " to h" + levels[i]);
  if (!document.querySelector("main")) out.push("no main landmark");
  // Contrast of every piece of visible text against what is behind it.
  const rgba = (s) => { const m = s.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const blend = (fg, bg, a) => [0, 1, 2].map((i) => fg[i] * a + bg[i] * (1 - a));
  const bgOf = (el) => {
    const layers = [];
    for (let e = el; e; e = e.parentElement) { const c = rgba(getComputedStyle(e).backgroundColor); if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; } }
    let bg = [255, 255, 255];
    for (const c of layers.reverse()) bg = blend(c, bg, c[3]);
    return bg;
  };
  const opacityOf = (el) => { let o = 1; for (let e = el; e; e = e.parentElement) o *= Number(getComputedStyle(e).opacity); return o; };
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let checked = 0;
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement;
    if (!el || seen.has(el) || !n.textContent.trim()) continue;
    seen.add(el);
    if (!shown(el) || el.closest(".sr-only, [disabled], :disabled, noscript, script, style, svg")) continue;
    const st = getComputedStyle(el);
    const fg = rgba(st.color);
    if (!fg) continue;
    const bg = bgOf(el);
    const c = blend(fg, bg, fg[3] * opacityOf(el));
    const l1 = lum(c); const l2 = lum(bg);
    const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const size = parseFloat(st.fontSize);
    const bold = Number(st.fontWeight) >= 700;
    const need = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5;
    checked++;
    if (ratio < need) out.push("contrast " + ratio.toFixed(2) + " < " + need + ": " + describe(el));
  }
  // Non-text contrast, WCAG 1.4.11: a field's edge against what surrounds it, and a bar against its track.
  const ratioOf = (a, b) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);
  for (const el of document.querySelectorAll("input[type=text], input[type=date], input[type=number], select, textarea")) {
    if (!shown(el)) continue;
    const edge = rgba(getComputedStyle(el).borderTopColor);
    if (edge && ratioOf(edge, bgOf(el.parentElement)) < 3) out.push("field edge " + ratioOf(edge, bgOf(el.parentElement)).toFixed(2) + " < 3: " + describe(el));
  }
  for (const f of document.querySelectorAll(".fill, .fun-fill")) {
    if (!shown(f) || f.__drawnRect().width < 2) continue;
    const c = rgba(getComputedStyle(f).backgroundColor);
    const track = bgOf(f.parentElement);
    if (c && ratioOf(c, track) < 3) out.push("bar on its track " + ratioOf(c, track).toFixed(2) + " < 3: " + describe(f.parentElement));
  }
  for (const t of document.querySelectorAll("svg text")) {
    if (!shown(t)) continue;
    const fill = rgba(getComputedStyle(t).fill);
    const bg = bgOf(t.closest("div, section"));
    if (fill) { const r = (Math.max(lum(fill), lum(bg)) + 0.05) / (Math.min(lum(fill), lum(bg)) + 0.05); if (r < 4.5) out.push("chart text contrast " + r.toFixed(2)); }
  }
  return {problems: out, checked};
}

// Every control a phone person taps is a 44px target (WCAG 2.5.5; Apple's 44pt).
function targetsProbe() {
  // Inside a closed menu is not shown, whatever the engine says: Safari's gives the buttons in
  // a closed <details> a 0x0 box where Chrome's gives none (2026-10-29).
  const folded = (el) => {
    for (let d = el.closest("details:not([open])"); d; d = d.parentElement && d.parentElement.closest("details:not([open])")) {
      const s = el.closest("summary");
      if (!(s && s.parentElement === d)) return true;
    }
    return false;
  };
  const shown = (el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden" && !folded(el);
  const small = [];
  const sel = "button, a[href], summary, select, textarea, input:not([type=checkbox]):not([type=radio]):not([type=hidden]), label.pick, .choice label, .look-choice, .pick-all label";
  for (const el of document.querySelectorAll(sel)) {
    if (!shown(el) || el.classList.contains("skip") || el.closest(".sr-only")) continue;
    const r = el.__drawnRect();
    // A control drawn smaller than its target reaches the rest through its ::after (app.css,
    // "A button is drawn 36px tall"): the reach counts, scaled by the page's zoom.
    const pa = getComputedStyle(el, "::after");
    const z = parseFloat(getComputedStyle(document.body).zoom) || 1;
    const reach = (v) => Math.max(0, -(parseFloat(v) || 0)) * z;
    const on = pa.content && pa.content !== "none" && pa.position === "absolute";
    const hgt = r.height + (on ? reach(pa.top) + reach(pa.bottom) : 0);
    const wid = r.width + (on ? reach(pa.left) + reach(pa.right) : 0);
    // A link inside a sentence keeps its own width (WCAG 2.5.8, "Inline"); its height is a target.
    const inline = getComputedStyle(el).display === "inline-block" && !!el.closest("p, li, h3, h4") && el.tagName !== "BUTTON" || (el.matches(".btn.link") && !!el.closest("p"));
    if (hgt < 43.5 || (wid < 43.5 && !inline)) small.push(el.tagName.toLowerCase() + "." + String(el.className).split(" ").join(".") + " \"" + (el.textContent || "").trim().slice(0, 30) + "\" " + Math.round(wid) + "x" + Math.round(hgt));
  }
  return small;
}

// What a person meets on a screen, counted: words of chrome, words and controls in the first
// screen, filled buttons in view, and each card's words and controls in its closed state.
function budgetProbe() {
  const vh = window.innerHeight;
  // Chromium keeps a box for what sits inside a closed <details>, so closed ones are checked by hand.
  const hiddenUp = (el) => {
    for (let e = el; e; e = e.parentElement) {
      if (e.classList && e.classList.contains("sr-only")) return true;
      if (e.tagName === "DIALOG" && !e.open) return true;
      if (e.tagName === "DETAILS" && !e.open) { const sum = e.querySelector(":scope > summary"); if (!sum || !sum.contains(el)) return true; }
    }
    return false;
  };
  const shown = (el) => el.getClientRects().length > 0 && getComputedStyle(el).visibility !== "hidden" && !hiddenUp(el);
  const inView = (el) => { const r = el.__drawnRect(); return r.bottom > 0 && r.top < vh && r.width > 0 && r.height > 0; };
  // skipText: leave out the words of a message to send, the card's content rather than its chrome.
  const wordsIn = (root, viewOnly, skipText) => {
    let n = 0;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let t = w.nextNode(); t; t = w.nextNode()) {
      const el = t.parentElement;
      if (!el || !t.textContent.trim() || el.closest("script, style, noscript") || !shown(el)) continue;
      if (skipText && el.closest(".sendtext")) continue;
      if (viewOnly && !inView(el)) continue;
      n += t.textContent.split(/\s+/).filter((x) => /[\p{L}\p{N}]/u.test(x)).length;
    }
    return n;
  };
  const CTRL = "button, a[href], summary, select, input:not([type=hidden]), textarea";
  const controls = (root, viewOnly) => [...root.querySelectorAll(CTRL)].filter((el) => shown(el) && (!viewOnly || inView(el)));
  const main = document.getElementById("main");
  const chrome = ["top", "foot"].map((id) => document.getElementById(id)).filter(Boolean).reduce((a, e) => a + wordsIn(e, false), 0);
  const filled = [...document.querySelectorAll(".btn.primary")].filter((b) => shown(b) && inView(b) && !b.closest("dialog")).length;
  const cards = [...main.querySelectorAll("[data-card]")].filter(shown).map((c) => {
    const cs = controls(c, false);
    return {item: c.getAttribute("data-item"), words: wordsIn(c, false, true), controls: cs.length,
      answers: cs.filter((b) => b.classList.contains("answer")).length, icons: cs.filter((b) => b.classList.contains("icon-only") || b.classList.contains("q")).length, names: cs.filter((b) => b.classList.contains("name-link")).length, filled: cs.filter((b) => b.classList.contains("primary")).length,
      alerts: c.querySelectorAll(".alert, .suggest").length,
      labels: cs.map((b) => (b.getAttribute("aria-label") || b.textContent || "").replace(/\s+/g, " ").trim().slice(0, 24))};
  });
  return {chrome, screenWords: wordsIn(main, true), screenControls: controls(main, true).length, filled, cards};
}

// ---------------------------------------------------------------- scenarios
const SECTIONS = ["brief", "todo", "jobs", "drafts", "drafts-messages", "contacts", "interviews", "progress", "chat", "settings", "profile"];
const S = {};
async function openMore(page, item) {
  await page.locator('[data-item="' + item + '"] summary.more-btn').first().click();
  await turn(page, 3);
}
const workSel = (id) => '[data-work="' + id + '"]';

S.paint = async (a) => {
  const o = await open({html: a.html, fake: a.fake, viewport: a.viewport, scheme: a.scheme, hash: a.hash, hostTheme: a.hostTheme, look: a.look, timezoneId: a.timezoneId, clock: a.clock});
  const {page} = o;
  if (a.wait) await page.waitForTimeout(a.wait);
  const r = {
    bg: await page.evaluate(() => getComputedStyle(document.body).backgroundColor),
    title: await page.title(), brand: await one(page, "#brand"), heading: await one(page, "#main h2"),
    pulse: await page.evaluate(() => (document.getElementById("pulse") || {}).textContent || ""),
    conn: await page.evaluate(() => (document.getElementById("conn") || {getAttribute: () => null}).getAttribute("data-state")),
    overflow: await overflow(page),
    side: await visible(page, "#side"), tabs: await visible(page, "#tabs"), rail: await visible(page, "#rail"),
    cards: (await page.$$("#main [data-card], #main .bpanel")).length,
    privateShown: await visible(page, "#private"), shellShown: await visible(page, "#shell"), opening: await visible(page, "#opening"),
    bodyText: await page.evaluate(() => document.body.innerText),
    errors: o.errors,
  };
  if (a.shot) r.shot = await shot(page, a.shot, a.full);
  await o.ctx.close();
  return r;
};

// Nothing personal before the owner check answers: the page is blank but for one line.
S.private_gate = async (a) => {
  const o = await open({html: a.html, fake: {ownerDelay: 1500}});
  const {page} = o;
  const before = {text: await page.evaluate(() => document.body.innerText), shell: await visible(page, "#shell"), opening: await visible(page, "#opening")};
  await page.waitForTimeout(1800);
  await turn(page, 6);
  const after = {shell: await visible(page, "#shell"), heading: await one(page, "#main h2")};
  await o.ctx.close();
  return {before, after, errors: o.errors};
};

S.sections = async (a) => {
  const o = await open({html: a.html, fake: a.fake, viewport: a.viewport});
  const {page} = o;
  const out = {};
  for (const id of SECTIONS) {
    await goto(page, id);
    await page.$$eval("details.band-more:not([open])", (ds) => ds.forEach((d) => { d.open = true; }));
    await turn(page, 2);
    out[id] = {heading: await one(page, "#main h2"), empty: await T(page, "#main .empty-title"), text: (await one(page, "#main")) || "",
      overflow: await overflow(page), items: (await page.$$("#main [data-card], #main .talk-msg, #main tbody tr")).length,
      // The "?" explainers and the tips a screen shows, all of it and in the first screenful.
      ...(await page.evaluate(() => {
        const shown = (e) => e.getClientRects().length > 0 && e.checkVisibility({visibilityProperty: true});
        const first = (e) => e.__drawnRect().top < innerHeight;
        const qs = [...document.querySelectorAll("#main button.q, #main button.help-q")].filter(shown);
        const tips = [...document.querySelectorAll("#main .tip, #main .bp-tip")].filter(shown);
        return {qs: qs.length, qsFirst: qs.filter(first).length, tips: tips.length, qKeys: qs.map((q) => q.getAttribute("data-k"))};
      }))};
    if (a.shots) out[id].shot = await shot(page, a.shots + "-" + id, true);
  }
  out.errors = o.errors;
  await o.ctx.close();
  return out;
};

// The page built by the engine itself (tools/app.py page) from an invented search: each
// section's text, with the view documents `app.py view` writes in the store, as a chat leaves
// them. `steps` taps buttons by name in a section and reads what follows; `upload` stands in
// for a file the person picks.
// LAYOUT_SPEC section 7, measured: every section's first item, the blocks above it, its one
// summary, the control row, the frame, the cards, names, type and the empty states, then the
// three sheets on a phone and the page at 200% text. The checks are in
// tests/test_the_page_keeps_its_layout_promises.py; this only measures.
function layoutMeasure() {
  // checkVisibility: a closed details' content keeps its boxes in Chromium but is not shown.
  const vis = (e) => !!e && e.checkVisibility({visibilityProperty: true, contentVisibilityAuto: true}) && e.getClientRects().length > 0 && !e.closest(".sr-only");
  const main = document.getElementById("main");
  const name = (e) => (e.getAttribute("aria-label") || (e.getAttribute("aria-labelledby") ? (document.getElementById(e.getAttribute("aria-labelledby")) || {}).textContent : "") || e.textContent || e.value || "").replace(/\s+/g, " ").trim();
  const firsts = [...main.querySelectorAll("[data-card], .empty, .setting-row")].filter(vis);
  firsts.sort((x, y) => x.__drawnRect().top - y.__drawnRect().top);
  const f = firsts[0] || null;
  const title = [...main.querySelectorAll("h2")].find(vis) || null;
  // The blocks between the title and the first item: siblings after the title's own block.
  const blocks = [];
  if (title && f) {
    let head = title;
    while (head.parentElement && head.parentElement !== main && !head.parentElement.contains(f)) head = head.parentElement;
    for (let el = head.nextElementSibling; el; el = el.nextElementSibling) {
      if (el === f || el.contains(f)) break;
      if (vis(el)) blocks.push(String(el.className || el.tagName));
    }
  }
  const summaries = [...main.querySelectorAll(".summary")].filter(vis);
  const afterTitle = title ? (() => { let el = title.nextElementSibling; while (el && !vis(el)) el = el.nextElementSibling; return el; })() : null;
  const controls = [...main.querySelectorAll(".controls")].filter(vis).map((c) => {
    const kids = [...c.querySelectorAll("button, select, input, a, summary")].filter(vis);
    const tops = kids.map((k) => k.__drawnRect().top);
    return {spread: tops.length ? Math.max(...tops) - Math.min(...tops) : 0, scroll: c.scrollWidth - c.clientWidth, n: kids.length};
  });
  const inView = (e) => { const r = e.__drawnRect(); return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  const primary = [...document.querySelectorAll(".btn.primary")].filter((e) => vis(e) && inView(e) && !e.closest("dialog:not([open])")).length;
  const qPrimary = [...main.querySelectorAll(".btn.answer.primary")].filter(vis).length;
  const cards = [...main.querySelectorAll("[data-card]")].filter(vis).map((c) => {
    const closed = (e) => !e.closest("details:not([open])") || e.matches("summary");
    const own = (sel) => [...c.querySelectorAll(sel)].filter((e) => vis(e) && closed(e) && e.closest("[data-card]") === c);
    // A warm route line (who can refer you) is the card's one alert; a link drawn as a button is a button.
    return {item: c.getAttribute("data-item"), states: own(".state").length, alerts: own(".alert, .warm").length, suggests: own(".suggest").length,
      // A card's actions: its one alert or suggestion, a question's answers and the "What was
      // checked" target are parts of their own line, not actions.
      // A More holding one action shows that action in its place (4.3): it fills the More's
      // slot, not a button's.
      buttons: own("button, a.btn").filter((b) => !b.closest("summary, .suggest, .alert, .warm") && !b.classList.contains("answer") && !b.classList.contains("q") && !b.classList.contains("icon-only") && !b.hasAttribute("data-more")).length,
      // A person's name that opens them is the card's title, not one of its links.
      links: own("a:not(.btn)").filter((x) => !x.closest(".suggest, .alert, .warm") && !x.classList.contains("name-link")).length, more: own("details.more, details.more-menu, summary.more-btn, [data-more]").length};
  });
  const named = [...main.querySelectorAll("button, a, input, select, summary")].filter(vis).map(name).filter(Boolean);
  const dupNames = named.filter((n, i) => named.indexOf(n) !== i);
  const items = cards.map((c) => c.item).filter(Boolean);
  const dupItems = items.filter((n, i) => items.indexOf(n) !== i);
  const pairs = new Set(), weights = new Set(), tones = new Set(), pairWhere = {};
  for (const el of main.querySelectorAll("*")) {
    if (!vis(el) || !inView(el)) continue;
    for (const c of el.classList) if (c.startsWith("tone-")) tones.add(c);
    if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) continue;
    const cs = getComputedStyle(el);
    const pair = cs.fontSize + "/" + cs.fontWeight;
    if (!pairs.has(pair)) pairWhere[pair] = (el.tagName + "." + [...el.classList].join(".")).slice(0, 40);
    pairs.add(pair);
    weights.add(cs.fontWeight);
  }
  const empties = [...main.querySelectorAll(".empty")].filter(vis).map((e) => ({buttons: [...e.querySelectorAll("button, a.btn")].filter(vis).length,
    words: e.innerText.trim().split(/\s+/).filter(Boolean).length}));
  return {first: f ? Math.round(f.__drawnRect().top + scrollY) : null, firstWhat: f ? String(f.className).slice(0, 40) : null,
    blocks, here: main.querySelectorAll(".here").length, activeFilters: main.querySelectorAll(".active-filters").length,
    summaries: summaries.map((e) => e.textContent.replace(/\s+/g, " ").trim()), summaryFirst: !!afterTitle && afterTitle.classList.contains("summary"),
    summarySentence: summaries[0] ? ((summaries[0].firstElementChild || summaries[0]).textContent || "").trim() : "",
    controls, primary, qPrimary, cards, dupNames: [...new Set(dupNames)], dupItems: [...new Set(dupItems)],
    pairs: [...pairs], pairWhere, weights: [...weights], tones: [...tones], empties, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth};
}
function frameMeasure() {
  const vis = (e) => !!e && e.checkVisibility({visibilityProperty: true, contentVisibilityAuto: true}) && e.getClientRects().length > 0;
  const top = document.getElementById("top");
  const tabs = [...document.querySelectorAll("#tabs a.tab, #tabs button.tab")].filter(vis);
  const badges = [...document.querySelectorAll("#tabs .badge, #side .badge, #main .seg .badge")].filter(vis).map((b) => ({text: b.textContent.trim(), where: (b.closest("a, button") || b).textContent.replace(b.textContent, "").trim()}));
  const navNumbers = [...document.querySelectorAll("#tabs a.tab, #side a, #main .seg button")].filter(vis).filter((e) => /\d/.test([...e.childNodes].filter((n) => !(n.classList && (n.classList.contains("badge") || n.classList.contains("navcount") || n.classList.contains("sr-only")))).map((n) => n.textContent).join(""))).map((e) => e.textContent.trim());
  const topKids = [...top.querySelectorAll("#brand, #screen, #conn, #pulse, #pill, button, a")].filter(vis).map((e) => e.id || String(e.className));
  return {topH: Math.round(top.__drawnRect().height), topKids, tabs: tabs.length, badges, navNumbers,
    pill: vis(document.getElementById("pill")) || vis(document.getElementById("pulse")), rail: vis(document.getElementById("rail"))};
}
async function sheetMeasure(page, kind) {
  return page.evaluate((k) => {
    const d = document.querySelector("dialog." + k + "[open]");
    if (!d) return null;
    const r = d.__drawnRect();
    const close = [...d.querySelectorAll("button")].find((b) => /^close\b/i.test((b.getAttribute("aria-label") || b.textContent).trim()));
    const cr = close ? close.__drawnRect() : null;
    // A null or undefined given to the DOM is printed as the word (the filter sheet's footer
    // read "Show 13 people null", 2026-10-29).
    const stray = /(^|[^\w])(null|undefined|NaN)([^\w]|$)|\[object /.test(d.innerText);
    return {bottom: Math.round(r.bottom), top: Math.round(r.top), h: Math.round(r.height), vh: innerHeight, close: !!close, closeRow: cr ? Math.round(cr.top - r.top) : null, stray};
  }, kind);
}
async function sheetCheck(page, kind, openIt) {
  const opener = await openIt();
  if (opener === null) return null;
  await turn(page, 4);
  const m = await sheetMeasure(page, kind);
  if (m) {
    // Where it is drawn against what opened it, as the screen shows them (not as the page
    // measures itself, which differs between engines under the page's zoom).
    const ob = await page.locator('[data-k="' + opener + '"]').first().boundingBox();
    const db = await page.locator("dialog." + kind + "[open]").boundingBox();
    m.gap = ob && db ? Math.round(db.y - (ob.y + ob.height)) : null;
    m.drawnRight = db ? Math.round(db.x + db.width) : null;
    m.vw = page.viewportSize().width;
    await page.locator("dialog." + kind + "[open]").getByRole("button", {name: /^close/i}).first().click();
    await turn(page, 4);
    m.focusBack = await page.evaluate((k) => !!document.activeElement && document.activeElement.getAttribute("data-k") === k, opener);
  }
  return m;
}
S.layout = async (a) => {
  // With the sheets measured, one search is running, so the Work pill is there to open.
  const seed = Object.assign(a.sheets ? {"work/search~1": runningDoc()} : {}, a.seed || {});
  const o = await open({html: a.html, viewport: a.viewport, scheme: a.scheme, fake: a.fake, seed, clock: a.clock || "2026-10-26T09:00:00Z"});
  const {page} = o;
  const out = {sections: {}, frames: {}, sheets: {}, big: {}};
  for (const id of SECTIONS) {
    await goto(page, id);
    await page.evaluate(() => window.scrollTo(0, 0));
    out.sections[id] = await page.evaluate(layoutMeasure);
    out.frames[id] = await page.evaluate(frameMeasure);
  }
  if (a.sheets) {
    for (const id of SECTIONS) {
      await goto(page, id);
      if (!(await page.locator("#main .filter-btn").count())) continue;
      out.sheets.filter = await sheetCheck(page, "filter-sheet", async () => { const b = page.locator("#main .filter-btn").first(); const k = await b.getAttribute("data-k"); await b.click(); return k; });
      out.sheets.filterAt = id;
      break;
    }
    await goto(page, "drafts-applications");
    await openMore(page, a.tweakItem);
    out.sheets.tweak = await sheetCheck(page, "tweak-sheet", async () => { const b = page.locator('[data-item="' + a.tweakItem + '"] .tweak-entry button').first(); if (!(await b.count())) return null; const k = await b.getAttribute("data-k"); await b.click(); return k; });
    await goto(page, "todo");
    out.sheets.work = await sheetCheck(page, "work-sheet", async () => { const b = page.locator("#pill").first(); if (!(await b.count()) || !(await b.isVisible())) return null; const k = await b.getAttribute("data-k"); await b.click(); return k; });
  }
  if (a.big) {
    await page.evaluate(() => { document.documentElement.style.fontSize = "200%"; });
    for (const id of SECTIONS) {
      await goto(page, id);
      await page.evaluate(() => window.scrollTo(0, 0));
      out.big[id] = await page.evaluate(() => {
        const vis = (e) => e.checkVisibility({visibilityProperty: true, contentVisibilityAuto: true}) && e.getClientRects().length > 0 && !e.closest(".sr-only");
        const clipped = [...document.querySelectorAll("#main button, #top button, #tabs a")].filter(vis).filter((b) => b.scrollWidth > b.clientWidth + 1 && getComputedStyle(b).overflow !== "visible").map((b) => b.textContent.trim().slice(0, 30));
        const rows = [...document.querySelectorAll("#main .controls")].filter(vis).map((c) => {
          const tops = [...c.querySelectorAll("button, select, input, a, summary")].filter(vis).map((k) => k.__drawnRect().top);
          return {spread: tops.length ? Math.max(...tops) - Math.min(...tops) : 0, scroll: c.scrollWidth - c.clientWidth};
        });
        // What sticks out, named, so a failure says where to look.
        const W = document.documentElement.clientWidth;
        const wide = [...document.querySelectorAll("#main *, #top *")].filter((e) => { const r = e.__drawnRect(); return r.width && r.right > W + 1; })
          .filter((e) => ![...e.children].some((c) => c.__drawnRect().right > W + 1)).slice(0, 5).map((e) => e.tagName.toLowerCase() + "." + [...e.classList].join(".") + " " + (e.textContent || "").trim().slice(0, 30));
        return {overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth, clipped, rows, wide};
      });
    }
  }
  out.errors = o.errors;
  await o.ctx.close();
  return out;
};

S.engine = async (a) => {
  const o = await open({html: a.html, viewport: a.viewport, scheme: a.scheme, seed: a.seed || {}, fake: a.fake, clipboard: a.clipboard, clock: a.clock});
  const {page, store} = o;
  const out = {texts: {}, after: [], shots: []};
  // To do shows five first: what a test reads is the whole list, the rest unfolded.
  const unfold = async () => { await page.$$eval("details.band-more:not([open])", (ds) => ds.forEach((d) => { d.open = true; })); await turn(page, 2); };
  for (const id of a.hashes || []) {
    await goto(page, id);
    await unfold();
    out.texts[id] = (await one(page, "#main")) || "";
    if (a.shots) out.shots.push(await shot(page, a.shots + "-" + id.replace(/[^a-z0-9-]/gi, "_"), true));
  }
  for (const st of a.steps || []) {
    if (st.hash) await goto(page, st.hash);
    if (st.more) await openMore(page, st.more);
    if (st.open) { await page.locator('[data-k="' + st.open + '"]').first().click(); await turn(page, 3); }
    // To do shows five first; what a step taps may wait behind "Show the other N".
    if (st.click) { await page.$$eval("details.band-more:not([open])", (ds) => ds.forEach((d) => { d.open = true; })); await turn(page, 2);
      await (st.within ? page.locator(st.within) : page).getByRole(st.role || "button", {name: st.click, exact: !!st.exact}).first().click(); await turn(page, 6); }
    if (st.fill) for (const [label, value] of Object.entries(st.fill)) await page.locator("dialog").getByLabel(label, {exact: false}).first().fill(value);
    if (st.file) { await page.setInputFiles('dialog input[type="file"]', {name: st.file, mimeType: "application/pdf", buffer: PDF}); await turn(page, 8); }
    if (st.submit) { await page.locator("dialog [data-k=sheet-go]").click(); await turn(page, 6); }
    if (st.wait) { await page.waitForTimeout(st.wait); await turn(page, 6); }
    // A chat, played: every action so far applied, then the next state of the model.
    if (st.receipts) {
      for (const k of store.list("actions/")) { const id = k.split("/")[1]; if (!store.get("receipts/" + id)) store.chat("receipts/" + id, {applied_at: new Date().toISOString(), by: "cloud-1", result: "ok", note: ""}); }
      await turn(page, 6);
    }
    if (st.view) { for (const [k, v] of Object.entries(st.view)) store.chat("view/" + k, {made_at: "2026-10-25T09:00:00Z", data: v}); await turn(page, 8); }
    if (st.hash2) await goto(page, st.hash2);
    await unfold();
    const entry = {text: (await one(page, st.read || "#main")) || "", dialog: (await one(page, "dialog")) || ""};
    if (st.clip) entry.clip = await copied(page);
    if (st.attr) entry.attr = await page.getAttribute(st.attr[0], st.attr[1]).catch(() => null);
    if (st.count) entry.count = (await page.$$(st.count)).length;
    if (st.calls) entry.calls = (await calls(page)).filter((c) => c.cap === st.calls);
    if (st.eval) entry.eval = await page.evaluate((c) => eval(c), st.eval);
    entry.hash = await page.evaluate(() => location.hash);
    entry.work = store.list("work/").map((k) => Object.assign({id: k.split("/")[1]}, store.get(k)));
    out.after.push(entry);
    if (a.shots && st.shot) out.shots.push(await shot(page, a.shots + "-" + st.shot, !!st.full));
  }
  out.actions = store.list("actions/").map((k) => store.get(k));
  out.work = store.list("work/").map((k) => store.get(k));
  out.rings = (await calls(page)).filter((c) => c.cap === "comments" && c.text).map((c) => c.text);
  out.assets = (await page.evaluate(() => (window.__ljsAssets || []).slice())) || [];
  out.errors = o.errors;
  await o.ctx.close();
  return out;
};

// A Tweak panel for one output: opened from its card's More (or the brief, or Jobs), changes
// chosen, the Apply line read, and Apply pressed. Returns what the panel said and the work
// item it asked for, if any.
S.tweak = async (a) => {
  const o = await open({html: a.html, viewport: a.viewport, scheme: a.scheme, hash: a.hash, look: a.look, seed: a.seed || {}});
  const {page, store} = o;
  if (a.item) await openMore(page, a.item);
  if (a.brief) { await page.locator("details.brief > summary").click(); await turn(page, 2); }
  await page.getByRole("button", {name: a.entry, exact: a.exact !== false}).first().click();
  await turn(page, 4);
  const panel = page.locator(".tweak-panel");
  const read = async () => ({line: (await panel.locator(".tweak-line").textContent()).trim(),
    disabled: await panel.locator("[data-k=tweak-apply]").isDisabled()});
  const out = {first: await read(), open: await panel.count(), inRail: await page.locator("#rail .tweak-panel").count(),
    sheet: await page.evaluate(() => { const d = document.querySelector("dialog.tweak-sheet"); if (!d) return null; const r = d.__drawnRect(); return {top: r.top, bottom: r.bottom, h: r.height, vh: innerHeight}; }),
    rows: await panel.locator(".tweak-body > .tweak-row").count(), recs: await panel.locator(".rec").count(),
    pressed: await panel.locator('[aria-pressed="true"].tw-opt').count(), keepChecked: await panel.locator("#tweak-keep").isChecked(),
    title: (await panel.locator(".tweak-title").textContent()).trim(), text: (await panel.innerText())};
  for (const [pp, v] of a.choose || []) { await panel.locator('[data-k="tw:' + pp + ":" + v + '"]').click(); await turn(page, 1); }
  for (const [pp, v] of a.type || []) { await panel.locator('[data-k="tw:' + pp + '"]').fill(v); await turn(page, 1); }
  for (const k of a.near || []) { await panel.locator('[data-k="tw-near:' + k + '"]').click(); await turn(page, 1); }
  if (a.text) { await panel.locator("[data-k=tweak-else]").click(); await panel.locator("#tweak-text").fill(a.text); await turn(page, 1); }
  if (a.keep) { await panel.locator("#tweak-keep").check(); await turn(page, 1); out.keepRead = (await panel.locator("#tweak-keep-read").textContent()).trim(); }
  if (a.when) { await panel.locator('[data-k="tweak-when:' + a.when + '"]').click(); await turn(page, 1); }
  out.after = await read();
  if (a.shot) out.shot = await shot(page, a.shot, false);
  if (a.apply) { await panel.locator("[data-k=tweak-apply]").click(); await turn(page, 6); }
  out.work = store.list("work/").map((k) => [k, store.get(k)]);
  out.prefs = await page.evaluate(() => { const r = {}; try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); if (k.startsWith("ljs:p:")) r[k] = localStorage.getItem(k); } } catch (e) {} return r; });
  out.closed = (await page.locator(".tweak-panel").count()) === 0;
  out.main = (await one(page, "#main")) || "";
  out.focus = await page.evaluate(() => (document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.k : null));
  out.errors = o.errors;
  await o.ctx.close();
  return out;
};

S.action_receipt = async (a) => {
  const o = await open({html: a.html, hash: "drafts-messages"});
  const {page, store} = o;
  await clickText(page, "button", "I sent the message to Juno");
  await turn(page, 4);
  const ids = store.list("actions/");
  const doc = ids.length ? store.get(ids[0]) : null;
  const text = (sel) => page.$eval(sel, (e) => e.textContent.trim()).catch(() => null);
  const saved = await text('#main [data-item="msg-juno-1"] .state');
  const toast = await one(page, ".toast");
  const focusAfter = await page.evaluate(() => { const e = document.activeElement; return {k: e.dataset ? e.dataset.k : null, inCard: !!(e.closest && e.closest('[data-item="msg-juno-1"]'))}; });
  const id = ids[0].split("/")[1];
  store.chat("receipts/" + id, {applied_at: new Date().toISOString(), by: "cloud-1", result: "ok", note: "", undo: {action: "msg.unsent", target: "msg-juno-1", value: null}});
  await turn(page, 6);
  const done = await text("#main .gone .state");
  const back = await T(page, "#main .gone button");
  const moved = await page.$$eval("#main .card.msg", (x) => x.length);
  // A refused one: the item changed since it was shown.
  await goto(page, "todo");
  await clickText(page, "button", "Yes, I have");
  await turn(page, 4);
  const ids2 = store.list("actions/").filter((x) => x !== ids[0]);
  store.chat("receipts/" + ids2[0].split("/")[1], {applied_at: new Date().toISOString(), by: "cloud-1", result: "conflict", note: "Answered differently on your phone."});
  await turn(page, 6);
  const refused = await one(page, '#main [data-item="q-larkspur-data-looker"] .state');
  const result = {ids, doc, saved, toast, focusAfter, done, back, moved, refused, errors: o.errors};
  await o.ctx.close();
  return result;
};

// Undo stays on the item, with no time limit, until Claude has done it.
S.undo = async (a) => {
  const o = await open({html: a.html, hash: "jobs", clock: "2026-10-25T09:00:00Z"});
  const {page, store} = o;
  // The bin asks what it is; "Not this role" is already chosen.
  await clickText(page, "button", "Not for me: Harbourline Bank, Pricing Analyst");
  await clickText(page, "button", "Take it off my list");
  await turn(page, 4);
  const before = store.list("actions/");
  const marked = await page.$eval('#main [data-item="r12-1"]', (x) => x.classList.contains("is-marked")).catch(() => false);
  const focus = await page.evaluate(() => document.activeElement.textContent.trim());
  const undoShown = (await page.$$(".toast button:text-is('Undo')")).length;
  await page.locator(".toast").getByRole("button", {name: "Undo", exact: true}).click();
  await turn(page, 6);
  const after = store.list("actions/");
  const back = await T(page, "#main .card.job h3");
  await clickText(page, "button", "Not for me: Copperleaf Pay, Data Analyst, Payments");
  // Why, asked once in the bin's sheet: the same action, with its reason.
  await page.locator("dialog").getByRole("radio", {name: "Not this role: the pay", exact: true}).check();
  await clickText(page, "button", "Take it off my list");
  await turn(page, 6);
  const reason = actionAt(store, "actions/act~r12-3~job.dismiss");
  const during = (await page.$$(".toast button:text-is('Undo')")).length + (await page.$$("#main button.undo")).length;
  // The pointer off the toast: a toast under it is held open on purpose.
  await page.mouse.move(1, 1);
  await page.clock.runFor(60000);
  await turn(page, 6);
  const later = {toast: (await page.$$(".toast")).length, item: (await page.$$("#main button.undo")).length};
  const kept = store.list("actions/");
  const r = {before, marked, focus, undoShown, after, back, reason, during, later, kept, errors: o.errors};
  await o.ctx.close();
  return r;
};

// A failed write says so, at once, with a way to try again, and never "Saved".
S.write_fail = async (a) => {
  const o = await open({html: a.html, hash: "drafts-messages", fake: {failWrites: true}});
  const {page} = o;
  await clickText(page, "button", "I sent the message to Juno");
  await turn(page, 8);
  const r = {toast: await T(page, ".toast"), state: await one(page, '#main [data-item="msg-juno-1"] .state'), alert: await page.evaluate(() => document.getElementById("alert").textContent),
    live: await page.evaluate(() => document.getElementById("live").textContent), errors: o.errors};
  await o.ctx.close();
  return r;
};

const T0 = "2026-10-25T09:00:00.000Z";
function runningDoc(extra) {
  return Object.assign({kind: "search", title: "Finding jobs", to: "cloud", args: {}, asked_at: T0, status: "running",
    claimed_by: "cloud-1", claimed_at: T0, stages: [{name: "Getting started", est_s: 60}, {name: "Searching job sites", est_s: 300}, {name: "Scoring", est_s: 120}],
    stage: 1, stage_at: T0, steps: [{at: T0, text: "Searching 4 job sites"}], stop_asked: false, attempt: 1}, extra || {});
}
async function bar(page, id) {
  return page.evaluate((i) => {
    const el = document.querySelector('[data-work="' + i + '"]');
    if (!el) return null;
    const b = el.querySelector("[role=progressbar]");
    return {now: b ? Number(b.getAttribute("aria-valuenow")) : null, text: b ? b.getAttribute("aria-valuetext") : null,
      time: (el.querySelector("[data-time]") || {}).textContent || "", status: (el.querySelector(".state-word, .chip") || {}).textContent || "",
      sentence: (el.querySelector(".wc-now") || {}).textContent || "",
      warn: [...el.querySelectorAll(".wc-warn")].map((x) => x.textContent), buttons: [...el.querySelectorAll("button, a.btn")].map((x) => x.textContent.trim()),
      steps: [...el.querySelectorAll(".wc-steps li")].map((x) => x.className + ":" + x.textContent.trim())};
  }, id);
}

S.progress = async (a) => {
  const o = await open({html: a.html, hash: "work", clock: T0, seed: {"work/search~1": runningDoc()}});
  const {page, store} = o;
  // A work row is compact; its title opens its steps.
  await page.locator('[data-k="wct:search~1"]').click();
  await turn(page, 3);
  const r = {sheet: await visible(page, "dialog.work-sheet"), pill: await one(page, "#pill"), at0: await bar(page, "search~1")};
  await page.clock.runFor(150000);
  await turn(page);
  r.at150 = await bar(page, "search~1");
  // The chat moves on a stage: one write at the boundary.
  const at2 = new Date(Date.parse(T0) + 280000).toISOString();
  store.chat("work/search~1", {stage: 2, stage_at: at2, steps: [{at: at2, text: "Scoring 214 postings"}], count: {done: 3, total: 4}}, store.version("work/search~1"), "update");
  await page.clock.runFor(140000);
  await turn(page, 6);
  r.stage2 = await bar(page, "search~1");
  store.chat("work/search~1", {count: null}, store.version("work/search~1"), "update");
  // Over twice the stage's estimate (120 s): a stall, with Try again.
  await page.clock.runFor(250000);
  await turn(page, 6);
  r.stalled = await bar(page, "search~1");
  await page.locator(workSel("search~1")).getByRole("button", {name: "Try again: Finding jobs"}).click();
  await turn(page, 6);
  r.retried = store.get("work/search~1");
  r.rings = (await calls(page)).filter((c) => c.cap === "comments");
  // Done.
  store.chat("work/search~1", {status: "done", finished_at: new Date().toISOString(), result: {summary: "6 roles worth a look", links: []}}, undefined, "update");
  await turn(page, 6);
  r.done = await bar(page, "search~1");
  if (a.shot) r.shot = await shot(page, a.shot);
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.limit = async (a) => {
  const old = new Date(Date.parse(T0) - 1500000).toISOString();
  const o = await open({html: a.html, hash: "work", clock: T0, seed: {
    "work/search~1": runningDoc({stage_at: old}),
    "work/draft~r12-2": runningDoc({kind: "draft", title: "CV and letter: Larkspur Retail", stage_at: old}),
  }});
  const {page, store} = o;
  const r = {banner: await T(page, "dialog .banner"), a: await bar(page, "search~1")};
  await page.locator("dialog").getByRole("button", {name: "Stop everything"}).click();
  await turn(page, 8);
  r.paused = [store.get("work/search~1").stop_asked, store.get("work/draft~r12-2").stop_asked];
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.stop = async (a) => {
  const late = new Date(Date.parse(T0) - 240000).toISOString();
  const o = await open({html: a.html, hash: "work", clock: T0, seed: {
    "work/search~1": runningDoc(),
    "work/prep~int-larkspur-supply": {kind: "prep", title: "Interview prep: Larkspur Retail", to: "cloud", args: {}, asked_at: late, status: "queued", stages: [], stage: 0, steps: [], stop_asked: false, attempt: 1},
  }, fake: {canSend: "available"}});
  const {page, store} = o;
  const r = {late: await bar(page, "prep~int-larkspur-supply")};
  // Late: the page asks its helper again first; only when that cannot be reached (no
  // connector here) is the link to start a chat by hand offered.
  r.rewake = (await bar(page, "prep~int-larkspur-supply")).buttons;
  await page.locator(workSel("prep~int-larkspur-supply")).getByRole("button", {name: "Ask Claude again: Interview prep: Larkspur Retail"}).click();
  await turn(page, 8);
  r.told = await page.$eval(workSel("prep~int-larkspur-supply"), (x) => x.textContent).catch(() => "");
  r.runningBefore = (await bar(page, "search~1")).buttons;
  await page.locator(workSel("search~1")).getByRole("button", {name: "Stop: Finding jobs"}).click();
  await turn(page, 6);
  r.running = store.get("work/search~1");
  r.runningCard = await bar(page, "search~1");
  await page.locator(workSel("prep~int-larkspur-supply")).getByRole("button", {name: "Don't do it: Interview prep: Larkspur Retail"}).click();
  await turn(page, 6);
  r.queued = store.get("work/prep~int-larkspur-supply");
  r.queuedCard = await bar(page, "prep~int-larkspur-supply");
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

async function draftViaDialog(page, opts) {
  await page.getByRole("button", {name: "Draft this: Harbourline Bank, Pricing Analyst"}).click();
  await turn(page, 3);
  const dlg = page.locator("dialog.sheet");
  if (opts && opts.submitEmpty) {
    await dlg.getByRole("button", {name: "Draft it"}).click();
    await turn(page, 3);
  }
  await dlg.getByLabel("No, draft it").check();
  await dlg.getByRole("group", {name: /fixed term/}).getByLabel("Yes").check();
  await dlg.getByRole("button", {name: "Draft it"}).click();
  await turn(page, 8);
}

S.draft = async (a) => {
  const o = await open({html: a.html, hash: "jobs", fake: a.fake || {canSend: "available"}});
  const {page, store} = o;
  await page.getByRole("button", {name: "Draft this: Harbourline Bank, Pricing Analyst"}).click();
  await turn(page, 3);
  const dlg = page.locator("dialog.sheet");
  const r = {open: await dlg.isVisible(), legends: await dlg.locator("legend").allInnerTexts(), focusInDialog: await page.evaluate(() => !!document.activeElement.closest("dialog")),
    cost: await one(page, "dialog .sheet-cost")};
  await dlg.getByRole("button", {name: "Draft it"}).click();
  await turn(page, 3);
  r.errors = await dlg.locator(".errors li").allInnerTexts();
  r.stillOpen = await dlg.isVisible();
  await dlg.getByLabel("Yes, I have applied").check();
  await turn(page, 2);
  r.submitWhenApplied = (await dlg.locator("button[type=submit]").innerText()).trim();
  await dlg.getByLabel("No, draft it").check();
  await turn(page, 2);
  r.submitWhenNot = (await dlg.locator("button[type=submit]").innerText()).trim();
  await dlg.getByRole("group", {name: /fixed term/}).getByLabel("Yes").check();
  await dlg.getByRole("button", {name: "Draft it"}).click();
  await turn(page, 8);
  r.closed = !(await page.$("dialog.sheet"));
  r.work = store.get("work/draft~r12-1");
  r.calls = (await calls(page)).filter((c) => c.cap === "comments" || c.cap === "room");
  r.doorbell = store.get("meta/doorbell");
  r.chip = await page.$eval('#main .card.job[aria-labelledby="job-r12-1"] .state-word', (x) => x.textContent).catch(() => null);
  r.pill = await one(page, "#pill");
  r.pageErrors = o.errors;
  if (a.shot) r.shot = await shot(page, a.shot);
  await o.ctx.close();
  return r;
};

// A referral in flight: the card says ask first, and drafting or marking it applied asks once.
S.referral = async (a) => {
  const o = await open({html: a.html, hash: "jobs"});
  const {page, store} = o;
  const card = page.locator('#main [data-item="r12-3"]');
  const r = {alert: await T(page, '#main [data-item="r12-3"] .alert-text'), primary: await T(page, '#main [data-item="r12-3"] .card-actions > a.btn.primary, #main [data-item="r12-3"] .card-actions > a.btn')};
  await openMore(page, "r12-3");
  await card.getByRole("button", {name: "I have applied: Copperleaf Pay, Data Analyst, Payments"}).click();
  await turn(page, 3);
  r.confirm = {title: await one(page, "dialog .sheet-title"), intro: await one(page, "dialog .sheet-intro"), go: await one(page, "dialog button[type=submit]")};
  await page.locator("dialog").getByRole("button", {name: "Not now"}).click();
  await turn(page, 4);
  r.afterNo = store.list("actions/");
  await card.getByRole("button", {name: "Draft this: Copperleaf Pay, Data Analyst, Payments"}).click();
  await turn(page, 3);
  r.draftConfirm = await one(page, "dialog button[type=submit]");
  await page.locator("dialog").getByRole("button", {name: "Draft it anyway"}).click();
  await page.waitForTimeout(50);
  await turn(page, 6);
  r.draftSheet = await one(page, "dialog .sheet-title");
  r.lead = await one(page, "dialog .warm");
  await page.keyboard.press("Escape");
  await turn(page, 3);
  // The warm note on another role links to the person it names.
  r.warmLink = await page.$eval('#main [data-item="r12-2"] .warm a', (x) => x.getAttribute("href")).catch(() => null);
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.applied_first = async (a) => {
  const o = await open({html: a.html, hash: "jobs"});
  const {page, store} = o;
  await page.getByRole("button", {name: "Draft this: Harbourline Bank, Pricing Analyst"}).click();
  await turn(page, 3);
  const dlg = page.locator("dialog.sheet");
  await dlg.getByLabel("Yes, I have applied").check();
  await dlg.getByLabel("When did you apply?").fill("2026-10-20");
  await dlg.getByRole("group", {name: /fixed term/}).getByLabel("No").check();
  await dlg.getByRole("button", {name: "Mark as applied"}).click();
  await turn(page, 8);
  const r = {work: store.list("work/"), actions: store.list("actions/").map((p) => store.get(p)), errors: o.errors};
  await o.ctx.close();
  return r;
};

S.two_tabs = async (a) => {
  const o = await open({html: a.html, hash: "jobs", tabs: 2, fake: {canSend: "available"}});
  const [p1, p2] = o.pages;
  for (const p of [p1, p2]) {
    await p.getByRole("button", {name: "Draft this: Harbourline Bank, Pricing Analyst"}).click();
    await turn(p, 3);
    const dlg = p.locator("dialog.sheet");
    await dlg.getByLabel("No, draft it").check();
    await dlg.getByRole("group", {name: /fixed term/}).getByLabel("Yes").check();
  }
  await Promise.all([p1, p2].map((p) => p.locator("dialog.sheet").getByRole("button", {name: "Draft it"}).click()));
  for (const p of [p1, p2]) await turn(p, 10);
  const r = {
    work: o.store.list("work/"),
    rings: (await calls(p1)).concat(await calls(p2)).filter((c) => c.cap === "comments").length,
    toasts: (await T(p1, ".toast")).concat(await T(p2, ".toast")),
    tabs: [await p1.evaluate(() => window.LJS.state().tab), await p2.evaluate(() => window.LJS.state().tab)],
  };
  // Both windows show the one job, live.
  r.seen = [await one(p1, "#pill"), await one(p2, "#pill")];
  // The same tick from both windows is one action.
  await p1.evaluate(() => { location.hash = "drafts-messages"; });
  await p2.evaluate(() => { location.hash = "drafts-messages"; });
  await turn(p1, 4); await turn(p2, 4);
  await p1.getByRole("button", {name: "I sent the message to Juno"}).click();
  await turn(p1, 6); await turn(p2, 6);
  // The other window shows it marked at once, live, with nothing left to press twice.
  r.otherWindow = {chip: await T(p2, "#main .card.msg.is-marked .state-word"), buttons: await p2.$$eval('#main button[aria-label="I sent the message to Juno"]', (x) => x.length)};
  r.actions = o.store.list("actions/");
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.room = async (a) => {
  const o = await open({html: a.html, hash: "jobs", fake: {canSend: "available", roomCan: "available"}});
  await draftViaDialog(o.page);
  const r = {calls: (await calls(o.page)).filter((c) => c.cap === "comments" || c.cap === "room"), work: o.store.list("work/"), errors: o.errors};
  await o.ctx.close();
  return r;
};

// The page wakes its helper chat by itself (Claude Code Remote send_message), and starts a
// new one on the person's copy when that fails, never asking anyone to wake Claude.
S.wake = async (a) => {
  const seed = {"meta/listener": {chat: "session_EXAMPLEHELPER", kind: "cloud", answered_at: "2026-10-25T08:00:00Z"}};
  const o = await open({html: a.html, hash: "jobs", seed, fake: {canSend: a.canSend || "available", mcp: {fail: a.fail || []}}});
  await draftViaDialog(o.page);
  await turn(o.page, 8);
  const all = await calls(o.page);
  const r = {mcp: all.filter((c) => c.cap === "mcp").map((c) => ({tool: c.tool, server: c.server, input: c.input})),
    rings: all.filter((c) => c.cap === "comments" && c.op === "sendToClaude").map((c) => ({text: c.text, active: c.active})), errors: o.errors};
  await goto(o.page, "todo");
  r.wakeCard = (await o.page.$$('#main [data-item="listen"]')).length;
  await o.ctx.close();
  return r;
};

// Reading LinkedIn in the desktop app: the page checks by itself when it opens there, and
// says how to sign in when signed out (2026-10-29).
S.reading = async (a) => {
  const o = await open({html: a.html, hash: a.hash || "todo", seed: a.seed || {}, model: a.model, fake: {canSend: a.canSend || "no_session", mcp: {browser: {inApp: a.inApp !== false, signedIn: !!a.signedIn, askFirst: !!a.askFirst, signInLater: !!a.signInLater, signOutAfter: a.signOutAfter || 0, check: a.check || 0, declined: !!a.declined, slowSections: !!a.slowSections}}}});
  await o.page.waitForTimeout(2500);
  // Until the page has finished reading (each page that draws late adds a moment).
  await o.page.waitForFunction(() => { const s = window.LJS.state().reading; return !s.busy && s.panel !== "run" && s.panel !== "check-run"; }, null, {timeout: 30000}).catch(() => {});
  await turn(o.page, 8);
  const r = {browser: (await calls(o.page)).filter((c) => c.cap === "mcp" && c.server === "host:claude_browser").map((c) => ({tool: c.tool, input: c.input})), errors: o.errors};
  if (a.signInLater) {
    // The person signs in in Claude's browser and comes back to the page.
    await o.page.evaluate(() => { window.__ljsBrowser.signedIn = true; window.dispatchEvent(new Event("focus")); });
    await o.page.waitForTimeout(1500);
    await o.page.waitForFunction(() => { const s = window.LJS.state().reading; return !s.busy && s.panel !== "run" && s.panel !== "check-run"; }, null, {timeout: 30000}).catch(() => {});
    await turn(o.page, 8);
  }
  r.panel = await o.page.evaluate(() => { const p = document.querySelector(".browser-panel"); return p ? p.textContent : ""; });
  r.state = await o.page.evaluate(() => { const s = window.LJS.state(); return {ok: s.reading.ok, signedOut: s.reading.signedOut, panel: s.reading.panel}; });
  r.acts = [...o.store.docs.entries()].filter(([p]) => p.startsWith("actions/")).map(([p, d]) => ({id: p.slice(8), action: d.data.action, value: d.data.value}));
  r.line = await o.page.evaluate(() => window.LJS.state().reading.line || "");
  r.todo = await o.page.evaluate(() => (document.querySelector("#main") || document.body).textContent);
  r.cards = await o.page.evaluate(() => [...document.querySelectorAll("#main [data-item]")].map((e) => e.getAttribute("data-item")));
  if (a.write) {
    // "Write my notes" in the panel: one ring for every profile read, from the person's tap.
    await o.page.click('[data-k="bp-write"]');
    await o.page.waitForTimeout(600);
    r.rings = (await calls(o.page)).filter((c) => c.cap === "comments" && c.op === "sendToClaude").map((c) => ({text: c.text, active: c.active}));
    r.cardsAfter = await o.page.evaluate(() => [...document.querySelectorAll("#main [data-item]")].map((e) => e.getAttribute("data-item")));
  }
  if (a.bin) {
    await o.page.$eval('[data-k="reading-bin"]', (b) => b.click());
    await o.page.waitForTimeout(300);
    await o.page.check('input[type="radio"][value="' + a.bin + '"]');
    await o.page.click('[data-k="sheet-go"]');
    await o.page.waitForTimeout(900);
    r.acts = [...o.store.docs.entries()].filter(([p]) => p.startsWith("actions/")).map(([p, d]) => ({id: p.slice(8), action: d.data.action, value: d.data.value, item: d.data.item}));
  }
  await o.ctx.close();
  return r;
};

// Your profile: a gap filled from To do, skills changed and a job taken off in Settings, each
// one `profile` work item a chat makes (2026-10-28).
S.you = async (a) => {
  const o = await open({html: a.html, hash: "todo"});
  const {page, store} = o;
  const works = () => store.list("work/").map((k) => store.get(k)).filter((w) => w && w.kind === "profile");
  const r = {card: await T(page, '#main [data-item="you"] .card-title')};
  await page.locator('#main [data-item="you"]').getByRole("button", {name: "Add what you did"}).click();
  await turn(page, 3);
  let dlg = page.locator("dialog.sheet");
  r.sheet = await T(page, "dialog.sheet #sheet-title");
  await dlg.getByLabel(/What you did there/).fill("Built the weekly stock report for 40 stores.");
  await dlg.getByRole("button", {name: "Add it"}).click();
  await turn(page, 6);
  // Settings, then Your profile: a page of its own since 4.3.
  await goto(page, "settings");
  await page.locator('[data-k="open-profile"]').first().click();
  await turn(page, 3);
  await page.getByRole("button", {name: "Add or take off"}).first().click();
  await turn(page, 3);
  dlg = page.locator("dialog.sheet");
  await dlg.getByLabel("Power BI").uncheck();
  await dlg.getByLabel(/^Add skills/).fill("Looker, SQL");
  await dlg.getByRole("button", {name: "Save"}).click();
  await turn(page, 6);
  await page.getByRole("button", {name: "Take Graduate Analyst at Saltmarsh Analytics off"}).first().click();
  await turn(page, 3);
  await page.locator("dialog.sheet").getByRole("button", {name: "Take it off"}).click();
  await turn(page, 6);
  r.works = works().map((w) => ({title: w.title, args: w.args}));
  r.busy = await T(page, "#main .you-busy, #main [role=status]");
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// The walkthrough: offered once on To do, each step opening its section, skippable one step
// or all of it; and one part of it from the "?" on any section's title (2026-10-28).
S.tour = async (a) => {
  // A laptop: the "?" on a section's title is not shown on a phone.
  const o = await open({html: a.html, hash: "todo", viewport: {width: 1280, height: 800}});
  const {page} = o;
  const r = {card: await T(page, '#main [data-item="tour"] .card-title')};
  await page.getByRole("button", {name: "Show me around"}).click();
  await turn(page, 4);
  r.first = await T(page, "dialog.sheet #sheet-title");
  await page.locator("dialog.sheet").getByRole("button", {name: "Next"}).click();
  await turn(page, 4);
  await page.waitForTimeout(100);
  r.second = {title: await T(page, "dialog.sheet #sheet-title"), hash: await page.evaluate(() => location.hash)};
  await page.locator("dialog.sheet").getByRole("button", {name: "Skip the rest"}).click();
  await turn(page, 4);
  r.closed = await page.locator("dialog.sheet[open]").count();
  await goto(page, "todo");
  r.cardAfter = await page.locator('#main [data-item="tour"]').count();
  await goto(page, "contacts");
  await page.getByRole("button", {name: "How Contacts works"}).click();
  await turn(page, 4);
  r.part = {title: await T(page, "dialog.sheet #sheet-title"), buttons: await T(page, "dialog.sheet button")};
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.no_listener = async (a) => {
  const o = await open({html: a.html, hash: "jobs", fake: {canSend: "no_session"}});
  await draftViaDialog(o.page);
  await goto(o.page, "work");
  const r = {notes: await T(o.page, workSel("draft~r12-1") + " .note"), links: await o.page.$$eval(workSel("draft~r12-1") + " a.btn", (x) => x.map((e) => e.href)),
    calls: (await calls(o.page)).filter((c) => c.cap === "comments"), work: o.store.get("work/draft~r12-1"), errors: o.errors};
  await o.ctx.close();
  return r;
};

S.downloads = async (a) => {
  const o = await open({html: a.html, hash: "drafts", fake: a.fake});
  const {page, store} = o;
  const r = {};
  await page.getByRole("button", {name: "Get both files: Morgan_Ellis_CV_Ellerwick.pdf and Morgan_Ellis_Cover_Letter_Ellerwick.pdf"}).click();
  await page.waitForTimeout(200);
  await turn(page, 8);
  r.saves = (await calls(page)).filter((c) => c.cap === "downloads");
  r.note = await T(page, '#main [data-item="app-ellerwick-insight"] .note');
  // Its question answered and done: then the draft asks for its files.
  await page.locator('#main [data-item="app-quayside-demand"]').getByRole("button", {name: "Not yet"}).click();
  await turn(page, 4);
  for (const p of store.list("actions/")) store.chat("receipts/" + p.split("/")[1], {applied_at: new Date().toISOString(), by: "cloud-1", result: "ok", note: ""});
  await turn(page, 6);
  r.noLetter = await T(page, '#main .card.app[aria-labelledby="app-app-quayside-demand"] .muted.small');
  r.askButtons = await T(page, '#main .card.app[aria-labelledby="app-app-quayside-demand"] button');
  r.primary = await T(page, '#main .card.app[aria-labelledby="app-app-quayside-demand"] .card-actions .btn[data-primary]');
  // Files not on the page yet are said once, above the drafts (4.3).
  r.filesLine = await T(page, "#main .files-line");
  await page.locator('[data-k="files-all"]').first().click();
  await turn(page, 8);
  r.work = store.get("work/files~app-quayside-demand");
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.copy = async (a) => {
  const o = await open({html: a.html, hash: "drafts-messages", clipboard: !a.denied, fake: {clipboardDenied: !!a.denied}});
  const {page} = o;
  const main = (sel) => page.$eval(sel, (x) => x.hasAttribute("data-primary"));
  const before = {copy: await main('#main [data-item="msg-juno-1"] button.copy'), sent: await main('#main [data-item="msg-juno-1"] [data-k="sent:msg-juno-1"]')};
  await page.getByRole("button", {name: "Copy message to Juno"}).click();
  await turn(page, 6);
  const r = {before, label: await T(page, '#main [data-item="msg-juno-1"] button.copy'), note: await T(page, "#main .card.msg .note"),
    sentFilled: await main('#main [data-item="msg-juno-1"] [data-k="sent:msg-juno-1"]'),
    selected: await page.evaluate(() => String(window.getSelection())), errors: o.errors};
  if (!a.denied) r.clip = await copied(page);
  await o.ctx.close();
  return r;
};

S.bulk = async (a) => {
  const o = await open({html: a.html, hash: "jobs"});
  const {page, store} = o;
  const boxesBefore = (await page.$$("#main label.pick")).length;
  await menuPick(page, "Select several");
  await turn(page, 3);
  await page.getByLabel("Select Harbourline Bank, Pricing Analyst").check();
  await page.getByLabel("Select Copperleaf Pay, Data Analyst, Payments").check();
  await turn(page, 4);
  const r = {boxesBefore, mixed: await page.$eval("#all-jobs", (x) => x.indeterminate), bar: await one(page, "#main .bulk"),
    toastsAbove: null};
  await page.getByRole("button", {name: "Mark 2 as applied"}).click();
  await turn(page, 3);
  r.confirm = await one(page, "dialog .sheet-title");
  await page.locator("dialog").getByRole("button", {name: "Mark as applied anyway"}).click();
  await page.waitForTimeout(30);
  await turn(page, 8);
  r.actions = store.list("actions/").map((p) => store.get(p));
  r.after = await page.$$eval("#main .card.job.is-marked h3", (x) => x.map((e) => e.textContent));
  r.focus = await page.evaluate(() => document.activeElement.tagName + ":" + (document.activeElement.id || ""));
  await goto(page, "drafts");
  await menuPick(page, "Select several");
  await turn(page, 3);
  await page.getByLabel("Select all 2 not yet sent").check();
  await turn(page, 4);
  await page.getByRole("button", {name: "Mark 2 as applied"}).click();
  await turn(page, 8);
  r.readyActions = store.list("actions/").filter((p) => p.indexOf("ready.applied") >= 0);
  r.toastAboveBulk = await page.evaluate(() => { const t = document.querySelector(".toast"); const b = document.querySelector(".bulk"); if (!t || !b) return null; return t.__drawnRect().bottom <= b.__drawnRect().top + 1; });
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// Alerts and suggestions on the cards: a coloured line with one button and its cost; one
// suggestion with No thanks; the Suggestions setting hides suggestions and never alerts.
S.alerts = async (a) => {
  const o = await open({html: a.html, hash: "jobs"});
  const {page, store} = o;
  const r = {closed: await T(page, '#main [data-item="r12-5"] .alert-text'), cost: await T(page, '#main [data-item="r12-5"] .alert .cost')};
  await page.locator('#main [data-item="r12-5"] .alert').getByRole("button", {name: "Set it aside"}).click();
  await turn(page, 6);
  r.fixed = actionAt(store, "actions/act~r12-5~job.dismiss");
  // The draft's own card asks its question first; its failed check is a card in To do.
  await goto(page, "todo");
  r.checksFix = await T(page, '#main [data-item="al:al-checks-app-quayside-demand"] .fix .btn');
  await goto(page, "drafts");
  r.suggest = await T(page, '#main [data-item="app-ellerwick-insight"] .suggest-text');
  await page.getByRole("button", {name: /^No thanks: The posting asks for Tableau/}).click();
  await turn(page, 6);
  r.dismissed = actionAt(store, "actions/act~sg-near-app-ellerwick-insight-3f2a9c1d~suggest.dismiss");
  r.gone = (await page.$$('#main [data-item="app-ellerwick-insight"] .suggest')).length;
  r.toast = await T(page, ".toast-text");
  await page.locator(".toast").last().getByRole("button", {name: "Undo", exact: true}).click();
  await turn(page, 6);
  r.back = (await page.$$('#main [data-item="app-ellerwick-insight"] .suggest')).length;
  await goto(page, "settings");
  await openSetting(page, "suggestions");
  await page.locator('[data-k="set-sum:suggestions"]').locator("xpath=..").getByLabel("Off", {exact: true}).first().check();
  await page.waitForTimeout(700);
  await turn(page, 6);
  await goto(page, "drafts");
  r.offSuggest = (await page.$$("#main .suggest")).length;
  await goto(page, "jobs");
  r.offAlerts = (await page.$$("#main .alert")).length;
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// To do: bands by when, employers together inside a band, the kind on every item, chips by
// kind, and each section opening with its own to-dos.
// A busy week: checklists, the hidden line, counts, Progress's two periods, the bin.
S.busy = async (a) => {
  const o = await open({html: a.html, hash: "todo", clock: "2026-10-25T09:00:00Z"});
  const {page} = o;
  const r = await page.evaluate(() => {
    const t = (e) => (e ? e.textContent.trim() : "");
    const groups = Object.fromEntries([...document.querySelectorAll("#main .group-card")].map((c) => [c.getAttribute("data-item"), {
      title: t(c.querySelector(".card-title")), rows: [...c.querySelectorAll(".g-row")].map((row) => ({buttons: [...row.querySelectorAll("button")].map(t)})),
      actions: [...c.querySelectorAll(".card-actions button")].map(t)}]));
    const counts = {};
    for (const a of document.querySelectorAll('[data-k^="tab:"], [data-k^="side:"]')) {
      const n = a.querySelector(".navcount");
      if (n) counts[a.getAttribute("data-k").split(":")[1]] = n.firstChild.textContent;
    }
    return {groups, counts, hidden: t(document.querySelector("#main .hidden-note")), text: document.getElementById("main").innerText,
      gauge: document.querySelectorAll("#main .cost .gauge").length};
  });
  await goto(page, "settings");
  r.settings = await page.evaluate(() => document.getElementById("main").innerText);
  await goto(page, "progress");
  r.progress = {recent: await page.evaluate(() => document.querySelector("#main .sum").textContent)};
  await page.click('[data-k="range:all"]');
  await turn(page, 4);
  r.progress.all = await page.evaluate(() => document.querySelector("#main .sum").textContent);
  await goto(page, "jobs");
  await clickText(page, "button", "Not for me: Harbourline Bank, Pricing Analyst");
  r.bin = await page.evaluate(() => { const d = document.querySelector("dialog[open]"); return d ? {title: d.querySelector("#sheet-title").textContent, options: [...d.querySelectorAll("label")].map((l) => l.textContent)} : null; });
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.todo = async (a) => {
  const o = await open({html: a.html, hash: "todo", viewport: a.viewport});
  const {page} = o;
  const r = await page.evaluate(() => {
    const title = (c) => { const t = c.querySelector(".card-title"); return t ? t.textContent : ""; };
    const bands = [...document.querySelectorAll("#main .band")].map((b) => ({band: b.querySelector("h3").textContent,
      groups: [...b.querySelectorAll(".todo-group")].map((g) => ({employer: g.querySelector("h4") ? g.querySelector("h4").textContent : null,
        titles: [...g.querySelectorAll("[data-card]")].map(title)}))}));
    const first = document.querySelector("#main [data-card]");
    return {bands, first: first ? title(first) : null, summary: (document.querySelector("#main .summary") || {}).textContent,
      soon: [...document.querySelectorAll("#main .soon .card-title")].map((x) => x.textContent),
      chips: document.querySelectorAll("#main .fbar button, #main .chips button").length,
      filled: [...document.querySelectorAll("#main .need .btn.primary")].length, answers: [...document.querySelectorAll("#main .need .btn.answer")].length,
      dueButtons: Object.fromEntries([...document.querySelectorAll("#main .due-row")].map((c) => [title(c), [...c.querySelectorAll(".card-actions button")].map((b) => b.textContent)]))};
  });
  await goto(page, "jobs");
  r.jobsQuestion = await page.evaluate(() => { const c = document.querySelector('#main [data-item="r12-2"]'); return c && c.querySelector(".question") ? c.querySelector(".question").textContent : null; });
  await goto(page, "contacts");
  r.juno = await page.evaluate(() => { const c = document.querySelector('#main [data-item="larkspur_retail_castellan"]'); return c ? {state: (c.querySelector(".state-word") || {}).textContent, buttons: [...c.querySelectorAll("button")].filter((b) => !b.closest("details")).map((b) => b.textContent)} : null; });
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.talk = async (a) => {
  const o = await open({html: a.html, hash: "chat", fake: {canSend: "available", sample: a.sample || {toolCalls: [{name: "read_section", input: {section: "due"}}], reply: "Two things are due today: reply to Juno and nudge Fernhill Freight."}}});
  const {page, store} = o;
  const r = {examples: await T(page, "#main .talk-examples button"), label: await one(page, "#talk-label"), placeholder: await page.getAttribute("#talk-text", "placeholder")};
  await page.getByLabel("Ask Claude anything").fill(a.question || "What is due today?");
  await page.getByRole("button", {name: "Send", exact: true}).click();
  await page.waitForTimeout(50);
  await turn(page, 12);
  r.quick = await T(page, "#main .talk-msg .talk-text");
  // Handed on to Claude, the note's one button sends it, from the person's own tap.
  const send = page.locator("#main .talk-msg").getByRole("button", {name: "Send to Claude"});
  if (await send.count()) { await send.first().click(); await turn(page, 6); r.afterSend = await T(page, "#main .talk-msg .talk-text"); }
  r.tools = await page.evaluate(() => (window.__toolResults || []).map((t) => [t.name, String(t.out).slice(0, 400)]));
  r.sampleCall = (await calls(page)).filter((c) => c.cap === "sample").map((c) => ({tools: c.tools, tier: c.modelTier, last: c.input[c.input.length - 1], first: String(c.input[0].content).slice(0, 120)}));
  r.stored = store.list("talk/");
  r.work = store.list("work/").map((p) => store.get(p));
  r.rings = (await calls(page)).filter((c) => c.cap === "comments").map((c) => c.text);
  r.status = await one(page, "#main .talk-status");
  r.busy = await page.getAttribute("#main .talk-list", "aria-busy");
  if (a.shot) r.shot = await shot(page, a.shot);
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// With no quick answers here, a question goes straight to Claude in the cloud, and its answer
// comes back into the same box.
S.chat_cloud = async (a) => {
  const o = await open({html: a.html, hash: "chat", fake: {canSend: "available", caps: ["user", "db", "comments", "room", "downloads", "assets"]}});
  const {page, store} = o;
  await page.getByLabel("Ask Claude anything").fill("Can you look at the careers page for Harbourline Bank?");
  await page.getByRole("button", {name: "Send", exact: true}).click();
  await turn(page, 10);
  const r = {docs: store.list("talk/cloud-1/messages/").map((p) => store.get(p)), work: store.list("work/").map((p) => [p, store.get(p)]),
    rings: (await calls(page)).filter((c) => c.cap === "comments").map((c) => c.text), waiting: await T(page, "#main .talk-msg.pending")};
  store.chat("talk/cloud-1/messages/m-reply", {from: "cloud", text: "Their careers page lists the Pricing Analyst role and closes on 31 October.", at: new Date().toISOString()});
  await turn(page, 8);
  r.shown = await T(page, "#main .talk-msg .talk-text");
  r.who = await T(page, "#main .talk-msg .talk-who");
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// Work goes to the one chat that answers the page, with nothing to choose (4.3): answered on
// the computer, a question waits for it there and the page says so; with it open, it goes there.
// The brief's bell on such a page starts the helper in the cloud in the same tap.
S.chat_computer = async (a) => {
  const listener = {"meta/listener": {chat: "local-1", kind: "computer", answered_at: "2026-10-25T08:00:00Z"}};
  const seed = Object.assign({}, listener, a.listening ? {"chats/computer-1": {kind: "computer", title: "On the laptop", can: ["talk"], seen_at: new Date().toISOString(), busy: null}} : {});
  const o = await open({html: a.html, hash: "settings", seed, fake: {canSend: "available", caps: ["user", "db", "comments", "room", "downloads", "assets"]}});
  const {page, store} = o;
  await page.$$eval("details.set-advanced:not([open])", (ds) => ds.forEach((d) => { d.open = true; }));
  await turn(page, 2);
  const r = {legend: await T(page, "#main fieldset legend"), settingKeys: await page.$$eval('[data-k^="set-sum:"]', (els) => els.map((e) => e.getAttribute("data-k")))};
  await goto(page, "chat");
  await page.getByLabel("Ask Claude anything").fill("Can you open the CV file on my laptop?");
  await page.getByRole("button", {name: "Send", exact: true}).click();
  await turn(page, 10);
  r.work = store.list("work/").map((p) => store.get(p)).filter((w) => w.kind === "talk");
  r.waiting = await T(page, "#main .talk-msg.pending");
  r.rings = (await calls(page)).filter((c) => c.cap === "comments").length;
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// The chat from any section: a round button bottom right opens a panel with the same thread
// as the Chat page, the same box and the same send. Data arriving and moving between sections
// leave it open; Escape closes it and gives focus back; Open in Chat carries on there.
S.chat_dock = async (a) => {
  const at = (s) => new Date(Date.parse("2026-10-25T08:00:00Z") + s * 1000).toISOString();
  const seed = {"talk/cloud-1": {to: "cloud", conv: "1", title: "Is Harbourline Bank hiring?", created_at: at(0)},
    "talk/cloud-1/messages/m1": {from: "you", text: "Is Harbourline Bank hiring analysts?", at: at(1)},
    "talk/cloud-1/messages/m2": {from: "cloud", text: "Yes: two analyst roles opened there this week.", at: at(2)}};
  const o = await open({html: a.html, viewport: a.viewport, hash: "jobs", seed, fake: {canSend: "available", caps: ["user", "db", "comments", "room", "downloads", "assets"]}});
  const {page, store} = o;
  const vis = (sel) => visible(page, sel);
  const focusK = () => page.evaluate(() => document.activeElement ? document.activeElement.getAttribute("data-k") : null);
  const r = {fab: await vis("#chat-fab"), fabName: await page.getAttribute("#chat-fab", "aria-label"), dockBefore: await vis("#chat-dock")};
  if (a.viewport && a.viewport.width < 760) {
    await goto(page, "contacts");
    await page.getByRole("button", {name: /^Got a message\?/}).first().click();
    await turn(page, 6);
    r.phone = {hash: await page.evaluate(() => location.hash), dock: await vis("#chat-dock"), focus: await focusK(), value: await page.inputValue("#main #talk-text")};
    r.errors = o.errors;
    await o.ctx.close();
    return r;
  }
  await page.click("#chat-fab");
  await turn(page, 6);
  r.open = {dock: await vis("#chat-dock"), fab: await vis("#chat-fab"), focus: await focusK(), box: await page.evaluate(() => !!document.querySelector("#chat-dock #talk-text")),
    role: await page.getAttribute("#chat-dock", "role"), name: await one(page, "#h-dock"), msgs: await T(page, "#chat-dock .talk-msg .talk-text")};
  r.geo = await page.evaluate(() => {
    const d = document.getElementById("chat-dock").__drawnRect();
    const t = document.getElementById("tabs");
    const tr = t && t.getClientRects().length ? t.__drawnRect() : null;
    return {top: d.top, bottom: d.bottom, left: d.left, right: d.right, vw: innerWidth, vh: innerHeight, tabsTop: tr ? tr.top : null};
  });
  r.a11y = await page.evaluate(a11yProbe);
  await page.fill("#chat-dock #talk-text", "Can you check their careers page?");
  await page.click("#chat-dock [data-k=talk-send]");
  await turn(page, 10);
  r.docs = store.list("talk/cloud-1/messages/").map((p) => store.get(p));
  r.work = store.list("work/").map((p) => store.get(p)).filter((w) => w.kind === "talk");
  r.sent = await T(page, "#chat-dock .talk-msg .talk-text");
  // A chat answers while the person moves to another section: the panel stays open with it.
  store.chat("talk/cloud-1/messages/m9", {from: "cloud", text: "Their careers page lists a Pricing Analyst role.", at: new Date(Date.now() + 1000).toISOString()});
  await turn(page, 8);
  await goto(page, "contacts");
  r.moved = {dock: await vis("#chat-dock"), msgs: await T(page, "#chat-dock .talk-msg .talk-text")};
  await page.focus("#chat-dock #talk-text");
  await page.keyboard.press("Escape");
  await turn(page, 4);
  r.esc = {dock: await vis("#chat-dock"), fab: await vis("#chat-fab"), focus: await focusK()};
  // Someone wrote to them: one line on Contacts opens the chat ready for it.
  const got = page.getByRole("button", {name: /^Got a message\?/}).first();
  r.got = {label: (await got.innerText()).trim()};
  await got.click();
  await turn(page, 6);
  Object.assign(r.got, {dock: await vis("#chat-dock"), focus: await focusK(), value: await page.inputValue("#talk-text")});
  await page.keyboard.press("Escape");
  await turn(page, 4);
  r.got.back = await focusK();
  await page.click("#chat-fab");
  await turn(page, 4);
  await page.click("#chat-dock [data-k=dock-full]");
  await turn(page, 6);
  r.chat = {hash: await page.evaluate(() => location.hash), dock: await vis("#chat-dock"), fab: await vis("#chat-fab"), msgs: await T(page, "#main .talk-msg .talk-text"),
    focus: await focusK(), value: await page.inputValue("#main #talk-text")};
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// Pictures in the chat: a screenshot pasted into the box goes to the page's file store, shows
// in the box, and its id goes with the message. With no file store the button is not there.
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
S.chat_pics = async (a) => {
  const caps = ["user", "db", "comments", "room", "downloads"].concat(a.noAssets ? [] : ["assets"]);
  const o = await open({html: a.html, viewport: a.viewport, hash: a.hash || "chat", fake: {canSend: "available", caps}});
  const {page, store} = o;
  if (a.hash && a.hash !== "chat") { await page.click("#chat-fab"); await turn(page, 6); }
  const r = {add: await visible(page, ".talk-add"), placeholder: await page.getAttribute("#talk-text", "placeholder"), intro: await one(page, ".talk-intro"),
    starters: await T(page, '[aria-label="Ways to start"] button'), asks: await T(page, '[aria-label="Questions you could ask"] button')};
  if (a.noAssets) { r.errors = o.errors; await o.ctx.close(); return r; }
  await page.evaluate((b64) => {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], "screenshot.png", {type: "image/png"}));
    const ta = document.getElementById("talk-text");
    ta.focus();
    // A paste event carrying the picture. Firefox drops clipboardData given to a synthetic
    // ClipboardEvent (the Everywhere check, 2026-10-29), so it is put on the event itself.
    const ev = new Event("paste", {bubbles: true, cancelable: true});
    Object.defineProperty(ev, "clipboardData", {value: dt});
    ta.dispatchEvent(ev);
  }, PNG.toString("base64"));
  await turn(page, 8);
  // A picture decodes in its own time, later in Firefox than in Chrome's engine.
  await page.waitForFunction(() => [...document.querySelectorAll(".talk-attach img.pic-thumb")].every((i) => i.complete && i.naturalWidth > 0), null, {timeout: 5000}).catch(() => {});
  r.tray = await page.evaluate(() => [...document.querySelectorAll(".talk-attach .pic-chip")].map((c) => {
    const img = c.querySelector("img.pic-thumb");
    return {img: !!img, loaded: !!img && img.complete && img.naturalWidth > 0, state: c.querySelector(".pic-state").textContent, remove: (c.querySelector("button") || {}).textContent};
  }));
  r.uploaded = await page.evaluate(() => (window.__ljsAssets || []).slice());
  r.typed = await page.inputValue("#talk-text");
  await page.setInputFiles(".talk-form input[type=file]", {name: "photo.heic", mimeType: "image/heic", buffer: Buffer.from("not a png")});
  await turn(page, 4);
  r.note = await one(page, ".talk-attach .note");
  r.trayCount = (await page.$$(".talk-attach .pic-chip")).length;
  await page.fill("#talk-text", "Help me reply to this");
  await page.click("[data-k=talk-send]");
  await turn(page, 12);
  r.docs = store.list("talk/").filter((p) => p.includes("/messages/")).map((p) => store.get(p));
  r.work = store.list("work/").map((p) => store.get(p)).filter((w) => w.kind === "talk");
  r.thread = await page.evaluate(() => [...document.querySelectorAll(".talk-msg .talk-pic")].map((e) => ({tag: e.tagName, alt: e.getAttribute("alt") || e.getAttribute("aria-label")})));
  r.texts = await T(page, ".talk-msg .talk-text");
  r.trayAfter = (await page.$$(".talk-attach .pic-chip")).length;
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.mock = async (a) => {
  const o = await open({html: a.html, hash: "interviews", fake: {sample: {reply: "First question: tell me about a forecast you built."}}});
  await o.page.getByRole("button", {name: "Practise with Claude for Larkspur Retail"}).click();
  await o.page.waitForTimeout(50);
  await turn(o.page, 10);
  const r = {heading: await one(o.page, "#main h2"), msgs: await T(o.page, "#main .talk-msg .talk-text"),
    first: (await calls(o.page)).filter((c) => c.cap === "sample").map((c) => String(c.input[0].content).slice(0, 200)), errors: o.errors};
  await o.ctx.close();
  return r;
};

S.keyboard = async (a) => {
  const o = await open({html: a.html, viewport: {width: 1440, height: 900}, hash: "jobs"});
  const {page} = o;
  const r = {};
  await page.keyboard.press("Tab");
  r.first = await page.evaluate(() => document.activeElement.textContent.trim());
  await page.keyboard.press("Enter");
  await turn(page, 2);
  r.afterSkip = await page.evaluate(() => document.activeElement.id);
  // Into the nav, then Contacts by keyboard alone.
  await page.focus('#side a[href="#contacts"]');
  await page.keyboard.press("Enter");
  await turn(page, 4);
  r.draftsFocus = await page.evaluate(() => document.activeElement.textContent.trim());
  await page.focus('#side a[href="#jobs"]');
  await page.keyboard.press("Enter");
  await turn(page, 4);
  let found = false;
  for (let i = 0; i < 40 && !found; i++) {
    await page.keyboard.press("Tab");
    found = await page.evaluate(() => (document.activeElement.getAttribute("aria-label") || "") === "Draft this: Harbourline Bank, Pricing Analyst");
  }
  r.reachedDraft = found;
  r.visibleFocus = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  await page.keyboard.press("Enter");
  await turn(page, 3);
  r.dialog = await page.evaluate(() => !!document.activeElement.closest("dialog"));
  await page.keyboard.press("Escape");
  await turn(page, 4);
  r.dialogGone = !(await page.$("dialog.sheet"));
  r.backOn = await page.evaluate(() => document.activeElement.getAttribute("aria-label"));
  // The keyboard layer: ? lists the keys, g then a letter moves, j to a card, Enter its main button.
  await page.evaluate(() => document.activeElement.blur());
  await page.keyboard.press("?");
  await turn(page, 3);
  r.help = await one(page, "dialog .sheet-title");
  await page.keyboard.press("Escape");
  await turn(page, 3);
  await page.keyboard.press("g");
  await page.keyboard.press("t");
  await turn(page, 4);
  r.afterGT = await one(page, "#main h2");
  await page.keyboard.press("g");
  await page.keyboard.press("j");
  await turn(page, 4);
  r.afterGJ = await one(page, "#main h2");
  await page.keyboard.press("j");
  await turn(page, 2);
  r.cardFocus = await page.evaluate(() => document.activeElement.getAttribute("data-item"));
  // Escape closes a card's More.
  await openMore(page, "r12-2");
  await page.keyboard.press("Escape");
  await turn(page, 2);
  r.moreClosed = await page.$eval('#main [data-item="r12-2"] details.more', (d) => !d.open);
  // Typing in a box is never a shortcut, and single keys can be switched off.
  await goto(page, "chat");
  await page.focus("#talk-text");
  await page.keyboard.type("gj");
  await turn(page, 3);
  r.typed = [await page.inputValue("#talk-text"), await one(page, "#main h2")];
  await goto(page, "settings");
  await page.$$eval("details.set-advanced:not([open])", (ds) => ds.forEach((d) => { d.open = true; }));
  await turn(page, 2);
  await page.getByRole("switch", {name: "Keyboard shortcuts"}).uncheck();
  await turn(page, 3);
  await page.evaluate(() => document.activeElement.blur());
  await page.keyboard.press("g");
  await page.keyboard.press("j");
  await turn(page, 3);
  r.offStays = await one(page, "#main h2");
  r.stored = await page.evaluate(() => localStorage.getItem("ljs:keys"));
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// Back goes back through the sections inside the page, and an item has an address of its own.
S.history = async (a) => {
  const o = await open({html: a.html, viewport: {width: 1440, height: 900}, hash: "todo"});
  const {page} = o;
  await page.click('#side a[href="#jobs"]');
  await turn(page, 3);
  await page.click('#side a[href="#contacts"]');
  await turn(page, 3);
  await page.goBack();
  await turn(page, 6);
  const r = {afterBack: await one(page, "#main h2"), hash: await page.evaluate(() => location.hash)};
  await page.evaluate(() => { location.hash = "contacts/copperleaf_pay_tamsin"; });
  await turn(page, 8);
  r.item = await page.evaluate(() => ({focus: document.activeElement.getAttribute("data-item"), heading: document.querySelector("#main h2").textContent}));
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// Times in the person's own zone, with the zone named when this device is in another one, and
// a date with no time shown as a day.
S.zones = async (a) => {
  const o = await open({html: a.html, hash: "interviews", timezoneId: a.timezoneId || "America/Toronto"});
  const r = {whens: await T(o.page, "#main .when"), chips: await T(o.page, "#main .card.interview .chip"), errors: o.errors};
  await o.ctx.close();
  return r;
};

// A person with many live things sees every live one without a tap; only finished history folds.
S.crowd = async (a) => {
  const o = await open({html: a.html, hash: "progress", viewport: a.viewport});
  const {page} = o;
  const r = {progressRows: (await page.$$('#main [data-list="progress:apps"] tbody tr, #main [data-list="progress:apps"] .app-row')).length, progressFold: await T(page, "#main .fold"), progressSearch: !!(await page.$("#main input[type=search]"))};
  await goto(page, "contacts");
  // Contacts opens on who needs the person (4.3), with no filter left on: everyone else is
  // one fold below.
  r.contactDefault = (await page.$$("#main .person")).length;
  r.defaultChips = await T(page, "#main .active-filters .af-chip");
  r.contactRows = r.contactDefault;
  r.contactFold = await T(page, "#main .fold");
  r.contactSearch = !!(await page.$("#main input[type=search]"));
  await page.locator("#main input[type=search]").fill("Quayside");
  await turn(page, 4);
  r.searched = (await page.$$("#main .person")).length;
  r.searchFocus = await page.evaluate(() => document.activeElement.type);
  r.hidden = await T(page, "#main .fold");
  await page.getByRole("button", {name: "Clear filters"}).first().click();
  await turn(page, 4);
  r.cleared = (await page.$$("#main .person")).length;
  const fold = page.getByRole("button", {name: /^Show \d+ more (person|people)/});
  await fold.first().click();
  await turn(page, 4);
  r.unfolded = (await page.$$("#main .person")).length;
  r.overflow = await overflow(page);
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// Every control on every screen, tapped one at a time on a fresh page: none throws, and each
// does something a person can see or that reaches Claude (the maintainer, 2026-10-29: "I'm
// starting to doubt even some of the buttons work"). A link to another site is checked for a
// real address instead of followed.
S.sweep = async (a) => {
  const out = {dead: [], errors: [], unclickable: [], badLinks: [], tapped: 0, perSection: {}};
  const keysOn = (page) => page.evaluate(() => {
    const vis = (e) => e.getClientRects().length > 0 && e.checkVisibility({visibilityProperty: true}) && !e.closest("details:not([open]) > :not(summary)");
    // What is already chosen (the switch's own place, a pressed answer) and what is switched
    // off are not taps that should do something.
    const els = [...document.querySelectorAll("#main [data-k]")].filter((e) => vis(e) && e.matches("button, a[href], summary, input[type=radio], input[type=checkbox], label")
      && e.getAttribute("aria-pressed") !== "true" && !e.hasAttribute("aria-current") && !e.disabled && e.getAttribute("aria-disabled") !== "true" && !(e.matches("input") && e.checked));
    const ext = els.filter((e) => e.matches("a[href]") && /^https?:/.test(e.getAttribute("href"))).map((e) => [e.getAttribute("data-k"), e.getAttribute("href")]);
    return {keys: [...new Set(els.filter((e) => !(e.matches("a[href]") && /^https?:/.test(e.getAttribute("href")))).map((e) => e.getAttribute("data-k")))], ext};
  });
  const snap = (page) => page.evaluate(() => {
    const m = document.getElementById("main");
    let h = 0; const t = (m ? m.innerHTML : "") + "|" + document.title + "|" + (document.getElementById("toasts") || {innerHTML: ""}).innerHTML + "|" + (document.getElementById("rail") || {innerHTML: ""}).innerHTML;
    for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) | 0;
    const ae = document.activeElement;
    return {h, hash: location.hash, dialogs: [...document.querySelectorAll("dialog")].filter((d) => d.open).length, calls: (window.__calls || []).length,
      opened: [...document.querySelectorAll("details[open]")].length, scroll: Math.round(scrollY), focus: ae ? ae.id || ae.getAttribute("data-k") || ae.tagName : ""};
  });
  for (const id of a.sections || SECTIONS) {
    const first = await open({html: a.html, viewport: a.viewport, fake: a.fake, clock: a.clock});
    await goto(first.page, id);
    const {keys, ext} = await keysOn(first.page);
    for (const [k, href] of ext) { try { const u = new URL(href); if (!u.hostname.includes(".")) out.badLinks.push([id, k, href]); } catch (e) { out.badLinks.push([id, k, href]); } }
    await first.ctx.close();
    out.perSection[id] = keys.length;
    for (const k of keys.slice(0, a.limit || 80)) {
      const o = await open({html: a.html, viewport: a.viewport, fake: a.fake, clock: a.clock});
      const {page} = o;
      await goto(page, id);
      // A choice drawn as a label is tapped on its label, as a person does; a file picker
      // opening is something happening.
      let el = page.locator('#main [data-k="' + k + '"]').first();
      if (await el.evaluate((e) => e.matches("input") && !!e.closest("label"))) el = page.locator('#main label:has([data-k="' + k + '"])').first();
      let chose = false;
      page.on("filechooser", () => { chose = true; });
      const before = await snap(page);
      try {
        // Found again once if the page drew it afresh between finding it and tapping it, as a
        // person's tap would land on the new one (Firefox under load, 2026-10-29).
        try { await el.scrollIntoViewIfNeeded({timeout: 2000}); }
        catch (e) { if (!/not attached|detached/i.test(String(e.message || e))) throw e; await turn(page, 3); el = page.locator('#main [data-k="' + k + '"]').first(); await el.scrollIntoViewIfNeeded({timeout: 2000}); }
        const b2 = await snap(page);
        await el.click({timeout: 3000});
        await turn(page, 5);
        const after = await snap(page);
        // Focus counts only where it moved somewhere else (an empty Send puts it in the box);
        // the tapped control taking focus itself is not something happening.
        const moved = chose || after.h !== b2.h || after.hash !== b2.hash || after.dialogs !== b2.dialogs || after.calls !== b2.calls || after.opened !== b2.opened || (after.focus !== b2.focus && after.focus !== k && after.focus !== "BODY");
        if (!moved) out.dead.push([id, k]);
        void before;
      } catch (e) { out.unclickable.push([id, k, String(e.message || e).split("\n")[0].slice(0, 120)]); }
      if (o.errors.length) out.errors.push([id, k, o.errors.slice(0, 2)]);
      out.tapped++;
      await o.ctx.close();
    }
  }
  return out;
};

// Every status pill on every screen, with its tone: a status always reads as a word a person
// uses (never "not_contacted") and carries a colour (the maintainer, 2026-10-29: "make sure
// all statuses work").
S.statuses = async (a) => {
  const o = await open({html: a.html, viewport: a.viewport, clock: a.clock, seed: a.seed});
  const {page} = o;
  const out = {words: [], errors: []};
  for (const id of a.sections || SECTIONS) {
    await goto(page, id);
    const got = await page.evaluate(() => [...document.querySelectorAll("#main .state-word")].map((e) => ({
      text: e.textContent.trim(), tone: ([...e.classList].find((c) => c.startsWith("tone-")) || "").replace("tone-", ""),
      bg: getComputedStyle(e).backgroundColor, color: getComputedStyle(e).color})));
    for (const w of got) out.words.push(Object.assign({section: id}, w));
  }
  out.errors = o.errors;
  await o.ctx.close();
  return out;
};

// The page's design language, measured on every screen (templates/app/DESIGN.md): one "?" a
// card at most; no x on a card (the bin is the one way to put something away); no line drawn
// down the side of anything; and every live item a person might not want carries the bin.
S.design = async (a) => {
  const o = await open({html: a.html, viewport: a.viewport, clock: a.clock, scheme: a.scheme});
  const {page} = o;
  const out = {sections: {}, errors: []};
  for (const id of a.sections || SECTIONS) {
    await goto(page, id);
    await page.$$eval("details.band-more:not([open])", (ds) => ds.forEach((d) => { d.open = true; }));
    await turn(page, 2);
    out.sections[id] = await page.evaluate(() => {
      const vis = (e) => e.getClientRects().length > 0 && e.checkVisibility({visibilityProperty: true}) && !e.closest("details:not([open]) > :not(summary)");
      const name = (c) => (c.getAttribute("data-item") || (c.querySelector("h3, .card-title") || {}).textContent || c.className).toString().trim().slice(0, 40);
      const cards = [...document.querySelectorAll("#main .card, #main .wave-row")].filter(vis);
      const manyQ = cards.filter((c) => [...c.querySelectorAll(".q")].filter(vis).length > 1).map(name);
      const xPath = "M7 7l10 10M17 7L7 17";
      const xs = [...document.querySelectorAll("#main svg path")].filter((p) => p.getAttribute("d") === xPath && vis(p)).map((p) => name(p.closest(".card, li, section") || p));
      const side = [...document.querySelectorAll("#main *")].filter(vis).filter((e) => {
        if (e.matches("input, textarea, select, blockquote, .prep-quote, .field.has-error, .tab, .side-list a")) return false;
        const cs = getComputedStyle(e);
        const w = parseFloat(cs.borderLeftWidth) || 0;
        return w >= 2 && cs.borderLeftStyle !== "none" && w > (parseFloat(cs.borderRightWidth) || 0) && cs.borderLeftColor !== "rgba(0, 0, 0, 0)";
      }).map((e) => e.tagName.toLowerCase() + "." + [...e.classList].join("."));
      const needBin = [...document.querySelectorAll("#main .card.job:not(.is-marked):not(.st-dismissed):not(.st-applied), #main .card.app:not(.st-applied):not(.st-not_applying):not(.quiet-card), #main .card.msg:not(.is-marked), #main li.person, #main .card.interview, #main .card.app-record, #main .wave-row")]
        .filter(vis).filter((c) => !c.querySelector('[data-k^="bin:"], [data-k^="dbin:"], [data-k^="mbin:"], [data-k^="pbin:"], [data-k^="ivbin:"], [data-k^="recbin:"], [data-k^="wbin:"]'))
        .filter((c) => !c.matches(".card.app") || !c.querySelector(".meta") || !/Made for|For the portal/.test(c.textContent))
        .map(name);
      return {manyQ, xs, side: [...new Set(side)], needBin};
    });
  }
  out.errors = o.errors;
  await o.ctx.close();
  return out;
};

// Every screen, counted against the budgets.
S.budget = async (a) => {
  const o = await open({html: a.html, viewport: a.viewport, scheme: a.scheme});
  const {page} = o;
  const out = {};
  for (const id of a.sections || SECTIONS) {
    await goto(page, id);
    await page.evaluate(() => window.scrollTo(0, 0));
    out[id] = await page.evaluate(budgetProbe);
  }
  out.errors = o.errors;
  await o.ctx.close();
  return out;
};

S.motion = async (a) => {
  const r = {};
  for (const m of ["reduce", "no-preference"]) {
    const o = await open({html: a.html, reducedMotion: m, hash: "work", seed: {"work/search~1": runningDoc({asked_at: new Date().toISOString(), stage_at: new Date().toISOString()})}});
    r[m] = await o.page.evaluate(() => { const s = document.querySelector(".work-card .spin"); const f = document.querySelector(".work-card .fill"); return {spin: s ? getComputedStyle(s).animationName : null, fill: f ? getComputedStyle(f).transitionDuration : null}; });
    await o.ctx.close();
  }
  return r;
};

S.theme = async (a) => {
  const r = {};
  for (const scheme of ["light", "dark"]) {
    const o = await open({html: a.html, scheme, viewport: a.viewport});
    r[scheme] = await o.page.evaluate(() => ({bg: getComputedStyle(document.body).backgroundColor, ink: getComputedStyle(document.body).color, scheme: getComputedStyle(document.documentElement).colorScheme}));
    await o.page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), scheme === "dark" ? "light" : "dark");
    r[scheme + "_flipped"] = await o.page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    await o.ctx.close();
  }
  return r;
};

S.a11y = async (a) => {
  const o = await open({html: a.html, scheme: a.scheme, viewport: a.viewport, look: a.look, hostTheme: a.hostTheme,
    seed: {"work/search~1": runningDoc({asked_at: new Date().toISOString(), stage_at: new Date(Date.now() - 100000).toISOString()})}});
  const {page} = o;
  const out = {};
  out.applied = await page.evaluate(() => ({bg: getComputedStyle(document.body).backgroundColor, look: document.documentElement.getAttribute("data-look"), scheme: getComputedStyle(document.documentElement).colorScheme}));
  out.targets = {};
  out.overflow = {};
  for (const id of SECTIONS) {
    await goto(page, id);
    await page.evaluate(() => document.querySelectorAll("#main details, #rail details").forEach((d) => { d.open = true; }));
    out[id] = await page.evaluate(a11yProbe);
    out.overflow[id] = await overflow(page);
    if (a.targets) out.targets[id] = await page.evaluate(targetsProbe);
  }
  await goto(page, "work");
  await page.evaluate(() => document.querySelectorAll("dialog details").forEach((d) => { d.open = true; }));
  out.work = await page.evaluate(a11yProbe);
  if (a.targets) out.targets.work = await page.evaluate(targetsProbe);
  await page.keyboard.press("Escape");
  await turn(page, 3);
  await goto(page, "jobs");
  await page.getByRole("button", {name: /^Draft this/}).first().click();
  await turn(page, 3);
  out.dialog = await page.evaluate(a11yProbe);
  if (a.targets) out.targets.dialog = await page.evaluate(targetsProbe);
  out.errors = o.errors;
  await o.ctx.close();
  return out;
};

// Light or dark in Settings: applied at once, kept for this viewer, taken up by another window.
S.picker = async (a) => {
  const o = await open({html: a.html, hash: "settings", tabs: 2});
  const [p1, p2] = o.pages;
  const r = {before: await p1.evaluate(() => getComputedStyle(document.body).backgroundColor), legends: await T(p1, "#main .look-row .set-name"), choices: await T(p1, "#main .look-row .look-name")};
  await p1.locator("label.look-choice:has(#look-dark)").click();
  await turn(p1, 4);
  r.after = await p1.evaluate(() => ({bg: getComputedStyle(document.body).backgroundColor, look: document.documentElement.getAttribute("data-look"), stored: localStorage.getItem("ljs:look"), scheme: getComputedStyle(document.documentElement).colorScheme}));
  r.actions = o.store.list("actions/");
  await turn(p2, 6);
  r.otherWindow = await p2.evaluate(() => ({bg: getComputedStyle(document.body).backgroundColor, checked: [...document.querySelectorAll(".look-row input:checked")].map((x) => x.value)}));
  await p1.reload();
  await settle(p1);
  // Back to Settings, where the look is chosen: the Firefox driver does not report a reload
  // as one, so the page opens on its first section (the Everywhere check, 2026-10-29). Where
  // a reload keeps its place is pinned on its own.
  await goto(p1, "settings");
  await p1.waitForSelector("label.look-choice:has(#look-auto)", {timeout: 15000}).catch(() => {});
  await turn(p1, 2);
  r.reloaded = await p1.evaluate(() => ({bg: getComputedStyle(document.body).backgroundColor, checked: [...document.querySelectorAll(".look-row input:checked")].map((x) => x.value)}));
  await p1.locator("label.look-choice:has(#look-auto)").click();
  await turn(p1, 4);
  r.back = await p1.evaluate(() => ({bg: getComputedStyle(document.body).backgroundColor, look: document.documentElement.getAttribute("data-look"), stored: localStorage.getItem("ljs:look")}));
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// The chosen look is on the root before the first paint: no flash of the wrong one.
S.first_paint_look = async (a) => {
  const o = await open({html: a.html, look: {look: "dark"}, watchPaint: true});
  const r = await o.page.evaluate(() => ({paint: window.__paint, look: document.documentElement.getAttribute("data-look"), bg: getComputedStyle(document.body).backgroundColor}));
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// With storage refused the page follows the device, and a choice still works for the visit.
S.no_storage = async (a) => {
  const o = await open({html: a.html, hash: "settings", noStorage: true, scheme: "dark"});
  const r = {bg: await o.page.evaluate(() => getComputedStyle(document.body).backgroundColor), heading: await one(o.page, "#main h2")};
  await o.page.locator("label.look-choice:has(#look-light)").click();
  await turn(o.page, 4);
  r.after = await o.page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// The phone or wide layout is chosen by the stylesheet alone, with no script at all.
S.no_js_layout = async (a) => {
  const r = {};
  for (const [name, viewport] of [["phone", {width: 375, height: 812}], ["wide", {width: 1440, height: 900}]]) {
    const o = await open({html: a.html, viewport, javaScriptEnabled: false});
    r[name] = await o.page.evaluate(() => {
      const shell = document.getElementById("shell");
      const shellHidden = shell.hidden;
      shell.hidden = false;
      const st = (id) => { const c = getComputedStyle(document.getElementById(id)); return {display: c.display, position: c.position}; };
      return {shellHidden, side: st("side"), tabs: st("tabs"), rail: st("rail"), cols: getComputedStyle(shell).gridTemplateColumns.split(" ").length,
        opening: getComputedStyle(document.getElementById("opening")).display,
        noscript: document.querySelector("noscript") ? document.body.innerText.indexOf("needs JavaScript") >= 0 : false, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth};
    });
    await o.ctx.close();
  }
  return r;
};

// A phone's safe areas, simulated: the env() insets replaced by a notched phone's numbers.
S.safe_area = async (a) => {
  const r = {};
  for (const [name, ins] of [["portrait", {top: "47px", bottom: "34px", left: "0px", right: "0px"}], ["landscape", {top: "0px", bottom: "21px", left: "47px", right: "47px"}]]) {
    const replace = [];
    for (const side of ["top", "bottom", "left", "right"]) {
      replace.push(["env(safe-area-inset-" + side + ", 0px)", ins[side]], ["env(safe-area-inset-" + side + ",0px)", ins[side]]);
    }
    const viewport = name === "portrait" ? {width: 375, height: 812} : {width: 740, height: 360};
    const o = await open({html: a.html, viewport, replace, hash: "jobs"});
    r[name] = await o.page.evaluate(() => {
      const px = (el, p) => parseFloat(getComputedStyle(el)[p]);
      const tabs = document.getElementById("tabs");
      const t = tabs.__drawnRect();
      return {tabsPadBottom: px(tabs, "paddingBottom"), tabsBottom: Math.round(t.bottom), vh: window.innerHeight, rootPadTop: px(document.documentElement, "paddingTop"),
        bodyLeft: px(document.body, "paddingLeft"), bodyRight: px(document.body, "paddingRight"), shellPadBottom: px(document.getElementById("shell"), "paddingBottom"),
        tabsHeight: Math.round(t.height), topTop: getComputedStyle(document.getElementById("top")).top, sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth};
    });
    r[name].errors = o.errors;
    await o.ctx.close();
  }
  return r;
};

// Windows high contrast: buttons keep an edge, focus and progress stay visible.
S.forced = async (a) => {
  const o = await open({html: a.html, forcedColors: "active", hash: "jobs", seed: {"work/search~1": runningDoc({asked_at: new Date().toISOString(), stage_at: new Date(Date.now() - 100000).toISOString()})}});
  const {page} = o;
  const c = (sel) => page.evaluate((s) => { const el = document.querySelector(s); if (!el) return null; const st = getComputedStyle(el); return {border: st.borderTopStyle + " " + st.borderTopWidth, bg: st.backgroundColor, outline: st.outlineStyle}; }, sel);
  const r = {button: await c("#main .btn.primary"), quiet: await c("#main .btn.quiet")};
  await page.focus("#main .btn.primary");
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  r.focus = await page.evaluate(() => { const s = getComputedStyle(document.activeElement); return {outline: s.outlineStyle, width: s.outlineWidth}; });
  await goto(page, "work");
  r.bar = await c("dialog .bar");
  r.fill = await c("dialog .fill");
  r.fillWidth = await page.evaluate(() => { const f = document.querySelector("dialog .fill"); return f ? f.__drawnRect().width : 0; });
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

// More contrast when the device asks: secondary text becomes the body ink.
S.more_contrast = async (a) => {
  const r = {};
  for (const contrast of ["no-preference", "more"]) {
    const o = await open({html: a.html, contrast, hash: "jobs"});
    r[contrast] = await o.page.evaluate(() => ({lede: getComputedStyle(document.querySelector("#main .sum-small")).color, ink: getComputedStyle(document.body).color}));
    await o.ctx.close();
  }
  return r;
};

// What the person opened, selected and typed outlives live updates and a reload, in their own tab only.
S.persist = async (a) => {
  const o = await open({html: a.html, hash: "drafts", tabs: 1});
  const {page, store, ctx} = o;
  await openMore(page, "app-ellerwick-insight");
  await page.getByText("Also to copy (4)").click();
  await turn(page, 3);
  // Select the note's words, as a person copying it by hand would.
  await page.evaluate(() => { const el = document.getElementById("out-app-ellerwick-insight"); const r = document.createRange(); r.selectNodeContents(el); const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); });
  store.chat("work/search~9", runningDoc({asked_at: new Date().toISOString(), stage_at: new Date().toISOString()}));
  await turn(page, 8);
  const r = {stillOpen: await page.$eval('details[data-k="det:copy:app-ellerwick-insight"]', (d) => d.open), pill: await one(page, "#pill"),
    selection: await page.evaluate(() => String(window.getSelection()).length)};
  await goto(page, "chat");
  await page.getByLabel("Ask Claude anything").fill("Half a thought about Harbourline");
  await page.waitForTimeout(50);
  await page.reload();
  await settle(page);
  r.afterReload = await page.inputValue("#talk-text");
  const other = await ctx.newPage();
  await other.goto("https://ljs.test/#chat");
  await settle(other);
  r.otherTab = await other.inputValue("#talk-text");
  r.errors = o.errors;
  await ctx.close();
  return r;
};

// The sweep finds what it is meant to: a nameless button, faint text and a repeated id.
S.a11y_selftest = async (a) => {
  const o = await open({html: a.html});
  await o.page.evaluate(() => {
    const box = document.createElement("div");
    box.innerHTML = '<button type="button"></button><p style="color:#ddd;background:#fff">faint words</p><span id="brand">again</span>';
    document.getElementById("main").appendChild(box);
  });
  const r = await o.page.evaluate(a11yProbe);
  await o.ctx.close();
  return r;
};

S.big = async (a) => {
  const o = await open({html: a.html, hash: "jobs", viewport: a.viewport});
  const t0 = Date.now();
  const r = {cards: (await o.page.$$("#main .card.job")).length, overflow: await overflow(o.page)};
  // Over 25 the Filter sheet holds an employer search (LAYOUT_SPEC 4.2).
  await o.page.locator("#main .filter-btn").first().click();
  await turn(o.page, 3);
  r.search = !!(await o.page.$("dialog.filter-sheet input[type=search]"));
  await o.page.keyboard.press("Escape");
  await turn(o.page, 3);
  await menuPick(o.page, "Select several");
  await turn(o.page, 3);
  await o.page.getByLabel(/^Select all/).check();
  await turn(o.page, 4);
  r.bar = await one(o.page, "#main .bulk");
  r.ms = Date.now() - t0;
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

S.view_overlay = async (a) => {
  const o = await open({html: a.html, hash: "jobs", seed: {"view/jobs": {made_at: "2026-10-26T07:00:00Z", data: {round: "r13", made_at: "2026-10-26T07:00:00Z", met: true, summary: "A fresh search: 1 worth a look.",
    rows: [{id: "r13-1", rank: 1, score: 88, band: "strong", company: "Ellerwick Trust", title: "Senior Research Analyst", place: "Salford", remote: "hybrid", pay: {text: "not stated", stated: false}, apply: {url: "https://example.com/jobs/e", status: "open"}, notes: [], status: "new", questions: [], rev: "x"}], filtered: {count: 0, groups: []}}}}});
  const r = {titles: await T(o.page, "#main .card.job h3"), lede: await one(o.page, "#main .summary"), errors: o.errors};
  await o.ctx.close();
  return r;
};

S.settings = async (a) => {
  const o = await open({html: a.html, hash: "settings"});
  const {page, store} = o;
  await openSetting(page, "app_updates");
  await page.getByLabel("By themselves").focus();
  await page.keyboard.press("ArrowDown");
  await turn(page, 2);
  const early = store.list("actions/").length;
  await page.waitForTimeout(700);
  await turn(page, 6);
  if (a.kinds) {
    await page.getByRole("switch", {name: "Let this page reach Claude on your computer while it is open"}).check();
    await turn(page, 6);
    await openSetting(page, "brief_days");
    await page.getByRole("textbox", {name: "Days the brief arrives", exact: true}).fill("Tuesday");
    await page.getByRole("button", {name: "Save Days the brief arrives"}).click();
    await turn(page, 6);
  }
  const r = {early, actions: store.list("actions/").map((p) => store.get(p)), checked: await page.$eval("#set-app_updates-1", (x) => x.checked),
    names: await T(page, "#main .set-name"), text: await one(page, "#main"), errors: o.errors};
  await o.ctx.close();
  return r;
};

S.split = async (a) => {
  // No "Side by side" menu any more (the maintainer, 2026-10-28); an address with two
  // sections still opens both, with one plain way to close the second.
  const o = await open({html: a.html, viewport: {width: 1440, height: 900}, hash: "jobs+contacts"});
  const {page} = o;
  await turn(page, 4);
  const menu = (await page.$$("#toptools summary.menu-btn")).length;
  const r = {menu, cols: (await page.$$("#main.split > .col")).length, headings: await T(page, "#main h2"), hash: await page.evaluate(() => location.hash)};
  await page.getByRole("button", {name: "Close the second column"}).click();
  await turn(page, 4);
  r.after = (await page.$$("#main.split > .col")).length;
  if (a.shot) r.shot = await shot(page, a.shot);
  r.errors = o.errors;
  await o.ctx.close();
  return r;
};

function shotSeed() {
  const runAt = new Date(Date.now() - 200000).toISOString();
  return {"work/search~1": runningDoc({asked_at: runAt, claimed_at: runAt, stage_at: new Date(Date.now() - 90000).toISOString(), steps: [{at: runAt, text: "Searching 4 job sites and 12 employers"}], count: {done: 3, total: 4}}),
    "work/draft~r12-2": runningDoc({kind: "draft", title: "CV and letter: Larkspur Retail, Senior Supply Chain Analyst", status: "queued", asked_at: new Date(Date.now() - 40000).toISOString(), stage: 0, steps: []})};
}
S.shots = async (a) => {
  const files = [];
  const seed = shotSeed();
  for (const s of a.list) {
    const o = await open({html: a.html, viewport: s.viewport, scheme: s.scheme, hash: s.hash, seed: s.seed === false ? {} : seed, fake: s.fake, look: s.look, scale: s.scale});
    if (s.click) { await o.page.getByRole("button", {name: s.click}).first().click(); await turn(o.page, 4); }
    if (s.go) { await o.page.locator('[data-k="side:' + s.go + '"], [data-k="tab:' + s.go + '"]').first().click(); await turn(o.page, 4); }
    if (s.more) await openMore(o.page, s.more);
    files.push(await shot(o.page, (s.dir ? s.dir + "/" : "") + s.name, !!s.full));
    await o.ctx.close();
  }
  return files;
};

// The README's walkthrough: one page, opened once, and a frame before each step with where
// its tap lands (k: a data-k prefix; text: a button's name; any: words on the screen; press: a
// key), so the animation
// shows someone moving through the page.
S.walk = async (a) => {
  const o = await open({html: a.html, viewport: a.viewport, hash: a.hash, seed: shotSeed(), scale: a.scale});
  const out = [];
  for (const [i, st] of a.steps.entries()) {
    const loc = st.k ? o.page.locator('[data-k^="' + st.k + '"]').first() :
      st.text ? o.page.getByRole(st.role || "button", {name: new RegExp("^" + st.text)}).first() :
      st.any ? o.page.locator("#main").getByText(st.any, {exact: true}).first() : null;
    let at = null;
    if (loc) { const b = await loc.boundingBox(); if (b) at = {x: b.x + b.width / 2, y: b.y + b.height / 2}; }
    out.push({file: await shot(o.page, a.name + "-" + String(i).padStart(2, "0"), false), at});
    if (loc) await loc.click();
    if (st.press) await o.page.keyboard.press(st.press);
    await turn(o.page, st.wait || 6);
  }
  out.push({file: await shot(o.page, a.name + "-end", false), at: null});
  await o.ctx.close();
  return out;
};

// ---------------------------------------------------------------- the loop
async function main() {
  browser = await playwright[ENGINE].launch();
  const out = (o) => process.stdout.write(JSON.stringify(o) + "\n");
  out({ready: true, version: browser.version()});
  const rl = readline.createInterface({input: process.stdin});
  let chain = Promise.resolve();
  rl.on("line", (line) => {
    chain = chain.then(async () => {
      let req;
      try { req = JSON.parse(line); } catch (e) { return; }
      try {
        if (!S[req.scenario]) throw new Error("no such scenario: " + req.scenario);
        out({id: req.id, ok: true, result: await S[req.scenario](req.args || {})});
      } catch (e) { out({id: req.id, ok: false, error: String(e && e.stack || e)}); }
    });
  });
  rl.on("close", async () => { await chain; await browser.close(); process.exit(0); });
}
main().catch((e) => { process.stdout.write(JSON.stringify({ready: false, error: String(e && e.stack || e)}) + "\n"); process.exit(1); });
