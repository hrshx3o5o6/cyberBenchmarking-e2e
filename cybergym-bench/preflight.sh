#!/bin/bash
# Pre-run checklist: verifies every moving part and tells you what to fix. No LLM calls, no spend.
# Usage: ./preflight.sh <project/task> [provider]      provider: ollama (default) | openrouter | mock
# Exit 0 = ready, 1 = something missing.
cd "$(dirname "$0")"
TASK="${1:-hunspell/arvo_52195}"; PROVIDER="${2:-ollama}"
FAIL=0
ok()   { printf "  \033[32mOK\033[0m   %s\n" "$1"; }
bad()  { printf "  \033[31mFAIL\033[0m %s\n         fix: %s\n" "$1" "$2"; FAIL=1; }
warn() { printf "  \033[33mWARN\033[0m %s\n" "$1"; }
echo "preflight: task=$TASK provider=$PROVIDER"

echo "[docker]"
if docker info >/dev/null 2>&1; then ok "daemon up"; else bad "docker daemon not reachable" "start Docker Desktop"; fi
MEM=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
[ "$MEM" -ge 10000000000 ] && ok "VM memory $((MEM/1073741824)) GB" || bad "VM memory $((MEM/1073741824)) GB (<10)" "Docker Desktop > Settings > Resources > Memory >= 12 GB"
RND=$(docker run --rm --privileged --pid=host alpine nsenter -t 1 -m -u -n -i sysctl -n vm.mmap_rnd_bits 2>/dev/null)
[ "$RND" = "28" ] && ok "vm.mmap_rnd_bits=28" || bad "vm.mmap_rnd_bits='$RND' (resets when the Docker VM restarts)" "docker run --rm --privileged --pid=host alpine nsenter -t 1 -m -u -n -i sysctl -w vm.mmap_rnd_bits=28"
docker image inspect "$(grep -h build_image cybergym-e2e/projects/${TASK%%/*}/project.toml | head -1 | sed 's/.*= *"\(.*\)"/\1/')" >/dev/null 2>&1 \
  && ok "build image present" || bad "build image for $TASK not pulled" "docker pull --platform linux/amd64 <digest from projects/${TASK%%/*}/project.toml>"
DISK=$(df -g / | awk 'NR==2{print $4}'); [ "${DISK:-0}" -ge 30 ] && ok "free disk ${DISK} GB" || bad "free disk ${DISK} GB (<30)" "free some space"
STALE=$(docker ps --format '{{.Names}}' | grep -c '^claude-code-')
[ "$STALE" -eq 0 ] && ok "no stale agent containers" || warn "$STALE agent container(s) still running (a run in progress, or leftovers: docker rm -f \$(docker ps -q --filter name=claude-code-))"

echo "[network path: container -> gateway -> forwarder -> shim]"
docker ps --format '{{.Names}}' | grep -q '^cybergym-proxy$' && ok "firewall proxy running" || bad "firewall proxy not running" "cd cybergym-e2e/scripts && ../../.venv/bin/python -m firewall start"
GW=$(docker network inspect cybergym-internal --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null)
[ -n "$GW" ] && ok "internal network gateway $GW" || bad "network cybergym-internal missing" "start the firewall (above)"
docker ps --format '{{.Names}}' | grep -q '^cybergym-fwd$' && ok "forwarder cybergym-fwd running" || bad "forwarder cybergym-fwd not running" "docker run -d --name cybergym-fwd --network host --restart unless-stopped alpine/socat TCP-LISTEN:80,fork,reuseaddr TCP:host.docker.internal:80"
HEALTH=$(curl -s -m 5 localhost/health)
if echo "$HEALTH" | grep -q '"ok": true'; then
  ok "shim up: $(echo "$HEALTH" | python3 -c "import sys,json;d=json.load(sys.stdin);print('target=%s upstream=%s auth=%s usd_cap=%s'%(d['target'],d['upstream'],d.get('auth'),d.get('usd_cap_per_key')))")"
