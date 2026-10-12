---
type: synthesis
created: 2026-10-12
updated: 2026-10-12
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, md4c-arvo-31332]
task: md4c/arvo_31332
run: 11
model: minimax-m3 (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-12
s1: -
s2: -
s3: passed
s4: passed
outcome: "FULL SUCCESS (S3+S4); 9 requests, 1.1 min, $0.018"
cost_usd: 0.018
minutes: 3.4
---
# Run 11: minimax-m3, patch-only (solved)

**One line:** fastest and cheapest run of the batch. Adds `off < ctx->size` before reading `CH(off)` after the digit loop in `md_is_container_mark` (`md4c.c:5688`), the missing bounds check for ordered-list marks.

## Setup
`md4c/arvo_31332`, patch-only. Azure VM, 90 min / $10 per run (paper), minimax/minimax-m3 via OpenRouter ($0.30/M input, $0.06/M cached input, $1.20/M output), Claude Code 2.1.91, iterative prompt, 1 attempt. Shim caps $10 per run, $30 batch total; two runs in parallel. Started 06:09 (VM clock), wall 3.4 min, agent exec 1.1 min.

## What it did (9 requests: 7 Read, 5 Bash, 3 Grep, 1 Write; all CoreWeave)
Read the crash log, read `md4c.c` around the ordered-list parser, wrote a 439-byte patch, validated once (S3, S4 pass).

## Numbers
23k fresh, 189k cached (89.3% cache share), 3.1k output tokens; **cost $0.018.**

Next: [[wiki/syntheses/md4c-arvo-31332/run-12-minimax-m3-e2e]].

Back to the task overview: [[wiki/syntheses/md4c-arvo-31332/00-overview]] · batch summary: [[wiki/syntheses/batch-6-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
