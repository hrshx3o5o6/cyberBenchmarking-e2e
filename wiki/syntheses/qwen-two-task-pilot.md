---
type: synthesis
created: 2026-11-05
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [qwen, qwen3-8-27b, vertex, pilot, expectations, codex, cybergym, living-document]
---
# Qwen3.8-27B two-task pilot on the Vertex endpoint: expectations and results (2026-11-05)

**Status: done. Both tasks passed S1 to S4 (section 7).** Expectations (sections 3 to 6) were written before the run and are left unchanged. Serving background and measurements: [[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]]; capacity reasoning: [[wiki/syntheses/qwen27b-serving-capacity-analysis]]; the 100-task Qwen protocol this feeds: [[wiki/syntheses/qwen-100-task-study-protocol]]; registry side: [[wiki/syntheses/plug-and-play-model-support]]. Ids are not recorded here.

## 1. Setup
- Model `qwen3.8-27b@vertex-dedicated` (registry), served in configuration C (prefix caching on, CUDA graphs on) on one A100 80GB; deployed 2026-11-05 about 08:36 UTC, about 25 minutes to answer.
- Tasks `igraph/arvo_29408` and `md4c/arvo_31332`, e2e, **2 at the same time**, Codex through the metering shim (Responses translated to Chat), paper limits 90 minutes per run, one attempt, token caps (the model has no price here).
- Why these two: the same model solved both e2e (S1 to S4) in batch 7, so a failure here points at the setup, not at task difficulty.

## 2. Baselines to compare with
| | igraph e2e | md4c e2e | Source |
|---|---|---|---|
| Qwen3.8-27B, Claude Code, OpenRouter (Wafer), batch 7 | S1-S4 pass, 18.6 min, 62 requests | S1-S4 pass, 14.1 min, 51 requests | [[wiki/syntheses/batch-7-summary]] |
- Batch 7 overall: 1,190 requests and 1.22M output tokens, so about **1,030 output tokens per request** (this is the only measured basis for output length).
- DeepSeek V4.1 Flash with Codex over 100 random tasks: median 165 requests per task (mean 182), median over tasks of mean prompt per call 78k tokens; the 8 tasks with 80 requests or fewer had a median agent time of 13.1 minutes ([[wiki/syntheses/deepseek-100-task-run-report]]).

## 3. Expectations (predicted before running)
| Quantity | Expectation | Reason |
|---|---|---|
| Endpoint through the shim | works; tool calls and streaming valid | direct tests passed on all three configurations; the open risk is whether the dedicated endpoint needs a user-project header that the shim only sends with real Google credentials |
| Calls per task | **about 50 to 100** (point guess 70) | batch 7 needed 51 and 62 with Claude Code; Codex tends to use more; a call is capped by speed (below) |
| Duration of one call | **about 30 to 45 s median**, decode-dominated | about 1,000 output tokens at 27 to 28 tokens/s per stream is about 36 s; time to first token is only 0.5 to 2 s on a warm cache |
| Time per task | **about 40 to 90 min, 2 to 4 times slower than the 14 to 19 min on Wafer** | slower serving, not a defect; a task that needs more than about 100 calls reaches the 90-minute limit |
| Cache behaviour | first half of the run warm (time to first token 0.5 to 3 s), then misses once both contexts exceed about 60k tokens (about 120k warm in total); late calls add 15 to 30 s of prefill | two growing conversations against a warm capacity of about 120k tokens; the shared static prefix (about 11k tokens) helps only a little |
| Two agents decoding together | per-stream speed stays about 27 tokens/s | measured: 55 tokens/s total with 2 streams |
| Failures | none expected beyond one-off retries | the risks are in section 5 |
| Outcome | both produce a PoC and patch (S1 to S3) is more likely than not, my weak prior about 55 to 65% | same model solved both in batch 7, but the scaffold (Codex instead of Claude Code), thinking handling and server differ; n is 2, so no conclusion about accuracy either way |
| Grading | a few minutes per task (S1 to S4 rebuild the project in fresh containers) | small projects; no ffmpeg-style tail |
| GPU time | about 2.5 h from deploy to undeploy | 25 min start, up to 95 min agent time, grading, test overhead |

**Largest uncertainty:** output tokens per call under Codex with thinking on. Section 4 of [[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]] assumed 1,000 (derived from batch 7). If real outputs are about 300 tokens, calls take about 12 s and a task could make 300 calls in 90 minutes; if they are about 3,000, calls take about 2 minutes and a task makes about 40. The pilot measures it for the first time.

