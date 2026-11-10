---
type: synthesis
created: 2026-11-06
updated: 2026-11-06
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [cybergym, validation, grader, docker, experiment, speed, shared-images, living-document]
---
# Validation with shared images instead of four separate setups: design, first results, comparison with the standard grader (2026-11-06)

**Status: fourth round done. Variant B (build once, no saved images, S1 in a second container at the same time) gave identical stage statuses in all seven inputs (igraph, four negative controls, binutils, ffmpeg) and was **3.87x faster on binutils and 3.71x on ffmpeg** (5,974 s to 1,612 s) while using 46% less container time than the standard grader. It beats the shared-images variant (A: 1.71x and 1.34x). Not yet done: the equivalence check on the 48 saved pairs, repeats, a harness patch.**

## Verdict so far: is it helping? (2026-11-06)
**Yes, where it matters, and modestly for the whole run.**
- **Correct:** the stage statuses were identical to the standard grader in nine comparisons, including a failing stage 4, a failing patch, a build error, a patch that only disables the code (S3 failed it in both) and a PoC that does not crash. No case where the variant turned a failure into a pass.
- **Faster on heavy builds, but less than hoped on the heaviest:** binutils (about 7 minutes per stage) went from 1,725 s to 1,006 s, **1.71x**; ffmpeg (about 25 minutes per stage) from 5,974 s to 4,458 s, **1.34x**, because saving the two images cost 1,462 s (33% of the variant); without the saves it would have been 1.99x. On tiny projects (igraph, md4c) it was 0.67x to 1.49x: the saves cost as much as the work they avoid. **The image save is the weak point of this design.**
- **Effect on the 100-task run, replayed** (the report's replay model, which reproduces the 11.3 h; the rows marked hypothetical are not measured):
| Change to grading | As run | ffmpeg first |
|---|---|---|
| none (standard) | 11.3 h | 9.7 h |
| shared images on ffmpeg tasks, 1.34x (**measured on ffmpeg**) | 10.5 h | 9.5 h |
| the same without the image-save cost, 1.99x (hypothetical) | 9.8 h | 9.2 h |
| **variant B, 3.71x on ffmpeg (measured)** | **9.1 h** | **8.9 h** |
| shared images and parallel stages, 2.9x (not tested) | 9.3 h | 9.0 h |
| the four standard stages in parallel, 3.9x (not tested) | 9.1 h | 8.9 h |
| grading 2x faster (the report's scenario) | 9.7 h | 8.8 h |
  So shared images as built would have saved about 0.8 h of 11.3 h on the whole run (about 7%) and only 0.2 h on top of ordering ffmpeg first. **Variant B, as measured, would have saved 2.2 h (11.3 h to 9.1 h) and, together with ffmpeg first, 2.4 h (to 8.9 h), close to the floor set by agent time (about 7.4 h) plus packing.** Ordering alone (1.6 h) remains the cheapest lever.
- **Resource view:** shared images save compute (1,725 s of container time to 1,006 s on binutils) at the price of disk (the saved images were several GB) and 11 to 92 s of save time; parallelism saves wall time but not compute. The VM sat at load 1.0 on 16 vCPUs during grading, so the CPU for parallel stages is there.
- **Recommended use:** variant B, not the shared images. It matched the standard grader's statuses on all seven inputs, took 3.7x to 3.9x less wall time on the two heavy projects and 46% less compute on ffmpeg, with no images to write. Adopt only after the equivalence check on the 48 saved pairs passes and the harness change (run S1 and the patched build side by side; S2, S4, then S3 in one container) is written as a patch through `patch_cybergym.py`. Keep ffmpeg-first ordering as well.
- **Limits of the evidence:** one run each of two heavy projects and a few small ones; the image saves are noisy (11 s to 1,175 s depending on image size); the hypothetical rows are projections.

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

### 4d. The heaviest project: ffmpeg `oss-fuzz_42537665` (task-specific 51.4 GB build image; about 25 minutes per stage)
Statuses identical: passed x4 in both. **Baseline 5,974 s (99.6 min), variant 4,458 s (74.3 min): 1.34x, 1,516 s saved.**
| Standard grader | Seconds | Variant | Seconds |
|---|---|---|---|
| S1 (setup 103.3 + `validate.py` 1,412.0) | 1,515.3 | setup 34.4, `prepare.sh` 0.1, **save prepared image 286.5** (once, total) | 366.0 |
| S2 (setup 39.5 + 1,439.4) | 1,478.9 | S1: build vulnerable tree + run PoC | 1,428.3 |
| S3 (setup 34.1 + 1,474.5) | 1,508.7 | patched build once (about 1,430) + **save image 1,175.2** (total) | 2,627.9 |
| S4 (setup 35.1 + 1,436.4) | 1,471.5 | S2 PoC only / S3 `test.sh` only / S4 PoC only | 0.3 / 30.4 / 0.2 |
| **Total** | **5,974.4** | **Total** | **4,457.7** |
- The work that disappears is about 2 x 1,420 s of builds plus three setups (about 210 s): about 3,050 s. The two image saves cost **1,462 s (33% of the variant)**, so the net saving is 1,516 s. **Without the saves the same plan would take about 2,996 s: 1.99x.**
- Saving the patched-build image (33 GB of build tree, 19.6 minutes) is the single largest cost of the variant: `docker commit` has to write and hash a layer of many small files, about 28 MB/s here. The prepared image (19 GB, 4.8 minutes) cost less.
- Once saved, the three checks took under 31 s in total (S3's tests 30.4 s). The VM's load stayed at about 1.0.
- A caveat on the comparison with the 100-task run: this baseline took 99.6 minutes, against 131 minutes of setup and grading for the same task in that run, which shared its node with other work.

### 4e. Variant B: build once, no saved images, two containers at once (2026-11-07)
**The design.** Container A builds the vulnerable tree and runs S1 exactly as the standard grader. Container B, at the same time, runs the standard S2 through `validate.py` (prepare, snapshot, restore, apply the patch, build the patched tree **once**, run the agent's PoC), then in the same container S4 (the ground-truth PoC, which only executes the binary) and last S3 (the tests, which can modify the tree). If S2 does not pass, B stops there. The skip rules are applied to the results afterwards, so the statuses are the ones the standard grader would report. No image is saved. Script: `tools/grader_bench.py --mode b` (or `bothb`, which also runs the standard grader on the same input).
**Results.** "Container time" is the sum of the two containers, the compute-side cost. Standard times for igraph and the controls are from a standard run on the same input in the same session; for binutils and ffmpeg they are the recorded standard results of 4c and 4d.
| Input | Statuses same as standard | Standard | Variant B wall | Ratio | B container time |
|---|---|---|---|---|---|
| igraph, real PoC and patch (all four pass) | yes | 133 s | 58 s | 2.27x | 97 s |
| control: PoC that does not crash (S1 fails) | yes (failed, skipped x3) | 28 s | 60 s | **0.47x** | 99 s |
| control: no-op patch (S2 fails) | yes | 57 s | 47 s | 1.20x | 82 s |
| control: patch that breaks the build (S2 error) | yes | 56 s | 43 s | 1.31x | 74 s |
| control: patch that disables the code (S2 passes, S3 fails) | yes (passed, passed, failed, skipped) | 103 s | 60 s | 1.71x | 99 s |
| binutils `arvo_55933` | yes (passed x4) | 1,725 s | 446 s | **3.87x** | 864 s |
| ffmpeg `oss-fuzz_42537665` | yes (passed x4) | 5,974 s | 1,612 s | **3.71x** | 3,199 s |
**The three designs on the two heavy projects**
| | Standard | A: shared images | B: build once, two containers |
|---|---|---|---|
| binutils, wall time | 1,725 s | 1,006 s (1.71x) | **446 s (3.87x)** |
| ffmpeg, wall time | 5,974 s | 4,458 s (1.34x) | **1,612 s (3.71x)** |
| ffmpeg, container time (compute) | 5,974 s | about 4,458 s | **3,199 s (46% less)** |
| image saves | none | two, 1,462 s on ffmpeg | none |
**Observations**
- **Correct in every case, including the ones designed to go wrong.** The code-disabling control is the sharpest: S2 passes, S3 fails, and S4 must be skipped. In B the raw S4 check had already run and passed (it runs before the tests), but the skip rule masks it, giving the standard grader's statuses. Same for the non-crashing PoC, where B's raw S2, S4 and S3 all passed and were masked to skipped because S1 failed.
- **Why it is fast on heavy builds:** both containers do one build each (about 1,577 s of it on ffmpeg) and run at the same time, so the wall time is the longer build plus the checks (S3's tests took 31 s on ffmpeg and 7 s on binutils; S2 and S4 take under a second beyond the build). The standard grader runs four builds in a row.
- **Why it also uses less compute:** two builds and two setups instead of four of each (3,199 s against 5,974 s on ffmpeg), and no 33 GB images to write.
- **Where it loses:** when S1 fails, B has already started the patched build, so it spends 99 s where the standard grader needs 28 s (0.47x). S1 failed in 2 of 47 graded tasks in the 100-task run. When S2 fails or errors B stops early and still wins (1.2x and 1.3x).
- **Resources:** two builds at once is twice the simultaneous CPU of the standard grader (the VM stayed near load 1 to 2 on 16 vCPUs) and two build trees on disk at once (about 30 GB each for ffmpeg); 187 GB were free afterwards.
- **What it does not prove:** seven inputs, one run each; the contamination question (the harness's own comment names stage-to-stage state) is answered only for these cases. S3 runs last for exactly that reason, and the tests ran on a tree where two PoC runs had already executed without any difference in result.
- A note on how this round was run: the watcher I set for the first test series missed its completion marker, so the notification came two hours late; the ffmpeg run itself had started automatically on time and finished with the VM idle afterwards.

### 4f. Is the patched build reproducible? (2026-11-09)
**The question.** The standard grader compiles the patched tree three times (S2, S3 and S4, each in its own container); variants A and B compile it once and reuse the result. That is the same thing only if every compile gives the same bytes. Until now this was assumed, not checked.
**The test** (`tools/repro_check.py`): build the patched tree in 3 independent fresh containers, each with its own setup, `prepare.sh` and compile exactly as the standard S2 does (all three ran at once on the head VM), then compare the SHA-256 of every file under `/out` (the binaries the PoC runs) and of every `*.o`, `*.a` and `*.so*` under `/src` (what the tests may link). Data: `aws-vm-data/grader-bench/repro_{igraph,md4c,binutils}.json`.
| Project | Builds | S2 status | `/out` files identical | Object, archive and library files identical | Build time each |
|---|---|---|---|---|---|
| igraph `arvo_29408` | 3 | passed x3 | 4 of 4 | 794 of 794 | 58 s |
| md4c `arvo_31332` | 3 | passed x3 | 2 of 2 | 94 of 94 | 19 s |
| binutils `arvo_55933` | 3 | passed x3 | 59 of 59 | 1,032 of 1,032 | 464 s |
**Reading.** For these three projects the three patched builds the standard grader makes are byte-identical, so building once (A or B) hands every stage exactly the files it would have built itself; this also means the S2 and S4 binaries of the standard grader are the same bytes. It supports the nine identical status comparisons with a direct check. **Not shown:** other projects (ffmpeg, the heaviest and the one where A and B matter most, is not tested; about 26 minutes for 3 parallel builds and about 90 GB of disk), files outside `/out` and the object files, and builds that differ by timestamp in a file that is not an object, archive or library.

### 4g. Setup A as a patch in the harness, checked through the harness's own functions (2026-11-09)
`tools/patch_setup_a.py` adds an optional shared-image validation path to `scripts/run_agent.py` (off unless `CYBERGYM_VALIDATION_MODE=shared`; the original function is kept, renamed `run_final_validation_standard`; a failure of the sharing machinery or too little free disk runs the standard grader instead; `summary.json` records `validation_mode`; saved images are named `cgval-<id>-prep` and `-built` and always removed; optional per-node cap `CYBERGYM_SHARED_MAX_CONCURRENT`). `tools/setup_a_check.py` and `tools/setup_a_fallback_test.py` call the real functions. Data: `aws-vm-data/grader-bench/` (seta_*.json are on the VM; the table below is the record).
| Input | Shared (A) | Standard | Same | A against standard |
|---|---|---|---|---|
| igraph, real pair | passed x4 | passed x4 | yes | 122 s against 147 s (1.21x) |
| control: PoC that does not crash | failed, skipped x3 | same | yes | 46 s against 33 s (0.70x) |
| control: no-op patch | passed, failed, skipped x2 | same | yes | 70 s against 65 s (0.93x) |
| control: patch that breaks the build | passed, error, skipped x2 | same | yes | 60 s against 63 s (1.05x) |
| control: patch that disables the code | passed, passed, failed, skipped | same | yes | 88 s against 115 s (1.30x) |
| md4c (S4 fails) | passed x3, failed | same | yes | 78 s against 76 s (0.97x) |
| binutils `arvo_55933` (recorded passed x4) | passed x4 | recorded | yes | 1,060 s against 1,725 s (1.63x) |
Fallbacks (igraph real pair): switch unset, disk below the threshold, `prepare.sh` failing (simulated) and image save failing (simulated) each returned passed x4 with the mode `standard`, `standard_low_disk`, `standard_after_shared_failure` and `standard_after_shared_failure`; no image was left in any case. Concurrency cap: three simultaneous calls with the cap at 1 ran one at a time (90 s, 194 s, 284 s), all passed, the wait was logged. 13 checks in all, no difference in any stage status. The replay on the recorded DeepSeek pairs was not run before the GLM 5.3 Flash run started.

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
4. Gate: an equivalence check on saved pairs (the 48 tasks of the 100-task run that have a PoC and patch) before anyone relies on it. The reproducibility check (4f) is done for igraph, md4c and binutils (identical bytes); ffmpeg is still open.

## 8. Next steps
Done: negative controls (4b), binutils (4c), ffmpeg (4d), variant B on igraph, the controls, binutils and ffmpeg (4e).
1. **Equivalence on the 48 saved pairs** (and a mix of failing pairs) for variant B against the standard grader: the gate before any real use. These can run several at a time on the VM (about 25 minutes each for ffmpeg-sized pairs).
2. **Repeats** on a second heavy task (binutils `arvo_51010`, ffmpeg `oss-fuzz_438780119`) to put a spread on 3.7x to 3.9x.
3. **The harness change:** run S1 and the patched build side by side in `run_final_validation`; `validate.py` gets an option to run S2, S4 and S3 in one container after one build without restoring and rebuilding between them; shipped as a patch through `scripts/patch_cybergym.py`, and proposed upstream.
4. **Resource budgeting for validation:** two builds at once per graded task means the Ray scheduler should reserve about 2 CPUs and 60 GB of disk for each validation (the split-validation idea of the 100-task report).
5. **Optional refinements:** skip the patched build when the agent's own stage-1 check never saw a crash; stop container B when S1 fails early.

## 9. Reproduce
On the head VM, from a folder holding `grader_bench.py`, a PoC and a patch: `~/cybergym-e2e/.venv/bin/python grader_bench.py --harness ~/cybergym-e2e --task igraph/arvo_29408 --poc poc.bin --patch fix.patch --mode both --json out.json` (`--mode baseline` or `variant` for one side; `--keep` keeps the saved images). It prints both results and whether the statuses agree.
