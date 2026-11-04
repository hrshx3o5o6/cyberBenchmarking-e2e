---
type: synthesis
created: 2026-11-03
updated: 2026-11-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [vertex, qwen, qwen3-8-27b, endpoint, vllm, tool-calling, findings, benchmark-evals]
---
# Self-deployed Qwen3.8-27B endpoint on Vertex AI: access check (2026-11-03)

Part of [[wiki/syntheses/model-registry-design]] (section 5, the `vertex` provider). The endpoint belongs to the shared Google project the owner granted access to; project and endpoint ids are deliberately not recorded here.

## What it is (read from the endpoint's own metadata)
| Item | Value |
|---|---|
| Model served | `Qwen/Qwen3.8-27B`, by vLLM 0.25.0 |
| Hardware | one NVIDIA A100 80GB (`a2-ultragpu-1g`), one replica fixed (minimum and maximum 1) |
| Endpoint type | shared (not dedicated), region `asia-southeast1` |
| Traffic | 100 percent to this one deployed model |
A deployed GPU endpoint is billed by the hour on the project while it exists, whatever we send it.

## What worked (from the Mac, personal login, a few cents)
- Reading the endpoint configuration, and a small chat call through the Vertex SDK in the request format shown in the owner's snippet (`@requestFormat: chatCompletions`): about 6 seconds for 40 tokens.
- An OpenAI-style route on the same endpoint (`.../endpoints/<id>/chat/completions`, model name `Qwen/Qwen3.8-27B`): plain chat 200 with usage (`prompt_tokens`, `completion_tokens`).

## What does not work yet: tool calls
A request with tools returns 400: `"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set`. The vLLM server was started without those flags, so **the endpoint cannot be used by an agent harness as deployed** (Codex and Claude Code both depend on tool calls). The streamed tool-result turn was not reached.

## Other observations
- **Reasoning is inline.** The model's thinking appears in the reply content before a `</think>` marker, and the separate `reasoning` field is empty, so a reasoning parser was not configured either. An agent would read the thinking text as part of the answer unless the server splits it or our shim strips it.
- **Thinking uses tokens.** A 40-token limit ended mid-thought (`finish_reason: length`); small limits are not safe on this model.
- **No cached-token field** was seen in usage on these small calls.
- **Throughput risk.** One A100 with one replica serves all concurrent agent calls; a 100-task run at the parallelism we use elsewhere would queue. Not measured.
- Auth worked with a personal Google login and its quota project, the same as for the Model Garden DeepSeek endpoint.

## Update 2026-11-03 (later): the serving settings, and a second blocker
Read from Vertex's own records for the deployed model (metadata only, nothing sent to the model; environment variable values were not read):
| Setting | Value |
|---|---|
| Serving image | Google's prebuilt vLLM serving container (build of 2026-07-13) |
| Start command | `python -m vllm.entrypoints.api_server --model=Qwen/Qwen3.8-27B --revision=<pinned> --max-model-len=2048 --gpu-memory-utilization=0.9 --enforce-eager --tensor-parallel-size=1 --enable-chunked-prefill` |
| Weights | downloaded from Hugging Face at start (`MODEL_ID` environment variable, no stored artifact), so every redeploy re-downloads them (about 54 GB) |
| Deployed | 2026-11-03 04:42 UTC; model uploaded 2026-11-01 |
**`--max-model-len=2048` is a second blocker, confirmed by a test:** a prompt of about 1,000 tokens returned 200; a prompt of about 3,200 tokens returned 400 with "This model's maximum context length is 2048 tokens ... your prompt contains at least 2044 input tokens". An agent harness needs tens of thousands of tokens of context (the earlier Study-1 screens recorded a 131,072-token endpoint limit), so the endpoint cannot run the benchmark even with tool calling fixed. No tool-call or reasoning flags are present either (the 400 we saw), and `--enforce-eager` costs speed.
Consequence: the model must be uploaded again with a large `--max-model-len` (how much fits next to a 27B model on one 80GB GPU is for the owner to decide), the tool-call parser and a reasoning parser; redeploying the current version unchanged would be pointless. The owner agreed (2026-11-03) that the deployment can be undeployed while idle; undeploying removes the GPU machine (the billing) and keeps the endpoint and the model record.

See [[wiki/syntheses/qwen27b-serving-capacity-analysis]] for how much context and capacity the benchmark actually needs and where a single A100 would bottleneck.

