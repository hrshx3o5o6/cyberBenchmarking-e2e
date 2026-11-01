#!/usr/bin/env bash
# Start the metering shim on THIS node, bound to the Docker gateway of the internal network (the address is the same
# on every node because the AMI creates the network the same way). Idempotent: does nothing if a shim already answers.
# The master key is read from the .env the autoscaler copied in; the upstream credential from .bedrock_key. Prints no secrets.
#
# usage: start_worker_services.sh <target-model> <total-spend-cap-usd> [per-key-cap-usd]
# env (optional): PRICE_IN_PER_M PRICE_CACHE_PER_M PRICE_OUT_PER_M (defaults are Kimi K3 on Bedrock, US tier)
#   TOTAL_START  spend already used, carried into a restarted shim so its total cap keeps counting (default: none)
set -euo pipefail
MODEL="${1:?target model}"; TOTAL="${2:?total spend cap in USD}"; PERKEY="${3:-10}"
BE="$HOME/benchmark-evals"; ENVF="$BE/config/.env"
get() { grep -E "^$1=" "$ENVF" | head -1 | cut -d= -f2-; }

GW="$(docker network inspect cybergym-internal --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null || true)"
[ -n "$GW" ] || { echo "the cybergym-internal docker network does not exist on this node" >&2; exit 1; }
if curl -fs -m 3 "http://$GW:4100/health" >/dev/null; then echo "shim already answering on $GW:4100"; exit 0; fi

MASTER="$(get SHIM_MASTER_KEY)"
[ -n "$MASTER" ] || { echo "SHIM_MASTER_KEY is missing from $ENVF" >&2; exit 1; }
[ -s "$BE/config/.bedrock_key" ] || { echo "$BE/config/.bedrock_key is missing" >&2; exit 1; }
mkdir -p "$HOME/cybergym-work"; cd "$BE"
env MASTER_KEY="$MASTER" UPSTREAM="https://bedrock-runtime.us-east-1.amazonaws.com/openai" TARGET_MODEL="$MODEL" \
    UPSTREAM_KEY_FILE="$BE/config/.bedrock_key" UPSTREAM_AUTH=bearer UPSTREAM_SERIAL=0 \
    PRICE_IN_PER_M="${PRICE_IN_PER_M:-3.30}" PRICE_CACHE_PER_M="${PRICE_CACHE_PER_M:-0.33}" PRICE_OUT_PER_M="${PRICE_OUT_PER_M:-16.50}" \
    MAX_SPEND_USD="$PERKEY" MAX_TOTAL_SPEND_USD="$TOTAL" MAX_REQUESTS=5000 MAX_INPUT_TOKENS=40000000 MAX_CACHE_TOKENS=400000000 \
    UPSTREAM_TIMEOUT_STREAM=600 UPSTREAM_TIMEOUT=600 PORT=4100 BIND="$GW" LOG_FILE="$HOME/cybergym-work/shim.log" \
    ${TOTAL_START:+TOTAL_START="$TOTAL_START"} \
    nohup setsid "$BE/.venv/bin/python" "$BE/tools/llm_shim_new.py" > "$HOME/cybergym-work/shim.out" 2>&1 < /dev/null &
for _ in $(seq 1 40); do
  if curl -fs -m 2 "http://$GW:4100/health" >/dev/null; then echo "shim started on $GW:4100 (total cap $TOTAL USD, per key $PERKEY USD)"; exit 0; fi
  sleep 0.5
done
echo "the shim did not come up; last output:" >&2; tail -5 "$HOME/cybergym-work/shim.out" >&2; exit 1
