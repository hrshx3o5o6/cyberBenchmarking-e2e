---
type: synthesis
created: 2026-10-30
updated: 2026-10-30
sources: ["[[wiki/sources/cybergym-e2e]]"]
tags: [postgres, shared-state, observations, autoscaler, workers, terminate, design, benchmark-evals, stage-5]
---
# Shared Postgres state: record observations centrally, then let workers go (stage 5 design)

Part of [[wiki/syntheses/ray-autoscaler-build-plan]] (stage 5). Why: today every node keeps its own SQLite file and `artifacts/`, so anything on a worker disappears with the worker. The idea agreed in discussion: **each task copies its observations to a shared Postgres on the head, confirms they arrived, and only then returns; the autoscaler removes the node once it is idle.** Code is on the branch `shared-postgres-state` of the owner's repo clone (local commits `c2ec6e0` and `69560b4`, not pushed, not a PR; see [[wiki/syntheses/benchmark-evals-codebase-guide]]).

## 1. Principles
| Rule | Meaning |
|---|---|
| A task is not finished until its data is confirmed | `execute()` writes, then **reads everything back and compares** before returning |
| Do not terminate per run | a worker runs up to 10 tasks at once; the autoscaler's idle logic removes the node when all have returned |
| A database problem never fails the run | SQLite stays the local record; the result carries `observations_synced` and the problems |
| Off by default | only active when `CYBERGYM_DATABASE_URL` is set; the URL is kept out of the manifest so it never enters the config hash or the stored config |
| Node-level data streams continuously | Ray gives no pre-termination hook, so sampler/PSI/shim logs must be pushed every minute or so, not at task end (**not built yet**) |

## 2. What goes where
| Data | Stored | Why |
|---|---|---|
| State, hostname, attempt, timings, heartbeat, result (JSONB), error | table `executions` | small, queried |
| `result.json`, `runner.log`, upstream `summary.json`, trajectory logs | table `artifacts` (gzip, SHA-256, 25 MB cap per file, larger ones skipped and reported) | enough for a few dozen runs; S3 is the better home later (workers have no AWS role: `PassRole` was denied) |
| Per-request model usage | `usage_events` | rows; (shim integration not built yet) |
| Node metrics | `node_metrics` (idempotent inserts) | small; (streaming not built yet) |
| Cluster-wide spend | `budget` with an atomic `try_spend` (an `UPDATE ... WHERE spent + x <= cap`) | a global cap instead of per-node caps; (shim integration not built yet) |

## 3. Write path (built)
1. Driver `run()` registers every pending execution (`register_many`, existing rows untouched).
2. `execute()` calls `mark_running` (upsert: creates the row if the driver did not; bumps `attempt` on a re-run), starts a heartbeat thread with its own connection (every 30 s).
3. After the harness returns: `mark_finished` with the normalised result, upload the artifacts, then `verify`: status matches and every artifact is read back, decompressed and its SHA-256 compared with what was sent.
4. The returned result gets `observations_synced` (and `observations_sync_problems` when false). Timeouts and infra errors are recorded the same way.
5. Connection errors are retried with back-off (3 tries in the worker); an unreachable database costs a few seconds, not the run.

## 4. Tests (all pass; 32 in the whole suite)
15 new tests, 11 of them against a **real Postgres 14** (a throwaway server on localhost for the test run, deleted afterwards; skipped when `TEST_DATABASE_URL` is unset): schema creation is idempotent and safe under 6 concurrent starters; register / running / finished round trip incl. JSONB; heartbeat only touches running rows and advances during a run; artifacts are compressed (more than 10x on repetitive logs) and verified; tampering and missing artifacts are detected; usage, idempotent metrics, and **25 concurrent spenders against a cap of 10 get exactly 10 successes**; `execute()` copies state, result and artifacts and reads them back, also for a timeout; an unreachable database leaves the run unaffected and returns in under 15 s; the driver registration is idempotent and only warns on failure. Mutation checks (disabling the read-back comparison, and the budget cap) make the tests fail, as they should.

