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
| `cluster.template.yaml` | Ray cluster config with `{{placeholders}}`; **rewritten 2026-10-29 for a head on the existing VM** (section 11) | **Validated offline** with Ray 2.59.0's `prepare_config` + `validate_config`; a negative test (bad type) is rejected |
| `render_cluster.py` | Fills the template from an untracked `autoscaler.local.env`; refuses unfilled or placeholder values | Run with fake values; rejects the example file |
| `dummy_demand.py` | Stage-3 job: sleeping tasks asking for `benchmark_slot:1`, prints nodes, slots and placement | Compiles; never run |
| `ami_recipe.sh`, `ami_scrub.sh`, `ami_verify.sh` | Clean build of the worker/head image, pre-image scrub (no secrets or state), post-boot checks | Syntax-checked only |
| `tagged_instances.sh` | Lists `project=benchmark-ray` instances with uptime; optional stop-if-older-than | Ran read-only: "no tagged instances" |
| `prepare_cluster.py` | Applies Ray's `prepare_config` to the rendered YAML so a hand-started head's monitor has its defaults (section 14) | Ran on the head; worked |
| `stop_workers.sh` | Worker-only teardown (replacement for `ray down`); see section 12 | Tested against a stub `aws` and against real AWS (nothing matches); never run on live workers |

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
| Recipe died at the base-image step with `invalid reference format` | the loop's quoting (`-c "..."` with an expanded array). **Correction:** an earlier version of this page blamed unpullable digests; that was wrong: `prepare.py` itself pulls `base-builder@sha256:8eda74a1…` by digest, and with Docker's containerd image store the image ID equals the manifest digest | plain `for` loop. The recipe now pulls both digests; AMI v2 was built from the earlier version (base-builder:latest, and the build instance also held two untagged base-builder images of 3.02 and 3.13 GB). Whether v2 holds exactly the `8eda74a1…` digest is **not yet confirmed**: check with `docker image inspect` on the first instance launched from it |
| **Proxy not running after the first image booted** (caught by the test instance) | the scrub step ran `docker stop`; a container stopped by hand stays stopped after a reboot under `unless-stopped` | restart policy `always`; the scrub no longer stops containers (shutdown does it cleanly) |
| My `pgrep -f` check showed "RUNNING" after the recipe had died | `pgrep -f` matched its own SSH command line (same trap as before) | `ps -eo pid,cmd \| grep "[a]mi_recipe"` |
| The scrub's "leftover secret-looking files" list is noisy | it matches library files (`cacert.pem`, package folders named `credentials`) | expected; the real secret check is in `ami_verify.sh` |

The first (faulty) image and its snapshot were deleted; the build and test instances were terminated. Left in the account: the final image and its snapshot (private to the account). The scripts in the vault are the corrected versions.

**Not in the image:** secrets (delivered by `file_mounts` at launch), task images beyond the base-builder ones, task data, manifests, and the per-node metering shim and monitors (stage 4: start them from `worker_start_ray_commands` or as services).

## 9. How a run will work once everything is built (sketch, nothing here has been run)
`ray up` only brings the cluster up; it does not run the benchmark and does not distribute images or data.

| Step | Command / actor | What happens |
|---|---|---|
| 1 | `render_cluster.py` | Fills the YAML template from the untracked local env file (AMI, subnet, security group, head profile ARN, secret file paths). |
| 2 | `ray up cluster.yaml`, from the laptop while `aws login` is valid | Launches the **head** from the AMI, syncs the secrets (`file_mounts`), starts Ray with the autoscaler on. |
| 3 | copy the manifest to the head, then `ray exec ... "cybergym-eval run --config ... --address auto"` (detached) | The **driver** submits one task per (task, mode). Its stdout is block-buffered, so read results from the driver log or SQLite. |
| 4 | autoscaler (automatic) | Tasks that find no free `benchmark_slot` are pending demand; it launches workers from the AMI up to `max_workers`; each runs `ray start --address=<head>` and joins. |
| 5 | Ray (automatic) | Places tasks; a node takes up to the slot count (10) at a time, with the per-node launch stagger. |
| 6 | autoscaler (automatic) | A worker idle for `idle_timeout_minutes` is stopped (`cache_stopped_nodes`: stop, not terminate). |
| 7 | `ray down cluster.yaml`, then `tagged_instances.sh` | Stops everything; confirm nothing tagged is left running. |

