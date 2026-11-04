#!/usr/bin/env python3
"""Aggregate the raw data of the 100-task DeepSeek run (pass 2) into the numbers used by the report.

Inputs (all outside git, in the run-logs folder):  pass2_executions.jsonl (Postgres export), pass2_node_metrics.csv (sampler export),
  extract/cybergym-work/shim-head-vertex.log and extract/cybergym-work/worker-backups/<ip>/shim.log (per-call shim logs),
  pass2-head-raylogs.tar.gz (head Ray logs: autoscaler events).
Output: <out>/summary.json, per_task.csv, node_timeseries_15min.csv, shim_hourly.csv
usage: analyze_deepseek100.py <run-logs folder> <out folder>
"""
import csv, collections, datetime as dt, glob, io, json, os, re, statistics as st, sys, tarfile

RUN, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
T0 = None
PRICE = (0.30, 0.03, 1.20)       # assumed USD per million fresh input, cached input, output tokens
NODES = {"ip-172-31-22-187": "head", "ip-172-31-20-48": "worker A (…20.48)", "ip-172-31-23-192": "worker B (…23.192)"}

def pct(xs, p):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else None

# ---------------------------------------------------------------- per task
rows = [json.loads(l) for l in open(os.path.join(RUN, "pass2_executions.jsonl"))]
tasks = []
for r in rows:
    res = r.get("result") or {}
    u = res.get("usage") or {}
    st_ = [res.get("stage%d" % i) for i in (1, 2, 3, 4)]
    ran = sum(1 for s in st_ if s in ("passed", "failed", "error"))
    dur = res.get("duration_seconds"); ag = res.get("agent_exec_seconds")
    t = dict(task=r["task"], project=r["task"].split("/")[0], kind="arvo" if "/arvo_" in r["task"] else "oss-fuzz", host=r["hostname"], status=r["status"],
             s1=st_[0], s2=st_[1], s3=st_[2], s4=st_[3], stages_run=ran, execution_id=r["execution_id"],
             agent_min=round(ag / 60, 1) if ag else None, total_min=round(dur / 60, 1) if dur else None,
             grading_min=None, requests=u.get("requests"), errors=u.get("errors"), fresh_in=u.get("input_tokens"), cached_in=u.get("cache_read_tokens"),
             out_tok=u.get("output_tokens"), spend=u.get("spend"), started=r["started_at"], finished=r["finished_at"])
    if t["total_min"] and t["agent_min"]:
        t["overhead_min"] = round(t["total_min"] - t["agent_min"], 1)
    tasks.append(t)
fin = [t for t in tasks if t["status"] in ("passed", "benchmark_failed")]
for t in fin:
    t["hit_limit"] = bool(t["agent_min"] and t["agent_min"] >= 89.9)
    t["outcome"] = ("PASS S1-S4" if t["status"] == "passed" else "no PoC" if t["s1"] == "no_poc" else "no patch" if t["s3"] == "no_patch" else
                    "S4 fail" if (t["s1"], t["s2"], t["s3"]) == ("passed", "passed", "passed") and t["s4"] in ("failed", "error") else "S1 fail" if t["s1"] == "failed" else "other")
    t["tokens_prompt"] = (t["fresh_in"] or 0) + (t["cached_in"] or 0)
    t["calls_per_task"] = t["requests"]
    t["spend_check"] = round(((t["fresh_in"] or 0) * PRICE[0] + (t["cached_in"] or 0) * PRICE[1] + (t["out_tok"] or 0) * PRICE[2]) / 1e6, 4)

# ---------------------------------------------------------------- shim logs (per call)
def read_shim(path, node):
    out = []
    if not os.path.exists(path): return out
    for l in open(path, errors="replace"):
        if l.startswith("{"):
            try: j = json.loads(l)
            except ValueError: continue
            if j.get("event") == "messages": j["_node"] = node; out.append(j)
    return out
calls = read_shim(os.path.join(RUN, "extract/cybergym-work/shim-head-vertex.log"), "head")
for d in glob.glob(os.path.join(RUN, "extract/cybergym-work/worker-backups/*/")):
    calls += read_shim(d + "shim.log", "worker " + os.path.basename(d.rstrip("/")))
