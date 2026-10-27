#!/usr/bin/env python3
"""Seeded random sample of CyberGym-E2E tasks, validated, with image estimate.

Shuffle all tasks with the seed, walk the shuffled order, accept a task only if
(1) projects/<task>/config.toml exists, (2) HF dataset lists src.tgz, poc.bin and
crash.log for it. The first N accepted tasks are the sample; rejected ones are reported.
"""
import json, random, sys, tomllib, urllib.request
from pathlib import Path
from collections import Counter

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 20261023
N = int(sys.argv[2]) if len(sys.argv) > 2 else 50
ROOT = Path("/Users/harsha/Downloads/Harsha_Stuff/internships/spark/research/cybergym-bench/cybergym-e2e")
DEFAULT_IMAGE = "gcr.io/oss-fuzz-base/base-builder@sha256:8eda74a11e800aead5a041ee479a65b33dab3150d6e89e5694e2b6eb27be98fc"
NEEDED = {"src.tgz", "poc.bin", "crash.log"}

tasks = [t.strip() for t in (ROOT / "scripts" / "tasks.txt").read_text().splitlines() if t.strip()]
info = json.load(urllib.request.urlopen("https://huggingface.co/api/datasets/sunblaze-ucb/cybergym-e2e", timeout=60))
files = {}
for s in info.get("siblings", []):
    f = s["rfilename"]
    if f.startswith("projects/"):
        task, _, name = f[len("projects/"):].rpartition("/")
        files.setdefault(task, set()).add(name)

def image_for(task):
    d = ROOT / "projects" / task
    merged = tomllib.loads((d.parent / "project.toml").read_text())
    merged.update(tomllib.loads((d / "config.toml").read_text()))
    return merged.get("build_image", DEFAULT_IMAGE)

order = sorted(set(tasks))
random.Random(SEED).shuffle(order)
accepted, rejected = [], []
for t in order:
    if len(accepted) == N: break
    why = None
    if not (ROOT / "projects" / t / "config.toml").is_file(): why = "no config.toml"
    elif not NEEDED <= files.get(t, set()): why = f"HF missing {sorted(NEEDED - files.get(t, set()))}"
    else:
        try: img = image_for(t)
        except Exception as e: why = f"image lookup: {type(e).__name__}"
    (rejected.append((t, why)) if why else accepted.append((t, img)))

out = {
    "seed": SEED, "n": N, "total_tasks": len(order), "hf_tasks_listed": len(files),
    "tasks": [t for t, _ in accepted], "rejected": rejected,
    "images": {t: i for t, i in accepted},
}
Path("sample50.json").write_text(json.dumps(out, indent=2) + "\n")
Path("sample50_tasks.txt").write_text("\n".join(t for t, _ in accepted) + "\n")
imgs = Counter(i for _, i in accepted)
vm_have = ["n132/arvo:41221-fix", "n132/arvo:61822-fix", "cybergym/oss-fuzz:42537128-fix"]
print(f"seed={SEED} listed={len(order)} hf_tasks={len(files)} accepted={len(accepted)} rejected={len(rejected)}")
for t, w in rejected: print("  rejected", t, w)
print("projects:", len({t.split('/')[0] for t, _ in accepted}), " distinct images:", len(imgs))
print("project counts (top):", Counter(t.split('/')[0] for t, _ in accepted).most_common(6))
print("kind:", Counter('arvo' if '/arvo_' in t else 'oss-fuzz' for t, _ in accepted))
print("already on VM:", [t for t, i in accepted if i in vm_have])
print("shared base-builder default:", sum(1 for _, i in accepted if i == DEFAULT_IMAGE))
print("tasks:"); [print("  ", t) for t, _ in accepted]