## 5. Reads and dead-worker handling (built, commit `69560b4`)
| Piece | Behaviour |
|---|---|
| `status`, `report`, `recover`, `run --resume` take `--source local|postgres` | default stays `local`; `postgres` needs `CYBERGYM_DATABASE_URL` and refuses to run without it (a `--source postgres` run also refuses to start if it cannot register in Postgres) |
| Heartbeat age | every Postgres row carries the age of its last beat, measured with the **database's clock** (no clock-skew between nodes); `status` prints it for running rows |
| `--resume` | skips executions that are `passed` or **still beating** (so a second driver cannot double-run live work), re-runs failed ones and ones whose worker stopped |
| **Driver survives a lost task** | `ray.get` is wrapped: a worker crash, node loss or out-of-memory becomes an `infra_error` (printed, counted as a failure, recorded locally and in Postgres) and the run carries on. Bookkeeping errors only warn. |
| Overwrite guards | `mark_infra_error` only changes `pending`/`running` rows, so a delivered result is never overwritten |
| `recover --source postgres` | marks `running` rows with no heartbeat for 5 minutes (default) as `stale_running`, naming the last host, **without reading the dead node's disk**; the age check is inside the `UPDATE`, so a late heartbeat or finish wins the race; `--dry-run` supported |
| `sync-check` (run **on a node**) | compares that node's local record and artifact files with Postgres: status, result, and the SHA-256 of every artifact; corrupt or missing copies are reported, not crashes; prints a warning when nothing was compared. This is the check for the rollout below. |
Tests: 14 new (46 in the suite), against a real Postgres 14 for the database ones. Mutation checks (each break must fail a test): driver no longer surviving a dead worker, `infra_error` overwriting a result, stale marking ignoring the heartbeat age, resume ignoring fresh rows, and `sync-check` skipping the artifact compare or the result compare. The last one initially **survived** (no test covered it); a test was added and the mutation now fails. Also tried through the real command-line entry point as a separate process against a seeded database: `status`, `recover --dry-run` and `recover`, `report`, `sync-check`, and the refusal without the variable.

