---
type: synthesis
created: 2026-11-01
updated: 2026-11-01
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [qwen, bedrock, codex, shim, responses-api, chat-completions, translation, benchmark-evals, living-document]
---
# Running Qwen models on Bedrock under Codex: the Responses-to-Chat translation layer (living page)

Part of [[wiki/syntheses/benchmark-evals-codebase-guide]]. **Status: translator written and tested locally and against real Bedrock for two Qwen models; not yet used for a real task; not deployed to the live shim or the AMI.** Context: the next study is 100 fixed tasks, e2e, `qwen3.8-27B`, Codex as harness, on Bedrock like the Kimi runs.

## 1. Findings that led here (2026-11-01, read-only checks, under $0.002)
| Check | Result |
|---|---|
| Is `qwen3.8-27B` on Bedrock? | No: not in the model list of us-east-1, us-east-2, us-west-2, eu-west-1, ap-northeast-1, ap-south-1, nor in us-east-1 inference profiles |
| Qwen models that are there (us-east-1) | `qwen3-coder-next`, `qwen3-next-80b-a3b`, `qwen3-32b-v1:0`, `qwen3-vl-235b-a22b`, `qwen3-coder-30b-a3b-v1:0` (all on-demand) |
| Kimi K3 on `/openai/v1/responses` | works with the inference-profile id `us.moonshotai.kimi-k3` (plain `moonshotai.kimi-k3` is rejected for on-demand) |
| `qwen3-coder-next` on `/responses` | 400: model "does not support the '/openai/v1/responses' API" |
| `qwen3-32b-v1:0` on `/responses` | 404 model_not_found |
| Both on `/chat/completions` | work, including tool calls and tool-result turns, streaming with a final usage chunk |

Cause: Bedrock decides per model which API formats it serves. Codex speaks only Responses, so for these models a translation is needed. Neither the models nor Codex are at fault. Usage from Bedrock's chat route carried no cached-token field for `qwen3-coder-next` and `qwen3-32b-v1:0`, so cache share cannot be measured for them; `qwen3-coder-30b-a3b-v1:0` did report cached tokens (see section 3).

## 2. Design
- New module `tools/responses_chat.py` (pure functions, no network): `responses_to_chat`, `chat_to_responses`, `StreamTranslator` (Chat chunks to Responses SSE events).
- Shim switch `UPSTREAM_API=chat` (default off, so existing runs are unchanged): Codex's `/v1/responses` call is translated to `/v1/chat/completions` and the reply translated back, streaming included. Metering reads the translated usage; if the upstream sends none the shim estimates from the request size so caps still count.
- Mapping: `instructions` plus developer messages become one system message; `function_call` and `function_call_output` items become assistant `tool_calls` and `role: tool` messages (consecutive calls merged); reasoning items and hosted tool types are dropped; Codex freeform tools (`apply_patch`) go upstream as a function with one string argument `input` and come back as `custom_tool_call`; `max_output_tokens` becomes `max_tokens`; a cut-off reply becomes `status: incomplete`.
- Caveat for any study: the translator is our code between Codex and the model; record it in the setup.

## 3. Tests
| Test | Result |
|---|---|
| 12 unit tests (`tests/test_responses_chat.py`): message and tool mapping, custom tools both ways, usage, streaming order, name-before-arguments chunks, parallel calls, truncation | pass |
| 2 end-to-end tests (`tests/test_shim_chat_mode.py`): Codex-style call through the real shim to a fake chat upstream, stream and non-stream, metering, missing-usage estimate | pass |
| Real Bedrock, 3-turn streaming conversation through the shim on a spare port, tool call then result then another call, with an echoed reasoning item and a freeform tool declared, for each model | `qwen3-coder-next`, `qwen3-32b-v1:0` and (2026-11-01, later) `qwen3-coder-30b-a3b-v1:0` all pass: tool calls come back as proper `function_call` items, final text correct, usage metered, 0 errors, about $0.0007, $0.0005 and $0.0006 at placeholder prices. Only the 30B coder model reported cached tokens (384 of 417 input on the second turn), one small request, not a hit-rate measurement |

## 4. Not yet done
- No real Codex run; no e2e task; nothing on the cluster. Streaming events were checked by our own client, not by Codex itself.
- Prices for the Bedrock Qwen models are placeholders in the test; real per-token prices and context windows still to confirm.
- `qwen3.8-27B` is not available on Bedrock; the models tested are stand-ins. Decision pending with the owner (another Bedrock model, a custom import, or a different provider).
- Code is in a local copy outside Git (`amit-repo/vm-copy-2026-11-01`), not on a branch, not on the VM's live `tools/`, not in the AMI.
