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

## What would make it usable
1. Redeploy (or reconfigure) the vLLM server with tool calling enabled (`--enable-auto-tool-choice` and the tool-call parser that matches Qwen3.8; the right parser name is to be taken from the model's own documentation) and a reasoning parser, so thinking is returned separately.
2. Then repeat the three-turn streaming tool test, through the shim in chat mode (the translation layer is already built for chat-only upstreams).
3. Decide capacity: how many replicas, and what hourly cost is acceptable for a 100-task run.
4. Move the credential question forward (service account or federation) before using it from the cluster.
