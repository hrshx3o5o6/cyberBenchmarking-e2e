"""Tests for the SQLite gate (db.claim_slot) and the adaptive controller (tools/controller.py). Run: python3 tests/test_gate_controller.py"""
import importlib.util, multiprocessing as mp, os, random, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from cybergym_eval import db

spec = importlib.util.spec_from_file_location("controller", os.path.join(os.path.dirname(__file__), "..", "tools", "controller.py"))
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)

GREEN = dict(cpu10=2, cpu60=3, mem_avail_gb=50, pending=10)
RED = dict(cpu10=80, cpu60=70)

def drive(st, p, steps, sig_kw, t0=0.0, dt=10.0, **over):
    """Run `steps` control ticks with constant signals; returns list of (t, limit, action)."""
    out = []
    for i in range(steps):
        sig = C.Signals(**{**sig_kw, **over})
        t = t0 + i * dt
        new, action, _ = C.decide(st, sig, p, t)
        out.append((t, new, action))
    return out

# ---- controller: control law
def test_climbs_when_green_and_binding():
    p = C.Params(); st = C.State(limit=4)
    trace = drive(st, p, 400, GREEN, running=4)           # limit binds only if running >= limit
    # running is fixed at 4 so after the first increase the limit is no longer binding
    assert st.limit == 5, st.limit
def test_climbs_to_ceiling_when_always_binding():
    p = C.Params(); st = C.State(limit=4); t = 0.0
    for _ in range(2000):
        C.decide(st, C.Signals(**GREEN, running=st.limit, warming=0), p, t); t += 10
    assert st.limit == p.ceiling, st.limit
def test_no_increase_when_limit_not_binding():
    p = C.Params(); st = C.State(limit=6)
    drive(st, p, 300, GREEN, running=3); assert st.limit == 6
def test_no_increase_while_warming():
    p = C.Params(); st = C.State(limit=4)
    drive(st, p, 300, GREEN, running=4, warming=2); assert st.limit == 4
def test_no_increase_without_queue():
    p = C.Params(); st = C.State(limit=4)
    drive(st, p, 300, {**GREEN, "pending": 0}, running=4); assert st.limit == 4
def test_decrease_on_red_respects_floor_and_cooldown():
    p = C.Params(); st = C.State(limit=12)
    trace = drive(st, p, 60, RED, running=12)
    limits = [l for _, l, a in trace if a == "decrease"]
    assert limits[0] == 9, limits                          # 12 * 0.75
    assert all(b < a for a, b in zip(limits, limits[1:]))
    times = [t for t, _, a in trace if a == "decrease"]
    assert all(b - a >= p.cooldown_dec for a, b in zip(times, times[1:]))
    assert st.limit >= p.floor
    drive(st, p, 600, RED, running=2, t0=1000); assert st.limit == p.floor
def test_single_red_sample_does_not_decrease():
    p = C.Params(); st = C.State(limit=8)
    C.decide(st, C.Signals(**RED, running=8), p, 0); assert st.limit == 8
    C.decide(st, C.Signals(**GREEN, running=8), p, 10); assert st.red == 0
def test_memory_and_swap_and_errors_and_failures_are_red():
    p = C.Params()
    for kw in (dict(mem_avail_gb=5), dict(swap_mb=500), dict(mem10=20), dict(err_rate=0.1, err_calls=50), dict(new_failures=1)):
        color, why = C.classify(C.Signals(**{**GREEN, **kw}), p); assert color == "red" and why, kw
    color, _ = C.classify(C.Signals(**{**GREEN, "err_rate": 0.5, "err_calls": 5}), p)   # too few calls to judge
    assert color == "green"
def test_amber_holds():
    p = C.Params(); st = C.State(limit=6)
    drive(st, p, 500, dict(cpu10=65, cpu60=50, mem_avail_gb=50, pending=9), running=6); assert st.limit == 6
def test_decrease_is_based_on_running_not_limit():
    p = C.Params(); st = C.State(limit=12)
    drive(st, p, 3, RED, running=4, t0=1000.0)             # only 4 actually running -> 4*0.75 = 3
    assert st.limit == 3, st.limit

def test_sustained_five_minute_pressure_is_red_even_when_short_averages_look_ok():
    p = C.Params()
    color, why = C.classify(C.Signals(**{**GREEN, "cpu10": 40, "cpu60": 40, "cpu300": 60}), p)
    assert color == "red" and any("cpu_psi300" in w for w in why), (color, why)
    color, _ = C.classify(C.Signals(**{**GREEN, "cpu10": 66, "cpu60": 57, "cpu300": 39}), p)     # the 8-slot burst we measured
    assert color != "red", color
    color, _ = C.classify(C.Signals(**{**GREEN, "cpu10": 76, "cpu60": 72, "cpu300": 70}), p)     # the 16-slot state we measured
    assert color == "red"

# ---- gate: real SQLite, concurrent workers
def _worker(args):
    path, i, limit, warm_s, warm_max, hold, log = args
    con = db.connect(path)
    while not db.claim_slot(con, f"e{i}", "h", "/a", limit, 0.0, warm_s, warm_max, 3600):
        time.sleep(0.05)
    start = time.time(); time.sleep(hold)
    db.mark_finished(con, f"e{i}", "passed", 0, {}); log.put((start, time.time()))