Concurrency = slots per node (calibrated from the single-VM study) times the number of nodes the autoscaler adds. Ray does not throttle on CPU load (load awareness is out of scope for now).

### What is NOT automatic yet (open items)
1. **Task images and data on every node.** `cybergym-eval prepare` is run by hand per machine today (build images from the registry, task data from the gated Hugging Face dataset). The AMI holds only the base images. A fresh worker given a task whose data or image it lacks will fail or stall; `preflight` runs only on the driver, so workers do not catch it early. Options: run `prepare` for the manifest on each worker at boot (slow), a shared copy of the data (S3 or registry), or bake the common items into the AMI. What `run_agent.py` pulls on demand has not been checked.
2. **Results and state.** Per-node SQLite and artifacts; stopped workers keep their disks but cannot be read while stopped. Shared state (Postgres on the head, artifacts in S3) is stage 5. First tests read results from the driver output.
3. **Model shim and budget.** The AMI has the proxy but does not start the metering shim; caps are per node, so there is no cluster-wide limit yet. Stage 4 needs the shim started per node at boot with small caps.
4. **Secrets** arrive by `file_mounts` from the machine running `ray up`; workers receive them from the head. Not in the image.

Practical reading: the first runs (dummy tasks, then 12 light tasks) work with these gaps handled by hand; a real batch needs items 1 to 3 solved first.

## 10. The instance role arrived (2026-10-29 check)
The owner created an EC2 role and instance profile named `RayHeadRole` and **attached it to the existing primary VM**, not to a new head. So the head decision is made by him: **the head runs on the existing VM**. Our user also gained some IAM read access (`ListInstanceProfiles` and `GetInstanceProfile` work; `ListRolePolicies` and `ListAttachedRolePolicies` are still denied, so the policy text is unreadable to us).

