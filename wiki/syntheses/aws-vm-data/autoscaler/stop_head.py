#!/usr/bin/env python3
"""Stop OUR autoscaling Ray head on this VM, by exact PIDs, and nothing else.

The head is identified by its temp directory (default /tmp/ray-1002d). Besides the processes that carry the directory
in their command line (GCS, raylet, monitor), Ray leaves orphans whose process titles hide it (the client server, the
dashboard and runtime-env agents); those are identified by the files they hold open inside that directory, with
parent PID 1. The owner's head and our other head use different temp directories and are never matched.
usage: stop_head.py [temp-dir-name]    (prints what it will stop; refuses an implausible number of processes)
"""
import os, pwd, signal, sys, time
NAME = (sys.argv[1] if len(sys.argv) > 1 else "ray-1002d")
OTHER = "ray-1002c"
me = pwd.getpwuid(os.getuid()).pw_name
def candidates():
    out = {}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        p = int(pid)
        try:
            if pwd.getpwuid(os.stat("/proc/%d" % p).st_uid).pw_name != me or p == os.getpid(): continue
            cmd = open("/proc/%d/cmdline" % p, "rb").read()
            fds = [os.readlink("/proc/%d/fd/%s" % (p, f)) for f in os.listdir("/proc/%d/fd" % p)]
            ppid = int(open("/proc/%d/stat" % p).read().split()[3])
        except OSError:
            continue
        mine_fd = sum(NAME in x for x in fds); other_fd = sum(OTHER in x for x in fds)
        if NAME.encode() in cmd and OTHER.encode() not in cmd:
            out[p] = "cmdline"
        elif ppid == 1 and mine_fd > 0 and other_fd == 0:
            out[p] = "orphan (%d open files in the temp dir)" % mine_fd
    return out
# WARNING: a head started afterwards with the same temp directory is matched too: run this BEFORE starting the new head.
# Several rounds: agents only become orphans (parent 1) after their parent has died, so one scan is not enough.
for rnd in range(4):
    found = candidates()
    if not found:
        print("round %d: nothing left" % (rnd + 1)); break
    for p, why in sorted(found.items()): print("  round %d: %d  %s  [%s]" % (rnd + 1, p, open("/proc/%d/comm" % p).read().strip(), why))
    assert len(found) <= 12, "implausible number of processes; refusing"
    for p in found:
        try: os.kill(p, signal.SIGTERM)
        except OSError: pass
    for _ in range(20):
        if not candidates(): break
        time.sleep(0.5)
    for p in candidates():
        print("  still alive, SIGKILL:", p)
        try: os.kill(p, signal.SIGKILL)
        except OSError: pass
    time.sleep(1.5)
print("remaining:", sorted(candidates()))
