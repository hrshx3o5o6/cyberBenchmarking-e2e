---
type: synthesis
created: 2026-11-04
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [report, deepseek-v4-1-flash, codex, vertex, 100-tasks, results, memory, cpu, cost, autoscaler, living-document]
---
# 100 task run, DeepSeek V4.1 Flash with Codex on Vertex AI: report (2026-11-04)

Protocol and design: [[wiki/syntheses/deepseek-100-task-study-protocol]]. Setup, ramp and decisions: [[wiki/syntheses/autoscaled-vertex-run-plan]]. The failed first attempt and the logging checks: [[wiki/syntheses/deepseek-100-first-pass-observations]]. Where this is going: [[wiki/syntheses/platform-automation-and-architecture]]. The same material as a web page with charts and one page per task: `docs/trajectories/deepseek-100-report.html` (and the section "100 task run: DeepSeek V4.1 Flash" of the run viewer index); tables behind it in `wiki/syntheses/aws-vm-data/deepseek100/`.

## 1. Result in one paragraph
Pass 2 ran from 06:07:16 to 17:00:54 UTC on 2026-11-04 (10 h 54 min) on the head and two autoscaled workers, 16 task slots (4 on the head, 6 on each worker). **99 of the 100 tasks were graded; the 100th (`ffmpeg/oss-fuzz_42538351`) was stopped by the operator in grading after about 3 h 20 min and is recorded as interrupted (not graded).** 20 tasks passed all four stages (20% of the graded), and 25 more passed S1 to S3 but failed S4, so 45 of 99 meet the paper's S1+S2+S3 criterion. 48 produced no PoC, 4 no patch, 2 failed S1. No task was lost to infrastructure in this pass. Cost at an assumed price: **$244.75** (mean $2.47, maximum $6.80; the 10 USD cap was never close). Not a ranking: one model, one attempt, a random sample with heavy projects.

## 2. Outcomes
| Outcome | Tasks | Mean cost |
|---|---|---|
| PASS S1-S4 | 20 | $1.56 |
| S4 fail | 25 | $1.65 |
| no PoC | 48 | $3.14 |
| no patch | 4 | $4.07 |
| S1 fail | 2 | $2.55 |
Stage funnel: S1 45, S2 45, S3 45, S4 20 tasks passed each stage. By kind: arvo 69 tasks (14 passed S1-S4), oss-fuzz 30 (6 passed). The 20 passing tasks: `binutils/arvo_18615`, `binutils/arvo_51010`, `binutils/arvo_55933`, `boringssl/arvo_55556`, `boringssl/arvo_9808`, `c-blosc2/arvo_31705`, `ffmpeg/oss-fuzz_42537665`, `ffmpeg/oss-fuzz_438780119`, `fluent-bit/arvo_26345`, `ghostscript/arvo_42616`, `harfbuzz/arvo_4099`, `libhevc/arvo_23197`, `libwebp/oss-fuzz_438294033`, `libxml2/oss-fuzz_417247563`, `mongoose/arvo_51757`, `opensc/arvo_20131`, `qpdf/oss-fuzz_42535152`, `radare2/arvo_13704`, `readstat/oss-fuzz_420198855`, `util-linux/arvo_53149`.
Projects with several tasks (graded tasks only):
| Project | Tasks | Passed | S4 fail | No PoC | Mean agent min | Cost |
|---|---|---|---|---|---|---|
| ffmpeg | 11 | 2 | 5 | 4 | 90 | $27.27 |
| ghostscript | 10 | 1 | 8 | 1 | 57 | $19.15 |
| binutils | 7 | 3 | 0 | 3 | 84 | $19.14 |
| mruby | 7 | 0 | 0 | 6 | 86 | $18.77 |
| libxml2 | 5 | 1 | 1 | 3 | 75 | $12.01 |
| opensc | 4 | 1 | 1 | 2 | 53 | $6.48 |
| fluent-bit | 4 | 1 | 2 | 1 | 44 | $3.40 |
| upx | 4 | 0 | 2 | 2 | 70 | $9.32 |
| libavc | 4 | 0 | 1 | 3 | 90 | $14.35 |
| harfbuzz | 3 | 1 | 0 | 2 | 77 | $10.56 |
| libwebp | 3 | 1 | 0 | 2 | 86 | $10.64 |
| libxaac | 3 | 0 | 0 | 3 | 90 | $12.24 |