## 4. What the pilot decides
| Observation | Decision it supports |
|---|---|
| Two agents finish or hit the limit with mean call time under about 60 s and no failures | the estimate for the 100-task run holds (one to two agents at a time, about 3 to 6 days); go on to choose a capacity upgrade (FP8 checkpoint, two GPUs, replicas) before it |
| Mean call time rises steeply once contexts pass 60k each | cache thrash confirmed on real agents; capacity must grow before 100 tasks, and two agents is the ceiling now |
| Median call time under about 15 s | outputs are shorter than assumed or warm capacity is larger than measured for real conversations; update the capacity analysis |
| Calls fail with 401 or 403 | token path or missing header; fix before anything else (plug-and-play item 1) |
| Calls fail with 400 | context above 262,144 tokens; check whether Codex compacts the history |

## 5. Failure signs to watch while it runs
401 or 403 (token expiry or header); 400 (context limit); streams cut by the idle (300 s) or total (900 s) caps; 5xx from a replica restart (one replica, no logs readable by us); the Mac refresher stopping (token lasts about one hour, refresh every 30 minutes); a task with no PoC at 90 minutes (log the last calls to tell slow from stuck).

## 6. What will be recorded
Per task: calls, prompt and output tokens per call and their growth, per-call seconds (median, p95, maximum), failed calls by status, time to first token if the shim logs it (otherwise call time minus output tokens divided by 28), stage times, outcome (S1 to S4), token totals against the caps, wall time, GPU time. Cached tokens are **not** reported by the endpoint (usage has no cached-token details), so caching is judged by call time, not by a counter.

## 7. Results (run 09:05 to 10:38 UTC, 2026-11-05)
Raw per-call data (no ids): `aws-vm-data/qwen-pilot/calls.csv` (169 rows: task, call number, seconds from task start, call seconds, prompt and output tokens, finish reason, reasoning chunks). Full artifacts and the shim log are on the study owner's Mac outside the repository (`spark/run-logs-20261105/`).

### 7.1 Outcome
| | md4c/arvo_31332 | igraph/arvo_29408 |
|---|---|---|
| S1 / S2 / S3 / S4 | pass / pass / pass / pass | pass / pass / pass / pass |
| Agent time | 1,190 s (19.8 min) | **5,400 s (the 90-minute limit was reached)** |
| Whole task (agent + grading) | 21.5 min (grading about 100 s) | 92.9 min (grading about 172 s) |
| Model calls | 58 | 111 |
| Prompt tokens, total / last call | 2.52M / 71k | 7.19M / 103k |
| Output tokens, total / mean / median per call | 27.0k / 465 / 256 | 105.3k / 949 / 286 |
| Seconds per call: median / p90 / max | 12 / 44 / 97 | 15 / 148 / 601 |
| Calls over 120 s | 0 | 14 (61% of call time, 52% of output tokens) |
| Calls that returned nothing | 0 | 2 (520 s and 601 s, section 7.3) |
| Batch 7 for comparison (Claude Code, OpenRouter) | 14.1 min, 51 requests | 18.6 min, 62 requests |
No call returned a non-200 status; the shim recorded no errors. No price exists for this model, so no dollar spend was recorded; total tokens 9.70M in, 132.3k out. The endpoint reports no cached tokens (`cache_read_tokens` is 0 in the results by construction).

### 7.2 Expectations against what happened
| Quantity | Expected | Observed | Verdict |
|---|---|---|---|
| Endpoint through the shim | works | worked first time; no user-project header needed | as expected |
| Calls per task | 50 to 100 | 58 and 111 | one inside, one just above |
| One call, median | 30 to 45 s | 12 s and 15 s | **too high**: most calls are short; the mean (20 s and 49 s) is pulled up by a heavy tail |
| Output tokens per call | about 1,000 (derived) | mean 465 and 949, median about 270 | mean confirmed for the longer task, but the distribution is skewed |
| Time per task | 40 to 90 min | 21.5 min and 92.9 min | md4c much faster, igraph at the limit |
| Cache | warm in the first half, misses after both pass 60k | warm throughout (section 7.4) | **better than expected**, but the two-large-contexts case did not occur |
| Failures | none beyond retries | none by status; 2 silent drops | minor surprise (section 7.3) |
| Outcome | both pass, weak prior 55 to 65% | both pass S1 to S4 | as hoped; n is 2, no conclusion about accuracy |
| Grading | a few minutes | 100 s and 172 s | as expected |
| GPU time | about 2.5 h | deployed 08:36, answering 09:02, tasks finished 10:38, undeployed 11:16 UTC (about 2 h 40 min from deploy start; about 2 h 15 min with the model serving) | as expected, plus 38 minutes idle after the tasks until undeploy |

