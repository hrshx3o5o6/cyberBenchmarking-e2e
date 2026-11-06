#!/bin/bash
# exits on: driver done, non-200 status, token older than 50 min, collapse (2 consecutive 5-min buckets with overhead median over 15 s and 3+ tasks calling), 3 failed ssh polls
SSH="ssh -i $HOME/.ssh/id_ed25519 -o BatchMode=yes -o ConnectTimeout=20 ${VM_HOST:?set VM_HOST=user@host}"
bad=0
while true; do
  out=$($SSH 'python3 ~/qwen_conc_monitor.py 2>&1 | cut -c1-300; echo TOKAGE=$(( $(date +%s) - $(stat -c %Y ~/.secrets/vertex_token) )); tail -2 ~/cybergym-work/qwen-conc2-driver.log | grep -c "EXIT=" || true' 2>&1)
  if [ $? -ne 0 ]; then bad=$((bad+1)); [ $bad -ge 3 ] && { echo "SSH FAILED x3"; exit 1; }; sleep 60; continue; fi
  bad=0; echo "$out" > ${OUT:-.}/conc_last.txt
  echo "$out" | tail -1 | grep -q "^1$" && { echo "DRIVER DONE"; echo "$out"; exit 0; }
  echo "$out" | head -1 | grep -qE "statuses \{[^}]*[45][0-9]{2}:" && { echo "NON-200"; echo "$out"; exit 0; }
  age=$(echo "$out" | sed -n 's/.*TOKAGE=//p'); [ -n "$age" ] && [ "$age" -gt 3000 ] && { echo "TOKEN STALE $age"; echo "$out"; exit 0; }
  c=$(echo "$out" | awk -F'|' '/^ *[0-9]+ \(/ {split($4,a,"/"); if ($2+0>=3 && a[1]+0>15) n++; else n=0} END{print n+0}')
  [ "$c" -ge 2 ] && { echo "COLLAPSE (2 buckets over 15 s with 3+ tasks)"; echo "$out"; exit 0; }
  sleep 300
done
