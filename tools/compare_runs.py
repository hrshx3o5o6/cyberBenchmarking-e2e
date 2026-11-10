#!/usr/bin/env python3
"""Compare the DeepSeek V4.1 Flash run and the GLM 5.3 Flash run of the same 100 CyberGym-E2E tasks from their small result tables
(wiki/syntheses/aws-vm-data/deepseek100/ and glm-flash-r3/). Writes wiki/syntheses/aws-vm-data/compare-deepseek-glm/{compare.json,per_task_pair.csv}.

Which tasks are compared matters: the GLM run was stopped after 5 h 23 min, so only 51 tasks have a valid result, and those are biased towards tasks that finish early. Three sets:
  prefix  = the first N tasks of the shared dispatch order that all have a valid GLM result (selected by start time, not by outcome): the fair comparison, used for headline numbers
  glm51   = all 51 valid GLM tasks with DeepSeek's result on the same tasks (more tasks, but biased towards early finishers)
  own     = each run on its own graded tasks (DeepSeek 99, GLM 51), for reference only
usage: compare_runs.py   (run from the repository root)
"""
import csv, json, math, os, statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AV = os.path.join(ROOT, "wiki", "syntheses", "aws-vm-data")
OUT = os.path.join(AV, "compare-deepseek-glm"); os.makedirs(OUT, exist_ok=True)
rd = lambda p: {r["task"]: r for r in csv.DictReader(open(p))}
DS, GL = rd(AV + "/deepseek100/per_task.csv"), rd(AV + "/glm-flash-r3/per_task.csv")
SD, SG = json.load(open(AV + "/deepseek100/summary.json")), json.load(open(AV + "/glm-flash-r3/summary.json"))
XD, XG = json.load(open(AV + "/deepseek100/extras.json")), json.load(open(AV + "/glm-flash-r3/extras.json"))
ORDER = [l.strip() for l in open(AV + "/random100_tasks.txt") if l.strip()]
num = lambda v, d=None: float(v) if v not in ("", "None", None) else d
valid = lambda r: r["status"] in ("passed", "benchmark_failed")
S13 = lambda r: (r["s1"], r["s2"], r["s3"]) == ("passed", "passed", "passed")
S14 = lambda r: r["status"] == "passed"
glm_valid = [t for t in ORDER if valid(GL[t])]
n_prefix = 0
for t in ORDER:
    if valid(GL[t]): n_prefix += 1
    else: break
prefix = ORDER[:n_prefix]


def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(100 * (c - w) / d, 1), round(100 * (c + w) / d, 1))


def sign_test(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c); p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return round(min(1.0, 2 * p), 4)


def agg(xs): return dict(mean=round(st.mean(xs), 2), median=round(st.median(xs), 2), total=round(sum(xs), 2)) if xs else {}


def stats(rows, price):
    """per-model figures for a set of valid rows; price = (fresh, cached, output) USD per million tokens for the cost recomputation at one common price list"""
    n = len(rows); k13 = sum(map(S13, rows)); k14 = sum(map(S14, rows))
    fresh = sum(num(r["fresh_in"], 0) for r in rows); cached = sum(num(r["cached_in"], 0) for r in rows); out = sum(num(r["out_tok"], 0) for r in rows); req = sum(num(r["requests"], 0) for r in rows)
    graded = [r for r in rows if int(r["stages_run"] or 0) > 0]
    oc = {}
    for r in rows: oc[r["outcome"]] = oc.get(r["outcome"], 0) + 1
    return dict(n=n, s1s3=k13, s1s3_pct=round(100 * k13 / n, 1), s1s3_ci=wilson(k13, n), s1s4=k14, s1s4_pct=round(100 * k14 / n, 1), s1s4_ci=wilson(k14, n),
                outcomes=oc, funnel=[sum(1 for r in rows if r["s%d" % i] == "passed") for i in (1, 2, 3, 4)],
                agent_min=agg([num(r["agent_min"]) for r in rows if num(r["agent_min"])]), at_limit=sum(1 for r in rows if r["hit_limit"] == "True"),
                total_min=agg([num(r["total_min"]) for r in rows if num(r["total_min"])]), graded=len(graded),
                grading_overhead_min=agg([num(r["overhead_min"]) for r in graded if num(r["overhead_min"]) is not None]),
                spend=agg([num(r["spend"]) for r in rows if num(r["spend"]) is not None]), spend_pass=round(sum(num(r["spend"], 0) for r in rows) / max(1, k14), 2),
                tokens=dict(fresh=fresh, cached=cached, out=out, requests=req, cached_share=round(100 * cached / max(1, fresh + cached), 1), prompt_per_call=round((fresh + cached) / max(1, req)), out_per_call=round(out / max(1, req)),
                            calls_per_task=round(req / n, 1), prompt_tokens_per_task_m=round((fresh + cached) / n / 1e6, 2), out_tokens_per_task_k=round(out / n / 1e3, 1)),
                cost_at_common_price=round((fresh * price[0] + cached * price[1] + out * price[2]) / 1e6, 2),
                cost_per_task_at_common_price=round((fresh * price[0] + cached * price[1] + out * price[2]) / 1e6 / n, 2))


