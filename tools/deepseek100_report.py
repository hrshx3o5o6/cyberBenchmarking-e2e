"""HTML for the "100 task run: DeepSeek V4.1 Flash" section of the run viewer: the report page and the per-task table.

Reads the small tables in wiki/syntheses/aws-vm-data/deepseek100/ (summary.json, per_task.csv, node_timeseries_15min.csv, shim_hourly.csv, made by
analyze_deepseek100.py from the raw run data). Pure functions: build_report(data, ctx) and task_table(data, links, ctx); ctx supplies head, TAIL, chip, esc from build_viewer.
Static output: inline SVG, no scripts, no external requests.
"""
import csv, collections, datetime as dt, json, os, statistics as st

NODE_COL = {"head": "var(--accent)", "worker A (…20.48)": "var(--pass)", "worker B (…23.192)": "#c27a00"}


def load(d):
    S = json.load(open(os.path.join(d, "summary.json")))
    num = lambda v: float(v) if v not in ("", "None", None) else None
    tasks = []
    for r in csv.DictReader(open(os.path.join(d, "per_task.csv"))):
        for k in ("agent_min", "total_min", "overhead_min", "requests", "calls_502", "calls_failed_stream", "call_secs_p50", "call_secs_max", "tokens_prompt", "fresh_in", "cached_in", "out_tok", "spend", "errors", "stages_run"):
            r[k] = num(r.get(k))
        r["hit_limit"] = r.get("hit_limit") == "True"
        tasks.append(r)
    series = list(csv.DictReader(open(os.path.join(d, "node_timeseries_15min.csv"))))
    shim = list(csv.DictReader(open(os.path.join(d, "shim_hourly.csv"))))
    ex = os.path.join(d, "extras.json")
    return dict(S=S, tasks=tasks, series=series, shim=shim, X=json.load(open(ex)) if os.path.exists(ex) else None)


# ------------------------------------------------------------------ svg
def _txt(x, y, s, anchor="start", size=11):
    return '<text x="%.1f" y="%.1f" text-anchor="%s" font-size="%d" style="fill:var(--muted)">%s</text>' % (x, y, anchor, size, s)


def svg_wrap(w, h, inner, label):
    return '<svg viewBox="0 0 %d %d" role="img" aria-label="%s" style="width:100%%;height:auto;max-width:%dpx">%s</svg>' % (w, h, label, w, inner)


def bars(items, width=860, bar_h=22, label_w=190, fmt="%d", color="var(--accent)", note=None):
    """horizontal bars: items = [(label, value, optional colour)]"""
    top = max([v for _, v, *_ in items] + [1]); h = bar_h * len(items) + 8
    out = []
    for i, it in enumerate(items):
        lab, v = it[0], it[1]; col = it[2] if len(it) > 2 else color
        w = (width - label_w - 70) * v / top
        y = 4 + i * bar_h
        out.append(_txt(label_w - 8, y + bar_h * .68, lab, "end", 12) + '<rect x="%d" y="%.1f" width="%.1f" height="%d" rx="3" style="fill:%s"/>' % (label_w, y + 3, max(w, 1), bar_h - 7, col)
                   + _txt(label_w + w + 6, y + bar_h * .68, fmt % v, "start", 12))
    return svg_wrap(width, h, "".join(out), "bar chart")


def histogram(values, edges, width=860, height=190, color="var(--accent)", xlabel="", vline=None, fmt_edge="%g"):
    counts = [sum(1 for v in values if lo <= v < hi) for lo, hi in zip(edges, edges[1:])]
    counts[-1] += sum(1 for v in values if v >= edges[-1])
    top = max(counts + [1]); L, R, T, B = 40, 10, 14, 34
    pw, ph = width - L - R, height - T - B; bw = pw / len(counts)
    out = []
    for g in range(0, 5):
        yy = T + ph - ph * g / 4
        out.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" style="stroke:var(--line)"/>' % (L, width - R, yy, yy) + _txt(L - 4, yy + 4, "%d" % round(top * g / 4), "end", 10))
    for i, c in enumerate(counts):
        x = L + i * bw
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" style="fill:%s"/>' % (x + 2, T + ph - ph * c / top, bw - 4, ph * c / top, color))
        if c: out.append(_txt(x + bw / 2, T + ph - ph * c / top - 3, str(c), "middle", 10))
        out.append(_txt(x + bw / 2, height - 18, fmt_edge % edges[i], "middle", 10))
    out.append(_txt(width / 2, height - 3, xlabel, "middle", 11))
    if vline is not None:
        xv = L + pw * (vline - edges[0]) / (edges[-1] - edges[0])
        out.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke-dasharray="4 3" style="stroke:var(--fail)"/>' % (xv, xv, T, T + ph))
    return svg_wrap(width, height, "".join(out), "histogram of " + xlabel)


