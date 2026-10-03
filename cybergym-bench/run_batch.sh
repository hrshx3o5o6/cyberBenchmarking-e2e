#!/bin/bash
# Queue runner for the Azure VM. Runs tasks N at a time; each task does patch-only THEN e2e.
#   ./run_batch.sh <model> <parallel> <task> [<task> ...]        (add DRY=1 to only print the plan)
# Needs: firewall up and shim started with ./run_linux.sh start-shim-openrouter <model> ...
# Logs: runs/batch_<task>_<mode>.log   Results: runs/agent_output/  (collect_results.py)
set -uo pipefail
cd "$(dirname "$0")"
MODEL="$1"; PAR="$2"; shift 2
TASKS=("$@")
[ ${#TASKS[@]} -gt 0 ] || { echo "no tasks given"; exit 1; }
one_task() {
  local task="$1" tag; tag=$(echo "$task" | tr '/' '_')
  for mode in patch-only e2e; do
    echo "[$(date +%H:%M:%S)] START $task $mode"
    ./run_linux.sh run "$task" "$mode" "$MODEL" 5400 > "runs/batch_${tag}_${mode}.log" 2>&1
    echo "[$(date +%H:%M:%S)] DONE  $task $mode exit=$? -> $(grep -E 'Attempt 1:' "runs/batch_${tag}_${mode}.log" | tail -1 | sed 's/^ *//')"
  done
}
export -f one_task; export MODEL
echo "model=$MODEL parallel=$PAR tasks=${TASKS[*]}"
if [ "${DRY:-0}" = "1" ]; then
  for t in "${TASKS[@]}"; do echo "would run: $t patch-only, then e2e"; done; exit 0
fi
printf '%s\n' "${TASKS[@]}" | xargs -P "$PAR" -I{} bash -c 'one_task {}' 2>&1 | tee -a runs/batch_progress.log
echo "[$(date +%H:%M:%S)] BATCH FINISHED"
