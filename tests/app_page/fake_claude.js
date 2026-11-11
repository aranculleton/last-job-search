/* A stand-in for the viewer's window.claude, for the page's browser tests.

   The shapes and the behaviour follow the runtime contract's type definitions (0.2.91:
   claude.d.ts, db.d.ts, comments.d.ts, sample.d.ts, downloads.d.ts, user.d.ts, assets.d.ts,
   mcp.d.ts, permissions.d.ts): use(name) resolves a namespace or null, never during the first
   synchronous run, null after ten seconds from a host that never answers, and only for what the
   page declares (DECLARED below, the page's own declaration). The db's documents live in the
   test runner (one store shared by every tab of a test, so two windows can race for one slot);
   each page keeps a replica the runner pushes changes into, and hands it out as the real one
   does: frozen, the same object while it has not changed, the page's own write at once marked
   pending and taken back if the store refuses it. Wherever the fake was kinder than the
   runtime, a page bug passed every test (the frozen prep, 2026-11-11), so a call the contract
   refuses is refused here too, with the contract's own code.
   window.__LJS_FAKE, set by an earlier init script, says what this viewer has. */
(() => {
  const cfg = window.__LJS_FAKE || {};
  const calls = (window.__calls = []);
  // The tap a slow answer outlived (sample `spendTap`): the browser's own activation, read
  // through this, says it is spent until the person's next press.
  {
    const real = navigator.userActivation;
    if (real) {
      try {
        Object.defineProperty(navigator, "userActivation", {configurable: true, get: () => ({
          get isActive() { return !window.__ljsTapSpent && real.isActive; }, get hasBeenActive() { return real.hasBeenActive; }})});
      } catch (e) { /* left as the browser has it */ }
      for (const ev of ["pointerdown", "keydown"]) window.addEventListener(ev, () => { window.__ljsTapSpent = false; }, true);
    }
  }
  if (cfg.noClaude) return;

  // What the page is published with (tools/app_page.py capabilities(), held the same by
  // tests/test_the_page_is_one_safe_document.py): the runtime serves a page only what it
  // declares, keeps its db by these rules and lets it call only these connector tools.
  const DECLARED = /*DECLARED*/{
    "db": {"rules": [{"path": "", "read": "owner", "write": "owner"},
                     {"path": "reach", "read": "owner", "write": "owner"},
                     {"path": "addr", "read": "owner", "write": "owner"}]},
    "user": {},
    "downloads": true,
    "comments": {},
    "sample": {},
    "assets": {},
    "mcp": {"servers": [{"server": "host:claude_browser",
                         "tools": ["navigate", "get_page_text", "read_page", "preview_start"]}]}
  }/*END*/;
  const owner = cfg.owner !== false;
  const ME = "u_test";
  const has = (n) => (!cfg.caps || cfg.caps.indexOf(n) >= 0);
  const later = (v) => Promise.resolve().then(() => v);
  const rpc = (op, args) => window.__ljsStore(op, args);
  const segs = (p) => String(p).split("/");
  const bytes = (s) => new TextEncoder().encode(String(s)).length;
  const fail = (code, message) => ({code, message: message || code});
  // db.d.ts, PATH GRAMMAR: letters, digits and `_ - . ~ : @ +`, never `.` or `..` alone, at most
  // 200 bytes a segment, 1000 bytes and 16 segments a path; a TypeError at once.
  const checkPath = (p, even) => {
    const s = segs(p);
    if (s.some((x) => !/^[A-Za-z0-9_\-.~:@+]+$/.test(x) || x === "." || x === "..")) throw new TypeError("bad path " + p);
    if (s.some((x) => bytes(x) > 200)) throw new TypeError("a segment over 200 bytes in " + p);
    if (s.length > 16 || bytes(p) > 1000) throw new TypeError("a path over 16 segments or 1000 bytes: " + p);
    if ((s.length % 2 === 0) !== even) throw new TypeError("wrong segment count (" + s.length + ") for " + p);
  };

  // ---------------------------------------------------------------- access (db.d.ts ACCESS RULES)
  // The viewer's level: the owner meets every level; anyone else is what the test says
  // (`level`), else a Viewer. A path this viewer may not read reads as not there; a write to it
  // rejects invalid_argument.
  const LEVELS = ["view", "interact", "admin", "owner"];
  const myLevel = owner ? "owner" : (cfg.level || "view");
  const RULES = ((DECLARED.db || {}).rules || []).map((r) => ({path: segs(r.path).filter(Boolean), read: r.read, write: r.write}));
  function levelFor(path, what) {
    const s = segs(path);
    // A viewer's own subtree under data/users is theirs alone (the default {self} rule).
    if (s[0] === "data" && s[1] === "users" && s.length > 2) return s[2] === ME ? "view" : null;
    let got = what === "read" ? "view" : "interact";
    let best = -1;
    for (const r of RULES) {
      if (r.path.length > s.length || r.path.some((x, i) => x !== s[i])) continue;
      if (r.path.length >= best && r[what]) { best = r.path.length; got = r[what]; }
    }
    return got;
  }
  const may = (path, what) => { const need = levelFor(path, what); return need !== null && LEVELS.indexOf(myLevel) >= LEVELS.indexOf(need); };

  // ---------------------------------------------------------------- db replica
  // cache: what the store has confirmed, path -> {data, version}; data frozen all the way down
  // (db.d.ts: "Delivered snapshots and their data() are frozen"). pend: this page's own writes
  // the store has not answered yet, oldest first, shown at once (latency compensation).
  const cache = new Map();
  const pend = [];
  const listeners = new Set();
  let ready = null;
  let revoked = false;
  function deepFreeze(o) {
    if (o && typeof o === "object" && !Object.isFrozen(o)) { for (const k of Object.keys(o)) deepFreeze(o[k]); Object.freeze(o); }
    return o;
  }
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  function viewOf(path) {
    for (let i = pend.length - 1; i >= 0; i--) if (pend[i].path === path) return {data: pend[i].data, pending: true};
    const c = cache.get(path);
    return {data: c ? c.data : null, pending: false};
  }
  // One snapshot object a document, kept while the document and its pending mark stay the same:
  // "a document that didn't change is the same object across deliveries".
  const shots = new Map();
  function snapDoc(path) {
    const v = viewOf(path);
    const data = v.data || undefined;
    const prev = shots.get(path);
    if (prev && prev.data === data && prev.pending === v.pending) return prev.snap;
    const snap = Object.freeze({id: segs(path).pop(), exists: !!data, data: () => data,
      metadata: Object.freeze({fromCache: false, hasPendingWrites: v.pending})});
    shots.set(path, {data, pending: v.pending, snap});
    return snap;
  }
  function parentOf(path) { return segs(path).slice(0, -1).join("/"); }
  const OPS = new Set(["==", "!=", "<", "<=", ">", ">=", "in", "not-in", "array-contains"]);
  // db.d.ts Query: up to 10 filters, `in`/`not-in` arrays of at most 30, one orderBy, a limit
  // of 1 to 1000. Broken, a read rejects and a subscription gets it on its error callback.
  function badQuery(q) {
    if (q.wheres.length > 10) return "more than 10 filters";
    for (const [f, op, v] of q.wheres) {
      if (typeof f !== "string" || !f) return "a filter's field is not a name";
      if (!OPS.has(op)) return "no such operator " + op;
      if ((op === "in" || op === "not-in") && (!Array.isArray(v) || v.length > 30)) return op + " takes an array of at most 30";
    }
    if (q.orders > 1) return "more than one orderBy";
    if (q.order && (typeof q.order[0] !== "string" || !q.order[0] || (q.order[1] !== "asc" && q.order[1] !== "desc"))) return "a bad orderBy";
    if (q.n !== null && !(Number.isInteger(q.n) && q.n >= 1 && q.n <= 1000)) return "a limit outside 1-1000";
    return null;
  }
  function matchDocs(q) {
    const paths = new Set([...cache.keys()].concat(pend.map((p) => p.path)));
    let docs = [...paths].filter((p) => parentOf(p) === q.path).map((p) => snapDoc(p)).filter((d) => d.exists);
    for (const [f, op, v] of q.wheres) {
      docs = docs.filter((d) => {
        const x = d.data()[f];
        switch (op) {
          case "==": return x === v; case "!=": return x !== v; case "<": return x < v; case "<=": return x <= v;
          case ">": return x > v; case ">=": return x >= v; case "in": return v.indexOf(x) >= 0; case "not-in": return v.indexOf(x) < 0;
          case "array-contains": return Array.isArray(x) && x.indexOf(v) >= 0; default: return true;
        }
      });
    }
    if (q.order) {
      const [f, dir] = q.order;
      docs.sort((a, b) => {
        const x = a.data()[f];
        const y = b.data()[f];
        if (x === undefined && y === undefined) return a.id < b.id ? -1 : 1;
        if (x === undefined) return 1;
        if (y === undefined) return -1;
        const c = x < y ? -1 : x > y ? 1 : 0;
        return dir === "desc" ? -c : c;
      });
    } else docs.sort((a, b) => (a.id < b.id ? -1 : 1));
    if (q.n) docs = docs.slice(0, q.n);
    return docs;
  }
  function querySnap(q, docs, prev) {
    // What changed since this listener's last snapshot (the first is all added): removed with
    // the last body it saw, then added and modified in the new order.
    const changes = [];
    const was = new Map((prev || []).map((d, i) => [d.id, {d, i}]));
    const now = new Set(docs.map((d) => d.id));
    for (const [id, o] of was) if (!now.has(id)) changes.push(Object.freeze({type: "removed", doc: o.d, oldIndex: o.i, newIndex: -1}));
    docs.forEach((d, i) => {
      const o = was.get(d.id);
      if (!o) changes.push(Object.freeze({type: "added", doc: d, oldIndex: -1, newIndex: i}));
      else if (o.d !== d) changes.push(Object.freeze({type: "modified", doc: d, oldIndex: o.i, newIndex: i}));
    });
    Object.freeze(changes);
    const pending = pend.some((p) => parentOf(p.path) === q.path);
    return Object.freeze({docs: Object.freeze(docs.slice()), size: docs.length, empty: !docs.length, docChanges: () => changes,
      metadata: Object.freeze({fromCache: false, hasPendingWrites: pending})});
  }
  function deliver(l, first) {
    if (l.dead) return;
    if (l.kind === "doc") {
      const s = snapDoc(l.path);
      if (!first && s === l.prev) return;
      l.prev = s;
      try { l.next(s); } catch (e) { console.error(e); }
      return;
    }
    const docs = matchDocs(l.q);
    const pending = pend.some((p) => parentOf(p.path) === l.q.path);
    if (!first && l.prev && l.prev.length === docs.length && docs.every((d, i) => d === l.prev[i]) && pending === l.pending) return;
    const s = querySnap(l.q, docs, first ? null : l.prev);
    l.prev = docs;
    l.pending = pending;
    try { l.next(s); } catch (e) { console.error(e); }
  }
  function fire() { for (const l of [...listeners]) deliver(l, false); }
  function store(path, data, version) {
    if (!may(path, "read")) { cache.delete(path); return; }
    const cur = cache.get(path);
    if (data === null) { cache.delete(path); return; }
    // The same body again keeps its object: nothing changed for the page.
    cache.set(path, {data: cur && same(cur.data, data) ? cur.data : deepFreeze(data), version});
  }
  function applyChanges(changes) {
    for (const c of changes) {
      const cur = cache.get(c.path);
      if (cur && c.version <= cur.version && c.data !== null) continue;
      store(c.path, c.data, c.version);
    }
    fire();
  }
  window.__ljsPush = applyChanges;
  // A test takes this viewer's access away while the page runs (db.d.ts `revoked`): each live
  // subscription hears it once and dies, and every later call rejects it.
  window.__ljsRevoke = () => {
    revoked = true;
    for (const l of [...listeners]) die(l, fail("revoked", "access was taken away"));
  };
  function die(l, err) {
    if (l.dead) return;
    l.dead = true;
    listeners.delete(l);
    if (typeof l.error === "function") { try { l.error(err); } catch (e) { console.error(e); } }
    else console.error(err);
  }
  // db.d.ts: a body is a plain JSON object, at most 256 KiB serialized and 32 levels deep.
  function badBody(data) {
    if (!data || typeof data !== "object" || Array.isArray(data)) return "the body is not an object";
    let json;
    try { json = JSON.stringify(data); } catch (e) { return "the body is not JSON"; }
    if (bytes(json) > 262144) return "a document over 256 KiB";
    const depth = (v) => (v && typeof v === "object" ? 1 + Math.max(0, ...Object.values(v).map(depth)) : 0);
    if (depth(data) > 32) return "a document over 32 levels deep";
    return null;
  }
  function merge(a, b) {
    const out = Object.assign({}, a);
    for (const k of Object.keys(b)) {
      const v = b[k];
      if (v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" && !Array.isArray(out[k])) out[k] = merge(out[k], v);
      else out[k] = v;
    }
    return out;
  }
  async function write(op, path, data) {
    if (revoked) { calls.push({cap: "db", op, path, failed: true, code: "revoked"}); throw fail("revoked"); }
    if (op !== "delete") { const bad = badBody(data); if (bad) { calls.push({cap: "db", op, path, failed: true, code: "invalid_argument"}); throw fail("invalid_argument", bad); } }
    // A write this viewer's level does not reach (the page's rules: the owner alone).
    if (!may(path, "write")) { calls.push({cap: "db", op, path, failed: true, code: "invalid_argument"}); throw fail("invalid_argument", "not this viewer's to write"); }
    // A write the store refuses is still a write the page tried: a test of the page's silent
    // drops reads every attempt, refused or not. `failWrites` may be changed while a test runs.
    const refuse = cfg.failWrites || (cfg.failDeletes && op === "delete") ||
      (cfg.failFirstWrites && (window.__ljsWriteN = (window.__ljsWriteN || 0) + 1) <= cfg.failFirstWrites);
    // Shown at once, before the store answers (db.d.ts: "Your own writes appear immediately
    // (hasPendingWrites: true until confirmed)"); an update shows only where the page already
    // holds the document, which the store requires.
    const cur = viewOf(path).data;
    const local = op === "delete" ? null : op === "set" ? deepFreeze(JSON.parse(JSON.stringify(data))) : cur ? deepFreeze(merge(cur, JSON.parse(JSON.stringify(data)))) : undefined;
    const mine = local === undefined ? null : {path, data: local};
    if (mine) { pend.push(mine); Promise.resolve().then(fire); }
    const settle = () => { const i = pend.indexOf(mine); if (i >= 0) pend.splice(i, 1); };
    try {
      if (refuse) { calls.push({cap: "db", op, path, failed: true}); await rpcLater(); throw fail("unavailable", "test"); }
      // A store that takes a write and never answers (`hangWrites`): the tap must not wait for ever.
      if (cfg.hangWrites && op === "set") { calls.push({cap: "db", op, path, hung: true}); return await new Promise(() => {}); }
      calls.push({cap: "db", op, path});
      const r = await rpc(op, {path, data});
      if (r && r.error) throw fail(r.error);
      settle();
      if (r && r.changes) applyChanges(r.changes); else fire();
      return r;
    } catch (e) {
      // Refused: the page's own copy goes back to what the store holds.
      settle();
      fire();
      throw e;
    }
  }
  // A refusal comes back from the store, after the write was shown.
  const rpcLater = () => new Promise((r) => setTimeout(r, 0));
  function subscribe(l) {
    const off = () => { l.off = true; l.dead = true; listeners.delete(l); };
    // Access taken away: the new listener hears it once and is dead.
    if (revoked) { Promise.resolve().then(() => { if (!l.off) die(l, fail("revoked")); }); return off; }
    // db.d.ts: at most 64 active subscriptions a view; the 65th rejects on its error callback.
    if (listeners.size >= 64) { Promise.resolve().then(() => { if (!l.off) die(l, fail("resource_exhausted", "more than 64 subscriptions")); }); return off; }
    listeners.add(l);
    const bad = l.kind === "query" ? badQuery(l.q) : null;
    ready.then(() => {
      if (l.dead) return;
      if (bad) { die(l, fail("invalid_argument", bad)); return; }
      deliver(l, true);
      // A feed that fails just after it delivers (`subError`: the collections it names).
      if (l.kind === "query" && (cfg.subError || []).includes(l.q.path)) setTimeout(() => die(l, fail("unavailable", "test")), 50);
    });
    // Idempotent; after it returns the callbacks never fire again, the first one included.
    return off;
  }
  function docRef(path) {
    checkPath(path, true);
    return {
      id: segs(path).pop(), path,
      get: async () => { if (revoked) throw fail("revoked"); await ready; return snapDoc(path); },
      set: async (data) => { await write("set", path, data); },
      update: async (data) => { await write("update", path, data); },
      delete: async () => { await write("delete", path, null); },
      acquire: async (o) => {
        if (cfg.noAcquire) throw fail("capability_removed", "old");
        if (revoked) throw fail("revoked");
        o = o || {};
        if (typeof o.holder !== "string" || !o.holder) throw fail("invalid_argument", "a lease needs its holder");
        if (o.data !== undefined && badBody(o.data)) throw fail("invalid_argument", badBody(o.data));
        if (!may(path, "write")) throw fail("invalid_argument", "not this viewer's to write");
        calls.push({cap: "db", op: "acquire", path});
        // db.d.ts AcquireOptions: absent or 0 is 30 s; clamped to 1 s - 10 min, never refused.
        const ttl = Number(o.ttlMs) > 0 ? Math.min(600000, Math.max(1000, Number(o.ttlMs))) : 30000;
        const r = await rpc("acquire", {path, holder: o.holder, ttlMs: ttl, data: o.data});
        if (r && r.error) throw fail(r.error);
        const {changes, ...out} = r || {};
        if (changes) applyChanges(changes);
        return out;
      },
      onSnapshot: (next, error) => subscribe({kind: "doc", path, next, error}),
      collection: (sub) => colRef(path + "/" + sub),
    };
  }
  function query(q) {
    return {
      where: (f, op, v) => query(Object.assign({}, q, {wheres: q.wheres.concat([[f, op, v]])})),
      orderBy: (f, dir) => query(Object.assign({}, q, {order: [f, dir === undefined ? "asc" : dir], orders: q.orders + 1})),
      limit: (n) => query(Object.assign({}, q, {n})),
      get: async () => {
        if (revoked) throw fail("revoked");
        const bad = badQuery(q);
        if (bad) throw fail("invalid_argument", bad);
        await ready;
        return querySnap(q, matchDocs(q), null);
      },
      onSnapshot: (next, error) => {
        const subs = (window.__subs = window.__subs || {});
        subs[q.path] = (subs[q.path] || 0) + 1;
        return subscribe({kind: "query", q, next, error});
      },
    };
  }
  const mint = () => "d" + Math.random().toString(36).slice(2, 10);
  function colRef(path) {
    checkPath(path, false);
    const q = query({path, wheres: [], order: null, orders: 0, n: null});
    return Object.assign(q, {path, doc: (id) => docRef(path + "/" + (id === undefined || id === null ? mint() : id)),
      add: async (data) => { const r = docRef(path + "/" + mint()); await r.set(data); return r; }});
  }
  const db = Object.freeze({doc: docRef, collection: colRef});

  // ---------------------------------------------------------------- user (user.d.ts)
  // Every read resolves, never rejects. can() answers its four names and false for any other;
  // me() agrees with each accessor of the same name.
  const CAN = new Set(["data.write", "files.write", "assets.write", "people.add"]);
  const user = Object.freeze({
    isOwner: async () => { if (cfg.ownerDelay) await new Promise((r) => setTimeout(r, cfg.ownerDelay)); return owner; },
    canEdit: async () => owner,
    can: async (n) => (CAN.has(n) ? (n === "data.write" ? may("", "write") : owner) : false),
    id: async () => ME,
    me: async () => ({id: ME, name: "", avatarUrl: "data:,", color: "#000", email: null, isOwner: owner, canEdit: owner}),
    profiles: async (ids) => Object.fromEntries([...new Set([].concat(ids))].map((i) => [i, {id: i, name: "", avatarUrl: "data:,", color: "#000", email: null, isMe: i === ME, guest: false}])),
    // Scope "profile" and "email" are not declared: names "", no search, no address.
    name: async () => "", avatarUrl: async () => "data:,", search: async () => [], email: async () => null,
  });

  // ---------------------------------------------------------------- comments (comments.d.ts)
  // Text: not blank, at most 4 KiB, no control characters but newlines and tabs; a target is
  // exactly one of an anchor and a thread. Else `invalid`, before anything else is decided.
  function badText(t) {
    if (typeof t !== "string" || !t.trim()) return "empty text";
    if (bytes(t) > 4096) return "text over 4 KiB";
    if (/[\u0000-\u0008\u000B-\u001F\u007F]/.test(t)) return "a control character in the text";
    return null;
  }
  const isAnchor = (a) => !!a && typeof a === "object" && typeof a.path === "string" && typeof a.x === "number" && typeof a.y === "number";
  let threadN = 0;
  const comments = Object.freeze({
    // Sending to Claude is for editors of the artifact: anyone else can only comment.
    canSendToClaude: async () => cfg.canSend || (owner ? "available" : "writers_only"),
    anchorFor: async (el) => { if (!el || !el.isConnected) throw fail("invalid", "not attached"); return Object.freeze({path: "body", x: 1, y: 1}); },
    // Only from the person's own recent tap (comments.d.ts), as the browser counts it: a ring
    // sent after a wait was refused live, and this fake took it until 4.3 (2026-10-29).
    sendToClaude: async (t) => {
      const ua = navigator.userActivation;
      const active = ua ? ua.isActive : null;
      t = t || {};
      calls.push({cap: "comments", op: "sendToClaude", text: t.text, threadId: t.threadId || null, anchor: !!t.anchor, active});
      const one = (t.anchor != null) !== (t.threadId != null);
      if (badText(t.text) || !one || (t.anchor != null && !isAnchor(t.anchor)) || (t.threadId != null && (typeof t.threadId !== "string" || !t.threadId))) throw fail("invalid", badText(t.text) || "a bad target");
      if (active === false && !cfg.anyTime) throw fail("claude_unavailable", "not from the viewer's own recent gesture");
      if (!owner) throw fail("claude_unavailable", "not an editor of the artifact");
      // A thread that is gone (deleted, or from before the page was published again).
      if (t.threadId && (cfg.deadThreads || []).indexOf(t.threadId) >= 0) throw fail("not_found", "test");
      if (cfg.sendError) throw fail(cfg.sendError, "test");
      return {threadId: t.threadId || "thread" + (++threadN), commentId: "c" + calls.length};
    },
    create: async (o) => { o = o || {}; if (badText(o.text) || !isAnchor(o.anchor)) throw fail("invalid"); return {threadId: "thread" + (++threadN), commentId: "c" + calls.length}; },
    reply: async (id, text) => { if (badText(text) || typeof id !== "string" || !id) throw fail("invalid"); return {commentId: "c" + calls.length}; },
    openComposer: async (target) => {
      const el = target && target.element;
      if (!(el && el.isConnected) && !(target && target.range)) throw fail("invalid", "not a connected element or range");
      return {opened: true};
    },
    resolve: async () => {},
    delete: async () => {},
  });

  // ---------------------------------------------------------------- sample (sample.d.ts)
  const TIERS = new Set(["default", "complex", "quick"]);
  const plain = (o) => !!o && typeof o === "object" && (Object.getPrototypeOf(o) === Object.prototype || Object.getPrototypeOf(o) === null);
  // A malformed call is a page bug the runtime names: `invalid_request`, nothing sent.
  function badCall(input, opts) {
    if (typeof input === "string") { if (!input.trim()) return ["invalid_request", "empty input"]; }
    else if (Array.isArray(input)) {
      if (!input.length) return ["invalid_request", "no turns"];
      for (const t of input) {
        if (!t || (t.role !== "user" && t.role !== "assistant")) return ["invalid_request", "a turn with another role"];
        if (typeof t.content !== "string" || !t.content) return ["invalid_request", "a turn with empty content"];
      }
      if (input[0].role !== "user" || input[input.length - 1].role !== "user") return ["invalid_request", "turns must start and end on a user turn"];
    } else return ["invalid_request", "input is not a string or a list of turns"];
    const size = typeof input === "string" ? bytes(input) : input.reduce((n, t) => n + bytes(t.content), 0);
    if (size > 262144) return ["prompt_too_large", "over 256 KiB of text"];
    if (opts === undefined) return null;
    if (!plain(opts)) return ["invalid_request", "options is not a plain object"];
    if (opts.signal !== undefined && !(opts.signal instanceof AbortSignal)) return ["invalid_request", "signal is not an AbortSignal"];
    if (opts.onText !== undefined && typeof opts.onText !== "function") return ["invalid_request", "onText is not a function"];
    if (opts.modelTier !== undefined && !TIERS.has(opts.modelTier)) return ["invalid_request", "no such modelTier"];
    const c = opts.cache;
    if (c !== undefined && c !== true && c !== false && !(plain(c) && (c.gcTime === undefined || (Number.isFinite(c.gcTime) && c.gcTime > 0)))) return ["invalid_request", "a bad cache"];
    if (opts.tools !== undefined) {
      if (!Array.isArray(opts.tools)) return ["invalid_request", "tools is not an array"];
      const names = new Set();
      for (const t of opts.tools) {
        if (!t || typeof t.name !== "string" || !/^[A-Za-z0-9_-]{1,128}$/.test(t.name) || names.has(t.name)) return ["invalid_request", "a tool's name"];
        names.add(t.name);
        if (typeof t.description !== "string" || !t.description || bytes(t.description) > 1024) return ["invalid_request", "a tool's description"];
        if (t.inputSchema !== undefined && (!plain(t.inputSchema) || t.inputSchema.type !== "object" || bytes(JSON.stringify(t.inputSchema)) > 4096)) return ["invalid_request", "a tool's inputSchema"];
        if (typeof t.execute !== "function") return ["invalid_request", "a tool's execute"];
      }
      if (c !== undefined && c !== false) return ["invalid_request", "cache with tools"];
      if (cfg.sampleNoTools) return ["tools_unavailable", "this view cannot run page tools"];
    }
    // The page does not declare images (DECLARED.sample has no images: true).
    if (opts.images !== undefined && !(DECLARED.sample || {}).images) return ["images_unavailable", "images are not declared"];
    return null;
  }
  // Answers are kept five minutes for a repeat of the same call, unless it says cache: false or
  // carries tools; a kept answer is replayed without asking Claude (sample.d.ts `cache`).
  const kept = new Map();
  function sampleCall(verb, input, opts) {
    opts = opts || {};
    const bad = badCall(input, opts === undefined ? undefined : opts);
    calls.push({cap: "sample", op: "sample", json: verb === "json", input, tools: (Array.isArray(opts.tools) ? opts.tools : []).map((t) => t && t.name), modelTier: opts.modelTier, cache: opts.cache, refused: bad ? bad[0] : undefined});
    const plan = cfg.sample || {};
    const signal = opts.signal;
    return (async () => {
      if (bad) throw fail(bad[0], bad[1]);
      // An aborted signal stays aborted: a call given one is cancelled at once.
      if (signal && signal.aborted) throw fail("cancelled", "stopped");
      const c = opts.cache;
      const key = c === false || opts.tools ? null : JSON.stringify([verb, input, opts.modelTier || "default", opts.model || null, opts.effort || null]);
      const gc = plain(c) && c.gcTime ? Math.min(c.gcTime, 86400000) : 300000;
      const hit = key && !(plain(c) && c.refresh) ? kept.get(key) : null;
      if (hit && Date.now() - hit.at < gc) {
        calls[calls.length - 1].cached = true;
        if (opts.onText) opts.onText({text: hit.r.text, delta: hit.r.text});
        return Object.assign({}, hit.r);
      }
      let stopped = null;
      const stop = new Promise((res, rej) => { if (signal) signal.addEventListener("abort", () => { stopped = fail("cancelled", "stopped"); rej(stopped); }); });
      stop.catch(() => {});
      const run = (async () => {
        // A quick answer slow enough that the tap which asked has stopped counting (the browser
        // keeps a tap live for a few seconds): the next tap of the person's own counts again.
        if (plan.spendTap) window.__ljsTapSpent = true;
        // An answer that has not come yet: it ends only when the page stops it.
        if (plan.hang) await new Promise(() => {});
        if (plan.error) throw {code: plan.error, message: "test", text: plan.partial};
        const results = [];
        const ctl = new AbortController();
        if (signal) signal.addEventListener("abort", () => ctl.abort());
        for (const use of plan.toolCalls || []) {
          const t = (opts.tools || []).find((x) => x.name === use.name);
          if (!t) continue;
          // A tool that throws is an answer to Claude ("Error: <message>"), never a failed call.
          let out;
          try { out = await t.execute(use.input || {}, {signal: ctl.signal}); } catch (e) { out = "Error: " + ((e && e.message) || String(e)); }
          if (stopped) throw stopped;
          results.push({name: use.name, out});
        }
        window.__toolResults = results;
        // A list of replies is answered one a call, the last one repeated.
        const nth = (window.__sampleN = (window.__sampleN || 0) + 1) - 1;
        const text = Array.isArray(plan.replies) ? plan.replies[Math.min(nth, plan.replies.length - 1)]
          : typeof plan.reply === "function" ? plan.reply(input, results) : (plan.reply || "Here is what the page shows.");
        if (!String(text || "").trim()) throw fail("empty_completion", "no text");
        if (stopped) throw stopped;
        if (opts.onText) opts.onText({text, delta: text});
        const r = {text, truncated: false, modelTierApplied: opts.modelTier || "default"};
        if (key) kept.set(key, {at: Date.now(), r});
        return r;
      })();
      return await Promise.race([run, stop]);
    })();
  }
  // sample.json reads the reply tolerantly: the whole of it, else one fenced block, else from
  // the first { or [ to the last } or ]; none parses, it rejects invalid_json with the reply.
  function readJson(text) {
    const tries = [text];
    const fence = /```(?:json)?\s*\n?([\s\S]*?)```/.exec(text);
    if (fence) tries.push(fence[1]);
    const a = text.search(/[{[]/);
    const b = Math.max(text.lastIndexOf("}"), text.lastIndexOf("]"));
    if (a >= 0 && b > a) tries.push(text.slice(a, b + 1));
    for (const t of tries) { try { return {ok: true, value: JSON.parse(t)}; } catch (e) { /* next */ } }
    return {ok: false};
  }
  const sampleFn = (input, opts) => sampleCall("sample", input, opts);
  sampleFn.json = async (input, opts) => {
    const r = await sampleCall("json", input, opts);
    const got = readJson(String(r.text));
    if (!got.ok) throw {code: "invalid_json", message: "no JSON value in the reply", text: r.text};
    return got.value;
  };
  sampleFn.limits = async () => ({maxPromptBytes: 262144, tools: cfg.sampleNoTools ? undefined : {maxCount: 8}});
  const sample = Object.freeze(sampleFn);

  // ---------------------------------------------------------------- downloads (downloads.d.ts)
  const SAVE_EXT = new Set("gif png jpg jpeg webp mp4 webm mov txt json md docx pptx epub csv ttf html svg pdf xlsx zip fig".split(" "));
  let prompting = false;
  const downloads = Object.freeze({
    save: async (req) => {
      req = req || {};
      const d = req.data;
      const name = req.filename;
      const size = d && (d.size !== undefined ? d.size : d.byteLength !== undefined ? d.byteLength : String(d).length);
      // A small file's bytes too, so a test can open what was saved (a calendar's zip). Read
      // before the call hands an ArrayBuffer over.
      let bytesOut = null;
      if (d instanceof Blob && d.size < 65536) { const u = new Uint8Array(await d.arrayBuffer()); let t = ""; for (const x of u) t += String.fromCharCode(x); bytesOut = btoa(t); }
      const ext = typeof name === "string" && /\.([A-Za-z0-9]+)$/.exec(name);
      // One prompt at a time, and only a named, allowed, non-empty file.
      const code = typeof name !== "string" || name.length > 512 || !size ? "bad_request" : !ext || !SAVE_EXT.has(ext[1].toLowerCase()) ? "rejected_extension"
        : prompting ? "rate_limited" : cfg.downloadError || null;
      calls.push({cap: "downloads", op: "save", filename: name, size, blob: d instanceof Blob, bytes: bytesOut, code});
      // An ArrayBuffer is transferred: the page's own is empty after the call.
      if (d instanceof ArrayBuffer && !code) { try { structuredClone(d, {transfer: [d]}); } catch (e) { /* already gone */ } }
      if (code) throw fail(code, "test");
      prompting = true;
      try { await new Promise((r) => setTimeout(r, 0)); } finally { prompting = false; }
      return {status: "saved"};
    },
  });

  // ---------------------------------------------------------------- assets (assets.d.ts)
  // The closed set of types, the size caps, and the id and url a stored file has. An upload
  // is recorded for the test to read.
  const TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml", "video/mp4", "video/webm", "application/pdf",
    "font/woff2", "font/woff", "font/ttf", "font/otf", "text/csv", "text/markdown", "application/json", "text/plain", "text/css", "text/javascript"]);
  const stored = [];
  const assets = Object.freeze({
    upload: async (blob, opts) => {
      if (!(blob instanceof Blob)) throw fail("invalid_request", "not a Blob");
      if (opts !== undefined && !plain(opts)) throw fail("invalid_request", "options is not a plain object");
      const type = (opts && opts.type) || blob.type || "";
      if (!blob.size) throw fail("invalid_request", "an empty file");
      if (!type) throw fail("invalid_request", "no type: pass options.type");
      if (!TYPES.has(type)) throw fail("unsupported_type", "not an accepted type: " + type);
      const cap = type === "image/svg+xml" ? 2 : type === "text/css" || type === "text/javascript" ? 16 : 20;
      if (blob.size > cap * 1048576) throw fail("too_large", "over " + cap + " MiB");
      const n = (window.__ljsAssets || []).length;
      const id = n.toString(16).padStart(32, "a");
      (window.__ljsAssets = window.__ljsAssets || []).push({id, name: blob.name || "", type});
      stored.push({id, url: "/_blob/" + id, contentType: type, sizeBytes: blob.size, createdAt: new Date().toISOString()});
      return {id, url: "/_blob/" + id, sizeBytes: blob.size, contentType: type};
    },
    list: async () => ({assets: stored.map((a) => Object.assign({}, a)),
      usage: {files: stored.length, bytes: stored.reduce((n, a) => n + a.sizeBytes, 0), maxFiles: 1000, maxBytes: 1073741824}}),
    delete: async (ref) => {
      const id = typeof ref === "string" ? ref.replace(/^\/_blob\//, "") : "";
      if (!/^[0-9A-Za-z]{32}$/.test(id)) throw fail("invalid_request", "not an asset id or url");
      const i = stored.findIndex((a) => a.id === id);
      if (i >= 0) stored.splice(i, 1);
      return {deleted: i >= 0};
    },
  });

  // ---------------------------------------------------------------- mcp (mcp.d.ts)
  // The page's one connector is Claude's own browser in the desktop app (host:claude_browser):
  // anywhere else its calls reject server_not_connected and listTools leaves it out; a tool or
  // server the page does not declare rejects not_in_manifest. `cfg.mcp.browser` puts the page
  // in the app (`inApp`), signed in or out (`signedIn`). describeTool rejects for every host:
  // server, and a call missing its address fails like the real tool does. Before 4.3 the fake
  // answered anything, so a page that sent navigate with no address passed every test.
  const B = "host:claude_browser";
  const MANIFEST = new Map(((DECLARED.mcp || {}).servers || []).map((s) => [s.server, s.tools]));
  const br = cfg.mcp && cfg.mcp.browser;
  // A test signs the person in or out between steps.
  window.__ljsBrowser = br || null;
  const browserTool = (tool, input) => {
    if (!br || !br.inApp) throw Object.assign(new Error("not connected"), {code: "server_not_connected", server: B});
    if (br.declined) throw Object.assign(new Error("declined"), {code: "not_in_manifest", server: B});
    if ((tool === "navigate" || tool === "preview_start") && !(input && input.url)) throw Object.assign(new Error("url is required"), {code: "tool_error", server: B});
    if (tool === "preview_start") return {payload: {tabId: 7}};
    // The person closes Claude's browser as a profile starts to load (`closeOnProfile`).
    if (tool === "navigate" && br.closeOnProfile && /\/in\//.test(input.url)) throw Object.assign(new Error("the tab was closed"), {code: "tool_error", server: B});
    if (tool === "navigate") return {payload: {ok: true}};
    if (tool === "get_page_text" || tool === "read_page") {
      // As the real browser gives it (seen live, 2026-10-29): a header naming the page, then
      // its text. A profile shows only its top card until scrolled; its Experience and
      // Education pages show everything. `slowSections` draws each of those late, once.
      const at = String(br.at || "");
      // A tab nothing has been loaded in yet is a blank one, never a LinkedIn page.
      if (!at) return {payload: {text: "Title: New tab\nURL: about:blank\nSource element: <main>\n---\n"}};
      const feed = /linkedin\.com\/(login|feed)/.test(at);
      const section = (/\/details\/(experience|education)\//.exec(at) || [])[1] || (/\/recent-activity\//.test(at) ? "activity" : "");
      if (!feed && !section) br.reads = (br.reads || 0) + 1;
      const head = "Title: LinkedIn\nURL: " + at + "\nSource element: <main>\n---\n";
      if (br.check && !feed && br.reads > br.check) return {payload: {text: head + "Let's do a quick security check\nPress and hold"}};
      const out = !br.signedIn || (br.signOutAfter && !feed && br.reads > br.signOutAfter);
      if (section && br.slowSections && !(br.drawn = br.drawn || {})[at]) { br.drawn[at] = true; return {payload: {text: head + "Profile language\nEnglish\nAbout\nAccessibility"}}; }
      const text = out ? "Sign in\nJoin now\nNew to LinkedIn?" : feed ? "Home | LinkedIn\nStart a post\nMy Network\nMessaging" :
        section === "experience" ? "Experience\nData analyst\nExample Co · Full-time\n2022 - Present · 3 yrs" :
        section === "education" ? "Education\nExample University\nBSc Statistics" :
        section === "activity" ? "All activity\nPosts\nAda Example posted this • 1w\nOur team is growing in Leeds." :
        "Ada Example\n· 2nd\nData analyst at Example Co\nContact info\nMessage\nConnect\nMore";
      return {payload: {text: head + text}};
    }
    return {payload: {ok: true}};
  };
  // A result carries its content blocks beside the payload (mcp.d.ts CallToolResult).
  const result = (r) => Object.assign({content: [{type: "text", text: typeof r.payload === "string" ? r.payload : JSON.stringify(r.payload)}]}, r);
  const mcp = Object.freeze({callTool: async (server, tool, input) => {
    calls.push({cap: "mcp", server, tool, input});
    if (typeof server !== "string" || typeof tool !== "string") throw Object.assign(new Error("server and tool are names"), {code: "bad_request"});
    try { if (input !== undefined) JSON.stringify(input); } catch (e) { throw Object.assign(new Error("input is not JSON"), {code: "bad_request"}); }
    if (!MANIFEST.has(server) || MANIFEST.get(server).indexOf(tool) < 0) throw Object.assign(new Error("not in the manifest"), {code: "not_in_manifest", server});
    if (server === B) {
      // Only the artifact's owner can use host servers for now.
      if (!owner) throw Object.assign(new Error("not connected"), {code: "server_not_connected", server: B});
      // The app's allow prompt still open: the first call is refused, retryable, as seen live.
      if (br && br.askFirst && !br.asked) { br.asked = true; throw Object.assign(new Error("connector access isn't confirmed for this artifact right now"), {code: "upstream_error", retryable: true, retryAfterMs: 200}); }
      if (br && br.inApp && input && input.url) br.at = input.url;
      return result(browserTool(tool, input));
    }
    if (((cfg.mcp || {}).fail || []).indexOf(tool) >= 0) throw Object.assign(new Error("tool_error"), {code: "tool_error", server});
    return result({payload: {ok: true}});
  }, describeTool: async (server, tool) => {
    if (!MANIFEST.has(server) || MANIFEST.get(server).indexOf(tool) < 0) throw Object.assign(new Error("not in the manifest"), {code: "not_in_manifest"});
    if (String(server).startsWith("host:")) throw Object.assign(new Error("no schema"), {code: "bad_request"});
    return {name: tool, description: "", inputSchema: {}};
  }, listTools: async (server) => {
    // In the app, a server the person has not been asked about lists from the manifest alone:
    // its declared tool names, empty descriptions, authStatus unknown. Elsewhere it is left out.
    const all = br && br.inApp && owner ? [{server: B, authStatus: "unknown", tools: MANIFEST.get(B).map((name) => ({name, description: ""}))}] : [];
    return {servers: server ? all.filter((x) => x.server === server) : all};
  }});

  // ---------------------------------------------------------------- permissions (built in)
  const permissions = Object.freeze({
    state: async (name) => {
      const map = Object.fromEntries(Object.keys(DECLARED).filter((n) => NS[n]).map((n) => [n, "granted"]));
      return name === undefined ? map : map[name] || "unavailable";
    },
    request: async (names) => {
      const all = await permissions.state();
      return names === undefined ? all : Object.fromEntries([].concat(names).map((n) => [n, all[n] || "unavailable"]));
    },
    manage: async () => { throw fail("unavailable", "no panel here"); },
  });
  // What this viewer is served: what the page declares and the test grants, less what the
  // platform keeps from someone who cannot edit (assets).
  const NS = {db, user, comments, sample, downloads, assets: owner ? assets : null, mcp};
  for (const n of Object.keys(NS)) if (!(n in DECLARED) || !has(n)) NS[n] = null;

  // What the page copied, kept for the test to read: only Chrome's engine lets a test read
  // the clipboard back (Safari's refuses with NotAllowedError, the Everywhere check,
  // 2026-10-29). The copy itself still goes through as before.
  if (navigator.clipboard && navigator.clipboard.writeText) {
    const write = navigator.clipboard.writeText.bind(navigator.clipboard);
    try { Object.defineProperty(navigator.clipboard, "writeText", {value: (t) => { window.__ljsCopied = String(t); return write(t); }, configurable: true}); } catch (e) { /* ignore */ }
  }
  {
    const exec0 = document.execCommand.bind(document);
    document.execCommand = (cmd, ...rest) => {
      const done = exec0(cmd, ...rest);
      if (cmd === "copy" && done) { const el = document.activeElement; window.__ljsCopied = el && "value" in el && el.selectionEnd > el.selectionStart ? el.value.slice(el.selectionStart, el.selectionEnd) : String(document.getSelection() || ""); }
      return done;
    };
  }
  if (cfg.clipboardDenied && navigator.clipboard) {
    try { Object.defineProperty(navigator.clipboard, "writeText", {value: () => Promise.reject(new Error("denied")), configurable: true}); } catch (e) { /* ignore */ }
    // A frame that refuses the clipboard refuses the old copy command too.
    const exec = document.execCommand.bind(document);
    document.execCommand = (cmd, ...rest) => (cmd === "copy" ? false : exec(cmd, ...rest));
  }
  // claude.d.ts: one promise a capability, the same on every call; null for a name not served;
  // a host that never answers (`hang`: the names it hangs on) resolves null after 10 s.
  const promised = new Map();
  window.claude = Object.freeze({
    use: (name) => {
      if (promised.has(name)) return promised.get(name);
      let p;
      if ((cfg.hang || []).includes(name)) p = new Promise((r) => setTimeout(() => r(null), 10000));
      else if (name === "permissions") p = later(permissions);
      else if (!NS[name]) return later(null);
      else if (name === "db") {
        if (!ready) ready = rpc("dump", {}).then((all) => { for (const [path, d] of all) store(path, d.data, d.version); });
        p = ready.then(() => db);
      } else p = later(NS[name]);
      promised.set(name, p);
      return p;
    },
  });
})();