def pair(tasks, price):
    d = [DS[t] for t in tasks if valid(DS[t])]; g = [GL[t] for t in tasks]
    both = [t for t in tasks if valid(DS[t])]
    a = sum(1 for t in both if S13(DS[t]) and S13(GL[t])); b = sum(1 for t in both if S13(DS[t]) and not S13(GL[t])); c = sum(1 for t in both if not S13(DS[t]) and S13(GL[t])); z = len(both) - a - b - c
    a4 = sum(1 for t in both if S14(DS[t]) and S14(GL[t])); b4 = sum(1 for t in both if S14(DS[t]) and not S14(GL[t])); c4 = sum(1 for t in both if not S14(DS[t]) and S14(GL[t]))
    return dict(tasks=len(tasks), deepseek=stats(d, price), glm=stats(g, price), agree_s1s3=dict(both=a, deepseek_only=b, glm_only=c, neither=z, sign_test_p=sign_test(b, c)),
                agree_s1s4=dict(both=a4, deepseek_only=b4, glm_only=c4, sign_test_p=sign_test(b4, c4)))


P_DS, P_GL = (0.30, 0.03, 1.20), (0.15, 0.03, 0.50)
extra = [t for t in glm_valid if t not in prefix]
C = dict(n_prefix=n_prefix, extra=[dict(position=ORDER.index(t) + 1, task=t) for t in extra], prefix_last=prefix[-1],
         prefix=pair(prefix, P_DS), glm51=pair(glm_valid, P_DS),
         own=dict(deepseek=stats([r for r in DS.values() if valid(r)], P_DS), glm=stats([GL[t] for t in glm_valid], P_DS)),
         price_lists=dict(deepseek_assumed=P_DS, glm_openrouter_list=P_GL),
         prefix_at_own_prices=dict(deepseek=round(sum(num(DS[t]["spend"], 0) for t in prefix if valid(DS[t])), 2), glm=round(sum(num(GL[t]["spend"], 0) for t in prefix), 2)),
         runs=dict(deepseek=dict(start=SD["run"]["start_utc"], end=SD["run"]["end_utc"], wall_h=10.9, graded=SD["run"]["finished"], interrupted=SD["run"]["interrupted"], task_hours=SD["task_hours"], spend=SD["spend"]["total"],
                                 requests=SD["tokens"]["requests"], calls=SD["shim"]["calls"], http_error=SD["shim"]["http_502"], failed_streams=SD["shim"]["failed_streams"], over_590=SD["shim"]["over_590s"],
                                 secs=[SD["shim"]["secs_p50"], SD["shim"]["secs_p90"], SD["shim"]["secs_p99"]], nodes={k: dict(mem_max=v["mem_used_max"], load_max=v["load_max"]) for k, v in SD["nodes"].items()}, top_container=SD["top_containers_gb"][0]),
                   glm=dict(start=SG["run"]["start_utc"], end=SG["run"]["end_utc"], wall_h=round(5 + 23 / 60, 2), graded=SG["run"]["finished"], interrupted=SG["run"]["interrupted"], not_started=SG["run"]["not_started"], void=SG["run"]["void"],
                            task_hours=SG["task_hours"], spend=SG["spend"]["total"], requests=SG["tokens"]["requests"], calls=SG["shim"]["calls"], http_error=SG["shim"]["http_402"], failed_streams=SG["shim"]["failed_streams"],
                            over_120=SG["shim"]["over_120s"], secs=[SG["shim"]["secs_p50"], SG["shim"]["secs_p90"], SG["shim"]["secs_p99"]], nodes={k: dict(mem_max=v["mem_used_max"], load_max=v["load_max"]) for k, v in SG["nodes"].items()},
                            top_container=SG["top_containers_gb"][0])),
         fuzzers=dict(deepseek=XD["fuzzers"], glm=XG["fuzzers"]), self_validation=dict(deepseek=XD["self_validation"], glm=XG["self_validation"]))
json.dump(C, open(OUT + "/compare.json", "w"), indent=1)
with open(OUT + "/per_task_pair.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["position", "task", "in_fair_prefix", "in_valid51", "deepseek_outcome", "glm_outcome", "deepseek_s1s3", "glm_s1s3", "deepseek_agent_min", "glm_agent_min", "deepseek_spend", "glm_spend", "deepseek_calls", "glm_calls"])
    for i, t in enumerate(ORDER):
        d, g = DS[t], GL[t]
        w.writerow([i + 1, t, t in prefix, t in glm_valid, d["outcome"], g["outcome"], S13(d) if valid(d) else "", S13(g) if valid(g) else "", d["agent_min"], g["agent_min"] if valid(g) else "", d["spend"], g["spend"] if valid(g) else "", d["requests"], g["requests"] if valid(g) else ""])
P = C["prefix"]
print("fair prefix: first", n_prefix, "tasks (last: %s)" % prefix[-1])
for k in ("deepseek", "glm"):
    s = P[k]; print("%-8s S1-S3 %d/%d (%.0f%%, CI %s)  S1-S4 %d (%.0f%%)  at limit %d  agent min mean %.0f  spend mean %.2f total %.2f  calls/task %.0f  cached %.1f%%  prompt/call %d  out/call %d  cost at DS price %.2f" % (
        k, s["s1s3"], s["n"], s["s1s3_pct"], s["s1s3_ci"], s["s1s4"], s["s1s4_pct"], s["at_limit"], s["agent_min"]["mean"], s["spend"]["mean"], s["spend"]["total"], s["tokens"]["calls_per_task"], s["tokens"]["cached_share"], s["tokens"]["prompt_per_call"], s["tokens"]["out_per_call"], s["cost_at_common_price"]))
print("agreement S1-S3:", P["agree_s1s3"], "| S1-S4:", P["agree_s1s4"])
print("outcomes DS:", P["deepseek"]["outcomes"]); print("outcomes GLM:", P["glm"]["outcomes"])
G = C["glm51"]; print("glm51: DS S1-S3 %d/%d vs GLM %d/%d; agreement %s" % (G["deepseek"]["s1s3"], G["deepseek"]["n"], G["glm"]["s1s3"], G["glm"]["n"], G["agree_s1s3"]))
