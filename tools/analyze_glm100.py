#!/usr/bin/env python3
"""Aggregate the raw data of the GLM 5.3 Flash run (run 3 of 2026-11-10, setup A, OpenRouter pinned to Z.AI) into the numbers used by the report, in the same shape as
analyze_deepseek100.py produces for the DeepSeek run.

Inputs (outside git, from the head VM export, see wiki/syntheses/glm-5.3-flash-100-task-run.md section 9): <export>/run3_executions.jsonl, run3_node_metrics.csv, run3_head_shim.jsonl,
run3_driver.log, runs/<execution id>/upstream/<task>/<ts>_e2e/{summary.json,trajectory/attempt_1.log}.
Differences from the DeepSeek analysis, all stated in the report: the run was stopped by a credit guard at 13:32:39 UTC (16 tasks were killed in progress, 30 never started); three tasks
recorded as finished at that moment are void (the stop cut their agents off); the workers' shim logs were lost with the workers, so per-call figures come from the head's shim only; prices are
OpenRouter's list prices for z-ai/fp8 (0.15 fresh, 0.03 cached, 0.50 output USD per million tokens), and per-task spend is the shim's own count.
usage: analyze_glm100.py <export folder> <out folder>
"""
import csv, collections, datetime as dt, json, os, re, statistics as st, sys

EXP, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
PRICE = (0.15, 0.03, 0.50)
VOID = {"readstat/oss-fuzz_420198855", "mruby/oss-fuzz_440058794", "libavc/arvo_58190"}
NODES = {"ip-172-31-22-187": "head", "ip-172-31-21-183": "worker A (…21.183)", "ip-172-31-29-158": "worker B (…29.158)"}
START, STOP = "2026-11-10T08:09:55Z", "2026-11-10T13:32:39Z"


def pct(xs, p):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else None


def agg(xs): return dict(n=len(xs), mean=round(st.mean(xs), 1), median=round(st.median(xs), 1), p90=round(pct(xs, .9), 1), max=round(max(xs), 1)) if xs else {}


def tparse(s): return dt.datetime.fromisoformat(s).astimezone(dt.timezone.utc).replace(tzinfo=None) if s else None


# ---------------------------------------------------------------- per task
rows = [json.loads(l) for l in open(os.path.join(EXP, "run3_executions.jsonl"))]
tasks = []
for r in rows:
    res = r.get("result") or {}
    u = res.get("usage") or {}
    st_ = [res.get("stage%d" % i) for i in (1, 2, 3, 4)]
    ran = sum(1 for s in st_ if s in ("passed", "failed", "error"))
    dur = res.get("duration_seconds"); ag = res.get("agent_exec_seconds")
    if r["status"] in ("passed", "benchmark_failed"):
        status = "void" if r["task"] in VOID else r["status"]
    else:
        status = {"running": "interrupted", "pending": "not_started"}.get(r["status"], r["status"])
    t = dict(task=r["task"], project=r["task"].split("/")[0], kind="arvo" if "/arvo_" in r["task"] else "oss-fuzz", host=NODES.get(r["hostname"], r["hostname"] or ""), status=status,
             s1=st_[0], s2=st_[1], s3=st_[2], s4=st_[3], stages_run=ran, execution_id=r["execution_id"],
             agent_min=round(ag / 60, 1) if ag else None, total_min=round(dur / 60, 1) if dur else None,
             requests=u.get("requests"), errors=u.get("errors"), fresh_in=u.get("input_tokens"), cached_in=u.get("cache_read_tokens"), out_tok=u.get("output_tokens"), spend=u.get("spend"),
             started=r["started_at"], finished=r["finished_at"])
    if t["total_min"] and t["agent_min"]:
        t["overhead_min"] = round(t["total_min"] - t["agent_min"], 1)
    tasks.append(t)
fin = [t for t in tasks if t["status"] in ("passed", "benchmark_failed")]          # valid results
for t in tasks:
    t["hit_limit"] = bool(t["agent_min"] and t["agent_min"] >= 89.9)
    if t in fin:
        t["outcome"] = ("PASS S1-S4" if t["status"] == "passed" else "no PoC" if t["s1"] == "no_poc" else "no patch" if t["s3"] == "no_patch" else
                        "S4 fail" if (t["s1"], t["s2"], t["s3"]) == ("passed", "passed", "passed") and t["s4"] in ("failed", "error") else "S1 fail" if t["s1"] == "failed" else
                        "S2 fail" if t["s1"] == "passed" and t["s2"] in ("failed", "error") else "other")
    else:
        t["outcome"] = {"void": "void (cut off)", "interrupted": "not finished (killed)", "not_started": "not started"}.get(t["status"], t["status"])
    t["tokens_prompt"] = (t["fresh_in"] or 0) + (t["cached_in"] or 0)
    t["spend_check"] = round(((t["fresh_in"] or 0) * PRICE[0] + (t["cached_in"] or 0) * PRICE[1] + (t["out_tok"] or 0) * PRICE[2]) / 1e6, 4) if t["fresh_in"] is not None else None