def test_gate_never_exceeds_limit():
    d = tempfile.mkdtemp(); path = os.path.join(d, "r.sqlite3"); con = db.connect(path)
    for i in range(12): db.register(con, f"e{i}", "x", f"t{i}", "patch-only")
    q = mp.Manager().Queue(); limit = 3
    with mp.Pool(8) as pool: pool.map(_worker, [(path, i, limit, 0.0, 99, 0.4, q) for i in range(12)])
    spans = [q.get() for _ in range(12)]
    peak = max(sum(1 for s, e in spans if s <= t < e) for t in [s for s, _ in spans])
    assert peak <= limit, peak; assert peak >= 2, peak
def test_gate_warm_cap():
    d = tempfile.mkdtemp(); path = os.path.join(d, "r.sqlite3"); con = db.connect(path)
    for i in range(6): db.register(con, f"e{i}", "x", f"t{i}", "patch-only")
    q = mp.Manager().Queue()
    with mp.Pool(6) as pool: pool.map(_worker, [(path, i, 10, 1.0, 2, 3.0, q) for i in range(6)])   # warm window 1 s, max 2
    starts = sorted(q.get()[0] for _ in range(6))
    for t in starts:                                         # never more than 2 starts inside any 1 s window
        assert sum(1 for s in starts if t <= s < t + 1.0) <= 2, starts
def test_gate_gap_and_stale_rows():
    d = tempfile.mkdtemp(); path = os.path.join(d, "r.sqlite3"); con = db.connect(path)
    for i in range(3): db.register(con, f"e{i}", "x", f"t{i}", "patch-only")
    assert db.claim_slot(con, "e0", "h", "/a", 5, 30.0, 0, 9, 3600, now_ts=1000.0)
    assert not db.claim_slot(con, "e1", "h", "/a", 5, 30.0, 0, 9, 3600, now_ts=1010.0)   # inside 30 s gap
    assert db.claim_slot(con, "e1", "h", "/a", 5, 30.0, 0, 9, 3600, now_ts=1031.0)
    # e0 and e1 are 'running'; far in the future they count as stale (crashed workers) and no longer block
    assert db.claim_slot(con, "e2", "h", "/a", 1, 0.0, 0, 9, 3600, now_ts=1031.0 + 7200)

# ---- simulation: toy machine with a hidden capacity and lagged pressure
def simulate(capacity=8.0, minutes=240, seed=1, heavy_fraction=0.3):
    rnd = random.Random(seed); p = C.Params(); st = C.State(limit=p.start)
    running = []; t = 0.0; cpu60 = cpu10 = 0.0; limits = []; press = []; pend = 10**6
    last_launch = -1e9
    while t < minutes * 60:
        load = sum(w * (2.0 if t - s < 240 else 0.5) for s, e, w in running)     # warming tasks burn 4x more CPU
        raw = 0.0 if load <= capacity else min(100.0, 100.0 * (load - capacity) / load)
        cpu10 += 0.4 * (raw - cpu10); cpu60 += 0.12 * (raw - cpu60)               # lagged averages
        running = [(s, e, w) for s, e, w in running if e > t]
        warming = sum(1 for s, e, w in running if t - s < p.warm_seconds)
        sig = C.Signals(cpu10=cpu10, cpu60=cpu60, mem_avail_gb=40, running=len(running), warming=warming, pending=pend)
        new, _, _ = C.decide(st, sig, p, t); limits.append(new); press.append(cpu60)
        while len(running) < st.limit and warming < p.warm_max and t - last_launch >= p.gap_seconds:   # the gate
            w = 2.0 if rnd.random() < heavy_fraction else 1.0
            running.append((t, t + rnd.uniform(300, 2400), w)); warming += 1; last_launch = t
        t += 10.0
    return limits, p, press
def test_simulation_is_stable_and_scales_with_capacity():
    means = {}
    for capacity in (4.0, 8.0, 14.0):
        limits, p, press = simulate(capacity=capacity, minutes=300)
        half = len(limits) // 2; tail, ptail = limits[half:], press[half:]
        mean = sum(tail) / len(tail); means[capacity] = mean
        changes_per_hour = sum(1 for a, b in zip(tail, tail[1:]) if a != b) / (len(tail) * 10 / 3600)
        red_frac = sum(1 for x in ptail if x > p.cpu60_hi) / len(ptail)
        print(f"  capacity {capacity:>4}: settled mean limit {mean:4.1f} (min {min(tail)}, max {max(tail)}), "
              f"{changes_per_hour:4.1f} changes/h, {red_frac:4.0%} of time in red pressure, mean cpu60 {sum(ptail)/len(ptail):4.1f}")
        assert p.floor <= min(tail) and max(tail) <= p.ceiling
        assert changes_per_hour <= 14, changes_per_hour            # no rapid flapping
        assert red_frac <= 0.20, red_frac                          # mostly out of the red zone
    assert means[4.0] < means[8.0] <= means[14.0] + 0.5, means    # a bigger machine gets a higher limit

if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for n, f in tests:
        try: f(); print("PASS", n)
        except AssertionError as e: failed += 1; print("FAIL", n, "->", e)
        except Exception as e: failed += 1; print("ERROR", n, "->", repr(e))
    print(f"\n{len(tests) - failed}/{len(tests)} passed"); sys.exit(1 if failed else 0)
