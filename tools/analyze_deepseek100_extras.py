#!/usr/bin/env python3
"""Extra observations of the 100-task DeepSeek run, saved so they are reproducible: time inside model calls, fuzzer usage and self-validation from the
trajectories, validation hours on the slot and wall clocks, and a what-if schedule on other slot counts.
Inputs (outside git): <run-logs>/pass2_executions.jsonl, <run-logs>/analysis/per_task.csv, shim logs and validation_analysis.json under <run-logs>/extract/,
and the per-task run folders in cybergym-bench/runs/deepseek100-pass2 (trajectories).
usage: analyze_deepseek100_extras.py <run-logs folder> <runs folder> <out json>
"""
import csv, datetime as dt, glob, heapq, json, re, sys

RL, RUNS, OUT = sys.argv[1:4]
tasks = {r["execution_id"]: r for r in csv.DictReader(open(RL + "/analysis/per_task.csv"))}
num = lambda v, d=0.0: float(v) if v not in ("", "None", None) else d
X = {}

# ---- 1. time inside model calls (per-call shim logs of the head and the workers)
calls = []
for p in [RL + "/extract/cybergym-work/shim-head-vertex.log"] + glob.glob(RL + "/extract/cybergym-work/worker-backups/*/shim.log"):
    for l in open(p, errors="replace"):
        if l.startswith("{"):
            try: j = json.loads(l)
            except ValueError: continue
            if j.get("event") == "messages" and j.get("alias") in tasks: calls.append(j)
agent_h = sum(num(t["agent_min"]) for t in tasks.values()) / 60 + 1.5          # plus the stopped task's agent, about 1.5 h
ok = [c for c in calls if c["secs"] < 590]; stalled = [c for c in calls if c["secs"] >= 590]
X["model_calls"] = dict(calls=len(calls), hours_all=round(sum(c["secs"] for c in calls) / 3600, 1), hours_normal=round(sum(c["secs"] for c in ok) / 3600, 1),
                        stalled_calls=len(stalled), hours_stalled=round(sum(c["secs"] for c in stalled) / 3600, 1), agent_hours=round(agent_h, 1),
                        share_of_agent_time_all=round(100 * sum(c["secs"] for c in calls) / 3600 / agent_h), share_without_stalled=round(100 * sum(c["secs"] for c in ok) / 3600 / agent_h),
                        mean_in_flight=round(sum(c["secs"] for c in calls) / 3600 / 10.89, 1), mean_call_s=round(sum(c["secs"] for c in calls) / len(calls), 1))

# ---- 2. fuzzer usage and self-validation, from the agents' own commands
FUZZ = re.compile(r"-max_total_time|-runs=\d|-jobs=|-fork=|-workers=|afl-fuzz|-use_value_profile|-max_len=|timeout\s+\d+\s+\S*fuzz|/out/\S*fuzz\S*\s+(-|/tmp|/corpus|corpus)", re.I)
PAR = re.compile(r"-jobs=([2-9]|\d\d)|-fork=([2-9]|\d\d)|-workers=([2-9]|\d\d)|afl-fuzz|parallel", re.I)
by_task = {t["task"]: t for t in tasks.values()}
rows = []
for f in sorted(glob.glob(RUNS + "/*/upstream/*/*/trajectory/attempt_1.log")):
    task = json.load(open(f.split("/trajectory/")[0] + "/summary.json"))["task"]
    n = fz = par = val = 0
    for l in open(f, errors="replace"):
        if '"type":"item.completed"' in l and '"command_execution"' in l:
            try: c = json.loads(l)["item"].get("command", "")
            except Exception: continue
            n += 1; fz += bool(FUZZ.search(c)); par += bool(FUZZ.search(c) and PAR.search(c)); val += ("validate.py" in c)
    rows.append(dict(task=task, commands=n, fuzzer_cmds=fz, parallel_fuzzer_cmds=par, validate_runs=val, outcome=by_task.get(task, {}).get("outcome", "?"), hit_limit=by_task.get(task, {}).get("hit_limit") == "True"))
