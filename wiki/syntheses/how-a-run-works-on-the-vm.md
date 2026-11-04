---
type: synthesis
created: 2026-11-01
updated: 2026-11-01
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [runbook, vm, ray, shim, postgres, autoscaler, benchmark-evals, onboarding]
---
# How a run works on the VM: what is executed under the hood

Plain-language runbook for what happens when a task run is started from the Claude Code session. Code detail is in [[wiki/syntheses/benchmark-evals-codebase-guide]]; the autoscaler in [[wiki/syntheses/ray-autoscaler-build-plan]]; the shared database in [[wiki/syntheses/shared-postgres-state-design]]; a worked example in [[wiki/syntheses/autoscaler-30-task-test]].

## 0. How commands reach the VM
Every action is an SSH command from the Mac: `ssh -i <private key> <user>@<head VM> '<command>'`. Longer scripts are sent on standard input. Nothing runs on the Mac except reading and editing files. Never paste keys or tokens into chat; secrets live in `config/.env` on the VM.

## 1. Prepare the VM (once, and after changes)
| What | Where / how |
|---|---|
| Runner source | `~/benchmark-evals`, own Python environment `.venv` (Python pinned to the exact patch version the cluster uses) |
| Upstream harness | `~/cybergym-e2e`, pinned to commit `d0ae0f0` plus local patches |
| Task data | downloaded from Hugging Face by `cybergym-eval prepare` |
| Docker images | base-builder images are baked into the worker image (AMI). Other per-task images are pulled by `prepare` (which the cluster template's worker setup runs for the whole manifest) **and also automatically by the harness**: every container is started with a plain `docker run`, which pulls a missing image (not counted in the agent timer; a failed pull fails the task). Corrected 2026-11-03; an earlier version of this page said the run code never pulls |
| Firewall | a Squid proxy on an internal Docker network, started by `prepare` (agents can reach only the model endpoint) |
| Secrets | `config/.env` (model key, shim master key, database URL, Hugging Face token); the Ray head and worker start commands load it so every Ray process inherits it |

## 2. Services that must be up before tasks start
1. **Metering shim** (`tools/llm_shim_new.py`, on the Docker gateway address of every node). Issues one capped key per task, forwards model calls to the provider, counts tokens, enforces per-key and total dollar caps, writes one log line per call. Restarted or re-capped with `swap_shim.py` (keeps live keys).
2. **Postgres** container on the head: results, artifacts, heartbeats.
3. **Ray head with the autoscaler**, started by hand, never with `ray up` or `ray down`: `render_cluster.py` fills the cluster YAML from an untracked local env file, `prepare_cluster.py` applies Ray's defaults, then `ray start --head --autoscaling-config=<yaml>` on its own port next to the other Ray heads on the same VM. Stopping it uses exact process ids (`stop_head.py`), never a pattern kill.

## 3. Launch a run
1. Write a manifest `config/<name>.json`: task list, modes (`e2e` or `patch-only`), agent (`codex` or Claude Code), model provider, model, base URL, timeouts, spend cap.
2. `cybergym-eval preflight --config <manifest>`: checks Docker, memory, `vm.mmap_rnd_bits`, each task's files and data, credentials; refuses to start if anything fails.
3. `cybergym-eval run --config <manifest> --address <head>`, detached with output to a log file. The driver registers every task as pending and submits one Ray task per (task, mode): 4 CPUs and one `benchmark_slot` each, no retries. (Exact `--address` value for our head is not recorded in these notes; see the build-plan page.)

## 4. What one task does on a worker
1. Mark running; stagger wait if configured.
2. Run `run_agent.py <task> --mode <e2e|patch-only> --agent ... --timeout ...` as a subprocess.
3. That starts the agent container and the build container behind the firewall, with the model base URL pointing at the shim.
4. The agent reads the code and writes a PoC and a patch; the harness grades them in fresh containers, stages S1 to S4, and writes `summary.json`.
5. The worker normalises it to `result.json`, mirrors state and artifacts to Postgres, heartbeats every 30 s, then reads everything back and reports `observations_synced`.
6. Deadline exceeded becomes `interrupted`; any exception becomes `infra_error`.

## 5. Scaling and monitoring
- A task with no free slot is pending demand; the autoscaler launches workers from the AMI (about 40 s to launch, about 2 min to join), each running `ray start --address=<head>`. Idle workers are terminated after 3 minutes.
- Watching: `cybergym-eval status --source postgres`, the shim's per-key info, per-node CPU and memory (`nodestats.py`), the driver log. Afterwards `report`, `recover` (heartbeat-based for lost tasks) and `sync-check` against Postgres.
- Rule: terminate workers only after the data is confirmed in Postgres.

## 6. What changes for Qwen on Bedrock
Manifest model and base URL, plus shim setting `UPSTREAM_API=chat` so Codex's Responses calls are translated to Chat Completions; see [[wiki/syntheses/qwen-bedrock-responses-translation]].
