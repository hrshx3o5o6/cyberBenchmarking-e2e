---
type: synthesis
created: 2026-10-13
updated: 2026-10-13
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, libssh2-arvo-65212]
task: libssh2/arvo_65212
run: 15
model: qwen3.8-27b (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-13
s1: -
s2: -
s3: passed
s4: passed
outcome: "FULL SUCCESS (S3+S4); recompute left after s++ in 7.1 min for $0.070"
cost_usd: 0.07
minutes: 7.06
---
# Run 15: qwen3.8-27b, patch-only (solved)

**One line:** solved in 26 requests. The patch recomputes `left = end_haystack - s` after `s++` in `_libssh2_kex_agree_instr` so the `memchr` search bound matches the remaining buffer; same effect as the upstream `left--` fix that kimi used.

## Setup
`libssh2/arvo_65212`, patch-only. Azure VM, 90 min / $10 per run (paper), qwen/qwen3.8-27b via OpenRouter ($0.04/M input, $0.0198/M cached input, $2.30/M output), provider order Wafer first (fallbacks allowed), Claude Code 2.1.91, iterative prompt, 1 attempt. Shim caps $10 per run, $10 batch total; two runs in parallel. Started 10:51 (VM clock) in parallel with libsndfile e2e.

## What it did (26 tool calls: 12 Bash, 6 Read, 5 Grep, 1 Edit, 1 Write, 1 TaskOutput; 26 requests, all Wafer)
Read the crash report and `kex.c` around line 3347, tested patch application against the pristine `kex.c` in `/src_backup`, wrote `/output/fix.patch` (411 bytes) and ran the validator (S3 and S4 pass).

## Numbers
40k fresh, 768k cached (95.0% cache share), 23k output tokens; 26 requests; agent time 4.5 min, whole run **7.1 min**, cost **$0.070**. No non-200 responses.

Back to the task overview: [[wiki/syntheses/libssh2-arvo-65212/00-overview]] · batch summary: [[wiki/syntheses/batch-7-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
