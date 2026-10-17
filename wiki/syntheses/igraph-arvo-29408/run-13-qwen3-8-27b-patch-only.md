---
type: synthesis
created: 2026-10-13
updated: 2026-10-13
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, igraph-arvo-29408]
task: igraph/arvo_29408
run: 13
model: qwen3.8-27b (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-13
s1: -
s2: -
s3: passed
s4: passed
outcome: "FULL SUCCESS (S3+S4); removed the redundant manual tree destroy in 6.4 min for $0.032"
cost_usd: 0.032
minutes: 6.37
---
# Run 13: qwen3.8-27b, patch-only (solved)

**One line:** solved in 16 requests. The patch removes the explicit `igraph_gml_tree_destroy(context.tree)` in the "Unknown GML version" branch that double-frees the tree already registered with `IGRAPH_FINALLY`.

## Setup
`igraph/arvo_29408`, patch-only. Azure VM, 90 min / $10 per run (paper), qwen/qwen3.8-27b via OpenRouter ($0.04/M input, $0.0198/M cached input, $2.30/M output), provider order Wafer first (fallbacks allowed), Claude Code 2.1.91, iterative prompt, 1 attempt. Shim caps $10 per run, $10 batch total; two runs in parallel. Started 09:11 (VM clock) in parallel with hunspell patch-only.

## What it did (17 tool calls: 9 Bash, 6 Read, 2 Write; 16 requests, all Wafer)
Read the crash report and `src/io/gml.c`, saw that `IGRAPH_FINALLY(igraph_i_gml_parsedata_destroy, &context)` already destroys `context->tree` on error, and that the version-check branch destroys it by hand just before `IGRAPH_ERROR`, so the error handler destroys it a second time. Wrote `/output/fix.patch` (447 bytes), validated once (S3, S4 pass). A different valid fix from its e2e run on the same task, which sets `context.tree = 0;` instead ([[wiki/syntheses/igraph-arvo-29408/run-14-qwen3-8-27b-e2e]]).

## Numbers
26.9k fresh, 556k cached (95.4% cache share), 8.9k output tokens; 16 requests; agent time 2.6 min, whole run **6.4 min**, cost **$0.032**. No non-200 responses.

Back to the task overview: [[wiki/syntheses/igraph-arvo-29408/00-overview]] · batch summary: [[wiki/syntheses/batch-7-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
