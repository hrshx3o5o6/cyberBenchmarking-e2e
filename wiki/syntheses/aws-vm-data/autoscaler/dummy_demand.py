#!/usr/bin/env python3
"""Stage-3 test: drive the autoscaler with sleeping tasks, no cybergym code and no model spend.

Run on the head:  RAY_AUTH_MODE=token python dummy_demand.py --tasks 24 --seconds 240
Each task asks for the same resources as a real execution (num_cpus=1, benchmark_slot=1), sleeps,
and reports which host ran it. With 0 workers up, the pending tasks are the demand that makes the
autoscaler launch workers; when they finish and the nodes sit idle it stops them again.
The timeline (nodes, slots in use, pending) is printed every --poll seconds.
"""
import argparse
import socket
import time

import ray


@ray.remote(num_cpus=1, resources={"benchmark_slot": 1}, max_retries=0)
def work(i, seconds):
    t0 = time.time()
    time.sleep(seconds)
    return {"task": i, "host": socket.gethostname(), "started": t0, "seconds": seconds}


def snapshot():
    nodes = [n for n in ray.nodes() if n["Alive"]]
    total = ray.cluster_resources().get("benchmark_slot", 0)
    free = ray.available_resources().get("benchmark_slot", 0)
    return len(nodes), total, total - free


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, default=24)
    ap.add_argument("--seconds", type=float, default=240)
    ap.add_argument("--poll", type=float, default=15)
    ap.add_argument("--tail", type=float, default=0, help="keep watching this long after the tasks finish (to see scale-down)")
    args = ap.parse_args()

    ray.init(address="auto")
    start = time.time()
    refs = [work.remote(i, args.seconds) for i in range(args.tasks)]
    print(f"submitted {len(refs)} tasks of {args.seconds:.0f}s")
    pending = list(refs)
    results = []
    while pending:
        done, pending = ray.wait(pending, num_returns=len(pending), timeout=args.poll)
        results += ray.get(done)
        n, total, used = snapshot()
        print(f"t={time.time()-start:6.0f}s nodes={n} slots_total={total:.0f} slots_used={used:.0f} done={len(results)}/{len(refs)}", flush=True)
    hosts = {}
    for r in results:
        hosts[r["host"]] = hosts.get(r["host"], 0) + 1
    print("placement:", hosts)
    end = time.time() + args.tail
    while time.time() < end:
        n, total, used = snapshot()
        print(f"t={time.time()-start:6.0f}s nodes={n} slots_total={total:.0f} slots_used={used:.0f} (tail)", flush=True)
        time.sleep(args.poll)
