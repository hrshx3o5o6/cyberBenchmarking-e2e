---
type: synthesis
created: 2026-11-10
updated: 2026-11-10
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [architecture, plug-and-play, benchmark-adapter, exploitgym, cybergym, planning, living-document]
---
# One engine, pluggable benchmarks: a plan for CyberGym and ExploitGym (2026-11-10)

**Status: plan and brainstorm, no code changed, nothing decided beyond the principles in section 1.** It extends the three-layer idea of [[wiki/syntheses/platform-automation-and-architecture]] (section 3) with what the GLM runs ([[wiki/syntheses/glm-5.3-flash-100-task-run]]) and the ExploitGym reading ([[wiki/syntheses/exploitgym-architecture-and-integration]], [[wiki/syntheses/exploitgym-code-walkthrough]]) have shown. The model side is already plug and play ([[wiki/syntheses/model-registry-design]]: `model@provider`); this page is about the benchmark side.

## 1. The goal in one sentence, and the principles
Pick a benchmark and a model in one run file; the engine does the rest, and everything that is specific to CyberGym (modes e2e or patch-only, prompt style, the four-stage grader, `patch_cybergym`-style patches) or to ExploitGym (families, defence profiles, controller, scorer, KVM) lives behind that choice and nowhere else.
1. **Config, not code, for a run.** One file says what to run; the engine reads only the parts it owns.
2. **The engine knows nothing about benchmarks.** It sees tasks with a resource profile, a way to run one, and an outcome. No benchmark name inside it.
3. **An adapter owns everything about its benchmark:** tasks, preparation, harness and agent runner, grading, node requirements, validity screens, protocol defaults, sensitivity of its outputs.
4. **Outcomes are uniform; details are not.** Every task ends as `model_result` (with a score and a benchmark-specific stage map) or `infrastructure_failure`; the stage map keeps its own labels.
5. **Guards live in the engine and apply to every benchmark** (the ones we had to learn the hard way, section 6).
6. **Two data points before freezing an interface:** design from CyberGym and ExploitGym together; do not freeze an adapter interface from CyberGym alone (the earlier note on this).
7. **Every change reversible and default-off**, as with the setup A, container-limit and apt-mirror patches.

## 2. What is generic and what is CyberGym-specific today
| Piece (file or tool) | Layer today | Where it belongs |
|---|---|---|
| Ray scheduling, slots, driver loop, resume, recover (`cli.py`) | engine, but with CyberGym wording | engine |
| Postgres store, heartbeats, artifacts, node metrics (`db.py`, `pgstore.py`, `mem_sampler.py`) | engine | engine |
| Shim, key per execution, spend cap, provider pin, registry | model layer | model layer (stays) |
| Autoscaler template, AMI, worker start | engine, with CyberGym assumptions (image pulls, ASLR 28, one pool) | engine + node profiles |
| `RunSpec(task, mode)`, `modes`, `prompt_style`, `use_firewall`, `benchmark_root` | CyberGym keys in the generic config | adapter options |
| `_command` (builds `scripts/run_agent.py ...`), `normalize_summary` (stage1 to stage4) | CyberGym | adapter |
| `prepare.py` (pull build images), preflight task checks (`projects/<task>/config.toml`, data files) | CyberGym | adapter |
| `patch_cybergym.py`, `patch_setup_a.py`, container-limit and apt-mirror patches | CyberGym harness patches | adapter `setup()`, versioned |
| Credit guard, janitor, disk cleanup, container limits | one-off tools | engine guards |

