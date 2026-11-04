---
type: synthesis
created: 2026-11-03
updated: 2026-11-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [protocol, study, deepseek-v4-1-flash, codex, 100-tasks, random-sample, vertex, draft, living-document]
---
# 100 random tasks, e2e, DeepSeek V4.1 Flash with Codex on Vertex: protocol (DRAFT)

**Status: draft, nothing scored yet.** The DeepSeek counterpart of [[wiki/syntheses/qwen-100-task-study-protocol]] (same sample and design; model, endpoint, caps and credential path differ). Fixes the settings before the scored run so they cannot be tuned afterwards; changes go in the deviations log at the end. Setup and results of the ramp: [[wiki/syntheses/autoscaled-vertex-run-plan]]. This replicates the CyberGym paper's per-run rules.

## 1. Question
How does DeepSeek V4.1 Flash, driven by Codex through Google Vertex AI, do on CyberGym-E2E (find the bug, write a PoC and a patch from source only) over a fixed random sample of 100 tasks? Results are for this model only and are not compared with Qwen3.8-27B or other models run through different paths.

## 2. Design (fixed)
| Factor | Setting |
|---|---|
| Tasks | the 100 in `wiki/syntheses/aws-vm-data/random100_tasks.txt` (selection rule and sha256 in the Qwen protocol, section 3); none overlaps the 20 dev tasks used for the ramp |
| Mode | e2e only; pass requires S1 to S4 |
| Attempts | 1 per task |
| Model | `deepseek-v4.1-flash@vertex` in the registry: `deepseek-ai/deepseek-v4.1-flash-maas`, Vertex managed service, chat format |
| Harness | Codex through the metering shim; the shim translates Codex's Responses calls to Chat Completions for Vertex (recorded as part of the setup) |
| Limits | **10 USD per run and 90 minutes per run** (the paper's rules); nothing else. Price assumed by the study owner: 0.30 USD per million fresh input tokens, 0.03 cached, 1.20 output (aggregator listings of the Vertex rate, not yet checked on Google's own page) |
| Prompt | repo default `--prompt-style iterative` |
| Network | repo firewall on |
| Slots | 10 per node; the head plus up to 2 autoscaled workers (vCPU limit), so up to 30 at once |
| Infrastructure | Ray autoscaler on EC2; workers 1024 GiB disks; shared Postgres store; Google token path: temporary Mac-side refresher plus head relay, because no service account exists yet |

## 3. Ramp results that shaped the setup (20 dev tasks, outside the 100)
Stage 2 (10 tasks, head only): 3 passed S1 to S4, 2 passed S1 to S3 and failed S4, 5 did not produce a PoC or patch (two early model stops, one repetition loop, three hit the 90-minute limit). Per-task cost at the assumed prices: mean 1.64 USD, maximum 7.05. Details: [[wiki/syntheses/autoscaled-vertex-run-plan]].

## 4. What is part of the setup (disclose with the results)
- The Responses-to-Chat translation layer, including the handling of truncated tool-call arguments (the model sometimes ends a call with unterminated JSON about 1 time in 30; Codex returns the parse error and the model retries).
- A shim silence limit of 180 seconds and a per-call total limit of 600 seconds for Vertex (a stage-2 call ran 1,800 seconds with no content). A call that hits either is reported to Codex as a failed response and Codex retries it. These are infrastructure rules fixed before the scored run; they do not change the 10 USD or 90 minute limits.
- Worker nodes join under load; their first tasks wait for image pulls outside the agent timer.
- The credential is a one-hour Google token refreshed from the Mac every 30 minutes; if the refresher stops, calls fail with 401 and the affected tasks must be rerun.

## 5. Validity and infrastructure failures
- Task failures caused by infrastructure (disk full, image pull failure, expired token, worker lost) are not model results: such a task is rerun once, in the same way, and both outcomes are logged. A model failure is never rerun.
- The replacement rule for tasks that cannot be built is unchanged from the Qwen protocol and applies only before the scored run.
- Validity screens (PoC against the source tarball, helper-script wording, file modification times) are run on the 100 before launch.

