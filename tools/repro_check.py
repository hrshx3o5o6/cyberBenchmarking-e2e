#!/usr/bin/env python3
"""Is the patched build reproducible? Build the PATCHED tree in N fresh containers the way the standard grader does for S2, S3 and S4
(one container each, own setup, own prepare.sh, own compile) and compare what each build produced.

Compared: every file under /out (the fuzz binaries the PoC runs), and every object file, archive and shared library under /src
(what the project's tests may link). Same hash in all N containers = the three standard builds were byte-identical, so sharing one build
(variants A and B) cannot change what a stage sees. Different hashes = report which files, how many bytes differ, and the ELF build-id.

Runs on the machine with Docker, the harness checkout and the task images. No model is called. Nothing is written outside the containers
except the JSON result and a temporary folder for the few differing files.

usage: repro_check.py --harness ~/cybergym-e2e --task igraph/arvo_29408 --poc poc.bin --patch fix.patch [--n 3] [--json out.json]
"""
import argparse, json, subprocess, sys, tempfile, time
import concurrent.futures as cf
from pathlib import Path

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--harness", required=True)
ap.add_argument("--task", required=True)
ap.add_argument("--poc", required=True)
ap.add_argument("--patch", required=True)
ap.add_argument("--n", type=int, default=3, help="number of independent builds (the standard grader makes 3 patched builds: S2, S3, S4)")
ap.add_argument("--json", default=None)
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
VALIDATE = "/scripts/.venv/bin/python /scripts/validate.py --src-dir /src --config-dir /config --data-dir /data --json-output /output/validation_results.json"
HASH_OUT = "sudo bash -c 'cd /out && find . -type f -print0 | sort -z | xargs -0 -r sha256sum'"
HASH_OBJ = ("sudo bash -c \"cd /src && find . -type f \\( -name '*.o' -o -name '*.a' -o -name '*.so' -o -name '*.so.*' \\) "
            "-not -path './.git/*' -print0 | sort -z | xargs -0 -r sha256sum\"")


def read_json(container, path):
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as t:
        p = t.name
    r = subprocess.run(["docker", "cp", f"{container}:{path}", p], capture_output=True)
    try:
        return json.load(open(p)) if r.returncode == 0 else None
    except ValueError:
        return None


def parse(text):
    d = {}
    for line in (text or "").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            d[parts[1].strip()] = parts[0]
    return d


def build(i):
    t0 = time.time(); c = start_container(IMAGE)
    try:
        setup_workspace(c, DATA_PATH, SCRIPT_PATH, "e2e", scripts_dir=SCRIPTS)
        copy_to_container(c, POC, "/output/poc.bin"); copy_to_container(c, PATCH, "/output/fix.patch")
        code, out, err = exec_run(c, VALIDATE + " --only-stage 2 --poc-file /output/poc.bin --patch-file /output/fix.patch --run-prepare",
                                  None, timeout=7200, workdir="/", verbose=False)
        r = read_json(c, "/output/validation_results.json")
        t_build = round(time.time() - t0, 1)
        _, o1, _ = exec_run(c, HASH_OUT, None, timeout=900, workdir="/", verbose=False)
        _, o2, _ = exec_run(c, HASH_OBJ, None, timeout=900, workdir="/", verbose=False)
    except BaseException:
        cleanup_container(c)
        raise
    return {"container": c, "stage2": (r or {}).get("stage2") or "error", "exit": code, "seconds": t_build, "out": parse(o1), "objs": parse(o2)}


def compare(builds, key):
    names = sorted(set().union(*[set(b[key]) for b in builds]))
    same, diff, missing = [], [], []
    for n in names:
        hs = [b[key].get(n) for b in builds]
        if None in hs:
            missing.append(n)
        elif len(set(hs)) == 1:
            same.append(n)
        else:
            diff.append(n)
    return same, diff, missing


def inspect_diff(builds, name, root):
    """Copy one differing file out of the first two containers and measure how they differ."""
    tmp = Path(tempfile.mkdtemp(prefix="repro_"))
    paths = []
    for k, b in enumerate(builds[:2]):
        dst = tmp / f"{k}_{Path(name).name}"
        subprocess.run(["docker", "cp", f"{b['container']}:{root}/{name}", str(dst)], capture_output=True)
        paths.append(dst)
    info = {"file": name, "size": [p.stat().st_size if p.exists() else None for p in paths]}
    if all(p.exists() for p in paths):
        cmp_out = subprocess.run(["cmp", "-l", str(paths[0]), str(paths[1])], capture_output=True, text=True).stdout
        info["bytes_differing"] = len(cmp_out.splitlines())
        ids = []
        for p in paths:
            n = subprocess.run(["readelf", "-n", str(p)], capture_output=True, text=True).stdout
            ids.append(next((l.split(":")[-1].strip() for l in n.splitlines() if "Build ID" in l), None))
        info["build_id"] = ids
    return info


builds = []
try:
    with cf.ThreadPoolExecutor(args.n) as pool:
        futs = [pool.submit(build, i) for i in range(args.n)]
        builds = [f.result() for f in futs]
    result = {"task": args.task, "n": args.n, "stage2_statuses": [b["stage2"] for b in builds], "build_seconds": [b["seconds"] for b in builds]}
    for key, root in (("out", "/out"), ("objs", "/src")):
        same, diff, missing = compare(builds, key)
        result[key] = {"files": len(same) + len(diff) + len(missing), "identical": len(same), "different": diff[:50], "missing_in_some": missing[:50],
                       "different_details": [inspect_diff(builds, n, root) for n in diff[:8]]}
    result["reproducible"] = all(not result[k]["different"] and not result[k]["missing_in_some"] for k in ("out", "objs")) and result["out"]["files"] > 0
    print(json.dumps({k: (v if k not in ("out", "objs") else {kk: vv for kk, vv in v.items() if kk != "different_details"}) for k, v in result.items()}, indent=1), flush=True)
    for key in ("out", "objs"):
        for d in result[key]["different_details"]:
            print(key, "DIFF", json.dumps(d), flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1))
finally:
    for b in builds:
        cleanup_container(b["container"])
