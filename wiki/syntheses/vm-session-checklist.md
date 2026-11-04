---
type: synthesis
created: 2026-11-03
updated: 2026-11-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [runbook, vm, smoke-test, codex, qwen, deepseek, vertex, checklist, living-document]
---
# VM session checklist: smoke tests and the 100-task blockers

One focused session on the head VM, before the 100-task study ([[wiki/syntheses/qwen-100-task-study-protocol]]). Goal: prove the whole path with cheap stand-in models so that, once the Qwen3.8-27B endpoint can do tool calls, the only new variable is the model. Stop and bring-up steps: [[wiki/syntheses/vm-stop-and-bring-up-runbook]]. Flow background: [[wiki/syntheses/how-a-run-works-on-the-vm]], [[wiki/syntheses/the-shim-step-by-step]]. Status: plan, nothing run.

## Ground rules
- No keys or tokens in chat or in Git. Secret-copying commands are run by the owner of the session, not typed by me.
- Do not touch the live shim or the other Ray heads; test shims run on spare ports.
- Every spend step has a cap; stop at the cap and report.
- Write down what happened as it happens (results page, log, index); back up Postgres before stopping the VM.

## A. Before starting the VM (on the Mac)
1. Local suite passes (the shim, translator, auto-detect, Google auth and registry tests).
2. Decide the three models for the session: smoke 1 `qwen3-coder-30b@bedrock`, smoke 2 `deepseek-v4.1-flash@vertex`, (later) the 27B endpoint.
3. For smoke 2 only: generate a one-hour Google access token on the Mac (`gcloud auth application-default print-access-token`) at the moment it is needed and copy it into a file on the VM yourself; the token expires in about an hour and cannot be refreshed. Never copy the Google login file to the VM.

## B. Start and bring up
Start the instance; note the public IP; follow the bring-up steps in the runbook (Docker, Postgres, firewall proxy, `cybergym-internal` network, the live shim carrying its spend, our Ray head). Check: Postgres healthy, the live shim's `/health`, no stray workers.

## C. Deploy our files (no change to the running shim)
1. Back up the current `tools/llm_shim_new.py` next to itself with a dated name.
2. Copy `llm_shim_new.py`, `responses_chat.py`, `model_registry.py`, `models.toml` into `~/benchmark-evals/tools/`; copy the new tests into `tests/`.
3. Run the shim and registry tests on the VM (needs a venv with pytest; for Google tests the stub package is used, no login).
4. The live shim process keeps running its old code until restarted: do not restart it in this session unless a run needs it. New code is exercised through spare-port shims only.
5. Record what changed (guide page, log).

## C2. Make workers start the shim from a registry reference
Today the worker start command in the cluster config runs `start_worker_services.sh <raw model> <cap>`, which has Bedrock written into it: any worker would start a Bedrock shim whatever the run is for. Change it so the config passes a model reference to `start_shim.sh`.
1. In the cluster template, replace the `{{SHIM_MODEL}}` placeholder in the worker start command with `{{MODEL_REF}}` and call `tools/start_shim.sh {{MODEL_REF}} {{WORKER_SHIM_TOTAL_USD or tokens}}`; add the matching entries to the untracked local env file the render script reads.
2. Render and prepare the config, then restart our head by exact process ids (no workers may be up; never `ray up`, `ray down` or a plain `ray stop`).
3. Test with one worker: force a launch with the dummy-demand script (`max_workers` 1), then check on the worker: the shim answers, its `/health` shows the expected target model and adapter, and the worker joined and took a task.
4. **Mind the credential.** A provider whose credential is not on the worker (Google, until the service account or federation exists) makes the worker's shim fail to start, so the start command fails and the worker never joins; the autoscaler may keep launching new workers. For such a run set `max_workers` to 0 (head only), or watch the instance count and stop the loop by hand. Before any launch, confirm that `max_workers` and the worker start command match the provider.
5. Keep the old script in place until this works; record the result in [[wiki/syntheses/model-registry-design]] and the codebase guide.

## D. Smoke 1: Codex through the translator on Bedrock (stand-in model)
Setup: a shim on the Docker gateway at a spare port (not 4100), settings taken from the registry route for `qwen3-coder-30b@bedrock`: upstream, bearer auth with the Bedrock key, `UPSTREAM_API=auto`, `TARGET_MODEL=qwen.qwen3-coder-30b-a3b-v1:0`, placeholder prices, total cap 2 USD and per-key cap 2 USD. A one-task manifest: `md4c/arvo_31332` (not in the 100), `patch-only`, `agent: codex`, `model_provider: openai-compatible`, `shim_url` and `shim_port` for the spare port, Postgres on.
Run: `preflight`, then `run`; watch the shim log live.
| Pass if | Fail signals to look for |
|---|---|
| Codex finishes by itself after several tool calls; every shim line is status 200 with `adapter: chat`; usage and cost counted; a `summary.json` exists and the harness graded it; Postgres row `observations_synced: true` | Codex rejecting the stream (an event we do not send), "invalid input" on turn two (reasoning items), "announce and stop" turns, freeform `apply_patch` returned wrongly, 4xx or 5xx |
Whether the model solves the task does not matter here. Expected cost under 1 USD.

