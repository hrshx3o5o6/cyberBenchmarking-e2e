#!/usr/bin/env python3
"""Adaptive concurrency controller for cybergym-eval (stdlib only, Linux).

Every INTERVAL seconds it reads machine pressure (Linux PSI), free memory, swap, the metering shim's error rate and the
run state in SQLite, then moves the concurrency limit up or down and writes <work_root>/state/limit.json. Workers read that
file through the SQLite gate (db.claim_slot): a worker starts a task only if running < limit, fewer than warm_max tasks
are still in their start-up phase, and the stagger gap has passed. Lowering the limit never kills a running task; it only
stops new launches. Every decision is appended to <work_root>/state/controller.jsonl.

Control law: AIMD with hysteresis. Red (2 samples in a row, 60 s cooldown) cuts the limit to 75% of min(limit, running);
green (12 samples in a row, 120 s cooldown, limit actually binding, nothing still warming up) adds 1; amber holds.

usage: controller.py --work-root DIR [--start 4 --floor 2 --ceiling 12 --interval 10] [--shim-log FILE] [--shadow] [--exit-when-idle]
"""
import argparse, json, os, sqlite3, sys, time
from dataclasses import dataclass, asdict


@dataclass
class Params:
    start: int = 4
    floor: int = 2
    ceiling: int = 12
    cpu10_hi: float = 75.0      # PSI cpu "some" avg10 above this = red (provisional: 8 slots peaked at 67, 16 slots sat at 65-88)
    cpu60_hi: float = 60.0      # (8 slots: avg60 max 59; 16 slots: mean 66)
    cpu300_hi: float = 50.0     # sustained overload: 8 slots avg300 max 39, 16 slots 68-73
    cpu10_ok: float = 60.0      # below both of these (and the other greens) = green
    cpu60_ok: float = 45.0
    mem_avail_ok_gb: float = 20.0
    mem_avail_lo_gb: float = 10.0   # below this = red
    mem10_hi: float = 5.0       # PSI memory "some" avg10
    mem10_ok: float = 1.0
    io10_ok: float = 50.0
    swap_hi_mb: float = 50.0
    err_hi: float = 0.02        # shim non-200 rate (needs err_min_calls calls in the window)
    err_ok: float = 0.01
    err_min_calls: int = 20
    dec_factor: float = 0.75
    cooldown_dec: float = 60.0
    cooldown_inc: float = 120.0
    red_streak: int = 2
    green_streak: int = 12
    warm_seconds: float = 240.0  # a task counts as "warming up" for this long after launch
    warm_max: int = 2            # at most this many tasks warming up at once
    gap_seconds: float = 5.0     # minimum gap between launches
    hint_ttl: float = 1200.0     # after a decrease, do not climb back to the failing level for this long


@dataclass
class Signals:
    cpu10: float = 0.0
    cpu60: float = 0.0
    cpu300: float = 0.0
    mem10: float = 0.0
    io10: float = 0.0
    mem_avail_gb: float = 99.0
    swap_mb: float = 0.0
    err_rate: float = 0.0
    err_calls: int = 0
    new_failures: int = 0       # infra_error / interrupted tasks since the last sample
    running: int = 0
    warming: int = 0
    pending: int = 0


@dataclass
class State:
    limit: int
    last_change: float = 0.0
    red: int = 0
    green: int = 0
    bad_level: int = 0           # the limit that was in force when the last decrease happened
    bad_until: float = 0.0


def classify(sig: Signals, p: Params):
    """Returns ('red'|'amber'|'green', [reasons])."""
    why = []
    if sig.cpu10 > p.cpu10_hi: why.append(f"cpu_psi10 {sig.cpu10:.0f}>{p.cpu10_hi:.0f}")
    if sig.cpu60 > p.cpu60_hi: why.append(f"cpu_psi60 {sig.cpu60:.0f}>{p.cpu60_hi:.0f}")
    if sig.cpu300 > p.cpu300_hi: why.append(f"cpu_psi300 {sig.cpu300:.0f}>{p.cpu300_hi:.0f}")
    if sig.mem10 > p.mem10_hi: why.append(f"mem_psi10 {sig.mem10:.1f}>{p.mem10_hi:.0f}")
    if sig.swap_mb > p.swap_hi_mb: why.append(f"swap {sig.swap_mb:.0f}MB")
    if sig.mem_avail_gb < p.mem_avail_lo_gb: why.append(f"mem_avail {sig.mem_avail_gb:.0f}GB<{p.mem_avail_lo_gb:.0f}")
    if sig.err_calls >= p.err_min_calls and sig.err_rate > p.err_hi: why.append(f"model_errors {sig.err_rate:.1%}")
    if sig.new_failures > 0: why.append(f"{sig.new_failures} new infra failure(s)")
    if why:
        return "red", why
    green = (sig.cpu60 < p.cpu60_ok and sig.cpu10 < p.cpu10_ok and sig.mem_avail_gb >= p.mem_avail_ok_gb
             and sig.mem10 < p.mem10_ok and sig.io10 < p.io10_ok
             and (sig.err_calls < p.err_min_calls or sig.err_rate <= p.err_ok))
    return ("green" if green else "amber"), []


