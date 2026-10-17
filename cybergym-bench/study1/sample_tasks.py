#!/usr/bin/env python3
"""Deterministic, project-stratified ordering of the CyberGym-E2E tasks.

Algorithm (fully specified so anyone can reproduce the list byte for byte):
  1. Pool = scripts/tasks.txt (920 tasks) minus EXCLUDED (the five hand-picked pilot tasks).
  2. Group the pool by project. Within each project, order tasks by
     sha256(f"{SEED}:task:{task}") ascending.
  3. Build the ordered list in rounds. In round r (r = 0, 1, 2, ...), take the r-th task of every
     project that still has one, visiting those projects in order of
     sha256(f"{SEED}:round{r}:{project}") ascending.
  4. The study uses prefixes of this list (first 20, later first 50 / 100). Extending a prefix
     never changes tasks already run.
No third-party RNG is used, so the result does not depend on the Python version.

Usage: sample_tasks.py [--check]   (--check re-derives the list and compares it with the files)
"""
import argparse, collections, hashlib, json, pathlib, sys, tomllib

SEED = "20261016"
HERE = pathlib.Path(__file__).resolve().parent
E2E = HERE.parent / "cybergym-e2e"
EXCLUDED = ["hunspell/arvo_52195", "igraph/arvo_29408", "md4c/arvo_31332",
            "libsndfile/arvo_27503", "libssh2/arvo_65212"]


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def build_order():
    tasks = [l.strip() for l in (E2E / "scripts" / "tasks.txt").read_text().splitlines() if l.strip()]
    assert len(tasks) == len(set(tasks)) == 920, len(tasks)
    pool = [t for t in tasks if t not in EXCLUDED]
    by_proj = collections.defaultdict(list)
    for t in pool:
        by_proj[t.split("/")[0]].append(t)
    for p in by_proj:
        by_proj[p].sort(key=lambda t: h(f"{SEED}:task:{t}"))
    ordered, r = [], 0
    while True:
        projs = [p for p in by_proj if len(by_proj[p]) > r]
        if not projs:
            break
        projs.sort(key=lambda p: h(f"{SEED}:round{r}:{p}"))
        ordered += [by_proj[p][r] for p in projs]
        r += 1
    assert len(ordered) == len(pool) == 915
    return tasks, ordered


def meta(task):
    p, tid = task.split("/")
    pc = tomllib.loads((E2E / "projects" / p / "project.toml").read_text())
    tc = tomllib.loads((E2E / "projects" / p / tid / "config.toml").read_text())
    m = {**pc, **tc}
    diff = (E2E / "projects" / p / tid / "patch.diff").read_text(errors="replace").splitlines()
    changed = sum(1 for l in diff if (l.startswith("+") or l.startswith("-")) and not l.startswith(("+++", "---")))
    return {"task": task, "project": p, "id_kind": tid.split("_")[0], "language": m.get("language"),
            "main_repo": m.get("main_repo"), "build_image": m.get("build_image"), "fix_changed_lines": changed}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); a = ap.parse_args()
    tasks, ordered = build_order()
    out = HERE / "task_order_915.txt"
    text = "\n".join(ordered) + "\n"
    s1 = HERE / "study1_tasks_20.txt"
    text20 = "\n".join(ordered[:20]) + "\n"
    manifest = {"seed": SEED, "algorithm": "see docstring of sample_tasks.py", "excluded": EXCLUDED,
                "order_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "study1_20_sha256": hashlib.sha256(text20.encode()).hexdigest(),
                "study1_tasks": [dict(index=i + 1, **meta(t)) for i, t in enumerate(ordered[:20])]}
    mp = HERE / "study1_manifest.json"
    if a.check:
        ok = out.read_text() == text and s1.read_text() == text20 and json.loads(mp.read_text()) == manifest
        print("CHECK", "OK" if ok else "MISMATCH", manifest["order_sha256"][:16], manifest["study1_20_sha256"][:16])
        sys.exit(0 if ok else 1)
    out.write_text(text); s1.write_text(text20); mp.write_text(json.dumps(manifest, indent=1) + "\n")
    print("order sha256", manifest["order_sha256"]); print("study1 sha256", manifest["study1_20_sha256"])
    for i, t in enumerate(manifest["study1_tasks"]):
        print(f'{t["index"]:2d} {t["task"]:38s} {t["language"]:5s} fix={t["fix_changed_lines"]:4d}')


if __name__ == "__main__":
    main()
