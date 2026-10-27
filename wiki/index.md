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
- [[wiki/syntheses/e2e-runs-and-vm-behaviour]] — e2e on the AWS VM: two runs (22 tasks: 11 passed, 2 S4 failures, 1 genuine no-PoC, 8 stopped by spend caps), CPU-bound behaviour at 10 concurrent (memory never limited), grading rebuild cost, the controller's live trial, threshold calibration, live shim cap swap, cost, mistakes.
