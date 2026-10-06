---
type: synthesis
created: 2026-10-06
updated: 2026-10-06
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, md4c-arvo-31332]
task: md4c/arvo_31332
run: 7
model: nemotron-3-super-120b-a12b (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-06
s1: skipped
s2: skipped
s3: error
s4: skipped
outcome: "FAILED: right function and right idea, but the hand-written patch was malformed (S3 error); the corrected patch came out as raw tool-call text and was never saved"
cost_usd: 0.017
minutes: 7.3
---
# Run 7: nemotron-3-super-120b-a12b, patch-only

**One line:** found the right line quickly, wrote a malformed patch by hand, saw the validator's `patch: **** malformed patch` error, and the corrected version was emitted as raw text instead of a tool call, so the run ended with the bad patch on disk.

## Setup
`md4c/arvo_31332`, patch-only, Azure VM, 90 min / $10 limits, **nvidia/nemotron-3-super-120b-a12b** via OpenRouter. Batch 4, parallel with the igraph e2e run.

## Result
S3 `error` ("Failed to apply patch with strip levels 0-3: patch: **** malformed patch at line 14"); S4 skipped. Validator verdict: **FAILED**.

## What it did (7 tool calls: 4 Read, 1 Glob, 1 Write, 1 Bash; 10 requests, 2 rate-limit errors, agent 372 s)
1. Read the crash log, then the area around `md_is_container_mark` in `md4c.c` (right function, the intended bug).
2. **Wrote `/output/fix.patch` directly with the Write tool**, typing the diff by hand: hunk header `@@ -5684,9 +5684,10 @@` does not match the body, it re-indents lines as remove/add pairs, and it adds an opening `{` with no matching close. Not a valid patch and, if it had applied, not a compilable one either.
3. Ran the validator (the only validation): S3 error from `patch`.
4. Read `md4c.c` once more, then produced the corrected diff **inside a thinking block as raw text** (`<parameter=content>... </function></tool_call>`), with `off < ctx->size &&` and the braces repaired. No structured tool call followed, so Claude Code ended the run; final message empty. See [[wiki/syntheses/nemotron-tool-call-format-failures]].

## The idea
Add `off < ctx->size &&` to the condition. Equivalent to upstream and to the glm, deepseek and qwen fixes ([[wiki/syntheses/md4c-arvo-31332/run-05-qwen3-8-flash-patch-only]]). Nothing about the idea was wrong; the file on disk was.

## Two separate faults in one run
- **Model skill:** hand-writing a unified diff instead of using `diff -u` against a backup. The same weakness cost gpt-oss a run in the pilot ([[wiki/syntheses/cybergym-pilot-hunspell-52195]], run 2). Every other model in batches 1-3 used `diff`, `git diff --no-index` or `sed` on a copy.
- **Format failure:** the repaired patch never became a tool call (third such case).

## Numbers
181k fresh input tokens, 0 cached, 4.7k output. Agent 6.2 min, whole run **7.3 min** (validation 16 s), cost **$0.017**.

## The other models on the same task (patch-only)
| | glm-5.3-flash | deepseek-v4.1-flash | qwen3.8-flash | nemotron-3-super |
|---|---|---|---|---|
| Result | S3+S4 pass | S3+S4 pass | S3+S4 pass | **S3 error** (malformed patch) |
| Requests | 10 | 20 | 16 | 10 |
| Cost | $0.008 | $0.016 | $0.027 | $0.017 |

Back to the task overview: [[wiki/syntheses/md4c-arvo-31332/00-overview]] · batch ledger: [[wiki/syntheses/cybergym-vm-runs]]
