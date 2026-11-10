/* The page in parts (tools/app_page.py render_parts) loads its code from small files beside
   it. If one does not arrive (missing on the host, or a republish half done) or throws while
   the page starts, the page never sits blank or half drawn: it says so in one line, and its
   one button asks Claude to put the whole page up again (a republish work item, then the
   doorbell, as the page rings for any work). Written inline, before any code file, and kept
   to plain browser code: the files it guards may be the ones that failed.
   A republish goes up in batches, each carrying the new page, so for the minutes it takes a
   page opened between them finds a file not there yet. That is an update under way, not a
   page that failed: within WAIT of the moment the page was built (render_parts writes it on
   this script as data-built) a missing file is said as one, with no button, and the page
   opens itself again every AGAIN until all of it arrives. After WAIT it is the failure
   above, and a part that arrived and threw is that failure at once. */
(function () {
  "use strict";
  var G = {failed: [], errors: 0, threw: 0, drawn: false, ended: false, late: false, box: null, ready: null};
  window.__ljsGuard = G;
  var me = document.currentScript || document.querySelector("script[data-built]");
  G.built = (me && me.getAttribute("data-built")) || "";
  var WAIT = 15 * 60 * 1000, AGAIN = 45 * 1000;
  var CODE = /(^|\/)code\/(js|css)\//;
  function ours(t) { return !!t && CODE.test(String(t)); }
  function mark(path) { if (path && G.failed.indexOf(path) < 0) G.failed.push(path); }
  function scriptMissing() { return G.failed.some(function (p) { return /\.js$/.test(p); }); }
  // A part that is missing makes the parts after it throw (they share its names), so only
  // a throw while every script so far arrived is a part at fault in itself.
  function threw() { G.errors++; if (!scriptMissing()) G.threw++; show(); }
  window.addEventListener("error", function (e) {
    var t = e.target;
    if (t && t !== window && (t.tagName === "SCRIPT" || t.tagName === "LINK")) {
      var p = t.getAttribute("src") || t.getAttribute("href") || "";
      if (ours(p)) { mark(p); show(); }
      return;
    }
    // Only an error thrown by the page's own code before its first screen is drawn: the
    // host's scripts and a later slip in one tap are not a page that failed to load.
    if (!G.drawn && ours(e.filename)) threw();
  }, true);
  window.addEventListener("unhandledrejection", function (e) {
    var r = e.reason;
    if (!G.drawn && r && ours(r.stack)) threw();
  });
  // After the last code file has run: anything missing shows now (every stylesheet before
  // a script has loaded or failed by the time the script runs).
  G.end = function () {
    G.ended = true;
    var links = document.querySelectorAll("link[rel=stylesheet]");
    for (var i = 0; i < links.length; i++) {
      var h = links[i].getAttribute("href") || "";
      if (ours(h) && !links[i].sheet) mark(h);
    }
    if (G.failed.length || G.errors || !window.LJS) show();
  };
  // The page's own code says its first screen is drawn (or that the page is not this
  // viewer's): from then on an error is the page's own business.
  G.done = function () { G.drawn = true; if (G.box) show(); };

  // How long is left of the update window: the build moment either side of now, so a
  // device clock a little off still waits, and one far off is the failure as before.
  function left() {
    var t = Date.parse(G.built);
    if (!(t > 0)) return 0;
    var ms = t + WAIT - Date.now();
    return ms > 0 && ms < 2 * WAIT ? ms : 0;
  }
  function updating() { return !G.late && !G.threw && G.failed.length > 0 && left() > 0; }
  // Open the page again every AGAIN while the window lasts; a reload that is refused is let
  // go quietly. When the window ends with the files still missing, it is the failure.
  function wait() {
    if (G.until) return;
    G.again = setInterval(function () {
      try { window.location.reload(); } catch (e) { clearInterval(G.again); }
    }, AGAIN);
    G.until = setTimeout(function () { G.late = true; clearInterval(G.again); show(); }, left());
  }

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (text) n.textContent = text;
    return n;
  }
  function iso() { return new Date().toISOString().replace(/\.\d{3}Z$/, "Z"); }
  function use(name) {
    try {
      var c = window.claude;
      if (!c || typeof c.use !== "function") return Promise.resolve(null);
      return Promise.resolve(c.use(name)).then(function (v) { return v || null; }, function () { return null; });
    } catch (e) { return Promise.resolve(null); }
  }
  // What a ring needs, read before the tap: the platform takes a ring only from the
  // person's own recent tap, so nothing slow may come between the tap and the ring.
  function prepare() {
    return Promise.all([use("db"), use("comments")]).then(function (got) {
      var db = got[0], c = got[1], out = {db: db, c: c, can: "none", anchor: null, thread: null, v: 1};
      if (!db || !c) return out;
      var steps = [
        Promise.resolve(c.canSendToClaude()).then(function (x) { out.can = x; }, function () { out.can = "off"; }),
        Promise.resolve(c.anchorFor(G.box)).then(function (x) { out.anchor = x; }, function () { out.anchor = null; }),
        Promise.resolve(db.doc("meta/doorbell").get()).then(function (d) { out.thread = d && d.exists ? (d.data() || {}).thread || null : null; }, function () {}),
        Promise.resolve(db.doc("work/" + G.id).get()).then(function (d) { var w = d && d.exists ? d.data() || {} : null; out.v = w && Number(w._v) > 0 ? Number(w._v) + 1 : 1; }, function () {}),
      ];
      return Promise.all(steps).then(function () { return out; });
    });
  }
  G.id = "republish~whole";
  function say(text) { if (G.note) G.note.textContent = text; }
  function ask() {
    var btn = G.btn;
    btn.disabled = true;
    say("One moment…");
    G.ready.then(function (r) {
      if (!r.db || !r.c || r.can !== "available" || (!r.thread && !r.anchor)) {
        say("Claude can't be reached from here. Open Claude and ask it to put your page up again.");
        btn.disabled = false;
        return;
      }
      var doc = {kind: "republish", title: "Put your page up again in full", to: "either",
        args: {whole: true, missing: G.failed.slice(0, 20)}, asked_at: iso(),
        status: "queued", stages: [{name: "Building the new page", est_s: 20}, {name: "Putting it up", est_s: 20}],
        stage: 0, stage_at: null, steps: [], claimed_by: null, claimed_at: null, stop_asked: false, attempt: 1, _v: r.v};
      // No asked_from: this button rings for it itself, so the page's own catch-up (which
      // rings what a tab asked for and has not sent) never rings it a second time.
      var text = "[app] [work:" + G.id + "]";
      var send = function (where) {
        try { return Promise.resolve(r.c.sendToClaude(Object.assign({text: text}, where))); } catch (e) { return Promise.reject(e); }
      };
      // Written first, then the doorbell, still inside the tap: the chat reads the request
      // from the page's store, never from the ring.
      Promise.resolve(r.db.doc("work/" + G.id).set(doc)).then(function () {
        var go = r.thread ? send({threadId: r.thread}).catch(function () { return r.anchor ? send({anchor: r.anchor}) : Promise.reject(); }) : send({anchor: r.anchor});
        return go;
      }).then(function () {
        say("Claude has been told. The page opens again by itself once it is back up.");
      }, function () {
        say("That did not reach Claude. Open Claude and ask it to put your page up again.");
        btn.disabled = false;
      });
    });
  }
  // While it is being updated, the line is the page's own, not a plain line on a blank page:
  // its colours and type (the palettes are inline in the page, so they are here whatever file
  // is missing; the device's own colours where they are not) and the small turning ring every
  // running piece of work shows (templates/app/DESIGN.md, Moving parts), still with reduced
  // motion. CSS alone: nothing is polled and nothing is fetched for it.
  var WAIT_CSS = "@keyframes ljs-turn{to{transform:rotate(360deg)}}" +
    "#ljs-broken .ljs-wait{display:inline-block;flex:none;width:16px;height:16px;border-radius:50%;" +
    "border:2.5px solid var(--accent-soft,GrayText);border-top-color:var(--mark,CanvasText);animation:ljs-turn .9s linear infinite}" +
    "@media (prefers-reduced-motion:reduce){#ljs-broken .ljs-wait{animation:none;border-right-color:var(--mark,CanvasText)}}" +
    "@media (forced-colors:active){#ljs-broken .ljs-wait{forced-color-adjust:none;border-color:CanvasText;border-top-color:Highlight}}";
  // The box's colours: the page's own while it waits, the device's own for the failure, whose
  // button is drawn in them.
  function look(own) {
    var s = G.box.style;
    s.background = own ? "var(--surface, Canvas)" : "Canvas";
    s.color = own ? "var(--ink, CanvasText)" : "CanvasText";
    s.borderBottomColor = own ? "var(--line, GrayText)" : "GrayText";
    s.fontFamily = own ? "var(--font-ui, system-ui, -apple-system, sans-serif)" : "system-ui, -apple-system, sans-serif";
  }
  function waiting() {
    look(true);
    if (!document.getElementById("ljs-wait-style")) {
      var st = el("style", {id: "ljs-wait-style"});
      st.textContent = WAIT_CSS;
      (document.head || document.documentElement).appendChild(st);
    }
    if (!G.spin) {
      G.spin = el("span", {"class": "ljs-wait", "aria-hidden": "true"});
      G.box.insertBefore(G.spin, G.line);
    }
  }
  function show() {
    var body = document.body;
    if (!body) return;
    var broke = G.errors || (G.ended && !window.LJS) || G.failed.some(function (p) { return /\.js$/.test(p); });
    if (!G.box) {
      // Plain colours that follow the device, because the page's own styles may be the part
      // that did not arrive.
      var box = el("div", {id: "ljs-broken", role: "alert",
        style: "position:fixed;inset:0 0 auto 0;z-index:2147483647;display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;" +
          "padding:14px max(16px,env(safe-area-inset-right,0px)) 14px max(16px,env(safe-area-inset-left,0px));" +
          "padding-top:calc(14px + env(safe-area-inset-top,0px));background:Canvas;color:CanvasText;" +
          "border-bottom:1px solid GrayText;font:16px/1.4 system-ui,-apple-system,sans-serif"});
      var line = el("span", {});
      box.appendChild(line);
      var note = el("span", {role: "status"});
      box.appendChild(note);
      G.box = box; G.line = line; G.note = note;
      body.insertBefore(box, body.firstChild);
    }
    if (G.btn) {
      // Already the failure, with its button: it stays so.
    } else if (updating()) {
      G.box.setAttribute("data-state", "updating");
      G.line.textContent = "Your page is being updated. It will be ready in a moment.";
      waiting();
      wait();
    } else {
      if (G.spin) { G.spin.remove(); G.spin = null; look(false); }
      clearInterval(G.again);
      clearTimeout(G.until);
      G.box.setAttribute("data-state", "failed");
      G.line.textContent = "Your page did not load fully.";
      var btn = el("button", {type: "button", id: "ljs-broken-ask",
        style: "font:inherit;padding:8px 14px;min-height:44px;border-radius:8px;border:1px solid CanvasText;background:CanvasText;color:Canvas;cursor:pointer"},
        "Ask Claude to put it up again");
      btn.addEventListener("click", ask);
      G.box.insertBefore(btn, G.note);
      G.btn = btn;
      G.ready = prepare().catch(function () { return {}; });
    }
    var op = document.getElementById("opening");
    if (op) op.hidden = true;
    // The page's code did not all run: what it drew is not to be trusted, so it goes.
    var shell = document.getElementById("shell");
    if (broke && shell) shell.hidden = true;
  }
  G.show = show;
})();