## 3. The run file (proposed shape)
```
run:
  name: glm-flash-100-r1
  benchmark: cybergym            # or exploitgym ; the only line that selects the adapter
  tasks:  { list: tasks/random100.txt }        # or { sample: {n: 100, seed: 20261103, rule: ...} }
  model:  glm-5.3-flash@openrouter             # registry string, unchanged
  agent:  codex                                # harness axis: which agent runner (adapter says which are valid)
  limits: { agent_minutes: 90, cost_per_task_usd: 10, attempts: 1 }
  nodes:  { head_slots: 4, workers: 2, slots_per_worker: 6 }     # engine; defaults come from the adapter's profile
  guards: { container_memory_gb: 40, pids: 2048, janitor: true, credit_guard: true, min_free_disk_gb: 90 }
  options:                                     # read ONLY by the chosen adapter
    cybergym:   { mode: e2e, prompt_style: iterative, validation: shared, apt_mirror: auto }
    exploitgym: { family: user, defense_profile: exp.none, scorer: { enabled: true, model: ... }, kernel_defense: default }
```
Rules: unknown keys under `options` of another benchmark are an error (no silent ignore); everything has a default from the adapter, so a CyberGym run file stays as short as today's; the whole resolved file (with versions and the dataset revision) is stored with the run (reproducibility record, section 6).

## 4. The adapter contract (what the engine may ask)
| Method | Meaning | CyberGym today | ExploitGym |
|---|---|---|---|
| `describe()` | name, version, valid agents, task id format, sensitivity of outputs | `cybergym-e2e@d0ae0f0` plus patches | `exploitgym@a8029e4`; outputs are exploits: `sensitivity=high` |
| `list_tasks(selection)` | the task set | `projects/*/*` listing, sampler | `data/task_ids/*.txt` (869: 502 user, 181 V8, 186 kernel) |
| `node_profile(tasks)` | what a node must have | build images, ASLR 28 | ASLR off or on per profile, controller and firewall services, static toolbox, KVM for kernel tasks |
| `prepare(tasks, node)` | data and images, idempotent, prefetch | `prepare.py`, `fetch_task_data.py` | `pull_images.py`, `setup_data.sh` (baked into the AMI) |
| `resource_profile(task)` | CPU, memory, disk, expected minutes, slots needed | 1 slot, about 4 GB, ffmpeg heavy | about 8 CPUs and 24 GB, 2 to 3 per 16-vCPU worker |
| `preflight(config)` | screens before launch | task config and data present, ASLR bits | six host checks of `pre_run.py`, images present |
| `run_task(task, ctx)` | run one task under the engine's limits; `ctx` = model endpoint and key, work dir, limits, node facts | `run_agent.py` call, setup A grading | `run_agent.py --max-workers 1`, then the scorer as a second step |
| `classify(raw)` | `model_result` (score, stage map) or `infrastructure_failure` (reason) | stages, no patch, no PoC; 402, node death | flag captured, scorer verdict, `on_target`; controller errors |
| `validity_screens()` | checks that a task is usable | PoC non-empty, task data present | image exists, no network escape |
| `report(rows)` | tables and viewer | `per_task.csv`, trajectory viewer | `results.json` of the leaderboard format (per-model usage and latency from the shim) |
Engine-supplied context keeps adapters small: a per-execution model key from the shim, a work directory, the limits, a logger, and a way to start a container with the engine's guards.

## 5. Node profiles: the infrastructure side
A **profile** is a named bundle the autoscaler renders into a node type: AMI, instance type and size, disk, resources (`slot`, `kvm`), host settings (sysctls such as ASLR), per-node services to start, and what must be prefetched. Examples: `cybergym-worker` (today: m7i.4xlarge, 1 TB, ASLR default, shim, janitor), `exploitgym-userv8-worker` (ASLR off, controller and firewall, toolbox in the image), `exploitgym-kernel-worker` (an `m8i` size with nested virtualization on, `kvm` resource; see [[wiki/syntheses/exploitgym-architecture-and-integration]] section 13). Rules: **a node serves one benchmark profile** (CyberGym's preflight needs the default ASLR, ExploitGym's default profile needs it off, and both start a Squid named `cybergym-proxy`); a run asks the autoscaler for the profile its adapter names; the head runs the control plane for any benchmark (and, by choice, a few tasks).

