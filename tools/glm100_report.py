"""HTML for the "100 task run: GLM 5.3 Flash" section of the run viewer: the report page and the per-task table. Same look and chart code as deepseek100_report.py (imported), different content:
the run was stopped at 13:32 UTC, so 51 tasks have a valid result, 3 are void, 16 were killed in progress and 30 never started.

Reads the small tables in wiki/syntheses/aws-vm-data/glm-flash-r3/ (summary.json, per_task.csv, node_timeseries_15min.csv, shim_hourly.csv, extras.json, made by analyze_glm100.py and
analyze_glm100_extras.py). Pure functions: load(d), build_report(data, links, ctx), task_table(data, links, ctx); ctx supplies head, TAIL, chip, esc from build_viewer.
Static output: inline SVG, no scripts, no external requests.
"""
import csv, collections, datetime as dt, json, os
import deepseek100_report as base
from deepseek100_report import bars, histogram, lines, table, sec, fmt_d

base.NODE_COL = {"head": "var(--accent)", "worker A (…21.183)": "var(--pass)", "worker B (…29.158)": "#c27a00"}
START = dt.datetime(2026, 11, 10, 8, 9, 55)


def load(d):
    S = json.load(open(os.path.join(d, "summary.json")))
    num = lambda v: float(v) if v not in ("", "None", None) else None
    tasks = []
    for r in csv.DictReader(open(os.path.join(d, "per_task.csv"))):
        for k in ("agent_min", "total_min", "overhead_min", "requests", "errors", "calls_402", "calls_failed_stream", "calls_length", "call_secs_p50", "call_secs_max", "tokens_prompt", "fresh_in", "cached_in", "out_tok", "spend"):
            r[k] = num(r.get(k))
        r["hit_limit"] = r.get("hit_limit") == "True"
        tasks.append(r)
    series = list(csv.DictReader(open(os.path.join(d, "node_timeseries_15min.csv"))))
    shim = list(csv.DictReader(open(os.path.join(d, "shim_hourly.csv"))))
    ex = os.path.join(d, "extras.json")
    return dict(S=S, tasks=tasks, series=series, shim=shim, X=json.load(open(ex)) if os.path.exists(ex) else None)


STATUS_LABEL = {"void": "void: the stop cut its agent off", "interrupted": "killed in progress at 13:32", "not_started": "never started"}
FLAGS = {"qpdf/oss-fuzz_42535152": "PoC sits in the source tree (leak)"}


def task_flags(t):
    f = []
    if t["status"] in STATUS_LABEL: f.append(STATUS_LABEL[t["status"]])
    elif t["hit_limit"]: f.append("90-minute limit")
    if t["task"] in FLAGS and t["status"] not in STATUS_LABEL: f.append(FLAGS[t["task"]])
    if t.get("overhead_min") and t["overhead_min"] >= 60 and t["status"] not in STATUS_LABEL: f.append("grading %d min" % t["overhead_min"])
    return "; ".join(f)


def task_table(data, links, ctx):
    rows = []
    for t in sorted(data["tasks"], key=lambda t: t["task"]):
        lab = {"void": "void", "interrupted": "killed", "not_started": "not started"}.get(t["status"])
        stages = [lab] * 4 if lab else [t["s1"], t["s2"], t["s3"], t["s4"]]
        a = '<a href="%s">%s</a>' % (links[t["task"]], ctx["esc"](t["task"])) if t["task"] in links else ctx["esc"](t["task"])
        rows.append("<tr><td>%s</td><td><div class=\"chips\" style=\"flex-wrap:wrap\">%s</div></td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td>%s</td></tr>" % (
            a, "".join(ctx["chip"](s) for s in stages), ("%.0f" % t["agent_min"]) if t["agent_min"] else "-", ("%.0f" % t["total_min"]) if t["total_min"] else "-",
            fmt_d(t["requests"]) if t["requests"] else "-", ("$%.2f" % t["spend"]) if t["spend"] is not None and t["status"] not in STATUS_LABEL else "-", ctx["esc"]((t["host"] or "").replace("ip-172-31-", "…")), ctx["esc"](task_flags(t))))
    return ('<div class="tablewrap"><table class="runs"><colgroup><col style="width:20%"><col style="width:20%"><col style="width:7%"><col style="width:7%"><col style="width:7%"><col style="width:8%"><col style="width:9%"><col style="width:22%"></colgroup>'
            '<thead><tr><th>Task</th><th>S1 · S2 · S3 · S4</th><th>Agent min</th><th>Total min</th><th>Calls</th><th>Cost</th><th>Node</th><th>Flags</th></tr></thead><tbody>@@ROWS@@</tbody></table></div>').replace("@@ROWS@@", "".join(rows))


