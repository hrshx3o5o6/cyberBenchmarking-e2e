---
type: synthesis
created: 2026-11-04
updated: 2026-11-04
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [observations, incident, memory, ray, autoscaler, deepseek-v4-1-flash, vertex, 100-tasks, living-document]
---
# First pass of the 100-task run (2026-11-03): observations

Protocol: [[wiki/syntheses/deepseek-100-task-study-protocol]]. Setup and ramp: [[wiki/syntheses/autoscaled-vertex-run-plan]]. Run 19:43 to 22:01 UTC, head (10 slots) plus up to 3 autoscaled workers (10 slots each, 16 vCPU, 64 GiB RAM, 1024 GiB disk), DeepSeek V4.1 Flash on Vertex, 10 USD and 90 minutes per run, price assumed 0.30 / 0.03 / 1.20 USD per million tokens.

## 1. Outcome
| | Tasks |
|---|---|
| Completed normally | 31 |
| of which passed S1 to S4 | 5 |
| passed S1 to S3, failed S4 | 12 |
| no PoC | 12 |
| passed S1, error in S2 | 1 |
| no patch | 1 |
| ran to the 90-minute limit | 13 |
| `infra_error` (lost to node failures, not model results) | 68 |
Spend of the 31: 47.91 USD in total, mean 1.55, maximum 5.12; no task reached the 10 USD cap. `qpdf/oss-fuzz_42535152` (the task with its PoC in the tree) finished with no PoC. These numbers cover 31 of 100 tasks that were not chosen at random (the tasks lost were whichever happened to sit on the failed nodes or in the queue) and must not be quoted as a pass rate.

## 2. What went wrong: node memory exhaustion
- Each node: `m7i.4xlarge`, 16 vCPU, 63,252 MB RAM, no swap. The harness starts task containers with a plain `docker run -d --rm` (no memory or CPU limit), so any container may use all RAM and all 16 cores. Ray's memory monitor kills workers at 95% of 66.3 GB (63.0 GB).
- Worker 3 (10 slots) crossed it at 20:41 (60 of 62 GB in use, 64.1 GB at the kill): Ray killed its 10 task processes within a second and the autoscaler terminated the then-idle node about 3 minutes later. Worker 1 did the same at about 21:08 (7 tasks). The head and the third worker survived to the end.
- The 10 lost running tasks had run for about 50 minutes each.
- Likely cause (unconfirmed): several heavy C/C++ builds (ffmpeg, ghostscript, libavc, mruby, h2o...) at once; each container sees 16 cores, so `make -j$(nproc)` starts 16 compile jobs; worker 1 showed load 32 on 16 cores 9 minutes before its loss. Per-container memory on the head was only 2 to 2.3 GB at rest. The actual process was never seen because the nodes were terminated.

## 3. Why 52 tasks that never started also failed
At 20:41:23 the driver log read "pending lease requests (10) reached limit (10), with 42 tasks waiting for lease requests": 10 + 42 = 52, exactly the number of never-started failures, all failed within 30 ms with the same out-of-memory message (62 failures in total with the 10 running tasks). The explanation that fits: with `max_retries=0`, Ray failed every task queued behind the killed workers. A local experiment (killing one running worker) failed only that one task; the memory-monitor path could not be reproduced on macOS, so the queued-task part is inferred from the log arithmetic.

## 4. What worked
- Worker scale-up and setup: three workers launched within seconds of the demand, joined after 5 to 10 minutes (data fetch of 36 GB each), 1024 GiB disks as configured (the running autoscaler reloaded the new size).
- The $10 per-run dollar cap and the price in the registry: costs recorded per task; the shim and token relay carried about 2,200 calls on the head alone with a handful of 502s and stream failures; the 600 s per-call cap fired on stalled calls (3 of the slowest).
- The Google token path ran for the whole 2 hours without a gap.
- Dollar spend per completed task was moderate (mean 1.55 USD).