## 6. Engine guards that must work for every adapter (lessons of 2026-11-09 and 10)
| Guard | Why (what happened) | Today |
|---|---|---|
| per-container memory and process limit | one agent container took a whole node (run 1) | harness patch, env switches |
| orphan-container janitor, with a low-disk image cleanup on small disks | the runaway outlived its task; the head's disk filled with 49 GB images | script on each node |
| credit and provider guard | out-of-credit 402s drained the queue into fake failures; a naive guard killed 16 good tasks | script on the head; needs a realistic-size probe and must **pause, not kill**, so running tasks survive |
| infrastructure failures retried by the engine (once, after the node is healthy), model failures never | runs 1 and 4 needed manual reruns of 88 and 49 tasks | manual (`--resume`, new manifest) |
| teardown timeout on `docker rm` | three head tasks held slots 97 minutes in a stuck removal | not applied |
| backup of results, logs and node samples off the VM at run end (and per-node shim logs shipped before a node scales down) | worker shim logs were lost with the workers | manual |
| a record of the run: resolved run file, versions (harness commit, patches, dataset revision, agent version), dates | the DeepSeek rerun record had to be reconstructed | written by hand into the vault |
Credit and rate-limit knowledge belongs to the **model layer** (provider type), not to a benchmark: the probe and the meaning of a 402 differ per provider (OpenRouter's credit and in-flight limits, Bedrock throttling, Vertex quotas).

## 7. The agent (harness) axis
CyberGym's harness installs Codex (pinned 0.118.0) inside the task container; ExploitGym ships three runners (Claude Code 2.1.119, Codex 0.120.0, Gemini CLI 0.37.2) and its own LiteLLM or proxy modes. So the agent is part of the pair **(benchmark, agent runner)**, with the adapter declaring which agents it supports and how each reaches the model (our shim answers the Responses route for Codex and the Messages route for Claude Code). The model remains independent of both. In the run file `agent` stays a plain key and the adapter validates it.

## 8. Migration, in steps that each ship alone (and fit the PR plan of [[wiki/syntheses/pull-request-plan]])
0. **Freeze today's behaviour:** a small regression run on CyberGym (a few cheap tasks) whose resolved settings and stage results are the reference after every step.
1. **Introduce the adapter seam without moving behaviour:** `benchmark: cybergym` (default), the CyberGym specifics behind an interface in one package; the old manifest still loads unchanged (all current keys map to `options.cybergym`).
2. **Uniform outcome and result schema:** add `benchmark`, `profile` and `outcome` columns next to the existing JSON `result`; the viewers and reports read the stage map through the adapter.
3. **Node profiles in the autoscaler template** (render per profile; today's single profile becomes `cybergym-worker`).
4. **Promote the guards into the engine** with the run-file `guards` block (the patches become adapter `setup()` steps and engine options, versioned); add pause-not-kill and engine-side infrastructure retry.
5. **ExploitGym adapter, smallest first:** 2 to 3 user tasks on one node of its own profile (ASLR off, controller, firewall, shim as the LiteLLM); then the scorer; then V8; then the kernel pool (`m8i`, nested virtualization). A smoke run per step with the cost estimated first.
6. **Reports and sensitivity:** the ExploitGym report format; access rules for exploit outputs (never the public vault or site).

## 9. Open decisions and risks
- **How abstract, how soon:** steps 1 to 3 are low risk and useful on their own; step 4 changes how every run is guarded.
- **Where the code lives:** the owner's repository (`prescera/benchmark-evals`) versus our local copy; the PR plan and the owner's agreement come first.
- **Adapter language and packaging:** Python classes in the runner package (simplest) versus plugin entry points (later).
- **One Postgres for all benchmarks** (add `benchmark` columns) versus one per benchmark (simplest isolation, but two dashboards).
- **Scheduling across benchmarks:** one run at a time per pool is enough now; running both at once needs both pools funded and separate slot resources.
- **ExploitGym's own runner is a process pool** (`--max-workers`) and a controller per host: the adapter should call it one task at a time (`--max-workers 1`) and let the engine own parallelism; still to be shown end to end.
- **Unverified:** the KVM node type, the shim as ExploitGym's LiteLLM end to end, image sizes on disk, kernel boot time under nested virtualization, cost of a run, and the data license and access terms.
- **Not to do:** build the interface from one benchmark, move the shim or registry (they work), or mix benchmarks on a node.
