#!/usr/bin/env python3
"""Raise the metering shim's TOTAL cap on this node WITHOUT losing the keys of tasks that are running.

Reads every live per-execution key from the running agent processes, records its state, stops the old shim (exact PID),
starts a new one with the higher cap, the spend carried over and the keys preloaded, then verifies each key (alias,
spend and request counters must be intact). Prints no secrets. Refuses to run if no live key is found (use
start_worker_services.sh with TOTAL_START for an idle shim instead).

usage: swap_shim.py <new-total-cap-usd> [target-model]
"""
import json, os, signal, subprocess, sys, time, urllib.request

HOME = os.path.expanduser("~"); BE = f"{HOME}/benchmark-evals"
NEW_CAP = sys.argv[1]; MODEL = sys.argv[2] if len(sys.argv) > 2 else "us.moonshotai.kimi-k3"
envfile = {}
for l in open(f"{BE}/config/.env"):
    if "=" in l and not l.startswith("#"):
        k, v = l.rstrip("\n").split("=", 1); envfile[k] = v
M = envfile["SHIM_MASTER_KEY"]
GW = subprocess.run(["docker", "network", "inspect", "cybergym-internal", "--format", "{{(index .IPAM.Config 0).Gateway}}"], capture_output=True, text=True).stdout.strip()
H = f"http://{GW}:4100"

def api(path):
    r = urllib.request.Request(H + path, headers={"Authorization": "Bearer " + M})
    return json.load(urllib.request.urlopen(r, timeout=10))

# 1. live throwaway shim keys, from our own agent processes
keys = set()
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        if "scripts/run_agent.py" not in open(f"/proc/{pid}/cmdline", "rb").read().decode("utf8", "replace"): continue
        for item in open(f"/proc/{pid}/environ", "rb").read().split(b"\0"):
            if item.startswith(b"OPENAI_API_KEY=sk-shim-"): keys.add(item.split(b"=", 1)[1].decode())
    except (OSError, PermissionError):
        pass
old = api("/health")
dump = {k: api("/key/info?key=" + k)["info"] for k in keys}
print(f"live keys: {len(keys)}; old caps: per-key {old['usd_cap_per_key']}, total {old['usd_cap_total']}, spent {old['total_spend']}")
assert keys, "no live keys found; refusing"
os.umask(0o077)
json.dump(dump, open(f"{HOME}/cybergym-work/keys_preload.json", "w"))

# 2. the old shim: exactly one python process of ours running llm_shim_new.py
cands = []
for pid in filter(str.isdigit, os.listdir("/proc")):
    try:
        cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf8", "replace").split("\0")
        if os.stat(f"/proc/{pid}").st_uid == os.getuid() and "python" in os.path.basename(cmd[0]) and any(c.endswith("tools/llm_shim_new.py") for c in cmd[1:3]):
            cands.append(int(pid))
    except OSError:
        pass
assert len(cands) == 1, f"expected exactly one shim process, found {cands}"
old_pid = cands[0]
total = old["total_spend"]
env = dict(os.environ, MASTER_KEY=M, UPSTREAM="https://bedrock-runtime.us-east-1.amazonaws.com/openai", TARGET_MODEL=MODEL,
           UPSTREAM_KEY_FILE=f"{BE}/config/.bedrock_key", UPSTREAM_AUTH="bearer", UPSTREAM_SERIAL="0",
           PRICE_IN_PER_M="3.30", PRICE_CACHE_PER_M="0.33", PRICE_OUT_PER_M="16.50", MAX_SPEND_USD=str(old["usd_cap_per_key"]), MAX_TOTAL_SPEND_USD=NEW_CAP,
           MAX_REQUESTS="5000", MAX_INPUT_TOKENS="40000000", MAX_CACHE_TOKENS="400000000", UPSTREAM_TIMEOUT_STREAM="600", UPSTREAM_TIMEOUT="600",
           PORT="4100", BIND=GW, LOG_FILE=f"{HOME}/cybergym-work/shim.log", KEYS_FILE=f"{HOME}/cybergym-work/keys_preload.json", TOTAL_START=str(total))
t0 = time.time()
os.kill(old_pid, signal.SIGTERM)
new = subprocess.Popen([f"{BE}/.venv/bin/python", f"{BE}/tools/llm_shim_new.py"], cwd=BE, env=env, stdin=subprocess.DEVNULL,
                       stdout=open(f"{HOME}/cybergym-work/shim.out", "a"), stderr=subprocess.STDOUT, start_new_session=True)
up = None
for _ in range(80):
    try: up = api("/health"); break
    except Exception: time.sleep(0.1)
print(f"gap between stopping the old shim and the new one answering: {time.time() - t0:.1f} s")
assert up, "new shim did not come up"
print(f"new shim: pid {new.pid}, per-key cap {up['usd_cap_per_key']}, TOTAL CAP {up['usd_cap_total']}, carried total {up['total_spend']} (was {total})")
bad = 0
for k, before in dump.items():
    after = api("/key/info?key=" + k)["info"]
    ok = after["alias"] == before["alias"] and after["spend"] >= before["spend"] - 1e-9 and after["requests"] >= before["requests"]
    bad += not ok
print(f"keys carried over: {len(dump) - bad}/{len(dump)} (alias, spend and request counters intact)")
