---
type: synthesis
created: 2026-10-23
updated: 2026-10-23
sources: ["[[sources/cybergym-e2e]]"]
tags: [aws, ec2, ray, parallelism, benchmark-evals, kimi-k3, codex, bedrock, patch-only, spend-guard, infrastructure]
---
# AWS VM: benchmark-evals replica, Kimi K3 patch-only on 20 tasks, 2 vs 8 parallel runs

**One line:** on Amit's 16 vCPU / 61 GB EC2 VM, Codex + Kimi K3 (Bedrock) solved **20 of 20** seeded random patch-only tasks (S3 and S4 passed every time, one attempt each). Running **8 at once** (CPU saturated, load up to 33.7 on 16 cores) did not break anything and barely changed per-task time on three control tasks; 13 tasks finished in 18.2 minutes at 8 slots, where 9 took 77.9 minutes at 2 slots. The **limit of the machine was not found**. Total model spend was **$21.04** of a $150 cap.

Raw data (per-run results, sampler CSVs, sample list): `wiki/syntheses/aws-vm-data/`. Earlier Azure VM results: [[wiki/syntheses/cybergym-vm-runs]]; cross-model notes: [[wiki/syntheses/cross-model-observations]].

## 1. What was set up
| Item | Value |
|---|---|
| Machine | Amit's AWS EC2, us-east-1, 16 vCPU, 61 GB RAM, 496 GB disk, Ubuntu 26.04, shared with his own Ray head and proxy |
| Code | replica of `prescera/benchmark-evals` (private repo, from a zip) under `/home/harshav`; upstream `cybergym-e2e` cloned and patched by the repo's bootstrap |
| Model route | Codex inside the task container, `us.moonshotai.kimi-k3` on Bedrock's OpenAI-compatible endpoint (both `/chat/completions` and `/responses` work) |
| Mode | patch-only, 1 attempt, 90 min agent limit, $10 cap per task, $150 total cap |
| Sample | 50 tasks drawn with seed `20261023` from the 920 (31 projects, 37 arvo and 13 oss-fuzz); the first 20 of the seeded order were run |
| Scheduler | Ray, private local instance per batch; `benchmark_slots` is a made-up Ray resource that caps simultaneous runs |

