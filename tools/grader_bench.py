#!/usr/bin/env python3
"""Compare CyberGym-E2E's validation (the grader) as the harness runs it with a variant that shares work between the four stages.

BASELINE  = what run_agent.run_final_validation does (end-to-end mode): one fresh container per stage, each repeating the setup (apt,
            dependencies, source extraction, prepare.sh, snapshot) and each building the project: S1 on the vulnerable tree, S2, S3 and S4
            each on the patched tree. Same commands, plus a timer around every stage.
VARIANT   = prepared image (setup + prepare.sh + snapshot, done once) -> S1 builds the vulnerable tree from it; the patched tree is built
            once and saved as an image; S2, S3 and S4 each start in a fresh container from that image and only run their own check.
            Nothing is shared between containers except those two saved images; the stage skip rules are the same.

VARIANT B = no saved images at all: container A builds the VULNERABLE tree and runs S1 (exactly as the standard stage 1); container B, at the same time,
            runs the standard stage 2 through validate.py (prepare, snapshot, restore, apply the patch, build the PATCHED tree once, run the agent's PoC) and then,
            in the same container, S4 (the ground-truth PoC, which only executes the binary) and last S3 (the project's tests, which can modify the tree).
            Skip rules are applied to the results afterwards, so the statuses are the ones the standard grader would report.

Runs on the machine that has Docker, the harness checkout and the task images (the head VM). No model is called.

usage: grader_bench.py --harness ~/cybergym-e2e --task igraph/arvo_29408 --poc poc.bin --patch fix.patch [--mode baseline|variant|both|b|bothb] [--ref earlier.json] [--json out.json] [--keep]
Result: one JSON object per mode with the status and the seconds of each stage; with --mode both, a comparison of the statuses.
"""
import argparse, json, subprocess, sys, tempfile, time
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--harness", required=True, help="the cybergym-e2e checkout (scripts/, projects/, data/)")
ap.add_argument("--task", required=True, help="project/task, e.g. igraph/arvo_29408")
ap.add_argument("--poc", required=True)
ap.add_argument("--patch", required=True)
ap.add_argument("--mode", choices=["baseline", "variant", "both", "b", "bothb"], default="both")
ap.add_argument("--ref", default=None, help="with --mode b: an earlier result JSON whose baseline statuses and time are the reference")
ap.add_argument("--json", default=None)
ap.add_argument("--keep", action="store_true", help="keep the saved images (default: delete them)")
args = ap.parse_args()

H = Path(args.harness).expanduser().resolve()
sys.path.insert(0, str(H / "scripts"))
import tomli                                                        # noqa: E402
from utils import start_container, setup_workspace, copy_to_container, exec_run, cleanup_container   # noqa: E402

SCRIPTS = H / "scripts"
SCRIPT_PATH = H / "projects" / args.task
DATA_PATH = H / "data" / "projects" / args.task
CONFIG = tomli.loads((SCRIPT_PATH / "../project.toml").read_text())
CONFIG.update(tomli.loads((SCRIPT_PATH / "config.toml").read_text()))
IMAGE = CONFIG["build_image"]
POC, PATCH = Path(args.poc).resolve(), Path(args.patch).resolve()
TAG = args.task.replace("/", "-").replace("_", "-").lower()
VALIDATE = "/scripts/.venv/bin/python /scripts/validate.py --src-dir /src --config-dir /config --data-dir /data --json-output /output/validation_results.json"
SKIP_RULES = {2: 1, 3: 2, 4: 3}          # a stage runs only if the one before it passed (run_final_validation)


def read_json(container, path):
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as t:
        p = t.name
    r = subprocess.run(["docker", "cp", f"{container}:{path}", p], capture_output=True)
    try:
        return json.load(open(p)) if r.returncode == 0 else None
    except ValueError:
        return None


def summary_line(text):
    for l in (text or "").splitlines():
        if "SUMMARY:" in l or "ERROR:" in l and "Sanitizer" in l:
            return l.strip()[:200]
    return None


