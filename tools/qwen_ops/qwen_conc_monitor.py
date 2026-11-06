# Run on the head. Per-5-minute table of the Qwen shim log since ~/autoscaler/qwenconc.start (a unix time): tasks calling, calls, overhead (call seconds minus
# output tokens / 27.5, about the prefill wait; stalled calls with no output are left out), mean call seconds, live context (sum of each task's latest prompt), calls over 120 s.
# Task names come from the executions table (alias = first 6 characters of the execution id).
import json, os, sys, collections, statistics as st, time, subprocess
HOME = os.path.expanduser("~")
since = float(open(HOME + "/autoscaler/qwenconc.start").read())
rows = []
for l in open(HOME + "/cybergym-work/shim-head-qwen.log"):
    if l.startswith("{"):
        try: j = json.loads(l)
        except ValueError: continue
        if j.get("event") == "messages" and j.get("ts", 0) >= since: rows.append(j)
q = "select task, status, left(execution_id,6), to_char(started_at,'HH24:MI'), to_char(finished_at,'HH24:MI') from executions where started_at > to_timestamp(%d) order by started_at" % since
out = subprocess.run(["docker", "exec", "-i", "cybergym-postgres", "psql", "-U", "cybergym", "-d", "cybergym", "-At", "-F", "|", "-c", q], capture_output=True, text=True).stdout.strip().split("\n")
tasks = [l.split("|") for l in out if l]
name = {t[2]: t[0].split("/")[0] for t in tasks}
print(time.strftime("%H:%M:%S"), "elapsed %d min | calls %d | statuses %s" % ((time.time() - since) / 60, len(rows), dict(collections.Counter(r["status"] for r in rows))))
print("tasks:", "; ".join("%s %s %s-%s" % (t[0].split("/")[0], t[1], t[3], t[4] or "") for t in tasks))
B = 300
by = collections.defaultdict(list)
for r in rows: by[int((r["ts"] - since) // B)].append(r)
last_in = {}
print("bucket(5min) | tasks calling | calls | overhead median/p90 (s) | call secs mean | live context (sum of latest prompt, k) | long(>120s) calls")
for b in sorted(by):
    rs = sorted(by[b], key=lambda r: r["ts"]); al = set(r["alias"][:6] for r in rs)
    for r in rs: last_in[r["alias"][:6]] = r["in_tok"]
    ov = sorted(r["secs"] - r["out_tok"] / 27.5 for r in rs if r.get("out_tok"))
    live = sum(last_in[a] for a in al) / 1000
    print("%3d (%2d min) | %d | %2d | %5.1f / %5.1f | %5.1f | %5.0f | %d" % (b, b * 5, len(al), len(rs), st.median(ov) if ov else 0, ov[int(.9 * len(ov))] if ov else 0, st.mean(r["secs"] for r in rs), live, sum(1 for r in rs if r["secs"] > 120)))