def lines(series, ymax, hlines=(), width=860, height=230, ylabel="", times=None):
    """series: {name: [(t_index, value)]}, times: list of x labels (one per index); hlines: [(value, label, colour)]"""
    L, R, T, B = 44, 10, 12, 30; pw, ph = width - L - R, height - T - B
    n = len(times); X = lambda i: L + pw * i / max(1, n - 1); Y = lambda v: T + ph - ph * min(v, ymax) / ymax
    out = []
    for g in range(0, 5):
        yy = T + ph - ph * g / 4
        out.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" style="stroke:var(--line)"/>' % (L, width - R, yy, yy) + _txt(L - 4, yy + 4, "%g" % (ymax * g / 4), "end", 10))
    for v, lab, col in hlines:
        out.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke-dasharray="5 4" style="stroke:%s"/>' % (L, width - R, Y(v), Y(v), col) + _txt(width - R - 2, Y(v) - 3, lab, "end", 10))
    step = max(1, n // 9)
    for i in range(0, n, step): out.append(_txt(X(i), height - 14, times[i], "middle", 10))
    legend = ""
    for k, (name, pts) in enumerate(series.items()):
        col = NODE_COL.get(name, "var(--accent)")
        out.append('<polyline fill="none" stroke-width="1.6" points="%s" style="stroke:%s"/>' % (" ".join("%.1f,%.1f" % (X(i), Y(v)) for i, v in pts), col))
        out.append('<rect x="%d" y="%d" width="10" height="10" style="fill:%s"/>' % (L + 8 + k * 170, 2, col) + _txt(L + 22 + k * 170, 11, name, "start", 11))
    out.append(_txt(8, T + 10, ylabel, "start", 10))
    return svg_wrap(width, height, "".join(out), ylabel + " over time")


# ------------------------------------------------------------------ pieces
def fmt_d(x): return format(int(x), ",")


def sec(title, body, id_=None): return '<section class="panel"%s><h2>%s</h2>%s</section>' % (' id="%s"' % id_ if id_ else "", title, body)


def table(headers, rows, cls=""):
    h = "<tr>" + "".join("<th>%s</th>" % x for x in headers) + "</tr>"
    return '<div class="tablewrap"><table%s><thead>%s</thead><tbody>%s</tbody></table></div>' % (' class="%s"' % cls if cls else "", h, "".join("<tr>" + "".join("<td%s>%s</td>" % (' class="n"' if i else "", c) for i, c in enumerate(r)) + "</tr>" for r in rows))


FLAGS = {"qpdf/oss-fuzz_42535152": "PoC sits in the source tree (leak); reported separately", "binutils/arvo_60532": "replaced task (the drawn one had an empty PoC)",
         "ghostscript/oss-fuzz_399390078": "replaced task (the drawn one had an empty PoC)", "ffmpeg/oss-fuzz_42538351": "stopped by the operator during grading; not graded"}


def task_flags(t):
    f = []
    if t["status"] == "interrupted": f.append("stopped in grading, not graded")
    elif t["hit_limit"]: f.append("90-minute limit")
    if t["task"] in FLAGS and t["status"] != "interrupted": f.append(FLAGS[t["task"]])
    if t.get("overhead_min") and t["overhead_min"] >= 60: f.append("grading %d min" % t["overhead_min"])
    return "; ".join(f)


def task_table(data, links, ctx):
    rows = []
    for t in sorted(data["tasks"], key=lambda t: t["task"]):
        stages = [t["s1"], t["s2"], t["s3"], t["s4"]] if t["status"] != "interrupted" else ["interrupted"] * 4
        a = '<a href="%s">%s</a>' % (links[t["task"]], ctx["esc"](t["task"])) if t["task"] in links else ctx["esc"](t["task"])
        rows.append("<tr><td>%s</td><td><div class=\"chips\" style=\"flex-wrap:wrap\">%s</div></td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td>%s</td></tr>" % (
            a, "".join(ctx["chip"](s) for s in stages), ("%.0f" % t["agent_min"]) if t["agent_min"] else "-", ("%.0f" % t["total_min"]) if t["total_min"] else "-",
            fmt_d(t["requests"]) if t["requests"] else "-", ("$%.2f" % t["spend"]) if t["spend"] is not None else "-", ctx["esc"]((t["host"] or "").replace("ip-172-31-", "…")), ctx["esc"](task_flags(t))))
    return ('<div class="tablewrap"><table class="runs"><colgroup><col style="width:20%"><col style="width:20%"><col style="width:7%"><col style="width:7%"><col style="width:7%"><col style="width:8%"><col style="width:9%"><col style="width:22%"></colgroup>'
            '<thead><tr><th>Task</th><th>S1 · S2 · S3 · S4</th><th>Agent min</th><th>Total min</th><th>Calls</th><th>Cost</th><th>Node</th><th>Flags</th></tr></thead><tbody>@@ROWS@@</tbody></table></div>').replace("@@ROWS@@", "".join(rows))


def build_report(data, links, ctx):
    S, tasks, series = data["S"], data["tasks"], data["series"]
    fin = [t for t in tasks if t["status"] != "interrupted"]
    R = S["run"]; sp = S["spend"]; tk = S["tokens"]; sh = S["shim"]
    out = [ctx["head"]("100 task run: DeepSeek V4.1 Flash")]
    out.append('<div class="crumbs"><a href="index.html">Run viewer</a> › 100 task run: DeepSeek V4.1 Flash</div>')
    out.append('<header><h1>100 task run: DeepSeek V4.1 Flash <span class="badge">report</span></h1><p class="sub">CyberGym-E2E, 100 random tasks, end to end, Codex through Google Vertex AI, one attempt per task, '
               'the paper\'s limits (90 minutes of agent time, 10 USD per run). Run on 3 EC2 nodes (the head and 2 autoscaled workers), 2026-11-04 06:07 to 17:00 UTC.</p></header>')
    out.append('<div class="banner info"><b>Read this first.</b> 99 of the 100 tasks were graded; the 100th (<code>ffmpeg/oss-fuzz_42538351</code>) was still in grading after about 3 hours 20 minutes when the operator stopped the run, so it is shown as not graded. '
               'Dollar figures use an <b>assumed</b> Vertex price (0.30 USD per million fresh input tokens, 0.03 cached, 1.20 output; read from third-party listings, not checked on Google\'s page). '
               'This is the second pass: a first attempt at 10 task slots per node lost 68 tasks to node out-of-memory events and is described in the first-pass section below.</div>')
    out.append('<nav class="jump"><a href="#glance">At a glance</a><a href="#outcomes">Outcomes</a><a href="#time">Time</a><a href="#money">Money</a><a href="#calls">Model calls</a><a href="#nodes">Memory and CPU</a><a href="#infra">Infrastructure</a><a href="#first">First pass</a><a href="#extras">Fuzzers and validation</a><a href="#whatif">What if</a><a href="#projects">By project</a><a href="#tasks">Per task</a><a href="#method">Method</a></nav>')
    # at a glance
    facts = [("Tasks graded", "%d of 100" % R["finished"]), ("Passed S1 to S4", "%d (%.0f%% of graded)" % (R["passed"], 100 * R["passed"] / R["finished"])), ("Run time", "10 h 54 min wall"),
             ("Agent time, mean / median", "%.0f / %.0f min" % (S["agent_minutes"]["mean"], S["agent_minutes"]["median"])), ("At the 90-minute limit", "%d of %d (%.0f%%)" % (S["hit_limit"], R["finished"], 100 * S["hit_limit"] / R["finished"])),
             ("Total cost (assumed price)", "$%.2f" % sp["total"]), ("Cost per task, mean / max", "$%.2f / $%.2f" % (sp["mean"], sp["max"])), ("Cost per passing task", "$%.2f" % sp["cost_per_pass"]),
             ("Model calls (usage)", fmt_d(tk["requests"])), ("Prompt tokens, fresh + cached", "%.2f billion" % ((tk["fresh"] + tk["cached"]) / 1e9)), ("Cached share of prompt tokens", "%.0f%%" % tk["cached_share"]),
             ("Output tokens", "%.1f million" % (tk["out"] / 1e6)), ("Task slots", "4 head + 6 + 6 workers = 16"), ("Infrastructure failures", "0 in this pass")]
    out.append(sec("At a glance", '<dl class="facts">%s</dl>' % "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (a, b) for a, b in facts), "glance"))
    # outcomes
    oc = S["outcomes"]; order = ["PASS S1-S4", "S4 fail", "no PoC", "no patch", "S1 fail"]
    cols = {"PASS S1-S4": "var(--pass)", "S4 fail": "var(--accent)", "no PoC": "var(--fail)", "no patch": "#c27a00", "S1 fail": "var(--skip)"}
    def stage_n(i, v="passed"): return sum(1 for t in fin if t["s%d" % i] == v)
    funnel = [("S1 PoC crashes the vulnerable build", stage_n(1)), ("S2 patch stops that crash", stage_n(2)), ("S3 other checks", stage_n(3)), ("S4 intended bug fixed", stage_n(4))]
    kinds = "".join("<tr><td>%s</td><td class=\"n\">%d</td><td class=\"n\">%d</td><td class=\"n\">%d</td><td class=\"n\">%d</td><td class=\"n\">$%.2f</td></tr>" % (k["kind"], k["n"], k["passed"], k["no_poc"], k["s4_fail"], k["spend"]) for k in S["by_kind"])
    out.append(sec("Outcomes", bars([(k, oc.get(k, 0), cols[k]) for k in order], label_w=120) +
                   '<p class="note">S4 fail: PoC and patch passed S1 to S3 (the paper\'s success criterion) but the patch does not fix the benchmark\'s own crash, meaning a different real bug was patched or the fix is partial; in %d of them the S4 stage itself ended in an error rather than a clean fail. '
                   'By the paper\'s S1+S2+S3 rule, <b>%d of %d</b> tasks succeed (those two groups together).</p>' % (sum(1 for t in fin if t["s4"] == "error" and t["outcome"] == "S4 fail"), oc.get("PASS S1-S4", 0) + oc.get("S4 fail", 0), R["finished"]) +
                   '<h3 class="task">Stage funnel (tasks that passed each stage)</h3>' + bars([(a, b) for a, b in funnel], label_w=260) +
                   '<h3 class="task">By task kind</h3>' + table(["Kind", "Tasks", "Passed S1-S4", "No PoC", "S4 fail", "Cost"], [list(map(str, [k["kind"], k["n"], k["passed"], k["no_poc"], k["s4_fail"], "$%.2f" % k["spend"]])) for k in S["by_kind"]]) +
                   '<p class="note">oss-fuzz and arvo are the two task families of the benchmark. Counts are small, so differences between them are not reliable.</p>', "outcomes"))
    # time
    am = [t["agent_min"] for t in fin]; ov = [t["overhead_min"] for t in fin if t["overhead_min"] is not None]; g = S["grading"]["graded_overhead"]
    ff = S["grading"]["ffmpeg_graded"]; ffsum = sum(x[1] for x in ff)
    done = sorted(dt.datetime.fromisoformat(t["finished"].replace("+00:00", "")) for t in fin if t["finished"])
    start = dt.datetime(2026, 11, 4, 6, 7, 16)
    hours_f = collections.Counter(int((d - start).total_seconds() // 3600) for d in done)
    out.append(sec("Time", "<p>Each task has three phases: setup (container start, build preparation, Codex install), <b>the agent's run, capped at 90 minutes</b>, then <b>grading</b> (stages S1 to S4, each in a fresh container that rebuilds the project). The cap holds: the longest agent run of the %d finished tasks is %.1f minutes.</p>" % (R["finished"], max(am)) +
                   "<h3 class=\"task\">Agent minutes per task</h3>" + histogram(am, list(range(0, 100, 10)) + [100], xlabel="agent minutes (bin start)", vline=90) +
                   '<p class="note">%d of %d tasks (%.0f%%) ran the full 90 minutes. The %d that passed all four stages took %.0f minutes on average (median %.0f); %d of them used the full time.</p>' % (S["hit_limit"], R["finished"], 100 * S["hit_limit"] / R["finished"], R["passed"], S["pass_by_limit"]["passed_agent_min"]["mean"], S["pass_by_limit"]["passed_agent_min"]["median"], S["pass_by_limit"]["passed_at_limit"]) +
                   '<h3 class="task">Where the %.0f task-hours went</h3>' % S["task_hours"]["total"] + bars([("agent run", S["task_hours"]["agent"], "var(--accent)"), ("setup and grading", S["task_hours"]["outside_agent"], "#c27a00")], fmt="%.1f h", label_w=150) +
                   "<h3 class=\"task\">Validation (grading): who spent time on it</h3><p><b>%d of %d</b> tasks were never graded (no PoC or no patch, so the harness skips every stage; about 0.1 minutes of overhead). Only <b>%d</b> were graded; 45 ran all four stages, 2 stopped after S1. "
                   "Time outside the agent for graded tasks: median %.0f, mean %.0f, 90th percentile %.0f, maximum %.0f minutes.</p>" % (S["not_graded"], R["finished"], S["graded"], g["median"], g["mean"], g["p90"], g["max"]) +
                   table(["Setup + grading time (minutes outside the agent run)", "Tasks (of %d)" % len(ov)], [[lab, str(sum(1 for v in ov if lo <= v < (hi or 1e9)))] for lab, lo, hi in (("under 5", 0, 5), ("5 to 15", 5, 15), ("15 to 30", 15, 30), ("30 to 60", 30, 60), ("1 to 2 hours", 60, 120), ("over 2 hours", 120, 0))]) +
                   "<p>The %d graded <b>ffmpeg</b> tasks spent %.0f to %.0f minutes each outside the agent run (mean %.0f; %.1f hours in all, %.0f%% of the %.1f hours every task spent outside it). These minutes are on top of the 90-minute agent run, "
                   "so an ffmpeg task takes 3 to 3.7 hours wall. Each grading stage rebuilds ffmpeg in a fresh container (the grader is CyberGym's own); the per-stage time was not measured separately.</p>" % (len(ff), min(x[1] for x in ff), max(x[1] for x in ff), ffsum / len(ff), ffsum / 60, 100 * (ffsum / 60) / S["task_hours"]["outside_agent"], S["task_hours"]["outside_agent"]) +
                   "<h3 class=\"task\">Tasks finished per hour since the start</h3>" + bars([("hour %d" % (h + 1), hours_f.get(h, 0)) for h in range(0, 11)], label_w=90) +
                   '<p class="note">The tail is long because the last hours held only a few ffmpeg tasks in grading; the agents were done by about 15:30 UTC (9.4 hours).</p>', "time"))
    # money
    spend = [t["spend"] for t in fin if t["spend"] is not None]
    top = sorted(fin, key=lambda t: -(t["spend"] or 0))[:10]
    out.append(sec("Money", "<p>Price assumed: 0.30 USD per million fresh input tokens, 0.03 cached, 1.20 output. Per-run cap 10 USD; <b>no task came near it</b> (maximum $%.2f, %d tasks above $5, none above $8).</p>" % (sp["max"], sp["over_5"]) +
                   histogram(spend, [0, 1, 2, 3, 4, 5, 6, 7, 8, 10], xlabel="cost per task, USD (bin start)", color="#c27a00", vline=None, fmt_edge="%g") +
                   table(["Outcome", "Tasks", "Mean cost", "Total cost"], [[k, str(oc.get(k, 0)), "$%.2f" % sp["by_outcome"][k], "$%.2f" % sp["total_by_outcome"][k]] for k in order if k in sp["by_outcome"]]) +
                   "<p>Total <b>$%.2f</b> for %d graded tasks (mean $%.2f, median $%.2f). Passing tasks are cheap (mean $%.2f); the money goes to tasks that run the full time and find nothing (<b>no PoC: $%.2f, %.0f%% of the total</b>). Cost per passing task: $%.2f.</p>" % (sp["total"], R["finished"], sp["mean"], sp["median"], sp["by_outcome"]["PASS S1-S4"], sp["total_by_outcome"]["no PoC"], 100 * sp["total_by_outcome"]["no PoC"] / sp["total"], sp["cost_per_pass"]) +
                   "<p>Tokens: %.0f million fresh prompt tokens, %.0f million cached (%.0f%% cached), %.1f million output, over %s calls: on average %s prompt tokens and %s output tokens per call and %.0f calls per task (median %.0f, maximum %s).</p>" % (tk["fresh"] / 1e6, tk["cached"] / 1e6, tk["cached_share"], tk["out"] / 1e6, fmt_d(tk["requests"]), fmt_d(S["prompt_tokens_per_call_mean"]), S["out_tokens_per_call_mean"], S["calls_per_task"]["mean"], S["calls_per_task"]["median"], fmt_d(S["calls_per_task"]["max"])) +
                   "<h3 class=\"task\">Ten most expensive tasks</h3>" + table(["Task", "Outcome", "Cost", "Agent min", "Calls"], [[ctx["esc"](t["task"]), t["outcome"], "$%.2f" % t["spend"], "%.0f" % t["agent_min"], fmt_d(t["requests"])] for t in top]) +
                   '<p class="note">Compute (EC2) is separate and small: the head plus two workers for about 10 hours each is about 30 instance-hours of a 16-vCPU instance. The Qwen GPU endpoint (a different experiment) is not included.</p>', "money"))
    # calls
    out.append(sec("Model calls", "<p>Every model call went through the metering shim on its node (the head's and each worker's), which logged one record per call: <b>%s calls</b>, of which %s returned 200 and <b>%d (%.1f%%) returned 502</b> from Vertex. %d streams failed (a cut-off or errored response, reported to Codex as a failed response so it retries), and <b>%d calls hit the 600-second per-call cap</b> that the shim applies. "
                   "Latency per call: median %.1f s, 90th percentile %.1f s, 99th percentile %.1f s.</p>" % (fmt_d(sh["calls"]), fmt_d(sh["http_200"]), sh["http_502"], 100 * sh["http_502"] / sh["calls"], sh["failed_streams"], sh["over_590s"], sh["secs_p50"], sh["secs_p90"], sh["secs_p99"]) +
                   table(["Hour (UTC, Nov 4)", "Calls", "HTTP 502", "Failed streams", "Median s", "90th pct s", "Calls over 590 s"], [[r["hour_utc"][-2:] + ":00", fmt_d(float(r["calls"])), r["http_502"], r["failed_streams"], r["secs_p50"], r["secs_p90"], r["calls_over_590s"]] for r in data["shim"]]) +
                   "<p class=\"note\">Finish reasons: %s. Calls per node: %s. Vertex answered every request within the run; no rate limiting (429) was seen. The 08:00 hour stands out: only 1,305 calls (about 2,200 in a normal hour), 99 HTTP 502s and a 90th-percentile latency of 158 s, a slowdown on the provider's side (the cause is unknown to us). Stalled calls (the tail above 590 s) are why the shim has a silence limit of 180 s and a total limit of 600 s per call.</p>" % (", ".join("%s %s" % (k, fmt_d(v)) for k, v in sh["finish"].items()), ", ".join("%s %s" % (k, fmt_d(v)) for k, v in sh["by_node"].items())), "calls"))
    # nodes: memory and cpu series
    names = ["head", "worker A (…20.48)", "worker B (…23.192)"]
    bks = sorted({r["bucket_start_utc"] for r in series}); idx = {b: i for i, b in enumerate(bks)}; times = [b[11:16] for b in bks]
    ser_mem = {n: [(idx[r["bucket_start_utc"]], float(r["mem_used_max_gb"])) for r in series if r["node"] == n] for n in names}
    ser_load = {n: [(idx[r["bucket_start_utc"]], float(r["load1_max"])) for r in series if r["node"] == n] for n in names}
    nrows = [[n, "%d" % S["nodes"][n]["samples"], "%.1f" % S["nodes"][n]["mem_used_avg"], "%.1f" % S["nodes"][n]["mem_used_p99"], "%.1f" % S["nodes"][n]["mem_used_max"], "%.1f" % S["nodes"][n]["mem_avail_min"],
              "%.0f / %.0f / %.0f / %.0f" % (S["nodes"][n]["load_avg"], S["nodes"][n]["load_p50"], S["nodes"][n]["load_p90"], S["nodes"][n]["load_max"]), "%.0f%% / %.0f%%" % (S["nodes"][n]["pct_load_over_16"], S["nodes"][n]["pct_load_over_32"])] for n in names]
    out.append(sec("Memory and CPU", "<p>Each node is an <code>m7i.4xlarge</code>: 16 vCPU and about 62 GB of RAM, no swap. The harness starts task containers with no memory or CPU limit, so one task can use the whole node. A sampler on every node wrote memory, load and the largest containers every 30 seconds (about 1,000 to 1,250 samples per node) to the shared database. Ray's memory monitor kills task processes at about 58.7 GB used.</p>" +
                   "<h3 class=\"task\">Memory used, maximum per 15 minutes (GB)</h3>" + lines(ser_mem, 64, [(58.7, "Ray kill threshold 58.7 GB", "var(--fail)")], ylabel="GB", times=times) +
                   "<h3 class=\"task\">Load average (1 min), maximum per 15 minutes</h3>" + lines(ser_load, 90, [(16, "16 cores", "var(--muted)")], ylabel="load", times=times) +
                   table(["Node", "Samples", "Mem used avg GB", "p99 GB", "Max GB", "Lowest free GB", "Load avg / median / p90 / max", "Samples over 16 / over 32"], nrows) +
                   "<p><b>Memory stayed well below the limit this pass:</b> the highest reading on any node is %.1f GB (the head %.1f, worker A %.1f, worker B %.1f), about half of the node's 62 GB and under the 58.7 GB kill threshold; the lowest free memory is %.1f GB. "
                   "<b>CPU was saturated in bursts</b>, mostly on worker B (above 16 in %.0f%% of its samples, above 32 in %.0f%%). The 90th-percentile load is 16 on worker A and 17 on the head.</p>" % (max(S["nodes"][n]["mem_used_max"] for n in names), S["nodes"]["head"]["mem_used_max"], S["nodes"]["worker A (…20.48)"]["mem_used_max"], S["nodes"]["worker B (…23.192)"]["mem_used_max"], min(S["nodes"][n]["mem_avail_min"] for n in names), S["nodes"]["worker B (…23.192)"]["pct_load_over_16"], S["nodes"]["worker B (…23.192)"]["pct_load_over_32"]) +
                   "<h3 class=\"task\">Largest single containers seen (GB of RAM)</h3>" + table(["Container peak", "Node", "Container"], [["%.1f" % c[0], c[1], c[2]] for c in S["top_containers_gb"]]) +
                   "<p>Observed with live inspection (not in the sampler): the biggest containers were fuzzers: a container with 425 processes (many <code>mruby_proto_fuz</code> and <code>fuzz_parse_msg</code> processes of about 0.4 GB each) held 23 GB, and a ghostscript task ran 36 <code>gs_device_faxg3</code> fuzzer processes that used about 14 of a node's 16 cores. "
                   "In CyberGym the agent is free to run the project's fuzzers; with many parallel fuzzer workers one container can take most of a node's CPU and tens of GB of RAM for as long as it runs, and the memory returns when the task ends. The memory spikes (23 GB, 20 GB) cleared on their own at the end of the task. "
                   "Whether the first pass's out-of-memory events were this same mechanism could not be confirmed (those nodes were gone before inspection; the sampler did not exist then); it is the best fit.</p>" +
                   "<p class=\"note\">What is not recorded: per-container CPU over time and CPU pressure (only load), and Docker's own container logs.</p>", "nodes"))
    # infra
    ev = S["autoscaler_event_counts"]
    out.append(sec("Infrastructure and autoscaler", "<p>Ray's autoscaler, from a hand-started head, launched workers on demand and removed idle ones after 3 minutes. Setup of each worker (data download of 36 GB, Postgres library, shim start) took 5 to 10 minutes; its first tasks then waited for image pulls (several GB each, up to about 51 GB for some ffmpeg images).</p>" +
                   table(["Item", "Value"], [["Nodes", "head (4 slots) + worker A and B (6 slots each) = 16 slots"], ["Disk", "workers 1024 GiB, head 496 GB. The harness never removes task images, so free space on the head fell from about 456 GB at the start (after clearing cached images before the run) to 145 GB at its lowest and was 221 GB at 15:02, when some large containers had ended"],
                                                 ["Workers launched / removed", "2 workers kept for the whole run; the autoscaler wanted up to 3"], ["Autoscaler launch failures", "<code>VcpuLimitExceeded</code> repeated about every 5 seconds (%s failed attempts in the logs): the account's vCPU limit allowed the head plus 2 workers (48 vCPUs); the first pass had 3 workers (64 vCPUs) so the limit is not simply 60" % fmt_d(5737)],
                                                 ["Token", "a Google access token refreshed every 30 minutes from the study owner's Mac and relayed to workers through the head; it never lapsed in this pass"], ["Postgres", "results, usage and the agent trajectories of all %d tasks, plus node samples" % R["finished"]]]) +
                   '<p class="note">Wall time 10 h 54 min against about 116 agent-hours: with 16 slots about 80% of the slot time was in use on average (about 143 task-hours of about 174 slot-hours); the queue stayed full until the last tasks.</p>', "infra"))
    # first pass
    out.append(sec("The first pass (10 slots per node) and why it was rerun", "<p>The first attempt (2026-11-03, 19:43 to 22:01 UTC) used 10 task slots per node. Two of its three workers ran out of memory (about 60 of 62 GB used): worker 3 at 20:41 after 50 minutes (all 10 running tasks killed) and worker 1 at about 21:08 (7 more). "
                   "When the first node died, <b>52 tasks that had not started also failed</b> in the same instant (the driver's log shows 10 pending lease requests plus 42 queued tasks, exactly 52), because the driver submits all tasks at once and does not retry. Result: <b>31 tasks completed normally and 68 were lost</b> to infrastructure, not to the model. "
                   "The 31 completed tasks (5 passed all four stages) are kept as a separate record and are not mixed into this pass.</p>" +
                   table(["", "First pass (10 slots/node)", "This pass (6 per worker, 4 on head)"], [["Tasks completed normally", "31 of 100", "99 of 100"], ["Lost to infrastructure", "68", "0"], ["Peak memory on a node", "about 60 GB at the failures (no sampler)", "%.1f GB" % max(S["nodes"][n]["mem_used_max"] for n in names)],
                                                                                                                    ["Wall time", "2 h 18 min", "10 h 54 min"], ["Slots", "up to 40", "16"]]) +
                   '<p class="note">Cause of the first pass\'s failure: memory exhaustion under 10 concurrent heavy tasks per node (probably fuzzers); the fix applied was fewer slots per node, not a change to the tasks or the limits.</p>', "first"))
    X = data.get("X")
    if X:
        mc, fz, sv, va = X["model_calls"], X["fuzzers"], X["self_validation"], X["validation"]
        pipeline = table(["Step", "What happens", "Inside the 90 minutes?"], [["1. Setup", "task container from the project image, <code>prepare.sh</code>, Codex install", "no"], ["2. Agent run", "the model reads the source, finds the bug, writes <code>/output/poc.bin</code> and <code>fix.patch</code>", "yes, capped at 90 min"],
                   ["2b. Self-validation", "the prompt tells the agent to test with CyberGym's <code>validate.py</code> (S1 after the PoC, later the patch checks); each run rebuilds the project", "yes"],
                   ["3. Official grading", "after the agent exits, <code>validate.py</code> runs S1 to S4 in fresh containers; skipped when there is no PoC or no patch", "no (only our 9.5-hour safety deadline)"], ["4. Result", "stage results; with several attempts they are fed back to the agent for the next one", "not used: one attempt"]])
        stages = table(["Stage", "Check (from CyberGym's code)", "Passes when"], [["S1", "the agent's PoC, no patch", "it crashes the vulnerable build"], ["S2", "the agent's PoC, with the agent's patch", "it no longer crashes (skipped if S1 failed)"], ["S3", "the project's test suite, with the patch", "tests pass (skipped if S2 failed)"], ["S4", "the benchmark's own ground-truth PoC, with the patch", "it no longer crashes: the patch fixes the recorded bug (\"bonus: found THE bug\")"]])
        out.append(sec("Fuzzers, validation and model hours", "<h3 class=\"task\">Where validation sits in the pipeline</h3>" + pipeline + "<h3 class=\"task\">The four grading stages</h3>" + stages +
                       "<p><b>Validation is about %d%% of the task time</b>: %.1f slot-hours of %.1f task-hours (%d%% of the cluster's %.0f slot-hours). It is concentrated in the ffmpeg tasks and it set the end of the run: the last %.1f hours (%d%% of the wall time) were grading alone. The agents' own <code>validate.py</code> self-checks are inside the agent time: %d of %d agents ran it, %d times in all (%.1f per task, at most %d; %.1f%% of their commands), each run rebuilding the project; their share of the 90 minutes is not known (the logs have no timestamps).</p>" % (va["share_of_task_hours"], va["slot_hours"], va["task_hours"], va["share_of_slot_capacity"], va["wall_hours"] * 16, va["tail_only_grading_hours"], round(100 * va["tail_only_grading_hours"] / va["wall_hours"]), sv["tasks_that_ran_validate_py"], fz["tasks"], sv["runs"], sv["mean_per_task"], sv["max_per_task"], sv["share_of_commands"]) +
                       "<h3 class=\"task\">Model hours</h3><p>Time inside model calls, summed over all calls of all agents: <b>%.1f hours</b>, %d%% of the %.1f agent-hours (%d%% without the stalled calls). %.1f of those hours came from just %d calls that hit the 600-second cap and were retried. On average %.1f calls were in flight at any moment with up to 16 agents running; the mean call lasted %.1f s. Agent-hours are not GPU-hours: DeepSeek ran on Vertex's managed service, so there were no GPU-hours of ours.</p>" % (mc["hours_all"], mc["share_of_agent_time_all"], mc["agent_hours"], mc["share_without_stalled"], mc["hours_stalled"], mc["stalled_calls"], mc["mean_in_flight"], mc["mean_call_s"]) +
                       "<h3 class=\"task\">Fuzzers</h3><p><b>%d of %d agents ran a fuzzer at least once</b> (%d with parallel workers or AFL); fuzzer commands are %.1f%% of all %s commands. %d of the %d tasks that hit the 90-minute limit ran one, and %d of the %d tasks that ended with no PoC. They are therefore almost universal and cannot by themselves separate passes from failures (%d of %d passing tasks ran one). Their measured effect is on the nodes: one container with 425 fuzzer processes held 23 GB, a ghostscript task held about 14 of 16 cores, and worker B was above load 16 in 42%% of samples. How much agent time went into fuzzing could not be measured. Counts come from a pattern search over command lines and are approximate.</p>" % (fz["ran_fuzzer"], fz["tasks"], fz["ran_parallel_or_afl"], 100 * fz["fuzzer_commands"] / fz["commands"], fmt_d(fz["commands"]), fz["at_limit_ran_fuzzer"], fz["at_limit"], fz["no_poc_ran_fuzzer"], fz["no_poc_tasks"], fz["pass_ran_fuzzer"], fz["pass_tasks"]), "extras"))
        wi = X["what_if"]
        out.append(sec("What if: other slot counts (an estimate)", "<p>The 100 tasks' real durations replayed on other configurations (%s). The model gives %.1f h for what was run; the run itself was 10.9 h but was cut about 20 minutes into the last grading.</p>" % (wi["model"], wi["scenarios"][0]["wall_hours"]) +
                       table(["Scenario", "Slots", "Wall time", "If setup and grading are 20% slower"], [[ctx["esc"](x["name"]), str(x["slots"]), "%.1f h" % x["wall_hours"], "%.1f h" % x["wall_hours_if_overhead_20pct_slower"]] for x in wi["scenarios"]]) +
                       "<p class=\"note\">With a 72-vCPU quota the head plus 3 workers fit (64 vCPUs). Eight slots per worker were not tested: ten per node ran two of three workers out of memory in the first pass, the largest container this pass held 23 GB, and CPU was already saturated in 42% of one worker's samples at six slots. Returns diminish because the 90-minute agents and the 3.7-hour ffmpeg tasks bound the wall time.</p>", "whatif"))
    # by project
    prow = [[ctx["esc"](p["project"]), str(p["n"]), str(p["passed"]), str(p["s4_fail"]), str(p["no_poc"]), "%.0f" % p["agent_min"], "$%.2f" % p["spend"]] for p in S["by_project"]]
    out.append(sec("By project", table(["Project", "Tasks", "Passed S1-S4", "S4 fail", "No PoC", "Mean agent min", "Cost"], prow) + '<p class="note">A random draw clusters on big projects (ffmpeg 12 including the task stopped in grading, ghostscript 10, mruby 7, binutils 7); the counts above are for the 99 graded tasks. Mruby: 0 passes, 6 of 7 no PoC, at the 90-minute limit on average; boringssl: 2 of 2 passed in 30 minutes on average.</p>', "projects"))
    out.append(sec("Per task (%d)" % len(tasks), "<p class=\"note\">Click a task for its full run: the prompt, every step and tool call, the PoC and the patch. S1 to S4 are the CyberGym grading stages. Minutes are agent time and whole-task time; cost is at the assumed price.</p>" + task_table(data, links, ctx), "tasks"))
    out.append(sec("Method, sources and caveats", "<ul style=\"margin:0;padding-left:1.1rem\"><li><b>Sample:</b> 100 tasks drawn by a seeded hash from the 915 tasks left after removing the five pilot tasks; two drawn tasks had an empty PoC file in the dataset (the runner's preflight rejects them) and were replaced by the next two in the order before the run; the 20 development tasks used to test the setup are not among them.</li>"
                   "<li><b>Setup:</b> Codex 0.118.0 in the benchmark's container, 1 attempt, 90-minute agent limit, 10 USD cap per run, a metering shim translating Codex's Responses calls into Chat Completions for Vertex (with handling for the model's occasionally truncated tool-call JSON, a 180-second silence limit and a 600-second total limit per call).</li>"
                   "<li><b>Not a ranking:</b> one model, one attempt per task, a random sample that includes heavy projects; failures include tasks where the agent found no crash within 90 minutes. Not comparable with the paper's numbers or with runs on other harnesses or servers.</li>"
                   "<li><b>Leaks:</b> <code>qpdf/oss-fuzz_42535152</code> has its PoC inside the source tree (the run still ended with no PoC). The file-modification-time marker on the bug's files, found in earlier work, was present in about 60 of the 100 tasks' source archives; it was not removed.</li>"
                   "<li><b>Costs</b> use an assumed price; <b>sampler</b> numbers are every 30 seconds, so short spikes can be missed.</li>"
                   "<li><b>Data:</b> the tables behind this page are in <code>wiki/syntheses/aws-vm-data/deepseek100/</code> in the repository; the raw trajectories, shim logs and database dump are kept outside the repository. Full write-up with the decisions taken: <code>wiki/syntheses/deepseek-100-task-run-report.md</code>.</li></ul>", "method"))
    out.append('<footer>Generated by tools/deepseek100_report.py from the run data; deterministic, static, no scripts.</footer>')
    out.append(ctx["TAIL"])
    return "".join(out)
