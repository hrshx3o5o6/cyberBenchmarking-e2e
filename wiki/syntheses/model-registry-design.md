---
type: synthesis
created: 2026-11-02
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [design, model-registry, shim, bedrock, openrouter, providers, benchmark-evals, living-document]
---
# Model registry: choose a model and provider by a string (design, living page)

**Status: the registry loader is built and tested locally (section 14); the shim, manifest and worker are not wired to it yet.** Decisions marked *proposed* are my recommendation and still need confirmation. Background: [[wiki/syntheses/how-a-run-works-on-the-vm]], [[wiki/syntheses/qwen-bedrock-responses-translation]], [[wiki/syntheses/benchmark-evals-codebase-guide]].

## 1. Problem
Today the provider is wired by hand, per model. Switching model means: edit the manifest; restart the metering shim on every node with different environment (target model, upstream URL, key file, auth style, prices, caps, and for chat-only models the translation switch); and, for autoscaled workers, re-render the cluster config because the model name and cap are baked into the worker start command. One shim process serves one model, so two models cannot run in one study at the same time. The Qwen tests on Bedrock showed that per-model facts (which API format it speaks, whether it reports cached tokens, which id form works) are real and easy to get wrong.

## 2. Goal
The main code names a model and a provider by a string (`kimi-k3@bedrock`, `glm-5.3@openrouter`). Everything else (endpoint, secret, API format, prices, pinning, limits) is resolved behind that string. A new model from a known provider needs no code change.

## 3. Where it plugs in (nothing else in the pipeline changes)
1. **Manifest:** one new optional key, `model_ref`. Absent means today's behaviour (backward compatible).
2. **Worker (`worker.py`):** it already requests a per-task key from the shim; add `model_ref` to that request (about 3 lines).
3. **Shim:** resolve the string against the registry, remember the route on that key, serve that task's calls with the resolved endpoint, secret, adapter, prices and caps. Agent containers still see only the shim URL and their key.
Ray, Docker, the harness and the autoscaler are unchanged, except that the cluster config no longer needs a model baked in.

## 4. String format (proposed)
`<model>@<provider>`, one field. `<model>` is a registry alias or a raw upstream id. Providers in version 1: `bedrock`, `openrouter`, `vertex` (Google Vertex AI; added 2026-11-02 once access to a DeepSeek model there was granted, see section 5a).

## 5. Two layers
| Layer | Content | How many |
|---|---|---|
| Provider profile | base URL, auth style, name of the secret, default API format, default pinning and fallback rules, usage-reading rules | a handful, written once |
| Model entry (optional) | alias, upstream id, API format override (for example `chat`), prices, context window, concurrency limit, provider pin, quirks | one per model we vet |

The file holds no secrets, only secret names (an environment variable or file on the node). Illustrative entries (prices intentionally blank until checked):
```yaml
kimi-k3@bedrock:
  upstream_model: us.moonshotai.kimi-k3     # on-demand calls need the inference-profile id
  api: responses
qwen3-coder-30b@bedrock:
  upstream_model: qwen.qwen3-coder-30b-a3b-v1:0
  api: chat                                  # shim translates Codex's Responses calls
glm-5.3@openrouter:
  upstream_model: <exact id>
  provider: {order: [<pinned provider>], allow_fallbacks: false}
```

## 5a. The `vertex` provider (added 2026-11-02)
Vertex AI serves some models as a managed service ("MaaS", model ids end in `-maas`) through an OpenAI-compatible endpoint: `https://aiplatform.googleapis.com/v1/projects/<project>/locations/<region>/endpoints/openapi`, with region `global` for the model offered to us. The call format observed is **Chat Completions**, so Codex needs the Responses-to-Chat adapter (whether Vertex also serves Responses for it is unknown until probed).
| Profile field | Value |
|---|---|
| base URL | built from project id and region (both in the profile, not secrets) |
| auth style | `google_adc`: a short-lived Google access token (about an hour) from Application Default Credentials, refreshed by the **shim**, never by the agent; set as the bearer token |
| quota and billing project | named in the profile; the shared project the access was granted under |
| default API format | `chat` |
| egress | the shim's node must reach the Vertex host and Google's token endpoint |
Illustrative entry: `deepseek-v4.1-flash@vertex` with upstream id `deepseek-ai/deepseek-v4.1-flash-maas` and `api: chat`. Price is not known yet, so a dollar cap needs it entered first.
**Credentials.** Access was granted to a specific user identity, and the user-login flow (`gcloud auth application-default login`) must be done by the person in a browser. A user's login file is a sensitive, long-lived refresh token: do not copy it to autoscaled workers. Safer options, to be decided with whoever granted the access: a service account for the project with a key kept only on the head, or running the Vertex shim only on the head node. Because the shim holds the credential, tasks of up to 90 minutes are fine: the shim refreshes the token itself.

