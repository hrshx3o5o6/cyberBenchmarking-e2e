#!/usr/bin/env python3
"""Publish every study listed in studies.json with tools/publisher (run on the head, where the databases are).

    python publish_studies.py --dest local:DIR | s3://BUCKET/ [--only SLUG ...] [--publisher ~/publisher/tools/publisher/publish.py]
                              [--state-dir DIR] [--redact FILE]

Per study: the full config hash is found from its prefix, executions that are not final (pending, running) are left out when the entry says
`finals_only`, ids in `exclude_ids` are left out, the notes file is written from `summary` and `notes`, and one --once --all pass is run.
Nothing is read from the manifest except these fields; the publisher sanitises everything it writes."""
import argparse, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL = ("passed", "benchmark_failed", "infra_error")   # statuses that mean a task is over, as the runner records them


def full_hash(env_name, prefix):
    import psycopg
    c = psycopg.connect(os.environ[env_name]).cursor()
    c.execute("select distinct config_hash from executions where config_hash like %s", (prefix + "%",))
    r = [x[0] for x in c.fetchall()]
    if len(r) != 1:
        raise SystemExit("config hash prefix %s matches %d hashes" % (prefix, len(r)))
    return r[0]


def non_final_ids(env_name, h):
    import psycopg
    c = psycopg.connect(os.environ[env_name]).cursor()
    c.execute("select execution_id from executions where config_hash = %s and status <> all(%s)", (h, list(FINAL)))
    return [x[0] for x in c.fetchall()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--manifest", default=os.path.join(HERE, "studies.json"))
    ap.add_argument("--publisher", default=os.path.expanduser("~/publisher/tools/publisher/publish.py"))
    ap.add_argument("--state-dir", default=os.path.expanduser("~/publisher/state-studies"))
    ap.add_argument("--redact")
    ap.add_argument("--analysis-dir", help="folder with analysis-<slug>.json files (per-task analysis keyed by task slug)")
    a = ap.parse_args()
    os.makedirs(a.state_dir, exist_ok=True)
    failed = 0
    for st in json.load(open(a.manifest)):
        if a.only and st["slug"] not in a.only:
            continue
        env = {"cybergym": "CYBERGYM_DATABASE_URL", "exploitgym": "EXPLOITGYM_DATABASE_URL"}[st["benchmark"]]
        h = full_hash(env, st["hash"])
        ex = set(st.get("exclude_ids") or [])
        if st.get("finals_only"):
            ex |= set(non_final_ids(env, h))
        with tempfile.TemporaryDirectory() as td:
            exf, nf = os.path.join(td, "exclude.txt"), os.path.join(td, "notes.json")
            open(exf, "w").write("\n".join(sorted(ex)) + "\n")
            json.dump({"summary": st["summary"], "observations": [{"title": "Note %d" % (i + 1), "body": b} for i, b in enumerate(st.get("notes") or [])]}, open(nf, "w"))
            cmd = [sys.executable, a.publisher, "--benchmark", st["benchmark"], "--study", st["slug"], "--source", "postgres", "--config-hash", h,
                   "--model", st["model"], "--title", st["title"], "--exclude-file", exf, "--notes-file", nf, "--dest", a.dest, "--once", "--all",
                   "--state-file", os.path.join(a.state_dir, "%s.json" % st["slug"])]
            if a.redact:
                cmd += ["--redact-file", a.redact]
            if st.get("analysis") and a.analysis_dir:
                cmd += ["--analysis-file", os.path.join(a.analysis_dir, "analysis-%s.json" % st["slug"])]
            print("== %s (%s): excluding %d executions" % (st["slug"], st["title"], len(ex)), flush=True)
            rc = subprocess.run(cmd).returncode
            if rc:
                failed += 1; print("!! %s exit %d" % (st["slug"], rc), flush=True)
    print("done; %d studies failed" % failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
