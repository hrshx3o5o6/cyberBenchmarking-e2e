---
type: synthesis
created: 2026-10-13
updated: 2026-10-13
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, hunspell-arvo-52195]
task: hunspell/arvo_52195
run: 21
model: qwen3.8-27b (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-13
s1: -
s2: -
s3: passed
s4: passed
outcome: "FULL SUCCESS (S3+S4); compound_check bounds fix in 9.2 min for $0.108"
cost_usd: 0.108
minutes: 9.24
---
# Run 21: qwen3.8-27b, patch-only (solved)

**One line:** solved. The patch adds an index guard in `AffixMgr::compound_check` (`i <= (int)word.size()`) so the checkcompoundpattern path no longer reads past `word`; the ground-truth PoC no longer crashes (S4 pass).

## Setup
`hunspell/arvo_52195`, patch-only (crash log given). Azure VM, 90 min / $10 per run (paper), qwen/qwen3.8-27b via OpenRouter ($0.04/M input, $0.0198/M cached input, $2.30/M output), provider order Wafer first (fallbacks allowed), Claude Code 2.1.91, iterative prompt, 1 attempt. Shim caps $10 per run, $10 batch total; two runs in parallel. Started 09:11 (VM clock) in parallel with igraph patch-only.

## What it did (27 tool calls: 19 Bash, 7 Read, 1 Edit; 26 requests, all Wafer)
Read the crash report and `affixmgr.cxx` around line 1882 and found that `st` (a working copy of `word`) is extended by `st.replace(...)` in the `simplifiedcpd` path while the split index `i` is bounded by `st.size()`, so `i` can exceed `word.size()` and `word[i - 1]` reads out of bounds. Edited the source, produced `/output/fix.patch` (587 bytes), ran `/scripts/validate.py` (S3 and S4 pass). It used a scratch git copy to test how the patch applies.

## Numbers
38.6k fresh, 790k cached (95.3% cache share), 39.3k output tokens; 26 requests; agent time 6.3 min, whole run **9.2 min**, cost **$0.108**. No non-200 responses.

Compare: [[wiki/syntheses/hunspell-arvo-52195/run-19-minimax-m3-patch-only]] (same task, MiniMax $0.229). Next run on this task: [[wiki/syntheses/hunspell-arvo-52195/run-22-qwen3-8-27b-e2e]].

Back to the task overview: [[wiki/syntheses/hunspell-arvo-52195/00-overview]] · batch summary: [[wiki/syntheses/batch-7-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
