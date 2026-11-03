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

## What would make it usable
1. Upload the model again and redeploy the vLLM server with a large context length (`--max-model-len`), tool calling enabled (`--enable-auto-tool-choice` and the tool-call parser that matches Qwen3.8; the right parser name is to be taken from the model's own documentation) and a reasoning parser, so thinking is returned separately.
2. Then repeat the three-turn streaming tool test, through the shim in chat mode (the translation layer is already built for chat-only upstreams).
3. Decide capacity: how many replicas, and what hourly cost is acceptable for a 100-task run.
4. Move the credential question forward (service account or federation) before using it from the cluster.
