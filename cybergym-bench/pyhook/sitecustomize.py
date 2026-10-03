# Loaded via PYTHONPATH by the pilot run only (no edits to the benchmark repo, no /etc/hosts change).
# The harness uses ONE base URL for (a) host-side key management and (b) the agent container.
# The container must use the Docker bridge gateway IP (it is in NO_PROXY); on Docker Desktop for Mac that
# IP is the Linux VM, so host-side code maps it to 127.0.0.1 where the shim listens.
import os, socket
_alias = {a for a in (os.environ.get("CYBERGYM_HOST_ALIAS", "host.docker.internal"), "host.docker.internal") if a}
_orig = socket.getaddrinfo
def _gai(host, *a, **k):
    if host in _alias:
        host = "127.0.0.1"
    return _orig(host, *a, **k)
socket.getaddrinfo = _gai
