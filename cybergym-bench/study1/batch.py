#!/usr/bin/env python3
"""Study 1 batch driver. For each task and each model, runs Claude Code and Codex AT THE SAME TIME (a pair),
so provider load and time of day do not favour one harness. Resumable: a cell already logged DONE is skipped.
  batch.py --tasks 10 --pairs 2          (4 runs in parallel)
"""
import argparse, concurrent.futures as cf, pathlib, re, subprocess, threading, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent                                   # ~/cybergym-bench
MODELS = {"vidoc": ("vidoc-1", 4004), "laguna": ("poolside/laguna-s-2.1", 4001), "ling": ("inclusionai/ling-3.0-flash", 4002), "qwen27b": ("qwen/qwen3.8-27b", 4003)}
AGENTS = ["claude-code", "codex"]
TAG = "study1"
PROG = ROOT / "runs/study1/progress.log"
LOGS = ROOT / "runs/study1/logs"; LOGS.mkdir(parents=True, exist_ok=True)
LOCK = threading.Lock()


def say(msg):
    line = f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}"
    with LOCK, open(PROG, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def done_cells():
    if not PROG.exists():
        return set()
    return set(re.findall(r"DONE\s+(\S+\|\S+\|\S+)", PROG.read_text()))


def run_cell(task, mname, agent, timeout):
    model, port = MODELS[mname]
    key = f"{task}|{mname}|{agent}"
    log = LOGS / (key.replace("/", "_").replace("|", "__") + ".log")
    say(f"START {key}")
    with open(log, "w") as f:
        rc = subprocess.run([str(HERE / "study.sh"), "run", task, model, agent, str(port), str(timeout)], stdout=f, stderr=subprocess.STDOUT).returncode
    m = re.findall(r"Attempt 1:.*", log.read_text())
    say(f"DONE  {key} exit={rc} -> {m[-1].strip() if m else 'NO RESULT LINE (infra failure?)'}")


def run_pair(task, mname, timeout):
    done = done_cells()
    todo = [a for a in AGENTS if f"{task}|{mname}|{a}" not in done]
    ts = [threading.Thread(target=run_cell, args=(task, mname, a, timeout)) for a in todo]
    for t in ts: t.start()
    for t in ts: t.join()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, default=10); ap.add_argument("--pairs", type=int, default=2)
    ap.add_argument("--models", default="laguna,ling,qwen27b"); ap.add_argument("--tasks-file", default="study1_tasks_20.txt"); ap.add_argument("--tag", default="study1"); ap.add_argument("--timeout", type=int, default=5400)
    a = ap.parse_args()
    global PROG
    if a.tag != "study1":
        PROG = ROOT / f"runs/study1/progress_{a.tag}.log"
    tasks = [l.strip() for l in (HERE / a.tasks_file).read_text().split()][: a.tasks]
    models = a.models.split(",")
    jobs = [(t, m) for t in tasks for m in models]
    say(f"BATCH START tasks={len(tasks)} models={models} agents={AGENTS} pairs={a.pairs} jobs={len(jobs)} runs={len(jobs) * 2}")
    with cf.ThreadPoolExecutor(max_workers=a.pairs) as ex:
        list(ex.map(lambda j: run_pair(j[0], j[1], a.timeout), jobs))
    say("BATCH FINISHED")


if __name__ == "__main__":
    main()