lim = [r for r in rows if r["hit_limit"]]
X["fuzzers"] = dict(tasks=len(rows), ran_fuzzer=sum(1 for r in rows if r["fuzzer_cmds"]), ran_parallel_or_afl=sum(1 for r in rows if r["parallel_fuzzer_cmds"]), commands=sum(r["commands"] for r in rows),
                    fuzzer_commands=sum(r["fuzzer_cmds"] for r in rows), at_limit=len(lim), at_limit_ran_fuzzer=sum(1 for r in lim if r["fuzzer_cmds"]),
                    no_poc_tasks=sum(1 for r in rows if r["outcome"] == "no PoC"), no_poc_ran_fuzzer=sum(1 for r in rows if r["outcome"] == "no PoC" and r["fuzzer_cmds"]),
                    pass_tasks=sum(1 for r in rows if r["outcome"] == "PASS S1-S4"), pass_ran_fuzzer=sum(1 for r in rows if r["outcome"] == "PASS S1-S4" and r["fuzzer_cmds"]),
                    note="pattern search over command lines (libFuzzer and AFL options); approximate; the logs have no timestamps, so the share of agent time is not known")
X["self_validation"] = dict(tasks_that_ran_validate_py=sum(1 for r in rows if r["validate_runs"]), runs=sum(r["validate_runs"] for r in rows), mean_per_task=round(sum(r["validate_runs"] for r in rows) / len(rows), 1),
                            max_per_task=max(r["validate_runs"] for r in rows), share_of_commands=round(100 * sum(r["validate_runs"] for r in rows) / sum(r["commands"] for r in rows), 1))

# ---- 3. validation (grading) on the slot clock and the wall clock
vj = json.load(open(RL + "/extract/autoscaler/validation_analysis.json"))
iv, slot = [], 0.0
for r in vj:
    t = by_task.get(r["task"])
    if t and t["finished"] and r["outside"] >= 1:
        e = dt.datetime.fromisoformat(t["finished"].replace("+00:00", "")); iv.append((e - dt.timedelta(minutes=r["outside"]), e)); slot += r["outside"] / 60
iv.append((dt.datetime(2026, 11, 4, 15, 18), dt.datetime(2026, 11, 4, 17, 0, 54))); slot += 1.7        # the stopped ffmpeg task
iv.sort(); merged = []
for s, e in iv:
    if merged and s <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], e)
    else: merged.append([s, e])
T0, T1 = dt.datetime(2026, 11, 4, 6, 7, 16), dt.datetime(2026, 11, 4, 17, 0, 54); wall = (T1 - T0).total_seconds() / 3600
task_hours = sum(num(t["total_min"]) for t in tasks.values() if t["status"] != "interrupted") / 60 + 3.3
X["validation"] = dict(slot_hours=round(slot, 1), share_of_task_hours=round(100 * slot / task_hours), task_hours=round(task_hours, 1), share_of_slot_capacity=round(100 * slot / (wall * 16)),
                       wall_hours=round(wall, 2), wall_hours_with_a_grading_running=round(sum((e - s).total_seconds() for s, e in merged) / 3600, 1), tail_only_grading_hours=1.7,
                       note="grading intervals reconstructed from each task's finish time and its time outside the agent run; the slot-hour figures do not depend on the reconstruction")

# ---- 4. what-if schedule: the real durations replayed on other slot counts
order = sorted(tasks.values(), key=lambda r: r["started"])
dur = [num(t["total_min"], 220.0) for t in order]
def simulate(head, workers, per_worker, join_min=8.0, stagger_min=0.5, grading_scale=1.0):
    free = [0.0] * head + [join_min] * (workers * per_worker); heapq.heapify(free); last = 0.0; ends = []
    for t, d in zip(order, dur):
        a = num(t["agent_min"], 90.0); d = a + (d - a) * grading_scale if d > a else d
        s = max(heapq.heappop(free), last + stagger_min); last = s; ends.append(s + d); heapq.heappush(free, s + d)
    return round(max(ends) / 60, 1)
X["what_if"] = dict(model="real per-task durations in the real dispatch order; workers join after 8 min; 30 s launch spacing; the stopped ffmpeg task counted as 220 min",
                    scenarios=[dict(name=n, head=h, workers=w, per_worker=p, slots=h + w * p, wall_hours=simulate(h, w, p), wall_hours_if_overhead_20pct_slower=simulate(h, w, p, grading_scale=1.2))
                               for n, h, w, p in (("what we ran", 4, 2, 6), ("72 vCPU quota, 3 workers x 8, head 4", 4, 3, 8), ("72 vCPU, 3 workers x 8, head 8", 8, 3, 8), ("72 vCPU, 3 workers x 6, head 4", 4, 3, 6),
                                                  ("quota unchanged, 2 workers x 8", 4, 2, 8), ("72 vCPU, 3 workers x 10 (first-pass setting)", 4, 3, 10))])
json.dump(X, open(OUT, "w"), indent=1)
print(json.dumps({k: X[k] for k in ("model_calls", "fuzzers", "self_validation", "validation")}, indent=1)); print([(s["name"], s["wall_hours"]) for s in X["what_if"]["scenarios"]])
