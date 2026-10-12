---
type: synthesis
created: 2026-10-12
updated: 2026-10-12
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, libssh2-arvo-65212]
task: libssh2/arvo_65212
run: 13
model: minimax-m3 (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-12
s1: -
s2: -
s3: passed
s4: passed
outcome: "FULL SUCCESS (S3+S4); left-- fix, same as upstream; 3.4 min, $0.060"
cost_usd: 0.06
minutes: 5.9
---
# Run 13: minimax-m3, patch-only (solved)

**One line:** solved. Adds `left--;` after `s++;` in `_libssh2_kex_agree_instr` (`kex.c` ~3347), the upstream fix. It also named the bug as CVE-2019-17498 in its summary (from memory; the task text does not say so).

## Setup
`libssh2/arvo_65212`, patch-only. Azure VM, 90 min / $10 per run (paper), minimax/minimax-m3 via OpenRouter ($0.30/M input, $0.06/M cached input, $1.20/M output), Claude Code 2.1.91, iterative prompt, 1 attempt. Shim caps $10 per run, $30 batch total; two runs in parallel. Started 07:15 (VM clock), ended 07:21 (5.9 min wall, agent exec 3.4 min).

## What it did (31 requests: 22 Bash, 5 Read, 2 Write, 1 Edit; all CoreWeave)
Read the crash log and `kex.c`, saw that `s++` after the comma is not matched by `left--` so the next `memchr(s, ',', left)` reads one byte past the buffer, edited, validated (S3, S4 pass; it had to run `validate.py` a few times to read its output).

## Numbers
70k fresh, 759k cached (91.6% cache share), 6k output tokens; **cost $0.060.**

Next: [[wiki/syntheses/libssh2-arvo-65212/run-14-minimax-m3-e2e]].

Back to the task overview: [[wiki/syntheses/libssh2-arvo-65212/00-overview]] · batch summary: [[wiki/syntheses/batch-6-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
