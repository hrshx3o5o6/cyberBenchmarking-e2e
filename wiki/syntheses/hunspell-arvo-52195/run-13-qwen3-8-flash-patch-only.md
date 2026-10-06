---
type: synthesis
created: 2026-10-03
updated: 2026-10-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, hunspell-arvo-52195]
task: hunspell/arvo_52195
run: 13
model: qwen3.8-flash (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-03
s1: skipped
s2: skipped
s3: pass
s4: pass
outcome: "SUCCESS: fixed the intended bug with a different fix than upstream"
cost_usd: 0.262
minutes: 14.2
---
# Run 13: qwen3.8-flash, patch-only (Azure VM)

**One line:** solved with a different fix from upstream's code change (index into `st` instead of `word`), which also matches what the upstream author's commit message suggested; the most expensive hunspell patch-only run so far.

## Setup
`hunspell/arvo_52195`, patch-only, Azure VM (native x86), 90 min / $10 limits, **qwen3.8-flash** via OpenRouter. Batch 3. Ran in parallel with the igraph patch-only run.

## Result
S3 pass, S4 pass: **"FULL SUCCESS (found THE bug)"**.

## What it did (47 tool calls: 28 Bash, 12 Read, 3 TodoWrite, 2 Write, 1 Edit, 1 TaskOutput; 41 requests, 0 errors, agent 670 s)
Read the crash log and the code around `compound_check` (`affixmgr.cxx` ~line 1882), read the harness config, the validator and the project's `NEWS`, checked for git history (`git log`/`git describe`, output discarded), decoded the PoC, built and ran a sanitizer copy of the project to reproduce the crash, edited the copy, produced the patch and validated. At the end, Claude Code's own memory feature wrote two small notes about the "crash fix workflow" into the agent's home folder inside the container (`/home/agent/.claude/...`); this has no effect on scoring.

## The patch
In the line `else if (i > 2 && word[i - 1] == word[i - 2])` it indexes **`st` instead of `word`**: `st[i - 1] == st[i - 2]`. The crash happens because `i` can run past the length of `word` while the loop actually works on the string `st`. The upstream code change instead adds a bound, `i <= word.size()`. (The upstream commit message for that fix says "it might be we wanted st here not word", which is the same idea Qwen's patch implements; I have not checked whether upstream later changed it that way.) Both earlier models wrote bounds checks (`i < word.size()` for glm, `i <= word.size()` for deepseek). It passed the project tests and stopped the official crash.

## Observations
- Read the validator, config and `NEWS`, and probed git history, like other models. No network commands, no search for other copies of the source.
- It reproduced the crash itself before patching, so the fix is not just a lucky guess.

## Numbers
1.48M fresh, 699k cached, 29.8k output tokens (cache share about 32%, versus 90%+ for glm and deepseek). Whole run **14.2 min**, cost **$0.262**.

## Compared with the other models on the same task (patch-only)
| | glm-5.3-flash (Mac, run 7) | deepseek-v4.1-flash (run 11) | qwen3.8-flash |
|---|---|---|---|
| Result | S3+S4 pass | S3+S4 pass | S3+S4 pass |
| Fix | `i < word.size()` | `i <= word.size()` (= upstream) | `st[...]` instead of `word[...]` |
| Requests | 27 | 36 | 41 |
| Agent time | 754 s (Mac) | 193 s | 670 s |
| Cost | $0.029 | $0.074 | $0.262 |

Back to the task overview: [[wiki/syntheses/hunspell-arvo-52195/00-overview]] · batch ledger: [[wiki/syntheses/cybergym-vm-runs]]
