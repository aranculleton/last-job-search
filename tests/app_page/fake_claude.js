/* A stand-in for the viewer's window.claude, for the page's browser tests.

   The shapes follow the runtime contract's type definitions (claude.d.ts, db.d.ts,
   comments.d.ts, room.d.ts, sample.d.ts, downloads.d.ts, user.d.ts, assets.d.ts):
   use(name) resolves a namespace or null, never during the first synchronous run. The db's
   documents live in the test runner (one store shared by every tab of a test, so two
   windows can race for one slot); each page keeps a replica the runner pushes changes into.
   window.__LJS_FAKE, set by an earlier init script, says what this viewer has. */
(() => {
  const cfg = window.__LJS_FAKE || {};
  const calls = (window.__calls = []);
  if (cfg.noClaude) return;
  const has = (n) => !cfg.caps || cfg.caps.indexOf(n) >= 0;
  const later = (v) => Promise.resolve().then(() => v);
  const rpc = (op, args) => window.__ljsStore(op, args);
  const segs = (p) => String(p).split("/");
  const checkPath = (p, even) => {
    const s = segs(p);
    if (s.some((x) => !/^[A-Za-z0-9_\-.~:@+]+$/.test(x) || x === "." || x === "..")) throw new TypeError("bad path " + p);
    if ((s.length % 2 === 0) !== even) throw new TypeError("wrong segment count for " + p);
  };

  // ---------------------------------------------------------------- db replica
  const cache = new Map();
  const listeners = new Set();
  let ready = null;
  function snapDoc(path) {
    const d = cache.get(path);
    const id = segs(path).pop();
    return Object.freeze({id, exists: !!d, data: () => (d ? JSON.parse(JSON.stringify(d.data)) : undefined), metadata: {fromCache: false, hasPendingWrites: false}});
  }
  function parentOf(path) { return segs(path).slice(0, -1).join("/"); }
  function evalQuery(q) {
    let docs = [...cache.keys()].filter((p) => parentOf(p) === q.path).map((p) => snapDoc(p));
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
    return {docs, size: docs.length, empty: !docs.length, docChanges: () => docs.map((d, i) => ({type: "added", doc: d, oldIndex: -1, newIndex: i})), metadata: {fromCache: false, hasPendingWrites: false}};
  }
  function key(l) { return l.kind === "doc" ? JSON.stringify(cache.get(l.path) || null) : JSON.stringify(evalQuery(l.q).docs.map((d) => [d.id, d.data()])); }
  function fire(force) {
    for (const l of listeners) {
      const k = key(l);
      if (!force && k === l.last) continue;
      l.last = k;
      try { l.next(l.kind === "doc" ? snapDoc(l.path) : evalQuery(l.q)); } catch (e) { console.error(e); }
    }
  }
  function applyChanges(changes) {
    for (const c of changes) {
      const cur = cache.get(c.path);
      if (cur && c.version <= cur.version && c.data !== null) continue;
      if (c.data === null) cache.delete(c.path); else cache.set(c.path, {data: c.data, version: c.version});
    }
    fire(false);
  }
  window.__ljsPush = applyChanges;
  async function write(op, path, data) {
    if (cfg.failWrites) throw {code: "unavailable", message: "test"};
    calls.push({cap: "db", op, path});
    const r = await rpc(op, {path, data});
    if (r && r.error) throw {code: r.error, message: r.error};
    if (r && r.changes) applyChanges(r.changes);
    return r;
  }
  function docRef(path) {
    checkPath(path, true);
    return {
      id: segs(path).pop(), path,
      get: async () => { await ready; return snapDoc(path); },
      set: async (data) => { await write("set", path, data); },
      update: async (data) => { await write("update", path, data); },
      delete: async () => { await write("delete", path, null); },
      acquire: async (o) => {
        if (cfg.noAcquire) throw {code: "capability_removed", message: "old"};
        calls.push({cap: "db", op: "acquire", path});
        return await rpc("acquire", {path, holder: o.holder, ttlMs: o.ttlMs});
      },
      onSnapshot: (next, error) => {
        const l = {kind: "doc", path, next, error, last: undefined};
        listeners.add(l);
        ready.then(() => { l.last = key(l); next(snapDoc(path)); });
        return () => listeners.delete(l);
      },
      collection: (sub) => colRef(path + "/" + sub),
    };
  }
  function query(q) {
    return {
      where: (f, op, v) => query(Object.assign({}, q, {wheres: q.wheres.concat([[f, op, v]])})),
      orderBy: (f, dir) => query(Object.assign({}, q, {order: [f, dir || "asc"]})),
      limit: (n) => query(Object.assign({}, q, {n})),
      get: async () => { await ready; return evalQuery(q); },
      onSnapshot: (next, error) => {
        const l = {kind: "query", q, next, error, last: undefined};
        listeners.add(l);
        ready.then(() => { l.last = key(l); next(evalQuery(q)); });
        return () => listeners.delete(l);
      },
    };
  }
  function colRef(path) {
    checkPath(path, false);
    const q = query({path, wheres: [], order: null, n: 0});
    return Object.assign(q, {path, doc: (id) => docRef(path + "/" + (id || "d" + Math.random().toString(36).slice(2, 10))),
      add: async (data) => { const r = docRef(path + "/d" + Math.random().toString(36).slice(2, 10)); await r.set(data); return r; }});
  }
  const db = Object.freeze({doc: docRef, collection: colRef});

  // ---------------------------------------------------------------- the others
  const user = Object.freeze({
    isOwner: async () => { if (cfg.ownerDelay) await new Promise((r) => setTimeout(r, cfg.ownerDelay)); return cfg.owner !== false; },
    canEdit: async () => cfg.owner !== false,
    can: async () => cfg.owner !== false,
    id: async () => "u_test",
    me: async () => ({id: "u_test", name: "", avatarUrl: "data:,", color: "#000", email: null, isOwner: cfg.owner !== false, canEdit: true}),
    profiles: async (ids) => Object.fromEntries([].concat(ids).map((i) => [i, {id: i, name: "", avatarUrl: "data:,", color: "#000", email: null, isMe: false, guest: false}])),
  });
  let threadN = 0;
  const comments = Object.freeze({
    canSendToClaude: async () => cfg.canSend || "available",
    anchorFor: async (el) => { if (!el || !el.isConnected) throw {code: "invalid", message: "not attached"}; return {path: "body", x: 1, y: 1}; },
    // Only from the person's own recent tap (comments.d.ts), as the browser counts it: a ring
    // sent after a wait was refused live, and this fake took it until 4.3 (2026-10-29).
    sendToClaude: async (t) => {
      const ua = navigator.userActivation;
      const active = ua ? ua.isActive : null;
      calls.push({cap: "comments", op: "sendToClaude", text: t.text, threadId: t.threadId || null, anchor: !!t.anchor, active});
      if (active === false && !cfg.anyTime) throw {code: "claude_unavailable", message: "not from the viewer's own recent gesture"};
      if (cfg.sendError) throw {code: cfg.sendError, message: "test"};
      return {threadId: t.threadId || "thread" + (++threadN), commentId: "c" + calls.length};
    },
    create: async () => ({threadId: "t", commentId: "c"}),
    reply: async () => ({commentId: "c"}),
    openComposer: async () => ({opened: true}),
    resolve: async () => {},
    delete: async () => {},
  });
  const room = Object.freeze({
    canSendToClaudeSession: async () => cfg.roomCan || "no_session",
    sendToClaudeSession: (data, opts) => {
      const ua = navigator.userActivation;
      calls.push({cap: "room", op: "sendToClaudeSession", data, opts, active: ua ? ua.isActive : null});
      return Promise.resolve({to: "pane"});
    },
    emit: async () => {}, on: () => () => {}, presence: async () => {}, peers: () => [], onPeers: () => () => {},
    connected: () => true, onConnection: () => () => {}, join: async () => { throw {code: "not_permitted"}; },
  });
  function sampleFn(input, opts) {
    opts = opts || {};
    calls.push({cap: "sample", op: "sample", input, tools: (opts.tools || []).map((t) => t.name), modelTier: opts.modelTier, cache: opts.cache});
    const plan = cfg.sample || {};
    return (async () => {
      if (plan.error) throw {code: plan.error, message: "test", text: plan.partial};
      const results = [];
      for (const use of plan.toolCalls || []) {
        const t = (opts.tools || []).find((x) => x.name === use.name);
        if (t) results.push({name: use.name, out: await t.execute(use.input || {}, {signal: new AbortController().signal})});
      }
      window.__toolResults = results;
      // A list of replies is answered one a call, the last one repeated.
      const nth = (window.__sampleN = (window.__sampleN || 0) + 1) - 1;
      const text = Array.isArray(plan.replies) ? plan.replies[Math.min(nth, plan.replies.length - 1)]
        : typeof plan.reply === "function" ? plan.reply(input, results) : (plan.reply || "Here is what the page shows.");
      if (opts.onText) opts.onText({text, delta: text});
      return {text, truncated: false, modelTierApplied: opts.modelTier || "default"};
    })();
  }
  sampleFn.json = async (input, opts) => JSON.parse((await sampleFn(input, opts)).text);
  sampleFn.limits = async () => ({maxPromptBytes: 262144, tools: cfg.sampleNoTools ? undefined : {maxCount: 8}});
  const sample = Object.freeze(sampleFn);
  const downloads = Object.freeze({
    save: async (req) => {
      const d = req.data;
      const size = d && (d.size !== undefined ? d.size : d.byteLength !== undefined ? d.byteLength : String(d).length);
      calls.push({cap: "downloads", op: "save", filename: req.filename, size, blob: d instanceof Blob});
      if (cfg.downloadError) throw {code: cfg.downloadError, message: "test"};
      return {status: "saved"};
    },
  });
  // An upload is recorded for the test to read, and a type the store does not take is refused
  // the way the real one refuses it.
  const assets = Object.freeze({upload: async (blob) => {
    const type = (blob && blob.type) || "";
    if (/word|msword|officedocument/.test(type)) throw Object.assign(new Error("unsupported"), {code: "unsupported_type"});
    const id = "a".repeat(31) + String((window.__ljsAssets || []).length);
    (window.__ljsAssets = window.__ljsAssets || []).push({id, name: (blob && blob.name) || "", type});
    return {id, url: "/_blob/" + id, sizeBytes: (blob && blob.size) || 0, contentType: type};
  }, list: async () => ({assets: [], usage: {}}), delete: async () => {}});
  // Claude's own connectors, for the page waking its helper chat: only when a test gives
  // `cfg.mcp` ({fail: [tool names that reject]}), so every other test sees none.
  // Claude's own browser in the desktop app (host:claude_browser), as its contract has it
  // (mcp.d.ts): it is listed only inside the app (`browser.inApp`), describeTool rejects for
  // every host: server, and a call missing its address fails like the real tool does. Signed
  // in or out is `browser.signedIn`. Before 4.3 the fake answered anything, so a page that
  // sent navigate with no address passed every test (2026-10-29).
  const B = "host:claude_browser";
  const br = cfg.mcp && cfg.mcp.browser;
  // A test signs the person in or out between steps.
  window.__ljsBrowser = br || null;
  const browserTool = (tool, input) => {
    if (!br || !br.inApp) throw Object.assign(new Error("not connected"), {code: "server_not_connected"});
    if (br.declined) throw Object.assign(new Error("declined"), {code: "not_in_manifest"});
    if ((tool === "navigate" || tool === "preview_start") && !(input && input.url)) throw Object.assign(new Error("url is required"), {code: "tool_error"});
    if (tool === "preview_start") return {payload: {tabId: 7}};
    if (tool === "navigate") return {payload: {ok: true}};
    if (tool === "get_page_text" || tool === "read_page") {
      // As the real browser gives it (seen live, 2026-10-29): a header naming the page, then
      // its text. A profile shows only its top card until scrolled; its Experience and
      // Education pages show everything. `slowSections` draws each of those late, once.
      const at = String(br.at || "");
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
        section === "activity" ? "All activity\nPosts\nAda Example posted this \u2022 1w\nOur team is growing in Leeds." :
        "Ada Example\n· 2nd\nData analyst at Example Co\nContact info\nMessage\nConnect\nMore";
      return {payload: {text: head + text}};
    }
    return {payload: {ok: true}};
  };
  const mcp = cfg.mcp ? Object.freeze({callTool: async (server, tool, input) => {
    calls.push({cap: "mcp", server, tool, input});
    if (server === B) {
      // The app's allow prompt still open: the first call is refused, retryable, as seen live.
      if (br && br.askFirst && !br.asked) { br.asked = true; throw Object.assign(new Error("connector access isn't confirmed for this artifact right now"), {code: "upstream_error", retryable: true, retryAfterMs: 200}); }
      if (input && input.url) br.at = input.url;
      return browserTool(tool, input);
    }
    if ((cfg.mcp.fail || []).indexOf(tool) >= 0) throw Object.assign(new Error("tool_error"), {code: "tool_error"});
    if (tool === "list_environments") return {payload: {environments: [{environment_id: "env_test1", kind: "anthropic_cloud"}]}};
    return {payload: {ok: true}};
  }, describeTool: async (server, tool) => {
    if (String(server).startsWith("host:")) throw Object.assign(new Error("no schema"), {code: "bad_request"});
    return {name: tool, description: "", inputSchema: {}};
  }, listTools: async (server) => {
    const all = br && br.inApp ? [{server: B, authStatus: "unknown", tools: [{name: "navigate", description: ""}]}] : [];
    return {servers: server ? all.filter((x) => x.server === server) : all};
  }}) : null;
  const NS = {db, user, comments, room, sample, downloads, assets, mcp};

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
  window.claude = Object.freeze({
    use: (name) => {
      if (!has(name) || !NS[name]) return later(null);
      if (name === "db") {
        if (!ready) ready = rpc("dump", {}).then((all) => { for (const [p, d] of all) cache.set(p, d); });
        return ready.then(() => db);
      }
      return later(NS[name]);
    },
  });
})();