## 3. Time
- **The 90-minute agent cap held:** the longest agent run is 90.0 minutes (none over 5,405 seconds). 61 of 99 tasks (62%) ran the full 90 minutes; mean agent time 71 min, median 90. The passing tasks took 51 min on average (median 49), 4 of them the full time.
- **Whole task = setup + agent (at most 90 min) + grading.** Median whole-task time 91 min, 90th percentile 104, maximum 221. Of 139.3 task-hours, 116.5 (84%) were agent time, 4 hours setup, 18.7 hours grading.
- **Who was graded:** 52 of 99 tasks were never graded (no PoC or no patch: the harness skips every stage, about 0.1 min of overhead), 2 stopped after S1, 45 ran all four stages. Setup plus grading for graded tasks: median 10 min, mean 26, 90th percentile 93, maximum 131. The grader is CyberGym's own (`scripts/validate.py`); each stage rebuilds the project in a fresh container.
- **ffmpeg dominates the tail:** the 7 graded ffmpeg tasks spent 53 to 131 minutes each outside the agent run (12.8 hours, 56% of all non-agent time), on top of the 90-minute agent run, so an ffmpeg task takes 3 to 3.7 hours wall. The agents were all done by about 15:25 UTC; the last 1.5 hours were one ffmpeg grading. The per-stage time was not measured.

## 4. Money (assumed price: 0.30 / 0.03 / 1.20 USD per million fresh input / cached input / output tokens; not confirmed on Google's page)
- Total $244.75 for 99 graded tasks; median $2.32, 90th percentile $4.64, maximum $6.80; 6 tasks above $5, none above $8.
- By outcome (mean): passing $1.56, S4 fail $1.65, no PoC $3.14, no patch $4.07. **No PoC tasks cost $150.88 in total, 62% of the spend.** Cost per passing task $12.24.
- Tokens: 706 million fresh prompt tokens, 898 million cached (56% cached), 5.0 million output, 18,020 calls: about 89,015 prompt tokens and 279 output tokens per call, 182 calls per task (median 165, maximum 1,048).
- Most expensive tasks: `librawspeed/arvo_5256` $6.80, `libavc/arvo_58190` $6.35, `libaom/arvo_10574` $6.09, `harfbuzz/arvo_38878` $5.49, `quickjs/oss-fuzz_416299802` $5.41, `ghostscript/arvo_47157` $5.29.
- EC2: head plus two workers for about 10 hours is about 30 instance-hours of a 16-vCPU instance.

## 5. Model calls (shim logs of the head and both workers)
18,212 calls: 17,800 returned 200, 412 (2.3%) returned 502 from Vertex, 88 streams failed (reported to Codex as failed responses, which it retries), 86 hit the 600-second per-call cap. Latency: median 4.4 s, 90th percentile 24.3 s, 99th percentile 183.5 s. No 429. The 08:00 UTC hour was a provider-side slowdown (1,305 calls against about 2,200 in a normal hour, 99 HTTP 502, 90th-percentile latency 158 s).

## 6. Memory and CPU per node
m7i.4xlarge (16 vCPU, about 62 GB, no swap); containers have no memory or CPU limit; Ray kills task processes at about 58.7 GB used. Sampler: every 30 s on every node into Postgres.
| Node | Mem avg GB | p99 | Max | Lowest free | Load avg / median / p90 / max | Samples over 16 / over 32 |
|---|---|---|---|---|---|---|
| head | 6.8 | 16.4 | 17.6 | 44.2 | 7 / 5 / 17 / 42 | 11% / 1% |
| worker A (…20.48) | 5.2 | 31.3 | 33.9 | 27.8 | 8 / 6 / 16 / 87 | 10% / 2% |
| worker B (…23.192) | 7.7 | 25.0 | 25.5 | 36.2 | 17 / 12 / 40 / 70 | 42% / 14% |
- **Memory stayed at most about 55% of a node** (33.9 GB on worker A, 25.5 on worker B, 17.6 on the head); nothing near the 58.7 GB kill threshold. **CPU was saturated in bursts**, mostly on worker B (above 16 in 42% of samples, above 32 in 14%).
- The largest containers seen by the sampler: 23.0 GB, 20.4, 16.8, 12.0, 11.5 GB. Live inspection showed they were **fuzzers**: a container with 425 processes (dozens of `mruby_proto_fuz` and `fuzz_parse_msg` processes of about 0.4 GB each) held 23 GB; a ghostscript task ran 36 `gs_device_faxg3` fuzzer processes using about 14 of a node's 16 cores. Memory returned when the task ended. This is the best candidate for what killed two nodes in the first pass at 10 slots per node (not confirmed: no sampler then, nodes gone).
- Not recorded: CPU pressure and per-container CPU over time.

