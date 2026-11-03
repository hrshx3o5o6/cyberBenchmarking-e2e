---
type: synthesis
created: 2026-11-03
updated: 2026-11-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [shim, metering, codebase, walkthrough, benchmark-evals, living-document]
---
# The metering shim, step by step

The shim is a small HTTP proxy (`tools/llm_shim_new.py`, about 370 lines plus `tools/responses_chat.py`, standard library only) that sits between the agent container and the model provider. It exists on our VMs only, not in the repo owner's repository (see [[wiki/syntheses/benchmark-evals-codebase-guide]], section 7). Part of the flow in [[wiki/syntheses/how-a-run-works-on-the-vm]]; the planned routing by model string is in [[wiki/syntheses/model-registry-design]]; the chat translation in [[wiki/syntheses/qwen-bedrock-responses-translation]].

## What it is for
1. **The agent never sees the real credential.** The container gets the shim's address and a throwaway per-task key.
2. **Spend control.** It counts tokens, converts them to dollars with a price table, and refuses calls once a per-key or total cap is reached.
3. **One place to adapt the provider**: forced model name, auth style, field stripping, and (new) Responses-to-Chat translation.
4. **A usage log**, one JSON line per call, with no request or response bodies and no keys.

It listens on the Docker gateway address of the internal network (the same address on every node, port 4100), so only containers on that network and the node itself can reach it.

## The settings it reads at start (environment)
| Group | Variables |
|---|---|
| Where to send calls | `UPSTREAM` (base URL, may carry a path prefix), `TARGET_MODEL` (forced on every call), `UPSTREAM_KEY` or `UPSTREAM_KEY_FILE`, `UPSTREAM_AUTH` (`x-api-key`, `bearer` or `both`) |
| Format | `UPSTREAM_API=chat` (translate Responses calls to Chat Completions), `STRIP_FIELDS`, `RESPONSES_INPUT_FIX`, `PROVIDER_ORDER` (OpenRouter), `COUNT_CACHE_CREATION` |
| Money | `PRICE_IN_PER_M`, `PRICE_CACHE_PER_M`, `PRICE_OUT_PER_M`, `MAX_SPEND_USD` (per key), `MAX_TOTAL_SPEND_USD`, `TOTAL_START` (spend already used, for restarts) |
| Other caps | `MAX_REQUESTS`, `MAX_INPUT_TOKENS` (fresh input only), `MAX_CACHE_TOKENS` |
| Behaviour | `UPSTREAM_SERIAL`, `UPSTREAM_TIMEOUT_STREAM` (seconds of silence tolerated on a stream), `UPSTREAM_TIMEOUT`, `KEYS_FILE` (preload keys on restart), `PORT`, `BIND`, `LOG_FILE`, `MASTER_KEY` |
**Refuses to start** if: no `TARGET_MODEL`; `MASTER_KEY` shorter than 16 characters; a dollar cap without all three prices; an HTTPS upstream with no real key; or an HTTPS upstream with no per-key cap (no uncapped paid spend, by design).

## Routes
| Route | Who calls it | What it does |
|---|---|---|
| `POST /key/generate` (master key) | the worker, once per task | creates a per-task key (alias, optional `max_budget`) with zeroed counters |
| `GET /key/info` (master key) | the worker, after the task | returns the key's requests, tokens, errors, spend, effective cap |
| `POST /key/delete` (master key) | cleanup | removes keys (logs their final counters) |
| `POST /v1/responses`, `/responses` | Codex | the metered Responses route |
| `POST /v1/messages` | Claude Code | the metered Anthropic route |
| `POST /v1/messages/count_tokens` | Claude Code | a rough local estimate (characters divided by 4) |
| `GET /v1/models`, `GET /health` | anyone on the network | the forced model; target, upstream, caps and total spend |

## One model call, step by step (`_forward`)
1. **Authenticate.** The key presented must exist, else 401.
2. **Parse and rewrite.** Read the JSON body, remember the original model name (logged as `orig_model`), and overwrite `model` with `TARGET_MODEL`. Drop any `STRIP_FIELDS`. For the Responses route, optionally fix Codex's echoed reasoning items (`strip_encrypted` or `drop_reasoning`). If a provider order is set, add it.
3. **Translate (chat mode only).** For a Responses call with `UPSTREAM_API=chat`, convert the request to Chat Completions and send to `/v1/chat/completions`.
4. **Check the caps before sending.** If the key is over its request, token or dollar cap, or the shim is over its total dollar cap, log `cap_hit` and return 400 "shim budget exhausted"; nothing is sent upstream. The per-key dollar cap is the stricter of the shim's own cap and the `max_budget` the worker asked for.
5. **Send upstream** with the configured auth. A 429 is retried up to 3 more times with 3, 6, 9 seconds of waiting. With `UPSTREAM_SERIAL` on (default for plain HTTP upstreams such as Ollama) calls go one at a time.
6. **Return the answer.**
   - *Streaming:* pass each line through as it arrives and watch the final events for the usage figures. In chat mode each upstream chunk goes through the stream translator, which emits Responses-style events and a closing event even if the upstream ends without `[DONE]`.
   - *Plain:* read the whole body, translate it back if in chat mode, and return it.
7. **Read usage.** Responses format: `input_tokens` includes cached tokens, so fresh input is input minus cached. Anthropic format: fresh and cache-read are separate fields. If the provider sends a cost figure it is used; otherwise the shim computes it from the price table. In chat mode, if the upstream reports no usage at all, the shim estimates input from the request size so caps still count.
8. **Account.** Add requests, tokens and spend to the key and to the shim total; count an error if the status is not 200.
9. **Log one line**: route, alias, original model, stream, number of tools, status, input, cache and output tokens, seconds, cost, how the cost was obtained, running spend and total. On an upstream error, the first 200 characters of the error and, for Responses, only the shapes of the input items, never content.

## Failure behaviour
- An upstream exception or timeout returns 502 to the agent and is logged; the shim itself keeps running.
- Accounting errors are logged, never raised into the response.
- Any request that is not 200 counts as an error on the key.

## Limits to remember
- **In memory only.** Counters and keys vanish if the shim restarts, unless `KEYS_FILE` and `TOTAL_START` are supplied (`swap_shim.py` does this for a live restart; `start_worker_services.sh` does it for an idle one).
- **Per node, not cluster-wide.** Every node has its own total; the cluster-wide budget in Postgres is built but not wired to the shim.
- **One model per process**; changing model means a restart (the registry design replaces this with routing by key).
- **Token-based providers** with expiring tokens (Google) are not supported yet; the shim only knows static keys.
- Prices are a manual table; a wrong price means a wrong dollar cap.
