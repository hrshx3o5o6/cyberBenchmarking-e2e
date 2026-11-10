#!/usr/bin/env python3
"""Check the setup A patch (tools/patch_setup_a.py) by calling the harness's own functions: run_final_validation (shared when
CYBERGYM_VALIDATION_MODE=shared) and, with --standard, run_final_validation_standard on the same input, then compare the stage statuses.
Also checks that no cgval-* image or container is left behind. No model is called.

Cases come from a JSON list: [{"label": "...", "task": "igraph/arvo_29408", "poc": "x.bin", "patch": "y.patch", "expect": {"stage1": "passed", ...}}]
("expect" is optional: recorded statuses, e.g. from an earlier run, to compare against when --standard is not used).
usage: setup_a_check.py --harness ~/cybergym-e2e --cases cases.json [--standard] [--env KEY=VALUE ...] [--json out.json]
  --env  extra environment for the shared call, e.g. CYBERGYM_SHARED_MIN_FREE_GB=100000 to test the disk fallback
"""
import argparse, contextlib, io, json, os, subprocess, sys, time
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--harness", required=True)
ap.add_argument("--cases", required=True)
ap.add_argument("--standard", action="store_true", help="also run the standard grader on each input and compare")
ap.add_argument("--env", action="append", default=[])
ap.add_argument("--json", default=None)
args = ap.parse_args()

H = Path(args.harness).expanduser().resolve()
sys.path.insert(0, str(H / "scripts"))
import tomli                                                         # noqa: E402
import run_agent                                                     # noqa: E402

STAGES = ("stage1", "stage2", "stage3", "stage4")
for kv in args.env:
    k, v = kv.split("=", 1)
    os.environ[k] = v


def leftovers():
    imgs = subprocess.run(["docker", "images", "--format", "{{.Repository}}", "--filter", "reference=cgval-*"], capture_output=True, text=True).stdout.split()
    return len(imgs)


def run(fn, case):
    task = case["task"]
    cfg = tomli.loads((H / "projects" / task / "../project.toml").read_text())
    cfg.update(tomli.loads((H / "projects" / task / "config.toml").read_text()))
    buf = io.StringIO(); t0 = time.time()
    with contextlib.redirect_stdout(buf):
        res = fn(poc_path=Path(case["poc"]).resolve(), patch_path=Path(case["patch"]).resolve(), data_path=H / "data" / "projects" / task,
                 script_path=H / "projects" / task, build_image=cfg["build_image"], mode="e2e")
    return {k: res.get(k) for k in STAGES}, round(time.time() - t0, 1), buf.getvalue()


out = []
for case in json.load(open(args.cases)):
    row = {"label": case["label"], "task": case["task"]}
    os.environ["CYBERGYM_VALIDATION_MODE"] = "shared"
    row["shared"], row["shared_s"], log = run(run_agent.run_final_validation, case)
    row["mode_used"] = run_agent.LAST_VALIDATION_MODE
    row["shared_log_lines"] = [l.strip() for l in log.splitlines() if "Shared" in l or "shared" in l or "skipped" in l.lower()][:6]
    ref = None
    if args.standard:
        os.environ.pop("CYBERGYM_VALIDATION_MODE", None)
        row["standard"], row["standard_s"], _ = run(run_agent.run_final_validation, case)
        row["standard_mode_used"] = run_agent.LAST_VALIDATION_MODE
        ref = row["standard"]
        row["speedup"] = round(row["standard_s"] / max(row["shared_s"], 0.1), 2)
    elif case.get("expect"):
        ref = case["expect"]
    if ref is not None:
        row["same_statuses"] = all(row["shared"].get(k) == ref.get(k) for k in STAGES)
    row["images_left"] = leftovers()
    print(json.dumps(row), flush=True)
    out.append(row)
if args.json:
    Path(args.json).write_text(json.dumps(out, indent=1))
print("ALL SAME:", all(r.get("same_statuses", True) for r in out), "| images left:", leftovers())
