---
type: synthesis
created: 2026-10-03
updated: 2026-10-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, hunspell-arvo-52195]
task: hunspell/arvo_52195
run: 2
model: gpt-oss:120b (Ollama free)
mode: patch-only
host: Mac (Rosetta)
date: 2026-10-01
s1: skipped
s2: skipped
s3: error
s4: skipped
outcome: "FAILED: patch could not be applied"
cost_usd: 0.00 (free plan)
minutes: 5.2
---
# Run 2: gpt-oss:120b, patch-only (Mac)

**One line:** it found the right function but never produced a patch file the tools could apply.

## Setup
`hunspell/arvo_52195`, patch-only, 45 min limit, free Ollama model. After the networking fix from run 1.

## Result
Stage 3 `error`: *"patch: Only garbage was found in the patch input."* S1/S2 are skipped in patch-only; S4 was never reached.

## What it did (83 s of agent time, 32 requests, 31 tool calls)
- Read the crash log, found the right place: `compound_check` in `affixmgr.cxx`, around line 1882.
- Proposed a different fix from the real one (`i--` changed to `continue`).
- Wrote the diff **by hand** and ran the validator **10 times** on the same "garbage" error, rewriting the file each time without ever fixing the format.

## Numbers
47.6k fresh input, 1.38M cached, 6.4k output tokens. Free plan, so no dollar cost (credits not visible to us).

## Observations
- Right area, wrong fix, and the file format was the real blocker. Writing a valid diff is its own skill; running `diff -u` on file copies would have worked (the paid GLM run did exactly that, see run 7).
- Not a clean model-ability verdict, but a clear failure pattern.

Back to the task overview: [[wiki/syntheses/hunspell-arvo-52195/00-overview]] · all VM runs: [[wiki/syntheses/cybergym-vm-runs]]