eid = {t["execution_id"] for t in tasks}
calls = [c for c in calls if c.get("alias") in eid]
by_exec = collections.defaultdict(list)
for c in calls: by_exec[c["alias"]].append(c)
for t in tasks:
    cs = by_exec.get(t["execution_id"], [])
    t["shim_calls"] = len(cs)
    t["calls_502"] = sum(1 for c in cs if c.get("status") == 502)
    t["calls_failed_stream"] = sum(1 for c in cs if c.get("stream_failed"))
    t["call_secs_p50"] = round(st.median([c["secs"] for c in cs]), 1) if cs else None
    t["call_secs_max"] = round(max([c["secs"] for c in cs]), 1) if cs else None
hours = collections.defaultdict(lambda: collections.defaultdict(list))
for c in calls:
    h = dt.datetime.fromtimestamp(c["ts"], dt.timezone.utc).strftime("%m-%d %H")
    hours[h]["secs"].append(c["secs"]); hours[h]["status"].append(c.get("status")); hours[h]["fail"].append(1 if c.get("stream_failed") else 0)
    hours[h]["out"].append(c.get("out_tok") or 0)
with open(os.path.join(OUT, "shim_hourly.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["hour_utc", "calls", "http_502", "failed_streams", "secs_p50", "secs_p90", "secs_p99", "calls_over_590s"])
    for h in sorted(hours):
        d = hours[h]; w.writerow([h, len(d["secs"]), sum(1 for s in d["status"] if s == 502), sum(d["fail"]), round(st.median(d["secs"]), 1), round(pct(d["secs"], .9), 1), round(pct(d["secs"], .99), 1), sum(1 for s in d["secs"] if s >= 590)])

# ---------------------------------------------------------------- node time series
ts = collections.defaultdict(lambda: collections.defaultdict(list))
ctr_peaks = collections.defaultdict(float)
first_ts = None
for node, t_, metric, value in csv.reader(open(os.path.join(RUN, "pass2_node_metrics.csv"))):
    if node not in NODES: continue
    v = float(value); tt = dt.datetime.strptime(t_, "%Y-%m-%dT%H:%M:%S")
    b = tt.replace(minute=(tt.minute // 15) * 15, second=0)
    if metric.startswith("ctr_mem_gb:"):
        ctr_peaks[(node, metric[11:])] = max(ctr_peaks[(node, metric[11:])], v); continue
    ts[(node, b)][metric].append(v)
buckets = sorted({b for (_, b) in ts})
with open(os.path.join(OUT, "node_timeseries_15min.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["bucket_start_utc", "node", "mem_used_avg_gb", "mem_used_max_gb", "mem_avail_min_gb", "load1_avg", "load1_max", "containers_avg"])
    for (node, b), m in sorted(ts.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        w.writerow([b.strftime("%Y-%m-%dT%H:%M"), NODES[node], round(st.mean(m["mem_used_gb"]), 1), round(max(m["mem_used_gb"]), 1), round(min(m["mem_avail_gb"]), 1),
                    round(st.mean(m["load1"]), 1), round(max(m["load1"]), 1), round(st.mean(m["containers"]), 1)])
node_stats = {}
allm = collections.defaultdict(lambda: collections.defaultdict(list))
for node, tsv in ((n, ts[k]) for k in ts for n in [k[0]]):
    for m, v in tsv.items(): allm[node][m] += v
for node in NODES:
    a = allm[node]
    if not a.get("mem_used_gb"): continue
    node_stats[NODES[node]] = dict(samples=len(a["mem_used_gb"]), mem_used_avg=round(st.mean(a["mem_used_gb"]), 1), mem_used_p99=round(pct(a["mem_used_gb"], .99), 1), mem_used_max=round(max(a["mem_used_gb"]), 1),
        mem_avail_min=round(min(a["mem_avail_gb"]), 1), load_avg=round(st.mean(a["load1"]), 1), load_p50=round(st.median(a["load1"]), 0), load_p90=round(pct(a["load1"], .9), 0), load_max=round(max(a["load1"]), 0),
        pct_load_over_16=round(100 * sum(1 for x in a["load1"] if x > 16) / len(a["load1"]), 1), pct_load_over_32=round(100 * sum(1 for x in a["load1"] if x > 32) / len(a["load1"]), 1), containers_avg=round(st.mean(a["containers"]), 1))
top_ctr = sorted(((v, NODES[n], c) for (n, c), v in ctr_peaks.items()), reverse=True)[:8]

# ---------------------------------------------------------------- autoscaler events (head Ray monitor log)
events = []
try:
    with tarfile.open(os.path.join(RUN, "pass2-head-raylogs.tar.gz")) as tf:
        m = next(x for x in tf.getmembers() if x.name.endswith("logs/monitor.log"))
        for l in io.TextIOWrapper(tf.extractfile(m), errors="replace"):
            if "event_summary" in l or "Terminating the node" in l or "NodeLauncher" in l:
                mm = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", l)
                if mm: events.append((mm.group(1), re.sub(r".*?(event_summary:|StandardAutoscaler: |NodeLauncher\d+: )", "", l).strip()[:140]))
except Exception as e:
    events.append(("error", str(e)))
ev_counts = collections.Counter(re.sub(r"\d+ ", "N ", e[1])[:60] for e in events)

# ---------------------------------------------------------------- summary
def agg(xs): return dict(n=len(xs), mean=round(st.mean(xs), 1), median=round(st.median(xs), 1), p90=round(pct(xs, .9), 1), max=round(max(xs), 1)) if xs else {}
spend = [t["spend"] for t in fin if t["spend"] is not None]
S = dict(
    run=dict(start_utc="2026-11-04T06:07:16Z", end_utc="2026-11-04T17:00:54Z", tasks=len(tasks), finished=len(fin), interrupted=sum(1 for t in tasks if t["status"] == "interrupted"),
             passed=sum(1 for t in fin if t["status"] == "passed")),
    outcomes=dict(collections.Counter(t["outcome"] for t in fin)),
    stage_patterns=[[list(k), v] for k, v in collections.Counter((t["s1"], t["s2"], t["s3"], t["s4"]) for t in fin).most_common()],
    agent_minutes=agg([t["agent_min"] for t in fin if t["agent_min"]]), hit_limit=sum(1 for t in fin if t["hit_limit"]), agent_max_seconds=max((t["agent_min"] for t in fin if t["agent_min"]), default=0) * 60,
    total_minutes=agg([t["total_min"] for t in fin if t["total_min"]]), overhead_minutes_all=agg([t["overhead_min"] for t in fin if t.get("overhead_min") is not None]),
    graded=sum(1 for t in fin if t["stages_run"] > 0), not_graded=sum(1 for t in fin if t["stages_run"] == 0),
    task_hours=dict(total=round(sum(t["total_min"] for t in fin) / 60, 1), agent=round(sum(t["agent_min"] for t in fin) / 60, 1), outside_agent=round(sum(t.get("overhead_min") or 0 for t in fin) / 60, 1)),
    spend=dict(total=round(sum(spend), 2), mean=round(st.mean(spend), 2), median=round(st.median(spend), 2), p90=round(pct(spend, .9), 2), max=round(max(spend), 2), over_5=sum(1 for s in spend if s > 5), over_8=sum(1 for s in spend if s > 8), over_10=sum(1 for s in spend if s >= 10),
               by_outcome={k: round(st.mean([t["spend"] for t in fin if t["outcome"] == k]), 2) for k in sorted({t["outcome"] for t in fin})},
               total_by_outcome={k: round(sum(t["spend"] for t in fin if t["outcome"] == k), 2) for k in sorted({t["outcome"] for t in fin})},
               cost_per_pass=round(sum(spend) / max(1, sum(1 for t in fin if t["status"] == "passed")), 2)),
    tokens=dict(fresh=sum(t["fresh_in"] or 0 for t in fin), cached=sum(t["cached_in"] or 0 for t in fin), out=sum(t["out_tok"] or 0 for t in fin), requests=sum(t["requests"] or 0 for t in fin),
                cached_share=round(100 * sum(t["cached_in"] or 0 for t in fin) / max(1, sum(t["tokens_prompt"] for t in fin)), 1)),
    calls_per_task=agg([t["requests"] for t in fin if t["requests"]]),
    prompt_tokens_per_call_mean=round(sum(t["tokens_prompt"] for t in fin) / max(1, sum(t["requests"] or 0 for t in fin))),
    out_tokens_per_call_mean=round(sum(t["out_tok"] or 0 for t in fin) / max(1, sum(t["requests"] or 0 for t in fin))),
    shim=dict(calls=len(calls), http_200=sum(1 for c in calls if c.get("status") == 200), http_502=sum(1 for c in calls if c.get("status") == 502), failed_streams=sum(1 for c in calls if c.get("stream_failed")),
              over_590s=sum(1 for c in calls if c["secs"] >= 590), secs_p50=round(st.median([c["secs"] for c in calls]), 1), secs_p90=round(pct([c["secs"] for c in calls], .9), 1), secs_p99=round(pct([c["secs"] for c in calls], .99), 1),
              finish=dict(collections.Counter(str(c.get("finish")) for c in calls)), by_node=dict(collections.Counter(c["_node"] for c in calls))),
    nodes=node_stats, top_containers_gb=[[round(v, 1), n, c] for v, n, c in top_ctr], autoscaler_event_counts=dict(ev_counts.most_common(12)),
    autoscaler_events=[list(e) for e in events if "Failed" not in e[1]][:40],
    by_project=[dict(project=p, n=len(xs), passed=sum(1 for t in xs if t["status"] == "passed"), s4_fail=sum(1 for t in xs if t["outcome"] == "S4 fail"), no_poc=sum(1 for t in xs if t["outcome"] == "no PoC"),
                     agent_min=round(st.mean([t["agent_min"] for t in xs]), 0), spend=round(sum(t["spend"] for t in xs), 2)) for p, xs in sorted(collections.defaultdict(list, {p: [t for t in fin if t["project"] == p] for p in {t["project"] for t in fin}}).items(), key=lambda kv: -len(kv[1]))],
    by_kind=[dict(kind=k, n=len(xs), passed=sum(1 for t in xs if t["status"] == "passed"), no_poc=sum(1 for t in xs if t["outcome"] == "no PoC"), s4_fail=sum(1 for t in xs if t["outcome"] == "S4 fail"), spend=round(sum(t["spend"] for t in xs), 2)) for k, xs in ((k, [t for t in fin if t["kind"] == k]) for k in ("arvo", "oss-fuzz"))],
    by_host=[dict(host=h, n=len(xs), passed=sum(1 for t in xs if t["status"] == "passed"), agent_min=round(st.mean([t["agent_min"] for t in xs]), 0), overhead_min=round(st.mean([t.get("overhead_min") or 0 for t in xs]), 1)) for h, xs in ((h, [t for t in fin if t["host"] == h]) for h in sorted({t["host"] for t in fin}))],
    grading=dict(graded_overhead=agg([t["overhead_min"] for t in fin if t["stages_run"] > 0]), ffmpeg_graded=[[t["task"], t["overhead_min"]] for t in fin if t["project"] == "ffmpeg" and t["stages_run"] > 0]),
    pass_by_limit=dict(passed_at_limit=sum(1 for t in fin if t["status"] == "passed" and t["hit_limit"]), passed_agent_min=agg([t["agent_min"] for t in fin if t["status"] == "passed"])),
)
json.dump(S, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
fields = ["task", "project", "kind", "host", "status", "outcome", "s1", "s2", "s3", "s4", "stages_run", "agent_min", "total_min", "overhead_min", "hit_limit", "requests", "calls_502", "calls_failed_stream", "call_secs_p50", "call_secs_max", "tokens_prompt", "fresh_in", "cached_in", "out_tok", "spend", "errors", "started", "finished", "execution_id"]
with open(os.path.join(OUT, "per_task.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(fields)
    for t in sorted(tasks, key=lambda t: t["task"]): w.writerow([t.get(k) for k in fields])
json.dump(tasks, open(os.path.join(OUT, "tasks_full.json"), "w"), indent=1, default=str)
print(json.dumps({k: S[k] for k in ("run", "outcomes", "agent_minutes", "hit_limit", "spend", "tokens", "shim", "graded", "not_graded", "task_hours")}, indent=1))
