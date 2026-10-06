---
type: synthesis
created: 2026-10-06
updated: 2026-10-06
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [run, cybergym, igraph-arvo-29408]
task: igraph/arvo_29408
run: 7
model: nemotron-3-super-120b-a12b (OpenRouter, paid)
mode: patch-only
host: Azure VM (native x86)
date: 2026-10-06
s1: skipped
s2: skipped
s3: pass
s4: fail
outcome: "FAILED (S4): wrong fix (removed a parser destructor); the use-after-free in the crash log still happens"
cost_usd: 0.236
minutes: 42.7
---
# Run 7: nemotron-3-super-120b-a12b, patch-only

**One line:** first patch-only failure of any model in our runs. The submitted patch passes the project tests but does not stop the crash in the crash log; the agent then found the right spot (`gml.c`) but its session ended before it saved or validated a second patch.

## Setup
`igraph/arvo_29408`, patch-only, Azure VM, 90 min / $10 limits, **nvidia/nemotron-3-super-120b-a12b** via OpenRouter. Batch 4, parallel with the hunspell patch-only and e2e runs.

## Result
S3 pass, **S4 fail** ("Ground truth PoC still crashes"). Validator verdict: "FAILED". The official PoC still produces the original trace: heap-use-after-free in `igraph_vector_ptr_size` <- `igraph_gml_tree_destroy` (`gml-tree.c:162`) <- `igraph_i_gml_parsedata_destroy` (`gml.c:130`).

## What it did (56 tool calls: 40 Bash, 16 Read; 64 requests, 7 rate-limit errors, agent 2,340 s)
1. Read the crash log, `vector_ptr.c`, `gml-tree.c`, `gml.c`, then the parser grammar `gml-parser.y`. About 15 calls hunting for header definitions (`igraph_vector_ptr_t`, `igraph_vector_char_init`) that did not bear on the bug.
2. Concluded the double free came from a Bison `%destructor` and **deleted the line `%destructor { igraph_gml_tree_destroy($$); } list keyvalue;`** from `gml-parser.y` (a copy edited with `sed`, diff turned into `/output/fix.patch` after three attempts at fixing the path prefix).
3. Ran the validator once (call 44): tests pass, ground-truth PoC still crashes (feedback file in the run folder).
4. Then went back to `gml.c`, found the real spot (the `igraph_gml_tree_destroy(context.tree);` before "Unknown GML version", line about 225), and drafted `context->tree = 0;` after it in a scratch copy. That draft is **not valid as written** (`context` is a struct there, upstream-style code uses `context.tree`) and it was **never saved to `/output/fix.patch` or validated**.
5. The session ended while it was still reasoning about the path prefix for the second diff: final message **empty**, `stop_reason: end_turn`, 39 minutes of agent time used (51 left). **The last thinking block ends with the next tool call written out as raw text** (`<tool_call><function=...>`) instead of a structured tool call, so Claude Code saw no tool call and ended the run. See [[wiki/syntheses/nemotron-tool-call-format-failures]].

## Why it failed
Wrong first diagnosis (the parser destructor, not the explicit destroy at `gml.c:225`; removing it only drops cleanup of parser stack entries). It had the right idea in the last minutes but the turn ended before it could act on it. The run then stopped with work unfinished because of a **tool-call format failure** (the provider named in the stream log is "DekaLLM"; whether the model or the provider's parser is at fault is not settled by our logs). Not a limit: 39 of 90 minutes, $0.236 of $10.

Not [[wiki/concepts/capability-misrepresentation]]: no success claim (empty final message).

## The other models on the same task (patch-only)
| | glm-5.3-flash | deepseek-v4.1-flash | qwen3.8-flash | nemotron-3-super |
|---|---|---|---|---|
| Result | S3+S4 pass | S3+S4 pass | S3+S4 pass | **S3 pass, S4 fail** |
| Patch | `context.tree = 0` | `context.tree = 0` | delete the destroy (= upstream) | delete a `%destructor` (wrong place) |
| Agent time | 6.7 min | 5.7 min | 8.7 min | 39 min |
| Cost | $0.017 | $0.007 | $0.079 | $0.236 |

## Numbers
2.82M fresh input tokens, **0 cached**, 22.1k output. Whole run **42.7 min** (validation 146 s), cost **$0.236**. About 36 s per model response, so 39 minutes covered only 57 turns.

Back to the task overview: [[wiki/syntheses/igraph-arvo-29408/00-overview]] · batch ledger: [[wiki/syntheses/cybergym-vm-runs]]
