---
type: synthesis
created: 2026-10-06
updated: 2026-10-06
sources: ["[[sources/cybergym-e2e]]"]
tags: [nemotron, tool-calls, failure-mode, provider, caveat]
---
# Nemotron runs: tool calls written as text (format failures)

**Finding (so far, batch 4 in progress):** in every Nemotron run that ended with an empty final message (6 clear cases plus 1 non-decisive of the ten runs; two runs finished by themselves and one ended on the 90-minute limit), the last thing the model produced was a **raw tool call as text inside a thinking block** (`<tool_call><function=Read>...`), not a structured tool call. Claude Code only continues when a response contains a structured tool call, so the run ended on the spot.

| Run | Ended | Last block | Raw `<tool_call>` text |
|---|---|---|---|
| [[wiki/syntheses/hunspell-arvo-52195/run-15-nemotron-3-super-patch-only]] | solved, normal end | text (final summary) | no |
| [[wiki/syntheses/igraph-arvo-29408/run-07-nemotron-3-super-patch-only]] | after 39 min, mid-fix | thinking | **yes** |
| [[wiki/syntheses/igraph-arvo-29408/run-08-nemotron-3-super-e2e]] | after 11.7 min, mid-exploration | thinking | **yes** |
| [[wiki/syntheses/md4c-arvo-31332/run-07-nemotron-3-super-patch-only]] | after 6.2 min, right after a validator error | thinking (a corrected Write call) | **yes** |
| [[wiki/syntheses/md4c-arvo-31332/run-08-nemotron-3-super-e2e]] | after 7.7 min, mid-exploration | thinking | **yes** |
| [[wiki/syntheses/hunspell-arvo-52195/run-16-nemotron-3-super-e2e]] | after 88.3 min (1.7 min before the limit) | thinking | yes, but **not decisive** (time limit imminent) |
| [[wiki/syntheses/libsndfile-arvo-27503/run-07-nemotron-3-super-patch-only]] | after 60.4 min, while checking its own patch | thinking | **yes** |
| [[wiki/syntheses/libssh2-arvo-65212/run-08-nemotron-3-super-e2e]] | after 7.7 min, mid-exploration | thinking | **yes** |
| [[wiki/syntheses/libssh2-arvo-65212/run-07-nemotron-3-super-patch-only]] | solved, normal end | text (final summary) | no |

## What it means
- These failures are **not simply evidence of weak reasoning**: the runs were making sensible progress (igraph patch-only had just located the real bug; igraph e2e was about to read the build script; md4c patch-only had the right idea and was about to rewrite a malformed patch). In md4c the first patch was also badly hand-written, a separate model-skill fault.
- Where the fault lies is not settled by our logs. Candidates: the model emitting its tool-call format inside its reasoning, or the provider's tool-call parser (the stream log names provider "DekaLLM") failing to extract it. The shim logs no request bodies and does not record the provider.
- Our harness is Claude Code speaking the Anthropic tool format via OpenRouter, so a model/provider pair whose tool parser is flaky is penalised by this harness whatever its coding ability.
- Same kind of effect (run ends early with work unfinished) as the Qwen libsndfile e2e run ([[wiki/syntheses/libsndfile-arvo-27503/run-06-qwen3-8-flash-e2e]]), but that one ended with a plain text sentence, no raw tool call, so it is a different case.

## Pattern
Every Nemotron run that ended before the time limit and did not finish by itself ended this way (6 of 6, plus hunspell e2e 1.7 minutes before the limit); the only two clean endings are the two patch-only runs that solved their task quickly (hunspell, libssh2), and one run ([[wiki/syntheses/libsndfile-arvo-27503/run-08-nemotron-3-super-e2e]]) ran out the clock without a format failure. Runs get longer and more likely to end badly the more turns they need, which fits a per-turn failure chance (roughly 1 per 50 requests here: about 7 endings in about 350 requests) more than a one-off glitch. This is an estimate from nine runs, not a measurement.

## Reporting rule for the Nemotron results
Report these runs as **"format failure (no PoC/patch)"**, not as capability failures, and do not mix them into pass counts without that label.

## Options (not done; needs the user's decision)
1. Leave the batch as is and report the failures with this label.
2. Pin a different OpenRouter provider for Nemotron (OpenRouter supports provider routing in the request) and re-run the failed runs. Changes the experimental setup for this model mid-batch; would need a shim change and a note.
3. Rerun failed runs unchanged (non-deterministic; may or may not recur).

Related: [[wiki/syntheses/cybergym-bench-mac-setup-notes]]
