#!/usr/bin/env python3
"""Fallback tests for the setup A patch: the wrapper must give the standard grader's answer, and say so in LAST_VALIDATION_MODE, when
  (1) CYBERGYM_VALIDATION_MODE is not set,           expect mode "standard"
  (2) free disk is below the threshold,              expect mode "standard_low_disk"
  (3) prepare.sh fails inside the shared path,       expect mode "standard_after_shared_failure" (simulated: the shared path's prepare call returns exit 1)
  (4) saving an image fails,                         expect mode "standard_after_shared_failure" (simulated: docker commit raises)
In every case no cgval-* image may be left. The input is one small real pair. No model is called.
usage: setup_a_fallback_test.py --harness ~/cybergym-e2e --task igraph/arvo_29408 --poc poc.bin --patch fix.patch [--json out.json]
"""
import argparse, contextlib, io, json, os, subprocess, sys, time
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--harness", required=True); ap.add_argument("--task", required=True)
ap.add_argument("--poc", required=True); ap.add_argument("--patch", required=True); ap.add_argument("--json", default=None)
args = ap.parse_args()
H = Path(args.harness).expanduser().resolve()
sys.path.insert(0, str(H / "scripts"))
import tomli                                                         # noqa: E402
import run_agent                                                     # noqa: E402

cfg = tomli.loads((H / "projects" / args.task / "../project.toml").read_text())
cfg.update(tomli.loads((H / "projects" / args.task / "config.toml").read_text()))
KW = dict(poc_path=Path(args.poc).resolve(), patch_path=Path(args.patch).resolve(), data_path=H / "data" / "projects" / args.task,
          script_path=H / "projects" / args.task, build_image=cfg["build_image"], mode="e2e")
STAGES = ("stage1", "stage2", "stage3", "stage4")
real_exec, real_run = run_agent.exec_run, run_agent.subprocess.run


def images_left():
    return len(subprocess.run(["docker", "images", "--format", "{{.Repository}}", "--filter", "reference=cgval-*"], capture_output=True, text=True).stdout.split())


def call():
    buf = io.StringIO(); t0 = time.time()
    with contextlib.redirect_stdout(buf):
        res = run_agent.run_final_validation(**KW)
    return {k: res.get(k) for k in STAGES}, round(time.time() - t0, 1), [l.strip() for l in buf.getvalue().splitlines() if "hared" in l or "prepare.sh failed" in l or "Could not save" in l][:4]


def fake_prepare_fails(c, command, *a, **k):          # only the shared path's own prepare call looks like this (validate.py calls prepare.sh itself, not through this string)
    if command.startswith("cd /src && sudo -E bash -eux /src/prepare.sh"):
        return 1, "", "simulated prepare failure"
    return real_exec(c, command, *a, **k)


class FakeRun:
    @staticmethod
    def run(cmd, *a, **k):
        if isinstance(cmd, list) and cmd[:2] == ["docker", "commit"]:
            raise subprocess.CalledProcessError(1, cmd)
        return real_run(cmd, *a, **k)


rows = []
for name, expect in (("mode unset", "standard"), ("low disk", "standard_low_disk"), ("prepare.sh fails (simulated)", "standard_after_shared_failure"),
                     ("image save fails (simulated)", "standard_after_shared_failure")):
    os.environ.pop("CYBERGYM_VALIDATION_MODE", None); os.environ.pop("CYBERGYM_SHARED_MIN_FREE_GB", None)
    run_agent.exec_run, run_agent.subprocess.run = real_exec, real_run
    if name != "mode unset":
        os.environ["CYBERGYM_VALIDATION_MODE"] = "shared"
    if name == "low disk":
        os.environ["CYBERGYM_SHARED_MIN_FREE_GB"] = "1000000"
    if name.startswith("prepare"):
        run_agent.exec_run = fake_prepare_fails
    if name.startswith("image save"):
        run_agent.subprocess.run = FakeRun.run
    res, secs, notes = call()
    run_agent.exec_run, run_agent.subprocess.run = real_exec, real_run
    row = {"case": name, "mode": run_agent.LAST_VALIDATION_MODE, "expected_mode": expect, "mode_ok": run_agent.LAST_VALIDATION_MODE == expect,
           "statuses": res, "seconds": secs, "notes": notes, "images_left": images_left()}
    print(json.dumps(row), flush=True); rows.append(row)
same = all(r["statuses"] == rows[0]["statuses"] for r in rows)
print("ALL MODES OK:", all(r["mode_ok"] for r in rows), "| ALL STATUSES EQUAL:", same, "| IMAGES LEFT:", images_left())
if args.json:
    Path(args.json).write_text(json.dumps(rows, indent=1))