def decide(st: State, sig: Signals, p: Params, now: float):
    """Pure control step. Updates `st` in place; returns (new_limit, action, reason)."""
    color, why = classify(sig, p)
    st.red = st.red + 1 if color == "red" else 0
    st.green = st.green + 1 if color == "green" else 0
    limit = st.limit
    if st.red >= p.red_streak:
        if now - st.last_change < p.cooldown_dec:
            return limit, "hold", "red, in cooldown: " + "; ".join(why)
        base = min(limit, max(sig.running, p.floor))
        new = max(p.floor, int(base * p.dec_factor))
        new = min(new, limit - 1) if limit > p.floor else limit
        if new != limit:
            st.bad_level, st.bad_until = limit, now + p.hint_ttl
            st.limit, st.last_change, st.red, st.green = new, now, 0, 0
            return new, "decrease", "; ".join(why)
        return limit, "hold", "red, already at floor: " + "; ".join(why)
    if st.green >= p.green_streak:
        if now - st.last_change < p.cooldown_inc:
            return limit, "hold", "green, in cooldown"
        if sig.pending == 0:
            return limit, "hold", "green, no queued work"
        if sig.running < limit:
            return limit, "hold", f"green, limit not binding ({sig.running} running < {limit})"
        if sig.warming >= p.warm_max:
            return limit, "hold", f"green, {sig.warming} tasks still warming up"
        if limit >= p.ceiling:
            return limit, "hold", "green, at ceiling"
        if st.bad_level and now < st.bad_until and limit + 1 >= st.bad_level:
            return limit, "hold", f"green, but {limit + 1} is the level that caused pressure (blocked until it ages out)"
        st.limit, st.last_change, st.green = limit + 1, now, 0
        return limit + 1, "increase", "green for %d samples" % p.green_streak
    return limit, "hold", color


# ---------------- I/O ----------------
def psi(kind):
    out = {}
    for line in open(f"/proc/pressure/{kind}"):
        parts = line.split()
        out[parts[0]] = {k: float(v) for k, v in (x.split("=") for x in parts[1:] if not x.startswith("total"))}
    return out


def meminfo():
    m = {}
    for line in open("/proc/meminfo"):
        k, v = line.split(":"); m[k] = int(v.split()[0])
    return m


def shim_errors(path, window_s, now):
    """(error_rate, calls) over the last window_s seconds of the shim's JSONL log."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - 400_000)); tail = f.read().decode("utf8", "replace").splitlines()
    except OSError:
        return 0.0, 0
    calls = bad = 0
    for line in tail:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("event") == "messages" and d.get("ts", 0) > now - window_s:
            calls += 1; bad += d.get("status") != 200
    return (bad / calls if calls else 0.0), calls


def read_signals(db_path, shim_log, p, failures_seen, now):
    c, m, i, mi = psi("cpu"), psi("memory"), psi("io"), meminfo()
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t))
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10)
    q = lambda sql, *a: con.execute(sql, a).fetchone()[0]
    running = q("SELECT COUNT(*) FROM executions WHERE status='running'")
    warming = q("SELECT COUNT(*) FROM executions WHERE status='running' AND started_at > ?", iso(now - p.warm_seconds))
    pending = q("SELECT COUNT(*) FROM executions WHERE status='pending'")
    failures = q("SELECT COUNT(*) FROM executions WHERE status IN ('infra_error','interrupted')")
    con.close()
    rate, calls = shim_errors(shim_log, 300, now)
    return Signals(cpu10=c["some"]["avg10"], cpu60=c["some"]["avg60"], cpu300=c["some"]["avg300"], mem10=m["some"]["avg10"], io10=i["some"]["avg10"],
                   mem_avail_gb=mi["MemAvailable"] / 1048576, swap_mb=(mi["SwapTotal"] - mi["SwapFree"]) / 1024,
                   err_rate=rate, err_calls=calls, new_failures=max(0, failures - failures_seen),
                   running=running, warming=warming, pending=pending), failures


def write_limit(path, limit, p):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"limit": limit, "warm_seconds": p.warm_seconds, "warm_max": p.warm_max,
                   "gap_seconds": p.gap_seconds, "updated": time.time()}, f)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-root", required=True)
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--shim-log", default=os.path.expanduser("~/cybergym-work/shim.log"))
    ap.add_argument("--shadow", action="store_true", help="log decisions but do not write the limit file")
    ap.add_argument("--exit-when-idle", action="store_true")
    for k, v in asdict(Params()).items():
        ap.add_argument("--" + k.replace("_", "-"), type=type(v), default=v)
    a = ap.parse_args()
    p = Params(**{k: getattr(a, k) for k in asdict(Params())})
    state_dir = os.path.join(os.path.expanduser(a.work_root), "state")
    db_path, limit_path, log_path = (os.path.join(state_dir, n) for n in ("runs.sqlite3", "limit.json", "controller.jsonl"))
    st = State(limit=p.start); failures_seen = None; idle_since = None
    if not a.shadow: write_limit(limit_path, st.limit, p)
    print(f"controller start: limit {st.limit} floor {p.floor} ceiling {p.ceiling} shadow={a.shadow}", flush=True)
    while True:
        now = time.time()
        try:
            sig, failures = read_signals(db_path, a.shim_log, p, failures_seen if failures_seen is not None else 10**9, now)
            if failures_seen is None: sig.new_failures = 0
            failures_seen = failures
            before = st.limit
            new, action, reason = decide(st, sig, p, now)
            if not a.shadow and new != before: write_limit(limit_path, new, p)
            with open(log_path, "a") as f:
                f.write(json.dumps({"ts": round(now, 1), "limit": st.limit, "action": action, "reason": reason, **asdict(sig)}) + "\n")
            if a.exit_when_idle:
                idle_since = (idle_since or now) if (sig.pending == 0 and sig.running == 0) else None
                if idle_since and now - idle_since > 60:
                    print("idle, exiting", flush=True); return
        except Exception as e:      # never die on a transient read error
            print("controller error:", repr(e), flush=True)
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
