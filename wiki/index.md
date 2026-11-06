---
type: index
---
# Wiki Index

Entrypoint. One line per page: link — summary. Claude keeps this current on every change.
Live views: [[wiki/dashboard]]. History: [[wiki/log]].

## Sources

- [[wiki/sources/cybergym-e2e]] — ICML'26 benchmark: 920 OSS-Fuzz vulns, discovery→PoC→patch→tests; discovery is the bottleneck.

## Concepts

- [[wiki/concepts/end-to-end-vulnerability-lifecycle-evaluation]] — scoring chained security stages, not isolated ones.
- [[wiki/concepts/benchmark-construction-pipeline]] — 4-step OSS-Fuzz → agent-environment pipeline with expert validation.
- [[wiki/concepts/alternative-vulnerability-discovery]] — S3 vs S4 gap: agent fixes a different real bug.
- [[wiki/concepts/agent-harness-design-effects]] — Claude Code vs OpenHands/Codex/Gemini CLI cost & success.
- [[wiki/concepts/cross-run-feedback]] — fresh-context retry with failure feedback, +5–7 pts.
- [[wiki/concepts/capability-misrepresentation]] — agent claims success without (or against) verification; why scoring is execution-based. Seen in our pilot.

## Entities

- [[wiki/entities/oss-fuzz]] — Google continuous fuzzing; task source.
- [[wiki/entities/arvo]] — OSS-Fuzz vulns as reproducible Docker images.
- [[wiki/entities/cybergym]] — predecessor benchmark (PoC generation).
- [[wiki/entities/openhands]] — full-file-reading agent harness.

## Syntheses

