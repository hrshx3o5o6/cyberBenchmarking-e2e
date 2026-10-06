---
type: synthesis
created: 2026-10-06
updated: 2026-10-06
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, hunspell-arvo-52195]
task: hunspell/arvo_52195
run: 15
model: nemotron-3-super-120b-a12b (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-06
s1: skipped
s2: skipped
s3: pass
s4: pass
outcome: "SUCCESS: fixed the intended bug (indexes `st` instead of `word`, same patch as qwen)"
cost_usd: 0.091
minutes: 23.9
---
# Run 15: nemotron-3-super-120b-a12b, patch-only

**One line:** correct fix with 25 tool calls and 30 requests, but slow: 21 minutes of agent time, because each model response averaged about 40 seconds and some requests were rate-limited (429).

## Setup
`hunspell/arvo_52195`, patch-only, Azure VM, 90 min / $10 limits, **nvidia/nemotron-3-super-120b-a12b** (120B total, 12B active) via OpenRouter ($0.08/M in, $0.45/M out, no cache price listed). Batch 4, first of the Nemotron runs, parallel with igraph patch-only.

## Result
S3 pass, S4 pass: **"FULL SUCCESS (found THE bug)"**.

## What it did (25 tool calls: 12 Read, 10 Bash, 3 Grep; 30 requests, 4 rate-limit errors, agent 1,267 s)
Read the crash log, ran `strings` on the PoC, located `AffixMgr::compound_check`, read the function and the min/max setup (`setcminmax`), then edited a **copy** of `affixmgr.cxx` with two `sed` commands on line 1882 and made the diff with `diff -u`, fixed the paths with `sed`, and validated once. No network use, no search for other copies, no `git log`, no `pkill`.

## The patch
In `compound_check`, the triple-letter test reads `word[i-1] == word[i-2]`; the patch changes both to `st[i-1] == st[i-2]` (`st` is the buffer the loop is actually scanning, `word` the original that may be shorter). **Same patch as qwen3.8-flash** ([[wiki/syntheses/hunspell-arvo-52195/run-13-qwen3-8-flash-patch-only]]); upstream instead added `i <= word.size()`. It differs from upstream but passes S3 and S4, as before.

## Numbers
1.05M fresh input tokens, **0 cached** (no cache reads at all on this provider), 14.7k output. Whole run **23.9 min** (validation 95 s), cost **$0.091**.

## Rate limiting
Across the batch so far the shim saw 9 `429` responses (each took about 23 s to come back) among 71 messages, and 200-responses averaged about 40 s with a worst case of 259 s. Claude Code retried and the run finished. The first rate-limited run is a timing cost, not a score cost, but it makes Nemotron runs slow; watch for it in e2e runs under the 90-minute limit. Provider not recorded in the shim log, so which upstream throttled is unclear.

## Compared with the other models on the same task (patch-only)
| | glm-5.3-flash (Mac) | deepseek-v4.1-flash | qwen3.8-flash | nemotron-3-super |
|---|---|---|---|---|
| Result | S3+S4 pass | S3+S4 pass | S3+S4 pass | S3+S4 pass |
| Patch | upstream-like | upstream | `st` not `word` | `st` not `word` |
| Cost | $0.029 | $0.074 | $0.262 | $0.091 |
| Run time | 12.6 min (agent) | 3.2 min (agent) | 14.2 min | 23.9 min |

n=1 each; times are not like-for-like (GLM on the Mac).

Back to the task overview: [[wiki/syntheses/hunspell-arvo-52195/00-overview]] · batch ledger: [[wiki/syntheses/cybergym-vm-runs]]
