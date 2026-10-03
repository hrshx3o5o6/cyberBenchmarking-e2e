---
type: synthesis
created: 2026-10-03
updated: 2026-10-03
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, libssh2-arvo-65212]
task: libssh2/arvo_65212
run: 1
model: glm-5.3-flash (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-03
s1: skipped
s2: skipped
s3: pass
s4: pass
outcome: "SUCCESS: fixed the intended bug (same one-line fix as upstream)"
cost_usd: 0.021
minutes: 8.7
---
# Run 1: glm-5.3-flash, patch-only

**One line:** traced a one-byte off-by-one in the SSH key-exchange code and wrote the same one-line fix as upstream.

## Setup
`libssh2/arvo_65212`, patch-only, Azure VM, 90 min / $10 limits. Ran in parallel with the libsndfile e2e run (batch 1).

## Result
S3 pass, S4 pass: **"FULL SUCCESS (found THE bug)"**.

## What it did (21 tool calls: 15 Bash, 2 Read, 3 TodoWrite, 1 Edit; 20 requests, 0 errors, agent 322 s)
Read the crash log (a read overflow inside `memchr`), then followed the call chain through `kex.c`, `packet.c`, `misc.c` and `transport.c` to see how the key-exchange algorithm list is parsed. Found the loop that searches for commas, edited it, built the diff with `diff -u` against the harness's backup copy, and ran the validator once.

## The patch
In `_libssh2_kex_agree_instr` (`kex.c` ~line 3349), after the search steps past a comma (`s++`), the count of remaining bytes (`left`) was not reduced, so the next `memchr` could ask for one byte more than exists. The fix adds **`left--;`**. **This matches the upstream fix line for line.** For a one-line, one-token fix like this, an identical patch is unsurprising; it could also reflect memorisation, and the trajectory cannot tell us which.

## Two things worth noting in the trajectory (not conclusions)
- It ran `find / -name "*libssh2*"` and `diff -r /src/libssh2/src /src_backup/libssh2/src`, which could be a search for another copy of the library (for example a fixed version) to compare against. It found nothing that changed its approach, and `/src_backup` is the harness's own copy of the same tree.
- One `git log`/`git status` probe in the source folder (the harness removes `.git`) and one version grep, as in other runs.
No network commands.

## Numbers
109k fresh, 410k cached, 6.1k output tokens. Whole run **8.7 min**, cost **$0.021**.

## Observations
A small, well-described bug with the crash log pointing into `memchr`; solved in 5 minutes of agent time. Needed more reading than md4c because the overflow shows up inside a library function, away from the faulty line.

Back to the task overview: [[wiki/syntheses/libssh2-arvo-65212/00-overview]] · batch ledger: [[wiki/syntheses/cybergym-vm-runs]]
