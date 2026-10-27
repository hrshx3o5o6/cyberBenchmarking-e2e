---
type: synthesis
created: 2026-10-23
updated: 2026-10-23
sources: ["[[sources/cybergym-e2e]]"]
tags: [aws, ec2, ray, concurrency, benchmark-evals, runbook, shim, docker, reference, infrastructure]
---
# AWS VM: how the concurrent setup works (Ray, the codebase, the tools, how to run it)

Reference for the benchmark-evals replica on Amit's EC2 VM. Results are in [[wiki/syntheses/benchmark-evals-aws-vm-parallelism]]; this page explains the machinery. Facts below were read from the VM on 2026-10-23 unless marked as an inference.

## 1. What is running on the VM (as of the end of 2026-10-23)
| Thing | Owner | State | Notes |
|---|---|---|---|
| **Ray head** (`gcs_server`, dashboard) | `ubuntu` (Amit) | up about 2 days | GCS on port 6379 (listening on all interfaces), dashboard `127.0.0.1:8265`, trajectory viewer `127.0.0.1:8765`. Ours does not use it. **Do not stop or restart.** |
| `cybergym-proxy` (squid) + 3 containers | Amit | up about 2 days | The shared firewall. We reuse it and never recreate it. |
| `llm_shim.py` (metering proxy) | `harshav` | **up, idle** | `172.18.0.1:4100`, bound to the Docker gateway only; running total spend $68.50 (resets if restarted) |
| Our Ray, `cybergym-eval`, `run_agent.py`, sampler, PSI logger, watchdog, controller | `harshav` | **all stopped** | The 16-slot batch was stopped on purpose; only the shim is left running. Our Ray exists only while a batch runs. |
| Images and data | `harshav` | on disk | 223 GB used, 273 GB free after pulling images for 50 tasks |

## 2. Layers, top to bottom
```
you / me ──ssh──▶ VM
                  cybergym-eval run --config config/ramp-s16.json     (the "driver", one Python process)
                       │ reads the manifest, registers 1 row per (task, mode) in SQLite
                       │ ray.init(address="local")  → a private Ray instance (own GCS, raylet, workers)
                       ▼
                  Ray scheduler  — pool: CPU=16, benchmark_slot=N
                       │ each task needs 1 benchmark_slot + task_cpus CPUs; waits in the queue until both are free
                       ▼
                  worker process  (one per running task)  execute():
                       │ 1. wait for its launch turn (start_stagger_seconds)
                       │ 2. mark the SQLite row "running"
                       │ 3. ask the shim for a key capped at $10
                       │ 4. subprocess: cybergym-e2e/scripts/run_agent.py <task> ...
                       ▼
                  Docker (host daemon, sibling containers)
                       agent container  (image of the task)  ── Codex ──▶ shim (172.18.0.1:4100) ──▶ Bedrock (Kimi K3)
                       fresh grading containers for stage 3 and 4
                       │
                  result.json + SQLite row ("passed", usage, spend) → Ray frees the slot → next task starts
```