## 5b. Still not built
1. **Shim integration:** usage rows and the atomic cluster-wide budget (the table and `try_spend` exist and are tested; the shim does not call them).
2. **Node-metric streaming** (sampler/PSI): Ray gives no pre-termination hook, so these must be pushed continuously.
3. ~~Hosting~~ done: see section 5d (the remaining parts are the scheduled backup, an off-machine copy, and getting the URL into every node's Ray environment).
4. **AMI v4** with `psycopg[binary]` (extra `postgres`), rebuilt with the Python pin.
5. **Big blobs:** the 25 MB-per-file cap means larger logs are skipped and reported; S3 later.
6. **Worker volume tags** and the switch from stop to terminate (next section).

## 5c. Rollout order (agreed)
1. Build the write path and keep `cache_stopped_nodes: true` while it is proven (done: sections 3 and 5).
2. Host Postgres on the head VM (done, section 5d), run a test, then check that **everything from the worker is in Postgres and matches the node's local files**: `sync-check` on each node, plus `status --source postgres` from the head.
3. Only then switch to terminate.

## 5d. Hosting: Postgres now runs on the head VM (2026-10-30)
Done with the owner's go-ahead. A container on the always-on head VM, **reachable only inside the VPC**; nothing else was changed on that VM.
| Item | Setting |
|---|---|
| Image / version | `postgres:16` (16.15), container `cybergym-postgres` |
| Network | published on the VM's **private address only** (checked with `ss`: nothing on the public side, nothing on loopback); the VM's two security groups allow only SSH from outside and all traffic among our own cluster's machines, so port 5432 is not internet-reachable |
| Authentication | `scram-sha-256` with a generated 40-character password; a custom `pg_hba` accepts only VPC addresses (and the Docker bridge) and **rejects everything else**; the password lives in files with mode 600 (and a 400 copy owned by the container's user), never in a command line, a manifest or this vault |
| Tested logins (from the VM, over the private address) | correct password connects; wrong password, no password and wrong user are all refused; loopback refused |
| Data | Docker volume `cybergym-pgdata` on the VM's disk (273 GB free when set up) |
| Resilience | restart policy `always` (the earlier lesson: `unless-stopped` stays down after a manual stop), health check, 4 GB memory limit, capped container logs |
| Databases | `cybergym` (production, schema created by `ensure_schema`, 5 tables, 0 rows) and `cybergym_test` (the test suite wipes its schema, so tests only ever target this one; a guard refuses any other name) |
| Client setting | `CYBERGYM_DATABASE_URL` added to the `.env` that the autoscaler copies to workers (mode 600); a temporary backup of that file made before the edit was deleted |

**Verification:** the whole suite (46 tests) was run from the VM against the hosted server through the real network path: all pass. A dump of the test database was restored into a scratch database and every table's row count matched (1 execution, 3 artifacts). **Bug found by this check:** the backup script named files by timestamp only, so two dumps in the same second overwrote each other (the test database's dump replaced the production one); the file name now includes the database name and pruning (keep the newest 14) is per database.

**Backups:** `~/autoscaler/pg/backup.sh [database]` writes a compressed custom-format dump to `~/pg_backups`; run by hand so far. **Not done:** a scheduled run (a cron entry in the VM user's crontab, e.g. daily) and a copy off the machine; if the VM's disk is lost the observations go with it.

**Open caveats found while doing this**
1. **Workers do not inherit the driver's environment**: a Ray task sees the environment of its node's raylet, not of the driver, and `load_config` only sets the variable in the driver process. So `CYBERGYM_DATABASE_URL` must be exported when each node starts Ray: for workers in the YAML's `worker_start_ray_commands` (read it from the mounted `.env`), and for the head by restarting it with the variable (by exact PIDs, as before). Not done yet.
2. **Branch code on the VM: done (see [[wiki/syntheses/ray-autoscaler-build-plan]] section 18).** Merged into the VM's working copy (which has its own shim and gate changes), 58 tests pass on the VM; running Ray processes need a restart to load it. Workers get the code through a file mount and the Postgres library through a setup command until the AMI carries both (AMI v4).
3. The `postgres:16` tag will move to new minor versions on a future pull; pin a digest or upgrade deliberately.

## 6. Terminate vs stop (decision pending)
A **stopped** worker keeps its disk (512 GiB, about $1.3/day, estimate) and its warm cache (images, task data); a **terminated** one deletes the disk and starts cold next time (about 86 s to join plus re-pulling images and data). Make the data durable first, measure a cold worker with the 12-task set, then choose.

## 7. Caveats
- **Config hash:** `execution_id` hashes the whole manifest after defaults; adding config keys with defaults (as the stagger and scheduling-strategy keys in our PR branch already do) changes every execution id relative to older runs, so `--resume` across code versions needs care. The Postgres URL deliberately avoids this.
- **Data sensitivity:** artifacts include agent transcripts; keep the database private.
- **Back-ups:** if the head's disk is lost the observations go with it.

## 8. Decisions still open
Blob destination (Postgres bytea now, S3 later); terminate or stop after measuring; keep this on our own branch or propose it upstream later.

## 5e. Status after the first real run (2026-10-30, about 14:20 UTC)
- **Server:** healthy, 5 h 46 min up with 0 restarts, restart policy `always`, 56 MiB of the 4 GiB limit, 1 connection of 200, database 8.4 MB, volume 75 MB, listening on the private address only. The only server-log errors in 6 hours are my own deliberate bad-login tests and shell-quoting slips in my diagnostic queries.
- **Contents:** 30 executions (19 passed, 11 `infra_error`), **78 artifacts** (2.06 MB raw, 0.42 MB gzip, largest 300 KB against the 25 MB cap). Rows by node: head 10, the two workers 6 and 4, never started 10. Passed tasks took 3.5 min (fastest), 8.4 (median), 16.0 (slowest).
- **Completeness checks, all clean:** no passed row without a result JSON, none with fewer than 4 artifacts, no row left `running`, no row with a hostname that never finished; 78 = 19 passed x 4 + 2 for the operator-stopped task. Every result that reached the sink reported `observations_synced: true`.
- **Not fed yet (0 rows):** `usage_events`, `node_metrics`, `budget` (the shim does not write to them and metrics are not streamed).
- **Backups:** only the two manual dumps taken right after setup (before any run data) existed, so the run's data had **no backup**; one was taken at about 14:20 UTC (502 KB) and restored into a scratch database: row counts matched, and a content fingerprint (an md5 over every execution row including its result JSON, and over every artifact's name, SHA-256 and bytes) was **identical** for the original and the restored copy. (My first attempt at the fingerprint comparison was a false pass: a shell-quoting error made both queries fail, both values came back empty and compared equal; it was caught because the output showed the SQL errors, and redone in Python with explicit checks that the values are non-empty.) **Still open:** no scheduled backup (a cron entry in our user's crontab on the head VM) and no copy off the machine; if the VM's disk were lost the observations would go with it.
