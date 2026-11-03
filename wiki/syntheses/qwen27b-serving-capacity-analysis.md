---
type: synthesis
created: 2026-11-03
updated: 2026-11-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [qwen3-8-27b, serving, vllm, capacity, context-window, bottlenecks, vertex, analysis, estimates]
---
# Serving Qwen3.8-27B ourselves: context needs, capacity and bottlenecks

Companion to [[wiki/syntheses/vertex-qwen27b-endpoint-check]] (what the endpoint is and why it cannot run the benchmark yet) and [[wiki/syntheses/qwen-100-task-study-protocol]] (the study this feeds). **Measurements** below come from our earlier run logs; **estimates** are arithmetic from the model configuration and public hardware figures and must be replaced by a load test before the study.

## 1. What the earlier runs needed (measured)
Source: the metering shim's log of the earlier Qwen3.8-27B batch (Claude Code harness through OpenRouter; 9 runs with model calls, 1,190 successful calls, patch-only and e2e mixed, five tasks). Context per call = fresh input plus cache-read input.
| Statistic | Tokens |
|---|---|
| Median call | about 85,000 |
| 90th percentile | about 153,000 |
| 99th percentile | about 165,000 |
| Largest call | 171,932 |
| Calls over 2,048 | 1,187 of 1,193 (99.5%) |
| Calls over 32,768 | 1,056 (88%) |
| Calls over 65,536 | 734 (62%) |
| Calls over 131,072 | 280 (23%) |
| Per run | mean | median | range |
|---|---|---|---|
| Input tokens (fresh plus cache reads) | about 11.7 million | about 5.6 million | 0.66 to 52.8 million |
| of which fresh | about 0.43 million | | 0.03 to 1.4 million |
| Output tokens | about 136,000 | about 46,000 | 9,000 to 610,000 |
| Model calls | about 132 | 73 | 20 to 482 |
About 96% of input was served from the provider's cache. A different run profile exists for Codex: in a Study-2 run (another model, endpoint capped at 131,072 tokens) Codex calls had a median of about 49,000, a 90th percentile of about 115,000 and a maximum of 131,018, just under that cap, so the cap probably shaped it. We have no Codex profile for Qwen3.8-27B beyond one short plumbing run.

## 2. Memory arithmetic (estimate)
Model configuration (public): 64 layers, of which 16 use full attention (the other 48 use linear attention with a small fixed state), 4 key/value heads of 256 dimensions, bf16, native maximum 262,144 tokens.
- Cache per token: 2 x 16 layers x 4 heads x 256 x 2 bytes, about 64 KB. A 131,072-token conversation needs about 8 GB, a 262,144-token one about 16 GB.
- One A100 80GB at 90% use gives 72 GB; the weights take about 54 GB; about 12 to 16 GB is left for cache: roughly 200,000 to 250,000 tokens in total across all conversations in bf16, about twice that with an 8-bit cache.
- Consequence at the 85K median context: about 3 concurrent agents in bf16, 5 or 6 with an 8-bit cache. vLLM's own start-up line for maximum concurrency should replace this guess.

## 3. Bottlenecks (estimates, in order of danger)
1. **Output speed.** Each generated token reads all the weights (about 54 GB) from memory; an A100 moves about 2 TB/s, so roughly 25 to 35 tokens per second for one agent. `--enforce-eager` costs perhaps another 20 to 40 percent. At 25 tokens per second the median run's output takes about 30 minutes and the mean about 90 minutes: the 90-minute limit can be hit by generation speed alone. For 100 e2e tasks the output is about 4.6 to 13.6 million tokens; at an aggregate 100 to 200 tokens per second that is roughly 6 to 38 hours of generation. Agents share the GPU, so concurrency raises aggregate speed only up to what the cache memory allows.
2. **Cache memory** limits concurrent agents (section 2); beyond it requests queue or saved prefixes are dropped and recomputed.
3. **Prompt processing.** Roughly 2,000 to 3,000 prompt tokens per second: a cold 100K-token prompt takes 35 to 50 seconds. Agents resend the whole history every call, so prefix caching is essential (without it a 132-call run would spend over an hour re-reading its own history), and with several agents the cached prefixes compete for the same cache memory.
4. **One replica, no safety net.** A crash or out-of-memory error at long context takes it down for the minutes needed to re-download the weights; tasks in flight fail; no scaling on demand.
5. **Limits of a shared endpoint:** a per-request time limit and a request-size limit probably apply (figures unknown; 170K tokens is about 0.7 MB of JSON), a per-project request quota may apply, and **streaming on this self-deployed endpoint is untested** (Codex needs it; the managed DeepSeek model streamed fine).
6. **Distance:** the endpoint is in Singapore and the shim in Virginia: about a quarter of a second per call, small, but a slow first token must not trip our timeouts (the shim waits up to 600 seconds of silence).
7. **Our side:** without a concurrency limit, 10 slots would flood one GPU and everything would time out together. The registry has a per-route `max_concurrent` field, but the shim does not enforce it yet. Codex also retries slow calls, adding load.

## 4. What to ask for
- **Hardware:** an H100 (about twice the memory bandwidth), or two GPUs per replica (`--tensor-parallel-size=2`: double the bandwidth and cache), or several replicas (agents are independent, so replicas scale almost linearly).
- **Settings:** a context of at least 131,072 tokens (the minimum; 23% of earlier calls were larger, and 262,144 allows only about one agent at a time), prefix caching on, an 8-bit cache, `--enforce-eager` removed, tool-call and reasoning parsers (names from the model's documentation).

## 5. What to measure before the study (load test)
Tokens per second with 1, 2, 4 and 8 concurrent agents; time to first token for a 100K-token prompt, cold and cached; where timeouts begin; the cache hit rate; memory headroom; whether streaming works through the endpoint for minutes at a time; the endpoint's request time and size limits. Then size the study (replicas, concurrency, task count, time) from the numbers.