### 7.3 New findings
1. **Most agent time is model time, but not all (corrected 2026-11-05).** Sum of call seconds as logged by the shim: 1,153 s of the 1,190 s agent time for md4c (97%) and 5,434 s of 5,400 s for igraph. The igraph sum is more than the wall time because the two abandoned calls (520 s and 601 s) overlap the retries that followed; without them the model time is 4,313 s, **80% of the agent time**. The rest is tool time and agent overhead: four gaps between calls of 121 to 317 s (about 890 s in total, long commands such as a fuzzer run) and small ones. The capacity model assumed 15 s of tool time per call ([[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]] section 4); that is too much for most calls and too little for the few long ones.
2. **Reasoning length is heavy-tailed and drives the time.** On igraph, 14 of 111 calls (13%) took 61% of the call time and produced 52% of the output tokens (3,000 to 6,700 tokens each, 2 to 4 minutes, almost all reasoning chunks). Decode stayed at about 25 to 28 tokens/s per stream, as measured before.
3. **Two calls were lost to silent thinking: 1,121 s, 21% of igraph's 90 minutes.** One ended at 520 s with `BrokenPipeError` (the client side hung up), one at 601 s with 14,901 reasoning chunks and no answer. The shim forwards no event while the model only reasons, so the agent (Codex) sees silence; both calls were longer than anything that completed (the longest completed call was 255 s). **Cause not confirmed**: candidates are a client idle timeout of about 300 s, and a 10-minute limit on the Vertex request. The agent recovered and went on to pass, but it would have had 20% more time. Candidate fixes, none tried: forward reasoning as stream events (or keep-alive comments) so the client sees activity; limit the reasoning length (maximum tokens, reasoning effort); check the endpoint's request timeout.
4. **The agent used its full time on igraph and still passed.** The files in the output folder at the cutoff passed all four stages; when they first appeared is not determined from the data kept. Whether igraph was refining a valid answer or only just found it is therefore unknown.

### 7.4 Cache, judged by call time
The endpoint does not report cached tokens, so caching is inferred from the time a call spends outside generating its output: call seconds minus output tokens divided by 27.5 tokens/s.
| Group | Calls | Median | p90 |
|---|---|---|---|
| md4c, all calls | 58 | 2.5 s | 7.0 s (16 calls with prompts of 60k and more: median 3.0 s) |
| igraph while md4c was running | 31 | 2.5 s | not computed |
| igraph after md4c finished | 78 | 2.8 s | not computed |
| igraph, prompts 60k and over | 68 | 2.7 s | 10.5 s |
A full cache miss on a 60 to 90k prompt would add 18 to 28 s of prefill (at 3,270 tokens/s), so most calls were served warm, up to a prompt of 103k tokens. **What this does not test:** two agents both holding more than 60k tokens. md4c ended at 09:27 with a 71k prompt while igraph's prompt was still under about 45k, so the combined context stayed near or below the 120k warm capacity. The thrash predicted in section 3 would show only with two long-running tasks overlapping late.

### 7.5 What it means
- The setup works end to end (registry route, shim, token relay, endpoint, Codex, grading) with no changes during the run. Plug-and-play side: [[wiki/syntheses/plug-and-play-model-support]].
- Per task, agent time ranges from 20 minutes to the full 90; at one to two agents this keeps the earlier estimate for 100 random tasks of days, not hours (rough: if the average task takes 60 of its 90 minutes, 100 tasks are about 100 agent-hours, so about 50 hours with two agents at best, before grading). Two easy tasks cannot estimate this; the DeepSeek run's median was 165 calls per task.
- The biggest lever on Qwen speed is the length of reasoning per call, then decode speed (MTP speculative decoding, not tried), then the dropped-call fix; more warm capacity matters only with more concurrent agents.
- Still open: behaviour of two long tasks at once, the cause of the dropped calls, accuracy over many tasks.

