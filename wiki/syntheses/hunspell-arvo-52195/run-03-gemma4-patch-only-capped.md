---
type: synthesis
created: 2026-10-03
updated: 2026-10-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, hunspell-arvo-52195]
task: hunspell/arvo_52195
run: 3
model: gemma4 (Ollama free)
mode: patch-only
host: Mac (Rosetta)
date: 2026-10-01
s1: skipped
s2: skipped
s3: no_patch
s4: skipped
outcome: "INCONCLUSIVE: stopped by our own spend/token cap"
cost_usd: 0.00 (free plan)
minutes: 5.4
---
# Run 3: gemma4, patch-only (Mac) — stopped by our own cap

**One line:** inconclusive, because my safety cap ended the run, not the model.

## Setup
`hunspell/arvo_52195`, patch-only, free gemma4. Our shim had a 6M-token input cap that counted cached tokens as full price.

## What happened
After 78 requests the shim returned "budget exhausted" and the agent exited. Tool calls: **73 Read, 4 Bash, 1 TodoWrite, 0 Edit, 0 Write**. It read the same source file over and over and never started editing.

## Why it matters
Cached input (about 6M tokens in 78 requests) crossed the cap. The cap was a flaw in *our tooling*; the fix was to count fresh and cached tokens separately (run 4).

## Takeaway
A tooling limit can look like a model failure. Always check why a run ended.

Back to the task overview: [[wiki/syntheses/hunspell-arvo-52195/00-overview]] · all VM runs: [[wiki/syntheses/cybergym-vm-runs]]