Changes made to our copy of the runner (Amit's checkout was not touched): `prepare --skip-firewall` (so his shared `cybergym-proxy` is not recreated), a private Ray instance (`address="local"`, short temp dir), and per-execution metering through `llm_shim.py`.

## 2. Spend guard (why a proxy, not a log watcher)
`run_agent.py` captures Codex's stdout in memory and writes the trajectory only when Codex exits, so a log-tailing guard sees nothing during a run. Instead, Codex talks to the existing metering shim on the Docker gateway (`172.18.0.1:4100`, bound to that address only), which forwards to Bedrock. Each execution gets its own key with a $10 cap; the shim also has a $150 total cap. The container holds only the throwaway shim key, never the real Bedrock key. Tested before use with a fake upstream (cost matched a hand calculation) and then in a container on the no-internet network (87 in / 50 out tokens, $0.001112, matching hand arithmetic). Kimi K3 prices used: $3.30 / $0.33 / $16.50 per million (input / cache read / output), taken from third-party pages and **not verified against AWS**. The shim counts cache writes as ordinary input, a small undercount. The cap is checked before each request, so a run can overshoot by one request.

## 3. Results
Pilot: `librawspeed/arvo_4511`, 8.9 min wall, 21 requests, $0.51, S3 and S4 passed.

**Batch A: 2 slots.** Stopped at about 81 min with 9 finished (all passed; the last at 77.9 min), 2 cut just after starting, 9 never started.
| Task | Result | Wall min | Agent min | Requests | Cost |
|---|---|---|---|---|---|
| binutils/oss-fuzz_449440793 | S3 passed, S4 passed | 44.9 | 37.7 | 50 | $1.78 |
| elfutils/arvo_56179 | S3 passed, S4 passed | 44.8 | 40.5 | 83 | $3.95 |
| exiv2/arvo_45993 | S3 passed, S4 passed | 4.9 | 2.9 | 12 | $0.18 |
| lcms/arvo_49386 | S3 passed, S4 passed | 8.7 | 7.2 | 25 | $0.58 |
| lcms/arvo_49495 | S3 passed, S4 passed | 5.4 | 3.9 | 23 | $0.41 |
| librawspeed/arvo_4511 | S3 passed, S4 passed | 10.0 | 7.8 | 16 | $0.32 |
| libxaac/arvo_62274 | S3 passed, S4 passed | 3.4 | 1.9 | 22 | $0.33 |
| mruby/arvo_49550 | S3 passed, S4 passed | 22.9 | 18.2 | 67 | $1.97 |
| openssl/arvo_8241 | S3 passed, S4 passed | 10.2 | 4.3 | 16 | $0.28 |

**Batch B: 8 slots.** 14 tasks (the 11 unrun tasks plus 3 quick controls repeated from batch A). All passed.
| Task | Result | Wall min | Agent min | Requests | Cost |
|---|---|---|---|---|---|
| binutils/arvo_25841 | S3 passed, S4 passed | 78.8 | 56.8 | 104 | $4.06 |
| c-blosc2/arvo_30113 | S3 passed, S4 passed | 8.7 | 4.1 | 19 | $0.34 |
| c-blosc2/arvo_34259 | S3 passed, S4 passed | 9.7 | 4.0 | 20 | $0.34 |
| exiv2/arvo_45993 | S3 passed, S4 passed | 4.9 | 2.3 | 12 | $0.25 |
| fmt/arvo_25884 | S3 passed, S4 passed | 14.0 | 9.8 | 43 | $1.40 |
| jsoncpp/arvo_21916 | S3 passed, S4 passed | 4.8 | 2.4 | 15 | $0.26 |
| kamailio/oss-fuzz_391689728 | S3 passed, S4 passed | 11.4 | 4.6 | 11 | $0.18 |
| lcms/arvo_49495 | S3 passed, S4 passed | 4.4 | 2.7 | 21 | $0.38 |
| librawspeed/arvo_3498 | S3 passed, S4 passed | 11.4 | 7.3 | 18 | $0.81 |
| libxaac/arvo_62274 | S3 passed, S4 passed | 4.1 | 2.0 | 20 | $0.35 |
| libxml2/oss-fuzz_42537493 | S3 passed, S4 passed | 12.4 | 6.3 | 31 | $0.86 |
| mupdf/oss-fuzz_42537168 | S3 passed, S4 passed | 7.6 | 3.0 | 12 | $0.18 |
| opensc/arvo_25885 | S3 passed, S4 passed | 7.2 | 3.3 | 18 | $0.40 |
| opensips/arvo_53080 | S3 passed, S4 passed | 8.4 | 4.3 | 14 | $0.24 |

Cost over the 20 distinct tasks (first completed run each): **$18.87, mean $0.94, median $0.37**, max $4.06 (`binutils/arvo_25841`). Wall time median 9.8 min, mean 16.5 min, max 78.8 min. 732 model requests were logged by the shim and **all returned HTTP 200**.

## 4. Parallelism observations
| | Batch A (2 slots) | Batch B (8 slots) |
|---|---|---|
| Tasks finished | 9 in 77.9 min (3 long ones: 45, 45, 23 min) | 13 in 18.2 min, then the last (binutils) at 78.9 min |
| Throughput while busy | about 6.9 tasks/hour | about 43 tasks/hour (not like-for-like: different tasks) |
| Peak load average | 10.7 | **33.7** (2x the 16 cores) |
| CPU | peaks at 100% | 100% for about 15 minutes (starts and builds); the whole-batch average is meaningless here because 60 of 79 minutes had one task running (see section 4b) |
| Memory used, max | 11.4 GB (with only 1 agent running) | 9.3 GB (5 agents) |
| Swap | 0 | 0 |

**Controls** (same task at 2 slots, then at 8 slots; the 8-slot copies ran while the machine was saturated):

| Task | Wall A -> B (min) | Agent A -> B (min) | Requests A -> B | Cost A -> B |
|---|---|---|---|---|
| libxaac/arvo_62274 | 3.4 -> 4.1 | 1.9 -> 2.0 | 22 -> 20 | $0.33 -> $0.35 |
| exiv2/arvo_45993 | 4.9 -> 4.9 | 2.9 -> 2.3 | 12 -> 12 | $0.19 -> $0.25 |
| lcms/arvo_49495 | 5.4 -> 4.4 | 3.9 -> 2.7 | 23 -> 21 | $0.41 -> $0.38 |

What this supports: at 8 slots the machine ran at the CPU limit but tasks were not noticeably slower, nothing failed, and Bedrock did not throttle. What it does not show: where the limit is (12 or 16 slots were not tried), or how e2e behaves. Tasks in this sample are mostly short (4 to 14 min), so the CPU-heavy start-up and build phases overlapped a lot early on and the agent phases barely at all; longer agent phases would lower load per slot. n=3 controls is thin.

## 4b. CPU and memory, 2 slots against 8 slots (sampler, 10-second rows)
Idle baseline before any run: **3.5 GB used, load 0.05** (Amit's idle Ray processes and the OS). CPU % is across all 16 vCPUs. Windows are minutes since each batch started; "8 busy" means the first 20 minutes, while the queue still had work (the batch had 8 agents at the start and about 4 on average, because short tasks finished and the queue ran dry).

| Window | Rows | CPU avg / p90 / max | Load avg / p90 / max | Memory GB avg / p90 / max | Agent containers avg / max |
|---|---|---|---|---|---|
| **A, 2 slots, whole run (82 min)** | 487 | 16% / 61% / 100% | 3.0 / 6.8 / 10.7 | 5.3 / 5.9 / 11.4 | 1.7 / 2 |
| **B, 8 slots, first 20 min** | 119 | **58% / 100% / 100%** | **15.5 / 29.3 / 33.7** | 6.5 / 8.1 / 9.3 | 4.3 / 8 |
| B, minutes 0-5 (starts) | 29 | 44% / 98% / 100% | 8.0 / 13.8 / 15.2 | 6.2 / 6.9 / 7.0 | 7.6 / 8 |
| B, minutes 5-10 (builds) | 30 | **93% / 100% / 100%** | **26.1 / 32.1 / 33.7** | 7.5 / 8.4 / 9.3 | 4.3 / 6 |
| B, minutes 10-15 | 30 | 71% / 99% / 100% | 20.1 / 25.7 / 28.3 | 6.9 / 8.2 / 8.2 | 4.3 / 6 |
| B, minutes 15-20 | 30 | 25% / 77% / 89% | 7.5 / 16.9 / 18.2 | 5.6 / 6.0 / 6.1 | 1.1 / 2 |
| B, minutes 20-79 (only binutils running) | 358 | 5.6% / 7.5% / 7.7% | 1.0 / 1.4 / 1.8 | 5.1 / 5.5 / 6.3 | 0.6 / 1 |

What stands out:
- **CPU is bursty, not steady.** Even with 2 slots the median CPU was only 6.7% (p90 61%): tasks spend most of their time waiting on the model and burn the cores in short compile/test bursts. At 8 slots the bursts overlapped and CPU sat near 100% for about 5 to 10 minutes (minutes 5-10: average 93%). That is the real contention window.
- **The work done is similar, just compressed:** about 202 core-minutes of CPU over the 82 minutes of batch A (9 tasks, about 22 per task) and about 185 core-minutes over the first 20 minutes of batch B (13 tasks, about 14 per task). So 8 slots used about 9 cores on average in that window, out of 16, and the machine was not saturated the whole time, only during the build overlap.
- **Load average peaked at 33.7 (about 2.1 per core) yet tasks were not slower** (controls, section 4), because load counts runnable and uninterruptible-IO threads, not just CPU-bound ones.
- **Memory per agent container above the 3.5 GB baseline: about 1.0 to 1.1 GB on average, p90 about 2 GB** (both batches). The two batches' maxima are not comparable: batch A's **11.4 GB peak happened with only one agent running** (minute 76, during a final grading/validation step, probably `elfutils/arvo_56179` but not verified), which implies one heavy task can use about 8 GB alone. Batch B's 9.3 GB came with 5 agents.
- **Memory is the likely limit at higher slot counts, not CPU.** Averages say 8 slots needs about 7 to 9 GB, but if several heavy builds coincide (8 GB each), 8 slots could reach about 60 GB of 61. No run came close, no swap was ever used, and no out-of-memory kills were seen. This is an inference from a single observation of one heavy task, so 12 or 16 slots should be tried with the memory curve watched.
- Disk did not change visibly during the runs (the images were pulled beforehand); network and per-container CPU were not separated by the sampler.

Limits of this comparison: the two batches ran different tasks, one sampler row per 10 seconds, no per-container CPU/memory (the sampler reads host totals), and Amit's own processes were idle throughout but are included in the baseline.

## 5. Estimates against reality
- My early patch-only estimate was **$0.18 per task** (from five easy tasks, see [[wiki/syntheses/all-runs-comparison]]). Over 20 random tasks the mean was **$0.94** (median $0.37): a few long tasks (elfutils $3.95, binutils $4.06, mruby $1.97, binutils-449440793 $1.78) dominate. For the remaining 30 sampled tasks, expect about $28 at the same mean (wide range).
- Time per task is heavy-tailed: median 9.8 min but 3 of 20 took 45 to 79 min. A batch finishes when its slowest task does; here the last task ran 60 minutes alone, so slot count mattered little for wall time at the end.
- e2e (not run here) cost $0.21 to $10.02 per task on the Azure VM with Kimi K3; see [[wiki/syntheses/cybergym-vm-runs]].

## 6. Mistakes and gotchas worth keeping
- **Stdout buffering:** the driver's progress file is block-buffered, so counting finished tasks from it undercounted (5 shown, 9 true). Use the SQLite state (`state/runs.sqlite3`), not the output file.
- **Ray socket path limit:** a temp dir under a long work-root path exceeded the 107-byte Unix socket limit and the first launch of batch A failed with nothing run. Fixed with a short temp dir (`/tmp/ray-<uid>`).
- **`pgrep -f` and `pkill -f` match their own SSH command line** (twice, "already running" false positives). Check a port or anchor the pattern.
- **Watcher false "ALLDONE":** when the laptop slept, SSH failed with a DNS error, my loop read empty output as "finished". A check must treat an SSH failure as unknown.
- **Container names:** agent containers are `codex-<id>`, but the grading containers get random Docker names, so counting `codex-*` undercounts running tasks.
- Stopping a Ray driver mid-batch: the two tasks just started were lost (a few minutes of work each); their containers had to be removed by hand (only ours, never Amit's four).
- Credential steps (copying Amit's key file with sudo, running the bootstrap) were blocked by the tool's permission classifier, and were done by the user or by file operations inside `/home/harshav` after consent.

## 7. Open questions and next steps
1. **Where is the limit?** Try 12 and 16 slots on the remaining 30 sampled tasks, with the sampler and the shim guard on.
2. **e2e** at the best slot count on a subset; about $129 of the $150 cap remains; 20 e2e tasks would cost roughly $77 to $136 (Kimi K3 e2e mean $3.86 on five Azure runs, times a possible Bedrock price premium).
3. Amit's confirmation of the key use, the proxy sharing and a quiet window is still wanted; his Ray head ran idle throughout.
4. Verify the Kimi K3 Bedrock price against AWS.
5. Scaling beyond one VM needs shared state (SQLite and artifacts are node-local) and node-loss handling; see the Ray cluster discussion in this session's notes.
