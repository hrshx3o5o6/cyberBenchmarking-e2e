---
type: synthesis
created: 2026-11-02
updated: 2026-11-02
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [runbook, vm, aws, ray, shim, postgres, autoscaler, cost]
---
# Stopping and starting the head VM: checklist and bring-up

The owner of the VM confirmed (2026-11-02) that it can be stopped when not in use and started when needed. Stopping ends compute charges; the disk (about 496 GB, 227 GB of Docker images, the Postgres volume) keeps billing. Background: [[wiki/syntheses/how-a-run-works-on-the-vm]], [[wiki/syntheses/ray-autoscaler-build-plan]], [[wiki/syntheses/shared-postgres-state-design]].

## What survives a stop, what does not
| Survives | Does not survive |
|---|---|
| Disk contents: code, images, Postgres data, rendered cluster config, local env file, `config/.env` | Every hand-started process: our autoscaling Ray head, the metering shim (and its in-memory spend total and live keys), the monitors |
| The four Ray tags on the instance, the instance role | The owner's Ray head and any of the owner's containers that are not set to restart |
| The private IP address | The public IP, unless the instance has an Elastic IP (not checked) |
| Postgres (container restarts always), the firewall proxy (restarts always) | `/tmp` contents (Ray's temp dir): use a new temp dir on the next start |

## Before stopping (done 2026-11-02, all clear)
1. No run in progress: no `cybergym-eval`, `run_agent` or task containers.
2. No EC2 workers: only the head instance carries the autoscaler's tags (checked with boto3 on the VM; the `aws` CLI is not installed there, so `tagged_instances.sh` does not work on the VM as is).
3. Fresh Postgres backup with `~/autoscaler/pg/backup.sh`, copied to the Mac outside any Git repository with the checksum matched (two dumps, 502,046 bytes each).
4. Note the shim's spend so a restart can carry it over: total spent 17.483334 of a 20 cap at that time.
If workers exist, terminate them first with the worker-only teardown script; a worker left running without a head keeps billing.

## Bring-up after the instance is started
1. Find the new public IP if it changed; SSH in.
2. Check Docker is up and `cybergym-postgres` and `cybergym-proxy` are running and healthy; check the `cybergym-internal` Docker network exists.
3. Start the shim (idle), carrying the spend over: `TOTAL_START=<spent so far> bash ~/benchmark-evals/tools/start_worker_services.sh <target-model> <total cap>` (it reads the master key and upstream key from the node's own files and prints no secrets; it does nothing if a shim already answers).
4. Start our Ray head. The rendered and prepared cluster YAML and the local env file are still on disk, so `render_cluster.py` and `prepare_cluster.py` only need re-running if the template changed. Then start the head by hand as described in the template's comment: `ray start --head` on its own port with a free autoscaler metrics port, `--autoscaling-config` pointing at the prepared YAML, `--resources` for the benchmark slots, a short private temp dir, `RAY_AUTH_MODE=token`. Never `ray up` or `ray down`, never a plain `ray stop`.
5. Verify: the head shows in `ray status`, the four tags are present, the instance role is attached, `/health` on the shim answers with the expected caps and spend.
6. The owner's head and containers are the owner's to restart.

## Cautions
- If the VM is unresponsive (SSH stalls at the handshake, seen once on 2026-11-02 and gone again later), do not stop it blindly mid-run; check for a run in progress first.
- Stopped means the disk charge continues. Terminating the instance deletes the disk and everything on it: never do that.
