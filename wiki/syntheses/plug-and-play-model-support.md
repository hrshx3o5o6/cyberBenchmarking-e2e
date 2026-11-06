---
type: synthesis
created: 2026-11-05
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [registry, providers, plug-and-play, automation, assessment, vertex, bedrock, openrouter, living-document]
---
# How plug-and-play are models and providers? (assessment, 2026-11-05)

Question from the study owner: how much of "plug in a model and run it" do we have? Direction and goal: [[wiki/syntheses/platform-automation-and-architecture]]. Design of the string registry: [[wiki/syntheses/model-registry-design]]. This page is the honest status as of the Qwen dedicated-endpoint work, from the registry file `tools/models.toml` in the runner copy (not in this repository).

**Verdict (my judgement, not a measurement): about 60%.** A model on a provider we already know works with one string. A new provider or dedicated endpoint costs about an hour of manual work. Everything around the model (scheduling, credentials, endpoint lifecycle, capacity) is still manual.

## 1. What the registry holds today
| Providers (5) | Auth | API | Notes |
|---|---|---|---|
| `bedrock` | bearer token | auto (per model) | some models serve Responses, some only Chat Completions |
| `openrouter` | bearer key | responses | provider order can be pinned (cache behaviour differs by provider, [[wiki/syntheses/qwen-cache-investigation]]) |
| `vertex` | Google login (`google_adc`) | chat | serverless Vertex models, stream timeouts set |
| `vertex-endpoint` | Google login | chat | self-deployed endpoint by shared regional name; its model is unvetted |
| `vertex-dedicated` | Google login | chat | self-deployed endpoint by its own DNS name (added 2026-11-05 for Qwen) |