What was verified from the VM itself (boto3 with the role's credentials, `iam-role` credential source; dry-runs only, nothing changed):
| Probe | Result |
|---|---|
| `describe_instances` | works |
| `RunInstances` dry-run, untagged and tagged `project=benchmark-ray` | allowed |
| `StopInstances` dry-run on the primary VM, the second VM and an unrelated stopped VM | allowed |
| `TerminateInstances` dry-run on the unrelated VM | allowed |
| `RunInstances` dry-run with `RayHeadRole` attached (needs `iam:PassRole`) | **UnauthorizedOperation** |
| Region scoping | inconclusive (the AMI does not exist in the other region) |

**Consequences**
1. The role is **not tag-scoped**: it can stop and terminate any instance in the account, including the VM it is attached to and instances that are not ours. Ray's autoscaler only touches nodes carrying its own cluster tag (read from the 2.59.0 source), so normal operation should be safe, but a bug or a stray command on that VM could stop or terminate the wrong machine. Worth asking the owner to add a tag condition on stop and terminate.
2. `PassRole` is denied, so the role cannot launch instances **with** a profile. Our workers need none (the YAML gives them no profile), so this does not block the plan.
3. The head is an existing machine, so `ray up` is not the way to start it. Instead start the head by hand with the autoscaler config (`ray start --head --autoscaling-config=<yaml>` on its own port, as we already run one on 6380). That path is **untested**.
4. Because the autoscaler runs on the head and SSHes into workers, the **worker key pair's private key must be present on the head** (with `ray up` it would be copied automatically). It is a secret that has to be placed there by the user, mode 600. The `.env`, Bedrock key and Ray token are already on that VM.
5. The head VM can itself run tasks (16 vCPUs); the YAML's head node type (`CPU 0`) is for a separate head and needs adjusting for this layout.
6. **Finding from the 2.59.0 source (`autoscaler.py`): the autoscaler locates the head through EC2 tags.** `NonTerminatedNodes` lists instances carrying the cluster-name tag and reads each one's node-kind tag; `head_id` is the one tagged `head`; every worker start then calls `provider.internal_ip(head_id)` to fill `RAY_HEAD_IP`. A head that `ray up` did not create has no such tags, so `head_id` would be `None` and starting workers would fail. For a head on the existing VM that VM needs **four** Ray tags, i.e. a **change to the owner's instance tags** that needs his OK: `ray-cluster-name=benchmark-ray`, `ray-node-type=head`, `ray-user-node-type=head` and `ray-node-status=up-to-date`. (Corrected 2026-10-29: this page first said three. The node-type mapping loop in `autoscaler.py` skips any node that lacks all of kind, user node type and status; the exact names are the constants in `ray/autoscaler/tags.py`.) The launch-config tag (`ray-launch-config`) is only read for nodes the autoscaler may replace; whether the head needs it is untested. Side effect to plan for: never run `ray down` for this cluster, because it would stop the tagged head too; teardown must stop workers only (our own script). Alternatively a separate head created by `ray up` is tagged automatically and avoids touching his VM. Not yet tested.

## 11. Step 1 done: the cluster YAML adjusted for a head on the existing VM (2026-10-29)
`cluster.template.yaml`, `autoscaler.local.env.example` and the render script were changed for the layout the owner chose (head on the existing VM, started by hand). Validated offline with Ray 2.59.0 (`prepare_config` + `validate_config`, fake values, a bad value is rejected); not used against AWS yet.
| Change | Why |
|---|---|
| Head node type now describes the existing VM: `CPU` and `benchmark_slot` are placeholders (`HEAD_CPUS`, `HEAD_SLOTS`), so it also runs tasks; no head profile, disk or tags in its `node_config` | the head is not created by Ray, and `node_config` is only required by the schema |
| `head_start_ray_commands: []`, with the manual start command shown as a comment | those commands only run under `ray up`; the head is started by hand with `--autoscaling-config` |
| Removed the jump-host proxy command and its variables | the head is inside the VPC and reaches workers by private IP |
| `{{HEAD_PORT}}` (default 6380) in the worker start line instead of a hard-coded 6379 | the owner's own head uses 6379; ours must use another port |
| `file_mounts` sources and `ssh_private_key` are paths **on the head** | the autoscaler runs on the head, and syncs files from the head to each worker |
| `worker_setup_commands: []` with a comment: real batches add `cybergym-eval prepare --config <manifest> --skip-firewall` | task data and images per node (gap 1 in section 9) |
| Header warns: never `ray up` / `ray down` with this file | `ray down` would also stop the tagged head VM |
| Env example defaults: `MAX_WORKERS=1`, `HEAD_TYPE=m7i.4xlarge`, `HEAD_CPUS=16`, `HEAD_SLOTS=10`, `HEAD_PORT=6380` | first test is one worker |
Still untested: the manual-head route, whether node-type `resources` reach the raylet, and whether the autoscaler's monitor works under token auth.

## 12. Worker-only teardown script (2026-10-29)
`aws-vm-data/autoscaler/stop_workers.sh` replaces `ray down`, which would also stop the tagged head VM.
- **Selection:** an instance is acted on only if all three tags match (EC2 filters are ANDed): `ray-cluster-name=<cluster>`, `ray-node-type=worker`, `project=benchmark-ray`. The head (`ray-node-type=head`), untagged instances and other VMs cannot match.
- **Safe by default:** it lists the matches and asks EC2 for a `--dry-run` of the stop or terminate; real calls need `--yes`. `--terminate` instead of stop; `--max N` (default 10) refuses if more nodes match.
- **State handling:** stop mode acts on `running` nodes only (a `pending` instance cannot be stopped yet, so it is reported, not included; this was a bug in the first draft, found by testing); terminate mode acts on running and stopped nodes.
- **Order matters:** stop the driver and the head's autoscaler first (or set `max_workers` to 0), or the autoscaler starts workers again.
- **Tested:** a stub `aws` verified the dry run, the `--yes` path, the `--terminate` path, the `--max` refusal and the pending handling; real AWS returned "no worker nodes" with all three filters matching zero instances today. The real stop path has not run on live workers, and the tag names (`ray-cluster-name`, `ray-node-type`) are from the 2.59.0 source and still to be confirmed on a launched worker.

## 13. The four head tags were added to the existing VM (2026-10-29)
After the owner's conditional OK ("fine as long as it does not disturb anything"), `create-tags` added `ray-cluster-name=benchmark-ray`, `ray-node-type=head`, `ray-user-node-type=head` and `ray-node-status=up-to-date` to the primary VM (it had only `Name`). Checked after: the VM is still running with the same type, profile and security groups; both worker-only scripts still ignore it (`stop_workers.sh`: no workers; `tagged_instances.sh`: no tagged instances); the owner's Ray raylet (running about 8 days) and our own old one are untouched. **Undo:** `aws ec2 delete-tags --resources <the VM> --tags Key=ray-cluster-name Key=ray-node-type Key=ray-user-node-type Key=ray-node-status`. Not yet confirmed: whether the autoscaler also wants `ray-launch-config` on the head (test when the head starts).

## 14. Step 2 done: the autoscaling head is running on the existing VM (2026-10-29)
Started a third Ray head on the primary VM next to the owner's head (6379, user `ubuntu`) and our old head (6380): ours on **6381**, client port 9991, its own short temp dir, `RAY_AUTH_MODE=token`, `--autoscaling-config` pointing at the prepared config. No workers were launched and nothing was spent. The owner's head and our old head were never touched (same uptimes and ports throughout).

**Result:** `ray status` shows `Active: 1 head`, no pending nodes, no failures, the VM's 16 CPUs and 10 `benchmark_slot`, and an empty error log. That proves, for the autoscaler as it runs here: the four tags let it find the head, the instance role gives it working EC2 access (it lists instances every iteration), and token auth works with the monitor. Not yet proven: launching a worker, the worker joining, the slot resources reaching a worker, scale-down, and the head's missing `ray-launch-config` tag only matters if a head replacement is ever considered (source: termination logic iterates worker nodes only, so the head can never be scheduled for termination).

**Problems hit and fixes**
| Problem | Cause | Fix |
|---|---|---|
| Monitor died at start: `KeyError: 'cluster_synced_files'` | A head started by hand gets the raw rendered YAML; `ray up` normally applies Ray's defaults before shipping it | `prepare_cluster.py` runs `prepare_config` (offline) and the head uses the prepared file |
| `Address already in use` while starting the metrics server | the other heads already use the monitor's default metrics port 44217 | `AUTOSCALER_METRIC_PORT=44218` |
| First kill attempt killed my own SSH session | the process filter matched my own shell's command line (it contained the temp-dir text), the same self-match trap as the earlier `pgrep -f` | kill by exact PIDs after checking each in `/proc`; never use a pattern that appears in the command itself |
| `ray stop` would stop all of the user's Ray processes | it has no per-session option, so it would also stop the old head on 6380 | stop our new head by PID only |
| Raylet and GCS ignored SIGTERM for 20 s | graceful shutdown was slow or stuck | exact-PID `kill -9` after a wait |

**How to start the head (on the VM):** (1) `render_cluster.py` with the local env file, (2) `prepare_cluster.py`, (3) `ray start --head ...` as in the template's comment. The rendered files, the local env file and the log live in `~/autoscaler/` on the VM (mode 600), not in the vault. The head runs as a plain process, so **it will not survive a VM reboot**: a systemd service is still to do.

**Next:** the dummy scale-up test (`dummy_demand.py`, `max_workers 1`): launches one billed `m7i.4xlarge` worker (about $0.8/hour, so about $1 to $2 for the test); needs the user's OK first.

## 15. Stage 3 result: dummy scale-up test, first run (2026-10-30)
Ran `dummy_demand.py` on the head (explicit `--address`; 20 tasks of 300 s, 1 CPU and 1 slot each, `max_workers 1`). **The autoscaler launched a worker, but it could not join the cluster**, so the test failed on a real finding. About 12 minutes of one `m7i.4xlarge` was billed (roughly $0.2, estimate); no model spend; the worker was stopped by `stop_workers.sh` and left in the `stopped` state.

**Timeline (from the autoscaler's `monitor.log` and `monitor.out`)**
| Step | What happened |
|---|---|
| Demand to launch | "Adding 1 node(s) of type worker" within about 10 s of submitting; the head's 10 slots were full, so 10 tasks were pending |
| SSH | available about 40 s after launch (`waiting-for-ssh`) |
| File mounts | `.env`, Bedrock key and Ray token synced in under 2 s (the files from the head reached the worker) |
| `ray stop` on the worker | took about 32 s (the cause was not investigated) |
| `ray start` | **failed**: `Version mismatch: cluster Ray 2.59.0 / Python 3.12.15, this node Ray 2.59.0 / Python 3.12.16` |
| After the failure | status `update-failed`; the autoscaler declared "launch failed", stopped the node, tried a replacement launch (`VcpuLimitExceeded`), then restarted the stopped node (reuse); the restarted node stayed `uninitialized` for 10 minutes with no new updater run, while the head ran the pending tasks on its own slots |

**Findings**
1. **Ray requires the exact Python patch version on every node.** The AMI recipe ran `uv python install 3.12`, which fetched 3.12.16; the head VM (and every earlier run) uses 3.12.15. The recipe now installs `${EXPECT_PYTHON}` (default 3.12.15) through a pinned copy of the owner's bootstrap script (checked that the three `3.12` places are pinned), asserts the version, and `ami_verify.sh` checks it. **AMI v2 has the wrong Python and has to be rebuilt as v3.** This is the same failure class as the earlier "versions must match across nodes" note, now at patch level.
2. **The vCPU quota is 32** for the instance family's bucket (read from the EC2 error text, since Service Quotas is not readable). The existing VM uses 16, so **only one 16-vCPU worker fits**. Scaling beyond that needs a quota increase request (the owner must make it).
3. **A node that fails to set up is not retried.** After a failed update the autoscaler stopped it, and when it was reused the node stayed `uninitialized`. For a real run this means a bad image strands capacity; the monitor needs watching and `stop_workers.sh` is the recovery.
4. The pieces that worked and are now proven on real EC2: demand-driven launch, the role's EC2 permissions for the autoscaler (launch, tag, stop, restart), SSH from the head with the worker key, file-mount sync of the three secret files, the `ray-node-status` tag updates, and the worker-only teardown script.
5. Test hygiene: the first `dummy_demand.py` used `address="auto"`, which could have attached to another user's head on the same VM; it now requires `--address` explicitly (caught before the run).

**Cost of the failed attempt:** about 12 minutes of one `m7i.4xlarge` plus the stopped worker's 512 GiB disk until it is deleted (the worker is still in the account, stopped).

**Next:** rebuild the AMI as v3 with the pinned Python (build instance about $0.2 to $0.3 an hour for 1 to 2 hours), update the cluster YAML's AMI, delete the stopped worker (its old AMI-v2 disk), and rerun the dummy test; ask the owner for a vCPU quota increase.

## 16. AMI v3 built and verified with the pinned Python (2026-10-30)
Rebuilt the worker image from a clean stock Ubuntu `m7i.xlarge` (60 GiB root) with `EXPECT_PYTHON=3.12.15`, matching the head VM (both of its venvs run 3.12.15). A test instance from the final image, launched with a 100 GiB volume, passed all 13 checks on a cold boot (the verify script now also checks that the Python patch version equals the head's, and that the default base-image digest `prepare.py` pulls is present), and its filesystem grew to 96 GB. Both base-image digests (`fba1033c…` and `8eda74a1…`) are present, which also settles the earlier mix-up: they are pullable digests.

**Recipe bugs found while rebuilding (each fixed, all in the pinning step)**
| Bug | Cause | Fix |
|---|---|---|
| `sed: can't read scripts/bootstrap_ec2.sh` | the pinned copy was made before the `cd` into the repo | use an absolute path |
| `Permission denied` reading `/home/ubuntu/...` | the line sits inside an unquoted heredoc, so `$HOME` was expanded by the outer shell as the build user's home | escape it (`\$HOME`) so the inner shell expands it |
| `can't open file '//scripts/patch_cybergym.py'` | the owner's bootstrap finds the repo root from its own location, and the pinned copy lived in `/tmp` | write the pinned copy next to the original (`scripts/.bootstrap_pinned.sh`), run it from the repo, delete it afterwards |
(One more slip of mine: a Python edit of the recipe failed on a wrong marker but the next lines ran anyway, so a run started with the old file; the recipe is idempotent, so it only cost a minute. Chain such steps with `&&`.)

**Cleanup done:** build and test instances terminated; the faulty v2 image and its snapshot deleted; the stale v2-based worker terminated with `stop_workers.sh --terminate` (it matched only that node). Left in the account: the v3 image and its snapshot (60 GiB, private, tagged), no tagged instances.

**Spend:** an `m7i.xlarge` for about 1 hour 15 minutes plus a test instance for about 15 minutes, and snapshot storage; a few tenths of a dollar for compute (estimate, not read from billing).

**Next:** point the cluster config at the v3 image (edit the prepared file on the head; the autoscaler reloads it) and rerun the dummy scale-up test (one billed worker, about $0.2 to $0.4), then ask the owner for a vCPU quota increase.

## 17. Stage 3 passed: dummy scale-up and scale-down on real EC2 (2026-10-30)
Same test as section 15 (20 sleeping tasks of 300 s, 1 CPU and 1 slot each, `max_workers 1`), now with the v3 image. **Everything worked end to end**, with no model spend and about 12 minutes of one `m7i.4xlarge` billed (about $0.16, estimate); the worker was stopped by the autoscaler itself.

| Phase | Result (VM clock, UTC) |
|---|---|
| Demand to launch | tasks submitted about 06:45:50; launch queued 06:46:01; "Adding 1 node(s) of type worker" |
| Worker image | verified from EC2: the launched instance used the v3 image (the autoscaler re-reads the YAML on every update loop, so no head restart was needed after changing the image id) |
| SSH ready | 06:46:46 (39 s after launch) |
| File mounts | `.env`, Bedrock key and Ray token synced in about 0.6 s |
| `ray start` (including `ray stop`) | about 38 s |
| Worker joined | 06:47:28 ("Resized to 32 CPUs", status `up-to-date`): about 86 s from launch decision to a working node |
| Placement | **10 tasks on the head, 10 on the worker**, all 20 running at once (20 of 20 slots); the cluster showed 2 nodes and 20 `benchmark_slot` |
| Tasks done | about 5 to 7 minutes after submit; the cluster went idle |
| Scale-down | 06:57:27 "Terminating the node ... (idle)" about 4.6 minutes after the last task, close to the 5-minute `idle_timeout_minutes`; the node ended `stopped` (not terminated) because `cache_stopped_nodes` is on; "Resized to 16 CPUs" |

**What this proves:** demand-driven launch from the pending queue; the slot custom resource reaches the worker (20 slots total) and is scheduled correctly across nodes; token auth works for the join; file-mount secret delivery; Python pin fixes the join; idle scale-down to a stopped node; the owner's head and our old head untouched throughout.

**Still not proven**
1. **Restart reuse:** the stopped worker should be restarted by the next burst (matching launch config); not tried. It still sits in the account **stopped**, with its 512 GiB disk billing (about $1.3 a day at the usual gp3 price, my estimate) until terminated (`stop_workers.sh --terminate --yes`).
2. The **real task path**: task data and images on the worker (`prepare`), the metering shim and budget on each node, shared results (sections 9 and 5 of the build plan).
3. **More than one worker:** the vCPU quota is 32, so one worker fits next to the head VM; scaling out needs the owner to request an increase.
4. The head is a plain process: **no restart after a VM reboot** (systemd unit still to do).
5. Minor: the Mac's EC2 call failed once with a transient network error mid-run; nothing to do with the autoscaler.

**Next:** a second burst to test restart reuse (cheap, same worker), then stage 4: twelve light real tasks, which needs the per-node data/images and shim handled first.

## 18. Full-path test, preparation: code merged and deployed, config prepared (2026-10-30)
Goal of the next test: run real tasks through the autoscaler with the shared Postgres in the loop, and prove that everything a worker produced is in Postgres before any worker is terminated (rollout order in [[wiki/syntheses/shared-postgres-state-design]] section 5c). **No tasks have been run and no worker launched; nothing here cost money.**

**What a worker needs for a real task (not just a sleeping one):** the new runner code; the Postgres library; the task data for the manifest (`prepare`; the image has only the base images); its own metering shim (bound to the Docker gateway, with a spend cap); the variables loaded into its Ray process (a Ray task sees its node's environment, not the driver's, so the shim master key, the database URL and the HF token must be exported when the node starts Ray).

**The VM's working copy is not the owner's repo plus our PR.** It also holds the shim integration, the concurrency gate (`db.claim_slot`), the tools and our manifests. Compared with the PR branch: `worker.py` +65/-7 lines, `db.py` +45, `config.py` +9/-2, `cli.py` comments only. So the Postgres commits were merged onto the VM copy, not copied over it: `cli.py` taken from the branch (identical apart from comments), `worker.py` merged by hand (the sink inserted after `_start_slot`, the three finish paths extended; only 3 lines of the VM version replaced, each by an extended line), `config.py` and `db.py` left as they were.

**Verification before touching the VM:** 58 tests pass in the merged tree against a throwaway Postgres (the VM's own gate tests, our 29 Postgres tests, and a new VM-only test that checks the shim's per-execution usage arrives in the Postgres result); the new test fails when the success-path sync is disabled.

**Deployed to the VM (2026-10-30):** the merged `src/`, `tests/` and `pyproject.toml`; `psycopg` installed into the VM venv (additive); the full suite run **on the VM against the hosted test database: 58 passed**; the three running Ray heads kept their uptimes (the running Ray processes still hold the old code in memory until restarted). Backups are on the VM as `src.bak-pre-pg`, `tests.bak-pre-pg` and `pyproject.toml.bak-pre-pg`.
**Slip:** the backup step failed (a shell variable used as a command, the same zsh trap as before) while the copy step ran, so for a few minutes the merged files were on the VM without a backup. A pristine copy of the VM tree had been pulled minutes earlier for the comparison; the backups were rebuilt from it and checked (the backup `worker.py` has no `_PgSink`; exactly `cli.py`, `worker.py`, `pgstore.py` and `pyproject.toml` differ).

**Prepared in the vault (validated offline with Ray's own checks, not yet used):** `start_worker_services.sh` (starts the shim on a node, idempotent, reads the master key from the copied `.env`, prints no secrets; its "already answering" path was run on the head VM and exited 0 with still exactly one shim); cluster template additions: file mounts for the runner source, the manifest and the services script, worker setup commands for the Postgres library and for `prepare`, and a worker start command that starts the shim, loads the `.env` into the shell (`set -a`), then starts Ray. Checked on the VM: the `.env` sources to values identical to the raw lines for the shim key, the database URL, the HF token and the Bedrock token (the one mismatch is a `~` in an unrelated path variable, expanded by the shell).

**Still to do for the test:** restart our head by exact PIDs with the `.env` loaded (the head's Ray process must carry the shim key and database URL) and with 1 head slot so tasks overflow to a worker; render the prepared config; a small 4-task manifest; then run. Worst-case model spend is bounded by the per-node shim caps (the head's shim has about $9.7 of its $12 left; a worker's would be capped at $4), since the cluster-wide budget in Postgres is not wired to the shim yet.

## 19. Quota raised to 40 vCPUs; worker size, CPUs and slots are template parameters (2026-10-30)
- **The owner raised the EC2 vCPU quota from 32 to 40** (relayed; not verifiable here: Service Quotas is denied for our user, and a dry-run launch does not check the quota, even a 192-vCPU dry-run returns "would have succeeded"). It is an AWS Service Quota ("Running On-Demand Standard (A, C, D, H, I, M, R, T, Z) instances", us-east-1), counted in **vCPUs** across all running instances, so the head VM's 16 leave 24 for workers: one 16-vCPU worker plus one 8, or **three 8-vCPU workers**, or six 4-vCPU. At 128 vCPUs the head plus seven 16-vCPU workers would fit (126 would not make eight full-size nodes). The limit is shown in the rejection message of a real launch; the autoscaler log reports it.
- **Worker size is our choice, not tied to the head:** it comes from `node_config.InstanceType` in the YAML; the AMI works for any size.
- **Slots per node are set in the cluster YAML** (the node type's `resources` and the worker's `ray start --resources`), not by the manifest's `benchmark_slots`, which only applies to `--address local`. The autoscaler plans node counts from the node type's numbers, so they must match the real instance: on the 16-vCPU machine 8 to 10 light patch-only slots were comfortable and 16 saturated the CPU (about 0.5 slots per vCPU), so an 8-vCPU worker gets about 4. Memory is not the limit (about 1 GB per patch-only task).
- **Template fixed** (it hard-coded 16 CPUs and the 4xlarge type): `WORKER_TYPE`, `WORKER_CPUS` and `SLOTS` are now parameters, worker volumes are tagged `project=benchmark-ray`, the example env defaults to 3 × `m7i.2xlarge` with 4 slots each, 150 GiB disks, head 4 slots on port 6381, worker shim cap $5. Validated offline (a bug in my edit, a text replacement that also hit `HEAD_SLOTS`, was caught by the check that every template placeholder is defined).
- **Proposed 20-task test (not run):** 20 light patch-only tasks (344 of the 920 tasks are light), 4 head + up to 3 × 4 worker slots = 16 concurrent; expected model spend about $10 (24 earlier Kimi K3 patch-only runs: mean $0.53, median $0.36, p90 $0.70, max $2.85, all 24 passed; mean duration 7 min, p90 9, max 15), about $14 if every task cost the p90; workers about $1.2 (estimate); per-node shim caps give an absolute ceiling of about $25 (the head's shim has about $9.7 left, $5 per worker); workers stay stopped, not terminated; the old stopped 4xlarge worker is terminated first (its disk bills about $1.3 a day).