## 5a. Validity screen results (2026-11-03, before any scored run)
Raw data: `wiki/syntheses/aws-vm-data/random100_screens.json`.
| Screen | Result |
|---|---|
| PoC byte-identical to a file in the source tarball | 5 tasks; 4 are coincidences with empty or tiny files (PoC of 0, 0, 1 and 4 bytes: `cpython3/arvo_61721`, `ffmpeg/oss-fuzz_385167047`, `libplist/arvo_44089`, `radare2/arvo_13704`); **1 is a real leak: `qpdf/oss-fuzz_42535152`, whose 33,453-byte PoC sits in the tree as `qpdf/build/fuzz/qpdf_corpus/357cc407...`** |
| Bug named in the task's helper files | 27 tasks match a word list (`overflow` in 14 test scripts, `CVE-2022` in 11 prepare scripts, `vulnerable` in 3); low signal, not read individually |
| Modification-time marker (1 to 10 files dated later than the tree, under 5% of it) | 60 of 100 tasks; 91 have some later-dated file. The pilot found the marker on all five tasks; here it is common but not universal |
Open: whether to replace `qpdf/oss-fuzz_42535152` (infrastructure evidence, allowed by the replacement rule before any scored run; the next unused task in the order is rank 121, because ranks 101 to 120 were the dev set) or keep it and report it separately. Decision: pending.

## 6. Gates before launch
| Gate | State (2026-11-03) |
|---|---|
| Tool calling through the shim | passed (smoke, stages 1 to 3) |
| Concurrency and context | 30 parallel calls completed; contexts up to 549k tokens completed |
| Disk | head cleared (41 GB used); workers 1024 GiB; the harness never removes images |
| Price and caps in the registry | set (10 USD per run, 1000 USD safety total per node) |
| Worker scale-up with real load | worked in stage 3 (one worker joined, calls through the relay returned 200) |
| First worker really has about 1 TB | to confirm at the first launch |
| 100-task manifest on the VM, data downloaded | done (`config/random100-e2e.json`, list sha256 matches; 36 GB of data, all 100 complete) |
| Validity screens on the 100 | done, see section 5a |
| Postgres dump before the run | done (Mac `spark/pg-backups/cybergym-pre-random100-20261103.sql`, outside git) |
| Mac awake and refresher running for the whole run | to arrange |

## 7. Deviations log
| Date | Deviation |
|---|---|
| 2026-11-03 | Two tasks of the drawn list were replaced before any scored run, under the replacement rule: `cpython3/arvo_61721` and `ffmpeg/oss-fuzz_385167047` have a 0-byte `poc.bin` in the dataset and the runner's preflight rejects them. Replaced in place by the next unused tasks in the order (ranks after the 20 dev tasks): `binutils/arvo_60532` and `ghostscript/oss-fuzz_399390078` (both non-empty PoCs; screens: no PoC in tree, marker present). The list sha256 changed from `8acd0cc32c7a457f3d5e0dc478a14aea07113d55de71806844af43e790317118` (as drawn) to `c685e88be6d2699fc22ba863e5eba8c1832bd4694afca401e1658335cbc82ee7` (as run). |
| 2026-11-03 | `qpdf/oss-fuzz_42535152` (PoC present in the source tree) was kept in the list as drawn; its result is reported separately. |
| 2026-11-03 | First pass of the 100 (19:43 to 22:01 UTC) lost 68 tasks to infrastructure failure. Two of the three autoscaled workers (10 slots each) ran out of memory (60 of 62 GB used, Ray memory monitor killed their task processes, then the autoscaler terminated the idle nodes): worker 3 at 20:41 (10 running tasks killed, and 52 not-yet-started tasks failed with the same error in the same 30 ms, matching the driver's 10 pending lease requests plus 42 queued tasks) and worker 1 at about 21:08 (7 more). Not model results; to be rerun (rule in section 5) with fewer slots per node. 31 tasks completed normally in the first pass. |
| 2026-11-04 | Rerun of the 68 lost tasks with 6 slots per worker and 4 on the head, plus a memory sampler; see [[wiki/syntheses/deepseek-100-first-pass-observations]]. |
| 2026-11-04 | Decision of the study owner: instead of rerunning only the 68 to 69 lost tasks, run all 100 again in one clean pass (pass 2, 06:07 UTC) under the changed settings (4 slots on the head, 6 per worker, 30 s launch spacing, memory sampler). The 31 tasks that completed in the first pass are kept as a separate record and are not mixed into pass 2. A 69-task driver started at 06:00 was stopped after about 7 minutes, before any task finished, and its three workers were terminated, because their data covered only 69 tasks. |