| Models (7) | Vetted | Priced |
|---|---|---|
| `kimi-k3@bedrock` | yes | yes (3.30 / 0.33 / 16.50 per million: fresh, cached, output) |
| `qwen3-coder-30b@bedrock`, `qwen3-coder-next@bedrock`, `qwen3-32b@bedrock` | yes | no |
| `deepseek-v4.1-flash@vertex` | yes | yes (0.30 / 0.03 / 1.20, the study owner's assumed prices) |
| `qwen3.8-27b@vertex-dedicated` | yes | no |
| `qwen3.8-27b@vertex-endpoint` | **no** | no |

"Vetted" means a person ran a multi-turn tool-call test against it; nothing checks this automatically. A price is optional, but without one the shim can only cap tokens, not dollars.

## 2. What costs how much to add
| Case | Effort | Evidence |
|---|---|---|
| New model on a known provider | no code: `<raw upstream id>@<provider>` runs with the provider's defaults, flagged unvetted | registry fallback rule ([[wiki/syntheses/model-registry-design]] section 6) |
| Same, vetted and priced | one toml block of about 5 lines plus a tool-call test | `kimi-k3@bedrock`, `deepseek-v4.1-flash@vertex` |
| New provider or dedicated endpoint | one provider block, environment variables on the node, a test; about an hour | `vertex-dedicated` for the Qwen endpoint; the full suite still passes (137 tests) |
| Start a run on a model | `tools/start_shim.sh <model@provider> <total or tokens> [per-key]`; the reference reaches workers as `MODEL_REF` | every run since the registry was wired in |

Already handled by registry and shim: three auth styles (bearer, `google_adc`, token-file reload); Chat Completions and Responses on the upstream side (the shim translates Responses to Chat so Codex can use chat-only models, [[wiki/syntheses/qwen-bedrock-responses-translation]]); per-provider idle and total stream timeouts; per-task keys; dollar or token caps.

## 3. What is not plug-and-play
1. **Quirks are found by running, not probed.** Each model so far cost one failed run or test before it worked, and the knowledge lives in wiki pages, not in code or the registry:
   | Model / provider | Quirk found | Where recorded |
   |---|---|---|
   | Qwen on Bedrock | chat only; Codex needs Responses | [[wiki/syntheses/qwen-bedrock-responses-translation]] |
   | DeepSeek on Vertex | streams stalled mid-call; fixed by a per-call total cap (`stream_total_timeout_s`) | [[wiki/syntheses/deepseek-100-first-pass-observations]] |
   | Qwen3.8-27B dedicated | tool calls and long context needed server flags; caching and graphs were off | [[wiki/syntheses/vertex-qwen27b-endpoint-check]], [[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]] |
   | Qwen on OpenRouter | cache share depends on the upstream provider | [[wiki/syntheses/qwen-cache-investigation]] |
2. **Credentials are fragile.** Vertex needs a Google token that is pushed from the study owner's Mac every 30 minutes (`tools/push_vertex_token.py`); a sleeping Mac or an expired login ends the model access (the login expired twice in the 100-task work). There is no service account on the VM. This is the largest gap.
3. **Dedicated endpoints have their own manual lifecycle.** Deploy is Amit's `manage_endpoint.py` (about 25 minutes, weights downloaded at each start), the GPU bills while up, undeploy is manual. The registry records where an endpoint is, not whether it is up.
4. **No price, no dollar cap.** The paper's rule is $10 per run; an unpriced model (five of seven here) gets a token cap instead, so the rule is not reproduced for it.
5. **The agent is fixed.** Codex is the scaffold; the model must cope with Codex-style tool calls. The harness `model_provider` coupling needs a 9-line local patch on upstream. Another scaffold is not a registry change.
6. **Capacity is not model-aware.** Slots and concurrency are hand-tuned. For Qwen the measured warm-cache capacity (about 120k tokens) fits about two agents, and nothing adapts concurrency to that ([[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]] sections 3.4 and 3.7).

## 4. Closing the gap (ordered by payoff, nothing started)
| # | Item | Removes |
|---|---|---|
| 1 | Service account (or workload identity) on the VM, no Mac token relay | the token-expiry failures; the Mac as a dependency |
| 2 | `registry probe <model@provider>`: plain call, streaming tool call, multi-turn tool test, stall test; writes quirks and `vetted` into the toml | per-model surprise runs; "vetted" by hand |
| 3 | Require a price or an explicit token cap before a run starts | uncapped or differently capped runs |
| 4 | Endpoint lifecycle hook: deploy, wait until ready, undeploy on finish, with a billing alarm | idle GPU billing; the 25-minute manual wait |
| 5 | Capacity hint per model (maximum concurrent agents from caching), read by the scheduler | hand-tuned slot counts |
Scheduling, recovery and monitoring are the bigger gaps on the run side, covered in [[wiki/syntheses/platform-automation-and-architecture]] section 4. Item 2 is the cheapest start: the Qwen smoke test (`qwen_smoke.py` on the VM) is already most of it.

## 5. What the Qwen pilot added (2026-11-05, [[wiki/syntheses/qwen-two-task-pilot]])
- Positive: a new provider block plus a registry route was enough. The dedicated endpoint answered through the shim on the first call, needed no extra header, and two Codex tasks ran to a graded pass (S1 to S4 both) with no changes during the run.
- Quirk found only by running: the endpoint's model reasons for a long time without sending anything the client sees, and two calls (520 s and 601 s) were lost, about a fifth of one task's agent time. A probe (item 2 above) would not have shown it in a short test; it needs a long-reasoning case or a stream-activity check.
- Not visible without extra serving flags: cached tokens (the endpoint reports none), so caching had to be inferred from call times. A probe should record whether usage includes cached tokens.
- Found on 2026-11-05: **the endpoint's DNS name can resolve to a stale address on some resolvers after a redeploy** (the head's VPC resolver kept an old address that stopped serving, public resolvers had the working one), so calls from the head failed with connection resets while the Mac worked. A probe should connect from the node that will run the study, not only from a laptop; a registry could hold an optional pinned address or the shim could re-resolve through a public resolver on failure. Worked around by pinning the name in the shim process ([[wiki/syntheses/qwen-capacity-levers-test]] section 7.3).
- Credentials held: the Mac relay kept the token fresh for the 93-minute run (token age stayed under 5 minutes at the last check), but it remains a dependency (section 3, item 2).
The step-by-step for changing and redeploying a dedicated endpoint is in [[wiki/syntheses/qwen-endpoint-redeploy-runbook]] (a candidate for the endpoint lifecycle hook of section 4, item 4).

## 6. Recheck when
After the next new provider or model: add its quirks here and update the rating (60% stands after the pilot: the model side worked, the surrounding automation is unchanged).