## 3. Concurrency: how the parallelism really works
- **`benchmark_slots` is an invented Ray resource.** `ray.init(resources={"benchmark_slot": N})` creates N tokens; every task requests 1. N is therefore the maximum number of simultaneous runs. Ray never measures real CPU or memory: all its resources (`num_cpus`, `benchmark_slot`) are declared numbers.
- **Real limit = min(`benchmark_slots`, floor(16 / `task_cpus`))**, since each task also reserves `task_cpus` of the 16 declared CPUs. We set `task_cpus: 1` so the slots are the only limit (Amit's own 5-task config used 4, which would cap at 4).
- **It is fixed per batch.** Resources cannot be resized in a running Ray instance, so each slot count is a separate `run` with a separate manifest (`ramp-s02`, `-s08`, `-s16`...).
- **All tasks are submitted at once** and the rest wait in Ray's queue; when a task finishes, the next starts immediately. The driver prints finished results (block-buffered, see section 9).
- **Staggered starts (our addition).** `start_stagger_seconds` (for example 20) makes each worker take a file lock in `<work_root>/state/launch.lock`, sleep until the last launch plus the gap, then record its own time in `launch.ts`. This spaces out the CPU-heavy install/build phase. The wait happens before `mark_running`, so recorded run times exclude it. Tested locally: six processes launched exactly 2.0 s apart.
- **What the machine did** (sampler, details in the results page): at 2 slots CPU median was 7%; at 8 slots CPU averaged 93% in minutes 5-10 (the build overlap) and load peaked at 33.7 on 16 cores, with no failures and no swap. Memory is about 1 GB per agent container above a 3.5 GB baseline (p90 about 2 GB), but one heavy step alone reached about 8 GB, so memory may be the limit at higher slot counts. Inference, not yet tested.
- **No feedback loop.** Nothing adapts slots to load. Ideas (an admission gate with PSI/memory signals, GNU parallel's `--load`/`--memfree`, Docker `--memory` limits) were discussed but not built; the safety net we added is the watchdog (section 7).

## 4. Ray: what exists and what does not
| | Amit's Ray | Our Ray |
|---|---|---|
| Started by | `ray start --head` under `ubuntu`, long-lived | `cybergym-eval run` itself, per batch |
| Address | GCS `:6379`, dashboard `127.0.0.1:8265` | local only, random ports, **no dashboard** |
| Temp dir | `/tmp/ray` | `/tmp/ray-<uid>` (`/tmp/ray-1002`), short on purpose |
| Nodes | 1 (the head is also the worker), 16 CPUs | 1 (this VM), 16 CPUs + N `benchmark_slot` |
| Ends | never (until stopped) | when the batch finishes (`ray.shutdown()`) |

- Version: Ray **2.59.0** on Python 3.12.15 (our venv). Ray prints a warning that token authentication is enabled.
- **Why `address="local"` matters:** without it, `ray.init()` can attach to an existing cluster on the same host, and refuses `num_cpus`/`resources` when it does. With it, our batch always starts its own private instance, so Amit's head is never used or disturbed. Verified: our test showed a new GCS on a different port and 4 test tasks ran on our own workers.
- **Why the temp dir is `/tmp/ray-<uid>`:** Ray puts Unix sockets inside the temp dir and paths over 107 bytes fail. A temp dir under the long work-root path broke the first launch of the first batch.
- **Ray does not know about Docker.** A Ray worker just runs `subprocess.run(run_agent.py)`; the containers are children of that subprocess, not Ray objects. Ray's memory monitor, if it ever killed a worker, would not necessarily remove its containers (untested).
- **`max_retries=0`:** a crashed worker loses its run; the SQLite row stays "running" until `recover` or a rerun.
- **Scaling across VMs** would use a real Ray cluster (head plus workers, each declaring its own `benchmark_slot`) and an autoscaler YAML. Not set up. Two blockers in the current code: SQLite and artifacts are node-local, and `preflight` runs on the driver machine. See the Ray cluster discussion in [[wiki/syntheses/benchmark-evals-aws-vm-parallelism]] section 7.

## 5. The codebase
Location on the VM: `/home/harshav/benchmark-evals` (our copy of the private `prescera/benchmark-evals`, from a zip), upstream benchmark at `/home/harshav/cybergym-e2e` (clone of `sunblaze-ucb/cybergym-e2e` at commit `d0ae0f0`, patched by `scripts/patch_cybergym.py`: 3 `openai-compatible` hits in `run_agent.py`, Git-rewrite fix in `install_codex.sh`). Amit's own copy is under `/home/ubuntu` and is untouched.

| File | Lines | Role |
|---|---|---|
| `src/cybergym_eval/cli.py` | 337 | commands: `prepare`, `preflight`, `model-check`, `run`, `status`, `report`, `recover`, `trajectory-html`; the driver (`run`) and Ray start-up |
| `src/cybergym_eval/worker.py` | 191 | `execute()`: one task, one mode: stagger, SQLite state, shim key, `run_agent.py` subprocess, result normalisation |
| `src/cybergym_eval/config.py` | 110 | manifest loading, defaults, env file, config hash, execution IDs |
| `src/cybergym_eval/db.py` | 84 | SQLite schema and helpers |
| `src/cybergym_eval/prepare.py` | 60 | pulls the task images, downloads the HF data, (optionally) starts the firewall |
| `src/cybergym_eval/trajectory_viewer.py` | 683 | HTML viewer for trajectories (not used by us; we have our own static viewer) |
| `scripts/bootstrap_ec2.sh` | | host setup (uv, upstream clone, patches, two venvs, CLI) |
| `tools/llm_shim.py` | 351 | metering proxy, copied from our `cybergym-bench/shim/` |
| `tools/sampler.py`, `tools/watchdog.py` | 46, 58 | resource logger, safety stop (ours; copies in `wiki/syntheses/aws-vm-data/tools/`) |
| `config/*.json` | | manifests: `pilot*.json`, `ramp-s02/s04/s08/s12/s16.json`, `ramp-b8.json`, `sample50.json` (seeded list) |

### What we changed in Amit's code (all small, all in our copy)
| File | Change | Why |
|---|---|---|
| `prepare.py`, `cli.py` | `prepare --skip-firewall` flag | the stock `prepare` runs `firewall update`, which force-removes and recreates Amit's shared `cybergym-proxy` |
| `cli.py` | `ray.init(address="local", _temp_dir="/tmp/ray-<uid>", include_dashboard=False)` | private Ray instance; short socket paths; no port clash with his dashboard |
| `config.py` | new keys `shim_url`, `shim_port`, `spend_cap_usd`, `start_stagger_seconds` | metering and staggering |
| `worker.py` | issues a capped shim key per execution, points the container's `OPENAI_BASE_URL`/`OPENAI_API_KEY` at the shim, removes the real Bedrock key from the worker environment, records `usage` and `spend_cap_usd` in `result.json` | spend control; the container never sees the real key |
| `worker.py` | `_stagger_start()` | smooth the start-up CPU spike |

These changes live only in the VM copy and in a scratchpad copy that will be deleted; a PR or patch to Amit's repo would be the way to keep them.

## 6. Config reference (manifest keys)
Required: `benchmark_root`, `work_root`, `tasks`, `modes` (`e2e`, `patch-only`), `agent` (`codex` here), `model_provider` (`openai-compatible` for Codex). Optional: `env_file`, `agent_timeout_seconds` (5400 = the 90-minute limit), `task_deadline_seconds`, `task_cpus`, `benchmark_slots`, `prompt_style`, `max_attempts`, `use_firewall`, `model` (`us.moonshotai.kimi-k3`), `aws_region`, `openai_base_url`, `firewall_domains`; ours: `shim_url` (`http://172.18.0.1:4100`), `shim_port` (4100), `spend_cap_usd` (10), `start_stagger_seconds` (0).
- The **config hash** covers every resolved key except the path, so changing `benchmark_slots`, the task list or any shim key makes new **execution IDs** (`sha256(hash:task:mode)[:20]`). That is why the same task can run again in a new batch without clashing, and why `--resume` only works within one manifest.
- The env file `config/.env` holds `AWS_BEARER_TOKEN_BEDROCK`, `HF_TOKEN`, `SHIM_MASTER_KEY` and leftover `EC2_*` variables. `config/.bedrock_key` holds the same Bedrock key for the shim. Both are mode 600. They must never be printed, committed or pasted.

## 7. State, logs and the safety tools
- **SQLite** `<work_root>/state/runs.sqlite3`, table `executions` (id, config_hash, task, mode, status, hostname, started_at, finished_at, exit_code, artifact_dir, result_json, error). Statuses: `pending`, `running`, `passed`, `benchmark_failed`, `infra_error`, `interrupted`, plus the `recover` outcomes. **This is the source of truth for progress** (not the driver's output file).
- **Artifacts** `<work_root>/artifacts/<execution_id>/`: `runner.log`, `result.json` (stages, `agent_exec_seconds`, `wall_seconds`, `usage` from the shim: requests, fresh/cache/output tokens, errors, spend), `upstream/.../summary.json`, trajectory, workspace.
- **Shim** logs one JSON line per model call to `~/cybergym-work/shim.log` (no bodies, no keys). Health: `curl http://172.18.0.1:4100/health` gives `total_spend`. It enforces $10 per key and $150 total (the total resets if the shim is restarted).
- **Sampler** writes `~/cybergym-work/sample_<label>.csv` every 10 s: load, CPU %, memory used/available, swap, disk, container counts, network totals, shim total.
- **Watchdog** (`tools/watchdog.py`, not yet running): every 5 s; if available memory is under 6 GB or swap use over 2 GB for 3 checks in a row, it stops **only our** driver, `run_agent.py` processes, Ray workers and containers (never Amit's four) and logs to `~/cybergym-work/watchdog.log`. Dry-run tested.

## 8. Docker and network model (what the benchmark does per task)
Per task: `docker run -d --rm <task image> sleep infinity` (random name `codex-<id>`) on Docker's default bridge → copy in source (not the ground-truth PoC), run the task's `prepare.sh` → install Codex → **switch the container to `cybergym-internal`** (no internet route) → run `codex exec` for up to 90 minutes → fresh containers (random Docker names) grade stage 3 and 4 → `--rm` removes them. All containers are siblings on the host daemon; none has the Docker socket; **no CPU or memory limits are set**. Only the squid proxy (allowing the LLM hosts) and the host gateway `172.18.0.1` (our shim, bypassing the proxy via `NO_PROXY`) are reachable from the agent. In patch-only, stages 1 and 2 are skipped.

## 9. Runbook
```
cd ~/benchmark-evals                               # on the VM, as harshav
.venv/bin/cybergym-eval prepare   --config config/X.json --skip-firewall   # images + data, no model spend
.venv/bin/cybergym-eval preflight --config config/X.json                   # read-only checks
.venv/bin/python tools/sampler.py <label> 10 &     # start the sampler (detached)
.venv/bin/cybergym-eval run --config config/X.json --address local        # the batch (detach with nohup setsid)
.venv/bin/cybergym-eval status --config config/X.json
.venv/bin/cybergym-eval report --config config/X.json --output results.json
.venv/bin/cybergym-eval recover --config config/X.json --dry-run          # stale "running" rows
```
- Progress: read the SQLite table (or `status`), not `ramp-*.out`.
- To stop a batch: SIGTERM the driver, then the `run_agent.py` processes, then remove only our containers (everything except `angry_ganguly`, `infallible_wozniak`, `cybergym-proxy`, `cybergym-openhands-inspect`).
- Shim start (needs `SHIM_MASTER_KEY` and the key file): see the environment variables in the shim's docstring; ours used `UPSTREAM=https://bedrock-runtime.us-east-1.amazonaws.com/openai`, `UPSTREAM_AUTH=bearer`, prices `3.30/0.33/16.50`, `MAX_SPEND_USD=10`, `MAX_TOTAL_SPEND_USD=150`, `MAX_REQUESTS=5000`, `BIND=172.18.0.1`, `PORT=4100`.
- Use the VM's IP (`98.81.87.162`) in SSH if the Mac's DNS lookup of the hostname fails intermittently (it did).

## 10. Known issues and gotchas
- The driver's stdout is block-buffered when redirected to a file: counts of finished tasks from it are wrong (5 shown, 9 real). Use SQLite.
- `pgrep -f` / `pkill -f` match their own SSH command; a watcher that treats an SSH failure as "no output" will report a false "done".
- Counting running tasks by `codex-*` container names misses grading containers.
- Ray's socket-path limit (107 bytes) and the need for `address="local"` (section 4).
- The shim's Kimi K3 prices are from third-party pages; it counts cache writes as ordinary input; the cap is checked before each request, so one request of overshoot is possible.
- `max_retries=0`; a killed batch leaves "running" rows and lost partial work (the few minutes since each task started).
- The stock `prepare` and `bootstrap` scripts touch shared things (proxy, `/etc/sysctl.d`); use the flags and read the scripts first.
- Several shell steps were blocked by the tool's permission classifier (copying credentials with sudo, running the bootstrap): the user ran those, or they were done inside `/home/harshav` after consent.

## 11. Ownership and security notes
- The VM, the Bedrock key and the Ray head are **Amit's**. `harshav` has passwordless sudo and is in the `docker` group, which is effectively root on the box. Tell Amit what runs there; get a quiet window for timing runs.
- The Bedrock key sits in `config/.env` and `config/.bedrock_key` (mode 600) and only the shim sends it upstream; agent containers get a throwaway shim key. Amit's own `config/.env` is mode 777 on his side, worth telling him.
- `benchmark-evals-main.zip` (the private repo) sits untracked in the vault root; the vault's remote is **public**. Keep it out of commits (move it or add it to `.gitignore`).
- Nothing in this page or in `wiki/syntheses/aws-vm-data/` contains a key or token (checked by search before committing).

## 12. Open items
1. Patch-only is done (35 distinct tasks completed, all passed; the 16-slot batch was stopped with 15 tasks cut). Next: upload the gate and controller patches and run them live on cheap tasks.
2. e2e on 10 to 12 tasks that passed patch-only, under the controller (start 4, ceiling 12), within the rest of the $150 cap (about $81 left after $68.50 spent).
3. Amit's confirmation (key use, proxy sharing, quiet window), and his view on the docker group and the `/home/ubuntu` reads we did.
4. Persisting our changes to the runner (patch or PR), since the working copy exists only on the VM.
5. Scaling beyond one VM (Ray cluster on EC2, shared job store, S3, image distribution): study and change list in [[wiki/syntheses/ray-ec2-scaling-study]].

## 14. The adaptive concurrency controller (built and tested, not yet run live)
**Why:** a fixed slot count is wrong for mixed tasks: 8 held up on light tasks, 16 saturated the CPU for 50+ minutes on a heavy mix (results page, section 4c). The controller raises and lowers the number of simultaneous tasks from measured machine pressure.

**Parts** (code in `wiki/syntheses/aws-vm-data/tools/`, patches described below):
1. **Gate** (`db.claim_slot`, called from `worker._start_slot`): a worker starts a task only if, in one SQLite write transaction, (a) fewer than `limit` executions are `running`, (b) fewer than `warm_max` (2) started within the last `warm_seconds` (240 s; still in their heavy start-up), and (c) the last launch was at least `gap_seconds` (5 s) ago. Rows `running` for longer than the agent timeout + 30 min count as crashed and are ignored. Waiting workers poll every 3 to 5 s. Enabled with `"gate_enabled": true`; Ray's `benchmark_slots` then acts only as a high hard ceiling.
2. **Limit file** `<work_root>/state/limit.json`: `{"limit": n, "warm_seconds", "warm_max", "gap_seconds", "updated"}`, written atomically by the controller; workers fall back to `gate_start` if it is missing.
3. **Controller** (`tools/controller.py`, a separate process like the sampler): every 10 s it reads signals, decides, writes the limit, and appends one JSON line per tick to `<work_root>/state/controller.jsonl` (time, signals, limit, action, reason). The trace of limit against time is the capacity result. Flags: `--shadow` (log only, do not write the limit), `--exit-when-idle`, plus every threshold as an option.

**Signals:** CPU PSI `some` avg10 and avg60; memory PSI avg10; I/O PSI avg10; `MemAvailable`; swap used; the shim's non-200 rate over 5 minutes (needs 20+ calls); newly failed (`infra_error`/`interrupted`) tasks; and from SQLite the counts of running, warming and pending executions.

**Control law (AIMD with hysteresis).** Start 4, floor 2, **ceiling 12**.
| State | Condition | Action |
|---|---|---|
| **Red** | CPU PSI avg10 > 50 or avg60 > 40, memory PSI avg10 > 5, swap > 50 MB, free memory < 10 GB, model error rate > 2%, or a new infra failure | After 2 red samples in a row and a 60 s cooldown: new limit = 75% of min(limit, running), at least 1 lower, never below the floor. Running tasks are never killed; it only stops new launches. Remembers the level that caused the pressure and blocks climbing back to it for 20 minutes (this removed flapping in simulation). |
| **Green** | CPU PSI avg60 < 20 and avg10 < 30, free memory >= 20 GB, memory PSI < 1, I/O PSI < 30, errors <= 1% | After 12 green samples in a row and a 120 s cooldown, add 1, but only if work is queued, the limit is actually binding (running >= limit), fewer than 2 tasks are still warming up, and it is below the ceiling and the remembered bad level. |
| **Amber** | in between | Hold. |

Thresholds are starting guesses: the 16-slot data shows what bad looks like (PSI 65 to 80%), but not where individual tasks begin to slow, so they need calibrating against the live trace and the control tasks.

**Tests** (`tests/test_gate_controller.py`, 14 of 14 pass, no model spend): control law (climbs only when green and binding; holds when not binding, warming, queue empty or amber; decreases from the running count, with cooldown and floor; one red sample is not enough; memory, swap, errors and failures are red); the gate with real concurrent SQLite workers (never exceeds the limit, honours the warm-up cap, the gap and stale rows); a toy-machine simulation (capacity 4/8/14: 0 to 10 limit changes per hour, under 7% of time in red pressure, a bigger machine gets a higher limit). The first version flapped (102 changes in 300 simulated minutes); the bad-level memory fixed that.

**Live check so far:** shadow mode on the 16-slot batch (71 ticks) read PSI, memory, the shim log and the SQLite state correctly, classified the saturated machine as red from the first tick and walked the limit 12 -> 9 -> 6 -> 4 -> 3 -> 2 (log in `aws-vm-data/controller_shadow.jsonl`). The gate itself has only been exercised in tests, not on the VM.

**Patches to Amit's runner needed on the VM** (not yet uploaded): `db.py` (a `meta` table and `claim_slot`), `worker.py` (`_read_gate`, `_start_slot`, removal of the early `_stagger_start`), `config.py` (`gate_enabled`, `gate_start`). All are backward compatible: with `gate_enabled` false the old path runs.

**Also uses the PSI logger** (`tools/psilog.py`, CSV of PSI and load every 10 s), added because the sampler did not record PSI.

**Planned next:** run the controller live with the gate on a few cheap tasks to watch it climb and back off, then e2e on 10 to 12 tasks. Possible later: weighted slots (a heavy project counts as 2), and per-container `docker --memory` limits.

## 13. Glossary of the measurement terms used in these pages
| Term | Meaning |
|---|---|
| **PSI** (Pressure Stall Information) | Linux kernel metric of how much time tasks spent **stalled waiting** for a resource; files `/proc/pressure/cpu`, `/memory`, `/io`. A line such as `some avg10=0.01 avg60=0.39 avg300=0.25` means: the share of time (in %) at least one task was waiting, averaged over the last 10 s, 60 s and 5 min. It tells you whether work is actually being delayed, which CPU % does not: a machine can sit at 100% CPU with PSI near zero (everything still gets its turn), or at 50% with high PSI. A better signal than load average for "can we run more?". |
| **Load average** | Average number of tasks running or waiting to run (Linux also counts those stuck in uninterruptible I/O) over 1/5/15 min. On 16 cores, a load of 16 is one task per core. Ours reached 33.7 at 8 slots with no measurable slowdown, so it is not trusted alone. |
| **CPU %** | How busy the CPU was in one sampler interval (10 s), averaged over all 16 vCPUs; 100% = all cores fully busy. |
| **p50 / median** | Half of the readings are below it; the typical value. |
| **p90** | 90% of the readings are below it; only the worst 10% exceed it. Shows busy periods that an average hides. |
| **max** | The single worst reading. |
| **avg vs p50 vs p90, example** | Batch A CPU: median 6.7%, p90 61%, max 100%, average 16%. The machine was mostly quiet and briefly saturated; the average describes neither state well. Memory per agent container: average about 1 GB, p90 about 2 GB means "usually 1 GB, but one reading in ten was 2 GB or more". |
| **Swap** | Disk space used as emergency memory. Any swap use means RAM ran short; the watchdog stops our run at 2 GB. |
| **Slot / `benchmark_slot`** | One permitted simultaneous run (section 3). |
| **Stagger** | Minimum gap between task launches (`start_stagger_seconds`, 20 s in the 16-slot batch). |
| **Control task** | A task run at two slot counts, to compare the same task under different load. |
| **Wall time vs agent time** | Wall = the whole task (setup, install, agent, grading); agent = only the model working inside the container (`agent_exec_seconds`). |
| **Core-minutes** | CPU % x 16 cores x minutes: total CPU work done, which lets different batches be compared regardless of how long they ran. |

See also: [[wiki/syntheses/e2e-runs-and-vm-behaviour]] for the live controller trial, the threshold calibration and the e2e results.