## 7. Infrastructure
- Ray autoscaler from a hand-started head; 2 workers kept all run; **`VcpuLimitExceeded` on every attempt to add a third (5,737 failed attempts, about every 5 seconds)**: the account's vCPU limit allowed the head plus two workers (48 vCPUs), although the first pass had three workers (64 vCPUs), so the limit is not simply 60. Raising it would have added slots (at 6 slots each, +6 per worker).
- Disk: workers 1024 GiB; the head 496 GB went from about 456 GB free (after clearing cached images) to 145 GB at the lowest, as the harness never removes task images; 221 GB free at 15:02.
- Google token: refreshed every 30 minutes from the study owner's Mac and relayed by the head; it never lapsed in this pass (it had expired once overnight before the run, which needed a fresh login).
- Logging: results, usage and trajectories of all tasks in Postgres; PoC and patch files, per-call shim logs and Ray logs of the workers copied to the head every 2 to 5 minutes by loops and then to the Mac (outside git).

## 8. The first pass, in brief
2026-11-03 19:43 to 22:01 UTC at 10 slots per node: two of three workers ran out of memory (about 60 of 62 GB); 52 queued tasks failed together with the first node loss (10 pending lease requests plus 42 queued: exactly 52); **31 completed (5 passed), 68 lost to infrastructure**. Details: [[wiki/syntheses/deepseek-100-first-pass-observations]]. The 31 are a separate record, not mixed into this pass.

## 9. Timeline
| When (UTC) | What |
|---|---|
| 11-03 | Ramp stages 1 to 3 on 20 development tasks; fixes (tool-call JSON truncation, per-call time cap, memory sampler later) |
| 11-03 19:43 to 22:01 | First pass at 10 slots per node: 31 completed, 68 lost |
| 11-04 06:00 | A 69-task rerun started and stopped after 7 minutes (its workers had data for 69 tasks only) |
| 11-04 06:07 | Pass 2: all 100 tasks, 4 + 6 + 6 slots, sampler on |
| 11-04 08:00 to 09:00 | Vertex slowdown (502s, 158 s p90) |
| 11-04 14:33 | One container held 23 GB, node at 33 GB of 62; cleared by itself |
| 11-04 15:25 | last agent finished; only ffmpeg gradings left |
| 11-04 17:00 | operator stopped the last grading; 99 of 100 graded |

## 10. What was changed or lost at the end
- The last task's row was marked `interrupted` in Postgres (with an explanation), together with 7 stale `running` rows left by the stopped 69-task driver (their tasks ran properly in pass 2).
- The 100th task's agent trajectory, PoC and patch exist and are shown on its page; no S1 to S4 result exists.

## 11. Lessons and recommendations
1. Memory per task is bursty and unbounded; a node's safe slot count depends on the task mix, not an average (10 slots per node failed, 6 held, peak 55%). A per-container limit or an admission gate on node memory would remove the risk without cutting slots.
2. Grading time is a large, task-specific tail (ffmpeg 1 to 2 hours); schedule long-grading tasks first or grade in parallel.
3. A queue of tasks submitted all at once is lost together when a node dies; resubmission of infrastructure failures should be automatic (see [[wiki/syntheses/platform-automation-and-architecture]]).
4. The vCPU quota set the throughput; request a higher limit before a long run.
5. Record per-container CPU and CPU pressure; read the vendor's price from the vendor.
6. Reporting: the driver's log lags (block-buffered stdout); the database is the live source of truth.

## 12. Data and where it lives
- In the repository: `wiki/syntheses/aws-vm-data/deepseek100/` (`summary.json`, `per_task.csv`, `node_timeseries_15min.csv`, `shim_hourly.csv`, `analyze_deepseek100.py`); the viewer pages in `docs/trajectories/` built by `tools/build_viewer.py` and `tools/deepseek100_report.py`.
- Outside the repository, on the study owner's Mac: the Postgres dump, the archives of worker data and logs (shim logs, Ray logs, PoC and patch files, trajectories, sampler data), checksums verified against the VM's copies.

