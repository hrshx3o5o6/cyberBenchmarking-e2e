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
