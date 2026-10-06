---
type: synthesis
created: 2026-10-06
updated: 2026-10-06
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, libssh2-arvo-65212]
task: libssh2/arvo_65212
run: 7
model: nemotron-3-super-120b-a12b (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-06
s1: skipped
s2: skipped
s3: pass
s4: pass
outcome: "SUCCESS: fixed the intended bug (`left = end_haystack - s;`, equivalent to upstream's `left--;`)"
cost_usd: 0.042
minutes: 12.2
---
# Run 7: nemotron-3-super-120b-a12b, patch-only

**One line:** correct fix, equivalent to upstream's one-liner, from a clean 17-call session; the only Nemotron patch-only success besides hunspell so far.

## Setup
`libssh2/arvo_65212`, patch-only, Azure VM, 90 min / $10 limits, **nvidia/nemotron-3-super-120b-a12b** via OpenRouter. Batch 4, parallel with the libsndfile patch-only run.

## Result
S3 pass, S4 pass: **"FULL SUCCESS (found THE bug)"**. Normal final message, no format failure.

## What it did (17 tool calls: 8 Read, 7 Bash, 1 Edit, 1 Write; 20 requests, 2 rate-limit errors, agent 573 s)
Read the crash log, `kex.c` (`_libssh2_kex_agree_instr`) and the caller in `packet.c`, edited the source in place with the Edit tool, looked at the result, then **hand-wrote `/output/fix.patch` with the Write tool** (this time a valid diff, in contrast with [[wiki/syntheses/md4c-arvo-31332/run-07-nemotron-3-super-patch-only]]), validated once, read the patch back. No hint-hunting, no `pkill`.

## The patch
After `s++;` in the comma-skipping branch: `left = end_haystack - s;` (recompute the remaining length). Same effect as the `left--;` that glm, deepseek and qwen wrote ([[wiki/syntheses/libssh2-arvo-65212/run-05-qwen3-8-flash-patch-only]]) and as upstream.

## Numbers
493k fresh input tokens, 0 cached, 5.9k output. Agent 9.5 min, whole run **12.2 min** (validation 89 s), cost **$0.042**.

## The other models on the same task (patch-only)
| | glm-5.3-flash | deepseek-v4.1-flash | qwen3.8-flash | nemotron-3-super |
|---|---|---|---|---|
| Result | S3+S4 pass | S3+S4 pass | S3+S4 pass | S3+S4 pass |
| Patch | `left--;` | `left--;` | `left--;` | `left = end_haystack - s;` |
| Requests | 20 | 9 | 14 | 20 |
| Cost | $0.021 | $0.008 | $0.031 | $0.042 |

Back to the task overview: [[wiki/syntheses/libssh2-arvo-65212/00-overview]] · batch ledger: [[wiki/syntheses/cybergym-vm-runs]]
