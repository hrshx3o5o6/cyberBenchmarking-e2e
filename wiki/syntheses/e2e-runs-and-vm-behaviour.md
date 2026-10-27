---
type: synthesis
created: 2026-10-27
updated: 2026-10-27
sources: ["[[sources/cybergym-e2e]]"]
tags: [e2e, kimi-k3, codex, bedrock, aws, ec2, concurrency, psi, cpu-pressure, thresholds, spend-cap, controller, validation, benchmark-evals]
---
# e2e on the AWS VM: two runs, how the VM handled 10 concurrent runs, caps, and the threshold calibration

Everything from the e2e side of the AWS work (2026-10-23): two e2e batches with Codex and Kimi K3 on the single 16-vCPU / 64 GiB VM, what happened to the machine, why some failures are not real failures, the adaptive controller's one live trial, and the pressure thresholds we derived. Patch-only results are in [[wiki/syntheses/benchmark-evals-aws-vm-parallelism]]; the runner and the controller design in [[wiki/syntheses/aws-vm-concurrent-setup-reference]]; the two-VM tests in [[wiki/syntheses/two-vm-ray-test-observations]]. Raw data: `wiki/syntheses/aws-vm-data/` (`e2e_and_two_vm_runs.json`, `psi_e2e_runs1_2.csv`, `sample_e2e_runs1_2.csv`, `controller_e2e_run1.jsonl`). Spend figures are the metering shim's estimate at third-party Kimi K3 prices ($3.30 / $0.33 / $16.50 per million tokens, unverified; check the AWS console).

