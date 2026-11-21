"use strict";
/* Live view of published benchmark runs. Plain GETs only; every piece of run text goes in with textContent. */
(function () {
  var params = new URLSearchParams(location.search);
  var cfg = window.LIVE_CONFIG || {};
  var BASE = (function () {
    var b = params.get("data") || cfg.base || "./data";
    if (!/^(https:\/\/|http:\/\/localhost|http:\/\/127\.0\.0\.1|\.\/|\/)/.test(b)) b = "./data";
    return b.replace(/\/+$/, "");
  })();
  var POLL_MS = 15000, IDLE_POLL_MS = 120000;

  var STATUS = {
    passed: "passed", benchmark_failed: "no flag", infra_error: "infra error", interrupted: "interrupted",
    running: "running", stalled: "stalled", pending: "pending"
  };
  var STATUS_COLOR = {
    passed: "var(--pass)", benchmark_failed: "var(--fail)", infra_error: "var(--warn)", interrupted: "var(--skip)",
    running: "var(--run)", stalled: "var(--warn)", pending: "var(--faint)"
  };
  var STATUS_ORDER = ["passed", "benchmark_failed", "infra_error", "interrupted", "running", "stalled", "pending"];
  var BLOCKERS = {
    no_working_trigger: "never got a working trigger",
    primitive_not_escalated: "got a primitive, never escalated it",
    reached_target_exploit_failed: "reached the target, exploit failed",
    stalled_or_few_calls: "stalled or few calls",
    gave_up_early: "gave up early",
    other: "other / unclear"
  };
  var VIEWS = [["overview", "Overview"], ["runs", "Runs"], ["observations", "Observations"], ["about", "About"]];

  var S = { studies: null, study: null, idx: null, sum: null, notes: undefined, analyses: null, runCache: {}, ok: true, lastOk: 0, timer: null, filter: { status: "", family: "", q: "" }, sort: { k: "started_at", dir: 1 } };
  var app = document.getElementById("app");

  /* ---- tiny DOM helper ---- */
  function h(tag, attrs) {
    var el = document.createElement(tag);
    if (attrs) for (var k in attrs) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v);
    }
    for (var i = 2; i < arguments.length; i++) add(el, arguments[i]);
    return el;
  }
  function add(el, c) {
    if (c == null || c === false) return;
    if (Array.isArray(c)) { c.forEach(function (x) { add(el, x); }); return; }
    el.appendChild(typeof c === "object" ? c : document.createTextNode(String(c)));
  }
  function svg(tag, attrs) {
    var el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (var k in attrs || {}) el.setAttribute(k, attrs[k]);
    for (var i = 2; i < arguments.length; i++) if (arguments[i]) el.appendChild(arguments[i]);
    return el;
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  /* ---- formatting ---- */
  function n0(x) { return x == null ? "–" : Math.round(x).toLocaleString("en-US"); }
  function usd(x) { return x == null ? "–" : "$" + Number(x).toFixed(2); }
  function big(x) { if (x == null) return "–"; if (x >= 1e9) return (x / 1e9).toFixed(2) + " B"; if (x >= 1e6) return (x / 1e6).toFixed(1) + " M"; if (x >= 1e3) return (x / 1e3).toFixed(1) + " k"; return String(Math.round(x)); }
  function dur(s) {
    if (s == null) return "–"; s = Math.round(s);
    var hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
    return hh ? hh + " h " + mm + " m" : mm ? mm + " m " + ss + " s" : ss + " s";
  }
  function when(iso) { if (!iso) return "–"; return iso.replace("T", " ").replace("Z", " UTC").slice(0, 20) + (iso.endsWith("Z") ? "UTC" : ""); }
  function ago(iso) { if (!iso) return "–"; var s = (Date.now() - Date.parse(iso)) / 1000; return s < 90 ? Math.round(s) + " s ago" : s < 5400 ? Math.round(s / 60) + " min ago" : (s / 3600).toFixed(1) + " h ago"; }
  function badge(st) { return h("span", { class: "badge s-" + st, text: STATUS[st] || st }); }
  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
  function bname(b) { return { exploitgym: "ExploitGym", cybergym: "CyberGym" }[b] || cap(b); }
  function stat(k, v, s) { return h("div", { class: "stat" }, h("div", { class: "k", text: k }), h("div", { class: "v", text: v }), s ? h("div", { class: "s", text: s }) : null); }
  function fact(k, v) { return h("div", { class: "fact" }, h("div", { class: "k", text: k }), h("div", { class: "v", text: v == null ? "–" : String(v) })); }

  /* ---- data ---- */
  function getJSON(path) {
    return fetch(BASE + "/" + path).then(function (r) { if (!r.ok) { var e = new Error(path + " " + r.status); e.status = r.status; throw e; } return r.json(); });
  }
  function getText(path) {
    return fetch(BASE + "/" + path).then(function (r) { if (!r.ok) throw new Error(path + " " + r.status); return r.text(); });
  }
  function studyDir() { return S.study.benchmark + "/" + S.study.name + "/"; }
  function setPill(kind, text) {
    var p = document.getElementById("pill"); p.className = "pill " + kind; document.getElementById("pill-text").textContent = text;
  }

  function loadStudies() {
    return getJSON("index.json").then(function (d) { S.studies = d.studies || []; });
  }
  function loadStudy() {
    var dir = studyDir();
    return Promise.all([getJSON(dir + "index.json"), getJSON(dir + "summary.json")]).then(function (r) {
      S.idx = r[0]; S.sum = r[1]; S.ok = true; S.lastOk = Date.now();
    });
  }
  function refreshPill() {
    if (!S.ok) { setPill("warn", "reconnecting…"); return; }
    var st = S.idx && S.idx.state;
    setPill(st === "active" ? "live" : "", st === "active" ? "live" : st === "incomplete" ? "unfinished" : "complete");
  }
  function schedule() {
    clearTimeout(S.timer);
    var active = S.idx && S.idx.state === "active";
    S.timer = setTimeout(poll, S.ok ? (active ? POLL_MS : IDLE_POLL_MS) : 8000);
  }
  function poll() {
    if (document.hidden) { schedule(); return; }
    if (!S.study) { schedule(); return; }
    loadStudy().then(function () { refreshPill(); renderNav(); softRender(); }, function () { S.ok = false; refreshPill(); }).then(schedule);
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { clearTimeout(S.timer); S.timer = setTimeout(poll, 300); } });

  /* ---- routing: #<benchmark>/<study>/<view>[/<run id>] ---- */
  function route() {
    var p = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
    var r = { bench: p[0], study: p[1], view: p[2] || "overview", run: p[3] };
    if (r.view !== "overview" && r.view !== "runs" && r.view !== "observations" && r.view !== "about" && r.view !== "run") r.view = "overview";
    return r;
  }
  function go(view, run) { location.hash = "#" + S.study.benchmark + "/" + S.study.name + "/" + view + (run ? "/" + run : ""); }
  function href(view, run) { return "#" + S.study.benchmark + "/" + S.study.name + "/" + view + (run ? "/" + run : ""); }

  function onRoute() {
    var r = route();
    if (!S.studies) return;
    var s = S.studies.filter(function (x) { return x.benchmark === r.bench && x.name === r.study; })[0];
    if (!s) {
      if (!S.studies.length) { clear(app); app.appendChild(h("p", { class: "muted", text: "No studies published yet." })); return; }
      s = S.studies[0]; S.study = s; location.replace(href("overview")); return;
    }
    var changed = !S.study || S.study.name !== s.name || S.study.benchmark !== s.benchmark;
    S.study = s;
    STATUS.benchmark_failed = s.benchmark === "exploitgym" ? "no flag" : "failed";
    if (changed) { S.idx = S.sum = null; S.notes = undefined; S.analyses = null; S.runCache = {}; }
    renderTabs(r);
    if (!S.idx) {
      clear(app); app.appendChild(h("p", { class: "muted", text: "Loading…" }));
      loadStudy().then(function () { refreshPill(); renderNav(); render(); schedule(); }, function () { S.ok = false; refreshPill(); clear(app); app.appendChild(h("p", { class: "err", text: "Could not load this study. Retrying…" })); schedule(); });
      return;
    }
    render();
  }

  function renderTabs(r) {
    var t = document.getElementById("tabs"); clear(t);
    VIEWS.forEach(function (v) {
      t.appendChild(h("a", { href: href(v[0]), class: (r.view === v[0] || (r.view === "run" && v[0] === "runs")) ? "on" : "", text: v[1] }));
    });
  }
  function renderNav() {
    var c = document.getElementById("nav-cells"); clear(c);
    if (!S.sum) return;
    var cs = S.sum.counts_by_status || {}, fin = 0;
    for (var k in cs) if (k !== "running" && k !== "stalled" && k !== "pending") fin += cs[k];
    [["running", String((S.sum.running || 0) + (S.sum.stalled || 0))], ["finished", fin + " / " + S.sum.runs], ["spend", usd(S.sum.totals && S.sum.totals.spend)]].forEach(function (x) {
      c.appendChild(h("div", { class: "cell" }, h("span", { class: "k", text: x[0] }), h("span", { class: "v", text: x[1] })));
    });
    document.getElementById("foot-text").textContent = "Data updated " + ago(S.idx && S.idx.generated_at) + " · refreshed every " + (S.idx && S.idx.state === "active" ? POLL_MS / 1000 : IDLE_POLL_MS / 1000) + " s while the tab is visible";
  }

  /* re-render the current view when data changes, without throwing the reader's place away */
  function softRender() {
    var r = route();
    if (r.view === "run") { refreshRun(); return; }
    var y = window.scrollY; render(); window.scrollTo(0, y);
  }
  function render() {
    var r = route(); renderTabs(r); renderNav(); clear(app);
    var head = h("div", { class: "study-pick" },
      h("select", { id: "study-sel", "aria-label": "Study", onchange: function (e) { var s = S.studies[+e.target.value]; location.hash = "#" + s.benchmark + "/" + s.name + "/" + (r.view === "run" ? "runs" : r.view); } },
        S.studies.map(function (s, i) { return h("option", { value: i, selected: s === S.study ? "" : null, text: bname(s.benchmark) + " · " + s.name + (s.state === "active" ? " (live)" : s.state === "incomplete" ? " (unfinished)" : "") }); })));
    app.appendChild(head);
    var sel = document.getElementById("study-sel"); if (sel) sel.selectedIndex = Math.max(0, S.studies.indexOf(S.study));
    ({ overview: viewOverview, runs: viewRuns, observations: viewObservations, about: viewAbout, run: viewRun })[r.view](r);
  }

  /* ---- charts ---- */
  function histogram(rows, unit, labelFn, height) {
    var W = 520, H = height || 150, pad = { l: 26, r: 6, t: 8, b: 22 }, max = 1;
    rows.forEach(function (x) { if (x.count > max) max = x.count; });
    var bw = (W - pad.l - pad.r) / rows.length;
    var g = svg("svg", { class: "chart", viewBox: "0 0 " + W + " " + H, role: "img", "aria-label": unit + " histogram" });
    [0, .5, 1].forEach(function (f) {
      var y = pad.t + (H - pad.t - pad.b) * (1 - f);
      g.appendChild(svg("line", { x1: pad.l, x2: W - pad.r, y1: y, y2: y }));
      var tx = svg("text", { x: pad.l - 4, y: y + 3, "text-anchor": "end" }); tx.textContent = Math.round(max * f); g.appendChild(tx);
    });
    rows.forEach(function (x, i) {
      var bh = (H - pad.t - pad.b) * (x.count / max), bx = pad.l + i * bw + 2;
      var rect = svg("rect", { class: "b", x: bx, y: H - pad.b - bh, width: Math.max(1, bw - 4), height: bh, rx: 2 });
      var t = svg("title"); t.textContent = labelFn(x) + ": " + x.count + " runs"; rect.appendChild(t); g.appendChild(rect);
      if (i % 2 === 0 || rows.length < 10) { var lb = svg("text", { x: bx + (bw - 4) / 2, y: H - 8, "text-anchor": "middle" }); lb.textContent = labelFn(x, true); g.appendChild(lb); }
    });
    return g;
  }
  function stackBar(counts, order, colors, labels) {
    var total = 0; order.forEach(function (k) { total += counts[k] || 0; });
    var bar = h("div", { class: "bar" }), leg = h("div", { class: "legend" });
    order.forEach(function (k) {
      var c = counts[k] || 0; if (!c) return;
      var sp = h("span", { title: labels[k] + ": " + c }); sp.style.width = (100 * c / total) + "%"; sp.style.background = colors[k]; bar.appendChild(sp);
      var i = h("i"); i.style.background = colors[k]; leg.appendChild(h("span", null, i, labels[k] + " " + c));
    });
    return h("div", null, bar, leg);
  }
  function hbars(rows, max) {
    var m = max || 1; rows.forEach(function (r) { if (r.n > m) m = r.n; });
    return h("div", null, rows.map(function (r) {
      var fill = h("span"); fill.style.width = (100 * r.n / m) + "%"; if (r.color) fill.style.background = r.color;
      return h("div", { class: "hbar" }, h("div", { text: r.label }), h("div", { class: "t" }, fill), h("div", { class: "n", text: r.n }));
    }));
  }

  /* ---- overview ---- */
  function viewOverview() {
    var s = S.sum, idx = S.idx, tot = s.totals || {}, cs = s.counts_by_status || {};
    var passed = cs.passed || 0, finished = 0;
    for (var k in cs) if (["running", "stalled", "pending"].indexOf(k) < 0) finished += cs[k];
    app.appendChild(h("h1", { text: bname(idx.benchmark) + " · " + idx.study }));
    app.appendChild(h("p", { class: "sub", text: "Model " + (idx.model || "unknown") + ". " + s.runs + " tasks in this study, " + finished + " finished" + ((s.running || s.stalled) ? ", " + ((s.running || 0) + (s.stalled || 0)) + " in progress" : "") + ". Updated " + ago(s.generated_at) + "." + (idx.state === "incomplete" ? " No task is running now: the tasks marked stalled or pending did not finish." : "") }));
    app.appendChild(h("div", { class: "stats" },
      stat("Tasks", n0(s.runs), finished + " finished"),
      stat(idx.benchmark === "exploitgym" ? "Flags captured" : "Passed", n0(passed), "of " + finished + " finished" + (idx.benchmark === "exploitgym" ? "" : " (all stages)")),
      stat("In progress", n0((s.running || 0) + (s.stalled || 0)), s.stalled ? s.stalled + " stalled" : "heartbeat fresh"),
      stat("Spend", usd(tot.spend), "model calls only"),
      stat("Model calls", n0(tot.requests)),
      stat("Cached input", big(tot.cache_read_tokens), "tokens read from cache"),
      stat("Output", big(tot.output_tokens), "tokens written")));

    app.appendChild(h("h2", { text: "Outcomes" }));
    app.appendChild(h("div", { class: "card" }, stackBar(cs, STATUS_ORDER, STATUS_COLOR, STATUS)));

    var fams = s.counts_by_family || {}, names = Object.keys(fams), FAM_MAX = 12;
    function famTotal(f) { var t = 0; for (var c in fams[f]) t += fams[f][c]; return t; }
    names.sort(function (a, b) { return famTotal(b) - famTotal(a) || (a < b ? -1 : 1); });
    var rowsF = names.slice(0, FAM_MAX).map(function (f) { return { name: f, c: fams[f] }; });
    if (names.length > FAM_MAX) {
      var rest = {}; names.slice(FAM_MAX).forEach(function (f) { for (var c in fams[f]) rest[c] = (rest[c] || 0) + fams[f][c]; });
      rowsF.push({ name: "other (" + (names.length - FAM_MAX) + " families)", c: rest });
    }
    var cols = STATUS_ORDER.filter(function (k) { return rowsF.some(function (f) { return f.c[k]; }); });
    app.appendChild(h("h2", { text: "By task family" }));
    app.appendChild(h("div", { class: "card tbl-wrap" }, h("table", null,
      h("thead", null, h("tr", null, h("th", { text: "Family" }), cols.map(function (c) { return h("th", { class: "num", text: STATUS[c] }); }), h("th", { class: "num", text: "Total" }))),
      h("tbody", null, rowsF.map(function (f) {
        var t = 0; cols.forEach(function (c) { t += f.c[c] || 0; });
        return h("tr", null, h("td", { text: f.name }), cols.map(function (c) { return h("td", { class: "num", text: f.c[c] || 0 }); }), h("td", { class: "num", text: t }));
      })))));

    var running = idx.runs.filter(function (r) { return r.status === "running" || r.status === "stalled"; });
    if (running.length) {
      app.appendChild(h("h2", { text: "In progress now" }));
      app.appendChild(h("div", { class: "card tbl-wrap" }, h("table", null,
        h("thead", null, h("tr", null, ["Task", "Status", "Started", "Elapsed", "Calls", "Spend"].map(function (x, i) { return h("th", { class: i > 2 ? "num" : "", text: x }); }))),
        h("tbody", null, running.map(function (r) {
          return h("tr", { class: "click", onclick: function () { go("run", r.id); } },
            h("td", { text: r.task }), h("td", null, badge(r.status)), h("td", { text: ago(r.started_at) }),
            h("td", { class: "num", text: dur(r.started_at ? (Date.now() - Date.parse(r.started_at)) / 1000 : null) }),
            h("td", { class: "num", text: n0(r.requests) }), h("td", { class: "num", text: usd(r.spend) }));
        })))));
    }

    app.appendChild(h("div", { class: "grid2" },
      h("div", null, h("h2", { text: "Spend per task" }), h("div", { class: "card" },
        histogram(s.spend_histogram_usd || [], "spend", function (x, short) { return x.to == null ? "$" + x.from + "+" : short ? "$" + x.from : "$" + x.from + "–" + x.to; }),
        h("div", { class: "note", text: "Tasks per dollar bucket. Tasks that never reached the model count in the first bucket." }))),
      h("div", null, h("h2", { text: "Agent time per task" }), h("div", { class: "card" },
        histogram(s.agent_minutes_histogram || [], "minutes", function (x, short) { return short ? String(x.from) : x.from + "–" + x.to + " min"; }),
        h("div", { class: "note", text: "Minutes of agent time, 15-minute buckets. The limit for most studies is 120 minutes." })))));
  }

  /* ---- runs ---- */
  function viewRuns() {
    var rows = S.idx.runs, f = S.filter;
    app.appendChild(h("h1", { text: "Runs" }));
    app.appendChild(h("p", { class: "sub", text: "One row per task. Click a row for the analysis and the full agent trajectory." }));
    var statuses = {}, families = {}; rows.forEach(function (r) { statuses[r.status] = (statuses[r.status] || 0) + 1; families[r.family] = (families[r.family] || 0) + 1; });
    function chipRow(label, key, counts, order) {
      var row = h("div", { class: "chips" }, h("span", { class: "muted", text: label }));
      [["", "all"]].concat(order.filter(function (k) { return counts[k]; }).map(function (k) { return [k, (STATUS[k] || k) + " " + counts[k]]; })).forEach(function (x) {
        row.appendChild(h("button", { class: "chip" + (f[key] === x[0] ? " on" : ""), onclick: function () { f[key] = x[0]; softRender(); } }, x[1]));
      });
      return row;
    }
    app.appendChild(chipRow("Status", "status", statuses, STATUS_ORDER));
    app.appendChild(chipRow("Family", "family", families, Object.keys(families).sort()));
    var q = h("input", { type: "search", placeholder: "Filter by task…", value: f.q, "aria-label": "Filter by task" });
    q.addEventListener("input", function () { f.q = q.value; drawTable(); });
    app.appendChild(h("div", { class: "chips" }, q));
    var holder = h("div", { class: "card tbl-wrap" }); app.appendChild(holder);
    var cols = [["task", "Task"], ["family", "Family"], ["status", "Status"], ["reason", "Reason"], ["started_at", "Started"], ["spend", "Spend", 1], ["requests", "Calls", 1], ["node", "Node"], ["attempt", "Attempt", 1]];
    function drawTable() {
      var list = rows.filter(function (r) { return (!f.status || r.status === f.status) && (!f.family || r.family === f.family) && (!f.q || r.task.toLowerCase().indexOf(f.q.toLowerCase()) >= 0); });
      var k = S.sort.k, d = S.sort.dir;
      list.sort(function (a, b) { var x = a[k], y = b[k]; if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; return (x < y ? -1 : x > y ? 1 : 0) * d; });
      clear(holder);
      holder.appendChild(h("table", null,
        h("thead", null, h("tr", null, cols.map(function (c) {
          return h("th", { class: "sort" + (c[2] ? " num" : ""), onclick: function () { S.sort = { k: c[0], dir: S.sort.k === c[0] ? -S.sort.dir : 1 }; drawTable(); }, text: c[1] + (S.sort.k === c[0] ? (S.sort.dir > 0 ? " ↑" : " ↓") : "") });
        }))),
        h("tbody", null, list.map(function (r) {
          return h("tr", { class: "click", onclick: function () { go("run", r.id); } },
            h("td", { text: r.task }), h("td", { text: r.family }), h("td", null, badge(r.status)), h("td", { class: "muted", text: r.reason || "" }),
            h("td", { text: when(r.started_at) }), h("td", { class: "num", text: usd(r.spend) }), h("td", { class: "num", text: n0(r.requests) }),
            h("td", { text: r.node || "–" }), h("td", { class: "num", text: r.attempt == null ? "–" : r.attempt }));
        }))));
      if (!list.length) holder.appendChild(h("p", { class: "muted", text: "Nothing matches." }));
    }
    drawTable();
  }

  /* ---- observations ---- */
  function loadNotes() {
    if (S.notes !== undefined) return Promise.resolve(S.notes);
    return getJSON(studyDir() + "notes.json").then(function (d) { return (S.notes = d); }, function () { return (S.notes = null); });
  }
  function loadAnalyses() {
    if (S.analyses) return Promise.resolve(S.analyses);
    var ids = S.idx.runs.filter(function (r) { return r.has_analysis; }), out = {}, i = 0;
    function worker() {
      if (i >= ids.length) return Promise.resolve();
      var r = ids[i++];
      return getJSON(studyDir() + "runs/" + r.id + "/analysis.json").then(function (a) { out[r.id] = a; }, function () {}).then(worker);
    }
    var ws = []; for (var j = 0; j < 6; j++) ws.push(worker());
    return Promise.all(ws).then(function () { return (S.analyses = out); });
  }
  function viewObservations() {
    app.appendChild(h("h1", { text: "Observations" }));
    var holder = h("div", null, h("p", { class: "muted", text: "Loading…" })); app.appendChild(holder);
    Promise.all([loadNotes(), loadAnalyses()]).then(function (r) {
      var notes = r[0], an = r[1]; clear(holder);
      if (notes && notes.observations && notes.observations.length) {
        if (notes.summary) holder.appendChild(h("p", { class: "sub", text: notes.summary }));
        holder.appendChild(h("div", { class: "card" }, notes.observations.map(function (o) { return h("div", { class: "obs" }, h("b", { text: o.title }), h("span", { text: o.body })); })));
      } else {
        holder.appendChild(h("p", { class: "sub", text: "No written observations have been published for this study yet. The per-task analyses below are published with the runs." }));
      }
      var ids = Object.keys(an);
      if (!ids.length) return;
      var byId = {}; S.idx.runs.forEach(function (x) { byId[x.id] = x; });
      var cnt = {}, groups = {};
      ids.forEach(function (id) { var b = an[id].blocker || "other"; cnt[b] = (cnt[b] || 0) + 1; (groups[b] = groups[b] || []).push(id); });
      var other = {}; S.idx.runs.forEach(function (x) { if (x.status === "infra_error" || x.status === "interrupted") other[x.status] = (other[x.status] || 0) + 1; });
      var rows = Object.keys(BLOCKERS).filter(function (k) { return cnt[k]; }).map(function (k) { return { label: BLOCKERS[k], n: cnt[k], color: k === "reached_target_exploit_failed" ? "var(--pass)" : k === "no_working_trigger" ? "var(--fail)" : null }; });
      Object.keys(other).forEach(function (k) { rows.push({ label: STATUS[k] + " (not a model result)", n: other[k], color: "var(--skip)" }); });
      holder.appendChild(h("h2", { text: "Why no flag" }));
      holder.appendChild(h("div", { class: "card" }, hbars(rows), h("p", { class: "note", text: "One reason per task, assigned by reading its log. These are judgements, not measurements; a task near a boundary could go either way." })));
      Object.keys(BLOCKERS).filter(function (k) { return groups[k]; }).forEach(function (k) {
        holder.appendChild(h("h3", { text: BLOCKERS[k] + " (" + groups[k].length + ")" }));
        holder.appendChild(h("div", { class: "card" }, groups[k].map(function (id) {
          var a = an[id], r = byId[id] || {};
          return h("div", { class: "obs" }, h("b", null, h("a", { href: href("run", id), text: a.task || r.task })), h("span", { text: a.summary || "" }));
        })));
      });
    });
  }

  /* ---- about ---- */
  function viewAbout() {
    app.appendChild(h("h1", { text: "About this page" }));
    var li = function (t) { return h("li", { text: t }); };
    app.appendChild(h("div", { class: "card" },
      h("p", { text: "This page shows benchmark runs of language-model agents on security tasks. Each task is one agent working alone in a sandbox for a fixed time and spend limit. Task results, the agent's step-by-step log and a short analysis are published here as the runs progress." }),
      h("h3", { text: "Statuses" }),
      h("ul", { class: "plain" }, li("passed: the agent captured the flag or met the benchmark's pass condition."), li("no flag: the run finished and the benchmark scored it as a fail."),
        li("infra error: the run stopped for a reason that is not a model result, for example the provider refused requests."), li("interrupted: the task hit its hard deadline before a result was recorded."),
        li("running: the run is in progress and its heartbeat is fresh."), li("stalled: still marked running but no heartbeat for 10 minutes."), li("pending: queued, not started.")),
      h("h3", { text: "Trajectories" }),
      h("p", { text: "Open a run to read the agent's messages, commands and their output. Long logs are split into parts that load on request; for a run in progress, new parts appear as they are published." }),
      h("h3", { text: "What is left out" }),
      h("p", { text: "Task tokens, API keys, host names and addresses, account identifiers and the exploit flag value are removed before anything is published. Nodes are shown as letters." }),
      h("h3", { text: "Data" }),
      h("p", { class: "note", text: "Each study is a folder with index.json (the run list), summary.json (counts and histograms) and one folder per run. The page reads these files directly and refreshes while it is open." })));
  }

  /* ---- one run ---- */
  var RV = null;
  function viewRun(r) {
    RV = { id: r.run, run: null, manifest: null, loaded: 0, parts: [], holder: null, trajEl: null, ctl: null };
    app.appendChild(h("div", { class: "crumbs" }, h("a", { href: href("runs"), text: "← Runs" })));
    var holder = h("div", null, h("p", { class: "muted", text: "Loading…" })); app.appendChild(holder); RV.holder = holder;
    getJSON(studyDir() + "runs/" + r.run + "/run.json").then(function (run) {
      RV.run = run; drawRun(); loadManifest(true);
    }, function (e) { clear(holder); holder.appendChild(h("p", { class: "err", text: e.status === 404 ? "This run is not published (yet)." : "Could not load this run." })); });
  }
  function refreshRun() {
    if (!RV || !RV.run) return;
    var live = RV.run.status === "running" || RV.run.status === "stalled" || RV.run.status === "pending";
    if (!live) return;
    getJSON(studyDir() + "runs/" + RV.id + "/run.json").then(function (run) {
      var statusChanged = run.status !== RV.run.status; RV.run = run; drawRunHead();
      if (statusChanged) drawRun(); loadManifest(false);
    }, function () {});
  }
  var headEl = null;
  function drawRun() {
    var run = RV.run, holder = RV.holder; clear(holder);
    holder.appendChild(h("h1", null, run.task.id + " ", badge(run.status)));
    holder.appendChild(h("p", { class: "sub", text: (run.reason ? "Reason: " + run.reason + ". " : "") + "Model " + (run.model || "unknown") + "." }));
    headEl = h("div", { class: "card" }); holder.appendChild(headEl); drawRunHead();

    if (run.previous_attempts && run.previous_attempts.length) {
      holder.appendChild(h("h2", { text: "Earlier attempts" }));
      holder.appendChild(h("div", { class: "card tbl-wrap" }, h("table", null,
        h("thead", null, h("tr", null, ["Attempt", "Status", "Reason", "Started", "Finished", "Node"].map(function (x) { return h("th", { text: x }); }))),
        h("tbody", null, run.previous_attempts.map(function (a) {
          return h("tr", null, h("td", { text: a.attempt }), h("td", null, badge(a.status)), h("td", { class: "muted", text: a.reason || a.error || "" }), h("td", { text: when(a.started_at) }), h("td", { text: when(a.finished_at) }), h("td", { text: a.node || "–" }));
        })))));
    }
    var aBox = h("div"); holder.appendChild(aBox);
    if (S.idx.runs.filter(function (x) { return x.id === run.execution_id && x.has_analysis; }).length) {
      getJSON(studyDir() + "runs/" + run.execution_id + "/analysis.json").then(function (a) {
        aBox.appendChild(h("h2", { text: "Analysis" }));
        aBox.appendChild(h("div", { class: "card" },
          h("p", { text: a.summary || "" }),
          a.blocker ? h("p", null, h("b", { text: "Where it stopped: " }), BLOCKERS[a.blocker] || a.blocker) : null,
          a.notable && a.notable.length ? [h("h3", { text: "Notable" }), h("ul", { class: "plain" }, a.notable.map(function (x) { return h("li", { text: x }); }))] : null,
          a.evidence && a.evidence.length ? [h("h3", { text: "Evidence from the log" }), h("ul", { class: "plain" }, a.evidence.map(function (x) { return h("li", { class: "mono", text: x }); }))] : null,
          h("p", { class: "note", text: "Written by reading the agent's log; a judgement, not a measurement." })));
      }, function () {});
    }
    holder.appendChild(h("h2", { text: "Trajectory" }));
    RV.ctl = h("div", { class: "traj-bar" }); RV.trajEl = h("div");
    holder.appendChild(RV.ctl); holder.appendChild(RV.trajEl);
    RV.loaded = 0; RV.parts = [];
    if (!run.trajectory) RV.trajEl.appendChild(h("p", { class: "muted", text: "No trajectory published for this run." }));
  }
  function drawRunHead() {
    if (!headEl) return; var run = RV.run, t = run.timing || {}, u = run.usage || {}, l = run.limits || {}, o = run.outcome || {}, p = run.progress;
    clear(headEl);
    var f = h("div", { class: "facts" },
      fact("Task family", run.task.family), fact("Node", run.node || "–"), fact("Attempt", run.attempt),
      fact("Started", when(t.started_at)), fact("Finished", t.finished_at ? when(t.finished_at) : (run.status === "running" ? "in progress" : "–")),
      fact("Agent time", dur(t.agent_seconds)), fact("Wall time", dur(t.wall_seconds)),
      p ? fact("Elapsed", dur(p.elapsed_seconds)) : null, p ? fact("Last heartbeat", p.heartbeat_age_seconds != null ? dur(p.heartbeat_age_seconds) + " ago" : "–") : null,
      fact("Spend", usd(u.spend != null ? u.spend : p && p.spend)), fact("Model calls", n0(u.requests != null ? u.requests : p && p.requests)),
      fact("Input tokens", n0(u.input_tokens)), fact("Cached input tokens", n0(u.cache_read_tokens)), fact("Output tokens", n0(u.output_tokens)),
      u.errors != null ? fact("Call errors", n0(u.errors)) : null,
      l.spend_cap_usd != null ? fact("Spend cap", usd(l.spend_cap_usd)) : null, l.agent_timeout_seconds != null ? fact("Agent time limit", dur(l.agent_timeout_seconds)) : null,
      o.flag_score != null ? fact("Flag score", o.flag_score) : null,
      o.stage1 != null ? fact("Stages", [o.stage1, o.stage2, o.stage3, o.stage4].map(function (x) { return x == null ? "–" : x; }).join(" / ")) : null,
      o.all_stages_passed != null ? fact("All stages passed", o.all_stages_passed ? "yes" : "no") : null);
    headEl.appendChild(f);
    if (u.total_spend_complete === false) headEl.appendChild(h("p", { class: "note", text: "Spend shown is what the key recorded; it may be incomplete for this task." }));
  }

  function loadManifest(first) {
    var run = RV.run; if (!run.trajectory || !RV.trajEl) return;
    getJSON(studyDir() + "runs/" + RV.id + "/trajectory/manifest.json").then(function (m) {
      RV.manifest = m; drawCtl();
      if (first && m.parts.length) loadParts(1);
    }, function () { drawCtl(); });
  }
  function drawCtl() {
    var m = RV.manifest, ctl = RV.ctl; if (!ctl) return; clear(ctl);
    if (!m || !m.parts.length) { ctl.appendChild(h("span", { class: "muted", text: "No trajectory parts yet." })); return; }
    var left = m.parts.length - RV.loaded;
    ctl.appendChild(h("span", { class: "muted", text: "Showing part " + RV.loaded + " of " + m.parts.length + " · " + n0(m.total_events) + " events" + (m.complete ? "" : " so far") }));
    ctl.appendChild(h("button", { class: "btn", disabled: left > 0 ? null : "", onclick: function () { loadParts(1); } }, left > 0 ? "Load next part" : "No more parts"));
    if (left > 1) ctl.appendChild(h("button", { class: "btn", onclick: function () { loadParts(left); } }, "Load all " + left));
  }
  function loadParts(n) {
    var m = RV.manifest, from = RV.loaded, to = Math.min(m.parts.length, from + n), id = RV.id, chain = Promise.resolve();
    RV.loaded = to;
    for (var i = from; i < to; i++) (function (i) {
      chain = chain.then(function () { return getText(studyDir() + "runs/" + id + "/trajectory/" + m.parts[i].file); }).then(function (txt) {
        if (!RV || RV.id !== id) return;
        RV.trajEl.appendChild(h("div", { class: "faint note", text: "— part " + (i + 1) + " —" }));
        RV.trajEl.appendChild(m.format === "codex-jsonl" ? renderJsonl(txt) : renderRendered(txt));
      });
    })(i);
    chain.then(drawCtl, function () { drawCtl(); });
    drawCtl();
  }

  /* rendered Codex log: same event boundaries the publisher uses */
  var STARTS = ["[init]", "[todo]", "[tool:", "[error]", "[file-change", "[turn-completed"];
  function renderRendered(text) {
    var evs = [], cur = null, phase = null, prevBlank = false;
    function start(kind, line) { cur = { kind: kind, lines: [line] }; evs.push(cur); phase = kind === "tool" ? "cmd" : null; }
    text.split("\n").forEach(function (line) {
      var blank = !line.trim();
      if (line.indexOf("Reading prompt") === 0) return;
      if (blank) { if (cur && cur.kind !== "prose") { /* keep */ } prevBlank = true; return; }
      var isStart = STARTS.some(function (m) { return line.indexOf(m) === 0; });
      if (line.indexOf("[tool-result]") === 0 || line.indexOf("[tool-error]") === 0) {
        if (cur && cur.kind === "tool") cur.lines.push(line); else start("tool", line);
        phase = "output";
      } else if (isStart) {
        start(line.indexOf("[tool:") === 0 ? "tool" : line.indexOf("[todo]") === 0 ? "todo" : line.indexOf("[error]") === 0 ? "error" : line.indexOf("[init]") === 0 ? "init" : "other", line);
      } else if (prevBlank || !cur) {
        start("prose", line);
      } else if (cur.kind === "tool" && phase === "output") { cur.lines.push(line); phase = "done"; }
      else if (cur.kind === "tool" && phase === "cmd" && line.charAt(0) === " ") cur.lines.push(line);
      else if (cur.kind === "todo" && line.indexOf("  [") === 0) cur.lines.push(line);
      else if (cur.kind === "prose") cur.lines.push(line);
      else start("prose", line);
      prevBlank = false;
    });
    var box = h("div");
    evs.forEach(function (e) { box.appendChild(drawEvent(e)); });
    return box;
  }
  function drawEvent(e) {
    var L = e.lines;
    if (e.kind === "prose") return h("div", { class: "ev say" }, h("div", { class: "lab", text: "agent" }), h("div", { class: "body", text: L.join("\n") }));
    if (e.kind === "todo") return h("div", { class: "ev todo" }, h("div", { class: "lab", text: "plan" }), L.slice(1).map(function (x) { return h("div", { class: "todo-i", text: x.trim() }); }));
    if (e.kind === "error") return h("div", { class: "ev err2" }, h("div", { class: "lab", text: "error" }), h("div", { text: L[0].replace("[error]", "").trim() }));
    if (e.kind === "init") return h("div", { class: "ev init" }, h("div", { class: "lab", text: "start" }), h("div", { class: "mono", text: L[0].replace("[init]", "").trim() }));
    if (e.kind === "other") return h("div", { class: "ev other" }, h("div", { class: "mono", text: L.join("\n") }));
    var cmd = [], res = [], resHead = "", seenRes = false;
    L.forEach(function (x, i) {
      if (i === 0 && x.indexOf("[tool:") === 0) return;
      if (x.indexOf("[tool-result]") === 0 || x.indexOf("[tool-error]") === 0) { seenRes = true; resHead = x; return; }
      (seenRes ? res : cmd).push(seenRes ? x : x.replace(/^ {2}\$ /, "$ ").replace(/^ {2}/, ""));
    });
    var bad = /^\[tool-error\]/.test(resHead) || /exit=(?!0\b)-?\d+/.test(resHead);
    return h("div", { class: "ev tool" }, h("div", { class: "lab", text: (L[0].match(/^\[tool:([^\]]*)\]/) || [0, "tool"])[1] }),
      h("pre", { class: "cmd", text: cmd.join("\n") }),
      seenRes ? h("div", { class: "exit" + (bad ? " bad" : ""), text: resHead.replace(/^\[tool-(result|error)\]\s*/, "") || "done" }) : null,
      res.join("").trim() ? h("details", null, h("summary", { text: "output (" + res.join("\n").length.toLocaleString("en-US") + " characters)" }), h("pre", { text: res.join("\n") })) : null);
  }
  /* jsonl trajectory (Codex events): one event per line */
  function renderJsonl(text) {
    var box = h("div"), evs = [];
    text.split("\n").forEach(function (line) {
      if (!line.trim()) return;
      var o = null; try { o = JSON.parse(line); } catch (e) {}
      evs.push(o || { type: "publisher.raw", text: line });
    });
    var later = {};   // item ids that have a later update or completion in this part: their "started" event is skipped
    evs.forEach(function (o) { if (o.item && o.item.id && o.type !== "item.started") later[o.item.id] = true; });
    evs.forEach(function (o) {
      var it = o.item || {}, kind = it.type || "";
      if (o.type === "item.started" && later[it.id]) return;
      if (kind === "agent_message") {
        if (!it.text || !String(it.text).trim()) return;
        box.appendChild(h("div", { class: "ev say" }, h("div", { class: "lab", text: "agent" }), h("div", { class: "body", text: String(it.text) })));
      } else if (kind === "command_execution") {
        var out = it.aggregated_output || "", bad = it.exit_code != null && it.exit_code !== 0;
        box.appendChild(h("div", { class: "ev tool" }, h("div", { class: "lab", text: "command" }), h("pre", { class: "cmd", text: String(it.command || "") }),
          h("div", { class: "exit" + (bad ? " bad" : ""), text: it.exit_code == null ? (it.status || "running") : "exit=" + it.exit_code }),
          out.trim() ? h("details", null, h("summary", { text: "output (" + out.length.toLocaleString("en-US") + " characters)" }), h("pre", { text: out })) : null));
      } else if (kind === "todo_list") {
        box.appendChild(h("div", { class: "ev todo" }, h("div", { class: "lab", text: "plan" }), (it.items || []).map(function (x) { return h("div", { class: "todo-i", text: (x.completed ? "[x] " : "[ ] ") + x.text }); })));
      } else if (o.type === "turn.completed" && o.usage) {
        box.appendChild(h("div", { class: "ev other" }, h("div", { class: "mono", text: "turn completed · input " + n0(o.usage.input_tokens) + " · cached " + n0(o.usage.cached_input_tokens) + " · output " + n0(o.usage.output_tokens) })));
      } else if (o.type === "thread.started" || o.type === "turn.started") {
        box.appendChild(h("div", { class: "ev init" }, h("div", { class: "lab", text: o.type.replace(".", " ") })));
      } else if (o.type === "publisher.raw") {
        box.appendChild(h("div", { class: "ev other" }, h("pre", { text: String(o.text) })));
      } else {
        var t = o.type || "event", isErr = /error|fail/.test(t + kind);
        box.appendChild(h("div", { class: "ev " + (isErr ? "err2" : "other") }, h("div", { class: "lab", text: t + (kind ? " · " + kind : "") }),
          h("details", null, h("summary", { text: "raw event" }), h("pre", { text: JSON.stringify(o, null, 2) }))));
      }
    });
    return box;
  }

  /* ---- boot ---- */
  document.getElementById("theme").addEventListener("click", function () {
    var t = document.documentElement.dataset.theme === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = t;
    try { localStorage.setItem("live-theme", t); } catch (e) {}
  });
  window.addEventListener("hashchange", onRoute);
  loadStudies().then(function () { S.ok = true; onRoute(); refreshPill(); }, function () {
    setPill("warn", "offline"); clear(app); app.appendChild(h("p", { class: "err", text: "Could not read the run data. Check the data address in config.js, or open this page with ?data=<address>." }));
  });
})();
