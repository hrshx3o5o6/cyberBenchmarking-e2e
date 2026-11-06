---
type: synthesis
created: 2026-11-05
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [qwen, qwen3-8-27b, vertex, vllm, kv-cache, fp8, max-num-seqs, capacity, concurrency, test-plan, living-document]
---
# Qwen3.8-27B: more warm cache and more concurrent agents on one A100 (test plan, 2026-11-05)

**Status: done (2026-11-05); expectations (sections 2 and 5) were written before the tests and are unchanged, results are in section 7.** Question from the study owner: what happens if the KV cache is stored in 8 bits, and how many tasks can run at the same time. Where we stand: [[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]] (warm cache about 120k tokens, 1 to 2 agents), [[wiki/syntheses/qwen-two-task-pilot]] (2 agents ran cleanly). Ids are not recorded here.

Related: scaling options and estimates in [[wiki/syntheses/qwen-scaling-plan]]; how each configuration was deployed in [[wiki/syntheses/qwen-endpoint-redeploy-runbook]]; the model's layout in [[wiki/syntheses/qwen3-8-27b-architecture]].

## 1. What the documentation says (searched 2026-11-05)
- Only 16 of the model's 64 layers keep a KV cache; the other 48 are linear attention (Gated DeltaNet) with a fixed-size recurrent state per sequence. vLLM keeps both kinds of memory in **one pool with equal page size**, and each decoding sequence needs its own state block ([LMCache recipe for the Qwen3.5 / 3.6 / 3.8 family](https://docs.lmcache.ai/recipes/qwen3_5.html), which also calls vLLM's prefix caching for these models in "align" mode experimental).
- The vLLM recipe for this model ([recipes.vllm.ai](https://recipes.vllm.ai/Qwen/Qwen3.8-27B)) reports on one RTX 5090: `--kv-cache-dtype fp8` gave 91,022 tokens against 76,458 with bf16 (**+19%, not 2x**), and adding `--max-num-seqs 8` raised the pool to 152,917 tokens. It calls fp8 KV "a choice here, not a requirement". Different GPU and settings from ours, so only a pointer.
- FP8 KV support on an Ampere GPU such as the A100 is **not confirmed** in the vLLM documentation we could reach (the FlashInfer backend lists fp8 KV dtypes; [vLLM config docs](https://docs.vllm.ai/en/v0.17.0/api/vllm/config/)); the deployment itself will show whether the server accepts it.
- One unofficial write-up reports that `--mamba-ssm-cache-dtype bfloat16` improved prefix-cache hits on one GPU; not used here.

## 2. Hypothesis
The measured 120k warm tokens (about 7.5 GiB at 64 KiB per token) is far below what the memory arithmetic allows (about 21 GiB after weights, section 5 of the capacity page), so more than half of the cache budget is probably reserved for per-sequence state because the server allows many simultaneous sequences (`--max-num-seqs` is not set in our deployment, so vLLM's default, likely several hundred, applies). Lowering it to what we need (16) may free a large share. If that holds, **8-bit KV is the smaller lever** (it only shrinks the 16 attention layers' share), which the recipe's +19% also suggests. This is a hypothesis; the test decides.

**Order note (2026-11-05):** the owner asked to test 8-bit first; arm 1 was already deploying and a deployment cannot be cancelled (the operation is not cancellable), so arm 1 is measured while it is up and arm 2 follows by a stop and start.

## 3. Arms (same endpoint, same procedure as the earlier changes: a new model record per argument list, about 25 minutes to start)
| Arm | Serving arguments (change against the previous arm) | Accuracy risk |
|---|---|---|
| Baseline (measured 2026-11-04) | prefix caching, CUDA graphs (no `--enforce-eager`), no `--max-num-seqs` | none |
| 1 | + `--max-num-seqs=16` | none (same numerics) |
| 2 | arm 1 + `--kv-cache-dtype=fp8` (run in any case: the study owner wants the 8-bit measurement; it shows what 8-bit adds on top of the cap) | lossy: default scales, long contexts |

## 4. Tests per arm (tool: `tools/qwen_endpoint_probe.py`) and baselines
| Test | Command | Baseline (bf16 KV, no cap) |
|---|---|---|
| Warm capacity | `residency --tokens 30000 --count 20` and `--tokens 59000 --count 12` | 4 prompts of 30k, 2 of 59k |
| Decode, 1 / 2 / 4 / 8 streams | `decode` | 28.3 / 55 / 108 / 210 tokens/s |
| Concurrent agents | `agents --counts 2 3 4 5 6 8 --turns 10` (50k start, +3k per turn) | 2 agents: later calls 4.2 s (max 16 s); 4 agents: 76 s |
| Long-context retrieval (quality) | `needle --tokens 90000 --trials 6` | none yet (absolute score; compare arms) |
| Real tasks | 4 tasks at once from the pilot set and the 100-task list, Codex through the shim (head has 4 slots) | pilot: 2 tasks, both S1 to S4 |

## 5. Expectations (written before running)
| Quantity | Arm 1 | Arm 2 (on top) |
|---|---|---|
| Starts and serves | yes | probably; the A100 attention backend may refuse or slow down fp8 KV (then the arm is dropped) |
| Warm capacity | 1.5x to 4x (about 180k to 480k tokens), wide because the default is unknown | +20% to +100% on top |
| Agents with later calls under about 5 s (2-minute test, 80k contexts) | 3 to 6 | 4 to 8 |
| Decode per stream | unchanged (about 28) | unchanged or slightly slower (dequantisation) |
| Needle retrieval | same as baseline (not measured yet) | the question: expect no loss at 90k, a loss would show as misses in the 90% position |

## 6. Decision rules
- Arm 1 reaches 5 agents with later calls under 5 s: adopt it, skip fp8 KV for the study (no accuracy question), then run real tasks.
- Arm 1 falls short: run arm 2; adopt it only if the needle score matches arm 1 and the real-task pass behaviour does not change; record it as a deviation from the plain model.
- Neither reaches 5: the remaining levers are FP8 weights, two GPUs with tensor parallelism (the KV cache splits at most 4 ways, so beyond 4 GPUs the cache grows less than in proportion; see [[wiki/syntheses/qwen-scaling-plan]] section 2) or fewer concurrent agents ([[wiki/syntheses/plug-and-play-model-support]] section 4 for the platform side).

## 7. Results
### 7.1 Arm 1: `--max-num-seqs=16` (deployed 12:56 UTC, tested 12:57 to 13:24, then replaced by arm 2)
| Test | Arm 1 | Baseline (2026-11-04) | Verdict |
|---|---|---|---|
| Warm prompts of 30k (cold 9.8 s each) | **4** (about 120k tokens) | 4 | no change |
| Warm prompts of 59k (cold 20.7 s each) | **2** (about 118k tokens) | 2 | no change |
| Time to first token on a warm hit | 1.17 to 1.19 s (30k), 1.49 to 1.51 s (59k) | 0.46 to 0.52 s (30k), 0.61 to 0.70 s (59k) | **slower by about 2.4x**; cause unknown (one deployment each, so variance cannot be excluded) |
| Decode tokens/s, 1 / 2 / 4 / 8 streams | 28.5 / 52.2 / 102.5 / 196.0 | 28.3 / 55.2 / 108.2 / 210.2 | same within a few percent |
| Tool call | finish `tool_calls` in 2.8 s | 2.1 s | works |
| Retrieval at 90k tokens (code hidden at 10%, 50%, 90%) | **6 of 6**; cold first token 35.4 s (about 2,550 tokens/s at this length) | not measured | quality baseline for bf16 KV |
| 2 agents (49k start, +3k per turn, 10 turns) | first call 25.6 s, later calls mean 3.9 s (max 16.2 s), wall 61 s | later mean 4.2 s (6 turns) | same |
| 3 agents, same pattern | first call 33.4 s, **later calls mean 64.9 s** (max 81.9 s), wall 644 s | not measured (4 agents: 76 s) | **collapse** |
| 4, 5, 6, 8 agents | not run | | stopped: 3 agents already collapsed; each further count would burn 10+ minutes of GPU for the same answer |
**Verdict: the cap on simultaneous sequences changed nothing.** Warm capacity stayed at about 120k tokens and the cliff stayed between 2 and 3 agents. The hypothesis of section 2 (cache budget eaten by reserved per-sequence state) is rejected for this flag value, which leaves the measured 120k against the arithmetic 250k to 300k unexplained. With the warm hit taking about 1.2 s instead of 0.5 s, the setting is not better than the baseline in any measured way.

### 7.2 Arm 2: arm 1 + `--kv-cache-dtype=fp8` (restart 13:24, serving 13:40, tested 13:40 to 14:11 UTC)
The server accepted the 8-bit setting on the A100 and started without a warning in the deployment output (about 16 minutes to start; the weights were probably cached on the node).
| Test | Arm 2 (8-bit KV) | Arm 1 (cap only) | Baseline (2026-11-04) | Verdict |
|---|---|---|---|---|
| Warm prompts of 30k | **5** (about 150k tokens; cold 10.0 s, warm 1.08 to 1.19 s) | 4 | 4 | +25% |
| Warm prompts of 59k | **3** (about 177k tokens; cold 22.1 to 22.3 s, warm 1.56 to 1.70 s) | 2 | 2 | **+50%** |
| Decode tokens/s, 1 / 2 / 4 / 8 streams | 28.5 / 52.2 / 102.6 / 195.3 | 28.5 / 52.2 / 102.5 / 196.0 | 28.3 / 55.2 / 108.2 / 210.2 | no effect |
| Retrieval at 90k tokens | **6 of 6**, the same six codes as arm 1; cold first token 38.6 to 38.7 s | 6 of 6; 35.3 to 35.5 s | | no loss seen; prefill about 9% slower (dequantisation) |
| Tool call | `tool_calls` in 2.8 s | 2.8 s | 2.1 s | works |
| 3 agents (49k start, +3k per turn, 10 turns) | first call 35.0 s, **later calls mean 6.9 s** (p90 5.9 s, max 35.3 s), wall 98 s | mean 64.9 s (collapse) | | **fits** (some late misses) |
| 4 agents, same pattern | first call 43.1 s, **later calls mean 93.0 s** (p90 114.6 s), wall 925 s | not run | 76 s (50k contexts, 6 turns) | **collapse** |
| 5, 6, 8 agents | not run | | | stopped at the first collapse |
**Verdict: 8-bit KV adds 25% to 50% warm capacity (the vLLM recipe's +19% on another GPU was the same order), which moves the back-to-back cliff from 2 agents to 3 and not to 4.** The cap of 16 sequences contributed nothing (arm 1 equals baseline), so the whole gain is the 8-bit cache. Cost: about 9% slower cold prefill; no loss of retrieval at 90k tokens (6 of 6, identical answers), but six trials at one length are a weak quality test; real-task behaviour is the stronger check (section 7.3). Still unexplained: the measured capacity is far below the arithmetic.

### 7.3 Real tasks on the 8-bit setup (ramp of 6)
**First attempt 14:14 UTC failed for an infrastructure reason, not the model:** every call returned 502 within 0.01 s (connection reset, SSL EOF) and two tasks were marked `benchmark_failed` before I stopped the driver (14:19). Cause: the endpoint's address had changed with the redeploys, and the head's resolver (the AWS VPC resolver, TTL about 2 minutes) kept returning an old address that no longer served this endpoint, while public resolvers (and the Mac) returned the working one; the same name gave different answers from different resolvers. A direct request from the Mac worked throughout. Fix without a system change: the shim was restarted with the name pinned to the working address (a `sitecustomize` that overrides the lookup for that one name, TLS still verifies the name), and the ramp was relaunched 14:21 UTC with a fresh work directory. This is a quirk of dedicated endpoints worth keeping: see [[wiki/syntheses/plug-and-play-model-support]] section 5.

Six tasks (igraph, md4c, opensc, boringssl, readstat, fluent-bit) on the head with 6 slots, one more started every 4 minutes from 14:21 UTC (fluent-bit, opensc, readstat, boringssl, md4c, igraph), Codex through the shim, 90-minute limit each. "Overhead" below is call seconds minus output tokens divided by 27.5 tokens/s (about the prefill wait); "live context" is the sum of the latest prompt of each task calling in that period.
| Minutes since 14:21 | Tasks calling | Live context | Overhead median / p90 | Calls over 120 s | Reading |
|---|---|---|---|---|---|
| 0 to 10 | 2 to 3 | 46 to 100k | 1.2 to 1.6 s / 2.8 to 4.8 s | 0 | clean |
| 10 to 20 | 4 to 5 | 164 to 202k | 2.6 to 4.4 s / 8 to 9 s | 2 per 5 min | tail starts |
| 20 to 30 | 6 | 252 to 291k | 3.4 to 5.2 s / 21 to 52 s | 2 to 6 per 5 min | degraded |
| 35 to 46 | 4 to 6 | 240 to 333k | **52 to 103 s / 190 to 310 s** | 2 to 7 per 5 min | **collapse** (calls of 300 to 600 s, many cut at the 10-minute limit) |
At minute 46 the six tasks held 44k to 73k tokens each (about 345k together), nearly twice the 177k that stays warm; every response was HTTP 200.

**Cut to three (15:09 UTC):** I stopped the three tasks with the largest contexts (fluent-bit, opensc, readstat; their partial work is lost and they show as failed with no PoC) to see whether the three smaller ones recover.
| Minutes after the cut | Tasks calling | Live context | Overhead median / p90 | Calls over 120 s |
|---|---|---|---|---|
| 0 to 3 | 5 (stopped ones finishing) | 291k | 3.5 s / 52 s | 3 |
| 3 to 6 | 3 | 151k | 5.6 s / 26 s | 3 |
| 6 to 9 | 2 | 112k | 6.8 s / 25 s | 2 |
| 9 to 12 | 3 | 181k | 3.1 s / 29 s | 2 |
| 12 to 15 | 3 | 188k | 3.1 s / 21 s | 1 |
Reading so far: three tasks with 60 to 64k tokens each are **workable but not clean** (median 3 s, but a tail of 20 to 30 s and some calls of several minutes, one of the three tasks mostly fast); two tasks were the clean regime in the earlier tests. Some of the slow calls are the silent-reasoning stalls found in the pilot (reasoning only, nothing sent, cut at 600 s), not cache misses; the overhead measure cannot separate them (stalled calls return no output tokens and are left out of it).

**Final outcomes** (the six tasks of the second attempt; the two first-attempt rows that died on DNS are not counted):
| Task | Agent time | Requests | Result | Reference |
|---|---|---|---|---|
| fluent-bit/arvo_26345 | 47.7 min | 51 | stopped by me at 15:09, no PoC yet | DeepSeek: passed S1 to S4 in 30.9 min, 92 requests |
| opensc/arvo_20131 | 43.6 min | 69 | stopped by me at 15:09, no PoC yet | DeepSeek: passed in 12.2 min, 68 requests |
| readstat/oss-fuzz_420198855 | 39.7 min | 43 | stopped by me at 15:09, no PoC yet | DeepSeek: passed in 23.8 min, 86 requests |
| boringssl/arvo_9808 | 90.0 min (limit) | 77 | **no PoC** | DeepSeek: passed in 23.6 min, 68 requests |
| md4c/arvo_31332 | 53.2 min | 90 | **S1 to S3 pass, S4 fail** (valid by the paper's rule, not the intended bug) | bf16 pilot: S1 to S4 in 19.8 min, 58 requests |
| igraph/arvo_29408 | 68.4 min | 94 | **S1 to S4 pass** | bf16 pilot: S1 to S4 at the 90-minute limit, 111 requests |
**Reading:** three tasks finished by themselves: one full pass, one valid but missing the intended bug, one with no PoC at the limit. This is **not a clean quality test of 8-bit KV**: the tasks ran through the collapse (calls of 300 to 600 s, about 70 s per call over the whole run for boringssl), the three stopped tasks never finished, and n is far too small. What it does show: nothing broke (all responses 200, tool calls valid, two of three finished tasks produced a valid PoC and patch), and no sign of garbled output. Whether 8-bit costs accuracy is **not answered**; a clean test needs two or three tasks at a time (the clean regime) over many tasks, compared with a full-precision run on the same list.

### 7.4 Bottom line
- Cap on sequences: no effect. 8-bit KV: +25% to +50% warm capacity, 3 agents instead of 2 in the probe; the real-task ramp collapsed at 6 and stayed tail-heavy at 3 once contexts passed about 60k each. The rule that fits: combined live context under the warm capacity (about 177k tokens with 8-bit KV).
- Costs of the experiment (2026-11-05, UTC): deployment started 12:28, undeployed 16:04 (3 h 36 min from deploy start; about 2 h 50 min serving); the probes took about 55 minutes in total, the real-task ramp from 14:14 to 16:03.
- Next steps and estimates: [[wiki/syntheses/qwen-scaling-plan]].

