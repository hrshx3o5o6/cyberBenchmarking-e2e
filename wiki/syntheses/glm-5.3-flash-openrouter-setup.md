---
type: synthesis
created: 2026-11-09
updated: 2026-11-09
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [glm-5.3-flash, openrouter, z-ai, provider-pinning, shim, probe, registry, 100-task-rerun, living-document]
---
# GLM 5.3 Flash on OpenRouter: provider pin, probes, two shim fixes (2026-11-09)

Preparation for rerunning the 100 tasks of [[wiki/syntheses/deepseek-100-task-run-report]] (list, limits and settings in section 19 of that report) with GLM 5.3 Flash, graded with setup A of [[wiki/syntheses/grader-shared-images-experiment]]. Nothing of the 100-task run has started; this page records what was set up and tested on the head VM.

## 1. Why the provider is pinned
OpenRouter lists 41 endpoints for `z-ai/glm-5.3-flash`. By default each request goes to one of them chosen at random, weighted by price, throughput, latency and reliability; a failed call is retried on another. Follow-up calls stay on the same provider only while its prompt cache is warm (OpenRouter's provider-routing documentation). The endpoints differ in quantization (fp8 on Z.AI; fp4, nvfp4 or unknown elsewhere), context (a few only 262k), and cache-read price (about $0.01 to $0.05 per million). The Qwen study already showed the cache share depending only on the provider: [[wiki/syntheses/qwen-cache-investigation]].

Pinned to **Z.AI** (endpoint tag `z-ai/fp8`): fp8, 1,048,576 context, 131,072 maximum output, $0.15 fresh / $0.03 cached read / $0.50 output per million tokens, 100% uptime in the last 30 minutes when listed. Output and prices from OpenRouter's public endpoint listing, not from Z.ai's own page.

## 2. Registry entry
`glm-5.3-flash@openrouter` in `tools/models.toml` (on the VM, backup `models.toml.pre-glm-flash`): upstream `z-ai/glm-5.3-flash`, `api = "chat"` (Codex's Responses calls are translated to Chat Completions by the shim, as for DeepSeek; OpenRouter's own Responses endpoint was not tried), `provider_order = ["z-ai"]`, `allow_fallbacks = false`, prices above, `vetted = false` until a real Codex task has run through it.

## 3. Probes (direct calls to OpenRouter, pinned to z-ai; cost about one cent in total)
Data in `aws-vm-data/glm-flash/`.
| Test | Result |
|---|---|
| key and a tiny completion (`or_auth.json`) | accepted; the key has a credit limit set by the study owner and nothing spent before the probes; Z.AI answered; 33 of 36 completion tokens were reasoning (reasoning is always on) |
| tool calls (`or_tools.json`) | two parallel tool calls in one turn, both with valid JSON arguments; the final answer used both results; second call read 192 of 229 prompt tokens from cache |
| growing conversation, 10 turns (`or_cache.json`; system prompt about 4k tokens, each turn adds a tool call and a 700-word result, prompts 4.3k to 31.6k tokens) | provider Z.AI on every turn; cache share per turn: 0, 2% (turn 2), 71%, 77%, 82%, 84%, 86%, 88%, 89%, 90% (turn 10); 82% overall from turn 2; 10 calls cost $0.0099 |

Reading: the cache keeps reusing the whole growing prefix (cached tokens rise with the prompt, they do not stay at a fixed prefix as on Alibaba in the Qwen study). Short synthetic test; real agent traffic will show the real share.

## 4. Through the shim, as Codex calls it (`shim_glm_test2.json`)
Shim started with `start_shim.sh glm-5.3-flash@openrouter 5 2` (probe caps: 5 USD total, 2 per key). A Responses-API streaming exchange with two parallel tool calls and a follow-up: both arguments valid, final answer correct, the shim counted 2 requests, 0 errors, cache reads and a cost (about $0.00007) and **logged the provider per call (Z.AI)**. The probe shim was then stopped by its exact PID; the real run restarts it with its real caps.

## 5. Two gaps in our own shim, found and fixed on the VM (backups `*.pre-fallbacks`, `*.pre-provlog`; patch scripts in `aws-vm-data/glm-flash/`)
1. **The registry's `allow_fallbacks = false` never reached OpenRouter.** The shim hardcoded `"allow_fallbacks": True` whenever `PROVIDER_ORDER` was set, so a pin was only a first choice: on an error or rate limit OpenRouter would have moved the call to another provider (different quantization and cache), silently. The registry now exports `PROVIDER_ALLOW_FALLBACKS` (0 unless an entry opts in) and the shim sends it; unset keeps the old behaviour. This corrects the statement in [[wiki/syntheses/model-registry-design]] that fallback is off unless the entry opts in, which was only true on paper until today. Earlier OpenRouter runs through this shim (the Qwen batches used `wafer` with fallbacks allowed, by design) are unaffected.
2. **The shim did not record which provider answered.** It now writes `provider` into each call's log record (from the stream chunks), so the report can state that all calls were served by Z.AI. A failure under the pin now surfaces as an error (Codex retries it), not a switch.

The run itself and its observations: [[wiki/syntheses/glm-5.3-flash-100-task-run]].

## 6. Still to do before the 100 tasks (see the change list in chat of 2026-11-09)
- Harness patch for setup A (new validation path in `scripts/run_agent.py`, selected by a `validation_mode` setting, shipped through `scripts/patch_cybergym.py`), with the equivalence replay on the recorded DeepSeek pairs as its gate. Nothing written yet.
- Start the stopped `cybergym-proxy`, the Ray head and workers, prefetch images, shim with the real caps (10 USD per run as before).
- A real Codex task through the shim to set `vetted = true`.
- Estimated cost of the run at this price list: about $135 with DeepSeek's token volumes and cache share (706M fresh, 898M cached, 5.0M output), about $70 at a 90% cache share; GLM's own token counts are unknown.