def build_report(data, links, ctx):
    S, tasks, series, X = data["S"], data["tasks"], data["series"], data.get("X")
    fin = [t for t in tasks if t["status"] in ("passed", "benchmark_failed")]
    R, sp, tk, sh = S["run"], S["spend"], S["tokens"], S["shim"]
    esc = ctx["esc"]; oc = S["outcomes"]
    s13 = oc.get("PASS S1-S4", 0) + oc.get("S4 fail", 0)
    out = [ctx["head"]("100 task run: GLM 5.3 Flash")]
    out.append('<div class="crumbs"><a href="index.html">Run viewer</a> › 100 task run: GLM 5.3 Flash</div>')
    out.append('<header><h1>100 task run: GLM 5.3 Flash <span class="badge">report</span></h1><p class="sub">CyberGym-E2E, the same 100 tasks as the DeepSeek run, end to end, Codex through OpenRouter (provider pinned to Z.AI), one attempt per task, '
               'the paper\'s limits (90 minutes of agent time, 10 USD per run), setup A grading. <b>Partial run: 51 tasks have a valid result, 49 do not</b> (a credit guard stopped the run at 13:32 UTC, then the account ran out of credit). 2026-11-10 08:09 to 13:32 UTC, 3 EC2 nodes.</p></header>')
    out.append('<nav class="jump"><a href="#glance">At a glance</a><a href="#happened">What happened</a><a href="#outcomes">Outcomes</a><a href="#time">Time</a><a href="#money">Money</a><a href="#calls">Model calls</a><a href="#nodes">Memory and CPU</a><a href="#extras">Fuzzers and grading</a><a href="#projects">By project</a><a href="#tasks">Per task</a><a href="#method">Method</a></nav>')
    facts = [("Tasks with a valid result", "%d of 100" % R["finished"]), ("Passed S1 to S4", "%d (%.0f%% of valid)" % (R["passed"], 100 * R["passed"] / R["finished"])), ("Passed S1 to S3 (the paper's rule)", "%d of %d (%.0f%%)" % (s13, R["finished"], 100 * s13 / R["finished"])),
             ("Void / killed in progress / never started", "%d / %d / %d" % (R["void"], R["interrupted"], R["not_started"])), ("Run time before the stop", "5 h 23 min wall"),
             ("Agent time, mean / median (valid)", "%.0f / %.0f min" % (S["agent_minutes"]["mean"], S["agent_minutes"]["median"])), ("At the 90-minute limit", "%d of %d (%.0f%%)" % (S["hit_limit"], R["finished"], 100 * S["hit_limit"] / R["finished"])),
             ("Cost of the valid tasks", "$%.2f" % sp["total"]), ("Cost per task, mean / max", "$%.2f / $%.2f" % (sp["mean"], sp["max"])), ("Cost per passing task (S1 to S4)", "$%.2f" % sp["cost_per_pass"]),
             ("Model calls of the valid tasks", fmt_d(tk["requests"])), ("Prompt tokens, fresh + cached", "%.2f billion" % ((tk["fresh"] + tk["cached"]) / 1e9)), ("Cached share of prompt tokens", "%.1f%%" % tk["cached_share"]),
             ("Output tokens", "%.1f million" % (tk["out"] / 1e6)), ("Task slots", "4 head + 6 + 6 workers = 16"), ("Grading", "setup A (shared images) for all %d graded tasks" % S["graded"])]
    out.append(sec("At a glance", '<dl class="facts">%s</dl>' % "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (a, b) for a, b in facts) +
                   '<p class="note">This is not a complete run. Treat the 51 results as a sample of the 100 (the first 51 to finish are biased towards tasks that ended early: passes and short failures finish sooner than tasks that run the full 90 minutes). Outcomes, cost and time below are for the 51 valid tasks only.</p>', "glance"))
    # what happened
    out.append(sec("What happened (four attempts, one set of results)", "<p>The 100 tasks were started four times in two days; only the third attempt produced results that are kept (plus 12 results from the first, which are not part of this page).</p>" +
                   table(["Attempt", "Start (UTC)", "What went wrong", "Result"], [
                       ["1", "11-09 17:54", "one agent container (mruby, hundreds of fuzzer processes) grew to about 50 GB on the head in under 3 minutes; Ray's memory monitor killed every task scheduled there, 76 queued tasks failed at once, both workers were declared dead; the container was never stopped and the head hung until a reboot", "12 tasks finished; the rest lost to infrastructure"],
                       ["2", "11-10 06:20", "the OpenRouter account ran out of credit: every request was refused with HTTP 402, each new task gave up after about 7 seconds and was recorded as no PoC or no patch; 39 such results; stopped by hand at 07:10", "all results void (spend about $10)"],
                       ["3", "11-10 08:09", "limits added (40 GB and 2,048 processes per container, a janitor, an apt mirror); ran 5 h 23 min; a credit guard then stopped the driver on a burst of HTTP 402 (<code>in_flight_budget_exhausted</code>: OpenRouter's cap on the credit reserved by requests in flight), killing the 16 tasks in progress; 3 tasks recorded as finished at that moment had been cut off", "<b>51 valid results</b>, 3 void, 16 killed, 30 not started"],
                       ["4", "11-10 15:16", "OpenRouter refused agent-size requests (<code>limit_source: openrouter_credits</code>, balance about $0.04); stopped after a minute", "nothing kept"]]) +
                   "<p class=\"note\">The memory limit and the janitor worked: the largest container of attempt 3 held %.1f GB (cap 40 GB), no node came near the 58.7 GB at which Ray kills tasks, and no container was killed for memory. The credit problems were not the harness's: the account's balance was drawn down (partly by other use of the same account), and the limit that applied was OpenRouter's. Details and timeline: <code>wiki/syntheses/glm-5.3-flash-100-task-run.md</code>.</p>" % S["top_containers_gb"][0][0], "happened"))
    # outcomes
    order = ["PASS S1-S4", "S4 fail", "S2 fail", "S1 fail", "no PoC", "no patch"]
    cols = {"PASS S1-S4": "var(--pass)", "S4 fail": "var(--accent)", "S2 fail": "var(--skip)", "S1 fail": "var(--skip)", "no PoC": "var(--fail)", "no patch": "#c27a00"}
    def stage_n(i, v="passed"): return sum(1 for t in fin if t["s%d" % i] == v)
    funnel = [("S1 PoC crashes the vulnerable build", stage_n(1)), ("S2 patch stops that crash", stage_n(2)), ("S3 other checks", stage_n(3)), ("S4 intended bug fixed", stage_n(4))]
    out.append(sec("Outcomes (51 valid tasks)", bars([(k, oc.get(k, 0), cols[k]) for k in order], label_w=120) +
                   '<p class="note">S4 fail: PoC and patch passed S1 to S3 (the paper\'s success criterion) but the patch does not fix the benchmark\'s own crash. By the paper\'s S1+S2+S3 rule <b>%d of %d</b> valid tasks succeed. <b>No patch</b> is the largest group (%d): the agent ran out of time with a PoC it could not turn into a patch, or never found a crash; the harness then skips every stage.</p>' % (s13, R["finished"], oc.get("no patch", 0)) +
                   '<h3 class="task">Stage funnel (tasks that passed each stage)</h3>' + bars([(a, b) for a, b in funnel], label_w=260) +
                   '<h3 class="task">By task kind</h3>' + table(["Kind", "Tasks", "Passed S1-S4", "No PoC", "S4 fail", "Cost"], [list(map(str, [k["kind"], k["n"], k["passed"], k["no_poc"], k["s4_fail"], "$%.2f" % k["spend"]])) for k in S["by_kind"]]) +
                   '<p class="note">Counts are small, so differences between kinds are not reliable.</p>', "outcomes"))
    # time
    am = [t["agent_min"] for t in fin]; ov = [t["overhead_min"] for t in fin if t["overhead_min"] is not None]; g = S["grading"]["graded_overhead"]
    done = sorted(dt.datetime.fromisoformat(t["finished"].replace("+00:00", "")) for t in fin if t["finished"])
    hours_f = collections.Counter(int((d - START).total_seconds() // 3600) for d in done)
    out.append(sec("Time", "<p>Each task has three phases: setup (container start, build preparation, Codex install), <b>the agent's run, capped at 90 minutes</b>, then <b>grading</b> (S1 to S4). The cap holds: the longest agent run of the %d valid tasks is %.1f minutes.</p>" % (R["finished"], max(am)) +
                   "<h3 class=\"task\">Agent minutes per task</h3>" + histogram(am, list(range(0, 100, 10)) + [100], xlabel="agent minutes (bin start)", vline=90) +
                   '<p class="note">%d of %d valid tasks (%.0f%%) ran the full 90 minutes (the DeepSeek run: 61 of 99). The %d that passed all four stages took %.0f minutes on average (median %.0f); %d of them used the full time.</p>' % (S["hit_limit"], R["finished"], 100 * S["hit_limit"] / R["finished"], R["passed"], S["pass_by_limit"]["passed_agent_min"]["mean"], S["pass_by_limit"]["passed_agent_min"]["median"], S["pass_by_limit"]["passed_at_limit"]) +
                   '<h3 class="task">Where the %.0f task-hours went</h3>' % S["task_hours"]["total"] + bars([("agent run", S["task_hours"]["agent"], "var(--accent)"), ("setup and grading", S["task_hours"]["outside_agent"], "#c27a00")], fmt="%.1f h", label_w=150) +
                   "<h3 class=\"task\">Grading</h3><p><b>%d of %d</b> valid tasks were never graded (no PoC or no patch: the harness skips every stage); <b>%d</b> were graded, all of them with setup A's shared images (prepare once, build the patched tree once, each stage in a fresh container from the saved images). Time outside the agent for graded tasks: median %.0f, mean %.0f, 90th percentile %.0f, maximum %.0f minutes; %.1f slot-hours in all.</p>" % (S["not_graded"], R["finished"], S["graded"], g["median"], g["mean"], g["p90"], g["max"], (X or {}).get("grading", {}).get("slot_hours", 0)) +
                   table(["Setup + grading time (minutes outside the agent run)", "Tasks (of %d)" % len(ov)], [[lab, str(sum(1 for v in ov if lo <= v < (hi or 1e9)))] for lab, lo, hi in (("under 5", 0, 5), ("5 to 15", 5, 15), ("15 to 30", 15, 30), ("30 to 60", 30, 60), ("1 to 2 hours", 60, 120), ("over 2 hours", 120, 0))]) +
                   "<h3 class=\"task\">Valid tasks finished per hour since the start (08:09:55 UTC)</h3>" + bars([("hour %d" % (h + 1), hours_f.get(h, 0)) for h in range(0, 6)], label_w=90) +
                   '<p class="note">The first agents reach their 90-minute cap at about 09:40, so almost everything finishes after the second hour; the run stopped 5 h 23 min in, with 16 tasks (8.1 task-hours) in progress. Three head tasks also spent about 97 minutes in container teardown after their agents had finished (see the run log); they are among the longest wall times.</p>', "time"))
    # money
    spend = [t["spend"] for t in fin if t["spend"] is not None]
    top = sorted(fin, key=lambda t: -(t["spend"] or 0))[:10]
    out.append(sec("Money", "<p>Price (OpenRouter's list for the Z.AI endpoint): 0.15 USD per million fresh input tokens, 0.03 cached, 0.50 output. Per-run cap 10 USD; <b>no task came near it</b> (maximum $%.2f, %d tasks above $5). Costs are the shim's own count per task.</p>" % (sp["max"], sp["over_5"]) +
                   histogram(spend, [0, 1, 2, 3, 4, 5, 6, 7, 8, 10], xlabel="cost per task, USD (bin start)", color="#c27a00", vline=None, fmt_edge="%g") +
                   table(["Outcome", "Tasks", "Mean cost", "Total cost"], [[k, str(oc.get(k, 0)), "$%.2f" % sp["by_outcome"][k], "$%.2f" % sp["total_by_outcome"][k]] for k in order if k in sp["by_outcome"]]) +
                   "<p>Total <b>$%.2f</b> for %d valid tasks (mean $%.2f, median $%.2f). Passing tasks are cheap (mean $%.2f); the money goes to tasks that run the full time without a result (<b>no patch: $%.2f, %.0f%% of the total</b>). Cost per passing task (S1 to S4): $%.2f.</p>" % (sp["total"], R["finished"], sp["mean"], sp["median"], sp["by_outcome"].get("PASS S1-S4", 0), sp["total_by_outcome"].get("no patch", 0), 100 * sp["total_by_outcome"].get("no patch", 0) / sp["total"], sp["cost_per_pass"]) +
                   "<p>Tokens: %.0f million fresh prompt tokens, <b>%.0f million cached (%.1f%% cached)</b>, %.1f million output, over %s calls: on average %s prompt tokens and %s output tokens per call and %.0f calls per task (median %.0f, maximum %s). The cache share is far higher than in the DeepSeek run (56%%): Z.AI reuses the whole growing prompt.</p>" % (tk["fresh"] / 1e6, tk["cached"] / 1e6, tk["cached_share"], tk["out"] / 1e6, fmt_d(tk["requests"]), fmt_d(S["prompt_tokens_per_call_mean"]), S["out_tokens_per_call_mean"], S["calls_per_task"]["mean"], S["calls_per_task"]["median"], fmt_d(S["calls_per_task"]["max"])) +
                   "<h3 class=\"task\">Ten most expensive tasks</h3>" + table(["Task", "Outcome", "Cost", "Agent min", "Calls"], [[esc(t["task"]), t["outcome"], "$%.2f" % t["spend"], "%.0f" % t["agent_min"], fmt_d(t["requests"])] for t in top]) +
                   "<p><b>What the whole attempt cost:</b> the key used for attempt 3 shows $160.52 of usage, of which $%.2f belongs to the %d valid tasks, $%.2f to the %d void ones and about $20 to the 16 killed in progress. Attempts 1 and 2 (earlier key) cost about $59.5. The study's OpenRouter total across both keys was about $220 at the time of writing.</p>" % (sp["total"], R["finished"], sp["void_tasks"], R["void"]) +
                   '<p class="note">Compute (EC2) is separate. The OpenRouter account balance that eventually stopped the work is not part of these numbers.</p>', "money"))
    # calls
    ex = X["model_calls"] if X else {}
    out.append(sec("Model calls", "<p>Source: the shim's per-call log on the <b>head only</b>. The two workers' logs were lost when the workers were scaled down, so call-level figures cover the %s calls of the head's tasks (%d tasks, valid and killed); per-task totals for all tasks come from the shim's per-key count and are used everywhere else on this page. Of the head's calls %s returned 200 and <b>%d returned HTTP 402</b> (almost all in the last minutes before the stop). Every answered call was served by Z.AI (the provider pin held; no fallback). %d streams failed. "
                   "Latency per call: median %.1f s, 90th percentile %.1f s, 99th percentile %.1f s, maximum %.0f s.</p>" % (fmt_d(sh["calls"]), ex.get("tasks", 16), fmt_d(sh["http_200"]), sh["http_402"], sh["failed_streams"], sh["secs_p50"], sh["secs_p90"], sh["secs_p99"], sh["secs_max"]) +
                   table(["Hour (UTC, Nov 10)", "Calls", "HTTP 402", "Failed streams", "Median s", "90th pct s", "Calls over 590 s"], [[r["hour_utc"][-2:] + ":00", fmt_d(float(r["calls"])), r["http_402"], r["failed_streams"], r["secs_p50"], r["secs_p90"], r["calls_over_590s"]] for r in data["shim"]]) +
                   "<p class=\"note\">Finish reasons: %s. <b>Runaway reasoning:</b> %d calls on the head hit the model's output maximum of 131,072 tokens with reasoning only and no answer (%.1f hours in those calls, 1,844 s and 2,067 s each); the shim has no per-call limit for OpenRouter (the DeepSeek run had 180 s of silence and 600 s per call), so such a call runs to the maximum. %d calls had a prompt of over 200,000 tokens and no cached tokens (probably Codex's context-compaction request); the long calls cluster there.</p>" % (", ".join("%s %s" % (k, fmt_d(v)) for k, v in sh["finish"].items()), ex.get("calls_hit_output_maximum", 0), ex.get("hours_in_output_maximum_calls", 0), ex.get("cache_zero_large_prompt_calls", 0)), "calls"))
    # nodes
    names = ["head", "worker A (…21.183)", "worker B (…29.158)"]
    bks = sorted({r["bucket_start_utc"] for r in series}); idx = {b: i for i, b in enumerate(bks)}; times = [b[11:16] for b in bks]
    ser_mem = {n: [(idx[r["bucket_start_utc"]], float(r["mem_used_max_gb"])) for r in series if r["node"] == n] for n in names}
    ser_load = {n: [(idx[r["bucket_start_utc"]], float(r["load1_max"])) for r in series if r["node"] == n] for n in names}
    nrows = [[n, "%d" % S["nodes"][n]["samples"], "%.1f" % S["nodes"][n]["mem_used_avg"], "%.1f" % S["nodes"][n]["mem_used_p99"], "%.1f" % S["nodes"][n]["mem_used_max"], "%.1f" % S["nodes"][n]["mem_avail_min"],
              "%.0f / %.0f / %.0f / %.0f" % (S["nodes"][n]["load_avg"], S["nodes"][n]["load_p50"], S["nodes"][n]["load_p90"], S["nodes"][n]["load_max"]), "%.0f%% / %.0f%%" % (S["nodes"][n]["pct_load_over_16"], S["nodes"][n]["pct_load_over_32"])] for n in names]
    out.append(sec("Memory and CPU", "<p>Each node is an <code>m7i.4xlarge</code>: 16 vCPU and about 62 GB of RAM, no swap. <b>Every container was limited to 40 GB and 2,048 processes in this attempt</b> (not in the DeepSeek run), and a janitor stopped containers outliving their task. A sampler on every node wrote memory, load and the largest containers every 30 seconds to the shared database. Ray's memory monitor kills task processes at about 58.7 GB used.</p>" +
                   "<h3 class=\"task\">Memory used, maximum per 15 minutes (GB)</h3>" + lines(ser_mem, 64, [(58.7, "Ray kill threshold 58.7 GB", "var(--fail)")], ylabel="GB", times=times) +
                   "<h3 class=\"task\">Load average (1 min), maximum per 15 minutes</h3>" + lines(ser_load, 90, [(16, "16 cores", "var(--muted)")], ylabel="load", times=times) +
                   table(["Node", "Samples", "Mem used avg GB", "p99 GB", "Max GB", "Lowest free GB", "Load avg / median / p90 / max", "Samples over 16 / over 32"], nrows) +
                   "<p><b>Memory stayed far below the kill threshold:</b> the highest reading on any node is %.1f GB (head %.1f, worker A %.1f, worker B %.1f); the lowest free memory is %.1f GB. CPU load went above the 16 cores in %.0f%% / %.0f%% / %.0f%% of the samples of the head / worker A / worker B.</p>" % (max(S["nodes"][n]["mem_used_max"] for n in names), S["nodes"]["head"]["mem_used_max"], S["nodes"][names[1]]["mem_used_max"], S["nodes"][names[2]]["mem_used_max"], min(S["nodes"][n]["mem_avail_min"] for n in names), S["nodes"]["head"]["pct_load_over_16"], S["nodes"][names[1]]["pct_load_over_16"], S["nodes"][names[2]]["pct_load_over_16"]) +
                   "<h3 class=\"task\">Largest single containers seen (GB of RAM)</h3>" + table(["Container peak", "Node", "Container"], [["%.1f" % c[0], c[1], c[2]] for c in S["top_containers_gb"]]) +
                   "<p class=\"note\">The largest container (%.1f GB) was under the 40 GB cap; the DeepSeek run's largest was 23 GB without a cap. The runaway of attempt 1 reached about 60 GB in a node without limits. The sampler cannot see short spikes (30-second samples).</p>" % S["top_containers_gb"][0][0], "nodes"))
    # extras
    if X:
        fz, sv, gr = X["fuzzers"], X["self_validation"], X["grading"]
        out.append(sec("Fuzzers and grading", "<h3 class=\"task\">Fuzzers</h3><p><b>%d of %d valid agents ran a fuzzer at least once</b> (%d with parallel workers or AFL); fuzzer commands are %.1f%% of all %s commands. %d of the %d tasks at the 90-minute limit ran one, %d of the %d with no PoC, and %d of the %d passing tasks. In this sample parallel fuzzing was rare, so it does not explain the attempt-1 runaway on its own (the agent's commands in that task were not saved).</p>" % (
                       fz["ran_fuzzer"], fz["tasks"], fz["ran_parallel_or_afl"], 100 * fz["fuzzer_commands"] / fz["commands"], fmt_d(fz["commands"]), fz["at_limit_ran_fuzzer"], fz["at_limit"], fz["no_poc_ran_fuzzer"], fz["no_poc_tasks"], fz["pass_ran_fuzzer"], fz["pass_tasks"]) +
                       "<h3 class=\"task\">Self-validation</h3><p>The prompt tells the agent to check its work with CyberGym's <code>validate.py</code>: %d of %d agents ran it, %d times in all (%.1f per task, at most %d; %.1f%% of their commands), inside the agent's 90 minutes.</p>" % (sv["tasks_that_ran_validate_py"], fz["tasks"], sv["runs"], sv["mean_per_task"], sv["max_per_task"], sv["share_of_commands"]) +
                       "<h3 class=\"task\">Official grading with setup A</h3><p>All %d graded tasks used the shared-image path (<code>validation_mode: shared</code> in each summary): the project is prepared once, the patched tree built once, and S2, S3 and S4 each run in a fresh container from the saved image. Mean time outside the agent run for graded tasks %.1f minutes, maximum %.0f; %.1f slot-hours in all. No stage disagreed with a standard grading in the pre-run checks (13 inputs, all statuses identical).</p>" % (gr["graded"], gr["overhead_min_mean"], gr["overhead_min_max"], gr["slot_hours"]), "extras"))
    prow = [[esc(p["project"]), str(p["n"]), str(p["passed"]), str(p["s4_fail"]), str(p["no_poc"]), "%.0f" % p["agent_min"], "$%.2f" % p["spend"]] for p in S["by_project"]]
    out.append(sec("By project", table(["Project", "Tasks", "Passed S1-S4", "S4 fail", "No PoC", "Mean agent min", "Cost"], prow) + '<p class="note">Counts are for the 51 valid tasks; with a partial sample the project counts are small and uneven.</p>', "projects"))
    out.append(sec("Per task (%d)" % len(tasks), "<p class=\"note\">Click a task for its full run (valid and void tasks that have a saved trajectory). Tasks marked killed or never started have no result. S1 to S4 are the CyberGym grading stages. Minutes are agent time and whole-task time; cost is the shim's count.</p>" + task_table(data, links, ctx), "tasks"))
    out.append(sec("Method, sources and caveats", "<ul style=\"margin:0;padding-left:1.1rem\"><li><b>Tasks:</b> the same 100 as the DeepSeek run (a seeded draw), dispatched in the same order. <b>Valid</b> = a result recorded by a task that ran to the end of its own limits. <b>Void</b> = recorded when the driver was stopped but cut off mid-run (20, 41 and 32 minutes of agent time): <code>readstat/oss-fuzz_420198855</code>, <code>mruby/oss-fuzz_440058794</code>, <code>libavc/arvo_58190</code>. Killed and never-started tasks have no result.</li>"
                   "<li><b>Setup:</b> Codex 0.118.0 in the benchmark's container, 1 attempt, 90-minute agent limit, 10 USD cap per run, harness commit d0ae0f0 with local patches (OpenAI-compatible provider, setup A grading, container limits of 40 GB and 2,048 processes, an apt mirror because archive.ubuntu.com was slow, a janitor). Model <code>z-ai/glm-5.3-flash</code> on OpenRouter pinned to Z.AI (fp8, 1M context) with fallbacks off, through a metering shim that translates Codex's Responses calls into Chat Completions; no per-call time limit.</li>"
                   "<li><b>Not a ranking:</b> one model, one attempt per task, a partial and biased sample of 51 tasks. Not comparable with the paper's numbers, and only loosely with the DeepSeek run (different model, price list, grading path, limits on containers, and a partial set).</li>"
                   "<li><b>Costs</b> are the shim's own count at OpenRouter's list price; <b>sampler</b> numbers are every 30 seconds; call-level figures are the head's only.</li>"
                   "<li><b>Data:</b> the tables behind this page are in <code>wiki/syntheses/aws-vm-data/glm-flash-r3/</code>; trajectories come from the database dump kept outside the repository. Full write-up: <code>wiki/syntheses/glm-5.3-flash-100-task-run.md</code>.</li></ul>", "method"))
    out.append('<footer>Generated by tools/glm100_report.py from the run data; deterministic, static, no scripts.</footer>')
    out.append(ctx["TAIL"])
    return "".join(out)