def baseline():
    res, secs, notes = {}, {}, {}
    for stage in (1, 2, 3, 4):
        if stage in SKIP_RULES and res.get(SKIP_RULES[stage]) != "passed":
            res[stage], secs[stage] = "skipped", 0.0
            continue
        t0 = time.time(); c = start_container(IMAGE)
        try:
            setup_workspace(c, DATA_PATH, SCRIPT_PATH, "e2e", scripts_dir=SCRIPTS)
            t_setup = time.time() - t0
            copy_to_container(c, POC, "/output/poc.bin"); copy_to_container(c, PATCH, "/output/fix.patch")
            cmd = VALIDATE + f" --only-stage {stage}"
            if stage in (1, 2):
                cmd += " --poc-file /output/poc.bin"
            cmd += " --patch-file /output/fix.patch --run-prepare"
            t1 = time.time()
            code, out, err = exec_run(c, cmd, None, timeout=7200, workdir="/", verbose=False)
            r = read_json(c, "/output/validation_results.json")
            res[stage] = (r or {}).get(f"stage{stage}") or "error"
            secs[stage] = round(time.time() - t0, 1)
            notes[stage] = {"setup_s": round(t_setup, 1), "validate_s": round(time.time() - t1, 1), "exit": code, "tail": (out or "")[-300:]}
        finally:
            cleanup_container(c)
    return {"status": res, "seconds": secs, "total_s": round(sum(secs.values()), 1), "notes": notes}


def run_stage_check(image, stage, kind):
    """Fresh container from a saved image; run only the stage's own check."""
    t0 = time.time(); c = start_container(image)
    try:
        copy_to_container(c, POC, "/output/poc.bin"); copy_to_container(c, PATCH, "/output/fix.patch")
        if kind == "poc":
            src = "/output/poc.bin" if stage == 2 else "/data/poc.bin"
            code, out, err = exec_run(c, f"cp {src} /src/poc.bin && cd /src && sudo -E bash -eux /src/run_poc.sh", None, timeout=1200, workdir="/", verbose=False)
            status = "error" if code == 124 else ("passed" if code == 0 else "failed")
        else:
            code, out, err = exec_run(c, "cd /src && sudo -E bash -eux /src/test.sh", None, timeout=1800, workdir="/", verbose=False)
            status = "error" if code == 124 else ("passed" if code == 0 else "failed")
        return status, round(time.time() - t0, 1), {"exit": code, "summary": summary_line(out + err)}
    finally:
        cleanup_container(c)