**Probe result, 2026-11-02 (from the Mac, personal Google login, under $0.001):** the endpoint answers on Chat Completions: plain call 200; a tool call returned `tool_calls` with `finish_reason: tool_calls`; a streamed second turn after the tool result returned the right text and a final usage chunk (`stream_options.include_usage`). `/responses` returned 404 ("publisher model not found or no access"), so Codex needs the Responses-to-Chat adapter for this model. Usage carries `prompt_tokens`, `completion_tokens` and a traffic type (`ON_DEMAND`), and `prompt_tokens_details` was empty (no cached-token reporting seen on these small calls). Google auth worked with the user-login credential and its quota project; no price is known yet.

## 5b. Vertex through the shim, tested for real (2026-11-03, from the Mac)
Built: `UPSTREAM_AUTH=google_adc` in the shim (token fetched at start, cached, refreshed before expiry, quota-project header added; the shim exits at start with a clear message if the login or the `google-auth` package is missing), plus `UPSTREAM_RESPONSES_PATH` and `UPSTREAM_CHAT_PATH` for Vertex's endpoint shape. 4 unit tests with a stub Google package (token and quota project sent and cached; refresh after expiry; no login stops the shim at start; missing package stops it at start); with the earlier shim tests 23 pass.
Real run: the shim with the Vertex endpoint, `google_adc`, `UPSTREAM_API=auto`, and a Codex-style three-turn streaming client (tools including a freeform one) against the DeepSeek V4.1 Flash model. The first call triggered detection: Responses answered 404, a tiny chat call answered 200, so chat was pinned; all three turns returned 200 with proper `function_call` items and a correct final answer, 0 errors, usage metered (1,213 input and 76 output tokens, about $0.0005 at placeholder prices, not real ones). The adapter shows as `chat` in `/health` and in every log line. Detection took about 15 seconds on this first call (cause not isolated). No cached tokens were reported. The token was never printed.

## 6. Resolution order for `x@provider`
1. Exact registry entry: its fields override the provider profile.
2. Otherwise treat `x` as a raw upstream id with the provider's defaults (a new model works with no entry; the recorded route is marked `unvetted`).
3. Unknown provider, or a model with no price when a dollar cap is requested: fail at task start with a clear message (offer token or request caps instead; the shim already has them).
Never guess at run time.

## 6a. Format detection: Responses or chat (added 2026-11-02, built in the shim)
Some models speak the Responses format (Codex's) and some only Chat Completions, so a call may need the translation layer. A plain "got a 404, retry with translation" is too ambiguous: Bedrock answered 400 for one model ("does not support the Responses API") and 404 `model_not_found` for another, Vertex answered 404 "not found or no access", and a 404 can also mean a typo, the wrong region or no access. A model can also pass the first Responses call and fail the second (the gpt-oss reasoning-items case). So:
1. **The registry names the format** (`api: responses` or `api: chat`); `models probe` finds it once with the multi-turn test. No guessing at run time. (Until the registry exists, the shim setting `UPSTREAM_API` plays this role.)
2. **`auto` mode, for unvetted models:** decide once per route, not per call. Two tiny calls: Responses; if it answers 200 pin Responses; if it answers 400, 404, 405 or 501 with an "unsupported / not found / no access" message, one tiny chat call, and if that works pin chat.
3. **Guards:** never fall back on 5xx, 429 or timeouts; if chat fails too, nothing is pinned and the real error is shown (the next call tries again); once pinned the adapter never changes, so a conversation never switches format midway.
4. **Record the adapter** in every log line, in `/health` and on the key, and (still to do) in each result.
Built and tested in the shim as `UPSTREAM_API=auto` with 5 tests (200 pins Responses; unsupported with working chat pins chat after exactly one detection; not found on both pins nothing and shows the real error; 503 is never treated as a format problem; the chat path is configurable for Vertex-style endpoints). Tried against a real provider on 2026-11-03, see section 5b.

## 7. Finding and probing models (commands, not part of a run)
- `models find "kimi k3" --provider bedrock`: normalises (case, separators) and matches against the provider's live list (Bedrock foundation models plus inference profiles, for the configured region; OpenRouter's models endpoint). One match: show the full id, optionally write it into the registry (pin). Several: print the list and stop. None: print nearest names and where else it exists.
- `models probe <ref>`: a multi-turn tool-call test (the three-turn test used for the Qwen models, including echoed reasoning items and streaming) over each API format the provider offers; prints a suggested entry (detected API format, whether usage and cached tokens are reported). Costs cents.
- Facts that listing alone does not give: catalog is not access (`moonshotai.kimi-k3` is listed but only the `us.` profile id works on demand); availability differs by region; floating names move (prefer the dated id when one exists).

