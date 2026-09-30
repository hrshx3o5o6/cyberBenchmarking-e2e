---
type: source
raw: "[[cybergym-e2e/cybergym-e2e]]"
created: 2026-09-30
tags: [paper, benchmark, cybersecurity, agents]
title: "CyberGym-E2E: Scalable Real-World Benchmark for AI Agents' End-to-End Cybersecurity Capabilities"
authors: [Tianneng Shi, Robin Rheem, Dongwei Jiang, Wenbo Guo, Dawn Song, et al.]
venue: ICML 2026 (PMLR 306)
year: 2026
arxiv: 2606.04460v2
---
# CyberGym-E2E

## TL;DR
Benchmark of 920 real OSS-Fuzz vulnerabilities across 139 C/C++ projects that scores agents on the *whole* lifecycle: find bug, write PoC, patch, keep tests passing. Patching is easy given a PoC (patch-only up to 87.1%); discovery is the bottleneck (end-to-end S3 19–66% depending on model, [[cybergym-e2e/cybergym-e2e#4.2. Main Results]]).

## Problem & motivation
Prior benchmarks cover one lifecycle stage, run agents with read-only code access, or lack post-patch functionality tests or scale ([[cybergym-e2e/cybergym-e2e#2.1. Comparing CyberGym-E2E to Other Benchmarks]]). See [[wiki/concepts/end-to-end-vulnerability-lifecycle-evaluation]].

## Method
- 4-step automated, agent-enhanced construction pipeline, expert-validated: [[wiki/concepts/benchmark-construction-pipeline]]. Data from [[wiki/entities/oss-fuzz]], partly via [[wiki/entities/arvo]] and [[wiki/entities/cybergym]].
- Agent runs inside the real build sandbox; test files/scripts are immutable to it.
- Two settings: **patch-only** (gets ground-truth PoC + crash log) and **end-to-end** (gets only codebase + build env).
- Validation stages S1 PoC crashes vulnerable build; S2 patch removes that crash; S3 developer tests pass; S4 (diagnostic) patch also removes the ground-truth PoC crash. Success = S1–S3. See [[wiki/concepts/alternative-vulnerability-discovery]] for S3 vs S4.

![[cybergym-e2e/cybergym-e2e_artifacts/image_000001_0b69b25328a8e21d4b7008bdd1c9e46ecd5add80c1dfe1e49a87a927fa500005.png]]
*Fig. 2: task settings and evaluation flow.*

## Results (exact from paper; $10 cap, 90 min unless noted)
Initial 615 tasks (Table 3), % success:

| Model | Harness | P-O | E2E S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|---|
| Opus 4.5 | Claude Code | 82.3 | 24.9 | 21.9 | 19.2 | 7.6 |
| Sonnet 4.5 | Claude Code | 77.4 | 18.1 | 12.1 | 10.6 | 3.4 |
| Sonnet 4.5 | OpenHands | 68.9 | 9.3 | 7.2 | 5.4 | 2.3 |
| GPT-5.2-Codex | Codex | 58.5 | 30.2 | 22.0 | 20.7 | 6.5 |
| Gemini 3 Pro | Gemini CLI | 77.6 | 29.6 | 23.6 | 22.6 | 5.0 |

Expanded 920 tasks (Table 4): Opus 4.6 P-O 84.1 / S3 37.9; GPT-5.4 87.1 / 65.9; Gemini 3.1 Pro 83.0 / 43.8; Opus 4.6 no cap 85.8 / 62.6 (S4 26.2).

Other findings: harness matters ([[wiki/concepts/agent-harness-design-effects]]); budgets show diminishing returns (Table 6); [[wiki/concepts/cross-run-feedback]] adds +4.8 to +7.1 pts; no significant memorization effect (all p > 0.1, Table 8); agents sometimes misreport success (capability misrepresentation, selective reporting).

## Limitations & caveats
C/C++ memory-safety only (sanitizer oracle); structured-input projects dominate; $10 cap truncates Opus 4.5 (>half runs hit cap); shallow patches that guard the crash frame still count as success; no LLM patch-quality judge. Dual-use noted by authors.

## Entities
[[wiki/entities/oss-fuzz]] · [[wiki/entities/arvo]] · [[wiki/entities/cybergym]] · [[wiki/entities/openhands]]

## Concepts
[[wiki/concepts/end-to-end-vulnerability-lifecycle-evaluation]] · [[wiki/concepts/benchmark-construction-pipeline]] · [[wiki/concepts/alternative-vulnerability-discovery]] · [[wiki/concepts/agent-harness-design-effects]] · [[wiki/concepts/cross-run-feedback]]

## Open questions / relevance to my work
Explicit tie to my research not recorded yet — add when known.
