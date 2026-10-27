---
type: synthesis
created: 2026-10-26
updated: 2026-10-26
sources: ["[[sources/cybergym-e2e]]"]
tags: [aws, ec2, ray, two-vm, cluster, setup, runbook, security-group, ssh, shim, token-auth, infrastructure, benchmark-evals]
---
# Two-VM Ray cluster on EC2: what we set up, step by step

This is the record of **what was actually done** to turn the single AWS VM into a two-node Ray cluster, in the order we did it, with the commands, the mistakes and the fixes. Results and findings are in [[wiki/syntheses/two-vm-ray-test-observations]]; the design thinking (why Ray, storage, what must change for a real scale-out) is in [[wiki/syntheses/ray-ec2-scaling-study]]; the single-VM runner is described in [[wiki/syntheses/aws-vm-concurrent-setup-reference]]. IP addresses, instance and security-group IDs and the AWS account ID are deliberately left out (the vault's remote is public): "VM1" is the original instance, "VM2" the new one, `<VM1-private-IP>` and `<VM2-private-IP>` their addresses inside the VPC.

## 0. Starting point
| | VM1 (existing) | VM2 (new) |
|---|---|---|
| Type | `m7i.4xlarge` (16 vCPU, 64 GiB), on-demand | same, launched with "Launch more like this" |
| Where | us-east-1c, default VPC | same zone, VPC and subnet |
| OS | Ubuntu 26.04 LTS, kernel 7.0.0-1006-aws | same image |
| Disk | 496 GB gp3 root | 496 GB gp3 root (copied from VM1; I had suggested 300 GB) |
| IAM role | none attached | none |
| Security group | `launch-wizard-4` (Amit's; has an open rule I did not change) + `ray-cluster-sg` | `ray-cluster-sg` |
| Ray | Amit's own head (GCS 6379) under another user; ours is separate | none until we start the worker |

## 1. AWS console steps (done by the user)
1. **Key pair:** created an ED25519 key pair (`.pem` format) in the EC2 console, saved to `~/.ssh/` and `chmod 400`. (The alternative is to import an existing public key; the pair is attached only to the default `ubuntu` user at launch.) A new pair does not replace existing ones.
2. **Launch VM2:** EC2, existing instance, *Actions, Images and templates, Launch more like this*: same AMI, type, VPC and subnet; auto-assign public IP on; key pair chosen from the dropdown.
3. **Security group:** *Create security group* `ray-cluster-sg` in the launch form. The default SSH rule was **Anywhere (0.0.0.0/0)**; changed it to **My IP** before launching.
4. **After launch, add the self-referencing rule:** Security Groups, `ray-cluster-sg`, Edit inbound rules, **Add rule**: All traffic, Source = `ray-cluster-sg` itself (it cannot be added in the launch form because the group does not exist yet). Mistake caught from a screenshot: the first attempt edited the *existing SSH row* to "All traffic", which would have deleted the SSH rule and locked us out; cancelled and added a second row instead.
5. **Attach the group to VM1 as well** (Actions, Security, Change security groups, add `ray-cluster-sg`, keep `launch-wizard-4`), so VM1 accepts traffic from VM2. It is Amit's instance; it was done by the user with his OK. Nothing was removed from his group.
6. **Verification without opening any port:** `ping` in both directions, 3 of 3, 0% loss, 0.4 to 1 ms. A first test with a temporary listener on an unused port was blocked by the permission checker (it exposes a local service); ICMP is allowed only by the self-referencing rule, so it proves the same thing.

## 2. Base setup on VM2 (over SSH as `ubuntu`)
- Created user **`harshav`** (same name and home path as VM1: the jobs carry absolute paths such as `/home/harshav/cybergym-e2e`, so the second machine must have identical ones), with our usual public key in `authorized_keys` and passwordless sudo.
- `apt` installed `docker.io git curl rsync`; Docker enabled; `harshav` added to the `docker` group (login as `harshav` then runs `docker ps` without sudo).
- `vm.mmap_rnd_bits=28` set and persisted in `/etc/sysctl.d/99-cybergym.conf` (the benchmark requires it; a normal user cannot read it back, root confirms it).

## 3. Code and environments
- **Copy via the Mac** (VM1 to Mac to VM2, because VM2 has no key for VM1): `rsync` of `benchmark-evals` (276 KB) excluding `.venv`, `__pycache__`, `*.egg-info`, `config/.env`, `config/.bedrock_key` and `.git`; and of `cybergym-e2e` (29 MB) excluding `.venv` and `data/`, *keeping* `.git` so it stays at commit `d0ae0f0` with our patches applied. A check confirmed 0 secret files in the relay directory.
- Ran **`scripts/bootstrap_ec2.sh`** on VM2 as `harshav` (installs `uv`, finds the upstream repo present, applies the idempotent patches, creates the two Python 3.12 environments, installs the `cybergym-eval` CLI). It finished with exit 0.
- **Versions must match across nodes**: checked on both machines, Ray 2.59.0, Python 3.12.15, Docker SDK 7.2.0, `uv` 0.13.x. They matched without pinning.

## 4. Network isolation and the model-call proxy on VM2
- Pulled `ubuntu/squid` and ran `python -m firewall start --which run --domain bedrock-runtime.us-east-1.amazonaws.com` from `cybergym-e2e/scripts`: created the internal Docker network `cybergym-internal` and the `cybergym-proxy` container, with the Bedrock host on the allowlist. Its Docker gateway came out as **`172.18.0.1`, the same as on VM1**, so the same `shim_url` works on both nodes without per-node manifests.
- **Secrets** (`config/.env` and `config/.bedrock_key`) were streamed from VM1 to VM2 through the Mac with `umask 077` and verified by size and checksum only (never printed); the user ran that command because the permission checker blocks an assistant-run credential copy.
- **A metering shim on each node** (`tools/llm_shim_new.py`, the key-preloading version), bound only to that node's Docker gateway, per-key cap $10, total cap $12 per node for the tests. The shim must be restarted when the target model changes; a restart wipes its in-memory keys and counters, so only restart when no run is active (the start script refuses otherwise).
- **Monitors per node:** `psilog.py` (5 s), `sampler.py` (10 s) and `watchdog.py` (stops our run if free memory stays under 6 GB or swap passes 2 GB).

## 5. Task data and images on VM2
- Test tasks were chosen to use only the **two shared `oss-fuzz-base` base images**, so VM2's pull stayed small (3.0 and 3.1 GB, versus 3 to 10 GB per task image otherwise), and the quickest of them (patch-only 4 to 14 minutes in earlier runs).
- Because Ray can place any task on any node, **every node needs the images and data for every task in the batch**. `cybergym-eval prepare --config config/smoke2.json --skip-firewall` on VM2 pulled the images and downloaded the 12 tasks' data from the gated Hugging Face dataset (token in `.env`). `preflight` on VM2: 31 of 31 checks passed. VM2's disk afterwards: 9.4 GB used.

## 6. Ray: token auth, head, worker
- **Token authentication** (Ray 2.59 enables it by default; see the [token auth docs](https://docs.ray.io/en/latest/ray-security/token-auth.html)): the token file `~/.ray/auth_token` on VM1 was reused, copied to VM2 (mode 600, directory 700, equal checksums), and `RAY_AUTH_MODE=token` was set on every `ray start`, `ray status` and driver command.
- **Environment:** worker processes inherit the raylet's environment, not the driver's, so only `SHIM_MASTER_KEY` was exported into each `ray start` (not the whole `.env`).
- **Head on VM1**, on its own ports so it cannot collide with Amit's head (6379, `/tmp/ray`, client 10001):
  `ray start --head --node-ip-address=<VM1-private-IP> --port=6380 --ray-client-server-port=9990 --num-cpus=16 --resources='{"benchmark_slot": 10}' --include-dashboard=false --temp-dir=/tmp/ray-1002c`.
  **Mistake:** the first try used client port 10101, which lies inside Ray's default worker port range (10002 to 19999) and Ray refused ("port used by other components"). The worker I started right after hung waiting for a head that did not exist; cleaning up meant killing the stuck `ray start` process by PID (`ray stop` did not stop it). Fixed with 9990.
- **Worker on VM2:** `ray start --address=<VM1-private-IP>:6380 --node-ip-address=<VM2-private-IP> --num-cpus=16 --resources='{"benchmark_slot": 10}' --temp-dir=/tmp/ray-1001c`.
- **Check:** `ray status --address=<VM1-private-IP>:6380` showed **2 active nodes, 32 CPU, 20 `benchmark_slot`**, no pending nodes or failures. The slot count (10 per node) is only an admission cap; the 12-task test never fills it.

## 7. Running a batch on the cluster
- The runner already supports a real cluster through `--address`. The driver runs **on VM1** and is started detached:
  `RAY_AUTH_MODE=token nohup setsid .venv/bin/cybergym-eval run --config config/<manifest>.json --address <VM1-private-IP>:6380`.
- Manifest for the first test (`smoke2.json`): 12 light patch-only tasks, `gate_enabled false`, `start_stagger_seconds 10` (the stagger is a file lock per node, so each node staggers its own starts), per-task cap $10, Kimi K3.
- **Added for the second test:** an optional `scheduling_strategy` key (empty = Ray's default; `"SPREAD"` = even distribution), implemented as `_task_options()` in `cli.py` and a default in `config.py`, applied on the driver only.
- **Mistakes to avoid:** (1) a launch with a mistyped address (`<VM2 IP>:0`) plus a `pkill -f` that matched its own SSH command; the stray driver had to be killed by PID, with `kill -9`. (2) A foreground `sleep` is blocked in this environment; wait inside the remote command instead. (3) Counting "agents running" with `grep` needs the `[r]un_agent` bracket trick or it counts itself.
- **State is per node.** Each node keeps its own SQLite file and `artifacts/`. VM1's database only sees VM1's tasks start (the rest stay "pending" there); the driver still prints every result, with the **hostname** of the machine that ran it, and that is how placement is read.

## 8. Network and SSH gotchas we hit
- **The "My IP" SSH rule broke every time the Mac's public IP changed.** The Mac's exit address was in a `104.28.x.x` range (a Cloudflare range; likely a VPN such as WARP, *unverified*) and rotated between `.225.172`, `.193.172` and `.193.171` within minutes. The console's "My IP" reads the *browser's* address, which may differ from the terminal's; the reliable fix was to type the terminal's address as a custom source (`curl https://checkip.amazonaws.com` shows it) and even then it can rotate again.
- **Reliable access:** VM1's SSH stays reachable through Amit's open rule, and VM1 and VM2 are in the same security group, so **VM2 is reachable through VM1 as a jump host**: `ssh -J harshav@<VM1-public-IP> harshav@<VM2-private-IP>` (add `-o StrictHostKeyChecking=accept-new` the first time, because the private address is a new name for a known host). Nothing running on the VMs is affected by an IP change; only our access is.
- **VM2's public IP changes on every stop and start** (auto-assigned addresses are released); the private IP is kept.

## 9. Stopping and cleaning up
- `ray stop` on each node (on VM1 it only affects processes of our own user; Amit's head runs under another user and was verified up afterwards), then stop the shims and monitors.
- **Pause VM2:** console, *Instance state, Stop instance* (not Terminate): compute billing stops (about $0.8/hour, *unverified*), the 496 GB disk keeps billing (about $1.30/day at $0.08/GB-month, *unverified*), and everything on it survives. After a start: new public IP, restart the squid container (`docker start cybergym-proxy`, it has no restart policy), the shim, the monitors and `ray start --address=...` (the token persists). Hibernate was not enabled at launch.
- **Delete VM2:** *Terminate*; with *Delete on termination* the disk goes with it.

## 10. Files created or changed
On VM1 and VM2 (`~/benchmark-evals`): `config/smoke2.json`, `smoke3.json`, `smoke3k.json` (manifests), `tools/llm_shim_new.py` (key-preloading shim, with a debug option and the `RESPONSES_INPUT_FIX` switch added during the gpt-oss experiments, see the observations page), `tools/psilog.py`, `tools/sampler.py`, `tools/watchdog.py`, `tools/controller.py`. On VM1 only: `src/cybergym_eval/cli.py` (`_task_options`) and `config.py` (`scheduling_strategy`). Nothing in Amit's folders was touched.
