---
type: synthesis
created: 2026-11-06
updated: 2026-11-06
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [cybergym, validation, grader, docker, experiment, speed, shared-images, living-document]
---
# Validation with shared images instead of four separate setups: design, first results, comparison with the standard grader (2026-11-06)

**Status: second round done. Stage results identical in all nine comparisons (igraph, md4c, four negative controls, binutils, two igraph repeats). Timing: 1.71x faster on binutils (a heavy build), 0.67x to 1.49x on tiny projects where saving the images costs as much as it saves. Not yet tested: ffmpeg, repeats on heavy tasks, equivalence on the 48 saved pairs.** Background: what the stages are in [[wiki/syntheses/cybergym-agent-and-validation-walkthrough]]; why validation matters for wall time in [[wiki/syntheses/deepseek-100-task-run-report]] sections 13 and 18; the scheduling side of the discussion (ordering, a separate validation pool) is in the same report and in the conversation notes of 2026-11-05. "Grader" and "validation" mean the same thing here. Raw numbers: `aws-vm-data/grader-bench/`; script: `tools/grader_bench.py`.

## Verdict so far: is it helping? (2026-11-06)
**Yes, where it matters, and modestly for the whole run.**
- **Correct:** the stage statuses were identical to the standard grader in nine comparisons, including a failing stage 4, a failing patch, a build error, a patch that only disables the code (S3 failed it in both) and a PoC that does not crash. No case where the variant turned a failure into a pass.
- **Faster on heavy builds:** binutils (a build of about 7 minutes per stage) went from 1,725 s to 1,006 s, **1.71x**, matching the cost model's 1.5x to 1.7x. On tiny projects (igraph, md4c) it was 0.67x to 1.49x: the two image saves cost as much as the work they avoid.
- **Effect on the 100-task run, replayed** (the report's replay model, which reproduces the 11.3 h; the ffmpeg ratio is an **assumption** carried over from binutils, ffmpeg has not been measured):
| Change to grading | As run | ffmpeg first |
|---|---|---|
| none (standard) | 11.3 h | 9.7 h |
| shared images on ffmpeg tasks, 1.71x (measured on binutils) | 10.0 h | 9.2 h |
| shared images and parallel stages, 2.9x (not tested) | 9.3 h | 9.0 h |
| the four standard stages in parallel, 3.9x (not tested) | 9.1 h | 8.9 h |
| grading 2x faster (the report's scenario) | 9.7 h | 8.8 h |
  So shared images alone would have saved about 1.3 h of 11.3 h (about 12%), 6.5 hours of slot time on the 12 ffmpeg tasks, and about 0.5 h on top of ordering ffmpeg first. **The scheduling change (ffmpeg first, 1.6 h) is a bigger lever than the images, and running the stages in parallel is probably a bigger lever too.**
- **Resource view:** shared images save compute (1,725 s of container time to 1,006 s on binutils) at the price of disk (the saved images were several GB) and 11 to 92 s of save time; parallelism saves wall time but not compute. The VM sat at load 1.0 on 16 vCPUs during grading, so the CPU for parallel stages is there.
- **Recommended use:** only for projects with long builds (ffmpeg and a few others), combined with ffmpeg-first ordering; not for small projects. Do not adopt until ffmpeg is measured and the equivalence check on the 48 saved pairs passes.
- **Limits of the evidence:** one heavy project, one run each, a few small ones; run-to-run noise of the image saves is large (11 to 92 s); the ffmpeg gain is extrapolated.

## 1. The standard grader (the baseline)
`run_final_validation` (`scripts/run_agent.py:332`) in end-to-end mode runs four stages, **each in its own fresh container from the plain build image**, and each container repeats the same work before its check:
```
every stage container:  start from the build image
   setup:       apt (sudo, git) -> validation dependencies -> extract source -> copy scripts and config
                -> delete the repo's .git -> apply pre-patches
   validate.py: run prepare.sh -> snapshot /src_backup -> restore /src  [-> apply the patch]  -> compile.sh -> the stage's check
S1: build the VULNERABLE tree, run the agent's PoC       (passes if it crashes)
S2: build the PATCHED tree,    run the agent's PoC       (passes if it does not crash)
S3: build the PATCHED tree,    run test.sh               (passes if the tests pass)
S4: build the PATCHED tree,    run the ground-truth PoC  (passes if it does not crash)
```
So one passing task costs 4 setups, 4 `prepare.sh` runs, 4 snapshots and **4 builds** (one vulnerable, the same patched tree three times). Stage timeouts: `prepare.sh` 1,800 s, compile 3,600 s, PoC run 1,200 s, tests 1,800 s, whole stage 7,200 s.

**Why four containers?** The one reason in the code: the docstring says a new container per stage is used "to avoid state contamination (e.g., MSan libs from stage 1 contaminating ASan build in stage 2)", and `validate.py --only-stage` is described as "for container state isolation". `validate.py` can run all stages in one container (it restores `/src` from the backup between them, and the agent uses it that way), but the restore does not reset the rest of the filesystem (`/out`, installed libraries). That the setup and builds are therefore repeated is a side effect of choosing isolation; whether there are other reasons is not stated in the code.

## 2. The variant
Keep a fresh container per stage, but start them from two saved images so the repeated work is done once:
```
P  container: setup + prepare.sh + snapshot (once)                    -> docker commit  "prepared image"
S1 container (from prepared):       build vulnerable, run the agent's PoC           expect: crash
Q  container (from prepared):       apply patch, build (once)         -> docker commit  "patched-build image"
S2 container (from patched-build):  run the agent's PoC                              expect: no crash
S3 container (from patched-build):  run test.sh                                      expect: tests pass
S4 container (from patched-build):  run the ground-truth PoC                         expect: no crash
```
Same stage skip rules (S2 only if S1 passed, S3 only if S2 passed, S4 only if S3 passed) and the same pass criteria. What is shared: only the two saved images. What stays separate: S1 never feeds anything to the patched stages (the contamination example in the docstring is exactly S1 versus S2), and S2, S3, S4 each start from the same post-build state in their own container, so no stage sees another's leftovers.

| | Standard | Variant |
|---|---|---|
| setup, `prepare.sh`, snapshot | 4 times | **once** (plus saving one image) |
| vulnerable build | once | once |
| patched build | **3 times** | **once** (plus saving one image) |
| fresh container per stage | yes | yes |

## 3. Method
`tools/grader_bench.py` runs on the head VM (Docker, the harness checkout, the task images; no model, no Ray, no shim). **Baseline mode** re-runs `run_final_validation`'s own commands (same container setup, same `validate.py` call with `--run-prepare`, same timeouts) with a timer around each stage; **variant mode** is the sequence of section 2. Inputs are saved PoC and patch pairs from earlier runs: igraph from the Qwen bf16 pilot (all four stages passed), md4c from the Qwen 8-bit six-task run (S1 to S3 passed, **S4 failed**: the wrong-bug case). Pass rule for the experiment: every stage status identical between the two methods.

## 4. Results (head VM, 16 vCPU, idle, 2026-11-06)
**Stage statuses: identical in all four comparisons**, including md4c's S4 = failed.

| Task | Run | Baseline total | Variant total | Ratio | Statuses |
|---|---|---|---|---|---|
| igraph arvo_29408 | 2 | 127.3 s | 117.7 s | 1.08 | pass, pass, pass, pass in both |
| igraph arvo_29408 | 3 (with finer timers) | 129.2 s | 86.8 s | **1.49** | same |
| md4c arvo_31332 | 1 | 72.8 s | 76.3 s | **0.95** | pass, pass, pass, **fail** in both |
(An earlier igraph run, 134.4 s baseline, crashed in the variant because of a bug in my script, section 6, and is not counted.)

**Per-stage comparison, igraph run 3** (seconds)
| Standard grader | | Variant | |
|---|---|---|---|
| S1 (setup 9.8 + `validate.py` 18.5) | 28.4 | setup, `prepare.sh` 3.9, snapshot, **save prepared image 11.4** (once; total 27.9) | 27.9 |
| S2 (setup 8.7 + 19.5) | 28.2 | S1: build vulnerable + run PoC | 16.6 |
| S3 (setup 9.4 + 34.3) | 43.7 | patched build once, **save image 6.5** (total) | 23.3 |
| S4 (setup 9.6 + 19.3) | 28.9 | S2 PoC only / S3 `test.sh` only / S4 PoC only | 0.2 / 15.8 / 0.2 |
| **Total** | **129.2** | **Total** | **86.8** |

**md4c** (seconds): standard S1 to S4 = 19.2, 14.7, 23.6, 15.3 (setup about 10 to 12 each); variant = prepare once 54.6 (setup 10.1, `prepare.sh` 0.0, **save prepared image 43.2**), S1 4.0, patched build once 6.9 (save 3.1), S2 0.2, S3 9.8, S4 0.2.

### 4b. Negative controls (igraph, 2026-11-06): the variant must never turn a failure into a pass
Each control feeds a deliberately wrong input to both methods. Expected and observed statuses were identical in both methods every time.
| Control | Input | Both methods gave (S1, S2, S3, S4) | Baseline | Variant | Ratio |
|---|---|---|---|---|---|
| PoC that does not crash | a tiny valid GML file with the real patch | failed, skipped, skipped, skipped | 29.3 s | 43.8 s | 0.67 |
| No-op patch | the real PoC, a patch that adds one comment | passed, **failed**, skipped, skipped | 57.5 s | 69.2 s | 0.83 |
| Patch that breaks the build | the real PoC, a patch with `#error` | passed, **error**, skipped, skipped | 55.5 s | 58.6 s | 0.95 |
| Patch that disables the code path | the real PoC, a patch that makes the reader return an error at once | passed, passed, **failed**, skipped | 101.0 s | 86.5 s | 1.17 |
The last row shows why S3 exists: S2 alone passes a patch that merely disables the code (the PoC no longer crashes), and the test suite fails it. (The variant skips the patched build when S1 fails, as the stage rules imply; that change was made before these runs.)

### 4c. A heavy project: binutils `arvo_55933` (task-specific 6.8 GB build image; setup and grading took about 36 minutes in the 100-task run)
Statuses identical: passed, passed, passed, passed in both. **Baseline 1,725 s (28.8 min), variant 1,006 s (16.8 min): 1.71x, 719 s saved.**
| Standard grader | Seconds | Variant | Seconds |
|---|---|---|---|
| S1 (setup 22.2 + `validate.py` 409.1) | 431.3 | setup 14.9, `prepare.sh` 0.0, **save prepared image 42.4** (once, total) | 69.2 |
| S2 (setup 14.0 + 407.7) | 421.8 | S1: build vulnerable tree + run PoC | 415.9 |
| S3 (setup 14.1 + 413.3) | 427.3 | patched build once (about 420 s) + **save image 91.6** (total) | 511.8 |
| S4 (setup 15.1 + 429.8) | 444.9 | S2 PoC only / S3 `test.sh` only / S4 PoC only | 0.2 / 6.6 / 0.2 |
| **Total** | **1,725.3** | **Total** | **1,006.3** |
Each standard stage is dominated by the build (about 400 s of the 410 to 430 s of `validate.py`); `test.sh` is short here (6.6 s). The two patched builds that disappear (about 2 x 410 s) and three setups (about 45 s) explain the saving, minus the two image saves (42 + 92 = 134 s, about 13% of the variant's time). The VM's load average stayed at about 1.0 on 16 vCPUs during the run: the build is effectively single-threaded and the machine was mostly idle.

## 5. Reading
- **Correctness first:** the variant gave the same pass, fail and skip status as the standard grader on all stages, including the case where S4 fails. That is the necessary condition; it is only a few cases.
- **Cost model that fits the numbers:** saving about 3 x (setup + `prepare.sh`) + 2 x (patched build) - (the two image saves). Saving an image of about 0.9 GB was the surprise: the first save took 11.4 s (igraph run 3), about 43 s (md4c) and visibly more in igraph run 2 (the prepared step took 58.8 s there, against 27.9 s in run 3), so it is **noisy**. For igraph (setup 9 to 10 s, `prepare.sh` 4 s, patched build about 15 s) the model gives about 50 s saved against 42 observed; for md4c (setup 11 s, `prepare.sh` 0 s, build about 3 s) it gives about -6 s against -3.5 observed.
- **The idea pays off where the patched build is long, and it did: 1.71x on binutils** (the model's prediction was 1.5x to 1.7x). On tiny projects the image saves cost as much as the work they avoid (igraph 1.08x and 1.49x, md4c 0.95x, the controls 0.67x to 1.17x). ffmpeg (setup and grading 78 minutes on average in the 100-task run, [[wiki/syntheses/deepseek-100-task-run-report]]) is the next test, where the builds are longer still. A simple rule would be to use shared images only for projects known to have long builds, which for the 100-task run means ffmpeg and a few others ([[wiki/syntheses/deepseek-100-task-run-report]] section 18).
- **Wall clock versus compute.** The variant cuts total work (1,725 s of container time to 1,006 s on binutils) but runs the same steps one after another. Two further, independent levers are visible in the timings: S1 and the patched build do not depend on each other, so the critical path would be the longer of the two (about 69 + 512 + 7 = 590 s on binutils, 2.9x); and the standard grader's four stages could even run side by side with the skip rules applied afterwards (about the longest stage, 445 s, 3.9x, at four times the simultaneous CPU). The VM stayed at load 1.0 on 16 vCPUs, so the CPU for either exists on this node. Sharing work saves compute, parallelism saves wall time; they can be combined. **Not tested.**
- Run-to-run noise on this VM is small for the stage work (igraph standard S2: 27.8, 28.2, 28.2 s; S3 44.1, 43.6, 43.7 s) and large for the image saves.

## 6. Problems met
- **Commit after stop:** the harness starts containers with `docker run --rm`, so stopping a container removes it; my first version stopped the container before `docker commit`, and the variant crashed. Fixed by committing the running container (`docker commit` pauses it).
- The timings of two runs of the variant were identical to 0.1 s in four steps (igraph runs 2 and 3: 16.6, 23.3, 15.8, 0.2 s); the machine was idle and the work deterministic, which is plausible but worth keeping in mind.

## 7. What changing the benchmark code would take (to use this outside the experiment)
The experiment needs no change to CyberGym's code (the script imports the harness helpers and `validate.py` unchanged). To use it for real runs:
1. `scripts/run_agent.py`: an image-based path beside `run_final_validation`, or a flag, and a way to clean up the saved images.
2. `scripts/validate.py`: a skip-build option (no `prepare.sh`, restore, patch or compile) so S2 to S4 can run from the saved patched build with the harness's own pass rules; today my script re-implements those rules (exit code 0 or not), which could drift from upstream.
3. The patch would go through `scripts/patch_cybergym.py` in the owner's repo, like the two existing upstream patches, and could also be proposed upstream.
4. Gate: an equivalence check on saved pairs (the 48 tasks of the 100-task run that have a PoC and patch) before anyone relies on it.

## 8. Next steps
Done: negative controls (4.b), a heavy project (4.c), repeats on igraph.
1. **ffmpeg** (up to 131 minutes of setup and grading in the 100-task run): where the saving should be largest and the image saves (several GB) matter most.
2. **A second heavy task and repeats** (binutils `arvo_51010`, `arvo_18615`) to put a spread on the 1.71x.
3. **Parallelism inside the variant:** S1 and the patched build at once; S2 to S4 side by side; compare with parallelising the standard stages.
4. **Equivalence on the 48 saved pairs** of the 100-task run (and a failing-pair mix), as the gate before any real use.
5. **Cheaper saves:** the first image save cost 11 to 91 s; options include committing less (a smaller tree), or running S2 to S4 in one container from the built state with a clean copy per stage.

## 9. Reproduce
On the head VM, from a folder holding `grader_bench.py`, a PoC and a patch: `~/cybergym-e2e/.venv/bin/python grader_bench.py --harness ~/cybergym-e2e --task igraph/arvo_29408 --poc poc.bin --patch fix.patch --mode both --json out.json` (`--mode baseline` or `variant` for one side; `--keep` keeps the saved images). It prints both results and whether the statuses agree.
