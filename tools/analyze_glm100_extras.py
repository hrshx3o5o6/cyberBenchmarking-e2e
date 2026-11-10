#!/usr/bin/env python3
"""Extra observations of the GLM 5.3 Flash run (run 3), from the agents' own commands and the head's shim log: fuzzer usage and self-validation (all valid trajectories), time inside model
calls (the head's shim only: the workers' logs were lost), and long reasoning calls. Same method as analyze_deepseek100_extras.py (pattern search over command lines, approximate).
usage: analyze_glm100_extras.py <export folder> <glm-flash-r3 tables folder> <out json>
"""
import csv, glob, json, os, re, sys

EXP, TAB, OUT = sys.argv[1:4]
tasks = {r["execution_id"]: r for r in csv.DictReader(open(TAB + "/per_task.csv"))}
num = lambda v, d=0.0: float(v) if v not in ("", "None", None) else d
valid = {e: t for e, t in tasks.items() if t["status"] in ("passed", "benchmark_failed")}
X = {}

calls = []
for l in open(EXP + "/run3_head_shim.jsonl"):
    try: j = json.loads(l)
    except ValueError: continue
    if j.get("event") == "messages" and j.get("alias") in tasks: calls.append(j)
head_exec = {c["alias"] for c in calls}
agent_h = sum(num(tasks[e]["agent_min"]) for e in head_exec if e in tasks) / 3600 * 60            # agent hours of the tasks that ran on the head
secs = sorted(c["secs"] for c in calls)
long_ = [c for c in calls if c["secs"] >= 120]
X["model_calls"] = dict(scope="head only", tasks=len(head_exec), calls=len(calls), hours_all=round(sum(secs) / 3600, 1), long_calls_over_120s=len(long_), hours_in_long_calls=round(sum(c["secs"] for c in long_) / 3600, 1),
                        calls_hit_output_maximum=sum(1 for c in calls if c.get("finish") == "length"), hours_in_output_maximum_calls=round(sum(c["secs"] for c in calls if c.get("finish") == "length") / 3600, 1),
                        agent_hours_of_these_tasks=round(agent_h, 1), mean_call_s=round(sum(secs) / len(secs), 1), cache_zero_large_prompt_calls=sum(1 for c in calls if (c.get("in_tok") or 0) > 200000 and (c.get("cache_tok") or 0) == 0))

FUZZ = re.compile(r"-max_total_time|-runs=\d|-jobs=|-fork=|-workers=|afl-fuzz|-use_value_profile|-max_len=|timeout\s+\d+\s+\S*fuzz|/out/\S*fuzz\S*\s+(-|/tmp|/corpus|corpus)", re.I)
PAR = re.compile(r"-jobs=([2-9]|\d\d)|-fork=([2-9]|\d\d)|-workers=([2-9]|\d\d)|afl-fuzz|parallel|xargs\s+-P", re.I)
rows = []
for eid, t in valid.items():
    fs = glob.glob("%s/runs/%s/upstream/*/*/trajectory/attempt_1.log" % (EXP, eid))
    if not fs: continue
    n = fz = par = val = 0
    for l in open(fs[0], errors="replace"):
        if '"type":"item.completed"' in l and '"command_execution"' in l:
            try: c = json.loads(l)["item"].get("command", "")
            except Exception: continue
            n += 1; fz += bool(FUZZ.search(c)); par += bool(FUZZ.search(c) and PAR.search(c)); val += ("validate.py" in c)
    rows.append(dict(task=t["task"], commands=n, fuzzer_cmds=fz, parallel_fuzzer_cmds=par, validate_runs=val, outcome=t["outcome"], hit_limit=t["hit_limit"] == "True"))
lim = [r for r in rows if r["hit_limit"]]
X["fuzzers"] = dict(tasks=len(rows), ran_fuzzer=sum(1 for r in rows if r["fuzzer_cmds"]), ran_parallel_or_afl=sum(1 for r in rows if r["parallel_fuzzer_cmds"]), commands=sum(r["commands"] for r in rows),
                    fuzzer_commands=sum(r["fuzzer_cmds"] for r in rows), at_limit=len(lim), at_limit_ran_fuzzer=sum(1 for r in lim if r["fuzzer_cmds"]),
                    no_poc_tasks=sum(1 for r in rows if r["outcome"] == "no PoC"), no_poc_ran_fuzzer=sum(1 for r in rows if r["outcome"] == "no PoC" and r["fuzzer_cmds"]),
                    pass_tasks=sum(1 for r in rows if r["outcome"] == "PASS S1-S4"), pass_ran_fuzzer=sum(1 for r in rows if r["outcome"] == "PASS S1-S4" and r["fuzzer_cmds"]),
                    note="pattern search over command lines (libFuzzer and AFL options); approximate; the logs have no timestamps, so the share of agent time is not known")
X["self_validation"] = dict(tasks_that_ran_validate_py=sum(1 for r in rows if r["validate_runs"]), runs=sum(r["validate_runs"] for r in rows), mean_per_task=round(sum(r["validate_runs"] for r in rows) / max(1, len(rows)), 1),
                            max_per_task=max((r["validate_runs"] for r in rows), default=0), share_of_commands=round(100 * sum(r["validate_runs"] for r in rows) / max(1, sum(r["commands"] for r in rows)), 1))
graded = [t for t in valid.values() if int(t["stages_run"] or 0) > 0]
X["grading"] = dict(graded=len(graded), modes=sorted({t["validation_mode"] for t in graded}), overhead_min_mean=round(sum(num(t["overhead_min"]) for t in graded) / max(1, len(graded)), 1),
                    overhead_min_max=max((num(t["overhead_min"]) for t in graded), default=0), slot_hours=round(sum(num(t["overhead_min"]) for t in graded) / 60, 1))
json.dump(X, open(OUT, "w"), indent=1)
print(json.dumps(X, indent=1))
