---
type: synthesis
created: 2026-10-12
updated: 2026-10-12
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, hunspell-arvo-52195]
task: hunspell/arvo_52195
run: 19
model: minimax-m3 (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-12
s1: -
s2: -
s3: passed
s4: passed
outcome: "FULL SUCCESS (S3+S4); fixed the compound_check overflow in 8.2 min for $0.229"
cost_usd: 0.229
minutes: 11.0
---
# Run 19: minimax-m3, patch-only (solved)

**One line:** solved. The patch stops `compound_check` from reading past the word in the checkcompoundpattern path; the ground-truth PoC no longer crashes (S4 pass).

## Setup
`hunspell/arvo_52195`, patch-only (crash log given). Azure VM, 90 min / $10 per run (paper), minimax/minimax-m3 via OpenRouter ($0.30/M input, $0.06/M cached input, $1.20/M output), Claude Code 2.1.91, iterative prompt, 1 attempt. Shim caps $10 per run, $30 batch total; two runs in parallel. Started 05:33 (VM clock) in parallel with igraph patch-only.

## What it did (48 requests: 25 Read, 16 Bash, 5 Grep, 1 Write; all served by CoreWeave)
Read the crash report, went to `affixmgr.cxx` (`AffixMgr::compound_check`, line 1882), traced how `i` can be pushed past `word.size()` when the pattern table is used, wrote the patch (`/output/fix.patch`, 413 bytes), ran `/scripts/validate.py` once (S3, S4 pass) and summarised. Its stated root cause: in the simplified checkcompoundpattern loop `i` grows by the pattern length, which can exceed the word, while a later loop reads the original `word`; the fix uses the local modified copy `st`, which is bounds-checked.

## Numbers
201k fresh, 2.58M cached (92.8% cache share), 56k output tokens; 48 requests; agent time 8.2 min, whole run about 11 min; **cost $0.229**. No non-200 responses.

Compare: [[wiki/syntheses/hunspell-arvo-52195/run-17-kimi-k3-patch-only]] (same task, Kimi). Next run on this task: [[wiki/syntheses/hunspell-arvo-52195/run-20-minimax-m3-e2e]].

Back to the task overview: [[wiki/syntheses/hunspell-arvo-52195/00-overview]] · batch summary: [[wiki/syntheses/batch-6-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
