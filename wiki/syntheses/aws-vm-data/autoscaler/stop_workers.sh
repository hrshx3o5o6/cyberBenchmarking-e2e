#!/usr/bin/env bash
# Stop (default) or terminate ONLY the autoscaler's worker nodes. Replacement for `ray down`, which would
# also stop the tagged head VM. Dry run unless --yes is given.
#
# A node is selected only if ALL of these tags match (EC2 filters are ANDed):
#   ray-cluster-name=<cluster>   ray-node-type=worker   project=benchmark-ray
# so the head (ray-node-type=head), untagged instances and other people's VMs can never match.
#
# Order matters: stop the driver and the Ray head's autoscaler FIRST (e.g. `ray stop` on the head, or set
# max_workers to 0), otherwise the autoscaler sees demand/min_workers and starts workers again.
#
# usage: stop_workers.sh [--yes] [--terminate] [--max N]      env: REGION (us-east-1), CLUSTER (benchmark-ray)
set -euo pipefail
REGION=${REGION:-us-east-1}
CLUSTER=${CLUSTER:-benchmark-ray}
YES=0; ACTION=stop; MAXN=10
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1 ;;
    --terminate) ACTION=terminate ;;
    --max) MAXN="${2:?number}"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

rows=$(aws ec2 describe-instances --region "$REGION" \
  --filters "Name=tag:ray-cluster-name,Values=${CLUSTER}" "Name=tag:ray-node-type,Values=worker" \
            "Name=tag:project,Values=benchmark-ray" \
            "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].[InstanceId,State.Name,InstanceType,LaunchTime]' --output text)
if [[ -z "$rows" ]]; then echo "no worker nodes for cluster '${CLUSTER}'"; exit 0; fi

ids=()
while IFS=$'\t' read -r id state type launch; do
  printf '%-20s %-9s %-12s launched %s\n' "$id" "$state" "$type" "$launch"
  if [[ "$ACTION" == stop ]]; then
    [[ "$state" == running ]] && ids+=("$id")                       # stopped: nothing to do
    [[ "$state" == pending ]] && echo "  (pending: EC2 cannot stop it yet; rerun in a minute)" >&2
  else
    [[ "$state" == running || "$state" == stopped ]] && ids+=("$id")   # terminate: running or stopped
    [[ "$state" == pending ]] && echo "  (pending: rerun in a minute)" >&2
  fi
done <<<"$rows"

if ((${#ids[@]} == 0)); then echo "nothing to ${ACTION}"; exit 0; fi
if ((${#ids[@]} > MAXN)); then echo "refusing: ${#ids[@]} nodes match, more than --max ${MAXN}" >&2; exit 1; fi

verb="${ACTION}-instances"
echo "would ${ACTION}: ${ids[*]}"
# always ask EC2 first whether the call would be allowed (no side effects)
out=$(aws ec2 "$verb" --region "$REGION" --instance-ids "${ids[@]}" --dry-run 2>&1 || true)
if ! grep -q DryRunOperation <<<"$out"; then echo "dry-run check failed:" >&2; echo "$out" >&2; exit 1; fi
if ((YES == 0)); then echo "dry run only: add --yes to do it"; exit 0; fi
aws ec2 "$verb" --region "$REGION" --instance-ids "${ids[@]}" \
  --query '*[].[InstanceId,CurrentState.Name]' --output text
