#!/usr/bin/env python3
"""Resource sampler: one CSV row every INTERVAL seconds. stdlib only, Linux only.
usage: sampler.py <label> [interval_s]   (stop with SIGTERM)"""
import csv, os, subprocess, sys, time

label = sys.argv[1]
interval = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
out = os.path.expanduser(f"~/cybergym-work/sample_{label}.csv")
os.makedirs(os.path.dirname(out), exist_ok=True)

def cpu():
    f = open("/proc/stat").readline().split()[1:]
    v = list(map(int, f)); idle = v[3] + v[4]; return sum(v), idle

def meminfo():
    m = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":"); m[k] = int(v.split()[0])
    return m

def sh(cmd):
    try: return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=8).stdout.strip()
    except Exception: return ""

cols = ["ts", "load1", "cpu_pct", "mem_used_mb", "mem_avail_mb", "swap_used_mb", "disk_used_gb",
        "containers", "agent_containers", "net_rx_mb", "net_tx_mb", "shim_total_usd"]
w = csv.writer(open(out, "a", buffering=1))
if os.path.getsize(out) == 0: w.writerow(cols)
t0, i0 = cpu()
while True:
    time.sleep(interval)
    t1, i1 = cpu()
    cpu_pct = round(100 * (1 - (i1 - i0) / max(1, t1 - t0)), 1); t0, i0 = t1, i1
    m = meminfo()
    rx = tx = 0
    for line in list(open("/proc/net/dev"))[2:]:
        n, rest = line.split(":"); 
        if n.strip() in ("lo",) or n.strip().startswith(("docker", "br-", "veth")): continue
        p = rest.split(); rx += int(p[0]); tx += int(p[8])
    st = os.statvfs("/")
    names = sh("docker ps --format '{{.Names}}'").split()
    spend = sh("curl -s -m 3 http://172.18.0.1:4100/health | python3 -c 'import sys,json;print(json.load(sys.stdin)[\"total_spend\"])'")
    w.writerow([int(time.time()), os.getloadavg()[0], cpu_pct,
                (m["MemTotal"] - m["MemAvailable"]) // 1024, m["MemAvailable"] // 1024,
                (m["SwapTotal"] - m["SwapFree"]) // 1024, round((st.f_blocks - st.f_bfree) * st.f_frsize / 1e9, 1),
                len(names), sum(1 for n in names if n.startswith("codex-")), round(rx / 1e6), round(tx / 1e6), spend])
