---
type: synthesis
created: 2026-10-13
updated: 2026-10-13
sources: ["[[sources/cybergym-e2e]]"]
tags: [prompt-cache, provider, qwen3.8-flash, qwen3.8-27b, investigation, openrouter]
---
# Why qwen3.8-flash barely hit the prompt cache, and what fixed it for qwen3.8-27b

**One line:** qwen3.8-flash is served only by **Alibaba** on OpenRouter, and Alibaba reuses only the **first few thousand tokens** of a growing agent conversation (the system prompt and tool list), not the accumulating history; changing where the cache markers sit does not help. qwen3.8-27b served by **Wafer** reuses the whole growing conversation (about 90%+). The real 27B batch confirmed it: **96.3% cache share**, against 19-40% for flash. This is a provider behaviour, not a harness fault, and it cannot be fixed for flash because there is no other provider for it.

## The observation
In [[wiki/syntheses/batch-3-summary]] qwen3.8-flash had a prompt-cache share of about 19-40% while glm, deepseek, kimi and minimax were above 90%. All ten flash runs were served by Alibaba (provider tag recorded in every trajectory). The flash price is $0.15/M fresh vs $0.016/M cached, so a low share inflates cost: flash cost $5.52 for ten runs.

## What OpenRouter offers
- `qwen/qwen3.8-flash`: two Alibaba endpoints only (`alibaba` and `alibaba/us-east-1`). No alternative.
- `qwen/qwen3.8-27b`: about 20 providers (Wafer, DekaLLM, Tenstorrent, Reka, Phala, Alibaba and others, with different prices and cache prices).

## Tests (direct calls to the OpenRouter Anthropic-format endpoint, provider pinned, synthetic text, run from the VM; cost not individually metered, well under $1 in total)
**Test 1: the same 6,000-token prompt twice, 4 seconds apart** (call 2 cache read / prompt size)
| Provider (model) | Result |
|---|---|
| alibaba, alibaba/us-east-1 (flash) | 6,033 / 6,048 and 6,036 / 6,051 read: **cached** |
| wafer, tenstorrent, dekallm, phala (27b) | about 6,016 of 6,050 read: **cached** |
| alibaba (27b) | call 1 reported 6,036 cache-creation tokens, call 2 read 6,036: cached (explicit cache) |
| reka (27b) | 4,704 read, 1,350 fresh: partly cached |
| chutes, parasail, akashml, novita, coreweave (27b) | **0 read**: no caching on this probe |
| near-ai (27b) | rate-limited, no result |

So a repeated identical prompt is cached by Alibaba. The problem only shows with a growing conversation.

**Test 2: a 14-turn agent-style conversation** (system prompt about 6k tokens, two tools, each turn adds an assistant tool call and a 700-word tool result; marker on the newest user block; with and without thinking blocks). Share of each request read from cache, turn 2 onward:
| Provider (model) | Overall | Per-turn trend |
|---|---|---|
| alibaba (flash) | 42% plain, 38% thinking | 83% on turn 2, falling to 28% by turn 14 |
| alibaba/us-east-1 (flash) | 40% / 39% | same decay (12-13 of 14 calls succeeded) |
| alibaba (27b) | 43% / 38% | same decay: the behaviour is the provider's, not the model's |
| wafer (27b) | **88% / 88%** | 86% from turn 3, rising to 94% |
| dekallm (27b) | **92% / 91%** | 81-86% rising to 94-95% |
| tenstorrent (27b) | 39% plain, 62% thinking | erratic, with runs of 0% |

The Alibaba curve is what a fixed cached prefix looks like: the amount read stays at about 6k tokens while the conversation grows, so the share shrinks. That matches the 19-40% in the real flash runs.

**Test 3: does marker placement matter?** 12 turns with thinking; marker on the last user block, the last two, the last three, or none:
| Provider | last | last 2 | last 3 | none |
|---|---|---|---|---|
| alibaba (flash) | 40% | 39% | 40% | 41% |
| wafer (27b) | 91% | 91% | 87% | 89% |

On Alibaba every variant gives the same result (even with no message markers), so the shim could not repair it by adding or moving `cache_control` blocks. Wafer caches regardless of markers (prefix caching on its side). Some Alibaba calls failed in the longer runs (7 of 12 succeeded in the first variant); the reason was not investigated.

## The real batch
[[wiki/syntheses/batch-7-summary]]: qwen3.8-27b with `provider.order = ["wafer"]` (fallbacks allowed). Wafer is the provider on every recorded assistant message except one (a Tenstorrent fallback in the igraph e2e run). Cache share **96.3% overall**, 77-98% per run, matching test 2's Wafer curve. 

## Conclusions
1. The low cache share was **Alibaba's behaviour with growing conversations**, reproducible without our harness, independent of marker placement and of model (flash and 27b both show it on Alibaba).
2. For flash there is **nothing to switch to**; the cost penalty stays. To compare Qwen models on equal terms one would need either Alibaba for both (27B on Alibaba would also hit about 40%) or a cache-capable provider for both (not available for flash).
3. For 27B, **pinning a cache-capable provider** is cheap and effective, but it is a setup change versus batches 1-6, which used default routing. The kimi runs alternated providers (Together/Wafer) and still reached 95-97%, so default routing can be fine when the mix is all cache-capable.
4. Do not over-read the dollar effect: flash's cache price is about one ninth of its fresh price, 27B's about one half, so caching mattered much more for flash's bill. At 27B's prices, output tokens are 56% of the bill.

## What is not known
- Whether Alibaba's behaviour is its explicit-cache design, a lookback limit, or something else (OpenRouter's translation of `cache_control` was not inspected; the probe used synthetic text).
- Whether other conversation shapes (longer idle gaps, much larger tool results, other thinking formats) change Alibaba's result.
- Why Alibaba calls failed in some test runs.
- Whether nemotron's 0% cache share and its tool-call format failures ([[wiki/syntheses/nemotron-tool-call-format-failures]]) have the same kind of provider cause; it was not tested.

Back to: [[wiki/syntheses/batch-7-summary]] · [[wiki/syntheses/batch-3-summary]]