## 8. Recording and audit
Every result stores the resolved route: provider, upstream id, endpoint (no secrets), API format, whether a translator ran, vetted or unvetted, and a hash of the registry content. The manifest hash covers the string but not the registry, so without this a changed price or endpoint would silently change what the same string means.

## 9. Shim changes
- `/key/generate` accepts `model_ref`; the response returns the resolved route (no secrets) for the worker to record.
- Routing by key replaces the single process-wide target. Keys already carry an alias and a budget; add a route.
- Adapters live as small pure functions with tests: responses to responses (pass-through), messages to messages, responses to chat (exists), messages to chat (missing, needed for Claude Code on chat-only models).
- Per-route concurrency limit and 429 backoff in one place; no silent provider fallback (OpenRouter fallback off unless the entry opts in).
- Token provider: a profile with `google_adc` auth gets its token from a small refresher (cached, refreshed before expiry, thread-safe); static-key profiles read their secret name as before.
- Usage reading per profile: Responses counts cached tokens inside input; OpenRouter reports cost per response; Bedrock chat may report no cached tokens.
- Keep the old env-variable mode as the default so existing runs are untouched.

## 10. Secrets and failure behaviour
Secrets stay in the node's `config/.env` and key files; the registry and logs hold names only. An unknown or ambiguous ref fails the task before any model call. Egress rules for the firewall must allow each provider's host (to be checked per provider).

## 11. Testing
Unit tests for loading and resolving (known entry, raw id, unknown provider, missing price, ambiguous find) on the Mac with no network; shim tests with a fake upstream per API format; `models probe` live only on the VM or with the provider key present.

## 12. Build order
1. This page. 2. Loader and `resolve()` with tests. 3. Shim routing by key (old mode kept). 4. `models find` and `models probe`. 5. Manifest key and the worker change. 6. The Google token refresher and the `vertex` profile (needs a login to probe live).

