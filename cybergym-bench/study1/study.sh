#!/bin/bash
# Study 1 runner (our tooling; the benchmark repo is untouched). Run on the VM; works from any cwd.
#   study.sh shim-start <model> <port> <provider_order|-> <usd_per_run> <usd_total>
#   study.sh vidoc-shim-start <port> <cap_per_run_Mtok> <cap_total_Mtok>
#   study.sh shim-stop <port>|all
#   study.sh run <task> <model> <claude-code|codex> <port> [timeout_s=5400]
#   study.sh status
set -uo pipefail
cd "$(dirname "$0")/.."            # ~/cybergym-bench
mkdir -p runs/study1
MK=$(cat runs/.master_key)
gw() { docker network inspect cybergym-internal --format '{{(index .IPAM.Config 0).Gateway}}' 2>/dev/null; }
case "${1:-}" in
  shim-start)
    MODEL="$2"; PORT="$3"; ORDER="$4"; USD="$5"; TOTAL="$6"; GW=$(gw); [ -n "$GW" ] || { echo "start the firewall first"; exit 1; }
    [ "$(stat -c %a runs/.openrouter_key)" = "600" ] || { echo "runs/.openrouter_key must be mode 600"; exit 1; }
    [ "$ORDER" = "-" ] && ORDER=""
    PRICES=$(curl -s -m 20 https://openrouter.ai/api/v1/models | MODEL="$MODEL" python3 -c "
import sys,json,os
m=[x for x in json.load(sys.stdin)['data'] if x['id']==os.environ['MODEL']]
if not m: sys.exit('model not found on OpenRouter: '+os.environ['MODEL'])
p=m[0]['pricing']; pin=float(p['prompt'])*1e6; pout=float(p['completion'])*1e6
cache=float(p['input_cache_read'])*1e6 if p.get('input_cache_read') not in (None,'') else pin
print(pin,cache,pout)") || { echo "$PRICES"; exit 1; }
    set -- $PRICES; PIN=$1; PCACHE=$2; POUT=$3
    TAG=$(echo "$MODEL" | tr '/:' '__')
    [ -f runs/study1/shim_$PORT.pid ] && kill "$(cat runs/study1/shim_$PORT.pid)" 2>/dev/null; sleep 1
    echo "model=$MODEL port=$PORT order=${ORDER:-default} USD/M: in=$PIN cache=$PCACHE out=$POUT caps: \$$USD/run \$$TOTAL total"
    PROVIDER_ORDER="$ORDER" MASTER_KEY=$MK TARGET_MODEL="$MODEL" BIND=$GW PORT=$PORT UPSTREAM=https://openrouter.ai/api UPSTREAM_KEY_FILE=runs/.openrouter_key \
      UPSTREAM_AUTH=bearer PRICE_IN_PER_M=$PIN PRICE_CACHE_PER_M=$PCACHE PRICE_OUT_PER_M=$POUT MAX_SPEND_USD=$USD MAX_TOTAL_SPEND_USD=$TOTAL \
      MAX_REQUESTS="${MAX_REQUESTS:-3000}" MAX_INPUT_TOKENS="${MAX_INPUT_TOKENS:-30000000}" MAX_CACHE_TOKENS="${MAX_CACHE_TOKENS:-300000000}" \
      LOG_FILE=runs/study1/shim_${PORT}_${TAG}.log nohup python3 shim/llm_shim.py > runs/study1/shim_${PORT}.out 2>&1 < /dev/null &
    echo $! > runs/study1/shim_$PORT.pid; sleep 2; cat runs/study1/shim_$PORT.out ;;
  vidoc-shim-start)
    # Vidoc-1 (GLM-5.3 based) free endpoint. Quota is TOKENS, not dollars: prompt + output count 1, cached prompt counts 0.5.
    # So the shim's "USD" accounting is run with prices in=1, cache=0.5, out=1 and the caps are in million quota tokens.
    #   study.sh vidoc-shim-start <port> <cap_per_run_Mtok> <cap_total_Mtok>
    PORT="$2"; USD="$3"; TOTAL="$4"; GW=$(gw); [ -n "$GW" ] || { echo "start the firewall first"; exit 1; }
    [ "$(stat -c %a runs/.vidoc_key)" = "600" ] || { echo "runs/.vidoc_key must exist with mode 600"; exit 1; }
    [ -f runs/study1/shim_$PORT.pid ] && kill "$(cat runs/study1/shim_$PORT.pid)" 2>/dev/null; sleep 1
    echo "vidoc-1 port=$PORT quota units (Mtok): in=1 cache=0.5 out=1 caps: $USD/run $TOTAL total"
    MASTER_KEY=$MK TARGET_MODEL=vidoc-1 BIND=$GW PORT=$PORT UPSTREAM=https://model.vidocsecurity.com UPSTREAM_KEY_FILE=runs/.vidoc_key \
      UPSTREAM_AUTH=bearer PRICE_IN_PER_M=1 PRICE_CACHE_PER_M=0.5 PRICE_OUT_PER_M=1 MAX_SPEND_USD=$USD MAX_TOTAL_SPEND_USD=$TOTAL \
      COUNT_CACHE_CREATION=1 MAX_REQUESTS=3000 MAX_INPUT_TOKENS=300000000 MAX_CACHE_TOKENS=3000000000 UPSTREAM_TIMEOUT_STREAM=400 UPSTREAM_TIMEOUT=600 \
      LOG_FILE=runs/study1/shim_${PORT}_vidoc-1.log nohup python3 shim/llm_shim.py > runs/study1/shim_${PORT}.out 2>&1 < /dev/null &
    echo $! > runs/study1/shim_$PORT.pid; sleep 2; cat runs/study1/shim_$PORT.out ;;
  shim-stop)
    for f in runs/study1/shim_${2/all/*}.pid; do [ -f "$f" ] && kill "$(cat $f)" 2>/dev/null && rm -f "$f"; done; echo stopped ;;
  run)
    TASK="$2"; MODEL="$3"; AGENT="$4"; PORT="$5"; TO="${6:-5400}"; GW=$(gw)
    [ -n "$GW" ] || { echo "start the firewall first"; exit 1; }
    curl -s -m 5 "http://$GW:$PORT/health" | grep -q '"ok": true' || { echo "shim not answering on $GW:$PORT"; exit 1; }
    export LITELLM_BASE_URL=http://$GW:$PORT LITELLM_MASTER_KEY=$MK
    # One output folder per model AND harness: run_agent.py names a run dir by the start second only, so two runs of the
    # same task started in the same second would otherwise share one dir (and one /output folder).
    OUT="../runs/study1/agent_output/$(echo "$MODEL" | tr '/:' '__')/$AGENT"; mkdir -p "$OUT"
    cd cybergym-e2e
    ../.venv/bin/python scripts/run_agent.py "$TASK" --mode e2e --agent "$AGENT" \
      --model-provider litellm --litellm-model-id "$MODEL" --timeout "$TO" --agent-output "$OUT" ;;
  status)
    GW=$(gw); echo "gateway=$GW"
    for f in runs/study1/shim_*.pid; do [ -f "$f" ] || continue; p=$(basename $f .pid | sed s/shim_//); echo "port $p: $(curl -s -m 5 http://$GW:$p/health | cut -c1-200)"; done ;;
  *) sed -n 2,8p "$0" ;;
esac