def variant():
    res, secs, notes, images = {}, {}, {}, []
    t_all = time.time()
    # prepared image: setup + prepare.sh + snapshot, once
    t0 = time.time(); p = start_container(IMAGE)
    try:
        setup_workspace(p, DATA_PATH, SCRIPT_PATH, "e2e", scripts_dir=SCRIPTS)
        notes["prep_setup_s"] = round(time.time() - t0, 1); t_p = time.time()
        code, out, err = exec_run(p, "cd /src && sudo -E bash -eux /src/prepare.sh", None, timeout=1800, workdir="/", verbose=False)
        notes["prep_prepare_sh_s"] = round(time.time() - t_p, 1)
        if code != 0:
            return {"status": {1: "error", 2: "error", 3: "error", 4: "error"}, "error": "prepare.sh failed: " + (err or "")[-300:]}
        exec_run(p, "sudo cp -a /src /src_backup", None, timeout=1800, workdir="/", verbose=False, check=True)
        prep = f"gb-prep-{TAG}"          # containers are started with --rm, so they are committed while running (docker commit pauses them)
        t_c = time.time(); subprocess.run(["docker", "commit", p, prep], capture_output=True, check=True); images.append(prep)
        notes["prep_commit_s"] = round(time.time() - t_c, 1)
    finally:
        cleanup_container(p)
    secs["prepare_once"] = round(time.time() - t0, 1)
    # S1: vulnerable build from the prepared image
    t0 = time.time(); c = start_container(prep)
    try:
        copy_to_container(c, POC, "/output/poc.bin")
        code, out, err = exec_run(c, VALIDATE + " --only-stage 1 --poc-file /output/poc.bin", None, timeout=7200, workdir="/", verbose=False)
        r = read_json(c, "/output/validation_results.json"); res[1] = (r or {}).get("stage1") or "error"
        notes[1] = {"exit": code, "tail": (out or "")[-200:]}
    finally:
        cleanup_container(c)
    secs[1] = round(time.time() - t0, 1)
    # the patched tree, built once and saved (not at all if S1 failed: S2 to S4 are skipped by the stage rules then)
    t0 = time.time(); built = None; q = start_container(prep) if res.get(1) == "passed" else None
    try:
        if q is None:
            raise StopIteration
        copy_to_container(q, PATCH, "/output/fix.patch")
        apply = ("/scripts/.venv/bin/python -c \"import sys, tomli; sys.path.insert(0, '/scripts'); import validate; "
                 "cfg = tomli.loads(open('/config/config.toml').read()); validate.apply_patch('/src/' + cfg['repo_to_patch'], '/output/fix.patch', True)\"")
        code, out, err = exec_run(q, apply, None, timeout=600, workdir="/", verbose=False)
        if code == 0:
            code, out, err = exec_run(q, "cd /src && sudo -E bash -eux /src/compile.sh", None, timeout=3600, workdir="/", verbose=False)
        if code == 0:
            built = f"gb-built-{TAG}"
            t_c = time.time(); subprocess.run(["docker", "commit", q, built], capture_output=True, check=True); images.append(built)
            notes["built_commit_s"] = round(time.time() - t_c, 1)
        notes["patched_build"] = {"exit": code, "tail": (err or "")[-200:]}
    except StopIteration:
        pass
    finally:
        cleanup_container(q)
    secs["patched_build_once"] = round(time.time() - t0, 1)
    # S2, S3, S4 from the saved patched build, with the same skip rules
    for stage, kind in ((2, "poc"), (3, "tests"), (4, "poc")):
        if res.get(SKIP_RULES[stage]) != "passed":
            res[stage], secs[stage] = "skipped", 0.0
        elif built is None:
            res[stage], secs[stage] = "error", 0.0
        else:
            res[stage], secs[stage], notes[stage] = run_stage_check(built, stage, kind)
    sizes = {}
    for im in images:
        r = subprocess.run(["docker", "image", "inspect", "--format", "{{.Size}}", im], capture_output=True, text=True)
        sizes[im] = round(int(r.stdout.strip() or 0) / 1e9, 2)
        if not args.keep:
            subprocess.run(["docker", "rmi", "-f", im], capture_output=True)
    return {"status": res, "seconds": secs, "total_s": round(time.time() - t_all, 1), "image_gb": sizes, "notes": notes}