# ---------------------------------------------------------------- the head's shim (per call; the workers' logs were lost)
calls = []
for l in open(os.path.join(EXP, "run3_head_shim.jsonl")):
    try: j = json.loads(l)
    except ValueError: continue
    if j.get("event") == "messages": calls.append(j)
by_exec = collections.defaultdict(list)
for c in calls: by_exec[c["alias"]].append(c)
for t in tasks:
    cs = by_exec.get(t["execution_id"], [])
    t["shim_calls"] = len(cs) or None
    t["calls_402"] = sum(1 for c in cs if c.get("status") == 402) if cs else None
    t["calls_failed_stream"] = sum(1 for c in cs if c.get("stream_failed")) if cs else None
    t["calls_length"] = sum(1 for c in cs if c.get("finish") == "length") if cs else None
    t["call_secs_p50"] = round(st.median([c["secs"] for c in cs]), 1) if cs else None
    t["call_secs_max"] = round(max([c["secs"] for c in cs]), 1) if cs else None
ok_calls = [c for c in calls if c.get("status") == 200]
long_calls = sorted(((c["secs"], c["alias"], c.get("finish"), c.get("out_tok")) for c in calls if c["secs"] >= 120), reverse=True)

# ---------------------------------------------------------------- node time series (the sampler, every 30 s)
ts = collections.defaultdict(lambda: collections.defaultdict(list))
ctr_peaks = collections.defaultdict(float)
for node, t_, metric, value in list(csv.reader(open(os.path.join(EXP, "run3_node_metrics.csv"))))[1:]:
    if node not in NODES: continue
    v = float(value); tt = tparse(t_)
    b = tt.replace(minute=(tt.minute // 15) * 15, second=0, microsecond=0)
    if metric.startswith("ctr_mem_gb:"):
        ctr_peaks[(node, metric[11:])] = max(ctr_peaks[(node, metric[11:])], v); continue
    ts[(node, b)][metric].append(v)
with open(os.path.join(OUT, "node_timeseries_15min.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["bucket_start_utc", "node", "mem_used_avg_gb", "mem_used_max_gb", "mem_avail_min_gb", "load1_avg", "load1_max", "containers_avg"])
    for (node, b), m in sorted(ts.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if not m.get("mem_used_gb"): continue
        w.writerow([b.strftime("%Y-%m-%dT%H:%M"), NODES[node], round(st.mean(m["mem_used_gb"]), 1), round(max(m["mem_used_gb"]), 1), round(min(m["mem_avail_gb"]), 1),
                    round(st.mean(m["load1"]), 1), round(max(m["load1"]), 1), round(st.mean(m["containers"]), 1)])
allm = collections.defaultdict(lambda: collections.defaultdict(list))
for (node, b), m in ts.items():
    for k, v in m.items(): allm[node][k] += v
node_stats = {}
for node in NODES:
    a = allm[node]
    if not a.get("mem_used_gb"): continue
    node_stats[NODES[node]] = dict(samples=len(a["mem_used_gb"]), mem_used_avg=round(st.mean(a["mem_used_gb"]), 1), mem_used_p99=round(pct(a["mem_used_gb"], .99), 1), mem_used_max=round(max(a["mem_used_gb"]), 1),
        mem_avail_min=round(min(a["mem_avail_gb"]), 1), load_avg=round(st.mean(a["load1"]), 1), load_p50=round(st.median(a["load1"]), 0), load_p90=round(pct(a["load1"], .9), 0), load_max=round(max(a["load1"]), 0),
        pct_load_over_16=round(100 * sum(1 for x in a["load1"] if x > 16) / len(a["load1"]), 1), pct_load_over_32=round(100 * sum(1 for x in a["load1"] if x > 32) / len(a["load1"]), 1), containers_avg=round(st.mean(a["containers"]), 1))
top_ctr = sorted(((v, NODES[n], c) for (n, c), v in ctr_peaks.items()), reverse=True)[:8]

# ---------------------------------------------------------------- autoscaler events (the driver log carries Ray's autoscaler lines)
events = []
for l in open(os.path.join(EXP, "run3_driver.log"), errors="replace"):
    m = re.search(r"\(autoscaler \+([0-9hms]+)\)\S*\s*(.*)", re.sub(r"\x1b\[[0-9;]*m", "", l))
    if m and "Tip:" not in m.group(2): events.append(["+" + m.group(1), m.group(2).strip()[:140]])
ev_counts = collections.Counter(re.sub(r"\d+ ", "N ", e[1])[:60] for e in events)

# ---------------------------------------------------------------- grading mode of setup A (from each run's summary.json)
modes = collections.Counter()
root = os.path.join(EXP, "runs")
for t in fin:
    for dp, dn, fn in os.walk(os.path.join(root, t["execution_id"])):
        if "summary.json" in fn and "upstream" in dp:
            a = (json.load(open(os.path.join(dp, "summary.json"))).get("attempts") or [{}])[-1]
            t["validation_mode"] = a.get("validation_mode"); modes[str(a.get("validation_mode"))] += 1

# ---------------------------------------------------------------- summary
spend = [t["spend"] for t in fin if t["spend"] is not None]
lost = [t for t in tasks if t["status"] == "interrupted"]
S = dict(
    run=dict(start_utc=START, end_utc=STOP, tasks=len(tasks), finished=len(fin), void=len([t for t in tasks if t["status"] == "void"]), interrupted=len(lost),
             not_started=len([t for t in tasks if t["status"] == "not_started"]), passed=sum(1 for t in fin if t["status"] == "passed")),
    outcomes=dict(collections.Counter(t["outcome"] for t in fin)),
    stage_patterns=[[list(k), v] for k, v in collections.Counter((t["s1"], t["s2"], t["s3"], t["s4"]) for t in fin).most_common()],
    agent_minutes=agg([t["agent_min"] for t in fin if t["agent_min"]]), hit_limit=sum(1 for t in fin if t["hit_limit"]), agent_max_seconds=max((t["agent_min"] for t in fin if t["agent_min"]), default=0) * 60,
    total_minutes=agg([t["total_min"] for t in fin if t["total_min"]]), overhead_minutes_all=agg([t["overhead_min"] for t in fin if t.get("overhead_min") is not None]),
    graded=sum(1 for t in fin if t["stages_run"] > 0), not_graded=sum(1 for t in fin if t["stages_run"] == 0),
    task_hours=dict(total=round(sum(t["total_min"] for t in fin) / 60, 1), agent=round(sum(t["agent_min"] for t in fin) / 60, 1), outside_agent=round(sum(t.get("overhead_min") or 0 for t in fin) / 60, 1)),
    spend=dict(total=round(sum(spend), 2), mean=round(st.mean(spend), 2), median=round(st.median(spend), 2), p90=round(pct(spend, .9), 2), max=round(max(spend), 2), over_5=sum(1 for s in spend if s > 5),
               over_8=sum(1 for s in spend if s > 8), over_10=sum(1 for s in spend if s > 10),
               by_outcome={k: round(st.mean([t["spend"] for t in fin if t["outcome"] == k]), 2) for k in sorted({t["outcome"] for t in fin})},
               total_by_outcome={k: round(sum(t["spend"] for t in fin if t["outcome"] == k), 2) for k in sorted({t["outcome"] for t in fin})},
               cost_per_pass=round(sum(spend) / max(1, sum(1 for t in fin if t["status"] == "passed")), 2),
               void_tasks=round(sum(t["spend"] or 0 for t in tasks if t["status"] == "void"), 2)),
    tokens=dict(fresh=sum(t["fresh_in"] or 0 for t in fin), cached=sum(t["cached_in"] or 0 for t in fin), out=sum(t["out_tok"] or 0 for t in fin), requests=sum(t["requests"] or 0 for t in fin),
                cached_share=round(100 * sum(t["cached_in"] or 0 for t in fin) / max(1, sum(t["tokens_prompt"] for t in fin)), 1)),
    calls_per_task=agg([t["requests"] for t in fin if t["requests"]]),
    prompt_tokens_per_call_mean=round(sum(t["tokens_prompt"] for t in fin) / max(1, sum(t["requests"] or 0 for t in fin))),
    out_tokens_per_call_mean=round(sum(t["out_tok"] or 0 for t in fin) / max(1, sum(t["requests"] or 0 for t in fin))),
    shim=dict(scope="the head's shim only (the workers' logs were lost with the workers)", calls=len(calls), http_200=len(ok_calls), http_402=sum(1 for c in calls if c.get("status") == 402),
              failed_streams=sum(1 for c in calls if c.get("stream_failed")), over_120s=len(long_calls), calls_length=sum(1 for c in calls if c.get("finish") == "length"),
              secs_p50=round(st.median([c["secs"] for c in calls]), 1), secs_p90=round(pct([c["secs"] for c in calls], .9), 1), secs_p99=round(pct([c["secs"] for c in calls], .99), 1),
              secs_max=round(max(c["secs"] for c in calls), 1), finish=dict(collections.Counter(str(c.get("finish")) for c in calls)), providers=dict(collections.Counter(str(c.get("provider")) for c in calls)),
              long_calls=[[round(s, 0), a[:8], f, o] for s, a, f, o in long_calls[:10]]),
    nodes=node_stats, top_containers_gb=[[round(v, 1), n, c] for v, n, c in top_ctr], autoscaler_event_counts=dict(ev_counts.most_common(12)), autoscaler_events=events[:40],
    by_project=[dict(project=p, n=len(xs), passed=sum(1 for t in xs if t["status"] == "passed"), s4_fail=sum(1 for t in xs if t["outcome"] == "S4 fail"), no_poc=sum(1 for t in xs if t["outcome"] == "no PoC"),
                     agent_min=round(st.mean([t["agent_min"] for t in xs]), 0), spend=round(sum(t["spend"] for t in xs), 2)) for p, xs in sorted({p: [t for t in fin if t["project"] == p] for p in {t["project"] for t in fin}}.items(), key=lambda kv: -len(kv[1]))],
    by_kind=[dict(kind=k, n=len(xs), passed=sum(1 for t in xs if t["status"] == "passed"), no_poc=sum(1 for t in xs if t["outcome"] == "no PoC"), s4_fail=sum(1 for t in xs if t["outcome"] == "S4 fail"),
                  spend=round(sum(t["spend"] for t in xs), 2)) for k, xs in ((k, [t for t in fin if t["kind"] == k]) for k in sorted({t["kind"] for t in fin}))],
    by_host=[dict(host=h, n=len(xs), passed=sum(1 for t in xs if t["status"] == "passed"), agent_min=round(st.mean([t["agent_min"] for t in xs]), 0), overhead_min=round(st.mean([t.get("overhead_min") or 0 for t in xs]), 1))
             for h, xs in ((h, [t for t in fin if t["host"] == h]) for h in sorted({t["host"] for t in fin}))],
    grading=dict(graded_overhead=agg([t["overhead_min"] for t in fin if t["stages_run"] > 0]), validation_modes=dict(modes),
                 ffmpeg_graded=[[t["task"], t["overhead_min"]] for t in fin if t["project"] == "ffmpeg" and t["stages_run"] > 0]),
    pass_by_limit=dict(passed_at_limit=sum(1 for t in fin if t["status"] == "passed" and t["hit_limit"]), passed_agent_min=agg([t["agent_min"] for t in fin if t["status"] == "passed"])),
    lost=dict(tasks=len(lost), hours_elapsed=round(sum((dt.datetime(2026, 11, 10, 13, 32, 39) - tparse(t["started"])).total_seconds() for t in lost if t["started"]) / 3600, 1)),
)
json.dump(S, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
fields = ["task", "project", "kind", "host", "status", "outcome", "s1", "s2", "s3", "s4", "stages_run", "agent_min", "total_min", "overhead_min", "hit_limit", "requests", "errors", "calls_402", "calls_failed_stream",
          "calls_length", "call_secs_p50", "call_secs_max", "tokens_prompt", "fresh_in", "cached_in", "out_tok", "spend", "spend_check", "validation_mode", "started", "finished", "execution_id"]
with open(os.path.join(OUT, "per_task.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(fields)
    for t in sorted(tasks, key=lambda t: t["task"]): w.writerow([t.get(k) for k in fields])
json.dump(tasks, open(os.path.join(OUT, "tasks_full.json"), "w"), indent=1, default=str)
# hourly head shim table
hours = collections.defaultdict(lambda: collections.defaultdict(list))
for c in calls:
    h = dt.datetime.fromtimestamp(c.get("ts", 0), dt.timezone.utc).strftime("%m-%d %H") if c.get("ts") else None
    if h is None: continue
    hours[h]["secs"].append(c["secs"]); hours[h]["status"].append(c.get("status")); hours[h]["fail"].append(1 if c.get("stream_failed") else 0)
with open(os.path.join(OUT, "shim_hourly.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["hour_utc", "calls", "http_402", "failed_streams", "secs_p50", "secs_p90", "secs_p99", "calls_over_590s"])
    for h in sorted(hours):
        d = hours[h]; w.writerow([h, len(d["secs"]), sum(1 for s in d["status"] if s == 402), sum(d["fail"]), round(st.median(d["secs"]), 1), round(pct(d["secs"], .9), 1), round(pct(d["secs"], .99), 1), sum(1 for s in d["secs"] if s >= 590)])
print(json.dumps({k: S[k] for k in ("run", "outcomes", "agent_minutes", "hit_limit", "spend", "tokens", "shim", "graded", "not_graded", "task_hours", "lost")}, indent=1))
print("validation modes:", dict(modes), "| autoscaler events:", len(events), "| shim hourly rows:", len(hours))
