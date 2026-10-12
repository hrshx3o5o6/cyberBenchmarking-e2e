---
type: synthesis
created: 2026-10-12
updated: 2026-10-12
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, igraph-arvo-29408]
task: igraph/arvo_29408
run: 11
model: minimax-m3 (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-12
s1: -
s2: -
s3: passed
s4: passed
outcome: "FULL SUCCESS (S3+S4); 13 requests, 1.9 min, $0.034"
cost_usd: 0.034
minutes: 5.6
---
# Run 11: minimax-m3, patch-only (solved)

**One line:** solved in 13 requests. The fix sets `context.tree = 0` after `igraph_gml_tree_destroy(context.tree)` in `igraph_read_graph_gml` (`gml.c:225`), so the cleanup handler does not free the tree twice.

## Setup
`igraph/arvo_29408`, patch-only. Azure VM, 90 min / $10 per run (paper), minimax/minimax-m3 via OpenRouter ($0.30/M input, $0.06/M cached input, $1.20/M output), Claude Code 2.1.91, iterative prompt, 1 attempt. Shim caps $10 per run, $30 batch total; two runs in parallel. Started 05:33 (VM clock), in parallel with hunspell patch-only; wall time 5.6 min including container setup, agent exec 1.9 min.

## What it did (13 requests: 5 Bash, 4 Read, 3 Write, all CoreWeave)
Read the crash log, the GML reader, wrote a 455-byte patch, ran `/scripts/validate.py` once: S3 and S4 pass. Its stated cause: when the GML `Version` is an integer other than 1 the code destroys the tree and raises an error, and the error cleanup destroys it again.

## Numbers
56k fresh, 352k cached (86.3% cache share), 3.2k output tokens; **cost $0.034**.

Next run on this task: [[wiki/syntheses/igraph-arvo-29408/run-12-minimax-m3-e2e]].

Back to the task overview: [[wiki/syntheses/igraph-arvo-29408/00-overview]] · batch summary: [[wiki/syntheses/batch-6-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
