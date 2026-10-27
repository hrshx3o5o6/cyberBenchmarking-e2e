---
type: synthesis
created: 2026-10-26
updated: 2026-10-26
sources: ["[[sources/cybergym-e2e]]"]
tags: [ray, two-vm, scheduling, spread, observations, results, kimi-k3, gpt-oss, bedrock, mantle, responses-api, codex, ssh, security-group]
---
# Two-VM Ray cluster: test results and observations

What the two-VM cluster did when we ran batches on it, and everything else we learned on the way (model routes on Bedrock, scheduling behaviour, network access). How the cluster was built is in [[wiki/syntheses/two-vm-ray-cluster-setup]]; the design discussion is in [[wiki/syntheses/ray-ec2-scaling-study]]. All tests: patch-only, the same 12 light tasks (the ones that use only the two shared base images), one VM each at 16 vCPU / 64 GiB, Ray 2.59.0 with token auth, driver on VM1. Hostnames are not shown; "VM1" is the head and the machine the driver runs on, "VM2" the worker.

## 1. Summary
| Test | Strategy | Model | Split VM1 / VM2 | Outcome |
|---|---|---|---|---|
| 1 | Ray default | Kimi K3 | **8 / 4** | 12 of 12 passed (S3 and S4), $5.67 |
| 2 | `SPREAD` | gpt-oss-20b (Mantle) | **6 / 6** | 11 of 12 "no patch" (Codex and gpt-oss incompatibility, section 4); placement valid |
| 3 | `SPREAD` | Kimi K3 | **6 / 6** | 12 of 12 passed, $7.09, both nodes evenly loaded |

**Main findings:** (a) Ray placed tasks across both VMs by itself, with nothing in our code naming a node; (b) the default strategy split 8/4, not evenly, and left VM2 nearly idle while VM1 ran hot; `SPREAD` split 6/6 both times (with gpt-oss and with Kimi K3) and loaded both nodes similarly; (c) of 97 model/endpoint combinations on Bedrock only Kimi K3 and gpt-oss-20b/120b support the Responses API with tool calls, which Codex needs; (d) gpt-oss on Bedrock Mantle fails on Codex's second turn; (e) a single-address SSH rule is fragile when the client's IP rotates; the first VM can act as a jump host.

## 2. Test 1: default scheduling, Kimi K3
12 tasks submitted at once to a cluster of 2 nodes with 32 CPU and 20 `benchmark_slot` (10 per node). Placement (read from the hostname on each result and from the run processes on each machine):

| | VM1 (head) | VM2 (worker) |
|---|---|---|
| Tasks | **8**: c-blosc2 ×2, jsoncpp, lcms ×2, librawspeed ×2, opensc | **4**: fmt, libdwarf, libxml2, openssl |
| Passed | 8 of 8 | 4 of 4 |
| Model calls (sum of per-task requests) | 127 | 96 |
| Spend | $3.22 | $2.46 |
| Wall time per task, mean | 7.1 min | 6.8 min |
| Setup + grading time (wall minus agent), mean | 3.7 min | 3.5 min |

**Machine state at 2.5 minutes** (while the tasks ran):
| | VM1 | VM2 |
|---|---|---|
| Tasks running | 8 | 4 |
| CPU | **100%** | **7%** |
| Load (1/5/15 min) | 21.2 / 7.3 / 2.7 | 4.4 / 2.3 / 1.0 |
| CPU pressure (PSI avg10 / avg60 / avg300) | 55 / 32 / 10 | 0.3 / 1.3 / 0.8 |
| Memory used / free, swap | 7.8 / 53.9 GB, 0 | 2.8 / 59.0 GB, 0 |
| I/O pressure | 3 | 16 |

The whole batch finished in about 11 minutes; total **$5.67** (estimate had been about $6). The imbalance cost nothing visible at this load: setup-and-grading time was about the same on the busy and the idle machine (3.7 vs 3.5 minutes), but these are short, light tasks, so it says little about heavier ones.

**Interpretation (my inference, not confirmed in the docs):** 8 is exactly 50% of VM1's 16 CPUs. The default policy appears to keep placing tasks on the node the driver runs on until about 50% of its CPUs are requested, then spill to the other node. The [scheduling page](https://docs.ray.io/en/latest/ray-core/scheduling/index.html) describes nodes under the 50% threshold as scoring equally and picked at random, which would not give 8/4; either there is an unstated local-node preference or the page is read wrongly. I told the user earlier that the default policy would suit our case; this result says it does not balance load across nodes, and I had described it loosely before reading the page closely ("packs onto busy nodes").

