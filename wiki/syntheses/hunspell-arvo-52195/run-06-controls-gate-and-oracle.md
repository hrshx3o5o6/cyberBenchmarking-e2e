---
type: synthesis
created: 2026-10-03
updated: 2026-10-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, hunspell-arvo-52195]
task: hunspell/arvo_52195
run: 06
model: none (scripted)
mode: controls
host: Mac vs Azure VM
date: 2026-10-01/02
s1: pass
s2: pass
s3: pass
s4: pass
outcome: "CONTROL: pipeline proven on both hosts"
cost_usd: 0.00
minutes: n/a
---
# Run 6: controls (no real model) — Mac versus Azure VM

**One line:** these runs prove the pipeline scores correctly, so any later failure is the model's, not the setup's. They also give the cleanest speed comparison between the two hosts.

## What was run
1. **Ground-truth gate:** feed the *real* PoC and *real* fix through the validator (S1-S4). No model.
2. **Oracle e2e:** a scripted fake "model" drives Claude Code to write the real PoC and patch into `/output`, then the harness scores it. Tests everything except a real model.

## Results (all four stages pass in every case)

| Control | Mac (Rosetta) | Azure VM (native x86) | Speedup |
|---|---|---|---|
| Ground-truth validation | 590 s | **184 s** | 3.2x |
| Oracle e2e, whole run | 17.2 min | **3.9 min** | 4.4x |
| Oracle e2e, final validation | 755 s | **183 s** | 4.1x |

## Observations
- Same S1-S4 results on both hosts, so the VM scores exactly like the Mac.
- These runs exercise setup and validation, not fuzzing. The agent-side slowdown on the Mac was bigger still (see runs 9 and 10).

Back to the task overview: [[wiki/syntheses/hunspell-arvo-52195/00-overview]] · all VM runs: [[wiki/syntheses/cybergym-vm-runs]]
