#!/bin/bash
# Usage: ./run_pilot.sh start-shim <ollama-model>      e.g. gpt-oss:120b-cloud
#        ./run_pilot.sh start-shim-openrouter <model-id> [usd_per_run] [usd_total] [--dry]   e.g. z-ai/glm-5.3-flash 2
#        ./run_pilot.sh run <task> <patch-only|e2e> <ollama-model> [timeout_sec]
# Local master key lives in runs/.master_key (random, protects the shim only; not a provider secret).
set -euo pipefail
cd "$(dirname "$0")"
MK=$(cat runs/.master_key)
# whole script is parsed before running, so editing it mid-run cannot break a running instance
main() {
case "${1:-}" in
  start-shim)
    pkill -f shim/llm_shim.py 2>/dev/null || true; sleep 1
    MASTER_KEY=$MK TARGET_MODEL="$2" PORT=80 MAX_REQUESTS="${MAX_REQUESTS:-300}" MAX_INPUT_TOKENS="${MAX_INPUT_TOKENS:-3000000}" MAX_CACHE_TOKENS="${MAX_CACHE_TOKENS:-30000000}" \
      nohup python3 shim/llm_shim.py > runs/shim.out 2>&1 &
    sleep 2; cat runs/shim.out ;;
  start-shim-openrouter)
    # ./run_pilot.sh start-shim-openrouter <openrouter-model-id> [max_usd_per_run=2] [max_usd_total=3x] [--dry]
    MODEL="$2"; USD="${3:-2}"; TOTAL="${4:-$(python3 -c "print($USD*3)")}"; DRY="${5:-}"
    [ -s runs/.openrouter_key ] || { echo "runs/.openrouter_key missing (pbpaste > runs/.openrouter_key && chmod 600 ...)"; exit 1; }
    [ "$(stat -f %Lp runs/.openrouter_key)" = "600" ] || { echo "runs/.openrouter_key must be mode 600"; exit 1; }
    PRICES=$(curl -s -m 20 https://openrouter.ai/api/v1/models | MODEL="$MODEL" python3 -c "
import sys,json,os
m=[x for x in json.load(sys.stdin)['data'] if x['id']==os.environ['MODEL']]
if not m: sys.exit('model not found on OpenRouter: '+os.environ['MODEL'])
p=m[0]['pricing']; pin=float(p['prompt'])*1e6; pout=float(p['completion'])*1e6
cache=float(p['input_cache_read'])*1e6 if p.get('input_cache_read') not in (None,'') else pin   # no discount known -> assume full price (conservative)
print(pin,cache,pout)") || { echo "$PRICES"; exit 1; }
    set -- $PRICES; PIN=$1; PCACHE=$2; POUT=$3
    echo "model=$MODEL  USD/M tokens: in=$PIN cache-read=$PCACHE out=$POUT  caps: \$$USD per run, \$$TOTAL total"
    [ "$DRY" = "--dry" ] && exit 0
    pkill -f shim/llm_shim.py 2>/dev/null || true; sleep 1
    MASTER_KEY=$MK TARGET_MODEL="$MODEL" PORT=80 UPSTREAM=https://openrouter.ai/api UPSTREAM_KEY_FILE=runs/.openrouter_key UPSTREAM_AUTH=bearer \
      PRICE_IN_PER_M=$PIN PRICE_CACHE_PER_M=$PCACHE PRICE_OUT_PER_M=$POUT MAX_SPEND_USD=$USD MAX_TOTAL_SPEND_USD=$TOTAL \
      MAX_REQUESTS="${MAX_REQUESTS:-3000}" MAX_INPUT_TOKENS="${MAX_INPUT_TOKENS:-30000000}" MAX_CACHE_TOKENS="${MAX_CACHE_TOKENS:-300000000}" \
      STRIP_FIELDS="${STRIP_FIELDS:-}" nohup python3 shim/llm_shim.py > runs/shim.out 2>&1 &
    sleep 2; cat runs/shim.out ;;
  run)
    TASK="$2"; MODE="$3"; MODEL="$4"; TO="${5:-5400}"   # paper protocol: 90 min per task
    GW=$(docker network inspect cybergym-internal --format '{{(index .IPAM.Config 0).Gateway}}')
    docker ps --format '{{.Names}}' | grep -q '^cybergym-fwd$' || { echo 'forwarder cybergym-fwd not running (see NOTES.md)'; exit 1; }
    export LITELLM_BASE_URL=http://$GW LITELLM_MASTER_KEY=$MK CYBERGYM_HOST_ALIAS=$GW
    export PYTHONPATH="$PWD/pyhook${PYTHONPATH:+:$PYTHONPATH}"
    cd cybergym-e2e
    ../.venv/bin/python scripts/run_agent.py "$TASK" --mode "$MODE" --agent claude-code \
      --model-provider litellm --litellm-model-id "$MODEL" --timeout "$TO" \
      --agent-output ../runs/agent_output ;;
  *) echo "see header"; exit 1 ;;
esac
}
main "$@"
exit $?