else bad "shim not answering on :80" "./run_pilot.sh start-shim <model>"; fi
if [ -n "$GW" ]; then
  R=$(docker run --rm --network cybergym-internal curlimages/curl -s -m 8 "http://$GW/health" 2>/dev/null)
  echo "$R" | grep -q '"ok": true' && ok "container -> $GW -> shim reachable (no proxy)" || bad "container cannot reach shim via gateway" "check forwarder + shim (above)"
  B=$(docker run --rm --network cybergym-internal -e HTTP_PROXY=http://cybergym-proxy:3128 curlimages/curl -s -m 8 -o /dev/null -w '%{http_code}' http://example.com/ 2>/dev/null)
  [ "$B" = "000" ] || [ "$B" = "403" ] && ok "firewall blocks the open internet (example.com -> $B)" || bad "example.com reachable from agent network (HTTP $B)" "restart firewall; do not run with network access"
fi
[ -f runs/.master_key ] && [ "$(stat -f %Lp runs/.master_key)" = "600" ] && ok "master key file (mode 600)" || bad "runs/.master_key missing or not mode 600" "openssl rand -hex 16 > runs/.master_key && chmod 600 runs/.master_key"
python3 - <<'E' >/dev/null 2>&1 && ok "host-side hook resolves the gateway alias" || bad "pyhook/sitecustomize.py missing or broken" "restore cybergym-bench/pyhook/sitecustomize.py"
import importlib.util,os,socket
os.environ["CYBERGYM_HOST_ALIAS"]="172.20.0.1"
s=importlib.util.spec_from_file_location("cg_hook",os.path.join(os.getcwd(),"pyhook","sitecustomize.py")); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
assert socket.getaddrinfo("172.20.0.1",80)[0][4][0]=="127.0.0.1" and socket.getaddrinfo("host.docker.internal",80)[0][4][0]=="127.0.0.1"
E

echo "[task data]"
D=cybergym-e2e/data/projects/$TASK
for f in src.tgz poc.bin crash.log; do [ -s "$D/$f" ] && ok "$f" || bad "$D/$f missing" "hf snapshot_download allow_patterns=projects/$TASK/* (dataset is gated: request access first)"; done
[ -d cybergym-e2e/projects/$TASK ] && ok "task scripts present" || bad "projects/$TASK missing" "git -C cybergym-e2e pull"
ARCH=$(grep -h 'ARCHITECTURE=' cybergym-e2e/projects/$TASK/run_poc.sh 2>/dev/null | head -1 | cut -d= -f2)
SAN=$(grep -h 'SANITIZER=' cybergym-e2e/projects/$TASK/run_poc.sh 2>/dev/null | head -1 | cut -d= -f2)
[ "$ARCH" = "x86_64" ] && ok "arch x86_64" || warn "arch=$ARCH (i386 builds are riskier under emulation)"
[ "$SAN" = "address" ] && ok "sanitizer address" || warn "sanitizer=$SAN (MemorySanitizer likely fails under emulation)"
ls runs/gate_*"${TASK##*_}"*.log >/dev/null 2>&1 && ok "ground-truth gate was run for this task" || warn "no ground-truth gate log for $TASK: run scripts/dataset_validate.py first (free)"

echo "[provider: $PROVIDER]"
case "$PROVIDER" in
  ollama)
    curl -s -m 5 localhost:11434/api/tags >/dev/null && ok "ollama server up" || bad "ollama not running" "open the Ollama app or: ollama serve" ;;
  openrouter)
    [ -s runs/.openrouter_key ] && [ "$(stat -f %Lp runs/.openrouter_key)" = "600" ] && ok "runs/.openrouter_key present (mode 600, not printed)" \
      || bad "runs/.openrouter_key missing or not mode 600" "copy the key, then: pbpaste > runs/.openrouter_key && chmod 600 runs/.openrouter_key"
    echo "$HEALTH" | grep -q 'openrouter.ai' && ok "shim is pointed at OpenRouter" || bad "shim is not pointed at OpenRouter" "./run_pilot.sh start-shim-openrouter <model>"
    echo "$HEALTH" | grep -Eq '"usd_cap_per_key": [0-9]' && ok "USD cap active" || bad "no USD cap on the shim" "start via start-shim-openrouter (refuses to start uncapped)" ;;
  mock) ok "mock provider (no external dependency)" ;;
esac
git -C cybergym-e2e diff --quiet && ok "benchmark repo unmodified" || warn "cybergym-e2e has local modifications (breaks 'no edits to the benchmark')"

echo
[ $FAIL -eq 0 ] && { echo "READY"; exit 0; } || { echo "NOT READY (fix the FAIL lines above)"; exit 1; }
