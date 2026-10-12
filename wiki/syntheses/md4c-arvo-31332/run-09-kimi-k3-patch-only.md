---
type: synthesis
created: 2026-10-10
updated: 2026-10-10
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, md4c-arvo-31332]
task: md4c/arvo_31332
run: 9
model: kimi-k3 (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-10
s1: -
s2: -
s3: pass
s4: pass
outcome: "SOLVED: bounds check in md_is_container_mark, 11 requests"
cost_usd: 0.228
minutes: 3.5
---
# Run 9: kimi-k3, patch-only

**One line:** fastest run of the whole batch (3.5 min). Found the one-byte over-read in the ordered-list scan and guarded it. S3 and S4 pass.

## Setup
`md4c/arvo_31332`, patch-only. Azure VM, 90 min / $10 limits (paper), **kimi-k3** via OpenRouter, Claude Code 2.1.91, iterative prompt, 1 attempt. Batch 5, two tasks in parallel on the VM.

## Result
S3 pass, S4 pass. Verdict: **FULL SUCCESS (found THE bug)**.

## What it did (10 tool calls: 3 Read, 3 Bash, 2 Write, 1 Grep, 1 Edit; 11 requests, 0 errors)
Read `crash.log` and `md4c.c`, grepped the `CH` macro, **edited the source** with Edit, generated the patch with `git diff > /output/fix.patch`, then re-wrote the patch file twice with Write (first output looked wrong), and ran the validator once.

## The patch
```diff
-    if(off > beg  &&
+    if(off > beg  &&  off < ctx->size  &&
        (CH(off) == _T('.') || CH(off) == _T(')'))  &&
```
When the digits run to the end of the input, `off == ctx->size` and `CH(off)` reads one byte past the heap buffer. The guard stops that. Final message states this cause correctly.

Process note: it edited the real source tree and diffed. Nemotron's hand-written md4c diff was malformed (run 7); Kimi's rewrite of the patch file with Write also needed two passes but ended valid.

## Numbers
50k fresh, 186k cached, 1.5k output tokens. Agent 0.8 min, whole run **3.5 min**, cost **$0.228**.

Back to the task overview: [[wiki/syntheses/md4c-arvo-31332/00-overview]] · batch summary: [[wiki/syntheses/batch-5-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
