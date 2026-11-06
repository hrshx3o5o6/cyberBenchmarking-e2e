"""Restart the running metering shim on the head with ONE hostname pinned to a given IP address (no system file is changed).

Used when the head's resolver returns a stale address for a dedicated Vertex endpoint after a redeploy (2026-11-05).
usage (on the head): python3 restart_shim_pinned.py <hostname> <ip>      the new process keeps the old one's environment, working directory and command line.
Find the right address from a machine that reaches the endpoint: dig +short @8.8.8.8 <hostname>
TLS still verifies the hostname; only the lookup is overridden (a sitecustomize.py in ~/shimfix, loaded through PYTHONPATH).
"""
import os, sys, subprocess, signal, time
host, ip = sys.argv[1], sys.argv[2]
pid = int(subprocess.check_output("pgrep -f llm_shim_new.py | head -1", shell=True).decode())
env = dict(l.split("=", 1) for l in open("/proc/%d/environ" % pid).read().split("\0") if "=" in l)
cwd = os.readlink("/proc/%d/cwd" % pid); exe = os.readlink("/proc/%d/exe" % pid)
cmd = open("/proc/%d/cmdline" % pid).read().split("\0")[:-1]
os.makedirs(os.path.expanduser("~/shimfix"), exist_ok=True)
open(os.path.expanduser("~/shimfix/sitecustomize.py"), "w").write('''import os, socket
_pin = os.environ.get("PIN_DNS")      # "host=ip": connect to this address for that name (TLS still verifies the name)
if _pin:
    _h, _ip = _pin.split("=")
    _orig = socket.getaddrinfo
    def getaddrinfo(host, *a, **k):
        return _orig(_ip if host == _h else host, *a, **k)
    socket.getaddrinfo = getaddrinfo
''')
env["PIN_DNS"] = "%s=%s" % (host, ip); env["PYTHONPATH"] = os.path.expanduser("~/shimfix") + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
os.kill(pid, signal.SIGTERM); time.sleep(2)
log = open(os.path.expanduser("~/cybergym-work/shim-head-qwen.log"), "a")
p = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
print("restarted shim, old pid", pid, "new pid", p.pid, "cmd", [os.path.basename(c) for c in cmd])
