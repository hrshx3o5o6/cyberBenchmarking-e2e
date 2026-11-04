#!/usr/bin/env python3
"""Download ONLY the task data (source archive, PoC, crash log) that a manifest's tasks need, and optionally prefetch their images.

The runner's `prepare` also pulls every task image and touches the firewall. On an autoscaled worker that is wrong for a large manifest: the harness
starts each container with `docker run`, which pulls a missing image by itself the first time a node needs it. This script is the data half of `prepare`,
and with --images-only the image half, in the order the manifest lists the tasks, so a fresh worker's first tasks do not all wait on their own pulls.

usage: fetch_task_data.py <manifest.json> [--images-only [--parallel N] [--min-free-gb G]]      (run inside the runner's environment)
  (no flag)      download task data; the Hugging Face token comes from the manifest's env file; exits 1 and lists tasks whose data is still incomplete
  --images-only  pull the images of the tasks already downloaded, in manifest order, N at a time (default 3), skipping images already on the node and
                 stopping when the disk has less than G GB free (default 150) so tasks still have room to run; a failed pull is reported and left to
                 `docker run`, which pulls on demand; always exits 0 unless the arguments are wrong
"""
import shutil
import subprocess
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

NEEDED = ("src.tgz", "poc.bin", "crash.log")
REPO = "sunblaze-ucb/cybergym-e2e"
DEFAULT_IMAGE = "gcr.io/oss-fuzz-base/base-builder@sha256:8eda74a11e800aead5a041ee479a65b33dab3150d6e89e5694e2b6eb27be98fc"      # as in cybergym_eval/prepare.py


def image_for_task(root, task):
    """The build image a task runs in: the task's config over its project's, else the shared base image (same rule as the runner's prepare)."""
    task_dir = Path(root) / "projects" / task
    merged = tomllib.loads((task_dir.parent / "project.toml").read_text())
    merged.update(tomllib.loads((task_dir / "config.toml").read_text()))
    return merged.get("build_image", DEFAULT_IMAGE)


def _docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True).returncode


def prefetch_images(images, parallel=3, min_free_gb=150, docker=_docker, free_gb=None, out=print):
    """Pull `images` (already in the order they are needed). Returns (pulled, skipped, failed, stopped_for_disk)."""
    if free_gb is None:
        free_gb = lambda: shutil.disk_usage("/var/lib/docker" if Path("/var/lib/docker").exists() else "/").free / 1e9
    pulled, skipped, failed, stopped = [], [], [], []

    def one(image):
        if free_gb() < min_free_gb:
            stopped.append(image)
            return
        if docker("image", "inspect", image) == 0:
            skipped.append(image)
            return
        for attempt in (1, 2):
            if docker("pull", "-q", image) == 0:
                pulled.append(image)
                out(f"pulled {image}")
                return
        failed.append(image)
        out(f"FAILED to pull {image} (left to docker run)")

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        list(pool.map(one, images))
    out(f"images: {len(pulled)} pulled, {len(skipped)} already present, {len(failed)} failed, {len(stopped)} not tried (less than {min_free_gb} GB free)")
    return pulled, skipped, failed, stopped


def _parse(argv):
    opts = {"images_only": False, "parallel": 3, "min_free_gb": 150.0}
    rest, it = [], iter(argv)
    for a in it:
        if a == "--images-only":
            opts["images_only"] = True
        elif a in ("--parallel", "--min-free-gb"):
            opts[a[2:].replace("-", "_")] = float(next(it, "x")) if a == "--min-free-gb" else int(next(it, "x"))
        else:
            rest.append(a)
    return (rest[0] if len(rest) == 1 else None), opts


def main(argv, download=None, load_config=None, prefetch=None):
    try:
        manifest, opts = _parse(argv)
    except ValueError:
        manifest = None
    if manifest is None:
        print("usage: fetch_task_data.py <manifest.json> [--images-only [--parallel N] [--min-free-gb G]]", file=sys.stderr)
        return 2
    if load_config is None:
        from cybergym_eval.config import load_config
    config = load_config(Path(manifest))
    root = Path(config["benchmark_root"]) / "data"
    tasks = list(config["tasks"])
    if opts["images_only"]:
        images, seen = [], set()
        for t in tasks:
            if (Path(config["benchmark_root"]) / "projects" / t / "config.toml").is_file():       # task configs live beside data/, as the runner's prepare reads them
                im = image_for_task(config["benchmark_root"], t)
                if im not in seen:
                    seen.add(im)
                    images.append(im)
        print(f"Prefetching {len(images)} image(s) for {len(tasks)} task(s) ...", flush=True)
        (prefetch or prefetch_images)(images, opts["parallel"], opts["min_free_gb"])
        return 0
    if download is None:
        from huggingface_hub import snapshot_download as download
    print(f"Downloading data for {len(tasks)} task(s) into {root} ...", flush=True)
    download(repo_id=REPO, repo_type="dataset", local_dir=root, allow_patterns=[f"projects/{t}/**" for t in tasks])
    missing = [t for t in tasks if not all((root / "projects" / t / f).is_file() for f in NEEDED)]
    if missing:
        print(f"INCOMPLETE data for {len(missing)} task(s): {', '.join(missing[:10])}{' ...' if len(missing) > 10 else ''}", file=sys.stderr)
        return 1
    print("Task data complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
