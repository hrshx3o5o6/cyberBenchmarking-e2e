---
type: synthesis
created: 2026-11-05
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [pull-request, benchmark-evals, shim, translation-layer, registry, upstreaming, plan, living-document]
---
# Pull requests we can raise against the owner's repository (plan, 2026-11-05)

**No pull request is open.** A combined branch for PR 1, 3 and 4 (and the hooks) is pushed to the owner's remote as `pr/model-shim-and-chat-translation` (section 5); the PR itself is for the study owner to open. The repository is the owner's (`prescera/benchmark-evals`, private); by the study owner's standing instruction nothing is pushed there without their go-ahead, and the owner has to accept the content. Code map and status of each copy: [[wiki/syntheses/benchmark-evals-codebase-guide]] (sections 7 and 8).

## 1. Where things stand (checked 2026-11-05)
- Owner's `main` is `c845c38` ("added gcp file": `src/gcp/manage_endpoint.py`). **PR #1** (Ray isolation, stagger, scheduling strategy; branch `ray-isolation-stagger-spread`) merged 2026-10-27 and **PR #2** (optional shared Postgres store and the SQLite lock race fix; branch `pr/postgres-store-and-race-fix`, with a description drafted in `spark/amit-repo/PR_DESCRIPTION_postgres-store-and-race-fix.md`) merged 2026-11-02. No PR is open.
- The owner's repository has **no `tools/` folder**: the metering shim, the Responses-to-Chat translation layer, the model registry, the sampler and the prefetch tool exist only in our local runner copy `spark/amit-repo/vm-copy-2026-11-01/benchmark-evals` (outside Git; the VM is not a Git repository either) and on the VM.
- Differences of the local copy from the owner's `src/`: `worker.py` (about 36 changed lines: per-execution key and cap from the shim, containers reach the shim through the Docker gateway, the concurrency gate), `db.py` (about 23 changed lines: `claim_slot`), `config.py` (a few keys: shim address, port, spend cap, gate).
- The two upstream-harness patches (provider `openai-compatible`; undo the offline GitHub rewrite before the Codex install) are **already in the owner's repo** as `scripts/patch_cybergym.py`; an optional PR to the public upstream (`sunblaze-ucb/cybergym-e2e`) is separate.

