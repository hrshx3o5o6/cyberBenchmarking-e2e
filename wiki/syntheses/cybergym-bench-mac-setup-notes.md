---
type: synthesis
created: 2026-10-01
updated: 2026-10-01
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [setup, docker, networking, reproducibility]
---
# Running CyberGym-E2E on an Apple-silicon Mac with a non-Anthropic model

Gotchas hit while setting up the pilot ([[wiki/syntheses/cybergym-pilot-hunspell-52195]]). The benchmark assumes a **Linux host with Docker** and a model reachable as an Anthropic/LiteLLM endpoint. Work dir: `cybergym-bench/` (clone, shim, run script; only `shim/`, `pyhook/`, `run_pilot.sh` are tracked).

## Gotchas, in the order they bit

| # | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | HF download 403 *gated repo* | dataset `sunblaze-ucb/cybergym-e2e` needs access approval | request access on the dataset page, then `snapshot_download(allow_patterns=[…one task…])` |
| 2 | Wrong first task | `curl/arvo_66012` (README example) has a 565-line real fix and slow `make test`; median fix is 7 lines | pick small ASan tasks; `hunspell/arvo_51988` is a 32-bit i386 build, so use `arvo_52195` |
| 3 | Sanitizers on a Mac? | images are x86_64; README wants `vm.mmap_rnd_bits=28` | Docker Desktop: enable Rosetta, VM ≥12 GB; set the sysctl in the VM (`docker run --privileged --pid=host alpine nsenter -t 1 -m -u -n -i sysctl -w vm.mmap_rnd_bits=28`, resets on VM restart). Free check: `scripts/dataset_validate.py <task>` |
| 4 | Harness wants LiteLLM key API | `--model-provider litellm` calls `/key/generate`, `/key/info`, `/key/delete` | our `shim/llm_shim.py` implements them and forwards Anthropic `/v1/messages` to Ollama |
| 5 | Ollama `count_tokens` 404 | not supported by Ollama's Anthropic API | shim answers with a chars/4 estimate |
| 6 | Agent: `UND_ERR_ABORTED`, 0 requests | Claude Code (Node) tunnels through the squid proxy with `CONNECT`, even for `http://`; squid only allows CONNECT to 443 | route around the proxy: containers reach the host at the bridge **gateway IP** (in `NO_PROXY`) |
| 7 | Gateway IP is the Docker VM, not the Mac | Docker Desktop for Mac | `alpine/socat` container on `--network host` forwards VM `:80` → `host.docker.internal:80` (the shim) |
| 8 | Host cannot resolve `host.docker.internal`; `sudo` not possible from the CLI | no `/etc/hosts` entry | `pyhook/sitecustomize.py` (via `PYTHONPATH`) maps the gateway IP / name to 127.0.0.1 for host-side Python only; no repo edits |
| 9 | macOS non-root can bind `:80` only on the wildcard | OS rule | shim listens on `0.0.0.0:80` and requires a random master key: `/key/*` need it, `/v1/messages` accepts only shim-issued keys |
| 10 | Run killed at 78 requests | my cap counted cache-read tokens as full input | separate caps: fresh input 3M, cache-read 30M, requests 300–400 |
| 11 | OpenRouter streaming: accounting silently wrong, USD cap would never trigger | OpenRouter sends `cache_read_input_tokens: null`; my shim did `+= None` and crashed mid-accounting | null-safe parsing; use provider-reported `usage.cost`; log accounting errors (found by testing the safety net with the real provider before the first paid run) |
| 12 | A model request hangs for 5-15 minutes with no tokens | provider stall (one provider, `StreamLake`); shim read timeout was 900 s, Claude Code aborts at 600 s | cost zero but eats the 90-min budget (about 30 min in the e2e run). Candidate fix: shim inactivity timeout of about 150 s so the call fails fast and Claude Code retries |
| 13 | Agent run ends with exit 137 / `Killed` | the agent ran `pkill -9 -f "fuzz"`; `pkill -f` matches the Claude Code process, whose argv contains the task prompt (mentions "fuzzer") | environment hazard for any agent in this harness; not editable without changing the harness. Record, do not hide; `collect_results.py` flags exit-137 runs |
| 14 | e2e runs are slow: 90 min hit with only ~6 min of model time | x86 builds and fuzz campaigns run under Rosetta emulation on Apple silicon; the agent's own strategy (libFuzzer with 6 workers, autoreconf builds) is tool-time heavy | host limitation, not a model limit. Use a native x86 Linux VM (also enables parallel tasks); quantify with the free ground-truth gate first (Mac: 590 s for four stages) |

