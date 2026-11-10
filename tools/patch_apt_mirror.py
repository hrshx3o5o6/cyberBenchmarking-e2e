#!/usr/bin/env python3
"""Optional apt mirror for every container the CyberGym-E2E harness starts, in the style of scripts/patch_cybergym.py.

Why: on 2026-11-10 Canonical's primary archive (archive.ubuntu.com, and to a lesser degree security.ubuntu.com) answered in 17 to 30 seconds per request, from the
host as well as from containers, while the AWS regional mirror answered in 0.1 s. Every task's set-up, agent install and grading starts with apt-get, so the slow archive made tasks
slow and made the standard grader return empty stage results. The regional mirror carries the same packages (all pockets).

Off by default: nothing changes unless CYBERGYM_APT_MIRROR is set (for example us-east-1.ec2.archive.ubuntu.com). When set, start_container rewrites archive.ubuntu.com and
security.ubuntu.com in the container's apt sources (/etc/apt/sources.list and /etc/apt/sources.list.d/*) right after it starts; a failure to rewrite is ignored.
Undo: unset the variable, or `cp scripts/utils.py.pre-aptmirror scripts/utils.py` (the backup this script makes).
usage: patch_apt_mirror.py CYBERGYM_ROOT
"""
from pathlib import Path
import shutil
import sys

MARKER = "CYBERGYM_APT_MIRROR"
OLD = "    result = subprocess.run(cmd, capture_output=True, text=True, check=True)\n    return result.stdout.strip()\n"
NEW = '''    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    container_id = result.stdout.strip()

    # optional apt mirror (tools/patch_apt_mirror.py): unset = apt sources untouched, as before
    mirror = os.environ.get("CYBERGYM_APT_MIRROR")
    if mirror:
        subprocess.run(
            ["docker", "exec", "-u", "root", container_id, "sh", "-c",
             f"sed -i -E 's#//(archive|security)\\\\.ubuntu\\\\.com/#//{mirror}/#g' /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; true"],
            check=False, capture_output=True,
        )
    return container_id
'''


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_apt_mirror.py CYBERGYM_ROOT")
    path = Path(sys.argv[1]) / "scripts" / "utils.py"
    source = path.read_text(encoding="utf-8")
    if MARKER in source:
        print("Apt mirror patch already applied.")
        return
    if source.count(OLD) != 1:
        raise SystemExit("Upstream utils.py structure changed; start_container return not found exactly once; apt mirror patch not applied")
    backup = path.with_name(path.name + ".pre-aptmirror")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(source.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"Applied apt mirror patch (backup: {backup.name}).")


if __name__ == "__main__":
    main()
