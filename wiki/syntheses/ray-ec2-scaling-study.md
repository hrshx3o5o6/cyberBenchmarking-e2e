---
type: synthesis
created: 2026-10-26
updated: 2026-10-26
sources: ["[[sources/cybergym-e2e]]"]
tags: [aws, ec2, ray, autoscaler, scaling, infrastructure, ebs, s3, ecr, postgres, design, ideation, benchmark-evals]
---
# Scaling beyond one VM: Ray on EC2 (study, design and the changes it needs)

**Status: the design below is ideation; a two-VM Ray test has since been built and run: see [[wiki/syntheses/two-vm-ray-cluster-setup]] (what we did) and [[wiki/syntheses/two-vm-ray-test-observations]] (results).** It records what we measured on the single AWS VM, what we learned about Ray clusters and the Ray autoscaler from the official docs, the storage questions (EBS, S3, ECR, a database), and the infrastructure and code changes the current setup would need. Single-VM measurements and the runner itself are in [[wiki/syntheses/benchmark-evals-aws-vm-parallelism]] and [[wiki/syntheses/aws-vm-concurrent-setup-reference]]. Claims marked *(inference)* are mine and not from the docs; claims marked *(unverified)* come from memory and should be checked.

## 1. What we measured that drives the design
| Fact (single 16-vCPU VM, Kimi K3 on Codex) | Consequence |
|---|---|
| **CPU is the bottleneck, not memory.** Memory 1 to 3 GB per task, never above 33 GB of 61, no swap | Scale on vCPUs; choose CPU-optimised instances, not memory-heavy ones |
| Patch-only: 8 at a time comfortable, 16 overloaded. e2e: 10 at a time busy but workable (CPU pressure 65 to 80 for about 20 minutes in the middle) | About 8 slots per 16-vCPU VM is the working number; e2e probably 7 to 8 *(inference)* |
| e2e throughput about 9.5 to 11 tasks/hour per VM (two runs of 12 and 10 tasks, not like-for-like) | A full 920-task e2e pass is roughly 85 to 100 VM-hours |
| Model spend dominates: e2e averaged about $4.9 per task over 22 tasks | 920 tasks is about $4,500 of model calls against roughly $65 of VM time (on-demand m7i.4xlarge about $0.8/hour, *unverified*); budget control matters more than VM count |
| Task images are large: 18 images took about 150 GB; 50 sampled tasks used about 190 GB | The full set (about 509 distinct images at 3 to 10 GB each) is roughly 1.5 to 3 TB before layer sharing, which we have not measured |
| Grading rebuilds the project in 4 fresh containers per task and stretches 1.5 to 5x under load | Stagger starts; the heavy period is several tasks reaching grading together |
| Provider limits are unknown: one e2e run made about 64 model calls/minute at 10 concurrent | At 100 concurrent that is 600+ calls/minute; **Bedrock's rate limit may cap the cluster before the VMs do** |

