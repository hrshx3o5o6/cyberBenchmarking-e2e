#!/usr/bin/env python3
"""Stop agent containers that outlived their task. The harness names an agent container codex-<8 hex>; an agent run is limited to 90 minutes (5,400 s) plus
install and set-up, so a codex-* container older than --max-minutes (default 120) belongs to a task whose process was killed (a lost Ray task cannot stop a
Docker container, which is how a runaway container kept a node busy for hours on 2026-11-09). Validation containers (random Docker names) are never touched.

With --min-free-gb N (use it on the head, whose disk is small) it also frees disk: when the root disk has less than N GB free it removes unused task images (cybergym/oss-fuzz, n132/arvo,
cybergym/e2e), largest first, with a plain `docker rmi` (which refuses images that a container uses), until N + 30 GB are free. Task images are re-pulled by `docker run` when a task needs them again.

usage: container_janitor.py [--max-minutes 120] [--interval 60] [--min-free-gb N] [--once] [--dry-run]
Run it on every node, in the background: nohup setsid python3 tools/container_janitor.py > ~/janitor.log 2>&1 &
"""
import argparse, datetime, shutil, subprocess, time

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--max-minutes", type=float, default=120)
ap.add_argument("--interval", type=float, default=60)
ap.add_argument("--min-free-gb", type=float, default=0, help="also free disk by removing unused task images when less than this is free (0 = off)")
ap.add_argument("--once", action="store_true")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()


def sweep():
    out = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True).stdout.split()
    now = datetime.datetime.now(datetime.timezone.utc)
    for cid in out:
        r = subprocess.run(["docker", "inspect", "-f", "{{.Name}} {{.State.StartedAt}}", cid], capture_output=True, text=True).stdout.split()
        if len(r) != 2 or not r[0].lstrip("/").startswith("codex-"):
            continue
        started = datetime.datetime.fromisoformat(r[1][:26].rstrip("Z") + "+00:00") if "." in r[1] else datetime.datetime.fromisoformat(r[1].rstrip("Z") + "+00:00")
        age = (now - started).total_seconds() / 60
        if age > args.max_minutes:
            print(f"{now:%FT%TZ} {'would stop' if args.dry_run else 'stopping'} {r[0].lstrip('/')} (running {age:.0f} min)", flush=True)
            if not args.dry_run:
                subprocess.run(["docker", "rm", "-f", cid], capture_output=True)


def free_disk():
    if args.min_free_gb <= 0:
        return
    free = shutil.disk_usage("/").free / 1e9
    if free >= args.min_free_gb:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    imgs = []
    for line in subprocess.run(["docker", "image", "ls", "--format", "{{.ID}} {{.Repository}}"], capture_output=True, text=True).stdout.splitlines():
        iid, repo = line.split(None, 1)
        if repo.split("/")[0] + "/" + repo.split("/")[-1] in ("cybergym/oss-fuzz", "n132/arvo", "cybergym/e2e") or repo in ("cybergym/oss-fuzz", "n132/arvo", "cybergym/e2e"):
            size = int(subprocess.run(["docker", "image", "inspect", "-f", "{{.Size}}", iid], capture_output=True, text=True).stdout.strip() or 0)
            imgs.append((size, iid, repo))
    for size, iid, repo in sorted(imgs, reverse=True):
        if shutil.disk_usage("/").free / 1e9 >= args.min_free_gb + 30:
            break
        print(f"{now:%FT%TZ} {free:.0f} GB free < {args.min_free_gb:.0f}: {'would remove' if args.dry_run else 'removing'} unused image {repo} {iid[:12]} ({size / 1e9:.1f} GB)", flush=True)
        if not args.dry_run:
            subprocess.run(["docker", "rmi", iid], capture_output=True)


while True:
    sweep()
    free_disk()
    if args.once:
        break
    time.sleep(args.interval)
