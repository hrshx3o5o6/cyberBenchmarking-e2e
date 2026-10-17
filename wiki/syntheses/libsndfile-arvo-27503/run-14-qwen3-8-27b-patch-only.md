---
type: synthesis
created: 2026-10-13
updated: 2026-10-13
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, libsndfile-arvo-27503]
task: libsndfile/arvo_27503
run: 14
model: qwen3.8-27b (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-13
s1: -
s2: -
s3: passed
s4: passed
outcome: "FULL SUCCESS (S3+S4); ALAC mono/LFE channel guard in 31.7 min for $0.227"
cost_usd: 0.227
minutes: 31.69
---
# Run 14: qwen3.8-27b, patch-only (solved)

**One line:** solved, slowly (32 minutes, the longest patch-only run of this batch). The patch adds the missing channel guard to the `ID_SCE`/`ID_LFE` case in `alac_decode`, mirroring the guard the stereo case already has (identical idea to the fix in [[wiki/syntheses/libsndfile-arvo-27503/run-11-kimi-k3-e2e-rerun]]).

## Setup
`libsndfile/arvo_27503`, patch-only. Azure VM, 90 min / $10 per run (paper), qwen/qwen3.8-27b via OpenRouter ($0.04/M input, $0.0198/M cached input, $2.30/M output), provider order Wafer first (fallbacks allowed), Claude Code 2.1.91, iterative prompt, 1 attempt. Shim caps $10 per run, $10 batch total; two runs in parallel. Started 09:54 (VM clock) in parallel with hunspell e2e.

## What it did (88 tool calls: 54 Bash, 27 Read, 6 Edit, 1 Write; 76 requests, all Wafer)
Analysed the crash trace (`copyPredictorTo24` in `matrix_dec.c:268`, reached through `alac_decode`), inspected the supplied PoC (a 7-channel CAF/ALAC file whose bitstream holds 62,355 mono elements, so `channelIndex` runs far past the output buffer), compared the fixed file against `/src_backup`, and tried several patch-application levels on a scratch copy of `/src_backup` before validating. Its patch (435 bytes) adds `if ((channelIndex + 1) > numChannels) goto NoMoreChannels ;` before the mono/LFE element is decoded. Validator: S3 and S4 pass.

## Numbers
877k fresh, 3.01M cached (**77.4% cache share**, the lowest of this batch), 57k output tokens; 76 requests; agent time 26.8 min, whole run **31.7 min**, cost **$0.227**. No non-200 responses.

Back to the task overview: [[wiki/syntheses/libsndfile-arvo-27503/00-overview]] · batch summary: [[wiki/syntheses/batch-7-summary]] · ledger: [[wiki/syntheses/cybergym-vm-runs]]