def variant_b():
    """Two containers at once, no saved images (see the module docstring)."""
    import concurrent.futures as cf

    def ready():
        c = start_container(IMAGE)
        setup_workspace(c, DATA_PATH, SCRIPT_PATH, "e2e", scripts_dir=SCRIPTS)
        copy_to_container(c, POC, "/output/poc.bin"); copy_to_container(c, PATCH, "/output/fix.patch")
        return c

    def check(c, command, timeout):
        code, out, err = exec_run(c, command, None, timeout=timeout, workdir="/", verbose=False)
        return "error" if code == 124 else ("passed" if code == 0 else "failed")

    def container_a():                                   # S1, as the standard stage 1
        t0 = time.time(); c = ready()
        try:
            exec_run(c, VALIDATE + " --only-stage 1 --poc-file /output/poc.bin --patch-file /output/fix.patch --run-prepare", None, timeout=7200, workdir="/", verbose=False)
            r = read_json(c, "/output/validation_results.json")
            return (r or {}).get("stage1") or "error", round(time.time() - t0, 1)
        finally:
            cleanup_container(c)

    def container_b():                                   # S2 through validate.py, then S4, then the tests
        t0 = time.time(); c = ready(); res, secs = {}, {}
        try:
            exec_run(c, VALIDATE + " --only-stage 2 --poc-file /output/poc.bin --patch-file /output/fix.patch --run-prepare", None, timeout=7200, workdir="/", verbose=False)
            r = read_json(c, "/output/validation_results.json"); res[2] = (r or {}).get("stage2") or "error"; secs[2] = round(time.time() - t0, 1)
            if res[2] == "passed":
                t1 = time.time(); res[4] = check(c, "cp /data/poc.bin /src/poc.bin && cd /src && sudo -E bash -eux /src/run_poc.sh", 1200); secs[4] = round(time.time() - t1, 1)
                t1 = time.time(); res[3] = check(c, "cd /src && sudo -E bash -eux /src/test.sh", 1800); secs[3] = round(time.time() - t1, 1)
            return res, secs, round(time.time() - t0, 1)
        finally:
            cleanup_container(c)

    t_all = time.time()
    with cf.ThreadPoolExecutor(2) as pool:
        fa, fb = pool.submit(container_a), pool.submit(container_b)
        s1, secs_a = fa.result(); res_b, secs_b, total_b = fb.result()
    ok1 = s1 == "passed"
    status = {1: s1, 2: res_b[2] if ok1 else "skipped"}
    status[3] = res_b.get(3, "skipped") if ok1 and status[2] == "passed" else "skipped"
    status[4] = res_b.get(4, "skipped") if status[3] == "passed" else "skipped"        # S4 only counts when S3 passed, as in the standard grader
    return {"status": status, "seconds": {"container_A_S1": secs_a, "container_B_total": total_b, **{f"B_S{k}": v for k, v in sorted(secs_b.items())}},
            "total_s": round(time.time() - t_all, 1), "container_seconds_sum": round(secs_a + total_b, 1), "raw_B_statuses": {str(k): v for k, v in res_b.items()}}


out = {"task": args.task, "build_image": IMAGE.split("@")[0]}
if args.mode in ("baseline", "both", "bothb"):
    out["baseline"] = baseline()
    print("baseline:", json.dumps({k: out["baseline"][k] for k in ("status", "seconds", "total_s")}), flush=True)
if args.mode in ("variant", "both"):
    out["variant"] = variant()
    print("variant: ", json.dumps({k: out["variant"].get(k) for k in ("status", "seconds", "total_s", "image_gb")}), flush=True)
if args.mode == "both":
    b, v = out["baseline"]["status"], out["variant"]["status"]
    out["same_statuses"] = all(b.get(s) == v.get(s) for s in (1, 2, 3, 4))
    out["speedup"] = round(out["baseline"]["total_s"] / max(out["variant"]["total_s"], 1), 2)
    print("same statuses:", out["same_statuses"], "| baseline %.0f s, variant %.0f s, ratio %.2f" % (out["baseline"]["total_s"], out["variant"]["total_s"], out["speedup"]))
if args.mode in ("b", "bothb"):
    out["variant_b"] = variant_b()
    print("variant B:", json.dumps({k: out["variant_b"][k] for k in ("status", "seconds", "total_s", "container_seconds_sum")}), flush=True)
    ref = out.get("baseline") or (json.load(open(args.ref))["baseline"] if args.ref else None)
    if ref:
        b, v = {str(k): x for k, x in ref["status"].items()}, {str(k): x for k, x in out["variant_b"]["status"].items()}
        out["same_statuses_b"] = all(b.get(s) == v.get(s) for s in "1234")
        out["speedup_b"] = round(ref["total_s"] / max(out["variant_b"]["total_s"], 1), 2)
        print("variant B same statuses:", out["same_statuses_b"], "| standard %.0f s, B %.0f s (wall), ratio %.2f; B container time %.0f s" % (ref["total_s"], out["variant_b"]["total_s"], out["speedup_b"], out["variant_b"]["container_seconds_sum"]), flush=True)
if args.json:
    Path(args.json).write_text(json.dumps(out, indent=1))
