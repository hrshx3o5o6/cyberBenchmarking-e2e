---
type: synthesis
created: 2026-10-29
updated: 2026-10-29
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [aws, ec2, ray, autoscaler, iam, instance-profile, ami, ray-up, build-plan, infrastructure, benchmark-evals]
---
# Ray autoscaler on EC2: how it creates instances, what we need, and the build plan

Follows [[wiki/syntheses/ray-ec2-scaling-study]] (design thinking) and [[wiki/syntheses/two-vm-ray-cluster-setup]] (the manual two-VM cluster). Scope decision: **Ray's own autoscaler only**; load-aware scaling (PSI-driven) is deliberately out for now. No account IDs, instance IDs or IPs are recorded here (public remote); the templates and scripts are in `wiki/syntheses/aws-vm-data/autoscaler/`.

## 1. What our AWS access can do (checked 2026-10-29)
- `aws login` (console credentials) works from the Mac, but its session **expires within hours**; fine for a manual `ray up`, not for an unattended head.
- Dry-runs **allowed**: `RunInstances` (with a `project=benchmark-ray` tag spec), `CreateImage`, `Start/Stop/TerminateInstances`. The permissions are **not tag-scoped**: they apply to every instance in the account, including the owner's.
- **Denied:** IAM role listing (so no role creation) and `servicequotas:GetServiceQuota` (the vCPU quota is unknown).
- The primary VM and the second VM have **no instance profile** (verified from the VM's metadata service: 404 on `iam/info`, and `IamInstanceProfile: null` from the API). `iam:PassRole` cannot be tested until a profile exists.
- Both VMs: one subnet in one zone, IMDSv2 required with hop limit 2, root volume 512 GiB gp3 (3000 IOPS, 125 MiB/s); the "496 GB" in older pages is the usable size from `df`.

## 2. How Ray's AWS node provider creates instances (read from the Ray 2.59.0 source)
| Question | Answer |
|---|---|
| Mechanism | `ec2.create_instances(**node_config)` through boto3: the YAML's `node_config` passed almost as-is, plus `MinCount`/`MaxCount` and merged tag specs. **No launch template.** |
| Subnet | `SubnetIds` is a Ray key: it picks one `SubnetId` per attempt and rotates on failure. |
| Tags it adds | Cluster name, node kind, user node type, launch-config hash. It finds "its" instances by these tags. |
| Scale-down | `cache_stopped_nodes` defaults to **true**: on-demand nodes are **stopped**, spot nodes **terminated**. Scale-up reuses a stopped node whose cluster, kind, launch-config and node-type tags match (so changing the node config orphans old stopped nodes). |
| Security group (if unnamed) | Looks for `ray-autoscaler-<cluster_name>`, **creates it** if missing: all traffic within the group plus **SSH open to 0.0.0.0/0**. |
| Key pair (if unnamed) | Creates `ray-autoscaler_<region>` and writes the private key under `~/.ssh`. |
| IAM (if no head profile) | Creates a role with **AmazonEC2FullAccess and AmazonS3FullAccess**. Needs IAM write access we do not have, and is far too broad anyway. |
| AMI (if unnamed) | An old Deep Learning AMI (Ubuntu 18.04). |

Consequence: the YAML names every resource (AMI, subnet, `ray-cluster-sg`, key pair, instance profile, disk, tags). The same security group on every node keeps the self-referencing rule that lets nodes reach each other. I did **not** read the autoscaler's scaling decisions (`resource_demand_scheduler`, idle handling); those are from the docs.

## 3. What the autoscaler reacts to (scope: no load awareness)
Queued demand only. Our driver submits every task; tasks that find no free `benchmark_slot` are the demand that triggers a new worker, up to `max_workers`. Idle nodes are stopped after `idle_timeout_minutes`. Because `task_cpus` is 1, the **slot count binds before CPUs** (10 slots on 16 vCPUs), so the calibrated slot number (8 to 10 per node from the single-VM study) is the capacity dial.

## 4. The head's instance profile
The autoscaler runs on the head and calls EC2 from there, so the head needs its own credentials: an IAM role wrapped as an instance profile, attached at launch; the instance gets rotating credentials from its metadata service and nothing is stored. Our user cannot create it, so the account owner must: EC2 describe, `RunInstances`, `Start/Stop/TerminateInstances`, `CreateTags`, limited to the project tag and us-east-1, plus `iam:PassRole` on itself. Also requested: the vCPU quota and an instance cap or budget alert. Open choice (undecided): attach it to the existing primary VM (then everything there inherits it) or to a **new small head instance** (my preference).

## 5. Artifacts written so far (all untested against AWS unless stated)
| File | Purpose | State |
|---|---|---|
| `cluster.template.yaml` | Ray cluster config with `{{placeholders}}` | **Validated offline** with Ray 2.59.0's `prepare_config` + `validate_config`; a negative test (bad type) is rejected |
| `render_cluster.py` | Fills the template from an untracked `autoscaler.local.env`; refuses unfilled or placeholder values | Run with fake values; rejects the example file |
| `dummy_demand.py` | Stage-3 job: sleeping tasks asking for `benchmark_slot:1`, prints nodes, slots and placement | Compiles; never run |
| `ami_recipe.sh`, `ami_scrub.sh`, `ami_verify.sh` | Clean build of the worker/head image, pre-image scrub (no secrets or state), post-boot checks | Syntax-checked only |
| `tagged_instances.sh` | Lists `project=benchmark-ray` instances with uptime; optional stop-if-older-than | Ran read-only: "no tagged instances" |

One real bug found by the validator: `--resources='{"benchmark_slot": 10}'` inside a plain YAML list item is parsed as a mapping because of the `": "`; the template uses no space after the colon.

## 4b. AMI design decisions
- Base: the stock Canonical Ubuntu 26.04 image (8 GB root). Build on a ~60 GB root; the image snapshot is that size, and workers/head enlarge the volume at launch through `BlockDeviceMappings` (an AMI's volume can grow, not shrink).
- Baked in: user `harshav`, Docker, `vm.mmap_rnd_bits=28`, the runner source with `tools/`, the upstream checkout pinned at `d0ae0f0` with our patches, two Python 3.12 environments (Ray 2.59.0, boto3 and `ray[default]` already pulled in by the runner's dependencies), the two shared `oss-fuzz-base` base images (by digest), and the squid proxy with `restart: unless-stopped` and the `cybergym-internal` network (gateway 172.18.0.1).
- **Kept out of the image:** `.env`, the Bedrock key, the HF token, the Ray auth token, run state. They are delivered by the YAML's `file_mounts` at launch (synced to the head, and from the head to workers).
- SSH: the key pair only injects into `ubuntu`, so the recipe puts the pair's public key in `harshav`'s `authorized_keys`.
- Task images (3 to 50 GB each) are not baked: pulled on first use or from a registry later.

## 6. Stages
| # | Stage | Cost | State |
|---|---|---|---|
| 0 | Permission and quota dry-runs | $0 | **done** (quota unreadable) |
| 1 | Build the AMI | a few dollars at most (an `m7i.xlarge` for about 1.5 h, a short test instance, snapshot storage) | **done 2026-10-29**, see section 8 |
| 2 | Head only (`max_workers 0`) | small instance | needs the instance profile |
| 3 | Dummy-demand scale-up and scale-down | $1 to $2 | job drafted |
| 4 | 12 light tasks, `max_workers 2`, node-local state | $6 to $8 | |
| 5 | Shared state: Postgres on the head, artifacts in S3, one cluster-wide budget | dev time | |
| 6 | 50 tasks, then a full pass | model spend | |

## 7. Open questions
- Head on the existing VM or a new instance; who creates the profile and with what cap.
- Whether the autoscaler's monitor and `ray status` work under token auth (to test at stage 2).
- Whether node-type `resources` reach the raylet automatically (the worker start line repeats them explicitly as a precaution).
- The vCPU quota.

## 8. Stage 1 result: the AMI was built and verified (2026-10-29)
Built from a clean stock Ubuntu 26.04 `m7i.xlarge` (60 GiB root) through the jump host, using the recipe in `aws-vm-data/autoscaler/`. Final image: 60 GiB, snapshot of used blocks, tagged `project=benchmark-ray`. A test instance launched from it with a **100 GiB** volume grew its filesystem to 96 GB on its own (cloud-init), so the "image small, enlarge at launch" plan works.

What the verify script checked on a cold boot of the final image (all 12 passed): user `harshav`, docker without sudo, `vm.mmap_rnd_bits=28`, proxy running with `restart=always`, bridge gateway 172.18.0.1, Ray 2.59.0, base image present, `cybergym-eval` CLI, no `.env` / Bedrock key / Ray token present, IMDSv2 reachable. The per-instance host key and `machine-id` differed from the build instance's.

**Problems found and fixed (the recipe was untested):**
| Problem | Cause | Fix |
|---|---|---|
| Recipe died at the base-image step with `invalid reference format` | the two `sha256:` values copied from the first VM's `docker images --digests` were local image IDs, not pullable repo digests; the `-c "..."` quoting was also fragile | pull `gcr.io/oss-fuzz-base/base-builder:latest` in a plain `for` loop. Other base variants are pulled on first use. |
| **Proxy not running after the first image booted** (caught by the test instance) | the scrub step ran `docker stop`; a container stopped by hand stays stopped after a reboot under `unless-stopped` | restart policy `always`; the scrub no longer stops containers (shutdown does it cleanly) |
| My `pgrep -f` check showed "RUNNING" after the recipe had died | `pgrep -f` matched its own SSH command line (same trap as before) | `ps -eo pid,cmd \| grep "[a]mi_recipe"` |
| The scrub's "leftover secret-looking files" list is noisy | it matches library files (`cacert.pem`, package folders named `credentials`) | expected; the real secret check is in `ami_verify.sh` |

The first (faulty) image and its snapshot were deleted; the build and test instances were terminated. Left in the account: the final image and its snapshot (private to the account). The scripts in the vault are the corrected versions.

**Not in the image:** secrets (delivered by `file_mounts` at launch), task images beyond the base-builder ones, task data, manifests, and the per-node metering shim and monitors (stage 4: start them from `worker_start_ray_commands` or as services).