## Tooling in `cybergym-bench/` (tracked files)
- `run_pilot.sh start-shim <ollama-model>` / `start-shim-openrouter <model> [usd_per_run] [usd_total] [--dry]` / `run <task> <mode> <model> [timeout]`
- `preflight.sh <task> [ollama|openrouter|mock]`: checks everything, prints the fix for each failure
- `collect_results.py`: tables + `runs/results.json` (submission schema) + `results_extended.csv`
- `shim/llm_shim.py` (key endpoints, caps incl. USD, HTTPS/Bearer upstream), `shim/mock_oracle_llm.py` (scripted control agent), `pyhook/sitecustomize.py`

## Provider findings (2026-10-01)
- **Ollama cloud free plan:** only `gpt-oss:120b`, `gemma4`, `nemotron-3-ultra` worked; glm-5.x, kimi, minimax, deepseek-v4-pro return "not included in your free usage"; free tier = 1 concurrent request, credit amount undocumented.
- **Groq free plan:** 8K tokens/min for every model, below Claude Code's ~15k-token first request, so unusable. Groq has no Anthropic-format endpoint either.
- **OpenRouter `:free` models:** 50 requests/day unless $10+ credits ever bought (then 1,000/day). Serves an Anthropic-format `/api/v1/messages`. `z-ai/glm-5.3-flash` listed at $0.15/M in, $0.50/M out.

## Safety posture
- Firewall on (agent container has no internet; tested that `example.com` and non-80/443 ports are blocked).
- Keys only in env/ignored files; local master key in `runs/.master_key` (git-ignored, mode 600).
- Shim logs token counts per request, never bodies or keys.

## Azure x86 Linux VM (added 2026-10-02)
Reason: Mac runs are emulated x86 (gotcha 14). VM: Azure, Ubuntu 24.04, **x86_64** (Xeon Platinum 8370C), 8 vCPU, 15 GB RAM, 247 GB disk, outbound internet open (OpenRouter, Hugging Face, gcr.io, Docker Hub, PyPI), sudo without password.
- Provisioned: Docker 29.8.2 (official apt repo), `uv`, `vm.mmap_rnd_bits=28` persisted in `/etc/sysctl.d/99-cybergym.conf`, `azureuser` in the `docker` group. Base image pulled in 30 s; ASan test native.
- Copied from the Mac: shim, `collect_results.py`, `run_linux.sh`, task data for `hunspell/arvo_52195` and `igraph/arvo_29408` (8.5 MB). **No secrets, no `runs/`.** Benchmark repo cloned fresh, commit `b46456c`, unmodified.
- **Measured emulation penalty (free ground-truth check, 4 validation stages, same task): Mac/Rosetta 590 s vs VM native 184 s: 3.2x faster.** One task, one run, a mix of compile/test/startup, so it is a floor for the gap on fuzzing-heavy work, not a fuzzing benchmark.
- `run_linux.sh` (Linux variant of `run_pilot.sh`): no forwarder container, no hostname hook; the shim binds only to the Docker bridge gateway (172.x.0.1) of `cybergym-internal` on port 4000, requires the master key for `/key/*`, and is **not** reachable on localhost or the VM's private IP (tested). Container-to-shim path works without the proxy (NO_PROXY includes the gateway).
- Habits: stop/deallocate the VM when idle (Azure bills while allocated); keys only in mode-600 files on the VM, never in chat.

**Oracle e2e (scripted model, free) on both hosts, same task:**

| | Mac (Rosetta) | Azure VM (native) | Speedup |
|---|---|---|---|
| Whole run | 17.2 min | **3.9 min** | 4.4x |
| Final validation (4 stages) | 755 s | **183 s** | 4.1x |
| Ground-truth gate (4 stages) | 590 s | **184 s** | 3.2x |

All S1-S4 PASS on the VM as on the Mac, so the Linux wiring (firewall, gateway-bound shim, container to shim, scoring) is verified without any model or key. Note the oracle run exercises setup and validation, not fuzzing; the gap for fuzz-heavy agent work is likely larger but is not measured. Shim and mock stopped after the test; no key or secret is on the VM.
