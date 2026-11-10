#!/usr/bin/env python3
"""Stop the 100-task driver when the model provider stops accepting calls, so that a credit problem cannot drain the queue into results that look like model failures
(2026-11-10: the OpenRouter account ran out of credit, every new task failed in seconds and 39 tasks were recorded as no_poc or no_patch before it was noticed).

Every --interval seconds, on the head, it checks (1) the provider key (OpenRouter /key: limit_remaining below --min-remaining USD stops the run), (2) the head shim's log
for HTTP 402 (--max-402 or more new ones within --window seconds triggers a tiny test call; the run is stopped only if that call is refused with 402 as well, because OpenRouter also answers 402 `in_flight_budget_exhausted` when many large requests are in flight at once, which clears by itself and is retried by Codex) and (3) Postgres for finished tasks in which every model call failed (--max-dead or more stops the run).
Stopping = terminating the driver process of --config (queued tasks are cancelled, running ones are left to end), then it writes ALERT to its log and exits.
The key is read from the environment (OPENROUTER_API_KEY) and never printed.

usage: credit_guard.py --config config/random100-glm53flash-r3.json --since "2026-11-10 08:30:00+00" [--min-remaining 5] [--max-402 10] [--window 300] [--max-dead 3] [--interval 60] [--dry-run]
"""
import argparse, json, os, subprocess, time, urllib.error, urllib.request

ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
ap.add_argument("--config", required=True)
ap.add_argument("--since", required=True, help="start time of the run (UTC, Postgres timestamp syntax)")
ap.add_argument("--min-remaining", type=float, default=5.0)
ap.add_argument("--max-402", type=int, default=10)
ap.add_argument("--window", type=int, default=300)
ap.add_argument("--max-dead", type=int, default=3)
ap.add_argument("--interval", type=int, default=60)
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()
SHIM_LOG = os.path.expanduser("~/cybergym-work/shim.log")
SQL = ("select count(*) from executions where updated_at > '%s' and finished_at is not null and (result->'usage'->>'requests')::int > 0 "
       "and (result->'usage'->>'errors')::int >= (result->'usage'->>'requests')::int") % args.since


def log(msg):
    print(time.strftime("%FT%TZ", time.gmtime()), msg, flush=True)


def key_remaining():
    try:
        r = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]})
        d = json.load(urllib.request.urlopen(r, timeout=30)).get("data") or {}
        return d.get("limit_remaining")
    except Exception as e:
        log(f"key check failed: {str(e)[:100]}")
        return None


def recent_402():
    n, cutoff = 0, time.time() - args.window
    try:
        with open(SHIM_LOG, "rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 6_000_000))
            for line in f.read().splitlines():
                if b'"status": 402' in line:
                    try:
                        ts = json.loads(line).get("ts")
                    except ValueError:
                        continue
                    n += 1 if (ts is None or ts >= cutoff) else 0     # message records carry no ts: counted against a rolling baseline below
    except OSError:
        pass
    return n


def dead_tasks():
    out = subprocess.run(["docker", "exec", "-i", "cybergym-postgres", "psql", "-U", "cybergym", "-d", "cybergym", "-At", "-c", SQL], capture_output=True, text=True).stdout.strip()
    return int(out or 0)


def probe_status():
    """A tiny completion on the pinned provider: 200 means the account can pay for a request right now (so a burst of 402 is the transient in-flight budget limit that OpenRouter lifts by itself after Retry-After), 402 means it cannot."""
    body = {"model": "z-ai/glm-5.3-flash", "messages": [{"role": "user", "content": "Reply with the single word: ok"}], "max_tokens": 300,
            "provider": {"order": ["z-ai"], "allow_fallbacks": False}}
    try:
        r = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
                                   {"authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "content-type": "application/json"})
        return urllib.request.urlopen(r, timeout=60).status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def stop(reason):
    log(f"ALERT: {reason}")
    if args.dry_run:
        log("dry run: not stopping the driver"); return
    subprocess.run(["pkill", "-TERM", "-f", f"[c]ybergym-eval run --config {args.config}"])
    log("driver terminated; queued tasks cancelled, running tasks left to end. Add credit, then relaunch with a new work_root.")


base402 = recent_402()
log(f"guard started: base 402 count {base402}, config {args.config}")
hist = [(time.time(), base402)]
while True:
    rem = key_remaining()
    if rem is not None and rem < args.min_remaining:
        stop(f"provider key has only {rem} USD of limit left"); break
    now402 = recent_402(); hist.append((time.time(), now402)); hist = [h for h in hist if h[0] >= time.time() - args.window]
    if now402 - hist[0][1] >= args.max_402:
        n402, status = now402 - hist[0][1], probe_status()
        if status == 402:
            stop(f"{n402} new HTTP 402 answers on the head within {args.window}s and a tiny test call was refused too (HTTP 402): the account cannot pay"); break
        log(f"{n402} new HTTP 402 on the head within {args.window}s, but a tiny test call returned HTTP {status}: transient in-flight budget limit (OpenRouter retries after Retry-After), not stopping")
        hist = [(time.time(), now402)]
    dead = dead_tasks()
    if dead >= args.max_dead:
        stop(f"{dead} finished tasks had every model call fail"); break
    log(f"ok: key remaining {rem}, 402 total {now402}, tasks with every call failed {dead}")
    time.sleep(args.interval)
