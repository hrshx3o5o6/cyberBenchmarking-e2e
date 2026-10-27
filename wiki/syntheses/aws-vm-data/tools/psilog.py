#!/usr/bin/env python3
"""PSI + load logger, one CSV row every INTERVAL s. usage: psilog.py <label> [interval_s]"""
import csv, os, sys, time
label = sys.argv[1]; interval = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
out = os.path.expanduser(f"~/cybergym-work/psi_{label}.csv")
def psi(kind):
    d = {}
    for line in open(f"/proc/pressure/{kind}"):
        p = line.split(); d[p[0]] = {k: float(v) for k, v in (x.split("=") for x in p[1:] if not x.startswith("total"))}
    return d
cols = ["ts", "load1", "cpu_some10", "cpu_some60", "cpu_some300", "mem_some10", "mem_full10", "io_some10", "io_full10"]
w = csv.writer(open(out, "a", buffering=1))
if os.path.getsize(out) == 0: w.writerow(cols)
while True:
    c, m, i = psi("cpu"), psi("memory"), psi("io")
    w.writerow([int(time.time()), os.getloadavg()[0], c["some"]["avg10"], c["some"]["avg60"], c["some"]["avg300"],
                m["some"]["avg10"], m["full"]["avg10"], i["some"]["avg10"], i["full"]["avg10"]])
    time.sleep(interval)
