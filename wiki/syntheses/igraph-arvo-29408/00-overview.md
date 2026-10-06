---
type: synthesis
created: 2026-10-03
updated: 2026-10-03
sources: ["[[sources/cybergym-e2e]]"]
tags: [task, overview, cybergym, igraph-arvo-29408]
task: igraph/arvo_29408
---
# Task `igraph/arvo_29408`: all runs

## The task in plain words
**igraph** is a C library for graph (network) analysis. The bug is in the **GML file reader**: if a file declares an unsupported GML version, the parser frees its parse tree and then the error cleanup frees it again (use-after-free). Upstream fix: remove the first free (`gml.c` ~line 225).
- x86_64, AddressSanitizer, 7.8 MB of source (the biggest of the four batch-1 tasks). Ground-truth validation on the VM: **312 s**.

## Runs

| # | Model | Mode | Outcome | S1 | S2 | S3 | S4 | Cost | Time | Page |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | glm-5.3-flash | patch-only | solved, different valid fix | - | - | pass | pass | $0.017 | 6.7 min | [[wiki/syntheses/igraph-arvo-29408/run-01-glm-5-3-flash-patch-only\|open]] |
| 2 | glm-5.3-flash | e2e | solved on its own (found the intended bug) | pass | pass | pass | pass | $0.205 | 29.9 min | [[wiki/syntheses/igraph-arvo-29408/run-02-glm-5-3-flash-e2e\|open]] |
| 3 | deepseek-v4.1-flash | patch-only | solved, same patch as GLM | - | - | pass | pass | $0.007 | 5.7 min | [[wiki/syntheses/igraph-arvo-29408/run-03-deepseek-v4-1-flash-patch-only\|open]] |
| 4 | deepseek-v4.1-flash | e2e | solved by reading the code; patch = upstream | pass | pass | pass | pass | $0.051 | 8.3 min | [[wiki/syntheses/igraph-arvo-29408/run-04-deepseek-v4-1-flash-e2e\|open]] |
| 5 | qwen3.8-flash | patch-only | solved, patch = upstream | - | - | pass | pass | $0.079 | 8.7 min | [[wiki/syntheses/igraph-arvo-29408/run-05-qwen3-8-flash-patch-only\|open]] |
| 6 | qwen3.8-flash | e2e | solved on its own; patch = upstream | pass | pass | pass | pass | $0.496 | 26.1 min | [[wiki/syntheses/igraph-arvo-29408/run-06-qwen3-8-flash-e2e\|open]] |
| 7 | nemotron-3-super | patch-only | **failed (S4)**: wrong fix, session ended early | - | - | pass | fail | $0.236 | 42.7 min | [[wiki/syntheses/igraph-arvo-29408/run-07-nemotron-3-super-patch-only\|open]] |
| 8 | nemotron-3-super | e2e | **no result**: tool-call format failure after 11.7 min | no_poc | | | | $0.070 | 12.5 min | [[wiki/syntheses/igraph-arvo-29408/run-08-nemotron-3-super-e2e\|open]] |

```dataview
TABLE model, mode, s1, s2, s3, s4, cost_usd AS cost, minutes
FROM "wiki/syntheses/igraph-arvo-29408"
WHERE run
SORT run ASC
```

Related: [[wiki/syntheses/cybergym-vm-runs]] · [[wiki/syntheses/hunspell-arvo-52195/00-overview]]
