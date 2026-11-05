---
type: synthesis
created: 2026-11-05
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [qwen, qwen3-8-27b, vertex, vllm, prefix-caching, cuda-graphs, benchmark, serving, a100, findings, living-document]
---
# Qwen3.8-27B on Vertex AI: what prefix caching and CUDA graphs changed (2026-11-04)

Three serving configurations of the same model on the same endpoint, measured the same way. Background and the access check: [[wiki/syntheses/vertex-qwen27b-endpoint-check]]. Capacity reasoning before these tests: [[wiki/syntheses/qwen27b-serving-capacity-analysis]]. Where the model fits in the registry: [[wiki/syntheses/model-registry-design]]. Ids (project, endpoint) are deliberately not recorded in this repository.

## 1. Summary
| | A. original (Amit's) | B. prefix caching on | C. prefix caching + CUDA graphs |
|---|---|---|---|
| Serving arguments | `--enforce-eager` | `--enforce-eager --enable-prefix-caching` | `--enable-prefix-caching` (no `--enforce-eager`) |
| Prefill speed (cache miss) | about 3,270 tokens/s | same | same (28.6k tokens in 8.6 to 10.4 s) |
| Same 28.6k-token prompt again, time to first token | 8.8 s (no effect) | **0.49 s** | **0.49 s** |
| Shared 28.5k prefix, last 100 tokens different | 8.7 s | 1.12 s | 1.00 s |
| Growing conversation (+3.8k tokens per turn, 23k to 42k) | not measured (a full prefill each turn, about 7 to 13 s) | **1.65 to 2.1 s per turn** | not repeated |
| Decode, one stream | 9.2 tokens/s | 9.2 | **28.3 tokens/s** |
| Decode, total with 2 / 4 / 8 parallel streams | not measured | 17 / 34 / 69 tokens/s | **55 / 108 / 210 tokens/s** |
| Tool call turn / tool-result turn | 6.7 s / 6.1 s | 6.0 s / 4.4 s | **2.1 s / 3.0 s** |
| Prompts of about 30k tokens that stay warm | none | 4 (about 120k tokens) | 4 (about 120k tokens) |
| Calls one agent can make in 90 minutes (model, section 4) | 36 | 43 | **104** |
Short version: prefix caching removes the cost of re-sending a growing agent conversation (9 s to 0.5 to 2 s per call); CUDA graphs triple the decode speed (9 to 28 tokens/s) and make the per-step cost independent of batch size; **neither changes the prefill speed or how much context stays warm (about 120k tokens), which is the limit for several concurrent agents.**

## 2. What was changed and how
- **Mechanism:** Amit's `src/gcp/manage_endpoint.py` (repository `prescera/benchmark-evals`, commit "added gcp file"). It finds the endpoint by a label, registers a "model" (a container recipe: the vLLM image, arguments, routes, environment; **not** the weights) with a hash of the recipe as a label, and deploys it to the endpoint (`a2-ultragpu-1g`, one A100 80GB, minimum and maximum replicas 1, all traffic). `restart` is `stop` then `start`.
- **Same endpoint every time:** address and dedicated DNS unchanged; each change of the argument list registered a new model version (the project now has four model records), and only one is deployed at a time.
- **The only edits** (a copy of the script run from the study owner's Mac, Amit's repository untouched): B added `--enable-prefix-caching`; C removed `--enforce-eager`. Everything else (model `Qwen/Qwen3.8-27B` at a pinned revision, maximum context 262,144, tool-call parser `qwen3_coder`, reasoning parser `qwen3`, chunked prefill, memory fraction 0.9) stayed.
- **Weights** are downloaded from Hugging Face at every start (about 54 GB), so each deployment took about 25 minutes until it answered.
- **Timeline (UTC, 2026-11-04):** A deployed 03:48 to 14:02 (undeployed through the API); B 16:18 to 16:57; C 16:57 to 17:57; about 12 GPU-hours in all; the hourly price is not known to us. Redeploy kit (outside the repository): the study owner's Mac, `spark/qwen-deploy/`.

## 3. Measurements
Method: calls from the Mac with the study owner's Google login to the endpoint's dedicated DNS name (`.../endpoints/<id>/chat/completions`), random-word prompts (so nothing is shared by accident), streaming with usage, `max_tokens` 1 for time-to-first-token tests, thinking off for those tests. Script: `tools/qwen_endpoint_probe.py` (section 10); raw numbers: `aws-vm-data/qwen27b/measurements.json`.

### 3.1 Prefill and the context limit (A)
| Prompt tokens | Time to answer |
|---|---|
| 16,008 | 6.7 s |
| 63,929 | 27.7 s |
| 127,794 | 58.7 s |
| 255,379 | 164.1 s |
A request over 262,144 tokens in total is refused with a clear 400. The first estimate of about 2,000 tokens/s came from these whole-call times (which include thinking and decoding); the time-to-first-token test gives **about 3,270 tokens/s** (28,576 tokens in 8.75 s).

### 3.2 Prefix caching (28.6k-token prompt, time to first token)
| Request | A | B | C |
|---|---|---|---|
| new prompt | 8.75 s | 9.98 s | 10.38 s |
| the same prompt again | 8.77 s | 0.49 s | 0.49 s |
| same first 28.5k tokens, different last ~100 | 8.74 s | 1.12 s | 1.00 s |
| the same prompt, third time | 8.72 s | 0.50 s | 0.45 s |
| a different new prompt | 8.74 s | 9.53 s | 8.59 s |
The usage field has no cached-token details in any configuration (`--enable-prompt-tokens-details` was not added), so caching is shown by timing only.

### 3.3 A growing conversation (B), each turn adds about 3.8k tokens after the previous prompt and reply
Turn 1 (19,694 tokens) 6.53 s cold; turns 2 to 7 (23,511 to 42,463 tokens): 1.65, 2.03, 2.05, 2.01, 2.09, 2.11 s. The time stays flat as the prompt grows, because only the new tokens are processed.

### 3.4 How much stays warm (B and C)
Send distinct prompts one after another, then re-send them newest first until one misses. About 59k-token prompts (B): 2 stayed warm (0.61 s and 0.70 s), the third missed (22.2 s). About 30k-token prompts: B 4 warm (0.46 to 0.52 s), the fifth missed (10.1 s); C the same (4 warm, fifth missed at 9.1 s). **The warm cache holds about 120k tokens in total in both B and C**, well below the 250k to 300k estimated from the architecture (section 5) and below the 262k context limit.

### 3.5 Decode speed and parallel streams
| | one stream | 2 streams | 4 streams | 8 streams |
|---|---|---|---|---|
| B (eager), total tokens/s | 9.2 | 17.0 | 34.0 | 68.8 |
| C (CUDA graphs), total tokens/s | **28.3** | **55.2** | **108.2** | **210.2** |
| C, per stream | 28.3 | 28.5 | 27.9 | 26.9 |
In B each stream stayed at 8.7 to 8.8 tokens/s whatever the number of streams: a fixed step of about 109 ms regardless of batch size is launch overhead, which CUDA graphs remove (step about 35 ms). Decode scales almost perfectly across streams to at least 8.

### 3.6 Tool calls
All three: a valid function call with JSON arguments (`finish_reason: tool_calls`) and a correct answer in the tool-result turn; reasoning arrives in a separate field. Round trips: A 6.7 s and 6.1 s, B 6.0 s and 4.4 s, C 2.1 s and 3.0 s.

### 3.7 Several agents at once (C): each starts at about 50k tokens, adds about 3k per turn, 6 turns, back to back
| Agents | First call (cold) | Later calls, mean (max) | Wall for 6 turns |
|---|---|---|---|
| 1 | 16.0 s | **1.9 s** (2.0 s) | 25 s |
| 2 | 24.7 s | **4.2 s** (16.2 s) | 46 s |
| 4 | 40.4 s | **76 s** (88 s) | 454 s |
Round-robin access to a least-recently-used cache is a cliff: once the combined context passes the warm capacity (about 120k tokens), each agent's cache is evicted before its next turn and the hit rate falls to about zero; with 4 agents every call is a miss and they queue behind each other.

## 4. What it means for an agent run (model, not measured on agents)
Assumptions: mean prompt 89,000 tokens (from the DeepSeek run), about 1,000 output tokens per call (derived from the earlier Qwen3.8-27B batch: output was 56% of a $4.98 bill at $2.30 per million over 1,190 requests), 15 s of tool time per call, prefill 3,300 tokens/s, a cache hit costs 1.5 s, 120k tokens warm; the DeepSeek run made 182 calls per task.
| Configuration | 1 agent | 2 agents | 4 agents | 8 agents | Aggregate ceiling per 90 min |
|---|---|---|---|---|---|
| A. eager, no caching | 36 calls | 36 | 36 | 25 | about 200 |
| B. caching, eager | 43 | 40 | 38 | 30 | about 238 |
| C. caching + CUDA graphs | **104** | 90 | 73 | 30 | about 294 |
The interpolated "warm share" for 2 and 4 agents is optimistic (section 3.7 shows the cliff: measured 4 agents behave like misses, so the aggregate ceiling is about 200 calls per 90 minutes there too). For one agent C is about 2.9 times better than A, but 104 calls is still 57% of DeepSeek's 182. A 100-task run is estimated at 3 to 6 days at this configuration (one to two agents at a time, 75 to 150 hours).

## 5. Why only about 120k tokens stay warm (open)
Checkpoint (at the pinned revision): `Qwen3_5ForConditionalGeneration`, 64 layers of which 16 are full attention and 48 are linear attention, 4 KV heads of dimension 256, bf16, one multi-token-prediction layer. KV memory is 64 KiB per token (16 layers x K and V x 4 heads x 256 x 2 bytes), so 128k tokens take about 7.8 GiB and the 80 GB card at 0.9 utilisation (about 71 GiB) minus about 50 GiB of weights suggests roughly 250k to 300k tokens. The measured warm capacity is less than half of that, in both B and C. Candidates: how vLLM budgets cache blocks and state for hybrid models, activation and buffer memory, a cap set by the server. The startup log ("GPU KV cache size") would answer it; the study owner's login cannot read logs (403) or metrics (`/metrics` is not exposed through the dedicated endpoint).

## 6. Prompt stability (needed for caching to pay off)
Real Codex 0.118.0 requests (captured in a throwaway container against a local server) are append-only across turns: `instructions` (20,771 characters) and the 10 tool definitions are identical every turn, and each request keeps all earlier items and adds two. After our Responses-to-Chat translation and the model's own chat template, each prompt is a 100% prefix of the next. The only date is `<current_date>` (no clock time) in the first user message, after a static block of about 45,400 characters (about 11,000 tokens) shared by every task. The template keeps earlier thinking by default and our translator drops reasoning from history consistently, so history is not rewritten. Tested with and without reasoning in history.

## 7. Versions
Model `Qwen/Qwen3.8-27B` revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`; serving image `pytorch-vllm-serve` tag `20260713_0916_RC01` (Google's prebuilt vLLM container); vLLM 0.25.0 as read from the endpoint metadata on 2026-11-03 (not re-confirmed); entry point `vllm.entrypoints.api_server`. MTP (the checkpoint has one multi-token-prediction layer) is **not** enabled in any configuration; whether this build supports it for this architecture is unknown.

## 8. What could improve it next (not tried)
1. **More warm capacity** (the binding limit): the official FP8 checkpoint `Qwen/Qwen3.8-27B-FP8` exists (weights about 27 GB instead of 54, freeing roughly 27 GB, about 400k more tokens of KV; weight-only FP8 on an A100; a different artifact than the bf16 model, so a protocol decision); an fp8 KV cache (about twice the tokens); memory fraction 0.95 (about 60k tokens more).
2. **Two GPUs with tensor parallelism:** about 5 times the KV memory and faster prefill, at twice the hourly cost.
3. **Replicas with session-sticky routing:** each adds about 120k warm tokens.
4. **MTP speculative decoding** for decode; **lower reasoning effort** for fewer output tokens (a behaviour change).
5. **Make caching visible:** add `--enable-prompt-tokens-details` so usage reports cached tokens (not verified that this entry point accepts it).

## 9. Not measured or not readable
Decode speed under a long context; thinking-mode output length on benchmark tasks (the 1,000 tokens per call is derived); the server's log and metrics; behaviour over a full 90-minute agent run; the accuracy effect of any change (none of these changes should affect outputs, quantisation would). The two-task pilot (`igraph/arvo_29408`, `md4c/arvo_31332`) has not been run: it needs a registry entry for the dedicated DNS, a second shim and a Google token on the head.

## 10. Reproduce
`tools/qwen_endpoint_probe.py` (environment variables `QWEN_PROJECT_NUMBER`, `QWEN_REGION`, `QWEN_ENDPOINT_ID`; the Google login through `gcloud auth application-default login`): subcommands `cache`, `conversation`, `residency`, `decode`, `agents`. The numbers above came from earlier, identical logic with the ids written in; the sanitised script was only syntax-checked (the GPU was undeployed). Deployment: the redeploy kit, `manage_endpoint.py start` and `stop`. Each full test takes about 10 to 15 minutes of GPU time once deployed (plus the 25-minute start).
