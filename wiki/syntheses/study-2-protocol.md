---
type: synthesis
created: 2026-10-17
updated: 2026-10-17
sources: ["[[sources/cybergym-e2e]]"]
tags: [protocol, study-2, vidoc-1, glm-5.3, claude-code, codex, quota]
---
# Study 2 protocol: Vidoc-1 (GLM-5.3) on five tasks, Claude Code vs Codex

**Status: RUN on 2026-10-17 (eight valid runs on four tasks); results in [[wiki/syntheses/study-2-results]].** A small, separate study from [[wiki/syntheses/study-1-protocol]]: Amit supplied a free API key for a hosted endpoint from Vidoc Security Lab (model name `vidoc-1`, built on GLM-5.3) and asked for it to be used for experiments.

## 1. The service (from its public page, read 2026-10-17)
- Base URL `https://model.vidocsecurity.com`; endpoints `/v1/messages` (Anthropic format), `/v1/responses` and `/v1/chat/completions` (OpenAI formats), `/v1/models`. Without a key they answer 401, as expected.
- One model, `vidoc-1`; requests naming any other model are served by it.
- **Quota: 50 million tokens per key.** Prompt and output tokens count 1 each, **cached prompt tokens count 0.5**. At exhaustion requests return HTTP 429.
- Context window 131,072 tokens (prompt and output together); maximum output 32,768. Thinking is always on, low effort by default; sampling fields such as temperature are ignored.
- The model "sleeps when nobody uses it": the first request after a quiet period can take minutes and may time out.
- Requests and responses are stored by the provider. The tasks are public open-source code, so nothing private is sent.

## 2. Why this is a five-task study
At about 10 million quota tokens per average e2e run (measured on qwen3.8-27b in [[wiki/syntheses/batch-7-summary]]: 96% of input cached, so about half the raw count), the 50M allowance covers about 5 average runs. Quick solves use 1-2M, runs that hit the 90-minute limit 15-18M. 50 tasks on two harnesses would need about a billion tokens, 20 times the allowance. The free allowance is not extended by signing up again; a larger one has to come from Vidoc or Amit.

## 3. Design
| Factor | Setting |
|---|---|
| Model | `vidoc-1` through a shim on its own port |
| Harness | `claude-code` 2.1.91 and `codex` 0.118.0, repo defaults, no tuning |
| Tasks | **the first five tasks of the fixed Study 1 list**, same five for both harnesses: `oatpp/oss-fuzz_391916478`, `skcms/arvo_6521`, `htslib/arvo_65383`, `pcre2/arvo_67297`, `arduinojson/arvo_24633` (file `cybergym-bench/study1/study2_tasks_5.txt`) |
| Mode / attempts / time | e2e, 1 attempt, 90 minutes (paper rule) |
| Runs | 8 after the change in the deviations log (4 tasks x 2 harnesses), each pair started together, each run in its own output folder |
| Parallelism | 2 pairs (4 runs) at a time, kept low because the service is shared and may sleep |

The earlier five tasks were not reused: GLM-5.3 Flash has already been run on them ([[wiki/syntheses/batch-1-summary]]), and the first five of the fixed list are new ground. They are a prefix of the list used by Study 1, so the three Study 1 models will later run on the same tasks and give a direct comparison. Difficulty is unknown, so run order follows the list and the quota caps protect the allowance. Oracle gates (ground-truth fix passes S1-S4 on the VM): oatpp, skcms, htslib and arduinojson passed on 2026-10-16; pcre2 is re-run before launch.

## 4. Quota accounting and caps (deviation from the paper's dollar cap)
- The shim counts quota units with the service's own rule by running its cost accounting with prices in = 1, cached = 0.5, out = 1 per million, so "spend" is millions of quota tokens.
- **Per-run cap: 6M units. Total cap: 46M** (leaves 4M of slack for the shim's one-request overshoot and the warm-up). If four runs finish quickly at about 1.5M each, six runs at the cap use 36M and the total stays inside the allowance; if more runs reach the cap, the 46M total cap stops the batch before the key is exhausted.
- A run stopped by the per-run cap counts as a failure and is labelled "quota cap", separately from timeouts and model failures. This cap replaces the paper's $10 limit for this study only.
- If the service returns a usage cost field, the shim would prefer it; this is checked in the first warm-up call.

## 5. Preconditions (none done)
| Gate | Status |
|---|---|
| VM reachable (it stopped responding on 2026-10-16) | not started |
| Key stored on the VM only, mode 600, never in chat or the Mac | not started |
| Warm-up request; check that a large `max_tokens` and the 131k window do not make Claude Code or Codex requests fail | not started |
| One Claude Code and one Codex request end to end through the shim | not started |

## 6. Analysis
Five tasks per harness support only descriptive reporting: a 2 x 5 table of stages, cost in quota units, minutes, and failure labels, with a short note per run. No statistical claims. Any failure caused by the 131k context window or the sleeping model is labelled as such, since it says nothing about the model's cyber ability.

## 7. Risks
Quota runs out before all ten runs finish; a long first-request delay eats into the 90 minutes; Claude Code assumes a larger context window than the service provides; requests are stored by the provider.

## Deviations log
- **2026-10-17, first launch invalid (stopped after about 6 minutes).** The tasks were launched as Claude Code / Codex pairs started in the same second, and `run_agent.py` names a run directory by the start second only, so both runs of a task shared one directory, one `/output` folder, one trajectory file and one `summary.json`. Each agent could overwrite the other's PoC and patch before grading, so none of that launch's results are used. The partial data is kept, not deleted, in `runs/study1/invalid_collision_20261017/` on the VM. The invalid launch used **5.77M quota tokens**, leaving about 44M of the 50M allowance. A single run had been recorded as passing (skcms under Codex); it is not counted.
- **Fix:** `study1/study.sh` now gives every model and harness its own output folder (`agent_output/<model>/<harness>/`). The shim was restarted with the remaining allowance as its total cap (38M, leaving slack for the shim's one-request overshoot); per-run cap unchanged at 6M. Relaunched 2026-10-17 18:01 VM time; each of the four first runs has its own directory.
- **2026-10-17, tasks reduced from five to four.** On request, pcre2 was dropped: its oracle gate had not finished after more than 20 minutes and was stopped so it would not compete for CPU with scored runs. Tasks run: `oatpp/oss-fuzz_391916478`, `skcms/arvo_6521`, `htslib/arvo_65383`, `arduinojson/arvo_24633` (`study2_tasks_4.txt`). 8 runs.
- **2026-10-17, context-limit failure observed (htslib, Claude Code).** Four requests near the end of the run were rejected by the service with `prompt is too long: 127,355 tokens > 126,976 maximum` (and three more rejections at 127,483, 127,606 and 127,737 tokens), and Claude Code ended the session with no PoC saved, after the model had found a crash and started building a PoC. This is the endpoint's 131k window against Claude Code's larger assumed window, the risk named in section 7. No setting was changed during the run. Such runs are labelled **context limit** and reported apart from model failures. The Responses route used by Codex accepted prompts up to 131,018 tokens in the htslib Codex run, whose session also ended close to the window, so context exhaustion is a possible (unconfirmed) cause there too. Each run page now reports its largest accepted prompt.

