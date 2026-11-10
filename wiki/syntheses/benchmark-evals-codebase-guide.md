---
type: synthesis
created: 2026-10-29
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [codebase, guide, benchmark-evals, ray, runner, shim, onboarding, living-document]
---
# benchmark-evals codebase guide (living page)

**Purpose:** brief yourself on the code that runs the CyberGym-E2E evaluations: what each file does, how a run flows, what exists only on our VM, and what we changed. **It is kept current:** every time we change code, the changelog at the bottom and the affected sections are updated in the same commit. Last verified against: owner's `main` `c845c38` (2026-11-05; PRs #1 and #2 merged), our PR branch `ray-isolation-stagger-spread` `dfa33e4`, upstream harness `d0ae0f0` (see section 8).

Related: [[wiki/syntheses/aws-vm-concurrent-setup-reference]] (the single-VM runner and its measured behaviour), [[wiki/syntheses/ray-autoscaler-build-plan]] (the autoscaler work), [[wiki/syntheses/two-vm-ray-cluster-setup]] (the manual two-node cluster).

## 1. The big picture
```
manifest.json ──► cybergym-eval run ──► one Ray task per (task × mode) ──► execute()
                    (cli.py)                                                (worker.py)
                                                                                │ subprocess
                                                                                ▼
                                         upstream cybergym-e2e/scripts/run_agent.py
                                         (Docker: agent container + 4 grading stages)
                                                                                │
                       state: SQLite (db.py)   artifacts/<execution_id>/  (local disk)
```
Two layers: the **runner** (`benchmark-evals`, a small Ray scheduler, owned by the project's maintainer) and the **upstream harness** (`cybergym-e2e`, the benchmark itself: Docker builds, the agent, grading). Our VM additionally runs a **metering shim** between the agent and the model API.

## 2. The runner package, `src/cybergym_eval/`
| File | Lines | Role |
|---|---|---|
| `config.py` | 107 | `load_config` validates the manifest, sets defaults, loads `.env`, derives firewall domains. `build_specs` creates one `RunSpec` per task × mode; `execution_id` = hash(config, task, mode), so the same manifest always yields the same IDs. |
| `cli.py` | 346 | Commands `prepare`, `preflight`, `model-check`, `run`, `status`, `report`, `recover`, `trajectory-html`. Core: `run()`. *(branch `shared-postgres-state` adds `--source local|postgres` to `status`, `report`, `recover` and `run --resume`, the command `sync-check`, and a driver that survives lost tasks; see [[wiki/syntheses/shared-postgres-state-design]].)* |
| `worker.py` | 158 | `execute()` is the Ray task: builds the harness command (`_command`), runs it with a deadline, normalises `summary.json` (`normalize_summary`), writes `result.json`, updates the DB. |
| `db.py` | 84 | SQLite table `executions`: `register`, `mark_running`, `mark_finished`, `rows`. |
| `pgstore.py` *(branch `shared-postgres-state`)* | 279 | Optional shared Postgres copy of the observations: schema, retrying store, gzip artifacts with SHA-256 read-back, usage, node metrics, atomic spend counter. Off unless `CYBERGYM_DATABASE_URL` is set. See [[wiki/syntheses/shared-postgres-state-design]]. |
| `prepare.py` | 60 | Pulls build images by digest (`DEFAULT_IMAGE`), starts the squid firewall, downloads task data from the Hugging Face dataset. |
| `trajectory_viewer.py` | 683 | Agent logs to HTML. Standalone. |
| `tests/test_runner.py` | 298 | Pytest; the best executable description of intended behaviour. |
| `scripts/` | | `bootstrap_ec2.sh` (uv, Python 3.12 envs, patches, CLI), `patch_cybergym.py` (idempotent patches to the upstream checkout), `sync_ec2.sh`, `remote_probe.sh`. |

## 3. How a run flows
For what the upstream harness does inside one execution (agent steps, then stages S1 to S4), see [[wiki/syntheses/cybergym-agent-and-validation-walkthrough]].

**`run()` (cli.py)**
1. `preflight`: upstream checkout and venv, Docker CLI and daemon, `vm.mmap_rnd_bits == 28`, memory ≥ 8 GiB, each task's `config.toml` and data files, HF token if data is missing, model credentials. Refuses to start if any check fails.
2. Register every spec as `pending`; `--resume` skips ones already `passed`.
3. Start Ray: `--address local` starts a private instance with `benchmark_slot = benchmark_slots`; any other address joins a cluster.
4. Submit one task per spec: `num_cpus = task_cpus`, `resources = {benchmark_slot: 1}`, `max_retries = 0` (a failed task is never retried).
5. Print each result as it arrives; exit 1 if any task is `benchmark_failed`, `infra_error` or `interrupted`. *(branch `shared-postgres-state`)* a task that dies without returning becomes an `infra_error` (recorded locally and in Postgres) instead of crashing the driver.

**`execute()` (worker.py)**
1. Stagger wait (if `start_stagger_seconds > 0`).
2. Create `artifacts/<execution_id>/`, remove stale `runner.log` and `result.json`.
3. `mark_running` (hostname recorded).
4. Run `run_agent.py <task> --mode <e2e|patch-only> --agent ... --timeout ...` as a subprocess, output to `runner.log`.
5. Read the newest `summary.json`, normalise, write `result.json`, `mark_finished`.
   *(branch `shared-postgres-state`, only when `CYBERGYM_DATABASE_URL` is set)* also mirror state and result to Postgres, heartbeat every 30 s while the harness runs, upload the artifacts, read everything back and compare, and report `observations_synced` in the returned result.
6. Deadline exceeded becomes `interrupted`; any exception becomes `infra_error`.

**Pass rule:** stages 3 and 4 must pass, plus stages 1 and 2 in `e2e` mode (they are skipped in `patch-only`).

**`recover`** looks at rows stuck in `running`: first a `result.json`, then an upstream `summary.json`, then a trajectory log containing "PATCH VALIDATION PASSED"; otherwise the row becomes `stale_running`. It reads only the local disk.

## 4. Manifest keys that matter
Required: `benchmark_root`, `work_root`, `tasks`, `modes` (`e2e` / `patch-only`), `agent`, `model_provider` (`anthropic`, `bedrock`, `openai-compatible`; `codex` requires `openai-compatible`). Defaults: `task_cpus` 4, `benchmark_slots` 1, `max_attempts` 1, `agent_timeout_seconds` 5400, `task_deadline_seconds` 34200, `use_firewall` true, `aws_region` us-east-1. Added by our PR branch: `start_stagger_seconds` (0), `scheduling_strategy` (""). Our VM manifests also use `shim_url`, `shim_port`, `spend_cap_usd`, `gate_enabled`, `gate_start`, `env_file`.

## 5. State and artifacts
SQLite file `work_root/state/runs.sqlite3` (WAL mode) plus `work_root/artifacts/<execution_id>/{runner.log, result.json, upstream/...}`. Both are **node-local**: in a multi-node cluster each node keeps its own, and only the driver's printed output sees every result. This is the central obstacle for autoscaling (shared state is stage 5 of [[wiki/syntheses/ray-autoscaler-build-plan]]).

## 6. The upstream harness (`~/cybergym-e2e`)
`scripts/run_agent.py` (1233 lines) is the real entrypoint: agent, prompt, Docker orchestration, four stages. `validate.py` and `utils.py` support it; `scripts/firewall/` (squid proxy with a domain allowlist, internal Docker network `cybergym-internal`). `projects/<project>/<task>/` holds `config.toml`, `compile.sh`, `prepare.sh`, `run_poc.sh`, `test.sh`, `patch.diff`; task data (`src.tgz`, `poc.bin`, `crash.log`) comes from the HF dataset into `data/`. 139 projects present. Pinned to `d0ae0f0` with local patches to `install_codex.sh` and `run_agent.py`. Agent run cost is dominated by Docker builds plus four grading containers that rebuild the project.

## 7. What exists only on our VM (not in the owner's repo)
| Where | What |
|---|---|
| `worker.py` (+76 lines) | `_shim_call`, `_container_shim_base` (agent containers reach the shim through the Docker gateway), per-execution key and cap from the shim, `_start_slot` and `_read_gate` (the concurrency gate) |
| `db.py` | `claim_slot`: atomic "may I start?" for the gate |
| `tools/llm_shim.py`, `llm_shim_new.py` | metering proxy between the agent and the model: per-key and total USD caps, token tallies, one JSON log line per request; Anthropic format on `/v1/messages` and OpenAI Responses on `/v1/responses` (for Codex). The `_new` file adds key preloading and gpt-oss experiment switches. |
| `tools/responses_chat.py`, shim switch `UPSTREAM_API=chat` (new, local copy only, not yet on the VM's live `tools/`) | translates Codex's Responses calls to Chat Completions and back so models that Bedrock serves only on chat can be used; see [[wiki/syntheses/qwen-bedrock-responses-translation]] |
| `tools/controller.py` | the concurrency controller we built and dropped |
| `tools/psilog.py`, `sampler.py`, `watchdog.py` | PSI logger, system sampler, memory/swap guard |
| `config/*.json` | our manifests (smoke, ramp, e2e, calibration) |
| `tools/model_registry.py`, `tools/models.toml`, `tools/start_shim.sh`, `tools/push_vertex_token.py` (local copy outside Git, deployed to the VM) | the string registry (`model@provider`; providers bedrock, openrouter, vertex, vertex-endpoint, `vertex-dedicated` added 2026-11-05 for an endpoint with its own DNS name), the bridge that starts the shim for any reference, and the Mac-side one-hour token pusher; see [[wiki/syntheses/model-registry-design]] section 14 and [[wiki/syntheses/plug-and-play-model-support]] |
| shim additions in `tools/llm_shim_new.py` and `tools/responses_chat.py` (same copy) | per-call total stream cap `UPSTREAM_STREAM_TOTAL_S`, `StreamTranslator.abort()`, chunk-kind statistics, token-file reload; tests `test_responses_chat.py`, `test_shim_stream_failures.py`, `test_model_registry.py` (137 pass across 14 files on 2026-11-04) |
| `tools/mem_sampler.py`, `tools/fetch_task_data.py` (same copy) | 30-second memory, load and container sampler into the Postgres `node_metrics` table; data and image prefetch per manifest (`--images-only`) |
| `tools/grader_bench.py` (in this vault repository, not the runner) | compares the harness's validation (a fresh container per stage, each repeating setup and builds) with a variant that shares a prepared image and one patched-build image; runs on the VM, no model; see [[wiki/syntheses/grader-shared-images-experiment]] |
| `tools/qwen_endpoint_probe.py`, `tools/qwen_ops/` (in this vault repository, not the runner) | probe for a Qwen endpoint (`cache`, `conversation`, `residency`, `decode`, `agents --counts --turns --start-words`, `needle`) and the operating scripts of the 2026-11-05 tests (suite runner, monitor, watcher, DNS-pinned shim restart); how to use them: [[wiki/syntheses/qwen-endpoint-redeploy-runbook]] |
These live on the VM (and are baked into the AMI's `tools/`), not in the owner's repo or the PR.

## 8. Status of each copy of the code
| Copy | Where | State |
|---|---|---|
| Owner's `main` | private repo `prescera/benchmark-evals` | `c845c38` ("added gcp file", the endpoint script `src/gcp/manage_endpoint.py`), after **PR #1** (`ray-isolation-stagger-spread`, merged 2026-10-27) and **PR #2** (`pr/postgres-store-and-race-fix`, merged 2026-11-02); no PR open; the repository has no `tools/` folder, so the shim, translation layer, registry and sampler are not in it |
| Our PR branch `ray-isolation-stagger-spread` | **merged as PR #1 (2026-10-27)** | `dfa33e4`: private local Ray, `prepare --skip-firewall`, `start_stagger_seconds`, `scheduling_strategy`, plus 4 tests; 17 tests pass |
| Our branch `shared-postgres-state` | local; its content was merged as **PR #2 (2026-11-02)** from the branch `pr/postgres-store-and-race-fix` (`215ae51`); earlier state: | `69560b4`: optional shared Postgres store (write path with read-back verification and heartbeat; `--source postgres` reads; dead-worker handling in the driver; `recover --source postgres`; `sync-check`), 29 new tests, 46 pass in the suite; shim budget, metric streaming and hosting not built |
| VM working copy | `~/benchmark-evals` on the primary VM | **Now contains the Postgres branch merged in** (2026-10-30): `pgstore.py`, a merged `worker.py` and the branch `cli.py`, plus its own shim integration, gate (`db.claim_slot`), tools and manifests; 58 tests pass on the VM; backups `*.bak-pre-pg` beside it; running Ray processes still hold the old code until restarted |
| Our branch `vm-live-2026-10-30` | local only, on top of `shared-postgres-state`, not pushed | **a Git record of what ran on the VM**: the VM's own `worker.py`, `db.py`, `config.py` (shim integration, concurrency gate), `tools/`, the manifests and two VM-only tests; verified identical to the VM (43 files, 0 differ) and 67 tests pass with a real Postgres; secrets excluded; a record, not a PR candidate (see `VM_SNAPSHOT.md` in the branch) |
| Local runner copy (registry, shim additions, sampler, prefetch, tests) | `spark/amit-repo/vm-copy-2026-11-01/benchmark-evals` on the study owner's Mac, **outside Git**; code archive kept next to the run logs | the newest copy of the runner `tools/` and tests; the VM's `tools/` matches it for the files deployed; no commit exists (design note in [[wiki/syntheses/platform-automation-and-architecture]]) |
| Upstream harness | `~/cybergym-e2e` | `d0ae0f0` + local patches |
| AMI v3 copy | baked into the worker/head image | runner as of 2026-10-30, Python 3.12.15 (matches the head); v2 deleted |

## 9. Try it (read-only first)
```
cybergym-eval preflight --config config/<manifest>.json
cybergym-eval status    --config config/<manifest>.json     # rows from the local SQLite
cybergym-eval report    --config config/<manifest>.json
cybergym-eval run       --config config/<manifest>.json --address local    # spends model money
```
Suggested reading order: `config.py`, `cli.py::run`, `worker.py::execute`, `db.py`, `tests/test_runner.py`, a manifest, then `run_agent.py`.

## 10. Where scaling touches the code
The Ray task boundary is `execute()`. Per-node assumptions to remove for a cluster: local SQLite and `artifacts/`, a per-node shim and per-node budget, absolute paths (same user and layout on every node, which the AMI provides), manifests that must exist on the head. See [[wiki/syntheses/ray-autoscaler-build-plan]] and section 8 of [[wiki/syntheses/ray-ec2-scaling-study]].

## 11. How this page is kept current
On any code change (runner, shim, tools, manifests, upstream patches, AMI contents): update the affected section above, bump `updated`, add a changelog line, and re-check the "Status" table's commit hashes. A change not reflected here is a bug in this page.

## Changelog
| Date | Change |
|---|---|
| 2026-10-29 | Page created from a read of `config.py`, `cli.py`, `worker.py`, `db.py`, `prepare.py` (owner's `main` `d88f145` plus our branch) and the VM-only files. Corrections noted: `prepare.py` pulls the base image by digest, which is pullable (an earlier AMI note said otherwise; fixed in [[wiki/syntheses/ray-autoscaler-build-plan]]). |
| 2026-10-29 | PR branch `ray-isolation-stagger-spread` (`dfa33e4`) pushed to the owner's repo: private local Ray instance, `--skip-firewall`, `start_stagger_seconds`, `scheduling_strategy`, tests. |
| 2026-10-30 | Branch code merged into the VM's working copy and deployed (the VM copy has shim and gate changes the PR branch lacks, so `worker.py` was merged by hand, `cli.py` taken from the branch); new VM-only test `tests/test_pg_with_shim.py` (shim usage reaches the Postgres result); `start_worker_services.sh` added for workers; 58 tests pass on the VM: [[wiki/syntheses/ray-autoscaler-build-plan]] section 18. |
| 2026-10-30 | Postgres 16 now runs as a container on the head VM (private address only, scram auth, restart always, volume, tested restore); `CYBERGYM_DATABASE_URL` added to the VM's `.env`; no code change. The branch code is not deployed on the VM yet: [[wiki/syntheses/shared-postgres-state-design]] section 5d. |
| 2026-10-30 | Branch `shared-postgres-state` (`69560b4`): reads from Postgres (`--source postgres`), the driver survives lost tasks, `recover --source postgres` (heartbeat based), `sync-check`; 14 new tests, mutation-checked: [[wiki/syntheses/shared-postgres-state-design]] sections 5 to 5c. |
| 2026-10-30 | New local branch `shared-postgres-state` (`c2ec6e0`): optional shared Postgres store for observations (`pgstore.py`, hooks in `worker.py` and `cli.py`, extra `postgres` in `pyproject.toml`), tested against a real Postgres; design and open items in [[wiki/syntheses/shared-postgres-state-design]]. Runner behaviour is unchanged unless `CYBERGYM_DATABASE_URL` is set. |
| 2026-10-31 | Local branch `vm-live-2026-10-30` created: a Git snapshot of the VM's working copy (shim integration, gate, tools, manifests, two tests), verified identical to the VM and tested (67 pass); the VM itself is not a Git repository, so this is the only record of that code. The "VM working copy" row above now points to it. |
| 2026-10-30 | Dummy scale-up and scale-down passed on real EC2 with the v3 image (worker joined in about 86 s, 20 slots across 2 nodes, idle stop to a stopped node); no runner code change: [[wiki/syntheses/ray-autoscaler-build-plan]] section 17. |
| 2026-10-30 | AMI v3 built with Python pinned to 3.12.15 and verified (13/13); v2 deleted; recipe's bootstrap pinning fixed (3 bugs): [[wiki/syntheses/ray-autoscaler-build-plan]] section 16. No runner code change. |
| 2026-10-30 | First dummy scale-up test: the worker could not join (Python patch mismatch 3.12.16 vs 3.12.15); recipe and verify script now pin the Python version; AMI v2 must be rebuilt: [[wiki/syntheses/ray-autoscaler-build-plan]] section 15. No runner code change. |
| 2026-10-29 | Autoscaling head started on the existing VM (port 6381) with `prepare_cluster.py`; no runner code change: [[wiki/syntheses/ray-autoscaler-build-plan]] section 14. |
| 2026-10-29 | Added `stop_workers.sh` (worker-only teardown; replaces `ray down` for the existing-VM head): [[wiki/syntheses/ray-autoscaler-build-plan]] section 12. No runner code change. |
| 2026-10-29 | Cluster YAML template and env example rewritten for a head on the existing VM (no runner code change): [[wiki/syntheses/ray-autoscaler-build-plan]] section 11. |
| 2026-10-29 | The owner attached the EC2 role `RayHeadRole` to the primary VM (the head will run there); no code change. See [[wiki/syntheses/ray-autoscaler-build-plan]] section 10. |
| 2026-10-29 | Added a pointer to the autoscaler run procedure and its open gaps (images and data per node, shared state, shim and budget): [[wiki/syntheses/ray-autoscaler-build-plan]] section 9. No code change. |
| 2026-10-29 | AMI v2 built and verified: runner source with `tools/`, upstream at `d0ae0f0`, squid proxy with `restart=always`, no secrets. |
| 2026-11-01 | Responses-to-Chat translation layer (`tools/responses_chat.py`, shim env `UPSTREAM_API=chat`) plus 14 tests, developed in a local copy of the VM source outside Git; verified on real Bedrock with two Qwen models. Not deployed. See [[wiki/syntheses/qwen-bedrock-responses-translation]]. |
| 2026-11-05 | **Catch-up entry** (changes of 2026-11-02 to 2026-11-05 were not logged here when made): model registry and `start_shim.sh` bridge, `vertex-dedicated` provider (2026-11-05), shim stream cap and chunk statistics, token-file reload and Mac token pusher, `mem_sampler.py`, `fetch_task_data.py --images-only`, hunks in the upstream harness patch list (`aws-vm-data/deepseek100/upstream-local-patches.diff`), and in this vault `tools/qwen_endpoint_probe.py` (`agents --counts --turns --start-words`, `needle`) and `tools/qwen_ops/` (suite runner, monitor, watcher, DNS-pinned shim restart). Sections 7 and 8 updated; none of it is in the owner's repo. |
| 2026-11-05 | Status table corrected: PR #1 and PR #2 are merged, owner's `main` is `c845c38`; the code still outside the owner's repository is everything under `tools/` (shim, translation layer, registry, bridge script, sampler, prefetch, token tools), the shim hooks in `worker.py` (about 70 changed lines), `db.py` (concurrency gate) and `config.py` (a few keys), and most of their tests. Pull request plan: [[wiki/syntheses/pull-request-plan]]. |
| 2026-11-06 | Added `tools/grader_bench.py` (validation experiment, no change to the runner or to the upstream harness) and the page [[wiki/syntheses/grader-shared-images-experiment]]; the PR branch `pr/model-shim-and-chat-translation` was pushed to the owner's remote the same day ([[wiki/syntheses/pull-request-plan]] section 5). |
| 2026-11-09 | VM-only changes (not in any repository): `tools/llm_shim_new.py` and `tools/model_registry.py` now send the registry's `allow_fallbacks` to OpenRouter (it was hardcoded true; new env `PROVIDER_ALLOW_FALLBACKS`, default 1 keeps the old behaviour) and `tools/responses_chat.py` plus the shim log the answering provider per call (`provider` in each log record); registry entry `glm-5.3-flash@openrouter` added to `tools/models.toml` (backups `*.pre-fallbacks`, `*.pre-provlog`, `models.toml.pre-glm-flash`). New helper scripts in the vault `tools/`: `repro_check.py` (patched-build reproducibility, [[wiki/syntheses/grader-shared-images-experiment]] section 4f), `openrouter_probe.py` and `shim_tool_test.py` ([[wiki/syntheses/glm-5.3-flash-openrouter-setup]]). The PR branch `pr/model-shim-and-chat-translation` does not contain these two shim fixes yet. |
| 2026-11-10 | Three more optional harness patches on the head VM (not in any repository; backups `scripts/utils.py.pre-limits`, `.pre-aptmirror`, `scripts/run_agent.py.pre-setupA`): `tools/patch_container_limits.py` (per-container memory and process limits, `CYBERGYM_CONTAINER_MEM_GB`, `CYBERGYM_CONTAINER_PIDS`, logs `CONTAINER_OOM`), `tools/patch_apt_mirror.py` (`CYBERGYM_APT_MIRROR`, rewrites apt sources in every container), and the setup A patch gained a per-node concurrency cap (`CYBERGYM_SHARED_MAX_CONCURRENT`); new `tools/container_janitor.py`. The cluster template now mounts the patched `utils.py` and `run_agent.py` and the janitor on every worker and starts the janitor. See [[wiki/syntheses/glm-5.3-flash-100-task-run]] sections 4 and 5. |
