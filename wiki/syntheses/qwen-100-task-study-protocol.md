---
type: synthesis
created: 2026-11-03
updated: 2026-11-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [protocol, study, qwen3-8-27b, codex, 100-tasks, random-sample, vertex, draft, living-document]
---
# 100 random tasks, e2e, Qwen3.8-27B with Codex: protocol (DRAFT)

**Status: draft, nothing run.** Fixes the design before any scored run so results cannot be tuned afterwards; changes go in the deviations log at the end. Related: [[wiki/syntheses/study-1-protocol]] (the earlier, never-run design this borrows from), [[wiki/syntheses/vertex-qwen27b-endpoint-check]] (the model's endpoint), [[wiki/syntheses/model-registry-design]], [[wiki/syntheses/how-a-run-works-on-the-vm]].

## 1. Question
How does Qwen3.8-27B, driven by Codex, do on CyberGym-E2E (find the bug, write a PoC and a patch from source only) over a fixed random sample of 100 tasks?

## 2. Design (fixed)
| Factor | Setting |
|---|---|
| Tasks | the 100 in section 3 |
| Mode | e2e only |
| Attempts | 1 per task |
| Model | `Qwen/Qwen3.8-27B` on the team's self-deployed Vertex AI endpoint (`qwen3.8-27b@vertex-endpoint` in the registry). **Blocked** until the server has tool calling enabled (section 6) |
| Harness | Codex 0.118.0 (the version Study 1 pinned), through the metering shim; Codex speaks the Responses format and this endpoint serves chat, so the shim's translation layer is in the path and is recorded as part of the setup |
| Limits | 90 minutes per run (paper rule); a per-run token cap in place of a dollar cap, because the endpoint bills by the hour, not per token (decision needed, section 8) |
| Prompt | repo default `--prompt-style iterative` |
| Network | repo firewall on |
| Harness code | upstream `d0ae0f0` with our local patches; runner as merged to the owner's main plus the shim changes; the registry digest and the shim version are recorded with every result |

## 3. The sample
Seeded uniform random, not stratified. Script `wiki/syntheses/aws-vm-data/tools/sample_random100.py`; list `wiki/syntheses/aws-vm-data/random100_tasks.txt`; metadata `random100_manifest.json` there.
- **Pool:** the 920 tasks minus the five hand-picked pilot tasks (chosen as small and easy; md4c is also the smoke-test task) = 915.
- **Order:** the pool sorted by `sha256("20261103:random:<task>")` ascending (no RNG library, so the list is the same on any Python).
- **Sample:** the first 100 in that order that pass the infrastructure gate (config exists locally; the dataset lists `src.tgz`, `poc.bin`, `crash.log`). One was replaced: `libcoap/arvo_26371` has no `crash.log` in the dataset, so the next task took its place. This was decided on infrastructure evidence alone.
- **List sha256:** `8acd0cc32c7a457f3d5e0dc478a14aea07113d55de71806844af43e790317118`. Extending it to 150 or 200 later keeps the first 100 unchanged.
- **Replacement rule:** a task that cannot be built or validated in our environment is replaced by the next unused task in the order, before any scored run only; never after a model has run on it.

### What this sample looks like (computed from the task configs)
| Property | Value |
|---|---|
| Projects | 43 (a random draw clusters: ffmpeg 13, ghostscript 9, mruby 7, binutils 6, libxml2 5, libavc 4) |
| Kind | 69 arvo, 31 oss-fuzz |
| Language | 89 C++, 11 C |
| Fix size (changed lines) | median 7, 90th percentile 53, maximum 3,856; 12 tasks at 50 lines or more |
| Build images | 30 tasks use the shared base-builder images; 39 need a per-task `n132/arvo` image; 17 a per-task `cybergym/oss-fuzz` image; 14 a per-project `cybergym/e2e` image; **67 distinct non-shared images** |
| Overlap with earlier work | 3 tasks with Study 1's 20; 5 with the AWS 50-task seeded sample |
Compared with a stratified draw (100 projects, one task each, 42 shared images, 8 oss-fuzz images), this sample is **heavier**: more per-task images, 17 oss-fuzz images (some around 50 GB each), and big projects such as ffmpeg whose builds and grading are slow. A random draw is the honest estimate of performance across the benchmark; the stratified one spreads over projects. The choice was made by the study owner.

## 4. Validity screens (before any scored run, no model involved)
Taken from the validity mechanisms found earlier ([[wiki/syntheses/cross-model-observations]]): compare each task's PoC with the files in its source tarball; scan helper and build scripts for wording that names the bug; list file modification times for the later-modified marker; read the endpoint's context-window limit and check it is large enough for the harness prompt. Any task that fails goes through the replacement rule above.

## 5. Capacity, time and cost (arithmetic, not measurements)
Full analysis, with the measured context sizes from the earlier Qwen3.8-27B runs (median call about 85,000 tokens, largest about 172,000, 23% of calls over 131,072) and the estimated bottlenecks: [[wiki/syntheses/qwen27b-serving-capacity-analysis]]. In short: output speed is the likely limit; for 100 e2e tasks the generation alone is roughly 6 to 38 hours on one A100 (estimate); at most about 3 to 6 agents fit in the cache memory at once.
- **Time:** 100 tasks of up to 90 minutes is up to 150 slot-hours. At the head's 10 slots that is up to about 15 hours; with autoscaled workers (30 slots) about 5 hours. Earlier Qwen3.8-27B e2e runs had a median of about 91 minutes, so many tasks will run to the limit.
- **The real limit is probably the model server (see the analysis page):** the endpoint is one A100 with one replica in Singapore, called from a VM in Virginia. Concurrent agents queue behind it. To be measured with a concurrency test before the full run (section 6, gate 5).
- **Where the credential is:** only nodes holding a Google credential can call Vertex; today that would be the head only (10 slots), until a service account or federation exists.
- **Cost:** not per-token. The endpoint's hourly price on the project times the hours it stays deployed. Not known to us.
- **Images:** 67 non-shared images to pull; the head holds 227 GB of images today; fresh workers would hold only the two shared base images. See [[wiki/syntheses/how-a-run-works-on-the-vm]] for why workers do not pull images themselves.

## 6. Gates before the full run
1. The endpoint's tool calling works (the three-turn streaming tool test passes against it).
2. The same test passes through the shim in chat mode with the endpoint's own settings, and the thinking text is handled (server reasoning parser, or a deliberate strip rule).
3. Real Codex smoke tasks on stand-in models pass (Bedrock Qwen, DeepSeek on Vertex), see [[wiki/syntheses/vm-session-checklist]].
4. The 67 images are pulled where they are needed, or a pull strategy is agreed.
5. A concurrency test of the endpoint (5 to 10 parallel streams): latency, tokens per second, errors.
6. A Google credential path for the nodes that will run it (service account or federation).
7. The budget, including the endpoint's hourly cost, approved by the project owner.
8. The validity screens (section 4) done and any replacements logged.

## 7. Fallbacks, only with the owner's agreement
Qwen3.8-27B through OpenRouter (used in earlier batches, provider price swings of 5 to 6 times seen); a Bedrock Qwen3 model as a clearly labelled stand-in, whose results must not be compared with the 27B.

## 8. Open decisions
| Decision | State |
|---|---|
| Per-run cap: token cap instead of dollars | proposed, not agreed |
| Total budget and who approves it | open |
| Endpoint replicas, GPU type, context length (at least 131,072) and hours it stays up | with the owner; the endpoint currently has a 2,048-token context and no tool calling |
| Credential path (service account or federation) | requested |
| Whether to keep the five pilot tasks excluded | proposed: yes |

## 9. Deviations log
(empty)