## 14. The loader as built (2026-11-03, local copy, not deployed)
`tools/model_registry.py` (standard library only, Python 3.11+, about 330 lines), the shipped registry `tools/models.toml`, and `tests/test_model_registry.py` (24 tests, all pass; three deliberate breakages of the code each made a test fail).
- **File format:** TOML. `[providers.NAME]` tables (base URL, auth style, secret reference, default API format, paths, pinning) and optional `[models."alias@provider"]` tables (upstream id, API format, prices, vetted flag, note). Unknown keys are errors, so typos do not pass silently. A secret must be written as `env:NAME` or `file:PATH`; a pasted value is rejected and never echoed in the error. `google_adc` takes no secret. Endpoint placeholders `{env:NAME}` and `{env:NAME|default}` let the project and region come from the environment.
- **`resolve(registry, "alias@provider")`:** exact entry first (its fields override the provider's), else the raw upstream id with the provider's defaults (reported `vetted: false`, `source: raw`), else a clear error (unknown provider lists the known ones; a missing environment variable is named, never its value; a dollar cap with no price is refused). Provider order pins and fallback is off unless an entry opts in.
- **`Route.public()`** is what to record with a result: the full route plus the registry digest, with only a secret *reference*.
- **`check_secret`** says whether the named secret is present, never what it is. **`find(query, candidates)`** matches a loose name against a provider's model list: one, many (never picks for you) or none with suggestions; it prefers the region-profile id when that is the only difference (the Kimi case).
- **Shipped entries:** `kimi-k3@bedrock` (Responses, price from the worker start script), three Bedrock Qwen models (chat), `deepseek-v4.1-flash@vertex` (chat); Bedrock, OpenRouter and Vertex providers. No prices yet for the Qwen and DeepSeek entries. The self-deployed Qwen3.8-27B endpoint is not in it (blocked on tool calling).
- **The bridge (added 2026-11-03):** `shim_env(route, ...)` turns a route into the metering shim's settings (upstream, model, auth style, API format, the two paths, prices, provider pinning, strip fields, timeouts and limits) and names the provider key through the new shim setting `UPSTREAM_KEY_ENV` (or `UPSTREAM_KEY_FILE`), so no secret value is ever in the settings. Caps follow the price: a model with a price takes dollar caps (a remote upstream needs a per-key one, refused early otherwise); a model with no price simply runs without one: no dollars are tracked (cost shows as 0 in the shim log and results), and it is capped per key by tokens and requests with defaults (5,000 requests, 40 million input tokens, 400 million cache tokens, overridable) in the new `TOKEN_CAPS_ONLY` mode. Asking for a dollar cap on a model with no price is an error, because a cap that cannot be enforced would give a false sense of safety. The shim itself still refuses a remote upstream with no cap of either kind. Command line: `model_registry.py show <ref>` (route, whether the secret is present) and `env <ref> [caps]` (shell exports).
- **`tools/start_shim.sh <ref> <total-usd | tokens> [per-key-usd]`** starts the shim for any registry reference on a node: settings from the registry, the shim master key and provider key from the node's `config/.env` in a subshell, idempotent, `DRY_RUN=1` prints the settings without starting anything. It replaces `start_worker_services.sh` (Bedrock written into the script) once the cluster config passes a model reference instead of a raw model name; not yet done, and the old script is unchanged.
- **Token file (added 2026-11-03):** `--token-file` / `TOKEN_FILE=` turns a `google_adc` route into a bearer key read from a file holding a one-hour access token, for a machine that must not hold a Google login; only valid for `google_adc` routes. **First real use: the DeepSeek-on-Vertex Codex smoke test passed (see [[wiki/syntheses/vm-session-checklist]], section E-result)**, started with `start_shim.sh deepseek-v4.1-flash@vertex tokens`.
- **Token URL (added 2026-11-03):** `--token-url` / `TOKEN_URL=` makes the shim fetch the current token from the head's relay; exclusive with the token file; `--token-file` now also switches the file reload on. Both only for `google_adc` routes and temporary.
- **Tests:** 11 for the bridge, the shim's new settings, the start script and an end-to-end run (a registry route drives a real shim against a fake provider); three deliberate breakages each made a test fail. With the rest, 59 local tests.
- **Not done:** listing models from a provider, `models probe`, the shim routing by key, the manifest key and the worker change, the cluster config passing a reference to workers (build order steps 3 to 5).

## 15. Status of plug-and-play (added 2026-11-05)
How far the registry gets us toward "plug in a model and run", with the dedicated Qwen endpoint as the latest example, and what is still manual: [[wiki/syntheses/plug-and-play-model-support]]. The `vertex-dedicated` provider (an endpoint with its own DNS name) was added for Qwen3.8-27B; see [[wiki/syntheses/qwen-two-task-pilot]].

## 13. Open questions
| Question | Proposed |
|---|---|
| String as one field or two (`model`, `provider`) | one field |
| Registry file in the repo or only on the nodes | in the repo (auditable), no secrets inside |
| One shim per node serving all routes, or one per route | one per node, route by key |
| Version 1 scope | Bedrock, OpenRouter and Vertex |
| How the shim gets Google credentials on workers | not decided: service account on the head only, or no Vertex on workers; never copy a personal login to workers |
| Does Vertex serve the Responses format for this model | unknown until probed (needs the owner's login) |
| Who owns it | the shim is VM-only today; goes in the later shim pull request with the owner |
