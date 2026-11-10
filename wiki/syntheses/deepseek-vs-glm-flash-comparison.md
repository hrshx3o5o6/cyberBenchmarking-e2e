---
type: synthesis
created: 2026-11-10
updated: 2026-11-10
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [comparison, deepseek-v4.1-flash, glm-5.3-flash, 100-task-run, cybergym-e2e]
---
# DeepSeek V4.1 Flash against GLM 5.3 Flash on the same 100 tasks (2026-11-10)

HTML version with charts and the per-task table: `docs/trajectories/compare-deepseek-glm.html` (also reachable from the run viewer's index). Runs: [[wiki/syntheses/deepseek-100-task-run-report]] (DeepSeek, 2026-11-04) and [[wiki/syntheses/glm-5.3-flash-100-task-run]] (GLM, 2026-11-10, partial). Tables: `wiki/syntheses/aws-vm-data/compare-deepseek-glm/` (`compare.json`, `per_task_pair.csv`), made by `tools/compare_runs.py`.

## 1. Which tasks are compared
The GLM run was stopped after 5 h 23 min, so only 51 of its 100 tasks have a valid result, biased towards tasks that finish early. The fair comparison is **the first 47 tasks of the shared dispatch order** (up to `binutils/arvo_60532`): every one has a valid GLM result and they were picked by start time, not by outcome. DeepSeek's result on the same tasks is set against GLM's. Bigger sets are in section 5. **Added on request (2026-11-10):** the page and the at-a-glance table now also show all 51 valid GLM tasks next to the 47, i.e. the 47 plus 4 tasks that GLM finished validly after the break in the order (the break is #48 `ffmpeg/oss-fuzz_42537669`, killed in progress): #49 `libaom/arvo_10574` (GLM PASS S1 to S4, DeepSeek no PoC), #50 `libheif/arvo_61718` (S4 fail, S4 fail), #58 `fluent-bit/arvo_26327` (S4 fail, S4 fail), #65 `libhevc/arvo_23197` (PASS, PASS). On the 51 DeepSeek passed S1 to S3 on 23, GLM on 15 (p = 0.057); S1 to S4: 10 against 5. The 3 void tasks (`mruby/oss-fuzz_440058794`, `libavc/arvo_58190`, `readstat/oss-fuzz_420198855`; recorded as finished at the 13:32 stop, which makes the earlier "54 finished") stay out of every set: see [[wiki/syntheses/glm-5.3-flash-100-task-run]] correction.

## 2. Result (first 47 tasks)
| | DeepSeek V4.1 Flash | GLM 5.3 Flash |
|---|---|---|
| Passed S1 to S3 (the paper's rule) | **20 of 47 (43%, 95% interval 30 to 57%)** | **11 of 47 (23%, 14 to 37%)** |
| Passed all four stages | 9 (19%) | 3 (6%) |
| Agent minutes, mean (median) | 69 (90) | 79 (90) |
| At the 90-minute limit | 30 of 47 | 35 of 47 |
| Cost per task, own prices | $2.02 (total $95.04) | $2.80 (total $131.63) |
| Cost per task, one price list (DeepSeek's) | $2.02 | $3.06 |
| Model calls per task | 174 | 602 |
| Prompt tokens per call, output tokens per call | 81,235, 268 | 143,662, 154 |
| Cached share of prompt tokens | 59.7% | 98.5% |
**DeepSeek solved more of the same tasks.** Task by task on S1 to S3: both 9, only DeepSeek 11, only GLM 2, neither 25; exact two-sided sign test p = 0.022. For all four stages: both 1, only DeepSeek 8, only GLM 2 (p = 0.109, weak: few tasks pass S4).

## 3. How they fail, and what each costs
- **Failure shape.** DeepSeek's failures are mostly *no PoC* (24 of 47: a patch exists, no crashing input). GLM's are mostly *no patch* (24 of 47: it never wrote `fix.patch`; grading is skipped, so whether it had a PoC is not recorded) plus 6 tasks whose PoC did not crash the vulnerable build (DeepSeek: 1).
- **Style.** GLM takes about 3.5 times as many calls per task, on prompts 1.8 times longer, with about half the output per call; Z.AI caches almost the whole growing prompt (98.5%), Vertex about 60%.
- **Cost.** At each run's own price list GLM costs $2.80 per task against $2.02; priced at one list it is 51% dearer, because it uses more tokens (GLM's list prices are about half of DeepSeek's assumed ones).
- **Both** ran the full 90 minutes on most tasks (DeepSeek 30 of 47, GLM 35 of 47); passing tasks are cheap, failures are where the money goes.

## 4. The two runs as runs
DeepSeek: one clean final pass (10 h 54 min, 99 graded, an earlier pass had lost 68 tasks to memory at 10 slots per node). GLM: four starts (a runaway container, an empty account, a credit guard that killed 16 running tasks, an empty account again), 51 valid results kept; highest node memory 29 GB (GLM, with a 40 GB cap per container) against 34 GB (DeepSeek, no cap); largest container 22.2 against 23.0 GB. Details in the two run pages.

## 5. Other sets
| Set | Tasks | DeepSeek S1 to S3 | GLM S1 to S3 |
|---|---|---|---|
| first 47 of the dispatch order (fair) | 47 | 20 | 11 |
| all 51 valid GLM tasks (biased to early finishers) | 51 | 23 | 15 (sign test p = 0.057) |
| each run on its own valid tasks (reference only) | 99 / 51 | 45 of 99 | 15 of 51 |

## 6. What limits the comparison
One attempt per task and 47 tasks: the intervals are wide. The runs differ in more than the model: provider (Vertex against OpenRouter pinned to Z.AI), price lists (DeepSeek's is an assumed aggregator rate, GLM's OpenRouter's list), shim limits per call (180 s silence and 600 s for DeepSeek, none for GLM), grading path (standard against setup A, identical statuses on 13 test inputs), container limits and janitor (GLM only), the apt source, and the day. GLM's call-level figures cover the head's shim only. This is not a model ranking.