## 5. Findings about the setup
- **Automation:** worker scaling, task distribution, limits, grading and result storage are automated. Starting the Ray head, shim, relay and driver, keeping the Mac refresher running, monitoring, failure recovery, reruns, code deployment to the VM, run preparation, worker cleanup and the wiki records are manual. Nothing alerts on failure and nothing reruns lost tasks.
- **Task container isolation:** no memory or CPU limits, so one heavy task can take down a node.
- **Dataset:** two tasks of the draw had a 0-byte PoC and failed the runner's preflight (replaced before the run); one task has its PoC inside the source tree (kept, reported separately).
- **Time to first model call on a fresh worker:** about 10 minutes of image pulls after the node joins (observed in the ramp).

## 6. Decisions taken after the run
- Rerun: first planned for the 68 to 69 lost tasks only, then (study owner, 2026-11-04) all 100 in one clean pass 2. The first pass's 31 completed results stay on record as the first pass and are not mixed into pass 2.
- Fewer slots: 6 per worker and 4 on the head (was 10 each); the head also runs Postgres, Ray's control process and the shim.
- Memory sampler on every node (every 30 s: node memory and load, memory of the largest containers) written to the shared Postgres `node_metrics` table, so the data survives a node loss.
- No Docker memory limits and no change to Ray's memory monitor (both would change the task environment).

## 7. Open questions
- Which task or step used the memory; does 6 slots per worker avoid the problem.
- Whether Ray's queued-task failure can be avoided by submitting in smaller waves.
- Vertex's sustained rate limit over several hours (no 429s seen).

## 8. What is recorded for pass 2 (checked 2026-11-04, 4h15 in)
| Data | Where | Survives the node? |
|---|---|---|
| Result per task (stages, usage totals, spend, host, times) | Postgres `executions` | yes |
| Per finished task: `result.json`, `runner.log`, `summary.json` and the full agent trajectory `trajectory/attempt_1.log` (gzip) | Postgres `artifacts` (430 rows so far, all three nodes) | yes |
| Node memory, load, container count and the largest containers every 30 s | Postgres `node_metrics` (12,600 rows) | yes |
| **The PoC and patch files each task produced** (`output/poc.bin`, `output/fix.patch`) | only on the disk of the node that ran the task | **no, until the copy loop below** |
| **Per-call model log of each worker's shim** (status, seconds, finish reason, tokens, stream failures) | only on that worker's disk (the head's own log is on the head) | **no, until the copy loop below** |
| Per-call usage in Postgres `usage_events` | the table exists but nothing writes to it (0 rows); per-task totals are in the result | n/a |
Fix applied 2026-11-04 10:21 UTC: a loop on the head (`~/pull_worker_data.sh`) copies each live worker's whole work folder (outputs, trajectories, shim log, memory log) to `~/cybergym-work/worker-backups/<worker ip>/` every 2 minutes. It must be stopped, and the folder copied to the Mac, when the run ends. Worker nodes terminate 3 minutes after going idle, so a last pull can be missed if the final tasks finish just before; the loop interval (2 minutes) is shorter than that.
Added 2026-11-04 14:08 UTC: a second loop (`~/pull_worker_raylogs.sh`, every 5 minutes) copies each worker's Ray logs (raylet, worker stdout and stderr, memory-monitor messages, about 118 files and 47 MB per worker) and its home-directory logs (the sampler's own log) to `~/cybergym-work/worker-backups/<worker ip>/ray-logs/` and `home-logs/`; the first loop's copies of shim logs, outputs, trajectories and memory logs were verified equal to the live files on both workers (6,402 and 6,358 shim log lines, 110 and 67 output files). Not copied: Docker's own container logs (task containers are started with `--rm`, so they are gone when a task ends) and the cloud-init output of the worker machines. At the end of the run: stop both loops and copy `worker-backups` to the Mac.

