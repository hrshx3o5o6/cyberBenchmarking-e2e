#!/usr/bin/env bash
# Start the metering shim on THIS node for a model reference from the registry (for example kimi-k3@bedrock).
# Unlike start_worker_services.sh (Bedrock written into the script), the provider, endpoint, API format, key source and prices
# all come from tools/models.toml through tools/model_registry.py. Idempotent: does nothing if a shim already answers.
# The shim's master key and the provider key come from the node's own config/.env (sourced in a subshell, never printed).
#
# usage: start_shim.sh <model-ref> <total-spend-cap-usd | tokens> [per-key-cap-usd]
#   a model with a price:      start_shim.sh kimi-k3@bedrock 20 10
#   a model with no price:     start_shim.sh qwen3.8-27b@vertex-endpoint tokens
#                              (no dollars are tracked, cost shows as 0; per-key caps on requests and tokens use the registry module's
#                               defaults, or set TOKEN_MAX_REQUESTS, TOKEN_MAX_INPUT and TOKEN_MAX_CACHE to override)
# env (optional): TOTAL_START (spend already used, carried into a restarted shim), PORT (default 4100), REGISTRY, BE (runner dir),
#                 PYTHON, GATEWAY (default: the Docker gateway of the cybergym-internal network), DRY_RUN=1 (print the settings, start nothing)
set -euo pipefail
REF="${1:?model reference, e.g. kimi-k3@bedrock}"; TOTAL="${2:?total spend cap in USD, or the word tokens}"; PERKEY="${3:-10}"
BE="${BE:-$HOME/benchmark-evals}"; ENVF="$BE/config/.env"; PY="${PYTHON:-$BE/.venv/bin/python}"
REGISTRY="${REGISTRY:-$BE/tools/models.toml}"; PORT="${PORT:-4100}"
get() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2-; }

GW="${GATEWAY:-$(docker network inspect cybergym-internal --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)}"
[ -n "$GW" ] || { echo "the cybergym-internal docker network does not exist on this node" >&2; exit 1; }
if [ -z "${DRY_RUN:-}" ] && curl -fs -m 3 "http://$GW:$PORT/health" >/dev/null; then echo "shim already answering on $GW:$PORT"; exit 0; fi

MASTER="$(get SHIM_MASTER_KEY)"
[ -n "$MASTER" ] || { echo "SHIM_MASTER_KEY is missing from $ENVF" >&2; exit 1; }

if [ "$TOTAL" = "tokens" ]; then
  CAPS=()
  [ -z "${TOKEN_MAX_REQUESTS:-}" ] || CAPS+=(--max-requests "$TOKEN_MAX_REQUESTS")
  [ -z "${TOKEN_MAX_INPUT:-}" ] || CAPS+=(--max-input-tokens "$TOKEN_MAX_INPUT")
  [ -z "${TOKEN_MAX_CACHE:-}" ] || CAPS+=(--max-cache-tokens "$TOKEN_MAX_CACHE")
else
  CAPS=(--per-key-usd "$PERKEY" --total-usd "$TOTAL")
  [ -z "${TOTAL_START:-}" ] || CAPS+=(--total-start "$TOTAL_START")
fi

# the provider key stays in this subshell's environment; the settings printed below name it but never contain it
exports="$("$PY" "$BE/tools/model_registry.py" env "$REF" --registry "$REGISTRY" ${CAPS[@]+"${CAPS[@]}"})"
if [ -n "${DRY_RUN:-}" ]; then
  echo "would start the shim for $REF on $GW:$PORT with:"; echo "$exports"; exit 0
fi
mkdir -p "$HOME/cybergym-work"; cd "$BE"
(
  set -a; . "$ENVF"; set +a
  eval "$exports"
  export MASTER_KEY="$MASTER" PORT="$PORT" BIND="$GW" LOG_FILE="$HOME/cybergym-work/shim.log"
  exec nohup setsid "$PY" "$BE/tools/llm_shim_new.py" > "$HOME/cybergym-work/shim.out" 2>&1 < /dev/null
) &
for _ in $(seq 1 40); do
  if curl -fs -m 2 "http://$GW:$PORT/health" >/dev/null; then echo "shim started for $REF on $GW:$PORT"; exit 0; fi
  sleep 0.5
done
echo "shim did not come up; see $HOME/cybergym-work/shim.out" >&2; tail -n 5 "$HOME/cybergym-work/shim.out" >&2; exit 1
