#!/usr/bin/env python3
"""Turn the rendered cluster.yaml into the file the autoscaler on a hand-started head needs.

`ray up` fills in Ray's defaults before it ships the config to the head; a head started by hand does not,
and the monitor then dies with KeyError: 'cluster_synced_files'. This applies Ray's own prepare_config
(offline, no AWS calls) and validates the result.

usage (on the head, with the Ray venv):  prepare_cluster.py [rendered/cluster.yaml [rendered/cluster.prepared.yaml]]
"""
import copy
import os
import sys

import yaml
from ray.autoscaler._private.util import prepare_config, validate_config

src = sys.argv[1] if len(sys.argv) > 1 else "rendered/cluster.yaml"
dst = sys.argv[2] if len(sys.argv) > 2 else "rendered/cluster.prepared.yaml"
config = prepare_config(copy.deepcopy(yaml.safe_load(open(src))))
validate_config(config)
os.umask(0o077)
with open(dst, "w") as out:
    yaml.safe_dump(config, out, sort_keys=False)
print(f"wrote {dst} (cluster_synced_files present: {'cluster_synced_files' in config})")
