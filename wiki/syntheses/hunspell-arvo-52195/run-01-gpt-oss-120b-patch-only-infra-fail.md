---
type: synthesis
created: 2026-10-03
updated: 2026-10-03
sources: ["[[sources/cybergym-e2e]]"]
tags: [run, cybergym, hunspell-arvo-52195]
task: hunspell/arvo_52195
run: 1
model: gpt-oss:120b (Ollama free)
mode: patch-only
host: Mac (Rosetta)
date: 2026-10-01
s1: skipped
s2: skipped
s3: no_patch
s4: skipped
outcome: "INFRA FAILURE: agent made 0 model calls"
cost_usd: 0.00
minutes: 5.4
---
# Run 1: gpt-oss:120b, patch-only (Mac) — setup failure, not a model result

**One line:** the agent could never reach the model, so nothing was tested.

## Setup
Task `hunspell/arvo_52195`, patch-only (crash log and PoC given), Claude Code harness, model served by Ollama's free cloud plan through our local shim. Time limit 45 min.

## What happened
Claude Code tried to call the model and failed 10 times in a row with `UND_ERR_ABORTED` ("Unable to connect to API"), then gave up. The shim saw **0 requests**.

## Why
Claude Code tunnels its web traffic through the benchmark's firewall proxy using an HTTP `CONNECT` request, even for plain `http://` addresses, and that proxy only allows `CONNECT` to port 443. Our shim was on port 80, so it was blocked.

## Fix
Send the agent to the shim by the Docker network's gateway IP, which the harness's `NO_PROXY` list skips, so it bypasses the proxy. (Details: [[wiki/syntheses/cybergym-bench-mac-setup-notes]], gotchas 6-8.)

## Takeaway
First lesson of the project: when a run fails, first check whether the model was ever called (shim log) before blaming the model.

Back to the task overview: [[wiki/syntheses/hunspell-arvo-52195/00-overview]] · all VM runs: [[wiki/syntheses/cybergym-vm-runs]]