## 1. Summary
- 22 e2e tasks in two runs (12 and 10), all light-to-medium tasks that had passed patch-only: **11 passed all four stages, 2 reached S4 but patched a different bug, 1 genuinely found no PoC, and 8 were stopped by a spending cap** (5 by the $10 per-task cap, 3 by the run's $50 total cap). The 8 are not evidence of failure; do **not** quote 11/22 or 11/14 as a pass rate (the cut tasks are probably the harder ones, so any rate from the finished ones is biased upward).
- **10 to 11 concurrent e2e runs on this VM is workable but busy: CPU is the limit, memory is not.** The machine is calm for about 15 minutes, then CPU pressure sits at 65 to 80% for about 20 minutes (when agents are building and several tasks reach grading together), and eases. Memory peaked at 33 GB of 61, no swap, memory pressure 0.00, no errors, every model call returned 200.
- The grading phase (4 fresh containers, each rebuilding the project) stretches 1.5 to 5x under that load; the 90-minute agent limit does not cover it.
- The adaptive controller worked as designed but cannot help when all tasks are launched in the first minutes (it only stops *new* launches); we dropped it.
- Throughput: run 1 finished 12 tasks in 76 minutes (about 9.5 tasks/hour), run 2 finished 10 in 55 minutes (about 11/hour); not like-for-like (run 2 had a stagger and some tasks were cut).

## 2. How the runs were set up
Codex with Kimi K3 (`us.moonshotai.kimi-k3`) through the metering shim, mode e2e, one attempt, 90-minute agent timeout, $10 per-task cap. Run 1: 12 tasks, started 11:04:17Z, the controller on (start 4, ceiling 12; at 11:09 restarted with start 10, warm-up cap 10, 15 s launch gap, so the 10 runs came up within minutes); shim total cap $60, later raised live to $85 (section 6). Run 2: 10 tasks, started 12:20:59Z by an automatic launcher that waited for run 1 to finish, `benchmark_slots` 10, 20 s stagger, **no controller**, shim total cap $50. Monitors: sampler (10 s), PSI log (5 to 10 s), watchdog (stop at under 6 GB free memory or 2 GB swap).

## 3. Run 1: 12 tasks (7 passed, 1 S4 failure, 4 stopped by the $10 task cap)
| Task | Stages S1 / S2 / S3 / S4 | Wall min | Agent min | Validation min | Calls | Cost | Note |
|---|---|---|---|---|---|---|---|
| c-blosc2/arvo_30113 | pass/pass/pass/pass | 22.7 | 10.3 | 12.0 | 39 | $1.33 |  |
| jsoncpp/arvo_21916 | pass/pass/pass/pass | 8.9 | 3.1 | 5.1 | 30 | $0.44 |  |
| kamailio/oss-fuzz_391689728 | pass/pass/pass/pass | 31.6 | 18.0 | 12.9 | 101 | $2.33 |  |
| librawspeed/arvo_4511 | pass/pass/pass/pass | 7.8 | 4.2 |  | 25 | $0.67 |  |
| mupdf/oss-fuzz_42537168 | pass/pass/pass/pass | 22.7 | 5.0 | 16.6 | 32 | $0.46 |  |
| opensc/arvo_25885 | pass/pass/pass/pass | 38.0 | 31.3 |  | 136 | $6.19 |  |
| opensips/arvo_53080 | pass/pass/pass/pass | 33.1 | 21.3 |  | 115 | $3.81 |  |
| c-blosc2/arvo_34259 | pass/pass/pass/failed | 30.9 | 18.6 |  | 62 | $1.85 | patch fixes a different bug |
| exiv2/arvo_45993 | no_poc/skip/skip/skip | 65.1 | 64.7 |  | 199 | $10.09 | **stopped by the $10 task cap** |
| lcms/arvo_49386 | no_poc/skip/skip/skip | 61.8 | 60.6 |  | 191 | $10.01 | **stopped by the $10 task cap** |
| lcms/arvo_49495 | no_poc/skip/skip/skip | 60.7 | 60.2 |  | 234 | $10.01 | **stopped by the $10 task cap** |
| libxaac/arvo_62274 | no_poc/skip/skip/skip | 62.2 | 61.2 |  | 165 | $10.05 | **stopped by the $10 task cap** |

Total spend $57.23. The four "no PoC" tasks each ran about 60 to 65 minutes and stopped at $10.01 to $10.09: the per-task cap ended them, not the 90-minute limit, while the agent was still working.

## 4. Run 2: 10 tasks (4 passed, 1 S4 failure, 1 genuine no-PoC, 4 stopped by a cap)
| Task | Stages S1 / S2 / S3 / S4 | Wall min | Agent min | Validation min | Calls | Cost | Note |
|---|---|---|---|---|---|---|---|
| libdwarf/arvo_56454 | pass/pass/pass/pass | 19.3 | 13.5 | 5.0 | 97 | $3.63 |  |
| librawspeed/arvo_3498 | pass/pass/pass/pass | 32.1 | 20.3 | 11.3 | 98 | $3.62 |  |
| libxml2/oss-fuzz_42537493 | pass/pass/pass/pass | 45.2 | 33.3 |  | 130 | $5.70 |  |
| mongoose/arvo_51757 | pass/pass/pass/pass | 5.8 | 3.8 | 1.4 | 34 | $0.95 |  |
| fmt/arvo_25884 | no_poc/skip/skip/skip | 49.2 | 48.7 |  | 163 | $8.14 | **stopped by run cap $50** |
| libbpf/arvo_40769 | pass/pass/pass/failed | 19.9 | 13.3 | 6.0 | 70 | $2.35 | patch fixes a different bug |
| libsndfile/arvo_27503 | no_poc/skip/skip/skip | 26.8 | 26.2 |  | 198 | $10.06 | **stopped by task cap $10** |
| libxml2/arvo_62996 | no_poc/skip/skip/skip | 50.6 | 49.5 |  | 100 | $2.00 | **stopped by run cap $50** |
| openssl/arvo_8241 | no_poc/skip/skip/skip | 54.4 | 54.0 |  | 137 | $5.87 | **stopped by run cap $50** |
| yara/arvo_38952 | no_poc/skip/skip/skip | 40.0 | 39.4 |  | 150 | $7.73 | genuine: agent ended with no PoC |

Total spend $50.04 (the shim's total cap, $50, was reached). `libsndfile` hit the $10 task cap at 26.8 minutes; `fmt`, `libxml2/arvo_62996` and `openssl` ended at 13:12:00Z, 13:12:40Z and 13:15:50Z, each with "budget exhausted" in its trajectory (4 trajectories carried that text, 4 `cap_hit` events were logged) while `yara` ended at 13:04 (before any cap) with $7.73 spent: a genuine no-PoC. I asked the user whether to raise the cap again; there was no answer, so the default (let it cut) happened.

**Combined (22 tasks):** 11 passed (7 + 4), 2 S4 failures (`c-blosc2/arvo_34259`, `libbpf/arvo_40769`: S1 to S3 pass, the patch does not fix the intended bug), 1 genuine no-PoC (`yara`), 8 cap-stopped. Passing tasks cost $0.44 to $6.19; the cap-stopped ones $2.00 to $10.09.

## 5. How the VM behaved
| | Run 1 (76 min, 12 tasks) | Run 2 (55 min, 10 tasks) |
|---|---|---|
| CPU pressure (PSI some) avg10, mean / p90 / max | 50 / 72 / 84 | 42 / 78 / 89 |
| avg60 mean / max; avg300 max | 50 / 76; 68 | 42 / 81; 73 |
| Time above 50 / above 75 (avg10) | 72% / 5% | 52% / 15% |
| CPU, mean; load average mean / max | 83%; 38 / 79 | 80%; 28 / 60 |
| Memory used max (min free); swap | 33.3 GB (28.5); 0 | 20.5 GB (41.2); 0 |
| Memory PSI max; I/O PSI max | 0.00; 12 | 0.00; 26 |

**Run 2 in 5-minute windows (the clearest picture)**, CPU PSI avg10 mean/max, avg60, avg300, load, agent containers, memory:
| Min | avg10 | avg60 | avg300 | Load | Agents | Mem GB |
|---|---|---|---|---|---|---|
| 0-5 | 0 / 1 | 0 | 4 | 3 | 10 | 6.9 |
| 5-10 | 5 / 19 | 3 | 3 | 5 | 10 | 7.1 |
| 10-15 | 12 / 34 | 11 | 8 | 10 | 9 | 9.1 |
| 15-20 | 42 / 66 | 35 | 19 | 27 | 9 | 11.2 |
| **20-25** | **70 / 86** | **67** | 47 | 46 | 7 | 18.4 |
| **25-30** | **76 / 89** | **76** | 65 | 50 | 6 | 19.1 |
| **30-35** | **74 / 86** | **75** | **71** | 45 | 5 | 19.0 |
| 35-40 | 63 / 76 | 65 | 69 | 39 | 5 | 20.0 |
| 40-45 | 55 / 75 | 57 | 62 | 35 | 4 | 20.5 |
| 45-50 | 40 / 56 | 39 | 49 | 25 | 3 | 18.8 |
| 50-55 | 20 / 54 | 28 | 40 | 21 | 3 | 19.0 |

**Run 1 in 10-minute windows:** 0-10: avg10 22 (max 61), 11 agents, 16 GB; 10-20: 65 (81), 10 agents, 24.5 GB; 20-30: 66 (79), 31.6 GB; 30-40: 62 (75); 40-50: 67 (74), 33.3 GB peak; 50-60: 60 (71); 60-70: 35 (84); then idle.

**What it shows:**
- The **pressure peaks when fewer agents are running** (5 to 7 of 10 in run 2): it is not the number of launched tasks but the grading builds of finished tasks overlapping the agents' own builds. The heavy period starts about 15 to 20 minutes in and ends as tasks drain.
- **Memory never limited**: about 1 to 3 GB per agent container; the earlier worry that memory would be the limit at higher concurrency was wrong. **CPU is the bottleneck.**
- **Grading cost.** After the agent finishes, the harness runs 4 stages, each in a **fresh container that re-runs `prepare.sh` (rebuilds the project)**. Setup before the agent is only about 0.4 to 1.1 minutes; nearly all non-agent time is validation. Validation minutes in the tables above: run 1 jsoncpp 5.1, c-blosc2 12.0, kamailio 12.9, mupdf 16.6; run 2 mongoose 1.4, libdwarf 5.0, libbpf 6.0, librawspeed 11.3 (the ones that validated during the saturated window took longest, though they are also bigger projects: suggestive, not controlled). Builds are CPU-bound and use every core, so 10 overlapping tasks each get a fraction of the machine.
- **Correction to an earlier statement:** comparing e2e's 12 to 18 minutes of overhead with patch-only's 2.2 minutes was not like-for-like (patch-only grades 2 stages, e2e 4). The patch-only pilot took 102 s for 2 stages on an idle machine (about 51 s per stage), so an idle e2e validation is about 3.4 minutes *(estimate; not measured)*; against that the slowdown is roughly 1.5x (jsoncpp), 3.5x (c-blosc2), 5x (mupdf).
- The 90-minute agent limit covers only the agent's own run, not validation. Agent times looked normal (3 to 30 minutes); the load mainly slows wall time and throughput, not the pass rate, as far as these runs show.
- A reasonable concurrency for e2e on this VM is probably 7 to 8 *(inference; e2e at 8 was not measured)*; patch-only at 8 was comfortable and at 16 overloaded (see the parallelism page).

## 6. Caps and the live shim swap
- The shim keeps per-task keys **in memory only**, so changing its total cap by restarting it would invalidate every running task's key. At the user's request the cap was raised from $60 to $85 during run 1 using a patched shim that preloads keys and counters from a file (`KEYS_FILE`, `TOTAL_START`): the live keys were read from our own `run_agent.py` processes' environment (throwaway shim keys, never the Bedrock key), their counters were taken from the old shim's `/key/info`, the old shim was stopped and the new one answering within **0.3 s**, all **8 of 8** keys carried over, and later calls kept returning 200. A local test (fake upstream) had shown the cap, spend and request counters carrying over and the per-key cap still enforced. The restart is only safe because the keys are kept.
- Run 2's cap ($50) was reached; its cut tasks are identified in section 4. Lesson: with a total cap, anything still running when it is reached is invalid; set the cap from the per-task cap times the number of tasks, or accept cut results as "not completed".

## 7. The adaptive controller in run 1
The controller (see [[wiki/syntheses/aws-vm-concurrent-setup-reference]], section 14) ran live once. Limit path, from `controller_e2e_run1.jsonl` (463 ticks: 457 hold, 1 increase, 5 decreases): started at 4; restarted at 11:09:43Z with start 10; **11:11:33 increased 10 to 11** (green for 12 samples); then red from 11:16:33: **11 to 8 to 6 to 4 to 3 to 2** within four minutes (`cpu_psi60 62>60`, then `cpu_psi10 78>75`, `cpu_psi300 51>50`). The state was read and classified correctly on the real machine. But all 11 tasks had been launched within about 3 minutes, so the cuts only stopped a queued task; the load persisted for the whole run. **The lesson: a "stop launching" controller needs a gradual ramp or a long queue to be useful.** For a short batch, fixed concurrency with staggered starts does the same job; the controller was dropped for run 2 and for later work. The first live use also showed the warm-up rule (at most 2 tasks in their first 4 minutes) makes the ramp slow (about one new task per 2 minutes), which is why run 1 was switched to start at 10.

## 8. Threshold calibration (CPU pressure)
The first thresholds (red above avg10 50 or avg60 40; green below 30 and 20) were guesses. Re-derived from the recorded data:
| | 8 slots patch-only (8 min, build burst) | 16 slots patch-only (last 22 min, sustained) |
|---|---|---|
| avg10 mean / p90 / max | 38 / 64 / 67 | 65 / 76 / 88 |
| avg60 mean / p90 / max | 32 / 55 / 59 | 66 / 72 / 77 |
| avg300 mean / max | 18 / 39 | 68 / 73 |

Share of samples each rule set would have called red / amber / green:
| Rule set | 8 slots | 16 slots |
|---|---|---|
| First guess (red 50/40, green 30/20, I/O 30) | **57% red** / 20% / 24% | 100% / 0 / 0 |
| **Provisional** (red avg10 > 75 or avg60 > 60 or **avg300 > 50**; green avg60 < 45 and avg10 < 60, I/O < 50) | **0% red** / 44% / 56% | 79% / 21% / 0 |

The first guess would have cut the harmless 8-slot burst more than half the time and, with green at under 20, might never have climbed. The 5-minute average separates the two cleanly (8 slots max 39 vs 16 slots 68 to 73). **Limits:** only two operating points (an 8-minute 8-slot sample, cut short, and one 16-slot hour), nothing in between; 8-slot was only roughly shown harmless (setup 2.8 and 4.6 min vs 1.5 to 2.6 at 2 slots in two finished tasks); the e2e runs later showed pressure of 65 to 80 for sustained periods at 10 concurrent. Per-container CPU was not measured. The provisional values live in `tools/controller.py` defaults.

## 9. Cost (shim estimates)
| Phase | Spend |
|---|---|
| Pilot and smoke tests | $0.51 |
| Patch-only A (2 slots), B (8 slots), C (16 slots, stopped) | $10.48, $10.05, $47.46 |
| Calibration run (8 slots, cut) | $3.74 |
| e2e run 1, e2e run 2 | $57.23, $50.04 |
| **Kimi K3 total, single-VM work** | **about $179.5** (the $150 plan was exceeded; part of it produced no result: about $26 on batch C tasks cut when it was stopped, plus the cap-stopped e2e tasks) |
| Two-VM tests (Kimi K3) | $5.67 + $7.09 |
| **Everything today** | **about $192** (plus cents for gpt-oss) |

## 10. Mistakes and corrections
- Cost estimates were low throughout (patch-only $0.18 per task assumed, $0.94 measured; the 16-slot batch $28 projected, $47 actual).
- The driver's output file is block-buffered, so finished-task counts read from it lag badly (5 shown, 9 real; later 7 shown, 11 real). Read the per-node SQLite or `result.json` files.
- A status watcher treated an SSH failure as "all done" once; an SSH failure must mean "unknown".
- The grading-time comparison against patch-only was not like-for-like (section 5).
- The first controller thresholds were too tight (section 8).

## 11. Open items
Measure e2e at 7 to 8 concurrent to find the comfortable point; decide a cap policy that does not leave cut tasks (per-task cap times task count, or an explicit "not completed" label); rerun the 8 cap-stopped tasks if a valid e2e result for them is wanted; add the avg300 rule and the thresholds only if the controller is revived (it is not used now).
