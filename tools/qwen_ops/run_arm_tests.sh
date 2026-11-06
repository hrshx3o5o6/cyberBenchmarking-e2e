#!/bin/bash
# usage: QWEN_ENV=<env file> OUT=<results dir> run_arm_tests2.sh <label>   (agents counts run one at a time; stops at the first count whose later calls average over 20 s)
set -u
. "${QWEN_ENV:?file exporting QWEN_PROJECT_NUMBER, QWEN_REGION, QWEN_ENDPOINT_ID}"
L=$1; D=${OUT:-.}/$L; mkdir -p $D
P="python3 -I $(dirname $0)/../qwen_endpoint_probe.py"
date -u +%T > $D/started
$P decode > $D/decode.log 2>&1
$P residency --tokens 30000 --count 24 > $D/residency30.log 2>&1
$P residency --tokens 59000 --count 12 > $D/residency59.log 2>&1
$P needle --tokens 90000 --trials 6 > $D/needle.log 2>&1
: > $D/agents.log
for n in 3 4 5 6 8; do
  $P agents --counts $n --turns 10 >> $D/agents.log 2>&1
  m=$(tail -1 $D/agents.log | sed -n 's/.*later calls mean \([0-9.]*\)s.*/\1/p')
  [ -z "$m" ] && break
  python3 -c "import sys; sys.exit(0 if float('$m') < 20 else 1)" || break
done
date -u +%T > $D/finished
echo ALLDONE
