#!/usr/bin/env bash
# Guardrail: list instances tagged project=benchmark-ray with state and uptime;
# --stop-older-than HOURS stops running ones older than that (stop, never terminate).
set -euo pipefail
REGION=${REGION:-us-east-1}
LIMIT=""
[[ "${1:-}" == "--stop-older-than" ]] && LIMIT="${2:?hours}"
rows=$(aws ec2 describe-instances --region "$REGION" \
  --filters Name=tag:project,Values=benchmark-ray Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType,LaunchTime,Tags[?Key==`Name`]|[0].Value]' --output text)
[[ -z "$rows" ]] && { echo "no tagged instances"; exit 0; }
now=$(date -u +%s)
stop_ids=()
while IFS=$'\t' read -r id state type launch name; do
  age_h=$(python3 -c "import datetime,sys;print(round((${now}-datetime.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00')).timestamp())/3600,1))" "$launch")
  printf '%-20s %-9s %-12s up %5sh  %s\n' "$id" "$state" "$type" "$age_h" "${name:-}"
  if [[ -n "$LIMIT" && "$state" == "running" ]] && python3 -c "import sys;sys.exit(0 if float(sys.argv[1])>float(sys.argv[2]) else 1)" "$age_h" "$LIMIT"; then stop_ids+=("$id"); fi
done <<<"$rows"
if ((${#stop_ids[@]})); then
  echo "stopping: ${stop_ids[*]}"
  aws ec2 stop-instances --region "$REGION" --instance-ids "${stop_ids[@]}" --query 'StoppingInstances[].[InstanceId,CurrentState.Name]' --output text
fi