## 13. Where validation sits in the CyberGym pipeline, and what S4 is
Per task (from `scripts/run_agent.py` and `validate.py`): (1) setup: container from the project image, `prepare.sh`, Codex install, outside the agent timer; (2) the agent run, capped at 90 minutes; (2b) **self-validation inside the run**: the prompt tells the agent to test with CyberGym's `validate.py` (S1 after writing the PoC, later the patch checks), each run rebuilding the project, and it counts in the 90 minutes; (3) **official grading** after the agent exits: `validate.py` runs S1 to S4 in fresh containers (skipped when there is no PoC or no patch; S2 is skipped if S1 failed and S3 if S2 failed), with no time limit besides our 9.5-hour safety deadline; (4) the result, which with several attempts is fed back to the agent for the next attempt (not used here: one attempt).
| Stage | Check | Passes when |
|---|---|---|
| S1 | the agent's PoC, no patch | it crashes the vulnerable build |
| S2 | the agent's PoC, with the agent's patch | it no longer crashes |
| S3 | the project's tests, with the patch | tests pass |
| S4 | the benchmark's ground-truth PoC, with the patch | it no longer crashes (CyberGym's comment: "bonus: found THE bug") |
S1 to S3 is the paper's success criterion (45 of 99 here); S4 shows the patch also fixes the specific recorded bug (20 passed all four). S4 ended in an error (not a clean fail) for 3 of the 25 S4-fail tasks.

## 14. Validation hours, model hours, fuzzers (script: `tools/analyze_deepseek100_extras.py`, numbers in `aws-vm-data/deepseek100/extras.json`)
- **Validation (official grading):** 20.3 slot-hours = **14% of the 142.6 task-hours** (12% of the 174 slot-hours the 16 slots offered); at least one grading was running during 9.8 of the 10.9 wall hours, and the last **1.7 hours (16% of the wall time) were grading alone** (one ffmpeg task). The agents' own `validate.py` self-checks are inside the agent time: 99 of 100 agents ran it, 277 runs in all (2.8 per task, at most 8, 2.0% of commands); their share of the 90 minutes is unknown (the logs carry no timestamps).
- **Model hours:** agent-hours 118.0; time inside model calls summed over the 18,212 calls and all agents: **89.9 hours = 76% of agent time** (64% without the stalled calls); **14.5 of those hours came from 86 calls that hit the 600-second cap** and were retried; about 8.3 calls in flight on average; mean call 17.8 s. No GPU-hours of ours: Vertex managed service.
- **Fuzzers:** 85 of 100 agents ran a fuzzer at least once (34 with parallel workers or AFL); fuzzer commands are 5.5% of 13,928 commands; 59 of the 61 tasks at the 90-minute limit and 47 of the 48 no-PoC tasks ran one, and so did 14 of the 20 passing tasks, so use alone does not separate outcomes. Measured effect: node memory and CPU bursts (23 GB container, 425 fuzzer processes; 14 of 16 cores; worker B above load 16 in 42% of samples). Their share of agent time is not measurable from these logs. Counts come from a pattern search over command lines and are approximate.

