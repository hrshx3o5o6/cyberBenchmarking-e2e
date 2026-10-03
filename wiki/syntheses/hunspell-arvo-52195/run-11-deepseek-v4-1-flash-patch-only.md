---
type: synthesis
created: 2026-10-03
updated: 2026-10-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, hunspell-arvo-52195]
task: hunspell/arvo_52195
run: 11
model: deepseek-v4.1-flash (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-03
s1: skipped
s2: skipped
s3: pass
s4: pass
outcome: "SUCCESS: fixed the intended bug (same fix as upstream)"
cost_usd: 0.074
minutes: 6.4
---
# Run 11: deepseek-v4.1-flash, patch-only (Azure VM)

**One line:** solved in about 3 minutes; its patch matches the upstream fix exactly (`i <= word.size()`).

## Setup
`hunspell/arvo_52195`, patch-only, Azure VM (native x86), 90 min / $10 limits, **deepseek-v4.1-flash** via OpenRouter. Batch 2: the DeepSeek comparison on the same five tasks as glm-5.3-flash. Ran in parallel with the igraph patch-only run.

## Result
S3 pass, S4 pass: **"FULL SUCCESS (found THE bug)"**.

## What it did (42 tool calls: 23 Bash, 15 Read, 3 Edit, 1 Write; 36 requests, 0 errors, agent 193 s)
- Read the crash log, then the code around `compound_check` in `affixmgr.cxx` (the real bug site, ~line 1882) and `suggestmgr.cxx`; decoded the PoC with a small script.
- **Reproduced the crash itself:** copied the source to `/tmp/hl`, compiled the fuzz target with AddressSanitizer, ran the PoC and saw the overflow.
- Edited the copy, rebuilt and re-ran until the crash was gone, then produced the diff (`diff -u` against the original) and validated.
- It explained the root cause correctly: in the compound-pattern path the loop index can run past the word length.

## The patch
Adds `i <= word.size() &&` to the `else if (i > 2 && word[i - 1] == word[i - 2])` condition, **exactly the upstream fix**. (glm-5.3-flash wrote `i < word.size()`, slightly stricter.)

## Checks and things worth noting (observations, not conclusions)
- It ran `git log` in the source folder (output discarded), looked at `NEWS`/`ChangeLog` and grepped the project version, ran `find / -name "affixmgr.cxx"` (looking for another copy of the file?) and listed `/data` and `/config` and compared the PoC's checksum with `/data/poc.bin`. In patch-only the PoC is provided; `/data` is empty for the agent and the config is sanitised by the harness, so it found nothing to use. The version lookups and the file search could be attempts to recall or locate the upstream fix; the trajectory cannot tell us. The patch matching upstream exactly makes this worth a caveat, but it also reproduced and verified the crash itself.
- No network commands.

## Numbers
138k fresh, 1.90M cached, 17.9k output tokens. Whole run **6.4 min**, cost **$0.074**.

## Compared with glm-5.3-flash on the same task (patch-only)
| | glm-5.3-flash (Mac, run 7) | deepseek-v4.1-flash (VM) |
|---|---|---|
| Result | S3+S4 pass | S3+S4 pass |
| Patch | `i < word.size()` | `i <= word.size()` (= upstream) |
| Requests | 27 | 36 |
| Agent time | 754 s (emulated Mac) | 193 s (native VM) |
| Cost | $0.029 | $0.074 |
Different hosts, so times are not like-for-like.

Back to the task overview: [[wiki/syntheses/hunspell-arvo-52195/00-overview]] · batch ledger: [[wiki/syntheses/cybergym-vm-runs]]
