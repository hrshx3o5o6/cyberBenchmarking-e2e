#!/usr/bin/env python3
"""TEMPORARY Mac-side token refresher: keeps a fresh one-hour Google access token in a file on the head VM.

Runs on the Mac, where the Google login lives. The login never leaves the Mac; only one-hour tokens are written to the VM, through ssh's standard
input (so a token never appears on a command line or in output), atomically (written to a temporary name, then moved into place). Delete this when
a service account or workload identity federation replaces the token path.

  push_vertex_token.py --host harshav@<head public ip> [--key ~/.ssh/id_ed25519] [--file '$HOME/.secrets/vertex_token'] [--interval 1800]
                       [--once] [--check] [--keep] [--no-caffeinate]
  --check  verify that a token can be fetched and the VM answers over ssh; push nothing
  --once   push one token and exit (0 on success)
  --keep   do not delete the remote file on exit (by default it is deleted when the script stops)
Environment (mostly for tests): TOKEN_CMD (default: gcloud auth application-default print-access-token), SSH_CMD (default: ssh), RETRY_WAITS
(seconds between the attempts of one push, default 5,15), FAIL_RETRY (seconds before trying again after a failed cycle, default 120), STATUS_FILE,
NO_NOTIFY=1 (no macOS notification).
A token lasts about 60 minutes; the default interval is 30 minutes, so a missed push is still covered. If pushes keep failing, the script says so
loudly (stderr, a macOS notification and the status file) and keeps trying; if the Google login has expired it tells you to log in again.
Keep the Mac awake and online while a run depends on it (caffeinate is started automatically on macOS; a closed lid still sleeps the Mac).
"""
import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time

STOP = {"flag": False}
FILE_RE = re.compile(r"^[A-Za-z0-9_./$~-]+$")


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def say(msg):
    print("[%s] %s" % (now(), msg), file=sys.stderr, flush=True)


def notify(msg):
    say("ATTENTION: " + msg)
    if os.environ.get("NO_NOTIFY") != "1" and shutil.which("osascript"):
        subprocess.run(["osascript", "-e", 'display notification "%s" with title "Vertex token refresher"' % msg.replace('"', "'")[:180]], capture_output=True)


def remote_path(path):
    if not FILE_RE.match(path):
        sys.exit("--file may only contain letters, digits and _ . / $ ~ -")
    return path.replace("~/", "$HOME/", 1) if path.startswith("~/") else path


def get_token():
    """(token, error). The token is never printed."""
    cmd = shlex.split(os.environ.get("TOKEN_CMD", "gcloud auth application-default print-access-token"))
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, "could not run the token command (%s)" % type(e).__name__
    text = r.stdout.strip()
    err = (r.stderr or "").strip()
    if "eauth" in err:
        return None, "the Google login has expired: run  gcloud auth application-default login"
    if r.returncode != 0:
        return None, "the token command failed (exit %d): %s" % (r.returncode, err[:160].replace(text, "<token>") if text else err[:160])
    if not text:
        return None, "the token command printed nothing"
    if len(text) < 20 or any(c.isspace() for c in text):
        return None, "the token command returned something that does not look like a token"
    return text, None


def ssh_base(host, key):
    base = shlex.split(os.environ.get("SSH_CMD", "ssh"))
    if key:
        base += ["-i", os.path.expanduser(key)]
    return base + ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=15", host]


def run_remote(host, key, command, data=None):
    try:
        r = subprocess.run(ssh_base(host, key) + [command], input=data, capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 255, type(e).__name__
    return r.returncode, r.stderr.decode(errors="replace")[:200]


def push_once(host, key, rfile, waits):
    token, err = get_token()
    if err:
        return False, err
    d = rfile.rsplit("/", 1)[0]
    cmd = 'umask 077; mkdir -p "%s" && cat > "%s.tmp" && mv -f "%s.tmp" "%s" && test -s "%s"' % (d, rfile, rfile, rfile, rfile)
    last = ""
    for i in range(len(waits) + 1):
        code, last = run_remote(host, key, cmd, token.encode())
        if code == 0:
            return True, ""
        if i < len(waits):
            time.sleep(waits[i])
    return False, "the push over ssh failed: " + last.replace(token, "<token>").strip()


def write_status(path, **kw):
    try:
        with open(path, "w") as f:
            json.dump(kw, f)
    except OSError:
        pass


def main():
    ap = argparse.ArgumentParser(description="Keep a fresh one-hour Google access token on the head VM.")
    ap.add_argument("--host", required=True, help="user@address of the head VM")
    ap.add_argument("--key", default=None, help="ssh identity file")
    ap.add_argument("--file", default="~/.secrets/vertex_token", help="token file on the VM")
    ap.add_argument("--interval", type=float, default=1800.0, help="seconds between pushes (default 1800)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--no-caffeinate", action="store_true")
    a = ap.parse_args()
    rfile = remote_path(a.file)
    waits = [float(x) for x in os.environ.get("RETRY_WAITS", "5,15").split(",") if x]
    fail_retry = float(os.environ.get("FAIL_RETRY", "120"))
    status = os.environ.get("STATUS_FILE", os.path.expanduser("~/.vertex_token_refresher.json"))

    if a.check:
        token, err = get_token()
        code, e2 = run_remote(a.host, a.key, "true")
        say("token: %s | ssh: %s" % ("ok" if token else "FAILED (%s)" % err, "ok" if code == 0 else "FAILED (%s)" % e2))
        return 0 if token and code == 0 else 1
    if a.once:
        ok, err = push_once(a.host, a.key, rfile, waits)
        say("pushed a fresh token" if ok else "FAILED: " + err)
        return 0 if ok else 1

    if sys.platform == "darwin" and not a.no_caffeinate and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())])
    signal.signal(signal.SIGTERM, lambda *_: STOP.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: STOP.update(flag=True))
    last_ok, last_notified = None, 0.0
    say("refreshing the token on %s every %d s (file %s); Ctrl-C to stop" % (a.host, a.interval, a.file))
    while not STOP["flag"]:
        ok, err = push_once(a.host, a.key, rfile, waits)
        if ok:
            last_ok = time.time()
            write_status(status, last_success=now(), last_error=None)
            say("pushed a fresh token")
            wait = a.interval
        else:
            write_status(status, last_success=datetime.datetime.fromtimestamp(last_ok).isoformat(timespec="seconds") if last_ok else None, last_error=err, at=now())
            age = (time.time() - last_ok) / 60 if last_ok else None
            if time.time() - last_notified > 300:
                notify("%s%s" % (err, " (the token on the VM is %d minutes old and expires at 60)" % age if age is not None else " (no token has been pushed yet)"))
                last_notified = time.time()
            wait = fail_retry
        end = time.time() + wait
        while not STOP["flag"] and time.time() < end:
            time.sleep(0.2)
    if not a.keep:
        code, _ = run_remote(a.host, a.key, 'rm -f "%s" "%s.tmp"' % (rfile, rfile))
        say("stopped; token file %s" % ("deleted on the VM" if code == 0 else "could NOT be deleted: remove it by hand"))
    else:
        say("stopped; token file kept on the VM")
    return 0


if __name__ == "__main__":
    sys.exit(main())
