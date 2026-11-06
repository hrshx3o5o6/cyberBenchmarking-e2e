---
type: synthesis
created: 2026-11-05
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [qwen, qwen3-8-27b, architecture, gated-deltanet, linear-attention, kv-cache, serving, living-document]
---
# Qwen3.8-27B architecture, and what it means for serving (2026-11-05)

Why this page exists: every serving number we measured ([[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]], [[wiki/syntheses/qwen-capacity-levers-test]]) follows from how this model is built. Numbers are from the model's published `config.json` (revision pinned in the redeploy kit; read 2026-11-05). Arithmetic marked *estimate* is mine, not a measurement.

## 1. Layout
```
tokens (vocabulary 248,320) -> embedding (width 5,120)
  -> 16 blocks of [ GDN layer, GDN layer, GDN layer, full-attention layer ]      = 64 layers (48 GDN + 16 attention)
  -> final norm -> output layer (separate from the embedding) -> next-token scores
every layer: RMSNorm -> token mixer -> add back;  RMSNorm -> MLP (SwiGLU, 17,408 wide, dense, no experts) -> add back
also: a 27-layer vision encoder (images, video; unused by us) and 1 extra multi-token-prediction (MTP) layer (not enabled)
```
Class `Qwen3_5ForConditionalGeneration`, bf16, native context 262,144 tokens, `full_attention_interval` 4 (a 3 : 1 mix).

## 2. The two token mixers
| | Full attention (16 layers) | Gated DeltaNet, "GDN" (48 layers) |
|---|---|---|
| What it keeps per sequence | a key and a value for every earlier token (the KV cache); grows with length | one fixed-size memory matrix per head; the same size at 1k or 200k tokens |
| Heads | 24 query heads, **4 key/value heads** (6 queries share each), 256 dimensions per head | 16 key heads, 48 value heads, 128 dimensions each, plus a short causal convolution (width 4) |
| Details | partial rotary position (25% of each head, `rope_theta` 10,000,000, interleaved multi-axis positions for images), a learned gate on the output, no bias | per token: decay part of the old memory, then write a correction along the new key (the "delta rule"); learned gates set forgetting and write strength; state kept in float32 |
| Strength | exact recall of anything in context (the 90k-token retrieval test passed 6 of 6) | cheap: linear time, no growing cache |
Why mix them: with attention in all 64 layers the KV cache would be 256 KiB per token; with it in only 16 it is 64 KiB per token (16 layers x 2 x 4 heads x 256 x 2 bytes), which is what makes 262k tokens practical on one GPU.

## 3. Size (estimate from the config)
| Part | Parameters |
|---|---|
| 64 MLPs (3 x 5,120 x 17,408 each) | about 17.1B |
| 48 GDN layers (about 116M each) | about 5.6B |
| 16 attention layers (about 105M each) | about 1.7B |
| Embedding plus separate output layer (2 x 248,320 x 5,120) | about 2.5B |
| **Total language model** | **about 26.9B, about 54 GB in bf16** (plus about 0.4B of vision tower, about 0.8 GB idle) |

## 4. Serving numbers this explains
| Measured | Why |
|---|---|
| 64 KiB of KV per token | only 16 layers cache keys and values |
| Decode about 28 tokens/s per stream; ceiling about 37 | each generated token reads all about 54 GB of weights; an A100 moves about 2 TB/s |
| Prefill about 3,270 tokens/s | about 54 GFLOP per token x 3,270 is about 177 TFLOPS of the A100's 312 |
| Decode total scales almost linearly to 8 streams | the weight read is shared by the whole batch (it grows only with the KV read) |
| Few key/value heads (4) | cheap KV, but tensor parallelism can split the KV cache at most 4 ways; beyond 4 GPUs the keys and values are duplicated, so the cache grows less than in proportion (estimate: about 1.6x for 8 GPUs against 4) |

## 5. Why the warm cache was only about 120k tokens (hypothesis, fits the data, not verified)
Reusing a cached prefix needs the GDN memory as it was at that point, not only the KV. One saved point costs, per sequence:
- GDN state: 48 layers x 48 value heads x 128 x 128 x 4 bytes = **144 MiB** (*estimate*)
- convolution state: 48 layers x 10,240 channels x 3 x 2 bytes = about 2.8 MiB
- together about **147 MiB, the KV of about 2,300 tokens** (64 KiB each).
vLLM keeps attention pages and these state pages in one pool ([LMCache recipe for this model family](https://docs.lmcache.ai/recipes/qwen3_5.html)). If a state snapshot is saved about every 2k tokens, it costs about as much as the KV it sits next to, so caching is roughly half as efficient as the KV arithmetic says. Three observations fit:
1. measured warm capacity about **0.45x** the arithmetic (about 120k against 250k to 300k tokens);
2. 8-bit KV shrinks only the KV half, so about **1.3x** is expected; measured +25% (30k prompts) and +50% (59k prompts), and the model's vLLM recipe reports +19% on another GPU ([recipes.vllm.ai](https://recipes.vllm.ai/Qwen/Qwen3.8-27B));
3. capping simultaneous sequences (`--max-num-seqs=16`) changed nothing, because the cost is per saved prefix, not per live request.
The save interval is not known. What would test it: the server's block size and cache log lines (not readable through our endpoint), or flags that change the state's size or the snapshot spacing (state precision, cache block size), listed in [[wiki/syntheses/qwen-scaling-plan]].

## 6. Not used
Vision tower (loaded, idle), MTP head (could speed decode through speculative decoding; not enabled, unknown whether this build supports it for this architecture), the 1M-token YaRN mode.
