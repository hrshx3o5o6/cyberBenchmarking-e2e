#!/usr/bin/env python3
"""Safety stop for our benchmark run on a shared VM. stdlib only.
Kills ONLY our driver, our run_agent.py processes and our containers (never the protected names).
usage: watchdog.py [--mem-floor-gb 6] [--swap-gb 2] [--strikes 3] [--dry-run]"""
import os, subprocess, sys, time

args = sys.argv[1:]
def opt(name, default):
    return float(args[args.index(name) + 1]) if name in args else default
FLOOR_KB = opt("--mem-floor-gb", 6) * 1024 * 1024
SWAP_KB = opt("--swap-gb", 2) * 1024 * 1024
STRIKES = int(opt("--strikes", 3))
DRY = "--dry-run" in args
PROTECTED = {"angry_ganguly", "infallible_wozniak", "cybergym-proxy", "cybergym-openhands-inspect"}
LOG = os.path.expanduser("~/cybergym-work/watchdog.log")
ME = os.getpid()

def log(msg):
    line = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + " " + msg
    print(line, flush=True)
    with open(LOG, "a") as f: f.write(line + "\n")

def mem():
    m = {}
    for l in open("/proc/meminfo"):
        k, v = l.split(":"); m[k] = int(v.split()[0])
    return m["MemAvailable"], m["SwapTotal"] - m["SwapFree"]

def ours():
    out = subprocess.run(["ps", "-u", "harshav", "-o", "pid=,args="], capture_output=True, text=True).stdout
    pids = []
    for l in out.splitlines():
        pid, _, cmd = l.strip().partition(" ")
        if int(pid) == ME or cmd.startswith(("bash", "ssh", "sh ", "-bash")): continue
        if ".venv/bin/cybergym-eval run" in cmd or "scripts/run_agent.py" in cmd or "ray::" in cmd or "raylet" in cmd:
            pids.append((int(pid), cmd[:70]))
    return pids

def stop():
    victims = ours()
    names = [n for n in subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split() if n not in PROTECTED]
    log(f"EMERGENCY STOP (dry={DRY}): {len(victims)} processes, {len(names)} containers: {names}")
    if DRY: return
    for pid, _ in victims:
        try: os.kill(pid, 15)
        except ProcessLookupError: pass
    time.sleep(5)
    for n in names: subprocess.run(["docker", "rm", "-f", n], capture_output=True)

log(f"watchdog start: floor {FLOOR_KB/1048576:.1f} GB avail, swap {SWAP_KB/1048576:.1f} GB, strikes {STRIKES}, dry={DRY}")
bad = 0
while True:
    avail, swap = mem()
    bad = bad + 1 if (avail < FLOOR_KB or swap > SWAP_KB) else 0
    if bad >= STRIKES:
        log(f"threshold hit: avail {avail/1048576:.1f} GB, swap {swap/1048576:.1f} GB"); stop(); break
    time.sleep(5)
log("watchdog exit")
