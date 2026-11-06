---
type: synthesis
created: 2026-11-04
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [architecture, automation, brainstorm, registry, benchmarks, exploitgym, living-document]
---
# How automated is the run system, and where it should go (brainstorm, 2026-11-04)

**Status: discussion, no decisions beyond section 1, nothing built from this page.** Context: the autoscaled DeepSeek run on Vertex ([[wiki/syntheses/autoscaled-vertex-run-plan]], [[wiki/syntheses/deepseek-100-first-pass-observations]]) showed how much of a run still depends on a person. Related designs: [[wiki/syntheses/model-registry-design]], [[wiki/syntheses/how-a-run-works-on-the-vm]], [[wiki/syntheses/the-shim-step-by-step]].

## 1. Direction stated by the study owner
- End goal: plug in a model and have the system run it over any number of tasks automatically.
- Multiple benchmarks are planned: CyberGym now, maybe ExploitGym next, others later. Keep that in mind in every design choice; not to be built yet.
- One cloud (AWS) is fine for now.
- What must be easy: the **model and its provider**, which the string registry (`model@provider`) already addresses.

## 2. How automated it is today
| Layer | Today | Gap |
|---|---|---|
| Model and provider | Registry string gives endpoint, API format, key source, prices, timeouts | Credentials (Mac token refresher is a single point of failure; no service account), automatic capability probe, a per-model record of known quirks |
| Task selection | Seeded sampler script | Validity screens, replacements and dataset gates are manual (empty PoCs and a PoC inside a source tree were found by hand) |
| Capacity planning | By hand: slots, disks, vCPU quota, image sizes | Derive slots and disk from measured memory per task and image sizes; check quotas first |
| Provisioning | Autoscaler adds and removes workers; head, shim and relay are started by hand | Head and service lifecycle, expiring AWS login, quota failures (`VcpuLimitExceeded` limited pass 2 to the head plus 2 workers) |
| Scheduling | Driver submits all tasks at once, no retries, no admission control | Biggest gap (section 4) |
| Credentials | Mac-side one-hour token pushed every 30 minutes | Service account or federation |
| Monitoring | Ad hoc scripts, a person reads them; memory sampler (new) writes to Postgres | One watcher with alerts and automatic pauses |
| Results and reports | Postgres rows, wiki entries written by hand | Automatic report; durable archive of trajectories and logs (they sit on node disks and are lost with the node) |
| Cost and safety | Per-run caps work | Total cap, automatic teardown |
Summary: the model plug-in is about 70% there; the run around it is about 20% automated (scaling, task execution, limits, grading and storage are automatic; starting, watching, recovering, preparing, cleaning up and recording are manual).

## 3. Proposed split into three layers (idea, not agreed)
```
 run spec ──► ENGINE (generic) ──► per task ──► BENCHMARK ADAPTER ──► agent in container
 (model ref,   plan, provision,        │            (CyberGym,              │
  benchmark,   schedule, retry,        │             ExploitGym, ...)       ▼
  task set,    monitor, report         ▼                                 shim ──► MODEL LAYER
  limits)                        results store                          (registry: model@provider)
```
- **Model layer:** the registry. Add capability fields filled by a probe (tool calling, context length, parallel burst, a cost sample), a credential plug-in per provider type, and a known-quirks record per model (for DeepSeek on Vertex: truncated tool-call JSON about 1 call in 30, 180 s silence limit, 600 s per-call cap). The agent (Codex or Claude Code) is already served by two shim routes; whether it belongs to the model or the benchmark protocol is open.
- **Benchmark adapter:** what the engine would ask of any benchmark: list tasks and metadata; prepare a task (data, images); run one task under limits and return a result; classify it (pass, model failure, infrastructure failure); give a resource profile (memory, disk, time per task); run validity screens; state protocol defaults (limits, attempts). Today these answers are spread over the runner, helper scripts and wiki pages.
- **Engine:** plans nodes and slots from the adapter's resource profile, provisions, runs a reconcile loop, watches, reports, tears down.

## 4. The most important gap: scheduling
Both big failures of the first pass came from the driver rather than the model plumbing: one node's memory exhaustion failed every task queued behind it (62 tasks at once), and nothing retried them. Target: a declarative run spec; a loop that continues until every task has a final state (a model result, or an infrastructure failure it retries on its own); infrastructure failures requeued, model failures never rerun (the protocol rule); new starts held back when a node's memory is low (the repo's adaptive gate `tools/controller.py` exists but is switched off).

## 5. Suggested build order (by value)
1. Reconcile loop with infrastructure retry, small submission waves and memory-aware admission.
2. A model onboarding command (the probe).
3. Credential fix (service account).
4. One-command lifecycle with a watcher and alerts.
5. Archive of logs and trajectories; automatic reports.

## 6. Cautions
- Build or study a **second adapter before freezing the interface**: ExploitGym's shape (container per task, grading, resources) is unknown; extract seams one at a time while CyberGym keeps running.
- Store a **digest of the run spec** with every result so runs stay comparable across models, benchmarks and protocol versions.
- Benchmarks differ most in the shape of the grader and the time per task; these drive scheduling and capacity.

## 7. Open questions
- Is the agent part of the model choice or of the benchmark protocol?
- Should a protocol (limits, prompt style, validity rules) be a versioned object referenced by the run spec? The protocol pages already play that role.
- Does ExploitGym use the same container-per-task pattern?
- How hands-off: approve the cost before each run, or fully automatic within a budget?

## 8. Model and provider side, assessed (added 2026-11-05)
The model plug-in layer is the part closest to done; its concrete status, costs of adding a model or provider, and the ordered gaps are in [[wiki/syntheses/plug-and-play-model-support]].