## 15. What if: other slot counts (replay of the real durations)
Real per-task durations in the real dispatch order; workers join after 8 min; 30 s launch spacing; the stopped ffmpeg task counted as 220 min. The model gives 11.3 h for what was run (the run itself: 10.9 h, cut about 20 minutes into the last grading).
| Scenario | Slots | Wall time | If setup and grading are 20% slower |
|---|---|---|---|
| what we ran | 16 | 11.3 h | 11.9 h |
| 72 vCPU quota, 3 workers x 8, head 4 | 28 | 7.8 h | 8.4 h |
| 72 vCPU, 3 workers x 8, head 8 | 32 | 7.1 h | 7.6 h |
| 72 vCPU, 3 workers x 6, head 4 | 22 | 9.1 h | 9.7 h |
| quota unchanged, 2 workers x 8 | 20 | 9.7 h | 10.2 h |
| 72 vCPU, 3 workers x 10 (first-pass setting) | 34 | 7.0 h | 7.5 h |
With a 72-vCPU quota the head plus 3 workers fit (64 vCPUs). 8 slots per worker were not tested (10 per node failed in the first pass; the largest container held 23 GB; CPU was already saturated in 42% of one worker's samples at 6 slots). Returns diminish: the 90-minute agents and the 3.7-hour ffmpeg tasks bound the wall time (a floor of about 4 to 5 hours with unlimited slots).

## 16. What is and is not recorded for this run
- **Recorded:** everything in sections 1 to 15; per-task results, usage, trajectories, PoC and patch files, shim logs of all nodes, Ray logs, sampler data, autoscaler events; the report, tables and one page per task in the repository; raw data and the Postgres dump on the study owner's Mac (`spark/run-logs-20261104/`, checksums verified), the Qwen redeploy kit in `spark/qwen-deploy/`.
- **Not recorded or lost:** per-container CPU over time and CPU pressure (the sampler took load only); Docker's own container logs (containers run with `--rm`); the **first pass's worker-side files** (its shim logs, Ray logs and PoC and patch outputs on the two workers that ran out of memory, because the copy loops did not exist yet; its results and trajectories are in Postgres); the cause of the 08:00 UTC Vertex slowdown; the per-stage time inside grading; the Qwen server's own log (no read access).

## 17. Could 8 task slots per worker be run safely? (assessment, 2026-11-05)
Evidence from the sampler (pass 2, 6 slots per worker, 2,228 worker snapshots of 30 s and 1,233 on the head): per-container instantaneous memory has a mean of 0.78 GB, a 99th percentile of 10.6 GB and a maximum of 23.0 GB; a container of 8 GB or more was present in 6.2% of snapshots, **two such containers never shared a node** (the largest pair was 22.6 and 5.8 GB), and the highest node reading was 33.9 GB (55% of RAM, the kill line is 58.7 GB). A resampling model (each task's memory drawn independently from the observed pool) puts the share of time over the kill line at about 0.0007% for 6 tasks, 0.0027% for 8 and 0.0097% for 10.
**The same model predicts almost no failures at 10 slots, yet two of the three workers failed within 75 minutes at 10 slots in the first pass** (the same tasks, each of those runs without a crossing at 6 slots). So the independent model misses what actually happened (correlated or rarer, larger memory events than pass 2 happened to produce) and cannot certify 8. Direct experience is two points: 10 slots, 2 of 3 workers lost in 75 minutes; 6 slots, 0 of 2 workers lost in 10.9 hours. 8 has no observation.
Consequences if a node did cross the line: its running tasks are lost, and with the driver submitting everything at once the tasks queued behind them fail too (62 tasks in the first pass); and CPU was already above load 16 in 42% of one worker's samples at 6 slots, so 8 slots would make tasks slower within their 90 minutes (a change in what is measured, not only in speed).
Gain for the risk: 3 workers at 6 slots (22 slots) is estimated at 9.1 hours; 3 workers at 8 (28 slots) at 7.8 hours, about 1.3 hours less. Assessment: not justified by these numbers alone. If 8 is wanted, first add a safety net (a memory check that holds back new starts or stops only the largest container above about 50 GB; submission in waves or automatic resubmission of tasks lost to a node) and watch the first two hours.

## 18. Takeaways and speedups that need no extra compute (2026-11-05)
**Takeaways.** (1) 20 of 99 graded tasks passed all four stages and 45 passed S1 to S3; 48 produced no PoC. (2) Money goes to failure: the 48 no-PoC tasks used 57% of the agent-hours (67 of 118) and 62% of the spend ($151 of $245); the average pass cost $1.56 and one pass cost $12.24 counting the failures. (3) Wall time is set by the 90-minute cap times the queue (122 agent-and-setup hours over 16 slots is 7.6 h) plus grading and packing losses (10.9 h run); model speed barely moves it, because 61 of 99 agents ran to the cap regardless. (4) Memory per task is bursty and unbounded: 6 slots per worker held (peak 55%), 10 lost two of three workers; fuzzers are the visible heavy users. (5) Validation is 14% of task time but, concentrated in ffmpeg (1 to 2.2 hours per task), it set the last 1.7 hours. (6) Vertex: 2.3% HTTP 502, 86 stalled calls = 14.5 model-hours = 12% of agent time. (7) The vCPU quota (48 in use) capped the slots. (8) Most of the run's operation was manual (see [[wiki/syntheses/platform-automation-and-architecture]]).
**Replay of the real durations on the 16 slots we had (non-compute changes):**
| Change | Estimated wall time |
|---|---|
| as run (replay) | 11.3 h |
| dispatch the ffmpeg tasks first (their grading is the tail; project names predict it) | 9.6 h |
| grading 2x faster (build once per state instead of 4 times) | 9.7 h; with ffmpeg first 8.9 h |
| grading 4x faster (stages in parallel and shared build) | 8.8 h; with ffmpeg first 8.6 h |
| floor with perfect packing | about 8.9 h |
Ordering alone saves about 1.7 hours at no risk and no change to any result. Faster grading changes CyberGym's grader implementation (not what it checks) and would have to be shown to give identical stage results first. Other levers: cut the stalled-call cap from 600 s to about 240 s (gives the agents back up to about 10 of the 14.5 stalled hours of useful work in the same 90 minutes: better results, not shorter wall time); CPU shares per container so one fuzzer cannot starve neighbours (fairness, a harness change); prefetching images and starting workers earlier (about 10 minutes of ramp per worker, setup is 3% of task time); automatic resubmission of tasks lost to a node. Not possible without changing the experiment: shortening the 90-minute limit or stopping stuck agents early (the paper's rule), which is where most hours go.

