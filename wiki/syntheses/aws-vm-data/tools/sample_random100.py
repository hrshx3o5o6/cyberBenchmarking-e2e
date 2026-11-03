#!/usr/bin/env python3
"""Seeded uniform random sample of CyberGym-E2E tasks (no stratification), reproducible byte for byte.

Pool   = scripts/tasks.txt (920 tasks) minus the five hand-picked pilot tasks (chosen as small and easy; md4c is also the smoke-test task).
Order  = pool sorted by sha256(f"{SEED}:random:{task}") ascending: a fixed random permutation that needs no RNG library.
Sample = the first N tasks in that order that pass the infrastructure gate (no model involved):
         projects/<task>/config.toml exists locally, and the HF dataset lists src.tgz, poc.bin and crash.log for it.
A rejected task is replaced by the next one in the order; this is decided before any scored run and logged.

usage: sample_random100.py <path to the cybergym-e2e checkout> [seed] [n] [out dir]
"""
import hashlib, json, sys, tomllib, urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1])
SEED = sys.argv[2] if len(sys.argv) > 2 else "20261103"
N = int(sys.argv[3]) if len(sys.argv) > 3 else 100
OUT = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(".")
EXCLUDED = ["hunspell/arvo_52195", "igraph/arvo_29408", "md4c/arvo_31332", "libsndfile/arvo_27503", "libssh2/arvo_65212"]
NEEDED = {"src.tgz", "poc.bin", "crash.log"}
h = lambda s: hashlib.sha256(s.encode()).hexdigest()

tasks = [t.strip() for t in (ROOT / "scripts" / "tasks.txt").read_text().splitlines() if t.strip()]
assert len(tasks) == len(set(tasks)) == 920
pool = [t for t in tasks if t not in EXCLUDED]
order = sorted(pool, key=lambda t: h(f"{SEED}:random:{t}"))
info = json.load(urllib.request.urlopen("https://huggingface.co/api/datasets/sunblaze-ucb/cybergym-e2e", timeout=60))
files = {}
for s in info.get("siblings", []):
    f = s["rfilename"]
    if f.startswith("projects/"):
        task, _, name = f[len("projects/"):].rpartition("/")
        files.setdefault(task, set()).add(name)

def meta(task):
    p, tid = task.split("/")
    m = {**tomllib.loads((ROOT / "projects" / p / "project.toml").read_text()), **tomllib.loads((ROOT / "projects" / p / tid / "config.toml").read_text())}
    diff = (ROOT / "projects" / p / tid / "patch.diff").read_text(errors="replace").splitlines()
    changed = sum(1 for l in diff if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))
    return {"task": task, "project": p, "id_kind": tid.split("_")[0], "language": m.get("language"), "build_image": m.get("build_image"), "fix_changed_lines": changed}

accepted, rejected = [], []
for t in order:
    if len(accepted) == N: break
    if not (ROOT / "projects" / t / "config.toml").is_file(): rejected.append((t, "no config.toml")); continue
    if not NEEDED <= files.get(t, set()): rejected.append((t, f"HF missing {sorted(NEEDED - files.get(t, set()))}")); continue
    accepted.append(t)
body = "\n".join(accepted) + "\n"
(OUT / f"random{N}_tasks.txt").write_text(body)
(OUT / f"random{N}_manifest.json").write_text(json.dumps({"seed": SEED, "n": N, "pool": len(pool), "rule": "sha256(seed:random:task) ascending, first N passing the gate",
    "excluded": EXCLUDED, "rejected": rejected, "list_sha256": hashlib.sha256(body.encode()).hexdigest(), "tasks": [meta(t) for t in accepted]}, indent=1) + "\n")
print("seed", SEED, "pool", len(pool), "accepted", len(accepted), "rejected", rejected)
print("list sha256", hashlib.sha256(body.encode()).hexdigest())
