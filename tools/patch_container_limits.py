#!/usr/bin/env python3
"""Optional memory and process limits for every container the CyberGym-E2E harness starts (agent and validation), in the style of scripts/patch_cybergym.py.

Off by default: nothing changes unless the environment variables are set (the nodes' config/.env is where the runner's study sets them):
  CYBERGYM_CONTAINER_MEM_GB=48   -> docker run --memory 48g --memory-swap 48g   (a hard cap, no swap: the kernel kills processes INSIDE the container only)
  CYBERGYM_CONTAINER_PIDS=2048   -> docker run --pids-limit 2048                (extra forks fail instead of growing without bound)
When the memory limit is set, cleanup_container also looks, before it removes a container, at whether the kernel killed anything in it for memory
(cgroup memory.events oom_kill, and Docker's OOMKilled flag) and prints one line `CONTAINER_OOM: <id> oom_kill=<n> OOMKilled=<flag>` into the run's log, so a task
that hit the limit is visible afterwards instead of looking like a model failure.

Undo: unset the variables (no code change needed), or `cp scripts/utils.py.pre-limits scripts/utils.py` (the backup this script makes).
usage: patch_container_limits.py CYBERGYM_ROOT
"""
from pathlib import Path
import shutil
import sys

MARKER = "CYBERGYM_CONTAINER_MEM_GB"

START_OLD = '    cmd = ["docker", "run", "-d", "--rm"]\n'
START_NEW = '''    cmd = ["docker", "run", "-d", "--rm"]

    # optional per-container limits (tools/patch_container_limits.py): unset = no limit, as before
    mem_gb = os.environ.get("CYBERGYM_CONTAINER_MEM_GB")
    if mem_gb:
        cmd.extend(["--memory", f"{mem_gb}g", "--memory-swap", f"{mem_gb}g"])
    pids_limit = os.environ.get("CYBERGYM_CONTAINER_PIDS")
    if pids_limit:
        cmd.extend(["--pids-limit", str(pids_limit)])
'''

CLEAN_OLD = '''def cleanup_container(container_id):
    """Remove a container."""
    if container_id:
        subprocess.run(["docker", "rm", "-f", container_id], check=False, capture_output=True)
'''
CLEAN_NEW = '''def _report_container_oom(container_id):
    """Print one line if the kernel killed something in this container for memory (only used when a memory limit is set)."""
    try:
        info = subprocess.run(["docker", "inspect", "-f", "{{.Id}} {{.State.OOMKilled}}", container_id], capture_output=True, text=True, timeout=30).stdout.split()
        if len(info) != 2:
            return
        full_id, flag = info
        kills = 0
        for path in (f"/sys/fs/cgroup/system.slice/docker-{full_id}.scope/memory.events", f"/sys/fs/cgroup/docker/{full_id}/memory.events"):
            if os.path.exists(path):
                for line in open(path).read().splitlines():
                    if line.startswith("oom_kill "):
                        kills = int(line.split()[1])
                break
        if kills > 0 or flag == "true":
            print(f"  CONTAINER_OOM: {container_id[:12]} oom_kill={kills} OOMKilled={flag}")
    except Exception:
        pass


def cleanup_container(container_id):
    """Remove a container."""
    if container_id:
        if os.environ.get("CYBERGYM_CONTAINER_MEM_GB"):
            _report_container_oom(container_id)
        subprocess.run(["docker", "rm", "-f", container_id], check=False, capture_output=True)
'''


def replace_once(source: str, needle: str, replacement: str, error: str) -> str:
    if source.count(needle) != 1:
        raise SystemExit(error)
    return source.replace(needle, replacement, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_container_limits.py CYBERGYM_ROOT")
    path = Path(sys.argv[1]) / "scripts" / "utils.py"
    source = path.read_text(encoding="utf-8")
    if MARKER in source:
        print("Container limits patch already applied.")
        return
    backup = path.with_name(path.name + ".pre-limits")
    if not backup.exists():
        shutil.copy2(path, backup)
    source = replace_once(source, START_OLD, START_NEW, "Upstream utils.py structure changed; start_container not found exactly once; limits patch not applied")
    source = replace_once(source, CLEAN_OLD, CLEAN_NEW, "Upstream utils.py structure changed; cleanup_container not found exactly once; limits patch not applied")
    path.write_text(source, encoding="utf-8")
    print(f"Applied container limits patch (backup: {backup.name}).")


if __name__ == "__main__":
    main()