**Per-node state:** VM1's database only saw its own 8 tasks start (the other 4 stayed "pending" there), which confirms that state is node-local and a shared job store is needed for any real scale-out.

## 3. Test 3: `SPREAD`, Kimi K3 (the like-for-like comparison with test 1)
Same 12 tasks, same model, `scheduling_strategy: "SPREAD"`, launched at 09:02:54Z (work folder `smoke3k`).

**Result: 12 of 12 passed (S3 and S4), split 6 / 6.** VM1: c-blosc2 ×2, jsoncpp, lcms ×2, opensc. VM2: fmt, libdwarf, librawspeed ×2, libxml2, openssl. Spend **$7.09** (248 model calls). Results were read from each node's `result.json` files, because the driver's own output file is block-buffered and showed only 7 of 12 while 11 were already finished.

| | VM1 | VM2 |
|---|---|---|
| Tasks / passed | 6 / 6 | 6 / 6 |
| Spend, model calls | $2.29, 95 | $4.80, 153 |
| Wall per task, mean | 5.5 min | 8.5 min (fmt 15.1) |
| Setup + grading (wall minus agent), mean | 2.8 min | 3.8 min |

**Machine load over the whole run** (09:02:54Z to 09:18:51Z, 10 s sampler and 5 s PSI rows):
| | VM1 | VM2 |
|---|---|---|
| CPU, mean / max | 26% / 100% | 35% / 100% |
| Load average, mean / max | 5.6 / 16.8 | 8.6 / 22.3 |
| CPU pressure avg10, mean / max (avg60 max) | 5 / 48 (22) | 10 / 61 (34) |
| Memory used, max; swap | 8.0 GB; 0 | 5.6 GB; 0 |

**Comparison with test 1 (default strategy, same tasks and model):**
| | Default (test 1) | `SPREAD` (test 3) |
|---|---|---|
| Split VM1 / VM2 | 8 / 4 | **6 / 6** |
| Load at 2.5 min | VM1 CPU 100%, load 21, PSI 55/32/10; **VM2 CPU 7%**, load 4.4, PSI about 0 | both nodes busy and similar (peak load 16.8 and 22.3; both hit 100% CPU briefly) |
| Passed | 12 / 12 | 12 / 12 |
| Spend | $5.67 | $7.09 (fmt alone cost $2.85, 72 calls, against $1.35 and 42 calls in test 1; the other 11 tasks cost the same or slightly less) |
| Batch wall time | about 11 min | about 16 min (set by one slow task, fmt, 15.1 min) |

**Reading it:** `SPREAD` did what the default did not: both VMs carried similar load and neither sat idle while the other ran hot. The longer batch time and higher spend come from model variance on one task (fmt), not from the strategy *(inference; one run each, so noisy)*. Each node's own setup-and-grading times were similar, so the spread did not slow any task visibly. The mild remaining asymmetry (VM2 busier) is because it had the long task.


## 4. Test 2: `SPREAD`, gpt-oss-20b on Bedrock Mantle
Run first because it was the cheapest model and the question was where tasks land. Result: **12 results, 6 on each VM**: VM1 got jsoncpp, opensc, c-blosc2 ×2, lcms ×2; VM2 got fmt, librawspeed ×2, libdwarf, openssl, libxml2. Because of the model problem below, 11 of 12 ended with no patch (median task wall 50 s, range 28 to 258 s), and one task passed S3; load and timings from this run say nothing about real work. Placement is valid: Ray decides at submission, and each result carries its hostname.

**What went wrong with gpt-oss-20b under Codex** (details in section 5): Codex's first call succeeded (200 OK, 9,256 input tokens), and the **second call was rejected** by Mantle with `Invalid 'input': value did not match any expected variant`.
- The shim (shapes only, never content) logged the second request's `input` items: three `message` items, one **`reasoning`** item (fields `content`, `encrypted_content`, `summary`, `type`), one `function_call` (`arguments`, `call_id`, `name`, `type`) and one `function_call_output` (`call_id`, `output`, `type`); body about 50 KB.
- Stripping `encrypted_content` from the echoed reasoning item did not fix it (three more rejected second calls). Dropping reasoning items entirely was **not tried**: the user decided to stop experimenting. Cost of these attempts: cents.
- The shim now has an optional `RESPONSES_INPUT_FIX` setting (`strip_encrypted` or `drop_reasoning`) and a shapes-only debug log on 400 responses; neither is needed for Kimi K3.

