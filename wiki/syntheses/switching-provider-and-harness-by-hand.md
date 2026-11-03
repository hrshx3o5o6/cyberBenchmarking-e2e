---
type: synthesis
created: 2026-11-02
updated: 2026-11-02
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [runbook, providers, harness, shim, manifest, benchmark-evals, as-is]
---
# Switching provider, model or harness by hand (the current setup)

How someone with no automation would change the provider, model or harness today. This is the "before" picture for [[wiki/syntheses/model-registry-design]] and [[wiki/syntheses/plug-and-play-layer-ideas]]. Background: [[wiki/syntheses/how-a-run-works-on-the-vm]]. Status: written from the code and our notes on 2026-11-02, discussed only, nothing run for this page.

## 1. Manifest (`config/<name>.json` in the runner)
| Key | Meaning |
|---|---|
| `agent` | the harness (`codex`, or Claude Code) |
| `model_provider` | `anthropic`, `bedrock` or `openai-compatible`; `codex` requires `openai-compatible` |
| `model` | the model id passed to the harness |
| `openai_base_url` | endpoint when it is not Bedrock |
| `shim_url`, `spend_cap_usd` | turn on the metered route through the shim |
| `tasks`, `modes`, `agent_timeout_seconds`, `firewall_domains`, `task_cpus`, ... | the rest of the order |
There is no `azure` or `gcp` option: any provider that speaks the OpenAI format is "openai-compatible" plus a base URL.

## 2. The shim: where the real provider is chosen
With `shim_url` set, the agent container only talks to the shim, and the real provider is whatever the shim was started with, through environment variables: `UPSTREAM`, `TARGET_MODEL`, key file, auth style, `UPSTREAM_API` (for chat-only models), prices, caps. To switch provider: stop the shim on each node, start it with the new settings, and set prices correctly (wrong prices mean wrong dollar caps). One shim serves one model.
The bundled start script (`start_worker_services.sh`) has the Bedrock URL, bearer auth and the Bedrock key file written into it, so another provider means editing that script or starting the shim by hand.

## 3. Secrets
The provider key goes into a key file or `config/.env` on the VM, placed by the person, never in chat or a manifest. Autoscaled workers get `.env` copied at launch.

## 4. Workers and the cluster
The worker start command in the cluster config runs the start script with a model name and total cap from the render step. So changing model or provider for autoscaled workers also means re-rendering the config and restarting the head. A node that is already running keeps its old shim until restarted.

## 5. Network
Without the shim, the provider host must be in the firewall allow-list (`firewall_domains`, then re-run the firewall update). With the shim in the path the shim makes the outbound call, so the container probably does not need the host allowed; not tested for non-Bedrock hosts.

## 6. Harness switching
Set `agent` in the manifest. Caveat: the worker only wires the shim for the OpenAI-style route (base URL and key through OpenAI-style variables), which is what Codex uses. Claude Code speaks the Anthropic Messages format; our earlier Claude Code runs on open models used the older Azure-VM scripts, not this runner. How Claude Code is meant to be pointed at the shim inside the runner is **unverified**. Adding another harness (OpenHands, opencode) needs the upstream `run_agent.py` to support it first; which agents it accepts has not been checked.

## 7. Worked example: Codex with GLM on OpenRouter
1. Put the OpenRouter key in a key file on the VM.
2. Edit the start script, or run the shim by hand, with the OpenRouter base URL, bearer auth, model id and prices.
3. Restart the shim on every node; re-render and restart the head for workers.
4. Manifest: `agent: codex`, `model_provider: openai-compatible`, `model`, `shim_url`.
5. `cybergym-eval preflight`, then `run`.

## 8. Pain points
- Provider facts live in three places: manifest, shim environment, start script; forgetting one gives silent mistakes (wrong prices, wrong cap).
- One shim, one model; switching means restarts on every node.
- Only Bedrock is baked in.
- A chat-only model needs the translation switch (`UPSTREAM_API=chat`) set by hand.
- Google-style tokens that expire are not supported at all.