## 2. Proposed pull requests, in order
| # | Pull request | Content (in the local copy) | Depends on | Evidence we can cite | Before raising |
|---|---|---|---|---|---|
| 1 | **gcp: faster serving arguments** | change `VLLM_ARGS` in `src/gcp/manage_endpoint.py`: add `--enable-prefix-caching`, drop `--enforce-eager`; ideally make the argument list overridable instead of edited; note that `--max-num-seqs=16` changed nothing and `--kv-cache-dtype=fp8` gave +25% to +50% warm cache | nothing | decode 9.2 to 28.3 tokens/s; repeat prompt 9 s to 0.5 s ([[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]], [[wiki/syntheses/qwen-capacity-levers-test]]) | smallest and best evidenced: a good first one; the file is the owner's own |
| 2 | **Standalone tools**: `tools/mem_sampler.py` (30-second memory, load and container sampler into the Postgres `node_metrics` table) and `tools/fetch_task_data.py` (data and image prefetch per manifest, `--images-only`) | two files plus `test_mem_sampler.py`, `test_fetch_task_data.py` | PR #2 for the Postgres table | memory findings of the 100-task run ([[wiki/syntheses/deepseek-100-task-run-report]]) | independent of the shim |
| 3 | **Metering shim and runner hooks** | `tools/llm_shim_new.py` (per-key and total caps, token tallies, one JSON log line per request, `UPSTREAM_STREAM_TOTAL_S` call cap, token-file reload), `start_worker_services.sh`, the hooks in `worker.py` and `config.py` (`shim_url`, `shim_port`, `spend_cap_usd`), `test_shim_*`, `test_runner` | nothing; behaviour unchanged when `shim_url` is unset (same pattern as PR #2) | used for every run since October, including the 100-task DeepSeek run | drop dead code (concurrency gate and `claim_slot` if not wanted, `controller.py`, `psilog.py`, `watchdog.py`); remove the Bedrock-specific defaults; README section |
| 4 | **Responses-to-Chat translation layer** | `tools/responses_chat.py` (non-streaming and streaming translation, tool calls, abort, chunk statistics), shim switch `UPSTREAM_API=chat`, `test_responses_chat.py`, `test_shim_chat_mode.py`, `test_shim_auto_adapter.py`, `test_shim_stream_failures.py` | 3 | lets Codex use chat-only models: verified on real Bedrock with two Qwen models ([[wiki/syntheses/qwen-bedrock-responses-translation]]), then DeepSeek V4.1 Flash on Vertex (100 tasks) and Qwen3.8-27B on a dedicated endpoint (6 real tasks) | note the known quirk that reasoning chunks produce no stream events ([[wiki/syntheses/qwen-two-task-pilot]] section 7.3) |
| 5 | **Model registry** | `tools/model_registry.py`, `tools/models.toml` (providers bedrock, openrouter, vertex, vertex-endpoint, vertex-dedicated; no secrets, only references), `tools/start_shim.sh`, tests (`test_model_registry`, `test_shim_env`, `test_shim_key_sources`, `test_shim_google_auth`) | 3 (and 4 for chat models) | `model@provider` strings drove Kimi, DeepSeek and Qwen runs ([[wiki/syntheses/model-registry-design]], [[wiki/syntheses/plug-and-play-model-support]]) | prices in `models.toml` are our assumptions: mark them as examples or leave them out |
| 6 | **Token tools (temporary)**: `tools/push_vertex_token.py` (Mac-side token pusher), `tools/token_relay.py` | two files and tests | 5 | kept a one-hour Google token on the head for the Vertex runs | optional; say plainly they are a stopgap until a service account exists (the biggest platform gap) |
| 7 | **Ray autoscaler on EC2**: cluster template, `prepare_cluster.py`, `render_cluster.py`, worker start scripts, `stop_head.py` and `stop_workers.sh` (the files under `~/autoscaler` on the VM) | a folder of scripts and templates | none | autoscaled runs of 30 and 100 tasks ([[wiki/syntheses/ray-autoscaler-build-plan]], [[wiki/syntheses/autoscaled-vertex-run-plan]]) | the largest cleanup: account-specific ids (images, networks, roles) must be parameters; discuss with the owner first |

## 3. Preparation common to all
1. **Put the local copy under version control.** It has no history. Create branches from the current owner's `main` and apply the PRs as commits in the order above (the stale local branch `vm-live-2026-10-30` is an older snapshot, not the base to use).
2. Run the full test suite (137 pass across 14 files on 2026-11-04) per PR, against a real Postgres where tests need one.
3. Scan for account, instance, image, network ids, addresses and keys (public mirror of our notes; the owner's repo is private but reviewers change).
4. One PR description per PR in the format of the earlier one (why, what changed, reading order, testing, what does not change when the feature is off).
5. Ask the owner which of 3 to 7 they want in their repository at all; items 6 and 7 may stay in ours.

## 4. What I would do first
Raise (or offer) PR 1 as a small, measured first step, then PR 2, then 3 to 5 as a series (shim, translation, registry), because 4 and 5 are only reviewable once 3 is merged. All of it needs the study owner's go-ahead before anything is pushed.

## 5. The combined, trimmed PR (built locally 2026-11-06; branch pushed to the owner's remote the same day, no pull request opened yet)
Decision of the study owner: club the gcp change, the shim and the translation layer into one PR, and cut the size by moving optional features to the next PR.
- **Branch:** `pr/model-shim-and-chat-translation` in `spark/amit-repo/benchmark-evals` (on top of the owner's `main` `c845c38`), four commits in review order: (1) gcp serving arguments, (2) `tools/responses_chat.py` with 16 tests, (3) `tools/llm_shim.py` with 6 tests, (4) runner hooks (`worker.py`, `config.py`), 3 tests and a README section. Description drafted in `spark/amit-repo/PR_DESCRIPTION_shim-and-chat-translation.md`.
- **Size:** 1,245 added lines: 740 code, 480 tests, 25 docs (the merged Postgres PR was 1,361). The first estimate for the same content was about 1,800.
- **How it was cut:** shim 627 -> 399 lines, translation 317 -> 298, hooks without the concurrency gate (+42/-1), tests 25 new instead of about 800 lines of mixed ones.
- **Moved to the next PR:** Google ADC auth and upstream-key reload (about 120 shim lines), the per-call total time cap and chunk statistics (also in the translator), `UPSTREAM_API=auto` detection (about 35 lines), `TOKEN_CAPS_ONLY`, 429 retry with jitter, OpenRouter provider order, the Responses input fix, and the model registry.
- **Tests:** whole suite 59 passed, 17 skipped (Postgres tests need a database), including the 25 new ones.
- **Caveat:** the files are a trimmed copy of the shim that ran on the VM, covered by tests but not yet used for a real task; a smoke run on the VM before raising is advisable.
- **Commit style:** author only the study owner, no assistant co-author lines, as in the earlier PR commits (dfa33e4, 215ae51).