## 5. Model routes on Bedrock (what works with Codex)
Codex needs the **Responses API**. Reports say it dropped `wire_api = "chat"` support in 2026 (removal version disagrees across sources, *unverified*; the version installed in our containers was not checked). Two OpenAI-compatible endpoints exist for the same key:
- **Runtime endpoint** `bedrock-runtime.us-east-1.amazonaws.com/openai/v1` (used so far).
- **Mantle** `bedrock-mantle.us-east-1.api.aws/v1` (60 models listed; a separate endpoint family).

A sweep of **97 model/endpoint pairs** (43 `us.` inference profiles on the runtime endpoint, 54 text models on Mantle), each with a "reply OK" Responses call and then a tool call:
| Responses API + tool call works | Endpoint |
|---|---|
| `us.moonshotai.kimi-k3` | runtime |
| `openai.gpt-oss-20b` | Mantle |
| `openai.gpt-oss-120b` | Mantle |

Everything else returned 400 or 404 on `/responses`: GPT-5 and GPT-6 entries, Claude, GLM, Grok, Qwen (all five Qwen text models and the Qwen3-Coder variants), DeepSeek, Nemotron, Mistral and Devstral, MiniMax, Gemma, Kimi K2.x, Llama. On the earlier runtime-endpoint test of 14 open-weight models, **all supported `/chat/completions` and 13 handled tool calls there** (Gemma-3-27b did not), so they could run behind a Responses-to-chat bridge, a pinned old Codex, or a harness that speaks chat. The `qwen3.8-27b` model used in earlier OpenRouter batches is **not in the Bedrock catalogue**.

Third-party list prices per million tokens, input / output (unverified; only Gemma's is on AWS's own pricing page): gpt-oss-20b $0.07 / $0.15, gpt-oss-120b $0.15 / $0.60, qwen3-coder-30b-a3b and qwen3-32b $0.15 / $0.62, nemotron-nano-3-30b $0.06 / $0.24, gemma-3-27b $0.23 / $0.38, against Kimi K3 US tier $3.30 / $16.50 ([pricepertoken](https://pricepertoken.com/endpoints/compare/amazon-bedrock-vs-nebius), [LLM Reference](https://www.llmreference.com/provider/aws-bedrock/models), [AWS](https://aws.amazon.com/bedrock/pricing/)). The shim for gpt-oss used the same cache and input price (cache price unknown), a conservative choice.

## 6. Network and access observations
- **The `/32` SSH rule broke repeatedly.** The Mac's public IP (a `104.28.x.x` range, probably a VPN such as Cloudflare WARP, *unverified*) changed between checks: `.225.172`, `.193.172`, `.193.171`. Each change made direct SSH to VM2 time out. The console's "My IP" reads the browser's address, which can differ from the terminal's; the fix that worked was typing the terminal's address (from `checkip.amazonaws.com`) as a custom source.
- **Jump host:** VM1 stays reachable through Amit's open rule and shares a security group with VM2, so `ssh -J <VM1> <VM2-private-IP>` worked throughout. Running jobs are unaffected by an IP change; only our access is.
- **Connection resets and timeouts** appeared a few times (once while VM2 was pulling images; DNS lookups of the EC2 hostname from the Mac failed intermittently; use IP addresses). A monitor that treats an SSH failure as "no output" will report a false "done"; treat it as unknown.
- **Permission checker:** it blocked an assistant-run listener on an unused port (exposes a local service), credential copies and an unreviewed bootstrap earlier; ICMP ping was an accepted equivalent for the network test.

## 7. Mistakes made (so they are not repeated)
- A launch with a mistyped Ray address plus `pkill -f` matching its own command line (kill by PID instead).
- Ray client port 10101 inside the worker port range (Ray's default worker range is 10002 to 19999).
- The first security-group edit changed the SSH row instead of adding a row (caught before saving).
- I reported 112 model calls for VM1 in test 1; the correct sum is 127.
- A foreground `sleep` is rejected here; waits belong inside the remote command, and very long SSH sessions can be closed by the remote side.

## 8. Cost
Test 1: **$5.67**. Tests 2 and the pilot on gpt-oss: cents (not tallied, the shim counter was reset when switching models). Test 3: **$7.09** ($2.29 on VM1, $4.80 on VM2). Running total for the two-VM tests with Kimi K3: $12.76. VM2 runs at about $0.8/hour plus its disk (*unverified*); nothing is running a task now.

## 9. Open items
Decide whether `SPREAD` becomes the default for the cluster (even CPU per VM) or whether the default policy is acceptable once the driver is not also a worker; build the shared job store and S3 results (see [[wiki/syntheses/ray-ec2-scaling-study]]); decide on a cheap-model route (a Responses-to-chat bridge or fixing the gpt-oss reasoning-item rejection); stop or terminate VM2 when not in use.
