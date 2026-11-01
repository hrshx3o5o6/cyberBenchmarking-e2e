import json, os, subprocess
def psi(path):
    out = {}
    try:
        for line in open(path):
            kind = line.split()[0]
            out[kind] = {kv.split("=")[0]: float(kv.split("=")[1]) for kv in line.split()[1:] if kv.split("=")[0].startswith("avg")}
    except OSError: pass
    return out
mem = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True).stdout.strip()
d = {
  "host": os.uname().nodename.replace("ip-172-31-", "ip-"),
  "vcpus": os.cpu_count(),
  "load": open("/proc/loadavg").read().split()[:3],
  "cpu_psi": psi("/proc/pressure/cpu"),
  "mem_psi": psi("/proc/pressure/memory"),
  "io_psi": psi("/proc/pressure/io"),
  "mem_total_gb": round(mem["MemTotal"] / 1048576, 1),
  "mem_used_gb": round((mem["MemTotal"] - mem["MemAvailable"]) / 1048576, 1),
  "mem_available_gb": round(mem["MemAvailable"] / 1048576, 1),
  "swap_used_gb": round((mem["SwapTotal"] - mem["SwapFree"]) / 1048576, 2),
  "containers": int(sh("docker ps -q | wc -l") or 0),
  "agents": int(sh("pgrep -f '[s]cripts/run_agent.py' | wc -l") or 0),
  "disk_root_used": sh("df -h / | tail -1 | awk '{print $5}'"),
}
try:
    import urllib.request
    gw = sh("docker network inspect cybergym-internal --format '{{(index .IPAM.Config 0).Gateway}}'")
    h = json.load(urllib.request.urlopen("http://%s:4100/health" % gw, timeout=4))
    d["shim_spend"], d["shim_cap"] = round(h["total_spend"], 3), h["usd_cap_total"]
except Exception:
    d["shim_spend"], d["shim_cap"] = None, None
print(json.dumps(d))