## E. Smoke 2: Codex on DeepSeek V4.1 Flash through Vertex
Same shape as D, started with `VERTEX_PROJECT=<project> TOKEN_FILE=<file> start_shim.sh deepseek-v4.1-flash@vertex tokens` (no price is entered, so token and request caps apply and cost shows as 0). `TOKEN_FILE` turns the registry's Google login into a bearer key read from a file holding the one-hour token; everything else (`auto` format detection, the chat and responses paths, the endpoint) comes from the registry. The owner of the session creates the token file with one command that pipes the token straight over ssh, so it never appears in chat: `gcloud auth application-default print-access-token | ssh <vm> 'umask 077; cat > <file>'`. Must finish inside the token's hour. Afterwards delete the token file. Only the head can run this (no credential on workers).
Extra to note: the 15-second detection delay seen on the first call; whether Codex's tool use is more reliable than on the Bedrock Qwen model; no cached tokens reported.

## E-result. Smoke 2 done (2026-11-03): DeepSeek V4.1 Flash on Vertex, passed
Run from the head VM with a one-hour access token copied by the session owner (never in chat), the shim from the scratch folder on a spare port, Codex on `md4c/arvo_31332` patch-only, 30-minute agent limit.
| Check | Result |
|---|---|
| Harness result | `passed`, `all_stages_passed: true`, whole task 182 s (agent 116 s) |
| Shim | 24 calls on the task's key (27 in the log including 3 from the earlier connectivity check), all status 200, adapter `chat`, 0 errors or exceptions |
| Tokens (the task's key) | fresh input 328,585; cache reads 95,744 (Vertex did report cached tokens on a long conversation, unlike the tiny earlier calls); output 3,496; largest context 23,142 |
| Cost | shown as 0 (no price entered; token and request caps applied, no dollar cap) |
| Postgres | row `passed`, `observations_synced: true` |
| Cleanup | token file deleted, test shim stopped by exact process id, backup taken and copied to the Mac with a matching checksum |
What it proves: the whole path works with the translator in the middle, Codex's streaming and tool calls were accepted, the registry route drove the shim (`start_shim.sh` with a token file), and the result reached Postgres. What it does not prove: `auto` detection (the registry says chat for this model, so chat was used from the start), multi-node (see below), the Bedrock stand-in (not run), the 27B endpoint. The VM's SSH connection stalled twice during the day and recovered each time.
Multi-node: this run used a private local Ray instance on the head; the autoscaler was not running, and autoscaled workers would have no Google token and would start the old Bedrock-only shim (item C2 still to do). For Vertex runs before a service account exists, either head only (`max_workers` 0) or a token relay from the Mac.

## F. Checks for the 100-task run (read-only unless noted)
1. **What a fresh worker holds:** images (only the two shared base images are baked in; others are pulled automatically by the harness's `docker run` on first use) and task data. Task data reaches a worker through the cluster template's worker setup, which runs `prepare` for the manifest (that pulls every image of the manifest too: fine for light manifests, too heavy for the random 100; see [[wiki/syntheses/autoscaled-vertex-run-plan]]).
2. **Image sizes for the sample:** the 67 non-shared images of the 100 (list from `random100_manifest.json`); estimate sizes from the registry manifests without pulling, then decide: pull on the head only, bake into a larger image, or per-node pull at launch. Check free disk against the head's 227 GB of images.
3. **Read the upstream harness** (`run_agent.py`, `validate.py`, `utils.py`, the firewall module) for the file-by-file wiki page.
4. **Validity screens** on the 100 (protocol section 4): byte-compare PoCs with tarball files, scan scripts for bug wording, list file modification times.

## G. Optional: a small autoscaled run
10 tasks, patch-only, the stand-in model of smoke 1, to see wall time, cost per task and failures on the new path with real autoscaling. Use tasks that are not in the 100 (for example the ten that never started in the 30-task test, after checking they are not in the sample). Cap 10 USD total.

## H. Wrap-up
1. Delete the Google token file; stop the spare-port shims by exact process id.
2. Check no workers exist (the autoscaler terminates idle ones; verify with boto3 on the VM).
3. Take a Postgres backup, copy it to the Mac, verify the checksum.
4. Update the wiki: what passed, what failed, costs, times; commit and push.
5. Stop the instance (not terminate).

## I. Stop rules
Any spend cap hit; any step failing twice for an unexplained reason; the token hour running out mid-run; the VM becoming unresponsive. Stop, report, do not improvise.
