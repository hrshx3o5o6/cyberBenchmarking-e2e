#!/bin/bash
# Native x86 Linux variant of run_pilot.sh (Azure VM). No forwarder, no hostname hook.
# The shim binds ONLY to the Docker bridge gateway of cybergym-internal (not the VM's public interface).
#   ./run_linux.sh start-firewall
#   ./run_linux.sh start-mock <task> <mode>                    scripted oracle LLM + shim (free pipeline test)
#   ./run_linux.sh start-shim-openrouter <model> [usd_run=10] [usd_total=15]   needs runs/.openrouter_key (mode 600)
#   ./run_linux.sh run <task> <mode> <model> [timeout=5400]
#   ./run_linux.sh status | stop
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p runs
[ -s runs/.master_key ] || { umask 077; openssl rand -hex 16 > runs/.master_key; }
chmod 600 runs/.master_key
MK=$(cat runs/.master_key)
PORT=4000
gw() { docker network inspect cybergym-internal --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null; }

main() {
case "${1:-}" in
  start-firewall)
    (cd cybergym-e2e/scripts && ../../.venv/bin/python -m firewall start 2>&1 | tail -2)
    echo "gateway: $(gw)" ;;
  start-mock)
    TASK="$2"; MODE="$3"; GW=$(gw); [ -n "$GW" ] || { echo "start the firewall first"; exit 1; }
    pkill -f shim/mock_oracle_llm.py 2>/dev/null || true; pkill -f shim/llm_shim.py 2>/dev/null || true; sleep 1
    PORT=11435 nohup python3 shim/mock_oracle_llm.py "$TASK" "$MODE" > runs/mock.out 2>&1 < /dev/null &
    MASTER_KEY=$MK TARGET_MODEL=oracle UPSTREAM=http://127.0.0.1:11435 BIND=$GW PORT=$PORT LOG_FILE=runs/shim.log \
      nohup python3 shim/llm_shim.py > runs/shim.out 2>&1 < /dev/null &
    sleep 2; cat runs/mock.out runs/shim.out ;;
  start-shim-openrouter)
    MODEL="$2"; USD="${3:-10}"; TOTAL="${4:-15}"; GW=$(gw); [ -n "$GW" ] || { echo "start the firewall first"; exit 1; }
    [ -s runs/.openrouter_key ] || { echo "runs/.openrouter_key missing"; exit 1; }
    [ "$(stat -c %a runs/.openrouter_key)" = "600" ] || { echo "runs/.openrouter_key must be mode 600"; exit 1; }
    PRICES=$(curl -s -m 20 https://openrouter.ai/api/v1/models | MODEL="$MODEL" python3 -c "
import sys,json,os
m=[x for x in json.load(sys.stdin)['data'] if x['id']==os.environ['MODEL']]
if not m: sys.exit('model not found on OpenRouter: '+os.environ['MODEL'])
p=m[0]['pricing']; pin=float(p['prompt'])*1e6; pout=float(p['completion'])*1e6
cache=float(p['input_cache_read'])*1e6 if p.get('input_cache_read') not in (None,'') else pin
print(pin,cache,pout)") || { echo "$PRICES"; exit 1; }
    set -- $PRICES; PIN=$1; PCACHE=$2; POUT=$3
    echo "model=$MODEL USD/M: in=$PIN cache=$PCACHE out=$POUT caps: \$$USD/run \$$TOTAL total"
    pkill -f shim/llm_shim.py 2>/dev/null || true; sleep 1
    MASTER_KEY=$MK TARGET_MODEL="$MODEL" BIND=$GW PORT=$PORT UPSTREAM=https://openrouter.ai/api UPSTREAM_KEY_FILE=runs/.openrouter_key \
      UPSTREAM_AUTH=bearer PRICE_IN_PER_M=$PIN PRICE_CACHE_PER_M=$PCACHE PRICE_OUT_PER_M=$POUT MAX_SPEND_USD=$USD MAX_TOTAL_SPEND_USD=$TOTAL \
      MAX_REQUESTS="${MAX_REQUESTS:-3000}" MAX_INPUT_TOKENS="${MAX_INPUT_TOKENS:-30000000}" MAX_CACHE_TOKENS="${MAX_CACHE_TOKENS:-300000000}" \
      LOG_FILE=runs/shim.log nohup python3 shim/llm_shim.py > runs/shim.out 2>&1 < /dev/null &
    sleep 2; cat runs/shim.out ;;
  run)
    TASK="$2"; MODE="$3"; MODEL="$4"; TO="${5:-5400}"; GW=$(gw)
    [ -n "$GW" ] || { echo "start the firewall first"; exit 1; }
    curl -s -m 5 "http://$GW:$PORT/health" | grep -q '"ok": true' || { echo "shim not answering on $GW:$PORT"; exit 1; }
    export LITELLM_BASE_URL=http://$GW:$PORT LITELLM_MASTER_KEY=$MK
    cd cybergym-e2e
    ../.venv/bin/python scripts/run_agent.py "$TASK" --mode "$MODE" --agent claude-code \
      --model-provider litellm --litellm-model-id "$MODEL" --timeout "$TO" --agent-output ../runs/agent_output ;;
  status)
    GW=$(gw); echo "gateway=$GW"; curl -s -m 5 "http://$GW:$PORT/health" || echo "shim down"; echo
    docker ps --format '{{.Names}} {{.Status}}' ;;
  stop)
    pkill -f shim/llm_shim.py 2>/dev/null || true; pkill -f shim/mock_oracle_llm.py 2>/dev/null || true; echo stopped ;;
  *) sed -n 2,10p "$0"; exit 1 ;;
esac
}
main "$@"
