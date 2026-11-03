---
type: synthesis
created: 2026-11-02
updated: 2026-11-02
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [design, ideas, abstraction, cli, studies, benchmark-evals, living-document]
---
# A plug-and-play layer over the runner (ideas, to come back to)

**Status: ideas only, discussed on 2026-11-02, nothing built.** Builds on [[wiki/syntheses/model-registry-design]] (the model and provider part) and starts from the pain points in [[wiki/syntheses/switching-provider-and-harness-by-hand]].

## Goal
A person writes one short study file and runs a few commands. They never touch shim environment, cluster YAML, start scripts or firewall rules. The runner (the owner's `benchmark-evals`) stays the engine; this is a thin layer on top, so his repo is unchanged.

## Sketch of the study file
```yaml
study: qwen-100-e2e
tasks:   {sample: 100, seed: 20261016, set: stratified}
modes:   [e2e]
runs:
  - {model: kimi-k3@bedrock, harness: codex}
  - {model: glm-5.3@openrouter, harness: codex}
limits:  {per_run_usd: 10, total_usd: 300, minutes: 90}
cluster: {max_workers: 3}
```

## Commands
| Command | Purpose |
|---|---|
| `doctor` | machine checks: Docker, Python version, secrets present (names only), provider reachable, VM and Postgres up |
| `models find`, `models probe` | discover and test a model (see the registry design) |
| `plan` | dry run: resolves everything, prints what would happen, spends nothing |
| `up` | start or verify the cluster: shim, Postgres, Ray head with the autoscaler |
| `run` | submit the study |
| `status`, `report` | live view and results tables |
| `down` | tear down workers safely, optionally stop the head |

## Abstractions underneath
1. **Models and providers**: the registry (`model@provider` resolves to endpoint, secret, API format, prices, pinning).
2. **Harness adapters**: a table (codex means Responses format and OpenAI-style variables; Claude Code means Messages format and Anthropic-style variables). The layer picks the adapter between harness format and provider format automatically: pass-through, responses-to-chat, messages-to-chat (the last does not exist yet).
3. **Task sets**: named, versioned, hashed samples (the Study-1 order); also computes which Docker images and data a sample needs.
4. **Cluster lifecycle**: the stop and bring-up runbook ([[wiki/syntheses/vm-stop-and-bring-up-runbook]]) as scripts; cluster config generated from the study file.
5. **Image and data prefetch**: make sure workers have what the sample needs, or warn up front (the per-task image gap found when planning the 100-task run).
6. **Secrets**: one place and one check; names only in any file.
7. **Budget and safety**: a study-level dollar cap kept in Postgres (built, not wired) and a per-task time cap (not built).
8. **Run record**: every result stores the resolved model route, harness adapter chain, registry hash, task-set hash and code version.

## What `plan` would print
Resolved route per model, adapter chain, whether a probe result is on file, images and GB to pull, an estimated cost and time range from earlier runs, and blockers (missing secret, unvetted model, no price for a dollar cap).

## What stays hard
A new provider with unusual behaviour (chat-only models, expiring Google tokens) still needs a person once to probe it and add a profile. First-time secrets and account quotas cannot be automated. The layer is more code to keep tested, and a registry mistake could send a run to the wrong model, hence the recorded route.

## Suggested build order (only what the 100-task study needs)
1. The registry. 2. Harness adapter table and shim routing by key. 3. Study file and `plan`. 4. Cluster `up` and `down` scripts. 5. Image prefetch. 6. Study-level budget. Do not build everything before the first 100-task run: the first run shows which layers matter.

## Open
Which layers matter most, and what to cut; where the package lives; how much of this goes to the repo owner as pull requests later.
