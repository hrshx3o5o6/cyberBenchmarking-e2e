---
type: synthesis
created: 2026-11-05
updated: 2026-11-05
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [qwen, vertex, vllm, runbook, deployment, endpoint, redeploy, how-to, living-document]
---
# How we changed and redeployed the Qwen endpoint ourselves (runbook, 2026-11-05)

What exactly was done on 2026-11-04 and 2026-11-05, as steps you can repeat. Background and results: [[wiki/syntheses/qwen27b-prefix-caching-and-cuda-graphs]], [[wiki/syntheses/qwen-capacity-levers-test]]; what to change next: [[wiki/syntheses/qwen-scaling-plan]]. **No ids in this page**: `<PROJECT_ID>`, `<PROJECT_NUMBER>`, `<ENDPOINT_ID>`, `<REGION>` (asia-southeast1 for us) and `<VM_HOST>` (user@address of the head) are filled in from your own notes; never commit them (the remote is public).

## 1. Where things are
| What | Where |
|---|---|
| Amit's deploy script | `src/gcp/manage_endpoint.py` in the private repo `prescera/benchmark-evals` (commit "added gcp file") |
| Our edited copies (contain the project id, so **outside this repository**) | Mac: `spark/qwen-deploy/` (`manage_endpoint.orig.py` = Amit's, `manage_endpoint.py` = our tested arguments, `README.txt`) |
| Probe and test tools | `tools/qwen_endpoint_probe.py`; `tools/qwen_ops/` (`run_arm_tests.sh`, `qwen_conc_monitor.py`, `conc_watch.sh`, `restart_shim_pinned.py`) |
| Registry route for the shim | `qwen3.8-27b@vertex-dedicated` in `tools/models.toml` of the runner copy ([[wiki/syntheses/model-registry-design]] section 14) |

## 2. What the script does
`manage_endpoint.py <action>` with action `status`, `start`, `stop`, `restart` (stop then start), `register`, `pause`, `delete`, `close`:
- finds the one endpoint by a label (`lifecycle_key` = the `NAME` in the script);
- `start` registers a Vertex "model" (not the weights: a **container recipe**: image, arguments, routes, environment) whose label holds a hash of that recipe, reuses it if the same recipe exists, and deploys it to the endpoint: machine `a2-ultragpu-1g` (one A100 80GB), minimum and maximum replicas 1, all traffic;
- the container is Google's prebuilt `pytorch-vllm-serve` image (tag `20260713_0916_RC01`) running `python -m vllm.entrypoints.api_server`; **the weights are downloaded from Hugging Face at every start** (about 54 GB; 16 to 25 minutes until it answers);
- `stop` undeploys everything and releases the GPU; the endpoint and the model records stay (each new argument list left one more model record, harmless).
The serving arguments are the list `VLLM_ARGS` near the top of the script; the endpoint address does not change when they do.

## 3. One-time setup (Mac)
```
cd spark/qwen-deploy                         # outside the repo
uv venv .venv && uv pip install --python .venv/bin/python google-cloud-aiplatform
gcloud auth application-default login        # you run this (browser); it expires and must be repeated
# set PROJECT_ID at the top of manage_endpoint.py (it refuses to run with the placeholder)
.venv/bin/python manage_endpoint.py status   # expect: "STOPPED: no model deployed" or the dedicated DNS name
```

## 4. Change the serving arguments and redeploy
1. Copy the script (`cp manage_endpoint.py manage_endpoint_arm.py`) and edit `VLLM_ARGS`. One flag per experiment, so the effect can be attributed.
2. Run `.venv/bin/python manage_endpoint_arm.py restart` (or `start` when nothing is deployed). It blocks until deployed (run it in the background; the output ends with `DEPLOYED: serving compute may be incurring charges.` and the dedicated DNS name). **A deployment cannot be cancelled** (the operation answers "not cancellable"): once started, wait for it, then stop or restart.
3. Check with `status` and a direct request (section 6) before testing.
4. `.venv/bin/python manage_endpoint_arm.py stop` when finished; confirm `status` says "STOPPED: no model deployed". An idle deployed GPU keeps billing (38 minutes of idle time on 2026-11-05 after the pilot).

## 5. What we changed (every configuration so far)
| Config | `VLLM_ARGS` change against Amit's original | Window (UTC) | Result |
|---|---|---|---|
| A: original | `--enforce-eager`, no prefix caching | 2026-11-04 03:48 to 14:02 | 9.2 tokens/s, no cache benefit |
| B | + `--enable-prefix-caching` | 16:18 to 16:57 | repeat prompt 9 s to 0.5 s; still 9 tokens/s |
| C | B minus `--enforce-eager` (CUDA graphs) | 16:57 to 17:57 | 28 tokens/s; this is the kit's `manage_endpoint.py` |
| Arm 1 | C + `--max-num-seqs=16` | 2026-11-05 12:28 start, up 12:56 to 13:24 | no change in warm capacity (about 120k tokens) |
| Arm 2 | arm 1 + `--kv-cache-dtype=fp8` | 13:24 restart, up 13:40, undeployed 16:04 | warm capacity +25% to +50%; 3 agents fit, 4 collapse |
Exact diffs: original to C removes `"--enforce-eager",` and adds `"--enable-prefix-caching",`; C to arm 2 adds `"--max-num-seqs=16",` and `"--kv-cache-dtype=fp8",`. Everything else is unchanged: model `Qwen/Qwen3.8-27B` at the pinned revision, `--max-model-len=262144`, `--gpu-memory-utilization=0.9`, `--tensor-parallel-size=1`, chunked prefill, `--enable-auto-tool-choice`, `--tool-call-parser=qwen3_coder`, `--reasoning-parser=qwen3`. Not tried yet: tensor parallelism over more GPUs (machine type, accelerator count and `TENSOR_PARALLEL_SIZE` change together), FP8 weights, `--enable-prompt-tokens-details`.

## 6. Test the endpoint from the Mac
```
TOKEN=$(gcloud auth application-default print-access-token)
curl -s https://<ENDPOINT_ID>.<REGION>-<PROJECT_NUMBER>.prediction.vertexai.goog/v1/projects/<PROJECT_NUMBER>/locations/<REGION>/endpoints/<ENDPOINT_ID>/chat/completions \
  -H "Authorization: Bearer $TOKEN" -H "x-goog-user-project: <PROJECT_NUMBER>" -H "content-type: application/json" \
  -d '{"model":"Qwen/Qwen3.8-27B","messages":[{"role":"user","content":"Say OK"}],"max_tokens":5}'
```
Capacity and speed probe (`tools/qwen_endpoint_probe.py`; environment `QWEN_PROJECT_NUMBER`, `QWEN_REGION`, `QWEN_ENDPOINT_ID`):
```
python3 -I tools/qwen_endpoint_probe.py decode                              # tokens/s, 1/2/4/8 streams, a tool call
python3 -I tools/qwen_endpoint_probe.py residency --tokens 30000 --count 24  # how many 30k prompts stay warm (baseline 4)
python3 -I tools/qwen_endpoint_probe.py residency --tokens 59000 --count 12  # (baseline 2)
python3 -I tools/qwen_endpoint_probe.py needle --tokens 90000 --trials 6     # hidden code at 10/50/90%: quality check
python3 -I tools/qwen_endpoint_probe.py agents --counts 3 4 5 --turns 10     # back-to-back agents; stop at the first collapse
QWEN_ENV=<file exporting the three variables> OUT=<dir> tools/qwen_ops/run_arm_tests.sh <label>   # the whole suite, stops at the first collapse
```
A full suite is about 30 minutes of GPU time. Compare with the baselines in [[wiki/syntheses/qwen-capacity-levers-test]] section 4.

## 7. Run real tasks on it (head VM)
1. **Token for the shim.** The head has no Google login. On the Mac: `python3 tools/push_vertex_token.py --host <VM_HOST> --key ~/.ssh/id_ed25519 --interval 1800` (leave it running, Mac awake; tokens last about an hour). **Stopping it deletes the token file on the head** (unless `--keep`), so restart it before any run.
2. **Shim on the head** (port 4100; registry route `qwen3.8-27b@vertex-dedicated`; needs `VERTEX_PROJECT_NUMBER`, `VERTEX_ENDPOINT_ID`, `VERTEX_ENDPOINT_REGION` in its environment, for example in `config/.env`): `TOKEN_FILE=$HOME/.secrets/vertex_token tools/start_shim.sh qwen3.8-27b@vertex-dedicated tokens` (no price, so token caps). Check `curl http://<docker gateway>:4100/health` and run `qwen_smoke.py` (a tool-call round trip through the shim).
3. **Name resolution check (found 2026-11-05).** From the head: `dig +short @8.8.8.8 <endpoint dns name>` against `getent hosts <endpoint dns name>`. If they differ and calls from the head die with `SSLEOFError` or connection resets, pin the working address in the shim: `python3 tools/qwen_ops/restart_shim_pinned.py <endpoint dns name> <ip>` (no system file is touched).
4. **Slots.** Concurrency is Ray's `benchmark_slot` resource, fixed when the head starts. To change it: stop our head by its temp directory only (`python3 ~/autoscaler/stop_head.py <temp dir name>`; run it from a shell whose own command line does not contain that name, or it kills itself) and start it again with a new `--temp-dir` and the slot count you want (we used 4, then 6): `cd ~/benchmark-evals; (set -a; . config/.env; set +a; RAY_AUTH_MODE=token AUTOSCALER_METRIC_PORT=44219 nohup .venv/bin/ray start --head --node-ip-address=<head private ip> --port=6381 --ray-client-server-port=9991 --num-cpus=16 --resources='{"benchmark_slot":6}' --include-dashboard=false --autoscaling-config=$HOME/autoscaler/rendered/cluster.prepared.yaml --temp-dir=/tmp/ray-h6 > ~/autoscaler/head6.log 2>&1 < /dev/null)`, then `ray status --address <head private ip>:6381` should show the slots. Background: [[wiki/syntheses/autoscaled-vertex-run-plan]].
5. **Manifest and driver.** Copy a manifest (for example `config/qwen-pilot2.json`), set `tasks`, `work_root` (new for every attempt), `benchmark_slots`, `start_stagger_seconds` (240 for a ramp). Launch: `date +%s > ~/autoscaler/qwenconc.start; (set -a; . config/.env; set +a; RAY_AUTH_MODE=token nohup bash -c "date -u +%FT%TZ; .venv/bin/cybergym-eval run --config config/<manifest>.json --address <head private ip>:6381; echo EXIT=\$?; date -u +%FT%TZ" > ~/cybergym-work/<name>-driver.log 2>&1 < /dev/null &)`.
6. **Monitor.** On the head: `python3 tools/qwen_ops/qwen_conc_monitor.py` (per-5-minute table: tasks calling, overhead, live context, long calls). From the Mac: `VM_HOST=<VM_HOST> tools/qwen_ops/conc_watch.sh` stops on a non-200, a stale token, or two buckets of collapse. Task outcomes: the `executions` table in Postgres (stage columns of the `result` field).
7. **To stop tasks on purpose:** `docker stop <agent container>`; containers start in task order, so the start times map them to tasks.

## 8. Pitfalls we hit
- Deployment cannot be cancelled; plan the order of experiments before starting one.
- The AWS resolver on the head returned a stale address after redeploys (section 7, step 3).
- Stopping the token pusher deletes the token file on the head; a restart is needed before the shim can call the endpoint.
- Vertex cuts a request at about 10 minutes; the model can reason silently for that long ([[wiki/syntheses/qwen-two-task-pilot]] section 7.3).
- The login (`gcloud auth application-default login`) expires; you have to repeat it yourself.
- We cannot read the endpoint's logs or metrics (403), so capacity is inferred from timings.
- Killing the Ray driver cancels its queued tasks but leaves failed rows in the database; use a new `work_root` and a new start-time file for the retry.