### 7.6 Bottleneck check for two tasks at the same time
| Resource | Evidence | Verdict |
|---|---|---|
| Endpoint, decode | igraph decode speed for calls of 1,000+ output tokens: 25.4 tokens/s while md4c ran (6 calls), 25.9 alone (20 calls); md4c 25.5 | no slowdown from the second agent |
| Endpoint, cache and prefill | time outside generating output: median 2.5 s with two tasks running, 2.8 s alone (section 7.4); calls per minute for igraph 1.49 with md4c, 1.18 alone (later calls are longer) | none seen; the overlap (09:06 to 09:27) held igraph under about 45k tokens, so combined context stayed near the warm capacity, not above it |
| Endpoint, queueing and GPU use | no metrics or logs are readable (403) | **unknown** |
| Head VM, memory | used 3.9 to 5.2 GB of about 62 GB for the whole run | no |
| Head VM, CPU | load average (16 vCPUs): under 4 during the overlap; 8.0 from about 10:00 to 10:10 and 12 to 16.5 from 10:10 to 10:25, while igraph ran alone | **saturated late in the run by the agent's own commands** (not by two tasks); model calls are remote so they were not slowed, the commands were |
| Shim, token path | no 401, 403 or non-200 status; the token never aged past about 5 minutes | no |
| Agent time limit | igraph used all 90 minutes | yes, from long reasoning (61% of call time in 14 calls) and the two lost calls (21%), not from running two tasks |
So two tasks did not interfere with each other at the endpoint; the delays came from reasoning length, silent streams and long tool commands. What remains untested is two long contexts at the same time. Plan for five: [[wiki/syntheses/qwen27b-serving-capacity-analysis]] and section 7.5.

### 7.7 Speed against Qwen3.8-27B on OpenRouter (Wafer), the same two tasks (added 2026-11-05)
Both are Qwen3.8-27B and both ran two tasks in parallel, but the **harness differs** (batch 7: Claude Code 2.1.91; pilot: Codex through the translating shim), so the number of calls and the search path differ. Batch 7 numbers from [[wiki/syntheses/igraph-arvo-29408/run-14-qwen3-8-27b-e2e]] and [[wiki/syntheses/md4c-arvo-31332/run-14-qwen3-8-27b-e2e]]; there is no direct decode measurement of the Wafer route, so its speed is a bound derived from per-request time.
| | OpenRouter / Wafer, md4c | Vertex pilot, md4c | OpenRouter / Wafer, igraph | Vertex pilot, igraph |
|---|---|---|---|---|
| Agent time | 684 s (11.4 min) | 1,190 s (19.8 min) | 798 s (13.3 min) | 5,400 s (limit) |
| Requests | 51 | 58 | 62 | 111 |
| Agent seconds per request (tool time included) | 13.4 | 20.5 | 12.9 | **48.6** (39.3 without the two lost calls) |
| Output tokens, total / per request | 21.9k / 429 | 27.0k / 465 | 58k / 935 | 105.3k / 949 |
| Output tokens per agent second | 32 | 22.7 | 72.7 | 19.5 |
- Output per request is about the same on both routes (429 vs 465, 935 vs 949), so the difference is speed, not how much the model writes.
- Per request the pilot is **1.5x slower on md4c and 3.8x slower on igraph** (3.0x without the lost calls); the whole igraph task took 6.8x longer (3.8x per request times 1.8x more requests).
- **Decode bound:** over both tasks, Wafer produced 79.9k output tokens in 1,482 agent seconds, at least **54 tokens/s** averaged over everything the agent did (igraph alone at least 73); the pilot generates at 25 to 28 tokens/s per stream (measured), 20 per agent second. Because tool time and prompt processing are inside the Wafer figure, its real decode speed is higher: at least about 2x, probably more.
- **Why the self-hosted route is limited:** one A100 80GB reads about 54 GB of bf16 weights for every generated token; at about 2 TB/s the ceiling is about 37 tokens/s, and the measured 28 is about three quarters of it. To get near Wafer's figure the model must read fewer bytes per token (FP8 weights, about 27 GB) or spread them over more GPUs (two GPUs with tensor parallelism), or generate several tokens per step (MTP, not tried). Whether Wafer serves a different precision or hardware is not known to us.
- Caching is similar: Wafer's cache share was 92 to 95% on these two tasks; the pilot's calls were mostly warm (section 7.4).
