---
type: synthesis
created: 2026-11-05
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [qwen, qwen3-8-27b, vertex, scaling, concurrency, kv-cache, capacity, plan, living-document]
---
# Qwen3.8-27B on Vertex: findings so far and how to scale (2026-11-05)

Summary of the Qwen serving work, in order of the evidence: [[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]] (caching, CUDA graphs, 2026-11-04), [[wiki/syntheses/qwen-two-task-pilot]] (two real tasks), [[wiki/syntheses/qwen-capacity-levers-test]] (cap on sequences, 8-bit KV, six real tasks). Why the numbers are what they are: [[wiki/syntheses/qwen3-8-27b-architecture]]. How to change and redeploy the endpoint: [[wiki/syntheses/qwen-endpoint-redeploy-runbook]]. Ids are not recorded here. **All scale-up figures below are estimates from measured numbers, not tested results** (the tested ones are marked).

## 1. Findings in simple terms
- An agent re-sends its whole conversation on every call and it grows to 60 to 100k tokens. If the GPU still holds it ("warm cache") a call costs 0.5 to 2 s of reading; if not, about 20 s per 60k tokens. **The limit is how many conversations stay warm at once, not generation speed.**
- Warm capacity on one A100 80GB: about **120k tokens** with caching (baseline and with a cap of 16 sequences), about **150k to 177k** with an 8-bit KV cache.
- **Tasks at once, measured:** probes (agents calling back to back, 49k start, +3k per turn): 2 agents clean, 3 clean only with 8-bit KV (later calls 6.9 s, max 35 s), 4 collapse (93 s). Real tasks (44 to 73k tokens each): 2 to 3 clean up to about 100k of combined context; 4 to 5 tail of 8 to 50 s; 6 collapse (calls of 300 to 600 s); after cutting 6 to 3 the tail stayed at 20 to 30 s (combined context 188k, slightly over the warm limit). **Rule that fits: the combined context of the running tasks must stay under the warm capacity (about 177k with 8-bit KV).**
- Speed: one stream decodes at 28 tokens/s (9 before CUDA graphs; ceiling about 37 on one A100); total scales to 196 to 210 tokens/s at 8 streams. OpenRouter/Wafer was at least about 2x faster per request on the same two tasks ([[wiki/syntheses/qwen-two-task-pilot]] section 7.7).
- Quality: retrieval at 90k tokens 6 of 6 in both arms; two real tasks passed S1 to S4 at full precision; under 8-bit (six real tasks, run through the collapse): igraph passed S1 to S4, md4c S1 to S3 with S4 failing, boringssl no PoC at the limit, three stopped by me; nothing broke, but accuracy under 8-bit is **not answered** ([[wiki/syntheses/qwen-capacity-levers-test]] section 7.3).
- Two infrastructure findings: the model can reason silently for minutes and the call is cut at 10 minutes (lost 21% of one task's time); after a redeploy the head's resolver kept a stale endpoint address ([[wiki/syntheses/plug-and-play-model-support]] section 5).

## 2. The ladder of ways to get more room (cheapest first)
Capacity in tokens is relative to the measured baseline of 120k; tasks assume 60k each.
| Step | Warm cache (estimate) | Tasks at once | Cost | Catch |
|---|---|---|---|---|
| Now: 8-bit KV | 177k (measured) | 2 to 3 | 1 GPU | |
| Software only: admission control (start a task only if live contexts fit), cap or compact context at about 45k, short tasks first | same memory, smaller tasks | 3 to 4 | none | caps change agent behaviour |
| Two flags to test (state precision in bf16; larger cache blocks) | up to +40% or more if the state-snapshot hypothesis of [[wiki/syntheses/qwen3-8-27b-architecture]] section 5 is right | 4 to 6 | 1 GPU, about 3 GPU-hours | unverified; state precision may change outputs slightly |
| FP8 weights (`Qwen/Qwen3.8-27B-FP8`, frees about 27 GB) | about 390k | about 6 | 1 GPU | a different checkpoint than the paper's: protocol decision |
| 2 GPUs, tensor parallelism, bf16 weights | about 500k (650k with 8-bit KV) | 8 to 10 | 2 GPUs | 2-GPU machine quota unknown; also faster decode |
| 4 GPUs, tensor parallelism | about 1.3M (1.7M with 8-bit KV) | 16 to 20 | 4 GPUs | 4-GPU quota; untested on this model |
Notes:
- Past 4 GPUs the cache grows less than in proportion (corrected 2026-11-05; earlier text said "almost none"): the KV cache cannot split beyond 4 ways (4 key/value heads), so each extra GPU keeps duplicate copies of the keys and values, while the weights and the GDN state still split. Estimate: 8 GPUs hold about 1.6x the warm tokens of 4 (about 2.1M against 1.3M), not 2x.
- One endpoint split over GPUs beats separate copies: each copy duplicates the 54 GB of weights (2 copies on 2 GPUs hold about 4 to 6 agents, tensor parallelism on the same 2 GPUs about 8 to 10), and Vertex does not keep a session on one replica, so copies would need routing by task in the shim.
- Beyond 16 tasks: several 4-GPU endpoints with the shim routing each task to one of them.

## 3. What 100 tasks would cost (about 63 minutes per task on average, estimate)
| Tasks at once | Hardware | Wall time | GPU-hours |
|---|---|---|---|
| 2 | 1 GPU (now) | about 52 h | 52 |
| 6 | 1 GPU, FP8 weights | about 17 h | 17 |
| 10 | 2 GPUs | about 10.5 h | 21 |
| 16 | 4 GPUs | about 6.6 h | 26 |
Scaling up cuts GPU-hours as well as time, because the weights stay loaded while more tasks share them. Not included: the grading tail and idle time.

## 4. Fixes outside the model server
| Fix | Why |
|---|---|
| service account on the head (no Mac token relay) | a 7 to 10 hour run cannot depend on a laptop; the login expired twice |
| forward stream activity (or keep-alives) while the model reasons, and cap reasoning length | silent calls cut at 10 minutes; reasoning-heavy calls were 13% of calls and 61% of call time |
| pin or re-resolve the endpoint name after a redeploy | stale address broke the first six-task launch |
| `--enable-prompt-tokens-details`, logs and metrics access | cached tokens and queueing are invisible today |
| admission control by live context | the rule that fits the data |
Slots, workers and quota are not the limit: 16 slots (head 4 + 2 workers x 6) fit the vCPU quota ([[wiki/syntheses/deepseek-100-task-run-report]] section 17 for the memory reasoning).

## 5. Order I would follow
1. A clean quality check of 8-bit KV: two or three tasks at a time over many tasks, against a full-precision run on the same list (the six-task run was confounded by the collapse).
2. Software fixes (no GPU).
3. Test the two cheap flags on one GPU (about 3 GPU-hours): if the hypothesis holds this may reach 5 to 6 tasks for free.
4. If short: 2-GPU tensor parallelism (bf16 weights, no protocol change), then 4 GPUs for 16.
5. Re-measure with the same tests after each step: `tools/qwen_endpoint_probe.py` (`residency`, `agents --counts ...`, `needle`) and a real-task ramp (`tools/qwen_ops/`), using the same baselines as [[wiki/syntheses/qwen-capacity-levers-test]] section 4.