## Undeployed (2026-11-03)
With the owner's agreement, the one deployed model was undeployed from the endpoint to stop the GPU charge while the endpoint cannot run the benchmark. Verified afterwards: the endpoint has no deployed models, the endpoint itself still exists (so its address is unchanged), and the uploaded model record (version 1, with the serving settings above) still exists. The undeploy took 2 seconds. **To bring it back:** deploy again to the same endpoint (one A100 80GB machine, one replica); because the old serving settings have a 2,048-token context and no tool-call or reasoning flags, redeploying the old version is pointless: upload a new version with the settings listed under "What would make it usable" first. A GPU of that type may not be available at the moment of redeployment, and the weights are downloaded from Hugging Face on every start, so allow some minutes.

## What would make it usable
1. Upload the model again and redeploy the vLLM server with a large context length (`--max-model-len`), tool calling enabled (`--enable-auto-tool-choice` and the tool-call parser that matches Qwen3.8; the right parser name is to be taken from the model's own documentation) and a reasoning parser, so thinking is returned separately.
2. Then repeat the three-turn streaming tool test, through the shim in chat mode (the translation layer is already built for chat-only upstreams).
3. Decide capacity: how many replicas, and what hourly cost is acceptable for a 100-task run.
4. Move the credential question forward (service account or federation) before using it from the cluster.

## Update 2026-11-04: new deployment tested (the blockers are fixed; speed is the problem)
The owner created a new endpoint and deployment (project, endpoint and model ids are deliberately not recorded here). Tests from the Mac with the personal Google login, a few minutes of GPU time.

**Deployment (read from Vertex's records; environment variable values not read)**
| Item | Value |
|---|---|
| Hardware | one `a2-ultragpu-1g` (NVIDIA A100 80GB), minimum and maximum replicas 1 |
| Endpoint type | **dedicated** endpoint: must be called on its own DNS name (`<endpoint id>.<region>-<project number>.prediction.vertexai.goog`); the shared `aiplatform.googleapis.com` domain returns 400 "Dedicated Endpoint cannot be accessed through the shared Vertex AI domain" |
| Serving command | `vllm.entrypoints.api_server ... --max-model-len=262144 --gpu-memory-utilization=0.9 --enforce-eager --tensor-parallel-size=1 --enable-chunked-prefill --enable-auto-tool-choice --tool-call-parser=qwen3_coder --reasoning-parser=qwen3` |
| Path used | `/v1/projects/<project>/locations/<region>/endpoints/<id>/chat/completions`, model name `Qwen/Qwen3.8-27B` |

**What now works**
| Test | Result |
|---|---|
| Plain chat | 200, usage returned, reasoning arrives in a separate field |
| Tool call | 200, `finish_reason: tool_calls` with a valid `sh` call and JSON arguments |
| Tool result turn | 200, the model answers from the tool output |
| Streaming | 200, 86 chunks, first chunk in 0.6 s, delta kinds `content` and `reasoning`, usage in the last chunk |
| Context | prompts of 16k, 64k, 128k and 255k tokens (my size estimate was off by a factor of 2, measured by the server) all 200; 262,144 is the hard limit (a request over it returns a clear 400) |

**What is slow (measured)**
| Measure | Value |
|---|---|
| Prefill (prompt processing) | 16k tokens in 6.7 s, 64k in 28 s, 128k in 59 s, 255k in 164 s: about 2,000 tokens per second as first measured from whole-call times (corrected to about 3,300 tokens per second by the time-to-first-token test below), with no benefit from sending the same prompt again (same 32k prompt three times: 15.3, 11.8, 15.3 s), so no useful prompt caching |
| Decode (generation) | 9.2 tokens per second for one stream (the server runs with `--enforce-eager`) |
| Parallel load | 4 parallel calls of 16k tokens finished in 24.5 s, 8 in 41.6 s (calls effectively queue; the single GPU is saturated) |
| Usage field | no cached-token details |

**What that means for the benchmark (rough estimate, not measured on agents)** The DeepSeek runs averaged about 130 calls per task with a mean prompt of about 128,000 tokens and about 340 output tokens. At the speeds above one such call takes about 60 s of prefill plus about 37 s of decoding, roughly 100 s of the GPU alone, so one A100 serves roughly one agent at a time (about 54 calls in 90 minutes). A 100-task run would need on the order of hundreds of GPU hours at this setting. Speed, not correctness, is now the blocker. Levers, for the owner to decide: prefix caching on, no `--enforce-eager` (CUDA graphs), more replicas or GPUs, a smaller sample, a lighter context policy. See [[wiki/syntheses/qwen27b-serving-capacity-analysis]].

**Still to do before an agent run:** the registry's `vertex-endpoint` provider builds the shared-domain URL and needs a dedicated-DNS variant; the three-turn streaming test through the shim in chat mode; a Codex smoke task; the credential question for cluster nodes (the endpoint is in a different project from the DeepSeek one). The GPU bills by the hour while deployed; undeploy when idle.

## Update 2026-11-04 (later): caching, KV capacity, prompt stability, versions
Question set: is prefix caching on, how much KV cache fits, are the agent's prompts append-only, which versions run. What could and could not be read:
- **Not readable by us:** the container's startup log (Cloud Logging returns 403 on all log views for our login) and `/metrics` (404 on every route through the dedicated endpoint's proxy), so no `prefix_cache_hits` counter and no "GPU KV cache size" line. To be requested from the owner (Logs Viewer role, or paste the lines): `GPU KV cache size: N tokens`, `Maximum concurrency for 262144 tokens per request`, `enable_prefix_caching`, the vLLM version banner, and the `vllm:prefix_cache_queries_total` / `vllm:prefix_cache_hits_total` counters.

**1. Prefix caching: measured as not working.** Time to first token (stream, 1 output token, thinking off) for a ~28,600-token prompt:
| Request | Time to first token |
|---|---|
| new prompt A | 8.75 s |
| A again, identical | 8.77 s |
| A with a different last ~100 tokens (same 28.5k prefix) | 8.74 s |
| A again, third time | 8.72 s |
| different prompt B | 8.74 s |
No difference at all, so a shared prefix is recomputed every time; usage also carries no cached-token details. From this the prefill speed is **about 3,270 tokens per second** (28,576 tokens in 8.75 s; the earlier 2,000 figure came from whole-call times that include thinking and decoding). Why it is off is not known: the serving command has no `--enable-prefix-caching`, and the model is a hybrid (see 2), a kind of model for which vLLM has historically disabled automatic prefix caching or needed extra settings. Either way the observed behaviour is no caching.

**2. KV cache capacity (estimate from the architecture; the log would give the exact number).** Checkpoint config at the pinned revision: `Qwen3_5ForConditionalGeneration`, 64 layers of which **16 are full attention and 48 are linear attention** (a layer pattern of 3 linear to 1 full), 4 KV heads of dimension 256, bf16, one MTP (multi-token prediction) layer present.
| Item | Value |
|---|---|
| KV bytes per token (full-attention layers only) | 16 layers x 2 (K and V) x 4 heads x 256 x 2 bytes = 64 KiB |
| 128,000 tokens of context | about 7.8 GiB of KV |
| Linear-attention state | a fixed size per sequence, about 80 to 150 MB, independent of length |
| GPU budget | 80 GB card x 0.9 utilisation = about 71 GiB, minus about 50 GiB of weights, minus activations: roughly 15 to 18 GiB for KV |
| Capacity N | roughly **250,000 to 300,000 tokens**; the server starts with `--max-model-len=262144`, which only works if at least 262,144 tokens fit, so N is at least that |
| N / 128k | about 2 agents with 128k-token contexts at the same time (about 3 at the 85k median seen in earlier Qwen runs) |
Because prefix caching is off (1), the cache is not kept warm between calls: the KV of a finished request is freed, so N limits how many requests can be in flight at once (about 2 long ones), not how many agents' histories stay warm. If caching were turned on, N / 128k would also be the number of agents whose histories could stay resident.

**3. Prompt stability: the agent's prompts are append-only (verified).** Method: ran the harness's Codex version (0.118.0, installed the way the harness installs it, in a throwaway container) against a local capture server for four turns, then pushed the captured requests through our Responses-to-Chat translation and the model's own chat template.
- Codex request structure: `instructions` (20,771 characters, identical on every turn), 10 function tools (`exec_command`, `write_stdin`, `update_plan`, and others; identical order), a developer message with permissions and skills, then a user message with an `<environment_context>` block (cwd, shell, **`<current_date>` as a date only, no clock time**, timezone), then the task. Each later request keeps all earlier items unchanged and adds two (the call and its output): leading items identical in turns 1 to 4.
- A `prompt_cache_key` (a per-session UUID) is sent; vLLM ignores it.
- After our translation: message lists extend the previous ones exactly; tools identical.
- After the Qwen chat template: the whole previous prompt, generation prompt included, is a prefix of the next prompt (100 percent shared in all three transitions, 45.7k to 46.3k characters). The date sits in the first user message, after a static block of about 45,400 characters (system plus tool definitions, roughly 11,000 tokens), not at the top.
- **Chat template and `<think>` blocks:** this template does not strip earlier thinking by default (it keeps it unless `preserve_thinking` is false and only for turns before the last user message). Our translator drops the model's reasoning from history, so every earlier assistant turn renders the same way each time. Tested: no history rewrite whether or not reasoning is sent, and also with `preserve_thinking=false` in a single-user-message loop like Codex's.
- Remaining risks, if caching is ever turned on: the date line changes at midnight UTC (only matters across tasks or a run that crosses it); a new user message mid-run would change how earlier thinking is rendered if `preserve_thinking` were false; our translator rewrites malformed tool-call arguments in history (rare, about 1 call in 30 on DeepSeek, unknown for Qwen). The static ~11,000-token prefix is also shared across tasks (apart from the date and the working directory).

**4. Versions.** Model: `Qwen/Qwen3.8-27B` at revision `1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0`, architecture `Qwen3_5ForConditionalGeneration`, bf16, 262,144 maximum positions. Serving: Google's prebuilt vLLM container, image tag `20260713_0916_RC01`; vLLM version 0.25.0 as read from the endpoint metadata on 2026-11-03 (not re-confirmed today). Flags: `--max-model-len=262144 --gpu-memory-utilization=0.9 --enforce-eager --tensor-parallel-size=1 --enable-chunked-prefill --enable-auto-tool-choice --tool-call-parser=qwen3_coder --reasoning-parser=qwen3`. **MTP is not enabled** (no `--speculative-config`) although the checkpoint has an MTP layer; whether this vLLM build supports MTP for this architecture is not known to us.

**What this changes in the speed picture:** prefill is about 3,300 tokens per second (not 2,000), decode 9 tokens per second, no prompt caching, MTP off, eager mode on. For an agent call at the 128k-token average seen with DeepSeek that is about 39 s of prefill plus about 37 s of decoding 340 tokens, still roughly 75 s of GPU time per call and about one agent at a time. Biggest levers, in order: get prefix caching working (the prompts are ready for it: each call would recompute only the new ~2 items instead of 128k tokens), drop `--enforce-eager`, enable MTP if supported, add replicas. See [[wiki/syntheses/qwen27b-serving-capacity-analysis]].

## Undeployed again (2026-11-04, 14:02 UTC)
At the study owner's request the GPU deployment was undeployed to stop the hourly charge; it had been deployed since 03:48 UTC the same day. Verified afterwards: the endpoint still exists (same address), it has no deployed model, and the uploaded model record still exists. The undeploy took 2 seconds.
**To redeploy:** deploy the existing model record to the existing endpoint with machine type `a2-ultragpu-1g` (one NVIDIA A100 80GB), minimum and maximum replicas 1, on the dedicated endpoint (its own DNS name). The serving arguments, including the large context, tool-call parser and reasoning parser, are stored in the model record, so nothing needs to be re-entered. The weights are downloaded from Hugging Face at start (about 54 GB), so allow several minutes before it answers. Ids are deliberately not recorded in this repository.
Next step agreed in principle: after the 100-task DeepSeek run, a two-task Qwen pilot (`igraph/arvo_29408` and `md4c/arvo_31332`, both passed by Qwen3.8-27B on OpenRouter earlier) to compare calls, speed and results; preparation (registry entry for the dedicated DNS, a second shim, a three-turn tool test) can be done earlier.

## Access check of the Qwen project (2026-11-04, after the owner granted changes)
Checked with read-only calls from the study owner's login. Ids are not recorded.
| Capability | Result |
|---|---|
| List models, read the endpoint, undeploy a deployed model | works (undeploy was done earlier the same day) |
| Upload a model record (a changed serving configuration is a new model version) | works (shown by accident, see below) |
| Deploy a model to the endpoint | not tested (a deployment bills by the hour); needs a GPU quota in the region, which could not be read |
| Read logs (the vLLM startup log) | **403, no access to any log view**: needs a logging viewer role with access to the default log view |
| Read monitoring metrics (GPU, endpoint) | 403 |
| Read GPU quotas through the API | 403 (the Console's Quotas page may still show them) |
| Resource Manager `testIamPermissions` | unavailable: the API is not enabled in either project |
Mistake and clean-up: an upload request with an empty body, sent to test the permission, created an empty model record (no name, no image). It was identified by its creation time and deleted; the two real model records are untouched.
To check the cache without logs or `/metrics`: redeploy with the vLLM option that adds cached-token details to the usage field (`--enable-prompt-tokens-details`), then repeat the time-to-first-token test.

## Redeployed with prefix caching on (2026-11-04, 16:18 to about 16:43 UTC): caching works, warm capacity is small
Change tested: Amit's `src/gcp/manage_endpoint.py` (repo `prescera/benchmark-evals`, commit "added gcp file"), run from a scratch copy with exactly one added serving argument, `--enable-prefix-caching`; everything else unchanged (including `--enforce-eager`). The script registered a new model version (a changed argument list gives a new configuration hash) and deployed it to the same endpoint, address unchanged. The deployment took about 25 minutes from start to answering (mostly the weights download); no error.
| Test (28,600-token prompt, time to first token, 1 output token) | Before (no caching) | After |
|---|---|---|
| new prompt | 8.75 s | 9.5 to 10.0 s |
| the same prompt again | 8.77 s | **0.49 s** |
| same first 28.5k tokens, different last ~100 tokens | 8.74 s | **1.12 s** |
| a different new prompt | 8.74 s | 9.5 s |
**Growing conversation (append-only, about 3.8k tokens added per turn):** turn 1 (19.7k tokens) 6.5 s cold; turns 2 to 7 (23.5k up to 42.5k tokens) 1.65 to 2.1 s each, flat as the prompt grows, because only the new tokens are processed.
**How much stays warm:** sending distinct prompts one after another and re-sending them newest first, then counting consecutive warm answers: with about 30k-token prompts **4 stayed warm and the 5th was evicted** (about 120k tokens); with about 59k-token prompts **2 stayed warm** (about 118k tokens). So the warm cache holds roughly **120k to 150k tokens in total**, well below the 250k to 300k I had estimated from the architecture and below the 262k context limit. The cause is not known (candidates: how vLLM budgets cache blocks and state for the hybrid layers, memory taken by weights and buffers); the server log would show the KV cache size. Consequences for agents: about 3 agents at 40k-token contexts, 1 to 2 at the 78k mean, 1 at 128k; more agents than that evict each other (least recently used first) and fall back to full prefill at about 3,300 tokens per second.
Not yet re-measured after the change: decode speed (still eager mode, expected about 9 tokens per second), cached-token details in the usage field (still absent: `--enable-prompt-tokens-details` was not added), and a tool-call and long-context re-check.

## Redeployed with CUDA graphs (2026-11-04, about 17:00 to 17:30 UTC): decode 3x faster, cache capacity unchanged
Change tested: `--enforce-eager` removed from the serving arguments (prefix caching kept), through the same copy of Amit's `manage_endpoint.py` (`restart`: undeploy, register a new model version, deploy to the same endpoint). It started without error; the deployment took about 25 minutes.
| Measure | Eager mode (caching on) | CUDA graphs (caching on) |
|---|---|---|
| Decode, one stream | 9.2 tokens/s | **28.3 tokens/s** (first token after 0.55 s) |
| Decode total, 2 / 4 / 8 parallel streams | 17 / 34 / 69 tokens/s | **55 / 108 / 210 tokens/s** (each stream stays near 27 to 28) |
| Tool call turn / tool-result turn | 6.0 s / 4.4 s | 2.1 s / 3.0 s (valid call, correct answer) |
| Time to first token, 28.6k-token prompt: new / identical repeat / shared prefix | 9.5-10.0 s / 0.49 s / 1.12 s | 8.6-10.4 s / 0.49 s / 1.00 s |
| Prompts of about 30k tokens that stay warm (newest first, then the 5th is evicted) | 4 (about 120k tokens) | 4 (about 120k tokens) |
So CUDA graphs fix the slow decoding step (the per-step cost was launch overhead: it did not grow with the number of streams) and cost nothing visible in cache capacity; prefill speed (about 3,300 tokens per second for a cache miss) and the roughly 120k warm tokens are unchanged. At the DeepSeek workload (mean 89k-token prompts, 280 output tokens) a cache miss still costs about 27 s of prefill, but decoding a call now takes about 10 s instead of 30 s; with caching a normal agent call (a few thousand new tokens) is about 2 s of prefill plus the decode.
Remaining limits: only about 120k tokens of context stay warm, so about 1 to 2 agents at the 78k to 89k mean and about 4 at 30k; beyond that they evict each other and recompute at 3,300 tokens per second. Next levers: understand why the warm cache is only about 120k tokens (needs the server log), a quantised KV cache or weights, a second GPU.