- [[wiki/syntheses/cybergym-pilot-hunspell-52195]] — pilot log: 5 runs, 3 free open models, failure classes, numbers (2026-10-01).
- [[wiki/syntheses/hunspell-arvo-52195/00-overview]] — **per-task run folder:** one page per run (model, mode, host, S1-S4, cost, observations) for `hunspell/arvo_52195`; add one folder per new task.
- [[wiki/syntheses/batch-2-summary]] — **batch 2 results + GLM vs DeepSeek comparison:** deepseek-v4.1-flash on the same 5 tasks, both modes: pass counts, cost, per-task head to head, caveats.
- [[wiki/syntheses/batch-3-summary]] — **batch 3 results + three-model comparison:** qwen3.8-flash on the same 5 tasks, both modes: pass counts (patch-only 5/5, e2e 3/5), cost ($5.52, low cache reuse), two empty e2e runs, caveats.
- [[wiki/syntheses/batch-5-summary]] — **batch 5 results + five-model comparison:** kimi-k3 on the same 5 tasks: patch-only 5/5, e2e 4/5 valid (3/5 intended bug) after reruns, $32.39 (6x any other model), my caps invalidating two first runs, the libsndfile timestamp artifact, billing reconciled to the cent.
- [[wiki/syntheses/study-2-results]] — **Study 2 results:** vidoc-1 (GLM-5.3) on four tasks with Claude Code and Codex; 3 of 4 pass under each; validity findings (corpus PoC leak in skcms, build-script hint in arduinojson, context-window limit in htslib); descriptive harness comparison
- Study 2 task pages: [[wiki/syntheses/oatpp-oss-fuzz-391916478/00-overview]] · [[wiki/syntheses/skcms-arvo-6521/00-overview]] · [[wiki/syntheses/htslib-arvo-65383/00-overview]] · [[wiki/syntheses/arduinojson-arvo-24633/00-overview]]
- [[wiki/syntheses/study-2-protocol]] — **protocol (run 2026-10-17):** five-task comparison of Claude Code and Codex on Vidoc's free GLM-5.3-based `vidoc-1` endpoint; 50M-token quota math, per-run and total quota caps, tasks, preconditions
- [[wiki/syntheses/study-1-protocol]] — **DRAFT protocol, not yet run:** 3 models (Laguna S 2.1, Ling 3.0 Flash, Qwen3.8-27B) x 2 harnesses (Claude Code, Codex) x 20 seeded project-stratified tasks, e2e only; selection method and hashes, fixed settings, failure rules, analysis plan, preconditions
- [[wiki/syntheses/batch-7-summary]] — **batch 7 results + seven-model comparison:** qwen3.8-27b on the same 5 tasks: patch-only 5/5, e2e 2/5 (igraph, md4c), three 90-minute runs with no PoC, $4.98; cache share 96% on Wafer vs 19-40% for qwen3.8-flash on Alibaba
- [[wiki/syntheses/qwen-cache-investigation]] — **why qwen3.8-flash barely cached and what fixed it:** Alibaba reuses only the static prefix of a growing conversation (marker placement irrelevant), Wafer and DekaLLM cache the whole history; tests, numbers, open questions
- [[wiki/syntheses/batch-6-summary]] — **batch 6 results + six-model comparison:** minimax-m3 on the same 5 tasks: patch-only 5/5, e2e 2/5 (igraph, md4c), three 90-minute runs with no crash, $10.84; file-timestamp marker found on the bug file of all five tasks; billing check.
- [[wiki/syntheses/cross-model-observations]] — **observations across all six models:** results matrix, task-by-task e2e, shared behaviours, per-model distinctives, failure taxonomy, benchmark-validity findings (timestamp marker), process lessons, open questions.
- [[wiki/syntheses/all-runs-comparison]] — **every run compared (81 run pages, 9 models, 5 tasks):** totals by model, best-result grids for patch-only and e2e, per-task list of every run with stages/cost/minutes, cost and time extremes, spend per intended-bug pass. Generated from run-page frontmatter.
- [[wiki/syntheses/batch-4-summary]] — **batch 4 results + four-model comparison:** nemotron-3-super on the same 5 tasks, both modes: patch-only 2/5, e2e 0/5, six format-failure endings, $1.78, caveats.
- [[wiki/syntheses/nemotron-tool-call-format-failures]] — **Nemotron caveat:** runs that end with the next tool call written as raw text in a thinking block (format failure, not capability); how to report them.
- [[wiki/syntheses/batch-1-summary]] — **batch 1 results:** 4 tasks x both modes with glm-5.3-flash: first pass counts, cost, time, what it shows, caveats.
- [[wiki/syntheses/md4c-arvo-31332/00-overview]] — task folder: md4c (Markdown parser), glm-5.3-flash patch-only and e2e, both solved.
- [[wiki/syntheses/igraph-arvo-29408/00-overview]] — task folder: igraph (GML reader use-after-free), glm-5.3-flash runs.
- [[wiki/syntheses/libsndfile-arvo-27503/00-overview]] — task folder: libsndfile (ALAC decoder overflow), glm-5.3-flash runs.
- [[wiki/syntheses/libssh2-arvo-65212/00-overview]] — task folder: libssh2 (key-exchange off-by-one), glm-5.3-flash runs.
- [[wiki/syntheses/cybergym-vm-runs]] — **start here for the VM:** every run on the Azure x86 VM, which task, plain-language results, why S4 failed, cost.
- [[wiki/syntheses/cybergym-glm-5-3-flash-run-log]] — live log of the first paid-model runs (glm-5.3-flash via OpenRouter): protocol, caps, pre-run checks, cost expectations, results.
- [[wiki/syntheses/cybergym-bench-mac-setup-notes]] — Mac/Docker/firewall/shim gotchas and provider limits for running the benchmark.
- [[wiki/syntheses/benchmark-evals-aws-vm-parallelism]] — AWS VM: benchmark-evals replica, Kimi K3 patch-only on 20 seeded tasks (20/20 passed, $21), 2 vs 8 parallel runs on 16 vCPU (no breaking point found), spend-guard design, mistakes.
- [[wiki/syntheses/aws-vm-concurrent-setup-reference]] — AWS VM reference: how the concurrent setup works (Ray slots, staggered starts, Amit's Ray vs ours), the benchmark-evals codebase and our changes, shim/sampler/watchdog, state locations, runbook, gotchas, security notes.
- [[wiki/syntheses/ray-ec2-scaling-study]] — Scaling beyond one VM: Ray clusters + autoscaler on EC2 (concepts, scheduling, fault tolerance, security), options compared, getting a second instance, storage (EBS/ECR/S3/DB, why images are not shared), changes needed by phase, experiments to run first. Ideation only.
- [[wiki/syntheses/two-vm-ray-cluster-setup]] — Two-VM Ray cluster on EC2, step by step as done: AWS console steps (key pair, security groups), VM2 base setup, code copy, proxy/shim, token auth, head and worker commands, gotchas and mistakes, stop/pause.
- [[wiki/syntheses/two-vm-ray-test-observations]] — Two-VM Ray test results: default scheduling split 8/4 vs SPREAD 6/6 (Kimi K3, 12 tasks, all passed), Bedrock model-route sweep (only Kimi K3 and gpt-oss on Mantle support the Responses API), gpt-oss second-turn failure under Codex, SSH/IP-rotation findings, mistakes.
- [[wiki/syntheses/ray-autoscaler-build-plan]] — Ray autoscaler on EC2: how the AWS node provider creates instances (read from the 2.59.0 source: create_instances, tags, stop-vs-terminate, default SG/key/IAM), what our AWS access can do, the head's instance profile, templates and scripts written (cluster YAML validated offline, AMI recipe, dummy-demand job), stages 0 to 6.
- [[wiki/syntheses/benchmark-evals-codebase-guide]] — LIVING PAGE: briefing on the benchmark-evals runner and the VM-only additions (files, run flow, state, manifest keys, shim and gate, upstream harness, status of each code copy, how to try it) with a changelog; updated on every code change.
- [[wiki/syntheses/shared-postgres-state-design]] — Stage 5 design and first build: shared Postgres for run observations (write path with read-back verification, heartbeat, artifacts, usage, atomic budget), tests against a real Postgres, what is not built yet, stop-vs-terminate decision.
- [[wiki/syntheses/the-shim-step-by-step]] — LIVING PAGE: what the metering shim is for, its settings, routes, one model call step by step (auth, rewrite, translate, caps, send, usage, accounting, log), failure behaviour and limits
- [[wiki/syntheses/switching-provider-and-harness-by-hand]] — the current setup: what to edit by hand (manifest, shim environment, start script, secrets, cluster, network) to change provider, model or harness; pain points
- [[wiki/syntheses/plug-and-play-layer-ideas]] — LIVING PAGE (ideas only): one study file and a few commands (doctor, plan, up, run, down) over the runner; abstractions, what stays hard, build order
- [[wiki/syntheses/vm-session-checklist]] — LIVING PAGE (plan): one focused VM session before the 100-task study: deploy our shim files, two Codex smoke tests (Bedrock Qwen, DeepSeek on Vertex with a one-hour token), image and data checks, optional small autoscaled run, wrap-up and stop rules
- [[wiki/syntheses/autoscaled-vertex-run-plan]] — LIVING PAGE (plan only): the 100 random tasks with DeepSeek on Vertex across the Ray autoscaler without a service account: how images and task data really reach a node (corrected), the temporary token relay, phases, risks, open decisions
- [[wiki/syntheses/qwen-100-task-study-protocol]] — LIVING PAGE (draft, nothing run): 100 random tasks, e2e, Qwen3.8-27B with Codex on the self-deployed Vertex endpoint; the seeded sample and its profile, design, gates, capacity arithmetic, open decisions
- [[wiki/syntheses/deepseek-100-task-study-protocol]] — **protocol (draft):** 100 random e2e tasks, DeepSeek V4.1 Flash with Codex on Vertex; paper rules (10 USD, 90 min), setup disclosures, launch gates.
- [[wiki/syntheses/deepseek-100-first-pass-observations]] — **first pass of the 100 (2026-11-03):** 31 completed, 68 lost to node memory exhaustion; cause, the 52 queued failures, what worked, decisions.
- [[wiki/syntheses/deepseek-100-task-run-report]] — **report of the 100-task DeepSeek run (pass 2):** outcomes, time, money, model calls, memory and CPU per node, infrastructure, timeline, lessons; web version with one page per task in the run viewer.
- [[wiki/syntheses/platform-automation-and-architecture]] — **brainstorm:** how automated the run system is, the three-layer split (model / benchmark adapter / engine), build order, multi-benchmark and one-cloud direction.
- [[wiki/syntheses/qwen27b-serving-capacity-analysis]] — serving Qwen3.8-27B ourselves: measured context and token needs from the earlier runs, cache-memory arithmetic, bottlenecks on one A100 (output speed, cache, prompt processing, single replica, endpoint limits), what to ask for and measure
- [[wiki/syntheses/vertex-qwen27b-endpoint-check]] — access check of the self-deployed Qwen3.8-27B endpoint on Vertex AI: what it is (one A100, vLLM), what works (plain chat), what does not (tool calls need server flags), what would make it usable
- [[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]] — **Qwen3.8-27B on Vertex, before and after prefix caching and CUDA graphs (2026-11-04):** three configurations measured the same way (prefill, caching, warm capacity, decode, tool calls, concurrent agents), what it means for an agent run, open questions, next levers.
- [[wiki/syntheses/plug-and-play-model-support]] — **how plug-and-play are models and providers (2026-11-05):** the 5 providers and 7 models in the registry, what a new model or provider costs to add, what is still manual (quirks found by running, Mac token relay, endpoint lifecycle, no price means no dollar cap, fixed Codex scaffold, capacity), ordered fixes.
- [[wiki/syntheses/qwen-two-task-pilot]] — **Qwen3.8-27B two-task pilot (igraph, md4c) on the Vertex endpoint, done 2026-11-05:** both passed S1 to S4; expectations written beforehand against results (calls, call time, cache, duration), model calls are 80% to 97% of agent time, heavy-tailed reasoning (14 calls = 61% of igraph's call time), two silent-thinking calls lost 21% of igraph's time, cache warm up to 103k prompts (two-large-contexts case untested); per-call data in `aws-vm-data/qwen-pilot/`.
- [[wiki/syntheses/qwen-capacity-levers-test]] — **LIVING PAGE: more warm cache and more concurrent agents on one A100 (test plan, 2026-11-05):** what vLLM's docs say (hybrid model: attention KV and linear-attention state share one pool; fp8 KV +19% in the model recipe), the hypothesis that `--max-num-seqs` is the bigger lever, arms (cap 16, then fp8 KV), tests and baselines, expectations, decision rules; results filled after the run.
- [[wiki/syntheses/qwen-scaling-plan]] — **Qwen3.8-27B on Vertex: findings in simple terms and how to scale (2026-11-05):** the warm-cache rule (combined context under about 177k tokens with 8-bit KV, so 2 to 3 tasks), measured probe and real-task ramps, the ladder of options (software, flags, FP8 weights, tensor parallelism on 2 or 4 GPUs) with estimated capacity, tasks at once and 100-task time and GPU-hours; fixes outside the server; order of work.
- [[wiki/syntheses/qwen3-8-27b-architecture]] — **Qwen3.8-27B architecture and its serving consequences:** 64 layers (48 Gated DeltaNet + 16 full attention, 3:1), 24 query and 4 KV heads, parameter breakdown (about 26.9B), what the layout explains (64 KiB KV per token, decode ceiling, prefill speed, 4-way limit on cache splitting), and the hypothesis that GDN state snapshots explain the 0.45x warm capacity.
- [[wiki/syntheses/qwen-endpoint-redeploy-runbook]] — **runbook: how we changed and redeployed the Qwen endpoint ourselves:** the script and what it does, setup, change-and-redeploy steps, every configuration so far with its argument diff, test commands (curl and probe), running real tasks (token pusher, shim, DNS check, Ray slots, driver, monitors), pitfalls.
- [[wiki/syntheses/pull-request-plan]] — **pull requests we can raise against the owner's repository (plan, nothing raised):** state of PR #1 and #2 (both merged), what exists only outside the owner's repo (the whole `tools/` folder, shim hooks), seven proposed PRs in order (gcp serving arguments, sampler and prefetch, shim, translation layer, registry, token tools, autoscaler), evidence per PR, and common preparation.
- [[wiki/syntheses/cybergym-agent-and-validation-walkthrough]] — **walkthrough of the agent phase and validation stages S1 to S4 (2026-11-06):** the two numberings (prompt STEP 1 to 4 vs Stage 1 to 4), what a task contains, the agent phase step by step, the validation phase (fresh container per stage, skip rules, timeouts), each stage's commands and pass criterion, what counts as success, subtleties (crash = non-zero exit), why validation is slow (four builds), a worked igraph example, code locations.
- [[wiki/syntheses/grader-shared-images-experiment]] — **experiment (first round, 2026-11-06): validation with two saved images instead of four separate setups:** how the standard grader repeats setup and builds, why (state contamination), the variant (prepared image + one patched-build image, fresh container per stage), results (stage statuses identical in all nine comparisons, including four negative controls: no-op patch, build-breaking patch, code-disabling patch, non-crashing PoC): igraph and md4c 0.95 to 1.49x, **binutils 1.71x (1,725 s to 1,006 s)**; image saves cost 11 to 92 s; the cost model; parallelism as a second lever; what adopting it would change in the benchmark code; next steps (ffmpeg, repeats, equivalence on 48 pairs).
- [[wiki/syntheses/model-registry-design]] — LIVING PAGE (design only): pick a model and provider by a string (`kimi-k3@bedrock`); where it plugs in, two layers, resolution order, find and probe commands, audit trail, shim changes, open questions
- [[wiki/syntheses/vm-stop-and-bring-up-runbook]] — checklist to stop the head VM safely and the steps to bring the shim, Postgres and autoscaling head back up
- [[wiki/syntheses/how-a-run-works-on-the-vm]] — plain-language runbook: the commands and steps from a Claude Code session to a finished task on the VM (ssh, services, manifest, preflight, run, worker steps, scaling, monitoring)
- [[wiki/syntheses/qwen-bedrock-responses-translation]] — LIVING PAGE: Qwen3.8-27B is not on Bedrock; the Bedrock Qwen models serve only Chat Completions, Codex needs Responses; translation layer in the shim, design, tests (unit, end-to-end, real Bedrock with two Qwen models), what is not done
- [[wiki/syntheses/autoscaler-30-task-test]] — LIVING PAGE: the 30-task test of the full path (autoscaler + shared Postgres): 30 never-tried light patch-only tasks, head plus one autoscaled worker, spend ceiling, safeguards, then results (load split, workers started, cost, Postgres completeness).
- [[wiki/syntheses/e2e-runs-and-vm-behaviour]] — e2e on the AWS VM: two runs (22 tasks: 11 passed, 2 S4 failures, 1 genuine no-PoC, 8 stopped by spend caps), CPU-bound behaviour at 10 concurrent (memory never limited), grading rebuild cost, the controller's live trial, threshold calibration, live shim cap swap, cost, mistakes.