## 2. The instance we have now
`m7i.4xlarge` (16 vCPU, 64 GiB), on-demand, us-east-1c, default VPC, security group `launch-wizard-4` (the console's default wizard group, normally SSH-only; rules not checked), 496 GB root volume (223 GB used), **no IAM instance profile attached** (so the VM cannot call AWS APIs, e.g. to launch instances), no AWS CLI installed. It also runs Amit's own Ray head (GCS on port 6379, listening on all interfaces) under another user; ours is separate.

## 3. Ray cluster concepts (from the docs)
| Piece | Meaning |
|---|---|
| **Head node** | One machine hosting the cluster singletons: the GCS (cluster state), the autoscaler, and the driver. It can run tasks but the docs say that is not desirable at scale ([Key Concepts](https://docs.ray.io/en/latest/cluster/key-concepts.html)). Start it with `ray start --head --num-cpus=0` to keep tasks off it. |
| **Worker nodes** | Run only user tasks and actors; each runs a **raylet** that accepts tasks and reports resources. One Ray node = one VM. |
| **Logical resources** | Declared numbers (`CPU`, custom ones such as our `benchmark_slot`) used for admission control only. They are **not enforced** and there is no CPU pinning; a `num_cpus=1` task can still use many threads ([resources](https://docs.ray.io/en/latest/ray-core/scheduling/resources.html)). Node capacities **cannot change after the node starts**; they are set with `ray start --resources`, `ray.init`, or the `resources` field in the cluster YAML. |
| **Hard constraints** | A task whose resources no node can provide waits until a feasible node joins. This is what makes autoscaling work: queued `benchmark_slot` demand causes new nodes to be launched. |
| **Autoscaler** | Open-source code inside the `ray` package, running on the head. It adds workers when demand exceeds capacity and removes idle ones, deciding from **requested resources, not real utilization**. It is not an AWS Auto Scaling Group; on EC2 it calls the EC2 APIs through `boto3` (so the head needs credentials or an instance role). On Kubernetes a variant runs as a sidecar. Ray has more than one autoscaler implementation (a newer "v2", mainly with Kubernetes); the classic one drives the EC2 YAML path *(unverified, check the autoscaling docs for the version in use)*. |
| **Cluster launcher** | The `ray up` / `ray down` commands, run from your laptop. They read the YAML, start the head and set it up over SSH. The head's autoscaler then manages workers. Two components: launcher (laptop) and autoscaler (head). |

**Scheduling** ([scheduling page](https://docs.ray.io/en/latest/ray-core/scheduling/index.html)): the **default** policy gives each node a score: nodes under 50% utilization (`RAY_scheduler_spread_threshold`) all score 0 and are equal; above that, less-utilised nodes win; Ray picks randomly from a top-k group (20% of nodes by default); tasks with large arguments prefer the node holding them (irrelevant for us: our arguments are small). **SPREAD** (`scheduling_strategy="SPREAD"`) forces even distribution. **NodeAffinity** pins to a node ID and cannot fully use an autoscaling cluster (node IDs must be known in advance): avoid. **Placement groups**: gang scheduling for actors, not needed. **Labels** (beta): placement by node labels; candidate for routing a task to a node that already holds its image; the labels sub-page has not been read, so user-defined labels are *unverified*. *Correction to an earlier statement:* I first said the default policy "packs work onto busy nodes before spreading"; per the page it is closer to randomised balancing with a bias against nodes above 50% utilisation. Consequence *(inference)*: scale-down may be slower because nodes tend to stay partly busy.

**Fault tolerance** ([node fault tolerance](https://docs.ray.io/en/latest/ray-core/fault_tolerance/nodes.html)): a dead worker's running tasks fail and are retried elsewhere up to `max_retries` (Ray's default is 3; **our runner sets 0**, so a lost VM loses its runs). A retry is only safe if the retried run is idempotent: stray containers cleaned, the old metering key revoked, no double spend. Losing the **head node loses the whole cluster** (it hosts the GCS); GCS fault tolerance exists but needs external storage and is probably not worth it, so job state must live outside Ray. If the driver dies, its tasks are cancelled, so run the driver on the head, not a laptop.

**Security** ([token authentication](https://docs.ray.io/en/latest/ray-security/token-auth.html), [Anyscale write-up](https://anyscale.com/blog/ray-security-token-based-authentication)): since Ray 2.52, `RAY_AUTH_MODE=token` enables a shared-secret token for the external APIs and internal traffic; it is sent as an HTTP header, so use a VPN, SSH tunnel or TLS rather than plain HTTP. An unauthenticated dashboard or Jobs API lets anyone with network access run code on the cluster (CVE-2025-34351). Keep ports 6379 and 8265 off the internet. Worth checking: whether Amit's head has token auth on (it listens on all interfaces).

## 4. Cluster launcher + autoscaler on EC2
Docs, in reading order: [Getting Started](https://docs.ray.io/en/latest/cluster/vms/getting-started.html) (`ray up -y config.yaml`, `ray down -y config.yaml`; needs `boto3` and AWS credentials in `~/.aws/credentials`), [Launching Ray Clusters on AWS](https://docs.ray.io/en/latest/cluster/vms/user-guides/launching-clusters/aws.html) (on-demand head, Spot workers; `IamInstanceProfile` in a node type's `node_config`; Ray nodes get broad EC2 and S3 access by default, which it recommends reducing), [Cluster YAML reference](https://docs.ray.io/en/latest/cluster/vms/references/ray-cluster-configuration.html), [Cluster Management CLI](https://docs.ray.io/en/latest/cluster/cli.html) (`ray up/down/exec/submit/attach`, `ray get_head_ip` with an underscore, `ray monitor` to tail the autoscaler log; `ray up` flags `--min-workers`, `--max-workers`, `--no-restart`, `--restart-only`, `-y`, `-n`). The AWS guide does not list minimum IAM permissions. Editing a node type's `node_config` and re-running `ray up` replaces the old nodes of that type. The guide's template is `example-full.yaml` in the Ray repository.

Illustrative YAML for our case (**untested**):
```yaml
cluster_name: cybergym-eval
max_workers: 12                      # hard cap on worker VMs
idle_timeout_minutes: 10
provider: {type: aws, region: us-east-1, availability_zone: us-east-1c}
auth: {ssh_user: ubuntu, ssh_private_key: ~/.ssh/cluster.pem}
head_node_type: head
available_node_types:
  head:                              # small, on-demand, never Spot
    resources: {CPU: 0}
    node_config: {InstanceType: m5.xlarge, ImageId: ami-xxxx, IamInstanceProfile: {Arn: ...}}
  worker:
    min_workers: 0
    max_workers: 12
    resources: {CPU: 16, benchmark_slot: 8}   # what Ray ASSUMES; must match the measurement
    node_config: {InstanceType: c7i.4xlarge, ImageId: ami-xxxx,
                  BlockDeviceMappings: [{DeviceName: /dev/sda1, Ebs: {VolumeSize: 1000}}]}
head_start_ray_commands: [ray stop, ray start --head --port=6379 --autoscaling-config=~/ray_bootstrap_config.yaml]
worker_start_ray_commands: [ray stop, ray start --address=$RAY_HEAD_IP:6379]
```

## 5. Options compared
| Option | Pros | Cons |
|---|---|---|
| **A. Ray cluster on EC2 VMs** (launcher + autoscaler) | Closest to what we have; Ray places work and scales nodes | Shared state, image distribution and the budget are all on us; the head is a single point of failure |
| **B. VM fleet + central queue** (SQS or a Postgres table); each VM runs our existing single-VM runner as a worker that pulls jobs | Simplest and most robust; a dead node just returns its job to the queue | We own the scheduling; less Ray |
| **C. KubeRay on EKS** | Standard autoscaling and restarts | Our tasks launch nested Docker containers and need privileged pods; operationally heavy |

Lean *(inference)*: A or B on top of a shared job store, because the hard problems (state, images, budget) are identical either way and Ray adds little once the store exists. Ray earns its place if we want its scheduler and autoscaler, or want to scale non-CyberGym benchmarks the same way.

## 6. Getting from one instance to several
"Multiple VMs" means multiple **EC2 instances** in the same VPC, preferably the same subnet and zone (private-IP traffic, free data transfer). Ways: (1) launch from the AWS console with the IAM login Amit provided, if it has EC2 permissions (not yet known): *Actions, Images and templates, Launch more like this* copies the type, network and security group; (2) Amit launches it; (3) later `ray up` from a machine with AWS credentials, plus an instance role on the head for the autoscaler. **Do not clone the existing instance into an image**: it would copy Amit's files, his `.env` key and 223 GB of images; start from clean Ubuntu and run the bootstrap.

Checks before anything: can the login reach the last step of *Launch instance*; the vCPU quota (two 16-vCPU instances need 32); a security-group rule letting the instances reach each other on the Ray ports plus SSH from our IP; Amit's approval of another paid instance; which SSH key pair to use.

**Smoke test (static cluster, no autoscaler):** our own head on VM1 on a port other than Amit's 6379 (own temp dir, token auth), VM2 joins with `ray start --address=<VM1 private IP>:<port> --num-cpus=16 --resources='{"benchmark_slot": 8}'`; run a handful of tasks from VM1 and check that some land on VM2. The runner's SQLite and artifacts stay node-local, so results are collected by hand; it proves placement and plumbing, nothing more. VM2 needs the same code paths, Docker, the images and data, and a local shim and squid.

## 7. Storage: who does what
| Storage | Role |
|---|---|
| **EBS** | The disk attached to **one** instance: Docker's image store and each run's scratch workspace and logs while running. Every instance already has one (ours: 496 GB root). Not shared. |
| **ECR** (or Docker Hub / GCR) | The container **registry**: one copy of the 509 images; nodes pull layers onto their EBS, which acts as a cache. Mirroring into ECR avoids Docker Hub rate limits and slow pulls. |
| **S3** | Shared, durable: `result.json`, `runner.log`, trajectories and logs after a run; a copy of the task data. Not the job state and not Docker images. |
| **A database** (RDS Postgres or DynamoDB) | Job state: pending, running, finished, leases. |
| **Secrets Manager / SSM** | The Bedrock key, the HF token, the shim master key. |

**Why images are not shared between instances:** a normal EBS volume attaches to only one instance (Multi-Attach exists only on io1/io2, within one zone, and needs a cluster-aware filesystem *(unverified)*); each Docker daemon assumes it owns its image store, so two daemons on one directory corrupt it; and a network filesystem (NFS/EFS) is unsupported or slow for Docker's storage and would slow the builds that are already our bottleneck. The shared home for images is the registry, with a local cache per node. Options to populate a node's EBS: pull on demand from ECR; bake into an AMI or EBS snapshot (restored blocks load lazily on first read *(unverified)*, so first use can still be slow); route tasks to nodes that already hold their image (labels or per-image custom resources); lazy-loading formats such as stargz or SOCI (read about later). N nodes mean N copies and N volumes billed per GB while they exist (gp3 roughly $0.08/GB-month, *unverified*); set `DeleteOnTermination` so terminated nodes do not leave paid disks. Layer sharing between images is unmeasured (`docker system df -v` on the VM would show it).

## 8. Changes needed in the current setup
The runner today assumes **one machine**: local SQLite, local files, one metering shim, one Docker. Ray already decides which node runs which task, so most of the work is removing the single-machine assumptions.

**Ray side (small).** Driver (`cli.py`): `ray.init(address="auto")` on the head instead of `address="local"`; drop the local `_temp_dir` and the `resources=` argument (nodes declare their own). Each node: `ray start --address=<head> --num-cpus=16 --resources='{"benchmark_slot": N}'` (or the YAML field); head `--num-cpus=0`. Submission: keep `num_cpus=1, resources={"benchmark_slot": 1}`; optionally `scheduling_strategy="SPREAD"`; set `max_retries` above 0 only once cleanup is idempotent. Not needed: placement groups, NodeAffinity, locality tuning. The repo already accepts `--address`.

**Phase 0: two-VM smoke test.** Almost no code change (section 6).

**Phase 1: shared state and a central budget** (the real work):
| Today | Change |
|---|---|
| SQLite state file (`db.py`) | Networked database with an atomic claim (`FOR UPDATE SKIP LOCKED` in Postgres), **leases and heartbeats** so a dead worker's rows are reclaimed; the `claim_slot` gate maps onto it |
| `artifacts/` on local disk (`worker.py`) | Upload results, logs and trajectories to S3; store the S3 paths in the job store |
| Metering shim: one process, **keys in memory only** (learned when the cap had to be raised) | A gateway service with persistent keys and a global atomic budget (Redis/Postgres), reachable from every node |
| `config/.env` copied to the VM | Secrets Manager / SSM; nodes get only short-lived per-run keys |
| `config.py` local paths | Cluster settings: store DSN, S3 bucket, gateway URL, slots per node |
| `status` / `report` read SQLite | Read the shared store and S3 |

**Phase 2: code and images on every node.** Bake an AMI (Packer or user-data): Docker and group, `vm.mmap_rnd_bits=28`, `uv`, repo, venvs, squid and the `cybergym-internal` network, systemd units for the shim and monitors; `bootstrap_ec2.sh` becomes idempotent. Choose the image strategy (section 7), mirror images to ECR, mirror or bake the task data. `preflight` and `prepare` stop being "run on the driver machine": node-level checks move into node bootstrap or a Ray task per node.

**Phase 3: robustness and scaling.** Retries with idempotent cleanup (label each run's containers with its execution ID; remove stragglers; revoke the old key); a heartbeat thread in `execute()`; per-node stagger (file lock, keeps working) and per-node watchdog; the adaptive gate stays optional and per-node (see [[wiki/syntheses/aws-vm-concurrent-setup-reference]], section 14); autoscaler YAML plus an IAM role on the head; head on-demand, workers possibly Spot (2-minute eviction notice).

**Phase 4: operations and security.** Per-node PSI, CPU, memory and disk to CloudWatch or Prometheus; the Ray dashboard; token auth; security groups limited to the cluster and our IP; SSH via SSM or a bastion; least-privilege IAM (head: EC2 launch/terminate and `iam:PassRole`; workers: S3, ECR pull, Secrets read); a global spend cap in the gateway, an hourly ceiling, idle timeouts, AWS budget alarms.

**Network decision to make early.** The agent container is on an internal Docker network with no internet route and reaches the shim at the Docker gateway IP; a central gateway on another machine is not reachable that way. Either a small forwarder/shim on every node that forwards to the central gateway (simpler, container's view unchanged), or add the central gateway to the squid allowlist.

Rough effort *(my estimates, not measured)*: smoke test, hours; shared store plus S3 plus gateway, a few days (the largest piece); AMI and image strategy, a couple of days (mostly waiting on pulls); retries and hardening, several days; autoscaler and operations, a few days.

## 9. Sizing sketch (from measured rates, to validate)
100 e2e tasks/hour needs about 10 VMs (about 160 vCPUs); a full 920-task pass is about 9 hours on 10 VMs. At the e2e average cost that is about $490/hour of model spend, so a global budget and an hourly ceiling matter more than the VM count. Cold start matters: a new worker has to boot and hold its images before it is useful.

## 10. Experiments to run before building
1. Best slot count per instance type (try a 32-vCPU instance: do slots scale linearly?).
2. Image distribution: time to pull the 509 images, EBS snapshot restore, ECR throughput; layer sharing via `docker system df -v`.
3. **Bedrock's actual rate limit** (requests and tokens per minute) for the account and model.
4. Two-VM smoke test (section 6).
5. Behaviour on worker loss (kill one mid-run) and on head loss; a Spot eviction drill.
6. AWS quotas and IAM: vCPU limits, launch permission, Spot vs on-demand.
7. Read the Ray labels sub-page and the Out-Of-Memory Prevention page (Ray's memory monitor could kill a Ray worker on a busy node and leave its Docker containers behind; untested).

## 11. Asks of Amit (drafted separately, not sent)
Launch a second instance (or grant EC2 launch permission), same type and zone; a security-group rule between the instances; approval of the extra cost (roughly $0.8/hour while running, *unverified*); a check that his head has token auth on; later, an IAM role on the head for the autoscaler. We run our own head on a different port and leave his alone.

## 12. Open questions
Static cluster first, or straight to the autoscaler YAML? Spot, on-demand, or a mix for the first scale-up? Who owns the AWS permissions to launch instances? What is the target: one full 920-task pass, repeated model sweeps, or other benchmarks too? Is there a per-run budget and an hourly spend ceiling agreed with Amit?
