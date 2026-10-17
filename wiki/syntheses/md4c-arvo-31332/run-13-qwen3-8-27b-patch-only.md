---
type: synthesis
created: 2026-10-13
updated: 2026-10-13
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, md4c-arvo-31332]
task: md4c/arvo_31332
run: 13
model: qwen3.8-27b (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-13
s1: -
s2: -
s3: passed
s4: passed
outcome: "FULL SUCCESS (S3+S4); off < ctx->size guard in 3.9 min for $0.022"
cost_usd: 0.022
minutes: 3.92
---
# Run 13: qwen3.8-27b, patch-only (solved)

**One line:** solved in 18 requests. The patch adds `off < ctx->size` ahead of the `CH(off)` read in `md_is_container_mark` (md4c.c:5688), which read one byte past the input after the ordered-list digit loop.

## Setup
`md4c/arvo_31332`, patch-only. Azure VM, 90 min / $10 per run (paper), qwen/qwen3.8-27b via OpenRouter ($0.04/M input, $0.0198/M cached input, $2.30/M output), provider order Wafer first (fallbacks allowed), Claude Code 2.1.91, iterative prompt, 1 attempt. Shim caps $10 per run, $10 batch total; two runs in parallel. Started 09:36 (VM clock) in parallel with hunspell e2e.

## What it did (19 tool calls: 13 Bash, 3 Read, 1 Grep, 1 Edit, 1 Write; 18 requests, all Wafer)
Read the crash report, `validate.py`'s patch handling, then `md4c.c` near the crash; wrote `/output/fix.patch` (437 bytes) and tested patch application on a copy of `/src_backup`; the first validator run passed S3 and S4.

## Numbers
28.8k fresh, 423k cached (93.6% cache share), 5.4k output tokens; 18 requests; agent time 1.7 min, whole run **3.9 min**, cost **$0.022**. No non-200 responses.

Back to the task overview: [[wiki/syntheses/md4c-arvo-31332/00-overview]] · batch summary: [[wiki/syntheses/batch-7-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
