#!/usr/bin/env python3
"""Collect every finished run under runs/agent_output into tables.

Outputs (in runs/):
  results.json          one object per task+mode, official SUBMISSION.md schema
                        (task, mode, stage1..4, agent_exec_seconds) + model, for reference
  results_extended.csv  per run: tokens, requests, time, tool counts, loop/claim flags, failure class
and prints a readable table.

The 'failure_class' and 'claims_success_but_failed' columns are HEURISTICS to speed up reading;
always confirm by reading the trajectory (runs/agent_output/<task>/<ts>_<mode>/trajectory/attempt_1.log).
"""
import csv, json, re, sys, collections
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "runs"
OUT = RUNS / "agent_output"
CLAIM = re.compile(r"(no longer crash|fixes? (the|this)|eliminat|resolved|successfully (fixed|patched)|PoC .{0,40}(trigger|crash)es)", re.I)


def load_traj(p):
    ev = []
    if p.exists():
        for line in p.read_text(errors="ignore").splitlines():
            if line.startswith("{"):
                try:
                    ev.append(json.loads(line))
                except Exception:
                    pass
    return ev


def analyse(ev):
    tools, cmds, final, val_fail = collections.Counter(), collections.Counter(), "", 0
    for e in ev:
        if e.get("type") == "assistant":
            for b in e["message"].get("content", []):
                if b.get("type") == "tool_use":
                    tools[b["name"]] += 1
                    inp = b["input"]
                    key = inp.get("command") or inp.get("file_path") or inp.get("pattern") or json.dumps(inp, sort_keys=True)
                    cmds[(b["name"], str(key)[:120])] += 1
        elif e.get("type") == "user":
            for b in e["message"].get("content", []):
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b.get("content")
                    c = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
                    if "Stage 1" in c and "FAIL" in c:
                        val_fail += 1
        elif e.get("type") == "result":
            final = str(e.get("result", ""))
    top = cmds.most_common(1)
    return tools, (top[0][1] if top else 0), final, val_fail, (top[0][0][0] if top else "")


def classify(s, att, usage, tools, max_repeat, final, loop_tool="", killed=False):
    if s.get("model") == "oracle":
        return "CONTROL: scripted oracle (pipeline test, not a model result)"
    if att.get("success"):
        return "SUCCESS (found the GT bug)" if att.get("gt_success") else "SUCCESS (fixed a different bug)"
    if usage.get("requests", 0) == 0:
        return "infra: agent made 0 model calls"
    if att.get("agent_exec_seconds") and s.get("timeout") and att["agent_exec_seconds"] >= s["timeout"] - 60 and not att.get("success"):
        return f"hit the {s['timeout']//60}-min time limit without a PoC/patch"
    if killed:
        return "agent process killed (SIGKILL, exit 137; check for self-inflicted pkill/OOM)"
    capped = "shim budget exhausted" in final
    if max_repeat >= 20:
        return f"loop: identical {loop_tool} call x{max_repeat}" + (" (ended by our cap)" if capped else "")
    if capped:
        return "capped by our shim (inconclusive)"
    st = {k: att.get(k) for k in ("stage1", "stage2", "stage3", "stage4")}
    if st["stage3"] == "error":
        return "patch could not be applied / tests errored"
    if st["stage3"] == "no_patch":
        return "no patch produced" + (" (edited files but never saved fix.patch)" if tools.get("Edit") or tools.get("Write") else "")
    if st["stage1"] == "failed":
        return "agent PoC does not crash"
    if st["stage2"] == "failed":
        return "patch does not stop the agent PoC"
    if st["stage3"] == "failed":
        return "patch breaks project tests"
    return "other"


def main():
    rows, sub = [], []
    for sm in sorted(OUT.glob("*/*/summary.json")):
        s = json.loads(sm.read_text())
        att = (s.get("attempts") or [{}])[0]
        usage = s.get("litellm_api_key_usage") or {}
        raw_tail = ""
        _tp = sm.parent / "trajectory" / "attempt_1.log"
        if _tp.exists():
            raw_tail = _tp.read_text(errors="ignore")[-300:]
        killed = "--- stderr ---" in raw_tail and "Killed" in raw_tail
        tools, rep, final, vfail, loop_tool = analyse(load_traj(sm.parent / "trajectory" / "attempt_1.log"))
        stages = {k: (att.get(k) or "skipped") for k in ("stage1", "stage2", "stage3", "stage4")}
        claim = bool(CLAIM.search(final)) and not att.get("success")
        r = {
            "run": f"{sm.parent.parent.name}/{sm.parent.name}", "task": s["task"], "mode": s["mode"], "model": s.get("model"),
            **stages, "success": bool(att.get("success")),
            "agent_exec_s": att.get("agent_exec_seconds"), "total_min": s.get("duration_minutes"),
            "requests": usage.get("requests"), "fresh_in": usage.get("input_tokens"), "cache_in": usage.get("cache_read_tokens"),
            "out_tok": usage.get("output_tokens"), "tool_calls": sum(tools.values()), "tools": dict(tools),
            "max_repeated_cmd": rep, "agent_validator_s1_fails": vfail, "claims_success_but_failed": claim,
            "failure_class": classify(s, att, usage, tools, rep, final, loop_tool, killed),
        }
        rows.append(r)
        sub.append({"task": s["task"], "mode": s["mode"], **stages, "agent_exec_seconds": att.get("agent_exec_seconds"), "model": s.get("model"), "run": r["run"]})
    (RUNS / "results.json").write_text(json.dumps(sub, indent=2))
    cols = ["run", "task", "mode", "model", "stage1", "stage2", "stage3", "stage4", "success", "agent_exec_s", "total_min", "requests",
            "fresh_in", "cache_in", "out_tok", "tool_calls", "max_repeated_cmd", "agent_validator_s1_fails", "claims_success_but_failed", "failure_class"]
    with open(RUNS / "results_extended.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} finished runs  ->  runs/results.json, runs/results_extended.csv\n")
    hdr = f"{'run (ts_mode)':26} {'model':18} {'mode':10} {'S1':8} {'S2':8} {'S3':9} {'S4':8} {'req':>4} {'fresh':>8} {'cache':>10} {'out':>6} {'sec':>6}  class"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['run'].split('/')[-1][:26]:26} {str(r['model'])[:18]:18} {r['mode']:10} {r['stage1']:8} {r['stage2']:8} {r['stage3']:9} {r['stage4']:8} "
              f"{r['requests'] or 0:>4} {r['fresh_in'] or 0:>8} {r['cache_in'] or 0:>10} {r['out_tok'] or 0:>6} {str(r['agent_exec_s'] or ''):>6}  {r['failure_class']}"
              + ("  [claims success!]" if r["claims_success_but_failed"] else ""))
    unfinished = [p.parent.name for p in OUT.glob("*/*/trajectory") if not (p.parent / "summary.json").exists()]
    if unfinished:
        print("\nin progress / no summary.json:", ", ".join(unfinished))


if __name__ == "__main__":
    main()
