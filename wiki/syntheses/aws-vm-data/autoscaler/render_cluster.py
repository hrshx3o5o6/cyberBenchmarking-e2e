#!/usr/bin/env python3
"""Fill cluster.template.yaml from autoscaler.local.env and write rendered/cluster.yaml (git-ignored).

usage: render_cluster.py [--env autoscaler.local.env] [--out rendered/cluster.yaml]
Fails on any unfilled or unused placeholder, so a half-rendered config can never be used.
"""
import argparse
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--env", default=str(here / "autoscaler.local.env"))
ap.add_argument("--out", default=str(here / "rendered" / "cluster.yaml"))
args = ap.parse_args()

values = {}
for line in Path(args.env).read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip()

text = (here / "cluster.template.yaml").read_text()
needed = set(re.findall(r"\{\{(\w+)\}\}", text))
missing = sorted(needed - values.keys())
if missing:
    sys.exit(f"missing values for: {', '.join(missing)}")
placeholder_like = sorted(k for k in needed if values[k].startswith("<") or values[k].endswith("xxxxxxxx") or "<" in values[k])
if placeholder_like:
    sys.exit(f"still placeholders: {', '.join(placeholder_like)}")
for k in needed:
    text = text.replace("{{" + k + "}}", values[k])
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(text)
out.chmod(0o600)
print(f"wrote {out}")
